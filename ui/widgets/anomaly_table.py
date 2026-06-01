from PySide6.QtWidgets import QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class AnomalyTable(QWidget):
    """Display anomaly events table."""
    def __init__(self, anomaly_df, parent=None):
        super().__init__(parent)
        self._build_ui(anomaly_df)
    
    def _build_ui(self, anomaly_df):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if anomaly_df is None or len(anomaly_df) == 0:
            no_data = QLabel("No anomalies detected in this period.")
            no_data.setStyleSheet("font-size: 12px; color: #6B7280; padding: 16px;")
            layout.addWidget(no_data)
            return
        
        # title
        title = QLabel(f"Detected Anomalies ({len(anomaly_df)} events)")
        title.setStyleSheet("font-size: 13px; font-weight: 600; color: #374151; margin-bottom: 8px;")
        layout.addWidget(title)
        
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Timestamp", "Actual (kW)", "Predicted (kW)", "Residual (kW)", "Status"])
        table.setRowCount(len(anomaly_df))
        
        for row in range(len(anomaly_df)):
            item = anomaly_df.iloc[row]
            table.setItem(row, 0, QTableWidgetItem(str(item['timestamp'])))
            table.setItem(row, 1, QTableWidgetItem(f"{float(item['active_power_kw']):.2f}"))
            table.setItem(row, 2, QTableWidgetItem(f"{float(item['predicted_power']):.2f}"))
            table.setItem(row, 3, QTableWidgetItem(f"{float(item['residual']):.2f}"))
            table.setItem(row, 4, QTableWidgetItem(item['status']))
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
