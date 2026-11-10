"""The refit clock, replacements and the held queue (campaign rules plan, sections 3.2 and 4 Phase 1; v0.41.334).

A jet that flies lands, then spends a refit on the ground before it can fly again. Each squadron keeps `refit`, a list of the absolute minute (see
clock.py) at which each of those jets is ready. `available` keeps its old meaning, "ready now": about a dozen places do `sq.available -= lost` and all
keep working, a jet in refit is simply not in `available`. In Java terms: `available` is a counter, `refit` is a list of timestamps, and `step()` moves
items from one to the other.

Since Phase 3 (v0.41.337) `Session._tick` (engine.py) calls `commit_turn` for the turn's sorties, then `step` and `replacements` EVERY turn (they used to run
in `end_day`). Planning is still per day until Phase 4, so a day's packages can ask for more jets than are ready by their turn: `commit_flight` never moves
more jets than `available` holds (it cannot create jets) and `commit_turn` reports the shortfall.

Replacements (plan decisions 9, 16, 17, 18): a squadron below strength gets a pair every `24 / FI` hours (FI = Force Index, `ground.supply`, clamped at
FI_MIN); red gets it per wing (field). The Tu-22M3 squadrons and the E-3 get one airframe per 48 hours instead, with no FI scaling. A pair that arrives
while the runway is closed (`runways.is_closed`) is `held`, counted toward the strength but not flyable, and released when the runway reopens.

Every number here is XO's rule or a judgment call, as marked.
"""
from __future__ import annotations

from . import clock

SORTIE_MIN = 100                 # launch to landing; the same value as blue_barcap.PACKAGE_WINDOW_MIN (judgment call)
REFIT_MIN = {"A-10C": 120, "Su_25": 120, "Tu_22M3": 360, "E_3A": 360}   # rugged 2 h (A-10C, Su-25), high maintenance 6 h (Tu-22M3, E-3): XO 2026-11-08, game rules ("anecdotes")
STANDARD_REFIT_MIN = 180         # everything else: 3 h (XO 2026-11-08)
LIMP_MULT = 2.0                  # a limping jet's refit is doubled and scaled by Force Index: hours = base x 2 / FI (XO 2026-11-08; the shape of ground.supply_repair)
FI_MIN = 0.2                     # clamp only: Force Index can dip under the floor through sams.debt (judgment call)
LIMP_PER_LOSS = 1.0              # war sim: each surviving jet of a flight limps with chance (losses / sortie size) x this (judgment call, plan section 7)

REPL_PAIR = 2                    # ordinary replacements arrive as a pair (XO, queue S3)
REPL_BASE_MIN = 1440             # ...every 24 h at Force Index 1.0, 24 / FI hours in general (XO, queue S3 / plan decision 16)
SLOW_TYPES = ("Tu_22M3", "E_3A") # high-maintenance types: lost outright, replaced one at a time and slowly (XO 2026-11-08)
SLOW_REPL_MIN = 2880             # one airframe per 48 hours, no Force Index scaling (XO 2026-11-08)


def fi_of(state, side: str) -> float:
    """The Force Index of one side (the old 'supply', ground.supply), 0.35 to 1.0 (0.70 and up for red on Level 1), less sams.debt."""
    from . import ground
    return ground.supply(state, side)


def refit_minutes(aircraft: str, limped: bool, fi: float) -> float:
    m = REFIT_MIN.get(aircraft, STANDARD_REFIT_MIN)
    return m * LIMP_MULT / max(FI_MIN, fi) if limped else m


def ready_minute(launch_min: int, aircraft: str, limped: bool, fi: float, sortie_min: int = SORTIE_MIN) -> int:
    """Absolute minute a jet that launched at `launch_min` can launch again."""
    return int(round(launch_min + sortie_min + refit_minutes(aircraft, limped, fi)))


def ready_by(q, minute: int) -> int:
    """Jets of this squadron (blue Squadron or RedSquadron) that can launch at `minute`: `available` plus the refit entries due by then."""
    return q.available + sum(1 for t in q.refit if t <= minute)


