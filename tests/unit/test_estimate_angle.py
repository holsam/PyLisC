'''
PyLisC: unit tests for shared consensus-robustness helpers (confidence clipping, anchor walk)
'''

# Import external libraries
import pytest

# Import internal functions
from pylisc.estimate_angle import clip_confidence_outliers, resolve_walk

class TestClipConfidenceOutliers:
    def test_no_outlier_leaves_confidences_unchanged(self):
        confidences = {'a': 1.0, 'b': 1.1, 'c': 0.9}
        assert clip_confidence_outliers(confidences) == confidences

    def test_spike_is_capped_others_untouched(self):
        confidences = {'a': 1.0, 'b': 1.1, 'c': 0.9, 'spike': 500.0}
        clipped = clip_confidence_outliers(confidences)
        assert clipped['spike'] < confidences['spike']
        assert clipped['a'] == confidences['a']
        assert clipped['b'] == confidences['b']
        assert clipped['c'] == confidences['c']

    def test_empty_dict(self):
        assert clip_confidence_outliers({}) == {}


class TestResolveWalk:
    def test_single_key_seeds_itself(self):
        resolved, status = resolve_walk([0], {0: 12.0}, angle_outlier_threshold=5.0, anchor_window=5)
        assert resolved == {0: 12.0}
        assert status == {0: 'seed'}

    def test_smooth_series_all_accepted(self):
        keys = list(range(7))
        values = {k: 10.0 + k for k in keys}
        resolved, status = resolve_walk(keys, values, angle_outlier_threshold=5.0, anchor_window=3)
        assert resolved == values
        assert all(s in ('seed', 'accepted') for s in status.values())

    def test_outlier_falls_back_to_nearest_resolved(self):
        keys = list(range(7))
        values = {0: 50.0, 1: 50.0, 2: 50.0, 3: 50.0, 4: 50.0, 5: 50.0, 6: -10.0}
        resolved, status = resolve_walk(keys, values, angle_outlier_threshold=5.0, anchor_window=3)
        assert status[6] == 'rejected'
        assert resolved[6] == pytest.approx(50.0)
