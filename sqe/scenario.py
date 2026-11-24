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
from .aircraft import AIRCRAFT, era_aircraft
from . import ground, redroster, theatres, story, samtier, f117
from . import bombers as _bombers_mod
from . import clock as clock_mod
from . import sams as _sams_mod
from . import sites as _sites_mod
from . import road_sites as _road_sites_mod
from . import works as _works_mod

# S150: the sort keys this module uses (they were lambdas)
def _squadron_id(squadron):
    return squadron.id


def THEATRES() -> dict:
    """{id: name} of the installed theatre packs."""
    return theatres.available()


SAM_LABEL = {"SA-8": "SA-8 battery", "AAA": "AAA battery", "MANPAD": "MANPADS team", "SA-2": "SA-2 site", "SA-3": "SA-3 site",
             "SA-6": "SA-6 site", "SA-11": "SA-11 site", "SA-10": "SA-10 site", "SA-15": "SA-15 battery",
             "SA-19": "SA-19 battery", "SA-5": "SA-5 site", "SA-9": "SA-9 battery"}
LONG_RANGE = samtier.GATE_VARIANTS      # the deep, doctrinally placed sites (S90 P4: the theatre pack's `sam_tier` gate list; the Caucasus default is SA-2 / 3 / 6 / 10 / 11)
SAM_VALUE = {"SA-8": 4, "AAA": 2, "MANPAD": 2, "SA-2": 5, "SA-3": 5, "SA-6": 6, "SA-11": 7, "SA-10": 9, "SA-15": 6, "SA-19": 5, "SA-5": 8, "SA-9": 3}


def _size(count: int, scale: float) -> int:
    """A squadron's authorized strength at a level's friendly_scale (blue is flat since v0.41.353: 1.0 at every level, so the pack's count stands)."""
    return max(4, int(round(count * scale / 2) * 2))


_TERRAIN: dict = {}


def _pack_terrain(th: dict):
    """A pydcs terrain object for a theatre pack, kept (building one is slow) and independent of the ACTIVE theatre (the New Campaign dialog runs before one is chosen)."""
    key = th["dcs_terrain"]
    if key not in _TERRAIN:
        from dcs import terrain as T
        _TERRAIN[key] = getattr(T, key)()
    return _TERRAIN[key]


def placement(th: dict, level: int = 2, player_squadron: str | None = None, terrain=None) -> dict:
    """{squadron id: field id} for a new campaign on theatre pack `th` at `level`: where every squadron of the pack really sits (v0.41.353, queue S6, XO 2026-11-09 option (b)).
    Each squadron, the player's included, is placed on a field that can park it: its pack field when it fits, else the nearest non-divert field with room (the type's DCS parking count, shared
    by every squadron there at authorized strength). The player's squadron goes first so it keeps its field when it fits, then the rest by id. A carrier squadron stays on the boat.
    `new_campaign` and the New Campaign dialog (`squadron_options`) both read it, so the dialog shows the field the campaign will use."""
    from .models import BaseKind as _BK
    terrain = terrain if terrain is not None else _pack_terrain(th)
    sc = get_difficulty(level).friendly_scale
    fields = {f["id"]: f for f in th["blue_fields"] if not f.get("divert")}
    pos = {}
    for f in th["blue_fields"]:
        try:
            pp = terrain.airports[f["airport"]].position
            pos[f["id"]] = (pp.x, pp.y)
        except Exception:
            pos[f["id"]] = (0.0, 0.0)
    out, used = {}, {}
    def player_first_then_id(q):
        return (q["id"] != player_squadron, q["id"])
    order = sorted(th["squadrons"], key=player_first_then_id)
    for q in order:
        cnt = _size(q["count"], sc)
        if q["base"] not in fields:                                   # the carrier (or a field the pack did not list): where the pack puts it
            out[q["id"]] = q["base"]
            continue
        cls = AIRCRAFT[q["aircraft"]].dcs_class
        def room(fid):
            cap = _slots(terrain, fields[fid]["airport"], [cls])
            return None if cap is None else cap - used.get(fid, 0)
        r = room(q["base"])
        if r is None or r >= cnt:
            out[q["id"]] = q["base"]
            used[q["base"]] = used.get(q["base"], 0) + cnt
            continue
        bx, by = pos[q["base"]]
        def distance_to_pack_base(fid):
            return math.hypot(pos[fid][0] - bx, pos[fid][1] - by)
        alt = sorted((fid for fid in fields if fid != q["base"] and (room(fid) or 0) >= cnt), key=distance_to_pack_base)
        dest = alt[0] if alt else q["base"]                           # nowhere with room: it stays (and the caller reports it)
        out[q["id"]] = dest
        used[dest] = used.get(dest, 0) + cnt
    return out


