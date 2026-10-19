# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [0.2.3] - 2026-10-19

### Added
- Adaptive baseline end (Settings > Baseline, off by default) for runs where some curves rise very early, inside a baseline region that suits the rest.
  - Per curve: if the raw 1st derivative between cycles c and c+1 exceeds a threshold (RFU/cycle, one value for all channels) inside the baseline region, that curve's baseline ends at cycle c. Curves that stay below the threshold use the regular region.
  - A configurable minimum number of baseline cycles (default 3) keeps the region from getting too short.
  - Saved in `*.plate` files as the optional keys `adaptive_end`, `deriv_threshold`, `min_cycles`. Files without them load with the feature off. The format version stays 1.
  - The LLM `set_baseline_settings` function accepts the new settings.
- CSV export has a `Baseline End` column with the last baseline cycle each well actually used, for the same channel as the Ct/Call columns.

## [0.2.2] - 2026-10-17

### Added
- View > Reset Plate View: after confirmation, clears custom well colors, reactivates all wells and restores default baseline settings.
- `*.plate` files now include baseline settings (start/end cycle, Ct and Call threshold) as an optional `baseline` key; the format version stays 1, so older viewer versions can still open them and ignore the baseline.
  - Loading a file without baseline settings applies the defaults (3 / 8 / 1.5 / 1.5).
  - A baseline region that does not fit the current run's cycle count is clamped; the status bar reports it.

### Changed
- Inactive wells are kept when importing another result file, like custom well colors and baseline settings.
- LLM `get_experiment_info` lists only inactive wells present in the current run.

## [0.2.1] - 2026-10-02

### Added
- View > Save Plate / Load Plate: persist plate setup (custom well colors incl. transparency, inactive wells) as JSON `*.plate` files (`plate_setup.py`).
  - Loading replaces the current plate configuration; requires imported data.
  - Wells in the file without data in the current run are still applied; the status bar reports their count.

## [0.2.0] - 2026-10-02

### Added
- Project housekeeping: `CHANGELOG.md`, `CLAUDE.md`, versioning rules.

### Changed
- `.gitignore`: stop ignoring `CHANGELOG.md` and `CLAUDE.md`.

### Baseline
First tracked version. Features present at this point:
- LC480 text export and LC Pro file parsing
- Amplification curve viewer with derivative views and smoothing
- Plate map with well activate/inactivate, sample table
- Heatmap dialog, CSV export
- Baseline settings, color settings, color compensation
- Gemini-based LLM console (API key via `.env`)
- Forced light color scheme