def _units(state):
    """(side, squadron, field id) for every blue squadron and every red squadron."""
    for sq in state.squadrons.values():
        yield "blue", sq, sq.base_id
    for w in state.enemy_air:
        for q in w.sqns:
            yield "red", q, w.base_asset_id


def step(state, now_min: int) -> list:
    """Jets whose ready minute has passed go back to `available` (or to `reserve` for a squadron that stood down to rest: `available` is 0 while it rests),
    never above the authorized strength. Then the held replacements of every field whose runway is open are released. -> log lines."""
    out = []
    for _side, q, _fid in _units(state):
        if not q.refit:
            continue
        due = [t for t in q.refit if t <= now_min]
        if not due:
            continue
        q.refit = [t for t in q.refit if t > now_min]
        if q.reserve > 0:
            q.reserve = min(q.authorized, q.reserve + len(due))
        else:
            q.available = min(q.authorized, q.available + len(due))
    out += release_held(state)
    return out


def release_held(state) -> list:
    """Replacements that waited on a closed runway are flyable again once it reopens (plan decision 15)."""
    from . import runways
    out = []
    for sq in state.squadrons.values():
        if sq.held and not sq.reserve and not runways.is_closed(state, sq.base_id):         # a resting squadron keeps them until it is back
            k, sq.held = sq.held, 0
            _add(sq, k)
            out.append(f"{sq.name}: the runway at {runways._name(state, sq.base_id)} is open again, {k} waiting replacement(s) join ({sq.available}/{sq.authorized})")
    for w in state.enemy_air:
        if runways.is_closed(state, w.base_asset_id):
            continue
        if w.held:
            k, w.held = w.held, 0
            w.replenish(k, skip=SLOW_TYPES)
            out.append(f"{runways._name(state, w.base_asset_id)}: the runway is open again, {k} waiting replacement(s) join the wing")
        for q in w.sqns:
            if q.held and not q.reserve:
                k, q.held = q.held, 0
                _add(q, k)
    return out


def _add(q, n: int) -> int:
    """Put n jets into a squadron's `available`, up to what the squadron has room for (refit entries count as present). -> how many went in."""
    room = max(0, q.authorized - q.available - len(q.refit))
    k = min(int(n), room)
    q.available += k
    return k


def _deficit(q) -> int:
    """Jets a squadron is short of: authorized less what is ready, in refit or waiting on a closed runway."""
    return max(0, q.authorized - q.available - len(q.refit) - q.held)


def _period(fi: float) -> int:
    return int(round(REPL_BASE_MIN / max(FI_MIN, fi)))


def replacements(state, now_min: int) -> list:
    """New airframes. Called every turn by `Session._tick` (v0.41.337; it was `end_day`, once a day) (Phase 3: `Session._tick` calls it every turn). -> log lines (only the ones worth a note).
    Blue: each squadron that is not resting and is below authorized gets a pair when its timer is due, then the timer restarts at now + 24 / FI hours; the
    timer starts when a deficit first shows (a full squadron has no timer). Red: the same per WING with `replenish`. Tu-22M3 squadrons: one airframe per
    48 h. A closed runway turns the arrival into `held`."""
    from . import runways
    out = []
    fi = {"blue": fi_of(state, "blue"), "red": fi_of(state, "red")}
    for sq in state.squadrons.values():
        if sq.reserve > 0:                                              # resting or moving: the rest rule (airwings.py) brings it back
            continue
        short = _deficit(sq)
        if not short:
            sq.repl_due = 0
            continue
        if not sq.repl_due:
            sq.repl_due = now_min + _period(fi["blue"])
        if now_min >= sq.repl_due:
            k = min(REPL_PAIR, short)
            if runways.is_closed(state, sq.base_id):
                sq.held += k
                out.append(f"{sq.name}: {k} replacement(s) arrived, but the runway at {runways._name(state, sq.base_id)} is closed; they wait")
            else:
                _add(sq, k)
            sq.repl_due = now_min + _period(fi["blue"])
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if a is None or a.destroyed:                                    # a destroyed field cannot take new jets (end_day scatters the wing)
            continue
        closed = runways.is_closed(state, w.base_asset_id)
        slow = [q for q in w.sqns if q.aircraft in SLOW_TYPES and not q.reserve]
        for q in slow:                                                  # the Tu-22M3: one a time, 48 h, no Force Index scaling
            if not _deficit(q):
                q.repl_due = 0
                continue
            if not q.repl_due:
                q.repl_due = now_min + SLOW_REPL_MIN
            if now_min >= q.repl_due:
                if closed:
                    q.held += 1
                else:
                    _add(q, 1)
                q.repl_due = now_min + SLOW_REPL_MIN
        ordinary = [q for q in w.sqns if q.aircraft not in SLOW_TYPES and not q.reserve]
        short = max(0, sum(max(0, q.authorized - q.available - len(q.refit)) for q in ordinary) - w.held)
        if not short:
            w.repl_due = 0
            continue
        if not w.repl_due:
            w.repl_due = now_min + _period(fi["red"])
        if now_min >= w.repl_due:
            k = min(REPL_PAIR, short)
            if closed:
                w.held += k
                out.append(f"{runways._name(state, w.base_asset_id)}: {k} replacement(s) arrived, but the runway is closed; they wait")
            else:
                w.replenish(k, skip=SLOW_TYPES)
            w.repl_due = now_min + _period(fi["red"])
    return out