def squadron_options(aircraft: str, theatre: str = "caucasus", level: int = 2, a10_variant: str | None = None, f14_variant: str | None = None) -> list:
    """(id, label) for the New Campaign squadron picker: the REAL field of each squadron (`placement`). A HAVCAP squadron is AI only and is not offered (XO: a guard is not a job type)."""
    th = theatres.load(theatre)
    names = {th["carrier"]["id"]: th["carrier"].get("short", th["carrier"]["name"]), **{f["id"]: f["name"].replace(" AB", "") for f in th["blue_fields"]}}
    sc = get_difficulty(level).friendly_scale
    out = []
    for q in th["squadrons"]:
        if era_aircraft(q["aircraft"], a10_variant, f14_variant) != aircraft or q.get("role") == "havcap":      # S103b: a slot the pack gives to an A-10 flies the campaign's A-10 variant
            continue
        where = placement(th, level, q["id"])[q["id"]]                  # this squadron as the player's: it is placed first
        out.append((q["id"], f"{q['name']}  -  {_size(q['count'], sc)} aircraft at {names.get(where, where)}"))
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
    def in_pair(a):
        return a.id in pair
    for a in sorted(st.assets.values(), key=in_pair):          # parents first
        if _sites_mod.on_spot(a.x, a.y):
            continue                                                      # sits on a condensed site spot (sites.py): dry, flat ground, kept 500 m off the sea
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


def _disperse_blue(st, th: dict, terrain, player_squadron=None) -> None:
    """Move the squadrons whose pack field cannot park them to the field `placement` gives them (v0.40.7: Batumi held 32 jets on 10 slots; v0.41.353: the player's squadron too)."""
    where = placement(th, st.level, player_squadron, terrain)
    for q in sorted(st.squadrons.values(), key=_squadron_id):
        dest = where.get(q.id, q.base_id)
        if dest != q.base_id:
            st.note(f"{q.name} is based at {st.bases[dest].name}: {st.bases[q.base_id].name} cannot park it.")
            q.base_id = dest


def _extra_sams(st, th: dict, d, ap, live: set, tiers: dict) -> None:
    """S90 J5: the pack's `extra_sams` ([{id, site, x/y or near + bearing + dist_m, levels, parent?, tier?, jitter_m?}]): fixed SAM sites for this level, registered like any red site (the SA-5 sites of Syria:
    the long-range tier is fixed by the theatre, not drawn per field). A site with a `parent` red field that is not in this level's roster is left out. Own random stream (only the optional `jitter_m` uses
    it), so no other draw of the campaign moves."""
    ex = [e for e in (th.get("extra_sams") or []) if d.level in e["levels"] and (not e.get("parent") or e["parent"] in live)]
    if not ex:
        return
    r = random.Random(f"{st.campaign_id}:extra_sams")
    for e in ex:
        if "x" in e:
            x, y = float(e["x"]), float(e["y"])
        else:
            p = ap(e["near"])
            x, y = _offset(p.x, p.y, float(e["bearing"]), float(e["dist_m"]))
        j = float(e.get("jitter_m", 0.0) or 0.0)
        if j > 0:
            x, y = _offset(x, y, r.uniform(0, 360), r.uniform(0, j))
        v = e["site"]
        tier = int(e.get("tier", tiers.get(e.get("parent", ""), 3)))
        st.assets[e["id"]] = EnemyAsset(e["id"], e.get("name") or f"{SAM_LABEL[v]} {e['id'][4:]}", AssetKind.SAM, x, y, 1.0, SAM_VALUE[v], [], None, v, tier, "")


