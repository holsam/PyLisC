'''
PyLisC: command-line entry point
'''

# Import external libraries
from importlib.metadata import version
from pathlib import Path
from rich.console import Console
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
    context_settings={'help_option_names': ['-h', '--help']},
)

# Set up version callback
def version_callback(value: bool | None) -> None:
    if value:
        Console().print(f'\nPyLisC version: [bold cyan]v{version('pylisc')}[/bold cyan]\n', highlight=False)
        raise typer.Exit()

# Shared options
VersionOpt = Annotated[
    bool | None,
    typer.Option('-V', '--version', help='Print version number and exit.', callback=version_callback, is_eager=True),
]
ModeOpt = Annotated[
    Literal['angular', 'linear'],
    typer.Option('-m', '--mode', help='Method of de-curtaining to use. [dim]\\[default: angular][/dim] [bold yellow]\\[WARNING: linear mode is deprecated, angular mode is recommended][/]', show_default=False, rich_help_panel='De-curtaining options'),
]
VerbosityOpt = Annotated[
    int,
    typer.Option('-v', '--verbose', count=True, help='Increase verbosity of logging.', show_default=False, metavar=''),
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
ForceOpt = Annotated[
    bool,
    typer.Option('--force', help='Overwrite existing output files.', show_default=False)
]
DryRunOpt = Annotated[
    bool,
    typer.Option('--dry-run', help='Print what would be processed/written without writing any output.', show_default=False),
]
WorkersOpt = Annotated[
    int,
    typer.Option('--workers', help='Number of parallel processes to use in batch mode (0: all CPUs).', min=0, rich_help_panel='Batch options'),
]
PrintAnglesOpt = Annotated[
    bool,
    typer.Option('--print-angles', help='Print a diagnostic table of per-file and per-bucket angle estimation (frames mode only).', rich_help_panel='Batch options', show_default=False),
]
AnchorTiltsOpt = Annotated[
    int,
    typer.Option('--anchor-tilts', help='Number of tilt buckets nearest each series\' median tilt used to seed its consensus walk (frames mode only).', rich_help_panel='Batch options', min=1),
]

# Define callback for pylisc (to allow version option)
@pylisc.callback()
def main(
    version: VersionOpt = None,
):
    pass

# Define command for pylisc stack
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
    dry_run: DryRunOpt = False,
    force: ForceOpt = False,
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
    version: VersionOpt = None,
    workers: WorkersOpt = 0,
):
    '''
    Destripe a single MRC tilt-series stack, or a directory of them.
    '''
    verbosity = 2 if verbosity >= 2 else verbosity
    configure_logger(input_path.is_dir(), input_path, output_mrc, output_dir, verbosity)
    logger.debug('running pylisc stack with: {}', ', '.join(f'{i[0]}: {i[1]}' for i in locals().items()))

    if angular_width <= 0:
        logger.error('angular width cannot be equal to or less than 0: {}', angular_width)
        raise typer.BadParameter(f'angular width cannot be equal to or less than 0: {angular_width}')

    if input_path.is_dir():
        if output_dir is None:
            raise typer.BadParameter('--output-dir is required when input_path is a directory')
        if output_mrc is not None:
            logger.warning('[batch mode] ignoring argument: {} (output filename)', output_mrc)
        if preview_strengths is not None:
            logger.warning('[batch mode] ignoring option: --preview-strengths {}', preview_strengths)
    else:
        if output_dir is not None:
            logger.warning('[single file mode] ignoring option: --output-dir {}', output_dir)
    
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
        force=force,
        dry_run=dry_run,
        workers=workers,
    )
    logger.info('pylisc completed')
    raise typer.Exit()

# Define command for pylisc frames
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
    dry_run: DryRunOpt = False,
    force: ForceOpt = False,
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
    anchor_tilts: AnchorTiltsOpt = 5,
    print_angles: PrintAnglesOpt = False,
    version: VersionOpt = None,
    workers: WorkersOpt = 0,
):
    '''
    Destripe a directory of 2D MRC frames.
    '''
    verbosity = 2 if verbosity >= 2 else verbosity

    configure_logger(True, input_path, None, output_dir, verbosity)
    logger.debug('running pylisc frames with: {}', ', '.join(f'{i[0]}: {i[1]}' for i in locals().items()))

    if angular_width <= 0:
        logger.error('angular width cannot be equal to or less than 0: {}', angular_width)
        raise typer.BadParameter(f'angular width cannot be equal to or less than 0: {angular_width}')

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
        anchor_tilts=anchor_tilts,
        force=force,
        dry_run=dry_run,
        workers=workers,
        print_angles=print_angles,
    )
    logger.info('pylisc completed')
    raise typer.Exit()
