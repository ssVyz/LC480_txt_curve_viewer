"""Main application window."""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QSplitter,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from lc480_parser import LC480Data, parse_lc480_file
from lcpro_parser import parse_lcpro_file
from plate_map_widget import PlateMapWidget
from sample_table_widget import SampleTableWidget
from curve_viewer_widget import CurveViewerWidget
from color_settings import ColorSettings, ColorSettingsDialog, SampleColorDialog
from baseline import BaselineSettings, BaselineResults, compute_baseline, BaselineSettingsDialog
from color_compensation import (
    ColorCompensationSettings, ColorCompensationDialog, apply_color_compensation,
)
from heatmap_dialog import HeatmapDialog
from LLM.settings_dialog import LLMSettingsDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LC480 Result Viewer")
        self.resize(1200, 800)

        self._data: LC480Data | None = None
        self._syncing = False
        self._color_settings = ColorSettings()
        self._baseline_settings = BaselineSettings()
        self._baseline_results: BaselineResults | None = None
        self._color_comp_settings = ColorCompensationSettings()
        self._inactive_wells: set[str] = set()

        # LLM state (not persisted)
        self._llm_api_key: str = ""
        self._llm_token_limit: int = 500_000
        self._llm_console = None

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

        left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.plate_map = PlateMapWidget()
        self.sample_table = SampleTableWidget()
        left_splitter.addWidget(self.plate_map)
        left_splitter.addWidget(self.sample_table)
        left_splitter.setSizes([300, 500])

        self.curve_viewer = CurveViewerWidget()
        self.curve_viewer.set_color_settings(self._color_settings)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_splitter)
        main_splitter.addWidget(self.curve_viewer)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)
        main_splitter.setSizes([350, 850])

        main_layout.addWidget(main_splitter)

    def _setup_menu(self):
        # File menu
        file_menu = self.menuBar().addMenu("&File")
        import_act = file_menu.addAction("&Import LC480 File...")
        import_act.setShortcut("Ctrl+O")
        import_act.triggered.connect(self._import_file)
        import_pro_act = file_menu.addAction("Import LC-&Pro File...")
        import_pro_act.triggered.connect(self._import_lcpro_file)
        export_act = file_menu.addAction("&Export Results as CSV...")
        export_act.setShortcut("Ctrl+S")
        export_act.triggered.connect(self._export_csv)
        file_menu.addSeparator()
        exit_act = file_menu.addAction("E&xit")
        exit_act.setShortcut("Ctrl+Q")
        exit_act.triggered.connect(self.close)

        # Settings menu
        settings_menu = self.menuBar().addMenu("&Settings")
        colors_act = settings_menu.addAction("&Colors...")
        colors_act.triggered.connect(self._open_color_settings)
        baseline_act = settings_menu.addAction("&Baseline...")
        baseline_act.triggered.connect(self._open_baseline_settings)
        color_comp_act = settings_menu.addAction("Color &Compensation...")
        color_comp_act.triggered.connect(self._open_color_compensation)

        # View menu
        view_menu = self.menuBar().addMenu("&View")
        heatmap_act = view_menu.addAction("&Heatmap")
        heatmap_act.triggered.connect(self._open_heatmap)

        # LLM menu
        llm_menu = self.menuBar().addMenu("&LLM")
        llm_settings_act = llm_menu.addAction("&Settings...")
        llm_settings_act.triggered.connect(self._open_llm_settings)
        llm_console_act = llm_menu.addAction("Open &Console")
        llm_console_act.triggered.connect(self._open_llm_console)

    def _connect_signals(self):
        self.plate_map.selectionChanged.connect(self._on_plate_selection)
        self.plate_map.configureColorRequested.connect(self._on_configure_color)
        self.plate_map.clearColorRequested.connect(self._on_clear_color)
        self.plate_map.inactivateRequested.connect(self._on_inactivate_wells)
        self.plate_map.reactivateRequested.connect(self._on_reactivate_wells)
        self.sample_table.selectionChanged.connect(self._on_table_selection)
        self.curve_viewer.channel_selector.checkedItemsChanged.connect(
            lambda _: self._update_table_ct_call()
        )

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

    def _import_lcpro_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import LC-Pro File", "",
            "XML Files (*.xml);;All Files (*)",
        )
        if not filepath:
            return
        try:
            self._data = parse_lcpro_file(filepath)
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._on_data_loaded()

    def _on_data_loaded(self):
        d = self._data
        self.setWindowTitle(f"LC480 Result Viewer - {d.experiment_name}")

        self._inactive_wells = set()
        self.plate_map.set_data(d.wells, d.sample_names)
        self.sample_table.set_data(d)
        self.curve_viewer.set_data(d)

        all_wells = set(d.wells)
        self._syncing = True
        self.plate_map.set_selection(all_wells)
        self.sample_table.set_selection(all_wells)
        self.curve_viewer.set_selected_wells(all_wells)
        self._syncing = False

        self._push_colors()
        self._push_inactive()
        self._recompute_baseline()
        self._update_status()

    # -- File export ---------------------------------------------------------

    def _export_csv(self):
        if not self._data:
            QMessageBox.information(self, "Export", "No data loaded.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Results as CSV", "",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not filepath:
            return

        import csv

        # Read current table contents (mirrors what the user sees)
        table = self.sample_table.table
        headers = []
        for col in range(table.columnCount()):
            headers.append(table.horizontalHeaderItem(col).text())

        rows = []
        for row in range(table.rowCount()):
            row_data = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                row_data.append(item.text() if item else "")
            rows.append(row_data)

        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as exc:
            QMessageBox.critical(self, "Export Error", str(exc))
            return

        self.statusBar().showMessage(f"Exported {len(rows)} rows to {filepath}")

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

    # -- Colour management ---------------------------------------------------

    def _push_colors(self):
        """Push current colour settings to all widgets that need them."""
        self.plate_map.set_sample_colors(self._color_settings.sample_colors)
        self.curve_viewer.set_color_settings(self._color_settings)

    def _open_color_settings(self):
        dlg = ColorSettingsDialog(self._color_settings, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            dlg.apply_to(self._color_settings)
            self._push_colors()

    def _on_configure_color(self, wells: set[str]):
        # Use existing colour of first well as initial, if any
        first = next(iter(wells))
        initial = self._color_settings.sample_colors.get(first)
        dlg = SampleColorDialog(len(wells), initial=initial, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            c = dlg.get_color()
            for w in wells:
                self._color_settings.sample_colors[w] = QColor(c)
            self._push_colors()

    def _on_clear_color(self, wells: set[str]):
        changed = False
        for w in wells:
            if w in self._color_settings.sample_colors:
                del self._color_settings.sample_colors[w]
                changed = True
        if changed:
            self._push_colors()

    # -- Well activation management ------------------------------------------

    def _push_inactive(self):
        """Push inactive well state to all widgets."""
        self.plate_map.set_inactive_wells(self._inactive_wells)
        self.curve_viewer.set_inactive_wells(self._inactive_wells)
        self.sample_table.set_inactive_wells(self._inactive_wells)

    def _on_inactivate_wells(self, wells: set[str]):
        self._inactive_wells |= wells
        self._push_inactive()

    def _on_reactivate_wells(self, wells: set[str]):
        self._inactive_wells -= wells
        self._push_inactive()

    # -- Baseline management -------------------------------------------------

    def _open_baseline_settings(self):
        num_cycles = self._data.num_cycles if self._data else 45
        dlg = BaselineSettingsDialog(
            self._baseline_settings, num_cycles=num_cycles, parent=self
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            dlg.apply_to(self._baseline_settings)
            self._recompute_baseline()

    def _open_color_compensation(self):
        channels = self._data.channels if self._data else []
        dlg = ColorCompensationDialog(
            self._color_comp_settings, channels=channels, parent=self
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            dlg.apply_to(self._color_comp_settings)
            self._recompute_baseline()

    def _recompute_baseline(self):
        """Recompute baseline results and push to all widgets."""
        if not self._data:
            return
        self._baseline_results = compute_baseline(
            self._data, self._baseline_settings
        )
        # Apply color compensation (modifies divided data + recalculates Ct/Call)
        self._baseline_results = apply_color_compensation(
            self._baseline_results, self._color_comp_settings,
            self._baseline_settings, self._data.wells, self._data.channels,
        )
        self.curve_viewer.set_baseline_results(self._baseline_results)
        self._update_table_ct_call()

    def _update_table_ct_call(self):
        """Update sample table Ct/Call/RFI columns for the first checked channel."""
        if not self._baseline_results or not self._data:
            self.sample_table.set_ct_call({}, {})
            return

        checked = self.curve_viewer.channel_selector.checked_items()
        if not checked:
            self.sample_table.set_ct_call({}, {})
            return

        first_channel = checked[0]
        ct_data: dict[str, float | None] = {}
        call_data: dict[str, str] = {}
        rfi_data: dict[str, float | None] = {}
        for well in self._data.wells:
            ct_data[well] = self._baseline_results.ct.get(well, {}).get(first_channel)
            call_data[well] = self._baseline_results.call.get(well, {}).get(first_channel, "N/A")
            rfi_data[well] = self._baseline_results.endpoint_rfi.get(well, {}).get(first_channel)

        self.sample_table.set_ct_call(ct_data, call_data, rfi_data)

    # -- View dialogs --------------------------------------------------------

    def _open_heatmap(self):
        if not self._data or not self._baseline_results:
            QMessageBox.information(self, "Heatmap", "No data loaded.")
            return

        checked = self.curve_viewer.channel_selector.checked_items()
        if not checked:
            QMessageBox.information(self, "Heatmap", "No channel selected.")
            return

        first_channel = checked[0]
        ct_data: dict[str, float | None] = {}
        call_data: dict[str, str] = {}
        for well in self._data.wells:
            ct_data[well] = self._baseline_results.ct.get(well, {}).get(first_channel)
            call_data[well] = self._baseline_results.call.get(well, {}).get(first_channel, "N/A")

        dlg = HeatmapDialog(
            self._data.wells, self._data.sample_names,
            call_data, ct_data, channel=first_channel,
            inactive_wells=self._inactive_wells, parent=self,
        )
        dlg.exec()

    # -- LLM ----------------------------------------------------------------

    def _open_llm_settings(self):
        dlg = LLMSettingsDialog(
            api_key=self._llm_api_key,
            token_limit=self._llm_token_limit,
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._llm_api_key = dlg.get_api_key()
            self._llm_token_limit = dlg.get_token_limit()

    def _open_llm_console(self):
        if self._llm_console is not None:
            self._llm_console.activateWindow()
            self._llm_console.raise_()
            return

        if not self._llm_api_key:
            QMessageBox.information(
                self, "LLM Console",
                "Please configure your API key first via LLM > Settings.",
            )
            return

        from LLM.console_window import LLMConsoleWindow

        self._llm_console = LLMConsoleWindow(
            self, self._llm_api_key, self._llm_token_limit
        )
        self._llm_console.closed.connect(self._on_llm_console_closed)
        self._llm_console.show()

    def _on_llm_console_closed(self):
        self._llm_console = None

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
