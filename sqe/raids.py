"""Red raids on our airfields (ground war, phase 2).

Red plans a raid the way we plan a strike: it looks for one of OUR airfields that its bombers (Su-24M) can reach, preferring the ones nearest
its own fields and the least defended. Raids are drawn TURN by turn (v0.41.341, campaign rules plan Phase 5b): each turn has the chance `raid_rate / 12` (half of it on a night turn, RED_RAID_NIGHT)
of one; a share of them are surprises (raid_surprise):

* Every raid red plans is an ordinary "<Base/Supply/Garrison/Troop> Defense: Intercept" package in the tasking order (v0.41.304: no dice, no
  hidden emergencies); a surprise one is marked "(no warning)". If you do not take it, the war simulation settles it by odds.
* Troops in contact are the planned CAS on the sector red presses hardest (`hot_sector`).

A raid is BOOKED the turn it is drawn: its raiders, SEAD / DEAD group and escorts come off the red jets still free that turn (`redair.take_ready`: ready now, less the patrols and, for fighters, the
reaction reserve), the plan is kept in `state.raids["booked"]` (the intercept package reads it, `PackageBuilder._land_raid_plan`) and the jets go to refit at the end of the turn (`Session._red_sorties`).
Everything here is seeded from the campaign and the turn, so reopening a dialog never re-rolls anything.
"""
from __future__ import annotations
import math
import random
from .models import Objective, ObjectiveType, BaseKind, Role, AssetKind
from . import clock, redair, runways
from .loadouts import BOMBER_TYPES

NM = 1852.0
BASE_LOSS = 0.06              # airfield defence lost per bomber that gets through
RAID_PRIORITY = 8.0
RAIDERS = BOMBER_TYPES + ("Su_25",)  # (v0.41.361, Phase 10d: the Su-34 too) attack types a raid can fly (bombers for fields; Su-25s lead against troops and, since v0.41.359, supply sites)
SU25_SUPPLY = True            # v0.41.359 (campaign rules plan Phase 10c): a Su-25 pair is the first pick for a raid on an uncovered supply site; the Su-24M keeps the fields (they need its SEAD group) and is the fallback
                              # when no Su-25 wing reaches (Su-25 radius 160 nm against the Su-24M's 300). The Su-25 raid goes UNESCORTED when no blue fighter squadron can reach the site's field (`plan_raid`). Judgment call.
TEMPO_STOP_SHARE = 0.5        # v0.41.171 (XO 2026-10-28): half of the AIR tempo is added to the chance a surprise raider is stopped (+20 points at the +40 cap; judgment call)
ASSET_HIT = 0.20              # health a supply site or garrison loses per aircraft that gets through
SECTOR_HIT = 4.0              # friendly sector strength lost per aircraft that gets through
GARRISON_SHIELD = 0.25        # a field's garrison takes this share off the damage its defences would suffer
RED_RAID_NIGHT = 0.5          # v0.41.341 (plan Phase 5b): a night turn draws half the raid chance of a day turn (judgment call: red's bombers and their escorts fly less at night; XO tunes it in Phase 13)
# v0.41.345 (scaled tasking, Phase C): the raid chance follows red's free attack pairs. Source: Phase A probe 2026-11-10 (free attack pairs per turn in red_air["free"]), judgment calls
RAID_REF_PAIRS = {1: 6, 2: 39, 3: 82}      # the Phase A medians of free attack pairs a turn (L1 5 to 6.5, L2 38 to 40, L3 80 to 84): a full-strength red keeps today's tempo
RAID_MULT_MAX = 1.5                        # a red above its reference never raids more than this times the plain rate
RAID_TEMPO = {1: 1.0, 2: 1.4, 3: 1.4}      # red rises with blue's +40% (judgment call); at L3 about 2.0 a day goes to about 2.8 (the queue's "about 2.7")
TURNS_PER_DAY = clock.DAY_MIN // clock.TURN_MIN      # 12: the level's raid_rate (raids a day) is spread over the day's turns
# v0.41.355 (campaign rules plan Phase 10a): the Tu-22M3 LAND STRIKE (2 Tu-22M3 + 2 Mozdok Su-27 on a blue supply site). All judgment calls (no public figure), tuned on the 40-day cadence runs.
TU22 = "Tu_22M3"
TU_STRIKE_TEMPO = 1.5         # the per-turn chance is the level's land-strike cap a day x this / 12, so most days reach the cap (`bombers.LAND_STRIKES_PER_DAY`)
TU_HIT_EQUIV = 2.0            # aircraft-equivalents one Tu-22M3 that gets through puts on a supply site: it drops four racks of nine OFAB-250 (about 9 t) against a Su-24M's two or three tonnes, but the bombs beyond the first
                              # few fall on rubble (`eff` already halves them past four); two Tu-22M3 through = 4 = 80% of a site (a second strike finishes it)


def wave_mult(state, d) -> float:
    """v0.41.155 (red zerg): 1.0 on an ordinary day, the level's `raid_wave_mult` on a massed-wave day (chance `raid_wave`; seeded from the campaign and the day)."""
    p = float(getattr(d, "raid_wave", 0.0))
    if p <= 0.0:
        return 1.0
    return float(getattr(d, "raid_wave_mult", 1.5)) if random.Random(f"{state.campaign_id}:{state.day}:wave").random() < p else 1.0


def eff(k: int) -> float:
    """v0.41.155: damage counts aircraft up to four in full, then half each (a big raid hurts more but the rest of the bombs fall on rubble; judgment call)."""
    return float(k) if k <= 4 else 4.0 + 0.5 * (k - 4)


