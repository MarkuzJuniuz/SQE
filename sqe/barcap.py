"""BARCAP as planned coverage (v0.41.73, same rules for both sides): pure planning, no pydcs.

Every defended asset (an airfield with a fighter wing, a blue airfield, a carrier) gets BARCAP areas: one station per direction a hostile base could still
send something from, placed fairly close to the asset on that side and clear of the enemy's SAM rings. A sortie stays up for the airframe's time on
station and its relief arrives before it leaves (a chain of sorties, one chain per area).

Where each number came from (CLAUDE.md doctrine rule):
* SOURCED, only in outline: a CAP sits between the threat and the asset, a pair or two at a time; without tankers a fighter stays "an hour or two", with
  tankers it can be held round the clock and the relief arrives as the last one runs low (migflug "Combat Air Patrol explained"; Linebacker MiGCAP
  accounts); AFIT thesis (ADA556690) Table 2 uses 60 / 40 / 20 minute stays against refuelling points 80 / 140 / 200 nm away. No public source found
  gives a station distance, a handover overlap or a sector width.
* XO's judgment calls (barcap-plan.md): 2 h on station for the long-legged jets (F-14, F-15C, Su-27), 30 min for the short-legged (F-16, F/A-18, MiG-29
  and older), 2 h for any jet guarding a tanker; stations a few miles outside the SAM umbrella for a base, about 15 mi from a carrier group.
* Judgment calls of mine: 10 min handover overlap, sectors merged inside 40 degrees (at most 3 per asset), a hostile base counts within 300 nm.
"""
from __future__ import annotations
import math
from .models import AssetKind, BaseKind
from .routes import NM, bearing, dist, offset

LONG_LEGGED = ("Su_27", "Su_30", "Su_33", "MiG_31", "F-14", "F_14", "F-15", "F_15")
ENDURANCE_LONG_MIN = 120       # XO: F-14 / F-15C type legs
ENDURANCE_SHORT_MIN = 30       # XO: F-16 / F/A-18 type legs
ENDURANCE_TANKER_MIN = 120     # XO: guarding a tanker, whatever the airframe (they can refuel)
HANDOVER_MIN = 10              # the relief is on station this long before the sortie it replaces goes home (judgment call)
STATION_BASE_NM = 12           # a base's station sits this far out toward the threat: XO "just a few miles outside the SAM protection" (judgment call)
STATION_FLEET_NM = 13          # a carrier group's station: XO "about 15 mi" from the group
STATION_MAX_NM = 30            # never further from the asset than this, even when a SAM ring is in the way
SAM_MARGIN_NM = 8              # a station stays this far outside an enemy SAM ring (judgment call)
SECTOR_MERGE_DEG = 40          # hostile bases within this many degrees of each other share one area (judgment call)
MAX_SECTORS = 3
THREAT_REACH_NM = 300          # a hostile base further than this cannot send anything at the asset (judgment call)


def endurance_min(aircraft: str, tanker: bool = False) -> int:
    """Minutes one sortie of this airframe stays on its station."""
    if tanker:
        return ENDURANCE_TANKER_MIN
    return ENDURANCE_LONG_MIN if any(k in (aircraft or "") for k in LONG_LEGGED) else ENDURANCE_SHORT_MIN


def _angdiff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def launch_points(state, side: str) -> list:
    """Where an attack on `side`'s assets could come from: [(x, y)] of the hostile fields and carriers that still have fighters or attackers."""
    out = []
    if side == "red":                                       # hostile = blue: fields and carriers with serviceable squadrons
        for sq in state.squadrons.values():
            b = state.bases.get(sq.base_id)
            if b is not None and sq.available > 0:
                out.append((b.x, b.y))
    else:                                                   # hostile = red: wing fields not destroyed with jets left
        for w in state.enemy_air:
            a = state.assets.get(w.base_asset_id)
            if a is not None and not a.destroyed and w.available > 0:
                out.append((a.x, a.y))
    return list(dict.fromkeys(out))


def sectors(x: float, y: float, points: list, reach_nm: float = THREAT_REACH_NM) -> list:
    """The directions (compass bearings) a hostile base on `points` could come from, one per cluster, nearest cluster first."""
    near = sorted(((dist(x, y, px, py), bearing(x, y, px, py)) for px, py in points if 0 < dist(x, y, px, py) <= reach_nm * NM))
    clusters = []                                           # [first bearing, [bearings], nearest distance]
    for d, brg in near:
        for c in clusters:
            if _angdiff(brg, c[0]) <= SECTOR_MERGE_DEG:
                c[1].append(brg)
                break
        else:
            clusters.append([brg, [brg], d])
    out = []
    for c in clusters[:MAX_SECTORS]:                        # nearest first (the list is already in distance order)
        sx = sum(math.sin(math.radians(b)) for b in c[1])
        sy = sum(math.cos(math.radians(b)) for b in c[1])
        out.append(round(math.degrees(math.atan2(sx, sy)) % 360.0, 1))
    return out


