"""Starting scenarios, built from the active theatre pack (sqe/data/theatres/<id>.json): airfields, squadrons, tiers, support targets.

Coordinates come from pydcs's own airport table so they stay valid. The carrier station is derived from an airfield named in the pack
(distance and heading are in the pack too).
"""
from __future__ import annotations
import math
import random
from .difficulty import Difficulty, get as get_difficulty
from .models import (Base, BaseKind, Squadron, EnemyAsset, AssetKind, EnemyAirWing, PlayerProfile)
from .state import CampaignState
from .aircraft import AIRCRAFT
from . import theatres

def THEATRES() -> dict:
    """{id: name} of the installed theatre packs."""
    return theatres.available()


SAM_LABEL = {"SA-8": "SA-8 battery", "AAA": "AAA battery", "MANPAD": "MANPADS team", "SA-2": "SA-2 site", "SA-3": "SA-3 site",
             "SA-6": "SA-6 site", "SA-11": "SA-11 site", "SA-10": "SA-10 site", "SA-15": "SA-15 battery",
             "SA-19": "SA-19 battery"}
LONG_RANGE = {"SA-2", "SA-3", "SA-6", "SA-10", "SA-11"}
SAM_VALUE = {"SA-8": 4, "AAA": 2, "MANPAD": 2, "SA-2": 5, "SA-3": 5, "SA-6": 6, "SA-11": 7, "SA-10": 9, "SA-15": 6, "SA-19": 5}


def squadron_options(aircraft: str, theatre: str = "caucasus") -> list:
    """(id, label) for the New Campaign squadron picker."""
    th = theatres.load(theatre)
    out = []
    for q in th["squadrons"]:
        if q["aircraft"] == aircraft:
            nm = {th["carrier"]["id"]: th["carrier"].get("short", th["carrier"]["name"]),
                  **{f["id"]: f["name"].replace(" AB", "") for f in th["blue_fields"]}}.get(q["base"], q["base"])
            out.append((q["id"], f"{q['name']}  -  {q['count']} aircraft at {nm}"))
    return out


def _offset(x, y, hdg, d):
    h = math.radians(hdg)
    return x + d * math.cos(h), y + d * math.sin(h)


def snap_assets_to_land(st) -> int:
    """Move every non-airfield enemy asset that sits in the water (or hugs the coast) to the nearest land. Garrisons and a column's air
    defence are then kept close to the site or column they belong to. Idempotent; returns how many moved."""
    from . import seacheck
    ok = seacheck.site_ok
    pair = {}
    for a in st.assets.values():
        if a.guards:
            pair[a.id] = a.guards
        elif a.id.startswith("fsam_"):
            pair[a.id] = "armor_" + a.id[5:]
    n = 0
    for a in sorted(st.assets.values(), key=lambda a: a.id in pair):          # parents first
        if a.kind == AssetKind.AIRFIELD:
            continue
        x, y = a.x, a.y
        par = st.assets.get(pair.get(a.id, ""))
        if par is not None and not (ok(x, y) and math.hypot(x - par.x, y - par.y) <= 4500):
            for r in (2500, 3200, 1900, 3800):
                cands = [(par.x + r * math.cos(math.radians(k * 30)), par.y + r * math.sin(math.radians(k * 30))) for k in range(12)]
                good = [c for c in cands if ok(*c)]
                if good:
                    x, y = good[(sum(map(ord, a.id)) + r) % len(good)]
                    break
        if not ok(x, y):
            x, y = seacheck.snap_to_land(x, y)
        if (x, y) != (a.x, a.y):
            a.x, a.y = x, y
            n += 1
    return n


