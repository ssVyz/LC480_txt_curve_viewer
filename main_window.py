"""Main application window."""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt

from lc480_parser import LC480Data, parse_lc480_file
from plate_map_widget import PlateMapWidget
from sample_table_widget import SampleTableWidget
from curve_viewer_widget import CurveViewerWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LC480 Result Viewer")
        self.resize(1200, 800)

        self._data: LC480Data | None = None
        self._syncing = False

        self._setup_ui()
        self._setup_menu()
        self._connect_signals()
        self.statusBar().showMessage("Ready - Import an LC480 file to begin")

    # -- UI setup ------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Left panel: plate map (top) + sample table (bottom)
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.plate_map = PlateMapWidget()
        self.sample_table = SampleTableWidget()
        left_splitter.addWidget(self.plate_map)
        left_splitter.addWidget(self.sample_table)
        left_splitter.setSizes([300, 500])

        # Right panel: curve viewer
        self.curve_viewer = CurveViewerWidget()

        # Main horizontal splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_splitter)
        main_splitter.addWidget(self.curve_viewer)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setSizes([350, 850])

        main_layout.addWidget(main_splitter)

    def _setup_menu(self):
        file_menu = self.menuBar().addMenu("&File")

        import_act = file_menu.addAction("&Import LC480 File...")
        import_act.setShortcut("Ctrl+O")
        import_act.triggered.connect(self._import_file)

        file_menu.addSeparator()

        exit_act = file_menu.addAction("E&xit")
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)

    def _connect_signals(self):
        self.plate_map.selectionChanged.connect(self._on_plate_selection)
        self.sample_table.selectionChanged.connect(self._on_table_selection)

    # -- File import ---------------------------------------------------------

    def _import_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import LC480 File", "",
            "Text Files (*.txt);;All Files (*)",
        )
        if not filepath:
            return
        try:
            self._data = parse_lc480_file(filepath)
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._on_data_loaded()

    def _on_data_loaded(self):
        d = self._data
        self.setWindowTitle(f"LC480 Result Viewer - {d.experiment_name}")

        # Populate widgets
        self.plate_map.set_data(d.wells, d.sample_names)
        self.sample_table.set_data(d)
        self.curve_viewer.set_data(d)

        # Select all wells by default
        all_wells = set(d.wells)
        self._syncing = True
        self.plate_map.set_selection(all_wells)
        self.sample_table.set_selection(all_wells)
        self.curve_viewer.set_selected_wells(all_wells)
        self._syncing = False

        self._update_status()

    # -- Selection sync ------------------------------------------------------

    def _on_plate_selection(self, wells: set[str]):
        if self._syncing:
            return
        self._syncing = True
        self.sample_table.set_selection(wells)
        self.curve_viewer.set_selected_wells(wells)
        self._syncing = False
        self._update_status()

    def _on_table_selection(self, wells: set[str]):
        if self._syncing:
            return
        self._syncing = True
        self.plate_map.set_selection(wells)
        self.curve_viewer.set_selected_wells(wells)
        self._syncing = False
        self._update_status()

    # -- Helpers -------------------------------------------------------------

    def _update_status(self):
        if not self._data:
            return
        sel = len(self.plate_map.get_selection())
        total = len(self._data.wells)
        self.statusBar().showMessage(
            f"{self._data.experiment_name}  |  "
            f"{sel}/{total} wells selected  |  "
            f"{self._data.num_cycles} cycles  |  "
            f"{len(self._data.channels)} channels"
        )
