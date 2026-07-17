'''
PyLisC: apply blurring, masking, and destriping to a single 2D projection
'''

# Import external libraries
import numpy as np
from scipy import ndimage as ndi

# Import internal PyLisC libraries
from blur import bandpass_highpass
from destripe import directional_destripe
from mask import compute_masks

def lisc_clear_frame(
    frame: np.ndarray,
    pixel_size_nm: float,
    curtain_angle: float = 0.0,
    filter_threshold_nm: float = 5000.0,
    contaminant_multiplier: float = 1.5,
    vacuum_multiplier: float = 1.5,
    dilate_iterations: int = 4,
    destripe_notch_fraction: float = 0.02,
    dc_protect_frac: float = 0.01,
    clear_vacuum: bool = False,
    clear_contamination: bool = False,
    fill_sigma_nm: float = None,
):
    '''
    Apply the LisC pipeline to a single 2D projection
    '''
    frame = frame.astype(np.float32)
    filter_px = max(filter_threshold_nm / pixel_size_nm, 1.0)
    sigma_masks = max(6.5 / pixel_size_nm, 0.5)
    fill_nm = fill_sigma_nm if fill_sigma_nm is not None else filter_threshold_nm
    fill_px = max(fill_nm / pixel_size_nm, 1.0)

    hp = bandpass_highpass(frame, filter_px)

    masks = {}
    if clear_vacuum:
        # Vacuum: bright, low-frequency regions of the raw frame
        vac_blur = ndi.gaussian_filter(frame, sigma=sigma_masks)
        vac_raw = threshold_mask(vac_blur, vacuum_multiplier, greater=True)
        masks["vacuum_mask"] = ndi.binary_dilation(vac_raw, iterations=dilate_iterations)
    if clear_contamination:
        # Contamination: dark, low-frequency regions of the HP-filtered frame
        con_blur = ndi.gaussian_filter(hp, sigma=sigma_masks)
        con_raw = threshold_mask(con_blur, contaminant_multiplier, greater=False)
        masks["contamination_mask"] = ndi.binary_dilation(con_raw, iterations=dilate_iterations)

    cleared = hp
    if masks:
        excluded = np.zeros(frame.shape, dtype=bool)
        for region in masks.values():
            excluded |= region

        # Normalised convolution: local mean of valid pixels only, so the masked content does not contaminate the value used to replace it.
        # Filling with a neutral local mean (rather than 255/0) keeps the output free of extreme outliers that would otherwise dominate the display range and any downstream intensity scaling.
        valid = (~excluded).astype(np.float32)
        numer = gaussian_blur_fft(hp * valid, fill_px)
        denom = gaussian_blur_fft(valid, fill_px)
        local_neutral = numer / np.maximum(denom, 1e-6)
        cleared = np.where(excluded, local_neutral, hp)

    # Remove curtaining artefacts in Fourier space, at the given angle
    cleared = directional_destripe(cleared, notch_frac=destripe_notch_fraction, angle_deg=curtain_angle, dc_protect_frac=dc_protect_frac)

    return cleared.astype(np.float32), masks