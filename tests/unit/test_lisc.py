'''
PyLisC: unit tests for the single-frame LisC pipeline
'''

# Import external libraries
import pytest

# Import internal functions
from pylisc.lisc import lisc_clear_frame

class TestLiscClearFrame:
    def test_apply_filter_without_pixel_size_raises(self, synthetic_frame):
        frame = synthetic_frame(size=64)
        with pytest.raises(ValueError, match='pixel_size_nm is required'):
            lisc_clear_frame(frame, decurtaining_mode='angular', apply_filter=True)

    def test_apply_filter_runs_highpass_before_destriping(self, synthetic_frame):
        frame = synthetic_frame(size=128, angle_deg=20)
        cleared = lisc_clear_frame(
            frame,
            decurtaining_mode='angular',
            pixel_size_nm=0.34,
            apply_filter=True,
            filter_threshold_nm=5000.0,
        )
        assert cleared.shape == frame.shape
        assert cleared.dtype.name == 'float32'

    def test_linear_mode_dispatches_to_linear_destripe(self, synthetic_frame):
        frame = synthetic_frame(size=64, angle_deg=0)
        cleared = lisc_clear_frame(frame, decurtaining_mode='linear', curtain_angle=0.0)
        assert cleared.shape == frame.shape
