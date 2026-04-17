"""LLM callable function registry."""

from .data_reading import get_experiment_info, get_well_data
from .view_settings import (
    set_wells_inactive, set_wells_active,
    set_well_colors, clear_well_colors,
    set_color_mode, set_display_mode,
    set_checked_channels, select_wells,
    set_line_width, set_smooth, set_log_y,
    set_baseline_settings,
)

FUNCTION_MAP: dict = {
    "get_experiment_info": get_experiment_info,
    "get_well_data": get_well_data,
    "set_wells_inactive": set_wells_inactive,
    "set_wells_active": set_wells_active,
    "set_well_colors": set_well_colors,
    "clear_well_colors": clear_well_colors,
    "set_color_mode": set_color_mode,
    "set_display_mode": set_display_mode,
    "set_checked_channels": set_checked_channels,
    "select_wells": select_wells,
    "set_line_width": set_line_width,
    "set_smooth": set_smooth,
    "set_log_y": set_log_y,
    "set_baseline_settings": set_baseline_settings,
}
