"""Runway cratering (v0.41.254, XO 2026-11-03).

DCS closes a bombed runway for AI for about 60 minutes (probe 2026-11-03: pairs on the ramp stayed at speed 0 until 61 min after the last bomb, then took off;
an inbound pair diverted on its own to Kutaisi), and nothing in the scripting API holds it shut. SQE ignores that and keeps its own rule: a field that took
HITS_TO_CLOSE bomb impacts on its runway is CRATERED for CLOSE_TURNS (12 turns = 24 hours, v0.41.334; it was 2 to 5 days by supply). While cratered, its squadrons do not
fly (no packages, no scrambles, no raids, no base CAP) and nobody plans to recover there. The whole field closes, not one runway (XO). Replacement jets that
arrive meanwhile wait, `held` (refit.py), and join when the runway reopens.

State: state.ground["craters"][field_id] = {"turn": turn it was hit, "until": first turn it works again, "hits": impacts counted so far, "side": "red"|"blue"}.
Field ids are the Base ids of blue fields and the EnemyAsset ids of red ones (one namespace in practice).

Sources and judgment calls:
  * Repair: a USAF crater team fills craters in about 2 hours (af.mil, "Airmen ready to rapidly repair runways"). A real strip is usable again in hours; the 24 hours
    here are a GAME rule (XO 2026-11-08, flat for now), not a sourced figure. Until Phase 3 of the campaign rules plan the clock moves a whole day at a time.
  * HITS_TO_CLOSE = 3: XO's call. One BMS player reports 2 to 3 hit zones per runway (forum.falcon-bms.com/post/121547, one person's observation, low firmness).
  * The runway is a rectangle, RUNWAY_HALF_LEN_M x RUNWAY_HALF_WIDTH_M about the field reference point along each runway heading (pydcs has the heading only):
    the same judgment-call corridor mission_builder uses to keep ground groups off the strip.
"""
from __future__ import annotations

import math

from . import clock

HITS_TO_CLOSE = 3             # bomb impacts inside the runway rectangle that close the field (XO 2026-11-03)
CLOSE_TURNS = 12              # a cratered field stays shut 12 two-hour turns = 24 hours, whatever the supply (XO 2026-11-08, "24 hours flat for now"; game rule, not a sourced figure)
RUNWAY_HALF_LEN_M = 2600.0    # same corridor as mission_builder.RUNWAY_HALF_LEN_M (long enough for the longest Caucasus strip; judgment call)
RUNWAY_HALF_WIDTH_M = 120.0   # ...and mission_builder.RUNWAY_HALF_WIDTH_M (runway 45-60 m wide plus a margin; judgment call)


def side_of(state, field_id: str) -> str:
    return "red" if field_id in state.assets else "blue"


def _craters(state) -> dict:
    g = state.ground
    if g is None:
        return {}
    return g.setdefault("craters", {})


def is_closed(state, field_id: str, turn: int | None = None) -> bool:
    """Is this field cratered on `turn` (default: the current turn)?"""
    c = (state.ground or {}).get("craters", {}).get(field_id)
    if not c:
        return False
    return (state.turn if turn is None else turn) < int(c["until"])


def closed_ids(state, turn: int | None = None) -> set:
    return {fid for fid in (state.ground or {}).get("craters", {}) if is_closed(state, fid, turn)}


def turns_left(state, field_id: str) -> int:
    c = (state.ground or {}).get("craters", {}).get(field_id)
    return max(0, int(c["until"]) - state.turn) if c else 0


def hours_left(state, field_id: str) -> int:
    return turns_left(state, field_id) * clock.TURN_MIN // 60


def crater(state, field_id: str, hits: int | None = None) -> str:
    """Close the field (a new hit while it is closed does NOT extend it: one repair crew, one timer). Returns the log line."""
    name = _name(state, field_id)
    side = side_of(state, field_id)
    if is_closed(state, field_id):
        c = _craters(state)[field_id]
        c["hits"] = int(c.get("hits", 0)) + int(hits or 0)
        return f"{name}: runway hit again, still cratered ({hours_left(state, field_id)} more hours)"
    _craters(state)[field_id] = {"turn": state.turn, "until": state.turn + CLOSE_TURNS, "hits": int(hits if hits is not None else HITS_TO_CLOSE), "side": side}
    return f"{name}: runway CRATERED. Closed for {CLOSE_TURNS * clock.TURN_MIN // 60} hours; its squadrons cannot fly and new jets wait until then"


def add_hits(state, field_id: str, hits: int) -> str | None:
    """Impacts counted in one mission. HITS_TO_CLOSE or more closes the field; fewer is damage the crews fix overnight (no state kept)."""
    if hits <= 0:
        return None
    name = _name(state, field_id)
    if hits >= HITS_TO_CLOSE:
        return crater(state, field_id, hits)
    return f"{name}: {hits} bomb{'s' if hits != 1 else ''} hit the runway, not enough to close it ({HITS_TO_CLOSE} needed); the repair crews fixed it overnight"


def _name(state, field_id: str) -> str:
    o = state.assets.get(field_id) or state.bases.get(field_id)
    return getattr(o, "name", field_id)


def squadron_grounded(state, sq) -> bool:
    return is_closed(state, sq.base_id)


def wing_grounded(state, wing) -> bool:
    return is_closed(state, wing.base_asset_id)


def rectangle(heading_deg: float, half_len: float = RUNWAY_HALF_LEN_M, half_w: float = RUNWAY_HALF_WIDTH_M):
    """(half_len, half_w) kept for symmetry with the Lua test: along = dx*cos(h) + dz*sin(h), across = -dx*sin(h) + dz*cos(h), DCS x north / z east."""
    return half_len, half_w


def inside(dx: float, dz: float, heading_deg: float) -> bool:
    """Python twin of the hook's test (used by the smoke check): is an impact (dx north, dz east of the field point) on a runway of this heading?"""
    h = math.radians(heading_deg)
    along = dx * math.cos(h) + dz * math.sin(h)
    across = -dx * math.sin(h) + dz * math.cos(h)
    return abs(along) <= RUNWAY_HALF_LEN_M and abs(across) <= RUNWAY_HALF_WIDTH_M


def fields_for_hook(state, terrain) -> list:
    """The hook's list of fields to watch: id, reference point and runway headings. Every airfield base and asset that has a pydcs airport."""
    out = []
    pool = [(b.id, b.airport) for b in state.bases.values() if b.kind.value == "AIRFIELD" and b.airport] + \
           [(a.id, a.airport) for a in state.assets.values() if a.kind.value == "AIRFIELD" and a.airport]
    for fid, apn in pool:
        ap = terrain.airports.get(apn)
        if ap is None:
            continue
        heads = sorted({int(r.main.heading) % 180 for r in ap.runways})
        out.append({"id": fid, "x": float(ap.position.x), "z": float(ap.position.y), "h": heads or [0]})
    return out
