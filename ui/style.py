"""
ui/style.py — Shared Qt stylesheet + small UI helper functions.
"""

from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QToolButton
from PyQt5.QtGui import QPixmap, QImage

from logic.export import load_json  # re-exported for convenience / backward compat

APP_STYLE = """
QWidget { background:#f4f4f4; font-family: Segoe UI; font-size:18px; color:#222; }
#Panel { background:#ffffff; border:1px solid #d0d0d0; }
QPushButton {
  background:#ffffff; border:1px solid #bdbdbd; padding:10px;
  font-size:16px; font-weight:600;
}
QPushButton:hover   { background:#ededed; }
QPushButton:pressed { background:#dcdcdc; }
QPushButton:disabled { color:#888; background:#f2f2f2; }
QLabel#RightTitle { font-size:18px; font-weight:700; }
QDialog { background:#f8f8f8; }
QTabWidget::pane { border:1px solid #d0d0d0; background:#ffffff; }
QTabBar::tab {
  background:#ececec; border:1px solid #c8c8c8;
  padding:6px 18px; font-size:14px;
}
QTabBar::tab:selected { background:#ffffff; border-bottom:none; font-weight:700; }
QGroupBox {
  border:1px solid #d0d0d0; border-radius:4px;
  margin-top:10px; font-size:14px; font-weight:600;
}
QGroupBox::title { subcontrol-origin:margin; left:8px; padding:0 4px; }
QFormLayout QLabel { font-size:14px; min-width:160px; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
  border:1px solid #c0c0c0; padding:4px 6px;
  font-size:14px; background:#ffffff;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color:#4a90d9; }
QToolButton { border:none; padding:2px 6px; font-size:13px; color:#555; }
QToolButton:hover { background:#e8e8e8; }
"""


def cv_bgr_to_pixmap(img_bgr):
    import cv2  # local import: keep OpenCV out of modules that don't need it
    import numpy as np

    if img_bgr is None:
        return QPixmap()
    rgb = np.ascontiguousarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    h, w, ch = rgb.shape
    # IMPORTANT: .copy() forces QImage to own a private deep copy of the
    # pixel data instead of just wrapping `rgb`'s raw buffer. Without it,
    # `rgb` (a local numpy array) can be garbage-collected/reused once this
    # function returns, leaving the QImage/QPixmap pointing at freed memory
    # — a dangling-pointer bug that crashes hard (STATUS_STACK_BUFFER_OVERRUN,
    # no Python traceback) as soon as something else (e.g. a YOLO inference
    # running in a worker thread) allocates into that now-freed region while
    # Qt repaints. Confirmed via crash repro during refactor testing.
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def path_row(parent, line_edit: QLineEdit, mode: str = "file",
             caption: str = "Chọn", ffilter: str = "Tất cả (*)") -> QHBoxLayout:
    """Return an HBox containing a line-edit + a "…" browse button."""
    btn = QToolButton(parent)
    btn.setText("…")
    btn.setFixedWidth(32)

    def browse():
        if mode == "dir":
            p = QFileDialog.getExistingDirectory(parent, caption, line_edit.text())
        else:
            p, _ = QFileDialog.getOpenFileName(parent, caption, line_edit.text(), ffilter)
        if p:
            line_edit.setText(p)

    btn.clicked.connect(browse)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(line_edit)
    row.addWidget(btn)
    return row

