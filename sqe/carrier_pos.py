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
BAND_KM = 80.0                  # S115 (XO 2026-11-20: "the carrier should be on a semi random spot ... to give it plausibility of not being found"): the station is drawn among the allowed spots no more than this much farther from the front than the nearest one (judgment call)
BAND_FIELD_NM = 30.0            # S120: a station is also never farther than this beyond the standoff from the nearest red airfield (a judgment call; the Hornets must be able to reach the front)
BAND_DAYS = 3                   # S115: a new spot is drawn every this many days (a seeded draw: the same campaign gives the same spots), so the fleet does not sit on one point
EVADE_NM = 215.0                # S115: a staged carrier raid: the fleet sails out to this far from every red airfield (S118: 215 = the Kh-22's reach as DCS flies it, `raid_spawns.RAID_REACH_NM` 208 nm, plus 7 nm margin, a judgment call; was 230; the pack's `carrier_evade_nm` replaces it) or, where the sea is too small, as far as it can get
EVADE_MOVE_KM = 250.0           # S115: the most the fleet moves in the day it runs from a raid (a carrier group makes 30 kt: 3 to 4 hours for the 100 nm it needs; the normal 150 km a day is the stay-on-station pace)


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
    from . import theatres
    mb = theatres.hook("map_box")                         # S90: a pack with a `map_box` (Syria) searches only inside it: the coastline file stops there, and beyond it every point reads "sea" (a 160 nm stand-off put the fleet inland in Turkey)
    if mb is not None:
        x0, x1, y0, y1 = max(x0, float(mb["x0"])), min(x1, float(mb["x1"])), max(y0, float(mb["y0"])), min(y1, float(mb["y1"]))
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


def _all_spots(state, max_move_km, fields, stand_m):
    """Every allowed spot within max_move_km of the carrier (None: unlimited), as (distance to the front, x, y)."""
    cv = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
    lx, ly = ground.line_xy(state.ground)
    reach = (max_move_km * 1000.0) if max_move_km is not None else 1e12
    step = GRID_KM * 1000.0
    xs = [a.x for a in state.assets.values()] + [b.x for b in state.bases.values()]
    ys = [a.y for a in state.assets.values()] + [b.y for b in state.bases.values()]
    x0, x1, y0, y1 = min(xs) - 250000, max(xs) + 250000, min(ys) - 250000, max(ys) + 250000
    from . import theatres
    mb = theatres.hook("map_box")
    if mb is not None:
        x0, x1, y0, y1 = max(x0, float(mb["x0"])), min(x1, float(mb["x1"])), max(y0, float(mb["y0"])), min(y1, float(mb["y1"]))
    out = []
    cx = x0
    while cx <= x1:
        cy = y0
        while cy <= y1:
            if math.hypot(cx - cv.x, cy - cv.y) <= reach and _ok(cx, cy, fields, stand_m):
                out.append((math.hypot(cx - lx, cy - ly), cx, cy))
            cy += step
        cx += step
    return out


def band_spot(state, max_move_km: float | None) -> tuple | None:
    """S115: a seeded draw among the allowed spots within BAND_KM of the best one (the pack's `carrier_band_km` replaces it), drawn once every BAND_DAYS days; -> ((x, y), whether the carrier is in the band now) or None.
    S120: the band is a DISC around the best spot (S115 measured the distance to the front, a ring that ran round the whole front) and no spot is more than BAND_FIELD_NM beyond the standoff from the nearest red airfield."""
    import random
    from . import theatres
    cv = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
    if cv is None or not ground.active(state):
        return None
    fields, stand_m = _red_fields(state), standoff_nm(state) * NM
    allp = _all_spots(state, None, fields, stand_m)
    if not allp:
        return None
    band_m = float((theatres.active().get("carrier") or {}).get("carrier_band_km", BAND_KM)) * 1000.0
    best = min(allp)                                                 # the best spot anywhere (nearest the front), not what is in reach today
    cap_m = stand_m + BAND_FIELD_NM * NM
    # Distance from a point to the nearest red field (0 when red has none).
    def nearest_red(x, y):
        return min(math.hypot(x - fx, y - fy) for fx, fy in fields) if fields else 0.0

    # A spot inside the band around the best spot and within reach of the red fields.
    def ok_band(x, y):
        return math.hypot(x - best[1], y - best[2]) <= band_m and nearest_red(x, y) <= cap_m

    in_band = ok_band(cv.x, cv.y)
    reach = (max_move_km * 1000.0) if max_move_km is not None else 1e12
    near = [s for s in allp if math.hypot(s[1] - cv.x, s[2] - cv.y) <= reach]
    pool = sorted((s[1], s[2]) for s in near if ok_band(s[1], s[2]))
    if not pool:                                                    # the band is out of reach today (back from a run): the reachable spot nearest the front, and on the next day again
        def spot_cost(spot):
            return spot[0]

        return (min(near, key=spot_cost)[1:], False) if near else None
    return random.Random(f"{state.campaign_id}:{state.day // BAND_DAYS}:cv").choice(pool), in_band


