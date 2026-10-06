"""The abstracted war: objective planning, AI-resolved packages (percentile roll with shown odds),
daily replenishment, and victory/defeat. Nothing here touches DCS."""
from __future__ import annotations
import math
import random
from . import threatmap as tm
from .difficulty import Difficulty
from .models import Objective, ObjectiveType, AssetKind, Role
from .packages import Package
from .state import CampaignState

ROLE_WEIGHT = {Role.STRIKE: 1.0, Role.SEAD: 0.9, Role.ESCORT: 0.6, Role.SWEEP: 0.7, Role.CAP: 0.6, Role.CAS: 1.0}


NM = 1852.0


class ObjectivePlanner:
    """Looks at the war and decides what matters today, with the FLOT rule: a target is only offered when the route to it
    does not cross an intact SAM belt in front of it; the blocking sites become DEAD objectives instead."""
    MIN_NM = 50

    def __init__(self, d=None):
        self.d = d

    def _near(self, state, a) -> bool:
        return min(math.hypot(a.x - b.x, a.y - b.y) for b in state.bases.values()) / NM < self.MIN_NM

    def _blockers(self, state, a) -> list:
        best = None
        for b in state.bases.values():
            bl = tm.blockers(state, (b.x, b.y), (a.x, a.y), a)
            if best is None or len(bl) < len(best):
                best = bl
        return best or []

    def plan(self, state: CampaignState, rng: random.Random, limit: int = 6) -> list:
        cand = []                                  # (priority, objective, blockers, too_near)
        alive = lambda aid: not state.assets[aid].destroyed
        for a in state.assets.values():
            if a.destroyed:
                continue
            defenders = [x for x in a.defended_by if alive(x)]
            if a.kind in (AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT):
                pr = a.value * a.health / (1 + 0.5 * len(defenders))
                cand.append((pr, Objective("", ObjectiveType.STRIKE, a.id, pr, f"Strike {a.name}"), self._blockers(state, a), self._near(state, a)))
            elif a.kind == AssetKind.SAM and a.value >= 5:
                covered = sum(x.value for x in state.assets.values() if a.id in x.defended_by and not x.destroyed) / 3.0
                pr = a.value * a.health + covered
                cand.append((pr, Objective("", ObjectiveType.DEAD, a.id, pr, f"Destroy {a.name}"), self._blockers(state, a), self._near(state, a)))
            elif a.kind == AssetKind.ARMOR:
                pr = a.value * a.health * 1.4
                cand.append((pr, Objective("", ObjectiveType.CAS, a.id, pr, f"Close air support against {a.name}"), [], False))
            elif a.kind == AssetKind.AIRFIELD:
                w = state.enemy_air_at(a.id)
                if w and w.available > 0:
                    pr = a.value * 1.2 * (w.available / max(1, w.authorized))
                    cand.append((pr, Objective("", ObjectiveType.COUNTER_AIR, a.id, pr, f"Counter-air at {a.name} ({w.available} aircraft)"),
                                 self._blockers(state, a), self._near(state, a)))
        blocking = {x.id for c in cand for x in c[2]}                  # sites that stand in front of something else
        pool = []
        for pr, o, bl, near in cand:
            if bl or near:
                continue
            if o.type == ObjectiveType.DEAD and o.target_id in blocking:
                pr *= 1.8                                              # clear the belt first
            pool.append((pr, o))
        if len([1 for _, o in pool if o.type != ObjectiveType.BARCAP]) < 4:      # nothing left but close-in targets: allow them
            pool += [(pr * (1.8 if (o.type == ObjectiveType.DEAD and o.target_id in blocking) else 1.0), o) for pr, o, bl, near in cand if near and not bl]
        fleet = next((b for b in state.bases.values() if b.kind.value == "CARRIER"), None)
        bw = next((x for x in state.enemy_air if "Tu_22M3" in x.types and x.available >= 2 and not state.assets[x.base_asset_id].destroyed), None)
        if fleet and bw and self.d is not None and self.d.bomber_policy != "none":
            t = totals(state)
            if self.d.bomber_policy == "normal" or t["enemy_air"] < 0.45 or t["c2"] < 0.5:     # regional powers use bombers only when losing badly
                pr = 6.0 + 0.3 * bw.available
                pool.append((pr, Objective("", ObjectiveType.FLEET_DEFENSE, fleet.id, pr, f"Intercept a bomber raid on {fleet.name}")))
        if fleet:
            tot = sum(x.available for x in state.enemy_air)
            auth = sum(x.authorized for x in state.enemy_air) or 1
            pr = 3.0 + 4.0 * tot / auth
            pool.append((pr, Objective("", ObjectiveType.BARCAP, fleet.id, pr, f"Combat air patrol over {fleet.name}")))
        scored = sorted(((s * rng.uniform(0.9, 1.1), o) for s, o in pool), key=lambda t: t[0], reverse=True)
        picked, seen = [], set()
        for s, o in scored:                    # one of each objective type first, for variety
            if o.type not in seen and len(picked) < limit:
                picked.append((s, o)); seen.add(o.type)
        for s, o in scored:
            if len(picked) >= limit:
                break
            if (s, o) not in picked:
                picked.append((s, o))
        picked.sort(key=lambda t: t[0], reverse=True)
        out = []
        for i, (_, o) in enumerate(picked, 1):
            o.id = f"obj-d{state.day}-{i}"
            out.append(o)
        return out


