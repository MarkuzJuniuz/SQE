"""Threat map: SAM rings, the FLOT/gatekeeper rule, safe tanker stations, egress steering, corridor sites.

The rule that keeps the war logical: a target is only offered if the straight route to it does not cross an intact
SAM ring that sits IN FRONT of the target (closer to us by more than 15 nm). Blocking sites are promoted to DEAD
objectives instead, so the war advances belt by belt instead of jumping straight to deep targets.
"""
from __future__ import annotations
import math
from .models import AssetKind

NM = 1852.0
RANGE_NM = {"SA-8": 7, "AAA": 3, "MANPAD": 3, "SA-2": 25, "SA-3": 13, "SA-6": 13, "SA-11": 18, "SA-10": 48, "SA-15": 8, "SA-19": 5}
SERIOUS_NM = 8          # shorter-ranged systems do not block routes (they only matter at the target)


def rings(state, min_range: float = SERIOUS_NM) -> list:
    out = []
    for a in state.assets.values():
        if a.kind == AssetKind.SAM and not a.destroyed and a.health > 0.25:
            r = RANGE_NM.get(a.variant, 0)
            if r >= min_range:
                out.append((a, r * NM))
    return out


def seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def poly_dist(px, py, pts) -> float:
    return min(seg_dist(px, py, *pts[i], *pts[i + 1]) for i in range(len(pts) - 1))


def cluster_ids(target_asset) -> set:
    return set() if target_asset is None else {target_asset.id, *target_asset.defended_by}


def blockers(state, base_xy, target_xy, target_asset=None, margin_nm: float = 8, front_nm: float = 15) -> list:
    """Intact SAM sites the route crosses that are in front of the target (the FLOT/gatekeeper rule)."""
    bx, by = base_xy
    tx, ty = target_xy
    d_t = math.hypot(tx - bx, ty - by)
    skip = cluster_ids(target_asset)
    out = []
    for a, r in rings(state):
        if a.id in skip:
            continue
        if seg_dist(a.x, a.y, bx, by, tx, ty) < r + margin_nm * NM and math.hypot(a.x - bx, a.y - by) < d_t - front_nm * NM:
            out.append(a)
    return out


def fighter_bases(state) -> list:
    return [(state.assets[w.base_asset_id].x, state.assets[w.base_asset_id].y) for w in state.enemy_air
            if w.available > 0 and not state.assets[w.base_asset_id].destroyed]


def tanker_station(state, base_xy, toward_xy, min_enemy_nm: float = 150, ring_margin_nm: float = 20):
    """A tanker track behind the FLOT: far from enemy fighter bases and outside every SAM ring. None if no such spot."""
    bx, by = base_xy
    mx, my = toward_xy
    enemies = fighter_bases(state)
    rs = rings(state, min_range=3)
    for f in (0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.1):
        x, y = bx + (mx - bx) * f, by + (my - by) * f
        if enemies and min(math.hypot(x - ex, y - ey) for ex, ey in enemies) / NM < min_enemy_nm:
            continue
        if any(math.hypot(x - a.x, y - a.y) < r + ring_margin_nm * NM for a, r in rs):
            continue
        return x, y
    return None


def safe_egress(state, tx, ty, hdg, egr_nm, skip_ids=()):
    """Pick the egress bearing that stays clear of live SAM rings (target cluster excluded)."""
    rs = [(a, r) for a, r in rings(state) if a.id not in skip_ids]
    best, best_clear = None, -1e18
    for off in (100, -100, 150, -150, 60, -60, 180):
        h = math.radians(hdg + off)
        x, y = tx + egr_nm * NM * math.cos(h), ty + egr_nm * NM * math.sin(h)
        clear = min((math.hypot(x - a.x, y - a.y) - r for a, r in rs), default=1e12)
        if clear > 5 * NM:
            return x, y
        if clear > best_clear:
            best, best_clear = (x, y), clear
    return best


MAX_ROUTE_SITES = 2     # SAM sites that merely touch the route (not the target's own cluster) that are spawned: keeps VR frame rate sane


