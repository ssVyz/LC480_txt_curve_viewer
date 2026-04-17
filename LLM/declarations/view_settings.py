"""Function declarations for view/settings manipulation tools."""

from google.genai import types

set_wells_inactive = types.FunctionDeclaration(
    name="set_wells_inactive",
    description=(
        "Mark wells as inactive. Inactive wells are excluded from the graph "
        "display regardless of selection. They keep their formatting but are "
        "visually marked on the plate map."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "wells": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Well positions to inactivate (e.g. ['A1', 'D5']).",
            ),
        },
        required=["wells"],
    ),
)

set_wells_active = types.FunctionDeclaration(
    name="set_wells_active",
    description="Reactivate previously inactivated wells so they appear on the graph again.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "wells": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Well positions to reactivate.",
            ),
        },
        required=["wells"],
    ),
)

set_well_colors = types.FunctionDeclaration(
    name="set_well_colors",
    description="Assign a custom color to one or more wells. The color applies to curves and the plate map.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "wells": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Well positions to color.",
            ),
            "color": types.Schema(
                type=types.Type.STRING,
                description="Hex color string (e.g. '#FF0000' for red, '#00AA00' for green).",
            ),
        },
        required=["wells", "color"],
    ),
)

clear_well_colors = types.FunctionDeclaration(
    name="clear_well_colors",
    description="Remove custom color assignments from wells, reverting them to the default color mode.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "wells": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Well positions to clear color from.",
            ),
        },
        required=["wells"],
    ),
)

set_color_mode = types.FunctionDeclaration(
    name="set_color_mode",
    description="Switch the curve color mode. 'Base Color' uses a single color; 'Channel Colors' uses a distinct color per channel.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "mode": types.Schema(
                type=types.Type.STRING,
                description="Color mode: 'Base Color' or 'Channel Colors'.",
                enum=["Base Color", "Channel Colors"],
            ),
        },
        required=["mode"],
    ),
)

set_display_mode = types.FunctionDeclaration(
    name="set_display_mode",
    description="Change what data the curve viewer shows.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "mode": types.Schema(
                type=types.Type.STRING,
                description="Display mode.",
                enum=[
                    "Raw Data", "Baseline Subtracted", "Baseline Divided",
                    "First Derivative", "Second Derivative",
                ],
            ),
        },
        required=["mode"],
    ),
)

set_checked_channels = types.FunctionDeclaration(
    name="set_checked_channels",
    description="Set which channels are displayed in the curve viewer. Channels not in the list are hidden.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "channels": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Channel names to display (e.g. ['465-510', '533-580']).",
            ),
        },
        required=["channels"],
    ),
)

select_wells = types.FunctionDeclaration(
    name="select_wells",
    description="Set which wells are selected for display in the curve viewer. Replaces the current selection.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "wells": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Well positions to select.",
            ),
        },
        required=["wells"],
    ),
)

set_line_width = types.FunctionDeclaration(
    name="set_line_width",
    description="Change the curve line width (0.5 to 5.0).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "width": types.Schema(
                type=types.Type.NUMBER,
                description="Line width in pixels (0.5 to 5.0).",
            ),
        },
        required=["width"],
    ),
)

set_smooth = types.FunctionDeclaration(
    name="set_smooth",
    description="Enable or disable curve smoothing (weighted moving average).",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "enabled": types.Schema(
                type=types.Type.BOOLEAN,
                description="True to enable smoothing, False to disable.",
            ),
        },
        required=["enabled"],
    ),
)

set_log_y = types.FunctionDeclaration(
    name="set_log_y",
    description="Enable or disable logarithmic Y-axis scaling.",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "enabled": types.Schema(
                type=types.Type.BOOLEAN,
                description="True for log scale, False for linear.",
            ),
        },
        required=["enabled"],
    ),
)

set_baseline_settings = types.FunctionDeclaration(
    name="set_baseline_settings",
    description=(
        "Modify baseline correction parameters. Only specify the parameters you want to "
        "change; others remain at their current values. Triggers a full recomputation of "
        "baseline, Ct, and Call values. Prefer the defaults unless a change is clearly "
        "needed or the user explicitly requests it."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "start_cycle": types.Schema(
                type=types.Type.INTEGER,
                description="First cycle of the baseline region (default: 3).",
            ),
            "end_cycle": types.Schema(
                type=types.Type.INTEGER,
                description="Last cycle of the baseline region (default: 8).",
            ),
            "ct_threshold": types.Schema(
                type=types.Type.NUMBER,
                description="RFI threshold for Ct determination (default: 1.5).",
            ),
            "call_threshold": types.Schema(
                type=types.Type.NUMBER,
                description="Endpoint RFI threshold for positive call (default: 1.5).",
            ),
        },
    ),
)

DECLARATIONS = [
    set_wells_inactive, set_wells_active,
    set_well_colors, clear_well_colors,
    set_color_mode, set_display_mode,
    set_checked_channels, select_wells,
    set_line_width, set_smooth, set_log_y,
    set_baseline_settings,
]
