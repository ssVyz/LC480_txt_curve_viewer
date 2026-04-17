"""Heatmap dialog showing a color-coded plate map based on Ct/Call results."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QCheckBox,
    QDoubleSpinBox, QFormLayout, QGroupBox,
)
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QLinearGradient


class HeatmapPlateWidget(QWidget):
    """Non-interactive plate map colored by Ct/Call results."""

    ROWS = 8
    COLS = 12
    ROW_LABELS = [chr(ord('A') + i) for i in range(8)]
    COL_LABELS = [str(i + 1) for i in range(12)]
    LABEL_MARGIN = 24
    PADDING = 4

    COLOR_NO_DATA = QColor(220, 220, 220)
    COLOR_NEGATIVE = QColor(76, 175, 80)       # green
    COLOR_POSITIVE = QColor(244, 67, 54)       # red (flat mode)
    COLOR_LOW_CT = QColor(244, 67, 54)          # red (lowest Ct = highest conc)
    COLOR_HIGH_CT = QColor(255, 235, 59)        # yellow (highest Ct = lowest conc)
    COLOR_NA = QColor(189, 189, 189)            # gray for N/A

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wells_with_data: set[str] = set()
        self._sample_names: dict[str, str] = {}
        self._call_data: dict[str, str] = {}
        self._ct_data: dict[str, float | None] = {}
        self._inactive_wells: set[str] = set()
        self._ct_min: float | None = None
        self._ct_max: float | None = None
        self._gradient_enabled: bool = True
        self._red_point: float | None = None   # user-defined low Ct (red end)
        self._yellow_point: float | None = None  # user-defined high Ct (yellow end)
        self.setMinimumSize(400, 300)

    def set_data(self, wells: list[str], sample_names: dict[str, str],
                 call_data: dict[str, str], ct_data: dict[str, float | None]):
        self._wells_with_data = set(wells)
        self._sample_names = dict(sample_names)
        self._call_data = dict(call_data)
        self._ct_data = dict(ct_data)

        # Compute Ct range from positive wells only
        positive_cts = [
            ct for well, ct in ct_data.items()
            if ct is not None and call_data.get(well) == "Positive"
        ]
        if positive_cts:
            self._ct_min = min(positive_cts)
            self._ct_max = max(positive_cts)
        else:
            self._ct_min = None
            self._ct_max = None

        self.update()

    def set_gradient_enabled(self, enabled: bool):
        self._gradient_enabled = enabled
        self.update()

    def set_gradient_range(self, red_point: float | None, yellow_point: float | None):
        self._red_point = red_point
        self._yellow_point = yellow_point
        self.update()

    def set_inactive_wells(self, wells: set[str]):
        self._inactive_wells = set(wells)
        self.update()

    @property
    def effective_red_point(self) -> float | None:
        return self._red_point if self._red_point is not None else self._ct_min

    @property
    def effective_yellow_point(self) -> float | None:
        return self._yellow_point if self._yellow_point is not None else self._ct_max

    # -- Geometry (same as PlateMapWidget) -----------------------------------

    def _cell_geometry(self) -> tuple[float, float, float]:
        avail_w = self.width() - self.LABEL_MARGIN - self.PADDING * 2
        avail_h = self.height() - self.LABEL_MARGIN - self.PADDING * 2
        cell_w = avail_w / self.COLS
        cell_h = avail_h / self.ROWS
        cell_size = min(cell_w, cell_h)
        grid_w = cell_size * self.COLS
        grid_h = cell_size * self.ROWS
        offset_x = self.LABEL_MARGIN + self.PADDING + (avail_w - grid_w) / 2
        offset_y = self.LABEL_MARGIN + self.PADDING + (avail_h - grid_h) / 2
        return cell_size, offset_x, offset_y

    def _well_rect(self, row: int, col: int) -> QRectF:
        cell_size, ox, oy = self._cell_geometry()
        d = cell_size * 0.78
        cx = ox + (col + 0.5) * cell_size
        cy = oy + (row + 0.5) * cell_size
        return QRectF(cx - d / 2, cy - d / 2, d, d)

    @staticmethod
    def _rc_to_well(row: int, col: int) -> str:
        return f"{chr(ord('A') + row)}{col + 1}"

    # -- Color logic ---------------------------------------------------------

    def _well_color(self, well: str) -> QColor:
        if well not in self._wells_with_data:
            return self.COLOR_NO_DATA
        if well in self._inactive_wells:
            return self.COLOR_NA

        call = self._call_data.get(well, "N/A")
        if call == "N/A":
            return self.COLOR_NA
        if call == "Negative":
            return QColor(self.COLOR_NEGATIVE)

        # Positive well
        if not self._gradient_enabled:
            return QColor(self.COLOR_POSITIVE)

        # Gradient mode: red (low Ct) to yellow (high Ct)
        ct = self._ct_data.get(well)
        if ct is None:
            return QColor(self.COLOR_LOW_CT)

        lo = self.effective_red_point
        hi = self.effective_yellow_point
        if lo is None or hi is None or lo == hi:
            return QColor(self.COLOR_LOW_CT)

        # t=0 at red point (red), t=1 at yellow point (yellow)
        t = (ct - lo) / (hi - lo)
        t = max(0.0, min(1.0, t))
        r = int(self.COLOR_LOW_CT.red() + t * (self.COLOR_HIGH_CT.red() - self.COLOR_LOW_CT.red()))
        g = int(self.COLOR_LOW_CT.green() + t * (self.COLOR_HIGH_CT.green() - self.COLOR_LOW_CT.green()))
        b = int(self.COLOR_LOW_CT.blue() + t * (self.COLOR_HIGH_CT.blue() - self.COLOR_LOW_CT.blue()))
        return QColor(r, g, b)

    # -- Painting ------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        cell_size, ox, oy = self._cell_geometry()
        if cell_size <= 0:
            painter.end()
            return

        font = QFont()
        font.setPointSize(max(7, int(cell_size * 0.3)))
        painter.setFont(font)

        # Column labels
        painter.setPen(QColor(0, 0, 0))
        for col in range(self.COLS):
            cx = ox + (col + 0.5) * cell_size
            r = QRectF(cx - cell_size / 2, 0, cell_size, self.LABEL_MARGIN)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, self.COL_LABELS[col])

        # Row labels
        for row in range(self.ROWS):
            cy = oy + (row + 0.5) * cell_size
            r = QRectF(0, cy - cell_size / 2, self.LABEL_MARGIN, cell_size)
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, self.ROW_LABELS[row])

        # Wells
        for row in range(self.ROWS):
            for col in range(self.COLS):
                well = self._rc_to_well(row, col)
                rect = self._well_rect(row, col)
                fill = self._well_color(well)
                border = fill.darker(120) if well in self._wells_with_data else QColor(180, 180, 180)
                painter.setPen(QPen(border, 1.0))
                painter.setBrush(fill)
                painter.drawEllipse(rect)

        painter.end()


class GradientLegendWidget(QWidget):
    """Horizontal gradient legend bar for the heatmap."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ct_min: float | None = None
        self._ct_max: float | None = None
        self.setFixedHeight(40)

    def set_range(self, ct_min: float | None, ct_max: float | None):
        self._ct_min = ct_min
        self._ct_max = ct_max
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        margin = 60
        bar_h = 14
        bar_y = 4

        if self._ct_min is not None and self._ct_max is not None:
            # Gradient bar: red (left, low Ct) → yellow (right, high Ct)
            grad = QLinearGradient(margin, 0, w - margin, 0)
            grad.setColorAt(0.0, HeatmapPlateWidget.COLOR_LOW_CT)
            grad.setColorAt(1.0, HeatmapPlateWidget.COLOR_HIGH_CT)
            bar_rect = QRectF(margin, bar_y, w - 2 * margin, bar_h)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(bar_rect, 3, 3)

            # Labels
            painter.setPen(QColor(0, 0, 0))
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(
                QRectF(margin, bar_y + bar_h + 2, 80, 16),
                Qt.AlignmentFlag.AlignLeft,
                f"Ct {self._ct_min:.1f}",
            )
            painter.drawText(
                QRectF(w - margin - 80, bar_y + bar_h + 2, 80, 16),
                Qt.AlignmentFlag.AlignRight,
                f"Ct {self._ct_max:.1f}",
            )
        else:
            painter.setPen(QColor(120, 120, 120))
            font = QFont()
            font.setPointSize(8)
            painter.setFont(font)
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "No positive wells to display gradient",
            )

        painter.end()


