"""The abstracted war: objective planning, AI-resolved packages (percentile roll with shown odds),
daily replenishment, and victory/defeat. Nothing here touches DCS."""
from __future__ import annotations
import math
import random
from . import threatmap as tm
from . import ground, theatres, tempo, story
from . import raids, sams, ecm, airwings
from .raids import hit as raids_hit
from .difficulty import Difficulty
from .models import SEAD_AIMS, Objective, ObjectiveType, AssetKind, Role
from .packages import Package
from .state import CampaignState
from .loadouts import ENEMY_FIGHTERS

ROLE_WEIGHT = {Role.STRIKE: 1.0, Role.SEAD: 0.9, Role.TARCAP: 0.6, Role.ESCORT: 0.7, Role.SWEEP: 0.7, Role.CAP: 0.6, Role.CAS: 1.0}


def _suppressor(f, pkg=None) -> bool:
    """A flight that works on the radars: a SEAD flight. A JSOW flight is the DEAD strike of a Standoff DEAD package (radars, launchers and
    Tors); in any other package (older saves: the SEAD package's JSOW slingers) it works on the radars."""
    if getattr(f, "kit", "") == "JSOW":
        return pkg is None or pkg.objective.aim != "STANDOFF"
    return f.role == Role.SEAD


GATE_VARIANTS = ("SA-2", "SA-3", "SA-6", "SA-11", "SA-10")    # v0.41.19: medium / long-range SAMs: they get a Standoff DEAD, and they gate strikes


def long_range_site(state, site) -> bool:
    """A site that gets a Standoff DEAD package (HARMs and JSOWs), not the SEAD then Close DEAD pair. v0.41.19: every medium / long-range site
    (GATE_VARIANTS): a Close DEAD sends GBU jets over the site, and a radar or launcher that survives the SEAD meets them close in (the Gudauta
    SA-6 in the v0.41.14 run). Before: only a site that is, or sits under, a live SA-10."""
    import math
    from . import threatmap as tm
    if site.variant in GATE_VARIANTS and not site.destroyed:
        return True
    live = lambda a: a.variant in tm.UMBRELLA_VARIANTS and not a.destroyed and not a.suppressed       # a suppressed SA-10 has no radars to shoot with
    return live(site) or any(live(a) and a.id != site.id and math.hypot(a.x - site.x, a.y - site.y) <= tm.UMBRELLA_KM * 1000 for a in state.assets.values())


def covering_sams(state, a) -> list:
    """v0.41.19: the strike gate. Live medium / long-range SAM sites (GATE_VARIANTS, its own cluster included) whose reach covers the target and
    that are not suppressed. While any is up, a strike on the target is not planned; the site gets a DEAD first (the SAM belt is rolled back,
    then the targets behind it). The v0.41.14 fuel-farm strike went in under a live SA-6 and lost all four jets."""
    from . import threatmap as tm
    out = []
    for x in state.assets.values():
        if x.kind != AssetKind.SAM or x.destroyed or x.health <= ground.DOWN_HEALTH or getattr(x, "suppressed", False) or x.variant not in GATE_VARIANTS:
            continue
        if ((x.x - a.x) ** 2 + (x.y - a.y) ** 2) ** 0.5 <= GATE_REACH_NM.get(x.variant, tm.RANGE_NM.get(x.variant, 0)) * 1852:
            out.append(x)
    return out


GATE_REACH_NM = {"SA-10": 35}    # v0.41.20: the SA-10's measured reach (54-57 km in the runs), not the 48 nm ring table, as everywhere else since v0.41.14


ESCORTABLE = ("SA-2", "SA-3", "SA-6")       # v0.41.20: a HARM escort can keep these quiet over a CAS target; an SA-11 / SA-10 needs a DEAD first


def cas_cover(state, a) -> tuple:
    """v0.41.20: (gate SAMs covering a CAS target, the ones among them a SEAD escort cannot handle). `a` needs only x and y."""
    cov = covering_sams(state, a)
    return cov, [x for x in cov if x.variant not in ESCORTABLE]


FOLLOW_MAX_SITES = 2    # v0.41.158: a strike / CAS target under at most this many SA-11 / SA-10 sites goes in behind their SEAD; under more it stays DEAD-first (judgment call: two is what one gate sequence and one day's package limit can carry)
FOLLOW_GAP_MIN = 10     # a follow job starts this long after the SEAD / standoff package of its site (same gap as the Close DEAD stage)


def after_sites(obj) -> list:
    """The long-reach SAM sites a follow job (a STRIKE / CAS with `after` set) waits on."""
    return [x for x in (getattr(obj, "after", "") or "").split(",") if x]


