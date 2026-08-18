'''
PyLisC: frames-mode processing
'''

# Import external libraries
import numpy as np, os, typer
from concurrent.futures import ProcessPoolExecutor, as_completed

# Import internal PyLisC modules
from pylisc.estimate_angle import combine_angles, estimate_curtain_angle
from pylisc.io import find_input_files, readMrcFile, writeMrcFile
from pylisc.lisc import lisc_clear_frame
from pylisc.log import logger, per_file_log
from pylisc.templates import compile_template, extract_tilt_angle


def run_frames(
    input_dir,
    output_dir,
    filename_template,
    filename_delimiters,
    mode,
    apply_filter,
    filter_threshold,
    pixel_size,
    curtain_angle,
    angular_width,
    notch_frac,
    dc_protect_frac,
    angle_outlier_threshold,
    force,
    dry_run,
    workers,
):
    if apply_filter and pixel_size is None:
        raise typer.BadParameter('--pixel-size is required when --apply-filter is set in frames mode (frame headers are not used for pixel size)')

    paths = find_input_files(input_dir, recursive=False)
    if not paths:
        raise typer.BadParameter(f'No frame files found under {input_dir}')
    logger.info('{} frame files found in {}', len(paths), input_dir)

    pattern = compile_template(filename_template, delimiters=filename_delimiters)
    tilt_of = {path: extract_tilt_angle(path.name, pattern) for path in paths}

    if curtain_angle is None:
        angle_for_path = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold)
    else:
        angle_for_path = {path: curtain_angle for path in paths}

    jobs = []
    for path in paths:
        relative = path.relative_to(input_dir)
        out_path = output_dir / relative.parent / f'{path.stem}_PyLisC_{mode}.mrc'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((path, out_path, angle_for_path[path]))

    max_workers = os.cpu_count()
    workers = max_workers if workers == 0 else min(workers, max_workers)

    logger.info('processing {} files across {} workers', len(jobs), workers)
    if dry_run:
        for path, out_path, _ in jobs:
            logger.info('[dry-run] ({}) would write {}', path.name, out_path)
        return

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _process_one,
                path,
                out_path,
                angle,
                mode,
                pixel_size,
                apply_filter,
                filter_threshold,
                angular_width,
                notch_frac,
                dc_protect_frac,
                force,
            ): path
            for path, out_path, angle in jobs
        }
        for future in as_completed(futures):
            path = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error('({}) failed during batch processing: {}', path.name, e)
                logger.debug('({}) traceback:', path.name, exc_info=e)
                continue
            logger.debug('({}) done', path.name)

    logger.info('cleared mrc files written to {}', output_dir)


def _process_one(
    path,
    out_path,
    curtain_angle,
    mode,
    pixel_size,
    apply_filter,
    filter_threshold,
    angular_width,
    notch_frac,
    dc_protect_frac,
    force,
):
    with per_file_log(out_path.parent, out_path.stem):
        logger.debug('({}) starting destriping', path.name)
        try:
            data, voxel_size = readMrcFile(path)
            cleared = lisc_clear_frame(
                data[0],
                decurtaining_mode=mode,
                pixel_size_nm=pixel_size,
                curtain_angle=curtain_angle,
                apply_filter=apply_filter,
                filter_threshold_nm=filter_threshold,
                angular_width_deg=angular_width,
                destripe_notch_fraction=notch_frac,
                dc_protect_frac=dc_protect_frac,
            )
            writeMrcFile(cleared[np.newaxis, ...], voxel_size, out_path, force)
            logger.debug('({}) cleared mrc file wrote to {}', path.name, out_path)
        except Exception as e:
            logger.error('({}) failed: {}', path.name, e)
            logger.debug('({}) traceback: {}', path.name, exc_info=e)
            raise


def _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold):
    angles, confidences = {}, {}
    for path in paths:
        data, _ = readMrcFile(path)
        angle, energy = estimate_curtain_angle(data[0])
        median_energy = np.median(energy)
        confidences[path] = energy.max() / median_energy if median_energy > 0 else 0.0
        angles[path] = angle
        logger.debug('({}) tilt {}° est. angle: {} (conf.: {})', path.name, tilt_of[path], angle, confidences[path])

    # A single spuriously sharp FFT peak can otherwise dominate its bucket's consensus and the overall weighted average
    conf_values = np.array(list(confidences.values()))
    if len(conf_values) >= 4:
        q1, median_conf, q3 = np.percentile(conf_values, [25, 50, 75])
        confidence_cap = median_conf + 1.5 * (q3 - q1)
    else:
        confidence_cap = np.median(conf_values) * 5 if len(conf_values) else 0.0
    if confidence_cap > 0:
        n_clipped = sum(1 for c in confidences.values() if c > confidence_cap)
        if n_clipped:
            logger.debug('clipping {} frame(s) with confidence above {}', n_clipped, f'{confidence_cap:.2f}')
        confidences = {p: min(c, confidence_cap) for p, c in confidences.items()}

    tilt_buckets = {}
    for path in paths:
        bucket = round(tilt_of[path])
        tilt_buckets.setdefault(bucket, []).append(path)

    bucket_consensus = {}
    bucket_weight = {}
    for bucket, bucket_paths in tilt_buckets.items():
        bucket_confidences = [confidences[p] for p in bucket_paths]
        consensus, agreement = combine_angles(
            [angles[p] for p in bucket_paths],
            bucket_confidences,
        )
        bucket_consensus[bucket] = consensus
        # High-tilt frames carry less signal (sample thickness grows ~1/cos(tilt)) so reduce weighting for overall consensus
        bucket_weight[bucket] = np.median(bucket_confidences) * np.cos(np.deg2rad(bucket))
        logger.info('tilt {}°: consensus angle {}° (agreement: {}, n={})', bucket, f'{consensus:.1f}', f'{agreement:.3f}', len(bucket_paths))

    overall_consensus, overall_agreement = combine_angles(
        list(bucket_consensus.values()), list(bucket_weight.values())
    )
    logger.info('overall consensus across {} tilt angle(s): {}° (agreement: {})', len(bucket_consensus), f'{overall_consensus:.1f}', f'{overall_agreement:.3f}')

    outlier_buckets = set()
    for bucket, angle in bucket_consensus.items():
        deviation = min(abs(angle - overall_consensus), 180 - abs(angle - overall_consensus))
        if deviation > angle_outlier_threshold:
            outlier_buckets.add(bucket)
    good_buckets = sorted(set(bucket_consensus) - outlier_buckets)
    resolved_consensus = dict(bucket_consensus)
    if not good_buckets:
        logger.warning('every tilt bucket deviates from the overall consensus - no reliable tilt to fall back on, using overall consensus ({}°) for all', f'{overall_consensus:.1f}')
        resolved_consensus = {bucket: overall_consensus for bucket in bucket_consensus}
    else:
        for bucket in outlier_buckets:
            own_angle = bucket_consensus[bucket]
            deviation = min(abs(own_angle - overall_consensus), 180 - abs(own_angle - overall_consensus))
            neighbor = min(good_buckets, key=lambda g: abs(g - bucket))
            resolved_consensus[bucket] = bucket_consensus[neighbor]
            logger.warning('tilt {}° consensus angle ({}°) deviates {}° from overall consensus ({}°) - using nearest reliable tilt {}°\'s angle ({}°) instead', bucket, f'{own_angle:.1f}', f'{deviation:.1f}', f'{overall_consensus:.1f}', neighbor, f'{bucket_consensus[neighbor]:.1f}')
    return {path: resolved_consensus[round(tilt_of[path])] for path in paths}
