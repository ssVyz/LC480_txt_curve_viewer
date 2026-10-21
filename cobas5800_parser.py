"""cobas 5800 XML result export parser."""

import zipfile
import numpy as np
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import IO

from lc480_parser import LC480Data, well_sort_key
from cobas_parser import _normalize_well

# The cobas 5800 plate has 24 wells, A1-D6
PLATE_ROWS = 4
PLATE_COLS = 6


def _iter_xml_files(paths: Iterable[str | Path]) -> Iterator[tuple[str, IO[bytes]]]:
    """Yield (name, open binary file) for each XML file and each XML in a zip."""
    for path in map(Path, paths):
        if path.suffix.lower() != ".zip":
            with open(path, "rb") as f:
                yield path.name, f
            continue
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                name = info.filename
                # Skip folders and macOS resource-fork copies ('__MACOSX/._x.xml')
                if (info.is_dir() or not name.lower().endswith(".xml")
                        or name.startswith("__MACOSX/")):
                    continue
                with zf.open(info) as f:
                    yield f"{path.name}/{name}", f


def _read_curves(md: ET.Element) -> dict[int, list[tuple[int, int, float]]]:
    """Channel number -> [(program sequence, cycle, value)] from <measurementData>."""
    seg_channel: dict[str, int] = {}
    seg_step: dict[str, str] = {}
    for ch in md.findall("channels"):
        number = int(ch.findtext("channelNumber"))
        for seg in ch.findall("segments"):
            seg_channel[seg.findtext("id")] = number
            seg_step[seg.findtext("id")] = seg.findtext("temperatureStepId")
    step_program = {
        step.findtext("id"): int(prog.findtext("sequenceNumber"))
        for prog in md.findall("programs")
        for step in prog.findall("temperatureSteps")
    }

    curves: dict[int, list[tuple[int, int, float]]] = defaultdict(list)
    for seg in md.findall("curveSegments"):
        if seg.findtext("pcrMeasurementType") != "Quantification":
            continue
        seg_id = seg.findtext("segmentId")
        if seg_id not in seg_channel:
            continue
        program = step_program.get(seg_step[seg_id], 0)
        for acq in seg.findall("acquisitions"):
            curves[seg_channel[seg_id]].append((
                program, int(acq.findtext("cycle")),
                float(acq.findtext("measuredValue")),
            ))
    return curves


def _local_time(timestamp: str) -> str:
    """'2026-10-16T11:11:53Z' (UTC) -> 'YYYY-MM-DD HH:MM' in local time."""
    try:
        return datetime.fromisoformat(timestamp).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return timestamp[:16].replace("T", " ")


def parse_cobas5800_files(paths: Iterable[str | Path]) -> list[LC480Data]:
    """Parse cobas 5800 result export XML files, given directly or as zips.

    The export has one XML per sample; each also repeats the control(s) the
    sample was validated against, which may come from an earlier run. Work
    orders are de-duplicated by id and grouped by the run they were processed
    in, so one LC480Data is returned per run, oldest first.
    """
    # run_id -> well -> channel number -> [(program, cycle, value)]
    raw: dict[str, dict[str, dict[int, list[tuple[int, int, float]]]]] = defaultdict(dict)
    sample_names: dict[str, dict[str, str]] = defaultdict(dict)
    run_start: dict[str, str] = {}
    run_tests: dict[str, set[str]] = defaultdict(set)
    software_versions: set[str] = set()
    seen_orders: set[str] = set()

    def add_work_order(order_id: str, wo: ET.Element, name: str, test: str):
        if order_id:
            if order_id in seen_orders:
                return
            seen_orders.add(order_id)
        md = wo.find("processingInfo/measurementData")
        if md is None:
            return
        curves = _read_curves(md)
        if not curves:
            return
        run_id = wo.findtext("processingInfo/runId", "")
        well = _normalize_well(md.findtext("positionName", ""))
        if well is None:
            return
        if not (ord(well[0]) - ord("A") < PLATE_ROWS and int(well[1:]) <= PLATE_COLS):
            raise ValueError(f"Invalid cobas 5800 data: well {well} is outside the 24-well plate")
        if well in raw[run_id]:
            raise ValueError(f"Invalid cobas 5800 data: well {well} occurs twice in run {run_id}")

        raw[run_id][well] = curves
        sample_names[run_id][well] = name.strip()
        start = wo.findtext("processingInfo/processingStartDateTime", "")
        if run_id not in run_start or start < run_start[run_id]:
            run_start[run_id] = start
        if test:
            run_tests[run_id].add(test)
        version = wo.findtext("instrumentInfo/softwareVersion", "")
        if version:
            software_versions.add(version)

    for name, f in _iter_xml_files(paths):
        try:
            root = ET.parse(f).getroot()
        except ET.ParseError as exc:
            raise ValueError(f"{name}: invalid XML ({exc})") from None
        if root.tag != "resultData":
            raise ValueError(f"{name}: not a cobas 5800 result file (root element is not 'resultData')")

        # Controls are named by their label, samples by barcode
        for wo in root.findall("controlWorkOrders/controlWorkOrder"):
            add_work_order(
                wo.get("id", ""), wo,
                wo.findtext("orderProperties/controlName", ""),
                wo.findtext("orderProperties/asap/name", ""),
            )
        for order in root.findall("testOrders/testOrder"):
            test = order.findtext("orderProperties/asap/name", "")
            for wo in order.findall("sampleWorkOrders/sampleWorkOrder"):
                add_work_order(
                    wo.findtext("id", ""), wo,
                    wo.findtext("sampleContainer/sampleId", ""), test,
                )

    if not raw:
        raise ValueError("No cobas 5800 PCR raw data found")

    software_version = f"cobas 5800 {', '.join(sorted(software_versions))}".strip()

    runs: list[LC480Data] = []
    for run_id in sorted(raw, key=lambda r: run_start[r]):
        wells = raw[run_id]
        data = LC480Data()
        tests = ", ".join(sorted(run_tests[run_id]))
        data.experiment_name = f"{tests} {_local_time(run_start[run_id])}".strip()
        data.software_version = software_version
        data.plate_rows = PLATE_ROWS
        data.plate_cols = PLATE_COLS

        numbers = sorted({n for curves in wells.values() for n in curves})
        data.channels = [f"Ch{n}" for n in numbers]
        data.wells = sorted(wells, key=well_sort_key)
        data.sample_names = sample_names[run_id]

        # The PCR runs as consecutive programs (5 + 45 cycles), each counting
        # from cycle 1; joining them in program order gives cycles 1-50
        for well in data.wells:
            data.fluorescence[well] = {}
            for n, ch in zip(numbers, data.channels):
                points = sorted(wells[well].get(n, []))
                data.fluorescence[well][ch] = np.array(
                    [v for _, _, v in points], dtype=float
                )

        if data.channels:
            first_ch = data.channels[0]
            data.num_cycles = len(data.fluorescence[data.wells[0]][first_ch])
            data.cycles = np.arange(1, data.num_cycles + 1)
        runs.append(data)

    return runs
