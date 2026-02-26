"""Sample list table widget with selection sync."""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt, Signal, QItemSelection, QItemSelectionModel

from lc480_parser import LC480Data


class SampleTableWidget(QWidget):
    """Table showing well positions, sample names, with multi-row selection."""

    selectionChanged = Signal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: LC480Data | None = None
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Well", "Sample Name", "Ct", "Call"])
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

    def set_data(self, data: LC480Data):
        """Populate the table with well and sample name data."""
        self._syncing = True
        self._data = data
        self.table.setRowCount(len(data.wells))
        for i, well in enumerate(data.wells):
            well_item = QTableWidgetItem(well)
            well_item.setFlags(well_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item = QTableWidgetItem(data.sample_names.get(well, ""))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            ct_item = QTableWidgetItem("")
            ct_item.setFlags(ct_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            call_item = QTableWidgetItem("")
            call_item.setFlags(call_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, well_item)
            self.table.setItem(i, 1, name_item)
            self.table.setItem(i, 2, ct_item)
            self.table.setItem(i, 3, call_item)
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)
        self._syncing = False

    def set_selection(self, wells: set[str]):
        """Set selected rows to match the given well set (for external sync)."""
        self._syncing = True
        selection = QItemSelection()
        model = self.table.model()
        last_col = self.table.columnCount() - 1
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item and item.text() in wells:
                selection.select(model.index(i, 0), model.index(i, last_col))
        self.table.selectionModel().select(
            selection, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )
        self._syncing = False

    def set_ct_call(self, ct_data: dict[str, float | None],
                    call_data: dict[str, str]):
        """Update the Ct and Call columns for each well."""
        for i in range(self.table.rowCount()):
            well_item = self.table.item(i, 0)
            if not well_item:
                continue
            well = well_item.text()

            ct_val = ct_data.get(well)
            ct_text = f"{ct_val:.2f}" if ct_val is not None else ""
            ct_item = self.table.item(i, 2)
            if ct_item:
                ct_item.setText(ct_text)

            call_val = call_data.get(well, "")
            call_item = self.table.item(i, 3)
            if call_item:
                call_item.setText(call_val)

        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)

    def _on_selection_changed(self):
        if self._syncing:
            return
        selected_wells: set[str] = set()
        for index in self.table.selectionModel().selectedRows(0):
            item = self.table.item(index.row(), 0)
            if item:
                selected_wells.add(item.text())
        self.selectionChanged.emit(selected_wells)
