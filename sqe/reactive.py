"""Reactive dispatch: extra fighters that launch DURING a sortie, on top of the planned enemy air picture.

Red: with a chance that depends on difficulty, other enemy wings send reinforcements to defend the target. They are real aircraft of that
wing (never more than the wing has available, counting what the planned picture already uses), and only from fields within the type's
intercept radius of the target. The total enemy fighter count is held to a ratio of the blue fighters in the mission (about 1:1 for a
regional power, up to 1.5:1, rarely 2:1, for a near-peer; almost never at Level 1).

Blue: alert pairs from the carrier or nearby bases, drawn from the squadron's available aircraft that the mission is not already using. They
launch when the enemy response outnumbers your fighters, for fleet defence and BARCAP, and when a raid on the fleet is part of the same wave.

Pure planning (no pydcs); the mission builder spawns what these functions return.
"""
from __future__ import annotations
import math
from .routes import NM

# How far from its field a type will be sent to intercept (nm). Hand-set and deliberately shorter than the published combat radius: a
# scramble has to reach the area, fight and get home. Tune freely.
from . import factions as _fx                       # noqa: E402
INTERCEPT_NM = _fx.INTERCEPT_LIVE                   # red faction: air.intercept_nm

# The same for our alert pairs: how far from its base a squadron's alert pair is sent (nm), never more than 60% of the combat radius. Hand-set, shorter
# than that radius for the same reason: it has to reach the area, fight and get home. Tune freely.
BLUE_DISPATCH_NM = {"F-14BU": 150, "FA-18C": 130, "F-16C": 120, "F-15C": 160}
BLUE_DISPATCH_DEFAULT_NM = 110

MAX_RED_FLIGHTS = 3                      # pairs added on top of the planned picture
COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def compass(brg: float) -> str:
    return COMPASS[int(((brg % 360) + 22.5) // 45) % 8]


def plan_red(state, d, rng, tx, ty, base_aircraft: int, blue_fighters: int, used: dict, fighters: set, bearing) -> list:
    """-> [{base, type, size, nm, brg}] extra enemy pairs. `used` = aircraft per wing base already in this mission (it is updated)."""
    chance = getattr(d, "react_chance", 0.0)
    if chance <= 0 or rng.random() >= chance:
        return []
    lo, hi = getattr(d, "react_ratio", (1.0, 1.0))
    ratio = rng.uniform(lo, hi)
    if d.level >= 3 and rng.random() < 0.10:
        ratio = 2.0                                           # now and then a near-peer commits everything it has
    total = round(ratio * max(blue_fighters, 2))
    pairs = min(MAX_RED_FLIGHTS, (total - base_aircraft) // 2)
    if pairs <= 0:
        return []
    pairs = rng.randint(1, pairs)
    cands = []
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if a is None or a.destroyed:
            continue
        nm = math.hypot(a.x - tx, a.y - ty) / NM
        types = [t for t in w.types if t in fighters and INTERCEPT_NM.get(t, 120) >= nm]
        if types:
            cands.append((w, a, nm, types))
    out = []
    for _ in range(pairs):
        free = [c for c in cands if c[0].available - used.get(c[0].base_asset_id, 0) >= 2]
        if not free:
            break
        w, a, nm, types = rng.choices(free, weights=[1.0 / max(30.0, c[2]) for c in free])[0]      # nearer fields are likelier
        used[w.base_asset_id] = used.get(w.base_asset_id, 0) + 2
        out.append({"base": w.base_asset_id, "type": rng.choice(types), "size": 2, "nm": nm, "brg": bearing(tx, ty, a.x, a.y)})
    return out


def blue_pairs(rng, red_total: int, blue_fighters: int, fleet_obj: bool, raid_in_wave: bool) -> int:
    """How many alert pairs blue puts up (0-2)."""
    p, n = 0.0, 0
    if fleet_obj:
        p, n = 0.70, 1 + (red_total >= 4)
    if raid_in_wave:
        p, n = max(p, 0.90), max(n, 1 + (red_total >= 4))
    if red_total > blue_fighters:
        p, n = max(p, 0.65), max(n, 1 + ((red_total - blue_fighters) >= 4))
    return min(2, n) if (n and rng.random() < p) else 0


def blue_sources(state, aircraft_table, fighter_roles, committed: dict, px, py) -> list:
    """Squadrons that can put a pair up near (px, py): a fighter type, within BLUE_DISPATCH_NM of its base (and 60% of its combat radius), with
    2+ aircraft the mission is not using. Nearest first. -> [(squadron, base, nm, free)]"""
    out = []
    for sq in state.squadrons.values():
        spec = aircraft_table.get(sq.aircraft)
        if spec is None or not (set(spec.roles) & fighter_roles):
            continue
        b = state.bases[sq.base_id]
        nm = math.hypot(b.x - px, b.y - py) / NM
        free = sq.available - committed.get(sq.id, 0)
        if free >= 2 and nm <= min(0.6 * spec.combat_radius_nm, BLUE_DISPATCH_NM.get(sq.aircraft, BLUE_DISPATCH_DEFAULT_NM)):
            out.append((sq, b, nm, free))
    out.sort(key=lambda c: c[2])
    return out
