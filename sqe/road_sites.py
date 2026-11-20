"""Supply sites along the roads of a new campaign (queue item i, v0.41.241; XO 2026-11-03).

The road-net step (roadnet.py) left a few hundred supply spots in the sites file under "road". A new campaign draws `d.road_sites_red` and `d.road_sites_blue` of them (two
numbers per level) and turns each into a fuel point or a supply dump: red's on its own side of the front, ours on ours. They are what makes both sides' supply
worth striking and worth guarding: together with the fuel farms and depots at the airfields they ARE the Supply figure (ground.supply counts every site
either side holds, so there is no separate production link). A handful per side are big plants (oil refineries = FUEL sites, factories = DEPOT sites)
well away from the front.

Judgment calls (no public figure; tune on XO's runs): the red/blue counts per level (Difficulty.road_sites_red / _blue: hometown advantage for red, a thin blue; XO 2026-11-11), the 9 km spacing between sites, 90 km from a sector centre for a
plant, the plant counts, the guard strengths, the shares of unguarded sites and battalions (Difficulty.road_*).

Rules from XO:
  * Owner by place: a spot belongs to the side whose airfield is nearest (the theatre file lists the blue-side airports); the north of the mountains is
    always red. Ownership is fixed when the campaign is built (a site does not change hands with the front).
  * Defenders scale with the level: most red sites have a light guard (ZU-23 truck / Shilka / Shilka + Strela-10), about a third of them at Level 3 only a parked
    truck, a few a dug-in battalion (a CAS job when it sits near a sector centre; no friendly ground troops or JTAC beyond the mountains, #280).
  * Blue's road sites are buildings only, like blue's other supply sites (their cover is the Patriot / HAWK / AAA at the fields); no blue battalions.
  * The ammo depots and fuel farms at the airfields are not touched here (they stay near their bases, sites.apply).
  * S108 (XO 2026-11-18, v0.41.496): (1) a depot lies at most OWNER_MAX_KM from its owner's nearest airfield; (2) along a road the depots of the two sides never interleave (all of one side, then all
    of the other); (3) no red depot within CROSS_SEP_M of a blue one. A side that cannot fill its quota under these gets fewer depots, never a bad one (the rules are never relaxed; the 9 km spacing
    still is). At `flip` a depot the front's move would put in breach of (2) or (3) FALLS (destroyed for good, stock lost) instead of changing hands.
New campaigns only: an older save keeps the sites it has.

Ids: `rsup_NNN` / `bsup_NNN` (a red id must not start with "b", see overview_detail.supply_rows), a battalion `rgar_sup_NNN` (guards = its site).
Variants: ROAD (light guard), ROAD0 (a parked truck), ROADB (light guard and a battalion), REFINERY / FACTORY (a plant: double guard, may have a battalion).
"""
from __future__ import annotations

import math
import random
import re

from . import road_front
from .models import AssetKind, EnemyAsset

SEP_M = 9000.0                # no two road sites closer than this (relaxed in two steps if a side cannot fill its quota)
OWNER_MAX_KM = 100.0          # S108 rule 1 (XO 2026-11-18, judgment call; the S108 report: red tops out at 99 km today): a depot is at most this far (straight line) from its owner's nearest airfield
CROSS_SEP_M = 20000.0         # S108 rule 3 (XO 2026-11-18, judgment call, 15 to 25 km: the report's closest red-blue pair was 4.8 km): no depot of one side this close to one of the other
AIRFIELD_CLEAR_M = 5000.0     # no road site this close to any airfield (the fuel farm and garrison sit there)
ASSET_CLEAR_M = 2500.0        # ...or to any existing asset
PLANT_MIN_KM = 90.0           # a refinery / factory is at least this far from every sector centre ("away from the front")
PLANT_SEP_M = 40000.0         # ...and at least this far from another plant
PLANTS_PER_100 = {"red": (3, 3), "blue": (2, 2)}      # (refineries, factories) for a 100-site campaign; scaled by (red + blue road sites) / 100, at least 1 each
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


