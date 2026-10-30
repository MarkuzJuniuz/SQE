"""Ground height measured by DCS itself (see terrainprobe.py). Read from <Saved Games>\\SQE\\SQE_relief_<theatre>.json.

A coarse grid (1 km cells in a scan). v0.41.200: without a scan of their own the app uses a built-in 2 km grid made from XO's scan (sqe/data/theatres/<id>_relief.json,
written by tools/sqe_scan.py condense); a scan, when there is one, wins.
A coarse grid (1 km cells by default). Each cell holds the HIGHEST ground in it (for safe altitudes, so a narrow ridge is never missed) and the
AVERAGE ground (for line of sight). Heights are stored in units of 10 m. Coordinates are DCS's: x north, y east, metres.

Everything here returns None when there is no relief file (or the point is off the grid), so callers keep their old behaviour.
The line-of-sight test is an approximation (1 km cells, 4/3-earth radar horizon): good enough to choose a profile, not a guarantee.
"""
from __future__ import annotations
import base64
import json
import math
import sys
import time
import zlib
from array import array
from pathlib import Path

NM = 1852.0
FT = 0.3048
UNIT_M = 10.0
EARTH_R = 6_371_000.0 * 4.0 / 3.0          # effective radius for the radar horizon
ANTENNA_M = 10.0

_R = None                                  # dict | None
_DIR = None
_MTIME = None
_CHECKED = 0.0
_FIXED = False                             # a grid installed by from_grid (tests): never reloaded from disk
_BUILTIN = False                           # engine.py asks for the built-in grid when the player has no scan of their own
_SRC = ""                                  # "scan" | "built-in": where the loaded grid came from
_SHIPPED: dict = {}                        # theatre id -> parsed built-in grid (or None)


def _file() -> str:
    from . import theatres
    sc = theatres.active()["scan"]
    return sc.get("relief_file") or sc["file"].replace("terrain", "relief")


def theatre_changed() -> None:
    global _R, _MTIME, _CHECKED, _FIXED
    _R, _MTIME, _CHECKED, _FIXED = None, None, 0.0, False
    if _DIR is not None:
        _refresh(force=True)


def configure(folder, builtin: bool = False) -> None:
    """Look for the player's own scan in `folder`. builtin=True (the app): without one, use the grid that ships with SQE (v0.41.200)."""
    global _DIR, _R, _MTIME, _CHECKED, _FIXED, _BUILTIN
    _DIR = Path(folder) if folder else None
    _BUILTIN = bool(builtin)
    _R, _MTIME, _CHECKED, _FIXED = None, None, 0.0, False
    _refresh(force=True)


def _parse(d: dict) -> dict:
    def rows(key):
        return [array("H", (int(v) for v in r.split())) for r in d[key]]
    return {"x0": float(d["x0"]), "y0": float(d["y0"]), "step": float(d["step"]), "nx": int(d["nx"]), "ny": int(d["ny"]),
            "max": rows("max"), "mean": rows("mean")}


def _parse_packed(d: dict) -> dict:
    """The built-in grid (written by tools/sqe_scan.py condense): `max` / `mean` are base64 of zlib of little-endian int16 differences between neighbouring
    cells along a row, rows one after the other, in 10 m units."""
    nx, ny = int(d["nx"]), int(d["ny"])

    def grid(key):
        a = array("h")
        a.frombytes(zlib.decompress(base64.b64decode(d[key])))
        if sys.byteorder == "big":
            a.byteswap()
        rows = []
        for i in range(nx):
            row, v = array("H"), 0
            for dv in a[i * ny:(i + 1) * ny]:
                v += dv
                row.append(v)
            rows.append(row)
        return rows
    return {"x0": float(d["x0"]), "y0": float(d["y0"]), "step": float(d["step"]), "nx": nx, "ny": ny, "max": grid("max"), "mean": grid("mean")}


