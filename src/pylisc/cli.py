'''
PyLisC: command-line entry point
'''

# Import external libraries
from pathlib import Path
from typing import Annotated, Optional

try:
    import matplotlib, mrcfile, numpy, tifffile, typer
except ImportError as e:
    raise ImportError('PyLisC requirements not met. Please see README for information.') from e

# Import internal PyLisC modules
from estimate_angle import estimate_curtain_angle, plot_angular_energy
from pipeline import lisc_clear_frame

# Set up Typer class
pylisc = typer.Typer()

# Define command for pylisc
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
    verbose: Annotated[
        bool,
        typer.Option('-v', '--verbose', help='Print additional progress messages')
    ] = False,
    curtain_angle: Annotated[
        Optional[float],
        typer.Option('--angle', help='Angle of curtaining from horizontal (0°)')
    ] = None,
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

    # Estimate curtaining angle
    if curtain_angle is None:
        mid_frame = len(data) // 2
        curtain_angle, angular_energy = estimate_curtain_angle(data[mid_frame])
        plot_angular_energy(angular_energy, curtain_angle, output_dir=output_mrc.parent)
    else:
        angular_energy = None

    # Output processing information if verbose
    if verbose:
        print()
        print(f'Input file: {input_mrc}')
        print(f'Output file: {output_mrc}')
        print(f'Voxel size: {voxel_size}')
        print(f'Pixel size: {pixel_size}')
        print(f'{"Estimated c" if angular_energy is not None else "C"}urtaining angle: {curtain_angle}{f"°; confidence: {angular_energy.max/np.median(angular_energy)}" if angular_energy is not None else "°"}')
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
            tifffile.imwrite(save_masks / f"tilt_{i:03d}_vacuum.tif", masks["vacuum_mask"].astype(np.uint8) * 255)
            tifffile.imwrite(save_masks / f"tilt_{i:03d}_contamination.tif", masks["contamination_mask"].astype(np.uint8) * 255)
        print(f'Processed tilt {i+1}/{data.shape[0]}')

    # Save output MRC
    with mrcfile.new(output_mrc, overwrite=True) as out:
        out.set_data(cleared_stack.astype(np.float32))
        out.voxel_size = voxel_size