'''
PyLisC: unit tests for stack-mode processing
'''

# Import external libraries
import numpy as np, pytest

# Import internal functions
from pylisc.log import logger
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
            dc_protect_frac=0.01, angle_outlier_threshold=5.0, anchor_tilts=5,
            force=False, dry_run=False,
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
                dc_protect_frac=0.01, angle_outlier_threshold=5.0, anchor_tilts=5,
                force=False, dry_run=False,
            )

    def test_explicit_curtain_angle_skips_estimation(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=2, angle_deg=20))
        out_path = tmp_path / 'out.mrc'

        angle = _process_series(
            input_path, out_path, mode='angular', apply_filter=False,
            filter_threshold=5000.0, pixel_size=0.34, curtain_angle=33.0,
            reference_frame=0, angular_width=8.0, notch_frac=0.02,
            dc_protect_frac=0.01, angle_outlier_threshold=5.0, anchor_tilts=5,
            force=False, dry_run=False,
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
                angle_outlier_threshold=5.0, anchor_tilts=5, force=False, dry_run=False, workers=0,
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
            angle_outlier_threshold=5.0, anchor_tilts=5, force=False, dry_run=False, workers=1,
        )
        assert (output_dir / 'good_PyLisC_angular.mrc').exists()

    def test_confidence_spike_does_not_skew_batch_consensus(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        import re
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'
        # three ordinary low-tilt series striped at 20deg, with slightly different noise so their confidences aren't identical
        write_synthetic_mrc(input_dir / 'low_a.mrc', synthetic_tilt_series(n_tilts=2, angle_deg=20, noise_std=5.0))
        write_synthetic_mrc(input_dir / 'low_b.mrc', synthetic_tilt_series(n_tilts=2, angle_deg=20, noise_std=6.0))
        write_synthetic_mrc(input_dir / 'low_c.mrc', synthetic_tilt_series(n_tilts=2, angle_deg=20, noise_std=4.5))
        # a single series with a much sharper (higher-confidence) peak at a wildly different angle
        write_synthetic_mrc(input_dir / 'spike.mrc', synthetic_tilt_series(n_tilts=2, angle_deg=-60, amplitude=600.0, noise_std=1.0))

        messages = []
        sink_id = logger.add(messages.append, level='INFO')
        try:
            run_stack(
                input_path=input_dir, output_mrc=None, output_dir=output_dir,
                mode='angular', apply_filter=False, filter_threshold=5000.0,
                pixel_size=None, curtain_angle=None, reference_frame=None,
                angular_width=8.0, notch_frac=0.02, dc_protect_frac=0.01,
                angle_outlier_threshold=5.0, anchor_tilts=5, force=False, dry_run=False, workers=1,
            )
        finally:
            logger.remove(sink_id)

        match = next(re.search(r'batch consensus angle: (-?\d+\.\d+)°', str(m)) for m in messages if 'batch consensus angle' in str(m))
        consensus = float(match.group(1))
        # the low-tilt cluster (3 files) should still pull the consensus closer to itself than to the single spiky outlier
        assert abs(consensus - 20.0) < abs(consensus - (-60.0))


class TestEstimatePerFrameAngles:
    def test_smooth_drift_uses_each_frame_own_estimate(self, tmp_path, synthetic_frame):
        from pylisc.stack import _estimate_per_frame_angles
        drift = [10, 12, 14, 16, 18]
        stack = np.stack([synthetic_frame(angle_deg=a, seed=i) for i, a in enumerate(drift)])
        resolved = _estimate_per_frame_angles(
            tmp_path / 'series.mrc', stack, resolved_reference_frame=2,
            angle_outlier_threshold=5.0, anchor_tilts=3, output_dir=tmp_path, dry_run=True,
        )
        for i, expected in enumerate(drift):
            assert resolved[i] == pytest.approx(expected, abs=2.0)

    def test_outlier_frame_falls_back_to_nearest_resolved(self, tmp_path, synthetic_frame):
        from pylisc.stack import _estimate_per_frame_angles
        angles = [50, 50, 50, 50, 50, -40]
        stack = np.stack([synthetic_frame(angle_deg=a, seed=i) for i, a in enumerate(angles)])

        messages = []
        sink_id = logger.add(messages.append, level='WARNING')
        try:
            resolved = _estimate_per_frame_angles(
                tmp_path / 'series.mrc', stack, resolved_reference_frame=2,
                angle_outlier_threshold=5.0, anchor_tilts=3, output_dir=tmp_path, dry_run=True,
            )
        finally:
            logger.remove(sink_id)

        assert resolved[5] == pytest.approx(50.0, abs=2.0)
        assert any('deviates' in str(m) and 'nearest resolved angle' in str(m) for m in messages)


class TestProcessSeriesPerFrame:
    def test_estimation_applies_per_frame_not_one_shared_angle(self, tmp_path, synthetic_frame, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        stack = np.stack([synthetic_frame(angle_deg=a, seed=i) for i, a in enumerate([10, 12, 14, 16, 18])])
        write_synthetic_mrc(input_path, stack)
        out_path = tmp_path / 'out.mrc'

        angle = _process_series(
            input_path, out_path, mode='angular', apply_filter=False,
            filter_threshold=5000.0, pixel_size=0.34, curtain_angle=None,
            reference_frame=2, angular_width=8.0, notch_frac=0.02,
            dc_protect_frac=0.01, angle_outlier_threshold=5.0, anchor_tilts=3,
            force=False, dry_run=False,
        )
        assert angle == pytest.approx(14.0, abs=2.0)
        assert out_path.exists()
