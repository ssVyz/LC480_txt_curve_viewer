"""Interactive 96-well plate map widget."""

from PySide6.QtWidgets import QWidget, QMenu, QToolTip
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont


class PlateMapWidget(QWidget):
    """Custom-painted 96-well plate map with interactive selection."""

    selectionChanged = Signal(set)

    ROWS = 8
    COLS = 12
    ROW_LABELS = [chr(ord('A') + i) for i in range(8)]
    COL_LABELS = [str(i + 1) for i in range(12)]
    LABEL_MARGIN = 24
    PADDING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._wells_with_data: set[str] = set()
        self._selected_wells: set[str] = set()
        self._sample_names: dict[str, str] = {}
        self._hovered_well: str | None = None

        # Drag / rubber-band state
        self._drag_start: QPointF | None = None
        self._drag_active: bool = False
        self._drag_current: QPointF | None = None
        self._pre_drag_selection: set[str] = set()

        self.setMouseTracking(True)
        self.setMinimumSize(300, 220)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # -- Public API ----------------------------------------------------------

    def set_data(self, wells: list[str], sample_names: dict[str, str]):
        """Set which wells contain data and their sample names."""
        self._wells_with_data = set(wells)
        self._sample_names = dict(sample_names)
        self.update()

    def set_selection(self, wells: set[str]):
        """Set the current selection (called externally for sync)."""
        if wells != self._selected_wells:
            self._selected_wells = set(wells)
            self.update()

    def get_selection(self) -> set[str]:
        return set(self._selected_wells)

    # -- Geometry helpers ----------------------------------------------------

    def _cell_geometry(self) -> tuple[float, float, float]:
        """Return (cell_size, offset_x, offset_y) for the grid layout."""
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

    def _well_center(self, row: int, col: int) -> tuple[float, float]:
        cell_size, ox, oy = self._cell_geometry()
        return ox + (col + 0.5) * cell_size, oy + (row + 0.5) * cell_size

    def _well_rect(self, row: int, col: int) -> QRectF:
        cell_size, ox, oy = self._cell_geometry()
        d = cell_size * 0.78
        cx, cy = self._well_center(row, col)
        return QRectF(cx - d / 2, cy - d / 2, d, d)

    @staticmethod
    def _rc_to_well(row: int, col: int) -> str:
        return f"{chr(ord('A') + row)}{col + 1}"

    def _well_at_pos(self, pos: QPointF) -> tuple[int, int] | None:
        """Return (row, col) if pos is inside a well circle, else None."""
        cell_size, ox, oy = self._cell_geometry()
        if cell_size <= 0:
            return None
        col = int((pos.x() - ox) / cell_size)
        row = int((pos.y() - oy) / cell_size)
        if 0 <= row < self.ROWS and 0 <= col < self.COLS:
            rect = self._well_rect(row, col)
            c = rect.center()
            dx, dy = pos.x() - c.x(), pos.y() - c.y()
            r = rect.width() / 2
            if dx * dx + dy * dy <= r * r:
                return (row, col)
        return None

    def _row_label_at_pos(self, pos: QPointF) -> int | None:
        cell_size, ox, oy = self._cell_geometry()
        if pos.x() >= ox:
            return None
        for row in range(self.ROWS):
            cy = oy + (row + 0.5) * cell_size
            if abs(pos.y() - cy) < cell_size / 2:
                return row
        return None

    def _col_label_at_pos(self, pos: QPointF) -> int | None:
        cell_size, ox, oy = self._cell_geometry()
        if pos.y() >= oy:
            return None
        for col in range(self.COLS):
            cx = ox + (col + 0.5) * cell_size
            if abs(pos.x() - cx) < cell_size / 2:
                return col
        return None

    # -- Painting ------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        cell_size, ox, oy = self._cell_geometry()
        if cell_size <= 0:
            painter.end()
            return

        # Font scaled to cell size
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
                has_data = well in self._wells_with_data
                is_sel = well in self._selected_wells
                is_hover = well == self._hovered_well

                if not has_data:
                    fill = QColor(220, 220, 220)
                    border = QColor(180, 180, 180)
                    bw = 1.0
                elif is_sel:
                    fill = QColor(0, 0, 0)
                    border = QColor(0, 0, 0)
                    bw = 1.5
                else:
                    fill = QColor(255, 255, 255)
                    border = QColor(0, 0, 0)
                    bw = 1.0

                if is_hover and has_data:
                    border = QColor(80, 80, 80)
                    bw = 2.5

                painter.setPen(QPen(border, bw))
                painter.setBrush(fill)
                painter.drawEllipse(rect)

        # Rubber-band rectangle
        if self._drag_active and self._drag_start and self._drag_current:
            band = QRectF(self._drag_start, self._drag_current).normalized()
            painter.setPen(QPen(QColor(0, 0, 0), 1, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 0, 0, 30))
            painter.drawRect(band)

        painter.end()

    # -- Mouse interaction ---------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position()
            self._drag_active = False
            self._drag_current = None
            self._pre_drag_selection = set(self._selected_wells)

    def mouseMoveEvent(self, event):
        pos = event.position()

        # Hover
        rc = self._well_at_pos(pos)
        new_hover = self._rc_to_well(*rc) if rc else None
        if new_hover != self._hovered_well:
            self._hovered_well = new_hover
            if new_hover and new_hover in self._wells_with_data:
                sample = self._sample_names.get(new_hover, "")
                tip = new_hover
                if sample:
                    tip += f" - {sample}"
                QToolTip.showText(
                    self.mapToGlobal(event.position().toPoint()), tip, self
                )
            else:
                QToolTip.hideText()
            self.update()

        # Rubber-band drag
        if event.buttons() & Qt.MouseButton.LeftButton and self._drag_start:
            if not self._drag_active:
                dx = pos.x() - self._drag_start.x()
                dy = pos.y() - self._drag_start.y()
                if dx * dx + dy * dy > 25:
                    self._drag_active = True

            if self._drag_active:
                self._drag_current = pos
                band = QRectF(self._drag_start, self._drag_current).normalized()
                drag_wells: set[str] = set()
                for r in range(self.ROWS):
                    for c in range(self.COLS):
                        w = self._rc_to_well(r, c)
                        if w in self._wells_with_data:
                            cx, cy = self._well_center(r, c)
                            if band.contains(QPointF(cx, cy)):
                                drag_wells.add(w)

                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._selected_wells = self._pre_drag_selection | drag_wells
                else:
                    self._selected_wells = drag_wells
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._drag_active:
                pos = event.position()

                # Row label click
                row = self._row_label_at_pos(pos)
                if row is not None:
                    row_wells = {
                        self._rc_to_well(row, c)
                        for c in range(self.COLS)
                    } & self._wells_with_data
                    if row_wells and row_wells <= self._selected_wells:
                        self._selected_wells -= row_wells
                    else:
                        self._selected_wells |= row_wells
                    self.selectionChanged.emit(set(self._selected_wells))
                    self.update()
                    self._drag_start = None
                    return

                # Column label click
                col = self._col_label_at_pos(pos)
                if col is not None:
                    col_wells = {
                        self._rc_to_well(r, col)
                        for r in range(self.ROWS)
                    } & self._wells_with_data
                    if col_wells and col_wells <= self._selected_wells:
                        self._selected_wells -= col_wells
                    else:
                        self._selected_wells |= col_wells
                    self.selectionChanged.emit(set(self._selected_wells))
                    self.update()
                    self._drag_start = None
                    return

                # Well click (toggle)
                rc = self._well_at_pos(pos)
                if rc:
                    well = self._rc_to_well(*rc)
                    if well in self._wells_with_data:
                        if well in self._selected_wells:
                            self._selected_wells.discard(well)
                        else:
                            self._selected_wells.add(well)
                        self.selectionChanged.emit(set(self._selected_wells))
                        self.update()
            else:
                # Rubber-band completed
                self.selectionChanged.emit(set(self._selected_wells))

            self._drag_start = None
            self._drag_active = False
            self._drag_current = None
            self.update()

    # -- Keyboard ------------------------------------------------------------

    def keyPressEvent(self, event):
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if event.key() == Qt.Key.Key_A and ctrl:
            self._selected_wells = set(self._wells_with_data)
            self.selectionChanged.emit(set(self._selected_wells))
            self.update()
        elif event.key() == Qt.Key.Key_D and ctrl:
            self._selected_wells = set()
            self.selectionChanged.emit(set(self._selected_wells))
            self.update()
        elif event.key() == Qt.Key.Key_Escape:
            self._selected_wells = set()
            self.selectionChanged.emit(set(self._selected_wells))
            self.update()
        elif event.key() == Qt.Key.Key_I and ctrl:
            self._selected_wells = self._wells_with_data - self._selected_wells
            self.selectionChanged.emit(set(self._selected_wells))
            self.update()
        else:
            super().keyPressEvent(event)

    # -- Context menu --------------------------------------------------------

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        act_all = menu.addAction("Select All")
        act_none = menu.addAction("Deselect All")
        act_inv = menu.addAction("Invert Selection")

        action = menu.exec(self.mapToGlobal(pos))
        if action == act_all:
            self._selected_wells = set(self._wells_with_data)
        elif action == act_none:
            self._selected_wells = set()
        elif action == act_inv:
            self._selected_wells = self._wells_with_data - self._selected_wells
        else:
            return

        self.selectionChanged.emit(set(self._selected_wells))
        self.update()
