'''
PyLisC: batch processing and directory-wide curtain angle consensus
'''

# Import external libraries
import numpy as np, mrcfile

# Import internal PyLisC modules
from pylisc.estimate_angle import combine_angles, estimate_curtain_angle
from pylisc.lisc import lisc_clear_frame
from pylisc.log import logger
from pylisc.io import find_tilt_series, nameOutputFile, readMrcFile, writeMrcFile

def run_batch(
    input_dir,
    output_dir,
    mode,
    filter_threshold,
    pixel_size,
    curtain_angle,
    reference_frame,
    angular_width,
    notch_frac,
    dc_protect_frac,
    angle_outlier_threshold,
):
    series_paths = find_tilt_series(input_dir)
    if not series_paths:
        raise typer.BadParameter(f'No tilt series found under {input_dir}')
    logger.info('{} files found in {}', len(series_paths), input_dir)

    if curtain_angle is None:
        angles, confidences, per_series_energy = [], [], []
        for path in series_paths:
            data, _ = readMrcFile(path)
            if reference_frame is None:
                reference_frame = len(data) // 2
            frame = data[reference_frame]
            angle, energy = estimate_curtain_angle(frame)
            confidence = energy.max() / np.median(energy)
            angles.append(angle); confidences.append(confidence); per_series_energy.append(energy)
            log.debug('({}) est. angle: {} (conf.: {})', path.name, angle, confidence)

        consensus_angle, agreement = combine_angles(angles, confidences)
        log.info('batch consensus angle: {}° (agreement: {})', '{consensus_angle:.1f}', '{agreement:.3f}')

        for path, angle in zip(series_paths, angles):
            deviation = min(abs(angle - consensus_angle), 180 - abs(angle - consensus_angle))
            if deviation > angle_outlier_threshold:
                log.warning('({}) est. angle ({}°) deviates {}° from consensus ({}°) - check diagnostic plot', path.name, '{angle:.1f}', '{deviation:.1f}', '{consensus_angle:.1f}')

        curtain_angle = consensus_angle

    for path in series_paths:
        relative = path.relative_to(input_dir)
        out_path = output_dir / relative.parent / f'{path.stem}_PyLisC_{mode}.mrc'
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Read data from path
        data, voxel_size = readMrcFile(path)

        # Resolve pixel size
        if pixel_size is None:
            pixel_size = float(voxel_size.x) / 10.0
            logger.debug('({}) pixel size ({}) resolved from mrc', path.name, pixel_size)
        if pixel_size <= 0:
            raise ValueError('Pixel size cannot be less than or equal to 0')

        # Resolve reference frame (use mid-frame as should be ok for both dose-symmetric & continuous acquisitions)
        if reference_frame is None:
            reference_frame = len(data) // 2
            logger.debug('({}) reference_frame defaulted to: {}', path.name, reference_frame)

        # Create placeholder for cleared frames
        cleared_stack = np.empty_like(data, dtype=np.float32)

        # Apply LisC to each frame
        for i, frame in enumerate(data):
            cleared = lisc_clear_frame(
                frame,
                decurtaining_mode=mode,
                pixel_size_nm=pixel_size,
                curtain_angle=curtain_angle,
                filter_threshold_nm=filter_threshold,
                angular_width_deg=angular_width,
                destripe_notch_fraction=notch_frac,
                dc_protect_frac=dc_protect_frac,
            )
            cleared_stack[i] = cleared

        # Save output MRC
        writeMrcFile(cleared_stack, voxel_size, out_path)
        log.debug('({}) cleared mrc file wrote to {}', path.name, output_mrc)
    log.info('cleared mrc files written to {}', output_dir)