def raider_wings(state, kind: str = "field", budget: bool = True, pref=None) -> list:
    """[(wing, type)] of the enemy wings that can send a raid now: a pair of that type free this turn (`redair.ready_of`: ready and not in a patrol; the serviceable jets when the turn has no plan), field not
    cratered, sorties left in the day's cap (`budget`). Bombers (Su-24M) are preferred against fields, Su-25s against troops and garrisons (and, `_reach`, supply sites: `pref`
    overrides the order)."""
    pref = pref or (("Su_25",) + BOMBER_TYPES if kind in ("garrison", "sector") else BOMBER_TYPES + ("Su_25",))      # v0.41.361 (Phase 10d): the Su-34 is a bomber type like the Su-24M (a wing with both flies the Su-24M first)
    out = []
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if a is None or a.destroyed or runways.is_closed(state, w.base_asset_id) or (budget and not redair.can(state, w.base_asset_id, 2)):
            continue
        t = next((t for t in pref if redair.ready_of(state, w, (t,)) >= 2), None)        # v0.41.53: a squadron of that type with a pair serviceable (v0.41.341: and free this turn)
        if t:
            out.append((w, t))
    return out


def _bomber_wings(state) -> list:
    return [w for w, _ in raider_wings(state)]


def aim_xy(state, aim: str, base):
    """Where the raiders are going: the airfield, a friendly supply site or garrison, or the middle of a contested sector."""
    if aim.startswith("sector:"):
        c = state.ground["centers"][int(aim.split(":")[1])]
        return float(c[0]), float(c[1])
    a = state.blue_assets.get(aim) if aim else None
    return (a.x, a.y) if a is not None else (base.x, base.y)


def aim_kind(aim: str) -> str:
    return "field" if not aim else "sector" if aim.startswith("sector:") else "garrison" if aim.startswith(("bgar_", "bfwd_")) else "supply"


def describe(state, base, aim: str = "") -> str:
    k = aim_kind(aim)
    if k == "field":
        return f"Intercept a raid on {base.name}"
    if k == "sector":
        return f"Intercept an air attack on friendly troops: {state.ground['names'][int(aim.split(':')[1])]}"
    a = state.blue_assets[aim]
    return f"Intercept an air attack on the {a.name}" if k == "garrison" else f"Intercept a raid on the {a.name}"


def _reach(state, kind: str, x: float, y: float, budget: bool = True, only=None, fits=None):
    """(distance nm, wing, type) of the nearest wing that can reach (x, y) with a raid of this kind, or None. v0.41.125: `only` restricts the aircraft type. v0.41.359 (Phase 10c, `SU25_SUPPLY`):
    a raid on a supply site is tried with the Su-25 wings first (`raider_wings` `pref`), then as before (Su-24M first)."""
    if kind == "supply" and SU25_SUPPLY and only is None and fits is None:
        r = _reach_by(state, kind, x, y, budget, ("Su_25",), only, fits)
        if r is not None:
            return r
    return _reach_by(state, kind, x, y, budget, None, only, fits)


def _reach_by(state, kind: str, x: float, y: float, budget: bool, pref, only, fits):
    from .loadouts import ENEMY_RADIUS_NM
    best = None
    only = (only,) if isinstance(only, str) else only                          # v0.41.361 (Phase 10d): a type or a tuple of types
    for w, t in raider_wings(state, kind, budget, pref):
        if only and t not in only:
            continue
        if fits is not None and not fits(w, t):
            continue
        a = state.assets[w.base_asset_id]
        nm = math.hypot(a.x - x, a.y - y) / NM
        if nm <= ENEMY_RADIUS_NM[t] * 0.85 and (best is None or nm < best[0]):
            best = (nm, w, t)
    return best


def _tu_reach(state, x: float, y: float):
    """(distance nm, wing, type) when the bomber wing (Mozdok) can reach (x, y) with a Tu-22M3 land strike (radius x 0.85), else None. The wing and its field are checked by `bombers._bomber_wing`."""
    from . import bombers
    from .loadouts import ENEMY_RADIUS_NM
    bw = bombers._bomber_wing(state)
    if bw is None:
        return None
    a = state.assets[bw.base_asset_id]
    nm = math.hypot(a.x - x, a.y - y) / NM
    return (nm, bw, TU22) if nm <= ENEMY_RADIUS_NM[TU22] * 0.85 else None


def _nearest_field(state, x: float, y: float):
    fallen = set((state.ground or {}).get("fallen", []))
    fs = [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD and b.id not in fallen and not b.divert] or [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD]          # Phase 9a: a divert field is nobody's home
    return min(fs, key=lambda b: math.hypot(b.x - x, b.y - y)) if fs else None


def candidates(state, kind: str, tu: bool = False) -> list:
    """[(base, aim, weight)] for one kind of raid ("field" | "supply" | "garrison" | "sector"). The base is the friendly field the package is flown for. `tu` (v0.41.355, Phase 10a; "supply" only): the
    Tu-22M3 land strike's targets: the supply sites the bomber wing reaches that no live Patriot / HAWK covers (no SEAD is built for it, as for every raid on a covered supply site)."""
    out = []
    fallen = set((state.ground or {}).get("fallen", []))
    if kind == "field":
        from .loadouts import ENEMY_RADIUS_NM
        for b in state.bases.values():
            if b.kind == BaseKind.CARRIER or not any(s.base_id == b.id and s.available > 0 for s in state.squadrons.values()) or b.id in fallen:
                continue
            r = _reach(state, "field", b.x, b.y)
            if r is None:
                continue
            out.append((b, "", max(0.15, 1.0 - r[0] / 330.0) * (0.6 + 0.8 * (1.0 - getattr(b, "defense", 0.5)))))
    elif kind in ("supply", "garrison"):
        for a in sorted(getattr(state, "blue_assets", {}).values(), key=lambda a: a.id):
            if a.destroyed:
                continue
            if (kind == "garrison") != (a.id.startswith(("bgar_", "bfwd_"))):
                continue
            wt_ = 1.0
            if a.id.startswith("bfwd_"):                                  # v0.41.102: a forward garrison is raided where friendly troops still hold the sector, more where the pressure is
                from . import ground
                i_ = ground.sector_of(state, a.id)
                if i_ is None or ground.blue_strength(state, i_) < ground.MIN_FORCE:
                    continue
                wt_ = 0.5 + ground.info(state, i_)["pressure"]
            home = state.bases.get(a.id.split("_", 1)[1]) if a.id.split("_", 1)[1] in state.bases else _nearest_field(state, a.x, a.y)
            if home is None or home.id in fallen:
                continue
            r = _tu_reach(state, a.x, a.y) if tu else _reach(state, kind, a.x, a.y)
            if r is None or (tu and cover_field(state, a.x, a.y) is not None):
                continue
            out.append((home, a.id, max(0.15, 1.0 - r[0] / 330.0) * (0.5 + 0.5 * a.health) * (a.value / 5.0) * wt_))
    elif kind == "sector":
        from . import ground
        if ground.active(state):
            for i in range(ground.n_zones(state.ground)):
                zi = ground.info(state, i)
                if not zi["contested"]:
                    continue
                c = state.ground["centers"][i]
                r = _reach(state, "sector", c[0], c[1])
                home = _nearest_field(state, c[0], c[1])
                if r is None or home is None:
                    continue
                out.append((home, f"sector:{i}", max(0.15, 1.0 - r[0] / 330.0) * (0.3 + zi["pressure"])))
    return out


