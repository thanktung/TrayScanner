"""
logic/export.py — RCS export logic, extracted out of the UI layer so it can
be reused (and unit-tested) without opening a Qt window.
"""

import json
import os


def load_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def export_rcs(json_path: str, export_dir: str, filename: str = "rcs.txt") -> str:
    """
    Read a pipeline result JSON (list of label dicts with .dmx.code) and
    write only the successfully-decoded ones as "<id>:<code>" lines.

    Returns the path written to.
    """
    os.makedirs(export_dir, exist_ok=True)
    out_path = os.path.join(export_dir, filename)

    data = load_json(json_path)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in data:
            code = r.get("dmx", {}).get("code") or "NG"
            if code == "NG":
                continue
            f.write(f"{r.get('id')}:{code}\n")

    return out_path
