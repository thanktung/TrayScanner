"""
main_manual.py — H08 TrayScanner, Manual Mode entry point.

Unlike main.py (camera-driven), this window takes images from disk:
    - click "MỞ ẢNH..." to browse, or
    - drag & drop an image file onto the window

Run with:
    .venv\Scripts\python.exe main_manual.py
"""

import sys

# OpenCV's internal thread pool (TBB/OpenMP) can conflict when cv2 calls
# happen on the main thread (e.g. displaying a loaded image) and then again
# from a worker QThread (the inspect pipeline) -- reproduced as a hard native
# crash (STATUS_STACK_BUFFER_OVERRUN, no Python traceback) during manual-mode
# testing: load image -> run pipeline. Forcing single-threaded OpenCV avoids
# the cross-thread conflict; the app's own ThreadPoolExecutor (per-label
# alignment/decode) still parallelises fine on top of this.
import cv2
cv2.setNumThreads(1)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PyQt5.QtWidgets import QApplication

from ui.manual_window import ManualInspectWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ManualInspectWindow()
    w.show()
    sys.exit(app.exec_())