def corridor_sam_sites(state, polyline, target_asset, margin_nm: float = 10, max_route: int = MAX_ROUTE_SITES) -> list:
    """The target's own SAM cluster, plus the few live sites whose ring reaches deepest into the route corridor."""
    skip = cluster_ids(target_asset)
    out, route = [], []
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed:
            continue
        r = RANGE_NM.get(a.variant, 0) * NM
        near_target = target_asset is not None and math.hypot(a.x - target_asset.x, a.y - target_asset.y) < 12_000
        if a.id in skip or near_target:
            out.append(a)
        elif r >= SERIOUS_NM * NM and poly_dist(a.x, a.y, polyline) < r + margin_nm * NM:
            route.append((r - poly_dist(a.x, a.y, polyline), a))
    route.sort(key=lambda t: t[0], reverse=True)
    return out + [a for _, a in route[:max_route]]


def point_back_along(poly, d_back: float):
    """Position d_back metres back from the END of a polyline, and the heading to the next point."""
    pts = list(poly)
    remaining = d_back
    for i in range(len(pts) - 1, 0, -1):
        (x1, y1), (x0, y0) = pts[i], pts[i - 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        if remaining <= seg:
            f = 1.0 - remaining / max(seg, 1e-9)
            return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f), i
        remaining -= seg
    return pts[0], 1


def safe_marshal(state, base_xy, hdg_to_target, min_enemy_nm: float = 90, ring_margin_nm: float = 20):
    """Marshal point BEHIND the base: well away from enemy fighter bases and at least ring_margin_nm outside every SAM ring.
    Tries close-in first, directly behind, then swings to the sides. Returns the best spot found (never None)."""
    bx, by = base_xy
    enemies = fighter_bases(state)
    rs = rings(state, min_range=3)
    back = hdg_to_target + 180
    best, best_slack = None, -1e18
    for nm in (15, 20, 25, 32, 40, 50, 62):
        for ang in (0, 35, -35, 70, -70, 105, -105):
            h = math.radians(back + ang)
            x, y = bx + nm * NM * math.cos(h), by + nm * NM * math.sin(h)
            slack = min([(math.hypot(x - ex, y - ey) / NM) - min_enemy_nm for ex, ey in enemies] +
                        [(math.hypot(x - a.x, y - a.y) - r) / NM - ring_margin_nm for a, r in rs] + [1e9])
            if slack >= 0:
                return x, y
            if slack > best_slack:
                best, best_slack = (x, y), slack
    return best


def first_safe_egress(state, tx, ty, hdg_to_target, skip_ids=(), min_nm: float = 8, max_nm: float = 60, margin_nm: float = 4, avoid=()):
    """EGR = the FIRST safe point after the target: the closest point (8 nm and out) that is clear of every live SAM ring (plus a margin).
    Bearings that turn for home are tried first; among equals, the one farther from enemy fighter bases wins (away from their CAP).
    avoid = [(x, y, nm)] extra keep-out circles (enemy CAP stations, fighter bases).
    Returns None when nothing within max_nm is clear (the caller falls back to safe_egress)."""
    rs = [(a, r) for a, r in rings(state, min_range=3) if a.id not in skip_ids]
    enemies = fighter_bases(state)
    best, best_score = None, 1e18
    for k, off in enumerate((150, -150, 120, -120, 180, 90, -90, 60, -60)):
        h = math.radians(hdg_to_target + off)
        r = min_nm
        while r <= max_nm:
            x, y = tx + r * NM * math.cos(h), ty + r * NM * math.sin(h)
            if all(math.hypot(x - a.x, y - a.y) >= rr + margin_nm * NM for a, rr in rs) and \
                    all(math.hypot(x - ax, y - ay) >= anm * NM for ax, ay, anm in avoid):
                far = min((math.hypot(x - ex, y - ey) for ex, ey in enemies), default=0) / NM
                score = r - 0.08 * min(far, 150) + 0.4 * k
                if score < best_score:
                    best, best_score = (x, y), score
                break
            r += 2
    return best
