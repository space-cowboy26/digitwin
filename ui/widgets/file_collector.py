from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QFileDialog, QLabel
)
from pathlib import Path

class FileCollector(QWidget):
    """
    Reusable widget for collecting Excel files.
    Supports folder browser, individual file picker,
    and manual path paste. Shows collected file list.
    """
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._files: list[Path] = []
        self._build_ui(label)

    def _build_ui(self, label):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 12)
        
        # label with styling
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #374151;")
        layout.addWidget(lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_folder = QPushButton("Browse Folder")
        self.btn_files  = QPushButton("Add Files")
        self.btn_clear  = QPushButton("Clear")
        btn_row.addWidget(self.btn_folder)
        btn_row.addWidget(self.btn_files)
        btn_row.addWidget(self.btn_clear)
        layout.addLayout(btn_row)

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(120)
        layout.addWidget(self.file_list)

        self.status_label = QLabel("No files selected.")
        self.status_label.setStyleSheet("font-size: 11px; color: #6B7280;")
        layout.addWidget(self.status_label)

        self.btn_folder.clicked.connect(self._browse_folder)
        self.btn_files.clicked.connect(self._browse_files)
        self.btn_clear.clicked.connect(self._clear)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            xlsx = list(Path(folder).glob("*.xlsx"))
            self._add_files(xlsx)

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", "", "Excel Files (*.xlsx *.xls)"
        )
        self._add_files([Path(f) for f in files])

    def _add_files(self, new_files):
        existing = {f.name for f in self._files}
        for f in new_files:
            if f.name not in existing:
                self._files.append(f)
                self.file_list.addItem(f.name)
                existing.add(f.name)
        self.status_label.setText(f"{len(self._files)} file(s) ready.")

    def _clear(self):
        self._files.clear()
        self.file_list.clear()
        self.status_label.setText("No files selected.")

    def get_files(self) -> list[Path]:
        return sorted(self._files)