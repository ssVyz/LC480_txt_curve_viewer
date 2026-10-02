# LC480 Result Viewer

PySide6 + pyqtgraph desktop viewer for Roche LightCycler 480 / LC Pro qPCR curves. Python >=3.12, managed with uv.

- Run: `uv run main.py`
- Parsers: `lc480_parser.py`, `lcpro_parser.py`; UI: `main_window.py` + `*_widget.py` / `*_dialog.py`; LLM console (Gemini): `LLM/`

## Rules
- **No git commits.** Never commit, push, or tag; humans do that.
- **Versioning:** version lives in `pyproject.toml` (keep `uv.lock` project entry in sync).
  - Any code change → bump the **patch** version (once per change set, not per edit).
  - **Minor/major** bumps only when a human explicitly asks.
  - Docs-only changes (README, CLAUDE.md, etc.) don't bump the version.
- **Changelog:** every code change gets an entry in `CHANGELOG.md` under the new version (Keep a Changelog sections: Added/Changed/Fixed/Removed).
