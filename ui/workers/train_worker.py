from PySide6.QtCore import QThread, Signal
from ui.workers.qt_log_handler import QtLogHandler


class TrainWorker(QThread):
    # signals emitted back to UI
    log_message = Signal(str)          # log message
    finished    = Signal(dict)         # results dict
    error       = Signal(str)          # error message

    def __init__(self, inv_files, wms_files, overwrite, remove_faults, remove_low_days=True, remove_oscillations=False):
        super().__init__()
        self.inv_files     = inv_files
        self.wms_files     = wms_files
        self.overwrite     = overwrite
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
            from pipelines.batch_pipeline import run_batch_train
            results = run_batch_train(
                inv_filepaths = self.inv_files,
                wms_filepaths = self.wms_files,
                overwrite     = self.overwrite,
                remove_faults = self.remove_faults,
                remove_low_days = self.remove_low_days,
                remove_oscillations_train = self.remove_oscillations,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            logging.getLogger().removeHandler(handler)