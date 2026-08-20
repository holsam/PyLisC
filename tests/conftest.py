'''
PyLisC: test fixtures for generating synthetic MRC files
'''

# Import external libraries
import numpy as np, pytest

@pytest.fixture(scope="session")
def synthetic_frame():
    '''
    A synthetic tilt frame: large-scale background + fine texture + directional curtaining at a known angle
    '''
    def _make(size=512, angle_deg=0.0, period_px=25, amplitude=60.0, noise_std=5.0, seed=0):
        from scipy import ndimage as ndi
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:size, 0:size]
        theta = np.deg2rad(angle_deg)
        stripe_coord = -xx * np.sin(theta) + yy * np.cos(theta)
        curtains = amplitude * np.sin(stripe_coord / period_px * 2 * np.pi)
        large_scale = ndi.gaussian_filter(rng.normal(0, 1, (size, size)), sigma=60) * 200
        fine = ndi.gaussian_filter(rng.normal(0, 1, (size, size)), sigma=2) * 20
        noise = rng.normal(0, noise_std, (size, size))
        return (1000 + large_scale + fine + curtains + noise).astype(np.float32)
    return _make

@pytest.fixture(scope="session")
def synthetic_tilt_series(synthetic_frame):
    def _make(n_tilts=5, angle_deg=0.0, **frame_kwargs):
        return np.stack([
            synthetic_frame(angle_deg=angle_deg, seed=i, **frame_kwargs)
            for i in range(n_tilts)
        ])
    return _make

@pytest.fixture(scope="session")
def write_synthetic_mrc():
    def _make(path, stack, pixel_size_nm=3.4):
        import mrcfile
        with mrcfile.new(path, overwrite=True) as mrc:
            mrc.set_data(stack.astype(np.float32))
            mrc.voxel_size = pixel_size_nm * 10  # nm -> Angstrom
    return _make

@pytest.fixture(scope="session")
def write_synthetic_frame(synthetic_frame, write_synthetic_mrc):
    '''
    Write a single synthetic 2D frame (as used in frames mode)
    '''
    def _make(path, angle_deg=0.0, pixel_size_nm=3.4, seed=0, **frame_kwargs):
        write_synthetic_mrc(path, synthetic_frame(angle_deg=angle_deg, seed=seed, **frame_kwargs), pixel_size_nm=pixel_size_nm)
    return _make
