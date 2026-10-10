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
from .models import Objective, ObjectiveType, BaseKind, Role

NM = 1852.0
RAID_RESERVE = 0.6            # an emergency is offered only if the event is within this share of the squadron's combat radius
BASE_LOSS = 0.06              # airfield defence lost per bomber that gets through
RAID_PRIORITY = 8.0


def _bomber_wings(state) -> list:
    return [w for w in state.enemy_air if "Su_24M" in w.types and w.available >= 2 and not state.assets[w.base_asset_id].destroyed]


def target_weights(state) -> list:
    """[(base, weight)] for our airfields a raid could go for: within reach of a bomber wing, with something to bomb, nearer and softer = likelier."""
    from .loadouts import ENEMY_RADIUS_NM
    wings = _bomber_wings(state)
    out = []
    for b in state.bases.values():
        if b.kind == BaseKind.CARRIER or not any(s.base_id == b.id and s.available > 0 for s in state.squadrons.values()):
            continue
        if b.id in (state.ground or {}).get("fallen", []):
            continue
        near = min((math.hypot(state.assets[w.base_asset_id].x - b.x, state.assets[w.base_asset_id].y - b.y) / NM for w in wings), default=None)
        if near is None or near > ENEMY_RADIUS_NM["Su_24M"] * 0.85:
            continue
        out.append((b, max(0.15, 1.0 - near / 330.0) * (0.6 + 0.8 * (1.0 - getattr(b, "defense", 0.5)))))
    return out


def pick_target(state, rng: random.Random):
    ws = target_weights(state)
    if not ws:
        return None
    tot = sum(w for _, w in ws)
    r = rng.random() * tot
    for b, w in ws:
        r -= w
        if r <= 0:
            return b
    return ws[-1][0]


def raid_objective(base) -> Objective:
    return Objective("", ObjectiveType.FLEET_DEFENSE, base.id, RAID_PRIORITY, f"Intercept a raid on {base.name}")


def todays_raids(state, d, rng: random.Random) -> tuple:
    """-> (objectives of the announced raids, number of surprise raids). One draw per day; the same seed gives the same answer."""
    rate = float(d.raid_rate)
    n = int(rate) + (1 if rng.random() < rate - int(rate) else 0)
    warned, surprise = [], 0
    for _ in range(n):
        if rng.random() < d.raid_surprise:
            surprise += 1
            continue
        b = pick_target(state, rng)
        if b is not None and all(o.target_id != b.id for o in warned):
            o = raid_objective(b)
            o.id = f"obj-d{state.day}-r{len(warned) + 1}"
            warned.append(o)
    return warned, surprise


def hit(state, base_id: str, wing, rng: random.Random, through: int | None = None) -> list:
    """Bombs fall on one of our airfields: its defence drops, parked aircraft burn, and the raiders lose a jet to the defences. Log lines."""
    b = state.bases[base_id]
    k = through if through is not None else rng.randint(1, 3)
    if wing is not None:
        wing.available = max(0, wing.available - 1)
    if b.kind != BaseKind.CARRIER:
        b.defense = max(0.0, b.defense - BASE_LOSS * k)
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
        b = pick_target(state, rng)
        wing = max(_bomber_wings(state), key=lambda w: w.available, default=None)
        if b is None or wing is None:
            continue
        alert = sum(s.available for s in state.squadrons.values() if s.base_id == b.id) / max(1, sum(s.authorized for s in state.squadrons.values() if s.base_id == b.id))
        p_stop = min(0.9, 0.25 + 0.35 * b.defense + 0.3 * alert)
        if rng.random() < p_stop:
            k = min(wing.available, rng.randint(1, 3)); wing.available -= k
            lines.append(f"Surprise raid on {b.name}: alert aircraft got up in time; {k} bombers shot down")
        else:
            lines.append(f"Surprise raid on {b.name}: nobody was warned and the bombers got through")
            lines += [x.strip() for x in hit(state, b.id, wing, rng)]
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
