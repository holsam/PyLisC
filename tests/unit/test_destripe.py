'''
PyLisC: unit tests for destriping
'''

# Import internal functions
from pylisc.destripe import directional_destripe_angular, directional_destripe_linear

class TestDestripe:
    def retained_fraction(self, clean_component, angle_deg, destripe_fn, **kwargs):
        out = destripe_fn(clean_component, angle_deg=angle_deg, **kwargs)
        return out.std() / clean_component.std()

    def test_linear_mode_dc_protect_preserves_low_frequencies(self):
        from scipy import ndimage as ndi
        import numpy as np
        rng = np.random.default_rng(5)
        large_scale = (ndi.gaussian_filter(rng.normal(0, 1, (1024, 1024)), sigma=60) * 200).astype('float32')

        kept_without_protect = self.retained_fraction(large_scale, -65, directional_destripe_linear, notch_frac=0.02, dc_protect_frac=0.0)
        kept_with_protect = self.retained_fraction(large_scale, -65, directional_destripe_linear, notch_frac=0.02, dc_protect_frac=0.05)
        assert kept_with_protect > kept_without_protect

    def test_angular_mode_decouples_from_curtain_period(self):
        # Passing large-scale/fine components through ALONE isolates the filter's effect on each, since it's linear
        from scipy import ndimage as ndi
        import numpy as np
        rng = np.random.default_rng(9)
        large_scale = (ndi.gaussian_filter(rng.normal(0, 1, (1024, 1024)), sigma=60) * 200).astype('float32')
        kept_at_each_period = [
            self.retained_fraction(large_scale, -65, directional_destripe_angular, angular_width_deg=8.0)
            for _ in range(3)  # angular filter doesn't depend on curtain period at all
        ]
        assert max(kept_at_each_period) - min(kept_at_each_period) < 0.01
        assert all(k > 0.9 for k in kept_at_each_period)

    def test_linear_mode_isotropic_loss_without_dc_protect(self):
        from scipy import ndimage as ndi
        import numpy as np
        rng = np.random.default_rng(5)
        large_scale = (ndi.gaussian_filter(rng.normal(0, 1, (1024, 1024)), sigma=60) * 200).astype('float32')
        kept = self.retained_fraction(large_scale, -65, directional_destripe_linear, notch_frac=0.02, dc_protect_frac=0.0)
        assert kept < 0.2

    def test_zero_angular_width_does_not_produce_nan(self, synthetic_frame):
        import numpy as np
        from pylisc.destripe import directional_destripe_angular
        frame = synthetic_frame(size=64, angle_deg=20)

        result = directional_destripe_angular(frame, angle_deg=20, angular_width_deg=0)

        assert not np.isnan(result).any()