'''
PyLisC: unit tests for input/output utilities
'''

# -- Import external libraries
import numpy as np, pytest

# -- Import internal functions
from pylisc.io import nameOutputFile, readMrcFile, writeMrcFile
from pylisc.stack import _default_output_path

class TestIo:
    def test_default_output_path_appends_numeric_suffix_on_collision(self, tmp_path):
        input_path = tmp_path / 'series.mrc'
        input_path.touch()
        (tmp_path / 'series_PyLisC_angular.mrc').touch()  # first choice taken
        (tmp_path / 'series_PyLisC_angular_1.mrc').touch()  # second choice also taken

        out_path = _default_output_path(input_path, mode='angular')

        assert out_path == tmp_path / 'series_PyLisC_angular_2.mrc'

    def test_write_then_read_roundtrip(self, tmp_path, synthetic_frame):
        path = tmp_path / 'out.mrc'
        frame = synthetic_frame(size=64)[np.newaxis, ...]

        writeMrcFile(frame, 34.0, path)  # voxel_size in Angstrom
        data, voxel_size = readMrcFile(path)

        assert data.shape == frame.shape
        np.testing.assert_allclose(data, frame, rtol=1e-5)
        assert float(voxel_size.x) == pytest.approx(34.0)

    def test_write_refuses_existing_file_without_force(self, tmp_path):
        path = tmp_path / 'out.mrc'
        path.write_bytes(b'not really an mrc, just occupying the path')

        with pytest.raises(FileExistsError):
            writeMrcFile(np.zeros((1, 4, 4), dtype=np.float32), 10.0, path)

    def test_write_overwrites_existing_file_with_force(self, tmp_path):
        path = tmp_path / 'out.mrc'
        path.write_bytes(b'not really an mrc, just occupying the path')

        writeMrcFile(np.zeros((1, 4, 4), dtype=np.float32), 10.0, path, force=True)
        data, _ = readMrcFile(path)
        assert data.shape == (1, 4, 4)

class TestIoNameOutputFile:
    def test_no_collision_returns_base_name(self, tmp_path):
        input_path = tmp_path / 'series.mrc'
        input_path.touch()

        out_path = nameOutputFile(input_path, mode='angular')

        assert out_path == tmp_path / 'series_PyLisC_angular.mrc'

    def test_collision_appends_numeric_suffix(self, tmp_path):
        input_path = tmp_path / 'series.mrc'
        input_path.touch()
        (tmp_path / 'series_PyLisC_angular.mrc').touch()

        out_path = nameOutputFile(input_path, mode='angular')

        assert out_path == tmp_path / 'series_PyLisC_angular_1.mrc'
