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
