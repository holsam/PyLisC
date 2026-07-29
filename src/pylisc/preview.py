'''
PyLisC: generate a preview of different strengths against a single frame
'''

# Import external libraries
from pathlib import Path

# Import internal PyLisC modules
from pylisc.estimate_angle import estimate_curtain_angle
from pylisc.lisc import lisc_clear_frame


def generate_strength_preview(
    reference_frame,
    mode,
    pixel_size_nm,
    values,
    curtain_angle,
    filter_threshold_nm,
    dc_protect_frac,
    notch_frac,
    output_dir,
    dpi=150
):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    n = len(values)
    fig, axes = plt.subplots(1, n, figsize=(4 * n, 4))
    if n == 1:
        axes = [axes]
    for ax, value in zip(axes, values):
        if mode == 'angular':
            cleared = lisc_clear_frame(
                reference_frame,
                decurtaining_mode='angular',
                pixel_size_nm=pixel_size_nm,
                curtain_angle=curtain_angle,
                filter_threshold_nm=filter_threshold_nm,
                angular_width_deg=value
            )
            label = f'angular_width={value:g}\u00b0'
        else:
            cleared = lisc_clear_frame(
                reference_frame,
                decurtaining_mode='linear',
                pixel_size_nm=pixel_size_nm,
                curtain_angle=curtain_angle,
                filter_threshold_nm=filter_threshold_nm,
                destripe_notch_fraction=value,
                dc_protect_frac=dc_protect_frac
            )
            label = f'notch_fraction={value:g}'
        ax.imshow(cleared, cmap='gray')
        ax.set_title(label, fontsize=10)
        ax.axis('off')
    fig.tight_layout()
    output_path = Path(output_dir) / 'destripe_strength_preview.tiff'
    fig.savefig(output_path, format='tiff', dpi=dpi)
    plt.close(fig)
    return output_path