OPENING_STRIKE_TEXT = "At midnight F-117A Nighthawks struck the long-range {kill} batteries: every one is down{also}."      # `{also}` (the default text only): ", along with some SA-10 sites and early-warning radars" for the `fill` kinds the pairs hit


def _opening_strike(st, th: dict, d) -> list:
    """S90 J9s: the pack's `opening_strike` ({"levels": [2, 3], "kill": "sa5", "text": optional}): before the first mission every red site of the named variant is down, as if a mission had killed it:
    health 0 (`destroyed`) and the day recorded in the SAM rebuild record (`sams.track`), so the normal rebuild rule (`sams.rebuild`: after 5 to 7 days by the Force Index, the level's `sam_rebuild` chance a day,
    half strength) brings them back, and the planner, map, debrief and Overview treat them as killed in a mission. S104d: the squadron's ready jets fly it as pairs, one per target; the pack's `fill` (SA variants
    and "EWR") names what the pairs left after the `kill` sites hit (`f117.opening_sortie`); the jets are out of `available` (returning, then in refit). Other sites stay. -> the opening war-log lines ([] when nothing happens)."""
    os_ = th.get("opening_strike")
    if not os_ or d.level not in os_["levels"]:
        return []
    want = os_["kill"].replace("-", "").lower()
    hit = [a for a in st.assets.values() if a.kind == AssetKind.SAM and a.variant.replace("-", "").lower() == want and not a.id.startswith("fsam_")]
    if not hit:
        return []
    for a in hit:
        a.health = 0.0
    _sams_mod.track(st)
    lines = f117.opening_sortie(st, os_, hit)
    if os_.get("text"):
        head = os_["text"].format(kill=hit[0].variant)
    else:
        kinds = []                                       # the other kinds the pairs hit, in the order first hit: "some SA-10 sites and early-warning radars" (no counts in the headline, XO 2026-11-19)
        for p in ((st.raids or {}).get("opening_strike") or {}).get("pairs", []):
            a = st.assets[p["target"]]
            k = "early-warning radars" if a.kind == AssetKind.EWR else SAM_LABEL.get(a.variant, a.variant) + "s"
            if a.variant != hit[0].variant and k not in kinds:
                kinds.append(k)
        head = OPENING_STRIKE_TEXT.format(kill=hit[0].variant, also=f", along with some {' and '.join(kinds)}" if kinds else "")
    return [head] + lines


