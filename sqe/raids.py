"""Red raids on our airfields, and emergencies (ground war, phase 2).

Red plans a raid the way we plan a strike: it looks for one of OUR airfields that its bombers (Su-24M) can reach, preferring the ones nearest
its own fields and the least defended. Each day a few raids happen (Difficulty.raid_rate); a share of them are surprises (raid_surprise):

* Announced raids are ordinary "Intercept a raid on <airfield>" packages in the tasking order, flown like the fleet-defence mission.
* Surprise raids are never announced. They are settled by odds overnight (the airfield's own alert aircraft against the bombers) unless an
  emergency (below) puts one of them in front of you.
* An emergency can break out while you are about to fly (Difficulty.emerg_chance per sortie, never in two sorties in a row, at most one per sortie):
  a surprise raid on one of our airfields, or "troops in contact" in a sector Red is pressing. If your squadron can take it you are offered the
  scramble. If you decline, or cannot, it is folded into your mission when it is a ground job inside the merge circle, and otherwise settled by odds.

Everything here is seeded from the campaign, the day and the package, so reopening a dialog never re-rolls anything.
"""
from __future__ import annotations
import math
import random
from .models import Objective, ObjectiveType, BaseKind, Role, AssetKind
from . import redair

NM = 1852.0
RAID_RESERVE = 0.6            # an emergency is offered only if the event is within this share of the squadron's combat radius
BASE_LOSS = 0.06              # airfield defence lost per bomber that gets through
RAID_PRIORITY = 8.0
RAIDERS = ("Su_24M", "Su_25")  # attack types a raid can fly (bombers for fields and supply sites; Su-25s lead against troops)
TEMPO_STOP_SHARE = 0.5        # v0.41.171 (XO 2026-10-28): half of the AIR tempo is added to the chance a surprise raider is stopped (+20 points at the +40 cap; judgment call)
ASSET_HIT = 0.20              # health a supply site or garrison loses per aircraft that gets through
SECTOR_HIT = 4.0              # friendly sector strength lost per aircraft that gets through
GARRISON_SHIELD = 0.25        # a field's garrison takes this share off the damage its defences would suffer


def wave_mult(state, d) -> float:
    """v0.41.155 (red zerg): 1.0 on an ordinary day, the level's `raid_wave_mult` on a massed-wave day (chance `raid_wave`; seeded from the campaign and the day)."""
    p = float(getattr(d, "raid_wave", 0.0))
    if p <= 0.0:
        return 1.0
    return float(getattr(d, "raid_wave_mult", 1.5)) if random.Random(f"{state.campaign_id}:{state.day}:wave").random() < p else 1.0


def eff(k: int) -> float:
    """v0.41.155: damage counts aircraft up to four in full, then half each (a big raid hurts more but the rest of the bombs fall on rubble; judgment call)."""
    return float(k) if k <= 4 else 4.0 + 0.5 * (k - 4)


def raider_wings(state, kind: str = "field", budget: bool = True) -> list:
    """[(wing, type)] of the enemy wings that can send a raid now: 2+ serviceable aircraft, field not cratered, sorties left in the day's budget.
    Bombers (Su-24M) are preferred against fields and supply sites, Su-25s against troops and garrisons."""
    pref = ("Su_25", "Su_24M") if kind in ("garrison", "sector") else ("Su_24M", "Su_25")
    out = []
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if w.available < 2 or a is None or a.destroyed or (budget and not redair.can(state, w.base_asset_id, 2)):
            continue
        t = next((t for t in pref if t in w.types_up), None)        # v0.41.53: a squadron of that type with a pair serviceable
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


def _reach(state, kind: str, x: float, y: float, budget: bool = True, only: str | None = None, fits=None):
    """(distance nm, wing, type) of the nearest wing that can reach (x, y) with a raid of this kind, or None. v0.41.125: `only` restricts the aircraft type."""
    from .loadouts import ENEMY_RADIUS_NM
    best = None
    for w, t in raider_wings(state, kind, budget):
        if only and t != only:
            continue
        if fits is not None and not fits(w, t):
            continue
        a = state.assets[w.base_asset_id]
        nm = math.hypot(a.x - x, a.y - y) / NM
        if nm <= ENEMY_RADIUS_NM[t] * 0.85 and (best is None or nm < best[0]):
            best = (nm, w, t)
    return best


