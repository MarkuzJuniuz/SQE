"""Land / water mask measured by DCS itself (see terrainprobe.py). Read from <Saved Games>\\SQE\\SQE_terrain_caucasus.json.

Cell codes: 0 land (roads and runways included), 1 water (sea and lakes), 2 shallow water (rivers, river mouths, shallows).
Coordinates are DCS's: x north, y east, metres. Everything here returns None when there is no mask (or the point is off it),
so callers can fall back to the coarse coastline in seacheck.py.
"""
from __future__ import annotations
import json
import math
import re
import time
from pathlib import Path

FILE = "SQE_terrain_caucasus.json"
RIVER_MARGIN = 100.0               # a site keeps this far from shallow water / rivers; the open-sea margin is passed in by the caller

_M = None                          # dict | None
_DIR = None
_MTIME = None
_CHECKED = 0.0
_OFFS: dict = {}


def configure(folder) -> None:
    global _DIR, _MTIME, _M, _CHECKED
    _DIR = Path(folder) if folder else None
    _MTIME, _M, _CHECKED = None, None, 0.0
    _refresh(force=True)


def _refresh(force: bool = False) -> None:
    global _M, _MTIME, _CHECKED
    now = time.time()
    if not force and now - _CHECKED < 3.0:
        return
    _CHECKED = now
    if _DIR is None:
        _M = None
        return
    p = _DIR / FILE
    try:
        mt = p.stat().st_mtime
    except OSError:
        _M, _MTIME = None, None
        return
    if mt == _MTIME and _M is not None:
        return
    try:
        _M = _parse(json.loads(p.read_text(encoding="utf-8")))
        _MTIME = mt
    except Exception:
        _M, _MTIME = None, None


def _parse(d: dict) -> dict:
    code = {"l": 0, "w": 1, "s": 2}
    rows = []
    for r in d["rows"]:
        buf = bytearray()
        for m in re.finditer(r"([lws])(\d+)", r):
            buf += bytes([code[m.group(1)]]) * int(m.group(2))
        rows.append(bytes(buf))
    return {"x0": float(d["x0"]), "y0": float(d["y0"]), "step": float(d["step"]), "nx": int(d["nx"]), "ny": int(d["ny"]), "rows": rows}


def available() -> bool:
    _refresh()
    return _M is not None


def info() -> str:
    _refresh()
    if _M is None:
        return "not scanned yet (using the coarse built-in coastline)"
    return f"loaded ({_M['nx']} x {_M['ny']} cells of {int(_M['step'])} m, measured by DCS)"


def _cell(x: float, y: float):
    m = _M
    i, j = int((x - m["x0"]) // m["step"]), int((y - m["y0"]) // m["step"])
    if 0 <= i < m["nx"] and 0 <= j < m["ny"]:
        return m["rows"][i][j]
    return None


def _offsets(margin: float):
    key = int(margin)
    if key not in _OFFS:
        step = _M["step"]
        n = int(math.ceil((margin + step) / step))
        out = []
        for di in range(-n, n + 1):
            for dj in range(-n, n + 1):
                d = math.hypot(di, dj) * step
                if d <= margin + step * 0.71:
                    out.append((d, di, dj))
        out.sort()
        _OFFS[key] = out
    return _OFFS[key]


def land_ok(x: float, y: float, margin: float = 1500.0):
    """True when (x, y) is land with no sea / lake within `margin` and no river within RIVER_MARGIN. None when there is no mask or the point is off it."""
    _refresh()
    if _M is None:
        return None
    if _cell(x, y) is None:
        return None
    m = _M
    step = m["step"]
    ci, cj = int((x - m["x0"]) // step), int((y - m["y0"]) // step)
    river = min(margin, RIVER_MARGIN)
    for d, di, dj in _offsets(margin):
        i, j = ci + di, cj + dj
        if 0 <= i < m["nx"] and 0 <= j < m["ny"]:
            c = m["rows"][i][j]
            if c == 1 or (c == 2 and d <= river + step * 0.71):
                return False
    return True
