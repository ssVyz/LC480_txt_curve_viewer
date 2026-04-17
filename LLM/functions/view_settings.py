"""View and settings manipulation function implementations."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from LLM.bridge import MainWindowBridge


def _require_data(bridge: MainWindowBridge) -> dict | None:
    if not bridge.has_data:
        return {"error": "No data loaded. Please load a file first."}
    return None


def set_wells_inactive(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    return bridge.set_wells_inactive(kwargs.get("wells", []))


def set_wells_active(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    return bridge.set_wells_active(kwargs.get("wells", []))


def set_well_colors(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    wells = kwargs.get("wells", [])
    color = kwargs.get("color", "")
    if not wells or not color:
        return {"error": "Both 'wells' and 'color' are required."}
    return bridge.set_well_colors(wells, color)


def clear_well_colors(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    return bridge.clear_well_colors(kwargs.get("wells", []))


def set_color_mode(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    mode = kwargs.get("mode", "")
    if mode not in ("Base Color", "Channel Colors"):
        return {"error": f"Invalid mode: {mode}. Use 'Base Color' or 'Channel Colors'."}
    return bridge.set_color_mode(mode)


def set_display_mode(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    valid = {"Raw Data", "Baseline Subtracted", "Baseline Divided",
             "First Derivative", "Second Derivative"}
    mode = kwargs.get("mode", "")
    if mode not in valid:
        return {"error": f"Invalid mode: {mode}. Valid: {sorted(valid)}"}
    return bridge.set_display_mode(mode)


def set_checked_channels(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    return bridge.set_checked_channels(kwargs.get("channels", []))


def select_wells(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    return bridge.select_wells(kwargs.get("wells", []))


def set_line_width(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    width = kwargs.get("width", 1.0)
    return bridge.set_line_width(float(width))


def set_smooth(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    return bridge.set_smooth(bool(kwargs.get("enabled", False)))


def set_log_y(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    return bridge.set_log_y(bool(kwargs.get("enabled", False)))


def set_baseline_settings(bridge: MainWindowBridge, **kwargs) -> dict:
    if err := _require_data(bridge):
        return err
    params = {}
    for key in ("start_cycle", "end_cycle", "ct_threshold", "call_threshold"):
        if key in kwargs:
            params[key] = kwargs[key]
    if not params:
        return {"error": "No parameters specified."}
    return bridge.set_baseline_settings(**params)
