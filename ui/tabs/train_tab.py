# ui/tabs/train_tab.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox,
    QProgressBar, QScrollArea
)
from PySide6.QtCore import Qt
from ui.workers.train_worker import TrainWorker
from ui.widgets.file_collector import FileCollector
from ui.widgets.quality_report import QualityReportWidget
from ui.widgets.plot_viewer import PlotViewer
from ui.widgets.metrics_table import MetricsTable
from ui.widgets.log_panel import LogPanel
class TrainTab(QWidget):

    def __init__(self, sidebar, parent=None):
        super().__init__(parent)
        self.sidebar = sidebar      # reference to sidebar so we can refresh it
        self.worker  = None         # will hold the QThread worker
        self._build_ui()

    def _build_ui(self):
        # main layout for the tab (minimal)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # content widget that goes inside scroll area
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # title
        title = QLabel("🏋️ Train Models — All Inverters")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #1F2937;")
        layout.addWidget(title)

        # description
        desc = QLabel("Upload Inverter Report and WMS Report files to train new models from scratch.")
        desc.setStyleSheet("font-size: 12px; color: #6B7280; margin-bottom: 8px;")
        layout.addWidget(desc)

        # file collectors
        self.inv_collector = FileCollector("Inverter Report Files")
        self.wms_collector = FileCollector("WMS Report Files")
        layout.addWidget(self.inv_collector)
        layout.addWidget(self.wms_collector)

        # settings section
        settings_label = QLabel("Settings")
        settings_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #374151; margin-top: 8px;")
        layout.addWidget(settings_label)

        # checkboxes
        self.chk_overwrite = QCheckBox("Overwrite existing models")
        self.chk_overwrite.setChecked(True)
        self.chk_remove_low = QCheckBox("Remove low-power days")
        self.chk_remove_low.setChecked(True)
        self.chk_remove_osc = QCheckBox("Remove oscillations")
        layout.addWidget(self.chk_overwrite)
        layout.addWidget(self.chk_remove_low)
        layout.addWidget(self.chk_remove_osc)

        # train button
        self.btn_train = QPushButton("Train All")
        self.btn_train.clicked.connect(self._on_train_clicked)
        self.btn_train.setMinimumHeight(40)
        layout.addWidget(self.btn_train)

        # progress bar — hidden until training starts
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # 0,0 = indeterminate spinning
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # log panel — shows real-time pipeline output
        self.log_panel = LogPanel()
        self.log_panel.hide()
        layout.addWidget(self.log_panel)

        # results area — populated after training
        self.results_area = QWidget()
        self.results_layout = QVBoxLayout(self.results_area)
        layout.addWidget(self.results_area)
        
        # add stretch at end for scrollable layout
        layout.addStretch()
        
        # set content widget to scroll area and add to main layout
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def _on_train_clicked(self):
        """Called when operator clicks Train All button."""
        inv_files = self.inv_collector.get_files()
        wms_files = self.wms_collector.get_files()

        if not inv_files or not wms_files:
            self._show_error("Please select both Inverter and WMS files.")
            return

        # disable button so operator cannot click twice
        self.btn_train.setEnabled(False)
        self.btn_train.setText("Training...")

        # show progress
        self.progress_bar.show()
        self.log_panel.show()
        self.log_panel.clear()

        # create worker with all needed parameters
        self.worker = TrainWorker(
            inv_files           = inv_files,
            wms_files           = wms_files,
            overwrite           = self.chk_overwrite.isChecked(),
            remove_faults       = False,
            remove_low_days     = self.chk_remove_low.isChecked(),
            remove_oscillations = self.chk_remove_osc.isChecked(),
        )

        # ── THIS IS THE CONNECT STEP ──────────────────────────────────────
        # wire worker signals to tab methods
        # "when worker fires log_message signal, call self.log_panel.append_log"
        self.worker.log_message.connect(self.log_panel.append_log)

        # "when worker fires finished signal, call self._on_train_complete"
        self.worker.finished.connect(self._on_train_complete)

        # "when worker fires error signal, call self._on_train_error"
        self.worker.error.connect(self._on_train_error)

        # start the worker — this calls worker.run() on a background thread
        self.worker.start()

    def _on_train_complete(self, results: dict):
        """
        Called automatically when worker.finished signal fires.
        results is the dict returned by run_batch_train.
        This runs on the MAIN thread — safe to touch UI here.
        """
        # hide progress, re-enable button
        self.progress_bar.hide()
        self.btn_train.setEnabled(True)
        self.btn_train.setText("Train All")

        # refresh sidebar status badges
        self.sidebar.refresh()

        # clear previous results
        self._clear_results()

        # check for blocked inverters
        blocked = {inv: r for inv, r in results.items() if r.get("blocked")}
        passed  = {inv: r for inv, r in results.items() if r.get("passed")}
        failed  = {inv: r for inv, r in results.items()
                   if not r.get("passed") and not r.get("blocked")
                   and not r.get("skipped")}

        # show quality report if any blocked
        if blocked:
            for itc_inv, r in blocked.items():
                report_widget = QualityReportWidget(r["quality_report"])
                # connect the proceed signal
                # when operator clicks "Proceed with Auto-removal"
                # call self._on_auto_remove with that inverter's result
                report_widget.proceed_signal.connect(
                    lambda low, osc, inv=itc_inv: self._on_auto_remove(
                        inv, low, osc
                    )
                )
                self.results_layout.addWidget(report_widget)

        # show metrics table for trained inverters
        if passed:
            table = MetricsTable(passed)
            self.results_layout.addWidget(table)

            # show plots for first trained inverter
            first = list(passed.values())[0]
            if first.get("plot_time"):
                viewer = PlotViewer()
                viewer.load_static(first["plot_time"], first["plot_gii"])
                self.results_layout.addWidget(viewer)

        # show errors
        for itc_inv, r in failed.items():
            lbl = QLabel(f"❌ {itc_inv}: {' | '.join(r['errors'])}")
            lbl.setStyleSheet("color: red;")
            self.results_layout.addWidget(lbl)

    def _on_train_error(self, error_msg: str):
        """Called if the worker crashes entirely."""
        self.progress_bar.hide()
        self.btn_train.setEnabled(True)
        self.btn_train.setText("Train All")
        self._show_error(f"Training failed: {error_msg}")

    def _on_auto_remove(self, itc_inv: str,
                         remove_low_days: bool,
                         remove_oscillations: bool):
        """
        Called when operator confirms auto-removal.
        Starts a new worker with remove_faults=True.
        """
        inv_files = self.inv_collector.get_files()
        wms_files = self.wms_collector.get_files()

        self.progress_bar.show()
        self.btn_train.setEnabled(False)

        self.worker = TrainWorker(
            inv_files           = inv_files,
            wms_files           = wms_files,
            overwrite           = self.chk_overwrite.isChecked(),
            remove_faults       = True,
            remove_low_days     = remove_low_days,
            remove_oscillations = remove_oscillations,
        )
        self.worker.log_message.connect(self.log_panel.append_log)
        self.worker.finished.connect(self._on_train_complete)
        self.worker.error.connect(self._on_train_error)
        self.worker.start()

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_error(self, msg: str):
        lbl = QLabel(msg)
        lbl.setStyleSheet("color: red; font-weight: bold;")
        self.results_layout.addWidget(lbl)