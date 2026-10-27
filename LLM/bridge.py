"""Bridge between LLM functions and the MainWindow application state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtGui import QColor

if TYPE_CHECKING:
    from lc480_parser import LC480Data
    from main_window import MainWindow


def _plate_layout(d: LC480Data) -> str:
    last_well = f"{chr(ord('A') + d.plate_rows - 1)}{d.plate_cols}"
    return f"{d.plate_rows * d.plate_cols} wells, A1-{last_well}"


class MainWindowBridge:
    """Provides LLM functions safe access to application state."""

    def __init__(self, main_window: MainWindow):
        self._mw = main_window

    @property
    def has_data(self) -> bool:
        return self._mw._data is not None

    # -- Data reading --------------------------------------------------------

    def get_experiment_info(self) -> dict:
        d = self._mw._data
        plates = self._mw._plates
        info = {
            "experiment_name": d.experiment_name,
            "plate_layout": _plate_layout(d),
            "num_wells": len(d.wells),
            "wells": d.wells,
            "channels": d.channels,
            "num_cycles": d.num_cycles,
            "sample_names": {w: n for w, n in d.sample_names.items() if n},
            "inactive_wells": sorted(self._mw._inactive_wells & set(d.wells)),
        }
        if len(plates) > 1:
            info["plate_layout"] = (
                f"{len(plates)} plates; wells are named P<plate>:<well>, e.g. P2:A1"
            )
            info["plates"] = [
                {
                    "plate": f"P{i}",
                    "experiment_name": p.experiment_name,
                    "plate_layout": _plate_layout(p),
                    "num_wells": len(p.wells),
                }
                for i, p in enumerate(plates, 1)
            ]
            info["displayed_plate"] = f"P{self._mw._current_plate + 1}"
        return info

    def get_well_data(self, wells: list[str], channels: list[str] | None) -> dict:
        d = self._mw._data
        br = self._mw._baseline_results

        if channels is None:
            channels = [d.channels[0]] if d.channels else []

        valid_channels = [c for c in channels if c in d.channels]
        valid_wells = [w for w in wells if w in d.wells]

        result = {}
        for well in valid_wells:
            well_info: dict = {
                "sample_name": d.sample_names.get(well, ""),
                "is_inactive": well in self._mw._inactive_wells,
                "channels": {},
            }
            for ch in valid_channels:
                raw = d.fluorescence.get(well, {}).get(ch)
                if raw is None:
                    continue
                ch_info: dict = {
                    "raw_start": round(float(raw[0]), 1),
                    "raw_end": round(float(raw[-1]), 1),
                }
                # First derivative max
                cycles = d.cycles
                dx = np.diff(cycles)
                first_deriv = np.diff(raw) / dx
                ch_info["max_first_derivative"] = round(float(np.max(first_deriv)), 2)

                # Second derivative max
                midpoints = (cycles[:-1] + cycles[1:]) / 2.0
                second_deriv = np.diff(first_deriv) / np.diff(midpoints)
                ch_info["max_second_derivative"] = round(float(np.max(second_deriv)), 2)

                # Baseline results if available
                if br:
                    ch_info["ct"] = br.ct.get(well, {}).get(ch)
                    if ch_info["ct"] is not None:
                        ch_info["ct"] = round(ch_info["ct"], 2)
                    ch_info["call"] = br.call.get(well, {}).get(ch, "N/A")
                    rfi = br.endpoint_rfi.get(well, {}).get(ch)
                    if rfi is not None:
                        ch_info["endpoint_rfi"] = round(float(rfi), 3)

                well_info["channels"][ch] = ch_info
            result[well] = well_info
        return {"wells": result}

    # -- Well activation -----------------------------------------------------

    def set_wells_inactive(self, wells: list[str]) -> dict:
        well_set = set(wells) & set(self._mw._data.wells)
        self._mw._inactive_wells |= well_set
        self._mw._push_inactive()
        return {"inactivated": sorted(well_set)}

    def set_wells_active(self, wells: list[str]) -> dict:
        well_set = set(wells) & self._mw._inactive_wells
        self._mw._inactive_wells -= well_set
        self._mw._push_inactive()
        return {"reactivated": sorted(well_set)}

    # -- Colors --------------------------------------------------------------

    def set_well_colors(self, wells: list[str], color: str) -> dict:
        qcolor = QColor(color)
        if not qcolor.isValid():
            return {"error": f"Invalid color: {color}"}
        for w in wells:
            if w in self._mw._data.wells:
                self._mw._color_settings.sample_colors[w] = QColor(qcolor)
        self._mw._push_colors()
        return {"colored": sorted(wells), "color": color}

    def clear_well_colors(self, wells: list[str]) -> dict:
        cleared = []
        for w in wells:
            if w in self._mw._color_settings.sample_colors:
                del self._mw._color_settings.sample_colors[w]
                cleared.append(w)
        if cleared:
            self._mw._push_colors()
        return {"cleared": sorted(cleared)}

    def set_color_mode(self, mode: str) -> dict:
        self._mw._color_settings.color_mode = mode
        self._mw.curve_viewer.color_mode_combo.setCurrentText(mode)
        self._mw._push_colors()
        return {"color_mode": mode}

    # -- Display settings ----------------------------------------------------

    def set_display_mode(self, mode: str) -> dict:
        self._mw.curve_viewer.display_combo.setCurrentText(mode)
        return {"display_mode": mode}

    def set_checked_channels(self, channels: list[str]) -> dict:
        self._mw.curve_viewer.channel_selector.set_checked(channels)
        return {"checked_channels": channels}

    def select_wells(self, wells: list[str]) -> dict:
        well_set = set(wells) & set(self._mw._data.wells)
        self._mw._set_selection(well_set)
        self._mw._update_status()
        return {"selected": sorted(well_set)}

    def set_line_width(self, width: float) -> dict:
        width = max(0.5, min(5.0, width))
        self._mw.curve_viewer.line_width_spin.setValue(width)
        return {"line_width": width}

    def set_smooth(self, enabled: bool) -> dict:
        self._mw.curve_viewer.smooth_check.setChecked(enabled)
        return {"smooth": enabled}

    def set_log_y(self, enabled: bool) -> dict:
        self._mw.curve_viewer.log_y_check.setChecked(enabled)
        return {"log_y": enabled}

    # -- Baseline settings ---------------------------------------------------

    def set_baseline_settings(self, **kwargs) -> dict:
        bs = self._mw._baseline_settings
        changed = {}
        for key in ("start_cycle", "end_cycle", "ct_threshold", "call_threshold",
                    "adaptive_end", "deriv_threshold", "min_cycles"):
            if key in kwargs and kwargs[key] is not None:
                setattr(bs, key, kwargs[key])
                changed[key] = kwargs[key]
        if changed:
            self._mw._recompute_baseline()
        return {"baseline_settings": changed}
