"""Air wings that fall back to recover (v0.36.0), the same rule for both sides.

A wing or squadron that is down to RETREAT_FRAC of its aircraft or less may stand down overnight: its survivors go to a rear field (they stop flying, so
they are off every patrol, raid, escort and threat count), recover at REST_BOOST times the normal replenishment rate, and come back once they are at
RETURN_FRAC of strength and have rested RETURN_MIN_DAYS nights. While they rest `available` is 0 and the aircraft sit in `reserve`; the strength totals
(victory / defeat) still count them, because they are not lost. Not touched: your own squadron, carrier squadrons (a ship has no rear field), and the
strategic bomber wing. Pure planning, no pydcs.
"""
from __future__ import annotations
from .loadouts import ENEMY_FIGHTERS

RETREAT_FRAC = 0.30
RETURN_FRAC = 0.65
REST_BOOST = 2.0
RETURN_MIN_DAYS = 2
MIN_AUTHORIZED = 4                 # tiny units just fly on


def resting(u) -> bool:
    return getattr(u, "reserve", 0) > 0


def _units(state):
    """(side, unit, name, replenish key, destroyed?) for everything that can stand down."""
    pid = state.player.squadron_id if state.player else None
    for sq in state.squadrons.values():
        if sq.id == pid or state.bases[sq.base_id].kind.value == "CARRIER":
            continue
        yield "blue", sq, sq.name, False
    for w in state.enemy_air:
        if "Tu_22M3" in w.types:
            continue
        a = state.assets.get(w.base_asset_id)
        yield "red", w, (a.name if a else w.base_asset_id), bool(a is None or a.destroyed)


def step(state, d, rng) -> list:
    """Overnight: wings fall back, rest and return. -> report lines."""
    out = []
    for side, u, name, gone in _units(state):
        rep = d.friendly_replenish if side == "blue" else d.enemy_replenish
        what = f"{name}" if side == "blue" else f"the air wing at {name}"
        if resting(u):
            if gone:                                               # its rear field is no safer than a cratered one
                u.reserve = int(u.reserve * 0.75)
                continue
            u.rest_days += 1
            u.reserve = min(u.authorized, u.reserve + max(1, round(u.authorized * rep * REST_BOOST)))
            if u.rest_days >= RETURN_MIN_DAYS and u.reserve >= RETURN_FRAC * u.authorized:
                u.available, u.reserve, u.rest_days = u.reserve, 0, 0
                out.append(f"{what[0].upper() + what[1:]} is back in the line with {u.available} aircraft.")
            continue
        if (not gone and u.authorized >= MIN_AUTHORIZED and 0 < u.available <= RETREAT_FRAC * u.authorized
                and rng.random() < d.air_retreat):
            u.reserve, u.available, u.rest_days = u.available, 0, 0
            out.append(f"{what[0].upper() + what[1:]} stood down to a rear field to recover ({u.reserve} aircraft).")
    return out