def target_weights(state) -> list:
    """[(base, weight)] for our airfields a raid could go for: within reach of a raider wing, with something to bomb, nearer and softer = likelier."""
    return [(b, w) for b, _, w in candidates(state, "field")]


def _weighted(rng: random.Random, ws: list):
    tot = sum(w for *_, w in ws)
    r = rng.random() * tot
    for item in ws:
        r -= item[-1]
        if r <= 0:
            return item
    return ws[-1]


def pick_aim(state, d, rng: random.Random):
    """-> (base, aim) for one raid: the airfield, or (with the level's raid_mix chances) a supply site, a field's garrison or friendly troops in a contested sector."""
    mix = tuple(getattr(d, "raid_mix", (0.0, 0.0, 0.0)))
    r = rng.random()
    order = ["supply", "garrison", "sector"]
    kind, acc = "field", 0.0
    for k, p in zip(order, mix):
        acc += p
        if r < acc:
            kind = k
            break
    def can_(ws_):                                  # v0.41.125: red does not start a raid on a covered target it cannot suppress
        out_ = []
        for b_, aim_, w_ in ws_:
            x_, y_ = aim_xy(state, aim_, b_)
            r_ = reach_for(state, aim_kind(aim_), x_, y_, d=d)
            if r_ is not None and sead_plan(state, d, b_, aim_, r_[1], r_[2])[0]:
                out_.append((b_, aim_, w_))
        return out_
    ws = can_(candidates(state, kind)) or (can_(candidates(state, "field")) if kind != "field" else [])
    if not ws:
        return None
    ws = shy(state, d, ws)
    base, aim, _ = _weighted(rng, ws)
    return base, aim


ARM_AD_FACTOR = 0.5     # v0.41.84: a field raid with a red SEAD pair meets half the battery cover in the unflown (background) raids (judgment call)
ARM_AD_FACTOR_8 = 0.2     # v0.41.116: ...and two four-jet flights (8 Su-24M, 16 Kh-31P) take more again (judgment call)
ARM_AD_FACTOR_4 = 0.3     # v0.41.94: ...and a four-jet SEAD group (both a Patriot and a HAWK live, or a full-strength Patriot) takes more of it (judgment call)


def arm_jets(state, base, available: int, nb: int, cap: int = 8, cap_free: int = 8) -> int:
    """v0.41.94: the size of red's Su-24M SEAD group against this field's batteries, like blue's salvo sizing: 2 jets (4 Kh-31P) for a Patriot or a HAWK
    alone, 4 (8 missiles) when both are live or the Patriot is at full strength, 8 (two four-jet flights, v0.41.116) when a full Patriot and a HAWK are both live. At most the Su-24Ms the wing has left beyond its `nb` bom
    (a short wing falls back to a pair), 0 when the field has neither battery. Thresholds are judgment calls (Kh-31P: 2 per Su-24M, Wikipedia).
    v0.41.125: `cap` (the level's `arm_cap`; L2 a pair) lowers the size unless the wing has `cap_free` jets spare."""
    from . import sams
    bt = sams.blue_battery(base, state)
    if not (bt["patriot_ln"] or bt["hawk"]):
        return 0
    full_ = bt["patriot_ln"] >= sams.BLUE_PATRIOT_LN
    want = 8 if (bt["patriot_ln"] and bt["hawk"] and full_) else (4 if ((bt["patriot_ln"] and bt["hawk"]) or full_) else 2)     # v0.41.116: a full Patriot AND a HAWK: two four-jet flights (XO 2026-10-22: 4 + 4)
    free = available - nb
    if free < cap_free:
        want = min(want, cap)
    for n_ in (want, 4, 2):                                  # a short wing steps down: 8, 4, 2, none
        if n_ <= want and free >= n_:
            return n_
    return 0
PATRIOT_NM = 40          # v0.41.20: a full-strength field's Patriot covers its own field and what lies this close to it
FLEET_NM = 70            # v0.41.31: ...and the carrier group's SM-2 reach (measured: CAP pairs killed 51-67 nm out; mission_builder.FLEET_RAID_AVOID_NM)
HAWK_NM = 25             # ...and a field's HAWK battery (v0.41.30: every full-strength field has one, not only yours)


