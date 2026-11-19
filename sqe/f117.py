"""The F-117A Nighthawk (S104, XO 2026-11-17 / 18; plan `.claude/f117-plan.md`): blue's small AI-only night squadron. It flies ONLY at night and ONLY against red early-warning radars and
red SAM sites that no red air can reach, one package of two to four jets with no escort, no SEAD and no stand-by tanker beyond what any strike has. Three small pieces live here:

* `covered(state, x, y)`: the "red air reaches this point" test the planner uses (one constant, `COVER_NM`).
* `objectives(state, skip)`: this turn's F-117A jobs (night turns of a campaign with night ops on; none without a squadron). Each is an ordinary STRIKE objective with `aim == "F117"`:
  `packages.PackageBuilder._slots` gives it one STRIKE slot only the F-117A fills (`Slot.only`), the mission builder flies it like any strike (laser GBU-27 on the target), and the war sim
  resolves it with `resolve` below.
* `resolve(sim, state, pkg)`: the war sim's roll for such a package: a hit chance per pair of jets, the target destroyed on a hit, a small loss chance per jet that grows with the live SAM sites
  that cover the target (one F-117A was shot down by an SA-3 in 1999, Serbia: firm, public).

Every number is a judgment call unless a source is named; see the constants.
"""
from __future__ import annotations

import math

from . import clock
from .models import AssetKind, ObjectiveType

KEY = "F-117A"
NM = 1852.0
COVER_NM = 40.0           # JUDGMENT CALL (one constant, XO's rule 2026-11-17: "no red CAP station, alert pair or BARCAP station can reach it"): red air covers a point within this far of one of red's BARCAP stations
                          # (`barcap.ensure(state)["red"]`) or of a red field that holds ready fighters (an alert pair). 40 nm is the engage circle the red air picture already uses for a patrol and an alert pair
                          # (`red_air_picture.ALERT_ZONE_NM` / `CALLIN_ZONE_NM`), not its 130 nm alert reach (a stealth jet at night is only found by a pair already close to it). Almost every EWR and SAM site stands by a
                          # fighter field, so the plan finds a target only once red's fighters there are gone: the probe prints how many qualify at 60 / 40 / 30 / 20 nm.
PAIR_HIT = 0.6            # JUDGMENT CALL: chance that one pair of F-117As destroys its target (laser-guided GBU-27, night, no escort); a package of 4 jets rolls it for each pair (0.84)
LOSS_BASE = 0.01          # JUDGMENT CALL: the chance a jet is shot down on a sortie against a target no live SAM covers (public: 1 F-117A lost to an SA-3 in the 1999 campaign, about 0.1% of its sorties; the game's scale is coarser)
LOSS_PER_SAM = 0.01       # ...plus this for every live SAM site (the target itself included) whose ring covers the target
LOSS_MAX = 0.15
PACKAGES_PER_TURN = 2     # JUDGMENT CALL: at most this many F-117A jobs in one night turn (a squadron of 12 with a 16 h refit puts about 3 pairs up a night)
COOLDOWN_DAYS = 7        # JUDGMENT CALL (XO 2026-11-19: the real F-117 that was shot down kept flying the same thing on the same route): the same target is not offered again for this many days after a strike on it
APPROACH_MIN_DEG, APPROACH_MAX_DEG = 25.0, 80.0      # JUDGMENT CALL: the IP is on a bearing this far (either side) off the straight line from the base, drawn per sortie
MIN_VALUE_VARIANTS = ("SA-5", "SA-10")      # the long-range killers come first (their priority is doubled)


def _last(state) -> dict:
    return ((state.raids or {}).get("f117_last") or {})


def cooling(state, target_id: str) -> bool:
    """Was this target struck by an F-117A less than COOLDOWN_DAYS ago?"""
    d = _last(state).get(target_id)
    return d is not None and state.day - int(d) < COOLDOWN_DAYS