def chance(rng: random.Random, p: float, variance: float) -> bool:
    """Percentile roll. variance 1 = a straight d100 against p; 0 = deterministic (succeeds if p >= 50%)."""
    u = variance * rng.random() + (1 - variance) * 0.5
    return u < p


def count_roll(rng, n: int, p: float, variance: float) -> int:
    if variance <= 0.001:
        return int(round(n * p))
    return sum(1 for _ in range(n) if rng.random() < p)


class WarSimulator:
    def __init__(self, d: Difficulty, rng: random.Random | None = None):
        self.d, self.rng = d, rng or random.Random()

    def odds(self, state: CampaignState, pkg: Package) -> tuple:
        obj = pkg.objective
        strength = sum(f.count * ROLE_WEIGHT[f.role] for f in pkg.flights)
        has_sead = any(f.role == Role.SEAD for f in pkg.flights)
        sam = 0.0
        if obj.type not in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            t = state.assets[obj.target_id]
            sam = sum(1.5 * state.assets[x].health for x in t.defended_by if not state.assets[x].destroyed)
            if t.kind == AssetKind.SAM and not t.destroyed:
                sam += 1.5 * t.health
            sam *= 0.6 + 0.8 * self.d.iads
            if has_sead:
                sam *= 0.5
        air = 0.05 * sum(w.available for w in state.enemy_air) * (0.6 + 0.6 * self.d.iads)
        defense = sam + air
        return (strength / (strength + defense) if strength + defense else 0.0), strength, defense

    def _resolve_raid(self, state: CampaignState, pkg: Package) -> dict:
        d, rng = self.d, self.rng
        bw = state.enemy_air_at(pkg.extra.get("bomber_wing", "")) if pkg.extra else None
        strength = sum(f.count * ROLE_WEIGHT[f.role] for f in pkg.flights)
        esc = pkg.extra.get("escorts", 0)
        p = strength / (strength + 2.5 + 2.0 * d.iads + 0.4 * esc)
        ok = chance(rng, p, d.variance)
        lines = [f"{pkg.objective.description}: {'RAID STOPPED' if ok else 'RAID GOT THROUGH'} (odds {p:.0%})"]
        if bw is not None and ok:
            k = min(bw.available, rng.randint(2, 4)); bw.available -= k
            lines.append(f"   {k} bombers shot down before launching their missiles")
        elif bw is not None:
            bw.available = max(0, bw.available - 1)
            carriers = [s for s in state.squadrons.values() if state.bases[s.base_id].kind.value == "CARRIER"]
            if carriers:
                sq = rng.choice(carriers); lost = rng.randint(1, 3); sq.available = max(0, sq.available - lost)
                lines.append(f"   missiles hit the fleet: {lost} aircraft lost on deck ({sq.name})")
        for ln in lines:
            state.note(ln.strip())
        return {"success": ok, "odds": p, "lines": lines, "objective": pkg.objective.description}

    def resolve_abstract(self, state: CampaignState, pkg: Package) -> dict:
        d, rng = self.d, self.rng
        if pkg.objective.type == ObjectiveType.FLEET_DEFENSE:
            return self._resolve_raid(state, pkg)
        p, strength, defense = self.odds(state, pkg)
        success = chance(rng, p, d.variance)
        obj = pkg.objective
        lines = [f"{obj.description}: {'SUCCESS' if success else 'FAILED'} (odds {p:.0%})"]
        if obj.type != ObjectiveType.BARCAP:
            t = state.assets[obj.target_id]
            if obj.type == ObjectiveType.CAS and not success:
                state.note("   the friendly position was overrun; the column advances")
            if success:
                t.health = max(0.0, t.health - d.base_damage * (0.5 + p))
                lines.append(f"   {t.name} now at {t.health:.0%}")
                if obj.type == ObjectiveType.COUNTER_AIR:
                    w = state.enemy_air_at(t.id)
                    if w:
                        k = min(w.available, max(1, round(w.available * 0.3 * p)))
                        w.available -= k
                        lines.append(f"   {k} enemy aircraft destroyed at {t.name}")
            else:
                t.health = max(0.0, t.health - 0.1 * d.base_damage)
        elif success:
            w = max(state.enemy_air, key=lambda w: w.available, default=None)
            if w and w.available:
                k = min(w.available, 1 + int(rng.random() < 0.5))
                w.available -= k
                lines.append(f"   {k} enemy fighters shot down by the patrol")
        loss_p = d.loss_rate * 2 * (defense / (strength + defense) if strength + defense else 0.0)
        for f in pkg.flights:
            lost = count_roll(rng, f.count, loss_p, d.variance)
            if lost:
                sq = state.squadrons[f.squadron_id]
                sq.available = max(0, sq.available - lost)
                lines.append(f"   {f.callsign} lost {lost} aircraft")
        for ln in lines:
            state.note(ln.strip())
        return {"success": success, "odds": p, "lines": lines, "objective": obj.description}

    def end_day(self, state: CampaignState) -> None:
        d = self.d
        for sq in state.squadrons.values():
            if sq.available < sq.authorized:
                sq.available = min(sq.authorized, sq.available + max(1, round(sq.authorized * d.friendly_replenish)))
        for w in state.enemy_air:
            if w.available < w.authorized:
                w.available = min(w.authorized, w.available + max(1, round(w.authorized * d.enemy_replenish)))
        for a in state.assets.values():
            if 0 < a.health < 1.0:
                a.health = min(1.0, a.health + (d.sam_repair if a.kind == AssetKind.SAM else d.asset_repair))
        self.counterstrike(state)
        state.day += 1
        update_status(state)

    def counterstrike(self, state: CampaignState) -> None:
        """The enemy may hit one coalition airfield's air defences; they repair a little every day."""
        fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD"]
        ea = sum(w.available for w in state.enemy_air) / max(1, sum(w.authorized for w in state.enemy_air))
        if fields and self.rng.random() < self.d.counterstrike * ea:
            enemy = [a for a in state.assets.values() if a.kind == AssetKind.AIRFIELD and not a.destroyed]
            wts = [1.0 / (1.0 + min(math.hypot(b.x - a.x, b.y - a.y) for a in enemy) / NM / 100.0) if enemy else 1.0 for b in fields]
            b = self.rng.choices(fields, weights=wts)[0]
            before = b.defense
            b.defense = max(0.0, b.defense - self.rng.uniform(0.15, 0.40))
            state.note(f"Enemy air strike on {b.name}: air defences {before:.0%} -> {b.defense:.0%}.")
        for b in fields:
            b.defense = min(1.0, b.defense + 0.10)


