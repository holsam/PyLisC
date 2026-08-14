from typer.testing import CliRunner
from pylisc.cli import pylisc

runner = CliRunner()

class TestCliSingle:
    def test_single_file_run(self, tmp_path):
        from tests.fixtures import synthetic_tilt_series, write_synthetic_mrc
        stack = synthetic_tilt_series(n_tilts=3, angle_deg=20)
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, stack)

        result = runner.invoke(pylisc, [str(input_path), '--mode', 'angular'])
        assert result.exit_code == 0
        assert (tmp_path / 'series_PyLisC_angular.mrc').exists()

class TestCliBatch:
    def test_batch_run_with_outlier_warning(self, tmp_path):
        from tests.fixtures import synthetic_tilt_series, write_synthetic_mrc
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'
        write_synthetic_mrc(input_dir / 'a.mrc', synthetic_tilt_series(angle_deg=20))
        print('wrote first mrc')
        write_synthetic_mrc(input_dir / 'b.mrc', synthetic_tilt_series(angle_deg=21))
        print('wrote second mrc')
        write_synthetic_mrc(input_dir / 'c.mrc', synthetic_tilt_series(angle_deg=60))  # deliberate outlier
        print('wrote third mrc')

        result = runner.invoke(pylisc, [str(input_dir), '--mode', 'angular', '--output-dir', str(output_dir)])
        print('completed result')
        print(f'exit code: {result.exit_code}')
        assert result.exit_code == 0
        assert 'WARNING' in result.output
        assert 'c.mrc' in result.output
        assert (output_dir / 'a_PyLisC_angular.mrc').exists()

class TestCliPreview:
    def test_preview_exits_without_full_run(self, tmp_path):
        from tests.fixtures import synthetic_tilt_series, write_synthetic_mrc
        stack = synthetic_tilt_series(n_tilts=3)
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, stack)

        result = runner.invoke(pylisc, [str(input_path), '--mode', 'angular', '--preview-strengths', '3,8,20'])
        assert result.exit_code == 0
        assert (tmp_path / 'destripe_strength_preview.tiff').exists()
        assert not (tmp_path / 'series_PyLisC_angular.mrc').exists()  # full run did NOT happen