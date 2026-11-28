"""S234 (XO 2026-11-27, dynamic planning): blue learns from the last round. When a strike, DEAD or CAS package fails or bleeds and red's fighters
are the bigger part of what it met, blue's planners raise their estimate of red's fighters in that area by one 2-ship flight for the next
packages of that kind there (at most LEARN_STEP_MAX flights). The estimate is what sizes the cover (`packages.PackageBuilder.build`:
`threat.fighters_required`), so the TARCAP grows first, and once it is a full 4-ship the area gets a Fighter Sweep ahead of the packages
(`engine` sweep step, `sweep_4ships`). The extra fades one flight every LEARN_FADE_DAYS days with no new such loss.

Doctrine (public sources, firmness medium for the principle, the step sizes are judgment calls): air planners re-assess every package's
results and change the next force package to match (JP 3-30 "Joint Air Operations", the assessment step of the joint air tasking cycle;
USAF Linebacker II, December 1972: after the losses of nights 1 to 3 the routes, timing and support packages were changed for the
following nights; the Eighth Air Force after the 1943 Schweinfurt raids: deep raids waited until escort could be sent). No dice: what
blue does follows from what it saw (memory `no-dice-for-decisions`).

Stored in `state.raids["cover_learn"]`: {"<kind>:<area>": {"step": flights, "day": day written}}; kept from turn to turn (engine keep list)."""
from .models import ObjectiveType

LEARN_STEP_MAX = 2          # at most this many extra expected red 2-ship flights (judgment call: two steps are a bigger TARCAP, then a sweep)
LEARN_FADE_DAYS = 2         # one step fades after this many days with no new loss to fighters in that area (judgment call)
LEARN_LOST_MIN = 2          # jets lost that count as "bled" for a package that still succeeded (judgment call; a failed package counts from 1)
LEARN_FIGHTER_SHARE = 0.5   # red fighters must be at least this share of the package's defence (the war sim's air term against its SAM term)

LEARN_KINDS = (ObjectiveType.STRIKE, ObjectiveType.DEAD, ObjectiveType.CAS)


def _area_key(state, obj) -> str:
    """The memory's key: the job kind and its ground sector (`war.job_sector`), or its target when the campaign has no sectors."""
    from . import war
    sector = war.job_sector(state, obj)
    if sector is None:
        return f"{obj.type.value}:t:{obj.target_id}"
    return f"{obj.type.value}:s:{sector}"


def _table(state) -> dict:
    if state.raids is None:
        state.raids = {}
    return state.raids.setdefault("cover_learn", {})


def _step_now(entry, day: int) -> int:
    """An entry's step today, after the fading."""
    days_since = max(0, int(day) - int(entry.get("day", day)))
    faded = days_since // LEARN_FADE_DAYS
    return max(0, int(entry.get("step", 0)) - faded)


def extra_flights(state, obj) -> int:
    """How many red 2-ship flights blue now expects in this job's area beyond its intel picture (0 when nothing was learned or it faded)."""
    if obj.type not in LEARN_KINDS:
        return 0
    entry = ((state.raids or {}).get("cover_learn") or {}).get(_area_key(state, obj))
    if not entry:
        return 0
    return _step_now(entry, state.day)


def fighter_share(sim, state, pkg):
    """Before the war sim resolves `pkg`: the share of its defence that is red's fighters (the air term of `WarSimulator.odds` against the
    whole), or None when the package is not one this memory follows, its target cannot be met by red fighters (intel expects no flight
    there) or it has no defence at all."""
    from . import threat, war
    from .packages import is_sweep, target_point
    obj = pkg.objective
    if obj.type not in LEARN_KINDS or is_sweep(obj) or pkg.extra.get("scrub"):
        return None
    if obj.target_id not in state.assets:
        return None
    xy = target_point(state, obj)
    if xy is None:
        return None
    iads = sim.d.iads
    if threat.defender_flights(threat.expected_defenders(state, xy[0], xy[1], iads)) < 1:
        return None
    _p, _strength, defense = sim.odds(state, pkg)
    if defense <= 0:
        return None
    air = war._air_cover(state, iads)
    return min(1.0, air / defense)


def note(state, pkg, result: dict, share) -> bool:
    """After a package is resolved: raise the area's step by one when it failed with a loss or lost LEARN_LOST_MIN jets, and red's fighters were
    at least LEARN_FIGHTER_SHARE of its defence. -> True when the memory was raised."""
    if share is None or share < LEARN_FIGHTER_SHARE:
        return False
    lost = 0
    for jets in (result.get("lost_by") or {}).values():
        lost += int(jets)
    failed = not result.get("success")
    if lost < 1:
        return False
    if not failed and lost < LEARN_LOST_MIN:
        return False
    table = _table(state)
    key = _area_key(state, pkg.objective)
    entry = table.get(key) or {}
    step = _step_now(entry, state.day) if entry else 0
    table[key] = {"step": min(LEARN_STEP_MAX, step + 1), "day": int(state.day)}
    return True
