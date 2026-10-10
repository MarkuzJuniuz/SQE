"""Carcasses: burnt-out wrecks left at ground sites the war has damaged or destroyed.

Pure planning, no pydcs here. The builder places what this module returns as DEAD static objects (cheap: no AI, no weapons, no radar).

Rules that make them look like a persistent war rather than random props:
  * the layout of a site is seeded by (campaign id, asset id), never by the day or the sortie, so the same wreck sits in the same spot on
    every sortie, and a site that gets worse only ADDS wrecks (a longer prefix of one fixed list);
  * how many: the share of the site's vehicles that is gone, from its health (a destroyed site shows all of them, at most MAX_PER_SITE);
  * a damaged site that still has live vehicles is centred where those vehicles are, so wrecks and survivors read as one site; a
    destroyed site (nothing live) is centred on a fixed, seeded spot.
"""
from __future__ import annotations
import math
import random
from .models import AssetKind

MAX_PER_SITE = 6
# (tank, IFV, APC) choices and the column's AAA come from the red faction pack (factions.py: ground.wreck_mix / wreck_aaa)


def _rng(campaign_id: str, aid: str, tag: str = "wreck") -> random.Random:
    return random.Random(f"{campaign_id}:{aid}:{tag}")


def composition(a, rng: random.Random, sites: dict, soft: dict) -> list:
    """The fixed vehicle list of a site, launchers and combat vehicles first (these are the ones that show as wrecks)."""
    if a.kind in (AssetKind.SAM, AssetKind.EWR):
        comp = sites.get(a.variant) or []
    elif a.kind == AssetKind.ARMOR:
        from . import factions
        mix, aaa = factions.wreck_mix("red")
        if len(mix) < 3:
            return []
        tank, ifv, apc = (rng.choice(x) for x in mix[:3])
        comp = [(tank, 2), (ifv, 1), (aaa, 1)] if a.variant == "GARRISON" else [(tank, 4), (ifv, 3), (apc, 2), (aaa, 1)]
        comp = [(n, c) for n, c in comp if n]
    else:
        comp = soft.get(a.kind) or []
    out: list = []
    for name, n in comp:
        out += [name] * n
    return out


def stable_center(a, campaign_id: str, ok) -> tuple:
    """Where a destroyed site's wrecks sit: a fixed spot within 900 m of the asset (the live sites jitter the same way), never in the water."""
    r = _rng(campaign_id, a.id, "centre")
    ang, d = r.uniform(0, 360), r.uniform(0, 900)
    x, y = a.x + d * math.cos(math.radians(ang)), a.y + d * math.sin(math.radians(ang))
    return (x, y) if ok(x, y) else (a.x, a.y)


def lost_count(a, n: int) -> int:
    if n <= 0:
        return 0
    if a.destroyed:
        k = n
    else:
        k = round(n * (1.0 - a.health))
        if a.health < 0.95 and k == 0:
            k = 1
    return max(0, min(k, MAX_PER_SITE, n))


def wrecks_for(a, campaign_id: str, center: tuple, sites: dict, soft: dict, ok) -> list:
    """[{type, x, y, hdg}] for one asset, in a fixed order (a worse site just shows a longer prefix). `ok(x, y)` rejects water."""
    if a.kind == AssetKind.AIRFIELD:
        return []
    r = _rng(campaign_id, a.id)
    types = composition(a, r, sites, soft)
    if not types:
        return []
    r.shuffle(types)
    spots = [(r.uniform(0, 360), r.uniform(35, 230), r.randint(0, 359)) for _ in types]         # drawn for all, so a prefix never moves
    out = []
    for name, (ang, d, hdg) in list(zip(types, spots))[:lost_count(a, len(types))]:
        x, y = center[0] + d * math.cos(math.radians(ang)), center[1] + d * math.sin(math.radians(ang))
        if ok(x, y):
            out.append({"type": name, "x": x, "y": y, "hdg": hdg})
    return out
