"""qPCR curve viewer widget using pyqtgraph."""

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QCheckBox, QDoubleSpinBox,
)
from PySide6.QtCore import Signal

from lc480_parser import LC480Data

# Global pyqtgraph config (white background for B&W theme)
pg.setConfigOptions(background='w', foreground='k', antialias=True)

ALL_CHANNELS = "All Channels"
DEFAULT_CHANNEL = "465-510"


class CurveViewerWidget(QWidget):
    """Curve viewer with channel selector, display mode, and plot controls."""

    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: LC480Data | None = None
        self._selected_wells: set[str] = set()
        self._line_width: float = 1.0
        self._log_y: bool = False
        self._display_mode: str = "Raw Data"

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # -- Toolbar ---------------------------------------------------------
        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setMinimumWidth(110)
        toolbar.addWidget(self.channel_combo)

        toolbar.addSpacing(12)

        toolbar.addWidget(QLabel("Display:"))
        self.display_combo = QComboBox()
        self.display_combo.addItem("Raw Data")
        toolbar.addWidget(self.display_combo)

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

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # -- Plot area -------------------------------------------------------
        self.graphics_layout = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphics_layout)

        # -- Status label ----------------------------------------------------
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def _connect_signals(self):
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        self.display_combo.currentTextChanged.connect(self._on_display_changed)
        self.log_y_check.toggled.connect(self._on_log_y_changed)
        self.line_width_spin.valueChanged.connect(self._on_line_width_changed)

    # -- Public API ----------------------------------------------------------

    def set_data(self, data: LC480Data):
        """Set the data source and populate channel selector."""
        self._data = data
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        if data and data.channels:
            for ch in data.channels:
                self.channel_combo.addItem(ch)
            self.channel_combo.addItem(ALL_CHANNELS)
            # Default to 465-510 (SYBR/FAM) if available
            idx = self.channel_combo.findText(DEFAULT_CHANNEL)
            if idx >= 0:
                self.channel_combo.setCurrentIndex(idx)
        self.channel_combo.blockSignals(False)
        self.refresh()

    def set_selected_wells(self, wells: set[str]):
        """Update which wells are displayed."""
        self._selected_wells = set(wells)
        self.refresh()

    def refresh(self):
        """Redraw all curves based on current settings."""
        self.graphics_layout.clear()

        if not self._data or not self._selected_wells:
            self.status_label.setText("")
            return

        channel = self.channel_combo.currentText()
        if not channel:
            return

        if channel == ALL_CHANNELS:
            self._draw_all_channels()
        else:
            self._draw_single_channel(channel)

        n_shown = len(self._selected_wells & set(self._data.wells))
        n_total = len(self._data.wells)
        self.status_label.setText(f"Showing {n_shown} of {n_total} wells")

    # -- Drawing helpers -----------------------------------------------------

    def _make_pen(self, n_curves: int) -> pg.mkPen:
        """Create a pen with alpha scaled to number of curves."""
        alpha = max(25, min(255, int(255 / max(1, n_curves / 4))))
        return pg.mkPen(color=(0, 0, 0, alpha), width=self._line_width)

    def _draw_single_channel(self, channel: str):
        plot = self.graphics_layout.addPlot(
            title=channel,
            labels={'left': 'Fluorescence (RFU)', 'bottom': 'Cycle'},
        )
        if self._log_y:
            plot.setLogMode(y=True)

        wells = sorted(self._selected_wells & set(self._data.wells))
        pen = self._make_pen(len(wells))

        for well in wells:
            fluo = self._data.fluorescence.get(well, {})
            y = fluo.get(channel)
            if y is not None:
                plot.plot(self._data.cycles, y, pen=pen)

    def _draw_all_channels(self):
        plots: list[pg.PlotItem] = []
        n_ch = len(self._data.channels)
        wells = sorted(self._selected_wells & set(self._data.wells))
        pen = self._make_pen(len(wells))

        for i, channel in enumerate(self._data.channels):
            is_last = (i == n_ch - 1)
            plot = self.graphics_layout.addPlot(
                row=i, col=0,
                title=channel,
                labels={
                    'left': 'RFU',
                    'bottom': 'Cycle' if is_last else '',
                },
            )
            if self._log_y:
                plot.setLogMode(y=True)
            if plots:
                plot.setXLink(plots[0])
            if not is_last:
                plot.hideAxis('bottom')
            plots.append(plot)

            for well in wells:
                fluo = self._data.fluorescence.get(well, {})
                y = fluo.get(channel)
                if y is not None:
                    plot.plot(self._data.cycles, y, pen=pen)

    # -- Signal handlers -----------------------------------------------------

    def _on_channel_changed(self, text: str):
        self.refresh()

    def _on_display_changed(self, text: str):
        self._display_mode = text
        self.refresh()

    def _on_log_y_changed(self, checked: bool):
        self._log_y = checked
        self.refresh()

    def _on_line_width_changed(self, value: float):
        self._line_width = value
        self.refresh()