def evade_nm(state) -> float:
    from . import theatres
    return float((theatres.active().get("carrier") or {}).get("carrier_evade_nm", EVADE_NM))


def evading(state) -> bool:
    """Is the fleet running from a staged carrier raid (today is the staging day or the launch day)?"""
    return int((state.ground or {}).get("cv_evade", -1)) >= state.day


def evade(state) -> str | None:
    """S115: the day red stages a carrier raid the fleet sails out of the bombers' reach: the allowed-or-not spot within EVADE_MOVE_KM that is at least evade_nm() from every red airfield
    (open water as usual), the nearest such spot to where it is; else the spot farthest from the nearest red airfield (a small sea). It stays there until the raid has flown (`update`
    holds it while `evading`). -> a war-log line, or None when it is already clear or cannot move."""
    g = state.ground
    cv = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
    if not g or cv is None or not ground.active(state):
        return None
    stage = ((state.raids or {}).get("bomber_stage") or {})
    if int(stage.get("launch", -1)) < state.day:
        return None
    g["cv_evade"] = int(stage["launch"])
    fields = _red_fields(state)
    if not fields:
        return None
    need_m = evade_nm(state) * NM
    # Distance from a point to the nearest red field.
    def near(x, y):
        return min(math.hypot(x - fx, y - fy) for fx, fy in fields)

    if near(cv.x, cv.y) >= need_m:
        return None
    cand = [(x, y) for _, x, y in _all_spots(state, EVADE_MOVE_KM, fields, 0.0)]
    ok = [(x, y) for x, y in cand if near(x, y) >= need_m]
    def distance_from_carrier(point):
        return math.hypot(point[0] - cv.x, point[1] - cv.y)

    def distance_to_red(point):
        return near(*point)

    spot = min(ok, key=distance_from_carrier) if ok else (max(cand, key=distance_to_red) if cand else None)
    if spot is None or near(*spot) <= near(cv.x, cv.y) + 1000.0:
        return None
    moved = math.hypot(spot[0] - cv.x, spot[1] - cv.y) / 1000.0
    cv.x, cv.y = spot
    return f"{cv.name} sails {moved:.0f} km out of the bombers' reach, {near(*spot) / NM:.0f} nm from the nearest red airfield."


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
    if evading(state):                                        # S115: it stays out of reach until the staged raid has flown
        return None
    spot = best_spot(state, None if first else CARRIER_MOVE_KM)
    if spot is None:
        return None
    nearest = spot
    drawn = band_spot(state, None if first else CARRIER_MOVE_KM)        # S115: a seeded spot in the band, not the same point every time
    spot, in_band = drawn if drawn else (nearest, True)
    lx, ly = ground.line_xy(g)
    now_ok = _ok(cv.x, cv.y, _red_fields(state), standoff_nm(state) * NM)
    if not first and now_ok and in_band and state.day % BAND_DAYS != 0:      # it stays on its spot until the next draw (every BAND_DAYS days), unless it is out of the band (back from a run, or a field fell)
        return None
    if not first and now_ok and in_band and math.hypot(spot[0] - cv.x, spot[1] - cv.y) < CARRIER_STAY_KM * 1000.0:
        return None
    moved = math.hypot(spot[0] - cv.x, spot[1] - cv.y) / 1000.0
    if moved < 1.0:
        return None
    cv.x, cv.y = spot
    return f"{cv.name} repositions {moved:.0f} km {'to its station' if first else 'along the front'}, {standoff_nm(state):.0f} nm clear of the red airfields."
