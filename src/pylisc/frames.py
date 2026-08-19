'''
PyLisC: frames-mode processing
'''

# Import external libraries
import csv, numpy as np, os, typer
from concurrent.futures import ProcessPoolExecutor, as_completed
from rich.console import Console
from rich.table import Table

# Import internal PyLisC modules
from pylisc.estimate_angle import combine_angles, estimate_curtain_angle
from pylisc.io import find_input_files, readMrcFile, writeMrcFile
from pylisc.lisc import lisc_clear_frame
from pylisc.log import logger, per_file_log
from pylisc.templates import compile_template, extract_tilt_angle

# Define dictionary of status colours (used by --print-angles)
_STATUS_COLORS = {'seed': 'cyan', 'accepted': 'green', 'rejected': 'red'}

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
    anchor_tilts,
    force,
    dry_run,
    workers,
    print_angles,
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
        angle_for_path = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold, anchor_tilts, print_angles, output_dir)
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

def _split_by_tilt_gap(bucket_list, tol_frac=0.5):
    '''Split a sorted bucket list wherever the tilt spacing breaks from the list's own regular step (e.g. two disjoint tilt ranges that happen to share the same frame count)'''
    if len(bucket_list) < 3:
        return [bucket_list]
    diffs = np.diff(bucket_list)
    step = np.median(diffs)
    runs, current = [], [bucket_list[0]]
    for b, d in zip(bucket_list[1:], diffs):
        if step > 0 and abs(d - step) > tol_frac * step:
            runs.append(current)
            current = [b]
        else:
            current.append(b)
    runs.append(current)
    return runs

def _split_series(tilt_buckets, tol_frac=0.5):
    '''
    Cluster tilt buckets into acquisition series by:
        1. Group by frame count
        2. Split each group where tilt spacing does not have a regular step
    '''
    buckets_sorted = sorted(tilt_buckets)
    n_by_bucket = {b: len(tilt_buckets[b]) for b in buckets_sorted}
    distinct_n = sorted(set(n_by_bucket.values()))
    n_groups = [[distinct_n[0]]]
    for n in distinct_n[1:]:
        if n - n_groups[-1][-1] <= 1:
            n_groups[-1].append(n)
        else:
            n_groups.append([n])
    series = []
    for group in n_groups:
        cluster = sorted(b for b in buckets_sorted if n_by_bucket[b] in group)
        series.extend(_split_by_tilt_gap(cluster, tol_frac))
    return series

def _resolve_series(series_buckets, bucket_consensus, angle_outlier_threshold, anchor_tilts) -> tuple[dict, dict]:
    '''
    Seed buckets around the median tilt, and walk out, checking each against the nearest already-resolved (seed/accepted) bucket
    '''
    buckets_sorted = sorted(series_buckets)
    if len(buckets_sorted) == 1:
        b = buckets_sorted[0]
        return {b: bucket_consensus[b]}, {b: 'seed'}

    median_tilt = np.median(buckets_sorted)
    center_idx = int(np.argmin([abs(b - median_tilt) for b in buckets_sorted]))
    window = max(1, anchor_tilts)
    half = window // 2
    start = max(0, center_idx - half)
    end = min(len(buckets_sorted), start + window)
    start = max(0, end - window)

    seed_buckets = buckets_sorted[start:end]
    resolved = {b: bucket_consensus[b] for b in seed_buckets}
    status = {b: 'seed' for b in seed_buckets}

    for direction, idx, edge in ((-1, start - 1, start), (1, end, end - 1)):
        nearest = resolved[buckets_sorted[edge]]
        i = idx
        while 0 <= i < len(buckets_sorted):
            b = buckets_sorted[i]
            own_angle = bucket_consensus[b]
            deviation = min(abs(own_angle - nearest), 180 - abs(own_angle - nearest))
            if deviation <= angle_outlier_threshold:
                resolved[b] = own_angle
                status[b] = 'accepted'
                nearest = own_angle
            else:
                resolved[b] = nearest
                status[b] = 'rejected'
                logger.warning(
                    "tilt {}° consensus angle ({}°) deviates {}° from nearest resolved angle ({}°) - using that angle instead",
                    b, f'{own_angle:.1f}', f'{deviation:.1f}', f'{nearest:.1f}',
                )
            i += direction

    return resolved, status

