"""The condensed site list (sqe/data/theatres/<theatre>_sites.json, written by tools/sqe_scan.py condense from a DCS terrain scan).

v0.41.199 (XO 2026-10-30): players must not have to run scans, and early flights had SAMs floating in the sea. The file holds ready-made spots on dry,
flat ground near roads: per ground-war sector (ground, SAM, supply) and per red airfield (SAM, supply). A new campaign builds its layout as before
(doctrinal bearings, the pack's offsets, the sector centres) and `apply` then moves each red SAM site, fuel farm / depot and front-line column to the nearest
unused spot of its kind within reach. No random draw is made, so the campaign's other draws are unchanged. A site with no spot in reach stays where it is
(the old rough coastline / road snap still covers it), and a theatre without a sites file is built exactly as before.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

SAM_REACH_M = 12000.0         # a SAM site moves to a spot at most this far from where the doctrinal placement put it (judgment call)
SUPPLY_REACH_M = 12000.0      # same for a fuel farm / depot
FOLLOWER_REACH_M = 3000.0     # a garrison / a column's air defence moves to a spot at most this far from where it stood next to its parent
COLUMN_REACH_M = 12000.0      # a front-line column moves onto a scanned road point at most this far away (sectors are 20 to 60 km apart)
_CACHE: dict = {}


def load(th: dict):
    """The sites dict of a theatre pack, or None when it has none (or the file is unreadable)."""
    tid = th.get("id", "")
    if tid in _CACHE:
        return _CACHE[tid]
    d = None
    try:
        p = Path(th.get("_dir", "")) / f"{tid}_sites.json"
        if p.is_file():
            d = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(d, dict) or "sectors" not in d:
                d = None
    except (OSError, ValueError):
        d = None
    _CACHE[tid] = d
    return d


def clear_cache() -> None:
    _CACHE.clear()
    _SPOTS.clear()


_SPOTS: dict = {}


def on_spot(x: float, y: float) -> bool:
    """True when (x, y) is a spot of the ACTIVE theatre's sites file (the sea snap leaves such an asset alone, and so does a re-check on load)."""
    from . import theatres
    th = theatres.active()
    tid = th.get("id", "")
    if tid not in _SPOTS:
        d = load(th)
        _SPOTS[tid] = {(round(float(px)), round(float(py))) for kind in ("sam", "supply", "ground") for px, py in _pool(d, kind)} if d else set()
    return (round(x), round(y)) in _SPOTS[tid]


def _pool(sites: dict, kind: str) -> list:
    """Every spot of a kind, fields' first (they are the ones near the airfields), as (x, y)."""
    out = []
    for grp in ("fields", "sectors"):
        for g in sites.get(grp, []):
            out += [(float(x), float(y)) for x, y in g.get(kind, [])]
    return list(dict.fromkeys(out))


def _nearest(pool: list, used: set, x: float, y: float, reach: float):
    best, bd = None, reach
    for sp in pool:
        if sp in used:
            continue
        d = math.hypot(sp[0] - x, sp[1] - y)
        if d <= bd:
            best, bd = sp, d
    return best


def free_spot(st, kind: str, x: float, y: float, reach: float):
    """The nearest spot of a kind within `reach` of (x, y) that no asset of the campaign (either side) sits within 1 km of, or None (no file, or none free).
    For things placed after the campaign is built (forward garrisons)."""
    from . import theatres
    sites = load(theatres.active())
    if not sites:
        return None
    taken = [(a.x, a.y) for pool in (getattr(st, "assets", {}), getattr(st, "blue_assets", None) or {}) for a in pool.values()]
    best, bd = None, reach
    for sp in _pool(sites, kind):
        d = math.hypot(sp[0] - x, sp[1] - y)
        if d <= bd and all(math.hypot(sp[0] - tx, sp[1] - ty) >= 1000.0 for tx, ty in taken):
            best, bd = sp, d
    return best


def apply(st, th: dict) -> set:
    """Move red's SAM sites, fuel farms / depots (blue's too) and front-line columns onto spots from the sites file. -> the ids of the assets that were placed on a
    spot (the sea snap leaves those alone). Garrisons and a column's air defence keep their offset and move with their parent. Idempotent for the
    same state (an asset already on a spot stays there)."""
    from .models import AssetKind
    sites = load(th)
    if not sites:
        return set()
    pools = {k: _pool(sites, k) for k in ("sam", "supply", "ground")}
    used: set = set()
    placed: set = set()
    followers = {}
    for a in st.assets.values():
        if a.guards:
            followers.setdefault(a.guards, []).append(a)
        elif a.id.startswith("fsam_"):
            followers.setdefault("armor_" + a.id[5:], []).append(a)

    def put(a, kind, reach):
        sp = _nearest(pools[kind], used, a.x, a.y, reach)
        if sp is None:
            return
        move(a, sp)

    def move(a, sp):
        used.add(sp)
        dx, dy = sp[0] - a.x, sp[1] - a.y
        a.x, a.y = sp
        placed.add(a.id)
        for c in followers.get(a.id, ()):
            c.x, c.y = c.x + dx, c.y + dy

    def put_all(items, kind, reach):
        """Smallest move first, over every (site, spot) pair, so no site is pushed far because an earlier one took its spot: the doctrinal layout
        (a short-range site next to its SA-10) only survives when every move is small."""
        pairs = sorted((math.hypot(sp[0] - a.x, sp[1] - a.y), a.id, sp, a) for a in items for sp in pools[kind] if math.hypot(sp[0] - a.x, sp[1] - a.y) <= reach)
        done = set()
        for d, aid, sp, a in pairs:
            if aid in done or sp in used:
                continue
            done.add(aid)
            move(a, sp)

    put_all([a for a in st.assets.values() if a.kind == AssetKind.SAM and a.id.startswith("sam_")], "sam", SAM_REACH_M)
    put_all([a for a in list(st.assets.values()) + list((getattr(st, "blue_assets", None) or {}).values()) if a.kind in (AssetKind.FUEL, AssetKind.DEPOT)], "supply", SUPPLY_REACH_M)
    put_all([a for a in st.assets.values() if a.kind == AssetKind.ARMOR and a.id.startswith("armor_")], "ground", COLUMN_REACH_M)
    # the dug-in garrisons of the SAM sites (off the road: a SAM spot) and the columns' air defence (a road spot) settle on a spot near where they ended up
    for a in sorted(st.assets.values(), key=lambda a: a.id):
        if a.id.startswith("gar_") and a.guards in placed:
            put(a, "sam", FOLLOWER_REACH_M)
        elif a.id.startswith("fsam_") and ("armor_" + a.id[5:]) in placed:
            put(a, "ground", FOLLOWER_REACH_M)
    return placed
