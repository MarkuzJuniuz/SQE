"""Objective -> package. Threat-sized, joint only when sound, real callsigns, flights of 2 or 4."""
from __future__ import annotations
import copy
import math
import random
from dataclasses import dataclass, field, asdict
from . import runways, threat
from . import threatmap as tm
from .loadouts import CBU_JETS, ENEMY_FIGHTERS, ENEMY_RADIUS_NM, EWR_KIT_ORDER, JSOW_PER_JET, PEN_PER_JET, PEN_REACH, SLAM_PER_JET
from .aircraft import AIRCRAFT, AWACS_FOR, TANKER_FOR, RECOVERY_TANKER, STRIKE_CONDITIONAL
from .models import AssetKind, Objective, ObjectiveType, Role, BaseKind, RefuelMethod
from .state import CampaignState

NM = 1852.0
MAX_FLIGHT = 4
CLUSTER_NM, SALVO_4_NEIGHBOURS, SALVO_8_NEIGHBOURS = 25, 2, 4     # judgment calls (v0.41.82): radius, neighbours for a 4-ship first / both HARM flights
CARRIER_PLAYER_FLIGHT_MAX = 2        # catapult spots are limited; keep the player's cat-start flight small
PLAYER_ROLE_PREFERENCE = {Role.STRIKE: 5, Role.SEAD: 4, Role.TARCAP: 3, Role.ESCORT: 2, Role.SWEEP: 2, Role.CAP: 1, Role.CAS: 0}
JTAC_OBJECTIVES = {ObjectiveType.CAS}


class NoPlayerSlot(Exception):
    pass


@dataclass
class Slot:
    role: Role
    size: int
    required: bool = True
    only_if_defended: bool = False
    tag: str = ""                      # "" | HAVCAP | BASE_BARCAP (support flights: AI only)
    kit: str = ""                      # "" | JSOW | SLAM | PEN (a strike slot that only JSOW- / SLAM-ER- / JSOW-C-capable jets fill, see loadouts.JSOW_PER_JET, SLAM_PER_JET, PEN_PER_JET)
    only: str = ""                     # S60: "" | an airframe name: only that airframe fills the slot (the F-16 in the JSOW slot of an EWR strike; the Hornet flies SLAM-ER there)
    land: bool = False                 # v0.41.256: a land-based squadron fills it when one reaches (the fleet raid's USAF share), long-range fighters first; any squadron when none does


TEMPLATES = {
    ObjectiveType.STRIKE: [Slot(Role.STRIKE, 4), Slot(Role.TARCAP, 2), Slot(Role.SEAD, 2, False, True)],
    # SEAD only blinds the radars; the DEAD flight (the strikers) kills the site right behind it. Both fly in the same package.
    ObjectiveType.DEAD: [Slot(Role.SEAD, 2), Slot(Role.STRIKE, 4), Slot(Role.TARCAP, 2)],
    ObjectiveType.COUNTER_AIR: [Slot(Role.SWEEP, 4), Slot(Role.STRIKE, 2)],       # v0.41.313 (XO 2026-11-06): the strikers are the point of the job (the ramp), so the pair is required; the Fighter Sweep has its own path (is_sweep)
    ObjectiveType.BARCAP: [Slot(Role.CAP, 2), Slot(Role.CAP, 2, False)],
    ObjectiveType.CAS: [Slot(Role.CAS, 4), Slot(Role.TARCAP, 2, False), Slot(Role.SEAD, 2, False, True)],
    ObjectiveType.FLEET_DEFENSE: [Slot(Role.CAP, 4), Slot(Role.CAP, 2, False), Slot(Role.SWEEP, 2, False)],
}
_FLEET = (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE)
# v0.41.27: AI-only job types (XO). They are planned, listed under "All squadrons" and played out by the war sim, but never offered to you
# and never folded into your mission (fleet / raid packages never were): their routes and fight circles don't follow the SAM rules yet
# (BARCAP jets wandered inland over red without a single scramble). They come back one at a time, the bomber intercept first.
AI_ONLY = (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE)


def carrier_raid(st, obj) -> bool:
    """v0.41.107: the bomber raid on the carrier (target is the carrier itself): the one fleet job that is a flyable SETPIECE (XO 2026-10-22)."""
    b = st.bases.get(obj.target_id)
    return obj.type == ObjectiveType.FLEET_DEFENSE and b is not None and b.kind == BaseKind.CARRIER


def ai_only(st, obj) -> bool:
    """Is this job AI-only? BARCAP is. Raid intercepts (the carrier raid and, since v0.41.303, raids on fields, supply sites and garrisons) are player-flyable."""
    if obj.type == ObjectiveType.FLEET_DEFENSE:                  # v0.41.303 (XO 2026-11-05): a raid on a field, a supply site or a garrison is player-flyable like the carrier raid
        return False
    return obj.type in AI_ONLY and not carrier_raid(st, obj)


SETPIECE_LAND_SHARE = 0.5   # v0.41.256: the part of the fleet raid's optional CAP flights that land-based squadrons fill first (judgment call; XO: the USAF wing should dispatch what it can)
SETPIECE_RATIO = 0.75       # blue CAP flights of 4 per bomber: 3 flights for 4 bombers + 8 escorts, i.e. about one blue fighter per raider (judgment call, XO: "overwhelming")
_SETPIECE_TASK = {Role.CAP: "Intercept: kill the Backfires before they reach launch range, then the escorts",
                  Role.SWEEP: "Sweep ahead of the fleet: engage the raid's escorts so the interceptors get at the bombers",
                  Role.SEAD: "Suppress the SAMs covering the raid's launch point before the interceptors go in"}
_TASK = {Role.STRIKE: "Strike target", Role.SEAD: "Suppress/destroy SAM",
         Role.TARCAP: "TARCAP: on station short of the target before the package, shoot what comes in range, do not chase; stay at least 15 minutes and until the last strike flight is off target plus 5 minutes, then home",
         Role.SWEEP: "Fighter sweep", Role.CAP: "Combat air patrol", Role.CAS: "Close air support"}
_DEAD_TASK = {Role.SEAD: "SEAD: suppress the radars ahead of the DEAD flight", Role.STRIKE: "Close DEAD: destroy the SAM site with GBUs (the SEAD package goes in ahead of you; call it off if the radars are up)"}
KIT_JETS = {"JSOW": JSOW_PER_JET, "SLAM": SLAM_PER_JET, "PEN": PEN_PER_JET}      # v0.41.298: the airframes that can fill each kit slot (S51: PEN = the F-15E's runway crater; the F-15E is in no other table, so no Standoff DEAD / counter-air slot can take it)
_KIT_TASK = {"CBU": "Counter-air strike: CBU-103 on the jets parked on the ramp", "SLAM": "Standoff Strike: AGM-84H SLAM-ER on the target from far out, released outside the fighters' reach; then home", "JSOW": "Standoff DEAD: AGM-154A on the site's radars, launchers and covering Tors, on the HARM salvo's time; stand-off release, then home",
             "PEN": "Standoff Runway Strike: AGM-154C JSOW on the middle of the runway from stand-off range, released outside the fighters' reach; then home"}
