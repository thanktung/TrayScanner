"""
ui/image_view.py — Zoom/pan image viewer widget (no drag & drop).
"""

from PyQt5.QtWidgets import QLabel, QSizePolicy
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtCore import Qt, QPoint

from .style import cv_bgr_to_pixmap


class ImageView(QLabel):
    """Label hiển thị ảnh với zoom và pan. Không hỗ trợ drag & drop."""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(520, 360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._pix       = QPixmap()
        self.zoom       = 1.0
        self._offset    = QPoint(0, 0)
        self._dragging  = False
        self._last_pos  = None
        self.zoom_min   = 0.3
        self.zoom_max   = 4.0
        self.zoom_step  = 1.15

        self._set_hint()

    def _set_hint(self):
        self.setStyleSheet(
            "QLabel { background:#ffffff; border:1px dashed #a0a0a0;"
            " font-size:16px; color:#666; }"
        )
        self.setPixmap(QPixmap())
        self.setText("Nhấn K hoặc nút CHỤP ẢNH để bắt đầu")
        self.zoom    = 1.0
        self._offset = QPoint(0, 0)

    def _scaled_pix(self):
        return self._pix.scaled(
            int(self.width()  * self.zoom),
            int(self.height() * self.zoom),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

    def _update_view(self):
        if self._pix.isNull():
            return
        scaled = self._scaled_pix()
        vw, vh = self.width(), self.height()
        sw, sh = scaled.width(), scaled.height()
        ox = (vw - sw) // 2 if sw <= vw else max(vw - sw, min(0, self._offset.x()))
        oy = (vh - sh) // 2 if sh <= vh else max(vh - sh, min(0, self._offset.y()))
        self._offset = QPoint(ox, oy)
        canvas = QPixmap(self.size())
        canvas.fill(Qt.white)
        p = QPainter(canvas)
        p.drawPixmap(self._offset, scaled)
        p.end()
        self.setPixmap(canvas)

    def set_image_bgr(self, img):
        self._pix = cv_bgr_to_pixmap(img)
        if self._pix.isNull():
            self._set_hint()
            return
        self.setStyleSheet("QLabel { background:#ffffff; border:none; }")
        self.setText("")
        self.zoom    = 1.0
        self._offset = QPoint(0, 0)
        self._update_view()

    def clear_image(self):
        self._pix = QPixmap()
        self._set_hint()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if not self._pix.isNull():
            self._update_view()

    def wheelEvent(self, e):
        if self._pix.isNull():
            return
        self.zoom *= self.zoom_step if e.angleDelta().y() > 0 else 1 / self.zoom_step
        self.zoom  = max(self.zoom_min, min(self.zoom_max, self.zoom))
        self._update_view()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not self._pix.isNull():
            self._dragging = True
            self._last_pos = e.pos()

    def mouseMoveEvent(self, e):
        if self._dragging and self._last_pos is not None:
            self._offset  += e.pos() - self._last_pos
            self._last_pos = e.pos()
            self._update_view()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self._last_pos = None
