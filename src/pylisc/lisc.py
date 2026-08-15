'''
PyLisC: apply filtering and destriping to a single 2D projection
'''

# Import external libraries
import numpy as np
from scipy import ndimage as ndi
from typing import Optional

# Import internal PyLisC libraries
from pylisc.blur import bandpass_highpass
from pylisc.destripe import directional_destripe_angular, directional_destripe_linear

def lisc_clear_frame(
    frame: np.ndarray,
    decurtaining_mode: str,
    pixel_size_nm: Optional[float] = None,
    curtain_angle: float = 0.0,
    apply_filter: bool = False,
    filter_threshold_nm: float = 5000.0,
    angular_width_deg: float = 8.0,
    destripe_notch_fraction: float = 0.02,
    dc_protect_frac: float = 0.01,
):
    '''
    Apply the LisC pipeline to a single 2D projection
    '''
    frame = frame.astype(np.float32)

    # Apply high-pass filter if specified
    if apply_filter:
        if pixel_size_nm is None:
            raise ValueError('pixel_size_nm is required when apply_filter is set')
        filter_px = max(filter_threshold_nm / pixel_size_nm, 1.0)
        frame = bandpass_highpass(frame, filter_px)
    
    # Remove curtaining artefacts in Fourier space, at the given angle
    if decurtaining_mode == 'angular':
        cleared = directional_destripe_angular(frame, angle_deg=curtain_angle, angular_width_deg=angular_width_deg)
    elif decurtaining_mode == 'linear':
        cleared = directional_destripe_linear(frame, notch_frac=destripe_notch_fraction, angle_deg=curtain_angle, dc_protect_frac=dc_protect_frac)

    return cleared.astype(np.float32)