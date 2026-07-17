'''
PyLisC: directional destriping (curtaining removal) in Fourier space
'''

# Import external libraries
import numpy as np

def directional_destripe(
    frame: np.ndarray,
    notch_frac: float = 0.02,
    angle_deg: float = 0.0,
    dc_protect_frac: float = 0.01,
) -> np.ndarray:
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
    if dc_protect_frac > 0:
        # Fade the suppression out towards DC so low frequencies survive every angle to avoid effective high-pass filter
        r = np.sqrt((xx-cx) ** 2 + (yy-cy) ** 2)
        r_protect = max(nx * dc_protect_frac, 1.0)
        gate = 1 - np.exp(-(r ** 2) / (2 * r_protect ** 2))
        notch = 1 - (1 - notch) * gate
    notch[cy, cx] = 1.0  # preserve DC / mean intensity
    f_filtered = f * notch
    return np.real(np.fft.ifft2(np.fft.ifftshift(f_filtered)))
