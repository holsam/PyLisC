'''
PyLisC: curtain angle estimation from FFT power spectrum and diagnostic plotting
'''

# Import external libraries
from pathlib import Path

import matplotlib, matplotlib.pyplot as plt, numpy as np
from scipy import ndimage as ndi

def estimate_curtain_angle(
    frame: np.ndarray,
    r_min_frac: float = 0.02,
    r_max_frac: float = 0.45,
    angle_bins: int = 180,
    max_size: int = 1024,
):
    '''
    Estimate curtaining orientation by finding the dominant ridge direction in the image's power spectrum
    '''
    work = frame.astype(np.float32)
    ny, nx = work.shape
    scale = max(ny, nx) / max_size
    if scale > 1:
        work = ndi.zoom(work, zoom=1.0 / scale, order=1)
        ny, nx = work.shape
    work = work - work.mean()
    window = np.outer(np.hanning(ny), np.hanning(nx))
    spectrum = np.fft.fftshift(np.fft.fft2(work * window))
    power = np.abs(spectrum) ** 2
    yy, xx = np.mgrid[0:ny, 0:nx]
    cy, cx = ny // 2, nx // 2
    ky, kx = yy - cy, xx - cx
    r = np.sqrt(kx ** 2 + ky ** 2)
    r_nyquist = min(cy, cx)
    annulus = (r >= r_min_frac * r_nyquist) & (r <= r_max_frac * r_nyquist)
    phi = np.degrees(np.arctan2(ky, kx)) % 180  # fold: a line has no direction
    bin_edges = np.linspace(0, 180, angle_bins + 1)
    bin_idx = np.clip(np.digitize(phi[annulus], bin_edges) - 1, 0, angle_bins - 1)
    angular_energy = np.bincount(bin_idx, weights=power[annulus], minlength=angle_bins)
    # light circular smoothing so a single noisy bin doesn't win
    smooth_kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0])
    smooth_kernel /= smooth_kernel.sum()
    padded = np.concatenate([angular_energy[-2:], angular_energy, angular_energy[:2]])
    smoothed = np.convolve(padded, smooth_kernel, mode="valid")
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    phi_ridge = bin_centers[int(np.argmax(smoothed))]
    curtain_angle = (phi_ridge - 90) % 180
    if curtain_angle > 90:
        curtain_angle -= 180  # wrap to (-90, 90]
    return float(curtain_angle), angular_energy


def plot_angular_energy(
    angular_energy: np.ndarray,
    estimated_angle_deg: float,
    output_dir: Path,
    frame_index: int = None,
    dpi: int = 150,
) -> Path:
    '''
    Save a diagnostic plot of the angular energy profile from estimate_curtain_angle, with the detected angle marked, as a TIFF
    '''
    matplotlib.use("Agg")
    angle_bins = len(angular_energy)
    bin_edges = np.linspace(0, 180, angle_bins + 1)
    phi_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    curtain_bins = (phi_centers - 90) % 180
    curtain_bins = np.where(curtain_bins > 90, curtain_bins - 180, curtain_bins)
    order = np.argsort(curtain_bins)
    curtain_bins_sorted = curtain_bins[order]
    energy_sorted = angular_energy[order]
    confidence = angular_energy.max() / np.median(angular_energy)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(curtain_bins_sorted, energy_sorted, color="tab:blue", lw=1.2)
    ax.axvline(estimated_angle_deg, color="tab:red", ls="--", lw=1.2, label=f"detected angle = {estimated_angle_deg:.1f} deg")
    ax.set_xlabel("Curtain angle, degrees from horizontal")
    ax.set_ylabel("Summed power spectrum (annulus, windowed)")
    ax.set_title(f"Curtain angle detection (confidence ratio = {confidence:.1f})")
    ax.set_xlim(-90, 90)
    ax.legend(loc="upper right")
    fig.tight_layout()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if frame_index is None else f"_tilt{frame_index:03d}"
    output_path = output_dir / f"curtain_angle_diagnostic{suffix}.tiff"
    fig.savefig(output_path, format="tiff", dpi=dpi)
    plt.close(fig)
    return output_path