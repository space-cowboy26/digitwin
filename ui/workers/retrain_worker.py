from PySide6.QtCore import QThread, Signal
from ui.workers.qt_log_handler import QtLogHandler


class RetrainWorker(QThread):
    # signals emitted back to UI
    log_message = Signal(str)          # log message
    finished    = Signal(dict)         # results dict
    error       = Signal(str)          # error message

    def __init__(self, inv_files, wms_files, remove_faults, remove_low_days=True, remove_oscillations=False):
        super().__init__()
        self.inv_files     = inv_files
        self.wms_files     = wms_files
        self.remove_faults = remove_faults
        self.remove_low_days = remove_low_days
        self.remove_oscillations = remove_oscillations

    def run(self):
        # create handler and connect its signal to our log_message signal
        handler = QtLogHandler()
        handler.log_signal.connect(self.log_message)

        # attach to root logger so all pipeline logs flow through it
        import logging
        logging.getLogger().addHandler(handler)

        try:
            from pipelines.batch_pipeline import run_batch_retrain
            results = run_batch_retrain(
                inv_filepaths = self.inv_files,
                wms_filepaths = self.wms_files,
                remove_faults = self.remove_faults,
                remove_low_days = self.remove_low_days,
                remove_oscillations = self.remove_oscillations,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            logging.getLogger().removeHandler(handler)