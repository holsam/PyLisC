'''
PyLisC: stack-mode processing
'''

# Import external libraries
import numpy as np, os, typer
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Import internal PyLisC modules
from pylisc.estimate_angle import combine_angles, estimate_curtain_angle, plot_angular_energy
from pylisc.io import find_input_files, readMrcFile, writeMrcFile
from pylisc.lisc import lisc_clear_frame
from pylisc.log import logger, per_file_log
from pylisc.preview import generate_strength_preview


def _default_output_path(input_path: Path, mode: str) -> Path:
    base_stem = f'{input_path.stem}_PyLisC_{mode}'
    output_path = Path(f'{input_path.parents[0]}/{base_stem}.mrc')
    if output_path.exists():
        counter = 1
        while True:
            output_path = Path(f'{input_path.parents[0]}/{base_stem}_{counter}.mrc')
            if not output_path.exists():
                break
            counter += 1
    return output_path


def _process_series(
    path: Path,
    out_path: Path,
    mode,
    apply_filter,
    filter_threshold,
    pixel_size,
    curtain_angle,
    reference_frame,
    angular_width,
    notch_frac,
    dc_protect_frac,
    force,
    dry_run,
    preview_strengths=None,
):
    with per_file_log(out_path.parent, out_path.stem):
        if out_path.exists() and not force:
            logger.error('({}) output {} already exists: use --force to overwrite', path.name, out_path)
            raise FileExistsError(f'{out_path} already exists: use --force to overwrite')

        logger.debug('({}) started processing', path.name)
        data, voxel_size = readMrcFile(path)

        # Resolve pixel size
        if pixel_size is None:
            resolved_pixel_size = float(voxel_size.x) / 10.0
            logger.debug('({}) pixel size ({}) resolved from mrc', path.name, resolved_pixel_size)
        else:
            resolved_pixel_size = pixel_size
        if resolved_pixel_size <= 0:
            raise ValueError('Pixel size cannot be less than or equal to 0')

        # Resolve reference frame (use mid-frame as should be ok for both dose-symmetric & continuous acquisitions)
        if reference_frame is None:
            resolved_reference_frame = len(data) // 2
            logger.debug('({}) reference_frame defaulted to: {}', path.name, resolved_reference_frame)
        elif reference_frame > len(data):
            logger.warning('({}) supplied reference frame index ({}) does not exist - defaulting to mid-frame')
            resolved_reference_frame = len(data) // 2
            logger.debug('({}) reference_frame defaulted to: {}', path.name, resolved_reference_frame)
        else:
            resolved_reference_frame = reference_frame

        # Estimate curtaining angle if not provided
        if curtain_angle is None:
            resolved_angle, angular_energy = estimate_curtain_angle(data[resolved_reference_frame])
            if not dry_run:
                plot_angular_energy(angular_energy, resolved_angle, output_dir=out_path.parent)
            median_energy = np.median(angular_energy)
            confidence = angular_energy.max() / median_energy if median_energy > 0 else 0.0
            logger.info('({}) estimated curtaining angle: {}° (confidence: {})', path.name, resolved_angle, confidence)
        else:
            resolved_angle = curtain_angle

        if dry_run:
            logger.info('({}) [dry-run] would write to {} (angle: {}°, pixel size: {})', path.name, out_path, resolved_angle, resolved_pixel_size)
            return resolved_angle

        if preview_strengths is not None:
            values = [float(v) for v in preview_strengths.split(',')]
            logger.info('previewing {} destriping strength(s)', len(values))
            preview_path = generate_strength_preview(
                data[resolved_reference_frame],
                mode=mode,
                pixel_size_nm=resolved_pixel_size,
                values=values,
                curtain_angle=resolved_angle,
                apply_filter=apply_filter,
                filter_threshold_nm=filter_threshold,
                dc_protect_frac=dc_protect_frac,
                notch_frac=notch_frac,
                output_dir=out_path.parent,
            )
            logger.info('Strength preview saved to {}', preview_path)
            return None

        # Apply LisC to each frame
        cleared_stack = np.empty_like(data, dtype=np.float32)
        for i, frame in enumerate(data):
            cleared_stack[i] = lisc_clear_frame(
                frame,
                decurtaining_mode=mode,
                pixel_size_nm=resolved_pixel_size,
                curtain_angle=resolved_angle,
                apply_filter=apply_filter,
                filter_threshold_nm=filter_threshold,
                angular_width_deg=angular_width,
                destripe_notch_fraction=notch_frac,
                dc_protect_frac=dc_protect_frac,
            )

        writeMrcFile(cleared_stack, voxel_size, out_path, force)
        logger.debug('({}) cleared mrc file wrote to {}', path.name, out_path)
        return resolved_angle


