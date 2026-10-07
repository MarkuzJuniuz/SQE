"""How many enemy fighters will defend a target, and how many friendly fighters we send against them."""
from __future__ import annotations
import math
from .loadouts import ENEMY_FIGHTERS

NM = 1852.0


def expected_defenders(state, tx: float, ty: float, iads: float = 0.5) -> float:
    e = 0.0
    for w in state.enemy_air:
        a = state.assets[w.base_asset_id]
        if a.destroyed or w.available <= 0:
            continue
        d = math.hypot(a.x - tx, a.y - ty) / NM
        if d > 180:
            continue
        wgt = 1.0 if d < 60 else 1.0 - 0.7 * (d - 60) / 120
        fighters = [t for t in w.types if t in ENEMY_FIGHTERS]
        e += w.available * (len(fighters) / max(1, len(w.types))) * 0.14 * wgt
    return e * (0.7 + 0.6 * iads)


def defender_flights(e: float) -> int:
    """Number of 2-ship enemy flights that will contest the target (0..4)."""
    if e < 0.3:
        return 0
    if e < 0.8:
        return 1
    return min(4, int(math.ceil(e / 2.0)))


def fighters_required(n_def_flights: int) -> int:
    """Friendly fighters to send: about 1.75x the defenders, in pairs, capped at 8."""
    if n_def_flights <= 0:
        return 0
    return min(8, 2 * math.ceil(1.75 * 2 * n_def_flights / 2))
