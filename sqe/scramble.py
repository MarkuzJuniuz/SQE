"""v0.41.91: where a scrambled (alert) pair stations itself (XO 2026-10-21: scramblers should think like the Fighter Sweep, and against small raids
stay defensive: stick forward toward the attackers but stay over SAM protection).

Until now both sides' alert pairs flew a straight line to the target and orbited ON it (red: an INTERCEPT point, no way home; blue: a CAP point
on the raid's target). Now the pair takes a STATION:

* the pair stations as far forward of the target toward the attackers (or, for red, from its own field toward the target) as it can while it is
  still under its own side's SAM cover (DEFENDER_FWD_MAX_NM at most), in steps of STEP_NM;
* blue's station is also clear of red's SAM rings (the sweep's rule, `sweep.clear_for_sweep`): the 2026-10-16 CAP-on-the-target gap;
* with no cover at all red holds over its own field, and blue holds on the target as before.

Doctrine: air-defence doctrine splits the air into a fighter engagement zone, a missile engagement zone and a joint zone where both work at once
(JP 3-01 terms; the definitions here are from a summary card, not the manual's text), so a defensive pair working at the edge of its own SAM cover is a
recognised shape. How far forward it sticks (DEFENDER_FWD_MAX_NM), the step and the cover margin are judgment calls. Pure planning, no pydcs.
"""
from __future__ import annotations
import math

from . import threatmap as tm
from .models import AssetKind
from .routes import NM, bearing, dist, offset

DEFENDER_FWD_MAX_NM = 20.0   # v0.41.191 (XO 2026-10-29: both sides save airframes before SAM missiles; was STICK_NM 30 and red's RED_FWD_MAX_NM 30, now one number): judgment call: the furthest a defensive pair sticks forward of its target (blue) or its field (red) toward the attackers
STEP_NM = 5.0
FIELD_HOLD_NM = 15.0     # red with no SAM cover at all holds this far out from its own field toward the target (the old patrols sit 20-25 nm out)
BLUE_COVER_AD = 0.3      # a blue field's air defence (sams.air_defence, 0 to 1) that counts as cover over what lies within BLUE_COVER_NM of it
BLUE_COVER_NM = 25.0     # raids.HAWK_NM: the field's HAWK reach, judgment call for the margin inside the Patriot's 40
BLUE_COVER_PAT_AD = 0.65   # v0.41.114: a field at Patriot strength (sams.air_defence: a Patriot at full strength is 0.7)...
BLUE_COVER_PAT_NM = 30.0   # ...covers this far, 10 nm inside the Patriot's 40 (raids.PATRIOT_NM): a station "well inside SAM support" (XO 2026-10-22; judgment call)


def red_covered(state, x, y, extra_nm: float = 0.0) -> bool:
    """Is (x, y) inside the reach of a live red SAM of 3 nm or more (an SA-10 by its practical umbrella), plus `extra_nm` of room beyond it?"""
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed or a.health <= 0.25 or getattr(a, "suppressed", False):
            continue
        reach = tm.UMBRELLA_KM / 1.852 if a.variant in tm.UMBRELLA_VARIANTS else tm.RANGE_NM.get(a.variant, 0)
        if reach >= 3 and dist(x, y, a.x, a.y) <= (reach + extra_nm) * NM:
            return True
    return False


def blue_covered(state, x, y) -> bool:
    """Is (x, y) under blue's own air defence: a field with a Patriot / HAWK battery up within BLUE_COVER_NM of it?"""
    from .sams import covering_ad
    return covering_ad(state, x, y, BLUE_COVER_NM) >= BLUE_COVER_AD or covering_ad(state, x, y, BLUE_COVER_PAT_NM) >= BLUE_COVER_PAT_AD


def _walk(frm, to, step_nm=STEP_NM):
    """Points from `frm` to `to` in steps (both ends included)."""
    n = max(1, int(dist(*frm, *to) / (step_nm * NM)))
    d = dist(*frm, *to)
    b = bearing(*frm, *to)
    return [offset(frm[0], frm[1], b, d * k / n) for k in range(n + 1)] if d > 1 else [frm]


def red_station(state, field_xy, tx, ty):
    """Red's alert pair against blue at (tx, ty): the covered point nearest the target on the line from its field (the target itself when it is
    covered), at most DEFENDER_FWD_MAX_NM beyond the cover; else over its own field. -> ((x, y), why) with why in 'target' / 'edge' / 'field'."""
    if red_covered(state, tx, ty):
        return (tx, ty), "target"
    for p in _walk((tx, ty), field_xy):
        if red_covered(state, *p):
            return p, "edge"
    b = bearing(*field_xy, tx, ty)
    return offset(field_xy[0], field_xy[1], b, min(FIELD_HOLD_NM * NM, dist(*field_xy, tx, ty))), "field"


