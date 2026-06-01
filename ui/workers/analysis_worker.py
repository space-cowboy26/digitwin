from PySide6.QtCore import QThread, Signal
from ui.workers.qt_log_handler import QtLogHandler


class AnalysisWorker(QThread):
    # signals emitted back to UI
    log_message = Signal(str)
    finished    = Signal(dict)
    error       = Signal(str)

    def __init__(self, inv_files, wms_files):
        super().__init__()
        self.inv_files = inv_files
        self.wms_files = wms_files

    def run(self):
        handler = QtLogHandler()
        handler.log_signal.connect(self.log_message)
        
        import logging
        logging.getLogger().addHandler(handler)
        
        try:
            from pipelines.batch_pipeline import run_batch_inference
            results = run_batch_inference(
                inv_filepaths=self.inv_files,
                wms_filepaths=self.wms_files
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            logging.getLogger().removeHandler(handler)
