"""A rate that is not a whole number, without dice (S207e; XO 2026-11-25: "no more dice for decisions").

A side that can task 8.4 packages a turn flies 8 most turns and 9 now and then: the fraction is carried to the next turn instead of rolled. The same for patrols, sweeps and strikes that
come "so many times a day". The carried amounts live in `state.raids["carry_frac"]`, which a day reset keeps.
"""
from __future__ import annotations

# A rate starts half way to its first whole unit, so rounding is not always down at the start of a war.
START = 0.5


def whole_units(state, key: str, turn: int, amount: float) -> int:
    """How many whole units turn `turn` gets when `amount` (a fraction) accrues under `key`; the rest is carried. Asking again for the same turn (a replan) gives the same answer."""
    if state.raids is None:
        return int(amount + START)
    store = state.raids.setdefault("carry_frac", {})
    entry = store.get(key)
    if entry is None:
        entry = {"turn": None, "before": START, "after": START}
        store[key] = entry
    if entry["turn"] != turn:
        entry["before"] = entry["after"]
        entry["turn"] = turn
    total = entry["before"] + amount
    whole = int(total + 1e-9)
    entry["after"] = total - whole
    return whole
