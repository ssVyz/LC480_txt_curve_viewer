"""Color compensation for qPCR multiplex cross-talk correction."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QCheckBox, QComboBox, QDoubleSpinBox,
    QPushButton, QFileDialog, QMessageBox, QScrollArea, QWidget,
)
from PySide6.QtCore import Qt

from baseline import BaselineResults, _calc_ct, BaselineSettings


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ColorCompensationRule:
    """A single compensation rule: subtract scaled source from target."""
    target_channel: str = ""
    source_channel: str = ""
    factor: float = 0.0


@dataclass
class ColorCompensationSettings:
    """All color compensation settings."""
    enabled: bool = False
    rules: list[ColorCompensationRule] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Computation
# ---------------------------------------------------------------------------

def apply_color_compensation(
    baseline_results: BaselineResults,
    settings: ColorCompensationSettings,
    baseline_settings: BaselineSettings,
    wells: list[str],
    channels: list[str],
) -> BaselineResults:
    """Apply color compensation to baseline divided data and recompute Ct/Call.

    For each rule: target -= (source - 1) * factor
    where source and target are baseline divided arrays.

    Returns a new BaselineResults with compensated divided data, and
    recalculated Ct and Call values for affected channels.
    """
    if not settings.enabled or not settings.rules:
        return baseline_results

    # Deep-copy the divided dict so we don't mutate the original
    new_divided: dict[str, dict[str, np.ndarray | None]] = {}
    for well in wells:
        new_divided[well] = {}
        for ch in channels:
            orig = baseline_results.divided.get(well, {}).get(ch)
            if orig is not None:
                new_divided[well][ch] = orig.copy()
            else:
                new_divided[well][ch] = None

    # Apply each rule
    channel_set = set(channels)
    for rule in settings.rules:
        if rule.target_channel not in channel_set or rule.source_channel not in channel_set:
            continue
        if rule.factor == 0.0:
            continue

        for well in wells:
            source = new_divided[well].get(rule.source_channel)
            target = new_divided[well].get(rule.target_channel)
            if source is None or target is None:
                continue
            target -= (source - 1.0) * rule.factor

    # Recompute Ct, Call, and endpoint_rfi for affected target channels
    affected_channels = {r.target_channel for r in settings.rules if r.target_channel in channel_set}

    new_ct = {}
    new_call = {}
    new_endpoint_rfi = {}
    for well in wells:
        new_ct[well] = dict(baseline_results.ct.get(well, {}))
        new_call[well] = dict(baseline_results.call.get(well, {}))
        new_endpoint_rfi[well] = dict(baseline_results.endpoint_rfi.get(well, {}))

        for ch in affected_channels:
            divided = new_divided[well].get(ch)
            if divided is None:
                new_ct[well][ch] = None
                new_call[well][ch] = "N/A"
                new_endpoint_rfi[well][ch] = None
            else:
                new_ct[well][ch] = _calc_ct(divided, baseline_settings.ct_threshold)
                endpoint_rfi = float(divided[-1])
                new_endpoint_rfi[well][ch] = endpoint_rfi
                if endpoint_rfi >= baseline_settings.call_threshold:
                    new_call[well][ch] = "Positive"
                else:
                    new_call[well][ch] = "Negative"

    return BaselineResults(
        subtracted=baseline_results.subtracted,
        divided=new_divided,
        ct=new_ct,
        call=new_call,
        endpoint_rfi=new_endpoint_rfi,
    )


# ---------------------------------------------------------------------------
# JSON import / export
# ---------------------------------------------------------------------------

def rules_to_json(rules: list[ColorCompensationRule]) -> dict:
    return {
        "rules": [
            {
                "target_channel": r.target_channel,
                "source_channel": r.source_channel,
                "factor": r.factor,
            }
            for r in rules
        ]
    }


def rules_from_json(data: dict, available_channels: list[str]) -> tuple[list[ColorCompensationRule], list[str]]:
    """Parse rules from JSON dict, filtering to available channels.

    Returns (accepted_rules, skipped_channel_names).
    """
    channel_set = set(available_channels)
    accepted = []
    skipped = set()

    for entry in data.get("rules", []):
        target = entry.get("target_channel", "")
        source = entry.get("source_channel", "")
        factor = entry.get("factor", 0.0)

        missing = []
        if target not in channel_set:
            missing.append(target)
        if source not in channel_set:
            missing.append(source)

        if missing:
            skipped.update(missing)
        else:
            accepted.append(ColorCompensationRule(
                target_channel=target,
                source_channel=source,
                factor=float(factor),
            ))

    return accepted, sorted(skipped)


# ---------------------------------------------------------------------------
# Rule row widget
# ---------------------------------------------------------------------------

class _RuleRow(QWidget):
    """A single rule row: target combo, source combo, factor spin, remove btn."""

    def __init__(self, channels: list[str], parent=None):
        super().__init__(parent)
        self._channels = channels
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)

        lay.addWidget(QLabel("Target:"))
        self.target_combo = QComboBox()
        self.target_combo.addItems(channels)
        self.target_combo.setMinimumWidth(100)
        lay.addWidget(self.target_combo)

        lay.addSpacing(8)
        lay.addWidget(QLabel("Source:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(channels)
        self.source_combo.setMinimumWidth(100)
        lay.addWidget(self.source_combo)

        lay.addSpacing(8)
        lay.addWidget(QLabel("Factor:"))
        self.factor_spin = QDoubleSpinBox()
        self.factor_spin.setRange(0.0, 1.0)
        self.factor_spin.setDecimals(3)
        self.factor_spin.setSingleStep(0.01)
        self.factor_spin.setValue(0.0)
        self.factor_spin.setFixedWidth(80)
        lay.addWidget(self.factor_spin)

        lay.addSpacing(8)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setFixedWidth(70)
        lay.addWidget(self.remove_btn)

        lay.addStretch()

    def get_rule(self) -> ColorCompensationRule:
        return ColorCompensationRule(
            target_channel=self.target_combo.currentText(),
            source_channel=self.source_combo.currentText(),
            factor=self.factor_spin.value(),
        )

    def set_rule(self, rule: ColorCompensationRule):
        idx_t = self.target_combo.findText(rule.target_channel)
        if idx_t >= 0:
            self.target_combo.setCurrentIndex(idx_t)
        idx_s = self.source_combo.findText(rule.source_channel)
        if idx_s >= 0:
            self.source_combo.setCurrentIndex(idx_s)
        self.factor_spin.setValue(rule.factor)


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class ColorCompensationDialog(QDialog):
    """Dialog for configuring color compensation rules."""

    def __init__(self, settings: ColorCompensationSettings,
                 channels: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Color Compensation")
        self.setMinimumWidth(620)
        self.setMinimumHeight(300)
        self._channels = channels
        self._rule_rows: list[_RuleRow] = []

        root = QVBoxLayout(self)

        # -- Enable checkbox --
        self._enabled_check = QCheckBox("Use color compensation")
        self._enabled_check.setChecked(settings.enabled)
        root.addWidget(self._enabled_check)

        # -- Rules group --
        rules_grp = QGroupBox("Compensation Rules")
        rules_outer = QVBoxLayout(rules_grp)

        # Scroll area for rule rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(150)
        self._rules_container = QWidget()
        self._rules_layout = QVBoxLayout(self._rules_container)
        self._rules_layout.setContentsMargins(4, 4, 4, 4)
        self._rules_layout.addStretch()
        scroll.setWidget(self._rules_container)
        rules_outer.addWidget(scroll)

        # Add rule button
        add_row = QHBoxLayout()
        add_btn = QPushButton("Add Rule")
        add_btn.clicked.connect(self._add_rule_row)
        add_row.addWidget(add_btn)
        add_row.addStretch()
        rules_outer.addLayout(add_row)

        root.addWidget(rules_grp)

        # -- Import/Export --
        io_row = QHBoxLayout()
        export_btn = QPushButton("Export Rules...")
        export_btn.clicked.connect(self._export_rules)
        io_row.addWidget(export_btn)
        import_btn = QPushButton("Import Rules...")
        import_btn.clicked.connect(self._import_rules)
        io_row.addWidget(import_btn)
        io_row.addStretch()
        root.addLayout(io_row)

        # -- OK / Cancel --
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

        # Populate existing rules
        for rule in settings.rules:
            self._add_rule_row(rule)

    def _add_rule_row(self, rule: ColorCompensationRule | None = None):
        if not self._channels:
            return
        row = _RuleRow(self._channels, self._rules_container)
        if isinstance(rule, ColorCompensationRule):
            row.set_rule(rule)
        row.remove_btn.clicked.connect(lambda: self._remove_rule_row(row))
        # Insert before the stretch
        self._rules_layout.insertWidget(self._rules_layout.count() - 1, row)
        self._rule_rows.append(row)

    def _remove_rule_row(self, row: _RuleRow):
        self._rules_layout.removeWidget(row)
        row.deleteLater()
        self._rule_rows.remove(row)

    def _get_rules(self) -> list[ColorCompensationRule]:
        return [row.get_rule() for row in self._rule_rows]

    def apply_to(self, settings: ColorCompensationSettings):
        """Write dialog values back to the settings object."""
        settings.enabled = self._enabled_check.isChecked()
        settings.rules = self._get_rules()

    def _export_rules(self):
        rules = self._get_rules()
        if not rules:
            QMessageBox.information(self, "Export", "No rules to export.")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Color Compensation Rules", "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not filepath:
            return
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(rules_to_json(rules), f, indent=2)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _import_rules(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Color Compensation Rules", "",
            "JSON Files (*.json);;All Files (*)",
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return

        accepted, skipped = rules_from_json(data, self._channels)

        if not accepted and skipped:
            QMessageBox.warning(
                self, "Import Failed",
                "The color compensation file does not match any of the "
                "channels in the loaded LC file.\n\n"
                f"Missing channels: {', '.join(skipped)}",
            )
            return

        if skipped:
            QMessageBox.information(
                self, "Partial Import",
                f"Some rules were skipped because channels are not present "
                f"in the loaded LC file:\n\n{', '.join(skipped)}",
            )

        # Add imported rules to existing ones
        for rule in accepted:
            self._add_rule_row(rule)
