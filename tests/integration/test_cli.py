from typer.testing import CliRunner
from pylisc.cli import pylisc

runner = CliRunner()

class TestCliSingle:
    def test_single_file_run(self, tmp_path):
        from tests.fixtures import synthetic_tilt_series, write_synthetic_mrc
        stack = synthetic_tilt_series(n_tilts=3, angle_deg=20)
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, stack)

        result = runner.invoke(pylisc, ['stack', str(input_path), '--mode', 'angular'])
        assert result.exit_code == 0
        assert (tmp_path / 'series_PyLisC_angular.mrc').exists()
        assert (tmp_path / 'series_PyLisC_angular.log').exists()

class TestCliBatch:
    def test_batch_run_with_outlier_warning(self, tmp_path):
        from tests.fixtures import synthetic_tilt_series, write_synthetic_mrc
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'
        write_synthetic_mrc(input_dir / 'a.mrc', synthetic_tilt_series(angle_deg=20))
        write_synthetic_mrc(input_dir / 'b.mrc', synthetic_tilt_series(angle_deg=21))
        write_synthetic_mrc(input_dir / 'c.mrc', synthetic_tilt_series(angle_deg=60))  # deliberate outlier

        result = runner.invoke(pylisc, ['stack', str(input_dir), '--mode', 'angular', '--output-dir', str(output_dir)])
        assert result.exit_code == 0
        assert 'WARNING' in result.output
        assert 'c.mrc' in result.output
        assert (output_dir / 'a_PyLisC_angular.mrc').exists()
        assert (output_dir / 'a_PyLisC_angular.log').exists()

class TestCliPreview:
    def test_preview_exits_without_full_run(self, tmp_path):
        from tests.fixtures import synthetic_tilt_series, write_synthetic_mrc
        stack = synthetic_tilt_series(n_tilts=3)
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, stack)

        result = runner.invoke(pylisc, ['stack', str(input_path), '--mode', 'angular', '--preview-strengths', '3,8,20'])
        assert result.exit_code == 0
        assert (tmp_path / 'destripe_strength_preview.tiff').exists()
        assert not (tmp_path / 'series_PyLisC_angular.mrc').exists()  # full run did NOT happen

class TestCliFrames:
    def test_frames_run_groups_by_tilt_and_warns_on_outlier(self, tmp_path):
        from tests.fixtures import write_synthetic_frame
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'
        template = '{}_{position}_{}_{tilt}_{}_{}_{}_{}_{}.mrc'

        # two positions at matching nominal tilts, same striping angle
        write_synthetic_frame(input_dir / 'Position_1_1_-10.00_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=0)
        write_synthetic_frame(input_dir / 'Position_2_1_-9.98_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=1)
        # a deliberate outlier at another tilt
        write_synthetic_frame(input_dir / 'Position_1_2_0.00_20240101_1_Fractions_motion_corrected.mrc', angle_deg=65, seed=2)

        result = runner.invoke(pylisc, [
            'frames', str(input_dir),
            '--output-dir', str(output_dir),
            '--filename-template', template,
            '--mode', 'angular',
        ])
        assert result.exit_code == 0
        assert 'WARNING' in result.output
        out_file = output_dir / 'Position_1_1_-10.00_20240101_1_Fractions_motion_corrected_PyLisC_angular.mrc'
        assert out_file.exists()
        assert (output_dir / f'{out_file.stem}.log').exists()

    def test_frames_requires_pixel_size_for_filter(self, tmp_path):
        from tests.fixtures import write_synthetic_frame
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        write_synthetic_frame(input_dir / 'Position_1_1_-10.00_20240101_1_Fractions_motion_corrected.mrc')

        result = runner.invoke(pylisc, [
            'frames', str(input_dir),
            '--output-dir', str(tmp_path / 'cleared'),
            '--filename-template', '{}_{position}_{}_{tilt}_{}_{}_{}_{}.mrc',
            '--apply-filter',
        ])
        assert result.exit_code != 0
        assert '--pixel-size' in result.output