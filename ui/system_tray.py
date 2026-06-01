# ui/system_tray.py

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QColor
from PySide6.QtCore import QObject

class SystemTray(QObject):
    """
    System tray icon with notification support.
    App stays accessible from tray when minimised.
    """
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window

        # create icon — use a simple coloured square if no icon file
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#FF9800"))   # orange sun colour
        icon = QIcon(pixmap)

        # create tray icon
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Solar Digital Twin")

        # right-click menu
        menu = QMenu()
        action_show  = menu.addAction("Open")
        action_quit  = menu.addAction("Quit")

        action_show.triggered.connect(self._show_window)
        action_quit.triggered.connect(QApplication.quit)

        self.tray.setContextMenu(menu)

        # double-click tray icon to open window
        self.tray.activated.connect(self._on_tray_activated)

        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def _show_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def notify_anomaly(self, itc_inv: str, anomaly_count: int):
        """
        Show a popup notification when anomalies are detected.
        Appears in bottom right corner of screen for 5 seconds.
        """
        self.tray.showMessage(
            "Solar Digital Twin — Anomaly Detected",
            f"{itc_inv.replace('_', '-')}: "
            f"{anomaly_count} anomaly event(s) detected. "
            f"Open the app to review.",
            QSystemTrayIcon.Warning,   # warning icon
            5000,                       # 5 seconds
        )

    def notify_info(self, title: str, message: str):
        """General info notification."""
        self.tray.showMessage(
            title,
            message,
            QSystemTrayIcon.Information,
            3000,
        )

    def notify_retrain_complete(self, itc_inv: str, new_rmse: float, saved: bool):
        """Notify when retrain finishes."""
        if saved:
            self.tray.showMessage(
                "Retrain Complete",
                f"{itc_inv.replace('_','-')} retrained. "
                f"New RMSE: {new_rmse:.1f} kW",
                QSystemTrayIcon.Information,
                3000,
            )
        else:
            self.tray.showMessage(
                "Retrain — Model Not Saved",
                f"{itc_inv.replace('_','-')}: new model was worse. "
                f"Old model kept.",
                QSystemTrayIcon.Warning,
                5000,
            )