"""The enemy's air tasking: what its fighter wings are doing, planned turn by turn (v0.41.340, campaign rules plan Phase 5a; before, one plan a day).

Red plans each turn on its own, from its READY fighters, as blue's standing patrols do (blue_barcap.plan_turn, Phase 4b):

* CAP pairs: a share of the BARCAP areas that can be up this turn (`RED_CAP_SHARE`, day / night, seeded) gets one pair, on a station in front of its own base toward the
  nearest friendly airfield (barcap.py). A pair of a short-legged type costs two (a second pair relieves it in the second wave).
* Sweeps (Level 2 and 3): a pair that patrols over a contested sector of the front for 90 minutes, a seeded chance each day turn (`SWEEPS_PER_DAY` a day).
* The pairs are drawn from a ledger of each fighter squadron's ready jets less the reaction reserve (reserve.py) BEFORE anything else, and every pair planned in a turn is
  committed to refit at the end of the turn (Session._sorties), so a red jet that flew is not ready again until its refit is over.
* The day's flights accumulate in `state.red_air["flights"]` (reset by `begin_day`); a replan of a turn replaces its own entries.

Raids are planned per turn too (v0.41.341, Phase 5b, raids.py): the turn's ready jets are shared in ONE place, `state.red_air["free"]` (squadron id -> jets still free this turn), which `plan_turn` fills
from the fighter ledger (after the reserve and the patrols) and from the attack squadrons' ready jets (the reserve is for fighters only). A raid books its raiders, SEAD / DEAD group and escorts off it
(`take_ready`), so a jet is not in a patrol, the reserve and a raid at once. The DAILY sortie budget (`budget`, `can`, `spend`, DAILY_SORTIES per serviceable airframe at the start of the day) stays only as a
day cap that the raids also count against, for the abstract strikes nobody plans turn by turn: the overnight raids (`raids.overnight`) and the supply round's / ground war's red strikes (ground.py).

The mission builder uses the plan where it overlaps your mission (the window contains the time on target, the station is near the target or the route): those are the
briefed, airborne-at-the-start enemy fighters. How many enemy fighters there are still follows the package's threat size (n_def); the plan decides which wings, where and when.

Pure planning, no pydcs.
"""
from __future__ import annotations
import math
import random
from . import barcap, clock, refit, reserve, runways
from .loadouts import ENEMY_FIGHTERS
from .models import AssetKind, BaseKind
from .routes import NM, bearing, dist, offset

SWEEP_MIN = 90
REL_NM = 110                                                   # a patrol station this close to the target counts as "in the area"
BEHIND_NM = 20                                                 # v0.41.74: a patrol whose station lies further than this BEYOND the target (along the way in) is not in the fight: it guards its own rear field
ROUTE_NM = 45                                                  # ...or this close to a point on the route
DAILY_SORTIES = 2                                              # per serviceable airframe per day: a day cap on the raids and the abstract strikes (patrols, sweeps and raids draw their jets per turn since v0.41.340 / 341)
SWEEPS_PER_DAY = {1: 0, 2: 1, 3: 2}                            # sweeps a day by level (the v0.41.110 doctrine); each day turn plans one with chance SWEEPS_PER_DAY / DAY_TURNS (judgment call)
DAY_TURNS = clock.DAY_MIN // clock.TURN_MIN - len(clock.NIGHT_START_HOURS)     # 6 turns of a day are not night turns
# share of the BARCAP areas that can be up that get a pair in a turn, by level: (day turn, night turn). The v0.41.110 patrol shares were 0.20 / 0.40 / 0.55 of the wing's day budget; the
# night values are the plan's own (section 4 Phase 5). Seeded per turn. Judgment call (plan sections 4 and 6; XO tunes it in Phase 13).
RED_CAP_SHARE = {1: (0.20, 0.05), 2: (0.40, 0.15), 3: (0.55, 0.20)}
SWEEP_START_SPREAD_MIN = 30                                    # a sweep goes up this soon (random, steps of 10) after its wave opens (judgment call)


def _level(d) -> int:
    return max(1, min(3, int(getattr(d, "level", 1))))


def begin_day(state) -> dict:
    """A new day's shell: no flights yet, and the raids' daily sortie budget per wing (`DAILY_SORTIES` x the jets it has now). `Session._begin_day` calls it; `plan_turn` fills the flights."""
    state.red_air = {"day": state.day, "flights": [], "budget": {w.base_asset_id: DAILY_SORTIES * w.available for w in state.enemy_air}, "used": {}}
    return state.red_air


