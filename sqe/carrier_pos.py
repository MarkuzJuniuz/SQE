"""Where the carrier sits, day by day (v0.41.159, XO 2026-10-27: "the carrier moves along the campaign").

The fleet stays CARRIER_STANDOFF_NM clear of every red airfield that red still holds (the fiction: shore-based anti-ship cruise missiles; the real
reason is that nothing red launches near it survives), at least CARRIER_COAST_NM off the coast (deck ops need open water), and as near the front line as
those rules allow. It moves at most CARRIER_MOVE_KM a day and does not bother for less than CARRIER_STAY_KM. As red fields fall the standoff circle
shrinks and the fleet closes in. All constants are judgment calls (XO: "100 sounds about right")."""
from __future__ import annotations
import math
from . import ground, seacheck
from .models import AssetKind, BaseKind

NM = 1852.0
CARRIER_STANDOFF_NM = 100.0     # from the theatre pack's `carrier_standoff_nm` when it has one (XO 2026-10-27)
CARRIER_COAST_NM = 25.0         # the same clearance mission_builder.carrier_station asks for
CARRIER_MOVE_KM = 150.0         # a carrier group makes about 30 kt: 150 km is about 4 hours' steaming at 20 kt, a day's repositioning with room to spare (judgment call)
CARRIER_STAY_KM = 30.0          # hysteresis: a better spot closer than this is not worth the move
GRID_KM = 20.0


def standoff_nm(state) -> float:
    from . import theatres
    return float(theatres.active().get("carrier", {}).get("carrier_standoff_nm", CARRIER_STANDOFF_NM))


def _red_fields(state) -> list:
    taken = set((state.ground or {}).get("taken", []))
    return [(a.x, a.y) for a in state.assets.values() if a.kind == AssetKind.AIRFIELD and not a.destroyed and a.id not in taken]


def _ok(x, y, fields, stand_m) -> bool:
    if any(math.hypot(x - fx, y - fy) < stand_m for fx, fy in fields):
        return False
    return seacheck.open_water(x, y, CARRIER_COAST_NM * NM)


def best_spot(state, max_move_km: float | None) -> tuple | None:
    """-> (x, y) of the best allowed spot within max_move_km of the carrier now (None: unlimited), or None when no spot is allowed."""
    cv = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
    if cv is None or not ground.active(state):
        return None
    fields, stand_m = _red_fields(state), standoff_nm(state) * NM
    lx, ly = ground.line_xy(state.ground)
    reach = (max_move_km * 1000.0) if max_move_km is not None else 1e12
    step = GRID_KM * 1000.0
    best, bd = None, None
    xs = [a.x for a in state.assets.values()] + [b.x for b in state.bases.values()]
    ys = [a.y for a in state.assets.values()] + [b.y for b in state.bases.values()]
    x0, x1, y0, y1 = min(xs) - 250000, max(xs) + 250000, min(ys) - 250000, max(ys) + 250000
    cx = x0
    while cx <= x1:
        cy = y0
        while cy <= y1:
            if math.hypot(cx - cv.x, cy - cv.y) <= reach:
                d = math.hypot(cx - lx, cy - ly)
                if (bd is None or d < bd) and _ok(cx, cy, fields, stand_m):
                    best, bd = (cx, cy), d
            cy += step
        cx += step
    return best


def update(state) -> str | None:
    """Move the fleet for the new day (once per day; a replan the same day changes nothing). -> a log line when it moved, else None."""
    g = state.ground
    if not g or g.get("cv_day") == state.day:
        return None
    cv = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
    if cv is None or not ground.active(state):
        return None
    first = "cv_day" not in g
    g["cv_day"] = state.day
    spot = best_spot(state, None if first else CARRIER_MOVE_KM)
    if spot is None:
        return None
    lx, ly = ground.line_xy(g)
    now_ok = _ok(cv.x, cv.y, _red_fields(state), standoff_nm(state) * NM)
    if not first and now_ok and math.hypot(cv.x - lx, cv.y - ly) - math.hypot(spot[0] - lx, spot[1] - ly) < CARRIER_STAY_KM * 1000.0:
        return None
    moved = math.hypot(spot[0] - cv.x, spot[1] - cv.y) / 1000.0
    if moved < 1.0:
        return None
    cv.x, cv.y = spot
    return f"{cv.name} repositions {moved:.0f} km {'to its station' if first else 'along the front'}, {standoff_nm(state):.0f} nm clear of the red airfields."
