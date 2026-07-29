'''
PyLisC: command-line entry point
'''

# Import external libraries
from pathlib import Path
from typing import Annotated, Literal, Optional

try:
    import matplotlib, mrcfile, numpy as np, tifffile, typer
except ImportError as e:
    raise ImportError('PyLisC requirements not met. Please see README for information.') from e

# Import internal PyLisC modules
from pylisc.batch import run_batch
from pylisc.estimate_angle import estimate_curtain_angle, plot_angular_energy
from pylisc.lisc import lisc_clear_frame

# Set up Typer class
pylisc = typer.Typer(
    rich_markup_mode='rich',
    add_completion=False,
    no_args_is_help=True,
)

# Define command for pylisc
@pylisc.command()
def main(
    input_path: Annotated[
        Path,
        typer.Argument(help='MRC file to apply LisC algorithm to')
    ],
    mode: Annotated[
        Literal['angular', 'linear'],
        typer.Option('-m', '--mode', help='Method of de-curtaining to use (angular or linear)', rich_help_panel='De-curtaining options')
    ],
    output_mrc: Annotated[
        Optional[Path],
        typer.Argument(help='Path to output MRC file (defaults to the same filename as input_path with _PyLisC_[mode] suffix)', exists=False)
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option('--output-dir', help='Output directory for batch mode (required when input_path is a directory)', rich_help_panel='Batch options')
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option('-v', '--verbose', help='Print additional progress messages')
    ] = False,
    filter_threshold: Annotated[
        float,
        typer.Option('--filter-threshold', help='High-pass cutoff (nm)', rich_help_panel='Filtering options',)
    ] = 5000.0,
    pixel_size: Annotated[
        Optional[float],
        typer.Option('--pixel-size', help='Override pixel size (nm) read from MRC header', rich_help_panel='Filtering options')
    ] = None,
    curtain_angle: Annotated[
        Optional[float],
        typer.Option('--angle', help='Angle of curtaining from horizontal (0°)', rich_help_panel='De-curtaining options')
    ] = None,
    reference_frame: Annotated[
        Optional[int],
        typer.Option('--reference-frame', help='Stack index used for angle estimation and the destriping preview', rich_help_panel='De-curtaining options', min=0)
    ] = None,
    angular_width: Annotated[
        float,
        typer.Option('--angular-width', help='Angular width (degrees) of the directional destriping notch. Narrower keeps more real structure at the cost of weaker curtain removal; only structure at the same angle as the curtains is unavoidably attenuated.', rich_help_panel='De-curtaining options')
    ] = 8.0,
    preview_strengths: Annotated[
        Optional[str],
        typer.Option('--preview-strengths', help='Comma-separated values to preview before committing to a full run (angular width in degrees for --mode angular, notch fraction for --mode linear)', rich_help_panel='De-curtaining options')
    ] = None,
    notch_frac: Annotated[
        float,
        typer.Option('--notch-fraction', help='Width of the directional destriping notch as a fraction of image width', rich_help_panel='De-curtaining options')
    ] = 0.03,
    dc_protect_frac: Annotated[
        float,
        typer.Option('--protect-fraction', help='Fraction of image width around Fourier origin exempted from destriping', rich_help_panel='De-curtaining options')
    ] = 0.01,
    angle_outlier_threshold: Annotated[
        float,
        typer.Option('--angle-outlier-threshold', help='Warn if an individual series\' own angle estimate differs from the batch consensus by more than this many degrees.', rich_help_panel='Batch options')
    ] = 5.0,
):
    # Branch on single file vs directory
    if input_path.is_dir():
        if output_dir is None:
            raise typer.BadParameter('--output-dir is required when input_path is a directory')
        if output_mrc is not None:
            print(f'Ignoring output filename: {output_mrc}')
        run_batch(
            input_dir=input_path,
            output_dir=output_dir,
            verbose=verbose,
            mode=mode,
            filter_threshold=filter_threshold,
            pixel_size=pixel_size, 
            curtain_angle=curtain_angle,
            reference_frame=reference_frame,
            angular_width=angular_width,
            notch_frac=notch_frac,
            dc_protect_frac=dc_protect_frac,
            angle_outlier_threshold=angle_outlier_threshold,
        )
        raise typer.Exit()

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
    with mrcfile.open(input_path, permissive=True) as mrc:
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
    with mrcfile.new(output_mrc, overwrite=True) as out:
        out.set_data(cleared_stack.astype(np.float32))
        out.voxel_size = voxel_size