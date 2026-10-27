"""The ground war: both sides hold strength in a row of sectors along the front, and the line between them moves.

The front axis (from the theatre pack: from_airport -> to_airport, optionally on to a second field) is cut into zones. Each zone holds a RED strength and a BLUE
strength (0-100 points). Where both are present the zone is contested and the fight happens there; where one side is alone, it holds the zone.
Everything is plain numbers in CampaignState.ground (JSON), so it saves with the campaign.

One rule set for both sides (only the numbers differ with difficulty):
  * each day, in every contested zone, strength x supply decides the fight. An attack (Red with a chance set by difficulty, Blue when it is clearly
    stronger) costs both sides more than a skirmish; a decisive win routs the loser, whose survivors fall back into the next zone behind;
  * reinforcements arrive at the zone in contact, scaled by that side's supply;
  * supply comes from the side's fuel and depot sites (Red: state.assets, Blue: state.blue_assets). A struck depot weakens every sector it feeds;
  * air power enters through the Red column of each zone, a real asset (armor_N): its health IS the zone's Red strength between days. A CAS flight
    that damages it takes strength off the zone; the daily fight then starts from the lower number;
  * if Red holds the zone next to one of our fields, that field falls (its defences go, its squadrons move to the nearest field with losses). Two fields
    lost at once is a defeat.

v0.41.143 (Campaign Revamp Stage B1, "the push"): the line of sectors now runs from the red end of the campaign (Sochi on Levels 1 and 2, Krymsk on
Level 3) through every red base on the coast road to Senaki and Kutaisi. Each red base has a doorstep sector on our side of it; it FALLS when we hold
that sector and the enemy has nothing there, and can be retaken the same way. The next attack waits for a takeover clock (CLOCK_DAYS) after a fall.
Victory is by ground only: Sochi (Levels 1, 2) or Sochi AND Krymsk (Level 3), and on Levels 2 and 3 the enemy gets one last counter-force at the final
base. See `docs/CHANGES.md` v0.41.143 and the plan docs in the Project.

Pure planning and bookkeeping, no pydcs. Positions are DCS metres (x north, y east).
"""
from __future__ import annotations
import math
from .models import AssetKind, EnemyAsset

NM = 1852.0
MIN_FORCE = 3.0               # below this a side has no organised force in the zone
MAX_FORCE = 100.0
SUPPLY_KINDS = (AssetKind.FUEL, AssetKind.DEPOT)
AIR_EFFECT = 0.6              # share of a visible column's losses that its zone's strength takes (the column is only the lead element)
BLUE_LOSS = 40.0              # blue strength lost when the whole friendly task force at the JTAC is destroyed
SKIRMISH, ATTACK = 0.04, 0.14
DECISIVE, REPULSED = 1.8, 0.55
RETREAT_SHARE = 0.6           # what a routed force saves by falling back
FALL_LOSS = 0.3               # aircraft lost when a field falls and its squadrons leave
SUPPLY_FLOOR, SUPPLY_NONE = 0.55, 0.85
SUPPLY_REPAIR_DAYS = 6.0     # v0.41.144 (XO 2026-10-24, judgment call): a supply site is fully repaired in this many days at 100% supply; slower when the owner's supply is low (55% = about 11 days); no repair on a day it is struck
L1_RED_SUPPLY_FLOOR = 0.70    # v0.41.141 (XO 2026-10-27, Campaign Revamp): on Level 1 the insurgents are resupplied across the border by night, so their supply never drops below this however many depots die (judgment call; a toy-model run showed it does not change who wins). Levels 2 and 3 keep the 55% floor.


GROUND_V = 3                  # state.ground["v"]: 2 = the Campaign Revamp ground war (red bases fall); a campaign with v 1 cannot be loaded
CLOCK_DAYS = 9                # takeover clock: days after a base falls before our next attack (toy-model base case; judgment call)
REAR_FRAC = 0.7               # red strength in the sectors behind its first line, as a share of its first sector's start strength (judgment call)
BLUE_ATTACK_MIN = 30.0        # our force in a sector must be at least this before we attack (toy model "THR"; judgment call)
BLUE_ATTACK_RATIO = 0.9       # ...and not weaker than this share of the enemy's strength there (supply-weighted)
BLUE_ATTACK_CHANCE = 0.7      # daily chance that a ready force attacks
RED_CLOCK_DAYS = 3            # after we take a base the enemy's own attacks wait this long (its force needs 3 days to arrive; XO 2026-10-24 item 5)
AI_CAS = {1: 3, 2: 2, 3: 3}     # abstract daily blue air strikes on the sector facing us (judgment call: the toy model's AI CAS, 1-3 a day)
AI_CAS_P = 0.55
AI_CAS_CUT = 0.15
COUNTER_DELAY_DAYS = 3        # the enemy's last counter-force arrives this many days after the final base falls
COUNTER_FORCED_DAYS = 6       # ...and attacks every day for this long
COUNTER_FRAC = {1: 0.0, 2: 0.35, 3: 0.60}      # counter-force strength as a share of a full 100-point sector (toy model; judgment call)


def active(state) -> bool:
    return bool(getattr(state, "ground", None))


# ---- layout ---------------------------------------------------------------------------------------------------------------------
def _lerp(a, b, f):
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f


def zone_centers(axis, leg_zones) -> list:
    """Evenly spaced zone centres: leg k of the axis is cut into leg_zones[k] equal zones."""
    out = []
    for k, n in enumerate(leg_zones):
        a, b = axis[k], axis[k + 1]
        for i in range(n):
            out.append(list(_lerp(a, b, (i + 0.5) / n)))
    return out


def _chain_for(th, level: int):
    """(nodes, legs, stage ids) for a level: the chain of the theatre pack cut at the level's last red target. Nodes run from the red end to the blue end;
    legs[k] is the number of sectors between node k and node k+1."""
    fr = th["front"]
    chain, legs = list(fr["chain"]), list(fr["leg_zones"])
    stages = list((fr.get("stages") or {}).get(str(level)) or [])
    k0 = 0
    if stages:
        k0 = next((k for k, n in enumerate(chain) if n.get("red") == stages[-1]), 0)
    return chain[k0:], legs[k0:], stages


