# LC480 Result Viewer

PySide6 + pyqtgraph desktop viewer for Roche LightCycler 480 / LC Pro qPCR curves. Python >=3.12, managed with uv.

- Run: `uv run main.py`
- Parsers: `lc480_parser.py`, `lcpro_parser.py`, `cobas_parser.py` (cobas 6800/8800 XML; one `LC480Data` per run), `cobas5800_parser.py` (cobas 5800 zip of per-sample XMLs; 24-well plate via `LC480Data.plate_rows`/`plate_cols`); UI: `main_window.py` + `*_widget.py` / `*_dialog.py`; LLM console (Gemini): `LLM/`
- Plate state (well colors in `ColorSettings.sample_colors`, `MainWindow._inactive_wells`) is saved/loaded via `plate_setup.py` (`*.plate`)
- Multiple plates (cobas runs only): `MainWindow._plates` holds the open plates, `_data` is their combination from `plate_set.combine_plates`. With one plate open, wells are keyed by position (`A1`) everywhere, as before; with several, all state uses keys `P<n>:<well>` except the plate map, which shows `_plates[_current_plate]` with plain names (translate via `MainWindow._plate_keys` / `_on_plate`). LC480/LC Pro behavior must stay unchanged.

## Rules
- **No git commits.** Never commit, push, or tag; humans do that.
- **Versioning:** version lives in `pyproject.toml` (keep `uv.lock` project entry in sync).
  - Any code change → bump the **patch** version (once per change set, not per edit).
  - **Minor/major** bumps only when a human explicitly asks.
  - Docs-only changes (README, CLAUDE.md, etc.) don't bump the version.
- **Changelog:** every code change gets an entry in `CHANGELOG.md` under the new version (Keep a Changelog sections: Added/Changed/Fixed/Removed).
