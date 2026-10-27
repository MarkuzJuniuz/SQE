"""Starting scenarios, built from the active theatre pack (sqe/data/theatres/<id>.json): airfields, squadrons, tiers, support targets.

Coordinates come from pydcs's own airport table so they stay valid. The carrier station is derived from an airfield named in the pack
(distance and heading are in the pack too).
"""
from __future__ import annotations
import math
import random
from .difficulty import Difficulty, get as get_difficulty
from .models import (Base, BaseKind, Squadron, EnemyAsset, AssetKind, EnemyAirWing, RedSquadron, PlayerProfile)
from .state import CampaignState
from .aircraft import AIRCRAFT
from . import ground, redroster, theatres
from . import sams as _sams_mod

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


def _slots(terrain, airport: str, types: list) -> int | None:
    """How many aircraft of these types the field can park: the scarcest type's DCS parking count (slots are shared). None = unknown."""
    try:
        from dcs import planes
        a = terrain.airports[airport]
        n = [len(a.free_parking_slots(getattr(planes, tp))) for tp in types if getattr(planes, tp, None) is not None]
        return min(n) if n else None
    except Exception:
        return None


def _disperse_blue(st, terrain, player_squadron=None) -> None:
    """Squadrons at an airfield that cannot park them all: the overflow squadrons (never yours) move to the nearest friendly airfield with room
    for their type (v0.40.7: Batumi held 32 jets on 10 slots)."""
    used = {}
    fields = {b.id: b for b in st.bases.values() if b.kind == BaseKind.AIRFIELD and b.airport}
    order = sorted(st.squadrons.values(), key=lambda q: (q.id != player_squadron, q.id))       # yours first: it keeps its field
    for q in order:
        b = fields.get(q.base_id)
        if b is None:
            continue
        cls = AIRCRAFT[q.aircraft].dcs_class
        def room(fb):
            cap = _slots(terrain, fb.airport, [cls])
            return None if cap is None else cap - used.get(fb.id, 0)
        r = room(b)
        if r is None or r >= q.authorized or q.id == player_squadron:
            used[b.id] = used.get(b.id, 0) + q.authorized
            continue
        alt = sorted((fb for fb in fields.values() if fb.id != b.id and (room(fb) or 0) >= q.authorized),
                     key=lambda fb: math.hypot(fb.x - b.x, fb.y - b.y))
        if alt:
            st.note(f"{q.name} is based at {alt[0].name}: {b.name} cannot park it.")
            q.base_id = alt[0].id
            used[alt[0].id] = used.get(alt[0].id, 0) + q.authorized
        else:
            used[b.id] = used.get(b.id, 0) + q.authorized


