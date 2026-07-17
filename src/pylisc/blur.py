'''
PyLisC: FFT-based Gaussian blur and high-pass filtering
'''

# Import external libraries
import numpy as np
import scipy.fft as sfft

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
