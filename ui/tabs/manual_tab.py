from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel, QScrollArea
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

class ManualTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
    
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        # Content widget
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # title
        title = QLabel("📖 User Manual")
        title.setStyleSheet("font-size: 18px; font-weight: 600; color: #1F2937;")
        layout.addWidget(title)
        
        # read manual content from app.py
        try:
            with open("app.py", "r", encoding="utf-8") as f:
                content_text = f.read()
            
            # Extract TAB 4 Manual section
            manual_start = content_text.find("# TAB 4 MANUAL")
            manual_end = content_text.find("# ── Sidebar ────────────────────────────────────────────────────────────")
            
            if manual_start > 0:
                if manual_end > 0:
                    manual_content = content_text[manual_start:manual_end]
                else:
                    manual_content = content_text[manual_start:]
            else:
                manual_content = "Manual content not found."
        except:
            manual_content = "Could not load manual content."
        
        # Create text area with proper styling
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(manual_content)
        text_edit.setFont(QFont("Courier New", 10))
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: white;
                color: #1F2937;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 12px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(text_edit)
        layout.addStretch()
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)
