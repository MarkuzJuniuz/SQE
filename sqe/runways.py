"""Runway cratering (v0.41.254, XO 2026-11-03).

DCS closes a bombed runway for AI for about 60 minutes (probe 2026-11-03: pairs on the ramp stayed at speed 0 until 61 min after the last bomb, then took off;
an inbound pair diverted on its own to Kutaisi), and nothing in the scripting API holds it shut. SQE ignores that and keeps its own rule: a field that took
HITS_TO_CLOSE bomb impacts on its runway is CRATERED for CLOSE_TURNS (6 turns = 24 hours, S25; v0.41.334 had 12 two-hour turns; it was 2 to 5 days by supply). While cratered, its squadrons do not
fly (no packages, no scrambles, no raids, no base CAP) and nobody plans to recover there. The whole field closes, not one runway (XO). Replacement jets that
arrive meanwhile wait, `held` (refit.py), and join when the runway reopens.

State: state.ground["craters"][field_id] = {"turn": turn it was hit, "until": first turn it works again, "hits": impacts counted so far, "side": "red"|"blue"}.
Field ids are the Base ids of blue fields and the EnemyAsset ids of red ones (one namespace in practice).

Sources and judgment calls:
  * Repair: a USAF crater team fills craters in about 2 hours (af.mil, "Airmen ready to rapidly repair runways"). A real strip is usable again in hours; the 24 hours
    here are a GAME rule (XO 2026-11-08, flat for now), not a sourced figure. Until Phase 3 of the campaign rules plan the clock moves a whole day at a time.
  * HITS_TO_CLOSE = 1 (was 3, XO 2026-11-13): XO's call. One BMS player reports 2 to 3 hit zones per runway (forum.falcon-bms.com/post/121547, one person's observation, low firmness).
  * The runway is a rectangle, RUNWAY_HALF_LEN_M x RUNWAY_HALF_WIDTH_M about the field reference point along each runway heading (pydcs has the heading only):
    the same judgment-call corridor mission_builder uses to keep ground groups off the strip.
"""
from __future__ import annotations

import math

from . import clock

HITS_TO_CLOSE = 1             # bomb impacts inside the runway rectangle that close the field (XO 2026-11-03: 3; XO 2026-11-13: 1, so a human pilot's own bomb alone closes it even if the wingmen drop nothing; judgment call, to be revisited after the next probes)
CLOSE_TURNS = 6               # S25: was 12; a cratered field stays shut 6 four-hour turns = 24 hours, whatever the supply (XO 2026-11-08, "24 hours flat for now"; game rule, not a sourced figure)
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
        return f"{name}: runway hit again, still closed"
    _craters(state)[field_id] = {"turn": state.turn, "until": state.turn + CLOSE_TURNS, "hits": int(hits if hits is not None else HITS_TO_CLOSE), "side": side}
    return f"{name}: runway CUT, field closed. Closed for some time; its squadrons cannot fly and new jets wait until then"


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


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# v0.41.336 (XO 2026-11-09, campaign rules plan Phase 2b): the crater visuals. NOT TESTED IN DCS. pydcs gives only each airfield's reference
# point and the runway numbers, not the runway ends, so every position here is an estimate along the runway axis from the reference point (judgment calls).
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
MAG_VAR_DEG = 6.0             # runway numbers are magnetic; true heading = number x 10 + this. About 6 degrees east for the Caucasus, from memory (judgment call, not checked against DCS)
RUNWAY_HALF_LENGTH_M = 1200.0 # the threshold is taken this far from the airfield reference point along the runway (Caucasus strips are about 2,400 to 2,900 m; the reference point may not be the exact middle: judgment call)
CRATER_BLASTS_MIN = 3         # crater blasts along a closed runway: the hit count, but at least this many ...
CRATER_BLASTS_MAX = 6         # ... and at most this many (judgment call: a few visible craters, not a field of them)
CRATER_POWER = 450.0          # trigger.action.explosion power of one blast, about one Mk-84 (judgment call; whether DCS leaves a runway crater from a scripted blast is untested)
CRATER_REACH = 0.75           # the blasts lie within this share of the runway half length either side of the reference point (judgment call: inside the strip even if the reference point is off centre)
CRATER_MIN_GAP_M = 120.0      # blasts at least this far apart along the runway (judgment call)

# Blue fields with an ILS: pydcs airport name -> the runway end the ILS belongs to. From the DCS airfield panels as XO copied them into kneeboard.NAV (v0.41.177, v0.41.252);
# the other end of each runway has no ILS. Phase 9a (XO data, 2026-11-10; not checked against DCS here): Vaziani and Tbilisi-Lochini have an ILS on both ends; one runway per field is kept, 13
# (the ILS runway follows it), the 31 end stays in the kneeboard text only. Soganlug has no ILS (no entry).
ILS_RUNWAY = {"Batumi": 13, "Kobuleti": 7, "Kutaisi": 7, "Senaki-Kolkhi": 9, "Sochi-Adler": 6, "Vaziani": 13, "Tbilisi-Lochini": 13}


def _end_number(name: str) -> int:
    return int(str(name).rstrip("LCR"))


def runway_end(ap, number: int):
    """The approach (heading, name) of the runway end `number` of this pydcs airport, or None."""
    for r in ap.runways:
        for end in (r.main, r.opposite):
            if _end_number(end.name) == number:
                return end
    return None


def _along(x: float, y: float, hdg_deg: float, d: float):
    h = math.radians(hdg_deg)
    return x + d * math.cos(h), y + d * math.sin(h)           # DCS x north, y east


def crater_points(state, field_id: str, ap, rng) -> list:
    """Blast points (x, y) along the first runway of a closed field: as many as it took hits (CRATER_BLASTS_MIN to CRATER_BLASTS_MAX), spread along the strip with a seeded
    jitter and kept CRATER_MIN_GAP_M apart, a few metres either side of the centreline. The hit positions are not kept in the state, so these are for show only."""
    if not ap.runways:
        return []
    c = (state.ground or {}).get("craters", {}).get(field_id) or {}
    n = min(CRATER_BLASTS_MAX, max(CRATER_BLASTS_MIN, int(c.get("hits", 0))))
    hdg = ap.runways[0].main.heading + MAG_VAR_DEG
    span = RUNWAY_HALF_LENGTH_M * CRATER_REACH
    cell = 2.0 * span / n
    jitter = max(0.0, (cell - CRATER_MIN_GAP_M) / 2.0)
    out = []
    for i in range(n):
        d = -span + cell * (i + 0.5) + rng.uniform(-jitter, jitter)
        x, y = _along(ap.position.x, ap.position.y, hdg, d)
        x, y = _along(x, y, hdg + 90.0, rng.uniform(-8.0, 8.0))
        out.append((x, y))
    return out
