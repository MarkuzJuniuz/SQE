"""The abstracted war: objective planning, AI-resolved packages (percentile roll with shown odds),
daily replenishment, and victory/defeat. Nothing here touches DCS."""
from __future__ import annotations
import math
import random
from . import threatmap as tm
from . import ground, theatres
from . import raids, sams
from .raids import hit as raids_hit
from .difficulty import Difficulty
from .models import Objective, ObjectiveType, AssetKind, Role
from .packages import Package
from .state import CampaignState

ROLE_WEIGHT = {Role.STRIKE: 1.0, Role.SEAD: 0.9, Role.ESCORT: 0.6, Role.SWEEP: 0.7, Role.CAP: 0.6, Role.CAS: 1.0}


NM = 1852.0


class ObjectivePlanner:
    """Looks at the war and decides what matters today, with the FLOT rule: a target is only offered when the route to it
    does not cross an intact SAM belt in front of it; the blocking sites become DEAD objectives instead."""
    def __init__(self, d=None):
        self.d = d

    @staticmethod
    def _open(state, a) -> bool:
        """Depth tiers: tiers up to (front + 2) are open for tasking, so the deep targets come late in a campaign."""
        return a.tier <= state.front + 2

    def _blockers(self, state, a) -> list:
        best = None
        for b in state.bases.values():
            bl = tm.blockers(state, (b.x, b.y), (a.x, a.y), a)
            if best is None or len(bl) < len(best):
                best = bl
        return best or []

    def plan(self, state: CampaignState, rng: random.Random, limit: int = 6) -> list:
        cand = []                                  # (priority, objective, blockers, locked)
        alive = lambda aid: not state.assets[aid].destroyed
        for a in state.assets.values():
            if a.destroyed:
                continue
            locked = not self._open(state, a)
            defenders = [x for x in a.defended_by if alive(x)]
            if a.kind in (AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT):
                pr = a.value * a.health / (1 + 0.5 * len(defenders))
                cand.append((pr, Objective("", ObjectiveType.STRIKE, a.id, pr, f"Strike {a.name}"), self._blockers(state, a), locked))
            elif a.kind == AssetKind.SAM and a.value >= 5 and tm.RANGE_NM.get(a.variant, 0) >= 10:      # short-range SAMs are CAS's problem, not a SEAD/DEAD package's
                covered = sum(x.value for x in state.assets.values() if a.id in x.defended_by and not x.destroyed) / 3.0
                pr = a.value * a.health + covered
                if a.health < 0.85:                                    # SEAD blinded it or CAS thinned it, but it still stands: mop up
                    pr *= 1.5
                    desc = f"Finish off {a.name} ({a.health:.0%} left)"
                else:
                    desc = f"SEAD and DEAD: {a.name}"
                cand.append((pr, Objective("", ObjectiveType.DEAD, a.id, pr, desc), self._blockers(state, a), locked))
            elif a.kind == AssetKind.ARMOR:
                pr = a.value * a.health * 1.4
                what = f"Close air support: dislodge the {a.name}" if a.variant == "GARRISON" else f"Close air support against {a.name}"
                z = ground.zone_of(state, a.id)
                if z is not None:                                    # a front-line column: only where the sector is actually being fought over
                    zi = ground.info(state, z)
                    if not zi["contested"]:
                        continue
                    pr *= 0.7 + 0.6 * zi["pressure"]                 # the harder Red is pressing, the more urgent
                    what = f"Close air support: {zi['name']} (Red {zi['red']:.0f}, Blue {zi['blue']:.0f})"
                cand.append((pr, Objective("", ObjectiveType.CAS, a.id, pr, what), [], locked))
            elif a.kind == AssetKind.AIRFIELD:
                w = state.enemy_air_at(a.id)
                if w and w.available > 0:
                    pr = a.value * 1.2 * (w.available / max(1, w.authorized))
                    cand.append((pr, Objective("", ObjectiveType.COUNTER_AIR, a.id, pr, f"Counter-air at {a.name} ({w.available} aircraft)"),
                                 self._blockers(state, a), locked))
        blocking = {x.id for c in cand for x in c[2]}                  # sites that stand in front of something else
        pool = []
        for pr, o, bl, locked in cand:
            if bl or locked:
                continue
            if o.type == ObjectiveType.DEAD and o.target_id in blocking:
                pr *= 1.8                                              # clear the belt first
            pool.append((pr, o))
        fleet = next((b for b in state.bases.values() if b.kind.value == "CARRIER"), None)
        from . import factions
        bw = next((x for x in state.enemy_air if factions.bomber() and factions.bomber() in x.types and x.available >= 2 and not state.assets[x.base_asset_id].destroyed), None)
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
        cap = max(2, math.ceil(0.4 * limit))                   # no single job type may swamp the day (DEAD packages are big)
        per = {}
        for _, o in picked:
            per[o.type] = per.get(o.type, 0) + 1
        for s, o in scored:
            if len(picked) >= limit:
                break
            if (s, o) not in picked and per.get(o.type, 0) < cap:
                picked.append((s, o)); per[o.type] = per.get(o.type, 0) + 1
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
            sam = sum(1.5 * state.assets[x].health * (0.4 if state.assets[x].suppressed else 1.0)
                      for x in t.defended_by if not state.assets[x].destroyed)
            if t.kind == AssetKind.SAM and not t.destroyed:
                sam += 1.5 * t.health
                sam += 0.8 * sum(g.health for g in state.assets.values() if g.guards == t.id)     # a dug-in garrison makes the site harder
            sam *= 0.6 + 0.8 * self.d.iads
            if has_sead:
                sam *= 0.5
        air = 0.05 * sum(w.available for w in state.enemy_air) * (0.6 + 0.6 * self.d.iads)
        defense = sam + air
        return (strength / (strength + defense) if strength + defense else 0.0), strength, defense

    def _resolve_raid(self, state: CampaignState, pkg: Package, force: dict | None = None) -> dict:
        d, rng = self.d, self.rng
        bw = state.enemy_air_at(pkg.extra.get("bomber_wing", "")) if pkg.extra else None
        strength = sum(f.count * ROLE_WEIGHT[f.role] for f in pkg.flights)
        esc = pkg.extra.get("escorts", 0)
        p = strength / (strength + 2.5 + 2.0 * d.iads + 0.4 * esc)
        ok = force["success"] if force and "success" in force else chance(rng, p, d.variance)
        lines = [f"{pkg.objective.description}: {'RAID STOPPED' if ok else 'RAID GOT THROUGH'} (odds {p:.0%})"]
        if bw is not None and ok:
            k = min(bw.available, rng.randint(2, 4)); bw.available -= k
            lines.append(f"   {k} bombers shot down before " + ("dropping their bombs" if pkg.extra.get("land") else "launching their missiles"))
        elif bw is not None and pkg.extra.get("land"):
            lines += raids_hit(state, pkg.objective.target_id, bw, rng)
        elif bw is not None:
            bw.available = max(0, bw.available - 1)
            carriers = [s for s in state.squadrons.values() if state.bases[s.base_id].kind.value == "CARRIER"]
            if carriers:
                sq = rng.choice(carriers); lost = rng.randint(1, 3); sq.available = max(0, sq.available - lost)
                lines.append(f"   missiles hit the fleet: {lost} aircraft lost on deck ({sq.name})")
        for ln in lines:
            state.note(ln.strip())
        return {"success": ok, "odds": p, "lines": lines, "objective": pkg.objective.description, "roll": {"success": ok}}

    def _resolve_dead(self, state: CampaignState, pkg: Package, force: dict | None = None) -> dict:
        """SEAD and DEAD are two different jobs. The SEAD flight blinds the radars (the site is 'suppressed', not dead). The DEAD flight
        then goes in: against a blinded site it usually destroys it; against an active one it takes losses and rarely finishes it."""
        d, rng = self.d, self.rng
        t = state.assets[pkg.objective.target_id]
        sead = [f for f in pkg.flights if f.role == Role.SEAD]
        dead = [f for f in pkg.flights if f.role == Role.STRIKE]
        garrison = sum(g.health for g in state.assets.values() if g.guards == t.id and not g.destroyed)
        site = (1.0 + 0.8 * d.iads) * t.health + 0.4 * garrison
        s_sead = sum(f.count * ROLE_WEIGHT[Role.SEAD] for f in sead)
        p_sead = s_sead / (s_sead + site) if s_sead else 0.0
        blinded = force["blinded"] if force and "blinded" in force else chance(rng, p_sead, d.variance)
        lines = [f"{pkg.objective.description}:"]
        if sead:
            lines.append(f"   SEAD: {'radars blinded' if blinded else 'radars still emitting'} (odds {p_sead:.0%})")
        if blinded:
            t.suppressed = True
            t.health = max(0.05, t.health - 0.2)            # the radars and a launcher or two; the battery survives
        s_dead = sum(f.count * ROLE_WEIGHT[Role.STRIKE] for f in dead)
        air = 0.05 * sum(w.available for w in state.enemy_air) * (0.6 + 0.6 * d.iads)
        defense = (site * (0.35 if blinded else 1.4)) + garrison * 0.3 + air
        p_dead = s_dead / (s_dead + defense) if s_dead else 0.0
        killed = force["killed"] if force and "killed" in force else chance(rng, p_dead, d.variance)
        if dead:
            if killed:
                before = t.health
                t.health = max(0.0, t.health - (1.0 if blinded else 0.45))
                lines.append(f"   DEAD: {t.name} {'destroyed' if t.destroyed else f'damaged, {t.health:.0%} left'} (odds {p_dead:.0%})")
            else:
                t.health = max(0.0, t.health - 0.05)
                lines.append(f"   DEAD: attack failed (odds {p_dead:.0%})")
        success = (killed if dead else blinded)
        loss_base = d.loss_rate * 2
        for f in pkg.flights:
            if f.tag:
                continue
            exposure = 1.0
            if f.role == Role.STRIKE:
                exposure = 0.5 if blinded else 1.8          # an unsuppressed site shoots at the DEAD flight
            elif f.role == Role.SEAD:
                exposure = 1.0 if blinded else 1.3
            lp = min(0.9, loss_base * exposure * (defense / (s_dead + s_sead + defense) if (s_dead + s_sead + defense) else 0.0))
            n_lost = count_roll(rng, f.count, lp, d.variance)
            if n_lost:
                sq = state.squadrons[f.squadron_id]
                sq.available = max(0, sq.available - n_lost)
                lines.append(f"   {f.callsign} lost {n_lost} aircraft")
        for ln in lines:
            state.note(ln.strip())
        return {"success": success, "odds": p_dead if dead else p_sead, "lines": lines, "objective": pkg.objective.description,
                "roll": {"success": success, "blinded": blinded, "killed": killed, "dead": bool(dead)}}

    def resolve_abstract(self, state: CampaignState, pkg: Package, force: dict | None = None) -> dict:
        d, rng = self.d, self.rng
        if pkg.extra.get("scrub"):                       # scrubbed for weather: it never flew, so nothing happens to the target
            state.note(f"Package #{pkg.number} ({pkg.objective.description}) was scrubbed: {pkg.extra['scrub']}")
            return {"success": False, "scrubbed": True, "odds": 0.0, "lines": [f"{pkg.objective.description}: SCRUBBED - {pkg.extra['scrub']}"],
                    "objective": pkg.objective.description, "roll": {"success": False}}
        if pkg.objective.type == ObjectiveType.FLEET_DEFENSE:
            return self._resolve_raid(state, pkg, force)
        if pkg.objective.type == ObjectiveType.DEAD and any(f.role == Role.STRIKE for f in pkg.flights):
            return self._resolve_dead(state, pkg, force)
        p, strength, defense = self.odds(state, pkg)
        success = force["success"] if force and "success" in force else chance(rng, p, d.variance)
        obj = pkg.objective
        lines = [f"{obj.description}: {'SUCCESS' if success else 'FAILED'} (odds {p:.0%})"]
        if obj.type != ObjectiveType.BARCAP:
            t = state.assets[obj.target_id]
            z = ground.zone_of(state, t.id) if obj.type == ObjectiveType.CAS else None
            if obj.type == ObjectiveType.CAS and not success:
                if z is not None:
                    ground.blue_losses(state, t.id, 1, 4)
                    state.note("   the friendly position was hard pressed")
                else:
                    state.note("   the friendly position was overrun; the column advances")
            if success:
                t.health = max(0.0, t.health - d.base_damage * (0.5 + p) * (ground.AIR_EFFECT if z is not None else 1.0))
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
        return {"success": success, "odds": p, "lines": lines, "objective": obj.description, "roll": {"success": success}}

    def end_day(self, state: CampaignState) -> None:
        d = self.d
        sams.track(state)                                           # the day each SAM site went down (it can be rebuilt later)
        for sq in state.squadrons.values():
            if sq.available < sq.authorized:
                sq.available = min(sq.authorized, sq.available + max(1, round(sq.authorized * d.friendly_replenish)))
        for w in state.enemy_air:
            if state.assets[w.base_asset_id].destroyed:             # a cratered field cannot operate or rearm: the survivors scatter or are lost
                w.available = int(w.available * 0.75)
                continue
            if w.available < w.authorized:
                w.available = min(w.authorized, w.available + max(1, round(w.authorized * d.enemy_replenish)))
        for a in state.assets.values():
            if 0 < a.health < 1.0:
                a.health = min(1.0, a.health + (d.sam_repair if a.kind == AssetKind.SAM else d.asset_repair))
        for a in state.assets.values():
            a.suppressed = False                                    # blinded radars come back on overnight
        for ln in self.counterstrike(state):
            state.note("Overnight: " + ln)
        for ln in sams.rebuild(state, d, self.rng) + sams.relocate(state, d, self.rng):
            state.note("Overnight: " + ln)
        for ln in raids.overnight(state, d, self.rng):               # surprise raids nobody flew: alert aircraft against the bombers
            state.note("Overnight: " + ln)
        if ground.active(state):
            for ln in ground.resolve_day(state, d, self.rng):
                state.note("Overnight: " + ln)
            ground.repair_blue(state, d)
            for bid in state.ground.get("fallen", []):
                if bid in state.bases:
                    state.bases[bid].defense = 0.0
        state.day += 1
        update_front(state)
        update_status(state)

    def counterstrike(self, state: CampaignState) -> list:
        """Our airfield air defences repair (by supply; see sams.blue_defence) and a strong field lends a battery to the weakest. (The old random
        overnight air strike is gone: Red raids are planned now, see raids.py.) Returns log lines."""
        return sams.blue_defence(state, self.d)


