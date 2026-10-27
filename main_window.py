"""Main application window."""

from dataclasses import replace

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QFileDialog, QMessageBox, QLabel, QComboBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from lc480_parser import LC480Data, parse_lc480_file
from lcpro_parser import parse_lcpro_file
from cobas_parser import parse_cobas_files
from cobas5800_parser import parse_cobas5800_files
from plate_set import combine_plates, split_well_key, well_key
from run_select_dialog import RunSelectDialog
from plate_map_widget import PlateMapWidget
from sample_table_widget import SampleTableWidget
from curve_viewer_widget import CurveViewerWidget
from color_settings import ColorSettings, ColorSettingsDialog, SampleColorDialog
from baseline import BaselineSettings, BaselineResults, compute_baseline, BaselineSettingsDialog
from color_compensation import (
    ColorCompensationSettings, ColorCompensationDialog, apply_color_compensation,
)
from heatmap_dialog import HeatmapDialog
from plate_setup import (
    PlateSetup, FILE_FILTER as PLATE_FILE_FILTER,
    save_plate_setup, load_plate_setup,
)
from LLM.settings_dialog import LLMSettingsDialog
from LLM.env_store import load_api_key, save_api_key, clear_api_key


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LC480 Result Viewer")
        self.resize(1200, 800)

        self._data: LC480Data | None = None
        # Open plates (several only for cobas runs); _data combines them, with
        # wells keyed 'P<n>:<well>' when there are several (see plate_set.py)
        self._plates: list[LC480Data] = []
        self._current_plate = 0  # index of the plate shown in the plate map
        self._selection: set[str] = set()
        self._syncing = False
        self._color_settings = ColorSettings()
        self._baseline_settings = BaselineSettings()
        self._baseline_results: BaselineResults | None = None
        self._color_comp_settings = ColorCompensationSettings()
        self._inactive_wells: set[str] = set()

        # LLM state (api key optionally persisted via .env)
        self._llm_api_key: str = load_api_key()
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

        # Plate picker above the plate map, shown only with several plates open
        plate_panel = QWidget()
        plate_layout = QVBoxLayout(plate_panel)
        plate_layout.setContentsMargins(0, 0, 0, 0)
        self.plate_picker = QWidget()
        picker_layout = QHBoxLayout(self.plate_picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        picker_layout.addWidget(QLabel("Plate:"))
        self.plate_combo = QComboBox()
        self.plate_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.plate_combo.setMinimumContentsLength(20)
        picker_layout.addWidget(self.plate_combo, 1)
        self.plate_picker.hide()
        plate_layout.addWidget(self.plate_picker)
        self.plate_map = PlateMapWidget()
        plate_layout.addWidget(self.plate_map)

        self.sample_table = SampleTableWidget()
        left_splitter.addWidget(plate_panel)
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
        import_cobas_act = file_menu.addAction("Import &cobas 6800/8800 Files...")
        import_cobas_act.triggered.connect(self._import_cobas_file)
        import_c5800_act = file_menu.addAction("Import cobas &5800 Results...")
        import_c5800_act.triggered.connect(self._import_cobas5800_files)
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
        view_menu.addSeparator()
        save_plate_act = view_menu.addAction("&Save Plate...")
        save_plate_act.triggered.connect(self._save_plate)
        load_plate_act = view_menu.addAction("&Load Plate...")
        load_plate_act.triggered.connect(self._load_plate)
        reset_plate_act = view_menu.addAction("&Reset Plate View...")
        reset_plate_act.triggered.connect(self._reset_plate_view)

        # LLM menu
        llm_menu = self.menuBar().addMenu("&LLM")
        llm_settings_act = llm_menu.addAction("&Settings...")
        llm_settings_act.triggered.connect(self._open_llm_settings)
        llm_console_act = llm_menu.addAction("Open &Console")
        llm_console_act.triggered.connect(self._open_llm_console)

    def _connect_signals(self):
        self.plate_combo.currentIndexChanged.connect(self._on_plate_switched)
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
            data = parse_lc480_file(filepath)
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._load_plates([data])

    def _import_lcpro_file(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import LC-Pro File", "",
            "XML Files (*.xml);;All Files (*)",
        )
        if not filepath:
            return
        try:
            data = parse_lcpro_file(filepath)
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._load_plates([data])

    def _import_cobas_file(self):
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Import cobas 6800/8800 Files", "",
            "XML Files (*.xml);;All Files (*)",
        )
        if not filepaths:
            return
        try:
            runs = parse_cobas_files(filepaths)
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._load_runs(runs)

    def _import_cobas5800_files(self):
        # The export is a zip of one XML per sample; unpacked XMLs work too
        filepaths, _ = QFileDialog.getOpenFileNames(
            self, "Import cobas 5800 Results", "",
            "cobas 5800 Results (*.zip *.xml);;All Files (*)",
        )
        if not filepaths:
            return
        try:
            runs = parse_cobas5800_files(filepaths)
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._load_runs(runs)

    def _load_runs(self, runs: list[LC480Data]):
        """Open the parsed runs as plates, asking which if there are several."""
        if len(runs) > 1:
            dlg = RunSelectDialog(runs, parent=self)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            runs = dlg.selected_runs()
        self._load_plates(runs)

    def _load_plates(self, plates: list[LC480Data]):
        """Replace the open plates (LC480 and LC Pro files are one plate)."""
        try:
            data = combine_plates(plates)
        except ValueError as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
            return
        self._rekey_wells(len(plates))
        self._plates = plates
        self._current_plate = 0
        self._data = data
        self._on_data_loaded()

    def _rekey_wells(self, plate_count: int):
        """Carry well colors and inactive wells over to a new set of plates by
        plate position (plate 1 to plate 1, ...); a single plate uses plain names."""
        def rekey(key: str) -> str | None:
            plate_no, well = split_well_key(key)
            if plate_no > plate_count:
                return None
            return well if plate_count == 1 else well_key(plate_no, well)

        colors = self._color_settings.sample_colors
        rekeyed = {k: c for key, c in colors.items() if (k := rekey(key)) is not None}
        colors.clear()
        colors.update(rekeyed)
        self._inactive_wells = {
            k for key in self._inactive_wells if (k := rekey(key)) is not None
        }

    def _on_data_loaded(self):
        d = self._data
        self.setWindowTitle(f"LC480 Result Viewer - {d.experiment_name}")

        multi = len(self._plates) > 1
        self.plate_combo.blockSignals(True)
        self.plate_combo.clear()
        if multi:
            self.plate_combo.addItems([
                f"{i}. {p.experiment_name} ({len(p.wells)} samples)"
                for i, p in enumerate(self._plates, 1)
            ])
        self.plate_combo.blockSignals(False)
        self.plate_picker.setVisible(multi)

        # Well colors, inactive wells and baseline settings carry over between
        # files; View > Reset Plate View returns them to defaults.
        self.sample_table.set_data(
            d, [p.experiment_name for p in self._plates] if multi else None
        )
        self.curve_viewer.set_data(d)
        self._set_selection(set(d.wells))
        self._show_plate()

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
        columns = [c for c in range(table.columnCount()) if not table.isColumnHidden(c)]
        headers = []
        for col in columns:
            headers.append(table.horizontalHeaderItem(col).text())

        # Baseline end actually used (adaptive end may shorten it per well),
        # for the same channel as the table's Ct/Call columns
        checked = self.curve_viewer.channel_selector.checked_items()
        ends: dict[str, int | None] = {}
        if checked and self._baseline_results:
            ends = {w: by_ch.get(checked[0])
                    for w, by_ch in self._baseline_results.baseline_end.items()}
        headers.append("Baseline End")

        rows = []
        for row in range(table.rowCount()):
            row_data = []
            for col in columns:
                item = table.item(row, col)
                row_data.append(item.text() if item else "")
            end = ends.get(self.sample_table.row_key(row))
            row_data.append(str(end) if end is not None else "")
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

    def _set_selection(self, wells: set[str]):
        """Select wells (keys, on all plates) in every widget."""
        self._selection = set(wells)
        self._syncing = True
        self.plate_map.set_selection(self._on_plate(wells))
        self.sample_table.set_selection(wells)
        self.curve_viewer.set_selected_wells(wells)
        self._syncing = False

    def _on_plate_selection(self, wells: set[str]):
        if self._syncing:
            return
        # The plate map shows one plate; the other plates keep their selection
        self._selection = (
            {k for k in self._selection if not self._is_on_plate(k)}
            | self._plate_keys(wells)
        )
        self._syncing = True
        self.sample_table.set_selection(self._selection)
        self.curve_viewer.set_selected_wells(self._selection)
        self._syncing = False
        self._update_status()

    def _on_table_selection(self, wells: set[str]):
        if self._syncing:
            return
        self._selection = set(wells)
        self._syncing = True
        self.plate_map.set_selection(self._on_plate(wells))
        self.curve_viewer.set_selected_wells(wells)
        self._syncing = False
        self._update_status()

    # -- Plates --------------------------------------------------------------
    # The plate map shows one plate and works with plain well names ('A1');
    # with several plates open, everything else uses keys like 'P2:A1'.

    def _on_plate_switched(self, index: int):
        if index < 0:
            return
        self._current_plate = index
        self._show_plate()
        self._update_status()

    def _show_plate(self):
        """Show the displayed plate with its selection, colors and inactive wells."""
        p = self._plates[self._current_plate]
        self.plate_map.set_data(p.wells, p.sample_names, p.plate_rows, p.plate_cols)
        self.plate_map.set_selection(self._on_plate(self._selection))
        self.plate_map.set_sample_colors(self._plate_colors())
        self.plate_map.set_inactive_wells(self._on_plate(self._inactive_wells))

    def _is_on_plate(self, key: str) -> bool:
        """Whether a well key belongs to the displayed plate."""
        return (len(self._plates) <= 1
                or split_well_key(key)[0] == self._current_plate + 1)

    def _plate_well(self, key: str) -> str:
        return key if len(self._plates) <= 1 else split_well_key(key)[1]

    def _plate_key(self, well: str) -> str:
        if len(self._plates) <= 1:
            return well
        return well_key(self._current_plate + 1, well)

    def _on_plate(self, keys) -> set[str]:
        """Well names of the keys that are on the displayed plate."""
        return {self._plate_well(k) for k in keys if self._is_on_plate(k)}

    def _plate_keys(self, wells) -> set[str]:
        """Keys of wells on the displayed plate."""
        return {self._plate_key(w) for w in wells}

    def _plate_colors(self) -> dict[str, QColor]:
        """Custom colors of the displayed plate's wells, by well name."""
        return {
            self._plate_well(k): c
            for k, c in self._color_settings.sample_colors.items()
            if self._is_on_plate(k)
        }

    # -- Colour management ---------------------------------------------------

    def _push_colors(self):
        """Push current colour settings to all widgets that need them."""
        self.plate_map.set_sample_colors(self._plate_colors())
        self.curve_viewer.set_color_settings(self._color_settings)

    def _open_color_settings(self):
        dlg = ColorSettingsDialog(self._color_settings, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            dlg.apply_to(self._color_settings)
            self._push_colors()

    def _on_configure_color(self, wells: set[str]):
        wells = self._plate_keys(wells)
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
        for w in self._plate_keys(wells):
            if w in self._color_settings.sample_colors:
                del self._color_settings.sample_colors[w]
                changed = True
        if changed:
            self._push_colors()

    # -- Well activation management ------------------------------------------

    def _push_inactive(self):
        """Push inactive well state to all widgets."""
        self.plate_map.set_inactive_wells(self._on_plate(self._inactive_wells))
        self.curve_viewer.set_inactive_wells(self._inactive_wells)
        self.sample_table.set_inactive_wells(self._inactive_wells)

    # Plate map context menu actions (wells of the displayed plate)

    def _on_inactivate_wells(self, wells: set[str]):
        self._inactive_wells |= self._plate_keys(wells)
        self._push_inactive()

    def _on_reactivate_wells(self, wells: set[str]):
        self._inactive_wells -= self._plate_keys(wells)
        self._push_inactive()

    # -- Plate setup save / load ---------------------------------------------

    def _save_plate(self):
        if not self._data:
            QMessageBox.information(self, "Save Plate", "No data loaded.")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Plate Setup", "", PLATE_FILE_FILTER,
        )
        if not filepath:
            return
        if not filepath.lower().endswith(".plate"):
            filepath += ".plate"

        # With several plates open, only the displayed one is saved
        plate = self._plates[self._current_plate]
        setup = PlateSetup(
            well_colors=self._plate_colors(),
            inactive_wells=self._on_plate(self._inactive_wells),
            baseline=replace(self._baseline_settings),
        )
        try:
            save_plate_setup(filepath, setup, plate.experiment_name)
        except OSError as exc:
            QMessageBox.critical(self, "Save Error", str(exc))
            return

        self.statusBar().showMessage(f"Saved plate setup to {filepath}")

    def _load_plate(self):
        if not self._data:
            QMessageBox.information(self, "Load Plate", "No data loaded.")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Plate Setup", "",
            f"{PLATE_FILE_FILTER};;All Files (*)",
        )
        if not filepath:
            return
        try:
            setup = load_plate_setup(filepath)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return

        # Replace (not merge) so the saved configuration is reproduced exactly;
        # files without baseline settings fall back to the defaults. With
        # several plates open, it replaces the displayed plate's wells only.
        baseline = setup.baseline or BaselineSettings()
        clamped = baseline.clamp_to_cycles(self._data.num_cycles)
        colors = {
            k: c for k, c in self._color_settings.sample_colors.items()
            if not self._is_on_plate(k)
        }
        colors.update({self._plate_key(w): c for w, c in setup.well_colors.items()})
        inactive = (
            {k for k in self._inactive_wells if not self._is_on_plate(k)}
            | self._plate_keys(setup.inactive_wells)
        )
        self._apply_plate_state(colors, inactive, baseline)

        plate = self._plates[self._current_plate]
        target = f" to plate {self._current_plate + 1}" if len(self._plates) > 1 else ""
        msg = (
            f"Loaded plate setup from {filepath}{target}: "
            f"{len(setup.well_colors)} colored, "
            f"{len(setup.inactive_wells)} inactive wells"
        )
        unmatched = (
            (setup.well_colors.keys() | setup.inactive_wells) - set(plate.wells)
        )
        if unmatched:
            msg += f" ({len(unmatched)} not in current data)"
        if setup.baseline is None:
            msg += "; no baseline settings in file, using defaults"
        elif clamped:
            msg += f"; baseline region adjusted to {self._data.num_cycles} cycles"
        self.statusBar().showMessage(msg)

    def _reset_plate_view(self):
        all_plates = " on all plates" if len(self._plates) > 1 else ""
        answer = QMessageBox.question(
            self, "Reset Plate View",
            f"Reset well colors, inactive wells{all_plates} and baseline settings to defaults?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._apply_plate_state({}, set(), BaselineSettings())
        self.statusBar().showMessage("Plate view reset to defaults")

    def _apply_plate_state(self, well_colors: dict[str, QColor],
                           inactive_wells: set[str],
                           baseline: BaselineSettings):
        """Replace well colors, inactive wells and baseline settings."""
        self._color_settings.sample_colors.clear()
        self._color_settings.sample_colors.update(well_colors)
        self._inactive_wells = set(inactive_wells)
        self._baseline_settings = baseline
        self._push_colors()
        self._push_inactive()
        self._recompute_baseline()

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

        # The heatmap shows the displayed plate
        plate = self._plates[self._current_plate]
        first_channel = checked[0]
        ct_data: dict[str, float | None] = {}
        call_data: dict[str, str] = {}
        for well in plate.wells:
            key = self._plate_key(well)
            ct_data[well] = self._baseline_results.ct.get(key, {}).get(first_channel)
            call_data[well] = self._baseline_results.call.get(key, {}).get(first_channel, "N/A")

        dlg = HeatmapDialog(
            plate.wells, plate.sample_names,
            call_data, ct_data, channel=first_channel,
            inactive_wells=self._on_plate(self._inactive_wells),
            plate_size=(plate.plate_rows, plate.plate_cols),
            plate_name=plate.experiment_name if len(self._plates) > 1 else "",
            parent=self,
        )
        dlg.exec()

    # -- LLM ----------------------------------------------------------------

    def _open_llm_settings(self):
        stored_key = load_api_key()
        dlg = LLMSettingsDialog(
            api_key=self._llm_api_key,
            token_limit=self._llm_token_limit,
            store_locally=bool(stored_key),
            parent=self,
        )
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._llm_api_key = dlg.get_api_key()
            self._llm_token_limit = dlg.get_token_limit()
            if dlg.get_store_locally() and self._llm_api_key:
                save_api_key(self._llm_api_key)
            elif stored_key:
                clear_api_key()

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
        plate = self._plates[self._current_plate]
        name = plate.experiment_name
        sel = len(self.plate_map.get_selection())
        selected = f"{sel}/{len(plate.wells)} wells selected"
        if len(self._plates) > 1:
            name = f"Plate {self._current_plate + 1}/{len(self._plates)}: {name}"
            selected += f" ({len(self._selection)}/{len(self._data.wells)} on all plates)"
        self.statusBar().showMessage(
            f"{name}  |  "
            f"{selected}  |  "
            f"{self._data.num_cycles} cycles  |  "
            f"{len(self._data.channels)} channels"
        )
