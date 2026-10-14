"""The enemy's air tasking (phase 1): what its fighter wings are doing today.

Until now the enemy's fighters were invented around your package when the mission was built: whichever wings were nearest, a CAP in front
of each base. Now the enemy has a plan for the day, made once and kept in the campaign (state.red_air):

* CAP pairs: a wing flies a few patrol pairs, each on a station in front of its own base toward the nearest friendly airfield, in a time
  window (the day is cut into four 6-hour waves; which waves a wing covers differs from wing to wing and from day to day, so there are gaps).
  How many pairs a wing flies a day follows the difficulty and what the wing has left; one pair always stays on alert.
* Sweeps (Level 2 and 3): a pair that patrols over a contested sector of the front for 90 minutes.

Patrols, sweeps and raids draw on one daily sortie budget per wing (DAILY_SORTIES per serviceable airframe, the rule the friendly packages follow).

The mission builder uses the plan where it overlaps your mission (the window contains the time on target, the station is near the target or
the route): those are the briefed, airborne-at-the-start enemy fighters. How many enemy fighters there are still follows the package's threat
size (n_def); the plan decides which wings, where and when. Losses carry on as before (the wing has fewer aircraft tomorrow, so tomorrow's plan
is smaller).

Pure planning, no pydcs.
"""
from __future__ import annotations
import hashlib
import random
from .loadouts import ENEMY_FIGHTERS
from .models import AssetKind, BaseKind
from .routes import NM, bearing, dist, offset

WAVES = [(0, 360), (360, 720), (720, 1080), (1080, 1440)]     # minutes of the day
WAVE_OVERLAP_MIN = 20                                          # a pair stays up this long into the next wave (no gap at the boundary)
SWEEP_MIN = 90
REL_NM = 110                                                   # a patrol station this close to the target counts as "in the area"
ROUTE_NM = 45                                                  # ...or this close to a point on the route
# per level: share of a wing's aircraft flying patrols, most patrol pairs per wing, sweeps per day
DAILY_SORTIES = 2                                              # per serviceable airframe per day: the same rule the friendly packages follow (engine.plan_day)
DOCTRINE = {1: {"frac": 0.20, "pairs": 1, "sweeps": 0}, 2: {"frac": 0.30, "pairs": 2, "sweeps": 1}, 3: {"frac": 0.40, "pairs": 3, "sweeps": 2}}


def budget(state, wing_id: str) -> int:
    """Aircraft-sorties a wing can fly today: DAILY_SORTIES per serviceable airframe (what it had when the day was planned)."""
    ra = getattr(state, "red_air", None) or {}
    if "budget" in ra and wing_id in ra["budget"]:
        return int(ra["budget"][wing_id])
    w = state.enemy_air_at(wing_id)
    return DAILY_SORTIES * w.available if w else 0


def used(state, wing_id: str) -> int:
    return int(((getattr(state, "red_air", None) or {}).get("used") or {}).get(wing_id, 0))


def can(state, wing_id: str, n: int) -> bool:
    return used(state, wing_id) + n <= budget(state, wing_id)


def spend(state, wing_id: str, n: int) -> None:
    """Book n aircraft-sorties against a wing's day (patrols, sweeps and raids all draw on the same budget)."""
    ra = getattr(state, "red_air", None)
    if ra is None:
        return
    ra.setdefault("used", {})
    ra["used"][wing_id] = int(ra["used"].get(wing_id, 0)) + int(n)


def _wave_order(base_id: str, day: int) -> list:
    s = int(hashlib.md5(f"{base_id}:{day}".encode()).hexdigest()[:4], 16) % 4
    return [(s + k) % 4 for k in (0, 2, 1, 3)]


