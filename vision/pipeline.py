"""
vision/pipeline.py — Unified AOI pipeline orchestration.

Wires together detection (vision.detection) + alignment/decode (vision.label)
into a single run_pipeline() call, with a thread pool for parallel per-label
processing and an optional progress callback for GUI integration.
"""

import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from typing import Optional, Callable

import cv2

from .detection import detect_labels_yolo, detect_white_labels, filter_boxes_by_format
from .label import Label, _template_cache


# ─────────────────────────────────────────────────────────────
# DEFAULT CONFIG  (overridable via run_pipeline() kwargs)
# ─────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "model_path":        r"D:\Travis\H08_TrayScanner\runs\detect\train-2\weights\best.pt",
    "img_out_dir":       "D:/project/result_images",
    "json_out_dir":      "D:/project/result_json",
    "label_timeout":     30,
    "yolo_imgsz":        1280,
    "yolo_conf":         0.5,
    "orb_features":      500,
    "dmx_dx":            120,
    "dmx_dy":            90,
    "dmx_w":             100,
    "dmx_h":             100,
    "detector":          "opencv",
    "debug":             False,   # True → ghi debug_roi images ra disk
    # Chỉ nhận 1 loại mã — box nào zxingcpp đọc ra loại KHÁC (vd QRCode của
    # tray) sẽ bị loại bỏ trước khi align/decode. "" = tắt lọc.
    "target_format":     "DataMatrix",
    # ── OpenCV white-label detection ──────────────────────────
    "cv_clahe_clip":     3.0,
    "cv_clahe_tile":     16,
    "cv_tophat_ksize":   61,
    "cv_blur_ksize":     9,
    "cv_close_ksize":    15,
    "cv_min_area":       25000,
    "cv_ratio_min":      0.55,
    "cv_ratio_max":      1.5,
    "cv_min_w":          120,
    "cv_min_h":          120,
    "cv_max_h":          500,
    "cv_tighten_margin": 4,
}


# ─────────────────────────────────────────────────────────────
# PIPELINE
# ─────────────────────────────────────────────────────────────

