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
import math
import random
from . import barcap
from .loadouts import ENEMY_FIGHTERS
from .models import AssetKind, BaseKind
from .routes import NM, bearing, dist, offset

WAVES = [(0, 360), (360, 720), (720, 1080), (1080, 1440)]     # minutes of the day
WAVE_OVERLAP_MIN = 20                                          # a pair stays up this long into the next wave (no gap at the boundary)
SWEEP_MIN = 90
REL_NM = 110                                                   # a patrol station this close to the target counts as "in the area"
BEHIND_NM = 20                                                 # v0.41.74: a patrol whose station lies further than this BEYOND the target (along the way in) is not in the fight: it guards its own rear field
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
    bc = barcap.ensure(state)
    flights, spare = [], []
    use, bud = {}, {}
    wings = sorted(state.enemy_air, key=lambda w: w.base_asset_id)
    for w in wings:
        types = [t for t in w.types_up if t in ENEMY_FIGHTERS]            # v0.41.53: only a fighter squadron with a pair serviceable flies patrols
        a = state.assets.get(w.base_asset_id)
        fav = w.available_of(ENEMY_FIGHTERS)                              # ...and the patrols are cut from its fighters, not from attack squadrons
        if not types or a is None or a.destroyed or fav < 2:
            continue
        pairs = fav // 2
        bud[w.base_asset_id] = DAILY_SORTIES * w.available                # the day's sortie budget is still the whole wing's (raids share it)
        # v0.41.73: the patrol share is now counted in SORTIES (a 30-minute stay is one sortie, so a pair can fly several a day): the level's share of the
        # wing's day budget, in pairs. At most one pair per area is up at a time and one pair always stays on alert, so no more areas than pairs - 1.
        n_cap = max(1, round(doc["frac"] * bud[w.base_asset_id] / 2)) if pairs >= 2 else 0
        # v0.41.73: BARCAP rules. The wing's pairs fly the BARCAP areas of its own field (one per direction a blue base could still send something
        # from, barcap.py), in a chain: each sortie stays its airframe's time on station and its relief arrives before it leaves.
        areas = [ar for ar in bc["red"] if ar["asset"] == w.base_asset_id][:max(0, pairs - 1)]
        order = _wave_order(w.base_asset_id, state.day)
        per = [[] for _ in areas]
        for k in range(max(0, n_cap) if areas else 0):
            per[k % len(areas)].append(k)
        for ai, ar in enumerate(areas):
            t0 = WAVES[order[ai % 4]][0]
            typs = [rng.choice(types) for _ in per[ai]]
            for j, (lo, hi) in enumerate(barcap.chain(t0, len(per[ai]), [barcap.endurance_min(t) for t in typs])):
                if use.get(w.base_asset_id, 0) + 2 > bud[w.base_asset_id] or lo >= 1440:
                    break
                use[w.base_asset_id] = use.get(w.base_asset_id, 0) + 2
                flights.append({"id": f"rf{state.day}-{w.base_asset_id}-{ai}.{j}", "kind": "CAP", "wing": w.base_asset_id, "type": typs[j], "size": 2,
                                "start": lo, "end": min(1440 + WAVE_OVERLAP_MIN, hi), "x": ar["x"], "y": ar["y"], "area": ar["id"], "bearing": ar["bearing"],
                                "ax": ar["ax"], "ay": ar["ay"]})
        if fav - 2 * min(len(areas), max(0, n_cap)) >= 4:
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


GUARD_NM = 150                 # v0.41.11: a patrol guards a SAM site within this of its own field (was 60: the big rear wings guarded only their own
                               # local sites and the front, Sukhumi and Gudauta, went unguarded in the v0.41.10 run)
