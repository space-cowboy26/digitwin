from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from pathlib import Path

class PlotViewer(QWidget):
    """
    Displays Plotly HTML plots in embedded browser tabs.
    No internet required — uses embedded plotlyjs.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

    def load_plots(self, plot_time: Path, plot_gii: Path, plot_anomaly: Path = None):
        self.tabs.clear()
        plots = [
            ("Time vs Power",    plot_time),
            ("GII vs Power",     plot_gii),
            ("Residual Timeline", plot_anomaly),
        ]
        for title, path in plots:
            if path and Path(path).exists():
                view = QWebEngineView()
                view.load(f"file:///{str(path).replace(chr(92), '/')}")
                self.tabs.addTab(view, title)

    def load_static(self, plot_time: Path, plot_gii: Path):
        """For train/retrain static PNG plots."""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtGui import QPixmap
        self.tabs.clear()
        for title, path in [("Time vs Power", plot_time), ("GII vs Power", plot_gii)]:
            if path and Path(path).exists():
                label = QLabel()
                label.setPixmap(QPixmap(str(path)).scaledToWidth(1200))
                self.tabs.addTab(label, title)