def new_campaign(name: str, player_aircraft: str, level: int = 2, theatre: str = "caucasus",
                 seed: int | None = None, start_date: str | None = None, night_ops: bool = True,
                 player_squadron: str | None = None, a10_variant: str | None = None, f14_variant: str | None = None, link16: bool | None = None) -> CampaignState:
    th = theatres.use(theatre)                            # S90 J5: the theatre first: `get_difficulty` applies the pack's level_overrides
    start_date = start_date or f"{th['era']['year']}-06-12"            # S90 J7: no date given = the 12th of June of the theatre's era year (Caucasus 2006 = the old default, Syria 2000)
    d: Difficulty = get_difficulty(level)
    rng = random.Random(seed)
    t = theatres.terrain()
    def ap(n):
        return t.airports[n].position
    era = th["era"]                                       # S103a: Era Equipment, chosen at creation (None = the theatre's own era value) and saved with the campaign
    st = CampaignState(name=name, theatre=theatre, level=d.level, start_date=start_date, night_ops=night_ops,
                       start_hour=int(th.get("start_hour", clock_mod.DEFAULT_START_HOUR)), a10_variant=a10_variant or era["a10_variant"], f14_variant=f14_variant or era["f14_variant"], link16=era["link16"] if link16 is None else bool(link16))

    # ---- friendly bases ---------------------------------------------------------------------
    cv = th["carrier"]
    kb = ap(cv["from_airport"])
    cx, cy = _offset(kb.x, kb.y, cv["heading"], cv["distance_m"])
    st.bases[cv["id"]] = Base(cv["id"], cv["name"], BaseKind.CARRIER, x=cx, y=cy)
    for f in th["blue_fields"]:
        p = ap(f["airport"])
        st.bases[f["id"]] = Base(f["id"], f["name"], BaseKind.AIRFIELD, x=p.x, y=p.y, airport=f["airport"], divert=bool(f.get("divert")))

    sc = d.friendly_scale
    def n(base):
        return _size(base, sc)
    # The squadron structure is in the theatre pack (`squadrons`; 272 jets in the Caucasus, the same at every level since v0.41.353). Callsigns are unique across the whole coalition (group names must never collide).
    st.squadrons = {q["id"]: Squadron(q["id"], q["name"], era_aircraft(q["aircraft"], st.a10_variant, st.f14_variant), q["base"], n(q["count"]), n(q["count"]), q["callsign"], role=q.get("role", "")) for q in th["squadrons"]}      # S103b: the slot's airframe is the campaign's A-10 / F-14 variant
    for s in st.squadrons.values():                       # sanity: land jets on land, carrier jets on the boat
        spec, base = AIRCRAFT[s.aircraft], st.bases[s.base_id]
        if spec.home != base.kind:
            raise ValueError(f"{s.name}: {spec.display} cannot be based at {base.name}")
    _disperse_blue(st, th, t, player_squadron)            # a field that cannot park its squadron (the player's too) sends it to the nearest one that can: `placement`

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
    for aid, n_ in (th.get("red_fill") or {}).get(str(d.level), {}).items():                      # v0.41.439 (S85): the level's jets per field (about 70% of its parking at L3, the rest is room for squadrons that fall back)
        if aid in cap_all:
            cap_all[aid] = n_ if not cap_all[aid] else min(cap_all[aid], n_)
    cap_hv = {aid: _slots(t, apt_of[aid], ["Su_24M", "Su_27", "MiG_31"]) for aid in ww}
    plan_r = redroster.allocate(d.level, list(ww), ww, FIELD_TIER, cap_all, cap_hv, roster=(th.get("red_roster") or {}).get(str(d.level)))          # S90 J5: the pack's roster, else redroster.ROSTERS[level]
    for aid, types in plan_r.items():
        sqns = [RedSquadron(i_, n_, t_, c_) for i_, n_, t_, c_ in redroster.cut(aid, st.assets[aid].name, types, d.red_squadron_max)]
        st.enemy_air.append(EnemyAirWing(aid, list(dict.fromkeys(q.aircraft for q in sqns)), len(sqns), sqns))

    # strategic bombers live far from the front (Mozdok in the Caucasus). B1 (XO 2026-11-21): a pack may name several bomber fields (`bomber_bases`, Syria: Damascus and Bassel Al-Assad): the level's Tu-22M3 and escort
    # counts are split between them as evenly as possible, the first field getting the extra jet (20 = 10 + 10, escorts 12 = 6 + 6); with one field (the Caucasus) it is the one squadron it was.
    bfields = [b_ for b_ in _bombers_mod.bomber_base_ids(th) if b_ in live]
    # S142 (XO 2026-11-22): the Tu-22M3 share of a field is capped at the field's DCS stand count (`_slots`; Tiyas parks none): the overflow goes to the next field in list order with room, and what no field can
    # park stays with the lead (Mozdok: 24 on 14 stands). An unknown count is uncapped. Escorts keep the even split. Syria L3: Damascus 14 + Bassel 6 Tu-22M3, 6 + 6 Su-27.
    def _split_bombers(n_: int) -> list:
        k_ = len(bfields)
        if k_ == 0:
            return []
        out_ = [n_ // k_ + (1 if i_ < n_ % k_ else 0) for i_ in range(k_)]
        caps_ = [_slots(t, apt_of[b_], ["Tu_22M3"]) if b_ in apt_of else None for b_ in bfields]
        spare_ = 0
        for i_ in range(k_):
            if caps_[i_] is not None and out_[i_] > caps_[i_]:
                spare_ += out_[i_] - caps_[i_]
                out_[i_] = caps_[i_]
        for i_ in range(k_):
            if spare_ and (caps_[i_] is None or out_[i_] < caps_[i_]):
                add_ = spare_ if caps_[i_] is None else min(spare_, caps_[i_] - out_[i_])
                out_[i_] += add_
                spare_ -= add_
        out_[0] += spare_
        return out_
    tu_share = _split_bombers(d.bomber_wing) if d.bomber_wing > 0 else []
    for bi_, bb_ in enumerate(bfields if d.bomber_wing > 0 else []):
        def share(n_):
            return n_ // len(bfields) + (1 if bi_ < n_ % len(bfields) else 0)
        bname = st.assets[bb_].name
        host = st.enemy_air_at(bb_)
        fresh = host is None                                              # a bomber field that is also a normal red field (Syria) keeps ONE wing (every lookup by field assumes it): the Tu-22M3 and escort squadrons join it, under ids of their own (`_tu`, `_tuesc`: the field's own squadrons are `_1`, `_2` ...)
        tu_sq = RedSquadron(f"{bb_}_1" if fresh else f"{bb_}_tu", f"{bname} 1" if fresh else f"{bname} Tu-22M3", "Tu_22M3", tu_share[bi_])     # one squadron a field (judgment call)
        if fresh:
            host = EnemyAirWing(bb_, ["Tu_22M3"], 1, [tu_sq])
            st.enemy_air.append(host)
        else:
            host.sqns.append(tu_sq)
            host.types = list(dict.fromkeys([*host.types, "Tu_22M3"]))
        if d.bomber_escort_wing > 0 and share(d.bomber_escort_wing) > 0:  # v0.41.106: a dedicated Su-27 escort squadron on the same field, escort-only
            host.sqns.append(RedSquadron(f"{bb_}_2" if fresh else f"{bb_}_tuesc", f"{bname} escorts", "Su_27", share(d.bomber_escort_wing), role="escort"))
            host.types = list(dict.fromkeys([*host.types, "Su_27"]))
        host.squadrons = len(host.sqns)

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

    _sites_mod.apply(st, th)                                         # v0.41.199: red's SAM sites, supply sites and columns move onto the condensed site spots
    snap_assets_to_land(st)                                          # nothing is generated in the sea
    _extra_sams(st, th, d, ap, live, FIELD_TIER)                     # S90 J5: the pack's fixed extra SAM sites (none in the Caucasus); after the snap and the site spots: they stay where the pack put them
    _works_mod.build(st, th, d)                                      # S111: the pack's `works` (Lutorin's plants; none in the Caucasus): fixed sites, after the sea check
    struck = _opening_strike(st, th, d)                              # S90 J9s: the scripted opening strike (none in the Caucasus): after every red SAM site is placed
    _road_sites_mod.build(st, th, d, {n_: (a_.position.x, a_.position.y) for n_, a_ in t.airports.items()}, rng)      # v0.41.241 (item i): supply sites along the roads, both sides (a stream of its own)
    sams = [x for x in st.assets.values() if x.kind == AssetKind.SAM]
    for x in st.assets.values():
        if x.kind in (AssetKind.SAM, AssetKind.EWR):
            continue
        x.defended_by = [s.id for s in sams if math.hypot(x.x - s.x, x.y - s.y) < 40_000]

    # ---- the player ---------------------------------------------------------------------------------------------------
    mine = [q for q in st.squadrons_for(player_aircraft) if q.role != "havcap"]          # a HAVCAP squadron is AI only
    if not mine or not AIRCRAFT[player_aircraft].player_flyable:
        raise ValueError(f"{player_aircraft} is not a player-flyable type with a squadron")
    me = next((q for q in mine if q.id == player_squadron), mine[0])
    st.player = PlayerProfile(aircraft=player_aircraft, squadron_id=me.id, callsign=me.callsign)
    st.note(f"Campaign '{name}' begins. You fly the {AIRCRAFT[player_aircraft].display} with {me.name}. {d.name}.")
    for _ln in struck:
        st.note(_ln)
    for _ln in story.beat(st, "open"):
        st.note(_ln)
    return st
