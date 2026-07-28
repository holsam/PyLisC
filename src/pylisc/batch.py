'''
PyLisC: batch processing and directory-wide curtain angle consensus
'''

# Import external libraries
import numpy as np


def combine_angles(angles_deg: list, confidences: list) -> tuple:
    '''
    Confidence-weighted circular mean of curtain angles
    '''
    angles = np.asarray(angles_deg, dtype=float)
    conf = np.asarray(confidences, dtype=float)
    doubled = np.deg2rad(angles * 2)
    x = np.sum(conf * np.cos(doubled))
    y = np.sum(conf * np.sin(doubled))
    consensus = np.degrees(np.arctan2(y, x)) / 2
    consensus = ((consensus + 90) % 180) - 90  # wrap to (-90, 90]
    agreement = np.sqrt(x ** 2 + y ** 2) / conf.sum()
    return float(consensus), float(agreement)


def find_tilt_series(input_dir, pattern: str = '*.mrc'):
    '''
    Recursively find tilt series MRCs under input_dir, excluding PyLisC's own output
    '''
    return sorted(
        p for p in input_dir.rglob(pattern)
        if '_PyLisC_' not in p.stem
    )

def run_batch(
    input_dir,
    output_dir,
    verbose,
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

    if curtain_angle is None:
        angles, confidences, per_series_energy = [], [], []
        for path in series_paths:
            with mrcfile.open(path, permissive=True) as mrc:
                frame = mrc.data[reference_frame].astype(np.float32) if mrc.data.ndim == 3 else mrc.data.astype(np.float32)
            angle, energy = estimate_curtain_angle(frame)
            confidence = energy.max() / np.median(energy)
            angles.append(angle); confidences.append(confidence); per_series_energy.append(energy)

        consensus_angle, agreement = combine_angles(angles, confidences)
        if verbose:
            print(f'Batch consensus angle: {consensus_angle:.1f} deg (agreement: {agreement:.3f})')

        for path, angle in zip(series_paths, angles):
            deviation = min(abs(angle - consensus_angle), 180 - abs(angle - consensus_angle))
            if deviation > angle_outlier_threshold:
                print(f'WARNING: {path.name} angle ({angle:.1f} deg) deviates {deviation:.1f} deg '
                      f'from consensus ({consensus_angle:.1f} deg) -- check its diagnostic plot')

        curtain_angle = consensus_angle

    for path in series_paths:
        relative = path.relative_to(input_dir)
        out_path = output_dir / relative.parent / f'{path.stem}_PyLisC_{mode}.mrc'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # ... run the existing single-series clearing loop against `path` -> `out_path`,
        #     with curtain_angle fixed to the consensus (no per-series re-estimation)
        # Read data from path
        with mrcfile.open(path, permissive=True) as mrc:
            data = mrc.data.astype(np.float32)
            voxel_size = mrc.voxel_size # in Ångstroms
        if data.ndim == 2:
            data = data[np.newaxis, ...]
        
        # Resolve pixel size
        if pixel_size is None:
            pixel_size = float(voxel_size.x) / 10.0
        if pixel_size <= 0:
            raise ValueError('Pixel size cannot be less than or equal to 0')

        # Resolve reference frame (use mid-frame as should be ok for both dose-symmetric & continuous acquisitions)
        if reference_frame is None:
            reference_frame = len(data) // 2

        # Create placeholder for cleared frames
        cleared_stack = np.empty_like(data, dtype=np.float32)

        # Apply LisC to each frame
        for i, frame in enumerate(data):
            if verbose:
                print(f'Processing tilt {i+1}/{data.shape[0]}')
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
            print(f'Processed tilt {i+1}/{data.shape[0]}')

        # Save output MRC
        with mrcfile.new(output_mrc, overwrite=True) as out:
            out.set_data(cleared_stack.astype(np.float32))
            out.voxel_size = voxel_size