"""Air wings that fall back to recover (v0.36.0), the same rule for both sides. Since v0.41.53 red does it per SQUADRON (a red wing is typed
squadrons): one squadron of a wing can stand down and return while the others keep flying.

A wing or squadron that is down to RETREAT_FRAC of its aircraft or less stands down overnight when its field is under threat (S208, XO 2026-11-25: no dice; before, a chance, `d.air_retreat`): its survivors go to a rear field (they stop flying, so
they are off every patrol, raid, escort and threat count), recover at REST_BOOST times the normal replenishment rate, and come back once they are at
RETURN_FRAC of strength and have rested RETURN_MIN_DAYS nights. While they rest `available` is 0 and the aircraft sit in `reserve`; the strength totals
(victory / defeat) still count them, because they are not lost. Not touched: your own squadron, carrier squadrons (a ship has no rear field), and the
strategic bomber wing. Pure planning, no pydcs.
"""
from __future__ import annotations
from . import clock, patrol_threat, runways
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
        a = state.assets.get(w.base_asset_id)
        for q in w.sqns:
            if q.aircraft == "Tu_22M3" or q.role == "escort":            # B1: the bomber wing's squadrons never stand down (it used to be the whole wing; a bomber field that is also a normal red wing keeps its other squadrons in the rotation)
                continue
            yield "red", q, (a.name if a else w.base_asset_id) + f" ({q.aircraft.replace('_', '-')})", bool(a is None or a.destroyed)


MOVE_TURNS_PER_NIGHT = 12 * 60 // clock.TURN_MIN          # a save from before v0.41.337 counts a move in nights: one night is 12 hours (S25: derived from the clock, was a literal 6; judgment call, only for that conversion)


def _moving_units(state):
    """Every squadron that can be on the move: (unit, display name), blue and red, the player's and the carrier's included."""
    for sq in state.squadrons.values():
        yield sq, sq.name
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        for q in w.sqns:
            yield q, f"the squadron at {a.name if a else w.base_asset_id} ({q.aircraft.replace('_', '-')})"


def step_moves(state) -> list:
    """v0.41.337 (Phase 3): every TURN, a squadron that changed field (ground._settle) comes back into the line when the clock reaches its `move_until` (12 or 24 hours, XO
    2026-11-09). Its jets wait in `reserve` meanwhile. Used to be a nightly tick of `move_days`; a save that still carries `move_days` is converted here. -> report lines."""
    out = []
    for u, name in _moving_units(state):
        if getattr(u, "move_days", 0) > 0 and not u.move_until:           # legacy save: nights left -> turns
            u.move_until = state.turn + MOVE_TURNS_PER_NIGHT * u.move_days
            u.move_days = 0
        if u.move_until > 0 and state.turn >= u.move_until:
            u.move_until = 0
            if u.reserve > 0:
                u.available, u.reserve, u.rest_days = u.reserve, 0, 0
            out.append(f"{name[0].upper() + name[1:]} has settled in at its new field with {u.available} aircraft.")
    return out


def field_threatened(state, side: str, unit) -> bool:
    """Is this squadron's field under threat: closed by a runway hit, or within reach of the enemy's ready jets (`patrol_threat`)? A blue squadron's field is its base, a red
    squadron's its wing's field."""
    if side == "blue":
        place_id = unit.base_id
        place = state.bases.get(place_id)
    else:
        place_id = ""
        for wing in state.enemy_air:
            if unit in wing.sqns:
                place_id = wing.base_asset_id
        place = state.assets.get(place_id)
    if place is None:
        return False
    if runways.is_closed(state, place_id):
        return True
    if side == "blue":
        return patrol_threat.red_on(state, place.x, place.y) > 0.0
    return patrol_threat.blue_on(state, place.x, place.y) > 0.0


def step(state, d, rng) -> list:
    """Overnight: wings fall back, rest and return. -> report lines. (A squadron on the move is brought back by `step_moves`, every turn.) `rng` is no longer used (S208)."""
    out = []
    for side, u, name, gone in _units(state):
        rep = d.friendly_replenish if side == "blue" else d.enemy_replenish
        what = f"{name}" if side == "blue" else f"the squadron at {name}"
        if resting(u):
            if gone:                                               # its rear field is no safer than a cratered one
                u.reserve = int(u.reserve * 0.75)
                continue
            if u.move_until > 0 or getattr(u, "move_days", 0) > 0:      # v0.41.243: a squadron that changed field (base fall or return) is on the move: no rest boost; step_moves brings it back
                continue
            u.rest_days += 1
            u.reserve = min(u.authorized, u.reserve + max(1, round(u.authorized * rep * REST_BOOST)))
            if u.rest_days >= RETURN_MIN_DAYS and u.reserve >= RETURN_FRAC * u.authorized:
                u.available, u.reserve, u.rest_days = u.reserve, 0, 0
                out.append(f"{what[0].upper() + what[1:]} is back in the line with {u.available} aircraft.")
            continue
        if (not gone and u.authorized >= MIN_AUTHORIZED and 0 < u.available <= RETREAT_FRAC * u.authorized
                and field_threatened(state, side, u)):
            u.reserve, u.available, u.rest_days = u.available, 0, 0
            out.append(f"{what[0].upper() + what[1:]} stood down to a rear field to recover ({u.reserve} aircraft).")
    return out