def _nearest_field(state, x: float, y: float):
    fallen = set((state.ground or {}).get("fallen", []))
    fs = [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD and b.id not in fallen] or [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD]
    return min(fs, key=lambda b: math.hypot(b.x - x, b.y - y)) if fs else None


def candidates(state, kind: str) -> list:
    """[(base, aim, weight)] for one kind of raid ("field" | "supply" | "garrison" | "sector"). The base is the friendly field the package is flown for."""
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
            r = _reach(state, kind, a.x, a.y)
            if r is None:
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


def pick_target(state, rng: random.Random, d=None):
    ws = target_weights(state)
    if d is not None:                               # v0.41.125: only a field red can suppress (see `sead_plan`)
        ws = [(b, w) for b, w in ws if (r_ := reach_for(state, "field", b.x, b.y, d=d)) is not None and sead_plan(state, d, b, "", r_[1], r_[2])[0]]
    return _weighted(rng, ws)[0] if ws else None


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
        fits = lambda w, t: bool(sead_groups(state, d, x, y, w.available_of({"Su_24M"}) if hasattr(w, "available_of") else w.available, int(d.raid_size[1])))
    return _reach(state, kind, x, y, budget, only="Su_24M", fits=fits)


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
    if aim_kind(aim) != "field" or ac != "Su_24M" or getattr(d, "raid_arm", 0) <= 0:
        return False, 0
    avail = wing.available_of({"Su_24M"}) if hasattr(wing, "available_of") else wing.available
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


def _commit(state, d, base, aim: str) -> None:
    """Book the raid's aircraft against the nearest capable wing's daily sortie budget."""
    x, y = aim_xy(state, aim, base)
    r = reach_for(state, aim_kind(aim), x, y, d=d)
    if r is not None:
        redair.spend(state, r[1].base_asset_id, int(d.raid_size[1]))


def todays_raids(state, d, rng: random.Random) -> tuple:
    """-> (objectives of the announced raids, number of surprise raids). One draw per day; the same seed gives the same answer."""
    from . import bombers
    if bombers.is_quiet(state):                             # v0.41.109: the quiet day before the carrier raid
        return [], 0
    from . import ground as _gr
    rate = float(d.raid_rate) * _gr.surge(state, d)                  # v0.41.155: red raids more while your squadron stands down
    n = int(rate) + (1 if rng.random() < rate - int(rate) else 0)
    warned, surprise = [], 0
    for _ in range(n):
        if rng.random() < d.raid_surprise:
            surprise += 1
            continue
        pa = pick_aim(state, d, rng)
        if pa is not None and all((o.target_id, o.aim) != (pa[0].id, pa[1]) for o in warned):
            base, aim = pa
            o = raid_objective(base, aim, describe(state, base, aim))
            o.id = f"obj-d{state.day}-r{len(warned) + 1}"
            _commit(state, d, base, aim)
            warned.append(o)
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
    return lines


# ---- emergencies ---------------------------------------------------------------------------------------------------------------
def emergency_seed(state, package_number: int, flight_id) -> random.Random:
    return random.Random(f"{state.campaign_id}:{state.day}:{package_number}:{flight_id}:emergency")


def emergency_happens(state, d, rng: random.Random) -> bool:
    """The per-sortie dice, with the cap: none right after a sortie that had one."""
    if (state.raids or {}).get("last_emerg", -9) == state.sortie_counter:
        return False
    from . import bombers
    if bombers.is_quiet(state):
        return False
    return rng.random() < d.emerg_chance


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


def eligible(state, spec, role_needed: str, event_xy, squadron, committed: int) -> tuple:
    """Can the player's squadron take the emergency? role matches, the base is within RAID_RESERVE of its combat radius, and 2+ aircraft are
    free once the tasked flight has taken its own. -> (bool, reason)"""
    roles = {r.value for r in spec.roles}
    if role_needed == "fighter" and not ({"CAP", "SWEEP"} & roles):
        return False, f"{spec.display} is not a fighter"
    if role_needed == "cas" and "CAS" not in roles:
        return False, f"{spec.display} does not fly close air support"
    b = state.bases[squadron.base_id]
    d_nm = math.hypot(event_xy[0] - b.x, event_xy[1] - b.y) / NM
    if d_nm > RAID_RESERVE * spec.combat_radius_nm:
        return False, f"{d_nm:.0f} nm from {b.name} is too far for your squadron"
    if squadron.available - committed < 2:
        return False, f"{squadron.name} has no free pair left"
    return True, ""
