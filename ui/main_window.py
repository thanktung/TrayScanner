"""
ui/main_window.py — Main application window (AOIGUI).
"""

import os
import cv2
from datetime import datetime
from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QTextEdit, QMenuBar, QAction, QSpinBox,
    QDialog
)
from PyQt5.QtCore import Qt

from hardware.basler import DualBaslerCamera
from vision.pipeline import DEFAULT_CONFIG
from logic.settings import load_settings, save_settings
from logic.export import export_rcs, load_json

from .style import APP_STYLE
from .image_view import ImageView
from .settings_dialog import SettingsDialog
from .worker import InspectWorker


class AOIGUI(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto H08")
        self.resize(1400, 820)
        self.setStyleSheet(APP_STYLE)

        self.results: dict = {}
        self._cfg: dict    = load_settings()
        self._worker: Optional[InspectWorker] = None

        self.cam = DualBaslerCamera(
            save_folder=self._cfg.get("raw_dir", "D:/project/raw_images"),
            concat_mode="v",
        )
        self.cam_connected = False

        self._build_ui()
        self._connect_signals()
        self._sync_ui_from_cfg()

        # Kết nối camera tự động khi khởi động
        self._auto_connect_camera()

    # ── Kết nối camera tự động ───────────────

    def _auto_connect_camera(self):
        if self.cam.connect():
            self.cam_connected = True
            self.set_status("Camera đã kết nối — Sẵn sàng  [K] Chụp  [L] Xuất file")
        else:
            self.cam_connected = False
            self.set_status("⚠ Kết nối camera THẤT BẠI — Kiểm tra lại thiết bị")

    # ── Xây dựng UI ──────────────────────────

    def _build_ui(self):
        # Chỉ 2 nút chức năng trên panel
        self.btn_capture = QPushButton("CHỤP ẢNH [K]")
        self.btn_export  = QPushButton("XUẤT FILE [L]")
        self.btn_export.setEnabled(False)

        # Nhãn xem nhanh tham số
        self.lbl_detector = QLabel()
        self.lbl_roi      = QLabel()
        self.lbl_detector.setStyleSheet("font-size:13px; color:#555;")
        self.lbl_roi.setStyleSheet("font-size:13px; color:#555;")

        # Chỉ thị trạng thái camera
        self.lbl_cam_status = QLabel("● Camera: đang kết nối…")
        self.lbl_cam_status.setStyleSheet("font-size:13px; color:#888;")

        # ── Số lượng nhãn cần đọc — chỉnh trực tiếp trên panel ──
        lbl_req = QLabel("Số nhãn cần đọc:")
        lbl_req.setStyleSheet("font-size:13px; color:#444;")
        self.sp_required = QSpinBox()
        self.sp_required.setRange(0, 9999)
        self.sp_required.setSpecialValueText("Không giới hạn")
        self.sp_required.setStyleSheet("font-size:14px;")
        self.sp_required.setValue(int(self._cfg.get("required_count", 0)))
        self.sp_required.valueChanged.connect(self._on_required_changed)

        req_row = QHBoxLayout()
        req_row.setContentsMargins(0, 0, 0, 0)
        req_row.addWidget(lbl_req)
        req_row.addWidget(self.sp_required)
        req_frame = QWidget()
        req_frame.setLayout(req_row)

        left_layout = QVBoxLayout()
        left_layout.addWidget(self.btn_capture)
        left_layout.addWidget(self.btn_export)
        left_layout.addSpacing(12)
        left_layout.addWidget(self.lbl_cam_status)
        left_layout.addSpacing(8)
        left_layout.addWidget(req_frame)
        left_layout.addSpacing(8)
        left_layout.addWidget(self.lbl_detector)
        left_layout.addWidget(self.lbl_roi)
        left_layout.addStretch()

        left_frame = QFrame()
        left_frame.setObjectName("Panel")
        left_frame.setLayout(left_layout)
        left_w = left_frame

        self.img_view = ImageView()
        center_w = self._panel([self.img_view])

        self.count_lbl = QLabel("Phát hiện: 0")
        self.count_lbl.setObjectName("RightTitle")
        self.code_view = QTextEdit()
        self.code_view.setReadOnly(True)
        right_w = self._panel([self.count_lbl, self.code_view])

        self.status_lbl = QLabel("Đang khởi động…")
        self.status_lbl.setFixedHeight(28)

        # Menu bar — giữ lại Cài đặt trong menu
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
        main_h.addWidget(left_w,   2)
        main_h.addWidget(center_w, 7)
        main_h.addWidget(right_w,  3)

        main = QVBoxLayout(self)
        main.addLayout(main_h)
        main.addWidget(self.status_lbl)
        main.setMenuBar(menu_bar)

    def _panel(self, widgets, stretch=False):
        layout = QVBoxLayout()
        for w in widgets:
            layout.addWidget(w)
        if stretch:
            layout.addStretch()
        frame = QFrame()
        frame.setObjectName("Panel")
        frame.setLayout(layout)
        return frame

    def _connect_signals(self):
        self.btn_capture.clicked.connect(self.capture_and_inspect)
        self.btn_export.clicked.connect(self.export_rcs)

    # ── Phím tắt ─────────────────────────────

    def keyPressEvent(self, event):
        """K = Chụp ảnh,  L = Xuất file."""
        key = event.key()
        if key == Qt.Key_K:
            if self.btn_capture.isEnabled():
                self.capture_and_inspect()
        elif key == Qt.Key_L:
            if self.btn_export.isEnabled():
                self.export_rcs()
        else:
            super().keyPressEvent(event)

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
        # Đồng bộ spinbox required_count (chặn signal để tránh lưu lại)
        self.sp_required.blockSignals(True)
        self.sp_required.setValue(int(c.get("required_count", 0)))
        self.sp_required.blockSignals(False)

    def _on_required_changed(self, value: int):
        """Người dùng thay đổi số nhãn cần đọc trực tiếp trên panel."""
        self._cfg["required_count"] = value
        save_settings(self._cfg)

    # ── Hộp thoại cài đặt ────────────────────

    def open_settings(self):
        dlg = SettingsDialog(self._cfg, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cfg = dlg.get_config()
            save_settings(self._cfg)
            self._sync_ui_from_cfg()
            self.cam.save_folder = self._cfg.get("raw_dir", "D:/project/raw_images")
            self.set_status("Đã lưu cài đặt")

    # ── Chụp ảnh + Kiểm tra (gộp 2 bước) ────

    def capture_and_inspect(self):
        if not self.cam_connected:
            self.set_status("⚠ Chưa kết nối camera")
            return

        img = self.cam.grab()
        if img is None:
            self.set_status("Chụp ảnh thất bại")
            return

        raw_dir = self._cfg.get("raw_dir", "D:/project/raw_images")
        os.makedirs(raw_dir, exist_ok=True)
        path = os.path.join(raw_dir, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        cv2.imwrite(path, img)

        self.img_view.set_image_bgr(img)
        self.set_status(f"Đã chụp: {path} — Đang kiểm tra…")

        self._run_inspect(path)

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

        lines        = []
        flipped_ids  = []
        ok_count     = 0

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

        required = int(self._cfg.get("required_count", 0))
        if required > 0 and ok_count < required:
            self.btn_export.setEnabled(False)
            status_suffix = f" — Decode OK: {ok_count}/{required} (chưa đủ để xuất)"
        else:
            self.btn_export.setEnabled(True)
            status_suffix = ""

        if flipped_ids:
            self.set_status(
                f"Kiểm tra xong — ĐẶT NGƯỢC: nhãn {', '.join(flipped_ids)}{status_suffix}"
            )
        else:
            self.set_status(f"Kiểm tra xong{status_suffix}")

    def _on_inspect_error(self, msg: str):
        self.set_status(f"Lỗi pipeline: {msg}")
        self._set_busy_ui(False)

    def _set_busy_ui(self, running: bool):
        self.btn_capture.setEnabled(not running)
        if running:
            self.btn_export.setEnabled(False)

    # ── Xuất file ────────────────────────────

    def export_rcs(self):
        if not self.results:
            self.set_status("Không có kết quả để xuất")
            return

        export_dir = self._cfg.get("export_dir", "D:/RCS")
        out_path = export_rcs(self.results["json"], export_dir)

        self._reset_after_export()
        self.set_status(f"Đã xuất → {out_path}  — Sẵn sàng lần tiếp theo")

    def _reset_after_export(self):
        """Xóa ảnh và data sau khi xuất file thành công."""
        self.results = {}
        self.code_view.clear()
        self.count_lbl.setText("Phát hiện: 0")
        self.btn_export.setEnabled(False)
        self.img_view.clear_image()

    # ── Tiện ích ─────────────────────────────

    def set_status(self, msg: str):
        self.status_lbl.setText(msg)

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait()
        if self.cam_connected:
            self.cam.disconnect()
        event.accept()


