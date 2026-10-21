"""Air defence that rebuilds and moves (ground war, phase 3).

Red:
* A SAM site you destroyed is not gone for good. After REBUILD_MIN_DAYS a replacement can go up (SAM_REBUILD chance a day by level, scaled by Red's
  supply, at most REBUILD_PER_DAY a night), at REBUILT_HEALTH. It is never rebuilt at a field that is itself cratered, never behind the front,
  and the column air defence (fsam_) travels with its sector and is not rebuilt.
* A mobile site that has been hurt (SA-6, SA-11, SA-8, SA-15, SA-19) can pack up and move (SAM_SCOOT chance a night by level): a few nm, never
  further than MAX_DRIFT_NM from where it started, at most MAX_MOVES times. Its dug-in garrison, if any, goes with it. Old positions in an old
  tasking order are simply stale: the next day's order has the new one.
* A badly hurt long-range site (RETREAT_HEALTH or less) can pull back from the front to recover: overnight, with a chance that grows the worse it
  is hurt and falls with Red's supply, the site and its dug-in garrison move RETREAT_NM further from our nearest airfield. It comes back to its
  old position once it is repaired to RETURN_HEALTH (after RETURN_MIN_DAYS at least). Its ring leaves the contested ground while it is away, but it is
  still on the map and can be hit where it sits.
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
MOBILE = {"SA-6", "SA-11", "SA-8", "SA-15", "SA-19"}
HURT = 0.8                    # health at or below this is "hurt" enough to move
MAX_MOVES = 2
MAX_DRIFT_NM = 10.0
STEP_NM = (3.0, 6.0)
RETREAT_HEALTH = 0.35         # a long-range site at or below this health may pull back to recover
RETREAT_NM = (35.0, 55.0)
RETURN_HEALTH = 0.65
RETURN_MIN_DAYS = 2
BLUE_REPAIR = 0.10
# v0.41.67: SAM orders by need (XO 2026-10-21: "SAMs can be ordered by both sides should the need arise"; "move first, build if nothing to spare").
# A destroyed blue site is in need. The least-threatened field that has a standing site of the same kind (health at or above BLUE_FULL_DEF) sends it;
# it arrives ORDER_TRANSIT_DAYS later (faster than the REBUILD_MIN_DAYS of a new build), and the field it left is rebuilt by the usual rule. When no
# field has one to spare, the usual rebuild (3 days, supply) is the only way. Doctrine: JP 3-01 defended asset list (the most threatened, most valuable
# asset first); no public figures for transit time or odds, so every number here is a judgment call.
ORDER_TRANSIT_DAYS = 2
ORDER_MIN_GAP_NM = 20.0       # the sender must sit this much further from the nearest enemy fighter field than the receiver
ORDERS_PER_NIGHT = 1

# v0.41.30: every blue airfield's air defence at doctrinal strength (XO 2026-10-16: "all bases are important", red-like firepower).
# Sources: FM 44-85 App. B, a Patriot fire unit = 1 radar, 1 ECS, 1 power plant, 1 antenna mast group and 8 launching stations;
# a Phase III HAWK battery = 1 PAR, 1 CWAR, 2 HIPIR and 6 launchers (18 missiles). The 0.6 / 0.15 thresholds are the old ones (judgment calls).
BLUE_PATRIOT_LN = 8           # launchers in a full Patriot fire unit (FM 44-85; GlobalSecurity also says "up to 16" in one place)
BLUE_HAWK_LN = 6              # launchers in a HAWK battery
BLUE_HAWK_TR = 2              # HAWK tracking radars (HIPIR) per battery
BLUE_FULL_DEF = 0.6           # a field at or above this `defense` has the full set: Patriot, HAWK, two AAA sites
BLUE_MIN_DEF = 0.15           # below this, nothing is standing. Between: a reduced Patriot (launchers by `defense`), one AAA site, no HAWK
AD_RAID_WEIGHT = 4.0          # a full field's air defence counts like this many fighters against a raid in the war sim (judgment call)


# v0.41.62: blue's air defence is three sites per airfield, the same record as red's SAM assets (XO 2026-10-21: "I'd rather use red's because I think
# it's tested and it's not abstract"). They live in `state.blue_sams` (not `blue_assets`, whose loops are for supply sites and garrisons), id
# `bsam_<field>_<key>`. The site health IS the strength: `Base.defense` is only a cache of the Patriot site's health for the readers that were not
# moved (GUI bar, war-sim score), kept in step by the helpers below. Every writer goes through `shift_field` / `set_field`.
BLUE_SITES = {"pat": ("Patriot", "Patriot battery"), "hawk": ("HAWK", "HAWK battery"), "aaa": ("AAA", "AAA sites")}
BLUE_SPACING_M = 80.0         # v0.41.69: metres between the units of a blue Patriot or HAWK battery (pydcs's default is 20 m). XO's 2026-10-21 run: a Patriot launcher's
                              # launch hit the 11 units round it (all 20 m apart) and one launcher died with no enemy near. 80 m is a judgment call (no public figure found).
BLUE_SITE_VALUE = 5           # planner weight (unused until blue's sites are tasked; same default as a red garrison)


def blue_site_id(bid: str, key: str) -> str:
    return f"bsam_{bid}_{key}"


def blue_sites(state, b) -> dict:
    """{key: asset} for a blue airfield's sites, empty when it has none (a carrier)."""
    sites = getattr(state, "blue_sams", None) or {}
    out = {k: sites[blue_site_id(b.id, k)] for k in BLUE_SITES if blue_site_id(b.id, k) in sites}
    return out if len(out) == len(BLUE_SITES) else {}


