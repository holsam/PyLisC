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
from pylisc.frames import run_frames
from pylisc.log import configure_logger, logger
from pylisc.stack import run_stack

# Set up Typer class
pylisc = typer.Typer(
    rich_markup_mode='rich',
    add_completion=False,
    no_args_is_help=True,
)

# Shared options
ModeOpt = Annotated[
    Literal['angular', 'linear'],
    typer.Option('-m', '--mode', help='Method of de-curtaining to use. [dim]\\[default: angular][/dim] [bold yellow]\\[WARNING: linear mode is deprecated, angular mode is recommended][/]', show_default=False, rich_help_panel='De-curtaining options'),
]
VerbosityOpt = Annotated[
    int,
    typer.Option('-v', '--verbose', count=True, help='Increase verbosity of logging.'),
]
ApplyFilterOpt = Annotated[
    bool,
    typer.Option('--apply-filter', help='Apply high-pass filter before destriping.', rich_help_panel='Filtering options', show_default=False),
]
FilterThresholdOpt = Annotated[
    float,
    typer.Option('--filter-threshold', help='High-pass filter cutoff (nm).', rich_help_panel='Filtering options'),
]
CurtainAngleOpt = Annotated[
    Optional[float],
    typer.Option('--angle', help='Angle of curtaining from horizontal (0°). If omitted, estimated automatically.', rich_help_panel='De-curtaining options'),
]
AngularWidthOpt = Annotated[
    float,
    typer.Option('--angular-width', help='Angular width (degrees) of the directional destriping notch. Narrower keeps more real structure at the cost of weaker curtain removal; only structure at the same angle as the curtains is unavoidably attenuated.', rich_help_panel='De-curtaining options'),
]
NotchFracOpt = Annotated[
    float,
    typer.Option('--notch-fraction', help='Width of the directional destriping notch as a fraction of image width in linear mode. [dim]\\[default: 0.03][/dim] [bold yellow]\\[WARNING: linear mode is deprecated][/]', show_default=False, rich_help_panel='De-curtaining options'),
]
DcProtectFracOpt = Annotated[
    float,
    typer.Option('--protect-fraction', help='Fraction of image width around Fourier origin exempted from destriping in linear mode. [dim]\\[default: 0.01][/dim] [bold yellow]\\[WARNING: linear mode is deprecated][/]', show_default=False, rich_help_panel='De-curtaining options'),
]
AngleOutlierThresholdOpt = Annotated[
    float,
    typer.Option('--angle-outlier-threshold', help='Warn if an individual angle estimate differs from its consensus by more than this many degrees.', rich_help_panel='Batch options'),
]

