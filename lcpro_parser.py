"""LC Pro XML export file parser."""

import numpy as np
import xml.etree.ElementTree as ET
from pathlib import Path

from lc480_parser import LC480Data, well_sort_key


def parse_lcpro_file(filepath: str | Path) -> LC480Data:
    """Parse an LC Pro customer export XML file.

    Returns an LC480Data object for full compatibility with the existing UI.
    """
    filepath = Path(filepath)
    tree = ET.parse(filepath)
    root = tree.getroot()

    data = LC480Data()

    # -- Metadata ------------------------------------------------------------
    plate_setup = root.find("plate/plateSetup")
    if plate_setup is not None:
        name_el = plate_setup.find("name")
        if name_el is not None and name_el.text:
            data.experiment_name = name_el.text.strip()

    instrument = root.find("instrument")
    if instrument is not None:
        ver_el = instrument.find("softwareVersion")
        if ver_el is not None and ver_el.text:
            data.software_version = f"LC Pro {ver_el.text.strip()}"

    # -- Channel map (filterId -> dye name) ----------------------------------
    channel_map: dict[int, str] = {}
    for target in root.findall(
        "runProfile/pcrProcess/pcrProfile/experimentDefinition/pcrTargets/pcrTarget"
    ):
        fid_el = target.find("filterId")
        name_el = target.find("name")
        if fid_el is not None and name_el is not None:
            channel_map[int(fid_el.text)] = name_el.text.strip()

    # Sort channels by filterId for consistent ordering
    sorted_filter_ids = sorted(channel_map.keys())
    data.channels = [channel_map[fid] for fid in sorted_filter_ids]

    # Build segmentId -> channel name lookup
    # segmentId pattern: channelNumber * 1000 + 32  (e.g. 22 -> 22032)
    seg_to_channel: dict[str, str] = {}
    for fid in sorted_filter_ids:
        seg_id = str(fid * 1000 + 32)
        seg_to_channel[seg_id] = channel_map[fid]

    # -- Raw fluorescence from rundata/measurements --------------------------
    raw: dict[str, dict[str, list[tuple[int, float]]]] = {}

    for measurement in root.findall("rundata/measurements/measurement"):
        pos_el = measurement.find("positionName")
        if pos_el is None or not pos_el.text:
            continue
        well = pos_el.text.strip()
        raw[well] = {ch: [] for ch in data.channels}

        for curve_seg in measurement.findall("curveSegments/curveSegment"):
            seg_id_el = curve_seg.find("segmentId")
            if seg_id_el is None:
                continue
            seg_id = seg_id_el.text.strip()
            channel_name = seg_to_channel.get(seg_id)
            if channel_name is None:
                continue

            for acq in curve_seg.findall("acquisitions/acquisition"):
                cycle_el = acq.find("cycle")
                value_el = acq.find("measuredValue")
                if cycle_el is not None and value_el is not None:
                    cycle = int(cycle_el.text)
                    value = float(value_el.text)
                    raw[well][channel_name].append((cycle, value))

    # -- Sample names from samples section -----------------------------------
    for sample in root.findall("samples/sample"):
        well_el = sample.find("wellPosition")
        if well_el is None or not well_el.text:
            continue
        well = well_el.text.strip()
        sample_id = sample.get("id", "")
        data.sample_names[well] = sample_id

    # -- Sort wells and build numpy arrays -----------------------------------
    data.wells = sorted(raw.keys(), key=well_sort_key)

    data.fluorescence = {}
    for well in data.wells:
        data.fluorescence[well] = {}
        for ch in data.channels:
            # Sort by cycle number, extract values
            points = sorted(raw[well][ch], key=lambda p: p[0])
            data.fluorescence[well][ch] = np.array(
                [v for _, v in points], dtype=float
            )

    if data.wells and data.channels:
        first_ch = data.channels[0]
        data.num_cycles = len(data.fluorescence[data.wells[0]][first_ch])
        data.cycles = np.arange(1, data.num_cycles + 1)

    return data
