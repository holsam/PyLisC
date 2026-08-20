'''
PyLisC: unit tests for per-tilt curtain angle consensus and outlier fallback
'''

# Import external libraries
import pytest

# Import internal functions
from pylisc.frames import _estimate_per_tilt_angles
from pylisc.log import logger
from tests.fixtures import write_synthetic_frame

class TestEstimatePerTiltAngles:
    def test_overall_consensus_favors_low_tilt_over_high_tilt(self, tmp_path):
        paths, tilt_of = [], {}
        for i, tilt in enumerate([0, 1, 2]):
            path = tmp_path / f'low_{i}.mrc'
            write_synthetic_frame(path, angle_deg=20, seed=i)
            paths.append(path)
            tilt_of[path] = tilt
        for i, tilt in enumerate([60, 61, 62]):
            path = tmp_path / f'high_{i}.mrc'
            write_synthetic_frame(path, angle_deg=65, seed=10 + i)
            paths.append(path)
            tilt_of[path] = tilt
        resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=90.0)
        low_tilt_consensus = resolved[tmp_path / 'low_0.mrc']
        assert low_tilt_consensus == pytest.approx(20, abs=1.0)


    def test_walk_rejects_bucket_that_deviates_from_trusted_neighbor(self, tmp_path):
        paths, tilt_of = [], {}
        # a reliable run around the median tilt, all striped at 50deg
        for i, tilt in enumerate([-2, -1, 0, 1, 2]):
            path = tmp_path / f'good_{i}.mrc'
            write_synthetic_frame(path, angle_deg=50, seed=i)
            paths.append(path)
            tilt_of[path] = tilt
        # a lone bad estimate just past the seed window
        bad_path = tmp_path / 'bad.mrc'
        write_synthetic_frame(bad_path, angle_deg=-40, seed=42)
        paths.append(bad_path)
        tilt_of[bad_path] = 3

        messages = []
        sink_id = logger.add(messages.append, level='WARNING')
        try:
            resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=5.0, anchor_tilts=5)
        finally:
            logger.remove(sink_id)

        # falls back to the trusted (seed) angle, not its own wildly different estimate
        assert resolved[bad_path] == pytest.approx(50, abs=2.0)
        assert any('deviates' in str(m) and 'nearest resolved angle' in str(m) for m in messages)

    def test_confidence_spike_does_not_skew_overall_consensus(self, tmp_path):
        paths, tilt_of = [], {}
        # a consistent low-tilt cluster, all striped at 20deg with ordinary confidence
        for i, tilt in enumerate([-10, 0, 10]):
            path = tmp_path / f'low_{i}.mrc'
            write_synthetic_frame(path, angle_deg=20, seed=i)
            paths.append(path)
            tilt_of[path] = tilt
        # a single high-tilt frame with a much sharper peak at a wildly different angle
        spike_path = tmp_path / 'spike.mrc'
        write_synthetic_frame(spike_path, angle_deg=-60, seed=42, amplitude=600.0, noise_std=1.0)
        paths.append(spike_path)
        tilt_of[spike_path] = 50

        resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=5.0, anchor_tilts=5, output_dir=tmp_path)
        # the low-tilt cluster should still win the overall consensus, not be outvoted by the single spiky frame
        assert resolved[tmp_path / 'low_0.mrc'] == pytest.approx(20, abs=1.0)

    def test_print_angles_does_not_change_result(self, tmp_path):
        paths, tilt_of = [], {}
        # a reliable cluster around 0deg tilt, all striped at 50deg
        for i, tilt in enumerate([-2, -1, 0, 1, 2]):
            path = tmp_path / f'good_{i}.mrc'
            write_synthetic_frame(path, angle_deg=50, seed=i)
            paths.append(path)
            tilt_of[path] = tilt
        angle_outlier_threshold = 5.0
        without_print = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold, print_angles=False, anchor_tilts=5, output_dir=tmp_path)
        with_print = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold, print_angles=True, anchor_tilts=5, output_dir=tmp_path)
        assert with_print == without_print

    def test_series_with_different_pretilt_are_resolved_independently(self, tmp_path):
            paths, tilt_of = [], {}
            # main series: 3 frames per tilt, regular 3deg step, striped at 55deg
            for tilt in range(-6, 7, 3):
                for i in range(3):
                    path = tmp_path / f'main_{tilt}_{i}.mrc'
                    write_synthetic_frame(path, angle_deg=55, seed=(tilt + 100) * 10 + i)
                    paths.append(path)
                    tilt_of[path] = tilt
            # sparse series: different pretilt (offset by 1deg), 1 frame per tilt,
            # same regular 3deg step, striped at a totally different angle
            for tilt in range(-5, 8, 3):
                path = tmp_path / f'sparse_{tilt}.mrc'
                write_synthetic_frame(path, angle_deg=-20, seed=1000 + tilt)
                paths.append(path)
                tilt_of[path] = tilt

            resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=5.0, anchor_tilts=5)

            assert resolved[tmp_path / 'main_0_0.mrc'] == pytest.approx(55, abs=1.0)
            assert resolved[tmp_path / 'sparse_1.mrc'] == pytest.approx(-20, abs=1.0)

    def test_walk_tracks_gradual_angle_drift_with_tilt(self, tmp_path):
        paths, tilt_of = [], {}
        tilts = list(range(-9, 10, 3))
        for i, tilt in enumerate(tilts):
            path = tmp_path / f'drift_{tilt}.mrc'
            # angle drifts smoothly from 50deg to 62deg as tilt increases
            angle = 50 + (tilt - tilts[0]) * (12 / (tilts[-1] - tilts[0]))
            write_synthetic_frame(path, angle_deg=angle, seed=i)
            paths.append(path)
            tilt_of[path] = tilt

        resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=5.0, anchor_tilts=3)

        assert resolved[tmp_path / f'drift_{tilts[0]}.mrc'] == pytest.approx(50, abs=1.5)
        assert resolved[tmp_path / f'drift_{tilts[-1]}.mrc'] == pytest.approx(62, abs=1.5)