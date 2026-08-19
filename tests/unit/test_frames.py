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


    def test_outlier_tilt_falls_back_to_nearest_reliable_neighbor(self, tmp_path):
        paths, tilt_of = [], {}
        # a reliable cluster around 0deg tilt, all striped at 50deg
        for i, tilt in enumerate([-2, -1, 0, 1, 2]):
            path = tmp_path / f'good_{i}.mrc'
            write_synthetic_frame(path, angle_deg=50, seed=i)
            paths.append(path)
            tilt_of[path] = tilt
        # a lone bad estimate at 3deg tilt, right next to the good cluster
        bad_path = tmp_path / 'bad.mrc'
        write_synthetic_frame(bad_path, angle_deg=-40, seed=42)
        paths.append(bad_path)
        tilt_of[bad_path] = 3
        resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=5.0)
        # the bad tilt should destripe at its nearest good neighbor's angle (~50deg), not its own different estimate (~-40deg)
        assert resolved[bad_path] == pytest.approx(50, abs=2.0)


    def test_all_buckets_outlier_falls_back_to_overall_consensus(self, tmp_path):
        paths, tilt_of = [], {}
        # two tilts that wildly disagree with each other
        for i, (tilt, angle) in enumerate([(-10, 10), (10, -70)]):
            path = tmp_path / f'p_{i}.mrc'
            write_synthetic_frame(path, angle_deg=angle, seed=i)
            paths.append(path)
            tilt_of[path] = tilt

        # loguru's global default sink is enqueue=True
        messages = []
        sink_id = logger.add(messages.append, level='WARNING')
        try:
            resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=1.0)
        finally:
            logger.remove(sink_id)

        assert resolved[paths[0]] == resolved[paths[1]]
        assert any('no reliable tilt' in str(m) for m in messages)


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

        resolved = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold=15.0)
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
        without_print = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold, print_angles=False)
        with_print = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold, print_angles=True)
        assert with_print == without_print