def follow_split(cov: list) -> tuple:
    """(the follow sites, the escortable ones) for a target's covering SAMs: the sites a SEAD / standoff package must hit first, and the SA-2/3/6 a
    HARM escort handles in the package itself. Follow sites are [] when there are none or more than FOLLOW_MAX_SITES (the target stays blocked)."""
    hard = [x for x in cov if x.variant not in ESCORTABLE]
    soft = [x for x in cov if x.variant in ESCORTABLE]
    return (hard if len(hard) <= FOLLOW_MAX_SITES else []), soft


NM = 1852.0


AIR_COVER_PER_FIGHTER = 0.0765      # v0.41.136: was 0.05 per aircraft of ANY kind; red's fighters are about 65% of its jets today, so this keeps today's defence term (judgment call)


def _air_cover(state: CampaignState, iads: float) -> float:
    """The red air cover that makes a strike or a DEAD harder: its serviceable FIGHTERS only (v0.41.136, Bug B). Bombers and strike jets on the ramp
    defend nothing, so adding them to the red order of battle (the striker zerg) no longer makes the whole war harder."""
    return AIR_COVER_PER_FIGHTER * sum(w.available_of(ENEMY_FIGHTERS) for w in state.enemy_air) * (0.6 + 0.6 * iads)


class ObjectivePlanner:
    """Looks at the war and decides what matters today, with the FLOT rule: a target is only offered when the route to it
    does not cross an intact SAM belt in front of it; the blocking sites become DEAD objectives instead."""
    def __init__(self, d=None):
        self.d = d

    @staticmethod
    def _open(state, a) -> bool:
        """Depth tiers: tiers up to (front + 2) are open for tasking, so the deep targets come late in a campaign."""
        return a.tier <= state.front + 2

    def _garrison_cover(self, state, a) -> list:
        """The long-range SAM sites (the kind a SEAD / DEAD package is sent to) whose ring covers a dug-in garrison and that can be tasked now. While any is
        alive the garrison is not offered as a CAS job: the A-10s would fly into the whole cluster (and the site's Tors and Shilkas, which are never DEAD
        targets themselves, are why only the long-range sites count)."""
        out = []
        for x in state.assets.values():
            if x.kind != AssetKind.SAM or x.destroyed or x.id.startswith("fsam_") or x.value < 5 or not self._open(state, x):
                continue
            r = tm.RANGE_NM.get(x.variant, 0)
            if r >= 10 and ((x.x - a.x) ** 2 + (x.y - a.y) ** 2) ** 0.5 <= r * 1852:
                out.append(x)
        return out

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
            if a.health <= ground.DOWN_HEALTH and a.kind in (AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT, AssetKind.SAM) and ground.active(state):
                continue                                   # v0.41.145: down for planning (a threshold, not the last vehicle): not hunted, it mends on its own
            locked = not self._open(state, a)
            defenders = [x for x in a.defended_by if alive(x)]
            if a.kind in (AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT):
                pr = a.value * a.health / (1 + 0.5 * len(defenders))
                cov = covering_sams(state, a)
                o_ = Objective("", ObjectiveType.STRIKE, a.id, pr, f"Strike {a.name}")
                fol, soft = follow_split(cov)
                if a.kind in (AssetKind.FUEL, AssetKind.DEPOT) and cov and all(x.variant in ESCORTABLE for x in cov):
                    # v0.41.144: a supply site under live SA-2/3/6 goes out with a HARM escort (as CAS does, v0.41.20)
                    o_.aim = "SEAD"
                    o_.description += " (with a SEAD escort)"
                    cov = []
                elif fol and (a.kind in (AssetKind.FUEL, AssetKind.DEPOT) or not soft):
                    # v0.41.158: under one or two SA-11 / SA-10 sites it goes in behind their SEAD (offered only when the day's plan has that SEAD / standoff job, see _add_followers)
                    o_.after = ",".join(x.id for x in fol)
                    o_.description += f", behind the SEAD on {' and '.join(x.name for x in fol)}"
                    if soft:
                        o_.aim = "SEAD"                                  # and the SA-2/3/6 round it get the HARM escort, as above
                        o_.description += " (with a SEAD escort)"
                    cov = []
                cand.append((pr, o_, self._blockers(state, a) + cov, locked))
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
                    if not zi["engaged"]:                            # v0.41.143: also a column our force stands facing across the line
                        continue
                    pr *= 0.7 + 0.6 * zi["pressure"]                 # the harder Red is pressing, the more urgent
                    what = f"Close air support: {zi['name']} (enemy {zi['red']:.0f}, friendly {zi['blue']:.0f})"
                sz = ground.sector_of(state, a.id)
                if sz is not None:                                   # v0.41.102: a red forward garrison: the harder Red presses in its sector, the more it matters
                    zi = ground.info(state, sz)
                    if zi["blue"] < ground.MIN_FORCE or zi["red"] < ground.MIN_FORCE:      # nothing of ours near it, or red does not hold the sector: not a job for today
                        continue
                    pr *= 0.7 + 0.6 * zi["pressure"]
                    what = f"Close air support: dislodge the enemy forward position, {zi['name']}"
                bl = self._garrison_cover(state, a) if a.variant == "GARRISON" else []        # a dug-in garrison sits under its sites' umbrella: SEAD / DEAD goes first
                # v0.41.20: no needless banzai. A CAS target under a live SA-2/3/6 goes out only with a SEAD escort (aim "SEAD": packages.py
                # requires the HARM flight or postpones the job); under a live SA-11 / SA-10 it is blocked and that site gets a DEAD first.
                cov, hard = cas_cover(state, a)
                fol, soft = follow_split(cov)
                if not fol:
                    bl = bl + [x for x in hard if x not in bl]
                o_ = Objective("", ObjectiveType.CAS, a.id, pr, what)
                if fol:                                              # v0.41.158: under one or two SA-11 / SA-10 sites: behind their SEAD (offered only when the day's plan has it)
                    o_.after = ",".join(x.id for x in fol)
                    o_.description += f", behind the SEAD on {' and '.join(x.name for x in fol)}"
                if soft and (not hard or fol):
                    o_.aim = "SEAD"
                    o_.description += " (with a SEAD escort)"
                cand.append((pr, o_, bl, locked))
            elif a.kind == AssetKind.AIRFIELD:
                w = state.enemy_air_at(a.id)
                if w and w.available > 0:
                    pr = a.value * 1.2 * (w.available / max(1, w.authorized))
                    cand.append((pr, Objective("", ObjectiveType.COUNTER_AIR, a.id, pr, f"Counter-air at {a.name} ({w.available} aircraft)"),
                                 self._blockers(state, a) + covering_sams(state, a), locked))
        blocking = {x.id for c in cand for x in c[2]} | {sid for c in cand for sid in after_sites(c[1])}      # sites that stand in front of something else
        pool, follows = [], []
        fsites = {sid for c in cand if not c[2] and not c[3] for sid in after_sites(c[1])}
        for pr, o, bl, locked in cand:
            if bl or locked:
                continue
            if o.type == ObjectiveType.DEAD and o.target_id in blocking:
                pr *= 1.8                                              # clear the belt first
                if o.target_id in fsites:
                    pr *= 1.4                                          # v0.41.158: and a site with a strike or CAS job waiting behind its SEAD (judgment call)
            (follows if o.after else pool).append((pr, o))
        fleet = next((b for b in state.bases.values() if b.kind.value == "CARRIER"), None)
        if fleet and self.d is not None and self.d.bomber_policy != "none":
            from . import bombers                                    # v0.41.105: the bomber wing is a trump card: safe window or desperation, never fewer than 4, 2 escorts each
            dec = bombers.decide(state, self.d)
            if dec["mode"] != "hold":
                pr = (12.0 if dec["mode"] == "desperate" else 7.0) + 0.3 * dec["n"]
                bombers.note_launch(state)
                pool.append((pr, Objective("", ObjectiveType.FLEET_DEFENSE, fleet.id, pr, f"Intercept a bomber raid on {fleet.name}")))
            else:
                bombers.note_stage(state, dec)                       # v0.41.109: the quiet day before the raid
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
        picked = self._add_followers(state, picked, sorted(((s * rng.uniform(0.9, 1.1), o) for s, o in follows), key=lambda t: t[0], reverse=True), limit, cap)
        picked = self._stage_dead(state, picked, limit)
        out = []
        for i, (_, o) in enumerate(picked, 1):
            o.id = f"obj-d{state.day}-{i}"
            out.append(o)
        return out

    def _add_followers(self, state, picked: list, follows: list, limit: int, cap: int) -> list:
        """v0.41.158: a STRIKE / CAS under one or two SA-11 / SA-10 sites goes in behind their SEAD: it is offered only when today's list already has
        the DEAD job of every one of those sites (which _stage_dead turns into a SEAD / standoff package), so those sites have their radars busy
        (or blind) when it arrives. It takes a free slot, or the place of a lower-ranked job of a type that has another one. Judgment call: the
        public SEAD sources describe suppression as temporary and partial, so the job is held (turned back) when the SEAD verdict fails."""
        valve = int(getattr(self.d, 'sead_valve', SEAD_FAIL_VALVE))
        dead_sites = {o.target_id for _, o in picked if o.type == ObjectiveType.DEAD and not o.aim}
        for s, o in follows:
            sites = after_sites(o)
            if not sites or any(sid not in dead_sites or sid not in state.assets
                                or not (long_range_site(state, state.assets[sid]) or sead_fail(state, sid) < valve) for sid in sites):
                continue
            if sum(1 for _, p in picked if p.type == o.type) >= cap:
                continue
            if len(picked) >= limit:
                per = {}
                for _, p in picked:
                    per[p.type] = per.get(p.type, 0) + 1
                weak = [(t, p) for t, p in picked if p.type != ObjectiveType.DEAD and not p.after and per[p.type] > 1 and t < s]
                if not weak:
                    continue
                picked.remove(min(weak, key=lambda t: t[0]))
            picked.append((s, o))
        picked.sort(key=lambda t: t[0], reverse=True)
        return picked

    def _stage_dead(self, state, picked: list, limit: int) -> list:
        """SEAD first. Each SEAD / DEAD job becomes two packages for the same site: a SEAD package that blinds the radars, and a DEAD package that
        goes in 25 minutes later and only if the radars are blind (see blinded_today). After SEAD_FAIL_VALVE failed days on the same site the
        combined package is offered again. The pair counts against the day's package limit: the lowest-priority other jobs make room."""
        out, extra = [], 0
        for s_, o in picked:
            if o.type == ObjectiveType.DEAD and not o.aim and long_range_site(state, state.assets[o.target_id]):
                a = state.assets[o.target_id]
                tail = f" ({a.health:.0%} left)" if a.health < 0.85 else ""
                out.append((s_, Objective("", ObjectiveType.DEAD, o.target_id, o.priority, f"Standoff DEAD: destroy {a.name}{tail}", "STANDOFF")))
            elif o.type == ObjectiveType.DEAD and not o.aim and sead_fail(state, o.target_id) < int(getattr(self.d, 'sead_valve', SEAD_FAIL_VALVE)):
                a = state.assets[o.target_id]
                tail = f" ({a.health:.0%} left)" if a.health < 0.85 else ""
                out.append((s_, Objective("", ObjectiveType.DEAD, o.target_id, o.priority, f"SEAD: suppress {a.name}{tail}", "SEAD")))
                out.append((s_, Objective("", ObjectiveType.DEAD, o.target_id, o.priority, f"Close DEAD: destroy {a.name}, once its radars are down", "DEAD")))
                extra += 1
            else:
                out.append((s_, o))
        while extra > 0 and len(out) > limit:
            for k in range(len(out) - 1, -1, -1):
                if out[k][1].type != ObjectiveType.DEAD:
                    del out[k]
                    break
            else:
                break
            extra -= 1
        return out


