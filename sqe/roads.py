"""Road points measured by DCS itself (see terrainprobe.py). Read from <Saved Games>\\SQE\\SQE_roads_<theatre>.json.

The scan mission asks land.getClosestPointOnRoads('roads', x, y) on a coarse grid and keeps the distinct road points it gets back (rounded to 50 m).
A snap is then "the nearest of those points, if one is close enough". It is a point cloud, not a road graph, so it puts a column or a supply site
ON a road; it does not route along one.

Everything returns None when there is no roads file, so callers keep their old behaviour. Coordinates are DCS's: x north, y east, metres.
"""
from __future__ import annotations
import json
import math
import time
from pathlib import Path

BUCKET_M = 5000.0
_P = None                       # {(bx, by): [(x, y), ...]} | None
_DIR = None
_MTIME = None
_CHECKED = 0.0
_FIXED = False                  # points installed by from_points (tests): never reloaded from disk


def _file() -> str:
    from . import theatres
    sc = theatres.active()["scan"]
    return sc.get("roads_file") or sc["file"].replace("terrain", "roads")


def theatre_changed() -> None:
    global _P, _MTIME, _CHECKED, _FIXED
    _P, _MTIME, _CHECKED, _FIXED = None, None, 0.0, False
    if _DIR is not None:
        _refresh(force=True)


def configure(folder) -> None:
    global _DIR, _P, _MTIME, _CHECKED, _FIXED
    _DIR = Path(folder) if folder else None
    _P, _MTIME, _CHECKED, _FIXED = None, None, 0.0, False
    _refresh(force=True)


def _index(pts) -> dict:
    out = {}
    for x, y in pts:
        out.setdefault((int(x // BUCKET_M), int(y // BUCKET_M)), []).append((float(x), float(y)))
    return out


def _refresh(force: bool = False) -> None:
    global _P, _MTIME, _CHECKED
    if _FIXED:
        return
    now = time.time()
    if not force and now - _CHECKED < 3.0:
        return
    _CHECKED = now
    if _DIR is None:
        _P = None
        return
    p = _DIR / _file()
    try:
        mt = p.stat().st_mtime
    except OSError:
        _P, _MTIME = None, None
        return
    if mt == _MTIME and _P is not None:
        return
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        _P = _index((int(a), int(b)) for a, b in d["pts"]) if d.get("pts") else None
        _MTIME = mt
    except Exception:
        _P, _MTIME = None, None


def from_points(pts) -> None:
    """Install road points directly (tests, tools)."""
    global _P, _MTIME, _FIXED
    _P, _MTIME, _FIXED = _index(pts), -1.0, True


def clear() -> None:
    global _P, _FIXED
    _P, _FIXED = None, True


def available() -> bool:
    _refresh()
    return _P is not None


def info() -> str:
    _refresh()
    if _P is None:
        return "not scanned yet"
    return f"loaded ({sum(len(v) for v in _P.values()):,} road points)"


def snap(x: float, y: float, max_m: float = 3000.0):
    """The nearest road point within max_m of (x, y) as (x, y), or None (no roads file, or none that close)."""
    _refresh()
    if _P is None:
        return None
    r = int(max_m // BUCKET_M) + 1
    bx, by = int(x // BUCKET_M), int(y // BUCKET_M)
    best, bd = None, max_m
    for i in range(bx - r, bx + r + 1):
        for j in range(by - r, by + r + 1):
            for px, py in _P.get((i, j), ()):
                d = math.hypot(px - x, py - y)
                if d <= bd:
                    best, bd = (px, py), d
    return best
