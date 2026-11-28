"""S234b (XO 2026-11-27, dynamic planning, the red half of S234): red learns from its raids. When a land raid or a SEAD raid is stopped by
blue's fighters (or gets through but loses LEARN_LOST_MIN raiders), and blue's fighters were most of what stopped it (not the field's own
air defence), red's planners give the next raid of that kind on that target one more escort pair, and at the second step a bigger
raid: a SEAD raid gets one more SEAD package and a bigger sweep ahead of it (`raids.SEAD_SWEEP_*`); a bomber raid's extra escorts are
split by the mission builder's own rule (half the escort groups fly a sweep ahead once there are three or more, `raid_spawns`).
The extra fades one step every LEARN_FADE_DAYS days with no new such loss, as blue's does (`cover_learn`).

Doctrine (public sources, firmness medium for the principle, the step sizes are judgment calls): the same re-assessment of the last
raid that blue's planners make (JP 3-30, assessment); Soviet / Russian air operations doctrine sizes the fighter cover of a strike
group to the expected fighter opposition (escort and a clearing group ahead of the strikers; judgment call how many more after a loss).
No dice: what red does follows from what it saw (memory `no-dice-for-decisions`).

The jets come from red's same wings (`raids.plan_raid` books them from the turn's ready jets), so a bigger raid leaves fewer jets for the
next raids that turn: the cost shows in the raids a day and the bombers flown (the wars probe, `probes/s212/win_ratio.py --feel`).

Not the carrier setpiece (its escorts are `bombers.ESCORT_PER_BOMBER`), and flown missions do not write the memory (as blue's).

Stored in `state.raids["red_cover_learn"]`: {"<kind>:<base id>:<aim>": {"step": steps, "day": day written}}; kept from turn to turn (engine keep list)."""
from .cover_learn import LEARN_STEP_MAX, LEARN_FADE_DAYS, LEARN_LOST_MIN, LEARN_FIGHTER_SHARE

MIN_LEVEL = 2             # Levels 2 and 3 only: Level 1's red is an insurgent force that keeps its raids as they are (judgment call: with it a 2-jet raid flew 6 escorts)
ESCORTS_PER_STEP = 2     # one more escort pair per step (judgment call, the same pair blue's TARCAP grows by)
SEAD_WAVE_STEP = 2        # at this step a SEAD raid adds one more SEAD package (`raids.sead_n` jets) and a 4-ship more sweep (judgment call)
SWEEP_PER_WAVE_STEP = 4   # ...the sweep's extra fighters at that step


def area_key(base_id: str, aim: str, sead: bool) -> str:
    """The memory's key: the raid kind (a SEAD raid, or the kind of its aim: field, supply, garrison, sector, sam) and its target."""
    from .raids import aim_kind
    kind = "sead" if sead else aim_kind(aim or "")
    return f"{kind}:{base_id}:{aim or ''}"


def _table(state) -> dict:
    if state.raids is None:
        state.raids = {}
    return state.raids.setdefault("red_cover_learn", {})


def _step_now(entry, day: int) -> int:
    """An entry's step today, after the fading."""
    days_since = max(0, int(day) - int(entry.get("day", day)))
    faded = days_since // LEARN_FADE_DAYS
    return max(0, int(entry.get("step", 0)) - faded)


def step(state, base_id: str, aim: str, sead: bool) -> int:
    """How many steps red has learned for this raid's target today (0 when nothing was learned or it faded, and always 0 below MIN_LEVEL)."""
    if int(getattr(state, "level", 3)) < MIN_LEVEL:
        return 0
    table = (state.raids or {}).get("red_cover_learn") or {}
    entry = table.get(area_key(base_id, aim, sead))
    if not entry:
        return 0
    return _step_now(entry, state.day)


def extra_escorts(state, base_id: str, aim: str, sead: bool) -> int:
    """The escorts red adds to this raid for what it learned."""
    return ESCORTS_PER_STEP * step(state, base_id, aim, sead)


def note(state, pkg, result: dict) -> bool:
    """After the war sim resolved a raid package: raise its target's step by one when blue's fighters were at least LEARN_FIGHTER_SHARE of
    the force that met it, and it was stopped with raiders lost, or got through but lost LEARN_LOST_MIN raiders. -> True when raised."""
    ex = pkg.extra or {}
    if int(getattr(state, "level", 3)) < MIN_LEVEL:
        return False
    if not ex.get("land"):
        return False
    learn = result.get("red_learn")
    if not learn:
        return False
    if float(learn.get("share", 0.0)) < LEARN_FIGHTER_SHARE:
        return False
    lost = int(learn.get("raiders_lost", 0))
    if lost < 1:
        return False
    if not learn.get("stopped") and lost < LEARN_LOST_MIN:
        return False
    table = _table(state)
    key = area_key(pkg.objective.target_id, ex.get("aim", ""), bool(ex.get("sead")))
    entry = table.get(key) or {}
    step_before = _step_now(entry, state.day) if entry else 0
    table[key] = {"step": min(LEARN_STEP_MAX, step_before + 1), "day": int(state.day)}
    return True
