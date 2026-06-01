from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QTableWidget, QTableWidgetItem,
    QGroupBox, QPushButton, QCheckBox
)

class QualityReportWidget(QWidget):
    """
    Displays data quality issues with collapsible detail sections.
    Emits proceed_signal when operator confirms auto-removal.
    """
    from PySide6.QtCore import Signal
    proceed_signal = Signal(bool, bool)  # remove_low_days, remove_oscillations

    def __init__(self, quality: dict, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        # header
        header = QLabel(f"⚠️ {quality['message']}")
        header.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(header)

        # one group box per issue type
        for issue in quality["issues"]:
            group = QGroupBox(
                f"{issue['type']} — {issue['count']} rows | {issue['date_range']}"
            )
            g_layout = QVBoxLayout(group)
            g_layout.addWidget(QLabel(issue["description"]))

            # sample table
            table = QTableWidget()
            sample = issue["sample"]
            if sample:
                table.setColumnCount(len(sample[0]))
                table.setHorizontalHeaderLabels(list(sample[0].keys()))
                table.setRowCount(len(sample))
                for row, record in enumerate(sample):
                    for col, val in enumerate(record.values()):
                        table.setItem(row, col, QTableWidgetItem(str(val)))
                table.resizeColumnsToContents()
                table.setMaximumHeight(180)
            g_layout.addWidget(table)
            layout.addWidget(group)

        # options
        self.chk_auto      = QCheckBox("Auto-remove faulty rows and proceed")
        self.chk_low_days  = QCheckBox("Also remove full low-output days")
        self.chk_oscillate = QCheckBox("Also remove oscillating/unstable power periods")
        self.chk_low_days.setChecked(True)
        self.chk_low_days.setEnabled(False)
        self.chk_oscillate.setEnabled(False)

        self.chk_auto.toggled.connect(self.chk_low_days.setEnabled)
        self.chk_auto.toggled.connect(self.chk_oscillate.setEnabled)

        layout.addWidget(self.chk_auto)
        layout.addWidget(self.chk_low_days)
        layout.addWidget(self.chk_oscillate)

        self.btn_proceed = QPushButton("Proceed with Auto-removal")
        self.btn_proceed.setEnabled(False)
        self.btn_proceed.setStyleSheet("background-color: #FF9800; color: white;")
        self.chk_auto.toggled.connect(self.btn_proceed.setEnabled)
        self.btn_proceed.clicked.connect(self._on_proceed)
        layout.addWidget(self.btn_proceed)

        self.btn_manual = QPushButton("I will clean data and re-upload")
        self.btn_manual.setStyleSheet("background-color: #9E9E9E; color: white;")
        layout.addWidget(self.btn_manual)

    def _on_proceed(self):
        self.proceed_signal.emit(
            self.chk_low_days.isChecked(),
            self.chk_oscillate.isChecked(),
        )