def covering_fields(state, x: float, y: float) -> list:
    """v0.41.129: every airfield whose live Patriot (PATRIOT_NM) or HAWK (HAWK_NM) covers (x, y), nearest first. In Georgia the fields are about 20 nm apart, so a
    target is usually covered by its neighbours' batteries too."""
    from .sams import blue_battery
    out = []
    for b in state.bases.values():
        if b.kind != BaseKind.AIRFIELD:
            continue
        bt = blue_battery(b, state)
        dn = math.hypot(b.x - x, b.y - y) / NM
        if (bt["patriot_ln"] and dn <= PATRIOT_NM) or (bt["hawk"] and dn <= HAWK_NM):
            out.append((dn, b.id, b))
    return [b for _, _, b in sorted(out, key=lambda t: t[:2])]


def cover_field(state, x: float, y: float):
    """v0.41.125: the nearest airfield whose live Patriot (PATRIOT_NM) or HAWK (HAWK_NM) covers (x, y), or None."""
    fs = covering_fields(state, x, y)
    return fs[0] if fs else None


def reach_for(state, kind: str, x: float, y: float, budget: bool = True, d=None):
    """v0.41.125: like `_reach`, but a target under live Patriot / HAWK cover is raided only by a Su-24M wing (the type that carries the SEAD group).
    v0.41.142: with the level `d`, the wing must also be big enough to field that SEAD group (a nearer wing of two Su-24M is passed over for the nearest
    one that can; the new red roster spreads the Su-24M over the fields, where the old random squadrons left whole wings of them)."""
    if cover_field(state, x, y) is None or getattr(d, "raid_banzai", False):
        return _reach(state, kind, x, y, budget)
    fits = None
    if d is not None and kind == "field":
        fits = lambda w, t: bool(sead_groups(state, d, x, y, redair.ready_of(state, w, (t,)), int(d.raid_size[1])))
    return _reach(state, kind, x, y, budget, only=BOMBER_TYPES, fits=fits)           # v0.41.361 (Phase 10d): any bomber type (the type the wing flies, `t`)


ARM_MAX_TOTAL = 12       # v0.41.129: the most SEAD jets one raid sends in all (three flights of four; judgment call)


def sead_groups(state, d, x: float, y: float, available: int, nb: int):
    """v0.41.129 (XO 2026-10-23: the neighbour's Patriot shot the bombers after the gate opened): -> [(field, jets)], one SEAD group for EVERY field whose
    live battery covers (x, y), nearest first; [] when nothing covers it; None when red cannot suppress them all. Every covering field gets a pair (4 Kh-31P
    to blind its radars; judgment call), and what is left of the wing's spare jets (`available` less the `nb` bombers) tops the nearest fields up to
    their `arm_jets` size, nearest first (the level's `arm_cap` caps one group: L2 a pair unless `arm_cap_free` jets are spare). None when the pairs alone
    need more jets than are spare, or the total tops ARM_MAX_TOTAL."""
    fs = covering_fields(state, x, y)
    if not fs:
        return []
    cap, cap_free = int(getattr(d, "arm_cap", 8)), int(getattr(d, "arm_cap_free", 8))
    free0 = available - nb
    if free0 < 2 * len(fs) or 2 * len(fs) > ARM_MAX_TOTAL:
        return None
    left = min(free0, ARM_MAX_TOTAL) - 2 * len(fs)
    out = []
    for f in fs:
        want = arm_jets(state, f, free0 + nb, nb, cap, cap_free)
        size = max([n for n in (8, 4, 2) if n <= max(2, want) and n - 2 <= left] or [2])
        left -= size - 2
        out.append((f, size))
    return out if sum(n for _, n in out) <= ARM_MAX_TOTAL else None


def sead_plan(state, d, base, aim: str, wing, ac: str):
    """v0.41.125 (XO 2026-10-23: no dice, intelligent planning): -> (ok, n_arm). A target under live Patriot / HAWK cover is raided only by a Su-24M wing
    that can field the SEAD groups (v0.41.129: one for every covering field, see `sead_groups`; L1 none); an uncovered target needs none. Raids on
    covered supply sites, garrisons and sectors are not attempted (no SEAD is built for them)."""
    x, y = aim_xy(state, aim, base)
    if cover_field(state, x, y) is None:
        return True, 0
    if getattr(d, "raid_banzai", False):                  # v0.41.146: Level 1's insurgents go in without suppression; the batteries shoot at them
        return True, 0
    if aim_kind(aim) != "field" or ac not in BOMBER_TYPES or getattr(d, "raid_arm", 0) <= 0:
        return False, 0
    avail = redair.ready_of(state, wing, (ac,))
    g = sead_groups(state, d, x, y, avail, int(d.raid_size[1]))
    n = sum(j for _, j in g) if g else 0
    return n > 0, n


def shy(state, d, ws: list) -> list:
    """v0.41.20: no needless banzai for red's raids. On Normal and Hard a raid's pick shies from targets under a full Patriot (Hard: also under
    your home field's HAWK); the weights drop by the level's "soft" factor. Easy's red does not care. Nothing is ruled out outright."""
    from . import redair
    doc = redair.doctrine(d)
    if doc["soft"] >= 1.0:
        return ws
    fields = [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD and getattr(b, "defense", 0.0) >= 0.6]
    from .sams import blue_battery
    hawks = [b for b in fields if blue_battery(b, state)["hawk"]] if doc["hawk"] else []
    fleets = [b for b in state.bases.values() if b.kind == BaseKind.CARRIER]     # v0.41.30: every field's HAWK, not only your home field's
    out = []
    for base, aim, w in ws:
        x, y = aim_xy(state, aim, base)
        hot = any(math.hypot(b.x - x, b.y - y) <= PATRIOT_NM * NM for b in fields)
        if any(math.hypot(h.x - x, h.y - y) <= HAWK_NM * NM for h in hawks):
            hot = True
        if any(math.hypot(c.x - x, c.y - y) <= FLEET_NM * NM for c in fleets):      # v0.41.31: the carrier group's SM-2s count too
            hot = True
        out.append((base, aim, w * (doc["soft"] if hot else 1.0)))
    return out


