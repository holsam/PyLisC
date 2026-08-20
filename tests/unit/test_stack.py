'''
PyLisC: unit tests for stack-mode processing
'''

# Import external libraries
import pytest

# Import internal functions
from pylisc.stack import _process_series, run_stack

class TestProcessSeries:
    def test_explicit_pixel_size_overrides_header(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=2, angle_deg=20))
        out_path = tmp_path / 'out.mrc'

        angle = _process_series(
            input_path, out_path, mode='angular', apply_filter=False,
            filter_threshold=5000.0, pixel_size=0.5, curtain_angle=20.0,
            reference_frame=0, angular_width=8.0, notch_frac=0.02,
            dc_protect_frac=0.01, force=False, dry_run=False,
        )
        assert angle == pytest.approx(20.0)
        assert out_path.exists()

    def test_invalid_pixel_size_raises(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=2, angle_deg=20))
        out_path = tmp_path / 'out.mrc'

        with pytest.raises(ValueError, match='Pixel size cannot be'):
            _process_series(
                input_path, out_path, mode='angular', apply_filter=False,
                filter_threshold=5000.0, pixel_size=0.0, curtain_angle=20.0,
                reference_frame=0, angular_width=8.0, notch_frac=0.02,
                dc_protect_frac=0.01, force=False, dry_run=False,
            )

    def test_explicit_curtain_angle_skips_estimation(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=2, angle_deg=20))
        out_path = tmp_path / 'out.mrc'

        angle = _process_series(
            input_path, out_path, mode='angular', apply_filter=False,
            filter_threshold=5000.0, pixel_size=0.34, curtain_angle=33.0,
            reference_frame=0, angular_width=8.0, notch_frac=0.02,
            dc_protect_frac=0.01, force=False, dry_run=False,
        )
        assert angle == 33.0

class TestRunStackBatch:
    def test_no_series_found_raises(self, tmp_path):
        import typer
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'

        with pytest.raises(typer.BadParameter, match='No tilt series found'):
            run_stack(
                input_path=input_dir, output_mrc=None, output_dir=output_dir,
                mode='angular', apply_filter=False, filter_threshold=5000.0,
                pixel_size=None, curtain_angle=None, reference_frame=None,
                angular_width=8.0, notch_frac=0.02, dc_protect_frac=0.01,
                angle_outlier_threshold=5.0, force=False, dry_run=False, workers=0,
            )

    def test_batch_one_bad_file_does_not_abort_others(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        # mirrors tests/integration/test_cli.py::TestCliBatch, but checks a corrupt file fails in-process while its sibling still completes
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'
        write_synthetic_mrc(input_dir / 'good.mrc', synthetic_tilt_series(n_tilts=3, angle_deg=20))
        (input_dir / 'bad.mrc').write_bytes(b'not a real mrc file')

        run_stack(
            input_path=input_dir, output_mrc=None, output_dir=output_dir,
            mode='angular', apply_filter=False, filter_threshold=5000.0,
            pixel_size=None, curtain_angle=None, reference_frame=None,
            angular_width=8.0, notch_frac=0.02, dc_protect_frac=0.01,
            angle_outlier_threshold=5.0, force=False, dry_run=False, workers=1,
        )
        assert (output_dir / 'good_PyLisC_angular.mrc').exists()
