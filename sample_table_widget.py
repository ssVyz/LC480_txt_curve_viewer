"""Sample list table widget with selection sync."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt, Signal, QItemSelection, QItemSelectionModel
from PySide6.QtGui import QColor

from lc480_parser import LC480Data
from plate_set import split_well_key

# Column indices; the Plate column is only shown with several plates open
COL_PLATE, COL_WELL, COL_NAME, COL_CT, COL_CALL, COL_RFI = range(6)


class SampleTableWidget(QWidget):
    """Table showing well positions, sample names, with multi-row selection.

    Rows are identified by well key (see plate_set.py), stored on the Well item.
    """

    selectionChanged = Signal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: LC480Data | None = None
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["Plate", "Well", "Sample Name", "Ct", "Call", "Endpoint RFI"]
        )
        self.table.setColumnHidden(COL_PLATE, True)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.MultiSelection
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        self.table.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

    def set_data(self, data: LC480Data, plate_names: list[str] | None = None):
        """Populate the table with well and sample name data.

        *plate_names* is given when several plates are open (wells keyed
        'P<n>:<well>'); it shows the Plate column.
        """
        self._syncing = True
        self._data = data
        self.table.setColumnHidden(COL_PLATE, plate_names is None)
        self.table.setRowCount(len(data.wells))
        for i, key in enumerate(data.wells):
            plate_no, well = split_well_key(key) if plate_names else (1, key)
            plate_item = QTableWidgetItem(str(plate_no) if plate_names else "")
            plate_item.setFlags(plate_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if plate_names:
                plate_item.setToolTip(plate_names[plate_no - 1])
            well_item = QTableWidgetItem(well)
            well_item.setFlags(well_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            well_item.setData(Qt.ItemDataRole.UserRole, key)
            name_item = QTableWidgetItem(data.sample_names.get(key, ""))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            ct_item = QTableWidgetItem("")
            ct_item.setFlags(ct_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            call_item = QTableWidgetItem("")
            call_item.setFlags(call_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            rfi_item = QTableWidgetItem("")
            rfi_item.setFlags(rfi_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, COL_PLATE, plate_item)
            self.table.setItem(i, COL_WELL, well_item)
            self.table.setItem(i, COL_NAME, name_item)
            self.table.setItem(i, COL_CT, ct_item)
            self.table.setItem(i, COL_CALL, call_item)
            self.table.setItem(i, COL_RFI, rfi_item)
        self.table.resizeColumnToContents(COL_PLATE)
        self.table.resizeColumnToContents(COL_WELL)
        self.table.resizeColumnToContents(COL_CT)
        self.table.resizeColumnToContents(COL_CALL)
        self.table.resizeColumnToContents(COL_RFI)
        self._syncing = False

    def row_key(self, row: int) -> str | None:
        """Well key of a table row."""
        item = self.table.item(row, COL_WELL)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def set_selection(self, wells: set[str]):
        """Set selected rows to match the given well set (for external sync)."""
        self._syncing = True
        selection = QItemSelection()
        model = self.table.model()
        last_col = self.table.columnCount() - 1
        for i in range(self.table.rowCount()):
            if self.row_key(i) in wells:
                selection.select(model.index(i, 0), model.index(i, last_col))
        self.table.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        self._syncing = False

    def set_ct_call(self, ct_data: dict[str, float | None],
                    call_data: dict[str, str],
                    rfi_data: dict[str, float | None] | None = None):
        """Update the Ct, Call, and Endpoint RFI columns for each well."""
        for i in range(self.table.rowCount()):
            well = self.row_key(i)
            if well is None:
                continue

            ct_val = ct_data.get(well)
            ct_text = f"{ct_val:.2f}" if ct_val is not None else ""
            ct_item = self.table.item(i, COL_CT)
            if ct_item:
                ct_item.setText(ct_text)

            call_val = call_data.get(well, "")
            call_item = self.table.item(i, COL_CALL)
            if call_item:
                call_item.setText(call_val)

            if rfi_data is not None:
                rfi_val = rfi_data.get(well)
                rfi_text = f"{rfi_val:.3f}" if rfi_val is not None else ""
                rfi_item = self.table.item(i, COL_RFI)
                if rfi_item:
                    rfi_item.setText(rfi_text)

        self.table.resizeColumnToContents(COL_CT)
        self.table.resizeColumnToContents(COL_CALL)
        self.table.resizeColumnToContents(COL_RFI)

    def set_inactive_wells(self, wells: set[str]):
        """Grey out rows for inactive wells."""
        inactive_fg = QColor(180, 180, 180)
        normal_fg = QColor(0, 0, 0)
        for i in range(self.table.rowCount()):
            well = self.row_key(i)
            if well is None:
                continue
            fg = inactive_fg if well in wells else normal_fg
            for col in range(self.table.columnCount()):
                item = self.table.item(i, col)
                if item:
                    item.setForeground(fg)

    def _on_selection_changed(self):
        if self._syncing:
            return
        selected_wells: set[str] = set()
        for index in self.table.selectionModel().selectedRows(0):
            well = self.row_key(index.row())
            if well is not None:
                selected_wells.add(well)
        self.selectionChanged.emit(selected_wells)
