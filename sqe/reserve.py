"""The reaction reserve (campaign rules plan decision 40, Phase 5a, v0.41.340): each side holds back a share of its READY fighters every turn for reactions
(scrambles, intercepts, Phase 6). The planners (blue's standing patrols and packages, red's patrols and sweeps) draw only on what is left.

Naming: "reserve" already means a RESTING squadron's jets (`Squadron.reserve`, `RedSquadron.reserve`, the rest rule in airwings.py). This module's word is the HOLD:
`react_hold`, the jets of a squadron kept back this turn. It is not a state field: the turn's holds are written into `state.barcap["react_hold"]` (blue) and
`state.red_air["react_hold"]` (red), plain dict keys that Phase 6 reads, so the save format does not change.

The hold is per squadron, so one field cannot empty: a squadron is asked for its own share, in whole pairs.
"""
from __future__ import annotations

REACTION_RESERVE = {1: 0.25, 2: 0.25, 3: 0.25}   # share of a squadron's ready fighters held back each turn, by level (judgment call: plan OPEN 4, XO: "see how it plays"; XO tunes it after flying Phase 5)


def share(level: int) -> float:
    return REACTION_RESERVE[max(1, min(3, int(level)))]


def held_back(ready: int, level: int) -> int:
    """Jets a squadron with `ready` serviceable jets keeps back: its share, rounded to the nearest whole PAIR (a reaction is a pair), but a squadron whose share
    comes to a whole jet or more keeps at least one pair back (4 ready at 25% = 2). A squadron whose share is under one jet holds none: a lone pair (2 or 3
    ready) stays free for tasking rather than sit idle (judgment call, comment of plan section 6.3). Never more than the squadron has."""
    k = share(level) * max(0, int(ready))
    if k < 1.0:
        return 0
    return min(int(ready), 2 * max(1, int(k / 2 + 0.5)))


def free_for_tasking(q, level: int) -> int:
    """Ready jets of one squadron (blue Squadron or RedSquadron) that the planner may use this turn: `available` less its hold."""
    return max(0, int(q.available) - held_back(q.available, level))


def apply(ledger, squadrons, level: int) -> dict:
    """Take the hold of each squadron off the ledger's ready pool (`ledger.free`; the late jets, ready only by the second wave, are not held). -> {squadron id: jets held}."""
    out = {}
    for q in squadrons:
        if q.id not in ledger.free:
            continue
        h = min(held_back(q.available, level), ledger.free[q.id])
        if h > 0:
            ledger.free[q.id] -= h
            out[q.id] = h
    return out


# ---- Phase 6a (v0.41.343): red's scrambles draw from the hold ------------------------------------------------------------------------------------------------
def _red_hold(state) -> dict:
    return ((getattr(state, "red_air", None) or {}).get("react_hold") or {})


def red_hold_left(state, wing, drawn: dict | None = None, types=None) -> int:
    """Jets of `wing` (an EnemyAirWing) still held for reactions: per squadron the turn's hold (`red_air["react_hold"]`, written by `redair.plan_turn`), never more than the squadron has ready now, less
    what this mission already drew (`drawn`: squadron id -> jets). `types`: count only squadrons of those aircraft types. An old save, or a turn not planned yet, has no hold: 0."""
    drawn = drawn if drawn is not None else {}
    h = _red_hold(state)
    return sum(max(0, min(int(h.get(q.id, 0)), int(q.available)) - drawn.get(q.id, 0)) for q in wing.sqns if types is None or q.aircraft in types)


def pick_red_hold(state, wing, drawn: dict, types=None, n: int = 2):
    """The squadron of `wing` a reaction pair comes from: the one with the most hold left (ties: the wing's order), with `n` or more left. Books the draw in `drawn` and returns the squadron; None when the wing
    has nothing held (then it sends nothing)."""
    h = _red_hold(state)
    best, left = None, n - 1
    for q in wing.sqns:
        if types is not None and q.aircraft not in types:
            continue
        k = max(0, min(int(h.get(q.id, 0)), int(q.available)) - drawn.get(q.id, 0))
        if k > left:
            best, left = q, k
    if best is not None:
        drawn[best.id] = drawn.get(best.id, 0) + n
    return best


# ---- Phase 6b (v0.41.344): the war sim spends the hold ----------------------------------------------------------------------------------------------------
REACTION_PAIRS = 1          # pairs of red fighters a package that meets a reaction draws from the hold (campaign rules plan, Phase 6 / section 6: judgment call, low firmness; one pair per package keeps the hold lasting a few packages)
RED_LOSS_PER_BLUE = 0.7     # red fighters shot down per blue aircraft the package loses (campaign rules plan section 6 calibration: judgment call, low firmness; keeps the L3 war roughly 50:50)


def red_drawn(state) -> dict:
    """The turn's per-squadron draws of the red hold (`red_air["react_drawn"]`, reset when `redair.plan_turn` writes a new hold). Missing key (old save): nothing drawn yet."""
    ra = getattr(state, "red_air", None)
    if ra is None:
        return {}
    return ra.setdefault("react_drawn", {})


def reaction_draw(state, side: str, package, rng=None) -> list:
    """The jets a package's reaction takes from the hold. `side` "red": up to REACTION_PAIRS pairs from the red hold of the wings within `reactive.INTERCEPT_NM` of the package's target (nearest wing first,
    `pick_red_hold`), booked in `red_air["react_drawn"]`. -> [(RedSquadron, jets)]; [] when no hold is left near the target (then nothing reacts). Blue's side is the FLEET_DEFENSE crewing in
    `Session.plan_turn` (it needs the ledger), not this function."""
    if side != "red":
        return []
    import math
    from .reactive import INTERCEPT_NM
    from .routes import NM
    t = state.assets.get(package.objective.target_id)
    if t is None:
        return []
    ra = getattr(state, "red_air", None)
    if not ra or not ra.get("react_hold"):
        return []
    drawn = red_drawn(state)
    wings = []
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if a is None or a.destroyed:
            continue
        nm = math.hypot(a.x - t.x, a.y - t.y) / NM
        types = {x for x in w.general_types_up(state) if INTERCEPT_NM.get(x, 120) >= nm}
        if types:
            wings.append((nm, w.base_asset_id, w, types))
    out = []
    for _ in range(REACTION_PAIRS):
        for nm, _b, w, types in sorted(wings, key=lambda x: (x[0], x[1])):
            sq = pick_red_hold(state, w, drawn, types)
            if sq is not None:
                out.append((sq, 2))
                break
    return out