def totals(state: CampaignState) -> dict:
    fa = sum(s.available for s in state.squadrons.values()); fz = sum(s.authorized for s in state.squadrons.values()) or 1
    ea = sum(w.available for w in state.enemy_air); ez = sum(w.authorized for w in state.enemy_air) or 1
    ad = [a for a in state.assets.values() if a.kind in (AssetKind.SAM, AssetKind.EWR)]
    iads = sum(a.health for a in ad) / len(ad) if ad else 0.0
    arm = [a for a in state.assets.values() if a.kind == AssetKind.ARMOR]
    armor = sum(a.health for a in arm) / len(arm) if arm else 0.0
    c2 = [a for a in state.assets.values() if a.kind == AssetKind.C2]
    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD"]
    return {"base_defense": (sum(b.defense for b in fields) / len(fields)) if fields else 1.0, "friendly_air": fa / fz, "enemy_air": ea / ez, "iads": iads, "armor": armor,
            "c2": sum(a.health for a in c2) / len(c2) if c2 else 0.0,
            "fa": fa, "fz": fz, "ea": ea, "ez": ez}


def update_status(state: CampaignState) -> str:
    t = totals(state)
    if state.status == "ACTIVE":
        if t["c2"] <= 0.05 and t["enemy_air"] < 0.15:
            state.status = "VICTORY"; state.note("VICTORY: the enemy command structure and air arm are broken.")
        elif t["friendly_air"] < 0.15:
            state.status = "DEFEAT"; state.note("DEFEAT: the coalition air component can no longer sustain operations.")
    return state.status
