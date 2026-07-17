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
):
    '''
    Apply the LisC pipeline to a single 2D projection
    '''
    frame = frame.astype(np.float32)
    filter_px = max(filter_threshold_nm / pixel_size_nm, 1.0)
    sigma_masks = max(6.5 / pixel_size_nm, 0.5)

    hp = bandpass_highpass(frame, filter_px)

    masks = compute_masks(
        frame, hp, sigma_masks, vacuum_multiplier, contaminant_multiplier, dilate_iterations
    )
    vacuum_region = masks["vacuum_mask"]
    contamination_region = masks["contamination_mask"]

    # Fill contamination/vacuum with local gray-scale average before destriping
    local_gray = gaussian_blur_fft(hp, sigma=filter_px)
    cleared = hp.copy()
    cleared = np.where(contamination_region, local_gray, cleared)
    cleared = np.where(vacuum_region, local_gray, cleared)

    # Remove curtaining artefacts in Fourier space, at the given angle
    cleared = directional_destripe(cleared, notch_frac=destripe_notch_fraction, angle_deg=curtain_angle)

    # Reset vacuum to bright / contamination to zero for downstream masking
    cleared = np.where(vacuum_region, 255.0, cleared)
    cleared = np.where(contamination_region, 0.0, cleared)

    return cleared.astype(np.float32), masks