def run_pipeline(
    img_path:      str,
    golden_path:   str,
    # ── paths ──────────────────────────────────────────────
    img_out_dir:   str   = DEFAULT_CONFIG["img_out_dir"],
    json_out_dir:  str   = DEFAULT_CONFIG["json_out_dir"],
    # ── detector ───────────────────────────────────────────
    detector:      str   = DEFAULT_CONFIG["detector"],
    model_path:    str   = DEFAULT_CONFIG["model_path"],
    yolo_imgsz:    int   = DEFAULT_CONFIG["yolo_imgsz"],
    yolo_conf:     float = DEFAULT_CONFIG["yolo_conf"],
    # ── opencv detection ───────────────────────────────────
    cv_clahe_clip:     float = DEFAULT_CONFIG["cv_clahe_clip"],
    cv_clahe_tile:     int   = DEFAULT_CONFIG["cv_clahe_tile"],
    cv_tophat_ksize:   int   = DEFAULT_CONFIG["cv_tophat_ksize"],
    cv_blur_ksize:     int   = DEFAULT_CONFIG["cv_blur_ksize"],
    cv_close_ksize:    int   = DEFAULT_CONFIG["cv_close_ksize"],
    cv_min_area:       int   = DEFAULT_CONFIG["cv_min_area"],
    cv_ratio_min:      float = DEFAULT_CONFIG["cv_ratio_min"],
    cv_ratio_max:      float = DEFAULT_CONFIG["cv_ratio_max"],
    cv_min_w:          int   = DEFAULT_CONFIG["cv_min_w"],
    cv_min_h:          int   = DEFAULT_CONFIG["cv_min_h"],
    cv_max_h:          int   = DEFAULT_CONFIG["cv_max_h"],
    cv_tighten_margin: int   = DEFAULT_CONFIG["cv_tighten_margin"],
    # ── alignment ──────────────────────────────────────────
    orb_features:  int   = DEFAULT_CONFIG["orb_features"],
    # ── dmx roi ────────────────────────────────────────────
    dmx_dx:        int   = DEFAULT_CONFIG["dmx_dx"],
    dmx_dy:        int   = DEFAULT_CONFIG["dmx_dy"],
    dmx_w:         int   = DEFAULT_CONFIG["dmx_w"],
    dmx_h:         int   = DEFAULT_CONFIG["dmx_h"],
    # ── misc ───────────────────────────────────────────────
    label_timeout: int   = DEFAULT_CONFIG["label_timeout"],
    debug:         bool  = DEFAULT_CONFIG["debug"],
    target_format: str   = DEFAULT_CONFIG["target_format"],
    # progress callback(n_done, n_total) — GUI can show per-label progress
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """
    Run the full AOI pipeline on one image.

    progress_cb(n_done, n_total): called from worker threads after each label
    finishes (success or failure). Use this to drive a GUI progress bar.
    The callback must be thread-safe (e.g. emit a Qt signal, not update a
    widget directly).
    """
    img = cv2.imread(img_path)
    if img is None:
        raise RuntimeError(f"Cannot read image: {img_path}")

    os.makedirs(img_out_dir,  exist_ok=True)
    os.makedirs(json_out_dir, exist_ok=True)

    base     = os.path.splitext(os.path.basename(img_path))[0]
    img_out  = os.path.join(img_out_dir,  f"{base}_result.png")
    json_out = os.path.join(json_out_dir, f"{base}.json")

    # ── Detection ────────────────────────────
    if detector == "yolo":
        boxes = detect_labels_yolo(img, model_path,
                                   imgsz=yolo_imgsz, conf=yolo_conf)
    elif detector == "opencv":
        boxes = detect_white_labels(
            img,
            clahe_clip     = cv_clahe_clip,
            clahe_tile     = cv_clahe_tile,
            tophat_ksize   = cv_tophat_ksize,
            blur_ksize     = cv_blur_ksize,
            close_ksize    = cv_close_ksize,
            min_area       = cv_min_area,
            ratio_min      = cv_ratio_min,
            ratio_max      = cv_ratio_max,
            min_w          = cv_min_w,
            min_h          = cv_min_h,
            max_h          = cv_max_h,
            tighten_margin = cv_tighten_margin,
        )
    else:
        raise ValueError(f"Unknown detector '{detector}' — use 'yolo' or 'opencv'")

    # ── Lọc mã sai loại (vd QRCode của tray bị detector bắt nhầm) ──
    boxes = filter_boxes_by_format(img, boxes, target_format=target_format)

    # ── Template ─────────────────────────────
    _template_cache.load(golden_path, orb_features=orb_features)

    labels = [
        Label(img, box, idx,
              json_out_dir=json_out_dir,
              orb_features=orb_features,
              debug=debug,
              target_format=target_format)
        for idx, box in enumerate(boxes, start=1)
    ]

    if not labels:
        cv2.imwrite(img_out, img)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)
        return {"image": img_out, "json": json_out, "count": 0}

    # ── Parallel processing ───────────────────
    n_total    = len(labels)
    n_workers  = min(n_total, os.cpu_count() or 4)
    done_lock  = threading.Lock()
    done_count = [0]   # list so inner closure can mutate it

    def _on_done():
        with done_lock:
            done_count[0] += 1
            n = done_count[0]
        if progress_cb is not None:
            try:
                progress_cb(n, n_total)
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_process_label, lb, dmx_dx, dmx_dy, dmx_w, dmx_h): lb
            for lb in labels
        }
        for future in as_completed(futures):
            lb = futures[future]
            try:
                future.result(timeout=label_timeout)
            except FuturesTimeout:
                print(f"[WARNING] Label {lb.id} timed out "
                      f"after {label_timeout}s — skipped")
            except Exception as exc:
                print(f"[WARNING] Label {lb.id} raised: {exc}")
            finally:
                _on_done()   # always report progress

    # ── Draw & save ───────────────────────────
    dbg     = img.copy()
    results = []

    for lb in labels:
        lb.draw_debug(dbg)
        results.append(lb.to_dict())

    cv2.imwrite(img_out, dbg)
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return {"image": img_out, "json": json_out, "count": len(results)}


# ─────────────────────────────────────────────────────────────
# INTERNAL WORKER
# ─────────────────────────────────────────────────────────────

def _process_label(lb: Label, dx: int, dy: int, w: int, h: int) -> Label:
    lb.align_to_template(_template_cache)
    lb.decode_dmx(dx, dy, w, h)
    return lb


# ─────────────────────────────────────────────────────────────
# CLI smoke test — `python -m vision.pipeline`
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    def _progress(done, total):
        bar = "#" * done + "." * (total - done)
        print(f"\r  [{bar}] {done}/{total}", end="", flush=True)

    run_pipeline(
        img_path    = "D:/project/raw_images/img20.png",
        golden_path = "D:/Travis/H08_TrayScanner/assets/golden_h08.png",
        detector    = "opencv",
        debug       = True,
        progress_cb = _progress,
    )
    print()