_EWR_KIT_TASK = {"PEN": "EWR strike: AGM-154C JSOW on the radar from stand-off range, released outside the fighters' reach; then home",         # S60: the kit texts of an EWR strike (not a SAM site, not a runway)
                 "JSOW": "EWR strike: AGM-154A JSOW on the radar from stand-off range, released outside the fighters' reach; then home",
                 "SLAM": "EWR strike: AGM-84H SLAM-ER on the radar from far out, released outside the fighters' reach; then home"}
_CA_JSOW_TASK = "Standoff Counter-Air: AGM-154A JSOW on the jets parked on the ramp, released from stand-off range; then home"
_SO_SEAD_TASK = "SEAD: HARMs on the site's radars and its Tors, in the same salvo as the Standoff DEAD JSOWs"
_ESC_TASK = "Escort: hold your station with the package, shoot what comes in range, do not chase; leave when the strikers are off target"
_TASK[Role.ESCORT] = _ESC_TASK
_TAG_TASK = {"HAVCAP": "HAVCAP (guards the AWACS)", "TKR_HAVCAP": "HAVCAP (guards the tanker)", "BASE_BARCAP": "BARCAP", "CARRIER_BARCAP": "BARCAP (guards the carrier group)"}
BASE_BARCAP_ENEMY_NM = 130     # v0.41.7: a land base gets a base BARCAP when an enemy fighter field is within this (an alert pair reaches it)


@dataclass
class FlightPlan:
    id: str
    callsign: str                      # "Springfield 1"; aircraft are Springfield 1-1, 1-2, ...
    role: Role
    squadron_id: str
    aircraft: str
    count: int
    base_id: str
    task: str
    is_player: bool = False
    tag: str = ""
    kit: str = ""                      # "JSOW": a JSOW slinger in a SEAD package (its loadout, route and attack differ from a plain strike)
    guard: str = ""                    # v0.41.10: a base BARCAP's guarded field (base id), when it is not the squadron's own base


@dataclass
class SupportPlan:
    slot: str
    dcs_class: str
    label: str
    altitude_ft: int
    speed_kts: int
    refuel: str | None = None
    from_carrier: bool = False


@dataclass
class Package:
    id: str
    number: int
    objective: Objective
    flights: list = field(default_factory=list)
    support: list = field(default_factory=list)
    jtac: bool = False
    jtac_laser_code: int = 1688
    start: str = "09:00"               # mission start (local time of day)
    n_def: int = 0                     # expected enemy fighters at the target
    extra: dict = field(default_factory=dict)   # mission-type extras (raid bearing, bomber count, escorts...)

    @property
    def kind(self) -> str:
        """v0.41.281 (XO 2026-11-04): the type the player sees. Every raid intercept is FLEET_DEFENSE inside (the carrier raid came first), but a raid on a field, a supply site or a
        garrison (`extra["land"]`) reads RAID_DEFENSE; only the carrier raid stays FLEET_DEFENSE."""
        t = self.objective.type.value
        return "RAID_DEFENSE" if (t == "FLEET_DEFENSE" and (self.extra or {}).get("land")) else t

    @property
    def title(self) -> str:
        """v0.41.304 (XO 2026-11-05): the name the player reads in the list: what is being defended, then the job ("Fleet Defense: Intercept"). The other jobs read as their type."""
        if (self.extra or {}).get("raid_prep"):                   # v0.41.305: a SEAD / Standoff DEAD package that opens the carrier raid's lane
            return "Fleet Defense: " + ("Standoff DEAD" if self.objective.aim == "STANDOFF" else "SEAD")
        if self.objective.type != ObjectiveType.FLEET_DEFENSE:
            return self._job_name()
        ex = self.extra or {}
        if not ex.get("land"):
            return "Fleet Defense: Intercept"
        aim = self.objective.aim or ""
        # S58 (XO 2026-11-12): no "Supply Defense". The field, its SAM site and its fuel farm are Base; the two supply depots out on the line are Depot; anything else (an old save) is Base.
        what = "Troop" if aim.startswith("sector:") else ("Garrison" if aim.startswith(("bgar_", "bfwd_")) else ("Depot" if aim.startswith("bdepot_") else "Base"))
        return f"{what} Defense: Intercept"

    def _job_name(self) -> str:
        """v0.41.306 (XO 2026-11-05: uniform Title Case names): the job's name for the list, from its type and aim."""
        o = self.objective; aim = o.aim or ""; ty = o.type
        if ty == ObjectiveType.DEAD:
            return {"SEAD": "SEAD", "STANDOFF": "Standoff DEAD", "DEAD": "Close DEAD"}.get(aim, "DEAD")
        if ty == ObjectiveType.STRIKE:
            if (o.description or "").startswith("EWR Strike"):                    # S60: before the STANDOFF test, an EWR strike is a stand-off job that keeps its name
                return "EWR Strike"
            return "Standoff Strike" if aim == "STANDOFF" else ("Runway Strike" if (o.description or "").startswith("Crater") else "Strike")
        if ty == ObjectiveType.CAS:
            return "Close Air Support: Troops in Contact" if (self.extra or {}).get("tic") else "Close Air Support"
        if ty == ObjectiveType.COUNTER_AIR:
            return "Fighter Sweep" if aim == "SWEEP" else ("Standoff Counter-Air" if aim == "STANDOFF" else "Counter-Air")
        if ty == ObjectiveType.BARCAP:
            return "Combat Air Patrol"
        return self.kind.replace("_", " ").title()

    @property
    def urgent(self) -> bool:
        """Red's raids and troops in contact are what red is doing to you now: the list draws them with a red border (v0.41.304, XO 2026-11-05: "no more hidden ones")."""
        return self.objective.type == ObjectiveType.FLEET_DEFENSE or bool((self.extra or {}).get("tic")) or bool((self.extra or {}).get("raid_prep"))

    @property
    def player_flight(self):
        return next((f for f in self.flights if f.is_player), None)

    def player_options(self, aircraft_key: str) -> list:
        spec = AIRCRAFT[aircraft_key]
        return [f for f in self.flights if f.aircraft == aircraft_key and f.role in spec.roles and not f.tag]

    def services(self) -> set:
        return {AIRCRAFT[f.aircraft].service for f in self.flights}

    @property
    def joint(self) -> bool:
        return len(self.services()) > 1

    def to_dict(self) -> dict:
        return {"id": self.id, "number": self.number, "objective": self.objective.to_dict(),
                "flights": [{**asdict(f), "role": f.role.value} for f in self.flights],
                "support": [asdict(s) for s in self.support], "jtac": self.jtac,
                "jtac_laser_code": self.jtac_laser_code, "start": self.start, "n_def": self.n_def, "extra": self.extra}

    @classmethod
    def from_dict(cls, d: dict) -> "Package":
        o = d["objective"]
        obj = Objective(o["id"], ObjectiveType(o["type"]), o["target_id"], o["priority"], o.get("description", ""), o.get("aim", ""), o.get("after", ""))
        return cls(d["id"], d["number"], obj, [FlightPlan(**{**f, "role": Role(f["role"])}) for f in d["flights"]],
                   [SupportPlan(**s) for s in d["support"]], d.get("jtac", False), d.get("jtac_laser_code", 1688),
                   d.get("start", "09:00"), d.get("n_def", 0), d.get("extra", {}))


