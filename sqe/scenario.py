"""Starting scenarios. Today: Caucasus (Black Sea carrier + Georgian airfields vs a fictional northern force).

Coordinates come from pydcs's own airport table so they stay valid. The carrier station is derived from
Kobuleti (100 km out to sea, due west); move it in `CARRIER_FROM` if you want it elsewhere.
"""
from __future__ import annotations
import math
import random
from .difficulty import Difficulty, get as get_difficulty
from .models import (Base, BaseKind, Squadron, EnemyAsset, AssetKind, EnemyAirWing, PlayerProfile)
from .state import CampaignState
from .aircraft import AIRCRAFT

THEATRES = {"caucasus": "Caucasus"}

# (key, display name, pydcs airport, role in the war, value)
BLUE_FIELDS = [("senaki", "Senaki-Kolkhi AB", "Senaki-Kolkhi"), ("kutaisi", "Kutaisi AB", "Kutaisi"),
               ("kobuleti", "Kobuleti AB", "Kobuleti"), ("batumi", "Batumi AB", "Batumi")]
RED_FIELDS = [("ab_sukhumi", "Sukhumi-Babushara", "Sukhumi-Babushara", 7), ("ab_gudauta", "Gudauta", "Gudauta", 8),
              ("ab_sochi", "Sochi-Adler", "Sochi-Adler", 9), ("ab_gelen", "Gelendzhik", "Gelendzhik", 5),
              ("ab_krymsk", "Krymsk", "Krymsk", 8), ("ab_maykop", "Maykop-Khanskaya", "Maykop-Khanskaya", 9),
              ("ab_nalchik", "Nalchik", "Nalchik", 6), ("ab_beslan", "Beslan", "Beslan", 6),
              ("ab_mozdok", "Mozdok", "Mozdok", 7)]
# Level 1 (insurgent): only these enemy airfields are enemy-held; every other field is neutral and never appears in the war.
RED_KEEP = {1: {"ab_sukhumi", "ab_sochi"}}
WING_WEIGHT = {"ab_sukhumi": 1, "ab_gudauta": 2, "ab_sochi": 3, "ab_krymsk": 3, "ab_maykop": 4, "ab_nalchik": 2,
               "ab_beslan": 2, "ab_gelen": 1}
SAM_LABEL = {"AAA": "AAA battery", "MANPAD": "MANPADS team", "SA-2": "SA-2 site", "SA-3": "SA-3 site",
             "SA-6": "SA-6 site", "SA-11": "SA-11 site", "SA-10": "SA-10 site", "SA-15": "SA-15 battery",
             "SA-19": "SA-19 battery"}
SAM_VALUE = {"AAA": 2, "MANPAD": 2, "SA-2": 5, "SA-3": 5, "SA-6": 6, "SA-11": 7, "SA-10": 9, "SA-15": 6, "SA-19": 5}


def _offset(x, y, hdg, d):
    h = math.radians(hdg)
    return x + d * math.cos(h), y + d * math.sin(h)


def _terrain(name: str):
    from dcs import terrain
    cls = getattr(terrain, THEATRES.get(name, ""), None)
    if cls is None:
        raise ValueError(f"unknown theatre {name!r}")
    return cls()