def chance(rng: random.Random, p: float, variance: float) -> bool:
    """Percentile roll. variance 1 = a straight d100 against p; 0 = deterministic (succeeds if p >= 50%)."""
    u = variance * rng.random() + (1 - variance) * 0.5
    return u < p


def count_roll(rng, n: int, p: float, variance: float) -> int:
    if variance <= 0.001:
        return int(round(n * p))
    return sum(1 for _ in range(n) if rng.random() < p)


SEAD_LEARN = 0.10             # each failed SEAD day on a site adds this to the next SEAD package's odds (the defence is being worn down and located)...
SEAD_LEARN_MAX = 0.40         # ...up to this much
SEAD_WEAR = 0.04              # health a failed SEAD still takes off the site
SEAD_FAIL_VALVE = 3           # days of failed SEAD on the same site before the combined SEAD + DEAD package is offered again
DEAD_STAGE_GAP_MIN = 10       # the DEAD package starts this long after the SEAD package of the same site (a radar hold covers the SEAD running late)


def sead_fail(state, site: str) -> int:
    return int(((state.raids or {}).get("sead_fail") or {}).get(site, 0))


def note_sead(state, site: str, blinded: bool) -> None:
    """Record a SEAD result for a site: today's verdict (the DEAD stage reads it) and the running count of failed days (the valve)."""
    if state.raids is None:
        state.raids = {}
    state.raids.setdefault("sead", {})[site] = bool(blinded)
    ff = state.raids.setdefault("sead_fail", {})
    ff[site] = 0 if blinded else int(ff.get(site, 0)) + 1


