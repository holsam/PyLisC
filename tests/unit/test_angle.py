'''
PyLisC: unit tests for angle estimation and consensus
'''

# Import external libraries
import numpy as np, pytest

# Import intneral functions
from pylisc.estimate_angle import combine_angles, estimate_curtain_angle
from tests.fixtures import synthetic_frame

# Test angle estimation
class TestEstimateCurtainAngle:
    @pytest.mark.parametrize('true_angle', [0, 15, 30, -25, 45, 60, 90, -70])
    @pytest.mark.parametrize('period', [10, 40, 100])
    def test_recovers_known_angle(self, true_angle, period):
        frame = synthetic_frame(size=2048, angle_deg=true_angle, period_px=period, seed=2)
        estimated, _ = estimate_curtain_angle(frame)
        error = min(abs(estimated - true_angle), abs(abs(estimated - true_angle) - 180))
        assert error <= 1.0  # within one bin width


    def test_low_confidence_on_pure_noise(self):
        import numpy as np
        noise = np.random.default_rng(3).normal(100, 10, (2048, 2048)).astype('float32')
        _, energy = estimate_curtain_angle(noise)
        assert energy.max() / np.median(energy) < 5  # no dominant direction


    def test_high_confidence_on_real_curtaining(self):
        frame = synthetic_frame(size=2048, angle_deg=20, period_px=40, seed=3)
        _, energy = estimate_curtain_angle(frame)
        assert energy.max() / np.median(energy) > 100  # clear peak

# Test angle consensus
class TestCombineAngles:
    def test_identical_angles_give_perfect_agreement(self):
        angle, agreement = combine_angles([30, 30, 30], [5, 5, 5])
        assert angle == pytest.approx(30, abs=0.01)
        assert agreement == pytest.approx(1.0, abs=0.001)


    def test_wraparound_averages_correctly(self):
        angle, agreement = combine_angles([89, -89], [5, 5])
        assert abs(angle) > 85  # near +-90, not near 0
        assert agreement > 0.99


    def test_low_confidence_outlier_is_downweighted(self):
        angle, _ = combine_angles([30, 30, -10], [5, 5, 0.5])
        assert abs(angle - 30) < abs(angle - (-10))