"""
logic/settings.py — Load/save persisted app configuration.

Pure logic, no PyQt5 / no hardware dependency — safe to import from a
future CLI tool or test suite without pulling in the GUI stack.
"""

import json
import os

from vision.pipeline import DEFAULT_CONFIG

SETTINGS_FILE = "D:/Travis/H08_TrayScanner/config/aoi_settings.json"


def load_settings() -> dict:
    """Load settings from disk, falling back to DEFAULT_CONFIG when missing."""
    cfg = dict(DEFAULT_CONFIG)
    cfg.setdefault("golden_path",    "D:/Travis/H08_TrayScanner/assets/golden_h08.png")
    cfg.setdefault("raw_dir",        "D:/project/raw_images")
    cfg.setdefault("export_dir",     "D:/RCS")
    cfg.setdefault("required_count", 0)
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    return cfg


def save_settings(cfg: dict):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        # NOTE: write WITHOUT a UTF-8 BOM — json.load(..., encoding="utf-8")
        # (no "-sig") cannot parse a BOM and would silently fail, falling
        # back to defaults. Do not swap this for `Set-Content -Encoding
        # UTF8` from PowerShell, which adds a BOM.
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as exc:
        print(f"[CẢNH BÁO] Không thể lưu cài đặt: {exc}")