def sead_stage_in_plan(state, site: str, aims: tuple = ("SEAD",)) -> bool:
    """Is there a SEAD package (not scrubbed) for this site in today's plan? (`aims`: which kinds count; a follow job accepts a standoff package too.)"""
    return any(p["objective"].get("type") == "DEAD" and p["objective"].get("aim") in aims and p["objective"].get("target_id") == site
               and not (p.get("extra") or {}).get("scrub") for p in (state.plan or []))


def blinded_today(state, site: str) -> bool:
    """Are the site's radars out for the DEAD stage: blinded by a SEAD package that already went in, or by one that is in today's plan and has a
    verdict of success (the dice are cast when the day is planned, so every part of the program reads the same answer)."""
    a = state.assets.get(site)
    if a is None:
        return False
    return bool(a.suppressed or (((state.raids or {}).get("sead") or {}).get(site) and sead_stage_in_plan(state, site)))


def follow_ready(state, obj) -> bool:
    """v0.41.158: may a follow job (STRIKE / CAS with `after`) go in? Every site it waits on is gone, already blinded, or has a SEAD / standoff
    package in today's plan whose cast verdict is success (the dice are cast at planning, so the sim, the briefing and the mission builder agree)."""
    return all(site_blind_today(state, sid) for sid in after_sites(obj))


