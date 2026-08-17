'''
PyLisC: frames-mode processing
'''

# Import external libraries
import numpy as np, typer

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
):
    if apply_filter and pixel_size is None:
        raise typer.BadParameter('--pixel-size is required when --apply-filter is set in frames mode (frame headers are not used for pixel size)')

    paths = find_input_files(input_dir, recursive=False)
    if not paths:
        raise typer.BadParameter(f'No frame files found under {input_dir}')
    logger.info('{} frame files found in {}', len(paths), input_dir)

    pattern = compile_template(filename_template, delimiters=filename_delimiters)
    tilt_of = {path: extract_tilt_angle(path.name, pattern) for path in paths}

    output_dir.mkdir(parents=True, exist_ok=True)

    if curtain_angle is None:
        angle_for_path = _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold)
    else:
        angle_for_path = {path: curtain_angle for path in paths}

    for path in paths:
        out_path = output_dir / f'{path.stem}_PyLisC_{mode}.mrc'
        with per_file_log(output_dir, out_path.stem):
            data, _ = readMrcFile(path)
            cleared = lisc_clear_frame(
                data[0],
                decurtaining_mode=mode,
                pixel_size_nm=pixel_size,
                curtain_angle=angle_for_path[path],
                apply_filter=apply_filter,
                filter_threshold_nm=filter_threshold,
                angular_width_deg=angular_width,
                destripe_notch_fraction=notch_frac,
                dc_protect_frac=dc_protect_frac,
            )
            writeMrcFile(cleared[np.newaxis, ...], _read_voxel_size(path), out_path)
            logger.debug('({}) cleared mrc file wrote to {}', path.name, out_path)

    logger.info('cleared mrc files written to {}', output_dir)


def _read_voxel_size(path):
    _, voxel_size = readMrcFile(path)
    return voxel_size


def _estimate_per_tilt_angles(paths, tilt_of, angle_outlier_threshold):
    angles, confidences = {}, {}
    for path in paths:
        data, _ = readMrcFile(path)
        angle, energy = estimate_curtain_angle(data[0])
        median_energy = np.median(energy)
        confidences[path] = energy.max() / median_energy if median_energy > 0 else 0.0
        angles[path] = angle
        logger.debug('({}) tilt {}° est. angle: {} (conf.: {})', path.name, tilt_of[path], angle, confidences[path])

    tilt_buckets = {}
    for path in paths:
        bucket = round(tilt_of[path])
        tilt_buckets.setdefault(bucket, []).append(path)

    bucket_consensus = {}
    for bucket, bucket_paths in tilt_buckets.items():
        consensus, agreement = combine_angles(
            [angles[p] for p in bucket_paths],
            [confidences[p] for p in bucket_paths],
        )
        bucket_consensus[bucket] = consensus
        logger.info('tilt {}°: consensus angle {}° (agreement: {}, n={})', bucket, f'{consensus:.1f}', f'{agreement:.3f}', len(bucket_paths))

    overall_consensus, overall_agreement = combine_angles(
        list(bucket_consensus.values()), [1.0] * len(bucket_consensus)
    )
    logger.info('overall consensus across {} tilt angle(s): {}° (agreement: {})', len(bucket_consensus), f'{overall_consensus:.1f}', f'{overall_agreement:.3f}')

    for bucket, angle in bucket_consensus.items():
        deviation = min(abs(angle - overall_consensus), 180 - abs(angle - overall_consensus))
        if deviation > angle_outlier_threshold:
            logger.warning('tilt {}° consensus angle ({}°) deviates {}° from overall consensus ({}°) - check per-tilt agreement', bucket, f'{angle:.1f}', f'{deviation:.1f}', f'{overall_consensus:.1f}')

    return {path: bucket_consensus[round(tilt_of[path])] for path in paths}
