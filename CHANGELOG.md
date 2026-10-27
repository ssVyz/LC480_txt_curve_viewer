# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [Unreleased]

## [0.2.6] - 2026-10-27

### Added
- Several cobas 6800/8800 or cobas 5800 runs can be open as plates at the same time.
  - When the selected files contain several runs, a checklist (all checked) chooses the runs to open. Each import replaces the open plates.
  - File > Import cobas 6800/8800 Files accepts several export files; runs are combined across files, and wells already read from an earlier, overlapping export are skipped.
  - A Plate drop-down above the plate map picks the plate shown there. Each plate keeps its own selection, well colors and inactive wells; switching plates keeps all of them.
  - The curve viewer shows the selected wells of all plates together. The sample table lists all plates with an extra Plate column, and the CSV export includes it.
  - Plate map actions (click, drag, row/column labels, Select All/Deselect All/Invert, colors, inactivate) apply to the plate shown.
  - Baseline and color compensation settings apply to all plates. Plates must have the same number of cycles.
  - View > Save/Load Plate save and load the plate shown (file format unchanged); Reset Plate View resets all plates. The heatmap shows the plate shown.
  - Well colors and inactive wells carry over to newly imported plates by plate position (plate 1 to plate 1, ...), as they did for a single plate.
  - The LLM console sees all plates, with wells named like `P2:A1`; `get_experiment_info` lists the plates and the plate shown.

### Changed
- LC480 and LC Pro files still open as a single plate; the drop-down and the Plate column only appear with several plates open.

## [0.2.5] - 2026-10-21

### Added
- File > Import cobas 5800 Results: reads the cobas 5800 result export, a zip with one XML per sample (`cobas5800_parser.py`). One or more unpacked XML files can be selected instead.
  - Each XML also repeats the control(s) the sample was validated against. Controls are loaded once and shown only in the run they were processed in, so a run that relied on an earlier run's controls has none on its plate.
  - If the files contain several runs, a dialog asks which run to load.
  - As with the 6800, the two PCR programs (5 + 45 cycles) are joined into 50 cycles, channels are `Ch1` to `Ch5` (Ch5 is the internal control), and the signal steps between cycles 5 and 6, so start the baseline region at cycle 6 or later.
  - Samples are named by barcode, controls by their label. Run start times are shown in local time.
- 24-well plate layout (A1-D6) for cobas 5800 runs: the plate map and heatmap draw wells that are not on the plate as faint outlines and grey out their row/column labels.
- LLM `get_experiment_info` reports the plate layout.

## [0.2.4] - 2026-10-20

### Added
- File > Import cobas 6800/8800 File: reads cobas 6800/8800 result export XML files (`cobas_parser.py`).
  - The two PCR programs (5 + 45 cycles) are joined into one 50-cycle curve, the cycle numbering the cobas Ct values use. The program change between cycles 5 and 6 causes a small signal step, so set the baseline region to start at cycle 6 or later.
  - Channels are named by filter: `Ch1` to `Ch5` (Ch5 is the internal control).
  - Samples are named by barcode, controls by their label (e.g. `(-) Ctrl`). Well positions like `G01` become `G1`.
  - If the file contains several runs, a dialog asks which run to load.

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
