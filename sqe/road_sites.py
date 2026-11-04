"""Supply sites along the roads of a new campaign (queue item i, v0.41.241; XO 2026-11-03).

The road-net step (roadnet.py) left a few hundred supply spots in the sites file under "road". A new campaign draws about `d.road_sites` of them (one
number per level) and turns each into a fuel point or a supply dump: red's on its own side of the front, ours on ours. They are what makes both sides' supply
worth striking and worth guarding: together with the fuel farms and depots at the airfields they ARE the Supply figure (ground.supply counts every site
either side holds, so there is no separate production link). A handful per side are big plants (oil refineries = FUEL sites, factories = DEPOT sites)
well away from the front.

Judgment calls (no public figure; tune on XO's runs): the 65/35 red/blue split, the 9 km spacing between sites, 90 km from a sector centre for a
plant, the plant counts, the guard strengths, the shares of unguarded sites and battalions (Difficulty.road_*).

Rules from XO:
  * Owner by place: a spot belongs to the side whose airfield is nearest (the theatre file lists the blue-side airports); the north of the mountains is
    always red. Ownership is fixed when the campaign is built (a site does not change hands with the front).
  * Defenders scale with the level: most red sites have a light guard (ZU-23 truck / Shilka / Shilka + Strela-10), about a third of them at Level 3 only a parked
    truck, a few a dug-in battalion (a CAS job when it sits near a sector centre; no friendly ground troops or JTAC beyond the mountains, #280).
  * Blue's road sites are buildings only, like blue's other supply sites (their cover is the Patriot / HAWK / AAA at the fields); no blue battalions.
  * The ammo depots and fuel farms at the airfields are not touched here (they stay near their bases, sites.apply).
New campaigns only: an older save keeps the sites it has.

Ids: `rsup_NNN` / `bsup_NNN` (a red id must not start with "b", see overview_detail.supply_rows), a battalion `rgar_sup_NNN` (guards = its site).
Variants: ROAD (light guard), ROAD0 (a parked truck), ROADB (light guard and a battalion), REFINERY / FACTORY (a plant: double guard, may have a battalion).
"""
from __future__ import annotations

import math
import random

from .models import AssetKind, EnemyAsset

RED_SHARE = 0.65              # share of the campaign's road sites that are red's (judgment call: red has the whole north, we have the Georgian side)
SEP_M = 9000.0                # no two road sites closer than this (relaxed in two steps if a side cannot fill its quota)
AIRFIELD_CLEAR_M = 5000.0     # no road site this close to any airfield (the fuel farm and garrison sit there)
ASSET_CLEAR_M = 2500.0        # ...or to any existing asset
PLANT_MIN_KM = 90.0           # a refinery / factory is at least this far from every sector centre ("away from the front")
PLANT_SEP_M = 40000.0         # ...and at least this far from another plant
PLANTS_PER_100 = {"red": (3, 3), "blue": (2, 2)}      # (refineries, factories) for a 100-site campaign; scaled by road_sites / 100, at least 1 each
VALUE_ROAD, VALUE_PLANT = 3, 7                        # planner weight (the airfield fuel farms are 5, depots 5 to 6)
BATTALION_OFFSET_M = (1600.0, 3000.0)
ROAD_PREFIX = ("rsup_", "bsup_")

GUARD = {                      # [level] -> a road site's guard, (vehicle type, count); a plant has it twice
    1: [("Ural_375_ZU_23", 1)],
    2: [("ZSU_23_4_Shilka", 1)],
    3: [("ZSU_23_4_Shilka", 1), ("Strela_10M3", 1)],
}
TRUCK = [("Ural_375", 1)]      # an unguarded site: one parked truck (a site's vehicle group has to have a member; it carries no weapon)
PLANT_VARIANTS = ("REFINERY", "FACTORY")


def is_road(a) -> bool:
    return a.id.startswith(ROAD_PREFIX)


def guard_comp(a, level: int) -> list:
    """The vehicle group of a road site: nothing but a truck when unguarded, the level's light guard, a plant's double guard."""
    if a.variant == "ROAD0":
        return list(TRUCK)
    g = GUARD.get(level, GUARD[2])
    return [(t, n * (2 if a.variant in PLANT_VARIANTS else 1)) for t, n in g]


CORRIDOR_KM = 60.0            # only sites this near the line of sectors are judged by the front (the north of the mountains is red whatever the front does)
FLIP_MARGIN_KM = 8.0          # a site changes hands when the line has gone this far past it (judgment call)
FLIP_PER_DAY = 2              # at most this many a day, the ones nearest the line first (judgment call: a front that jumps does not swing the supply figure at once)


