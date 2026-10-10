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

Pure planning and bookkeeping, no pydcs. Positions are DCS metres (x north, y east).
"""
from __future__ import annotations
import math
from .models import AssetKind, EnemyAsset

NM = 1852.0
MIN_FORCE = 3.0               # below this a side has no organised force in the zone
MAX_FORCE = 100.0
AIR_EFFECT = 0.6              # share of a visible column's losses that its zone's strength takes (the column is only the lead element)
BLUE_LOSS = 40.0              # blue strength lost when the whole friendly task force at the JTAC is destroyed
SKIRMISH, ATTACK = 0.04, 0.14
DECISIVE, REPULSED = 1.8, 0.55
RETREAT_SHARE = 0.6           # what a routed force saves by falling back
FALL_LOSS = 0.3               # aircraft lost when a field falls and its squadrons leave
SUPPLY_FLOOR, SUPPLY_NONE = 0.55, 0.85


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


def build(state, th, d, rng, ap) -> None:
    """New campaign: the zones, the Red column in each, and Blue's facilities. `ap(name)` -> a pydcs airport position."""
    from . import seacheck
    fr = th["front"]
    pts = [ap(fr["from_airport"]), ap(fr["to_airport"])]
    leg_zones = [int(fr.get("zones", 4))]
    if fr.get("beyond"):
        pts.append(ap(fr["beyond"]))
        leg_zones.append(int(fr.get("deep_zones", 1)))
    axis = [[p.x, p.y] for p in pts]
    centers = zone_centers(axis, leg_zones)
    centers = [list(seacheck.snap_to_land(c[0], c[1])) for c in centers]
    n = len(centers)
    names = list(fr.get("zone_names") or [])
    names = [names[i] if i < len(names) else f"Sector {i + 1}" for i in range(n)]
    red0, blue0 = _initial(d, n)
    state.ground = {"v": 1, "axis": axis, "legs": leg_zones, "centers": centers, "names": names, "red": red0, "blue": blue0,
                    "fall": {str(k): v for k, v in (fr.get("fall") or {}).items()}, "fallen": [], "line_km": 0.0}
    state.ground["line_km"] = line_km(state.ground)
    # the Red column of each zone
    for i, (cx, cy) in enumerate(centers):
        state.assets[f"armor_{i + 1}"] = EnemyAsset(f"armor_{i + 1}", f"Armor column {chr(65 + i)}", AssetKind.ARMOR, cx, cy, 1.0, 6 + min(i, 2), [], None, "ARMOR", 1)
    push(state)
    build_blue_assets(state, rng, ap)


def _initial(d, n) -> tuple:
    red = list(getattr(d, "ground_red", (70, 55, 15, 0, 0)))
    blue = list(getattr(d, "ground_blue", (0, 15, 60, 70, 50)))
    pad = lambda v: (v + [0.0] * n)[:n]
    return [float(x) for x in pad(red)], [float(x) for x in pad(blue)]


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
    g = state.ground
    if g:
        c = g["centers"][min(len(g["centers"]) - 1, max(0, g["legs"][0] - 1))]
        far = g["axis"][min(1, len(g["axis"]) - 1)]
        x, y = seacheck.snap_to_land(*_lerp(c, far, 0.6))
        ba["bdepot_fwd"] = EnemyAsset("bdepot_fwd", "Forward supply depot", AssetKind.DEPOT, x, y, 1.0, 6, [], None, "", 1)
    state.blue_assets = ba


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
    return {"i": i, "name": state.ground["names"][i], "red": r, "blue": b, "contested": r >= MIN_FORCE and b >= MIN_FORCE,
            "pressure": r / (r + b) if r + b > 0 else 0.0}


