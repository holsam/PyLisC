'''
PyLisC: integration tests for PyLisC CLI
'''

# Import external libraries
from typer.testing import CliRunner
from pylisc.cli import pylisc

runner = CliRunner()

class TestCliSingle:
    def test_single_file_run(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        stack = synthetic_tilt_series(n_tilts=3, angle_deg=20)
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, stack)

        result = runner.invoke(pylisc, ['stack', str(input_path), '--mode', 'angular'])
        assert result.exit_code == 0
        assert (tmp_path / 'series_PyLisC_angular.mrc').exists()
        assert (tmp_path / 'series_PyLisC_angular.log').exists()
   
    def test_rerun_without_force_fails_then_succeeds_with_force(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
            input_path = tmp_path / 'series.mrc'
            write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=3, angle_deg=20))
            out_path = tmp_path / 'series_PyLisC_angular.mrc'

            first = runner.invoke(pylisc, ['stack', str(input_path), '--mode', 'angular'])
            assert first.exit_code == 0
            original_mtime = out_path.stat().st_mtime

            rerun = runner.invoke(pylisc, ['stack', str(input_path), str(out_path), '--mode', 'angular'])
            assert rerun.exit_code != 0
            assert out_path.stat().st_mtime == original_mtime  # untouched

            forced = runner.invoke(pylisc, ['stack', str(input_path), str(out_path), '--mode', 'angular', '--force'])
            assert forced.exit_code == 0

    def test_dry_run_writes_nothing(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=3, angle_deg=20))

        result = runner.invoke(pylisc, ['stack', str(input_path), '--mode', 'angular', '--dry-run'])
        assert result.exit_code == 0
        assert not (tmp_path / 'series_PyLisC_angular.mrc').exists() 
    
    def test_reference_frame_at_series_length_is_rejected_cleanly(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=3, angle_deg=20))

        result = runner.invoke(pylisc, [
            'stack', str(input_path), '--mode', 'angular', '--reference-frame', '3',
        ])
        assert result.exit_code == 0
        assert 'IndexError' not in result.output