def plan(state, d) -> dict:
    """-> {"day": n, "flights": [{id, kind CAP|SWEEP, wing (base asset id), type, size, start, end (minutes of the day), x, y}]}."""
    rng = random.Random(f"{state.campaign_id}:{state.day}:redair")
    doc = DOCTRINE[max(1, min(3, int(getattr(d, "level", 1))))]
    blue_af = [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD]
    flights, spare = [], []
    use, bud = {}, {}
    wings = sorted(state.enemy_air, key=lambda w: w.base_asset_id)
    for w in wings:
        types = [t for t in w.types if t in ENEMY_FIGHTERS]
        a = state.assets.get(w.base_asset_id)
        if not types or a is None or a.destroyed or w.available < 2:
            continue
        pairs = w.available // 2
        bud[w.base_asset_id] = DAILY_SORTIES * w.available
        n_cap = min(doc["pairs"], pairs - 1, max(1, round(doc["frac"] * w.available / 2)))     # one pair always stays on alert
        tgt = min(blue_af, key=lambda b: dist(a.x, a.y, b.x, b.y)) if blue_af else None
        order = _wave_order(w.base_asset_id, state.day)
        for k in range(max(0, n_cap)):
            if use.get(w.base_asset_id, 0) + 2 > bud[w.base_asset_id]:
                break
            use[w.base_asset_id] = use.get(w.base_asset_id, 0) + 2
            if tgt is not None and dist(a.x, a.y, tgt.x, tgt.y) < 35 * NM:
                sx, sy = offset(a.x, a.y, bearing(a.x, a.y, tgt.x, tgt.y), 0.5 * dist(a.x, a.y, tgt.x, tgt.y))
            elif tgt is not None:
                sx, sy = offset(a.x, a.y, bearing(a.x, a.y, tgt.x, tgt.y) + rng.uniform(-12, 12), rng.uniform(20, 25) * NM)
            else:
                sx, sy = a.x, a.y
            lo, hi = WAVES[order[k]]
            flights.append({"id": f"rf{state.day}-{w.base_asset_id}-{k}", "kind": "CAP", "wing": w.base_asset_id, "type": rng.choice(types), "size": 2,
                            "start": lo, "end": min(1440 + WAVE_OVERLAP_MIN, hi + WAVE_OVERLAP_MIN), "x": sx, "y": sy})
        if w.available - 2 * max(0, n_cap) >= 4:
            spare.append((w, types))
    g = state.ground or {}
    contested = [i for i, (r, b) in enumerate(zip(g.get("red", []), g.get("blue", []))) if r >= 15 and b >= 15]
    for k in range(doc["sweeps"] if (spare and contested) else 0):
        w, types = spare[rng.randrange(len(spare))]
        if use.get(w.base_asset_id, 0) + 2 > bud.get(w.base_asset_id, 0):
            continue
        use[w.base_asset_id] = use.get(w.base_asset_id, 0) + 2
        c = g["centers"][rng.choice(contested)]
        lo = rng.randrange(6 * 60, 19 * 60, 30)
        flights.append({"id": f"rf{state.day}-{w.base_asset_id}-s{k}", "kind": "SWEEP", "wing": w.base_asset_id, "type": rng.choice(types), "size": 2,
                        "start": lo, "end": lo + SWEEP_MIN, "x": float(c[0]), "y": float(c[1])})
    return {"day": state.day, "flights": flights, "budget": bud, "used": dict(use), "patrol_used": dict(use)}


GUARD_NM = 60                  # v0.41.10: a patrol guards a SAM site within this of its own field
GUARD_FWD_NM = 10              # ...from a station this far in front of the site, toward the nearest friendly (blue) field
GUARD_VALUE = {"SA-10": 4.0, "SA-11": 3.0, "SA-6": 2.5, "SA-15": 2.0, "SA-19": 1.5, "SA-8": 1.5, "SA-3": 1.5, "SA-2": 1.2}
GUARD_READ = {1: 0.25, 2: 0.5, 3: 0.75}   # how often red's "briefing" reads the day's blue targets right, by level


def guard_score(state, site, blue_af, attacked: set, expected: list) -> float:
    """Red's threat rating of one of its SAM sites: how valuable it is, how close it is to blue's fields, whether it was attacked
    lately, and whether red expects it to be attacked today (expected: [(x, y)] of the blue targets red has read correctly)."""
    v = GUARD_VALUE.get(site.variant, 1.0)
    dblue = min((dist(site.x, site.y, b.x, b.y) / NM for b in blue_af), default=200.0)
    sc = v * (1.0 + max(0.0, (150.0 - dblue) / 50.0))
    if site.id in attacked:
        sc += 2.0
    if any(dist(site.x, site.y, ex, ey) <= 25 * NM for ex, ey in expected):
        sc += 10.0
    return sc