def budget(state, wing_id: str) -> int:
    """Aircraft-sorties a wing can fly in raids today: DAILY_SORTIES per serviceable airframe (what it had when the day began)."""
    ra = getattr(state, "red_air", None) or {}
    if "budget" in ra and wing_id in ra["budget"]:
        return int(ra["budget"][wing_id])
    w = state.enemy_air_at(wing_id)
    return DAILY_SORTIES * w.available if w else 0


def used(state, wing_id: str) -> int:
    return int(((getattr(state, "red_air", None) or {}).get("used") or {}).get(wing_id, 0))


def _fighters_left(state, wing_id: str):
    """Ready fighters of a wing that this turn's patrols, sweeps and the reaction reserve left free; None when the turn is not planned (no limit known)."""
    left = (getattr(state, "red_air", None) or {}).get("left")
    return None if left is None else int(left.get(wing_id, 0))


def ready_of(state, wing, types) -> int:
    """Jets of these aircraft types the wing has free THIS turn (v0.41.341, Phase 5b): what `plan_turn` left in `state.red_air["free"]` (ready now, less the reaction reserve for fighters, less the turn's patrols
    and what raids booked since). With no plan for the current turn (the overnight raids, a tool) it is simply the serviceable jets of those types."""
    ra = getattr(state, "red_air", None) or {}
    free = ra.get("free") if ra.get("turn") == state.turn else None
    if free is None:
        return wing.available_of(types)
    return sum(int(free.get(q.id, 0)) for q in wing.sqns if q.aircraft in types)


def take_ready(state, wing, types, n: int) -> list:
    """Book n of the wing's free jets of these types for a raid this turn, the squadron with most free first. -> [[squadron id, jets]] (short of n when the wing has fewer free). They come off
    `state.red_air["free"]` (and `["left"]` for fighters), so a second raid, a patrol or an escort does not take them again; the day's sortie cap is `spend`'s job."""
    ra = getattr(state, "red_air", None) or {}
    free = ra.get("free") if ra.get("turn") == state.turn else None
    pool = sorted((q for q in wing.sqns if q.aircraft in types), key=lambda q: (-(int(free.get(q.id, 0)) if free is not None else q.available), q.id))
    out, left_n = [], int(n)
    for q in pool:
        k = min(left_n, int(free.get(q.id, 0)) if free is not None else int(q.available))
        if k <= 0:
            continue
        out.append([q.id, k])
        left_n -= k
        if free is not None:
            free[q.id] = int(free.get(q.id, 0)) - k
            if q.aircraft in ENEMY_FIGHTERS and ra.get("left") is not None and wing.base_asset_id in ra["left"]:
                ra["left"][wing.base_asset_id] = max(0, int(ra["left"][wing.base_asset_id]) - k)
        if left_n <= 0:
            break
    return out


def can(state, wing_id: str, n: int, fighters: bool = False) -> bool:
    """Can the wing send n more aircraft today? `fighters`: they are fighters (a raid's escort), which must also be free this turn after the patrols and the reserve."""
    if fighters:
        fl = _fighters_left(state, wing_id)
        if fl is not None and fl < n:
            return False
    return used(state, wing_id) + n <= budget(state, wing_id)


def spend(state, wing_id: str, n: int, fighters: bool = False) -> None:
    """Book n aircraft-sorties against a wing's day (raids and the supply round's red strikes; since v0.41.340 not the patrols). `fighters`: also take them off this turn's free fighters."""
    ra = getattr(state, "red_air", None)
    if ra is None:
        return
    ra.setdefault("used", {})
    ra["used"][wing_id] = int(ra["used"].get(wing_id, 0)) + int(n)
    if fighters and ra.get("left") is not None and wing_id in ra["left"]:
        ra["left"][wing_id] = max(0, int(ra["left"][wing_id]) - int(n))