def _next_callsign(st, sq, used: dict) -> str:
    """The squadron's next free flight name today: Viper 1 ... Viper 9. DCS flight numbers stop at 9, so a squadron that flies more
    than nine flights in a day carries on under a spare callsign of its type that no squadron owns (Python 1, Python 2 ...)."""
    from .callsigns import table
    owned = {q.callsign for q in st.squadrons.values()}
    for nm in [sq.callsign] + [c for c in table(sq.aircraft) if c not in owned]:
        if used.get(nm, 0) < 9:
            used[nm] = used.get(nm, 0) + 1
            return f"{nm} {used[nm]}"
    used[sq.callsign] = used.get(sq.callsign, 0) + 1                  # every name taken nine times over: not reachable with real unit counts
    return f"{sq.callsign} {used[sq.callsign]}"


LONG_RANGE_A2A = {"F-15C", "F-14BU"}
# S45 (XO 2026-11-11): the F-14B(U) is not lumped with the F-15C. Its AIM-54C is a long, heavy missile (a bomber-killer, fleet defence): it earns its keep on range, not in a close
# fighter fight like the Eagle's AIM-120 (public sources, firmness low: the Phoenix's published reach is about 100+ nm, the longest test shot 110 nm at a Mach 1.5 drone, 1973;
# the AIM-120's quoted reach is about 60 to 70% of that; DCS's Mk47 does not loft inside about 21 nm). It stays on the sweep list but behind every F-15C squadron (`_pick_squadron`).
SWEEP_LAST = {"F-14BU"}
CAS_JET_MIN_DEF_FLIGHTS = 99     # v0.41.214 (XO 2026-10-30): was 3. 99 = never "hot": the A-10C is the CAS master on every job and the jets only fly it when no A-10C squadron is free and in range (the Vipers were engaged at their wait point; the cure is the gate hold, below, not the airframe). v0.41.189 (was 3): jets take CAS first only when this many red defender flights can reach the target (judgment call; 2026-10-29 sim: with 1 nearly every L1 / L2 job counted as hot and the A-10Cs flew none)
CAS_JET_SWAY_NM = 400            # v0.41.188: the CAS squadron of the other kind is picked only when none of the preferred kind is free within this much of it (judgment call)
A2A_SECONDARY_NM = 400          # an F-16 / F/A-18 squadron is picked for TARCAP or escort only when no long-range shooter is within this much of it
A10_RUNIN_NM = 8                # v0.41.360 (Phase 10c part 2): an A-10C supply strike needs the site clear of every live SAM ring (>= 5 nm range) by this much, the run-in leg (the same margin `threatmap.blockers` keeps off the route). Judgment call


def is_sweep(obj) -> bool:
    """A Fighter Sweep package: offensive counterair over a target area, planned when intel expects more enemy fighters there than the
    packages' own TARCAP and escort can take (AFDP 3-01: sweeps are flown for local air superiority, as the air threat requires)."""
    return obj.type == ObjectiveType.COUNTER_AIR and obj.aim == "SWEEP"


def sweep_4ships(n_def_flights: int) -> int:
    """4-ships of sweep needed for this many enemy 2-ship flights: the fighters required beyond a 4-ship TARCAP, 4 per sweep flight."""
    return int(math.ceil(max(0, threat.fighters_required(n_def_flights) - 4) / 4))


class Ledger:
    """The jets each squadron can still be asked for. `free` is what the builder reads and spends (`ledger.free[sid] -= n`).

    v0.41.338 (campaign rules plan Phase 4): one Ledger serves a whole TURN with two launch waves. `free` = the jets ready now (wave 1); `late` = the jets that finish
    their refit by the second wave (`refit.ready_by(q, ready_min)` less `available`). `view(wave)` hands the builder a throw-away Ledger for one wave, and `settle` books what
    the builder spent in it: wave 2 spends the late jets first, so the ready ones stay for wave 1. `ready_min=None` (the plain `Ledger(state)`) means no late jets."""
    hfree = None                 # v0.41.353 (Phase 9b): the jets of the HAVCAP squadrons (`Squadron.role`), kept apart: only the AWACS / tanker guards draw them (`hroom` / `htake`); every other reader sees 0 in `free` / `late`
    hlate = None

    def __init__(self, state: CampaignState, ready_min: int | None = None):
        self.free = {sid: (0 if runways.is_closed(state, s.base_id) else s.available) for sid, s in state.squadrons.items()}      # v0.41.254: a cratered field flies nothing
        self.late = {sid: 0 for sid in self.free}
        if ready_min is not None:
            from . import refit
            for sid, s in state.squadrons.items():
                if not runways.is_closed(state, s.base_id) and s.reserve <= 0:         # a resting squadron's jets go to its reserve, not to the line
                    self.late[sid] = max(0, refit.ready_by(s, ready_min) - s.available)
        self.hfree, self.hlate = {}, {}
        for sid, s in state.squadrons.items():
            if s.role == "havcap":                                                     # guards only: out of the pools the packages, patrols and scrambles read
                self.hfree[sid], self.hlate[sid] = self.free[sid], self.late[sid]
                self.free[sid], self.late[sid] = 0, 0

    def scale(self, sids, f: float) -> None:
        """A damaged carrier deck launches fewer of its jets (carrier_hit.deck_factor): both pools shrink for these squadrons."""
        for sid in sids:
            self.free[sid] = int(self.free[sid] * f)
            self.late[sid] = int(self.late[sid] * f)

    def room(self, sid: str, wave: int) -> int:
        """Jets of a squadron a sortie of this wave can still draw: the ready ones, and in wave 2 also the late ones."""
        return self.free.get(sid, 0) + (self.late.get(sid, 0) if wave == 2 else 0)

    def take(self, sid: str, n: int, wave: int) -> bool:
        """Spend n jets of a squadron on a standing patrol or guard of this wave (v0.41.339, Phase 4b: they are planned from the turn's ledger, before the packages). Wave 2 spends the late
        jets first, so the ready ones stay for wave 1, as `settle` does. False (and nothing spent) when the squadron has not got them."""
        if self.room(sid, wave) < n:
            return False
        k = min(self.late.get(sid, 0), n) if wave == 2 else 0
        if k:
            self.late[sid] -= k
        self.free[sid] = self.free.get(sid, 0) - (n - k)
        return True

    def hroom(self, sid: str, wave: int) -> int:
        """Jets of a HAVCAP squadron a guard of this wave can still draw (0 for any other squadron)."""
        return (self.hfree or {}).get(sid, 0) + ((self.hlate or {}).get(sid, 0) if wave == 2 else 0)

    def htake(self, sid: str, n: int, wave: int) -> bool:
        """`take` for a HAVCAP squadron's guard pair: wave 2 spends the late jets first."""
        if self.hroom(sid, wave) < n:
            return False
        k = min(self.hlate.get(sid, 0), n) if wave == 2 else 0
        if k:
            self.hlate[sid] -= k
        self.hfree[sid] = self.hfree.get(sid, 0) - (n - k)
        return True

    def copy(self) -> "Ledger":
        c = Ledger.__new__(Ledger)
        c.free, c.late = dict(self.free), dict(self.late)
        c.hfree, c.hlate = dict(self.hfree or {}), dict(self.hlate or {})
        return c

    def view(self, wave: int) -> "Ledger":
        v = Ledger.__new__(Ledger)
        v.free = dict(self.free) if wave == 1 else {sid: self.free[sid] + self.late[sid] for sid in self.free}
        v.late = {sid: 0 for sid in self.free}
        return v

    def settle(self, view: "Ledger", wave: int) -> None:
        """Book what the builder spent in `view`."""
        for sid, left in view.free.items():
            have = self.free[sid] if wave == 1 else self.free[sid] + self.late[sid]
            used = have - left
            if used <= 0:
                continue
            take = 0 if wave == 1 else min(used, self.late[sid])
            self.late[sid] -= take
            self.free[sid] -= used - take