def approach_deg(state, package, base_xy, tx, ty, profile) -> float:
    """S104c (XO 2026-11-19: "does it do different routes every time"): the bearing (degrees off the straight base-to-target line) an F-117A sortie's IP sits on. Drawn from a Random seeded by campaign,
    day, turn and target, so a replan or a second build of the same sortie gives the same route and another night another one. Up to 8 draws; one whose IP, or the IP-to-target leg, lies inside the ring
    (plus 5 nm) of a live SAM site OUTSIDE the target's own cluster (15 nm round it) is thrown away; none left: 0 (the plain route, as before)."""
    import random
    from . import threatmap as tm
    from .routes import offset
    tgt = state.assets.get(package.objective.target_id)
    skip = tm.cluster_ids(tgt)
    rings = [(a.x, a.y, r + 5 * NM) for a, r in tm.rings(state) if a.id not in skip and math.hypot(a.x - tx, a.y - ty) > 15 * NM]      # the target's own cluster (15 nm round it) is the run-in's business, as for every strike
    hdg = math.degrees(math.atan2(ty - base_xy[1], tx - base_xy[0])) % 360
    rnd = random.Random(f"{state.campaign_id}:{state.day}:{state.turn}:{package.objective.target_id}:f117route")
    def hit(ip):                                              # the rings this IP or its leg to the target lies in
        return {i for i, (x, y, r) in enumerate(rings) if math.hypot(ip[0] - x, ip[1] - y) <= r or tm.seg_dist(x, y, ip[0], ip[1], tx, ty) <= r}
    plain = hit(offset(tx, ty, hdg + 180, profile.ip_nm * NM))   # what the plain route already lies in (an SA-10 can cover the whole area round a target): a draw may not add a ring to that
    for _ in range(8):
        dev = rnd.uniform(APPROACH_MIN_DEG, APPROACH_MAX_DEG) * rnd.choice((-1.0, 1.0))
        if hit(offset(tx, ty, hdg + 180 + dev, profile.ip_nm * NM)) <= plain:
            return dev
    return 0.0


def squadrons(state) -> list:
    return [q for q in state.squadrons.values() if q.aircraft == KEY]


def ready_jets(state) -> int:
    return sum(q.available for q in squadrons(state))


def is_job(obj) -> bool:
    """Is this objective an F-117A night job: the EWR / SAM strike (aim F117) or the runway strike (aim RUNWAY, id `obj-t<turn>-f<k>`)?"""
    return obj.type == ObjectiveType.STRIKE and (obj.aim == "F117" or (obj.aim == "RUNWAY" and obj.id.rsplit("-", 1)[-1].startswith("f")))


def covered(state, x: float, y: float, own: str = "") -> bool:
    """Can red air reach (x, y)? True when a red BARCAP station (today's areas) or a red airfield with a ready fighter pair lies within COVER_NM of it. `own` (a red field id, for the runway strike): that
    field's own station and alert pair do not count (they are what the crater catches on the ground); the other fields' still do."""
    from . import barcap
    from .loadouts import ENEMY_FIGHTERS
    reach = COVER_NM * NM
    for ar in barcap.ensure(state)["red"]:
        if ar["asset"] != own and math.hypot(ar["x"] - x, ar["y"] - y) < reach:
            return True
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if a is None or a.destroyed or w.available_of(ENEMY_FIGHTERS) < 2 or a.id == own:
            continue
        if math.hypot(a.x - x, a.y - y) < reach:
            return True
    return False


def reachable(state, a) -> bool:
    """Can a ready F-117A pair fly to `a`? Within its combat radius (no tanker bonus counted: conservative) and with no intact SAM belt of ANOTHER cluster in front of the target (the FLOT rule the packages
    use for every strike, `threatmap.blockers`: the F-117A is NOT excused from it; stealth in DCS is simplified, so nothing is assumed)."""
    from . import threatmap as tm
    from .aircraft import AIRCRAFT
    for q in squadrons(state):
        b = state.bases.get(q.base_id)
        if b is None or q.available < 2:
            continue
        if math.hypot(a.x - b.x, a.y - b.y) / NM > AIRCRAFT[KEY].combat_radius_nm:
            continue
        if tm.blockers(state, (b.x, b.y), (a.x, a.y), a):
            continue
        return True
    return False


def targets(state, skip=frozenset()) -> list:
    """[(priority, asset)] best first: live red EWRs and SAM sites of the long-range kind (a ring of 10 nm or more, the DEAD planner's own filter) that red air does not cover."""
    from . import ground, threatmap as tm
    out = []
    for a in state.assets.values():
        if a.destroyed or a.id in skip or a.id.startswith("fsam_"):
            continue
        if a.kind == AssetKind.SAM:
            if tm.RANGE_NM.get(a.variant, 0) < 10 or a.value < 5:
                continue
        elif a.kind != AssetKind.EWR:
            continue
        if cooling(state, a.id):
            continue
        if a.health <= ground.DOWN_HEALTH and ground.active(state):
            continue                                        # down for planning (a threshold): it mends on its own, not hunted
        if covered(state, a.x, a.y) or not reachable(state, a):
            continue
        pr = a.value * a.health * (2.0 if a.variant in MIN_VALUE_VARIANTS else 1.0)
        out.append((pr, a))
    out.sort(key=lambda t: (-t[0], t[1].id))
    return out


