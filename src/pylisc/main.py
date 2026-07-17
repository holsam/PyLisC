'''
PyLisC
'''

###########
# INITIALISATION
##########

# Import from stdlib
from pathlib import Path
from typing import Annotated, Optional

# Import from non-stdlib
try:
    import mrcfile, numpy as np, scipy.fft as sfft, typer
    from scipy import ndimage as ndi
except ImportError as e:
    raise ImportError('PyLisC requirements not met. Please see README for information.')

###########
# CLI INTERFACE
##########
pylisc = typer.Typer()

@pylisc.command()
def main(
    input_mrc: Annotated[
        Path,
        typer.Argument(help='MRC file to apply LisC algorithm to')
    ],
    output_mrc: Annotated[
        Optional[Path],
        typer.Argument(help='Path to output MRC file (defaults to the same filename as input_mrc with _LisC suffix)')
    ] = None,
    curtain_angle: Annotated[
        float,
        typer.Option('--angle', help='Angle of curtaining from horizontal (0°)')
    ] = 0.0,
    save_masks: Annotated[
        Optional[Path],
        typer.Option('--masks', help='Path to directory to save per-frame vacuum/contamination masks as TIFF images')
    ] = None,
    pixel_size: Annotated[
        Optional[float],
        typer.Option('--pixel-size', help='Override pixel size (nm) read from MRC header')
    ] = None,
    filter_threshold: Annotated[
        float,
        typer.Option('--filter-threshold', help='High-pass cutoff (nm)')
    ] = 5000.0,
    con_mult: Annotated[
        float,
        typer.Option('--con-multiplier', help='Contaminant threshold multiplier on blurred SD')
    ] = 1.5,
    vac_mult: Annotated[
        float,
        typer.Option('--vac-multiplier', help='Vacuum threshold multiplier on blurred SD')
    ] = 1.5,
    dilate_iter: Annotated[
        int,
        typer.Option('--iters', help='Binary dilation iterations for masking')
    ] = 4,
    notch_frac: Annotated[
        float,
        typer.Option('--notch-fraction', help='Width of the directional destriping notch as a fraction of image width')
    ] = 0.03,
    verbose: Annotated[
        bool,
        typer.Option('-v', '--verbose', help='Print additional progress messages')
    ] = False,
):
    # Set output file path if none provided
    if output_mrc is None:
        output_mrc = f'{input_mrc.parents[0]}/{input_mrc.stem}_LisC.mrc'

    # Read data from input_mrc
    with mrcfile.open(input_mrc, permissive=True) as mrc:
        data = mrc.data.astype(np.float32)
        voxel_size = mrc.voxel_size # in Ångstroms
    if data.ndim == 2:
        data = data[np.newaxis, ...]

    # Resolve pixel size
    if pixel_size is None:
        pixel_size = float(voxel_size.x) / 10.0
    if pixel_size <= 0:
        raise ValueError('Pixel size cannot be less than or equal to 0')

    # Create save masks directory if required
    if save_masks is not None:
        save_masks.mkdir(parents=True, exist_ok=True)

    # Create placeholder for cleared frames
    cleared_stack = np.empty_like(data, dtype=np.float32)

    # Output processing information if verbose
    if verbose:
        print()
        print(f'Input file: {input_mrc}')
        print(f'Output file: {output_mrc}')
        print(f'Voxel size: {voxel_size}')
        print(f'Pixel size: {pixel_size}')
        print()

    # Apply LisC to each frame
    for i, frame in enumerate(data):
        if verbose:
            print(f'Processing tilt {i+1}/{data.shape[0]}')
        cleared, masks = lisc_clear_frame(
            frame,
            curtain_angle=curtain_angle,
            pixel_size_nm=pixel_size,
            filter_threshold_nm=filter_threshold,
            contaminant_multiplier=con_mult,
            vacuum_multiplier=vac_mult,
            dilate_iterations=dilate_iter,
            destripe_notch_fraction=notch_frac,
        )
        cleared_stack[i] = cleared
        if save_masks is not None:
            import tifffile
            tifffile.imwrite(save_masks / f"tilt_{i:03d}_vacuum.tif", masks["vacuum_mask"].astype(np.uint8) * 255)
            tifffile.imwrite(save_masks / f"tilt_{i:03d}_contamination.tif", masks["contamination_mask"].astype(np.uint8) * 255)
        print(f'Processed tilt {i+1}/{data.shape[0]}')

    # Save output MRC
    with mrcfile.new(output_mrc, overwrite=True) as out:
        out.set_data(cleared_stack.astype(np.float32))
        out.voxel_size = voxel_size
    
