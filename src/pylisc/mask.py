'''
PyLisC: contamination and vacuum mask thresholding
'''

# Import external libraries
import numpy as np
from scipy import ndimage as ndi

def threshold_mask(blurred: np.ndarray, mult: float, greater: bool) -> np.ndarray:
    mean, std = blurred.mean(), blurred.std()
    thr = mean + mult * std if greater else mean - mult * std
    return (blurred >= thr) if greater else (blurred < thr)

def compute_masks(
    frame: np.ndarray,
    hp: np.ndarray,
    sigma_masks: float,
    vacuum_multiplier: float,
    contaminant_multiplier: float,
    dilate_iterations: int,
) -> dict:
    '''
    Build vacuum and contamination masks used to fill curtaining-cleared frames before destriping
    '''
    # Vacuum mask: bright, low-frequency regions of the raw frame
    vac_blur = ndi.gaussian_filter(frame, sigma=sigma_masks)
    vac_raw = threshold_mask(vac_blur, vacuum_multiplier, greater=True)
    vacuum_region = ndi.binary_dilation(vac_raw, iterations=dilate_iterations)
    # Contamination mask: dark, low-frequency regions of the HP-filtered frame
    con_blur = ndi.gaussian_filter(hp, sigma=sigma_masks)
    con_raw = threshold_mask(con_blur, contaminant_multiplier, greater=False)
    contamination_region = ndi.binary_dilation(con_raw, iterations=dilate_iterations)
    # Return masks
    return {"vacuum_mask": vacuum_region, "contamination_mask": contamination_region}