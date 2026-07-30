'''
PyLisC: single series processing
'''

# Import external libraries
import numpy as np, mrcfile, typer
from pathlib import Path

# Import internal PyLisC modules
from pylisc.estimate_angle import estimate_curtain_angle, plot_angular_energy
from pylisc.io import readMrcFile, writeMrcFile
from pylisc.lisc import lisc_clear_frame
from pylisc.preview import generate_strength_preview


def run_single(
    input_path,
    output_mrc,
    verbose,
    mode,
    filter_threshold,
    pixel_size,
    curtain_angle,
    reference_frame,
    angular_width,
    notch_frac,
    dc_protect_frac,
    preview_strengths,
):
   # Set output file path if none provided
    if output_mrc is None:
            base_stem = f'{input_path.stem}_PyLisC_{mode}'
            output_mrc = Path(f'{input_path.parents[0]}/{base_stem}.mrc')
            if output_mrc.exists():
                counter = 1
                while True:
                    output_mrc = Path(f'{input_path.parents[0]}/{base_stem}_{counter}.mrc')
                    if not output_mrc.exists():
                        break
                    counter += 1

    # Read data from input_path
    data, voxel_size = readMrcFile(input_path)

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

    # Estimate curtaining angle
    if curtain_angle is None:
        curtain_angle, angular_energy = estimate_curtain_angle(data[reference_frame])
        plot_angular_energy(angular_energy, curtain_angle, output_dir=output_mrc.parent)
    else:
        angular_energy = None

    if preview_strengths is not None:
        values = [float(v) for v in preview_strengths.split(',')]
        preview_path = generate_strength_preview(
            data[reference_frame],
            mode=mode,
            pixel_size_nm = pixel_size,
            values=values,
            curtain_angle=curtain_angle,
            filter_threshold_nm=filter_threshold,
            dc_protect_frac=dc_protect_frac,
            notch_frac=notch_frac,
            output_dir=output_mrc.parent,
        )
        print(f'Strength preview saved to {preview_path}')
        raise typer.Exit()

    # Output processing information if verbose
    if verbose:
        print()
        print(f'Input file: {input_path}')
        print(f'Output file: {output_mrc}')
        print(f'Voxel size: {voxel_size}')
        print(f'Pixel size: {pixel_size}')
        print(f'{"Estimated c" if angular_energy is not None else "C"}urtaining angle: {curtain_angle}{f"°; confidence: {angular_energy.max()/np.median(angular_energy)}" if angular_energy is not None else "°"}')
        print()

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
    writeMrcFile(cleared_stack, voxel_size, output_mrc)