class PackageBuilder:
    def __init__(self, state: CampaignState, d=None):
        self.state, self.d = state, d
        self._tk, self._ctx = {}, (None, None)
        self.short = []                                  # v0.41.247: (role, x, y) of every slot of the day that no squadron could fill (ground.note_shortfall)
        self.missing = 0                                 # v0.41.338: the jets the REQUIRED slots of the last `build` are short of (the turn planner moves a package with some to the second wave)

    def target_xy(self, obj: Objective):
        if obj.type in _FLEET:
            b = self.state.bases[obj.target_id]
            if obj.aim:
                from . import raids
                return raids.aim_xy(self.state, obj.aim, b)
            return b.x, b.y
        a = self.state.assets[obj.target_id]
        return a.x, a.y

    def _dist_nm(self, sq_id, tx, ty) -> float:
        b = self.state.bases[self.state.squadrons[sq_id].base_id]
        return math.hypot(tx - b.x, ty - b.y) / NM

    def _tanker_ok(self, base_xy, target_xy) -> bool:
        key = (round(base_xy[0]), round(base_xy[1]), round(target_xy[0]), round(target_xy[1]))
        if key not in self._tk:
            self._tk[key] = tm.tanker_station(self.state, base_xy, target_xy) is not None
        return self._tk[key]

    def _in_range(self, sq_id, tx, ty, kit: str = "") -> bool:
        """Reach counts tanker support (x1.5) only when a safe tanker track exists, and the route must not cross a SAM belt
        in front of the target (the FLOT rule). S51: the PEN kit (no wing tanks) reaches `PEN_REACH` of the jet's combat radius."""
        sq = self.state.squadrons[sq_id]
        b = self.state.bases[sq.base_id]
        spec = AIRCRAFT[sq.aircraft]
        reach = spec.combat_radius_nm * (PEN_REACH if kit == "PEN" else 1.0) * (1.5 if self._tanker_ok((b.x, b.y), (tx, ty)) else 1.0)
        if math.hypot(tx - b.x, ty - b.y) / NM > reach:
            return False
        obj, asset = self._ctx
        if obj is not None and obj.type not in _FLEET and tm.blockers(self.state, (b.x, b.y), (tx, ty), asset):
            return False
        return True

    def _cluster_sites(self, obj) -> int:
        """Live SAM sites other than the target within CLUSTER_NM of it (v0.41.82)."""
        a = self.state.assets.get(obj.target_id)
        if a is None:
            return 0
        return sum(1 for o, _ in tm.rings(self.state) if o.id != a.id and math.hypot(o.x - a.x, o.y - a.y) / NM <= CLUSTER_NM)

    def _defended(self, obj) -> bool:
        if obj.type in _FLEET:
            return False
        a = self.state.assets[obj.target_id]
        return any(not self.state.assets[d].destroyed for d in a.defended_by)

    def _a10_supply_strike(self, obj, n_fl: int) -> bool:
        """v0.41.360 (campaign rules plan Phase 10c part 2): may an A-10C squadron fly the STRIKE slot of this job? Only a plain supply strike (fuel / depot; no aim, no follow-after: not a runway
        crater, EWR strike, Standoff Strike, strike under SEAD, Close DEAD or counter-air) where no red fighter flight can reach the target (`n_fl` = `threat.defender_flights`, the planner's own
        count, 0) and no live SAM site covers the target or its run-in: any live site of 5 nm reach or more (`threatmap.rings`, a site SEAD only blinded still counts, it comes back) within
        its ring + A10_RUNIN_NM of the target. The route to the target is checked by `_in_range` (`threatmap.blockers`) as for every strike."""
        from . import ground
        if obj.type != ObjectiveType.STRIKE or obj.aim or obj.after or n_fl != 0:
            return False
        a = self.state.assets.get(obj.target_id)
        if a is None or a.destroyed or a.kind not in ground.SUPPLY_KINDS:
            return False
        return not any(math.hypot(s_.x - a.x, s_.y - a.y) <= r_ + A10_RUNIN_NM * NM for s_, r_ in tm.rings(self.state, min_range=5))

    def _is_ewr(self, obj) -> bool:
        """S60: the objective's target is an early-warning radar."""
        a_ = self.state.assets.get(obj.target_id) if obj.type != ObjectiveType.FLEET_DEFENSE else None
        return a_ is not None and a_.kind == AssetKind.EWR

    def _slot_ok(self, aircraft: str, slot) -> bool:
        """v0.41.360: the airframes with a conditional STRIKE role (A-10C) fly a STRIKE slot only on a job `_a10_supply_strike` passed; every other slot is as before."""
        return not (slot.role == Role.STRIKE and aircraft in STRIKE_CONDITIONAL and not getattr(self, "_a10_strike", False))

    def _raid_threat_count(self, obj, extra) -> int:
        """v0.41.287 (XO 2026-11-04: "every SAM threatening the intercept line"): how many live red SAM sites threaten the carrier raid's
        intercept line (`tm.raid_inbound_sites`) -- one SEAD/DEAD 4-ship goes to each, not a fixed two (the old RAID_BLOCK_MAX). At least 1,
        so the setpiece always carries a SEAD flight even when the geometry can't be read yet (no bearing or bomber wing decided)."""
        b = self.state.bases.get(obj.target_id)
        if b is None or extra.get("bomber_wing") not in self.state.assets or extra.get("brg") is None:
            return 1
        dx, dy = extra.get("dest") or (b.x, b.y)
        return max(1, len(tm.raid_inbound_sites(self.state, (dx, dy), extra["brg"], extra["bomber_wing"])))

    # ---- slot list sized to the threat ---------------------------------------------------------------------
    def _slots(self, obj, defended, n_fl, extra=None) -> list:
        extra = extra or {}
        tmpl = TEMPLATES[obj.type]
        if obj.type == ObjectiveType.DEAD and obj.aim == "SEAD":            # SEAD first: a package that only suppresses the radars...
            tmpl = [Slot(Role.SEAD, 2), Slot(Role.SEAD, 2, False)]
        elif obj.type == ObjectiveType.DEAD and obj.aim == "DEAD":          # ...and the Close DEAD package (GBUs) that follows once they are down
            tmpl = [Slot(Role.STRIKE, 4), Slot(Role.TARCAP, 2)]
        elif obj.type == ObjectiveType.DEAD and obj.aim == "STANDOFF":      # under a long-range SAM: one package, HARMs and JSOWs together
            # Two HARM flights, both required: one on the long-range radars, one on the Tors, from the same salvo (equal weight, so the Tors are
            # busy with HARMs when the JSOWs arrive). The Standoff DEAD flight is JSOW-capable only (Hornet, Viper): no Tomcats on DEAD here.
            # v0.41.82: the HARM flights grow with the live SAM sites around the target (judgment call, no source: a bigger cluster needs a bigger salvo)
            nb = self._cluster_sites(obj)
            tmpl = [Slot(Role.SEAD, 4 if nb >= SALVO_4_NEIGHBOURS else 2), Slot(Role.STRIKE, 4, kit="JSOW"),
                    Slot(Role.SEAD, 4 if nb >= SALVO_8_NEIGHBOURS else 2)]     # the JSOW flight is picked before the second HARM flight: without it nothing is destroyed
        elif obj.type == ObjectiveType.COUNTER_AIR and obj.aim == "STANDOFF":   # v0.41.313: counter-air under air cover: the sweep flight as cover, JSOW-A Vipers or Hornets on the ramp from far out
            tmpl = [Slot(Role.SWEEP, 4), Slot(Role.STRIKE, 4, kit="JSOW")]
        elif obj.type == ObjectiveType.STRIKE and obj.aim == "STANDOFF" and self._is_ewr(obj):      # S60: an EWR strike: the kit is chosen in `build` (EWR_KIT_ORDER; none for a player's build)
            tmpl = [Slot(Role.STRIKE, 4), Slot(Role.TARCAP, 2)]
        elif obj.type == ObjectiveType.STRIKE and obj.aim == "STANDOFF":    # v0.41.298: a supply strike under heavy fighter cover: SLAM-ER Hornets, the TARCAP / escort added below
            tmpl = [Slot(Role.STRIKE, 4, kit="SLAM"), Slot(Role.TARCAP, 2)]
        elif obj.type == ObjectiveType.CAS and obj.aim == "SEAD":           # v0.41.20: CAS under a live SA-2/3/6: the HARM escort is not optional
            tmpl = [Slot(Role.CAS, 4), Slot(Role.SEAD, 2), Slot(Role.TARCAP, 2, False)]
        elif obj.type == ObjectiveType.STRIKE and obj.aim == "SEAD":        # v0.41.144: a supply strike under a live SA-2/3/6: same, the HARM escort is required
            tmpl = [Slot(Role.STRIKE, 4), Slot(Role.SEAD, 2), Slot(Role.TARCAP, 2, False)]
        if carrier_raid(self.state, obj):                                    # v0.41.107: the setpiece: every fighter flight in reach, about one blue fighter per raider
            k = max(2, math.ceil(SETPIECE_RATIO * n_fl))              # n_fl = raiders / 3 (set in build) -> k flights of 4, about one blue fighter per raider
            n_land = SETPIECE_LAND_SHARE * (k - 2)                    # v0.41.256 (XO 2026-11-03: the USAF wing gave no help): a share of the optional flights is land-based (F-15C first)
            n_land = int(n_land)
            n_sead = 0 if extra.get("prep_rec") else self._raid_threat_count(obj, extra)              # v0.41.287: one 4-ship per site that threatens the intercept line, not a fixed two (v0.41.357: none when the prep of the turn before is on record, its own packages did that job; a save with no record keeps the seats)
            return [Slot(Role.CAP, 4), Slot(Role.CAP, 4)] + [Slot(Role.CAP, 4, False, land=i < n_land) for i in range(k - 2)] + [Slot(Role.SWEEP, 2, False)] + [Slot(Role.SEAD, 4, False) for _ in range(n_sead)]
        if is_sweep(obj):                                                    # Fighter Sweep: 4-ships only, one per 4 bandits beyond the packages' own cover
            n4 = max(1, sweep_4ships(n_fl))
            return [Slot(Role.SWEEP, 4)] + [Slot(Role.SWEEP, 4, False) for _ in range(n4 - 1)]
        slots = [copy.copy(s) for s in tmpl if not (s.only_if_defended and not defended)]
        if obj.type in (ObjectiveType.STRIKE, ObjectiveType.DEAD, ObjectiveType.CAS):
            req = threat.fighters_required(n_fl)
            slots = [s for s in slots if s.role != Role.TARCAP]
            if req:
                slots.append(Slot(Role.TARCAP, min(4, req), True))            # the TARCAP. More bandits than it can take: a Fighter Sweep package (v0.40.2)
                slots.append(Slot(Role.ESCORT, 2, False))                      # v0.41.1: the escort, back (v0.40.2 dropped it with the old sweep slot)
        if obj.type not in _FLEET:
            slots.append(Slot(Role.CAP, 2, False, tag="HAVCAP"))
        return slots

    def build(self, obj: Objective, number: int, ledger: Ledger, *, for_player: bool, names: dict | None = None) -> Package:
        st = self.state
        tx, ty = self.target_xy(obj)
        self._ctx = (obj, None if obj.type in _FLEET else self.state.assets[obj.target_id])
        iads = self.d.iads if self.d else 0.5
        extra = {}
        if obj.type == ObjectiveType.FLEET_DEFENSE:
            extra = self._raid_plan(number, obj) or {}
            if not extra:
                raise NoPlayerSlot("no raid is planned for this job")        # v0.41.341: a raid with no booked plan is no package (it was one with empty extras: the KeyError in raid_spawns._raid_axis)
            n_fl = extra.get("escorts", 0) // 2
            if extra and carrier_raid(st, obj):
                extra = {**extra, "setpiece": True}                          # v0.41.107: flown from the Missions page like any job, every flight listed (v0.41.270: it folds into no other mission)
                if ((st.raids or {}).get("raid_prep") or {}).get("turn") == st.turn:      # v0.41.357 (Phase 10b part 2): the SEAD prep of the turn before is on record: the raid carries no SEAD seats of its own and the mission builds the SAM picture the prep left (`MissionBuilder._raid_prep_standing`)
                    extra["prep_rec"] = True
                n_fl = math.ceil((extra["bombers"] + extra["escorts"]) / 3)  # v0.41.250: _slots sizes the blue CAP as raiders / 3 (the old 4 + 8 raid gave 4); with 1 escort per 2 bombers, bombers / 2 is no longer that
        elif obj.type == ObjectiveType.BARCAP:       # a fleet patrol meets a probing enemy flight if the enemy still has fighters
            n_fl = 1 if any(w.available > 0 for w in st.enemy_air) else 0
        else:
            n_fl = threat.defender_flights(threat.expected_defenders(st, tx, ty, iads))
        self._hot = n_fl >= CAS_JET_MIN_DEF_FLIGHTS                                  # v0.41.188: red fighters can reach the target: CAS jets first
        self._a10_strike = self._a10_supply_strike(obj, n_fl)                        # v0.41.360 (Phase 10c part 2): a clean supply strike may take A-10C squadrons
        pkg = Package(id=f"pkg{number}", number=number, objective=obj, n_def=2 * n_fl, extra=extra)
        slots = self._slots(obj, self._defended(obj), n_fl, extra)
        if obj.type == ObjectiveType.STRIKE and obj.aim == "RUNWAY" and not for_player:
            # S51 (XO 2026-11-12): the runway crater goes out as F-15E standoff JSOW-Cs when an F-15E squadron reaches the field (with the PEN kit's shorter reach) and has jets free; none: the
            # plain strike as before (unlike the Standoff DEAD the kit is NOT required, no waiting for another day). Not for the player's own build: no player airframe can fly the kit, so his job and
            # route stay exactly as they were (a Viper / Hornet pilot is never moved to another slot).
            if any(s_.role == Role.STRIKE and not s_.tag and not s_.kit for s_ in slots) and any(
                    sq_.aircraft in PEN_PER_JET and ledger.free[sq_.id] >= 2 and self._in_range(sq_.id, tx, ty, "PEN") for sq_ in st.squadrons.values()):
                next(s_ for s_ in slots if s_.role == Role.STRIKE and not s_.tag and not s_.kit).kit = "PEN"
        ewr_so_ = obj.type == ObjectiveType.STRIKE and obj.aim == "STANDOFF" and self._is_ewr(obj)
        if ewr_so_ and not for_player:
            # S60 (XO 2026-11-12: EWR strikes are stand-off only): the strike slot takes the kit of the first airframe in EWR_KIT_ORDER that has a squadron with 2+ free jets in range for it (the PEN kit's
            # reach is shorter). None: the package cannot be built, the EWR waits (no GBU fallback). Not for the player's own build (as S51): a Viper / Hornet pilot keeps the plain strike slot, his route and loadout.
            for ac_, kit_ in EWR_KIT_ORDER:
                if any(sq_.aircraft == ac_ and ledger.free[sq_.id] >= 2 and self._in_range(sq_.id, tx, ty, kit_) for sq_ in st.squadrons.values()):
                    s_ = next(s_ for s_ in slots if s_.role == Role.STRIKE and not s_.tag)
                    s_.kit, s_.only = kit_, ac_
                    break
            else:
                raise NoPlayerSlot("no stand-off-capable squadron (F-15E, F-16C, F/A-18C) free for the EWR strike today")
        pp = st.player

        player_idx, lead_service, psq = None, None, None
        if for_player and pp:
            psq = st.squadrons[pp.squadron_id]
            spec = AIRCRAFT[psq.aircraft]
            ok = [i for i, s in enumerate(slots) if not s.tag and s.role in spec.roles and self._slot_ok(psq.aircraft, s) and (not s.kit or psq.aircraft in KIT_JETS.get(s.kit, ())) and (not s.only or psq.aircraft == s.only)
                  and (not is_sweep(obj) or psq.aircraft in LONG_RANGE_A2A)                    # v0.41.15: no BVR sweep in an F-16 / F/A-18
                  and self._in_range(psq.id, tx, ty) and ledger.free[psq.id] >= 2]
            if obj.type == ObjectiveType.CAS and psq.aircraft != "A-10C" and not self._hot:
                # v0.41.189 (XO): a quiet CAS job is the A-10Cs' job; a Viper / Hornet pilot is offered the CAS slot only when no A-10C squadron can fly it today
                hog_ = any(sq_.aircraft == "A-10C" and ledger.free[sq_.id] >= 2 and self._in_range(sq_.id, tx, ty) for sq_ in st.squadrons.values())
                if hog_:
                    ok = [i for i in ok if slots[i].role != Role.CAS]
            if not ok:
                raise NoPlayerSlot(f"{psq.name} cannot fly any role in: {obj.description}")
            player_idx = max(ok, key=lambda i: PLAYER_ROLE_PREFERENCE[slots[i].role])
            if obj.type == ObjectiveType.CAS and psq.aircraft != "A-10C":      # v0.41.188: a Hornet / Viper pilot picking a CAS job flies the Maverick slot, not the escort
                cas_ = [i for i in ok if slots[i].role == Role.CAS]
                player_idx = cas_[0] if cas_ else player_idx
            lead_service = spec.service

        chosen = []                      # (slot, squadron, count, is_player)
        self.missing = 0
        for i, slot in enumerate(slots):
            if slot.tag:
                continue
            sq = psq if i == player_idx else self._pick_squadron(slot, tx, ty, ledger, lead_service)
            want = min(slot.size, MAX_FLIGHT)
            if sq is None:
                self.short.append((slot.role.value, tx, ty))
                self.missing += want if slot.required else 0
                continue
            count = min(slot.size, MAX_FLIGHT, ledger.free[sq.id])
            count -= count % 2
            if slot.required:
                self.missing += max(0, want - count)                          # jets a required slot is short of (before the carrier's own cap on the player's flight)
            if i == player_idx and st.bases[sq.base_id].kind == BaseKind.CARRIER:
                count = min(count, CARRIER_PLAYER_FLIGHT_MAX)
            if count < 2:
                self.short.append((slot.role.value, tx, ty))
                continue
            ledger.free[sq.id] -= count
            lead_service = lead_service or AIRCRAFT[sq.aircraft].service
            chosen.append((slot, sq, count, i == player_idx))
        if not chosen:
            raise NoPlayerSlot("no squadron could fly this objective")
        if ewr_so_ and not for_player and not any(sl_.kit for sl_, *_ in chosen):
            # S60: the slot's squadron was there when the kit was chosen; if its jets went to another slot, the EWR strike waits for another day (never a plain strike)
            for sl_, sq_, n_, _ in chosen:
                ledger.free[sq_.id] += n_
            raise NoPlayerSlot("no stand-off-capable squadron free for the EWR strike today")
        if obj.aim == "STANDOFF" and obj.type == ObjectiveType.STRIKE and not ewr_so_ and not any(sl_.kit == "SLAM" for sl_, *_ in chosen):
            # v0.41.298: no SLAM-ER Hornets free: the Standoff Strike waits for another day (a plain strike under that fighter cover is the loss it exists to avoid)
            for sl_, sq_, n_, _ in chosen:
                ledger.free[sq_.id] += n_
            raise NoPlayerSlot("no SLAM-ER-capable squadron free for the Standoff Strike today")
        if obj.aim == "STANDOFF" and obj.type in (ObjectiveType.DEAD, ObjectiveType.COUNTER_AIR) and not any(sl_.kit == "JSOW" for sl_, *_ in chosen):
            # v0.41.19: no JSOW jets free today: the Standoff DEAD waits for another day (the planner offers it again) rather than going without them
            for sl_, sq_, n_, _ in chosen:
                ledger.free[sq_.id] += n_
            raise NoPlayerSlot("no JSOW-capable squadron free for the Standoff DEAD today")
        if obj.type in (ObjectiveType.CAS, ObjectiveType.STRIKE) and obj.aim == "SEAD" and not any(sl_.role == Role.SEAD for sl_, *_ in chosen):
            # v0.41.20: no HARM jets free: the CAS under a live SAM waits for another day rather than going in unescorted (no needless banzai)
            for sl_, sq_, n_, _ in chosen:
                ledger.free[sq_.id] += n_
            raise NoPlayerSlot("no SEAD flight free to escort the " + ("CAS" if obj.type == ObjectiveType.CAS else "strike") + " today")

        # support CAP: all four kinds (TKR_HAVCAP, HAVCAP, BASE_BARCAP, CARRIER_BARCAP) are planned chains now (blue_barcap.py), attached after the start times are known
        # v0.41.88: TKR_HAVCAP and HAVCAP are planned too (blue_barcap.py): chains per tanker / AWACS asset, attached once the start times are known.

        used, n = (names if names is not None else {}), 0     # names: the day's callsign counter, shared by every package that day
        for slot, sq, count, is_pl in chosen:
            n += 1
            cs = _next_callsign(st, sq, used)
            kit_ = slot.kit or ("CBU" if (obj.type == ObjectiveType.COUNTER_AIR and obj.aim not in ("SWEEP", "STANDOFF") and slot.role == Role.STRIKE and sq.aircraft in CBU_JETS) else "")
            pkg.flights.append(FlightPlan(f"{pkg.id}-f{n}", cs, slot.role, sq.id,
                                          sq.aircraft, count, sq.base_id,
                                          (_CA_JSOW_TASK if (kit_ == "JSOW" and obj.type == ObjectiveType.COUNTER_AIR) else None) or (_EWR_KIT_TASK.get(kit_) if ewr_so_ and slot.role == Role.STRIKE else None) or _KIT_TASK.get(kit_) or _TAG_TASK.get(slot.tag) or (_SO_SEAD_TASK if (obj.aim == "STANDOFF" and slot.role == Role.SEAD) else None) or (_ESC_TASK if slot.role == Role.ESCORT else None) or (_DEAD_TASK.get(slot.role) if obj.type == ObjectiveType.DEAD else None) or (_SETPIECE_TASK.get(slot.role) if pkg.extra.get("setpiece") else None) or _TASK[slot.role],
                                          is_pl, slot.tag, kit_, ""))
        pkg.support = self._support(pkg)
        pkg.jtac = obj.type in JTAC_OBJECTIVES
        return pkg

    def _land_raid_plan(self, number: int, obj):
        """Air raid on one of our airfields, a supply site, a garrison or friendly troops (raids.py): the raiders' field and type, how many, where they are going, the bearing they arrive on, and the escorts.
        v0.41.341 (Phase 5b): the plan was made when the raid was drawn and booked (`raids.plan_raid`, kept in `state.raids["booked"]` under the objective's id); this only hands it over, so the package is built
        from the very jets that were booked. No booking, no raid (None)."""
        bk = ((self.state.raids or {}).get("booked") or {}).get(obj.id)
        return None if bk is None else {k: v for k, v in bk.items() if k not in ("jets", "start", "turn")}

    def _raid_plan(self, number: int, obj=None):
        """Bomber raid on the fleet: bearing it arrives on, how many bombers, and escorts that can really reach (range-limited)."""
        st = self.state
        if obj is not None and obj.target_id in st.bases and st.bases[obj.target_id].kind != BaseKind.CARRIER:
            return self._land_raid_plan(number, obj)
        from . import bombers
        from . import fleet as _fleet
        cv = _fleet.carrier(st)
        dec = bombers.decide(st, self.d) if self.d is not None else {"mode": "hold"}
        if cv is None or dec["mode"] == "hold":
            return None
        rnd = random.Random(f"{st.campaign_id}:{st.day}:{number}:raid")
        stg_ = (st.raids or {}).get("bomber_stage") or {}
        brg_ = round(float(stg_["brg"]), 1) if (stg_.get("launch") == st.day and stg_.get("brg") is not None) else None      # v0.41.356 (Phase 10b part 1): the bearing is fixed when the raid is staged (the prep of the turn before needs it); an older stage keeps the seed by the raid's index
        bw_id = next(w.base_asset_id for w in st.enemy_air if "Tu_22M3" in w.types)
        # v0.41.279 (XO 2026-11-04): back to a random 8 to 40 degrees. v0.41.275 pointed it at the bombers' field, but Mozdok lies ~213 nm from the carrier, just outside the
        # X-22's 208 nm reach: on the straight line only 30 to 50 nm of way in is left outside the ring, the SAM circles cover it, and the interceptors find no intercept point.
        # The dogleg is what gives blue the room. Probed (seed 3, L3): bearing 20 gives a lane for every interceptor, bearing 60 none.
        return {"brg": brg_ if brg_ is not None else round(rnd.uniform(20, 40), 1), "bombers": dec["n"], "bomber_wing": bw_id,
                "escort_wing": dec["wing"], "escort_type": dec["type"], "escorts": dec["escorts"], "mode": dec["mode"]}

    def _pick_squadron(self, slot: Slot, tx, ty, ledger: Ledger, lead_service):
        """Prefer the lead's service; cross over only when sound (same-service option missing, or the other base is >=30% closer)."""
        obj0_ = self._ctx[0] if self._ctx else None
        sweep_ = obj0_ is not None and is_sweep(obj0_)            # v0.41.15: a Fighter Sweep flies long-range fighters only (F-15C, F-14)
        cands = [sq for sq in self.state.squadrons.values()
                 if slot.role in AIRCRAFT[sq.aircraft].roles and self._slot_ok(sq.aircraft, slot) and ledger.free[sq.id] >= 2 and self._in_range(sq.id, tx, ty, slot.kit)
                 and (not slot.kit or sq.aircraft in KIT_JETS.get(slot.kit, ())) and (not slot.only or sq.aircraft == slot.only) and (not sweep_ or sq.aircraft in LONG_RANGE_A2A)]
        if not cands:
            return None
        if slot.land:                                            # v0.41.256: the fleet raid's USAF share: land-based squadrons only, the lead's service does not matter; none reach = the usual pick
            land_ = [c for c in cands if self.state.bases[c.base_id].kind != BaseKind.CARRIER]
            if land_:
                cands, lead_service = land_, None
        # TARCAP and sweep: the long-range shooters (F-15C, F-14) first, F-16 / F/A-18 behind them. The package escort (v0.41.1) the other
        # way round: F-16 / F/A-18 first (it stays with the package and fights close), an F-15C / F-14 only when none is free.
        obj_ = self._ctx[0] if self._ctx else None
        escort = slot.role in (Role.ESCORT, Role.SWEEP) and obj_ is not None and not is_sweep(obj_)
        long_first = (slot.role in (Role.TARCAP, Role.ESCORT, Role.SWEEP) and not escort) or slot.land
        def key(sq):
            k = self._dist_nm(sq.id, tx, ty) - 40 * (ledger.free[sq.id] / max(1, sq.authorized))
            if long_first and sq.aircraft not in LONG_RANGE_A2A:
                k += A2A_SECONDARY_NM
            if escort and sq.aircraft in LONG_RANGE_A2A:
                k += A2A_SECONDARY_NM
            if sweep_ and sq.aircraft in SWEEP_LAST:
                k += A2A_SECONDARY_NM         # S45: a Fighter Sweep goes into red's fighters: an F-15C first, the Tomcat only when no Eagle squadron can fly it
            if slot.role == Role.CAS and (sq.aircraft != "A-10C") == (not getattr(self, "_hot", False)):
                k += CAS_JET_SWAY_NM         # v0.41.188: A-10Cs where the air is clear, F-16C / F/A-18C when red fighters reach the target
            return k
        if lead_service is None:
            return min(cands, key=key)
        same = [c for c in cands if AIRCRAFT[c.aircraft].service == lead_service]
        cross = [c for c in cands if AIRCRAFT[c.aircraft].service != lead_service]
        bs = min(same, key=key) if same else None
        bc = min(cross, key=key) if cross else None
        if bs and (not bc or self._dist_nm(bc.id, tx, ty) > 0.7 * self._dist_nm(bs.id, tx, ty)):
            return bs
        return bc or bs

    def _pick_cap_near(self, base, ledger: Ledger, lead_service):
        best, best_s = None, 1e9
        for sq in self.state.squadrons.values():
            spec = AIRCRAFT[sq.aircraft]
            if Role.CAP not in spec.roles or ledger.free[sq.id] < 2:
                continue
            b = self.state.bases[sq.base_id]
            d = math.hypot(b.x - base.x, b.y - base.y) / NM
            if d > spec.combat_radius_nm:
                continue
            s = d + (0 if spec.service == lead_service else 40)
            if s < best_s:
                best, best_s = sq, s
        return best

    def _pick_cap_at(self, base, ledger: Ledger, lead_service):
        """v0.41.7: a fighter squadron AT this base (the carrier BARCAP flies off its own deck)."""
        cands = [sq for sq in self.state.squadrons.values() if sq.base_id == base.id and Role.CAP in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 2]
        return max(cands, key=lambda sq: (AIRCRAFT[sq.aircraft].service == lead_service, ledger.free.get(sq.id, 0))) if cands else None

    def _pick_cap_any(self, ledger: Ledger, lead_service):
        """The tanker CAP is mandatory: any fighter will do (it stays with the tanker, short of the scramble circles), range aside."""
        cands = [sq for sq in self.state.squadrons.values() if Role.CAP in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 2]
        if not cands:
            cands = [sq for sq in self.state.squadrons.values() if Role.CAP in AIRCRAFT[sq.aircraft].roles and sq.available >= 2 and sq.role != "havcap"]
        if not cands:
            return None
        return max(cands, key=lambda sq: (AIRCRAFT[sq.aircraft].service == lead_service, ledger.free.get(sq.id, 0)))

    def _support(self, pkg: Package) -> list:
        lead = pkg.player_flight or next((f for f in pkg.flights if not f.tag), pkg.flights[0])
        lead_home = AIRCRAFT[lead.aircraft].home
        _sq = self.state.squadrons.get(getattr(lead, "squadron_id", ""))
        if _sq is not None and _sq.base_id in self.state.bases:           # v0.41.257: a carrier squadron moved to a land field (its ship sunk) recovers there
            lead_home = self.state.bases[_sq.base_id].kind
        awacs = AWACS_FOR[lead_home]          # E-2C for Navy leads (F-14 Link-4), E-3 for USAF leads
        from . import support_assets as sa_
        out = [SupportPlan("AWACS", awacs.dcs_class, awacs.label, awacs.altitude_ft, awacs.speed_kts)]
        methods: list = []
        for f in sorted((f for f in pkg.flights if not f.tag), key=lambda f: f is not lead):
            m = AIRCRAFT[f.aircraft].refuel
            if m not in methods:
                methods.append(m)
        t1 = TANKER_FOR[methods[0]]
        out.append(SupportPlan("TANKER1", t1.dcs_class, t1.label, t1.altitude_ft, t1.speed_kts, methods[0].value))
        if len(methods) > 1:
            t2 = TANKER_FOR[methods[1]]
            out.append(SupportPlan("TANKER2", t2.dcs_class, "Arco" if t2.label == t1.label else t2.label,
                                   t2.altitude_ft, t2.speed_kts, methods[1].value))
        elif lead_home == BaseKind.CARRIER and t1.dcs_class != RECOVERY_TANKER.dcs_class:      # v0.41.335: a probe jet's TANKER1 is already the S-3B
            r = RECOVERY_TANKER
            out.append(SupportPlan("TANKER2", r.dcs_class, r.label, r.altitude_ft, r.speed_kts,
                                   RefuelMethod.BASKET.value, from_carrier=True))
        return [x for x in out if sa_.up_for(self.state, x.dcs_class, pkg.start)]      # v0.41.87: only what has an aircraft on orbit while the package flies

    def assign_player(self, pkg: Package, flight_id: str | None = None):
        pp = self.state.player
        opts = pkg.player_options(pp.aircraft)
        if not opts:
            raise NoPlayerSlot("package has no flight your aircraft can fly")
        chosen = (max(opts, key=lambda f: PLAYER_ROLE_PREFERENCE[f.role]) if flight_id is None
                  else next((f for f in opts if f.id == flight_id), None))
        if chosen is None:
            raise NoPlayerSlot(f"{flight_id} is not a flight you can fly in this package")
        for f in pkg.flights:
            f.is_player = f is chosen
        _sq = self.state.squadrons.get(getattr(chosen, "squadron_id", ""))
        if (self.state.bases[_sq.base_id].kind if _sq is not None else AIRCRAFT[chosen.aircraft].home) == BaseKind.CARRIER:
            chosen.count = min(chosen.count, CARRIER_PLAYER_FLIGHT_MAX)
        pkg.support = self._support(pkg)
        return chosen


def target_point(state: CampaignState, obj: Objective):
    if obj.type in _FLEET:
        b = state.bases[obj.target_id]
        return b.x, b.y
    a = state.assets[obj.target_id]
    return a.x, a.y


def packages_linked(state: CampaignState, p1: "Package", p2: "Package", km: float = 45.0) -> bool:
    """Same general area: targets within ~45 km of each other, or covered by the same SAM cluster (asset.defended_by), or one is the
    SAM site that defends the other's target. Fleet objectives are never linked."""
    if p1.objective.type in _FLEET or p2.objective.type in _FLEET:
        return False
    a, b = state.assets[p1.objective.target_id], state.assets[p2.objective.target_id]
    if math.hypot(a.x - b.x, a.y - b.y) <= km * 1000:
        return True
    if a.id in b.defended_by or b.id in a.defended_by:
        return True
    return bool(set(a.defended_by) & set(b.defended_by))


def folded_n_def(package, extras, pct: int = 100) -> int:
    """Enemy fighters for a mission with folded packages: the biggest package's need plus pct% of every other package's need."""
    needs = sorted([package.n_def] + [x.n_def for x in extras], reverse=True)
    return needs[0] + int(round(sum(needs[1:]) * max(0, pct) / 100.0))
