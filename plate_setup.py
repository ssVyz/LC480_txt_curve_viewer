"""Plate setup persistence: custom well colors and inactive wells as JSON *.plate files."""

import json
import re
from dataclasses import dataclass, field

from PySide6.QtGui import QColor

from lc480_parser import well_sort_key


FORMAT_ID = "lc480-plate"
FORMAT_VERSION = 1
FILE_FILTER = "Plate Setup (*.plate)"

_WELL_RE = re.compile(r"^[A-H](1[0-2]|[1-9])$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")


@dataclass
class PlateSetup:
    """Per-well plate configuration."""
    well_colors: dict[str, QColor] = field(default_factory=dict)
    inactive_wells: set[str] = field(default_factory=set)


# -- Color encoding (#RRGGBBAA, CSS order — not Qt's #AARRGGBB) --------------

def _color_to_hex(c: QColor) -> str:
    return f"#{c.red():02x}{c.green():02x}{c.blue():02x}{c.alpha():02x}"


def _hex_to_color(value) -> QColor:
    if not isinstance(value, str) or not _COLOR_RE.match(value):
        raise ValueError(f"Invalid color: {value!r}")
    r, g, b = (int(value[i:i + 2], 16) for i in (1, 3, 5))
    a = int(value[7:9], 16) if len(value) == 9 else 255
    return QColor(r, g, b, a)


def _check_well(well) -> str:
    if not isinstance(well, str) or not _WELL_RE.match(well):
        raise ValueError(f"Invalid well position: {well!r}")
    return well


# -- Save / load -------------------------------------------------------------

def save_plate_setup(filepath: str, setup: PlateSetup,
                     experiment_name: str = "") -> None:
    payload = {
        "format": FORMAT_ID,
        "format_version": FORMAT_VERSION,
        "experiment_name": experiment_name,
        "inactive_wells": sorted(setup.inactive_wells, key=well_sort_key),
        "well_colors": {
            w: _color_to_hex(setup.well_colors[w])
            for w in sorted(setup.well_colors, key=well_sort_key)
        },
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def load_plate_setup(filepath: str) -> PlateSetup:
    """Read a *.plate file. Raises ValueError on malformed content."""
    with open(filepath, encoding="utf-8") as f:
        try:
            payload = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("Not a plate setup file (invalid JSON).") from exc

    if not isinstance(payload, dict) or payload.get("format") != FORMAT_ID:
        raise ValueError("Not a plate setup file.")
    version = payload.get("format_version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise ValueError(f"Unsupported plate setup version: {version!r}")

    inactive = payload.get("inactive_wells", [])
    colors = payload.get("well_colors", {})
    if not isinstance(inactive, list) or not isinstance(colors, dict):
        raise ValueError("Malformed plate setup file.")

    setup = PlateSetup()
    for well in inactive:
        setup.inactive_wells.add(_check_well(well))
    for well, value in colors.items():
        setup.well_colors[_check_well(well)] = _hex_to_color(value)
    return setup