def flip(state) -> list:
    """v0.41.258 (XO 2026-11-03: "red supplies on the plains that belong to blue... how would they even get their goods through?"; "road connections cut by the front"): a road
    supply site belongs to the side its road connects to (road_front.py). The night the front cuts a site off from its owner, it changes hands with its stock, both ways (the same move
    as a captured field's sites; the Overview lists it as "(captured)"). The red battalion that guarded a site that goes to Blue is destroyed. -> log lines."""
    from . import ground, theatres
    g = state.ground
    if not ground.active(state) or not g.get("centers"):
        return []
    th = theatres.active()
    rts = road_front.routes(th)
    if not rts:
        return []
    sides = road_front.route_sides(state, th, rts)
    lost = set(g.get("road_fell") or [])
    sites = {}                                                        # id -> (asset, the side that holds it now); a fallen depot is out of it for good
    for pool, own in ((state.assets, "red"), (state.blue_assets, "blue")):
        for a in pool.values():
            if is_road(a) and a.kind in ground.SUPPLY_KINDS and a.id not in lost:
                sites[a.id] = (a, own)
    post = {i: road_front.site_side(state, th, rts, sides, a.x, a.y) for i, (a, _o) in sites.items()}          # who holds each one once the sides are re-assigned
    movers = sorted(i for i in sites if post[i] != sites[i][1])
    if not movers:
        return []
    falls = _falls(sites, post, movers, rts)
    lines = []
    for i in movers:
        a, own = sites[i]
        to_blue = own == "red"
        if i in falls:                                                # S108 rule 4: the move would break rule 2 or 3: it is destroyed instead of changing hands
            a.health = 0.0
            g.setdefault("sup_h", {})[i] = 0.0
            g.setdefault("road_fell", []).append(i)
            for x in state.assets.values():
                if getattr(x, "guards", "") == i:
                    x.health = 0.0
            g.setdefault("road_flips", []).append({"id": i, "day": state.day, "to": "lost"})
            lines.append(f"{a.name}: the front has cut its road, it is lost, with its stock")
            continue
        if a.variant in ("ROAD0", "ROADB"):
            a.variant = "ROAD"
        ground._move_sites(state, [i], to_blue=to_blue)
        if to_blue:
            for x in state.assets.values():
                if getattr(x, "guards", "") == i:
                    x.health = 0.0                                   # the battalion that held it is gone (kept as a destroyed asset: a postponed job may still name it)
        g.setdefault("road_flips", []).append({"id": i, "day": state.day, "to": "blue" if to_blue else "red"})
        lines.append(f"{a.name}: the front has cut its road, it is ours now, with its stock" if to_blue else f"{a.name}: the front has cut its road, the enemy holds it now, with its stock")
    return lines


def _changes(seq) -> int:
    """Side changes along an ordered list of sides: 0 or 1 = 'all of one side, then all of the other'; 2 or more = interleaved (B R B)."""
    return sum(1 for a, b in zip(seq, seq[1:]) if a != b)


def _falls(sites: dict, post: dict, movers: list, rts: list) -> set:
    """S108 rule 4: which of the depots about to change hands fall instead. `sites` {id: (asset, side now)}, `post` {id: side after the move}. One falls when, in the state after the move (those
    that fell before it in this loop left out), an enemy depot lies closer than CROSS_SEP_M to it (rule 3) or the move makes a road read B R B (rule 2: more side changes along a route it lies on than
    before). Judged in id order, one at a time, so the depots of one stretch that all change hands together do not make each other interleave."""
    along = {i: dict(road_front.along(rts, a.x, a.y)) for i, (a, _o) in sites.items()}
    gone: set = set()

    def breaks(i) -> bool:
        a = sites[i][0]
        for j, (b, _o) in sites.items():
            if j != i and j not in gone and post[j] != post[i] and math.hypot(a.x - b.x, a.y - b.y) < CROSS_SEP_M:
                return True
        for ri in along[i]:
            ent = sorted((along[j][ri], j) for j in sites if j not in gone and ri in along[j])
            after = _changes([post[j] for _k, j in ent])
            before = _changes([sites[j][1] if j == i else post[j] for _k, j in ent])
            if after >= 2 and after > before:
                return True
        return False

    for i in movers:
        if breaks(i):
            gone.add(i)
    return gone


def guard_units(a, level: int) -> int:
    return sum(n for _t, n in guard_comp(a, level))


def _place(name: str) -> str:
    """'Maykop-Khanskaya' -> 'Maykop', 'Mineralnye Vody' stays: the town a site is named for."""
    return re.split(r"(?<!al)-", name, maxsplit=1, flags=re.I)[0].strip()      # S127: 'Abu al-Duhur' keeps its article part (was cut to 'Abu al')


def _rng(st, parent: random.Random | None) -> random.Random:
    """Its own random stream (seeded from one draw of the campaign's): the campaign's other draws are the same as without road sites."""
    return random.Random(parent.random() if parent is not None else st.campaign_id)