###########
# LisC FUNCTIONS
##########
def gaussian_blur_fft(frame: np.ndarray, sigma: float) -> np.ndarray:
    '''
    FFT-based Gaussian blur
    '''
    ny, nx = frame.shape
    fy = np.fft.fftfreq(ny)
    fx = np.fft.rfftfreq(nx)
    fyy, fxx = np.meshgrid(fy, fx, indexing="ij")
    kernel = np.exp(-2 * (np.pi ** 2) * (sigma ** 2) * (fxx ** 2 + fyy ** 2)).astype(np.float32)
    spectrum = sfft.rfft2(frame, workers=-1)
    return sfft.irfft2(spectrum * kernel, s=frame.shape, workers=-1)

def bandpass_highpass(frame: np.ndarray, sigma_large: float) -> np.ndarray:
    '''
    Remove large-scale brightness modulation (proxy for ImageJ Bandpass Filter, filter_large cutoff)
    '''
    low = gaussian_blur_fft(frame, sigma=sigma_large)
    return frame - low

def directional_destripe(frame: np.ndarray, notch_frac: float = 0.02, angle_deg: float = 0.0) -> np.ndarray:
    '''
    Attenuate the Fourier-space line corresponding to stripes running at `angle_deg` from horizontal (0 = horizontal curtaining, ImageJ's suppress=Horizontal case).
    For stripes constant along direction u=(cosθ, sinθ), Fourier support lies on the line through the origin which is perpendicular to u so points are attenuated by projection onto u.
    '''
    f = np.fft.fftshift(np.fft.fft2(frame))
    ny, nx = frame.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    cy, cx = ny // 2, nx // 2
    theta = np.deg2rad(angle_deg)
    proj = (xx - cx) * np.cos(theta) + (yy - cy) * np.sin(theta)
    width = max(nx * notch_frac, 1.0)
    notch = 1 - np.exp(-(proj ** 2) / (2 * width ** 2))
    notch[cy, cx] = 1.0  # preserve DC / mean intensity
    f_filtered = f * notch
    return np.real(np.fft.ifft2(np.fft.ifftshift(f_filtered)))

def threshold_mask(blurred: np.ndarray, mult: float, greater: bool) -> np.ndarray:
    mean, std = blurred.mean(), blurred.std()
    thr = mean + mult * std if greater else mean - mult * std
    return (blurred >= thr) if greater else (blurred < thr)

def lisc_clear_frame(
    frame: np.ndarray,
    pixel_size_nm: float,
    curtain_angle: float = 0.0,
    filter_threshold_nm: float = 5000.0,
    contaminant_multiplier: float = 1.5,
    vacuum_multiplier: float = 1.5,
    dilate_iterations: int = 4,
    destripe_notch_fraction: float = 0.02,
):
    '''
    Apply the LisC pipeline to a single 2D projection
    '''
    frame = frame.astype(np.float32)
    filter_px = max(filter_threshold_nm / pixel_size_nm, 1.0)
    sigma_masks = max(6.5 / pixel_size_nm, 0.5)

    hp = bandpass_highpass(frame, filter_px)

    # Vacuum mask: bright, low-frequency regions of the raw frame
    vac_blur = ndi.gaussian_filter(frame, sigma=sigma_masks)
    vac_raw = threshold_mask(vac_blur, vacuum_multiplier, greater=True)
    vacuum_region = ndi.binary_dilation(vac_raw, iterations=dilate_iterations)

    # Contamination mask: dark, low-frequency regions of the HP-filtered frame
    con_blur = ndi.gaussian_filter(hp, sigma=sigma_masks)
    con_raw = threshold_mask(con_blur, contaminant_multiplier, greater=False)
    contamination_region = ndi.binary_dilation(con_raw, iterations=dilate_iterations)

    # Fill contamination/vacuum with local gray-scale average before destriping
    local_gray = ndi.gaussian_blur_fft(hp, sigma=filter_px)
    cleared = hp.copy()
    cleared = np.where(contamination_region, local_gray, cleared)
    cleared = np.where(vacuum_region, local_gray, cleared)

    # Remove curtaining artefacts in Fourier space, at the given angle
    cleared = directional_destripe(cleared, notch_frac=destripe_notch_fraction, angle_deg=curtain_angle)

    # Reset vacuum to bright / contamination to zero for downstream masking
    cleared = np.where(vacuum_region, 255.0, cleared)
    cleared = np.where(contamination_region, 0.0, cleared)

    return cleared.astype(np.float32), {"vacuum_mask": vacuum_region, "contamination_mask": contamination_region}