class HeatmapDialog(QDialog):
    """Dialog displaying a color-coded plate heatmap based on Ct/Call results."""

    def __init__(self, wells: list[str], sample_names: dict[str, str],
                 call_data: dict[str, str], ct_data: dict[str, float | None],
                 channel: str = "", inactive_wells: set[str] | None = None,
                 parent=None):
        super().__init__(parent)
        title = "Heatmap"
        if channel:
            title += f" - {channel}"
        self.setWindowTitle(title)
        self.resize(600, 520)

        layout = QVBoxLayout(self)

        self._plate = HeatmapPlateWidget()
        self._plate.set_data(wells, sample_names, call_data, ct_data)
        if inactive_wells:
            self._plate.set_inactive_wells(inactive_wells)
        layout.addWidget(self._plate)

        # Legend row
        legend_row = QHBoxLayout()
        legend_row.addSpacing(8)

        # Positive swatch
        pos_swatch = QLabel()
        pos_swatch.setFixedSize(16, 16)
        pos_swatch.setStyleSheet(
            f"background-color: {HeatmapPlateWidget.COLOR_POSITIVE.name()}; "
            "border: 1px solid #888; border-radius: 3px;"
        )
        legend_row.addWidget(pos_swatch)
        legend_row.addWidget(QLabel("Positive"))
        legend_row.addSpacing(16)

        # Negative swatch
        neg_swatch = QLabel()
        neg_swatch.setFixedSize(16, 16)
        neg_swatch.setStyleSheet(
            f"background-color: {HeatmapPlateWidget.COLOR_NEGATIVE.name()}; "
            "border: 1px solid #888; border-radius: 3px;"
        )
        legend_row.addWidget(neg_swatch)
        legend_row.addWidget(QLabel("Negative"))

        legend_row.addSpacing(16)

        # N/A swatch
        na_swatch = QLabel()
        na_swatch.setFixedSize(16, 16)
        na_swatch.setStyleSheet(
            f"background-color: {HeatmapPlateWidget.COLOR_NA.name()}; "
            "border: 1px solid #888; border-radius: 3px;"
        )
        legend_row.addWidget(na_swatch)
        legend_row.addWidget(QLabel("N/A"))

        legend_row.addStretch()
        layout.addLayout(legend_row)

        # Gradient controls
        grad_group = QGroupBox()
        grad_layout = QHBoxLayout(grad_group)

        self._grad_checkbox = QCheckBox("Ct gradient")
        self._grad_checkbox.setChecked(True)
        grad_layout.addWidget(self._grad_checkbox)

        grad_layout.addSpacing(16)

        # Determine default spin box range from data
        ct_min = self._plate._ct_min
        ct_max = self._plate._ct_max

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self._red_spin = QDoubleSpinBox()
        self._red_spin.setDecimals(1)
        self._red_spin.setRange(0.0, 50.0)
        self._red_spin.setSingleStep(0.5)
        self._red_spin.setValue(ct_min if ct_min is not None else 0.0)
        form.addRow("Red (low Ct):", self._red_spin)

        self._yellow_spin = QDoubleSpinBox()
        self._yellow_spin.setDecimals(1)
        self._yellow_spin.setRange(0.0, 50.0)
        self._yellow_spin.setSingleStep(0.5)
        self._yellow_spin.setValue(ct_max if ct_max is not None else 45.0)
        form.addRow("Yellow (high Ct):", self._yellow_spin)

        grad_layout.addLayout(form)
        grad_layout.addStretch()
        layout.addWidget(grad_group)

        # Gradient legend for positives
        self._legend = GradientLegendWidget()
        self._update_gradient()
        layout.addWidget(self._legend)

        # Connections
        self._grad_checkbox.toggled.connect(self._on_gradient_toggled)
        self._red_spin.valueChanged.connect(self._on_range_changed)
        self._yellow_spin.valueChanged.connect(self._on_range_changed)

    def _on_gradient_toggled(self, checked: bool):
        self._red_spin.setEnabled(checked)
        self._yellow_spin.setEnabled(checked)
        self._plate.set_gradient_enabled(checked)
        self._update_gradient()

    def _on_range_changed(self):
        self._plate.set_gradient_range(self._red_spin.value(), self._yellow_spin.value())
        self._update_gradient()

    def _update_gradient(self):
        if self._grad_checkbox.isChecked():
            self._legend.set_range(self._red_spin.value(), self._yellow_spin.value())
            self._legend.show()
        else:
            self._legend.set_range(None, None)
            self._legend.hide()