def run_stack(
    input_path,
    output_mrc,
    output_dir,
    mode,
    apply_filter,
    filter_threshold,
    pixel_size,
    curtain_angle,
    reference_frame,
    angular_width,
    notch_frac,
    dc_protect_frac,
    angle_outlier_threshold,
    force,
    dry_run,
    workers,
    preview_strengths=None,
):
    if input_path.is_dir():
        _run_stack_batch(
            input_dir=input_path,
            output_dir=output_dir,
            mode=mode,
            apply_filter=apply_filter,
            filter_threshold=filter_threshold,
            pixel_size=pixel_size,
            curtain_angle=curtain_angle,
            reference_frame=reference_frame,
            angular_width=angular_width,
            notch_frac=notch_frac,
            dc_protect_frac=dc_protect_frac,
            angle_outlier_threshold=angle_outlier_threshold,
            force=force,
            dry_run=dry_run,
            workers=workers,
        )
    else:
        out_path = output_mrc if output_mrc is not None else _default_output_path(input_path, mode)
        _process_series(
            input_path,
            out_path,
            mode=mode,
            apply_filter=apply_filter,
            filter_threshold=filter_threshold,
            pixel_size=pixel_size,
            curtain_angle=curtain_angle,
            reference_frame=reference_frame,
            angular_width=angular_width,
            notch_frac=notch_frac,
            dc_protect_frac=dc_protect_frac,
            preview_strengths=preview_strengths,
            force=force,
            dry_run=dry_run,
        )


def _run_stack_batch(
    input_dir,
    output_dir,
    mode,
    apply_filter,
    filter_threshold,
    pixel_size,
    curtain_angle,
    reference_frame,
    angular_width,
    notch_frac,
    dc_protect_frac,
    angle_outlier_threshold,
    force,
    dry_run,
    workers,
):
    series_paths = find_input_files(input_dir, recursive=True)
    if not series_paths:
        raise typer.BadParameter(f'No tilt series found under {input_dir}')
    logger.info('{} files found in {}', len(series_paths), input_dir)

    if curtain_angle is None:
        angles, confidences = [], []
        for path in series_paths:
            data, _ = readMrcFile(path)
            frame_index = reference_frame if reference_frame is not None else len(data) // 2
            frame = data[frame_index]
            angle, energy = estimate_curtain_angle(frame)
            median_energy = np.median(energy)
            confidence = energy.max() / median_energy if median_energy > 0 else 0.0
            angles.append(angle); confidences.append(confidence)
            logger.debug('({}) est. angle: {} (conf.: {})', path.name, angle, confidence)

        consensus_angle, agreement = combine_angles(angles, confidences)
        logger.info('batch consensus angle: {}° (agreement: {})', f'{consensus_angle:.1f}', f'{agreement:.3f}')

        for path, angle in zip(series_paths, angles):
            deviation = min(abs(angle - consensus_angle), 180 - abs(angle - consensus_angle))
            if deviation > angle_outlier_threshold:
                logger.warning('({}) est. angle ({}°) deviates {}° from consensus ({}°) - check diagnostic plot', path.name, f'{angle:.1f}', f'{deviation:.1f}', f'{consensus_angle:.1f}')

        curtain_angle = consensus_angle
    
    jobs = []
    for path in series_paths:
        relative = path.relative_to(input_dir)
        out_path = output_dir / relative.parent / f'{path.stem}_PyLisC_{mode}.mrc'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((path, out_path))

    max_workers = os.cput_count()
    workers = max_workers if workers == 0 else min(workers, max_workers)
    
    logger.info('processing {} files across {} workers', len(jobs), workers)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _process_series,
                path,
                out_path,
                mode=mode,
                apply_filter=apply_filter,
                filter_threshold=filter_threshold,
                pixel_size=pixel_size,
                curtain_angle=curtain_angle,
                reference_frame=reference_frame,
                angular_width=angular_width,
                notch_frac=notch_frac,
                dc_protect_frac=dc_protect_frac,
                force=force,
                dry_run=dry_run,
            ): path
            for path, out_path in jobs
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error('({}) failed during batch processing: {}', path.name, e)
                logger.debug('({}) traceback:', path.name, exc_info=e)
    logger.info('cleared mrc files written to {}', output_dir)
