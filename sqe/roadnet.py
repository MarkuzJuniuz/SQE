"""The road network, measured by DCS itself (queue item m, step 2; XO 2026-11-03).

land.findPathOnRoads (probe result 2026-11-03: dense polylines, about 100 m between points, fast, mountain passes included) is run in DCS by
tools/road_net_scan.py between neighbouring airfields and sector centres. This module turns the raw answer into two shipped things:
  * `simplify` / `build_net`: each route cut down to a few hundred points (Douglas-Peucker, ROUTE_TOLERANCE_M), written to <theatre>_roads_net.json;
  * `spots_along` / `road_spots`: supply spots laid along the routes every SPOT_SPACING_M (5 km), set ROAD_OFFSET_M off the road (alternating sides, so a
    depot does not sit on the tarmac), no two closer than MIN_SEPARATION_M. They go into the sites file under the key "road" (supply), where a later
    step (queue item i: more supply sites, defenders, quotas) draws from them. Nothing in a campaign reads the key yet.
Judgment calls (no public figure): the 5 km spacing (XO's choice), the 150 m offset, the 3 km separation, the 100 m tolerance."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROUTE_TOLERANCE_M = 100.0     # Douglas-Peucker tolerance: a route may deviate this far from the measured polyline
SPOT_SPACING_M = 5000.0       # one supply spot per this much road (XO 2026-11-03: 5 km; was 10 km in the first draft)
ROAD_OFFSET_M = 150.0         # spots sit this far beside the road, alternating sides
MIN_SEPARATION_M = 3000.0     # two spots (from overlapping routes) closer than this are one


def simplify(pts, tol: float = ROUTE_TOLERANCE_M) -> list:
    """Douglas-Peucker on a list of (x, y); keeps both ends. Iterative (routes have thousands of points)."""
    n = len(pts)
    if n < 3:
        return [tuple(p) for p in pts]
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        far, far_d = -1, tol
        for i in range(a + 1, b):
            px, py = pts[i]
            d = math.hypot(px - ax, py - ay) if L == 0 else abs(dy * (px - ax) - dx * (py - ay)) / L
            if d > far_d:
                far, far_d = i, d
        if far >= 0:
            keep[far] = True
            stack.append((a, far))
            stack.append((far, b))
    return [tuple(pts[i]) for i in range(n) if keep[i]]


def spots_along(route, spacing: float = SPOT_SPACING_M, offset: float = ROAD_OFFSET_M, start_side: int = 1) -> list:
    """Points every `spacing` metres along a route, `offset` metres to the left / right of it (alternating). The first sits one spacing in, so two
    routes meeting at an airfield do not both put a spot on it."""
    out, side, run, nxt = [], start_side, 0.0, spacing
    for (x0, y0), (x1, y1) in zip(route, route[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg <= 0:
            continue
        while run + seg >= nxt:
            f = (nxt - run) / seg
            px, py = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
            nx, ny = -(y1 - y0) / seg, (x1 - x0) / seg                 # left-hand normal
            out.append((round(px + side * offset * nx), round(py + side * offset * ny)))
            side = -side
            nxt += spacing
        run += seg
    return out


def road_spots(routes, existing=(), spacing: float = SPOT_SPACING_M, min_sep: float = MIN_SEPARATION_M) -> list:
    """Supply spots for every route, deduplicated: a spot within `min_sep` of an accepted one (or of an `existing` point) is dropped."""
    keep = [tuple(p) for p in existing]
    new = []
    for r in routes:
        for p in spots_along(r, spacing):
            if all(math.hypot(p[0] - q[0], p[1] - q[1]) >= min_sep for q in keep):
                keep.append(p)
                new.append(p)
    return new


def routes_from_raw(raw) -> list:
    """The raw scan file (a list of {"pair", "kind", "pts"}) -> simplified road routes (railroads and empty answers skipped), longest first."""
    out = []
    for o in raw:
        if o.get("kind") != "roads" or len(o.get("pts") or []) < 2:
            continue
        out.append(simplify([tuple(p) for p in o["pts"]]))
    out.sort(key=lambda r: -sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(r, r[1:])))
    return out


def build_net(raw, theatre_dir, theatre_id: str = "caucasus", spacing: float = SPOT_SPACING_M) -> dict:
    """Write <theatre>_roads_net.json (the simplified routes) and add {"road": {"supply": [...]}} to the sites file. Returns a summary dict."""
    theatre_dir = Path(theatre_dir)
    routes = routes_from_raw(raw)
    total_km = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for r in routes for a, b in zip(r, r[1:])) / 1000.0
    sites_p = theatre_dir / f"{theatre_id}_sites.json"
    sites = json.loads(sites_p.read_text(encoding="utf-8"))
    old = [tuple(p) for sec in sites.get("sectors", []) for p in sec.get("supply", [])] + [tuple(p) for f in sites.get("fields", []) for p in f.get("supply", [])]
    spots = road_spots(routes, existing=old, spacing=spacing)
    net_p = theatre_dir / f"{theatre_id}_roads_net.json"
    net_p.write_text(json.dumps({"terrain": theatre_id, "version": 1, "tolerance_m": ROUTE_TOLERANCE_M,
                                 "routes": [[[round(x), round(y)] for x, y in r] for r in routes]}, separators=(",", ":")), encoding="utf-8")
    sites["road"] = {"spacing_m": spacing, "offset_m": ROAD_OFFSET_M, "min_sep_m": MIN_SEPARATION_M, "supply": [[x, y] for x, y in spots]}
    sites_p.write_text(json.dumps(sites, separators=(",", ":")), encoding="utf-8")
    return {"routes": len(routes), "points": sum(len(r) for r in routes), "km": round(total_km), "spots": len(spots)}
