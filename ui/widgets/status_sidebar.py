from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGroupBox
from core.model import model_status
from config.settings import ITC_INV_LIST

class StatusSidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel("☀️ Solar Digital Twin"))
        self._layout.addWidget(QLabel("Inverter Status"))
        self._groups = {}
        for inv in ITC_INV_LIST:
            lbl = QLabel()
            self._groups[inv] = lbl
            self._layout.addWidget(lbl)
        self._layout.addStretch()
        self.refresh()

    def refresh(self):
        for inv, lbl in self._groups.items():
            s = model_status(inv)
            if s["trained"]:
                lbl.setText(
                    f"✅ {inv.replace('_','-')}\n"
                    f"   RMSE: {s['test_rmse']:.1f} kW\n"
                    f"   {s['last_trained'][:10]}"
                )
                lbl.setStyleSheet("color: green;")
            else:
                lbl.setText(f"⚪ {inv.replace('_','-')}\n   Not trained")
                lbl.setStyleSheet("color: grey;")