def commit_flight(unit, launch_min: int, flew: int, lost: int, fi: float, rng=None, limped: int | None = None, sortie_min: int = SORTIE_MIN) -> tuple:
    """One flight's survivors go from `available` to `refit` (call AFTER the flight's losses were taken off `available`, so a loss is not counted twice).
    `limped`: how many survivors limp, when the debrief says (the hook's `limped` list); else each survivor limps with chance (lost / flew) x LIMP_PER_LOSS.
    Never more than `available` goes into refit: a plan made before the refit clock existed can ask for jets that are already out (v0.41.337: Phase 4 plans against
    what is ready), and a jet must not be created out of that. -> (survivors that went into refit, limped)."""
    flew = max(0, int(flew))
    lost = max(0, min(int(lost), flew))
    surv = min(flew - lost, max(0, int(unit.available)))
    if surv <= 0:
        return 0, 0
    if limped is None:
        p = min(1.0, (lost / flew) * LIMP_PER_LOSS) if flew else 0.0
        limped = sum(1 for _ in range(surv) if rng is not None and rng.random() < p)
    limped = max(0, min(int(limped), surv))
    unit.refit = sorted(unit.refit + [ready_minute(launch_min, unit.aircraft, True, fi, sortie_min)] * limped
                        + [ready_minute(launch_min, unit.aircraft, False, fi, sortie_min)] * (surv - limped))
    unit.available = max(0, unit.available - surv)
    return surv, limped


def commit_turn(state, sorties: list, rng=None) -> list:
    """Commit a turn's flights (Session._tick calls it once per turn, after the losses came off `available`). Each sortie is a dict {"unit": Squadron or RedSquadron,
    "side": "blue" | "red", "launch_min", "flew", "lost", "limped"?, "sortie_min"?}; the caller counts each planned sortie once (an attached CAP appears in several packages; the engine
    dedupes by callsign). -> [(unit, survivors in refit, limped, short)]: `short` is how many survivors had no ready jet to move (an overbooked plan, see commit_flight)."""
    fi = {"blue": fi_of(state, "blue"), "red": fi_of(state, "red")}
    out = []
    for s in sorties:
        n, lp = commit_flight(s["unit"], s["launch_min"], s["flew"], s["lost"], fi[s["side"]], rng, s.get("limped"), int(s.get("sortie_min") or SORTIE_MIN))      # a standing patrol that stays on station longer than SORTIE_MIN adds that to its sortie (v0.41.339)
        out.append((s["unit"], n, lp, max(0, int(s["flew"]) - int(s["lost"]) - n)))
    return out


def now_min(state) -> int:
    """The clock's absolute minute at the start of the current turn."""
    return clock.minute(state.turn)
