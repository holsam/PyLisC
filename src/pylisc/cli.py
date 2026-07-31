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
from pylisc.log import configure_logger, logger
from pylisc.single import run_single

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
    verbosity: Annotated[
        int,
        typer.Option('-v', '--verbose', count=True, help='Print additional progress messages')
    ] = 0,
    filter_threshold: Annotated[
        float,
        typer.Option('--filter-threshold', help='High-pass cutoff (nm)', rich_help_panel='Filtering options',)
    ] = 5000.0,
    pixel_size: Annotated[
        Optional[float],
        typer.Option('--pixel-size', help='Override pixel size (nm) read from MRC header', rich_help_panel='Filtering options', min=0)
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
    # CLI argument/option validation
    if input_path.is_dir():
        if output_dir is None:
            raise typer.BadParameter('--output-dir is required when input_path is a directory')
        if output_mrc is not None:
            print(f'Ignoring argument: {output_mrc} (output filename)')
        if preview_strengths is not None:
            print(f'Ignoring option: --preview-strengths {preview_strengths}')
        batch = True
    else:
        if output_dir is not None:
            print(f'Ignoring option: --output-dir {output_dir}')
        batch = False
    verbosity = 2 if verbosity >= 2 else verbosity

    # Set up logging
    configure_logger(batch, input_path, output_mrc, output_dir, verbosity)
    logger.debug('running pylisc with: {}', ', '.join(f'{i[0]}: {i[1]}' for i in locals().items()))

    # Branch on batch vs single processing
    if batch:
        run_batch(
            input_dir=input_path,
            output_dir=output_dir,
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
    else:
        run_single(
            input_path=input_path,
            output_mrc=output_mrc,
            mode=mode,
            filter_threshold=filter_threshold,
            pixel_size=pixel_size, 
            curtain_angle=curtain_angle,
            reference_frame=reference_frame,
            angular_width=angular_width,
            notch_frac=notch_frac,
            dc_protect_frac=dc_protect_frac,
            preview_strengths=preview_strengths,
        )
    logger.info('pylisc completed')
    raise typer.Exit()