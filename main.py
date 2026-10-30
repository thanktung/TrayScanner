"""
main.py — H08 TrayScanner entry point.

Run with:
    .venv\Scripts\python.exe main.py
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

# Force UTF-8 on stdout/stderr regardless of the Windows console codepage.
# Without this, any print() of Vietnamese text (e.g. basler.py's error
# messages) raises UnicodeEncodeError under cp1252 and kills the app before
# the window ever shows — happened during testing when no camera is attached.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from PyQt5.QtWidgets import QApplication

from ui.main_window import AOIGUI


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AOIGUI()
    w.show()
    sys.exit(app.exec_())


