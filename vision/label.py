"""
vision/label.py — Single-label alignment, DMX decode, drawing, serialisation.

Alignment:
    - ORB homography (thread-local ORB instance per worker thread)

Decode:
    - zxingcpp  (fast, tried first)
    - libdmtx   (robust fallback)
"""

import os
import threading
from typing import Optional, Generator

import cv2
import numpy as np
import zxingcpp
from pylibdmtx import pylibdmtx


# ─────────────────────────────────────────────────────────────
# thread-local ORB — one instance per worker thread, zero contention
# ─────────────────────────────────────────────────────────────

_thread_local = threading.local()


def _get_orb(n_features: int) -> cv2.ORB:
    """Return (or lazily create) a thread-local ORB instance."""
    orb = getattr(_thread_local, "orb", None)
    if orb is None or getattr(_thread_local, "orb_features", None) != n_features:
        _thread_local.orb          = cv2.ORB_create(n_features)
        _thread_local.orb_features = n_features
    return _thread_local.orb


# ─────────────────────────────────────────────────────────────
# TEMPLATE CACHE — invalidates on (path, orb_features)
# ─────────────────────────────────────────────────────────────

class TemplateCache:
    """
    Loads a golden-template image once and exposes its ORB keypoints /
    descriptors.  After load() returns the object is read-only, so worker
    threads may safely read .kp / .des / .shape without any lock.

    Cache is invalidated when either the file path OR orb_features changes.
    """

    def __init__(self):
        self._lock         = threading.Lock()
        self._path         = None
        self._orb_features = None
        self._img          = None
        self._kp           = None
        self._des          = None

    def load(self, path: str, orb_features: int = 500):
        with self._lock:
            if (path == self._path
                    and orb_features == self._orb_features
                    and self._img is not None):
                return

            img = cv2.imread(path)
            if img is None:
                raise RuntimeError(f"Cannot read template: {path}")

            orb     = cv2.ORB_create(orb_features)
            kp, des = orb.detectAndCompute(img, None)

            if des is None:
                raise RuntimeError("ORB found no features in template")

            self._path         = path
            self._orb_features = orb_features
            self._img          = img
            self._kp           = kp
            self._des          = des

    @property
    def img(self):   return self._img
    @property
    def kp(self):    return self._kp
    @property
    def des(self):   return self._des
    @property
    def shape(self): return self._img.shape[:2]


# Shared singleton used by vision.pipeline
_template_cache = TemplateCache()


# ─────────────────────────────────────────────────────────────
# LABEL CLASS
# ─────────────────────────────────────────────────────────────

