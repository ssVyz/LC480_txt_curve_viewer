"""LC480 raw fluorescence data parser."""

import re
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LC480Data:
    """Parsed LC480 export data."""
    experiment_name: str = ""
    software_version: str = ""
    channels: list[str] = field(default_factory=list)
    wells: list[str] = field(default_factory=list)
    sample_names: dict[str, str] = field(default_factory=dict)
    num_cycles: int = 0
    fluorescence: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    cycles: np.ndarray = field(default_factory=lambda: np.array([]))


def well_sort_key(well: str) -> tuple[int, int]:
    """Sort key for well positions, column-first (A1, B1, ..., H1, A2, ...)."""
    row = ord(well[0].upper()) - ord('A')
    col = int(well[1:])
    return (col, row)


def parse_lc480_file(filepath: str | Path) -> LC480Data:
    """Parse an LC480 raw data export txt file.

    Handles both LCS480 v1.5 (1 metadata line) and v2.x (2 metadata lines)
    by dynamically finding the header row.
    """
    filepath = Path(filepath)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        with open(filepath, 'r', encoding='latin-1') as f:
            lines = f.readlines()

    data = LC480Data()

    # Find the header line (starts with SamplePos)
    header_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith('SamplePos'):
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Invalid LC480 file: could not find 'SamplePos' column header")

    # Parse metadata from lines before the header
    for i in range(header_idx):
        line = lines[i].strip()
        match = re.search(
            r'Experiment\s*-\s*(.+?)\s*\(Run on LCS480\s+(.+?)\)', line
        )
        if match:
            data.experiment_name = match.group(1).strip()
            data.software_version = match.group(2).strip()

    # Parse column headers to identify fluorescence channels
    headers = lines[header_idx].strip().split('\t')
    data.channels = [h.strip() for h in headers[7:] if h.strip()]

    # Parse data rows
    raw: dict[str, dict[str, list[float]]] = {}

    for line_num in range(header_idx + 1, len(lines)):
        line = lines[line_num].strip()
        if not line:
            continue

        parts = line.split('\t')
        if len(parts) < 8:
            continue

        well = parts[0].strip()
        sample_name = parts[1].strip()

        if well not in raw:
            raw[well] = {ch: [] for ch in data.channels}
            data.sample_names[well] = sample_name

        for j, ch in enumerate(data.channels):
            try:
                raw[well][ch].append(float(parts[7 + j]))
            except (IndexError, ValueError):
                raw[well][ch].append(0.0)

    # Sort wells in plate order
    data.wells = sorted(raw.keys(), key=well_sort_key)

    # Convert to numpy arrays
    data.fluorescence = {}
    for well in data.wells:
        data.fluorescence[well] = {}
        for ch in data.channels:
            data.fluorescence[well][ch] = np.array(raw[well][ch])

    if data.wells:
        first_ch = data.channels[0]
        data.num_cycles = len(data.fluorescence[data.wells[0]][first_ch])
        data.cycles = np.arange(1, data.num_cycles + 1)

    return data