def ensure_blue_sams(state) -> bool:
    """Give every blue airfield its three sites at the health its `defense` number says (a new campaign: 1.0; an older save: whatever it had), and
    keep `Base.defense` in step with the Patriot site. Returns True when it added any."""
    if not isinstance(getattr(state, "blue_sams", None), dict):
        state.blue_sams = {}
    added = False
    for b in state.bases.values():
        if b.kind.value != "AIRFIELD":
            continue
        for k, (var, label) in BLUE_SITES.items():
            sid = blue_site_id(b.id, k)
            if sid not in state.blue_sams:
                h = max(0.0, min(1.0, float(getattr(b, "defense", 1.0) or 0.0)))
                state.blue_sams[sid] = _site(sid, f"{b.name} {label}", b, var, h, state, k)
                added = True
        for k in BLUE_SITES:                       # a site made before v0.41.64 sits on the field centre: give it its place
            a = state.blue_sams[blue_site_id(b.id, k)]
            if a.x == b.x and a.y == b.y:
                a.x, a.y = place_blue_site(state, b, k)
        _sync(state, b)
    return added


def _sync(state, b) -> None:
    """`Base.defense` (the cache for the GUI bar, the war-sim score and the raid rules) = the mean health of the field's three sites."""
    sites = blue_sites(state, b)
    if sites:
        b.defense = sum(a.health for a in sites.values()) / len(sites)


# v0.41.64: where a blue site sits (XO 2026-10-21: "doctrinal, but randomness on the exact positioning so no two campaigns are the same"). The layout is the
# v0.41.7 one, which already follows the US Army air-defence employment guidelines (mutual support, overlapping fires, weighted coverage toward the likely
# air avenue, defence in depth; they give no distances, the numbers below are judgment calls): the Patriot faces the threat axis (the nearest enemy
# fighter field), the AAA sits either side to cover its dead zone, the HAWK is the outer layer. Each site gets a seeded jitter on top, fixed for the
# campaign (campaign id + field + site), so a field looks the same every day and different in the next campaign.
SITE_PLACE = {"pat": (0.0, 4500.0), "aaa": (120.0, 3500.0), "aaa2": (-120.0, 3500.0), "hawk": (50.0, 6000.0)}      # (bearing from the threat axis, metres from the field)
SITE_JITTER_DEG = 15.0
SITE_JITTER_FRAC = 0.15


