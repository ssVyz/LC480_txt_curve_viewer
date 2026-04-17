"""Function declarations for data reading tools."""

from google.genai import types

get_experiment_info = types.FunctionDeclaration(
    name="get_experiment_info",
    description=(
        "Get an overview of the currently loaded experiment: name, list of wells, "
        "channels, number of cycles, and sample names. Call this first to understand "
        "the plate layout before querying individual wells."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={},
    ),
)

get_well_data = types.FunctionDeclaration(
    name="get_well_data",
    description=(
        "Get summary statistics for specified wells. Returns per-well, per-channel: "
        "raw fluorescence at first and last cycle, max first derivative, max second "
        "derivative, Ct value, Call (Positive/Negative/N/A), and endpoint RFI. "
        "Use this to assess which wells contain reactions, are empty, or are "
        "positive/negative. Query only the wells you need to save tokens."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "wells": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="List of well positions to query (e.g. ['A1', 'B2', 'H12']).",
            ),
            "channels": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description=(
                    "Optional list of channel names to include. If omitted, "
                    "uses the first available channel only."
                ),
            ),
        },
        required=["wells"],
    ),
)

DECLARATIONS = [get_experiment_info, get_well_data]
