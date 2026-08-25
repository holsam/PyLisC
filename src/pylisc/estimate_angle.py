'''
PyLisC: curtain angle estimation from FFT power spectrum and diagnostic plotting
'''

# Import external libraries
import matplotlib, matplotlib.pyplot as plt, numpy as np
from pathlib import Path
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
    median_energy = np.median(angular_energy)
    confidence = angular_energy.max() / median_energy if median_energy > 0 else 0.0
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

def clip_confidence_outliers(confidences: dict) -> dict:
    '''
    Cap confidences above a median+MAD threshold so a single spuriously sharp FFT peak can't dominate a consensus
    '''
    conf_values = np.array(list(confidences.values()))
    if len(conf_values) == 0:
        return dict(confidences)
    median_conf = np.median(conf_values)
    mad = np.median(np.abs(conf_values - median_conf))
    confidence_cap = median_conf + 3 * 1.4826 * mad if mad > 0 else median_conf * 5
    if confidence_cap <= 0:
        return dict(confidences)
    return {k: min(v, confidence_cap) for k, v in confidences.items()}

def resolve_walk(keys_sorted: list, values: dict, angle_outlier_threshold: float, anchor_window: int) -> tuple[dict, dict]:
    '''
    Seed a window of keys around the median key, and walk outward, checking each key's own value against the nearest already-resolved (seed/accepted) value
    '''
    if len(keys_sorted) == 1:
        k = keys_sorted[0]
        return {k: values[k]}, {k: 'seed'}
    median_key = np.median(keys_sorted)
    center_idx = int(np.argmin([abs(k - median_key) for k in keys_sorted]))
    window = max(1, anchor_window)
    half = window // 2
    start = max(0, center_idx - half)
    end = min(len(keys_sorted), start + window)
    start = max(0, end - window)
    seed_keys = keys_sorted[start:end]
    resolved = {k: values[k] for k in seed_keys}
    status = {k: 'seed' for k in seed_keys}
    for direction, idx, edge in ((-1, start - 1, start), (1, end, end - 1)):
        nearest = resolved[keys_sorted[edge]]
        i = idx
        while 0 <= i < len(keys_sorted):
            k = keys_sorted[i]
            own_value = values[k]
            deviation = min(abs(own_value - nearest), 180 - abs(own_value - nearest))
            if deviation <= angle_outlier_threshold:
                resolved[k] = own_value
                status[k] = 'accepted'
                nearest = own_value
            else:
                resolved[k] = nearest
                status[k] = 'rejected'
            i += direction
    return resolved, status

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
    conf_sum = conf.sum()
    agreement = np.sqrt(x ** 2 + y ** 2) / conf_sum if conf_sum > 0 else 0.0
    return float(consensus), float(agreement)