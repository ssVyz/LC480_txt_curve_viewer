# LC480 Result Viewer

Desktop viewer for qPCR amplification curves from Roche LightCycler 480, LightCycler Pro, cobas 6800/8800 and cobas 5800 result exports. Built with PySide6 and pyqtgraph.

## Features

- Import LC480 text exports, LC Pro XML exports, cobas 6800/8800 XML exports and cobas 5800 exports (zip of per-sample XMLs, 24-well plate)
- Amplification curves with 1st/2nd derivative views, smoothing and log scale
- Plate map with well selection, activation/inactivation and custom colors
- Baseline correction (fixed or adaptive end), Ct and call calculation
- Color compensation for multiplex cross-talk
- Heatmap view and CSV export of results
- Save/load plate setups (`*.plate`: well colors, inactive wells, baseline settings)
- Optional LLM console (Google Gemini) that can read run data and change view settings

## Usage

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
uv run main.py
```

Then use **File > Import** to open a result file. Baseline, colors and color compensation are under **Settings**; heatmap and plate setup files under **View**.

To use the LLM console, enter a Google API key under **LLM > Settings** (stored in a local `.env` file, which is git-ignored) and open **LLM > Open Console**.

## Structure

| Path | Purpose |
| --- | --- |
| `main.py` | Entry point |
| `main_window.py` | Main window, menus, application state |
| `lc480_parser.py` | LC480 text export parser and the shared `LC480Data` model |
| `lcpro_parser.py` | LC Pro XML parser |
| `cobas_parser.py` | cobas 6800/8800 XML parser (one `LC480Data` per run) |
| `cobas5800_parser.py` | cobas 5800 parser for zipped or loose per-sample XMLs (one `LC480Data` per run) |
| `baseline.py` | Baseline correction, Ct/call calculation, baseline dialog |
| `color_compensation.py` | Cross-talk correction and its dialog |
| `color_settings.py` | Well/channel color settings |
| `plate_setup.py` | Save/load `*.plate` files |
| `curve_viewer_widget.py`, `plate_map_widget.py`, `sample_table_widget.py` | Main UI widgets |
| `heatmap_dialog.py` | Heatmap dialog |
| `LLM/` | Gemini console: API service, function declarations and implementations, bridge to the main window |
| `CHANGELOG.md` | Version history |

## Disclaimer

**AI-assisted development.** Large parts of this code were written with AI coding assistants (Anthropic Claude) under human direction and review. Check results before relying on them.

**LLM console.** The optional console sends run data (experiment and sample names, which can be patient barcodes, plus per-well values such as Ct, call and fluorescence) to Google's Gemini API. Do not use it with data that must not leave your institution. LLM answers can be wrong.

**Not for diagnostic use.** This is a research tool and has not been validated for clinical or diagnostic use. Ct values and calls may differ from the instrument software.
