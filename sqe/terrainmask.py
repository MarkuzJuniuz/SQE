"""Land / water mask measured by DCS itself (see terrainprobe.py). Read from <Saved Games>\\SQE\\SQE_terrain_<theatre>.json.

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


def _file() -> str:
    from . import theatres
    return theatres.active()["scan"]["file"]


def theatre_changed() -> None:
    """The active theatre changed: drop the loaded mask and look for the new theatre's scan."""
    global _M, _MTIME, _CHECKED
    _M, _MTIME, _CHECKED = None, None, 0.0
    _OFFS.clear()
    if _DIR is not None:
        _refresh(force=True)

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
    p = _DIR / _file()
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
    out = {"x0": float(d["x0"]), "y0": float(d["y0"]), "step": float(d["step"]), "nx": int(d["nx"]), "ny": int(d["ny"]), "rows": rows}
    out["big"] = _big_water(out)
    return out


BLOCK = 4                      # cells per block side for the water-body classification (1 km at the default 250 m)
BIG_BLOCKS = 40                # a water body of at least this many blocks (about 40 km2) counts as sea / big lake


def _big_water(m: dict):
    """DCS reports rivers, ponds and the sea alike as water. Label 1 km blocks that are mostly water, find their connected bodies, and keep
    the large ones (the sea, big lakes): those get the full shore margin. Everything else (rivers, small lakes) gets the river margin."""
    nx, ny, rows = m["nx"], m["ny"], m["rows"]
    bx, by = (nx + BLOCK - 1) // BLOCK, (ny + BLOCK - 1) // BLOCK
    wet = [bytearray(by) for _ in range(bx)]
    half = BLOCK * BLOCK // 2
    for bi in range(bx):
        sub = rows[bi * BLOCK:(bi + 1) * BLOCK]
        for bj in range(by):
            n = 0
            for r in sub:
                n += r[bj * BLOCK:(bj + 1) * BLOCK].count(1)
            if n > half:
                wet[bi][bj] = 1
    big = [bytearray(by) for _ in range(bx)]
    seen = [bytearray(by) for _ in range(bx)]
    for si in range(bx):
        for sj in range(by):
            if wet[si][sj] and not seen[si][sj]:
                comp, stack = [], [(si, sj)]
                seen[si][sj] = 1
                while stack:
                    a, b = stack.pop()
                    comp.append((a, b))
                    for c, d in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
                        if 0 <= c < bx and 0 <= d < by and wet[c][d] and not seen[c][d]:
                            seen[c][d] = 1
                            stack.append((c, d))
                if len(comp) >= BIG_BLOCKS:
                    for a, b in comp:
                        big[a][b] = 1
    return big


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
    big = m["big"]
    for d, di, dj in _offsets(margin):
        i, j = ci + di, cj + dj
        if 0 <= i < m["nx"] and 0 <= j < m["ny"]:
            c = m["rows"][i][j]
            if c == 0:
                continue
            if c == 1 and big[i // BLOCK][j // BLOCK]:
                return False                      # sea or a big lake within the shore margin
            if d <= river + step * 0.71:
                return False                      # a river, pond or shallows too close (or the site is in it)
    return True


def scanned(folder) -> list:
    """The theatres that have a terrain scan in `folder`: [(theatre, 'YYYY-MM-DD')]. Reads only the first bytes of each file."""
    out = []
    if not folder:
        return out
    for p in sorted(Path(folder).glob("SQE_terrain_*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                head = f.read(200)
            mt = re.search(r'"terrain"\s*:\s*"([^"]+)"', head)
            out.append((mt.group(1) if mt else p.stem[len("SQE_terrain_"):].title(), time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))))
        except OSError:
            continue
    return out