CALLIN_LINK_NM = 40            # v0.41.73: a patrol is linked to (and called in to) the best-rated SAM site within this of its BARCAP station (judgment call)
GUARD_FWD_NM = 10              # ...from a station this far in front of the site, toward the nearest friendly (blue) field
GUARD_VALUE = {"SA-10": 4.0, "SA-11": 3.0, "SA-6": 2.5, "SA-15": 2.0, "SA-19": 1.5, "SA-8": 1.5, "SA-3": 1.5, "SA-2": 1.2}
# v0.41.20: no needless banzai, red's side. "commit": red fighters go after blue only with at least this quality-weighted edge (red : blue), except
# over their own field or a SAM site blue is attacking (then at any odds). "soft": how much a raid's pick shies from a target under a full Patriot
# (and on Hard also from your home field's HAWK): 1.0 = not at all (Easy's careless red).
RED_DOCTRINE = {1: {"commit": 0.0, "soft": 1.0, "hawk": False}, 2: {"commit": 1.0, "soft": 0.5, "hawk": False}, 3: {"commit": 2.0, "soft": 0.25, "hawk": True}}
RED_QUALITY = {"MiG_29A": 0.67, "MiG_29S": 0.67, "Su_27": 0.67, "MiG_21Bis": 0.5, "MiG_23MLD": 0.5, "F_4E": 0.5, "F_5E_3": 0.5}   # one blue fighter = 1.0


def doctrine(d) -> dict:
    return RED_DOCTRINE[max(1, min(3, int(getattr(d, "level", 1))))]


def commits(d, red_types: list, blue_jets: int) -> bool:
    """v0.41.20: does red take this fight? red_types: one entry per red jet; blue_jets: blue air-to-air jets in it (each weighs 1.0)."""
    need = doctrine(d)["commit"]
    if need <= 0 or blue_jets <= 0:
        return True
    return sum(RED_QUALITY.get(t, 0.6) for t in red_types) >= need * blue_jets - 1e-6


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
    """v0.41.10 / v0.41.73: red's own "briefing". Each planned patrol pair is linked to the SAM site near its BARCAP station that its wing rates most
    likely to be attacked (guard_score) and is called in to it when blue comes close (the station itself no longer moves: it is a BARCAP station,
    barcap.py). Whether red reads today's blue targets correctly follows the level (GUARD_READ), once per flight."""
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
        cands = [s for s in sams if dist(s.x, s.y, f["x"], f["y"]) <= CALLIN_LINK_NM * NM]       # v0.41.73: the station is a BARCAP station now; it only calls in to a site near it
        if not cands:
            continue
        reads = rng.random() < GUARD_READ[lvl]
        exp = tgt_xy if reads else []
        ranked = sorted(cands, key=lambda s: (-guard_score(state, s, blue_af, attacked, exp), s.id))
        site = ranked[0]
        f["guard"], f["gx"], f["gy"], f["read"] = site.id, site.x, site.y, reads


def ensure(state, d) -> dict:
    """Today's plan (made on first use, kept for the day; an old save without one gets one)."""
    ra = getattr(state, "red_air", None)
    if not ra or ra.get("day") != state.day:
        state.red_air = ra = plan(state, d)
    return ra


def beyond_nm(x: float, y: float, pts: list, tx: float, ty: float) -> float:
    """How far (nm) the point (x, y) lies PAST the target along the way in (IP -> target; pts = [push, ip, target]): positive = behind the target as
    blue comes in. 0 when the way in is not known."""
    if len(pts) < 2 or dist(pts[1][0], pts[1][1], tx, ty) <= 1:
        return 0.0
    hdg = math.radians(bearing(pts[1][0], pts[1][1], tx, ty))
    return ((x - tx) * math.cos(hdg) + (y - ty) * math.sin(hdg)) / NM


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
        if w is None or a is None or a.destroyed or w.available_of(ENEMY_FIGHTERS) // 2 <= used.get(f["wing"], 0):
            continue
        if not (dist(f["x"], f["y"], tx, ty) <= REL_NM * NM or any(dist(f["x"], f["y"], px, py) <= ROUTE_NM * NM for px, py in pts)):
            continue
        if beyond_nm(f["x"], f["y"], pts, tx, ty) > BEHIND_NM:
            continue
        used[f["wing"]] = used.get(f["wing"], 0) + 1
        out.append(f)
    return out


def hhmm(minute: float) -> str:
    m = int(minute) % 1440
    return f"{m // 60:02d}{m % 60:02d}"
