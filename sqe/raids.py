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
ASSET_HIT = 0.20              # health a supply site or garrison loses per aircraft that gets through
SECTOR_HIT = 4.0              # friendly sector strength lost per aircraft that gets through
GARRISON_SHIELD = 0.25        # a field's garrison takes this share off the damage its defences would suffer


def raider_wings(state, kind: str = "field", budget: bool = True) -> list:
    """[(wing, type)] of the enemy wings that can send a raid now: 2+ serviceable aircraft, field not cratered, sorties left in the day's budget.
    Bombers (Su-24M) are preferred against fields and supply sites, Su-25s against troops and garrisons."""
    pref = ("Su_25", "Su_24M") if kind in ("garrison", "sector") else ("Su_24M", "Su_25")
    out = []
    for w in state.enemy_air:
        a = state.assets.get(w.base_asset_id)
        if w.available < 2 or a is None or a.destroyed or (budget and not redair.can(state, w.base_asset_id, 2)):
            continue
        t = next((t for t in pref if t in w.types), None)
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
    return "field" if not aim else "sector" if aim.startswith("sector:") else "garrison" if aim.startswith("bgar_") else "supply"


def describe(state, base, aim: str = "") -> str:
    k = aim_kind(aim)
    if k == "field":
        return f"Intercept a raid on {base.name}"
    if k == "sector":
        return f"Intercept an air attack on friendly troops: {state.ground['names'][int(aim.split(':')[1])]}"
    a = state.blue_assets[aim]
    return f"Intercept an air attack on the {a.name}" if k == "garrison" else f"Intercept a raid on the {a.name}"


def _reach(state, kind: str, x: float, y: float, budget: bool = True):
    """(distance nm, wing, type) of the nearest wing that can reach (x, y) with a raid of this kind, or None."""
    from .loadouts import ENEMY_RADIUS_NM
    best = None
    for w, t in raider_wings(state, kind, budget):
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
            if (kind == "garrison") != (a.id.startswith("bgar_")):
                continue
            home = state.bases.get(a.id.split("_", 1)[1]) if a.id.split("_", 1)[1] in state.bases else _nearest_field(state, a.x, a.y)
            if home is None or home.id in fallen:
                continue
            r = _reach(state, kind, a.x, a.y)
            if r is None:
                continue
            out.append((home, a.id, max(0.15, 1.0 - r[0] / 330.0) * (0.5 + 0.5 * a.health) * (a.value / 5.0)))
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


def pick_target(state, rng: random.Random):
    ws = target_weights(state)
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
    ws = candidates(state, kind) or (candidates(state, "field") if kind != "field" else [])
    if not ws:
        return None
    ws = shy(state, d, ws)
    base, aim, _ = _weighted(rng, ws)
    return base, aim


PATRIOT_NM = 40          # v0.41.20: a full-strength field's Patriot covers its own field and what lies this close to it
FLEET_NM = 70            # v0.41.31: ...and the carrier group's SM-2 reach (measured: CAP pairs killed 51-67 nm out; mission_builder.FLEET_RAID_AVOID_NM)
HAWK_NM = 25             # ...and a field's HAWK battery (v0.41.30: every full-strength field has one, not only yours)


def shy(state, d, ws: list) -> list:
    """v0.41.20: no needless banzai for red's raids. On Normal and Hard a raid's pick shies from targets under a full Patriot (Hard: also under
    your home field's HAWK); the weights drop by the level's "soft" factor. Easy's red does not care. Nothing is ruled out outright."""
    from . import redair
    doc = redair.doctrine(d)
    if doc["soft"] >= 1.0:
        return ws
    fields = [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD and getattr(b, "defense", 0.0) >= 0.6]
    from .sams import blue_battery
    hawks = [b for b in fields if blue_battery(b)["hawk"]] if doc["hawk"] else []
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
    r = _reach(state, aim_kind(aim), x, y)
    if r is not None:
        redair.spend(state, r[1].base_asset_id, int(d.raid_size[1]))


