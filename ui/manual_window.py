"""
ui/manual_window.py — Manual Mode window.

Same inspect/export pipeline as the camera-driven AOIGUI (ui.main_window),
but the image comes from the user instead of a Basler camera:
    - "MỞ ẢNH..." button → file dialog
    - drag & drop an image file anywhere onto the window

No camera / hardware dependency at all — useful for offline testing/tuning
against images already saved to disk.
"""

import os
import cv2
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame, QTextEdit,
    QMenuBar, QAction, QFileDialog, QDialog
)
from PyQt5.QtCore import Qt

from vision.pipeline import DEFAULT_CONFIG
from logic.settings import load_settings, save_settings
from logic.export import export_rcs, load_json

from .style import APP_STYLE
from .image_view import ImageView
from .settings_dialog import SettingsDialog
from .worker import InspectWorker

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp")


class ManualInspectWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto H08 — Manual Mode (mở ảnh / kéo thả)")
        self.resize(1400, 820)
        self.setStyleSheet(APP_STYLE)
        self.setAcceptDrops(True)

        self.results: dict = {}
        self._cfg: dict    = load_settings()
        self._worker: Optional[InspectWorker] = None
        self._current_path: Optional[str] = None

        self._build_ui()
        self._connect_signals()
        self._sync_ui_from_cfg()
        self.set_status("Kéo thả ảnh vào đây, hoặc bấm MỞ ẢNH để bắt đầu")

    # ── Xây dựng UI ──────────────────────────

    def _build_ui(self):
        self.btn_open    = QPushButton("MỞ ẢNH... [O]")
        self.btn_run     = QPushButton("CHẠY PIPELINE [R]")
        self.btn_export  = QPushButton("XUẤT FILE [L]")
        self.btn_run.setEnabled(False)
        self.btn_export.setEnabled(False)

        self.lbl_detector = QLabel()
        self.lbl_roi      = QLabel()
        self.lbl_detector.setStyleSheet("font-size:13px; color:#555;")
        self.lbl_roi.setStyleSheet("font-size:13px; color:#555;")

        self.lbl_path = QLabel("Chưa nạp ảnh")
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setStyleSheet("font-size:12px; color:#888;")

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.btn_open)
        left_layout.addWidget(self.btn_run)
        left_layout.addWidget(self.btn_export)
        left_layout.addSpacing(12)
        left_layout.addWidget(self.lbl_path)
        left_layout.addSpacing(8)
        left_layout.addWidget(self.lbl_detector)
        left_layout.addWidget(self.lbl_roi)
        left_layout.addStretch()

        left_frame = QFrame()
        left_frame.setObjectName("Panel")
        left_frame.setLayout(left_layout)

        self.img_view = ImageView()
        self.img_view.setText("Kéo thả ảnh vào đây, hoặc bấm MỞ ẢNH [O]")
        center_w = self._panel([self.img_view])

        self.count_lbl = QLabel("Phát hiện: 0")
        self.count_lbl.setObjectName("RightTitle")
        self.code_view = QTextEdit()
        self.code_view.setReadOnly(True)
        right_w = self._panel([self.count_lbl, self.code_view])

        self.status_lbl = QLabel("Đang khởi động…")
        self.status_lbl.setFixedHeight(28)

        menu_bar  = QMenuBar()
        menu_main = menu_bar.addMenu("Menu")
        act_settings = QAction("Cài đặt…", self)
        act_settings.triggered.connect(self.open_settings)
        act_exit = QAction("Thoát", self)
        act_exit.triggered.connect(self.close)
        menu_main.addAction(act_settings)
        menu_main.addSeparator()
        menu_main.addAction(act_exit)

        main_h = QHBoxLayout()
        main_h.addWidget(left_frame, 2)
        main_h.addWidget(center_w,   7)
        main_h.addWidget(right_w,    3)

        main = QVBoxLayout(self)
        main.addLayout(main_h)
        main.addWidget(self.status_lbl)
        main.setMenuBar(menu_bar)

    def _panel(self, widgets):
        layout = QVBoxLayout()
        for w in widgets:
            layout.addWidget(w)
        frame = QFrame()
        frame.setObjectName("Panel")
        frame.setLayout(layout)
        return frame

    def _connect_signals(self):
        self.btn_open.clicked.connect(self.open_image_dialog)
        self.btn_run.clicked.connect(self.run_pipeline_on_current)
        self.btn_export.clicked.connect(self.export_rcs)

    # ── Phím tắt ─────────────────────────────

    def keyPressEvent(self, event):
        """O = Mở ảnh,  R = Chạy pipeline,  L = Xuất file."""
        key = event.key()
        if key == Qt.Key_O:
            self.open_image_dialog()
        elif key == Qt.Key_R:
            if self.btn_run.isEnabled():
                self.run_pipeline_on_current()
        elif key == Qt.Key_L:
            if self.btn_export.isEnabled():
                self.export_rcs()
        else:
            super().keyPressEvent(event)

    # ── Drag & drop ──────────────────────────

    @staticmethod
    def _is_image(path: str) -> bool:
        return os.path.splitext(path)[1].lower() in IMAGE_EXTS

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(self._is_image(u.toLocalFile()) for u in urls):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for u in event.mimeData().urls():
            path = u.toLocalFile()
            if self._is_image(path):
                self._load_image(path)
                break

    # ── Mở ảnh ───────────────────────────────

    def open_image_dialog(self):
        start_dir = self._cfg.get("raw_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh", start_dir,
            "Ảnh (*.png *.jpg *.jpeg *.bmp);;Tất cả (*)"
        )
        if path:
            self._load_image(path)

    def _load_image(self, path: str):
        img = cv2.imread(path)
        if img is None:
            self.set_status(f"⚠ Không đọc được ảnh: {path}")
            return

        self._current_path = path
        self.results = {}
        self.code_view.clear()
        self.count_lbl.setText("Phát hiện: 0")
        self.btn_export.setEnabled(False)

        self.img_view.set_image_bgr(img)
        self.lbl_path.setText(path)
        self.btn_run.setEnabled(True)
        self.set_status("Đã nạp ảnh — bấm CHẠY PIPELINE [R] để kiểm tra")

    # ── Đồng bộ nhãn xem nhanh ───────────────

    def _sync_ui_from_cfg(self):
        c = self._cfg
        self.lbl_detector.setText(
            f"Detector: {c.get('detector', '?')}"
            + (f"  conf={c.get('yolo_conf', '?')}" if c.get("detector") == "yolo" else "")
            + f"  |  Mã: {c.get('target_format', 'DataMatrix')}"
        )
        self.lbl_roi.setText(
            f"DMX ROI: {c.get('dmx_dx')};{c.get('dmx_dy')};"
            f"{c.get('dmx_w')};{c.get('dmx_h')}"
        )

    def open_settings(self):
        dlg = SettingsDialog(self._cfg, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cfg = dlg.get_config()
            save_settings(self._cfg)
            self._sync_ui_from_cfg()
            self.set_status("Đã lưu cài đặt")

    # ── Chạy pipeline ────────────────────────

    def run_pipeline_on_current(self):
        if not self._current_path:
            self.set_status("⚠ Chưa có ảnh để chạy")
            return
        self._run_inspect(self._current_path)

    def _run_inspect(self, img_path: str):
        c = self._cfg
        self._set_busy_ui(True)

        self._worker = InspectWorker({
            "img_path":          img_path,
            "golden_path":       c.get("golden_path",  ""),
            "img_out_dir":       c.get("img_out_dir",  "D:/project/result_images"),
            "json_out_dir":      c.get("json_out_dir", "D:/project/result_json"),
            "detector":          c.get("detector",     "opencv"),
            "model_path":        c.get("model_path",   ""),
            "yolo_imgsz":        int(c.get("yolo_imgsz",        1280)),
            "yolo_conf":         float(c.get("yolo_conf",       0.5)),
            "cv_clahe_clip":     float(c.get("cv_clahe_clip",   3.0)),
            "cv_clahe_tile":     int(c.get("cv_clahe_tile",     16)),
            "cv_tophat_ksize":   int(c.get("cv_tophat_ksize",   61)),
            "cv_blur_ksize":     int(c.get("cv_blur_ksize",     9)),
            "cv_close_ksize":    int(c.get("cv_close_ksize",    15)),
            "cv_min_area":       int(c.get("cv_min_area",       25000)),
            "cv_ratio_min":      float(c.get("cv_ratio_min",    0.55)),
            "cv_ratio_max":      float(c.get("cv_ratio_max",    1.5)),
            "cv_min_w":          int(c.get("cv_min_w",          120)),
            "cv_min_h":          int(c.get("cv_min_h",          120)),
            "cv_max_h":          int(c.get("cv_max_h",          500)),
            "cv_tighten_margin": int(c.get("cv_tighten_margin", 4)),
            "orb_features":      int(c.get("orb_features",      500)),
            "dmx_dx":            int(c.get("dmx_dx",   120)),
            "dmx_dy":            int(c.get("dmx_dy",   90)),
            "dmx_w":             int(c.get("dmx_w",    100)),
            "dmx_h":             int(c.get("dmx_h",    100)),
            "label_timeout":     int(c.get("label_timeout", 30)),
            "target_format":     c.get("target_format", "DataMatrix"),
        })
        self._worker.finished.connect(self._on_inspect_done)
        self._worker.error.connect(self._on_inspect_error)
        self._worker.start()

    def _on_inspect_done(self, result: dict):
        self.results = result
        data = load_json(result["json"])

        out_img = cv2.imread(result["image"])
        if out_img is not None:
            self.img_view.set_image_bgr(out_img)

        lines       = []
        flipped_ids = []
        ok_count    = 0

        for r in data:
            code    = r.get("dmx", {}).get("code") or "NG"
            flipped = r.get("flipped", False)
            angle   = r.get("rotation_angle", 0)
            rid     = r.get("id")
            if flipped:
                lines.append(f"[{rid}] ĐẶT NGƯỢC ({angle:.0f}°)  →  {code}")
                flipped_ids.append(str(rid))
            else:
                lines.append(f"[{rid}] {code}")
            if code != "NG":
                ok_count += 1

        self.code_view.setPlainText("\n".join(lines))
        self.count_lbl.setText(f"Phát hiện: {len(data)}")
        self._set_busy_ui(False)
        self.btn_export.setEnabled(len(data) > 0)

        if flipped_ids:
            self.set_status(f"Kiểm tra xong — ĐẶT NGƯỢC: nhãn {', '.join(flipped_ids)}")
        else:
            self.set_status(f"Kiểm tra xong — OK: {ok_count}/{len(data)}")

    def _on_inspect_error(self, msg: str):
        self.set_status(f"Lỗi pipeline: {msg}")
        self._set_busy_ui(False)

    def _set_busy_ui(self, running: bool):
        self.btn_run.setEnabled(not running)
        self.btn_open.setEnabled(not running)
        if running:
            self.btn_export.setEnabled(False)

    # ── Xuất file ────────────────────────────

    def export_rcs(self):
        if not self.results:
            self.set_status("Không có kết quả để xuất")
            return
        export_dir = self._cfg.get("export_dir", "D:/RCS")
        out_path = export_rcs(self.results["json"], export_dir)
        self.set_status(f"Đã xuất → {out_path}")

    # ── Tiện ích ─────────────────────────────

    def set_status(self, msg: str):
        self.status_lbl.setText(msg)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()
        event.accept()


