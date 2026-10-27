"""Dialog to pick which of several parsed runs to open as plates."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton,
)
from PySide6.QtCore import Qt

from lc480_parser import LC480Data


class RunSelectDialog(QDialog):
    """Checklist of runs, all checked; each checked run opens as a plate."""

    def __init__(self, runs: list[LC480Data], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Runs")
        self.setMinimumWidth(420)
        self._runs = runs

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Found {len(runs)} runs. Select the runs to open as plates:"
        ))

        self._list = QListWidget()
        for i, d in enumerate(runs, 1):
            item = QListWidgetItem(f"{i}. {d.experiment_name} ({len(d.wells)} samples)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._list.addItem(item)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        self._ok = QPushButton("OK")
        self._ok.setDefault(True)
        self._ok.clicked.connect(self.accept)
        btn_row.addWidget(self._ok)
        layout.addLayout(btn_row)

        self._list.itemChanged.connect(
            lambda _: self._ok.setEnabled(bool(self.selected_runs()))
        )

    def selected_runs(self) -> list[LC480Data]:
        return [
            run for i, run in enumerate(self._runs)
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]