def red_ledger(state, level: int, ready_min: int):
    """Red's fighter squadrons' jets for one turn, as a `packages.Ledger` keyed by RedSquadron id: `free` = ready now less the reaction reserve, `late` = ready by `ready_min`
    (the second wave). A cratered or destroyed field, a resting squadron and a non-fighter squadron have none. -> (ledger, {squadron id: jets held back})."""
    from .packages import Ledger
    led = Ledger.__new__(Ledger)
    led.free, led.late = {}, {}
    units = []
    for w in sorted(state.enemy_air, key=lambda w: w.base_asset_id):
        a = state.assets.get(w.base_asset_id)
        if a is None or a.destroyed or runways.is_closed(state, w.base_asset_id):      # v0.41.254: a cratered field flies no patrols
            continue
        for q in w.sqns:
            if q.aircraft not in ENEMY_FIGHTERS or q.reserve > 0:                      # v0.41.53: only a fighter squadron flies patrols; a resting one is out
                continue
            led.free[q.id] = q.available
            led.late[q.id] = max(0, refit.ready_by(q, ready_min) - q.available)
            units.append(q)
    return led, reserve.apply(led, units, level)


def _today(state):
    ra = getattr(state, "red_air", None)
    if not ra or ra.get("day") != state.day:
        ra = begin_day(state)
    return ra


def plan_turn(state, d, turn: int | None = None, t0: int | None = None, rng: random.Random | None = None) -> list:
    """THIS TURN's red patrols and sweeps (v0.41.340, Phase 5a; it was one plan for the whole day). `turn` defaults to the current one; `t0` = the turn's first minute of the day;
    `rng` is seeded by the turn. The pairs are crewed from `red_ledger` (ready jets less the reserve, then the ones ready by the second wave), one pair per BARCAP area, `RED_CAP_SHARE`
    of the areas that can be up; a short-legged pair costs two. Flights are added to `state.red_air["flights"]` (earlier turns' stay; this turn's earlier plan is replaced).
    -> this turn's flights [{id, kind CAP|SWEEP, wing (base asset id), type, size, start, end (minutes of the day), x, y, area, bearing, ax, ay, turn, wave, squadron}]."""
    from . import blue_barcap
    from .timeofday import WAVE2_OFFSET_MIN
    turn = state.turn if turn is None else turn
    t0 = clock.minute(turn) - clock.day_start_minute(state.day) if t0 is None else t0
    t1 = t0 + clock.TURN_MIN
    rng = rng or random.Random(f"{state.campaign_id}:{turn}:redair")
    lvl = _level(d)
    ra = _today(state)
    night = clock.is_night_turn(turn)
    led, held = red_ledger(state, lvl, clock.minute(turn) + WAVE2_OFFSET_MIN)
    bc = barcap.ensure(state)
    flights, cands = [], []
    for w in sorted(state.enemy_air, key=lambda w: w.base_asset_id):
        sqs = [q for q in w.sqns if q.id in led.free]
        if sqs:
            cands += [(w, ar, sqs) for ar in bc["red"] if ar["asset"] == w.base_asset_id]
    want = RED_CAP_SHARE[lvl][1 if night else 0] * len(cands)
    want = int(want) + (1 if rng.random() < want - int(want) else 0)        # a share of the areas that can be up, a fraction is a seeded chance of one more
    order = list(range(len(cands)))
    rng.shuffle(order)
    up = 0
    for i in order:
        if up >= want:
            break
        w, ar, sqs = cands[i]
        got = blue_barcap._pairs(led, sqs, t0, t1, 0)                        # the same crewing as blue's: a long-legged pair holds the turn, a short-legged one is relieved in wave 2 (no `keep`: the reserve is red's pair kept back)
        for j, (sq, wave, lo, hi) in enumerate(got):
            flights.append({"id": f"rf{turn}-{ar['id']}.{j}", "kind": "CAP", "wing": w.base_asset_id, "type": sq.aircraft, "size": 2, "start": lo, "end": hi, "x": ar["x"], "y": ar["y"],
                            "area": ar["id"], "bearing": ar["bearing"], "ax": ar["ax"], "ay": ar["ay"], "turn": turn, "wave": wave, "squadron": sq.id})
        up += 1 if got else 0
    g = state.ground or {}
    contested = [i for i, (r, b) in enumerate(zip(g.get("red", []), g.get("blue", []))) if r >= 15 and b >= 15]
    sw_p = 0.0 if night else SWEEPS_PER_DAY[lvl] / max(1, DAY_TURNS)         # the day's sweeps spread over its day turns by a seeded chance (judgment call)
    if contested and rng.random() < sw_p:
        owner = {q.id: (w, q) for w in state.enemy_air for q in w.sqns}
        spare = [owner[sid] for sid in sorted(led.free) if led.room(sid, 2) >= 2]
        if spare:
            w, sq = spare[rng.randrange(len(spare))]
            wave = 1 if led.room(sq.id, 1) >= 2 else 2
            led.take(sq.id, 2, wave)
            c = g["centers"][rng.choice(contested)]
            lo = t0 + (WAVE2_OFFSET_MIN if wave == 2 else 0) + rng.randrange(0, SWEEP_START_SPREAD_MIN + 1, 10)
            flights.append({"id": f"rf{turn}-{w.base_asset_id}-s", "kind": "SWEEP", "wing": w.base_asset_id, "type": sq.aircraft, "size": 2, "start": lo, "end": min(t1, lo + SWEEP_MIN),
                            "x": float(c[0]), "y": float(c[1]), "turn": turn, "wave": wave, "squadron": sq.id})
    ra["flights"] = [f for f in ra.get("flights", []) if f.get("turn") is not None and f["turn"] < turn] + flights      # earlier turns of the day stay; this turn's earlier plan (and an old whole-day plan, no `turn`) goes
    ra["turn"] = turn
    ra["react_hold"] = held                                                  # squadron id -> jets kept back this turn (Phase 6 reads it)
    ra["left"] = {w.base_asset_id: sum(led.free.get(q.id, 0) for q in w.sqns) for w in state.enemy_air}      # ready fighters each wing has left after the reserve and this turn's pairs (`can(fighters=True)`)
    free = {sid: int(n) for sid, n in led.free.items()}                      # fighters: after the reserve and the pairs above; attack squadrons (raiders, the Tu-22M3): every ready jet, the reserve is for fighters only
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if a is None or a.destroyed or runways.is_closed(state, w.base_asset_id):
            continue
        for q in w.sqns:
            if q.aircraft not in ENEMY_FIGHTERS and q.reserve <= 0:
                free[q.id] = int(q.available)
    ra["free"] = free                                                        # the turn's one pool of free red jets: raids book from it (`take_ready`), see the module doc
    return flights


