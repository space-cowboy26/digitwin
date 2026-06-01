from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QTabWidget
)
from ui.widgets.status_sidebar import StatusSidebar
from ui.tabs.train_tab import TrainTab
from ui.tabs.analysis_tab import AnalysisTab
from ui.tabs.retrain_tab import RetrainTab
from ui.tabs.manual_tab import ManualTab

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Solar Digital Twin")
        self.setMinimumSize(1400, 900)

        central = QWidget()
        layout  = QHBoxLayout(central)

        # sidebar
        self.sidebar = StatusSidebar()
        layout.addWidget(self.sidebar)

        # tabs
        self.tabs = QTabWidget()
        self.train_tab    = TrainTab(self.sidebar)
        self.analysis_tab = AnalysisTab()
        self.retrain_tab  = RetrainTab(self.sidebar)
        self.manual_tab   = ManualTab()

        self.tabs.addTab(self.train_tab,    "🏋️ Train")
        self.tabs.addTab(self.analysis_tab, "🔍 Analysis")
        self.tabs.addTab(self.retrain_tab,  "🔄 Retrain")
        self.tabs.addTab(self.manual_tab,   "📖 Manual")

        layout.addWidget(self.tabs)
        self.setCentralWidget(central)