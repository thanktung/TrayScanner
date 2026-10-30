"""
vision/detection.py — Label detection strategies.

Two interchangeable detectors:
    - OpenCV morphology (detect_white_labels)   — no extra ML dependency
    - YOLOv8 (detect_labels_yolo)                — needs ultralytics/torch

NOTE: `ultralytics` (and therefore `torch`) is imported LAZILY inside
detect_labels_yolo(), not at module top level. This means a user who only
ever selects detector="opencv" never needs torch installed/working at all —
avoids forcing a heavy (and on some Windows machines, DLL-fragile) torch
dependency onto code paths that do not need it.
"""

import threading
from typing import Optional

import cv2
import numpy as np
import zxingcpp


# ─────────────────────────────────────────────────────────────
# SORTING — shared by both detectors
# ─────────────────────────────────────────────────────────────

def sort_top_left(boxes: list, row_tol: Optional[int] = None) -> list:
    if not boxes:
        return boxes

    if row_tol is None:
        heights = [h for _, _, _, h in boxes]
        row_tol = max(10, int(np.median(heights) * 0.6))

    rows: list[list] = []
    for b in sorted(boxes, key=lambda b: b[1]):
        for row in rows:
            if abs(row[0][1] - b[1]) < row_tol:
                row.append(b)
                break
        else:
            rows.append([b])

    for row in rows:
        row.sort(key=lambda b: b[0])

    return [b for row in rows for b in row]


# ─────────────────────────────────────────────────────────────
# MODEL CACHE (YOLO)  — thread-safe, lazily loads ultralytics
# ─────────────────────────────────────────────────────────────

class ModelCache:

    def __init__(self):
        self._lock  = threading.Lock()
        self._model = None
        self._path  = None

    def load(self, path: str):
        # Lazy import: only touches `ultralytics`/`torch` when YOLO detector
        # is actually used.
        from ultralytics import YOLO

        with self._lock:
            if self._model is None or self._path != path:
                self._model = YOLO(path)
                self._path  = path
            return self._model


_model_cache = ModelCache()


# ─────────────────────────────────────────────────────────────
# DETECTION — YOLO
# ─────────────────────────────────────────────────────────────

def detect_labels_yolo(img, model_path: str,
                       imgsz: int = 1280, conf: float = 0.5) -> list:
    model = _model_cache.load(model_path)
    res   = model(img, imgsz=imgsz, conf=conf, verbose=False)[0]
    boxes = res.boxes.xyxy.cpu().numpy()

    H, W = img.shape[:2]
    pad  = 20
    out  = []

    for x1, y1, x2, y2 in boxes:
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        x = max(0, x1 - pad)
        y = max(0, y1 - pad)
        w = min(W - x, x2 - x1 + pad * 2)
        h = min(H - y, y2 - y1 + pad * 2)
        out.append((x, y, w, h))

    return sort_top_left(out)


# ─────────────────────────────────────────────────────────────
# DETECTION — OPENCV
# ─────────────────────────────────────────────────────────────

def tighten_white(gray_roi: np.ndarray, margin: int = 4) -> tuple:
    _, th = cv2.threshold(gray_roi, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    if th.mean() < 127:
        th = cv2.bitwise_not(th)

    k  = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, k, iterations=1)

    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h_img, w_img = gray_roi.shape

    if not cnts:
        return 0, 0, w_img, h_img

    x, y, w, h = cv2.boundingRect(max(cnts, key=cv2.contourArea))
    x = max(0, x - margin)
    y = max(0, y - margin)
    w = min(w_img - x, w + 2 * margin)
    h = min(h_img - y, h + 2 * margin)
    return x, y, w, h


def detect_white_labels(
    img_bgr:        np.ndarray,
    clahe_clip:     float = 3.0,
    clahe_tile:     int   = 16,
    tophat_ksize:   int   = 61,
    blur_ksize:     int   = 9,
    close_ksize:    int   = 15,
    min_area:       int   = 25000,
    ratio_min:      float = 0.55,
    ratio_max:      float = 1.5,
    min_w:          int   = 120,
    min_h:          int   = 120,
    max_h:          int   = 500,
    tighten_margin: int   = 4,
) -> list:
    tophat_ksize = tophat_ksize | 1
    blur_ksize   = blur_ksize   | 1
    close_ksize  = close_ksize  | 1

    gray  = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip,
                            tileGridSize=(clahe_tile, clahe_tile))
    gray  = clahe.apply(gray)

    k_wh     = cv2.getStructuringElement(cv2.MORPH_RECT,
                                         (tophat_ksize, tophat_ksize))
    whitehat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, k_wh)

    blur = cv2.GaussianBlur(whitehat, (blur_ksize, blur_ksize), 0)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    k  = cv2.getStructuringElement(cv2.MORPH_RECT, (close_ksize, close_ksize))
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, k, iterations=1)

    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        ratio = w / h if h > 0 else 0
        if (w * h > min_area
                and ratio_min < ratio < ratio_max
                and w > min_w
                and min_h < h < max_h):
            boxes.append((x, y, w, h))

    boxes = sort_top_left(boxes)

    final = []
    for x, y, w, h in boxes:
        tx, ty, tw, th_ = tighten_white(gray[y:y + h, x:x + w],
                                        margin=tighten_margin)
        final.append((x + tx, y + ty, tw, th_))

    return final



# ─────────────────────────────────────────────────────────────
# FORMAT FILTER — drop boxes that are clearly a DIFFERENT barcode type
# (e.g. the tray's own QR code sticker, which the detector sometimes
# mistakes for a label because it is also a small white/square-ish blob).
# ─────────────────────────────────────────────────────────────

def filter_boxes_by_format(img_bgr: np.ndarray, boxes: list,
                            target_format: str = "DataMatrix") -> list:
    """
    Quick, cheap pre-check (no ORB alignment needed) run on each raw
    candidate box BEFORE the expensive per-label pipeline: if zxingcpp can
    already read a barcode in the *unaligned* crop and its format does not
    match target_format, the box is dropped entirely (not counted, not
    aligned, not decoded) instead of ending up as a confusing "NG" result.

    Boxes where nothing decodes yet (the normal case for a DataMatrix that
    still needs perspective alignment) are kept unchanged — this function
    only REMOVES boxes it can positively identify as "the wrong code type",
    it never invents new ones.

    target_format: "" / None disables filtering (keeps old behaviour).
    """
    if not target_format:
        return boxes

    kept = []
    for box in boxes:
        x, y, w, h = box
        roi = img_bgr[y:y + h, x:x + w]
        if roi.size == 0:
            kept.append(box)
            continue

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        try:
            results = zxingcpp.read_barcodes(gray)
        except Exception:
            results = []

        has_wrong_format = any(r.format.name != target_format for r in results)
        if has_wrong_format:
            continue  # vd: phát hiện QRCode của tray trong khi target là DataMatrix

        kept.append(box)

    return kept