def assign_guards(state, d, objectives) -> None:
    """v0.41.10: red's own "briefing". Each planned patrol pair takes a station over the SAM site its wing rates most likely to be attacked
    (guard_score), 10 nm in front of it toward blue, instead of a point in front of its own base: red CAP sits over its air defence and
    comes to its help. Whether red reads today's blue targets correctly follows the level (GUARD_READ), once per wing per day."""
    ra = getattr(state, "red_air", None)
    if not ra:
        return
    lvl = max(1, min(3, int(getattr(d, "level", 1))))
    rng = random.Random(f"{state.campaign_id}:{state.day}:redguard")
    blue_af = [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD]
    attacked = set((state.raids or {}).get("sead", {}).keys()) | set((state.raids or {}).get("sead_fail", {}).keys())
    tgt_xy = []
    for o in objectives or []:
        a = state.assets.get(getattr(o, "target_id", None) or "")
        if a is not None:
            tgt_xy.append((a.x, a.y))
    sams = [a for a in state.assets.values() if a.kind == AssetKind.SAM and not a.destroyed]
    taken = {}
    for f in ra.get("flights", []):
        if f.get("kind") != "CAP":
            continue
        a = state.assets.get(f["wing"])
        if a is None:
            continue
        cands = [s for s in sams if dist(s.x, s.y, a.x, a.y) <= GUARD_NM * NM]
        if not cands:
            continue
        reads = rng.random() < GUARD_READ[lvl]
        exp = tgt_xy if reads else []
        ranked = sorted(cands, key=lambda s: (-guard_score(state, s, blue_af, attacked, exp), s.id))
        k = taken.get(f["wing"], 0)
        site = ranked[min(k, len(ranked) - 1)]
        taken[f["wing"]] = k + 1
        nb = min(blue_af, key=lambda b: dist(site.x, site.y, b.x, b.y)) if blue_af else None
        sx, sy = offset(site.x, site.y, bearing(site.x, site.y, nb.x, nb.y), GUARD_FWD_NM * NM) if nb else (site.x, site.y)
        f["x"], f["y"], f["guard"], f["gx"], f["gy"], f["read"] = sx, sy, site.id, site.x, site.y, reads


def ensure(state, d) -> dict:
    """Today's plan (made on first use, kept for the day; an old save without one gets one)."""
    ra = getattr(state, "red_air", None)
    if not ra or ra.get("day") != state.day:
        state.red_air = ra = plan(state, d)
    return ra


def pick(state, tot_min: float, pts: list, tx: float, ty: float, limit: int) -> list:
    """The planned patrol flights that are up at the time on target and near the target or the route, nearest the target first.
    A wing never supplies more pairs than it has aircraft for right now."""
    out, used = [], {}
    t = tot_min % 1440
    for f in sorted((state.red_air or {}).get("flights", []), key=lambda f: dist(f["x"], f["y"], tx, ty)):
        if len(out) >= limit:
            break
        if not (f["start"] <= t <= f["end"] or f["start"] <= t + 1440 <= f["end"]):
            continue
        w = state.enemy_air_at(f["wing"])
        a = state.assets.get(f["wing"])
        if w is None or a is None or a.destroyed or w.available // 2 <= used.get(f["wing"], 0):
            continue
        if not (dist(f["x"], f["y"], tx, ty) <= REL_NM * NM or any(dist(f["x"], f["y"], px, py) <= ROUTE_NM * NM for px, py in pts)):
            continue
        used[f["wing"]] = used.get(f["wing"], 0) + 1
        out.append(f)
    return out


def hhmm(minute: float) -> str:
    m = int(minute) % 1440
    return f"{m // 60:02d}{m % 60:02d}"