def runway_targets(state, skip=frozenset()) -> list:
    """[(priority, airfield asset)] best first (XO 2026-11-19: "the Nighthawks do OCA runways if red did not schedule a patrol"): red fields with a wing that has ready jets and an open runway, no OTHER red field's patrol
    station or alert pair within COVER_NM, and in reach with no belt in front. The field's own station and alert pair are ignored. Priority as the day jobs' runway craters (value x 0.9 x the wing's ready share)."""
    from . import runways
    out = []
    for a in state.assets.values():
        if a.kind != AssetKind.AIRFIELD or a.destroyed or a.id in skip or runways.is_closed(state, a.id) or cooling(state, a.id):
            continue
        w = state.enemy_air_at(a.id)
        if w is None or w.available <= 0 or covered(state, a.x, a.y, own=a.id) or not reachable(state, a):
            continue
        out.append((a.value * 0.9 * (w.available / max(1, w.authorized)), a))
    out.sort(key=lambda t: (-t[0], t[1].id))
    return out


def objectives(state, skip=frozenset()) -> list:
    """This turn's F-117A jobs, [Objective] (ids are given by the caller). Night turns only, and only in a campaign with night ops on (as the Tu-22M3 raids); one job per ready pair, at most
    PACKAGES_PER_TURN."""
    from .models import Objective
    if not squadrons(state) or not getattr(state, "night_ops", False) or not clock.is_night_turn(state.turn):
        return []
    n = min(PACKAGES_PER_TURN, ready_jets(state) // 2)
    if n <= 0:
        return []
    first_night = not clock.is_night_turn(state.turn - 1)                 # the runway strike is offered on the FIRST turn of the night only: at most one a night (a field cratered every night stays shut, and the first probe flew two a night)
    cands = [(pr, a, "F117") for pr, a in targets(state, skip)[:n]] + ([(pr, a, "RUNWAY") for pr, a in runway_targets(state, skip)[:1]] if first_night else [])
    out = []
    for pr, a, aim in sorted(cands, key=lambda c: (-c[0], c[1].id))[:n]:
        if aim == "RUNWAY":
            out.append(Objective("", ObjectiveType.STRIKE, a.id, pr, f"Night OCA: Runway Strike, {a.name} (F-117A, no other red patrol can reach it)", "RUNWAY"))
        else:
            out.append(Objective("", ObjectiveType.STRIKE, a.id, pr, f"Night strike: {a.name} (F-117A, no red air can reach it)", "F117"))
    return out


def cover_count(state, a) -> int:
    """Live red SAM sites whose ring covers the target `a` (itself included when it is one)."""
    from . import threatmap as tm
    n = 0
    for s in state.assets.values():
        if s.kind != AssetKind.SAM or s.destroyed or s.health <= 0.25:
            continue
        r = tm.RANGE_NM.get(s.variant, 0)
        if r > 0 and (s is a or math.hypot(s.x - a.x, s.y - a.y) <= r * NM):
            n += 1
    return n


def resolve(sim, state, pkg, force=None) -> dict:
    """The war sim's roll for an F-117A package (`WarSimulator.resolve_abstract` calls it for `aim == "F117"`): the target is destroyed with chance `1 - (1 - PAIR_HIT) ** pairs`; each jet is lost with chance
    LOSS_BASE + LOSS_PER_SAM x the live SAM sites that cover the target (at most LOSS_MAX)."""
    from .war import chance, count_roll
    d, rng = sim.d, sim.rng
    t = state.assets[pkg.objective.target_id]
    flights = [f for f in pkg.flights if f.count > 0 and not f.tag]
    pairs = max(1, sum(f.count for f in flights) // 2)
    p = 1.0 - (1.0 - PAIR_HIT) ** pairs
    success = force["success"] if force and "success" in force else chance(rng, p, d.variance)
    if state.raids is None:
        state.raids = {}
    state.raids.setdefault("f117_last", {})[t.id] = state.day                       # the cooldown clock: struck (hit or not) today
    lines = [f"{pkg.objective.description}: {'objective achieved' if success else 'no effect observed'}"]
    if success and pkg.objective.aim == "RUNWAY":
        from . import runways
        lines.append("   " + runways.crater(state, t.id))
    elif success:
        t.health = 0.0
        lines.append(f"   {t.name}: destroyed")
    ncov = cover_count(state, t)
    loss_p = min(LOSS_MAX, LOSS_BASE + LOSS_PER_SAM * ncov)
    lost_by = {}
    for f in flights:
        lost = count_roll(rng, f.count, loss_p, d.variance)
        if lost:
            sq = state.squadrons[f.squadron_id]
            sq.available = max(0, sq.available - lost)
            lost_by[f.id] = lost
            lines.append(f"   {f.callsign} lost {lost} aircraft")
    for ln in lines:
        state.note(ln.strip())
    return {"success": success, "odds": p, "lines": lines, "objective": pkg.objective.description, "roll": {"success": success}, "lost_by": lost_by}
