"""The carrier raid nobody flew and that got through (v0.41.109, XO 2026-10-22: "a bigger deal, random chance for spice, leaning towards yes it's a super duper
big deal at L3; at L2 carry on with what we have").

At Level 3 a raid that reaches the carrier hits it hard with chance BIG_P: every squadron on the deck loses a share of its aircraft, the group's air defence
drops, and the flight deck is out of action for a day and cut by half the day after. Level 2 and a raid you FLY keep their old, smaller results (a flown raid
is counted by what really reached the boat). All numbers are judgment calls: no public figure applies to a game carrier, tune on XO's runs."""
from __future__ import annotations

from .models import BaseKind

BIG_P = 0.8                   # chance a raid that gets through is the big one at Level 3
SQN_LOSS = (0.15, 0.35)       # share of each carrier squadron's serviceable aircraft lost on deck
DEFENSE_HIT = 0.25            # the carrier group's air defence strength lost (it repairs daily like any base's)
DEFENSE_FLOOR = 0.2


def big(state, d, rng):
    """-> log lines for a big hit, or None (Level 2 and below, or the dice say a lesser one)."""
    if int(getattr(d, "level", 1)) < 3 or rng.random() >= BIG_P:
        return None
    cv = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
    if cv is None:
        return None
    lines = [f"   MISSILES HIT {cv.name}: the flight deck is torn up"]
    total = 0
    for sq in sorted((s for s in state.squadrons.values() if s.base_id == cv.id and s.available > 0), key=lambda s: s.id):
        lost = min(sq.available, max(1, round(sq.available * rng.uniform(*SQN_LOSS))))
        sq.available -= lost
        total += lost
        lines.append(f"   {lost} aircraft lost on deck ({sq.name}: {sq.available}/{sq.authorized} left)")
    cv.defense = max(DEFENSE_FLOOR, cv.defense - DEFENSE_HIT)
    lines.append(f"   the group's air defence is down to {cv.defense:.0%}; no launches tomorrow and half the sorties the day after")
    if state.raids is None:
        state.raids = {}
    state.raids["deck_out_to"] = state.day + 2
    return lines


def deck_factor(state) -> float:
    """Share of the carrier squadrons' sorties available today: 0 the day after a big hit, 0.5 the day after that, else 1."""
    to = (state.raids or {}).get("deck_out_to")
    if to is None:
        return 1.0
    if state.day == to - 1:
        return 0.0
    if state.day == to:
        return 0.5
    return 1.0