def totals(state: CampaignState) -> dict:
    fa = sum(s.available for s in state.squadrons.values()); fz = sum(s.authorized for s in state.squadrons.values()) or 1
    ea = sum(w.available for w in state.enemy_air); ez = sum(w.authorized for w in state.enemy_air) or 1
    ad = [a for a in state.assets.values() if a.kind in (AssetKind.SAM, AssetKind.EWR)]
    iads = sum(a.health for a in ad) / len(ad) if ad else 0.0
    arm = [a for a in state.assets.values() if a.kind == AssetKind.ARMOR and a.variant != "GARRISON"]
    armor = sum(a.health for a in arm) / len(arm) if arm else 0.0
    c2 = [a for a in state.assets.values() if a.kind == AssetKind.C2]
    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD"]
    return {"base_defense": (sum(b.defense for b in fields) / len(fields)) if fields else 1.0, "friendly_air": fa / fz, "enemy_air": ea / ez, "iads": iads, "armor": armor,
            "c2": sum(a.health for a in c2) / len(c2) if c2 else 0.0,
            "fa": fa, "fz": fz, "ea": ea, "ez": ez}


FRONT_STALL_DAYS = 14        # a stalled front breaks anyway: the enemy line buckles
FRONT_MIN_DAYS = 4           # the front never jumps two stages in a week


