# ui/widgets/log_panel.py

from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QColor, QTextCharFormat, QFont

class LogPanel(QTextEdit):
    """
    Read-only scrolling log panel.
    Shows real-time pipeline progress with colour coding.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMinimumHeight(150)
        self.setMaximumHeight(250)
        self.setFont(QFont("Consolas", 10))
        self.setStyleSheet(
            "background-color: #1E1E1E; color: #D4D4D4;"
        )

    def append_log(self, message: str):
        """
        Appends a log line with colour coding.
        Called by worker signal — safe from main thread.
        """
        # colour by log level
        if "ERROR" in message or "failed" in message.lower():
            color = "#F44336"    # red
        elif "WARNING" in message or "blocked" in message.lower():
            color = "#FF9800"    # orange
        elif "complete" in message.lower() or "saved" in message.lower():
            color = "#4CAF50"    # green
        else:
            color = "#D4D4D4"    # default grey

        self.append(f'<span style="color:{color}">{message}</span>')

        # auto scroll to bottom
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().maximum()
        )