def new_campaign(name: str, player_aircraft: str, level: int = 2, theatre: str = "caucasus",
                 seed: int | None = None, start_date: str = "2004-06-12", night_ops: bool = False,
                 player_squadron: str | None = None) -> CampaignState:
    d: Difficulty = get_difficulty(level)
    rng = random.Random(seed)
    th = theatres.use(theatre)
    t = theatres.terrain()
    ap = lambda n: t.airports[n].position
    st = CampaignState(name=name, theatre=theatre, level=d.level, start_date=start_date, night_ops=night_ops)

    # ---- friendly bases ---------------------------------------------------------------------
    cv = th["carrier"]
    kb = ap(cv["from_airport"])
    cx, cy = _offset(kb.x, kb.y, cv["heading"], cv["distance_m"])
    st.bases[cv["id"]] = Base(cv["id"], cv["name"], BaseKind.CARRIER, x=cx, y=cy)
    for f in th["blue_fields"]:
        p = ap(f["airport"])
        st.bases[f["id"]] = Base(f["id"], f["name"], BaseKind.AIRFIELD, x=p.x, y=p.y, airport=f["airport"])

    sc = d.friendly_scale
    n = lambda base: max(4, int(round(base * sc / 2) * 2))
    # Realistic squadron structure (about 175 jets at Level 2): two Tomcat and two Hornet squadrons on the carrier, three Viper,
    # two Eagle and two Hog squadrons ashore. Callsigns are unique across the whole coalition (group names must never collide).
    st.squadrons = {q["id"]: Squadron(q["id"], q["name"], q["aircraft"], q["base"], n(q["count"]), n(q["count"]), q["callsign"]) for q in th["squadrons"]}
    for s in st.squadrons.values():                       # sanity: land jets on land, carrier jets on the boat
        spec, base = AIRCRAFT[s.aircraft], st.bases[s.base_id]
        if spec.home != base.kind:
            raise ValueError(f"{s.name}: {spec.display} cannot be based at {base.name}")

    # ---- enemy airfields + air wings -----------------------------------------------------------
    def add(id_, name_, kind, x, y, value, apt=None, variant="", tier=1, guards=""):
        st.assets[id_] = EnemyAsset(id_, name_, kind, x, y, 1.0, value, [], apt, variant, tier, guards)

    FIELD_TIER = th["field_tier"]
    keep = th["red_keep"].get(str(d.level))
    fields = [(f["id"], f["name"], f["airport"], f["value"]) for f in th["red_fields"] if keep is None or f["id"] in keep]
    live = {f[0] for f in fields}
    for aid, nm, apt, val in fields:
        p = ap(apt)
        add(aid, nm, AssetKind.AIRFIELD, p.x, p.y, val, apt, tier=FIELD_TIER.get(aid, 3))
    ww = {k: v for k, v in th["wing_weight"].items() if k in live}
    total_w = sum(ww.values())
    for aid, w in ww.items():
        cnt = max(2, round(d.enemy_air_total * w / total_w))
        squads = max(1, round(cnt / 14))                   # several squadrons per field at the bigger levels
        types = rng.sample(d.enemy_types, k=min(len(d.enemy_types), 1 + min(2, squads)))
        st.enemy_air.append(EnemyAirWing(aid, types, cnt, cnt, squads))

    if d.bomber_wing > 0 and th["bomber_base"] in live:       # strategic bombers live far from the front (Mozdok in the Caucasus)
        st.enemy_air.append(EnemyAirWing(th["bomber_base"], ["Tu_22M3"], d.bomber_wing, d.bomber_wing))

    # ---- air defence clusters ----------------------------------------------------------------------
    variants = d.sam_variants
    k = 0
    for aid, nm, apt, val in fields:
        p = ap(apt)
        for i in range(d.sam_sites_per_cluster):
            v = variants[k % len(variants)]
            k += 1
            x, y = _offset(p.x, p.y, (60 + 130 * i + rng.randint(-20, 20)) % 360, 7000 + 3000 * i)
            add(f"sam_{aid[3:]}_{i}", f"{nm} {SAM_LABEL[v]}", AssetKind.SAM, x, y, SAM_VALUE[v], variant=v, tier=FIELD_TIER.get(aid, 3))
            if v in LONG_RANGE and rng.random() < d.garrison_chance:       # a dug-in garrison: a reason for CAS and armour
                gx, gy = _offset(x, y, rng.randint(0, 359), rng.randint(1800, 3200))
                add(f"gar_{aid[3:]}_{i}", f"{nm} {SAM_LABEL[v]} garrison", AssetKind.ARMOR, gx, gy, 5, variant="GARRISON",
                    tier=FIELD_TIER.get(aid, 3), guards=f"sam_{aid[3:]}_{i}")
        if d.iads > 0.3 and val >= 7:
            x, y = _offset(p.x, p.y, 20 + rng.randint(0, 80), 14000)
            add(f"ewr_{aid[3:]}", f"{nm} early-warning radar", AssetKind.EWR, x, y, 4,
                variant="EWR55" if d.level >= 3 else "EWR", tier=FIELD_TIER.get(aid, 3))

    # ---- strategic and logistics targets -------------------------------------------------------------------
    def near(apt, dx, dy):
        p = ap(apt)
        return p.x + dx, p.y + dy
    for q in th["support_targets"]:
        if q["parent"] in live:
            add(q["id"], q["name"], AssetKind[q["kind"]], *near(q["airport"], q["dx"], q["dy"]), q["value"], tier=FIELD_TIER.get(q["parent"], 3))

    # ---- the ground push toward Senaki (CAS targets) ------------------------------------------------------------
    a, b = ap(th["front"]["from_airport"]), ap(th["front"]["to_airport"])
    for i in range(d.armor_columns):
        f = 0.15 + 0.22 * i
        x, y = a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f
        add(f"armor_{i+1}", f"Armor column {chr(65 + i)}", AssetKind.ARMOR, x, y, 6 + i, variant="ARMOR", tier=1)
        if i < len(d.forward_sams):                                  # short-range air defence travels with the column
            v = d.forward_sams[i]
            sx, sy = _offset(x, y, rng.randint(0, 359), rng.randint(2200, 3600))
            add(f"fsam_{i+1}", f"Column {chr(65 + i)} {SAM_LABEL[v]}", AssetKind.SAM, sx, sy, SAM_VALUE[v], variant=v, tier=1)

    snap_assets_to_land(st)                                          # nothing is generated in the sea
    sams = [x for x in st.assets.values() if x.kind == AssetKind.SAM]
    for x in st.assets.values():
        if x.kind in (AssetKind.SAM, AssetKind.EWR):
            continue
        x.defended_by = [s.id for s in sams if math.hypot(x.x - s.x, x.y - s.y) < 40_000]

    # ---- the player ---------------------------------------------------------------------------------------------------
    mine = st.squadrons_for(player_aircraft)
    if not mine or not AIRCRAFT[player_aircraft].player_flyable:
        raise ValueError(f"{player_aircraft} is not a player-flyable type with a squadron")
    me = next((q for q in mine if q.id == player_squadron), mine[0])
    st.player = PlayerProfile(aircraft=player_aircraft, squadron_id=me.id, callsign=me.callsign)
    st.note(f"Campaign '{name}' begins. You fly the {AIRCRAFT[player_aircraft].display} with {me.name}. {d.name}.")
    return st