GUARD_NM = 150                 # v0.41.11: a patrol guards a SAM site within this of its own field (was 60: the big rear wings guarded only their own
                               # local sites and the front, Sukhumi and Gudauta, went unguarded in the v0.41.10 run)
CALLIN_LINK_NM = 40            # v0.41.73: a patrol is linked to (and called in to) the best-rated SAM site within this of its BARCAP station (judgment call)
GUARD_FWD_NM = 10              # ...from a station this far in front of the site, toward the nearest friendly (blue) field
GUARD_VALUE = {"SA-10": 4.0, "SA-11": 3.0, "SA-6": 2.5, "SA-15": 2.0, "SA-19": 1.5, "SA-8": 1.5, "SA-3": 1.5, "SA-2": 1.2}
# v0.41.20: no needless banzai, red's side. "commit": red fighters go after blue only with at least this quality-weighted edge (red : blue), except
# over their own field or a SAM site blue is attacking (then at any odds). "soft": how much a raid's pick shies from a target under a full Patriot
# (and on Hard also from your home field's HAWK): 1.0 = not at all (Easy's careless red).
RED_DOCTRINE = {1: {"commit": 0.0, "soft": 1.0, "hawk": False}, 2: {"commit": 1.0, "soft": 0.5, "hawk": False}, 3: {"commit": 2.0, "soft": 0.25, "hawk": True}}
RED_QUALITY = {"MiG_29A": 0.67, "MiG_29S": 0.67, "Su_27": 0.67, "MiG_31": 0.67, "MiG_21Bis": 0.5, "MiG_23MLD": 0.5, "F_4E": 0.5, "F_5E_3": 0.5}   # one blue fighter = 1.0


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
    barcap.py). Whether red reads today's blue targets correctly follows the level (GUARD_READ), once per flight. Since v0.41.340 it is seeded by the turn and touches only THIS turn's flights."""
    ra = getattr(state, "red_air", None)
    if not ra:
        return
    lvl = max(1, min(3, int(getattr(d, "level", 1))))
    rng = random.Random(f"{state.campaign_id}:{state.turn}:redguard")
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
        if f.get("kind") != "CAP" or f.get("turn") != state.turn:
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
    """The current turn's plan, made on first use (a mission build, an old save, a night turn nobody planned): the day's shell if the day has none, then `plan_turn` when this turn has no plan.
    It never replans a turn that has one (v0.41.340; it used to plan the whole day)."""
    ra = _today(state)
    if ra.get("turn") != state.turn:
        plan_turn(state, d)
        ra = state.red_air
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
