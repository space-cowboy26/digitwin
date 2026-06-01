from PySide6.QtWidgets import QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class MetricsTable(QWidget):
    """Display training/retraining metrics table."""
    def __init__(self, results: dict, parent=None):
        super().__init__(parent)
        self._build_ui(results)
    
    def _build_ui(self, results: dict):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # title
        title = QLabel("Training Results Summary")
        title.setStyleSheet("font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 8px;")
        layout.addWidget(title)
        
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Inverter", "Status", "Test RMSE", "Val RMSE", "Duration", "Notes"])
        table.setRowCount(len(results))
        
        row = 0
        for itc_inv, r in results.items():
            table.setItem(row, 0, QTableWidgetItem(itc_inv.replace("_", "-")))
            
            if r.get("skipped"):
                table.setItem(row, 1, QTableWidgetItem("Skipped"))
                table.setItem(row, 2, QTableWidgetItem("-"))
                table.setItem(row, 3, QTableWidgetItem("-"))
                table.setItem(row, 4, QTableWidgetItem("-"))
            elif not r.get("passed"):
                table.setItem(row, 1, QTableWidgetItem("Failed"))
                table.setItem(row, 2, QTableWidgetItem("-"))
                table.setItem(row, 3, QTableWidgetItem("-"))
                table.setItem(row, 4, QTableWidgetItem("-"))
            else:
                table.setItem(row, 1, QTableWidgetItem("Success"))
                table.setItem(row, 2, QTableWidgetItem(f"{r['test_metrics']['rmse']:.2f} kW"))
                table.setItem(row, 3, QTableWidgetItem(f"{r['val_metrics']['rmse']:.2f} kW"))
                table.setItem(row, 4, QTableWidgetItem(f"{r.get('duration_sec', '-')}s"))
            
            row += 1
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
