"""Land / sea tests on the embedded coastline (DCS coordinates: x north, y east, metres). Used to keep ships in open water."""
from __future__ import annotations
import math

_RINGS = None


def _rings():
    global _RINGS
    if _RINGS is None:
        from . import theatres
        _RINGS = [r for r in theatres.geo()["land"] if len(r) >= 3]
    return _RINGS


def reset() -> None:
    """Forget the cached coastline (the active theatre changed)."""
    global _RINGS
    _RINGS = None


def _inside(x, y, ring):
    c = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                c = not c
    return c


def is_land(x, y):
    return any(_inside(x, y, r) for r in _rings())


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def coast_distance(x, y):
    """Metres to the nearest coastline segment."""
    best = 1e12
    for r in _rings():
        n = len(r)
        for i in range(n):
            a, b = r[i], r[(i + 1) % n]
            best = min(best, _seg_dist(x, y, a[0], a[1], b[0], b[1]))
    return best


def open_water(x, y, clearance_m):
    return (not is_land(x, y)) and coast_distance(x, y) >= clearance_m


def clear_run(x, y, hdg_deg, length_m, clearance_m, step_m=9260):
    """True when a straight run of length_m from (x, y) on hdg stays in open water."""
    h = math.radians(hdg_deg)
    d = 0.0
    while d <= length_m + 1:
        px, py = x + d * math.cos(h), y + d * math.sin(h)
        if not open_water(px, py, clearance_m):
            return False
        d += step_m
    return True


SITE_MARGIN = 1500.0                 # metres a ground site keeps from the sea (rivers: terrainmask.RIVER_MARGIN); set from Settings


def site_ok(x, y, margin=None):
    """True when a ground site can sit here: on land, clear of the sea by `margin`. Uses the map DCS measured (terrainmask) when the terrain
    scan has been run and covers the point, otherwise the coarse built-in coastline."""
    margin = SITE_MARGIN if margin is None else margin
    from . import terrainmask
    r = terrainmask.land_ok(x, y, margin)
    if r is not None:
        return r
    return is_land(x, y) and coast_distance(x, y) >= margin


def snap_to_land(x, y, margin_m=None, max_m=40000.0):
    """The nearest point to (x, y) where site_ok holds (the point itself when it already does). Searches outward in 1 km rings, every 15 degrees,
    preferring the point furthest from the water on the first ring that has any. Returns the original when nothing is found."""
    if site_ok(x, y, margin_m):
        return x, y
    r = 1000.0
    while r <= max_m:
        best = None
        for k in range(24):
            a = math.radians(k * 15)
            px, py = x + r * math.cos(a), y + r * math.sin(a)
            if site_ok(px, py, margin_m):
                cd = coast_distance(px, py)
                if best is None or cd > best[0]:
                    best = (cd, px, py)
        if best is not None:
            return best[1], best[2]
        r += 1000.0
    return x, y