def red_squadrons(aid: str, wing_name: str, types: list, jets: int, max_size: int, pool: list | None = None, rng=None) -> list:
    """v0.41.52: cut a wing into typed squadrons. ceil(jets / max_size) squadrons, split as evenly as possible (never over max_size), one aircraft
    type each. `types` is the wing's old mixed type pool; it is kept in force so red raids as before (XO 2026-10-21: keep raid strength):
    - 2+ squadrons: the types are dealt fighter, attack, fighter, attack ... so a mixed wing keeps one of each; every wing has a fighter squadron.
    - 1 squadron, mixed pool: it flies an attack type with the chance (attack types / pool types), from `rng` (a wing of its own, no draw from the world's).
    Attack = not in ENEMY_FIGHTERS (Su-24M, Su-25)."""
    from .loadouts import ENEMY_FIGHTERS
    n = max(1, -(-jets // max(1, max_size)))                    # ceil without math
    fig = [t for t in types if t in ENEMY_FIGHTERS]
    atk = [t for t in types if t not in ENEMY_FIGHTERS]
    if n == 1 and fig and atk and rng is not None:
        order = [atk[0]] if rng.random() < len(atk) / len(types) else [fig[0]]
    elif n == 1:
        order = [(fig or atk)[0]]
    else:
        order = []
        for k in range(max(len(fig), len(atk))):
            order += fig[k:k + 1] + atk[k:k + 1]
    if not any(t in ENEMY_FIGHTERS for t in order):             # every wing keeps a fighter squadron: swap in the level's first fighter type
        fighter = next((t for t in (pool or []) if t in ENEMY_FIGHTERS), None)
        if fighter and n > 1:
            order = [fighter] + order[1:]
        elif fighter and not fig:
            order = [fighter]
    base, extra = divmod(jets, n)
    return [RedSquadron(f"{aid}_{i + 1}", f"{wing_name} {i + 1}", order[i % len(order)], base + (1 if i < extra else 0)) for i in range(n)]


def _disperse_red(st, terrain, plan_w: list) -> None:
    """[[asset id, types, count, squadrons]]: a wing bigger than its field can park keeps what fits; the rest is dispersed to the nearest
    enemy fields with room (as their aircraft). The total stays the same unless no field has room."""
    cap = {}
    for row in plan_w:
        a = st.assets[row[0]]
        c = _slots(terrain, a.airport, row[1]) if a.airport else None
        cap[row[0]] = c
    for row in sorted(plan_w, key=lambda r: -r[2]):
        c = cap[row[0]]
        if c is None or row[2] <= c:
            continue
        extra, row[2] = row[2] - max(2, c), max(2, c)
        a = st.assets[row[0]]
        for other in sorted(plan_w, key=lambda r: math.hypot(st.assets[r[0]].x - a.x, st.assets[r[0]].y - a.y)):
            if extra <= 0:
                break
            co = cap[other[0]]
            if other is row or co is None or other[2] >= co:
                continue
            k = min(extra, co - other[2])
            other[2] += k; extra -= k
            st.note(f"{k} enemy aircraft from {a.name} are dispersed to {st.assets[other[0]].name}: {a.name} cannot park them.")
        row[2] += max(0, extra)                          # nowhere to go: they stay (and spawn wherever they can)


def new_campaign(name: str, player_aircraft: str, level: int = 2, theatre: str = "caucasus",
                 seed: int | None = None, start_date: str = "2006-06-12", night_ops: bool = False,
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
    _disperse_blue(st, t, player_squadron)               # a field that cannot park its squadrons sends the overflow to the nearest one that can

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
    # v0.41.142 (Campaign Revamp Stage A3): red's jets come from the level's roster (redroster.py), not a total and random types. The old random draw per
    # field is made and dropped so the campaign's other random draws (SAM layouts and so on) stay as they were.
    for aid in ww:
        rng.sample(d.enemy_types, k=min(len(d.enemy_types), 1 + min(2, max(1, round(max(2, round(d.enemy_air_total * ww[aid] / sum(ww.values()))) / 14)))))
    apt_of = {f[0]: f[2] for f in fields}
    cap_all = {aid: _slots(t, apt_of[aid], ["MiG_29A"]) for aid in ww}
    cap_hv = {aid: _slots(t, apt_of[aid], ["Su_24M", "Su_27", "MiG_31"]) for aid in ww}
    plan_r = redroster.allocate(d.level, list(ww), ww, FIELD_TIER, cap_all, cap_hv)
    for aid, types in plan_r.items():
        sqns = [RedSquadron(i_, n_, t_, c_) for i_, n_, t_, c_ in redroster.cut(aid, st.assets[aid].name, types, d.red_squadron_max)]
        st.enemy_air.append(EnemyAirWing(aid, list(dict.fromkeys(q.aircraft for q in sqns)), len(sqns), sqns))

    if d.bomber_wing > 0 and th["bomber_base"] in live:       # strategic bombers live far from the front (Mozdok in the Caucasus)
        st.enemy_air.append(EnemyAirWing(th["bomber_base"], ["Tu_22M3"], 1,
                                         [RedSquadron(f"{th['bomber_base']}_1", f"{st.assets[th['bomber_base']].name} 1", "Tu_22M3", d.bomber_wing)]))     # one squadron (judgment call)
        if d.bomber_escort_wing > 0:                                      # v0.41.106: a dedicated Su-27 escort squadron on the same field, escort-only
            bwing = st.enemy_air[-1]
            bwing.sqns.append(RedSquadron(f"{th['bomber_base']}_2", f"{st.assets[th['bomber_base']].name} escorts", "Su_27", d.bomber_escort_wing, role="escort"))
            bwing.types = ["Tu_22M3", "Su_27"]; bwing.squadrons = len(bwing.sqns)

    # ---- air defence clusters ----------------------------------------------------------------------
    variants = d.sam_variants
    k = 0
    for aid, nm, apt, val in fields:
        p = ap(apt)
        placed = {True: 0, False: 0}                                        # sites placed so far in this cluster, by class
        for i in range(d.sam_sites_per_cluster):
            v = variants[k % len(variants)]
            k += 1
            rng.randint(-20, 20)                                            # (the old random bearing: drawn and dropped so the campaign's other random draws stay as they were)
            x, y = _sams_mod.place_red_site(st, aid, p.x, p.y, v in LONG_RANGE, placed[v in LONG_RANGE])    # v0.41.65: doctrinal place + seeded jitter (sams.py)
            placed[v in LONG_RANGE] += 1
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
    ground.build(st, th, d, rng, ap)                                # the sectors of the front, a Red column in each, Blue's supply sites
    _sams_mod.ensure_blue_sams(st)                                       # v0.41.62: blue's Patriot, HAWK and AAA sites at every airfield
    for i, v in enumerate(d.forward_sams):                          # short-range air defence travels with the column
        col = st.assets.get(f"armor_{i + 1}")
        if col is None:
            break
        sx, sy = _offset(col.x, col.y, rng.randint(0, 359), rng.randint(2200, 3600))
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
