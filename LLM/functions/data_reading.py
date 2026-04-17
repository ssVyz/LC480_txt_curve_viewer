"""Data reading function implementations."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from LLM.bridge import MainWindowBridge


def get_experiment_info(bridge: MainWindowBridge, **kwargs) -> dict:
    if not bridge.has_data:
        return {"error": "No data loaded. Please load a file first."}
    return bridge.get_experiment_info()


def get_well_data(bridge: MainWindowBridge, **kwargs) -> dict:
    if not bridge.has_data:
        return {"error": "No data loaded. Please load a file first."}
    wells = kwargs.get("wells", [])
    channels = kwargs.get("channels")
    if not wells:
        return {"error": "No wells specified."}
    return bridge.get_well_data(wells, channels)