def raid_objective(base, aim: str = "", desc: str | None = None) -> Objective:
    return Objective("", ObjectiveType.FLEET_DEFENSE, base.id, RAID_PRIORITY, desc or f"Intercept a raid on {base.name}", aim)


def red_attack_pairs(state, turn: int):
    """v0.41.345 (scaled tasking, Phase C): red's free attack pairs this turn (Su-24M, Su-25, Tu-22M3: every squadron whose aircraft is not a fighter), read from `red_air["free"]` once `redair.plan_turn`
    has filled it for THIS turn; None when it has not (an unplanned night turn, overnight, tools)."""
    from .loadouts import ENEMY_FIGHTERS
    ra = getattr(state, "red_air", None) or {}
    free = ra.get("free")
    if not free or ra.get("turn") != turn:
        return None
    typ = {q.id: q.aircraft for w in state.enemy_air for q in w.sqns}
    return sum(int(n) // 2 for sid, n in free.items() if typ.get(sid) is not None and typ[sid] not in ENEMY_FIGHTERS)


def turn_rate(state, d, turn: int) -> float:
    """The chance of a raid in this turn: the level's `raid_rate` a day spread over the day's 12 turns (v0.41.341, Phase 5b; it was one draw a day in `Session._begin_day`), times the idle surge
    (v0.41.155: red raids more while your squadron stands down) and `RED_RAID_NIGHT` on a night turn. v0.41.345 (scaled tasking, Phase C): times `RAID_TEMPO` x red's free attack pairs / `RAID_REF_PAIRS`
    (at most `RAID_MULT_MAX`), so a worn-down red raids less; a turn with no pool (unplanned night, tools) keeps the plain rate."""
    from . import ground as _gr
    r = float(d.raid_rate) * _gr.surge(state, d) / TURNS_PER_DAY * (RED_RAID_NIGHT if clock.is_night_turn(turn) else 1.0)
    pairs = red_attack_pairs(state, turn)
    if pairs is None:
        return r
    lvl = max(1, min(3, int(getattr(d, "level", 1))))
    return r * max(0.0, min(RAID_MULT_MAX, pairs / RAID_REF_PAIRS[lvl])) * RAID_TEMPO[lvl]


def plan_raid(state, d, base, aim: str, oid: str, turn: int):
    """Book one raid out of the turn's free red jets and plan it: the wing and type that fly it, the raiders (`bombers`), the SEAD / DEAD group, the escort wing and type with the escorts and the SEAD / DEAD
    covers, the bearing it arrives on. v0.41.341 (Phase 5b): this was done at build time (`PackageBuilder._land_raid_plan`) from the wings' serviceable jets, and a wing that could not reach any more by then
    left the package with no plan (the KeyError in `raid_spawns._raid_axis`); now the draw, the booking and the package agree. -> {extras of the package, "jets": [[squadron id, jets, "raid" | "esc"]]}, or None
    when no wing can field it (then nothing is booked and there is no raid). A target under live cover needs its SEAD group (`sead_plan`); Level 1 goes in without."""
    from .loadouts import ENEMY_FIGHTERS, ENEMY_RADIUS_NM
    ax, ay = aim_xy(state, aim, base)
    r = reach_for(state, aim_kind(aim), ax, ay, d=d)
    if r is None:
        return None
    bw, raider = r[1], r[2]
    if not sead_plan(state, d, base, aim, bw, raider)[0]:
        return None
    rnd = random.Random(f"{state.campaign_id}:{turn}:{oid}:{base.id}:{aim}:raid")
    ba = state.assets[bw.base_asset_id]
    lo, hi = d.raid_size
    rdy = redair.ready_of(state, bw, (raider,))
    nb = max(2, min(int(round(rnd.randint(lo, hi) * wave_mult(state, d))), rdy))        # v0.41.155: a massed-wave day
    nb -= nb % 2
    if nb < 2 or rdy < nb:
        return None
    esc, esc_avail = None, 0
    from . import bombers, blue_barcap
    held_ = bombers.escorts_held(state)                                             # v0.41.355 (Phase 10a): the Mozdok escort squadron escorts land raids too, unless a carrier raid is staged
    alone_ = (raider == "Su_25" and aim_kind(aim) == "supply" and SU25_SUPPLY                          # v0.41.359 (Phase 10c): no blue fighter squadron can reach the site's field (blue's own patrol rule, `blue_barcap._cap_squadrons`): the Su-25s go alone
              and not blue_barcap._cap_squadrons(state, base))
    for w in ([] if alone_ else sorted(state.enemy_air, key=lambda w: math.hypot(state.assets[w.base_asset_id].x - ax, state.assets[w.base_asset_id].y - ay))):
        a = state.assets[w.base_asset_id]
        if w is bw or a.destroyed:
            continue
        d_nm = math.hypot(a.x - ax, a.y - ay) / NM
        types = [t for t in dict.fromkeys(q.aircraft for q in w.sqns if q.role != "escort" or not held_)
                 if t in ENEMY_FIGHTERS and redair.ready_of(state, w, (t,)) >= 2 and ENEMY_RADIUS_NM.get(t, 0) * 0.85 >= d_nm]
        if types:
            esc = (w, rnd.choice(types))
            esc_avail = redair.ready_of(state, w, (esc[1],))
            break
    brg = math.degrees(math.atan2(ba.y - ay, ba.x - ax)) % 360                      # they come from where they took off
    arm, arm_fields = 0, []
    if getattr(d, "raid_arm", 0) > 0 and not aim and raider in BOMBER_TYPES and rdy >= nb + 2:    # v0.41.84: a SEAD group ahead of the bombers
        sg_ = sead_groups(state, d, ax, ay, rdy, nb)                                 # v0.41.94: sized like blue's salvo; v0.41.125: L2 capped at a pair; v0.41.129: a group for every covering field
        arm_fields = [[f_.id, n_] for f_, n_ in (sg_ or [])]
        arm = sum(n_ for _, n_ in arm_fields)
    free2_ = rdy - nb - arm
    dead = (8 if (arm >= 8 and free2_ >= 8) else (4 if (arm >= 4 and free2_ >= 4) else (2 if (arm >= 2 and free2_ >= 2 and getattr(d, "arm_cap", 8) <= 2) else 0)))     # v0.41.125: L2 gets a DEAD pair behind its SEAD pair; v0.41.117: the DEAD package (KAB-500Kr), gated; only behind a SEAD group of four or more
    if cover_field(state, ax, ay) is not None and not arm and not getattr(d, "raid_banzai", False):      # v0.41.125: no SEAD to send under live cover: no raid (v0.41.341: Level 1's banzai raids go in, as `sead_plan` says)
        return None
    esc_even = esc_avail - esc_avail % 2
    escorts = min(max(4 if nb >= 4 else 2, nb // 2 + (2 if nb >= 8 else 0)), esc_even) if esc else 0      # v0.41.341: never more than the wing has free (the floor of four used to ignore it)
    spare = esc_even - escorts
    arm_cover = 4 if (arm >= 4 and esc and spare >= 4) else 0                        # v0.41.116: a SEAD group of four or more brings its own fighters: a pair of escorts and a pair on a TARCAP station (v0.41.341: when the wing has them free)
    spare -= arm_cover
    dead_cover = 4 if (dead and esc and spare >= 4) else 0
    jets = [[sid, n, "raid"] for sid, n in redair.take_ready(state, bw, (raider,), nb + arm + dead)]
    if esc:
        jets += [[sid, n, "esc"] for sid, n in redair.take_ready(state, esc[0], (esc[1],), escorts + arm_cover + dead_cover)]
    redair.spend(state, bw.base_asset_id, nb + arm + dead)                           # the day's sortie cap: the overnight raids and the abstract strikes draw on it too
    if esc:
        redair.spend(state, esc[0].base_asset_id, escorts + arm_cover + dead_cover)
    return {"arm": arm, "arm_fields": arm_fields, "arm_cover": arm_cover, "dead": dead, "dead_cover": dead_cover, "land": True, "raider": raider, "brg": round((brg + rnd.uniform(-12, 12)) % 360, 1), "bombers": nb,
            "bomber_wing": bw.base_asset_id, "escort_wing": esc[0].base_asset_id if esc else "", "escort_type": esc[1] if esc else "", "escorts": escorts, "mass": nb >= 8, "aim": aim, "dest": [ax, ay], "jets": jets}


def plan_tu_strike(state, d, base, aim: str, oid: str, turn: int):
    """v0.41.355 (Phase 10a): book a Tu-22M3 LAND STRIKE out of the turn's free red jets: `bombers.LAND_TU` Tu-22M3 and `bombers.LAND_ESCORTS` Su-27 of the Mozdok escort squadron, on the supply site `aim`. The same
    plan dict as `plan_raid` (`land`, `raider` Tu_22M3, `jets` ...), so the package, the war sim and the builder treat it as one more land raid. The jets the carrier raid still needs today are left alone
    (`bombers.carrier_claim`). None when the wing cannot field it."""
    from . import bombers
    from .loadouts import ENEMY_FIGHTERS
    bw = bombers._bomber_wing(state)
    if bw is None:
        return None
    ax, ay = aim_xy(state, aim, base)
    et = next((q.aircraft for q in bw.sqns if q.role == "escort" and q.aircraft in ENEMY_FIGHTERS), None)
    if et is None or not redair.can(state, bw.base_asset_id, bombers.LAND_TU + bombers.LAND_ESCORTS):
        return None
    c_tu, c_es = bombers.carrier_claim(state, d, turn)
    if redair.ready_of(state, bw, (TU22,)) - c_tu < bombers.LAND_TU or redair.ready_of(state, bw, (et,)) - c_es < bombers.LAND_ESCORTS:
        return None
    rnd = random.Random(f"{state.campaign_id}:{turn}:{oid}:{base.id}:{aim}:tu")
    ba = state.assets[bw.base_asset_id]
    brg = math.degrees(math.atan2(ba.y - ay, ba.x - ax)) % 360
    jets = [[sid, n, "raid"] for sid, n in redair.take_ready(state, bw, (TU22,), bombers.LAND_TU)]
    jets += [[sid, n, "esc"] for sid, n in redair.take_ready(state, bw, (et,), bombers.LAND_ESCORTS)]
    redair.spend(state, bw.base_asset_id, bombers.LAND_TU + bombers.LAND_ESCORTS)
    return {"arm": 0, "arm_fields": [], "arm_cover": 0, "dead": 0, "dead_cover": 0, "land": True, "raider": TU22, "brg": round((brg + rnd.uniform(-12, 12)) % 360, 1), "bombers": bombers.LAND_TU,
            "bomber_wing": bw.base_asset_id, "escort_wing": bw.base_asset_id, "escort_type": et, "escorts": bombers.LAND_ESCORTS, "mass": False, "aim": aim, "dest": [ax, ay], "jets": jets, "tu_strike": True}


def tu_strike(state, d, rng: random.Random, turn: int):
    """v0.41.355 (Phase 10a, cadence (c)): this turn's Tu-22M3 land strike, drawn BEFORE the ordinary raids so it takes its jets first. -> (objective, booking) or None. Never when the wing never raids
    (`bomber_policy` "none"), when today's cap (`bombers.land_cap`) is reached, or when no supply site that no live battery covers lies within reach. The chance per turn is `TU_STRIKE_TEMPO` x the cap / 12
    (half of it at night, `RED_RAID_NIGHT`), drawn from `rng` so a replan of the turn gives the same answer. The strike is counted in `raids["tu_land"]` (turn -> 1)."""
    from . import bombers
    cap = bombers.land_cap(d)
    p = cap * TU_STRIKE_TEMPO / TURNS_PER_DAY * (RED_RAID_NIGHT if clock.is_night_turn(turn) else 1.0)
    hit_ = rng.random() < p                                  # always drawn: the sequence does not depend on the state
    pick_ = random.Random(f"{state.campaign_id}:{turn}:tu-aim")
    if cap <= 0 or not hit_ or bombers.land_done(state, turn) >= cap:
        return None
    ws = candidates(state, "supply", tu=True)
    if not ws:
        return None
    base, aim, _ = _weighted(pick_, ws)
    o = raid_objective(base, aim, describe(state, base, aim))
    o.id = f"obj-t{turn}-t1"
    bk = plan_tu_strike(state, d, base, aim, o.id, turn)
    if bk is None:
        return None
    if state.raids is not None:
        state.raids.setdefault("tu_land", {})[str(turn)] = 1
    return o, bk


def turn_raids(state, d, rng: random.Random, turn: int, planned: bool = True) -> tuple:
    """-> (objectives of the raids red plans THIS turn; number of unwarned raids that could not be built, settled overnight). One draw a turn (chance `turn_rate`; v0.41.341, Phase 5b: it was one draw a day in
    `Session._begin_day`); the same seed gives the same answer. Each raid is booked (`plan_raid`) as it is drawn and its plan is kept in `state.raids["booked"]`. Ids are obj-t<turn>-r<n>, and obj-t<turn>-s<n> for an
    unwarned one (`Session.plan_turn` reads "-s<n>" as "no warning"). `planned` False (a night turn with night ops off: nothing is planned in it and nothing is booked): every raid drawn is a surprise,
    settled overnight."""
    from . import bombers
    if bombers.is_quiet(state):                             # v0.41.109: the quiet day before the carrier raid
        return [], 0
    rate = turn_rate(state, d, turn)
    n = int(rate) + (1 if rng.random() < rate - int(rate) else 0)
    warned, surprise = [], 0
    booked = state.raids.setdefault("booked", {}) if state.raids is not None else {}
    if state.raids is not None:
        state.raids.setdefault("tu_land", {}).pop(str(turn), None)      # v0.41.355: this turn's land strike is drawn again (a replan of the turn)
    if planned:
        tu_ = tu_strike(state, d, random.Random(f"{state.campaign_id}:{turn}:tu"), turn)       # v0.41.355 (Phase 10a): the Tu-22M3 land strike first, before the ordinary raids take the jets
        if tu_ is not None:
            booked[tu_[0].id] = tu_[1]
            warned.append(tu_[0])
    for _ in range(n):
        unwarned = rng.random() < d.raid_surprise
        if not planned:
            surprise += 1
            continue
        pa = pick_aim(state, d, rng)
        if pa is not None and all((o.target_id, o.aim) != (pa[0].id, pa[1]) for o in warned):
            base, aim = pa
            o = raid_objective(base, aim, describe(state, base, aim))
            # v0.41.304 (XO 2026-11-05: "no more hidden ones"): an unwarned raid is listed like the others (id ...-s<n>, the package reads "no warning"); it used to be only a count settled overnight
            o.id = f"obj-t{turn}-{'s' if unwarned else 'r'}{len(warned) + 1}"
            bk = plan_raid(state, d, base, aim, o.id, turn)
            if bk is not None:
                booked[o.id] = bk
                warned.append(o)
                continue
        if unwarned:
            surprise += 1                                    # no target to build it on, or no wing that can field it: it still happens, settled overnight as before
    return warned, surprise


def hit(state, base_id: str, wing, rng: random.Random, through: int | None = None, aim: str = "", ac: str | None = None) -> list:
    """Bombs fall on one of our airfields, a supply site, a garrison or on friendly troops. The raiders lose a jet to the defences. Log lines."""
    b = state.bases[base_id]
    k = through if through is not None else rng.randint(1, 3)
    ke = eff(k)
    from .sams import covering_ad
    ad = covering_ad(state, *aim_xy(state, aim, b))
    if wing is not None:                                # v0.41.30: a full Patriot + HAWK takes a second jet (was always one)
        wing.lose(ac, 1 + (round(ad) if through is None else 0))    # (a flown raid's real kills are counted by the debrief)
    kind = aim_kind(aim)
    if kind == "sector":
        g, i = state.ground, int(aim.split(":")[1])
        g["blue"][i] = max(0.0, g["blue"][i] - SECTOR_HIT * ke)
        return [f"   {g['names'][i]}: friendly strength down to {g['blue'][i]:.0f} after the air attack"]
    if kind in ("supply", "garrison"):
        a = state.blue_assets[aim]
        a.health = max(0.0, a.health - ASSET_HIT * ke)
        return [f"   {a.name} {'destroyed' if a.destroyed else f'damaged, {a.health:.0%} left'}"]
    gar = state.blue_assets.get(f"bgar_{base_id}") if getattr(state, "blue_assets", None) else None
    shield = 1.0 - GARRISON_SHIELD * (gar.health if gar is not None and not gar.destroyed else 0.0)
    gone = []
    if b.kind != BaseKind.CARRIER:
        from .sams import hit_field
        gone = hit_field(state, b, BASE_LOSS * ke * shield * (1.0 - 0.4 * ad))     # v0.41.30: batteries soak part of the damage (judgment call)
    sqs = sorted((s for s in state.squadrons.values() if s.base_id == base_id and s.available > 0), key=lambda s: -s.available)
    lines = [f"   bombs fell on {b.name}: its defences are down to {b.defense:.0%}{' (' + ', '.join(gone) + ' destroyed)' if gone else ''}" if b.kind != BaseKind.CARRIER else f"   missiles hit {b.name}"]
    if sqs:
        sq = sqs[0]
        lost = min(sq.available, rng.randint(1, 1 + int(ke)))
        sq.available -= lost
        lines.append(f"   {lost} parked aircraft lost ({sq.name}: {sq.available}/{sq.authorized} left)")
    return lines


def tu_hit(state, base_id: str, wing, rng: random.Random, aim: str, nb: int) -> list:
    """v0.41.355 (Phase 10a): a Tu-22M3 land strike that got through. 1 to `nb` of the Tu-22M3 drop (random), each worth `TU_HIT_EQUIV` aircraft on the supply site (`hit`, judgment call); the wing loses a jet
    only to the batteries round the target (`round(covering_ad)`: none for the uncovered sites the strike picks), where the Su-24M raids always lose one."""
    from .sams import covering_ad
    n_thr = rng.randint(1, max(1, int(nb)))
    ad = covering_ad(state, *aim_xy(state, aim, state.bases[base_id]))
    lost = wing.lose(TU22, round(ad)) if (wing is not None and round(ad) > 0) else 0
    lines = hit(state, base_id, None, rng, int(round(TU_HIT_EQUIV * n_thr)), aim, TU22)
    if lost:
        lines.append(f"   {lost} Tu-22M3 lost to the defences")
    return lines


def overnight(state, d, rng: random.Random) -> list:
    """Surprise raids nobody flew: our alert aircraft and the field's defences against the bombers. Returns the log lines."""
    n = int((state.raids or {}).get("surprise", 0))
    lines = []
    for _ in range(n):
        pa = pick_aim(state, d, rng)
        if pa is None:
            continue
        b, aim = pa
        x, y = aim_xy(state, aim, b)
        r = reach_for(state, aim_kind(aim), x, y, d=d)
        if r is None:
            continue
        wing = r[1]
        redair.spend(state, wing.base_asset_id, int(d.raid_size[1]))
        alert = sum(s.available for s in state.squadrons.values() if s.base_id == b.id) / max(1, sum(s.authorized for s in state.squadrons.values() if s.base_id == b.id))
        from .sams import covering_ad
        ad_ = covering_ad(state, x, y)
        ok_, n_arm_ = sead_plan(state, d, b, aim, wing, r[2])      # v0.41.125: no dice: a covered target is raided only with its SEAD group
        if not ok_:
            continue
        arm_ = n_arm_ > 0
        if arm_:
            ad_ *= ARM_AD_FACTOR_8 if n_arm_ >= 8 else (ARM_AD_FACTOR_4 if n_arm_ >= 4 else ARM_AD_FACTOR)
        p_stop = min(0.95, 0.2 + 0.45 * ad_ + 0.3 * alert)       # v0.41.30: the batteries that cover the target (was the field's defense number)
        what = {"field": b.name, "supply": state.blue_assets[aim].name if aim in state.blue_assets else "", "garrison": state.blue_assets[aim].name if aim in state.blue_assets else "",
                "sector": "friendly troops in " + state.ground["names"][int(aim.split(":")[1])] if aim.startswith("sector:") else ""}[aim_kind(aim)]
        from . import blue_barcap
        wa_ = state.assets.get(wing.base_asset_id)
        up_, psq_ = blue_barcap.patrol_up(state, rng, b, (wa_.x, wa_.y)) if (wa_ is not None and b.kind != BaseKind.CARRIER) else (False, None)       # v0.41.86: a pair on station
        if up_:
            p_stop = min(0.95, p_stop + blue_barcap.PATROL_STOP)
        from . import tempo as _tp
        p_stop = min(0.95, p_stop + TEMPO_STOP_SHARE * _tp.get(state, "AIR"))      # v0.41.171: the player's air work taught the alert pairs (Pilot Influence off: 0)
        lo_, hi_ = d.raid_size
        n_ = max(2, int(round(rng.randint(int(lo_), int(hi_)) * wave_mult(state, d))))
        if n_ <= 4:                                              # a small raid is settled as one lump (all stopped or all through), as before v0.41.155
            if rng.random() < p_stop:
                k = wing.lose(r[2], rng.randint(1, 3 + round(covering_ad(state, x, y))))
                lines.append(f"Surprise raid on {what}: " + ("the base patrol and " if up_ else "") + f"alert aircraft got up in time; {k} attack aircraft shot down")
                if up_ and (ln_ := blue_barcap.patrol_fight(state, rng, psq_)):
                    lines.append(ln_)
            else:
                lines.append(f"Surprise raid on {what}: nobody was warned and the aircraft got through" + (" (red anti-radiation missiles suppressed the batteries)" if arm_ else ""))
                lines += [x_.strip() for x_ in hit(state, b.id, wing, rng, None, aim, r[2])]
        else:                                                    # v0.41.155 (red zerg): a mass raid is settled aircraft by aircraft
            stopped_ = sum(1 for _ in range(n_) if rng.random() < p_stop)
            through_ = n_ - stopped_
            k = wing.lose(r[2], stopped_ + (1 if through_ else 0))
            lines.append(f"Surprise raid on {what}: {n_} attack aircraft; " + ("the base patrol and " if up_ else "") + f"alert aircraft stopped {stopped_}, {through_} got through" + (" (red anti-radiation missiles suppressed the batteries)" if arm_ else ""))
            if up_ and (ln_ := blue_barcap.patrol_fight(state, rng, psq_)):
                lines.append(ln_)
            if through_:
                lines += [x_.strip() for x_ in hit(state, b.id, None, rng, through_, aim, r[2])]
    if state.raids is not None:
        state.raids["surprise"] = 0
        state.raids["surprise_by"] = {}
    return lines


def hot_sector(state):
    """The contested sector Red is pressing hardest (an index into ground.zones), or None."""
    from . import ground
    if not ground.active(state):
        return None
    best, bi = 0.0, None
    for i in range(ground.n_zones(state.ground)):
        zi = ground.info(state, i)
        if zi["contested"] and zi["pressure"] > best:
            best, bi = zi["pressure"], i
    return bi


