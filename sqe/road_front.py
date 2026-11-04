"""Which side a road site belongs to: the side its road connects to (v0.41.258, XO 2026-11-03).

XO: "on campaign starts everything from the front connected to the road and away from it belongs to that side... road connections cut by the front is an easier thing
to digest". The measured road net (roadnet.py, `<theatre>_roads_net.json`, 69 routes that join into one network) is the map of who can reach what:
  * the front is a cut across the roads at the line of sectors (`ground.path_pos`: how far along the line of sector centres a point is, against `line_km`);
  * a road point near the line of sectors is on the side of the cut it lies on; a point far from it (north of the mountains, the Georgian plain) takes the side of the road it
    hangs on, i.e. of the last side the road came from, and the end of the road has the side of the nearest airfield;
  * a site belongs to the side of the road point it sits beside.
Used twice: `road_sites.build` (who owns a site at the start of a campaign) and `road_sites.flip` (the night the front cuts a site off from its owner, it changes hands).
No radii and no margins. A theatre with no road net returns None and the callers keep the old nearest-airfield rule."""
from __future__ import annotations

import json
import math
from pathlib import Path

CORRIDOR_KM = 60.0            # a road point this near the line of sectors is judged by the cut (judgment call)
SNAP_M = 3000.0               # a site this near a road point is "on" that road
_ROUTES: dict = {}


def routes(th: dict):
    """The road routes of a theatre pack ([[ (x, y), ... ], ...]) or None when it has none."""
    tid = th.get("id", "")
    if tid in _ROUTES:
        return _ROUTES[tid]
    r = None
    try:
        p = Path(th.get("_dir", "")) / f"{tid}_roads_net.json"
        if p.is_file():
            r = [[(float(x), float(y)) for x, y in rt] for rt in json.loads(p.read_text(encoding="utf-8")).get("routes", []) if len(rt) >= 2] or None
    except (OSError, ValueError):
        r = None
    _ROUTES[tid] = r
    return r


_AP: dict = {}


def airports(th: dict) -> dict:
    """{airport name: (x, y)} of the theatre (from the terrain, once)."""
    tid = th.get("id", "")
    if tid not in _AP:
        from . import theatres
        _AP[tid] = {n: (a.position.x, a.position.y) for n, a in theatres.terrain().airports.items()}
    return _AP[tid]


def field_side(th: dict, x: float, y: float) -> str:
    """The side of the airfield nearest a point: blue if it is one of the theatre's blue-side airports (`road_blue_airports`), else red (the same rule as before v0.41.258)."""
    ap = airports(th)
    blue = set(th.get("road_blue_airports") or [])
    near = min(ap, key=lambda n: math.hypot(ap[n][0] - x, ap[n][1] - y))
    return "blue" if near in blue else "red"


def cut_side(state, x: float, y: float):
    """'red' / 'blue' by the cut across the line of sectors, or None when the point is not near that line."""
    from . import ground
    g = state.ground
    k, lat = ground.path_pos(g, x, y)
    if lat > CORRIDOR_KM:
        return None
    return "red" if k < float(g.get("line_km", ground.line_km(g))) else "blue"


def route_sides(state, th: dict, rts: list) -> list:
    """Per route, the side of each of its points. Anchors: the points near the front (the cut) and the two ends of the road (the side of the nearest airfield). Every other
    point takes the side of the nearest anchor along the road."""
    out = []
    for r in rts:
        n = len(r)
        cum = [0.0]
        for i in range(1, n):
            cum.append(cum[-1] + math.hypot(r[i][0] - r[i - 1][0], r[i][1] - r[i - 1][1]))
        anch = {i: cut_side(state, *r[i]) for i in range(n)}
        anch = {i: s for i, s in anch.items() if s}
        anch.setdefault(0, field_side(th, *r[0]))
        anch.setdefault(n - 1, field_side(th, *r[n - 1]))
        idx = sorted(anch)
        sides, j = [], 0
        for i in range(n):
            while j + 1 < len(idx) and abs(cum[idx[j + 1]] - cum[i]) <= abs(cum[idx[j]] - cum[i]):
                j += 1
            sides.append(anch[idx[j]])
        out.append(sides)
    return out


def site_side(state, th: dict, rts: list, sides: list, x: float, y: float) -> str:
    """The side a site beside a road belongs to. Not near any road: by the cut, else by the nearest airfield."""
    best, hit = SNAP_M, None
    for ri, r in enumerate(rts):
        for pi in range(len(r) - 1):                                    # the nearest stretch of road (spots lie beside a stretch, the vertices can be km apart)
            ax, ay = r[pi]; bx, by = r[pi + 1]
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / max(1.0, dx * dx + dy * dy)))
            d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
            if d < best:
                best, hit = d, (ri, pi if t < 0.5 else pi + 1)
    if hit is not None:
        return sides[hit[0]][hit[1]]
    return cut_side(state, x, y) or field_side(th, x, y)