def todays_raids(state, d, rng: random.Random) -> tuple:
    """-> (objectives of the announced raids, number of surprise raids). One draw per day; the same seed gives the same answer."""
    rate = float(d.raid_rate)
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


def hit(state, base_id: str, wing, rng: random.Random, through: int | None = None, aim: str = "") -> list:
    """Bombs fall on one of our airfields, a supply site, a garrison or on friendly troops. The raiders lose a jet to the defences. Log lines."""
    b = state.bases[base_id]
    k = through if through is not None else rng.randint(1, 3)
    from .sams import covering_ad
    ad = covering_ad(state, *aim_xy(state, aim, b))
    if wing is not None:                                # v0.41.30: a full Patriot + HAWK takes a second jet (was always one)
        wing.available = max(0, wing.available - 1 - (round(ad) if through is None else 0))    # (a flown raid's real kills are counted by the debrief)
    kind = aim_kind(aim)
    if kind == "sector":
        g, i = state.ground, int(aim.split(":")[1])
        g["blue"][i] = max(0.0, g["blue"][i] - SECTOR_HIT * k)
        return [f"   {g['names'][i]}: friendly strength down to {g['blue'][i]:.0f} after the air attack"]
    if kind in ("supply", "garrison"):
        a = state.blue_assets[aim]
        a.health = max(0.0, a.health - ASSET_HIT * k)
        return [f"   {a.name} {'destroyed' if a.destroyed else f'damaged, {a.health:.0%} left'}"]
    gar = state.blue_assets.get(f"bgar_{base_id}") if getattr(state, "blue_assets", None) else None
    shield = 1.0 - GARRISON_SHIELD * (gar.health if gar is not None and not gar.destroyed else 0.0)
    if b.kind != BaseKind.CARRIER:
        b.defense = max(0.0, b.defense - BASE_LOSS * k * shield * (1.0 - 0.4 * ad))     # v0.41.30: batteries soak part of the damage (judgment call)
    sqs = sorted((s for s in state.squadrons.values() if s.base_id == base_id and s.available > 0), key=lambda s: -s.available)
    lines = [f"   bombs fell on {b.name}: its defences are down to {b.defense:.0%}" if b.kind != BaseKind.CARRIER else f"   missiles hit {b.name}"]
    if sqs:
        sq = sqs[0]
        lost = min(sq.available, rng.randint(1, 1 + k))
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
        r = _reach(state, aim_kind(aim), x, y)
        if r is None:
            continue
        wing = r[1]
        redair.spend(state, wing.base_asset_id, int(d.raid_size[1]))
        alert = sum(s.available for s in state.squadrons.values() if s.base_id == b.id) / max(1, sum(s.authorized for s in state.squadrons.values() if s.base_id == b.id))
        from .sams import covering_ad
        p_stop = min(0.95, 0.2 + 0.45 * covering_ad(state, x, y) + 0.3 * alert)       # v0.41.30: the batteries that cover the target (was the field's defense number)
        what = {"field": b.name, "supply": state.blue_assets[aim].name if aim in state.blue_assets else "", "garrison": state.blue_assets[aim].name if aim in state.blue_assets else "",
                "sector": "friendly troops in " + state.ground["names"][int(aim.split(":")[1])] if aim.startswith("sector:") else ""}[aim_kind(aim)]
        if rng.random() < p_stop:
            k = min(wing.available, rng.randint(1, 3 + round(covering_ad(state, x, y)))); wing.available -= k
            lines.append(f"Surprise raid on {what}: alert aircraft got up in time; {k} attack aircraft shot down")
        else:
            lines.append(f"Surprise raid on {what}: nobody was warned and the aircraft got through")
            lines += [x_.strip() for x_ in hit(state, b.id, wing, rng, None, aim)]
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
