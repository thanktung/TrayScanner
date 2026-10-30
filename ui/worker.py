"""
ui/worker.py — Background QThread that runs the (possibly slow) AOI pipeline
without blocking the Qt event loop.
"""

from PyQt5.QtCore import QThread, pyqtSignal

from vision.pipeline import run_pipeline


class InspectWorker(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, kwargs: dict, parent=None):
        super().__init__(parent)
        self._kwargs = kwargs

    def run(self):
        try:
            result = run_pipeline(**self._kwargs)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
