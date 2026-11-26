"""How threatened is a place from the air (S208; XO 2026-11-25: no dice for decisions)?

Used to give the turn's patrol pairs to the most threatened stations first (a CAP sits between the threat and the asset it covers, see `barcap.py`) and to decide whether a worn
wing's field is under threat. The threat is the enemy's ready jets that can reach the place, the nearer the heavier; for a red place also blue's strikes of today near it (red
sees where blue has been going). All weights are judgment calls.
"""
from __future__ import annotations

import math

from .aircraft import AIRCRAFT
from .loadouts import ENEMY_RADIUS_NM

NM = 1852.0
REACH_SHARE = 0.85               # the share of a type's combat radius counted as its reach, as the raid planner does (`raids._reach`)
RECENT_STRIKE_JETS = 8.0         # one blue package of today near a red place weighs like this many jets in reach
RECENT_STRIKE_NM = 110           # ...within this distance (`redair.REL_NM`: "in the area")


def red_on(state, x: float, y: float) -> float:
    """Red's jets that can reach (x, y), weighted from 1 (on top of it) to 0 (at the edge of their reach)."""
    total = 0.0
    for wing in state.enemy_air:
        field = state.assets.get(wing.base_asset_id)
        if field is None or field.destroyed:
            continue
        distance = math.hypot(field.x - x, field.y - y) / NM
        for squadron in wing.sqns:
            reach = ENEMY_RADIUS_NM.get(squadron.aircraft, 0) * REACH_SHARE
            if distance < reach:
                total += squadron.available * (1.0 - distance / reach)
    return total


def blue_on(state, x: float, y: float) -> float:
    """Blue's jets that can reach (x, y), weighted the same way, plus the strikes blue has flown near it today."""
    total = 0.0
    for squadron in state.squadrons.values():
        base = state.bases.get(squadron.base_id)
        if base is None:
            continue
        reach = AIRCRAFT[squadron.aircraft].combat_radius_nm * REACH_SHARE
        distance = math.hypot(base.x - x, base.y - y) / NM
        if distance < reach:
            total += squadron.available * (1.0 - distance / reach)
    for package in state.plan_done or []:
        target = state.assets.get((package.get("objective") or {}).get("target_id", ""))
        if target is not None and math.hypot(target.x - x, target.y - y) / NM <= RECENT_STRIKE_NM:
            total += RECENT_STRIKE_JETS
    return total