def _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold, anchor_tilts=5, print_angles=False, output_dir=None):
    angles, confidences = {}, {}
    for path in paths:
        data, _ = readMrcFile(path)
        angle, energy = estimate_curtain_angle(data[0])
        median_energy = np.median(energy)
        confidences[path] = energy.max() / median_energy if median_energy > 0 else 0.0
        angles[path] = angle
        logger.debug('({}) tilt {}° est. angle: {} (conf.: {})', path.name, tilt_of[path], angle, confidences[path])

    # A single spuriously sharp FFT peak can otherwise dominate its bucket's consensus
    raw_confidences = dict(confidences)
    conf_values = np.array(list(confidences.values()))
    if len(conf_values):
        median_conf = np.median(conf_values)
        mad = np.median(np.abs(conf_values - median_conf))
        confidence_cap = median_conf + 3 * 1.4826 * mad if mad > 0 else median_conf * 5
    else:
        confidence_cap = 0.0
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
        # High-tilt frames carry less signal (sample thickness grows ~1/cos(tilt)) so reduce weighting within a series
        bucket_weight[bucket] = np.median(bucket_confidences) * np.cos(np.deg2rad(bucket))
        logger.info('tilt {}°: consensus angle {}° (agreement: {}, n={})', bucket, f'{consensus:.1f}', f'{agreement:.3f}', len(bucket_paths))

    series_list = _split_series(tilt_buckets)
    resolved_consensus = {}
    series_of_bucket = {}
    status_of_bucket = {}
    for series_id, series_buckets in enumerate(series_list):
        series_resolved, series_status = _resolve_series(series_buckets, bucket_consensus, angle_outlier_threshold, anchor_tilts)
        resolved_consensus.update(series_resolved)
        status_of_bucket.update(series_status)
        for b in series_buckets:
            series_of_bucket[b] = series_id
        logger.info('series {}: {} tilt bucket(s), tilts {}° to {}°', series_id, len(series_buckets), min(series_buckets), max(series_buckets))

    if print_angles:
        _report_angle_estimates(output_dir, paths, tilt_of, angles, raw_confidences, confidences, bucket_consensus, bucket_weight, series_of_bucket, status_of_bucket, resolved_consensus, series_list)

    return {path: resolved_consensus[round(tilt_of[path])] for path in paths}

def _report_angle_estimates(
    output_dir,
    paths,
    tilt_of,
    angles,
    raw_confidences,
    confidences,
    bucket_consensus,
    bucket_weight,
    series_of_bucket,
    status_of_bucket,
    resolved_consensus,
    series_list,
):
    # create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # per-file estimates go to a CSV
    csv_path = output_dir / 'per_file_angle_estimates.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['file', 'tilt_bucket', 'series', 'angle_deg', 'raw_confidence', 'clipped_confidence', 'bucket_status'])
        for path in paths:
            bucket = round(tilt_of[path])
            writer.writerow([
                path.name,
                bucket,
                series_of_bucket[bucket],
                f'{angles[path]:.2f}',
                f'{raw_confidences[path]:.3f}',
                f'{confidences[path]:.3f}',
                status_of_bucket[bucket],
            ])
    logger.info('per-file angle estimates written to {}', csv_path)

    # per-tilt consensus is printed to stdout and csv
    console = Console()
    n_by_bucket = {}
    for path in paths:
        n_by_bucket[round(tilt_of[path])] = n_by_bucket.get(round(tilt_of[path]), 0) + 1
    for series_id, series_buckets in enumerate(series_list):
        series_csv_path = output_dir / f'per_tilt_angle_estimates_{series_id}.csv'
        buckets_sorted = sorted(series_buckets)
        seed_buckets = sorted(b for b in buckets_sorted if status_of_bucket[b] == 'seed')
        table = Table(title=f'Series {series_id}: tilts {buckets_sorted[0]}° to {buckets_sorted[-1]}° (anchor: {seed_buckets})')
        table.add_column('tilt bucket', justify='right')
        table.add_column('n', justify='right')
        table.add_column('bucket consensus °', justify='right')
        table.add_column('resolved °', justify='right')
        table.add_column('weight', justify='right')
        table.add_column('status', justify='center')
        with open(series_csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['tilt bucket', 'n', 'bucket consensus °', 'resolved °', 'weight', 'status'])
            for bucket in buckets_sorted:
                status = status_of_bucket[bucket]
                table.add_row(
                    str(bucket),
                    str(n_by_bucket[bucket]),
                    f'{bucket_consensus[bucket]:.1f}',
                    f'{resolved_consensus[bucket]:.1f}',
                    f'{bucket_weight[bucket]:.2f}',
                    f'[{_STATUS_COLORS[status]}]{status}[/{_STATUS_COLORS[status]}]',
                )
                writer.writerow([
                    str(bucket),
                    str(n_by_bucket[bucket]),
                    f'{bucket_consensus[bucket]:.1f}',
                    f'{resolved_consensus[bucket]:.1f}',
                    f'{bucket_weight[bucket]:.2f}',
                    status_of_bucket[bucket],
                ])
        logger.info('per-tilt angle estimates for series {} written to {}', series_id, series_csv_path)
        console.print(table)