class TestCliBatch:
    def test_batch_run_with_outlier_warning(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
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

    def test_batch_reference_frame_out_of_range_does_not_crash_whole_batch(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'
        write_synthetic_mrc(input_dir / 'a.mrc', synthetic_tilt_series(n_tilts=5, angle_deg=20))
        write_synthetic_mrc(input_dir / 'short.mrc', synthetic_tilt_series(n_tilts=2, angle_deg=20))

        result = runner.invoke(pylisc, [
            'stack', str(input_dir), '--mode', 'angular',
            '--output-dir', str(output_dir), '--reference-frame', '4',
        ])
        assert result.exit_code == 0
        assert (output_dir / 'a_PyLisC_angular.mrc').exists()

class TestCliOptions:
    def test_preview_exits_without_full_run(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        stack = synthetic_tilt_series(n_tilts=3)
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, stack)

        result = runner.invoke(pylisc, ['stack', str(input_path), '--mode', 'angular', '--preview-strengths', '3,8,20'])
        assert result.exit_code == 0
        assert (tmp_path / 'destripe_strength_preview.tiff').exists()
        assert not (tmp_path / 'series_PyLisC_angular.mrc').exists()  # full run did NOT happen

    def test_zero_angular_width_is_rejected(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=3, angle_deg=20))

        result = runner.invoke(pylisc, [
            'stack', str(input_path), '--mode', 'angular', '--angular-width', '0',
        ])
        assert result.exit_code != 0

class TestCliFrames:
    def test_frames_run_groups_by_tilt_and_warns_on_outlier(self, tmp_path, write_synthetic_frame):
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        output_dir = tmp_path / 'cleared'
        template = '{}_{position}_{}_{tilt}_{}_{}_{}_{}_{}.mrc'

        # three tilts, two positions each, all striped at the same angle
        write_synthetic_frame(input_dir / 'Position_1_1_-10.00_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=0)
        write_synthetic_frame(input_dir / 'Position_2_1_-9.98_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=1)
        write_synthetic_frame(input_dir / 'Position_1_2_0.00_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=3)
        write_synthetic_frame(input_dir / 'Position_2_2_0.02_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=4)
        write_synthetic_frame(input_dir / 'Position_1_3_10.00_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=0)
        write_synthetic_frame(input_dir / 'Position_2_3_9.98_20240101_1_Fractions_motion_corrected.mrc', angle_deg=20, seed=1)
        # a deliberate outlier at another tilt, past the anchor window
        write_synthetic_frame(input_dir / 'Position_1_4_20.00_20240101_1_Fractions_motion_corrected.mrc', angle_deg=65, seed=2)

        result = runner.invoke(pylisc, [
            'frames', str(input_dir),
            '--output-dir', str(output_dir),
            '--filename-template', template,
            '--mode', 'angular',
            '--anchor-tilts', '2',
        ])
        assert result.exit_code == 0
        assert 'WARNING' in result.output
        out_file = output_dir / 'Position_1_1_-10.00_20240101_1_Fractions_motion_corrected_PyLisC_angular.mrc'
        assert out_file.exists()
        assert (output_dir / f'{out_file.stem}.log').exists()

    def test_frames_requires_pixel_size_for_filter(self, tmp_path, write_synthetic_frame):
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

class TestCliVersionAndWarnings:
    def test_version_flag_prints_and_exits(self):
        result = runner.invoke(pylisc, ['--version'])
        assert result.exit_code == 0
        assert 'PyLisC version' in result.output

    def test_linear_mode_warns_deprecated(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=2, angle_deg=20))

        result = runner.invoke(pylisc, ['stack', str(input_path), '--mode', 'linear'])
        assert result.exit_code == 0
        assert 'deprecated' in result.output

    def test_single_file_mode_warns_on_ignored_output_dir(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_path = tmp_path / 'series.mrc'
        write_synthetic_mrc(input_path, synthetic_tilt_series(n_tilts=2, angle_deg=20))

        result = runner.invoke(pylisc, [
            'stack', str(input_path), '--mode', 'angular',
            '--output-dir', str(tmp_path / 'ignored'),
        ])
        assert result.exit_code == 0
        assert 'ignoring option: --output-dir' in result.output

    def test_batch_mode_warns_on_ignored_output_arg_and_preview(self, tmp_path, synthetic_tilt_series, write_synthetic_mrc):
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        write_synthetic_mrc(input_dir / 'a.mrc', synthetic_tilt_series(n_tilts=2, angle_deg=20))

        result = runner.invoke(pylisc, [
            'stack', str(input_dir), str(tmp_path / 'ignored_out.mrc'),
            '--mode', 'angular', '--output-dir', str(tmp_path / 'cleared'),
            '--preview-strengths', '3,8',
        ])
        assert result.exit_code == 0
        assert 'ignoring argument' in result.output
        assert 'ignoring option: --preview-strengths' in result.output

class TestCliFramesOptions:
    def test_zero_angular_width_is_rejected(self, tmp_path, write_synthetic_frame):
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        write_synthetic_frame(input_dir / 'a_0.00.mrc', angle_deg=20)

        result = runner.invoke(pylisc, [
            'frames', str(input_dir),
            '--output-dir', str(tmp_path / 'cleared'),
            '--filename-template', '{}_{tilt}.mrc',
            '--angular-width', '0',
        ])
        assert result.exit_code != 0

    def test_linear_mode_warns_deprecated(self, tmp_path, write_synthetic_frame):
        input_dir = tmp_path / 'raw'
        input_dir.mkdir()
        write_synthetic_frame(input_dir / 'a_0.00.mrc', angle_deg=20)

        result = runner.invoke(pylisc, [
            'frames', str(input_dir),
            '--output-dir', str(tmp_path / 'cleared'),
            '--filename-template', '{}_{tilt}.mrc',
            '--mode', 'linear',
        ])
        assert result.exit_code == 0
        assert 'deprecated' in result.output