def site_blind_today(state, sid: str) -> bool:
    """For a follow job: is this long-reach site gone, already blinded, or hit today by a SEAD / standoff package with a verdict of success?"""
    a = state.assets.get(sid)
    if a is None or a.destroyed or a.suppressed:
        return True
    return bool(((state.raids or {}).get("sead") or {}).get(sid) and sead_stage_in_plan(state, sid, SEAD_AIMS))


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
            for sid in after_sites(obj):                  # v0.41.158: a follow job: the SA-11 / SA-10 sites it waits on are blinded (follow_ready), but still there
                x_ = state.assets.get(sid)
                if x_ is not None and not x_.destroyed and sid not in t.defended_by:
                    sam += 1.5 * x_.health * 0.4
            sam *= 0.6 + 0.8 * self.d.iads
            if has_sead:
                sam *= 0.5
        air = _air_cover(state, self.d.iads)
        defense = sam + air
        if obj.type == ObjectiveType.STRIKE and obj.aim == "SEAD":
            # v0.41.144: a supply strike under escortable SAM cover goes in at the SEAD flight's own chance (the salvo-size rule of sead_p: the HARMs
            # against the covering sites' weight), not worse than the plain strike odds (judgment call; the roll rates are unchanged)
            t = state.assets[obj.target_id]
            cov = covering_sams(state, t)
            s_sead = sum(f.count * ROLE_WEIGHT[Role.SEAD] for f in pkg.flights if f.role == Role.SEAD)
            site = sum((1.0 + 0.8 * self.d.iads) * x.health for x in cov)
            p_s = min(0.95, s_sead / (s_sead + site)) if (s_sead and site) else (0.95 if s_sead else 0.0)
            p_e = max(p_s, strength / (strength + defense) if strength + defense else 0.0) if cov else (strength / (strength + defense) if strength + defense else 0.0)
            return max(0.02, min(0.98, p_e + tempo.get(state, "STRIKE"))), strength, defense
        p0 = strength / (strength + defense) if strength + defense else 0.0
        return max(0.02, min(0.98, p0 + tempo.get(state, tempo.kind_of(obj.type)))), strength, defense

    def _resolve_sweep(self, state: CampaignState, pkg: Package, force: dict | None = None) -> dict:
        """A Fighter Sweep fights the enemy fighters near its area; the target itself is not attacked. Kills come off the nearest wings, which
        lowers the enemy air term (and so the losses) of the packages resolved after it."""
        import math
        d, rng = self.d, self.rng
        t = state.assets[pkg.objective.target_id]
        wings = sorted([w for w in state.enemy_air if w.available > 0 and w.base_asset_id in state.assets],
                       key=lambda w: math.hypot(state.assets[w.base_asset_id].x - t.x, state.assets[w.base_asset_id].y - t.y))[:3]
        strength = sum(f.count * ROLE_WEIGHT[f.role] for f in pkg.flights)
        red = sum(w.available for w in wings) * (0.6 + 0.6 * d.iads) * 0.25
        p = max(0.02, min(0.98, (strength / (strength + red) if strength + red else 0.0) + tempo.get(state, "AIR")))
        ok = force["success"] if force and "success" in force else chance(rng, p, d.variance)
        lines = [f"{pkg.objective.description}: {'AIR CLEARED' if ok else 'CONTESTED'} (odds {p:.0%})"]
        kills = (max(1, round(sum(f.count for f in pkg.flights) * 0.4 * p)) if ok else int(rng.random() < 0.5)) if wings else 0
        for w in wings:
            if kills <= 0:
                break
            k = min(w.available, kills); w.available -= k; kills -= k
            if k:
                lines.append(f"   {k} enemy fighters from {state.assets[w.base_asset_id].name} shot down")
        loss_p = d.loss_rate * (0.6 if ok else 1.4) * (red / (strength + red) if strength + red else 0.0)
        for f in pkg.flights:
            lost = count_roll(rng, f.count, loss_p, d.variance)
            if lost:
                sq = state.squadrons[f.squadron_id]
                sq.available = max(0, sq.available - lost)
                lines.append(f"   {f.callsign} lost {lost} aircraft")
        for ln in lines:
            state.note(ln.strip())
        return {"success": ok, "odds": p, "lines": lines, "objective": pkg.objective.description, "roll": {"success": ok}}

    def _resolve_raid(self, state: CampaignState, pkg: Package, force: dict | None = None) -> dict:
        d, rng = self.d, self.rng
        bw = state.enemy_air_at(pkg.extra.get("bomber_wing", "")) if pkg.extra else None
        strength = sum(f.count * ROLE_WEIGHT[f.role] for f in pkg.flights)
        esc = pkg.extra.get("escorts", 0)
        if pkg.extra.get("land"):           # v0.41.30: the batteries round the raid's target fight it too (sams.covering_ad, AD_RAID_WEIGHT)
            from .sams import covering_ad, AD_RAID_WEIGHT
            from .raids import aim_xy
            strength += AD_RAID_WEIGHT * covering_ad(state, *aim_xy(state, pkg.objective.aim, state.bases[pkg.objective.target_id]))
        up_, psq_ = False, None
        from . import blue_barcap
        if pkg.extra.get("land") and pkg.extra.get("bomber_wing"):        # v0.41.86: a base patrol on station on the side the raid comes from adds a pair
            wa_ = state.assets.get(pkg.extra["bomber_wing"])
            fb_ = state.bases.get(pkg.objective.target_id)
            if wa_ is not None and fb_ is not None and fb_.kind.value != "CARRIER":
                up_, psq_ = blue_barcap.patrol_up(state, rng, fb_, (wa_.x, wa_.y))
                if up_:
                    strength += blue_barcap.PATROL_RAID_WEIGHT * ROLE_WEIGHT[Role.CAP]
        nb_ = int(pkg.extra.get("bombers", 4)) if pkg.extra else 4
        p = strength / (strength + 2.5 + 2.0 * d.iads + 0.4 * esc + 0.25 * max(0, nb_ - 4))     # v0.41.155 (red zerg): a mass raid is harder to stop (judgment call)
        ok = force["success"] if force and "success" in force else chance(rng, p, d.variance)
        lines = [f"{pkg.objective.description}: {'RAID STOPPED' if ok else 'RAID GOT THROUGH'} (odds {p:.0%})"]
        if bw is not None and ok:
            k = bw.lose(pkg.extra.get("raider"), (rng.randint(2, 4) if nb_ <= 4 else max(2, round(nb_ * rng.uniform(0.4, 0.7)))) if pkg.extra.get("land") else max(1, round(pkg.extra.get("bombers", 4) * rng.uniform(0.4, 0.8))))
            lines.append(f"   {k} attack aircraft shot down before " + ("dropping their bombs" if pkg.extra.get("land") else "launching their missiles"))
            if up_ and (ln_ := blue_barcap.patrol_fight(state, rng, psq_)):
                lines.append(ln_)
        elif bw is not None and pkg.extra.get("land"):
            if nb_ <= 4:
                lines += raids_hit(state, pkg.objective.target_id, bw, rng, None, pkg.objective.aim, pkg.extra.get("raider"))
            else:                                                                  # v0.41.155: a mass raid that got through puts most of its bombers on target
                thr_ = max(2, round(nb_ * rng.uniform(0.4, 0.8)))
                bw.lose(pkg.extra.get("raider"), max(1, thr_ // 3))
                lines += raids_hit(state, pkg.objective.target_id, None, rng, thr_, pkg.objective.aim, pkg.extra.get("raider"))
        elif bw is not None:
            bw.lose(pkg.extra.get("raider"), 1)
            from . import carrier_hit
            carriers = [s for s in state.squadrons.values() if state.bases[s.base_id].kind.value == "CARRIER"]
            big_ = carrier_hit.big(state, d, rng)                        # v0.41.109: Level 3, the raid nobody flew: usually a very big deal
            if big_:
                lines += big_
            elif carriers:
                sq = rng.choice(carriers); lost = rng.randint(1, 3); sq.available = max(0, sq.available - lost)
                lines.append(f"   missiles hit the fleet: {lost} aircraft lost on deck ({sq.name})")
        for ln in lines:
            state.note(ln.strip())
        return {"success": ok, "odds": p, "lines": lines, "objective": pkg.objective.description, "roll": {"success": ok}}

    def sead_p(self, state: CampaignState, pkg: Package) -> float:
        """Odds that this package's SEAD flights blind the site's radars."""
        t = state.assets[pkg.objective.target_id]
        garrison = sum(g.health for g in state.assets.values() if g.guards == t.id and not g.destroyed)
        site = ((1.0 + 0.8 * self.d.iads) * t.health + 0.4 * garrison) * (1.0 - ecm.SITE_CUT * ecm.package_cover(pkg))
        s_sead = sum(f.count * ROLE_WEIGHT[Role.SEAD] for f in pkg.flights if _suppressor(f, pkg))        # JSOW slingers add to the overwhelm
        if not s_sead:
            return 0.0
        return min(0.95, s_sead / (s_sead + site) + min(SEAD_LEARN_MAX, SEAD_LEARN * sead_fail(state, t.id)) + tempo.get(state, "DEAD"))

    def _resolve_dead(self, state: CampaignState, pkg: Package, force: dict | None = None) -> dict:
        """SEAD and DEAD are two different jobs. The SEAD flight blinds the radars (the site is 'suppressed', not dead). The DEAD flight
        then goes in: against a blinded site it usually destroys it; against an active one it takes losses and rarely finishes it."""
        d, rng = self.d, self.rng
        t = state.assets[pkg.objective.target_id]
        sead = [f for f in pkg.flights if _suppressor(f, pkg) and f.count > 0]
        dead = [f for f in pkg.flights if f.role == Role.STRIKE and not _suppressor(f, pkg) and f.count > 0]
        garrison = sum(g.health for g in state.assets.values() if g.guards == t.id and not g.destroyed)
        site = (1.0 + 0.8 * d.iads) * t.health + 0.4 * garrison
        s_sead = sum(f.count * ROLE_WEIGHT[Role.SEAD] for f in sead)
        p_sead = self.sead_p(state, pkg)
        if pkg.objective.aim == "DEAD" and not blinded_today(state, t.id) and not (force and force.get("blinded")):
            line = f"{pkg.objective.description}: HELD - the radars were not suppressed, so the DEAD flight did not go in"
            state.note(line)
            return {"success": False, "held": True, "odds": 0.0, "lines": [line], "objective": pkg.objective.description, "roll": {"success": False, "held": True}}
        if sead:
            verdict = ((state.raids or {}).get("sead") or {}).get(t.id) if pkg.objective.aim in SEAD_AIMS else None
            blinded = force["blinded"] if force and "blinded" in force else (bool(verdict) if verdict is not None else chance(rng, p_sead, d.variance))
            note_sead(state, t.id, blinded)
        else:
            blinded = bool(t.suppressed) or blinded_today(state, t.id)               # the DEAD stage: the SEAD package already went in
        lines = [f"{pkg.objective.description}:"]
        if sead:
            lines.append(f"   SEAD: {'radars suppressed' if blinded else 'radars still emitting'} (odds {p_sead:.0%})")
        if sead and not blinded:
            t.health = max(0.05, t.health - SEAD_WEAR)      # a failed attempt still wears the site down
        if blinded and sead:
            t.suppressed = True
            t.health = max(0.05, t.health - 0.2)            # the radars and a launcher or two; the battery survives
        s_dead = sum(f.count * ROLE_WEIGHT[Role.STRIKE] for f in dead)
        air = _air_cover(state, d.iads)
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
            if getattr(f, "kit", "") == "JSOW" and not _suppressor(f, pkg):
                exposure = 0.6 if blinded else 1.0          # Standoff DEAD: released outside the long-range SAM's reach
            elif f.role == Role.STRIKE and not _suppressor(f, pkg):
                exposure = 0.5 if blinded else 1.8          # an unsuppressed site shoots at the DEAD flight
            elif _suppressor(f, pkg):
                exposure = 1.0 if blinded else 1.3
            lp = min(0.9, loss_base * exposure * (1.0 - ecm.LOSS_CUT * ecm.package_cover(pkg)) * (defense / (s_dead + s_sead + defense) if (s_dead + s_sead + defense) else 0.0))
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
        if pkg.objective.after and not follow_ready(state, pkg.objective) and not (force and force.get("blinded")):
            line = f"{pkg.objective.description}: HELD - the SAM radars were not suppressed, so the flight turned back"
            state.note(line)
            return {"success": False, "held": True, "odds": 0.0, "lines": [line], "objective": pkg.objective.description, "roll": {"success": False, "held": True}}
        if pkg.objective.type == ObjectiveType.FLEET_DEFENSE:
            return self._resolve_raid(state, pkg, force)
        if pkg.objective.type == ObjectiveType.COUNTER_AIR and pkg.objective.aim == "SWEEP":
            return self._resolve_sweep(state, pkg, force)
        if pkg.objective.type == ObjectiveType.DEAD and (any(f.role == Role.STRIKE and not _suppressor(f, pkg) for f in pkg.flights) or pkg.objective.aim in SEAD_AIMS):
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
            if sq.available < sq.authorized and not sq.reserve:
                sq.available = min(sq.authorized, sq.available + max(1, round(sq.authorized * d.friendly_replenish)))
        for w in state.enemy_air:
            if state.assets[w.base_asset_id].destroyed:             # a cratered field cannot operate or rearm: the survivors scatter or are lost
                w.scatter(0.75)
                continue
            w.replenish(max(1, round(w.authorized * d.enemy_replenish)))       # new jets for the squadrons that are not resting (v0.41.53)
        for ln in airwings.step(state, d, self.rng):
            state.note("Overnight: " + ln)
        from . import support_assets
        for ln in support_assets.step(state, self.rng):                  # v0.41.87: missing AWACS / tanker airframes come back
            state.note("Overnight: " + ln)
        for a in state.assets.values():
            if 0 < a.health < 1.0 and ground.zone_of(state, a.id) is None and not (ground.active(state) and a.kind in ground.SUPPLY_KINDS):        # v0.41.143: a front column is a sector's strength: the ground war reinforces it, it does not repair itself
                a.health = min(1.0, a.health + (d.sam_repair if a.kind == AssetKind.SAM else d.asset_repair))
        if not (state.ground or {}).get("stand_down"):                 # v0.41.164: not on a stand-down day (nothing to fly: the edge is kept)
            tempo.decay(state)                                       # v0.41.147: the squadrons' edge fades a little each night
        for a in state.assets.values():
            a.suppressed = False                                    # blinded radars come back on overnight
        for ln in self.counterstrike(state):
            state.note("Overnight: " + ln)
        for ln in sams.red_orders(state, d, self.rng) + sams.rebuild(state, d, self.rng) + sams.relocate(state, d, self.rng) + sams.retreat(state, d, self.rng):
            state.note("Overnight: " + ln)
        for ln in raids.overnight(state, d, self.rng):               # surprise raids nobody flew: alert aircraft against the bombers
            state.note("Overnight: " + ln)
        if ground.active(state):
            for ln in ground.resolve_day(state, d, self.rng):
                state.note("Overnight: " + ln)
            ground.repair_blue(state, d)
            for ln in ground.supply_repair(state):                 # v0.41.144: both sides' supply sites mend on their own timer
                state.note("Overnight: " + ln)
            for ln in ground.rebuild_blue(state, d, self.rng):
                state.note("Overnight: " + ln)
            for bid in state.ground.get("fallen", []):
                if bid in state.bases:
                    sams.set_field(state, state.bases[bid], 0.0)
        state.day += 1
        update_front(state)
        update_status(state)

    def counterstrike(self, state: CampaignState) -> list:
        """Our airfield air defences repair (by supply; see sams.blue_defence) destroyed sites are ordered or rebuilt (sams.blue_orders). (The old random
        overnight air strike is gone: Red raids are planned now, see raids.py.) Returns log lines."""
        return sams.blue_defence(state, self.d) + sams.blue_orders(state, self.d, self.rng) + sams.rebuild_blue_sites(state, self.d, self.rng)


def totals(state: CampaignState) -> dict:
    fa = sum(s.available + s.reserve for s in state.squadrons.values()); fz = sum(s.authorized for s in state.squadrons.values()) or 1
    ea = sum(w.available + w.reserve for w in state.enemy_air); ez = sum(w.authorized for w in state.enemy_air) or 1
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
        by_ground = ground.active(state) and bool(state.ground.get("victory_ids"))      # v0.41.143: victory is by ground only (jet counts no longer decide the war)
        if by_ground and ground.victory(state):
            state.status = "VICTORY"; state.note("VICTORY: the objectives are ours and the enemy has nothing left to throw at us.")
        elif not by_ground and t["c2"] <= 0.05 and t["enemy_air"] < 0.15:
            state.status = "VICTORY"; state.note("VICTORY: the enemy command structure and air arm are broken.")
        elif t["friendly_air"] < 0.15:
            state.status = "DEFEAT"; state.note("DEFEAT: the coalition air component can no longer sustain operations.")
        elif ground.fallen_count(state) >= 2:
            state.status = "DEFEAT"; state.note("DEFEAT: the front has collapsed; two of our airfields are lost.")
            for ln in story.beat(state, "lose"):
                state.note(ln)
    return state.status
