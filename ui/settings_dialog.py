"""
ui/settings_dialog.py — Settings dialog with 4 tabs (paths / detector /
OpenCV params / alignment+DMX).
"""

from PyQt5.QtWidgets import (
    QWidget, QDialog, QDialogButtonBox, QTabWidget, QFormLayout,
    QVBoxLayout, QLabel, QComboBox, QLineEdit, QFileDialog,
    QSpinBox, QDoubleSpinBox, QScrollArea, QGroupBox
)
from PyQt5.QtCore import Qt

from .style import path_row


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(560)
        self._cfg = dict(cfg)
        self._build()

    def _build(self):
        tabs = QTabWidget()
        tabs.addTab(self._tab_paths(),   "Đường dẫn")
        tabs.addTab(self._tab_detect(),  "Phát hiện")
        tabs.addTab(self._tab_opencv(),  "OpenCV")
        tabs.addTab(self._tab_align(),   "Căn chỉnh / DMX")

        bbox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal, self
        )
        bbox.accepted.connect(self._accept)
        bbox.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bbox)

    def _tab_opencv(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        inner = QWidget()
        lay   = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        def dsp(key, lo=0.0, hi=100.0, step=0.5, dec=1) -> QDoubleSpinBox:
            s = QDoubleSpinBox()
            s.setRange(lo, hi); s.setSingleStep(step)
            s.setDecimals(dec); s.setValue(float(self._cfg.get(key, 0)))
            return s

        def isp(key, lo=1, hi=9999, step=1) -> QSpinBox:
            s = QSpinBox()
            s.setRange(lo, hi); s.setSingleStep(step)
            s.setValue(int(self._cfg.get(key, lo)))
            return s

        def note(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size:12px; color:#666; padding-left:4px;")
            return lbl

        def grp(title, rows) -> QGroupBox:
            g = QGroupBox(title)
            f = QFormLayout(g)
            f.setSpacing(6)
            for label, widget, hint in rows:
                f.addRow(label, widget)
                if hint:
                    f.addRow("", note(hint))
            return g

        self._sp_clahe_clip = dsp("cv_clahe_clip", 0.5, 20.0, 0.5, 1)
        self._sp_clahe_tile = isp("cv_clahe_tile", 2, 64, 2)
        lay.addWidget(grp("CLAHE — Tăng độ tương phản cục bộ", [
            ("Clip limit:",    self._sp_clahe_clip, "Giới hạn khuếch đại tương phản. Tăng → ảnh sắc nét hơn nhưng nhiễu nhiều hơn. Thông thường 2–5. Mặc định: 3.0"),
            ("Tile size (px):", self._sp_clahe_tile, "Kích thước ô xử lý (pixel). Nhỏ → chi tiết cục bộ tốt hơn; lớn → mượt hơn. Thông thường 8–32. Mặc định: 16"),
        ]))

        self._sp_tophat = isp("cv_tophat_ksize", 11, 301, 2)
        lay.addWidget(grp("Top-hat kernel — Tách vùng sáng khỏi nền", [
            ("Kernel size (px, lẻ):", self._sp_tophat, "Kernel morphology dùng để tách nhãn trắng khỏi nền tối. Phải lớn hơn chiều rộng của nhãn. Tăng → bắt nhãn rộng hơn. Thông thường 41–101. Mặc định: 61"),
        ]))

        self._sp_blur = isp("cv_blur_ksize", 3, 51, 2)
        lay.addWidget(grp("Gaussian Blur — Làm mờ trước khi threshold", [
            ("Kernel size (px, lẻ):", self._sp_blur, "Làm mịn ảnh top-hat trước khi threshold Otsu. Tăng → bỏ qua chi tiết nhỏ, giảm noise; giảm → giữ cạnh sắc hơn. Thông thường 5–15. Mặc định: 9"),
        ]))

        self._sp_close = isp("cv_close_ksize", 3, 101, 2)
        lay.addWidget(grp("Morphology Close — Lấp lỗ hổng trong mask", [
            ("Kernel size (px, lẻ):", self._sp_close, "Sau threshold, dùng Close để lấp các lỗ nhỏ bên trong nhãn. Tăng → lấp lỗ lớn hơn, dễ nối các vùng rời; giảm → giữ hình dạng gốc. Thông thường 9–25. Mặc định: 15"),
        ]))

        self._sp_min_area  = isp("cv_min_area",  100, 500000, 1000)
        self._sp_ratio_min = dsp("cv_ratio_min", 0.1,  5.0,   0.05, 2)
        self._sp_ratio_max = dsp("cv_ratio_max", 0.1, 10.0,   0.05, 2)
        self._sp_min_w     = isp("cv_min_w",       1,  2000,    10)
        self._sp_min_h     = isp("cv_min_h",       1,  2000,    10)
        self._sp_max_h     = isp("cv_max_h",       1,  5000,    10)
        lay.addWidget(grp("Lọc contour — Chỉ giữ lại nhãn đúng kích thước", [
            ("Diện tích tối thiểu (px²):", self._sp_min_area,  "Bỏ qua vùng nhỏ hơn giá trị này. Tăng → loại bỏ nhiễu nhỏ; giảm → bắt cả nhãn nhỏ. Mặc định: 25 000"),
            ("w/h tối thiểu:",             self._sp_ratio_min, "Tỉ lệ chiều rộng/chiều cao. Nhỏ hơn → bỏ qua (vật thể quá hẹp/cao). Mặc định: 0.55"),
            ("w/h tối đa:",                self._sp_ratio_max, "Lớn hơn → bỏ qua (vật thể quá rộng/dẹt). Mặc định: 1.5"),
            ("Chiều rộng tối thiểu (px):", self._sp_min_w,     "Bỏ qua contour có width < giá trị này. Mặc định: 120"),
            ("Chiều cao tối thiểu (px):",  self._sp_min_h,     "Bỏ qua contour có height < giá trị này. Mặc định: 120"),
            ("Chiều cao tối đa (px):",     self._sp_max_h,     "Bỏ qua contour có height > giá trị này (loại đối tượng quá lớn). Mặc định: 500"),
        ]))

        self._sp_tighten = isp("cv_tighten_margin", 0, 50, 1)
        lay.addWidget(grp("Tighten — Căn chỉnh lại bounding box sau khi detect", [
            ("Margin (px):", self._sp_tighten, "Sau khi tìm đúng nhãn, mở rộng thêm N pixel mỗi chiều để không cắt sát mép. Tăng → lấy thêm viền; giảm → crop sát hơn. Mặc định: 4"),
        ]))

        lay.addStretch()
        scroll.setWidget(inner)
        return scroll

    def _tab_paths(self) -> QWidget:
        w   = QWidget()
        frm = QFormLayout(w)
        frm.setSpacing(10)
        frm.setContentsMargins(12, 12, 12, 12)

        def le(key):
            e = QLineEdit(str(self._cfg.get(key, "")))
            e.setProperty("cfg_key", key)
            return e

        self._e_golden     = le("golden_path")
        self._e_model      = le("model_path")
        self._e_raw_dir    = le("raw_dir")
        self._e_img_out    = le("img_out_dir")
        self._e_json_out   = le("json_out_dir")
        self._e_export_dir = le("export_dir")

        img_filt = "Ảnh (*.png *.jpg *.bmp);;Tất cả (*)"
        pt_filt  = "Model (*.pt);;Tất cả (*)"

        frm.addRow("Ảnh mẫu (golden):",    path_row(self, self._e_golden,     "file", "Chọn ảnh mẫu", img_filt))
        frm.addRow("Model YOLO (.pt):",     path_row(self, self._e_model,      "file", "Chọn file weights", pt_filt))
        frm.addRow("Thư mục ảnh gốc:",      path_row(self, self._e_raw_dir,    "dir",  "Thư mục ảnh gốc"))
        frm.addRow("Thư mục ảnh kết quả:",  path_row(self, self._e_img_out,    "dir",  "Thư mục ảnh kết quả"))
        frm.addRow("Thư mục JSON kết quả:", path_row(self, self._e_json_out,   "dir",  "Thư mục JSON kết quả"))
        frm.addRow("Thư mục xuất (RCS):",   path_row(self, self._e_export_dir, "dir",  "Thư mục xuất RCS"))

        return w

    def _tab_detect(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        grp_det = QGroupBox("Bộ phát hiện")
        frm_det = QFormLayout(grp_det)
        self._cb_detector = QComboBox()
        self._cb_detector.addItems(["opencv", "yolo"])
        self._cb_detector.setCurrentText(self._cfg.get("detector", "opencv"))
        frm_det.addRow("Detector:", self._cb_detector)

        self._cb_format = QComboBox()
        self._cb_format.addItems(["DataMatrix", "QRCode"])
        self._cb_format.setCurrentText(self._cfg.get("target_format", "DataMatrix"))
        frm_det.addRow("Loại mã cần đọc:", self._cb_format)
        note_fmt = QLabel(
            "Chỉ nhận 1 loại mã. Box nào phát hiện ra loại KHÁC (vd mã QR dán "
            "trên khay) sẽ tự động bị loại bỏ, không tính là nhãn, không báo NG."
        )
        note_fmt.setWordWrap(True)
        note_fmt.setStyleSheet("font-size:12px; color:#666; padding-left:4px;")
        frm_det.addRow("", note_fmt)

        grp_yolo = QGroupBox("Tham số YOLO")
        frm_yolo = QFormLayout(grp_yolo)

        self._sp_imgsz = QSpinBox()
        self._sp_imgsz.setRange(320, 4096)
        self._sp_imgsz.setSingleStep(32)
        self._sp_imgsz.setValue(int(self._cfg.get("yolo_imgsz", 1280)))

        self._sp_conf = QDoubleSpinBox()
        self._sp_conf.setRange(0.01, 1.0)
        self._sp_conf.setSingleStep(0.05)
        self._sp_conf.setDecimals(2)
        self._sp_conf.setValue(float(self._cfg.get("yolo_conf", 0.5)))

        frm_yolo.addRow("Kích thước ảnh (imgsz):", self._sp_imgsz)
        frm_yolo.addRow("Ngưỡng tin cậy (conf):",  self._sp_conf)

        lay.addWidget(grp_det)
        lay.addWidget(grp_yolo)
        lay.addStretch()
        return w

    def _tab_align(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        grp_orb = QGroupBox("ORB (căn chỉnh)")
        frm_orb = QFormLayout(grp_orb)
        self._sp_orb = QSpinBox()
        self._sp_orb.setRange(50, 5000)
        self._sp_orb.setSingleStep(50)
        self._sp_orb.setValue(int(self._cfg.get("orb_features", 500)))
        frm_orb.addRow("ORB max features:", self._sp_orb)

        grp_dmx = QGroupBox("DMX ROI (trong ảnh đã căn chỉnh, pixel)")
        frm_dmx = QFormLayout(grp_dmx)

        def sp(key, lo=0, hi=4096):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(int(self._cfg.get(key, 0)))
            return s

        self._sp_dx = sp("dmx_dx")
        self._sp_dy = sp("dmx_dy")
        self._sp_dw = sp("dmx_w", 1)
        self._sp_dh = sp("dmx_h", 1)

        frm_dmx.addRow("dx (lề trái):",   self._sp_dx)
        frm_dmx.addRow("dy (lề trên):",   self._sp_dy)
        frm_dmx.addRow("w (chiều rộng):", self._sp_dw)
        frm_dmx.addRow("h (chiều cao):",  self._sp_dh)

        grp_misc = QGroupBox("Khác")
        frm_misc = QFormLayout(grp_misc)

        self._sp_timeout = QSpinBox()
        self._sp_timeout.setRange(1, 300)
        self._sp_timeout.setSuffix(" s")
        self._sp_timeout.setValue(int(self._cfg.get("label_timeout", 30)))
        frm_misc.addRow("Timeout nhãn:", self._sp_timeout)

        self._sp_required_count = QSpinBox()
        self._sp_required_count.setRange(0, 9999)
        self._sp_required_count.setValue(int(self._cfg.get("required_count", 0)))
        self._sp_required_count.setSpecialValueText("Không giới hạn")

        note = QLabel(
            "Số mã decode thành công tối thiểu để cho phép xuất file. "
            "Đặt 0 = không giới hạn (luôn cho phép xuất)."
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size:12px; color:#666; padding-left:4px;")

        frm_misc.addRow("Số lượng mẫu yêu cầu:", self._sp_required_count)
        frm_misc.addRow("", note)

        lay.addWidget(grp_orb)
        lay.addWidget(grp_dmx)
        lay.addWidget(grp_misc)
        lay.addStretch()
        return w

    def _accept(self):
        self._cfg.update({
            "golden_path":  self._e_golden.text().strip(),
            "model_path":   self._e_model.text().strip(),
            "raw_dir":      self._e_raw_dir.text().strip(),
            "img_out_dir":  self._e_img_out.text().strip(),
            "json_out_dir": self._e_json_out.text().strip(),
            "export_dir":   self._e_export_dir.text().strip(),
            "detector":     self._cb_detector.currentText(),
            "target_format": self._cb_format.currentText(),
            "yolo_imgsz":   self._sp_imgsz.value(),
            "yolo_conf":    self._sp_conf.value(),
            "cv_clahe_clip":     self._sp_clahe_clip.value(),
            "cv_clahe_tile":     self._sp_clahe_tile.value(),
            "cv_tophat_ksize":   self._sp_tophat.value(),
            "cv_blur_ksize":     self._sp_blur.value(),
            "cv_close_ksize":    self._sp_close.value(),
            "cv_min_area":       self._sp_min_area.value(),
            "cv_ratio_min":      self._sp_ratio_min.value(),
            "cv_ratio_max":      self._sp_ratio_max.value(),
            "cv_min_w":          self._sp_min_w.value(),
            "cv_min_h":          self._sp_min_h.value(),
            "cv_max_h":          self._sp_max_h.value(),
            "cv_tighten_margin": self._sp_tighten.value(),
            "orb_features":    self._sp_orb.value(),
            "dmx_dx":          self._sp_dx.value(),
            "dmx_dy":          self._sp_dy.value(),
            "dmx_w":           self._sp_dw.value(),
            "dmx_h":           self._sp_dh.value(),
            "label_timeout":   self._sp_timeout.value(),
            "required_count":  self._sp_required_count.value(),
        })
        self.accept()

    def get_config(self) -> dict:
        return self._cfg