def _enemy_rings(state, side: str) -> list:
    """[(x, y, reach_m)] of the SAM sites that would shoot at `side`'s CAP: blue's sites for red's patrols, red's for blue's."""
    from .threatmap import RANGE_NM, SERIOUS_NM
    sites = state.blue_sams.values() if side == "red" else (a for a in state.assets.values() if a.kind == AssetKind.SAM)
    return [(s.x, s.y, RANGE_NM.get(s.variant, 0) * NM) for s in sites if not s.destroyed and RANGE_NM.get(s.variant, 0) >= SERIOUS_NM]


def station(state, side: str, ax: float, ay: float, brg: float, out_nm: float) -> tuple:
    """-> (x, y, in_ring): the station `out_nm` from the asset toward `brg`, pushed out of every enemy SAM ring (plus margin), but never further than
    STATION_MAX_NM from the asset. in_ring is True when even that leaves it inside a ring (the asset itself sits under the enemy's umbrella)."""
    px, py = offset(ax, ay, brg, out_nm * NM)
    rings = _enemy_rings(state, side)
    for _ in range(3):
        moved = False
        for sx, sy, r in rings:
            lim = r + SAM_MARGIN_NM * NM
            if dist(px, py, sx, sy) < lim:
                px, py = offset(sx, sy, bearing(sx, sy, px, py), lim)
                moved = True
        if not moved:
            break
    if dist(px, py, ax, ay) > STATION_MAX_NM * NM:
        px, py = offset(ax, ay, bearing(ax, ay, px, py), STATION_MAX_NM * NM)
    return px, py, any(dist(px, py, sx, sy) < r for sx, sy, r in rings)


def plan_areas(state, side: str) -> list:
    """The BARCAP areas of one side: [{id, side, asset, name, x, y (station), ax, ay (asset), bearing, in_ring, types, endurance_min}]."""
    pts = launch_points(state, side)
    out = []
    if side == "red":
        assets = []
        for w in state.enemy_air:
            a = state.assets.get(w.base_asset_id)
            if a is not None and not a.destroyed and w.available > 0 and w.fighter_types():
                assets.append((a.id, a.name, a.x, a.y, STATION_BASE_NM, list(w.fighter_types())))
    else:
        assets = []
        for b in state.bases.values():
            if b.kind not in (BaseKind.AIRFIELD, BaseKind.CARRIER):
                continue
            tps = [sq.aircraft for sq in state.squadrons.values() if sq.base_id == b.id and sq.available > 0]
            assets.append((b.id, b.name, b.x, b.y, STATION_FLEET_NM if b.kind == BaseKind.CARRIER else STATION_BASE_NM, tps))
    for aid, name, ax, ay, out_nm, types in assets:
        for k, brg in enumerate(sectors(ax, ay, pts)):
            sx, sy, ring = station(state, side, ax, ay, brg, out_nm)
            eng = max((endurance_min(t) for t in types), default=ENDURANCE_SHORT_MIN)
            out.append({"id": f"ba-{side}-{aid}-{k}", "side": side, "asset": aid, "name": name, "x": sx, "y": sy, "ax": ax, "ay": ay,
                        "bearing": brg, "in_ring": ring, "types": types, "endurance_min": eng})
    return out


def chain(first_start: int, n: int, endurances: list) -> list:
    """n back-to-back sorties of one area: [(start, end)] in minutes of the day, each one starting HANDOVER_MIN before the last one leaves.
    endurances[i] is the stay of sortie i (its airframe's)."""
    out, t = [], int(first_start)
    for i in range(n):
        e = int(endurances[i % len(endurances)]) if endurances else ENDURANCE_SHORT_MIN
        out.append((t, t + e))
        t = t + e - HANDOVER_MIN
    return out


def facing_area(state, side: str, asset_id: str, toward_xy: tuple):
    """The BARCAP area of one asset that faces the mission: the area whose direction is closest to the bearing from the asset to `toward_xy`
    (the target; XO: an area is built into the mission when its station lies on the side facing the targets). None when the asset has no area
    today (no hostile base can reach it): the caller keeps its old placement."""
    areas = [a for a in ensure(state)[side] if a["asset"] == asset_id]
    if not areas:
        return None
    want = bearing(areas[0]["ax"], areas[0]["ay"], toward_xy[0], toward_xy[1])
    return min(areas, key=lambda a: (_angdiff(a["bearing"], want), a["id"]))


def ensure(state) -> dict:
    """Today's BARCAP areas for both sides (made once a day, kept in state.barcap; an old save gets them on first use)."""
    bc = getattr(state, "barcap", None)
    if not bc or bc.get("day") != state.day:
        state.barcap = bc = {"day": state.day, "red": plan_areas(state, "red"), "blue": plan_areas(state, "blue")}
    return bc
