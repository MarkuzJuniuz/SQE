"""The land / water map that ships with SQE: sqe/data/theatres/<theatre>_water.json, a condensed copy of what DCS itself answers about its surface.

Cell codes: 0 land (roads and runways included), 1 small water (ponds, wide rivers), 2 shallow water (rivers, river mouths, shallows), 3 sea or a big lake.
Coordinates are DCS's: x north, y east, metres. Everything here returns None when the theatre has no map (or the point is off it), so callers fall back
to the coarse coastline in seacheck.py.
"""
from __future__ import annotations
import base64
import json
import math
import zlib
from pathlib import Path

LAND, SMALL_WATER, SHALLOW_WATER, SEA = 0, 1, 2, 3
RIVER_MARGIN = 100.0               # a site keeps this far from shallow water / rivers; the open-sea margin is passed in by the caller (judgment call)

_M = None                          # the active theatre's map: dict | None
_LOADED = False                    # True once the active theatre's file has been looked for
_SHIPPED: dict = {}                # theatre id -> parsed map (or None)
_OFFS: dict = {}


def theatre_changed() -> None:
    """The active theatre changed: forget the loaded map and read the new theatre's when it is next asked for."""
    global _M, _LOADED
    _M, _LOADED = None, False
    _OFFS.clear()


def parse(d: dict) -> dict:
    """A shipped water file's dict -> the map: `cells` is base64 of zlib of one byte per cell, rows (along x) one after the other."""
    nx, ny = int(d["nx"]), int(d["ny"])
    cells = zlib.decompress(base64.b64decode(d["cells"]))
    rows = []
    for i in range(nx):
        rows.append(cells[i * ny:(i + 1) * ny])
    return {"x0": float(d["x0"]), "y0": float(d["y0"]), "step": float(d["step"]), "nx": nx, "ny": ny, "rows": rows, "source": str(d.get("source", ""))}


def _shipped():
    """The water map of the active theatre, or None when its pack ships none (or the file is unreadable)."""
    from . import theatres
    th = theatres.active()
    theatre_id = th.get("id", "")
    if theatre_id not in _SHIPPED:
        found = None
        try:
            path = Path(th.get("_dir", "")) / f"{theatre_id}_water.json"
            if path.is_file():
                found = parse(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            found = None
        _SHIPPED[theatre_id] = found
    return _SHIPPED[theatre_id]


def _map():
    global _M, _LOADED
    if not _LOADED:
        found = _shipped()                  # may switch the default theatre on, which calls theatre_changed()
        _M, _LOADED = found, True
    return _M


def available() -> bool:
    return _map() is not None


def _cell(m: dict, x: float, y: float):
    i, j = int((x - m["x0"]) // m["step"]), int((y - m["y0"]) // m["step"])
    if 0 <= i < m["nx"] and 0 <= j < m["ny"]:
        return m["rows"][i][j]
    return None


def _offsets(step: float, margin: float) -> list:
    """The cells round a point that lie within `margin` of it, as (distance, rows away, columns away), nearest first."""
    key = int(margin)
    if key not in _OFFS:
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
    """True when (x, y) is land with no sea / lake within `margin` and no river within RIVER_MARGIN. None when there is no map or the point is off it."""
    m = _map()
    if m is None or _cell(m, x, y) is None:
        return None
    step = m["step"]
    ci, cj = int((x - m["x0"]) // step), int((y - m["y0"]) // step)
    river = min(margin, RIVER_MARGIN)
    for d, di, dj in _offsets(step, margin):
        i, j = ci + di, cj + dj
        if 0 <= i < m["nx"] and 0 <= j < m["ny"]:
            code = m["rows"][i][j]
            if code == LAND:
                continue
            if code == SEA:
                return False                      # sea or a big lake within the shore margin
            if d <= river + step * 0.71:
                return False                      # a river, pond or shallows too close (or the site is in it)
    return True


def is_sea(x: float, y: float):
    """True when the point itself is in the sea or a big lake (rivers and ponds do not count). None when there is no map or the point is off it."""
    m = _map()
    if m is None:
        return None
    code = _cell(m, x, y)
    if code is None:
        return None
    return code == SEA
