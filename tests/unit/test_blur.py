'''
PyLisC: unit tests for FFT-based blur/high-pass filtering
'''

# Import external libraries
import numpy as np

# Import internal functions
from pylisc.blur import bandpass_highpass, gaussian_blur_fft

class TestBlur:
    def test_gaussian_blur_attenuates_fine_texture(self, synthetic_frame):
        frame = synthetic_frame(size=128, amplitude=0.0, noise_std=0.0)
        blurred = gaussian_blur_fft(frame, sigma=10.0)
        assert blurred.std() < frame.std()
        assert blurred.shape == frame.shape

    def test_gaussian_blur_zero_sigma_is_near_identity(self, synthetic_frame):
        frame = synthetic_frame(size=64, amplitude=0.0, noise_std=0.0)
        blurred = gaussian_blur_fft(frame, sigma=0.0)
        np.testing.assert_allclose(blurred, frame, rtol=1e-4, atol=1e-2)

    def test_bandpass_highpass_removes_large_scale_background(self):
        rng = np.random.default_rng(1)
        # large-scale ramp the high-pass should strip out
        yy, _ = np.mgrid[0:128, 0:128]
        background = (yy * 5.0).astype(np.float32)
        fine = rng.normal(0, 1, (128, 128)).astype(np.float32)
        frame = background + fine

        result = bandpass_highpass(frame, sigma_large=20.0)

        # mean/large-scale trend should be far smaller relative to the fine texture
        assert abs(result.mean()) < abs(frame.mean())
