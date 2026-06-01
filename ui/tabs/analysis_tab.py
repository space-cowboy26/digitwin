from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QProgressBar, QScrollArea
from PySide6.QtCore import Qt
from ui.workers.analysis_worker import AnalysisWorker
from ui.widgets.file_collector import FileCollector
from ui.widgets.log_panel import LogPanel

class AnalysisTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
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
        title = QLabel("🔍 Analysis — All Inverters")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #1F2937;")
        layout.addWidget(title)
        
        # description
        desc = QLabel("Upload Inverter Report and WMS Report files to run anomaly detection (1-2 weeks of data).")
        desc.setStyleSheet("font-size: 12px; color: #6B7280; margin-bottom: 8px;")
        layout.addWidget(desc)
        
        self.inv_collector = FileCollector("Inverter Report Files")
        self.wms_collector = FileCollector("WMS Report Files")
        layout.addWidget(self.inv_collector)
        layout.addWidget(self.wms_collector)
        
        self.btn_analyze = QPushButton("Run Analysis")
        self.btn_analyze.clicked.connect(self._on_analyze_clicked)
        self.btn_analyze.setMinimumHeight(40)
        layout.addWidget(self.btn_analyze)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        
        self.log_panel = LogPanel()
        self.log_panel.hide()
        layout.addWidget(self.log_panel)
        
        self.results_area = QWidget()
        self.results_layout = QVBoxLayout(self.results_area)
        layout.addWidget(self.results_area)
        
        # add stretch at end for scrollable layout
        layout.addStretch()
        
        # set content widget to scroll area and add to main layout
        scroll.setWidget(content)
        main_layout.addWidget(scroll)
    
    def _on_analyze_clicked(self):
        inv_files = self.inv_collector.get_files()
        wms_files = self.wms_collector.get_files()
        
        if not inv_files or not wms_files:
            self._show_error("Please select both Inverter and WMS files.")
            return
        
        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Running Analysis...")
        self.progress_bar.show()
        self.log_panel.show()
        self.log_panel.clear()
        
        self.worker = AnalysisWorker(inv_files, wms_files)
        self.worker.log_message.connect(self.log_panel.append_log)
        self.worker.finished.connect(self._on_analyze_complete)
        self.worker.error.connect(self._on_analyze_error)
        self.worker.start()
    
    def _on_analyze_complete(self, results: dict):
        self.progress_bar.hide()
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Run Analysis")
        
        self._clear_results()
        
        if not results:
            self._show_error("Analysis failed - no results returned.")
            return
        
        trained_invs = [inv for inv, r in results.items() if not r.get("skipped") and r.get("passed")]
        
        for itc_inv, r in results.items():
            if r.get("skipped"):
                self.results_layout.addWidget(QLabel(f"⏭ {itc_inv.replace('_', '-')}: Not trained yet"))
            elif not r.get("passed"):
                self.results_layout.addWidget(QLabel(f"❌ {itc_inv.replace('_', '-')}: Failed - {' | '.join(r.get('errors', []))}"))
        
        if trained_invs:
            from ui.widgets.metrics_table import MetricsTable
            table = MetricsTable(results)
            self.results_layout.addWidget(table)
        
        for itc_inv, r in results.items():
            if r.get("passed"):
                if r.get("report"):
                    from ui.widgets.anomaly_table import AnomalyTable
                    table = AnomalyTable(r["report"].get("anomaly_table"))
                    self.results_layout.addWidget(QLabel(f"📊 {itc_inv.replace('_', '-')} Analysis Complete"))
                    self.results_layout.addWidget(table)
    
    def _on_analyze_error(self, error_msg: str):
        self.progress_bar.hide()
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Run Analysis")
        self._show_error(f"Analysis failed: {error_msg}")
    
    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _show_error(self, msg: str):
        self.results_layout.addWidget(QLabel(f"❌ {msg}"))
