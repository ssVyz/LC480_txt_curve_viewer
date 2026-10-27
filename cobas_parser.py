"""cobas 6800/8800 XML export file parser."""

import numpy as np
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from lc480_parser import LC480Data, well_sort_key


def _normalize_well(name: str) -> str | None:
    """'G01' -> 'G1' (the plate map and *.plate files use unpadded names)."""
    name = name.strip()
    try:
        return f"{name[0].upper()}{int(name[1:])}"
    except (IndexError, ValueError):
        return None


def _channel_name(excitation: int, emission: int) -> str:
    return f"Ch{emission}" if excitation == emission else f"Ch{excitation}-{emission}"


def _sample_name(order: ET.Element) -> str:
    """Barcode for samples; the label (e.g. '(-) Ctrl') for controls."""
    specimen = order.find("Specimen")
    el = next(iter(specimen), None) if specimen is not None else None
    if el is None:
        return ""
    label = el.get("Info", "") if el.get("ControlType") else ""
    return (label or el.get("Barcode", "")).strip()


def _read_file(filepath: Path, raw, sample_names, run_start, run_tests,
               test_names) -> str:
    """Add one export file's runs to the dicts; returns its software version."""
    # (run, well) read from this file
    file_wells: set[tuple[str, str]] = set()

    # Stream the file: full exports are large, mostly process logs and
    # embedded algorithm files that are not needed here
    context = ET.iterparse(filepath, events=("start", "end"))
    _, root = next(context)
    if root.tag != "DomainObjects":
        raise ValueError(
            f"Invalid cobas file {filepath.name}: root element is not 'DomainObjects'"
        )

    for event, el in context:
        if event != "end":
            continue
        if el.tag == "TestRequested":
            test_names[el.get("Id", "")] = el.get("Name", "")
        elif el.tag == "ProcessRequested":
            el.clear()
        elif el.tag == "TestOrder":
            sample = _sample_name(el)
            for proc in el.findall("ProcessOrders/ProcessOrder"):
                raw_data = proc.find("ProcessResult/ProcessResultData/RawData")
                if raw_data is None:
                    continue
                run = proc.find("ProcessRun")
                run_id = run.get("RunId", "") if run is not None else ""
                start = run.get("StartTime", "") if run is not None else ""
                if run_id not in run_start or start < run_start[run_id]:
                    run_start[run_id] = start
                run_tests[run_id].add(el.get("TestRequested", ""))

                for well_el in raw_data.findall("Wells/Well"):
                    well = _normalize_well(well_el.get("PositionName", ""))
                    if well is None:
                        continue
                    if (run_id, well) in file_wells:
                        raise ValueError(
                            f"Invalid cobas file {filepath.name}: "
                            f"well {well} occurs twice in one run"
                        )
                    file_wells.add((run_id, well))
                    # Already read from an earlier, overlapping export
                    if well in raw[run_id]:
                        continue
                    curves: dict[tuple[int, int], list[tuple[int, int, float]]] = defaultdict(list)
                    for program in well_el.findall("Programs/Program"):
                        program_id = int(program.get("Id", "0"))
                        for ch_el in program.findall("Channels/Channel"):
                            key = (int(ch_el.get("ExcitationFilterId")),
                                   int(ch_el.get("EmissionFilterId")))
                            for mtype in ch_el.findall("MeasurementTypes/MeasurementType"):
                                if mtype.get("Type") != "Quantification":
                                    continue
                                for m in mtype.findall("Measurements/Measurement"):
                                    curves[key].append((
                                        program_id, int(m.get("Sequence")),
                                        float(m.findtext("Value")),
                                    ))
                    raw[run_id][well] = curves
                    sample_names[run_id][well] = sample
            el.clear()

    return root.get("SoftwareVersion", "")


def parse_cobas_files(paths: Iterable[str | Path]) -> list[LC480Data]:
    """Parse cobas 6800/8800 result export XML files.

    An export can hold test orders from several runs (AD plates) whose well
    positions overlap, so one LC480Data is returned per run, oldest first.
    Runs can span several exports, and exports can overlap: a well already
    read from an earlier file is skipped.
    """
    # run_id -> well -> channel key (excitation, emission) -> [(program, seq, value)]
    raw: dict[str, dict[str, dict[tuple[int, int], list[tuple[int, int, float]]]]] = (
        defaultdict(dict)
    )
    sample_names: dict[str, dict[str, str]] = defaultdict(dict)
    run_start: dict[str, str] = {}
    run_tests: dict[str, set[str]] = defaultdict(set)
    test_names: dict[str, str] = {}
    software_versions: set[str] = set()

    for filepath in map(Path, paths):
        version = _read_file(filepath, raw, sample_names, run_start, run_tests, test_names)
        if version:
            software_versions.add(version)

    if not raw:
        raise ValueError("Invalid cobas file: no PCR raw data found")

    software_version = f"cobas {', '.join(sorted(software_versions))}".strip()

    runs: list[LC480Data] = []
    for run_id in sorted(raw, key=lambda r: run_start[r]):
        wells = raw[run_id]
        data = LC480Data()
        tests = ", ".join(sorted(test_names.get(t, t) for t in run_tests[run_id]))
        # ISO timestamp -> 'YYYY-MM-DD HH:MM'
        data.experiment_name = f"{tests} {run_start[run_id][:16].replace('T', ' ')}".strip()
        data.software_version = software_version

        keys = sorted({k for curves in wells.values() for k in curves})
        data.channels = [_channel_name(*k) for k in keys]
        data.wells = sorted(wells, key=well_sort_key)
        data.sample_names = sample_names[run_id]

        # The PCR runs as consecutive programs (e.g. 5 + 45 cycles); joining
        # them in program order gives the cycle numbering the cobas Ct uses
        for well in data.wells:
            data.fluorescence[well] = {}
            for key, ch in zip(keys, data.channels):
                points = sorted(wells[well].get(key, []))
                data.fluorescence[well][ch] = np.array(
                    [v for _, _, v in points], dtype=float
                )

        if data.channels:
            first_ch = data.channels[0]
            data.num_cycles = len(data.fluorescence[data.wells[0]][first_ch])
            data.cycles = np.arange(1, data.num_cycles + 1)
        runs.append(data)

    return runs
