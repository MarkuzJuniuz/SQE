"""Road points taken from the shipped road net (sqe/data/theatres/<theatre>_roads_net.json, routes DCS itself drove between airfields and sector centres).

A snap is "the nearest road point, if one is close enough". It puts a column ON a road so that DCS drives it along the road; it does not route along one.
A theatre with no road net has no road points, and its columns drive across country. Coordinates are DCS's: x north, y east, metres.
"""
from __future__ import annotations
import math

BUCKET_M = 5000.0
POINT_SPACING_M = 200.0          # the net's routes are simplified to long straight pieces (within 100 m of the road): points are laid along them this far apart (judgment call)
_P = None                        # {(bx, by): [(x, y), ...]} | None
_LOADED = False
_BY_THEATRE: dict = {}           # theatre id -> indexed points (or None)


def theatre_changed() -> None:
    """The active theatre changed: read the new theatre's road net when it is next asked for."""
    global _P, _LOADED
    _P, _LOADED = None, False


def _points_along(route) -> list:
    """Points every POINT_SPACING_M along a route of (x, y) pairs, its own corners included."""
    out = []
    for (x0, y0), (x1, y1) in zip(route, route[1:]):
        steps = max(1, int(math.ceil(math.hypot(x1 - x0, y1 - y0) / POINT_SPACING_M)))
        for step in range(steps):
            out.append((x0 + (x1 - x0) * step / steps, y0 + (y1 - y0) * step / steps))
    if route:
        out.append((route[-1][0], route[-1][1]))
    return out


def _index(points) -> dict:
    out = {}
    for x, y in points:
        out.setdefault((int(x // BUCKET_M), int(y // BUCKET_M)), []).append((float(x), float(y)))
    return out


def _shipped():
    """The indexed road points of the active theatre, or None when its pack ships no road net."""
    from . import road_front, theatres
    th = theatres.active()
    theatre_id = th.get("id", "")
    if theatre_id not in _BY_THEATRE:
        points = []
        for route in road_front.routes(th) or []:
            points += _points_along(route)
        _BY_THEATRE[theatre_id] = _index(points) if points else None
    return _BY_THEATRE[theatre_id]


def _loaded_points():
    global _P, _LOADED
    if not _LOADED:
        found = _shipped()                  # may switch the default theatre on, which calls theatre_changed()
        _P, _LOADED = found, True
    return _P


def available() -> bool:
    return _loaded_points() is not None


def snap(x: float, y: float, max_m: float = 3000.0):
    """The nearest road point within max_m of (x, y) as (x, y), or None (no road net, or no road that close)."""
    points = _loaded_points()
    if points is None:
        return None
    reach = int(max_m // BUCKET_M) + 1
    bx, by = int(x // BUCKET_M), int(y // BUCKET_M)
    best, best_distance = None, max_m
    for i in range(bx - reach, bx + reach + 1):
        for j in range(by - reach, by + reach + 1):
            for px, py in points.get((i, j), ()):
                distance = math.hypot(px - x, py - y)
                if distance <= best_distance:
                    best, best_distance = (px, py), distance
    return best
