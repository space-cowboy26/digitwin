# ui/workers/qt_log_handler.py

import logging
from PySide6.QtCore import QObject, Signal

class QtLogHandler(logging.Handler, QObject):
    """
    Custom logging handler that emits a Qt signal
    for every log message. This bridges Python logging
    and the PySide6 signal system.
    """
    log_signal = Signal(str)

    def __init__(self):
        logging.Handler.__init__(self)
        QObject.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)