def build(state, th, d, rng, ap) -> None:
    """New campaign: the sectors of the front, the Red column in each, and Blue's facilities. `ap(name)` -> a pydcs airport position."""
    from . import seacheck
    nodes, legs, stages = _chain_for(th, int(getattr(d, "level", 2)))
    pts = [ap(n["airport"]) for n in nodes]
    axis = [[p.x, p.y] for p in pts]
    centers = zone_centers(axis, legs)
    centers = [list(seacheck.snap_to_land(c[0], c[1])) for c in centers]
    n = len(centers)
    names = []
    for k, cnt in enumerate(legs):
        a_, b_ = nodes[k]["name"], nodes[k + 1]["name"]
        names += [f"{a_} - {b_}" if cnt == 1 else f"{a_} - {b_} {j + 1}/{cnt}" for j in range(cnt)]
    red0, blue0 = _initial(d, n)
    off = lambda k: sum(legs[:k])
    rbases = [{"id": nd["red"], "name": nd["name"], "zone": off(k), "x": axis[k][0], "y": axis[k][1]} for k, nd in enumerate(nodes) if nd.get("red")]
    order = {sid: i for i, sid in enumerate(stages)}
    rbases.sort(key=lambda r: order.get(r["id"], 99))                      # in the order we take them
    fall = {str(off(k) - 1): nd["blue"] for k, nd in enumerate(nodes) if nd.get("blue") and off(k) >= 1}
    fr = th["front"]
    state.ground = {"v": GROUND_V, "axis": axis, "legs": legs, "centers": centers, "names": names, "red": red0, "blue": blue0,
                    "fall": fall, "fallen": [], "line_km": 0.0,
                    "rbases": rbases, "stages": stages, "taken": [], "taken_day": {}, "clock": 0,
                    "victory_ids": list((fr.get("victory") or {}).get(str(d.level), [])), "counter_id": (fr.get("counter") or {}).get(str(d.level), ""),
                    "counter": None, "won": False}
    state.ground["line_km"] = line_km(state.ground)
    # the Red column of each sector
    for i, (cx, cy) in enumerate(centers):
        state.assets[f"armor_{i + 1}"] = EnemyAsset(f"armor_{i + 1}", f"Armor column {_col_letter(i)}", AssetKind.ARMOR, cx, cy, 1.0, 6 + min(i, 2), [], None, "ARMOR", 1)
    push(state)
    build_blue_assets(state, rng, ap)
    ensure_forward_garrisons(state)


