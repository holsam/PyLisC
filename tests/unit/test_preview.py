'''
PyLisC: unit tests for strength preview generation
'''

# Import internal functions
from pylisc.preview import generate_strength_preview

class TestGenerateStrengthPreview:
    def test_single_value_angular(self, tmp_path, synthetic_frame):
        frame = synthetic_frame(size=64, angle_deg=20)
        out_path = generate_strength_preview(
            frame, mode='angular', pixel_size_nm=0.34, values=[8.0],
            curtain_angle=20.0, apply_filter=False, filter_threshold_nm=5000.0,
            dc_protect_frac=0.01, notch_frac=0.02, output_dir=tmp_path,
        )
        assert out_path.exists()

    def test_linear_mode_multiple_values(self, tmp_path, synthetic_frame):
        frame = synthetic_frame(size=64, angle_deg=20)
        out_path = generate_strength_preview(
            frame, mode='linear', pixel_size_nm=0.34, values=[0.01, 0.05],
            curtain_angle=20.0, apply_filter=False, filter_threshold_nm=5000.0,
            dc_protect_frac=0.01, notch_frac=0.02, output_dir=tmp_path,
        )
        assert out_path.exists()
