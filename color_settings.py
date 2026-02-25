"""Color configuration: settings model, dialogs, and widgets."""

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton, QSlider, QColorDialog,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor


# -- Default channel palette (tableau-10) ------------------------------------

DEFAULT_CHANNEL_COLORS: list[QColor] = [
    QColor(31, 119, 180, 180),
    QColor(255, 127, 14, 180),
    QColor(44, 160, 44, 180),
    QColor(214, 39, 40, 180),
    QColor(148, 103, 189, 180),
    QColor(140, 86, 75, 180),
    QColor(227, 119, 194, 180),
    QColor(127, 127, 127, 180),
    QColor(188, 189, 34, 180),
    QColor(23, 190, 207, 180),
]

NUM_CHANNEL_SLOTS = 10


# -- Settings model ----------------------------------------------------------

class ColorSettings:
    """Central store for all colour configuration."""

    def __init__(self):
        self.base_color: QColor = QColor(0, 0, 0, 255)
        self.channel_colors: list[QColor] = [QColor(c) for c in DEFAULT_CHANNEL_COLORS]
        self.sample_colors: dict[str, QColor] = {}
        self.color_mode: str = "Base Color"  # or "Channel Colors"

    def get_curve_color(self, well: str, channel_index: int) -> QColor:
        """Resolve the colour for a given well / channel.

        Priority: sample colour > channel colour (if mode) > base colour.
        """
        if well in self.sample_colors:
            return QColor(self.sample_colors[well])
        if self.color_mode == "Channel Colors":
            idx = min(channel_index, len(self.channel_colors) - 1)
            return QColor(self.channel_colors[idx])
        return QColor(self.base_color)

    def reset_defaults(self):
        self.base_color = QColor(0, 0, 0, 255)
        self.channel_colors = [QColor(c) for c in DEFAULT_CHANNEL_COLORS]


# -- Small reusable widgets --------------------------------------------------

class ColorButton(QPushButton):
    """Clickable swatch that opens a QColorDialog."""

    colorChanged = Signal(QColor)

    def __init__(self, color: QColor = QColor(0, 0, 0), parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(36, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._apply_style()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, c: QColor):
        self._color = QColor(c)
        self._apply_style()

    def _pick(self):
        c = QColorDialog.getColor(
            self._color, self, "Select Color",
            QColorDialog.ColorDialogOption.DontUseNativeDialog,
        )
        if c.isValid():
            self._color = c
            self._apply_style()
            self.colorChanged.emit(c)

    def _apply_style(self):
        self.setStyleSheet(
            f"background-color: {self._color.name()};"
            f"border: 1px solid #888;"
            f"border-radius: 2px;"
        )


class ColorEntryWidget(QWidget):
    """Color button + transparency slider (0–100 %)."""

    changed = Signal()

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.color_btn = ColorButton(QColor(color.red(), color.green(), color.blue()))
        lay.addWidget(self.color_btn)

        lay.addSpacing(6)
        lay.addWidget(QLabel("Transparency:"))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        # Convert alpha (255=opaque) → transparency % (0=opaque)
        self.slider.setValue(round((1 - color.alpha() / 255) * 100))
        self.slider.setFixedWidth(120)
        lay.addWidget(self.slider)

        self.pct_label = QLabel()
        self.pct_label.setFixedWidth(32)
        lay.addWidget(self.pct_label)
        self._update_label()

        self.color_btn.colorChanged.connect(lambda _: self.changed.emit())
        self.slider.valueChanged.connect(self._on_slider)

    def _on_slider(self, _v: int):
        self._update_label()
        self.changed.emit()

    def _update_label(self):
        self.pct_label.setText(f"{self.slider.value()}%")

    def get_color(self) -> QColor:
        """Return the full RGBA colour."""
        c = self.color_btn.color()
        alpha = round(255 * (1 - self.slider.value() / 100))
        return QColor(c.red(), c.green(), c.blue(), alpha)

    def set_color(self, color: QColor):
        self.color_btn.set_color(QColor(color.red(), color.green(), color.blue()))
        self.slider.setValue(round((1 - color.alpha() / 255) * 100))


# -- Dialogs -----------------------------------------------------------------

class ColorSettingsDialog(QDialog):
    """Full colour-settings dialog (base + 10 channel slots)."""

    def __init__(self, settings: ColorSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Color Settings")
        self.setMinimumWidth(460)
        self._settings = settings

        root = QVBoxLayout(self)

        # -- Base colour -----------------------------------------------------
        base_grp = QGroupBox("Base Color")
        base_lay = QHBoxLayout(base_grp)
        self._base_editor = ColorEntryWidget(settings.base_color)
        base_lay.addWidget(self._base_editor)
        base_lay.addStretch()
        root.addWidget(base_grp)

        # -- Channel colours (scrollable) ------------------------------------
        ch_grp = QGroupBox("Channel Colors")
        ch_outer = QVBoxLayout(ch_grp)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_w = QWidget()
        grid = QGridLayout(scroll_w)
        grid.setColumnStretch(1, 1)

        self._ch_editors: list[ColorEntryWidget] = []
        for i in range(NUM_CHANNEL_SLOTS):
            lbl = QLabel(f"Channel {i + 1}:")
            grid.addWidget(lbl, i, 0)
            ed = ColorEntryWidget(settings.channel_colors[i])
            grid.addWidget(ed, i, 1)
            self._ch_editors.append(ed)

        scroll.setWidget(scroll_w)
        ch_outer.addWidget(scroll)
        root.addWidget(ch_grp)

        # -- Buttons ---------------------------------------------------------
        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def _reset(self):
        self._base_editor.set_color(QColor(0, 0, 0, 255))
        for i, c in enumerate(DEFAULT_CHANNEL_COLORS):
            self._ch_editors[i].set_color(c)

    def apply_to(self, settings: ColorSettings):
        """Write editor values back into *settings*."""
        settings.base_color = self._base_editor.get_color()
        settings.channel_colors = [
            ed.get_color() for ed in self._ch_editors
        ]


class SampleColorDialog(QDialog):
    """Simple dialog to pick a colour + transparency for selected wells."""

    def __init__(self, num_wells: int, initial: QColor | None = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            f"Configure Color ({num_wells} well{'s' if num_wells != 1 else ''})"
        )
        layout = QVBoxLayout(self)

        if initial is None:
            initial = QColor(214, 39, 40, 200)
        self._editor = ColorEntryWidget(initial)
        layout.addWidget(self._editor)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

    def get_color(self) -> QColor:
        return self._editor.get_color()