def _col_letter(i: int) -> str:
    return chr(65 + i) if i < 26 else chr(65 + i // 26 - 1) + chr(65 + i % 26)


def _initial(d, n) -> tuple:
    """Strength per sector, red end first: the level's five start values sit at the blue end (the old front); the sectors behind them hold red's rear
    strength, REAR_FRAC of the first start value, and none of ours."""
    red_t = [float(x) for x in getattr(d, "ground_red", (70, 55, 15, 0, 0))]
    blue_t = [float(x) for x in getattr(d, "ground_blue", (0, 15, 60, 70, 50))]
    rear = max(0, n - len(red_t))
    red = [REAR_FRAC * red_t[0]] * rear + red_t
    blue = [0.0] * rear + blue_t
    return red[-n:], blue[-n:]


def build_blue_assets(state, rng, ap=None) -> None:
    """Blue's supply sites: a fuel farm at every airfield and a forward depot behind the front. They can be struck (by Red raids, later) and repair daily."""
    from . import seacheck
    import hashlib
    ba = {}
    for b in state.bases.values():
        if b.kind.value != "AIRFIELD":
            continue
        ang = int(hashlib.md5(b.id.encode()).hexdigest()[:4], 16) % 360
        x, y = seacheck.snap_to_land(b.x + 2200 * math.cos(math.radians(ang)), b.y + 2200 * math.sin(math.radians(ang)))
        ba[f"bfuel_{b.id}"] = EnemyAsset(f"bfuel_{b.id}", f"{b.name.replace(' AB', '')} fuel farm", AssetKind.FUEL, x, y, 1.0, 5, [], None, "", 1)
        ba[f"bgar_{b.id}"] = _blue_garrison(b)
    g = state.ground
    if g:
        zi = min((int(k) for k in g.get("fall", {})), default=len(g["centers"]) - 1)         # the sector next to our first airfield (Senaki)
        c = g["centers"][zi]
        kn = next((k for k in range(len(g["legs"]) + 1) if sum(g["legs"][:k]) == zi + 1), min(1, len(g["axis"]) - 1))
        far = g["axis"][kn]
        x, y = seacheck.snap_to_land(*_lerp(c, far, 0.6))
        ba["bdepot_fwd"] = EnemyAsset("bdepot_fwd", "Forward supply depot", AssetKind.DEPOT, x, y, 1.0, 6, [], None, "", 1)
        x, y = seacheck.snap_to_land(*_lerp(g["centers"][-1], g["axis"][-1], 0.5))           # v0.41.144: a rear depot at the back of our line, well behind the forward one
        ba["bdepot_rear"] = EnemyAsset("bdepot_rear", "Rear supply depot", AssetKind.DEPOT, x, y, 1.0, 5, [], None, "", 1)
    state.blue_assets = ba
    if g is not None:
        g["sup_n"] = {"red": sum(1 for a in state.assets.values() if a.kind in SUPPLY_KINDS), "blue": sum(1 for a in ba.values() if a.kind in SUPPLY_KINDS)}
        g["sup_h"] = {a.id: 1.0 for a in list(state.assets.values()) + list(ba.values()) if a.kind in SUPPLY_KINDS}


def _blue_garrison(b) -> EnemyAsset:
    """A friendly dug-in garrison next to an airfield: the same record as the enemy's, so it follows the same rules (raids, repair, rebuild)."""
    from . import seacheck
    import hashlib
    ang = (int(hashlib.md5(b.id.encode()).hexdigest()[:4], 16) + 137) % 360
    x, y = seacheck.snap_to_land(b.x + 3200 * math.cos(math.radians(ang)), b.y + 3200 * math.sin(math.radians(ang)))
    return EnemyAsset(f"bgar_{b.id}", f"{b.name.replace(' AB', '')} garrison", AssetKind.ARMOR, x, y, 1.0, 5, [], None, "GARRISON", 1, b.id)


# v0.41.102: forward garrisons, one dug-in position per sector for each side (red `rfwd_N` in state.assets, blue `bfwd_N` in state.blue_assets), 
# a few km either side of the sector centre, red toward the enemy end of the axis (sector 1) and blue toward ours. Numbers are JUDGMENT CALLS inside the
# range open sources give (Dupuy Institute: a prepared defence is worth about x1.3 to over x3 depending on preparation and terrain; US planning ratios about
# 3:1 against a prepared defender, 2.5:1 against a hasty one; positional defence keeps at least two-thirds of the force forward in platoon / company
# strongpoints). Tune on XO's runs.
FWD_OFFSET_M = 3000.0         # each garrison sits this far either side of the sector centre
FWD_EXTRA = 0.25              # defender factor added by a full-health garrison in the sector: DEFENDER 1.25 -> 1.5 (a standing garrison, still inside the sourced range)
FWD_SHARE = 0.15              # share of its side's sector strength lost when the garrison is destroyed (scaled by the health it lost)
FWD_REBUILD = 0.25            # daily chance (scaled by supply) that a lost forward garrison is re-established while its side still holds the sector


def fwd_id(side: str, i: int) -> str:
    return f"{'r' if side == 'red' else 'b'}fwd_{i + 1}"


def fwd_pos(g, i: int, side: str) -> tuple:
    from . import seacheck
    c, n = g["centers"], len(g["centers"])
    cx, cy = c[i]
    a, b = c[max(i - 1, 0)], c[min(i + 1, n - 1)]
    vx, vy = a[0] - b[0], a[1] - b[1]                  # from the higher-numbered neighbour toward the lower one: toward the enemy
    L = math.hypot(vx, vy) or 1.0
    k = (1.0 if side == "red" else -1.0) * FWD_OFFSET_M / L
    return seacheck.snap_to_land(cx + vx * k, cy + vy * k)


def ensure_forward_garrisons(state) -> bool:
    """Every sector gets a dug-in garrison for each side (new campaigns and older saves). Returns True when it added any."""
    g = getattr(state, "ground", None)
    if not g or not g.get("centers") or not isinstance(getattr(state, "blue_assets", None), dict):
        return False
    added = False
    for i in range(n_zones(g)):
        for side, pool in (("red", state.assets), ("blue", state.blue_assets)):
            aid = fwd_id(side, i)
            if aid in pool:
                continue
            x, y = fwd_pos(g, i, side)
            nm = f"{'Enemy' if side == 'red' else 'Friendly'} forward position, {g['names'][i]}"
            pool[aid] = EnemyAsset(aid, nm, AssetKind.ARMOR, x, y, 1.0, 5, [], None, "GARRISON", 1)
            added = True
    if added:
        g.setdefault("fwd", {"r": [1.0] * n_zones(g), "b": [1.0] * n_zones(g)})
    return added


def sector_of(state, asset_id: str):
    """Sector index of a forward garrison ('rfwd_N' / 'bfwd_N'), or None."""
    if not active(state) or not (asset_id.startswith("rfwd_") or asset_id.startswith("bfwd_")):
        return None
    try:
        i = int(asset_id[5:]) - 1
    except ValueError:
        return None
    return i if 0 <= i < n_zones(state.ground) else None


def fwd_health(state, side: str, i: int) -> float:
    a = (state.assets if side == "red" else getattr(state, "blue_assets", {})).get(fwd_id(side, i))
    return 0.0 if a is None else max(0.0, a.health)


def ensure_blue_garrisons(state) -> bool:
    """An older campaign has no friendly garrisons: give every airfield one. Returns True when it added any."""
    if not isinstance(getattr(state, "blue_assets", None), dict):
        return False
    added = False
    for b in state.bases.values():
        if b.kind.value == "AIRFIELD" and f"bgar_{b.id}" not in state.blue_assets:
            state.blue_assets[f"bgar_{b.id}"] = _blue_garrison(b)
            added = True
    return added


ROAD_SNAP_M = 3000.0                     # a column or supply site moves onto a road if one is this close


def snap_roads(state) -> int:
    """Once, as soon as a road scan exists: front-line columns, fuel farms and depots (both sides) move onto the nearest road point (<= ROAD_SNAP_M,
    and still on land); a column's air defence and anything guarding a moved site moves with it. Garrisons stay off the road, dug in. Returns how many moved."""
    from . import roads, seacheck
    g = getattr(state, "ground", None)
    if not g or g.get("roads") or not roads.available():
        return 0
    g["roads"] = True
    moved = 0
    pool = list(state.assets.values()) + list((getattr(state, "blue_assets", None) or {}).values())
    for a in pool:
        if not (a.kind in (AssetKind.FUEL, AssetKind.DEPOT) or (a.kind == AssetKind.ARMOR and a.variant != "GARRISON")):
            continue
        p = roads.snap(a.x, a.y, ROAD_SNAP_M)
        if p is None or p == (a.x, a.y) or not seacheck.site_ok(*p):
            continue
        dx, dy = p[0] - a.x, p[1] - a.y
        a.x, a.y = p
        moved += 1
        for c in state.assets.values():                                   # followers
            if c.guards == a.id or (a.id.startswith("armor_") and c.id == "fsam_" + a.id[6:]):
                c.x, c.y = c.x + dx, c.y + dy
    if moved:
        state.note(f"{moved} columns and supply sites now sit on roads.")
    return moved


def rebuild_blue(state, d, rng) -> list:
    """Overnight: a destroyed friendly supply site or garrison is replaced with a chance that follows friendly supply (the enemy's SAM sites rebuild the same way)."""
    out = []
    sup = supply(state, "blue")
    fallen = set((state.ground or {}).get("fallen", []))
    for a in sorted(state.blue_assets.values(), key=lambda a: a.id):
        if a.health > 0.05 or (a.guards and a.guards in fallen):
            continue
        if rng.random() < d.blue_rebuild * sup:
            a.health = 0.4
            out.append(f"{a.name} was replaced")
    return out


def ensure(state) -> bool:
    """An old campaign (format 4) has no ground war: make one for its level without touching anything else. Returns True when it did."""
    if active(state):
        return False
    try:
        import random
        from . import theatres
        from .difficulty import get as get_difficulty
        th = theatres.use(state.theatre)
        if not th.get("front"):
            return False
        t = theatres.terrain()
        d = get_difficulty(state.level)
        build(state, th, d, random.Random(state.campaign_id), lambda n: t.airports[n].position)
        return True
    except Exception:
        state.ground = {}
        return False


# ---- reading the state ----------------------------------------------------------------------------------------------------------
def n_zones(g) -> int:
    return len(g["red"])


def zone_of(state, asset_id: str):
    """Zone index of a column asset 'armor_N', or None (no ground war, or a garrison / other asset)."""
    if not active(state) or not asset_id.startswith("armor_"):
        return None
    try:
        i = int(asset_id[6:]) - 1
    except ValueError:
        return None
    return i if 0 <= i < n_zones(state.ground) else None


def red_strength(state, i: int) -> float:
    a = state.assets.get(f"armor_{i + 1}")
    return a.health * MAX_FORCE if a is not None else state.ground["red"][i]


def blue_strength(state, i: int) -> float:
    return state.ground["blue"][i]


def info(state, i: int) -> dict:
    r, b = red_strength(state, i), blue_strength(state, i)
    n = n_zones(state.ground)
    contested = r >= MIN_FORCE and b >= MIN_FORCE
    facing = r >= MIN_FORCE and b < MIN_FORCE and i + 1 < n and blue_strength(state, i + 1) >= MIN_FORCE and red_strength(state, i + 1) < MIN_FORCE      # our force stands across the line from the enemy column
    return {"i": i, "name": state.ground["names"][i], "red": r, "blue": b, "contested": contested, "engaged": contested or facing,
            "pressure": r / (r + b) if r + b > 0 else 0.0}


def blue_scale(state, asset_id: str) -> float:
    """How big the friendly task force at this column's JTAC is, against the 1.0 it always was: from the zone's Blue strength."""
    i = zone_of(state, asset_id)
    if i is None:
        i = sector_of(state, asset_id)                  # v0.41.102: a forward garrison is as big as its sector
    if i is None:
        return 1.0
    return max(0.5, min(1.5, blue_strength(state, i) / 50.0))


def pull(state) -> None:
    """Between days the Red column's health is the zone's Red strength (air power changes the column, the fight changes the zone)."""
    g = state.ground
    for i in range(n_zones(g)):
        a = state.assets.get(f"armor_{i + 1}")
        if a is not None:
            g["red"][i] = max(0.0, min(MAX_FORCE, a.health * MAX_FORCE))


def push(state) -> None:
    g = state.ground
    for i in range(n_zones(g)):
        a = state.assets.get(f"armor_{i + 1}")
        if a is not None:
            r = g["red"][i]
            a.health = 0.0 if r < MIN_FORCE else min(1.0, r / MAX_FORCE)


def facility_health(assets, kinds):
    hs = [a.health for a in assets if a.kind in kinds]
    return sum(hs) / len(hs) if hs else None


def supply(state, side: str) -> float:
    """0.55 (no stock left) .. 1.0 (all of the side's sites at hand and intact). v0.41.144: the stock held (sum of the health of the supply sites a side holds)
    over the number it started with, so a captured site raises the captor's figure (up to 100%) and lowers the old owner's (to 55% at worst); a site's
    health is its stock and does not fade. A side that started with no sites runs at 0.85. Red on Level 1 never falls below L1_RED_SUPPLY_FLOOR (0.70)."""
    pool = state.assets.values() if side == "red" else getattr(state, "blue_assets", {}).values()
    sites = [a for a in pool if a.kind in SUPPLY_KINDS]
    n = int(((state.ground or {}).get("sup_n") or {}).get(side, len(sites)))
    v = SUPPLY_NONE if n <= 0 else SUPPLY_FLOOR + (1.0 - SUPPLY_FLOOR) * min(1.0, sum(a.health for a in sites) / n)
    return max(v, L1_RED_SUPPLY_FLOOR) if (side == "red" and getattr(state, "level", 2) == 1) else v


def supply_repair(state) -> list:
    """Overnight: each side's supply sites mend at supply / SUPPLY_REPAIR_DAYS of a full site a day (a destroyed one is back in 6 days at 100% supply,
    about 11 at 55%), except a site that was struck since last night. Skip days count. The owner at the moment pays: a captured site mends at the
    captor's rate."""
    g = state.ground
    prev = g.setdefault("sup_h", {})
    out = []
    for side in ("red", "blue"):
        pool = state.assets if side == "red" else getattr(state, "blue_assets", {})
        rate = supply(state, side) / SUPPLY_REPAIR_DAYS
        for a in pool.values():
            if a.kind not in SUPPLY_KINDS:
                continue
            before = prev.get(a.id, a.health)
            if a.health < before - 1e-6:                                    # struck today: no repair tonight
                pass
            elif a.health < 1.0:
                was_down = a.destroyed
                a.health = min(1.0, a.health + rate)
                if was_down and not a.destroyed and side == "blue":
                    out.append(f"{a.name} is working again")
            prev[a.id] = a.health
    return out


SUPPLY_ROUND_BLUE = 2         # v0.41.144 (XO 2026-10-24, "skip days run a supply-strike round"): background strikes a side tries on a day nobody flew (judgment call)
SUPPLY_ROUND_P = {"open": 0.50, "escorted": 0.20}      # chance one succeeds: site under no live SAM cover / only SA-2/3/6 (the escort has to deal with them); under an SA-11 / SA-10 belt none is tried
SUPPLY_ROUND_HIT = 0.35       # health a struck site loses


def supply_round(state, d, rng) -> list:
    """The background supply-strike round of a skip day: both sides' air still tries to bomb the other's depots and fuel. Blue picks among red's sites
    (not under a live SA-11 / SA-10), red among ours. A struck site is not repaired that night (supply_repair). Returns log lines."""
    from .war import covering_sams, ESCORTABLE
    lines = []
    g = state.ground
    if not g or not active(state):
        return lines

    def pick(pool, attempts, who, p_scale=1.0):
        sites = [a for a in pool if a.kind in SUPPLY_KINDS and not a.destroyed]
        for _ in range(attempts):
            if not sites:
                return
            cands = []
            for a in sites:
                cov = covering_sams(state, a) if who == "blue" else []
                if any(x.variant not in ESCORTABLE for x in cov):
                    continue
                cands.append((a, SUPPLY_ROUND_P["escorted" if cov else "open"], a.value))
            if not cands:
                return
            a, p, _v = rng.choices(cands, weights=[c[2] for c in cands])[0]
            if rng.random() < p * p_scale:
                a.health = max(0.0, a.health - SUPPLY_ROUND_HIT)
                lines.append(f"{'Our' if who == 'red' else 'Enemy'} {a.name} was hit in the background supply strikes ({a.health:.0%} left)")
    pick(list(state.assets.values()), SUPPLY_ROUND_BLUE, "blue")
    pick(list(getattr(state, "blue_assets", {}).values()), 1 + int(rng.random() < getattr(d, "raid_rate", 0.3)), "red")
    return lines


def _move_sites(state, ids, to_blue: bool) -> None:
    src, dst = (state.assets, state.blue_assets) if to_blue else (state.blue_assets, state.assets)
    for i in ids:
        a = src.pop(i, None)
        if a is not None:
            dst[i] = a


def capture_sites(state, base_id: str, ids) -> list:
    """The supply sites of a fallen base change sides with their stock (no fade). `ids` are the sites to move; remembered under the base so a retake moves them back."""
    g = state.ground
    red_base = base_id.startswith("ab_")
    ids = [i for i in ids if i in (state.assets if red_base else state.blue_assets)]
    if not ids:
        return []
    g.setdefault("capt", {})[base_id] = ids
    _move_sites(state, ids, to_blue=red_base)
    names = ", ".join((state.blue_assets if red_base else state.assets)[i].name for i in ids)
    return [f"   captured with their stock: {names}"]


def release_sites(state, base_id: str) -> list:
    g = state.ground
    ids = (g.get("capt") or {}).pop(base_id, [])
    red_base = base_id.startswith("ab_")
    ids = [i for i in ids if i in (state.blue_assets if red_base else state.assets)]
    if not ids:
        return []
    _move_sites(state, ids, to_blue=not red_base)
    return [f"   its supply sites are back under {'enemy' if red_base else 'friendly'} control"]


def _control(r: float, b: float) -> float:
    return (b - r) / (b + r) if b + r > 0 else 0.0


def _path(g) -> list:
    """Cumulative distance (m) along the line of zone centres."""
    c, out, t = g["centers"], [0.0], 0.0
    for i in range(1, len(c)):
        t += math.hypot(c[i][0] - c[i - 1][0], c[i][1] - c[i - 1][1])
        out.append(t)
    return out


def line_km(g, red=None, blue=None) -> float:
    """Where the line stands, in km along the line of zone centres (0 = at the first zone's centre; larger = Red has pushed further toward our side)."""
    red, blue = red or g["red"], blue or g["blue"]
    path, n = _path(g), len(red)
    ctl = [_control(red[i], blue[i]) for i in range(n)]
    for i in range(n):
        if ctl[i] > 0:
            if i == 0:
                return 0.0
            c0, c1 = ctl[i - 1], ctl[i]
            f = (-c0) / (c1 - c0) if c1 != c0 else 0.5
            return (path[i - 1] + (path[i] - path[i - 1]) * max(0.0, min(1.0, f))) / 1000.0
    return path[-1] / 1000.0


def line_xy(g) -> tuple:
    """DCS position of the line (on the line of zone centres)."""
    km, path, c = g.get("line_km", line_km(g)) * 1000.0, _path(g), g["centers"]
    for i in range(1, len(c)):
        if km <= path[i]:
            f = (km - path[i - 1]) / max(1.0, path[i] - path[i - 1])
            return tuple(_lerp(c[i - 1], c[i], max(0.0, min(1.0, f))))
    return tuple(c[-1])


# ---- the daily fight ------------------------------------------------------------------------------------------------------------
def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def resolve_day(state, d, rng) -> list:
    """One day of ground fighting. Returns the overnight lines for the log."""
    g = state.ground
    pull(state)
    red, blue, n = g["red"], g["blue"], n_zones(g)
    sr, sb = supply(state, "red"), supply(state, "blue")
    lines = _counter_arrives(state)
    forced = _forced_zone(state)
    fw = g.setdefault("fwd", {"r": [1.0] * n, "b": [1.0] * n})
    for key, side, force in (("r", "red", red), ("b", "blue", blue)):
        for i in range(n):
            h = fwd_health(state, side, i)
            drop = fw[key][i] - h
            if drop > 0.01 and force[i] > 0:                    # a garrison lost since yesterday takes its share of the sector's force with it
                force[i] = max(0.0, force[i] * (1.0 - FWD_SHARE * min(1.0, drop)))
            fw[key][i] = h
    for _ in range(AI_CAS.get(getattr(d, "level", 3), 2)):  # v0.41.143: blue's own air (the AI flights nobody flies) works the red sector that faces us
        facing = [i for i in range(n) if red[i] >= MIN_FORCE and (blue[i] >= MIN_FORCE or (i + 1 < n and blue[i + 1] >= MIN_FORCE))]
        if facing and rng.random() < AI_CAS_P:
            i = max(facing)
            red[i] = max(0.0, red[i] * (1.0 - AI_CAS_CUT))
    # who is in contact: a sector both sides hold, or (v0.41.143) two neighbouring sectors, red's on the enemy side, when neither is shared: an assault across the line
    pairs = [(i, i) for i in range(n) if red[i] >= MIN_FORCE and blue[i] >= MIN_FORCE]
    pairs += [(i, i + 1) for i in range(n - 1) if red[i] >= MIN_FORCE and blue[i + 1] >= MIN_FORCE and blue[i] < MIN_FORCE and red[i + 1] < MIN_FORCE]
    for ri, bi in pairs:
        R, B = red[ri], blue[bi]
        if R < MIN_FORCE or B < MIN_FORCE:                                              # an earlier fight today moved them
            continue
        quiet = ri != bi                                                                # across the line: nothing happens unless one side attacks
        pR, pB = R * sr, B * sb
        att = None
        if forced == ri and not quiet:                                                  # the enemy's last counter-force presses every day
            att = "red"
        elif state.day >= g.get("red_clock", 0) and rng.random() < getattr(d, "red_attack", 0.3) * _clamp(pR / max(pB, 1.0), 0.4, 1.6):
            att = "red"
        elif state.day >= g.get("clock", 0) and B >= BLUE_ATTACK_MIN and pB >= BLUE_ATTACK_RATIO * pR and rng.random() < BLUE_ATTACK_CHANCE:
            att = "blue"                                                                # v0.41.143: our force is ready (takeover clock over, enough strength)
        if quiet and not att:
            continue
        inten = ATTACK if att else SKIRMISH
        ur, ub = rng.uniform(0.8, 1.2), rng.uniform(0.8, 1.2)
        kr = 1.1 if att == "red" else 0.9 if att == "blue" else 1.0         # the attacker pays a little more
        kb = 1.1 if att == "blue" else 0.9 if att == "red" else 1.0
        red[ri] = max(0.0, R - min(R, inten * pB * kr * ur))
        blue[bi] = max(0.0, B - min(B, inten * pR * kb * ub))
        name = g["names"][ri]
        if att:
            a_is_red = att == "red"
            pa = (red[ri] * sr) if a_is_red else (blue[bi] * sb)
            dh = fwd_health(state, "blue", bi) if a_is_red else fwd_health(state, "red", ri)       # a standing forward garrison strengthens the defence (v0.41.102)
            pd = (DEFENDER + FWD_EXTRA * dh) * ((blue[bi] * sb) if a_is_red else (red[ri] * sr))
            if pa > DECISIVE * pd:
                if a_is_red:
                    _rout(g, bi, "blue"); _advance(g, ri, "red")
                else:
                    _rout(g, ri, "red"); _advance(g, bi, "blue")
                lines.append(f"{name}: {'Enemy' if a_is_red else 'Friendly'} forces attacked and broke the other side; the survivors fell back")
            elif pa < REPULSED * pd:
                if a_is_red:
                    red[ri] *= 0.85
                else:
                    blue[bi] *= 0.85
                lines.append(f"{name}: {'Enemy' if a_is_red else 'Friendly'} forces attacked and were thrown back")
            else:
                lines.append(f"{name}: {'Enemy' if a_is_red else 'Friendly'} forces attacked, heavy fighting (enemy {red[ri]:.0f}, friendly {blue[bi]:.0f})")
    for i in range(n):                                  # a remnant too small to hold ground withdraws
        if red[i] < MIN_FORCE and red[i] > 0 and blue[i] >= MIN_FORCE:
            _fall_back(g, i, "red")
        if blue[i] < MIN_FORCE and blue[i] > 0 and red[i] >= MIN_FORCE:
            _fall_back(g, i, "blue")
    for i in range(n):                                  # nobody holds this zone any more: whoever is next to it moves in (Red from the front side)
        if red[i] < MIN_FORCE and blue[i] < MIN_FORCE:
            if i > 0 and red[i - 1] >= MIN_FORCE and not (i + 1 < n and blue[i + 1] >= MIN_FORCE and rng.random() < 0.5):
                _advance(g, i - 1, "red")
            elif i + 1 < n and blue[i + 1] >= MIN_FORCE and state.day >= g.get("clock", 0):      # v0.41.143: not during the takeover clock
                _advance(g, i + 1, "blue")
    lines += _check_red_bases(state)                     # v0.41.143: a base is taken (or retaken) on the state of the sectors before the day's reinforcements arrive
    # reinforcements arrive at the zone in contact: Red's front-most zone, Blue's front-most (lowest-numbered) zone
    rz = max((i for i in range(n) if red[i] >= MIN_FORCE), default=None)
    bz = min((i for i in range(n) if blue[i] >= MIN_FORCE), default=n - 1)
    if rz is not None:                                   # red with no organised force anywhere gets none (its last counter-force is the only way back)
        red[rz] = min(MAX_FORCE, red[rz] + getattr(d, "red_reinf", 5.0) * sr)
    blue[bz] = min(MAX_FORCE, blue[bz] + getattr(d, "blue_reinf", 5.0) * sb)
    for i in range(n):                                   # a lost red forward garrison is re-established where red still holds the sector (blue's come back through rebuild_blue)
        a = state.assets.get(fwd_id("red", i))
        if a is not None and a.health <= 0.05 and red[i] >= MIN_FORCE and rng.random() < FWD_REBUILD * sr:
            a.health = 0.4
            fw["r"][i] = 0.4
            lines.append(f"{g['names'][i]}: Enemy forces dug in a new forward position")
    km0 = g.get("line_km", 0.0)
    g["line_km"] = line_km(g)
    if abs(g["line_km"] - km0) >= 1.0:
        lines.append(f"The front line moved {abs(g['line_km'] - km0):.0f} km {'toward our airfields' if g['line_km'] > km0 else 'back toward the enemy'}")
    lines += check_falls(state)
    lines += _update_win(state)
    push(state)
    return lines


def _rout(g, i, loser: str) -> None:
    key, step = ("blue", 1) if loser == "blue" else ("red", -1)
    left = g[key][i]
    g[key][i] = 0.0
    j = i + step
    if 0 <= j < n_zones(g):
        g[key][j] = min(MAX_FORCE, g[key][j] + RETREAT_SHARE * left)


def _fall_back(g, i, side: str) -> None:
    _rout(g, i, side)


DEFENDER = 1.25              # ground and prepared positions favour whoever is attacked
ADVANCE_SHARE = 0.4           # the winner of a battle (or the side next to an empty zone) moves this share of its force forward


def _advance(g, i: int, winner: str) -> None:
    """The winning side pushes part of its force into the next zone toward the enemy, where the beaten force fell back to."""
    key, step = ("red", 1) if winner == "red" else ("blue", -1)
    j = i + step
    if 0 <= j < n_zones(g) and g[key][i] >= MIN_FORCE:
        move = ADVANCE_SHARE * g[key][i]
        g[key][i] -= move
        g[key][j] = min(MAX_FORCE, g[key][j] + move)


def check_falls(state) -> list:
    """A field falls while Red holds the zone next to it (and Blue has nothing there); it is retaken when Blue holds the zone again."""
    g, lines = state.ground, []
    for k, bid in g.get("fall", {}).items():
        i = int(k)
        if i >= n_zones(g) or bid not in state.bases:
            continue
        held = g["red"][i] >= MIN_FORCE and g["blue"][i] < MIN_FORCE
        if held and bid not in g["fallen"]:
            g["fallen"].append(bid)
            lines += apply_fall(state, bid)
            lines += capture_sites(state, bid, [f"bfuel_{bid}"])
        elif not held and bid in g["fallen"] and g["blue"][i] >= MIN_FORCE:
            g["fallen"].remove(bid)
            release_sites(state, bid)
            lines.append(f"{state.bases[bid].name} is back in our hands, with its defences gone; the squadrons stay where they moved")
    return lines


def _base_zone(g, rid: str):
    return next((rb["zone"] for rb in g.get("rbases", []) if rb["id"] == rid), None)


def _counter_arrives(state) -> list:
    """The enemy's last counter-force: it arrives COUNTER_DELAY_DAYS after the final base fell, in the sector in front of that base, and presses every
    day for COUNTER_FORCED_DAYS. If red has retaken the base by then, the try is spent."""
    g, c = state.ground, state.ground.get("counter")
    if not c or c.get("arrived"):
        return []
    if state.day < c["arrive"]:
        return []
    c["arrived"] = True
    cid = g.get("counter_id", "")
    i = _base_zone(g, cid)
    if cid not in g["taken"] or i is None:
        c["used"] = True
        return []
    g["red"][i] = min(MAX_FORCE, g["red"][i] + MAX_FORCE * c["frac"])
    c["until"] = state.day + COUNTER_FORCED_DAYS
    rb = next(r for r in g["rbases"] if r["id"] == cid)
    return [f"{rb['name']}: the enemy counter-force has arrived and is attacking"]


def _forced_zone(state):
    g, c = state.ground, state.ground.get("counter")
    if not c or not c.get("arrived") or c.get("resolved") or c.get("used") or state.day > c.get("until", -1):
        return None
    return _base_zone(g, g.get("counter_id", ""))


def _check_red_bases(state) -> list:
    """A red base falls while we hold the sector on our side of it and the enemy has nothing there; it is retaken when the enemy holds that sector again."""
    g, lines = state.ground, []
    for rb in g.get("rbases", []):
        i, rid = rb["zone"], rb["id"]
        ours = g["blue"][i] >= MIN_FORCE and g["red"][i] < MIN_FORCE
        theirs = g["red"][i] >= MIN_FORCE and g["blue"][i] < MIN_FORCE
        if rid not in g["taken"] and ours:
            g["taken"].append(rid)
            g["taken_day"][rid] = state.day
            g["clock"] = state.day + CLOCK_DAYS
            g["red_clock"] = state.day + RED_CLOCK_DAYS
            lines.append(f"{rb['name'].upper()} HAS FALLEN: our forces hold it. The next push waits for the takeover ({CLOCK_DAYS} days)")
            lines += apply_red_fall(state, rb)
            c = g.get("counter")
            if rid == g.get("counter_id") and c is None:
                g["counter"] = {"arrive": state.day + COUNTER_DELAY_DAYS, "frac": COUNTER_FRAC.get(int(state.level), 0.0), "arrived": False}
            elif c is not None and c.get("used"):
                c["resolved"] = True                                        # the one try is spent: retaking the base ends it
        elif rid in g["taken"] and theirs:
            g["taken"].remove(rid)
            g["taken_day"].pop(rid, None)
            a = state.assets.get(rid)
            if a is not None:
                a.health = max(a.health, 0.5)
            release_sites(state, rid)
            c = g.get("counter")
            if c is not None and rid == g.get("counter_id"):
                c["used"] = True
            lines.append(f"{rb['name']} has been retaken by the enemy")
    return lines


def _update_win(state) -> list:
    """Victory is by ground only. A level with no counter-force wins when its victory bases are ours; with one, when the counter-force has been beaten."""
    g = state.ground
    if g.get("won") or not g.get("victory_ids"):
        return []
    if not all(x in g["taken"] for x in g["victory_ids"]):
        return []
    c = g.get("counter")
    if g.get("counter_id"):
        if c is None:
            return []
        if not c.get("resolved"):
            i = _base_zone(g, g["counter_id"])
            if c.get("arrived") and not c.get("used") and i is not None and g["red"][i] < MIN_FORCE and g["blue"][i] >= MIN_FORCE:
                c["resolved"] = True
            elif not c.get("resolved"):
                return []
    g["won"] = True
    return ["The last objective is ours and nothing is left to stop us"]


def victory(state) -> bool:
    return bool(active(state) and state.ground.get("won"))


def apply_red_fall(state, rb) -> list:
    """A red base falls to us: the field and everything dug in round it go down for good, and its jets withdraw to the nearest standing red field
    (FALL_LOSS of them lost on the way), the way our own squadrons do when one of our fields falls. Its depots and fuel farms change sides with their
    stock (v0.41.144); command posts are left alone. Nothing happens to an asset the level does not have (Level 1 has no field at Gudauta)."""
    rid = rb["id"]
    key = rid[3:] if rid.startswith("ab_") else rid
    lines = []
    fa = state.assets.get(rid)
    if fa is not None:
        fa.health = 0.0
    for a in state.assets.values():
        if a.kind in (AssetKind.SAM, AssetKind.EWR) and (a.id.startswith(f"sam_{key}_") or a.id.startswith(f"ewr_{key}") or a.id.startswith(f"fsam_{key}")):
            a.health = 0.0
        elif a.kind == AssetKind.ARMOR and a.variant == "GARRISON" and a.id.startswith(f"gar_{key}_"):
            a.health = 0.0
    lines += capture_sites(state, rid, [a.id for a in state.assets.values() if a.kind in SUPPLY_KINDS and a.id.endswith("_" + key)])      # v0.41.144: depots and fuel change sides with their stock
    w = state.enemy_air_at(rid)
    if w is not None and w.sqns:
        dests = [x for x in state.enemy_air if x is not w and not state.assets[x.base_asset_id].destroyed]
        fx, fy = rb["x"], rb["y"]
        dest = min(dests, key=lambda x: (state.assets[x.base_asset_id].x - fx) ** 2 + (state.assets[x.base_asset_id].y - fy) ** 2) if dests else None
        total = sum(q.available + q.reserve for q in w.sqns)
        if dest is None:
            w.sqns.clear(); w.squadrons = 0
            lines.append(f"   the {total} enemy aircraft there are lost")
        else:
            lost = 0
            for q in list(w.sqns):
                k = int(round(q.available * FALL_LOSS))
                q.available = max(0, q.available - k); lost += k
                w.sqns.remove(q); dest.sqns.append(q)
            w.squadrons = len(w.sqns); dest.squadrons = len(dest.sqns)
            lines.append(f"   its squadrons withdraw to {state.assets[dest.base_asset_id].name}, {lost} aircraft lost")
    return lines


def apply_fall(state, bid: str) -> list:
    b = state.bases[bid]
    from . import sams
    sams.set_field(state, b, 0.0)
    others = [x for x in state.bases.values() if x.kind.value == "AIRFIELD" and x.id != bid and x.id not in state.ground["fallen"]]
    lines = [f"{b.name} HAS FALLEN: the front reached it. Its defences are gone"]
    if not others:
        return lines
    for sq in state.squadrons.values():
        if sq.base_id != bid:
            continue
        dest = min(others, key=lambda x: (x.x - b.x) ** 2 + (x.y - b.y) ** 2)
        lost = int(round(sq.available * FALL_LOSS))
        sq.available = max(0, sq.available - lost)
        sq.base_id = dest.id
        lines.append(f"   {sq.name} withdraws to {dest.name}, {lost} aircraft lost")
    return lines


def fallen_count(state) -> int:
    return len(state.ground.get("fallen", [])) if active(state) else 0


def repair_blue(state, d) -> None:
    for a in getattr(state, "blue_assets", {}).values():
        if a.kind in SUPPLY_KINDS:                                      # v0.41.144: supply sites mend on their own timer (supply_repair)
            continue
        if 0 < a.health < 1.0:
            a.health = min(1.0, a.health + d.asset_repair)


# ---- hooks from the debrief and the abstract resolution ----------------------------------------------------------------------
def column_health(state, a, before: float, frac: float) -> float:
    """New health of a Red column after a flown sortie. The visible column is the lead element: the zone takes AIR_EFFECT of its losses."""
    if zone_of(state, a.id) is None:
        return max(0.0, min(before, frac))
    return max(0.0, before - (before - min(before, frac)) * AIR_EFFECT)


def blue_losses(state, asset_id: str, dead: int, total: int):
    """The friendly task force at a column's JTAC took losses: the zone's Blue strength drops. Returns a log line or None (no ground war)."""
    i = zone_of(state, asset_id)
    if i is None or total <= 0:
        return None
    g = state.ground
    g["blue"][i] = max(0.0, g["blue"][i] - BLUE_LOSS * dead / total)
    return f"{g['names'][i]}: friendly strength now {g['blue'][i]:.0f}"


def summary(state) -> list:
    """Lines for the GUI and the briefing: one per sector, then the line."""
    g = state.ground
    out = []
    for i in range(n_zones(g)):
        r, b = red_strength(state, i), blue_strength(state, i)
        tag = "contested" if (r >= MIN_FORCE and b >= MIN_FORCE) else ("enemy holds" if r >= MIN_FORCE else "friendly holds" if b >= MIN_FORCE else "empty")
        out.append(f"{g['names'][i]}: enemy {r:.0f} | friendly {b:.0f}  ({tag})")
    if g.get("fallen"):
        out.append("FALLEN: " + ", ".join(state.bases[x].name for x in g["fallen"] if x in state.bases))
    if g.get("rbases"):
        out.append("TAKEN: " + (", ".join(rb["name"] for rb in g["rbases"] if rb["id"] in g["taken"]) or "none yet"))
    return out