def _pick(cands, n, sep, rng, taken, ok=None):
    """n spots out of `cands` (shuffled), none within `sep` of one already taken (`taken`: list of (x, y), grown here). Three passes with a smaller sep. `ok(c, out)` (S108) is a rule the spot
    must pass whatever the pass: it is never relaxed, so a short list comes back instead of a bad spot."""
    out = []
    pool = list(cands)
    rng.shuffle(pool)
    for s in (sep, sep * 0.55, sep * 0.33):
        for c in pool:
            if len(out) >= n:
                return out
            if c in out or (ok is not None and not ok(c, out)):
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
    want = {"red": int(getattr(d, "road_sites_red", 0)), "blue": int(getattr(d, "road_sites_blue", 0))}
    cap = (((th.get("works") or {}).get("levels") or {}).get(str(getattr(d, "level", ""))) or {}).get("supply_total")
    if cap and g and g.get("works"):                                  # S131 (XO 2026-11-20): red's whole supply count with the works (25 on Syria 2/3): the road sites fill what the fixed sites and the works leave
        fixed = sum(1 for a in st.assets.values() if ground.is_supply(a))
        want["red"] = min(want["red"], max(0, int(cap) - len(g["works"].get("ids") or []) - fixed))
    total = want["red"] + want["blue"]
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
    own_fields = {"red": [ap[n] for n in [f["airport"] for f in th["red_fields"]] + list(th.get("red_extra_airports") or []) if n in ap],
                  "blue": [ap[n] for n in blue_ap if n in ap]}         # S108 rule 1: the fields a side's depots are measured from
    skipped = {s: {"cap": 0, "sep": 0, "order": 0} for s in ("red", "blue")}
    rts = road_front.routes(th)
    rsides = road_front.route_sides(st, th, rts) if rts else None
    for x, y in spots:
        near = min(names, key=lambda n: math.hypot(ap[n][0] - x, ap[n][1] - y))
        if math.hypot(ap[near][0] - x, ap[near][1] - y) < AIRFIELD_CLEAR_M:
            continue
        if any(math.hypot(x - tx, y - ty) < ASSET_CLEAR_M for tx, ty in taken_assets):
            continue
        side = road_front.site_side(st, th, rts, rsides, x, y) if rts else ("blue" if near in blue_ap else "red")          # v0.41.258: the side its road connects to (road_front.py)
        tier = 1
        if side == "red" and red_fields:
            fid = min(red_fields, key=lambda f: math.hypot(f[1][0] - x, f[1][1] - y))[0]
            tier = int(tiers.get(fid, 3))
        dfront = min((math.hypot(x - cx, y - cy) for cx, cy in centres), default=1e9) / 1000.0
        too_far = min((math.hypot(x - fx, y - fy) for fx, fy in own_fields[side]), default=0.0) / 1000.0 > OWNER_MAX_KM
        skipped[side]["cap"] += int(too_far)
        cands[side].append({"x": x, "y": y, "place": _place(near), "tier": tier, "dfront": dfront, "far": too_far})          # kept in the list (the shuffle is the same as before the rule), never picked
    n_red = min(len(cands["red"]), want["red"])
    n_blue = min(len(cands["blue"]), want["blue"])
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
        other = "blue" if side == "red" else "red"
        placed = added[other]                                       # S108: the depots the other side already has (none for the first side)
        if placed and rts:
            for c in placed + cands[side]:
                c.setdefault("along", dict(road_front.along(rts, c["x"], c["y"])))
        seps: set = set()
        orders: set = set()

        def ok(c, out) -> bool:
            if c["far"]:                                            # rule 1
                return False
            if not placed:
                return True
            if any(math.hypot(c["x"] - p["x"], c["y"] - p["y"]) < CROSS_SEP_M for p in placed):          # rule 3
                seps.add(id(c))
                return False
            if rts:                                                 # rule 2: this spot must not make a road read B R B
                for ri, km in c["along"].items():
                    seq = sorted([(p["along"][ri], other) for p in placed if ri in p["along"]] + [(m["along"][ri], side) for m in plants + out if ri in m["along"]] + [(km, side)])
                    if _changes([s for _k, s in seq]) >= 2:
                        orders.add(id(c))
                        return False
            return True

        for variant, k in (("REFINERY", want_ref), ("FACTORY", want_fac)):
            got = _pick([c for c in far if c not in plants], min(k, n), PLANT_SEP_M, r, ptaken, ok)
            for c in got:
                c["variant"] = variant
            plants += got
        taken += [(c["x"], c["y"]) for c in plants]
        rest = _pick([c for c in cands[side] if c not in plants], n - len(plants), SEP_M, r, taken, ok)
        skipped[side]["sep"], skipped[side]["order"] = len(seps), len(orders)
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
    ground.set_supply_counts(st)                                      # v0.41.408 (S49): the counts, and on Level 1 the inner / road split of red's
    g.setdefault("sup_h", {}).update({a.id: 1.0 for pool in (st.assets, st.blue_assets) for a in pool.values() if a.kind in ground.SUPPLY_KINDS})
    rec = {"v": 1, "red": len(added["red"]), "blue": len(added["blue"]),
           "plants": {s: sum(1 for c in added[s] if c["variant"] in PLANT_VARIANTS) for s in ("red", "blue")},
           "open": sum(1 for c in added["red"] if c["variant"] == "ROAD0"), "battalions": sum(1 for c in added["red"] if c.get("battalion")),
           "skipped": skipped}          # S108: per side, the spots the new rules kept out: "cap" (beyond OWNER_MAX_KM), "sep" (within CROSS_SEP_M of the other side's depot), "order" (would interleave a road)
    g["road"] = rec
    return rec
