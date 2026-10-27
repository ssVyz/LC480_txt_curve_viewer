"""Several plates open side by side: well keys and the combined run.

With one plate open, wells are keyed by their position ('A1') as always. With
several, keys carry the plate number ('P2:A1') so plates can share positions.
"""

from lc480_parser import LC480Data


def well_key(plate_no: int, well: str) -> str:
    """'A1' on plate 2 -> 'P2:A1'."""
    return f"P{plate_no}:{well}"


def split_well_key(key: str) -> tuple[int, str]:
    """'P2:A1' -> (2, 'A1'); a plain well name is on plate 1."""
    prefix, sep, well = key.partition(":")
    if sep and prefix[:1] == "P" and prefix[1:].isdigit():
        return int(prefix[1:]), well
    return 1, key


def combine_plates(plates: list[LC480Data]) -> LC480Data:
    """Merge plates into one run for the curve viewer, sample table and baseline.

    A single plate is returned unchanged. Plates must have the same number of
    cycles, since all curves share one cycle axis.
    """
    if len(plates) == 1:
        return plates[0]
    if len({p.num_cycles for p in plates}) > 1:
        counts = ", ".join(str(p.num_cycles) for p in plates)
        raise ValueError(
            f"Plates with different numbers of cycles ({counts}) cannot be opened together."
        )

    data = LC480Data()
    data.experiment_name = "; ".join(p.experiment_name for p in plates)
    data.software_version = ", ".join(
        dict.fromkeys(p.software_version for p in plates if p.software_version)
    )
    data.channels = list(dict.fromkeys(ch for p in plates for ch in p.channels))
    data.num_cycles = plates[0].num_cycles
    data.cycles = plates[0].cycles
    data.plate_rows = max(p.plate_rows for p in plates)
    data.plate_cols = max(p.plate_cols for p in plates)
    for n, p in enumerate(plates, 1):
        for well in p.wells:
            key = well_key(n, well)
            data.wells.append(key)
            data.sample_names[key] = p.sample_names.get(well, "")
            data.fluorescence[key] = p.fluorescence[well]
    return data