@pylisc.command()
def stack(
    input_path: Annotated[
        Path,
        typer.Argument(help='MRC tilt-series stack, or a directory of them, to apply LisC algorithm to.')
    ],
    output_mrc: Annotated[
        Optional[Path],
        typer.Argument(help='Path to output MRC file (defaults to the same filename as input_path with _PyLisC_[mode] suffix).', exists=False)
    ] = None,
    output_dir: Annotated[
        Optional[Path],
        typer.Option('--output-dir', help='Output directory for batch mode (required when input_path is a directory).', rich_help_panel='Batch options')
    ] = None,
    mode: ModeOpt = 'angular',
    verbosity: VerbosityOpt = 0,
    apply_filter: ApplyFilterOpt = False,
    filter_threshold: FilterThresholdOpt = 5000.0,
    pixel_size: Annotated[
        Optional[float],
        typer.Option('--pixel-size', help='Override pixel size (nm) read from MRC header.', rich_help_panel='Filtering options', min=0)
    ] = None,
    curtain_angle: CurtainAngleOpt = None,
    reference_frame: Annotated[
        Optional[int],
        typer.Option('--reference-frame', help='Stack index used for angle estimation and the destriping preview.', rich_help_panel='De-curtaining options', min=0)
    ] = None,
    angular_width: AngularWidthOpt = 8.0,
    preview_strengths: Annotated[
        Optional[str],
        typer.Option('--preview-strengths', help='Comma-separated values to preview before committing to a full run (angular width in degrees for --mode angular, notch fraction for --mode linear).', rich_help_panel='De-curtaining options')
    ] = None,
    notch_frac: NotchFracOpt = 0.03,
    dc_protect_frac: DcProtectFracOpt = 0.01,
    angle_outlier_threshold: AngleOutlierThresholdOpt = 5.0,
):
    '''
    Destripe a single MRC tilt-series stack, or a directory of them.
    '''
    if input_path.is_dir():
        if output_dir is None:
            raise typer.BadParameter('--output-dir is required when input_path is a directory')
        if output_mrc is not None:
            print(f'Ignoring argument: {output_mrc} (output filename)')
        if preview_strengths is not None:
            print(f'Ignoring option: --preview-strengths {preview_strengths}')
        is_dir = True
    else:
        if output_dir is not None:
            print(f'Ignoring option: --output-dir {output_dir}')
        is_dir = False
    verbosity = 2 if verbosity >= 2 else verbosity

    configure_logger(is_dir, input_path, output_mrc, output_dir, verbosity)
    logger.debug('running pylisc stack with: {}', ', '.join(f'{i[0]}: {i[1]}' for i in locals().items()))

    if mode == 'linear':
        logger.warning('Linear destriping mode is deprecated and may be removed in future updates. Angular destriping is more effective and is the recommended destriping mode.')

    run_stack(
        input_path=input_path,
        output_mrc=output_mrc,
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
        preview_strengths=preview_strengths,
    )
    logger.info('pylisc completed')
    raise typer.Exit()

@pylisc.command()
def frames(
    input_path: Annotated[
        Path,
        typer.Argument(help='Directory of individual 2D MRC frames (e.g. one micrograph per tilt) to apply LisC algorithm to.')
    ],
    output_dir: Annotated[
        Path,
        typer.Option('--output-dir', help='Output directory.')
    ],
    filename_template: Annotated[
        str,
        typer.Option('--filename-template', help='Template string describing the delimited filename fields, see README for further information.')
    ],
    filename_delimiters: Annotated[
        str,
        typer.Option('--filename-delimiters', help='Characters that separate filename fields, see README for further information.')
    ] = '_',
    mode: ModeOpt = 'angular',
    verbosity: VerbosityOpt = 0,
    apply_filter: ApplyFilterOpt = False,
    filter_threshold: FilterThresholdOpt = 5000.0,
    pixel_size: Annotated[
        Optional[float],
        typer.Option('--pixel-size', help='Pixel size (nm). Required if --apply-filter is set (frame headers are not used for pixel size).', rich_help_panel='Filtering options', min=0)
    ] = None,
    curtain_angle: CurtainAngleOpt = None,
    angular_width: AngularWidthOpt = 8.0,
    notch_frac: NotchFracOpt = 0.03,
    dc_protect_frac: DcProtectFracOpt = 0.01,
    angle_outlier_threshold: AngleOutlierThresholdOpt = 5.0,
):
    '''
    Destripe a directory of 2D MRC frames.
    '''
    verbosity = 2 if verbosity >= 2 else verbosity

    configure_logger(True, input_path, None, output_dir, verbosity)
    logger.debug('running pylisc frames with: {}', ', '.join(f'{i[0]}: {i[1]}' for i in locals().items()))

    if mode == 'linear':
        logger.warning('Linear destriping mode is deprecated and may be removed in future updates. Angular destriping is more effective and is the recommended destriping mode.')

    run_frames(
        input_dir=input_path,
        output_dir=output_dir,
        filename_template=filename_template,
        filename_delimiters=filename_delimiters,
        mode=mode,
        apply_filter=apply_filter,
        filter_threshold=filter_threshold,
        pixel_size=pixel_size,
        curtain_angle=curtain_angle,
        angular_width=angular_width,
        notch_frac=notch_frac,
        dc_protect_frac=dc_protect_frac,
        angle_outlier_threshold=angle_outlier_threshold,
    )
    logger.info('pylisc completed')
    raise typer.Exit()