def flip(state) -> list:
    """v0.41.258 (XO 2026-11-03: "red supplies on the plains that belong to blue... how would they get their goods through?"): a road site the front has passed changes hands
    with its stock, in both directions. A red site flips to Blue when the line is FLIP_MARGIN_KM or more on the red side of it; a Blue one to Red the other way. The red battalion that
    guarded a flipped site is destroyed. -> log lines."""
    from . import ground
    g = state.ground
    if not ground.active(state) or not g.get("centers"):
        return []
    lk = float(g.get("line_km", ground.line_km(g)))
    cand = []
    for pool, to_blue in ((state.assets, True), (state.blue_assets, False)):
        for a in pool.values():
            if not is_road(a) or a.kind not in ground.SUPPLY_KINDS:
                continue
            k, lat = ground.path_pos(g, a.x, a.y)
            if lat > CORRIDOR_KM:
                continue
            past = (k - lk) if to_blue else (lk - k)               # km the line has gone beyond the site (larger km = the Blue end)
            if past >= FLIP_MARGIN_KM:
                cand.append((past, a.id, to_blue))
    lines = []
    for _past, aid, to_blue in sorted(cand, reverse=True)[:FLIP_PER_DAY]:
        src, dst = (state.assets, state.blue_assets) if to_blue else (state.blue_assets, state.assets)
        a = src[aid]
        if a.variant in ("ROAD0", "ROADB"):
            a.variant = "ROAD"
        ground._move_sites(state, [aid], to_blue=to_blue)
        if to_blue:
            for x in state.assets.values():
                if getattr(x, "guards", "") == aid:
                    x.health = 0.0                                   # the battalion that held it is gone (kept as a destroyed asset: a postponed job may still name it)
        g.setdefault("road_flips", []).append({"id": aid, "day": state.day, "to": "blue" if to_blue else "red"})
        lines.append(f"{a.name}: the front has passed it, it is ours now, with its stock" if to_blue else f"{a.name}: the front has passed it, the enemy holds it now, with its stock")
    return lines


def guard_units(a, level: int) -> int:
    return sum(n for _t, n in guard_comp(a, level))


def _place(name: str) -> str:
    """'Maykop-Khanskaya' -> 'Maykop', 'Mineralnye Vody' stays: the town a site is named for."""
    return name.split("-")[0].strip()


def _rng(st, parent: random.Random | None) -> random.Random:
    """Its own random stream (seeded from one draw of the campaign's): the campaign's other draws are the same as without road sites."""
    return random.Random(parent.random() if parent is not None else st.campaign_id)


def _pick(cands, n, sep, rng, taken):
    """n spots out of `cands` (shuffled), none within `sep` of one already taken (`taken`: list of (x, y), grown here). Three passes with a smaller sep."""
    out = []
    pool = list(cands)
    rng.shuffle(pool)
    for s in (sep, sep * 0.55, sep * 0.33):
        for c in pool:
            if len(out) >= n:
                return out
            if c in out:
                continue
            if all(math.hypot(c["x"] - tx, c["y"] - ty) >= s for tx, ty in taken):
                out.append(c)
                taken.append((c["x"], c["y"]))
    return out


def _dry_near(x, y, rng) -> tuple | None:
    """A dry point 1.6 to 3 km from (x, y) for a battalion, or None."""
    from . import seacheck
    for _ in range(12):
        r = rng.uniform(*BATTALION_OFFSET_M)
        a = rng.uniform(0, 2 * math.pi)
        px, py = x + r * math.cos(a), y + r * math.sin(a)
        if seacheck.site_ok(px, py):
            return round(px), round(py)
    return None