def place_blue_site(state, b, key: str) -> tuple:
    """The (x, y) of blue site `key` ('pat', 'hawk', 'aaa' or the second AAA site 'aaa2') at airfield `b`: the doctrinal bearing and distance plus the
    seeded jitter, moved along nearby bearings until it is on dry land (as the old layout did)."""
    import random as _random
    from . import seacheck as seac, threatmap as tm
    axis = tm.nearest_threat_bearing(state, b.x, b.y, 0.0)
    off, dist_m = SITE_PLACE[key]
    r = _random.Random(f"{state.campaign_id}:{b.id}:{key}")
    off += r.uniform(-SITE_JITTER_DEG, SITE_JITTER_DEG)
    dist_m *= 1.0 + r.uniform(-SITE_JITTER_FRAC, SITE_JITTER_FRAC)
    for k in range(12):
        ang = math.radians(axis + off + 30 * ((k + 1) // 2) * (1 if k % 2 else -1))
        x, y = b.x + dist_m * math.cos(ang), b.y + dist_m * math.sin(ang)
        if seac.site_ok(x, y, 300.0):
            return x, y
    ang = math.radians(axis + off)
    return b.x + dist_m * math.cos(ang), b.y + dist_m * math.sin(ang)


def _site(sid, name, b, variant, health, state=None, key=None):
    from .models import EnemyAsset
    x, y = place_blue_site(state, b, key) if state is not None and key else (b.x, b.y)
    return EnemyAsset(sid, name, AssetKind.SAM, x, y, health, BLUE_SITE_VALUE, [], None, variant, 1, b.id)


def field_defence(state, b) -> float:
    """A blue field's air-defence strength, 0..1: the mean health of its three sites (the cache `Base.defense` holds the same number)."""
    ensure_blue_sams(state)
    sites = blue_sites(state, b)
    return sum(a.health for a in sites.values()) / len(sites) if sites else float(getattr(b, "defense", 0.0) or 0.0)


def shift_field(state, b, delta: float) -> None:
    """Add `delta` to every site of a blue field, kept within 0..1 (repair and a lent battery: a destroyed site is not revived by it, only rebuilt).
    A carrier has no sites: its number moves."""
    ensure_blue_sams(state)
    sites = blue_sites(state, b)
    if not sites:
        b.defense = max(0.0, min(1.0, float(b.defense) + delta))
        return
    for a in sites.values():
        if delta > 0 and a.destroyed:
            continue
        a.health = max(0.0, min(1.0, a.health + delta))
    _sync(state, b)


def set_field(state, b, value: float) -> None:
    """Set every site of a blue field to `value` (a fallen field: 0; a test)."""
    ensure_blue_sams(state)
    sites = blue_sites(state, b)
    v = max(0.0, min(1.0, float(value)))
    for a in sites.values():
        a.health = v
    _sync(state, b)


HIT_ORDER = ("hawk", "pat", "aaa")        # damage takes the outer layer first (judgment call: defence in depth, the HAWK sits furthest out at 6 km)


def hit_field(state, b, amount: float) -> list:
    """v0.41.63: damage to a blue field's air defence. `amount` is the drop in the field's mean strength (what shift_field(-amount) did to the one
    number), spread over the three sites outside-in: the HAWK goes first, then the Patriot, then the AAA. Returns the names of sites it destroyed."""
    ensure_blue_sams(state)
    sites = blue_sites(state, b)
    if not sites:
        b.defense = max(0.0, float(b.defense) - amount)
        return []
    pool, gone = amount * len(sites), []
    for k in HIT_ORDER:
        a = sites[k]
        if pool <= 0:
            break
        was = a.destroyed
        take = min(a.health, pool)
        a.health -= take; pool -= take
        if a.destroyed and not was:
            gone.append(BLUE_SITES[k][1])
    _sync(state, b)
    return gone


def blue_battery(b, state=None) -> dict:
    """v0.41.30: what stands at a blue airfield: Patriot launchers, HAWK yes/no, AAA sites. All fields alike. v0.41.62: with `state`, read from the
    field's three sites (each by its own health, the old thresholds); without it (or a field with no sites) from the field's `defense` number."""
    if getattr(b, "kind", None) is None or b.kind.value != "AIRFIELD":
        return {"patriot_ln": 0, "hawk": False, "aaa": 0}
    sites = blue_sites(state, b) if state is not None else {}
    if not sites:
        dv = float(getattr(b, "defense", 0.0) or 0.0)
        return _battery(dv, dv, dv)
    return _battery(sites["pat"].health, sites["hawk"].health, sites["aaa"].health)


def _battery(pat: float, hawk: float, aaa: float) -> dict:
    """The thresholds are v0.41.30's (BLUE_FULL_DEF / BLUE_MIN_DEF, judgment calls), now applied to each site's own health."""
    if pat < BLUE_MIN_DEF:
        ln = 0
    elif pat >= BLUE_FULL_DEF:
        ln = BLUE_PATRIOT_LN
    else:
        ln = max(2, round(BLUE_PATRIOT_LN * pat))
    return {"patriot_ln": ln, "hawk": hawk >= BLUE_FULL_DEF, "aaa": 2 if aaa >= BLUE_FULL_DEF else 1 if aaa >= BLUE_MIN_DEF else 0}


def air_defence(b, state=None) -> float:
    """v0.41.30: a field's air defence for the war sim, 0 (nothing standing) to 1 (full Patriot + HAWK), from blue_battery (v0.41.63: from the sites with `state`)."""
    bt = blue_battery(b, state)
    return min(1.0, 0.7 * bt["patriot_ln"] / BLUE_PATRIOT_LN + (0.3 if bt["hawk"] else 0.0))


def covering_ad(state, x, y, reach_nm: float = 40.0) -> float:
    """v0.41.30: the strongest blue field air defence that covers (x, y) (within reach_nm of the field: raids.PATRIOT_NM)."""
    return max([air_defence(b, state) for b in state.bases.values()
                if b.kind.value == "AIRFIELD" and math.hypot(b.x - x, b.y - y) <= reach_nm * 1852.0] + [0.0])


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
    """Remember the day each SAM site went down; forget the ones that are back up. (v0.41.63: blue's sites too.)"""
    r = _rec(state)
    for a in list(state.assets.values()) + list((getattr(state, "blue_sams", None) or {}).values()):
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
        if a is None or not a.destroyed or aid.startswith("fsam_") or state.day - day0 < REBUILD_MIN_DAYS or aid in _red_ordered(state):
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
            lines.append(f"The enemy put up a replacement {a.variant} site: {a.name} (half strength)")
    return lines


def _red_ordered(state) -> set:
    return {o["to"] for o in _rec(state).get("red_orders", [])}


def red_orders(state, d, rng: random.Random) -> list:
    """v0.41.68: red's SAM orders, the same rule as blue's (blue_orders). First the batteries that arrive today; then, at most ORDERS_PER_NIGHT, a new
    order for the shallowest-tier destroyed site that is in play (tier up to front + 2, its field still standing, value first among equals): a standing
    site of the same kind in a DEEPER tier (health BLUE_FULL_DEF or more) sends its battery; the chance is red's supply. The sender's site goes down
    (the usual rebuild takes it when its tier comes into play), the receiver is not rebuilt meanwhile. No spare, no order: sams.rebuild is the only
    way. Returns log lines."""
    from . import ground
    track(state)
    r = _rec(state)
    orders, vacated = r.setdefault("red_orders", []), r.setdefault("red_vacated", [])
    lines = []
    for o in [o for o in orders if o["due"] <= state.day]:
        orders.remove(o)
        a = state.assets.get(o["to"])
        if a is not None and (a.destroyed or a.health < o["health"]):
            a.health = max(a.health, o["health"])
            r["down"].pop(a.id, None)
            lines.append(f"A {a.variant} battery arrived to replace the loss at {a.name}")
    busy = _red_ordered(state)
    sup = ground.supply(state, "red") if ground.active(state) else 0.85
    sites = [x for x in state.assets.values() if x.kind == AssetKind.SAM and not x.id.startswith("fsam_")]
    needy = sorted((a for a in sites if a.destroyed and a.tier <= state.front + 2 and not _parent_down(state, a)
                    and a.id not in busy and a.id not in vacated), key=lambda a: (a.tier, -a.value, a.id))
    for a in needy[:ORDERS_PER_NIGHT]:
        donors = sorted((x for x in sites if x.variant == a.variant and not x.destroyed and x.health >= BLUE_FULL_DEF and x.tier > a.tier
                         and x.id not in busy and not _parent_down(state, x)), key=lambda x: (-x.tier, x.id))
        if not donors or rng.random() >= sup:
            continue
        src = donors[0]
        orders.append({"to": a.id, "from": src.id, "due": state.day + ORDER_TRANSIT_DAYS, "health": round(src.health, 2)})
        src.health = 0.0
        vacated.append(src.id)
        lines.append(f"The enemy ordered a {a.variant} battery from {src.name} to replace the loss at {a.name}")
    r["red_vacated"] = [v for v in vacated if state.assets.get(v) is not None and state.assets[v].destroyed]
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


def _long_range(state, a) -> bool:
    from . import threatmap as tm
    return (a.kind == AssetKind.SAM and not a.id.startswith("fsam_") and a.value >= 5 and tm.RANGE_NM.get(a.variant, 0) >= 10)


def _shift(state, a, dx: float, dy: float) -> None:
    a.x, a.y = a.x + dx, a.y + dy
    for g in state.assets.values():                                     # the dug-in garrison goes with it
        if g.guards == a.id:
            g.x, g.y = g.x + dx, g.y + dy


def retreat(state, d, rng: random.Random) -> list:
    """A badly hurt long-range site pulls back to recover; a recovered one returns. Returns log lines."""
    from . import ground, seacheck
    r = _rec(state)
    r.setdefault("pulled", {})
    lines = []
    for aid, rec in sorted(r["pulled"].items()):                        # first, the ones that come back
        a = state.assets.get(aid)
        if a is None or a.destroyed:
            r["pulled"].pop(aid, None)                                  # destroyed where it sat: the rebuild rule takes it from here
            continue
        if a.health >= RETURN_HEALTH and state.day - rec["day"] >= RETURN_MIN_DAYS and rng.random() < 0.5:
            hx, hy = rec["home"]
            _shift(state, a, hx - a.x, hy - a.y)
            r["pulled"].pop(aid, None)
            lines.append(f"{a.name} is back in position")
    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD"]
    if not fields:
        return lines
    sup = ground.supply(state, "red") if ground.active(state) else 0.85
    scale = float(getattr(d, "sam_retreat", 1.0))
    for a in sorted((x for x in state.assets.values() if _long_range(state, x)), key=lambda x: x.id):
        if a.destroyed or a.id in r["pulled"] or a.health > RETREAT_HEALTH:
            continue
        p = min(0.8, 0.30 + (RETREAT_HEALTH - a.health) * 1.5) * (0.6 + 0.4 * sup) * scale
        if rng.random() >= p:
            continue
        nb = min(fields, key=lambda b: math.hypot(b.x - a.x, b.y - a.y))
        away = math.atan2(a.y - nb.y, a.x - nb.x)
        step = rng.uniform(*RETREAT_NM) * NM
        for da in (0, 25, -25, 50, -50):
            ang = away + math.radians(da)
            nx, ny = seacheck.snap_to_land(a.x + step * math.cos(ang), a.y + step * math.sin(ang))
            if math.hypot(nx - a.x, ny - a.y) >= 0.6 * step:
                break
        else:
            continue
        r["pulled"][a.id] = {"home": [a.x, a.y], "day": state.day}
        moved = math.hypot(nx - a.x, ny - a.y) / NM
        _shift(state, a, nx - a.x, ny - a.y)
        lines.append(f"{a.name} ({a.health:.0%} left) pulled back about {moved:.0f} nm from the front to recover")
    return lines


def blue_defence(state, d) -> list:
    """Airfield defences repair by supply; a fallen field does not. (v0.41.67: the old "lend a battery" is gone: see blue_orders.)"""
    from . import ground
    sup = ground.supply(state, "blue") if ground.active(state) else 1.0
    fallen = set((state.ground or {}).get("fallen", []))
    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD" and b.id not in fallen]
    for b in fields:
        shift_field(state, b, BLUE_REPAIR * sup)          # every standing site; a destroyed one waits for rebuild_blue_sites
    return []


def night(state, d, rng: random.Random) -> list:
    return rebuild(state, d, rng) + relocate(state, d, rng) + retreat(state, d, rng) + blue_defence(state, d)


def _threat_nm(state, b) -> float:
    """Distance from a blue field to the nearest enemy fighter field, in nm (smaller = more threatened); 9999 when red has none."""
    from . import threatmap as tm
    fb = tm.fighter_bases(state)
    return min(math.hypot(ex - b.x, ey - b.y) for ex, ey in fb) / NM if fb else 9999.0


def _ordered(state) -> set:
    """Ids of the sites a battery is on its way to: the rebuild rule leaves them alone."""
    return {blue_site_id(o["to"], o["key"]) for o in _rec(state).get("orders", [])}


def blue_orders(state, d, rng: random.Random) -> list:
    """v0.41.67: blue's SAM orders. First the batteries that arrive today; then, at most ORDERS_PER_NIGHT, a new order for the most threatened
    field with a destroyed site: the least-threatened field with a standing site of that kind sends it (needs the supply to move it: the chance is
    blue's supply). The sender's site goes down and is rebuilt by the usual rule, and a site emptied by an order is not itself in need. Returns log lines."""
    from . import ground
    track(state)
    ensure_blue_sams(state)
    r = _rec(state)
    orders, vacated = r.setdefault("orders", []), r.setdefault("vacated", [])
    lines = []
    for o in [o for o in orders if o["due"] <= state.day]:
        orders.remove(o)
        a, b = state.blue_sams.get(blue_site_id(o["to"], o["key"])), state.bases.get(o["to"])
        if a is None or b is None:
            continue
        if a.destroyed or a.health < o["health"]:
            a.health = max(a.health, o["health"])
            r["down"].pop(a.id, None)
            _sync(state, b)
            lines.append(f"A {BLUE_SITES[o['key']][0]} battery from {o['from_name']} arrived at {b.name}")
    fallen = set((state.ground or {}).get("fallen", []))
    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD" and b.id not in fallen and blue_sites(state, b)]
    busy = _ordered(state)
    sup = ground.supply(state, "blue") if ground.active(state) else 1.0
    needy = sorted(((_threat_nm(state, b), b.id, k, b) for b in fields for k in BLUE_SITES
                    if blue_sites(state, b)[k].destroyed and blue_site_id(b.id, k) not in busy and blue_site_id(b.id, k) not in vacated),
                   key=lambda t: t[:3])
    for thr, _bid, k, b in needy[:ORDERS_PER_NIGHT]:
        donors = sorted(((_threat_nm(state, f), f.id, f) for f in fields if f.id != b.id
                         and blue_sites(state, f)[k].health >= BLUE_FULL_DEF and blue_site_id(f.id, k) not in busy
                         and _threat_nm(state, f) >= thr + ORDER_MIN_GAP_NM), key=lambda t: (-t[0], t[1]))
        if not donors or rng.random() >= sup:
            continue
        f = donors[0][2]
        src = blue_sites(state, f)[k]
        orders.append({"key": k, "to": b.id, "from": f.id, "from_name": f.name, "due": state.day + ORDER_TRANSIT_DAYS, "health": round(src.health, 2)})
        src.health = 0.0
        vacated.append(src.id)
        _sync(state, f)
        lines.append(f"A {BLUE_SITES[k][0]} battery was ordered from {f.name} to {b.name}")
    r["vacated"] = [v for v in vacated if state.blue_sams.get(v) is not None and state.blue_sams[v].destroyed]
    return lines


def rebuild_blue_sites(state, d, rng: random.Random) -> list:
    """v0.41.63: red's rebuild rule for blue's destroyed air-defence sites: after REBUILD_MIN_DAYS a replacement can go up (the level's `blue_rebuild`
    chance a night, scaled by blue's supply, at most REBUILD_PER_DAY a night) at REBUILT_HEALTH, never at a field that has fallen. Returns log lines."""
    from . import ground
    track(state)
    r = _rec(state)
    fallen = set((state.ground or {}).get("fallen", []))
    p = float(getattr(d, "blue_rebuild", 0.0)) * (ground.supply(state, "blue") if ground.active(state) else 1.0)
    busy = _ordered(state)                                                     # a battery is on its way there: no new build
    cands = sorted((a for aid, day0 in r["down"].items() for a in [state.blue_sams.get(aid)]
                    if a is not None and a.destroyed and state.day - day0 >= REBUILD_MIN_DAYS and a.guards not in fallen and aid not in busy), key=lambda a: a.id)
    rng.shuffle(cands)
    lines = []
    for a in cands:
        if len(lines) >= REBUILD_PER_DAY:
            break
        if rng.random() < p:
            a.health = REBUILT_HEALTH
            r["down"].pop(a.id, None)
            b = state.bases.get(a.guards)
            if b is not None:
                _sync(state, b)
            lines.append(f"A replacement {a.name} went up (half strength)")
    return lines


# v0.41.65: where a red site sits (XO 2026-10-21: "follow doctrine and adjust as I test"). Red's clusters used to sit at random bearings round the field.
# Now the same employment guidelines as blue's (mutual support, overlapping fires, weighted coverage toward the likely air avenue, defence in depth;
# no distances in the public text, so every number here is a judgment call): the axis is the bearing to the nearest blue base (airfield or carrier,
# where the attack comes from); the medium and long-range sites are the outer layer, the first on the axis and the next ones fanned out either side,
# at 7 km and 3 km further each (the old distances); the short-range sites (AAA, MANPADS, SA-8 / 15 / 19) sit near the field either side, to cover
# the dead zone round it. Each site gets the same seeded jitter as blue's (15 degrees, 15%), fixed for the campaign.
RED_LONG_PLACE_DEG = (0.0, 40.0, -40.0, 80.0, -80.0)
RED_LONG_BASE_M, RED_LONG_STEP_M = 7000.0, 3000.0
RED_SHORT_PLACE = ((100.0, 3500.0), (-100.0, 3500.0), (150.0, 4500.0), (-150.0, 4500.0))


def red_threat_axis(state, x: float, y: float, fallback: float = 60.0) -> float:
    """The bearing from (x, y) to the nearest blue base, airfield or carrier (where the attack on a red field comes from)."""
    bases = list(getattr(state, "bases", {}).values())
    if not bases:
        return fallback
    b = min(bases, key=lambda e: math.hypot(e.x - x, e.y - y))
    return math.degrees(math.atan2(b.y - y, b.x - x)) % 360


def place_red_site(state, field_id: str, fx: float, fy: float, long_range: bool, j: int) -> tuple:
    """The (x, y) of the j-th medium / long-range (or short-range) SAM site of red's cluster at the field (fx, fy): doctrinal bearing and distance plus
    the seeded jitter, moved along nearby bearings until it is on dry land."""
    import random as _random
    from . import seacheck as seac
    axis = red_threat_axis(state, fx, fy)
    if long_range:
        off, dist_m = RED_LONG_PLACE_DEG[j % len(RED_LONG_PLACE_DEG)], RED_LONG_BASE_M + RED_LONG_STEP_M * j
    else:
        off, dist_m = RED_SHORT_PLACE[j % len(RED_SHORT_PLACE)]
    r = _random.Random(f"{state.campaign_id}:{field_id}:{'L' if long_range else 'S'}{j}")
    off += r.uniform(-SITE_JITTER_DEG, SITE_JITTER_DEG)
    dist_m *= 1.0 + r.uniform(-SITE_JITTER_FRAC, SITE_JITTER_FRAC)
    for k in range(12):
        ang = math.radians(axis + off + 30 * ((k + 1) // 2) * (1 if k % 2 else -1))
        x, y = fx + dist_m * math.cos(ang), fy + dist_m * math.sin(ang)
        if seac.site_ok(x, y, 300.0):
            return x, y
    ang = math.radians(axis + off)
    return fx + dist_m * math.cos(ang), fy + dist_m * math.sin(ang)

