# PyLisC

A Python port of the Lamella in-silico Clearing algorithm

## Contents
- [Overview](#overview)
- [Installation](#installation)
- [Usage](#usage)
   - [`pylisc stack`](#pylisc-stack)
   - [`pylisc frames`](#pylisc-frames)
- [Output](#output)
- [Additional information](#additional-information)
- [PyLisC vs LisC](#pylisc-vs-lisc)
- [Citation](#citation)


## Overview
This is a Python implementation of the Lamella in-silico Clearing (LisC) algorithm originally described in [Bauerlein et al., 2021](https://doi.org/10.1101/2021.04.14.437159) and available as an ImageJ Macro [here](https://github.com/FJBauerlein/LisC_Algorithm), which removes curtaining artefacts from cryo-FIB/ET images. For information about the differences between PyLisC and the original LisC macro, see the [PyLisC vs LisC section below](#pylisc-vs-lisc).

In brief, PyLisC:
1. _(Optional)_ Removes large-scale brightness modulation with a high-pass filter.
2. Removes directional curtaining stripes at a specified angle in Fourier space.

PyLisC has two subcommands, depending on the type of input MRC file:
Command | Expected input type | Output notes | Additional information
-- | -- | -- | --
`pylisc stack` | An MRC tilt-series stack (or directory of these) | Each tilt image in a stack is processed independently and reassembled into a cleared output MRC | See [`pylisc stack` usage](#pylisc-stack) below
`pylisc frames` | A directory of 2D MRC frames (i.e. pre-alignment) | A directory of destriped frames (i.e. of the same structure as input) | See [`pylisc frames` usage](#pylisc-frames) below

## Installation
The easiest way to install PyLisC is using the `uv` package manager:
```sh
# Install PyLisC
uv tool install git+https://github.com/holsam/PyLisC.git

# Confirm installation
pylisc --help
```

## Usage 
### `pylisc stack`
```sh
pylisc stack [OPTIONS] INPUT_MRC [OUTPUT_MRC]
```
`OUTPUT_MRC` is optional. If omitted, it defaults to `INPUT_MRC` with a `_PyLisC_{mode}` suffix, saved to the same directory as `INPUT_MRC`. If that file already exists, a numeric suffix is appended instead of overwriting it.

#### Options

##### Filtering options
Option | Default | Description
--|--|--
`--filter-threshold` | `5000.0` | High-pass cutoff, in nm. Large-scale structure below this frequency is removed before destriping.
`--pixel-size` | *(read from MRC header)* | Override the pixel size, in nm. Use this if the header value is missing or unreliable.

##### De-curtaining options
Option | Default | Description
--|--|--
`-m`, `--mode` | `angular` | Destriping approach: `angular` (recommended) or `linear` (deprecated). See [Destriping mode](#destriping-mode) below.
`--angle` | *(auto-estimated)* | Curtaining orientation, degrees from horizontal. Omit to estimate automatically from the tilt series' central frame[^estimation]; pass a value to override. A diagnostic plot is saved alongside the output when auto-estimated[^diagnosticplot].
`--reference-frame` | `0` | Stack index used for angle estimation and the destriping preview. See [Choosing a reference frame](#choosing-a-reference-frame) for more information.
`--angular-width` | `8.0` | Angular width of the destriping notch, in degrees. Only used when `--mode angular`. Narrower keeps more real structure sharing a nearby angle to the curtains, at the cost of weaker curtain removal.
`--notch-fraction` | `0.03` | Width of the destriping notch, as a fraction of image width. Narrower removes less real signal running parallel to the curtains, but leaves more curtaining behind. Only used when `--mode linear`, which is deprecated.
`--protect-fraction` | `0.01` | Fraction of image width around the zero-frequency (DC) origin exempted from destriping. See [Destriping mode](#destriping-mode) below for why this exists and its trade-off. Only used when `--mode linear`, which is deprecated.

##### Batch options
Option | Default | Description
--|--|--
`--output-dir` | *(required for directory input)* | Output directory for batch mode, mirroring the input directory's structure.
`--angle-outlier-threshold` | `5.0` | Warn if an individual series' own angle estimate differs from the batch consensus by more than this many degrees. In `frames` mode, a tilt beyond this threshold also has its angle replaced with its nearest reliable tilt's angle, see [per-tilt curtain angle](#per-tilt-curtain-angle) for details.
#### Example
```sh
# Run PyLisC, estimating the curtaining angle automatically
pylisc stack tilt_series.mrc

# Manually define the curtaining angle
pylisc stack --angle 50 tilt_series.mrc

# Manually define the pixel size (instead of reading from MRC header)
pylisc stack --pixel-size 4.4 tilt_series.mrc

# Use the linear notch mode instead (note this will log a warning message)
pylisc stack --mode linear tilt_series.mrc
```

#### Previewing destriping strength
Before committing to a full run, different strength values can be previewed against on a single frame:

```sh
pylisc stack --preview-strengths 3,5,8,12,20 tilt_series.mrc
```

This saves `destripe_strength_preview.tiff`, a side-by-side montage labelled with each value, and exits without processing the rest of the stack. Uses `--reference-frame` (see [below](#choosing-a-reference-frame)) as the preview frame.

### Batch mode

`INPUT_MRC` can be a directory instead of a single MRC. When it is, PyLisC processes every tilt series it finds, and `--output-dir` (required in this mode) receives the cleared output, mirroring the input directory's structure.

```sh
pylisc stack raw_tilt_series/ --output-dir cleared_tilt_series/
```

Files already carrying a `_PyLisC_` suffix (i.e. previous PyLisC output) are skipped, so re-running against the same directory won't reprocess its own results.

#### Shared curtain angle
Unless `--angle` is given explicitly, single-file mode estimates the curtaining angle from one frame. In batch mode, PyLisC instead estimates an angle **per series** and combines them into a single shared angle, which is then applied to every series in the batch rather than letting each one drift independently.

The combination is a confidence-weighted circular mean: each series' angle is weighted by its own confidence ratio (see [Curtain angle diagnostic plot](#curtain-angle-diagnostic-plot) below), so a series with a clear, sharp peak counts for more than one with a flat, uncertain profile.

#### Outlier detection

If any individual series' own angle estimate differs from the batch consensus by more than `--angle-outlier-threshold` (default `5.0` degrees), a warning is printed naming that series:

```
WARNING: sample_07.mrc angle (58.3 deg) deviates 41.2 deg from consensus (17.1 deg) -- check its diagnostic plot
```

### `pylisc frames`

```sh
pylisc frames [OPTIONS] --output-dir OUTPUT_DIR --filename-template TEMPLATE INPUT_DIR
```

This command is aimed at destriping tilt images that exist as individual 2D MRC frames, i.e. not yet assembled/aligned into a stack. `INPUT_DIR` is not recursed into; every `*.mrc` directly inside it (excluding PyLisC's own `_PyLisC_` output) is treated as one tilt image. `--output-dir` is required, and mirrors the input's flat structure: each frame is written back out individually with a `_PyLisC_{mode}` suffix, same as `--output-dir` does for [batch mode](#batch-mode).

#### Options
`pylisc frames` uses many of the same options as `pylisc stack`, see [above](#options) or run `pylisc frames -h` for further information.

#### Filename template
Since a flat directory has no per-series subdirectory to group frames by, PyLisC needs to know which filename field is the tilt angle. This is given as a template describing the delimited filename fields, with `{}` for fields to ignore and `{tilt}` (required) for the tilt angle field, e.g. for `Position_012_003_-30.00_20240115_1_Fractions_motion_corrected.mrc`:

```sh
--filename-template '{}_{position}_{}_{tilt}_{}_{}_{}_{}_{}.mrc'
```

`{position}` here is accepted but currently unused beyond parsing; only `{tilt}` drives behaviour. Any other named field is likewise parsed but ignored.

Field boundaries default to underscore only. `--filename-delimiters` sets which characters count as boundaries (each character in the string is treated independently, so it can mix separators) — don't include a decimal point if a field's own value (like the tilt angle) contains one. E.g. for `sample-01_tilt-30.00.mrc`:

```sh
--filename-template '{}-{}_{}-{tilt}.mrc' --filename-delimiters '_-'
```

#### Per-tilt curtain angle
Curtaining orientation drifts slightly with tilt angle, so unless `--angle` is given explicitly, frames mode does **not** use one consensus angle for the whole directory. Instead:
1. Every frame's own angle is estimated.
2. Frames are grouped by tilt angle, rounded to the nearest whole degree (so e.g. two positions' `-30.00°` and `-29.98°` tilts fall in the same group).
3. Each group's estimates are combined into a per-tilt consensus (same confidence-weighted circular mean as [batch mode](#shared-curtain-angle)), which is the angle applied to every frame in that group.
4. All per-tilt consensus angles are then combined into an overall consensus, weighted both by confidence and by `cos(tilt)` (sample thickness grows ~1/cos(tilt) so high tilt angles are less reliable), so they count for less than well-sampled low-tilt groups rather than skewing the overall consensus by an equal vote.
5. Any per-tilt consensus that still deviates from the overall consensus by more than `--angle-outlier-threshold` is treated as unreliable, and will be destriped at the consensus angle of its nearest reliable tilt (by tilt-angle distance) instead, logging a warning naming both tilts. If every tilt ends up flagged, PyLisC falls back to the overall consensus for all of them.

#### Pixel size
Individual frame MRCs frequently lack a reliable pixel size in their header, so frames mode does not fall back to it. Pixel size is only needed for the optional high-pass filter — if `--apply-filter` is set, `--pixel-size` must be given explicitly, or PyLisC exits with an error.

## Output
In `stack` mode: a cleared MRC stack, one processed frame per input tilt, at the same dimensions and pixel size as the input. In `frames` mode: one cleared 2D MRC per input frame, same naming/dimensions/pixel-size convention, written flat into `--output-dir`.

### Curtain angle diagnostic plot

If `--angle` is omitted, `curtain_angle_diagnostic.tiff` is saved alongside the output MRC. It plots summed Fourier power spectrum against curtain angle (−90° to 90°), with the detected angle marked as a dashed red line[^diagnosticplot].

#### How to read it

- A single sharp, narrow peak at the marked angle means the estimate is reliable — the frame has one dominant, consistent curtaining direction.
- A flat or noisy profile with no clear peak means the frame doesn't have strong directional curtaining, and the detected angle shouldn't be trusted. In this case, set `--angle` manually instead.
- Multiple peaks of similar height mean competing directional structure in the frame (e.g. genuine linear features at a different angle to the curtains), and the detected peak may not be the curtaining.

#### Rough confidence check
A rough numerical confidence check is the ratio of the peak to the median of the plotted profile. Pure noise (no curtaining) should give a relatively low ratio of around 1, whereas frames with clear curtaining will give higher ratios. `-v`/`--verbose` prints this ratio alongside the estimated angle.

### Per-file debug logs
Alongside the usual run-wide log, both `stack` and `frames` modes write a `DEBUG`-level log per output file (`<output_stem>.log`, next to that file) containing only the messages relevant to it — e.g. its resolved pixel size, its estimated angle, and confirmation it was written.

## Additional information
### Destriping mode
Curtaining removal works by finding curtaining's signature in Fourier space and dimming it. PyLisC offers two ways to do this, selected with the `--mode`/`-m` flag:

- **`angular` (recommended).** Dims frequencies by their *direction*, regardless of how close they are to the zero-frequency origin. This keeps large-scale contrast and fine detail intact at every radius, so curtain removal strength does not affect signal preservation. Only structures genuinely running at the same angle as the curtains are affected, since they share the Fourier signature.
- **`linear` (deprecated).** Dims frequencies by their *distance* from the curtain line rather than their direction. Below a radius set by `--notch-fraction`, distance alone can no longer distinguish direction at all, so without `--protect-fraction` exempting a small disc around the origin, large-scale contrast gets suppressed at every angle near that radius, not just along the curtains. Protecting that disc, in turn, risks letting broad, low-frequency curtaining pass through unfiltered if the curtaining's own frequency sits close to the protected radius. `angular` avoids this trade-off entirely.

### Choosing a reference frame
The reference frame should be the tilt with the least foreshortening and the best signal-to-noise, since that gives the most reliable curtain angle estimate and the clearest destriping preview. In practice this is the 0° tilt (or the pretilt used during lamella imaging).

- **Dose-symmetric schemes** (0° acquired first, then alternating ±): use `--reference-frame 0`.
- **Continuous sweeps** (most-negative tilt acquired first): 0° sits in the middle of the stack, so use roughly `--reference-frame <n//2>` for an n-tilt series.

By default, the reference frame is taken as the middle of the stack, under the assumption that this will be correct for continous sweeps and workable for dose-symmetric schemes (vs using the first frame which would be correct for dose-symmetric but an extreme tilt angle for continous).

### Limitations
- **Directional filering:** Any real structure running parallel to the curtains shares the same Fourier orientation and is attenuated along with them, in both destriping modes. A narrower `--angular-width` (or `--notch-fraction` in linear mode) limits this but cannot eliminate it where curtains and genuine structure share an angle. Some loss of signal is likely to be observed for these structures.

- **Linear mode radius/direction trade-off:** `--mode linear` couples curtain removal strength to large-scale contrast preservation, since a fixed-width distance notch loses directional selectivity below its own width in radius (see [Destriping mode](#destriping-mode)). `--mode angular` does not have this limitation.

## PyLisC vs LisC
PyLisC follows the same processing logic as the original macro but is not a pixel-identical reimplementation. See the below table for the key differences:

Aspect | LisC (ImageJ macro) | PyLisC
-- | -- | --
Bit depth | Converts to 8-bit before processing | Float32 throughout (not directly comparable to Fiji output at the pixel-level)
Bandpass/high-pass filter | ImageJ's FFT Bandpass Filter (Gaussian-weighted large/small cutoffs) | Difference-of-Gaussians high-pass, computed via FFT
Masking | Manual Brightness/Contrast check, applied by hand per lamella | No masking performed
Curtain orientation | Must be horizontal; user manually rotates the lamella image if not | Any angle, supplied manually or auto-estimated from the FFT power spectrum[^estimation]; no image rotation needed, the Fourier notch itself is rotated
Curtain angle detection | Not automated | Automated, with a saved diagnostic plot and confidence ratio[^diagnosticplot]
Directional filtering | FFT Bandpass Filter with `suppress=Horizontal` | Gaussian notch in Fourier space, gated by angle (`--mode angular`) or by distance (`--mode linear`)
Processing scope | One image at a time (the lamella overview) | Whole tilt series in one call, each frame processed independently
Output | Cleared image in Fiji | Cleared MRC stack, same dimensions/pixel size as input


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