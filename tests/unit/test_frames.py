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
