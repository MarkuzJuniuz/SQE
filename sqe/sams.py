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
LEND_FROM, LEND_TO, LEND_AMOUNT = 0.80, 0.50, 0.05

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
                state.blue_sams[sid] = _site(sid, f"{b.name} {label}", b, var, h)
                added = True
        _sync(state, b)
    return added


def _sync(state, b) -> None:
    """`Base.defense` (the cache for the GUI bar, the war-sim score and the raid rules) = the mean health of the field's three sites."""
    sites = blue_sites(state, b)
    if sites:
        b.defense = sum(a.health for a in sites.values()) / len(sites)


def _site(sid, name, b, variant, health):
    from .models import EnemyAsset
    return EnemyAsset(sid, name, AssetKind.SAM, b.x, b.y, health, BLUE_SITE_VALUE, [], None, variant, 1, b.id)


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
            lines.append(f"The enemy put up a replacement {a.variant} site: {a.name} (half strength)")
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
    """Airfield defences repair by supply; a fallen field does not, and a strong field lends a battery to the weakest."""
    from . import ground
    sup = ground.supply(state, "blue") if ground.active(state) else 1.0
    fallen = set((state.ground or {}).get("fallen", []))
    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD" and b.id not in fallen]
    for b in fields:
        shift_field(state, b, BLUE_REPAIR * sup)          # every standing site; a destroyed one waits for rebuild_blue_sites
    lines = []
    if len(fields) >= 2:
        weak = min(fields, key=lambda b: (b.defense, b.id)); strong = max(fields, key=lambda b: (b.defense, b.id))
        if weak.defense < LEND_TO and strong.defense >= LEND_FROM and weak is not strong:        # `defense` = the Patriot site's health (kept in step by shift_field)
            shift_field(state, strong, -LEND_AMOUNT); shift_field(state, weak, LEND_AMOUNT)
            lines.append(f"A SAM battery moved from {strong.name} to {weak.name}")
    return lines


def night(state, d, rng: random.Random) -> list:
    return rebuild(state, d, rng) + relocate(state, d, rng) + retreat(state, d, rng) + blue_defence(state, d)


def rebuild_blue_sites(state, d, rng: random.Random) -> list:
    """v0.41.63: red's rebuild rule for blue's destroyed air-defence sites: after REBUILD_MIN_DAYS a replacement can go up (the level's `blue_rebuild`
    chance a night, scaled by blue's supply, at most REBUILD_PER_DAY a night) at REBUILT_HEALTH, never at a field that has fallen. Returns log lines."""
    from . import ground
    track(state)
    r = _rec(state)
    fallen = set((state.ground or {}).get("fallen", []))
    p = float(getattr(d, "blue_rebuild", 0.0)) * (ground.supply(state, "blue") if ground.active(state) else 1.0)
    cands = sorted((a for aid, day0 in r["down"].items() for a in [state.blue_sams.get(aid)]
                    if a is not None and a.destroyed and state.day - day0 >= REBUILD_MIN_DAYS and a.guards not in fallen), key=lambda a: a.id)
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