def blue_scale(state, asset_id: str) -> float:
    """How big the friendly task force at this column's JTAC is, against the 1.0 it always was: from the zone's Blue strength."""
    i = zone_of(state, asset_id)
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
    """0.55 (every depot and fuel site gone) .. 1.0 (all intact). A side with no such sites at all runs at 0.85."""
    pool = state.assets.values() if side == "red" else getattr(state, "blue_assets", {}).values()
    h = facility_health(pool, (AssetKind.FUEL, AssetKind.DEPOT))
    return SUPPLY_NONE if h is None else SUPPLY_FLOOR + (1.0 - SUPPLY_FLOOR) * h


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
    lines = []
    for i in range(n):
        R, B = red[i], blue[i]
        if R >= MIN_FORCE and B >= MIN_FORCE:
            pR, pB = R * sr, B * sb
            att = None
            if rng.random() < getattr(d, "red_attack", 0.3) * _clamp(pR / max(pB, 1.0), 0.4, 1.6):
                att = "red"
            elif pB > 1.15 * pR and rng.random() < 0.5:
                att = "blue"
            inten = ATTACK if att else SKIRMISH
            ur, ub = rng.uniform(0.8, 1.2), rng.uniform(0.8, 1.2)
            kr = 1.1 if att == "red" else 0.9 if att == "blue" else 1.0         # the attacker pays a little more
            kb = 1.1 if att == "blue" else 0.9 if att == "red" else 1.0
            red[i] = max(0.0, R - min(R, inten * pB * kr * ur))
            blue[i] = max(0.0, B - min(B, inten * pR * kb * ub))
            name = g["names"][i]
            if att:
                a_is_red = att == "red"
                pa = (red[i] * sr) if a_is_red else (blue[i] * sb)
                pd = DEFENDER * ((blue[i] * sb) if a_is_red else (red[i] * sr))
                if pa > DECISIVE * pd:
                    _rout(g, i, "blue" if a_is_red else "red")
                    _advance(g, i, "red" if a_is_red else "blue")
                    lines.append(f"{name}: {'Enemy' if a_is_red else 'Friendly'} forces attacked and broke the other side; the survivors fell back")
                elif pa < REPULSED * pd:
                    if a_is_red:
                        red[i] *= 0.85
                    else:
                        blue[i] *= 0.85
                    lines.append(f"{name}: {'Enemy' if a_is_red else 'Friendly'} forces attacked and were thrown back")
                else:
                    lines.append(f"{name}: {'Enemy' if a_is_red else 'Friendly'} forces attacked, heavy fighting (enemy {red[i]:.0f}, friendly {blue[i]:.0f})")
    for i in range(n):                                  # a remnant too small to hold ground withdraws
        if red[i] < MIN_FORCE and red[i] > 0 and blue[i] >= MIN_FORCE:
            _fall_back(g, i, "red")
        if blue[i] < MIN_FORCE and blue[i] > 0 and red[i] >= MIN_FORCE:
            _fall_back(g, i, "blue")
    for i in range(n):                                  # nobody holds this zone any more: whoever is next to it moves in (Red from the front side)
        if red[i] < MIN_FORCE and blue[i] < MIN_FORCE:
            if i > 0 and red[i - 1] >= MIN_FORCE and not (i + 1 < n and blue[i + 1] >= MIN_FORCE and rng.random() < 0.5):
                _advance(g, i - 1, "red")
            elif i + 1 < n and blue[i + 1] >= MIN_FORCE:
                _advance(g, i + 1, "blue")
    # reinforcements arrive at the zone in contact: Red's front-most zone, Blue's front-most (lowest-numbered) zone
    rz = max((i for i in range(n) if red[i] >= MIN_FORCE), default=0)
    bz = min((i for i in range(n) if blue[i] >= MIN_FORCE), default=n - 1)
    red[rz] = min(MAX_FORCE, red[rz] + getattr(d, "red_reinf", 5.0) * sr)
    blue[bz] = min(MAX_FORCE, blue[bz] + getattr(d, "blue_reinf", 5.0) * sb)
    km0 = g.get("line_km", 0.0)
    g["line_km"] = line_km(g)
    if abs(g["line_km"] - km0) >= 1.0:
        lines.append(f"The front line moved {abs(g['line_km'] - km0):.0f} km {'toward our airfields' if g['line_km'] > km0 else 'back toward the enemy'}")
    lines += check_falls(state)
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
        elif not held and bid in g["fallen"] and g["blue"][i] >= MIN_FORCE:
            g["fallen"].remove(bid)
            lines.append(f"{state.bases[bid].name} is back in our hands, with its defences gone; the squadrons stay where they moved")
    return lines


def apply_fall(state, bid: str) -> list:
    b = state.bases[bid]
    b.defense = 0.0
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
    return out
