# PyLisC

A Python port of the Lamella in-silico Clearing algorithm

## Overview
This is a Python implementation of the Lamella in-silico Clearing (LisC) algorithm originally described in [Bauerlein et al., 2021](https://doi.org/10.1101/2021.04.14.437159) and available as an ImageJ Macro [here](https://github.com/FJBauerlein/LisC_Algorithm), which removes curtaining artefacts and contamination/vacuum contrast from cryo-FIB/ET tilt series. For information about the differences between PyLisC and the original LisC macro, see the [PyLisC vs LisC section below](#pylisc-vs-lisc).

Given a low-magnification tilt series MRC, PyLisC:
1. Removes large-scale brightness modulation with a high-pass filter.
2. Optionally detects contamination and vacuum regions, and fills them with a local grey-scale average.
3. Removes directional curtaining stripes at a specified angle in Fourier space.

Each tilt image in a stack is processed independently and reassembled into a cleared output MRC.

## Installation
The easiest way to install PyLisC is using the `uv` package manager:
```sh
# Install PyLisC
uv tool install git+https://github.com/holsam/PyLisC.git

# Confirm installation
pylisc --help
```

## Usage
```sh
pylisc --mode {angular,linear} [OPTIONS] INPUT_MRC [OUTPUT_MRC]
```
`--mode`/`-m` must be specified. Available modes are: `angular` or `linear` (see [Destriping mode](#destriping-mode) below).

`OUTPUT_MRC` is optional. If omitted, it defaults to `INPUT_MRC` with a `_PyLisC_{mode}` suffix, saved to the same directory as `INPUT_MRC`. If that file already exists, a numeric suffix is appended instead of overwriting it.

### Example
```sh
# Run PyLisC with the recommended angular mode, estimating the curtaining angle automatically
pylisc --mode angular tilt_series.mrc

# Manually define the curtaining angle
pylisc --mode angular --angle 50 tilt_series.mrc

# Manually define the pixel size (instead of reading from MRC header)
pylisc --mode angular --pixel-size 4.4 tilt_series.mrc

# Clear vacuum and contamination via masking, and save masks
pylisc --mode angular --clear-vacuum --clear-contamination --masks masks_dir/ tilt_series.mrc

# Use the linear notch mode instead
pylisc --mode linear tilt_series.mrc
```

### Destriping mode

Curtaining removal works by finding curtaining's signature in Fourier space and dimming it. PyLisC offers two ways to do this, selected with the required `--mode`/`-m` flag:

- **`angular` (recommended).** Dims frequencies by their *direction*, regardless of how close they are to the zero-frequency origin. This keeps large-scale contrast and fine detail intact at every radius, so curtain removal strength does not affect signal preservation. Only structures genuinely running at the same angle as the curtains are affected, since they share the Fourier signature.
- **`linear`.** Dims frequencies by their *distance* from the curtain line rather than their direction. Below a radius set by `--notch-fraction`, distance alone can no longer distinguish direction at all, so without `--protect-fraction` exempting a small disc around the origin, large-scale contrast gets suppressed at every angle near that radius, not just along the curtains. Protecting that disc, in turn, risks letting broad, low-frequency curtaining pass through unfiltered if the curtaining's own frequency sits close to the protected radius. `angular` avoids this trade-off entirely.

### Options

#### General
Option | Default | Description
--|--|--
`--pixel-size` | *(read from MRC header)* | Override the pixel size, in nm. Use this if the header value is missing or unreliable.
`-v`, `--verbose` | `False` | Print per-tilt progress and parameter summary.

#### De-curtaining options
Option | Default | Description
--|--|--
`-m`, `--mode` | *(required)* | Destriping approach: `angular` (recommended) or `linear` (legacy). See [Destriping mode](#destriping-mode) above.
`--angle` | *(auto-estimated)* | Curtaining orientation, degrees from horizontal. Omit to estimate automatically from the tilt series' central frame[^estimation]; pass a value to override. A diagnostic plot is saved alongside the output when auto-estimated[^diagnosticplot].
`--filter-threshold` | `5000.0` | High-pass cutoff, in nm. Large-scale structure below this frequency is removed before masking and destriping.
`--angular-width` | `8.0` | Angular width of the destriping notch, in degrees. Only used when `--mode angular`. Narrower keeps more real structure sharing a nearby angle to the curtains, at the cost of weaker curtain removal.
`--notch-fraction` | `0.03` | Width of the destriping notch, as a fraction of image width. Only used when `--mode linear`. Narrower removes less real signal running parallel to the curtains, but leaves more curtaining behind.
`--protect-fraction` | `0.01` | Fraction of image width around the zero-frequency (DC) origin exempted from destriping. Only used when `--mode linear`. See [Destriping mode](#destriping-mode) above for why this exists and its trade-off.

#### Mask options
Option | Default | Description
--|--|--
`--clear-contamination` | `False` | Detect dark contamination and replace it with a neutral local mean. Off by default (decurtaining only).
`--clear-vacuum` | `False` | Detect bright vacuum regions and replace it with a neutral local mean. Off by default (decurtaining only).
`--con-multiplier` | `1.5` | Contamination threshold, as a multiple of the blurred image's standard deviation.
`--vac-multiplier` | `1.5` | Vacuum threshold, as a multiple of the blurred image's standard deviation.
`--fill-sigma` | *(=`--filter-threshold`)* | Length scale (nm) for the neutral fill of cleared regions (lower for more local blending). Only used if masking is enabled.
`--iters` | `4` | Number of binary dilation iterations applied to each mask.
`--masks` | *(none)* | Directory to save each frame's vacuum/contamination masks as TIFF, for quality control.

## Output
A cleared MRC stack, one processed frame per input tilt, at the same dimensions and pixel size as the input. If `--masks` is given, per-tilt `tilt_NNN_vacuum.tiff` and `tilt_NNN_contamination.tiff` masks are written alongside it.

### Curtain angle diagnostic plot

If `--angle` is omitted, `curtain_angle_diagnostic.tiff` is saved alongside the output MRC. It plots summed Fourier power spectrum against curtain angle (−90° to 90°), with the detected angle marked as a dashed red line[^diagnosticplot].

#### How to read it

- A single sharp, narrow peak at the marked angle means the estimate is reliable — the frame has one dominant, consistent curtaining direction.
- A flat or noisy profile with no clear peak means the frame doesn't have strong directional curtaining, and the detected angle shouldn't be trusted. In this case, set `--angle` manually instead.
- Multiple peaks of similar height mean competing directional structure in the frame (e.g. genuine linear features at a different angle to the curtains), and the detected peak may not be the curtaining.

#### Rough confidence check
A rough numerical confidence check is the ratio of the peak to the median of the plotted profile. Pure noise (no curtaining) should give a relatively low ratio of around 1, whereas frames with clear curtaining will give higher ratios. `-v`/`--verbose` prints this ratio alongside the estimated angle.

## Limitations
### Directional filtering
Any real structure running parallel to the curtains shares the same Fourier orientation and is attenuated along with them, in both destriping modes. A narrower `--angular-width` (or `--notch-fraction` in linear mode) limits this but cannot eliminate it where curtains and genuine structure share an angle. Some loss of signal is likely to be observed for these structures.

### Linear mode's radius/direction trade-off
`--mode linear` couples curtain removal strength to large-scale contrast preservation, since a fixed-width distance notch loses directional selectivity below its own width in radius (see [Destriping mode](#destriping-mode)). `--mode angular` does not have this limitation.

## PyLisC vs LisC
PyLisC follows the same processing logic as the original macro but is not a pixel-identical reimplementation. See the below table for the key differences:

Aspect | LisC (ImageJ macro) | PyLisC
-- | -- | --
Bit depth | Converts to 8-bit before processing | Float32 throughout (not directly comparable to Fiji output at the pixel-level)
Bandpass/high-pass filter | ImageJ's FFT Bandpass Filter (Gaussian-weighted large/small cutoffs) | Difference-of-Gaussians high-pass, computed via FFT
Mask threshold | Manual Brightness/Contrast check, applied by hand per lamella | Automated: `mean ± (multiplier × SD)` of the blurred image, same rule the macro's "Apply" step performs
Curtain orientation | Must be horizontal; user manually rotates the lamella image if not | Any angle, supplied manually or auto-estimated from the FFT power spectrum[^estimation]; no image rotation needed, the Fourier notch itself is rotated
Curtain angle detection | Not automated | Automated, with a saved diagnostic plot and confidence ratio[^diagnosticplot]
Directional filtering | FFT Bandpass Filter with `suppress=Horizontal` | Gaussian notch in Fourier space, gated by angle (`--mode angular`) or by distance (`--mode linear`)
Processing scope | One image at a time (the lamella overview) | Whole tilt series in one call, each frame processed independently
Output | Cleared image in Fiji | Cleared MRC stack, same dimensions/pixel size as input
Mask inspection | Visual only, within Fiji | Optional per-tilt vacuum/contamination masks saved as TIFF (`--masks`)


## Citation
If you use PyLisC, please cite the original LisC algorithm:
```md
Bäuerlein FJB, Renner M, El Chami D, Lehnart SE, Pastor-Pareja JC, Fernández-Busnadiego R. Cryo-electron tomography of large biological specimens vitrified by plunge freezing. bioRxiv 2021. doi:10.1101/2021.04.14.437159
```

<br>

[^estimation]: Curtaining that is constant along a direction *u*, where *u* = *cosθ*, *sinθ*, has concentrated Fourier energy in the line through the origin which is perpendicular to *u*. Therefore the curtaining angle can be determined by binning the power spectrum (PyLisC uses width 1°), identifying the bin with the most energy, and rotating this 90° to recover the real-space angle.

      DC-adjacent low frequencies (general brightness/thickness gradient) and the highest frequencies (noise) are excluded via `r_min_frac`/`r_max_frac` (fractions of the Nyquist radius).

      The frame is downsampled to at most `max_size` on its longest side first. As curtaining is a large-scale artefact and orientation doesn't require full resolution for detection, this keeps the estimate cheap even on a 4K tilt frame.

[^diagnosticplot]: Angular energy is binned over the raw Fourier angle, *φ*. *φ* is converted to the corresponding real-space angle in the diagnostic plot's x-axis, to allow values to be used directly as inputs to `--angle`.