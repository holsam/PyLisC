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
    input_mrc: Annotated[
        Path,
        typer.Argument(help='MRC file to apply LisC algorithm to')
    ],
    mode: Annotated[
        Literal['angular', 'linear'],
        typer.Option('-m', '--mode', help='Method of de-curtaining to use (angular or linear)', rich_help_panel='De-curtaining options')
    ],
    output_mrc: Annotated[
        Optional[Path],
        typer.Argument(help='Path to output MRC file (defaults to the same filename as input_mrc with _PyLisC_[mode] suffix)', exists=False)
    ] = None,
    pixel_size: Annotated[
        Optional[float],
        typer.Option('--pixel-size', help='Override pixel size (nm) read from MRC header')
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option('-v', '--verbose', help='Print additional progress messages')
    ] = False,
    curtain_angle: Annotated[
        Optional[float],
        typer.Option('--angle', help='Angle of curtaining from horizontal (0°)', rich_help_panel='De-curtaining options')
    ] = None,
    filter_threshold: Annotated[
        float,
        typer.Option('--filter-threshold', help='High-pass cutoff (nm)', rich_help_panel='De-curtaining options')
    ] = 5000.0,
    angular_width: Annotated[
        float,
        typer.Option('--angular-width', help='Angular width (degrees) of the directional destriping notch. Narrower keeps more real structure at the cost of weaker curtain removal; only structure at the same angle as the curtains is unavoidably attenuated.', rich_help_panel='De-curtaining options')
    ] = 8.0,
    notch_frac: Annotated[
        float,
        typer.Option('--notch-fraction', help='Width of the directional destriping notch as a fraction of image width', rich_help_panel='De-curtaining options')
    ] = 0.03,
    dc_protect_frac: Annotated[
        float,
        typer.Option('--protect-fraction', help='Fraction of image width around Fourier origin exempted from destriping', rich_help_panel='De-curtaining options')
    ] = 0.01,
):
    # Set output file path if none provided
    if output_mrc is None:
            base_stem = f'{input_mrc.stem}_PyLisC_{mode}'
            output_mrc = Path(f'{input_mrc.parents[0]}/{base_stem}.mrc')
            if output_mrc.exists():
                counter = 1
                while True:
                    output_mrc = Path(f'{input_mrc.parents[0]}/{base_stem}_{counter}.mrc')
                    if not output_mrc.exists():
                        break
                    counter += 1

    # Read data from input_mrc
    with mrcfile.open(input_mrc, permissive=True) as mrc:
        data = mrc.data.astype(np.float32)
        voxel_size = mrc.voxel_size # in Ångstroms
    if data.ndim == 2:
        data = data[np.newaxis, ...]

    # Resolve pixel size
    if pixel_size is None:
        pixel_size = float(voxel_size.x) / 10.0
    if pixel_size <= 0:
        raise ValueError('Pixel size cannot be less than or equal to 0')

    # Create placeholder for cleared frames
    cleared_stack = np.empty_like(data, dtype=np.float32)

    # Estimate curtaining angle
    if curtain_angle is None:
        mid_frame = len(data) // 2
        curtain_angle, angular_energy = estimate_curtain_angle(data[mid_frame])
        plot_angular_energy(angular_energy, curtain_angle, output_dir=output_mrc.parent)
    else:
        angular_energy = None

    # Output processing information if verbose
    if verbose:
        print()
        print(f'Input file: {input_mrc}')
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