class Label:

    def __init__(self, img: np.ndarray, box: tuple, idx: int,
                 json_out_dir: str = ".",
                 orb_features: int = 500,
                 debug: bool = False,
                 target_format: str = "DataMatrix"):
        self.img           = img
        self.id            = idx
        self.x, self.y, self.w, self.h = box
        self._json_out_dir = json_out_dir
        self._orb_features = orb_features
        self._debug        = debug
        self._target_format = target_format

        self.aligned_img         = None
        self.code                = None
        self.dmx_poly            = None
        self.align_ok            = False
        self.align_fail_reason: Optional[str] = None
        self.rotation_angle: float = 0.0   # góc xoay so với template (độ)
        self.flipped:        bool  = False  # True = label đặt ngược (>90°)

        self.H_matrix = None
        self._H_inv   = None

    def get_roi(self) -> np.ndarray:
        return self.img[self.y:self.y + self.h, self.x:self.x + self.w]

    # ── Alignment ────────────────────────────

    def align_to_template(self, cache: TemplateCache):
        """
        Uses thread-local ORB — no object construction overhead, no lock
        contention between worker threads.
        """
        roi = self.get_roi()
        if roi.size == 0:
            self.align_fail_reason = "empty ROI"
            return

        orb       = _get_orb(self._orb_features)
        kp2, des2 = orb.detectAndCompute(roi, None)

        if cache.des is None or des2 is None:
            self.align_fail_reason = "no ORB descriptors"
            return

        matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(
            cache.des, des2
        )

        if len(matches) < 10:
            self.align_fail_reason = f"too few ORB matches: {len(matches)}"
            return

        src_pts = np.float32(
            [kp2[m.trainIdx].pt for m in matches]
        ).reshape(-1, 1, 2)

        dst_pts = np.float32(
            [cache.kp[m.queryIdx].pt for m in matches]
        ).reshape(-1, 1, 2)

        H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5)

        if H is None:
            self.align_fail_reason = "findHomography returned None"
            return

        if abs(np.linalg.det(H)) < 1e-6:
            self.align_fail_reason = "homography is near-singular"
            return

        # ── Orientation check ─────────────────────────────────
        # arctan2(H[1,0], H[0,0]) gives the in-plane rotation angle.
        # |angle| > 90° means the label is rotated more than a quarter turn
        # compared to the template — almost always means it was placed upside-down.
        angle = float(np.degrees(np.arctan2(H[1, 0], H[0, 0])))
        self.rotation_angle = round(angle, 1)
        self.flipped        = abs(angle) > 90
        # ─────────────────────────────────────────────────────

        self.H_matrix = H
        self._H_inv   = np.linalg.inv(H)

        th, tw = cache.shape
        self.aligned_img = cv2.warpPerspective(roi, H, (tw, th))
        self.align_ok    = True

    # ── DMX region mapping ───────────────────

    def map_box_back(self, dx: int, dy: int, w: int, h: int):
        if self._H_inv is None:
            return None

        pts = np.float32([
            [dx,     dy    ],
            [dx + w, dy    ],
            [dx + w, dy + h],
            [dx,     dy + h],
        ]).reshape(-1, 1, 2)

        pts_back = cv2.perspectiveTransform(pts, self._H_inv)
        pts_back[:, 0, 0] += self.x
        pts_back[:, 0, 1] += self.y
        return pts_back.astype(int)

    # ── Decode ───────────────────────────────

    def decode_dmx(self, dx: int, dy: int, w: int, h: int):
        if self.aligned_img is None:
            return

        ah, aw = self.aligned_img.shape[:2]
        x0 = max(0, min(dx,     aw - 1))
        y0 = max(0, min(dy,     ah - 1))
        x1 = max(0, min(dx + w, aw))
        y1 = max(0, min(dy + h, ah))

        roi = self.aligned_img[y0:y1, x0:x1]
        if roi.size == 0:
            return

        # Debug I/O only when requested — no silent disk writes in production.
        if self._debug:
            debug_dir = os.path.join(self._json_out_dir, "debug_roi")
            os.makedirs(debug_dir, exist_ok=True)
            aligned_dbg = self.aligned_img.copy()
            cv2.rectangle(aligned_dbg, (x0, y0), (x1, y1), (0, 255, 255), 2)
            cv2.imwrite(
                os.path.join(debug_dir, f"label{self.id:02d}_aligned.png"),
                aligned_dbg,
            )
            cv2.imwrite(
                os.path.join(debug_dir, f"label{self.id:02d}_roi.png"),
                roi,
            )

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # zxing tried first (faster on clean aligned ROIs); generator yields
        # lazily so later/expensive variants are never computed once one
        # succeeds.
        # pylibdmtx can only ever decode DataMatrix — skip calling it
        # entirely when the user has configured a different target format
        # (e.g. QRCode), it would never match anyway.
        use_libdmtx = self._target_format == "DataMatrix"

        for variant in self._variants(gray):
            code = self._decode_zxing(variant)
            if not code and use_libdmtx:
                code = self._decode_libdmtx(variant)
            if code:
                self.code     = code
                self.dmx_poly = self.map_box_back(dx, dy, w, h)
                return

    def _decode_zxing(self, gray: np.ndarray) -> Optional[str]:
        try:
            for r in zxingcpp.read_barcodes(gray):
                if r.format.name == self._target_format:
                    return r.text
        except Exception:
            pass
        return None

    def _decode_libdmtx(self, gray: np.ndarray) -> Optional[str]:
        try:
            r = pylibdmtx.decode(gray)
            return r[0].data.decode("utf-8") if r else None
        except Exception:
            return None

    def _variants(self, gray: np.ndarray) -> Generator[np.ndarray, None, None]:
        """
        Yield image variants one at a time, cheapest first.
        Because decode_dmx() returns on the first successful decode,
        a success on variant 1 means variants 2-5 are never computed.
        """
        yield gray                                                    # 1. raw

        clahe = cv2.createCLAHE(2.0, (8, 8))
        yield clahe.apply(gray)                                       # 2. CLAHE

        _, th = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        yield th                                                      # 3. Otsu

        yield cv2.adaptiveThreshold(                                  # 4. adaptive
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 2,
        )

        yield cv2.filter2D(                                           # 5. sharpen
            gray, -1,
            np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        )

    # ── Drawing ──────────────────────────────

    def draw_debug(self, dbg: np.ndarray):
        x, y, w, h = self.x, self.y, self.w, self.h
        color = (0, 255, 0) if self.code else (0, 0, 255)
        cv2.rectangle(dbg, (x, y), (x + w, y + h), color, 2)
        if self.dmx_poly is not None:
            cv2.polylines(dbg, [self.dmx_poly], True, (255, 0, 0), 2)
        label_text = f"[{self.id}] {self.code if self.code else 'NG'}"
        cv2.putText(dbg, label_text, (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        # Cảnh báo đặt ngược — chữ cam bên dưới bounding box
        if self.flipped:
            cv2.putText(dbg,
                        f"FLIP {self.rotation_angle:.0f}deg",
                        (x, y + h + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 255), 2)

    # ── Serialisation ────────────────────────

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "align_ok":       self.align_ok,
            "label": {
                "x": self.x, "y": self.y,
                "w": self.w, "h": self.h,
            },
            "align_fail":     self.align_fail_reason,
            "rotation_angle": self.rotation_angle,
            "flipped":        self.flipped,
            "dmx":            {"code": self.code},
        }