def _shipped():
    """The built-in ground-height grid of the active theatre (sqe/data/theatres/<id>_relief.json), or None."""
    from . import theatres
    th = theatres.active()
    tid = th.get("id", "")
    if tid not in _SHIPPED:
        g = None
        try:
            p = Path(th.get("_dir", "")) / f"{tid}_relief.json"
            if p.is_file():
                g = _parse_packed(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            g = None
        _SHIPPED[tid] = g
    return _SHIPPED[tid]


def _refresh(force: bool = False) -> None:
    global _R, _MTIME, _CHECKED, _SRC
    if _FIXED:
        return
    now = time.time()
    if not force and now - _CHECKED < 3.0:
        return
    _CHECKED = now
    if _DIR is not None:
        p = _DIR / _file()
        try:
            mt = p.stat().st_mtime
        except OSError:
            mt = None
        if mt is not None:
            if mt == _MTIME and _R is not None and _SRC == "scan":
                return
            try:
                _R = _parse(json.loads(p.read_text(encoding="utf-8")))
                _MTIME, _SRC = mt, "scan"
                return
            except Exception:
                pass
    _R, _MTIME, _SRC = None, None, ""
    if _BUILTIN:
        g = _shipped()
        if g is not None:
            _R, _SRC = g, "built-in"


def from_grid(x0: float, y0: float, step: float, hi: list, mean: list | None = None) -> None:
    """Install a grid directly (tests, tools). hi / mean: rows[i][j] in metres, i along x, j along y."""
    global _R, _MTIME, _FIXED
    mean = mean or hi
    conv = lambda g: [array("H", (int(round(v / UNIT_M)) for v in r)) for r in g]
    _R = {"x0": float(x0), "y0": float(y0), "step": float(step), "nx": len(hi), "ny": len(hi[0]), "max": conv(hi), "mean": conv(mean)}
    _MTIME, _FIXED = -1.0, True


def clear() -> None:
    global _R, _FIXED
    _R, _FIXED = None, True               # "no relief", and stay that way until configure()


def available() -> bool:
    _refresh()
    return _R is not None


def info() -> str:
    _refresh()
    if _R is None:
        return "not scanned yet"
    if _SRC == "built-in":
        return f"built-in grid ({_R['nx']} x {_R['ny']} cells of {int(_R['step'])} m; run the terrain scan for a finer one)"
    top = max(max(r) for r in _R["max"] if len(r)) * UNIT_M
    return f"loaded ({_R['nx']} x {_R['ny']} cells of {int(_R['step'])} m, highest ground {int(top):,} m / {int(top / FT):,} ft)"


def _cell(x: float, y: float):
    r = _R
    i, j = int((x - r["x0"]) // r["step"]), int((y - r["y0"]) // r["step"])
    if 0 <= i < r["nx"] and 0 <= j < r["ny"]:
        return i, j
    return None


def ground_m(x: float, y: float, kind: str = "mean"):
    """Ground height in metres at a point, or None."""
    _refresh()
    if _R is None:
        return None
    c = _cell(x, y)
    return None if c is None else _R[kind][c[0]][c[1]] * UNIT_M


def max_near_m(x: float, y: float, radius_m: float):
    """Highest ground within radius_m of a point (square window of cells), or None."""
    _refresh()
    if _R is None:
        return None
    st = _R["step"]
    i0, i1 = int((x - radius_m - _R["x0"]) // st), int((x + radius_m - _R["x0"]) // st)
    j0, j1 = int((y - radius_m - _R["y0"]) // st), int((y + radius_m - _R["y0"]) // st)
    best = None
    for i in range(max(0, i0), min(_R["nx"] - 1, i1) + 1):
        row = _R["max"][i]
        seg = row[max(0, j0):min(_R["ny"] - 1, j1) + 1]
        if len(seg):
            m = max(seg)
            best = m if best is None or m > best else best
    return None if best is None else best * UNIT_M


def leg_max_ft(a, b, corridor_m: float = 5 * NM):
    """Highest ground within corridor_m of the straight leg a -> b, in feet; None without relief (or when the leg is off the grid)."""
    _refresh()
    if _R is None:
        return None
    d = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(1, int(d // (_R["step"] * 0.5)))
    best = None
    for k in range(n + 1):
        f = k / n
        h = max_near_m(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, corridor_m)
        if h is not None and (best is None or h > best):
            best = h
    return None if best is None else best / FT


def msa_ft(points, corridor_m: float = 5 * NM):
    """Minimum safe altitude along a route: the highest ground within corridor_m of any leg plus 1,000 ft (2,000 ft over mountains, where the
    highest ground is above 5,000 ft), rounded up to 500 ft. None without relief."""
    hi = None
    for a, b in zip(points, points[1:]):
        h = leg_max_ft(a, b, corridor_m)
        if h is not None and (hi is None or h > hi):
            hi = h
    if hi is None:
        return None
    margin = 2000 if hi > 5000 else 1000
    return int(math.ceil((hi + margin) / 500.0) * 500)


def los_clear(site, site_agl_m: float, pt, pt_agl_m: float, step_m: float | None = None) -> bool | None:
    """Can a radar at `site` (antenna site_agl_m above the ground) see an aircraft at `pt` flying pt_agl_m above the ground? Average ground
    along the line against the straight line, with the earth's curvature at 4/3 radius. None without relief."""
    _refresh()
    if _R is None:
        return None
    g0, g1 = ground_m(site[0], site[1]), ground_m(pt[0], pt[1])
    if g0 is None or g1 is None:
        return None
    h0, h1 = g0 + site_agl_m, g1 + pt_agl_m
    d = math.hypot(pt[0] - site[0], pt[1] - site[1])
    step = step_m or _R["step"] * 0.5
    n = int(d // step)
    for k in range(1, n):
        f = k / n
        x, y = site[0] + (pt[0] - site[0]) * f, site[1] + (pt[1] - site[1]) * f
        g = ground_m(x, y)
        if g is None:
            continue
        line = h0 + (h1 - h0) * f - (d * f) * (d * (1 - f)) / (2.0 * EARTH_R)
        if g > line:
            return False
    return True


def visible_fraction(site, route, agl_ft: float, range_m: float):
    """Share of the route (points sampled every 2 km) inside range_m of the site that a radar there can see at agl_ft above the ground.
    None without relief or when no part of the route is in range."""
    _refresh()
    if _R is None:
        return None
    seen = tot = 0
    for a, b in zip(route, route[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(d // 2000.0))
        for k in range(n + 1):
            f = k / n
            p = (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)
            if math.hypot(p[0] - site[0], p[1] - site[1]) > range_m:
                continue
            v = los_clear(site, ANTENNA_M, p, agl_ft * FT)
            if v is None:
                continue
            tot += 1
            seen += 1 if v else 0
    return None if tot == 0 else seen / tot