def raid_origin(state, pkg, tx, ty):
    """Where the raid comes from: its bomber wing, else the red fighter wing nearest the target; (x, y) or None."""
    a = state.assets.get((getattr(pkg, "extra", None) or {}).get("bomber_wing") or "")
    if a is not None:
        return (a.x, a.y)
    wings = [state.assets[w.base_asset_id] for w in state.enemy_air if w.base_asset_id in state.assets and not state.assets[w.base_asset_id].destroyed]
    if not wings:
        return None
    w = min(wings, key=lambda a_: dist(a_.x, a_.y, tx, ty))
    return (w.x, w.y)


STATION_SA10_NM = 35.0      # judgment call (v0.41.114): a defender sits under its own cover, so it keeps less room from red's SA-10 than a sweep (45)
STATION_RING_MARGIN_NM = 3.0  # judgment call: the sweep uses 20 nm outside the other rings; 3 keeps a CAP off a point-defence SAM's ring only


RED_FWD_MAX_NM = DEFENDER_FWD_MAX_NM    # v0.41.191: the same cap as blue's alert pairs (a red station moves at most this far toward the incoming shooters)
RED_GAP_NM = 20.0         # ...and stops this far short of them (judgment call: about the reach of an R-27 / R-77 shot at a shooter that turned round)
RED_EXTRA_NM = {True: 15.0, False: 0.0}   # ...a long-range type (the Su-27) may work this far beyond its SAM cover, the MiG-29A not at all (judgment call)


def red_station_vs(state, field_xy, tx, ty, threat_xy, long_range: bool = False, fwd_nm: float = RED_FWD_MAX_NM, gap_nm: float = RED_GAP_NM):
    """v0.41.119: `red_station`, then forward toward `threat_xy` (the blue shooters' launch point): the furthest point, `fwd_nm` at most and `gap_nm` short of the
    threat, that is under red's SAM cover (plus RED_EXTRA_NM for a long-range type). With no cover (a station over the field) or no threat it is
    `red_station`. -> ((x, y), why) with why 'fwd' when it moved."""
    base, why = red_station(state, field_xy, tx, ty)
    if threat_xy is None or why == "field":
        return base, why
    top = min(fwd_nm, dist(*base, *threat_xy) / NM - gap_nm)
    if top < STEP_NM:
        return base, why
    extra = RED_EXTRA_NM[bool(long_range)]
    b = bearing(*base, *threat_xy)
    for i in range(int(top // STEP_NM), 0, -1):                 # furthest forward first
        p = offset(base[0], base[1], b, i * STEP_NM * NM)
        if red_covered(state, *p, extra_nm=extra):
            return p, "fwd"
    return base, why


def clear_for_station(state, x, y) -> bool:
    """A blue defensive station: STATION_SA10_NM from every live red SA-10, STATION_RING_MARGIN_NM outside every other SAM ring of 3 nm+."""
    from . import threatmap as tm
    from .sweep import _sams
    for a in _sams(state):
        if a.variant in tm.UMBRELLA_VARIANTS:
            if dist(x, y, a.x, a.y) < STATION_SA10_NM * NM:
                return False
        elif tm.RANGE_NM.get(a.variant, 0) >= 3 and dist(x, y, a.x, a.y) < (tm.RANGE_NM[a.variant] + STATION_RING_MARGIN_NM) * NM:
            return False
    return True


def blue_station(state, tx, ty, origin_xy):
    """Blue's alert pair against a raid on (tx, ty): on the line from the target toward where the raid comes from, as far forward (DEFENDER_FWD_MAX_NM at
    most) as it is still under blue's air defence and clear of red's SAM rings; else on the target (when that is clear of red's SAMs) or the
    nearest clear point back toward the field side. -> ((x, y), why) with why in 'target' / 'forward' / 'clear'."""
    clear_for_sweep = clear_for_station
    if origin_xy is None or dist(tx, ty, *origin_xy) < 2 * NM:
        return (tx, ty), "target"
    fwd = offset(tx, ty, bearing(tx, ty, *origin_xy), min(DEFENDER_FWD_MAX_NM * NM, dist(tx, ty, *origin_xy)))
    for p in reversed(_walk((tx, ty), fwd)):                       # furthest forward first
        if blue_covered(state, *p) and clear_for_sweep(state, *p):
            return p, ("target" if dist(*p, tx, ty) < 1 * NM else "forward")
    if clear_for_sweep(state, tx, ty):
        return (tx, ty), "target"
    back = offset(tx, ty, bearing(tx, ty, *origin_xy) + 180, DEFENDER_FWD_MAX_NM * NM)
    for p in _walk((tx, ty), back):
        if clear_for_sweep(state, *p):
            return p, "clear"
    return (tx, ty), "target"