def build(st, th: dict, d, ap: dict, rng: random.Random | None = None) -> dict:
    """Lay the road sites of a new campaign. `ap` = {airport name: (x, y)} of the theatre. Adds to st.assets / st.blue_assets, keeps the Supply figure's
    bookkeeping (ground["sup_n"], ["sup_h"]) in step and records the counts under ground["road"]. -> that record ({} when nothing was laid)."""
    from . import ground, sites as sites_mod
    g = getattr(st, "ground", None)
    sites = sites_mod.load(th)
    spots = [tuple(p) for p in ((sites or {}).get("road") or {}).get("supply", [])]
    blue_ap = set(th.get("road_blue_airports") or [])
    total = int(getattr(d, "road_sites", 0))
    if not g or not spots or not blue_ap or total <= 0 or not ap:
        return {}
    r = _rng(st, rng)
    names = list(ap)
    red_fields = [(f["id"], ap[f["airport"]]) for f in th["red_fields"] if f["airport"] in ap]
    tiers = th.get("field_tier", {})
    centres = g.get("centers") or []
    taken_assets = [(a.x, a.y) for pool in (st.assets, getattr(st, "blue_assets", None) or {}) for a in pool.values()
                    if a.kind in (AssetKind.FUEL, AssetKind.DEPOT, AssetKind.C2)]          # supply and command sites only: the SAM and column spots shift from run to run (hash order), the sites must not
    cands = {"red": [], "blue": []}
    for x, y in spots:
        near = min(names, key=lambda n: math.hypot(ap[n][0] - x, ap[n][1] - y))
        if math.hypot(ap[near][0] - x, ap[near][1] - y) < AIRFIELD_CLEAR_M:
            continue
        if any(math.hypot(x - tx, y - ty) < ASSET_CLEAR_M for tx, ty in taken_assets):
            continue
        side = "blue" if near in blue_ap else "red"
        tier = 1
        if side == "red" and red_fields:
            fid = min(red_fields, key=lambda f: math.hypot(f[1][0] - x, f[1][1] - y))[0]
            tier = int(tiers.get(fid, 3))
        dfront = min((math.hypot(x - cx, y - cy) for cx, cy in centres), default=1e9) / 1000.0
        cands[side].append({"x": x, "y": y, "place": _place(near), "tier": tier, "dfront": dfront})
    n_red = min(len(cands["red"]), round(total * RED_SHARE))
    n_blue = min(len(cands["blue"]), total - round(total * RED_SHARE))
    added = {"red": [], "blue": []}
    for side, n in (("red", n_red), ("blue", n_blue)):
        if n <= 0:
            continue
        taken: list = []
        sc = total / 100.0
        want_ref, want_fac = (max(1, round(k * sc)) for k in PLANTS_PER_100[side])
        far = [c for c in cands[side] if c["dfront"] >= PLANT_MIN_KM]
        plants: list = []
        ptaken: list = []
        for variant, k in (("REFINERY", want_ref), ("FACTORY", want_fac)):
            got = _pick([c for c in far if c not in plants], min(k, n), PLANT_SEP_M, r, ptaken)
            for c in got:
                c["variant"] = variant
            plants += got
        taken += [(c["x"], c["y"]) for c in plants]
        rest = _pick([c for c in cands[side] if c not in plants], n - len(plants), SEP_M, r, taken)
        sites_ = plants + rest
        rest_ids = [id(c) for c in rest]
        if side == "red":
            n_open = round(float(getattr(d, "road_open", 0.0)) * len(rest))
            for c in r.sample(rest, min(n_open, len(rest))):
                c["variant"] = "ROAD0"
            n_bat = round(float(getattr(d, "road_battalion", 0.0)) * len(sites_))
            guarded = [c for c in sites_ if c.get("variant") != "ROAD0"]
            guarded.sort(key=lambda c: (c["dfront"] > ground.GARRISON_CAS_MAX_KM, r.random()))        # near the front first: those are the CAS jobs
            for c in guarded[:n_bat]:
                c["battalion"] = True
        for c in sites_:
            c.setdefault("variant", "ROAD")
            if c.get("battalion") and c["variant"] == "ROAD":
                c["variant"] = "ROADB"
        # fuel points and supply dumps, half and half (the plants' kind follows their variant)
        ordinary = [c for c in sites_ if id(c) in rest_ids]
        r.shuffle(ordinary)
        for i, c in enumerate(ordinary):
            c["kind"] = AssetKind.FUEL if i % 2 == 0 else AssetKind.DEPOT
        for c in plants:
            c["kind"] = AssetKind.FUEL if c["variant"] == "REFINERY" else AssetKind.DEPOT
        added[side] = sorted(sites_, key=lambda c: (c["place"], c["x"], c["y"]))
    count: dict = {}
    for side in ("red", "blue"):
        pool = st.assets if side == "red" else st.blue_assets
        pre = "rsup" if side == "red" else "bsup"
        for n, c in enumerate(added[side], 1):
            kind, var = c["kind"], c["variant"]
            label = {"REFINERY": "Oil refinery", "FACTORY": "Factory"}.get(var) or ("Fuel point" if kind == AssetKind.FUEL else "Supply dump")
            k = count[(side, label, c["place"])] = count.get((side, label, c["place"]), 0) + 1
            aid = f"{pre}_{n:03d}"
            nm = f"{label} near {c['place']}" + (f" {k}" if k > 1 else "")
            val = VALUE_PLANT if var in PLANT_VARIANTS else VALUE_ROAD
            pool[aid] = EnemyAsset(aid, nm, kind, float(c["x"]), float(c["y"]), 1.0, val, [], None, var, c["tier"] if side == "red" else 1, "")
            if c.get("battalion"):
                p = _dry_near(c["x"], c["y"], r)
                if p is not None:
                    gid = f"rgar_sup_{n:03d}"
                    pool[gid] = EnemyAsset(gid, f"Battalion at {nm}", AssetKind.ARMOR, float(p[0]), float(p[1]), 1.0, 5, [], None, "GARRISON", c["tier"], aid)
    # the Supply figure: every site either side holds, counted from the start
    g["sup_n"] = {"red": sum(1 for a in st.assets.values() if a.kind in ground.SUPPLY_KINDS), "blue": sum(1 for a in st.blue_assets.values() if a.kind in ground.SUPPLY_KINDS)}
    g.setdefault("sup_h", {}).update({a.id: 1.0 for pool in (st.assets, st.blue_assets) for a in pool.values() if a.kind in ground.SUPPLY_KINDS})
    rec = {"v": 1, "red": len(added["red"]), "blue": len(added["blue"]),
           "plants": {s: sum(1 for c in added[s] if c["variant"] in PLANT_VARIANTS) for s in ("red", "blue")},
           "open": sum(1 for c in added["red"] if c["variant"] == "ROAD0"), "battalions": sum(1 for c in added["red"] if c.get("battalion"))}
    g["road"] = rec
    return rec
