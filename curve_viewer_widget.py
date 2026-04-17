"""qPCR curve viewer widget using pyqtgraph."""

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QDoubleSpinBox,
)
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, Signal, QEvent

import numpy as np

from lc480_parser import LC480Data
from color_settings import ColorSettings
from baseline import BaselineResults

# Global pyqtgraph config (white background)
pg.setConfigOptions(background='w', foreground='k', antialias=True)

DEFAULT_CHANNEL = "465-510"


# ---------------------------------------------------------------------------
# CheckableComboBox – multi-check dropdown that stays open on click
# ---------------------------------------------------------------------------

class CheckableComboBox(QComboBox):
    """QComboBox where each item has a checkbox; popup stays open on toggle."""

    checkedItemsChanged = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._item_model = QStandardItemModel(self)
        self.setModel(self._item_model)
        # Editable + read-only lets us set arbitrary display text
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setCursor(Qt.CursorShape.ArrowCursor)
        self.lineEdit().installEventFilter(self)
        self.view().viewport().installEventFilter(self)
        self._item_model.itemChanged.connect(self._on_item_changed)
        self._updating = False

    # -- public API ---------------------------------------------------------

    def add_checkable_item(self, text: str, checked: bool = True):
        item = QStandardItem(text)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setCheckState(
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self._updating = True
        self._item_model.appendRow(item)
        self._updating = False
        self._refresh_text()

    def clear_items(self):
        self._updating = True
        self._item_model.clear()
        self._updating = False
        self._refresh_text()

    def checked_items(self) -> list[str]:
        out: list[str] = []
        for i in range(self._item_model.rowCount()):
            it = self._item_model.item(i)
            if it and it.checkState() == Qt.CheckState.Checked:
                out.append(it.text())
        return out

    def set_checked(self, names: list[str]):
        """Check only the items whose text is in *names*."""
        self._updating = True
        name_set = set(names)
        for i in range(self._item_model.rowCount()):
            it = self._item_model.item(i)
            if it:
                state = (Qt.CheckState.Checked if it.text() in name_set
                         else Qt.CheckState.Unchecked)
                it.setCheckState(state)
        self._updating = False
        self._refresh_text()
        self.checkedItemsChanged.emit(self.checked_items())

    # -- internals ----------------------------------------------------------

    def eventFilter(self, obj, event):
        # Prevent popup from closing when an item is clicked
        if obj is self.view().viewport():
            if event.type() == QEvent.Type.MouseButtonRelease:
                idx = self.view().indexAt(event.pos())
                if idx.isValid():
                    it = self._item_model.itemFromIndex(idx)
                    if it and (it.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                        new = (Qt.CheckState.Unchecked
                               if it.checkState() == Qt.CheckState.Checked
                               else Qt.CheckState.Checked)
                        it.setCheckState(new)
                return True
        # Clicking the line-edit should open the popup
        if obj is self.lineEdit():
            if event.type() == QEvent.Type.MouseButtonPress:
                self.showPopup()
                return True
        return super().eventFilter(obj, event)

    def _on_item_changed(self, _item):
        if self._updating:
            return
        self._refresh_text()
        self.checkedItemsChanged.emit(self.checked_items())

    def _refresh_text(self):
        checked = self.checked_items()
        total = self._item_model.rowCount()
        if not checked:
            txt = "No channels"
        elif len(checked) == total and total > 1:
            txt = "All channels"
        elif len(checked) == 1:
            txt = checked[0]
        else:
            txt = f"{len(checked)} channels"
        self.lineEdit().setText(txt)
        self.lineEdit().deselect()
        self.lineEdit().setCursorPosition(0)


# ---------------------------------------------------------------------------
# CurveViewerWidget
# ---------------------------------------------------------------------------

class CurveViewerWidget(QWidget):
    """Curve viewer with multi-channel selector, colour modes, and controls."""

    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: LC480Data | None = None
        self._selected_wells: set[str] = set()
        self._inactive_wells: set[str] = set()
        self._line_width: float = 1.0
        self._log_y: bool = False
        self._color_settings: ColorSettings | None = None
        self._baseline_results: BaselineResults | None = None

        self._setup_ui()
        self._connect_signals()

    # -- UI ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Channels:"))
        self.channel_selector = CheckableComboBox()
        self.channel_selector.setMinimumWidth(130)
        toolbar.addWidget(self.channel_selector)

        toolbar.addSpacing(12)

        toolbar.addWidget(QLabel("Display:"))
        self.display_combo = QComboBox()
        self.display_combo.addItems([
            "Raw Data", "Baseline Subtracted", "Baseline Divided",
            "First Derivative", "Second Derivative",
        ])
        toolbar.addWidget(self.display_combo)

        toolbar.addSpacing(12)

        toolbar.addWidget(QLabel("Colors:"))
        self.color_mode_combo = QComboBox()
        self.color_mode_combo.addItems(["Base Color", "Channel Colors"])
        toolbar.addWidget(self.color_mode_combo)

        toolbar.addSpacing(12)

        self.log_y_check = QCheckBox("Log Y")
        toolbar.addWidget(self.log_y_check)

        toolbar.addSpacing(12)

        toolbar.addWidget(QLabel("Line width:"))
        self.line_width_spin = QDoubleSpinBox()
        self.line_width_spin.setRange(0.5, 5.0)
        self.line_width_spin.setSingleStep(0.5)
        self.line_width_spin.setValue(1.0)
        self.line_width_spin.setFixedWidth(60)
        toolbar.addWidget(self.line_width_spin)

        toolbar.addSpacing(12)

        self.smooth_check = QCheckBox("Smooth")
        toolbar.addWidget(self.smooth_check)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        self.graphics_layout = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics_layout)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def _connect_signals(self):
        self.channel_selector.checkedItemsChanged.connect(self._on_channels_changed)
        self.display_combo.currentTextChanged.connect(lambda _: self.refresh())
        self.color_mode_combo.currentTextChanged.connect(self._on_color_mode_changed)
        self.log_y_check.toggled.connect(self._on_log_y_changed)
        self.line_width_spin.valueChanged.connect(self._on_line_width_changed)
        self.smooth_check.toggled.connect(lambda _: self.refresh())

    # -- Public API ----------------------------------------------------------

    def set_data(self, data: LC480Data):
        """Load new data and populate channel selector."""
        self._data = data
        self.channel_selector.clear_items()
        if data and data.channels:
            default_found = False
            for ch in data.channels:
                is_default = (ch == DEFAULT_CHANNEL)
                self.channel_selector.add_checkable_item(ch, checked=is_default)
                if is_default:
                    default_found = True
            if not default_found:
                # Check the first channel if default not present
                self.channel_selector.set_checked([data.channels[0]])
        self.refresh()

    def set_selected_wells(self, wells: set[str]):
        self._selected_wells = set(wells)
        self.refresh()

    def set_inactive_wells(self, wells: set[str]):
        self._inactive_wells = set(wells)
        self.refresh()

    def set_baseline_results(self, results: BaselineResults):
        self._baseline_results = results
        self.refresh()

    def set_color_settings(self, cs: ColorSettings):
        self._color_settings = cs
        self.color_mode_combo.blockSignals(True)
        self.color_mode_combo.setCurrentText(cs.color_mode)
        self.color_mode_combo.blockSignals(False)
        self.refresh()

    def refresh(self):
        self.graphics_layout.clear()

        if not self._data or not self._selected_wells:
            self.status_label.setText("")
            return

        checked = self.channel_selector.checked_items()
        if not checked:
            self.status_label.setText("No channels selected")
            return

        wells = sorted(
            (self._selected_wells - self._inactive_wells) & set(self._data.wells)
        )

        if len(checked) == 1:
            self._draw_single(checked[0], wells)
        else:
            self._draw_multi(checked, wells)

        n_total = len(self._data.wells)
        self.status_label.setText(f"Showing {len(wells)} of {n_total} wells")

    # -- Drawing helpers -----------------------------------------------------

    def _get_y_data(self, well: str, channel: str) -> np.ndarray | None:
        """Return the Y array for the current display mode, or None to skip."""
        mode = self.display_combo.currentText()

        if mode in ("First Derivative", "Second Derivative"):
            raw = self._data.fluorescence.get(well, {}).get(channel)
            if raw is None:
                return None
            cycles = self._data.cycles
            dx = np.diff(cycles)
            first_deriv = np.diff(raw) / dx
            if mode == "First Derivative":
                return first_deriv
            midpoints = (cycles[:-1] + cycles[1:]) / 2.0
            return np.diff(first_deriv) / np.diff(midpoints)

        if mode == "Raw Data":
            return self._data.fluorescence.get(well, {}).get(channel)
        if not self._baseline_results:
            return None
        if mode == "Baseline Subtracted":
            return self._baseline_results.subtracted.get(well, {}).get(channel)
        if mode == "Baseline Divided":
            return self._baseline_results.divided.get(well, {}).get(channel)
        return None

    def _get_x_data(self) -> np.ndarray:
        """Return the X array matching the current display mode."""
        mode = self.display_combo.currentText()
        cycles = self._data.cycles
        if mode == "First Derivative":
            return (cycles[:-1] + cycles[1:]) / 2.0
        if mode == "Second Derivative":
            midpoints = (cycles[:-1] + cycles[1:]) / 2.0
            return (midpoints[:-1] + midpoints[1:]) / 2.0
        return cycles

    def _smooth(self, y: np.ndarray) -> np.ndarray:
        """Apply weighted smoothing: 50% actual point, 25% each neighbour."""
        if not self.smooth_check.isChecked() or len(y) < 2:
            return y
        s = np.empty_like(y)
        s[0] = 0.5 * y[0] + 0.5 * y[1]
        s[-1] = 0.5 * y[-1] + 0.5 * y[-2]
        s[1:-1] = 0.5 * y[1:-1] + 0.25 * y[:-2] + 0.25 * y[2:]
        return s

    def _y_label(self) -> str:
        mode = self.display_combo.currentText()
        if mode == "First Derivative":
            return "dF/dCycle"
        if mode == "Second Derivative":
            return "d\u00b2F/dCycle\u00b2"
        if mode == "Baseline Subtracted":
            return "Fluorescence (RFU, baseline subtracted)"
        if mode == "Baseline Divided":
            return "Relative Fluorescence (RFI)"
        return "Fluorescence (RFU)"

    def _pen_for(self, well: str, channel_index: int) -> pg.mkPen:
        if self._color_settings:
            c = self._color_settings.get_curve_color(well, channel_index)
        else:
            c = QColor(0, 0, 0, 255)
        return pg.mkPen(
            color=(c.red(), c.green(), c.blue(), c.alpha()),
            width=self._line_width,
        )

    def _add_zero_line(self, plot):
        """Add a dotted y=0 reference line for derivative modes."""
        if self.display_combo.currentText() in ("First Derivative", "Second Derivative"):
            zero_line = pg.InfiniteLine(
                pos=0, angle=0,
                pen=pg.mkPen(color=(0, 0, 0, 150), width=1, style=Qt.PenStyle.DotLine),
            )
            plot.addItem(zero_line)

    def _draw_single(self, channel: str, wells: list[str]):
        plot = self.graphics_layout.addPlot(
            title=channel,
            labels={'left': self._y_label(), 'bottom': 'Cycle'},
        )
        if self._log_y:
            plot.setLogMode(y=True)
        self._add_zero_line(plot)
        x = self._get_x_data()
        ch_idx = (self._data.channels.index(channel)
                  if channel in self._data.channels else 0)
        for well in wells:
            y = self._get_y_data(well, channel)
            if y is not None:
                plot.plot(x, self._smooth(y), pen=self._pen_for(well, ch_idx))

    def _draw_multi(self, channels: list[str], wells: list[str]):
        title = ", ".join(channels)
        plot = self.graphics_layout.addPlot(
            title=title,
            labels={'left': self._y_label(), 'bottom': 'Cycle'},
        )
        if self._log_y:
            plot.setLogMode(y=True)
        self._add_zero_line(plot)
        x = self._get_x_data()
        for channel in channels:
            ch_idx = (self._data.channels.index(channel)
                      if channel in self._data.channels else 0)
            for well in wells:
                y = self._get_y_data(well, channel)
                if y is not None:
                    plot.plot(x, self._smooth(y), pen=self._pen_for(well, ch_idx))

    # -- Slots ---------------------------------------------------------------

    def _on_channels_changed(self, _items: list[str]):
        self.refresh()

    def _on_color_mode_changed(self, text: str):
        if self._color_settings:
            self._color_settings.color_mode = text
        self.refresh()

    def _on_log_y_changed(self, checked: bool):
        self._log_y = checked
        self.refresh()

    def _on_line_width_changed(self, value: float):
        self._line_width = value
        self.refresh()