def tier_health(state: CampaignState, tier: int) -> float:
    """Mean health of the combat assets (SAMs and ground forces) of one tier; 0 when there are none."""
    xs = [a.health for a in state.assets.values() if a.tier <= tier and a.kind in (AssetKind.SAM, AssetKind.ARMOR) and ground.zone_of(state, a.id) is None]
    return sum(xs) / len(xs) if xs else 0.0


def update_front(state: CampaignState) -> bool:
    """The front advances when the tier now in play is broken (its SAMs and ground forces average 30% or less), or after a long stall.
    Destroyed assets stay destroyed, so progress always sticks. Returns True when the front moved."""
    state.front_days += 1
    if state.front >= 2 or state.status != "ACTIVE":
        return False
    broken = tier_health(state, state.front + 2) <= 0.30 and state.front_days >= FRONT_MIN_DAYS
    if broken or state.front_days >= FRONT_STALL_DAYS:
        state.front += 1
        state.front_days = 0
        state.note(f"THE FRONT ADVANCES: {'the enemy line is broken' if broken else 'the enemy line buckles'}. "
                   f"New targets are open: {theatres.active()['front_names'][state.front]}.")
        return True
    return False


def update_status(state: CampaignState) -> str:
    t = totals(state)
    if state.status == "ACTIVE":
        if t["c2"] <= 0.05 and t["enemy_air"] < 0.15:
            state.status = "VICTORY"; state.note("VICTORY: the enemy command structure and air arm are broken.")
        elif t["friendly_air"] < 0.15:
            state.status = "DEFEAT"; state.note("DEFEAT: the coalition air component can no longer sustain operations.")
        elif ground.fallen_count(state) >= 2:
            state.status = "DEFEAT"; state.note("DEFEAT: the front has collapsed; two of our airfields are lost.")
    return state.status