def new_campaign(name: str, player_aircraft: str, level: int = 2, theatre: str = "caucasus",
                 seed: int | None = None, start_date: str = "2004-06-12", night_ops: bool = False) -> CampaignState:
    d: Difficulty = get_difficulty(level)
    rng = random.Random(seed)
    t = _terrain(theatre)
    ap = lambda n: t.airports[n].position
    st = CampaignState(name=name, theatre=theatre, level=d.level, start_date=start_date, night_ops=night_ops)

    # ---- friendly bases ---------------------------------------------------------------------
    kb = ap("Kobuleti")
    cx, cy = _offset(kb.x, kb.y, 270, 100_000)
    st.bases["cvn74"] = Base("cvn74", "USS Stennis (CVN-74)", BaseKind.CARRIER, x=cx, y=cy)
    for bid, nm, apt in BLUE_FIELDS:
        p = ap(apt)
        st.bases[bid] = Base(bid, nm, BaseKind.AIRFIELD, x=p.x, y=p.y, airport=apt)

    sc = d.friendly_scale
    n = lambda base: max(4, int(round(base * sc / 2) * 2))
    st.squadrons = {s.id: s for s in [
        Squadron("vf_a", "VF-31 'Hammer'", "F-14BU", "cvn74", n(12), n(12), "Springfield"),
        Squadron("vfa_b", "VFA-37 'Tiger'", "FA-18C", "cvn74", n(12), n(12), "Hornet"),
        Squadron("fs_a", "77th FS 'Viper'", "F-16C", "senaki", n(14), n(14), "Viper"),
        Squadron("fs_b", "55th FS 'Cobra'", "F-16C", "kutaisi", n(14), n(14), "Cowboy"),
        Squadron("fs_c", "27th FS 'Eagle'", "F-15C", "kutaisi", n(12), n(12), "Enfield"),
        Squadron("as_a", "354th FS 'Hog'", "A-10C", "kobuleti", n(14), n(14), "Hawg"),
    ]}
    for s in st.squadrons.values():                       # sanity: land jets on land, carrier jets on the boat
        spec, base = AIRCRAFT[s.aircraft], st.bases[s.base_id]
        if spec.home != base.kind:
            raise ValueError(f"{s.name}: {spec.display} cannot be based at {base.name}")

    # ---- enemy airfields + air wings -----------------------------------------------------------
    def add(id_, name_, kind, x, y, value, apt=None, variant=""):
        st.assets[id_] = EnemyAsset(id_, name_, kind, x, y, 1.0, value, [], apt, variant)

    keep = RED_KEEP.get(d.level)
    fields = [f for f in RED_FIELDS if keep is None or f[0] in keep]
    live = {f[0] for f in fields}
    for aid, nm, apt, val in fields:
        p = ap(apt)
        add(aid, nm, AssetKind.AIRFIELD, p.x, p.y, val, apt)
    ww = {k: v for k, v in WING_WEIGHT.items() if k in live}
    total_w = sum(ww.values())
    for aid, w in ww.items():
        cnt = max(2, round(d.enemy_air_total * w / total_w))
        types = rng.sample(d.enemy_types, k=min(len(d.enemy_types), 2))
        st.enemy_air.append(EnemyAirWing(aid, types, cnt, cnt))

    if d.bomber_wing > 0:       # strategic bombers live far to the east, at Mozdok
        st.enemy_air.append(EnemyAirWing("ab_mozdok", ["Tu_22M3"], d.bomber_wing, d.bomber_wing))

    # ---- air defence clusters ----------------------------------------------------------------------
    variants = d.sam_variants
    k = 0
    for aid, nm, apt, val in fields:
        p = ap(apt)
        for i in range(d.sam_sites_per_cluster):
            v = variants[k % len(variants)]
            k += 1
            x, y = _offset(p.x, p.y, (60 + 130 * i + rng.randint(-20, 20)) % 360, 7000 + 3000 * i)
            add(f"sam_{aid[3:]}_{i}", f"{nm} {SAM_LABEL[v]}", AssetKind.SAM, x, y, SAM_VALUE[v], variant=v)
        if d.iads > 0.3 and val >= 7:
            x, y = _offset(p.x, p.y, 20 + rng.randint(0, 80), 14000)
            add(f"ewr_{aid[3:]}", f"{nm} early-warning radar", AssetKind.EWR, x, y, 4,
                variant="EWR55" if d.level >= 3 else "EWR")

    # ---- strategic and logistics targets -------------------------------------------------------------------
    def near(apt, dx, dy):
        p = ap(apt)
        return p.x + dx, p.y + dy
    for parent, aid, nm, kind, apt, dx, dy, val in (
            ("ab_maykop", "c2_maykop", "Southern Sector HQ (Maykop)", AssetKind.C2, "Maykop-Khanskaya", -9000, 11000, 9),
            ("ab_sochi", "c2_sochi", "Coastal Command Post (Sochi)", AssetKind.C2, "Sochi-Adler", 8000, -9000, 8),
            ("ab_krymsk", "fuel_krymsk", "Krymsk fuel depot", AssetKind.FUEL, "Krymsk", 6000, 14000, 6),
            ("ab_gudauta", "fuel_gudauta", "Gudauta fuel farm", AssetKind.FUEL, "Gudauta", -4000, 9000, 5),
            ("ab_beslan", "depot_beslan", "Beslan ammunition depot", AssetKind.DEPOT, "Beslan", 9000, 8000, 5),
            ("ab_nalchik", "depot_nalchik", "Nalchik ammunition depot", AssetKind.DEPOT, "Nalchik", -8000, 6000, 4)):
        if parent in live:
            add(aid, nm, kind, *near(apt, dx, dy), val)

    # ---- the ground push toward Senaki (CAS targets) ------------------------------------------------------------
    a, b = ap("Sukhumi-Babushara"), ap("Senaki-Kolkhi")
    for i in range(d.armor_columns):
        f = 0.15 + 0.22 * i
        x, y = a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f
        add(f"armor_{i+1}", f"Armor column {chr(65 + i)}", AssetKind.ARMOR, x, y, 6 + i, variant="ARMOR")

    sams = [x for x in st.assets.values() if x.kind == AssetKind.SAM]
    for x in st.assets.values():
        if x.kind in (AssetKind.SAM, AssetKind.EWR):
            continue
        x.defended_by = [s.id for s in sams if math.hypot(x.x - s.x, x.y - s.y) < 40_000]

    # ---- the player ---------------------------------------------------------------------------------------------------
    mine = st.squadrons_for(player_aircraft)
    if not mine or not AIRCRAFT[player_aircraft].player_flyable:
        raise ValueError(f"{player_aircraft} is not a player-flyable type with a squadron")
    st.player = PlayerProfile(aircraft=player_aircraft, squadron_id=mine[0].id, callsign=mine[0].callsign)
    st.note(f"Campaign '{name}' begins. You fly the {AIRCRAFT[player_aircraft].display} with {mine[0].name}. {d.name}.")
    return st
