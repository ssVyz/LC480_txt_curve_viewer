"""Baseline correction, Ct calculation, and Call determination for qPCR data."""

from dataclasses import dataclass, field

import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QCheckBox,
)

from lc480_parser import LC480Data


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class BaselineSettings:
    """User-configurable baseline parameters."""
    start_cycle: int = 3
    end_cycle: int = 8
    ct_threshold: float = 1.5   # RFI threshold for Ct determination
    call_threshold: float = 1.5  # RFI at endpoint for positive call
    # Adaptive end: per curve, end the region before the first raw 1st-derivative
    # step (RFU/cycle) inside it that exceeds deriv_threshold
    adaptive_end: bool = False
    deriv_threshold: float = 0.1
    min_cycles: int = 3  # adaptive end never shortens the region below this

    def clamp_to_cycles(self, num_cycles: int) -> bool:
        """Fit the baseline region into 1..num_cycles (same limits as the
        dialog: at least 2 points). Returns True if anything changed."""
        old = (self.start_cycle, self.end_cycle)
        self.end_cycle = max(2, min(self.end_cycle, num_cycles))
        self.start_cycle = max(1, min(self.start_cycle, self.end_cycle - 1))
        return (self.start_cycle, self.end_cycle) != old


@dataclass
class BaselineResults:
    """Precomputed baseline correction results for all wells/channels."""
    # subtracted[well][channel] = fluorescence - baseline
    subtracted: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)
    # divided[well][channel] = fluorescence / baseline, or None if baseline has zeros
    divided: dict[str, dict[str, np.ndarray | None]] = field(default_factory=dict)
    # ct[well][channel] = Ct value or None
    ct: dict[str, dict[str, float | None]] = field(default_factory=dict)
    # call[well][channel] = "Positive" | "Negative" | "N/A"
    call: dict[str, dict[str, str]] = field(default_factory=dict)
    # endpoint_rfi[well][channel] = divided value at last cycle, or None
    endpoint_rfi: dict[str, dict[str, float | None]] = field(default_factory=dict)
    # baseline_end[well][channel] = last baseline cycle actually used, or None
    baseline_end: dict[str, dict[str, int | None]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def compute_baseline(data: LC480Data, settings: BaselineSettings) -> BaselineResults:
    """Compute baseline correction, Ct, and Call for all wells and channels."""
    results = BaselineResults()

    if not data or not data.wells:
        return results

    cycles = data.cycles  # np.array([1, 2, ..., num_cycles])
    start_idx = settings.start_cycle - 1  # 0-based inclusive

    for well in data.wells:
        results.subtracted[well] = {}
        results.divided[well] = {}
        results.ct[well] = {}
        results.call[well] = {}
        results.endpoint_rfi[well] = {}
        results.baseline_end[well] = {}

        for channel in data.channels:
            fluor = data.fluorescence.get(well, {}).get(channel)
            if fluor is None:
                results.subtracted[well][channel] = np.zeros_like(cycles, dtype=float)
                results.divided[well][channel] = None
                results.ct[well][channel] = None
                results.call[well][channel] = "N/A"
                results.endpoint_rfi[well][channel] = None
                results.baseline_end[well][channel] = None
                continue

            # Fit linear baseline to the baseline region
            # (end_cycle is 1-based inclusive, i.e. the 0-based exclusive index)
            end_cycle = _baseline_end_cycle(fluor, cycles, settings)
            results.baseline_end[well][channel] = end_cycle
            fit_x = cycles[start_idx:end_cycle]
            fit_y = fluor[start_idx:end_cycle]
            slope, intercept = np.polyfit(fit_x, fit_y, 1)
            baseline_curve = slope * cycles + intercept

            # Subtracted
            results.subtracted[well][channel] = fluor - baseline_curve

            # Divided (with zero check)
            if np.any(baseline_curve == 0):
                results.divided[well][channel] = None
                results.ct[well][channel] = None
                results.call[well][channel] = "N/A"
                results.endpoint_rfi[well][channel] = None
            else:
                divided = fluor / baseline_curve
                results.divided[well][channel] = divided

                # Ct: first cycle where divided >= ct_threshold, with interpolation
                results.ct[well][channel] = _calc_ct(divided, settings.ct_threshold)

                # Call: endpoint RFI >= call_threshold
                endpoint_rfi = float(divided[-1])
                results.endpoint_rfi[well][channel] = endpoint_rfi
                if endpoint_rfi >= settings.call_threshold:
                    results.call[well][channel] = "Positive"
                else:
                    results.call[well][channel] = "Negative"

    return results


def _baseline_end_cycle(fluor: np.ndarray, cycles: np.ndarray,
                        settings: BaselineSettings) -> int:
    """Last baseline cycle (1-based, inclusive) for one curve.

    With adaptive_end, the region ends at cycle c when the 1st derivative
    between cycles c and c+1 is the first in the region to exceed
    deriv_threshold, but always keeps at least min_cycles cycles.
    """
    start, end = settings.start_cycle, settings.end_cycle
    if not settings.adaptive_end:
        return end
    # deriv[k] = slope between cycles start+k and start+k+1
    region = slice(start - 1, end)
    deriv = np.diff(fluor[region]) / np.diff(cycles[region])
    above = np.flatnonzero(deriv > settings.deriv_threshold)
    if above.size == 0:
        return end
    min_end = min(end, start + settings.min_cycles - 1)
    return max(start + int(above[0]), min_end)


def _calc_ct(divided: np.ndarray, threshold: float) -> float | None:
    """Find Ct with linear interpolation between cycles.

    Cycles are 1-based: divided[0] = cycle 1, divided[i] = cycle i+1.
    """
    for i in range(len(divided)):
        if divided[i] >= threshold:
            if i == 0:
                return 1.0
            y_prev = divided[i - 1]
            y_curr = divided[i]
            fraction = (threshold - y_prev) / (y_curr - y_prev)
            # Cycle at index i-1 is (i), at index i is (i+1)
            return float(i) + fraction
    return None


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class BaselineSettingsDialog(QDialog):
    """Dialog for configuring baseline correction parameters."""

    def __init__(self, settings: BaselineSettings, num_cycles: int = 45,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Baseline Settings")
        self.setMinimumWidth(360)

        root = QVBoxLayout(self)

        # -- Baseline region --
        region_grp = QGroupBox("Baseline Region")
        region_lay = QGridLayout(region_grp)

        region_lay.addWidget(QLabel("Start Cycle:"), 0, 0)
        self._start_spin = QSpinBox()
        self._start_spin.setRange(1, max(num_cycles - 1, 1))
        self._start_spin.setValue(settings.start_cycle)
        region_lay.addWidget(self._start_spin, 0, 1)

        region_lay.addWidget(QLabel("End Cycle:"), 1, 0)
        self._end_spin = QSpinBox()
        self._end_spin.setRange(2, num_cycles)
        self._end_spin.setValue(settings.end_cycle)
        region_lay.addWidget(self._end_spin, 1, 1)

        # Keep end >= start + 1 (need at least 2 points for linear fit)
        self._start_spin.valueChanged.connect(
            lambda v: self._end_spin.setMinimum(v + 1)
        )
        self._end_spin.valueChanged.connect(
            lambda v: self._start_spin.setMaximum(v - 1)
        )

        root.addWidget(region_grp)

        # -- Adaptive end --
        adaptive_grp = QGroupBox("Adaptive Baseline End")
        adaptive_lay = QGridLayout(adaptive_grp)

        self._adaptive_check = QCheckBox("End region before the 1st derivative exceeds threshold")
        self._adaptive_check.setToolTip(
            "Per curve: if the raw 1st derivative between cycles c and c+1 exceeds "
            "the threshold inside the baseline region, the region ends at cycle c. "
            "Curves that stay below it use the regular region."
        )
        self._adaptive_check.setChecked(settings.adaptive_end)
        adaptive_lay.addWidget(self._adaptive_check, 0, 0, 1, 2)

        adaptive_lay.addWidget(QLabel("1st Derivative Threshold (RFU/cycle):"), 1, 0)
        self._deriv_spin = QDoubleSpinBox()
        self._deriv_spin.setRange(0.0001, 10000.0)
        self._deriv_spin.setDecimals(4)
        self._deriv_spin.setSingleStep(0.01)
        self._deriv_spin.setValue(settings.deriv_threshold)
        adaptive_lay.addWidget(self._deriv_spin, 1, 1)

        adaptive_lay.addWidget(QLabel("Minimum Cycles:"), 2, 0)
        self._min_spin = QSpinBox()
        self._min_spin.setMinimum(2)
        self._update_min_cycles_range()
        self._min_spin.setValue(settings.min_cycles)
        adaptive_lay.addWidget(self._min_spin, 2, 1)

        # Minimum can't exceed the regular region length
        self._start_spin.valueChanged.connect(self._update_min_cycles_range)
        self._end_spin.valueChanged.connect(self._update_min_cycles_range)

        self._adaptive_check.toggled.connect(self._deriv_spin.setEnabled)
        self._adaptive_check.toggled.connect(self._min_spin.setEnabled)
        self._deriv_spin.setEnabled(settings.adaptive_end)
        self._min_spin.setEnabled(settings.adaptive_end)

        root.addWidget(adaptive_grp)

        # -- Thresholds --
        thresh_grp = QGroupBox("Thresholds (RFI)")
        thresh_lay = QGridLayout(thresh_grp)

        thresh_lay.addWidget(QLabel("Ct Threshold:"), 0, 0)
        self._ct_spin = QDoubleSpinBox()
        self._ct_spin.setRange(0.01, 100.0)
        self._ct_spin.setDecimals(3)
        self._ct_spin.setSingleStep(0.1)
        self._ct_spin.setValue(settings.ct_threshold)
        thresh_lay.addWidget(self._ct_spin, 0, 1)

        thresh_lay.addWidget(QLabel("Call Threshold:"), 1, 0)
        self._call_spin = QDoubleSpinBox()
        self._call_spin.setRange(0.01, 100.0)
        self._call_spin.setDecimals(3)
        self._call_spin.setSingleStep(0.1)
        self._call_spin.setValue(settings.call_threshold)
        thresh_lay.addWidget(self._call_spin, 1, 1)

        root.addWidget(thresh_grp)

        # -- Buttons --
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def _update_min_cycles_range(self):
        self._min_spin.setMaximum(
            self._end_spin.value() - self._start_spin.value() + 1
        )

    def apply_to(self, settings: BaselineSettings):
        """Write dialog values back to the settings object."""
        settings.start_cycle = self._start_spin.value()
        settings.end_cycle = self._end_spin.value()
        settings.ct_threshold = self._ct_spin.value()
        settings.call_threshold = self._call_spin.value()
        settings.adaptive_end = self._adaptive_check.isChecked()
        settings.deriv_threshold = self._deriv_spin.value()
        settings.min_cycles = self._min_spin.value()
