"""Air defence that rebuilds and moves (ground war, phase 3).

Red:
* A SAM site you destroyed is not gone for good. After REBUILD_MIN_DAYS a replacement can go up (SAM_REBUILD chance a day by level, scaled by Red's
  supply, at most REBUILD_PER_DAY a night), at REBUILT_HEALTH. It is never rebuilt at a field that is itself cratered, never behind the front,
  and the column air defence (fsam_) travels with its sector and is not rebuilt.
* A mobile site that has been hurt (SA-6, SA-11, SA-8, SA-15, SA-19) can pack up and move (SAM_SCOOT chance a night by level): a few nm, never
  further than MAX_DRIFT_NM from where it started, at most MAX_MOVES times. Its dug-in garrison, if any, goes with it. Old positions in an old
  tasking order are simply stale: the next day's order has the new one.
Blue:
* Airfield air-defence strength repairs by supply (0.10 a day at full supply, about half that with every fuel farm and depot gone), a fallen field
  does not repair until it is retaken, and a well-defended field lends a battery to the weakest one.
Everything draws on the campaign's own dice, so a night is repeatable from the same seed.
"""
from __future__ import annotations
import math
import random
from .models import AssetKind

NM = 1852.0
REBUILD_MIN_DAYS = 3
REBUILT_HEALTH = 0.5
REBUILD_PER_DAY = 1
from . import factions as _fx
MOBILE = _fx.VariantFlag("mobile")                  # site types that can move (factions.py)
HURT = 0.8                    # health at or below this is "hurt" enough to move
MAX_MOVES = 2
MAX_DRIFT_NM = 10.0
STEP_NM = (3.0, 6.0)
BLUE_REPAIR = 0.10
LEND_FROM, LEND_TO, LEND_AMOUNT = 0.80, 0.50, 0.05


def _rec(state) -> dict:
    if not isinstance(getattr(state, "sams", None), dict):
        state.sams = {}
    r = state.sams
    r.setdefault("down", {}); r.setdefault("moves", {}); r.setdefault("home", {})
    return r


def _parent_down(state, a) -> bool:
    if not a.id.startswith("sam_"):
        return False
    p = state.assets.get("ab_" + a.id[4:a.id.rindex("_")])
    return p is not None and p.destroyed


def track(state) -> None:
    """Remember the day each SAM site went down; forget the ones that are back up."""
    r = _rec(state)
    for a in state.assets.values():
        if a.kind != AssetKind.SAM:
            continue
        if a.destroyed:
            r["down"].setdefault(a.id, state.day)
        else:
            r["down"].pop(a.id, None)


def rebuild(state, d, rng: random.Random) -> list:
    from . import ground
    track(state)
    r = _rec(state)
    p = float(getattr(d, "sam_rebuild", 0.0)) * (ground.supply(state, "red") if ground.active(state) else 0.85)
    cands = []
    for aid, day0 in r["down"].items():
        a = state.assets.get(aid)
        if a is None or not a.destroyed or aid.startswith("fsam_") or state.day - day0 < REBUILD_MIN_DAYS:
            continue
        if a.tier > state.front + 2 or _parent_down(state, a):
            continue
        cands.append(a)
    rng.shuffle(cands)
    lines = []
    for a in cands:
        if len(lines) >= REBUILD_PER_DAY:
            break
        if rng.random() < p:
            a.health = REBUILT_HEALTH
            r["down"].pop(a.id, None)
            lines.append(f"Red put up a replacement {a.variant} site: {a.name} (half strength)")
    return lines


def relocate(state, d, rng: random.Random) -> list:
    from . import seacheck
    r = _rec(state)
    p = float(getattr(d, "sam_scoot", 0.0))
    lines = []
    for a in sorted((x for x in state.assets.values() if x.kind == AssetKind.SAM), key=lambda x: x.id):
        if a.id.startswith("fsam_") or a.variant not in MOBILE or a.destroyed or a.health > HURT or r["moves"].get(a.id, 0) >= MAX_MOVES:
            continue
        if rng.random() >= p:
            continue
        hx, hy = r["home"].setdefault(a.id, [a.x, a.y])
        for _try in range(6):
            ang = math.radians(rng.uniform(0, 360)); step = rng.uniform(*STEP_NM) * NM
            nx, ny = seacheck.snap_to_land(a.x + step * math.cos(ang), a.y + step * math.sin(ang))
            if math.hypot(nx - hx, ny - hy) <= MAX_DRIFT_NM * NM and math.hypot(nx - a.x, ny - a.y) > 1500:
                break
        else:
            continue
        dx, dy = nx - a.x, ny - a.y
        a.x, a.y = nx, ny
        for g in state.assets.values():                                     # the dug-in garrison goes with it
            if g.guards == a.id:
                g.x, g.y = g.x + dx, g.y + dy
        r["moves"][a.id] = r["moves"].get(a.id, 0) + 1
        lines.append(f"{a.name} was hit and has moved about {math.hypot(dx, dy) / NM:.0f} nm")
    return lines


def blue_defence(state, d) -> list:
    """Airfield defences repair by supply; a fallen field does not, and a strong field lends a battery to the weakest."""
    from . import ground
    sup = ground.supply(state, "blue") if ground.active(state) else 1.0
    fallen = set((state.ground or {}).get("fallen", []))
    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD" and b.id not in fallen]
    for b in fields:
        b.defense = min(1.0, b.defense + BLUE_REPAIR * sup)
    lines = []
    if len(fields) >= 2:
        weak = min(fields, key=lambda b: (b.defense, b.id)); strong = max(fields, key=lambda b: (b.defense, b.id))
        if weak.defense < LEND_TO and strong.defense >= LEND_FROM and weak is not strong:
            strong.defense -= LEND_AMOUNT; weak.defense += LEND_AMOUNT
            lines.append(f"A SAM battery moved from {strong.name} to {weak.name}")
    return lines


def night(state, d, rng: random.Random) -> list:
    return rebuild(state, d, rng) + relocate(state, d, rng) + blue_defence(state, d)
