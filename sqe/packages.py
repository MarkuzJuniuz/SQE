"""Objective -> package. Threat-sized, joint only when sound, real callsigns, flights of 2 or 4."""
from __future__ import annotations
import copy
import math
import random
from dataclasses import dataclass, field, asdict
from . import threat
from . import threatmap as tm
from .loadouts import ENEMY_FIGHTERS, ENEMY_RADIUS_NM, JSOW_PER_JET
from .aircraft import AIRCRAFT, AWACS_FOR, TANKER_FOR, RECOVERY_TANKER
from .models import Objective, ObjectiveType, Role, BaseKind, RefuelMethod
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
    tag: str = ""                      # "" | HAVCAP | BASECAP (support flights: AI only)
    kit: str = ""                      # "" | JSOW (a strike slot that only JSOW-capable jets fill, see loadouts.JSOW_PER_JET)


TEMPLATES = {
    ObjectiveType.STRIKE: [Slot(Role.STRIKE, 4), Slot(Role.TARCAP, 2), Slot(Role.SEAD, 2, False, True)],
    # SEAD only blinds the radars; the DEAD flight (the strikers) kills the site right behind it. Both fly in the same package.
    ObjectiveType.DEAD: [Slot(Role.SEAD, 2), Slot(Role.STRIKE, 4), Slot(Role.TARCAP, 2)],
    ObjectiveType.COUNTER_AIR: [Slot(Role.SWEEP, 4), Slot(Role.STRIKE, 2, False)],
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
    """Is this job AI-only? BARCAP and land-raid intercepts are; the carrier raid is a setpiece the player can fly."""
    return obj.type in AI_ONLY and not carrier_raid(st, obj)


SETPIECE_RATIO = 0.75       # blue CAP flights of 4 per bomber: 3 flights for 4 bombers + 8 escorts, i.e. about one blue fighter per raider (judgment call, XO: "overwhelming")
_SETPIECE_TASK = {Role.CAP: "Intercept: kill the Backfires before they reach launch range, then the escorts",
                  Role.SWEEP: "Sweep ahead of the fleet: engage the raid's escorts so the interceptors get at the bombers"}
_TASK = {Role.STRIKE: "Strike target", Role.SEAD: "Suppress/destroy SAM",
         Role.TARCAP: "TARCAP: on station short of the target before the package, shoot what comes in range, do not chase; stay at least 15 minutes and until the last strike flight is off target plus 5 minutes, then home",
         Role.SWEEP: "Fighter sweep", Role.CAP: "Combat air patrol", Role.CAS: "Close air support"}
_DEAD_TASK = {Role.SEAD: "SEAD: suppress the radars ahead of the DEAD flight", Role.STRIKE: "Close DEAD: destroy the SAM site with GBUs (the SEAD package goes in ahead of you; call it off if the radars are up)"}
_KIT_TASK = {"JSOW": "Standoff DEAD: AGM-154A on the site's radars, launchers and covering Tors, on the HARM salvo's time; stand-off release, then home"}
_SO_SEAD_TASK = "SEAD: HARMs on the site's radars and its Tors, in the same salvo as the Standoff DEAD JSOWs"
_ESC_TASK = "Escort: hold your station with the package, shoot what comes in range, do not chase; leave when the strikers are off target"
_TASK[Role.ESCORT] = _ESC_TASK
_TAG_TASK = {"HAVCAP": "HAVCAP (guards the AWACS)", "TNKCAP": "Tanker CAP (guards the tanker)", "BASECAP": "Base CAP", "CVCAP": "Carrier CAP"}
BASECAP_ENEMY_NM = 130     # v0.41.7: a land base gets a base CAP when an enemy fighter field is within this (an alert pair reaches it)


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
    guard: str = ""                    # v0.41.10: a base CAP's guarded field (base id), when it is not the squadron's own base


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
        obj = Objective(o["id"], ObjectiveType(o["type"]), o["target_id"], o["priority"], o.get("description", ""), o.get("aim", ""))
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
A2A_SECONDARY_NM = 400          # an F-16 / F/A-18 squadron is picked for TARCAP or escort only when no long-range shooter is within this much of it


def is_sweep(obj) -> bool:
    """A Fighter Sweep package: offensive counterair over a target area, planned when intel expects more enemy fighters there than the
    packages' own TARCAP and escort can take (AFDP 3-01: sweeps are flown for local air superiority, as the air threat requires)."""
    return obj.type == ObjectiveType.COUNTER_AIR and obj.aim == "SWEEP"


def sweep_4ships(n_def_flights: int) -> int:
    """4-ships of sweep needed for this many enemy 2-ship flights: the fighters required beyond a 4-ship TARCAP, 4 per sweep flight."""
    return int(math.ceil(max(0, threat.fighters_required(n_def_flights) - 4) / 4))


class Ledger:
    def __init__(self, state: CampaignState):
        self.free = {sid: s.available for sid, s in state.squadrons.items()}


class PackageBuilder:
    def __init__(self, state: CampaignState, d=None):
        self.state, self.d = state, d
        self._tk, self._ctx = {}, (None, None)

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

    def _in_range(self, sq_id, tx, ty) -> bool:
        """Reach counts tanker support (x1.5) only when a safe tanker track exists, and the route must not cross a SAM belt
        in front of the target (the FLOT rule)."""
        sq = self.state.squadrons[sq_id]
        b = self.state.bases[sq.base_id]
        spec = AIRCRAFT[sq.aircraft]
        reach = spec.combat_radius_nm * (1.5 if self._tanker_ok((b.x, b.y), (tx, ty)) else 1.0)
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

    # ---- slot list sized to the threat ---------------------------------------------------------------------
    def _slots(self, obj, defended, n_fl) -> list:
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
        elif obj.type == ObjectiveType.CAS and obj.aim == "SEAD":           # v0.41.20: CAS under a live SA-2/3/6: the HARM escort is not optional
            tmpl = [Slot(Role.CAS, 4), Slot(Role.SEAD, 2), Slot(Role.TARCAP, 2, False)]
        if carrier_raid(self.state, obj):                                    # v0.41.107: the setpiece: every fighter flight in reach, about one blue fighter per raider
            k = max(2, math.ceil(SETPIECE_RATIO * n_fl))              # n_fl = bombers; raiders = bombers x 3 (2 escorts each) -> k flights of 4
            return [Slot(Role.CAP, 4), Slot(Role.CAP, 4)] + [Slot(Role.CAP, 4, False) for _ in range(k - 2)] + [Slot(Role.SWEEP, 2, False)]
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
            n_fl = extra.get("escorts", 0) // 2
            if extra and carrier_raid(st, obj):
                extra = {**extra, "setpiece": True}                          # v0.41.107: flown from the Missions page like any job, no merging, every flight listed
        elif obj.type == ObjectiveType.BARCAP:       # a fleet patrol meets a probing enemy flight if the enemy still has fighters
            n_fl = 1 if any(w.available > 0 for w in st.enemy_air) else 0
        else:
            n_fl = threat.defender_flights(threat.expected_defenders(st, tx, ty, iads))
        pkg = Package(id=f"pkg{number}", number=number, objective=obj, n_def=2 * n_fl, extra=extra)
        slots = self._slots(obj, self._defended(obj), n_fl)
        pp = st.player

        player_idx, lead_service, psq = None, None, None
        if for_player and pp:
            psq = st.squadrons[pp.squadron_id]
            spec = AIRCRAFT[psq.aircraft]
            ok = [i for i, s in enumerate(slots) if not s.tag and s.role in spec.roles and (s.kit != "JSOW" or psq.aircraft in JSOW_PER_JET)
                  and (not is_sweep(obj) or psq.aircraft in LONG_RANGE_A2A)                    # v0.41.15: no BVR sweep in an F-16 / F/A-18
                  and self._in_range(psq.id, tx, ty) and ledger.free[psq.id] >= 2]
            if not ok:
                raise NoPlayerSlot(f"{psq.name} cannot fly any role in: {obj.description}")
            player_idx = max(ok, key=lambda i: PLAYER_ROLE_PREFERENCE[slots[i].role])
            lead_service = spec.service

        chosen = []                      # (slot, squadron, count, is_player)
        for i, slot in enumerate(slots):
            if slot.tag:
                continue
            sq = psq if i == player_idx else self._pick_squadron(slot, tx, ty, ledger, lead_service)
            if sq is None:
                continue
            count = min(slot.size, MAX_FLIGHT, ledger.free[sq.id])
            count -= count % 2
            if i == player_idx and st.bases[sq.base_id].kind == BaseKind.CARRIER:
                count = min(count, CARRIER_PLAYER_FLIGHT_MAX)
            if count < 2:
                continue
            ledger.free[sq.id] -= count
            lead_service = lead_service or AIRCRAFT[sq.aircraft].service
            chosen.append((slot, sq, count, i == player_idx))
        if not chosen:
            raise NoPlayerSlot("no squadron could fly this objective")
        if obj.aim == "STANDOFF" and not any(sl_.kit == "JSOW" for sl_, *_ in chosen):
            # v0.41.19: no JSOW jets free today: the Standoff DEAD waits for another day (the planner offers it again) rather than going without them
            for sl_, sq_, n_, _ in chosen:
                ledger.free[sq_.id] += n_
            raise NoPlayerSlot("no JSOW-capable squadron free for the Standoff DEAD today")
        if obj.type == ObjectiveType.CAS and obj.aim == "SEAD" and not any(sl_.role == Role.SEAD for sl_, *_ in chosen):
            # v0.41.20: no HARM jets free: the CAS under a live SAM waits for another day rather than going in unescorted (no needless banzai)
            for sl_, sq_, n_, _ in chosen:
                ledger.free[sq_.id] += n_
            raise NoPlayerSlot("no SEAD flight free to escort the CAS today")

        # support CAP: all four kinds (TNKCAP, HAVCAP, BASECAP, CVCAP) are planned chains now (blue_barcap.py), attached after the start times are known
        # v0.41.88: TNKCAP and HAVCAP are planned too (blue_barcap.py): chains per tanker / AWACS asset, attached once the start times are known.

        used, n = (names if names is not None else {}), 0     # names: the day's callsign counter, shared by every package that day
        for slot, sq, count, is_pl in chosen:
            n += 1
            cs = _next_callsign(st, sq, used)
            pkg.flights.append(FlightPlan(f"{pkg.id}-f{n}", cs, slot.role, sq.id,
                                          sq.aircraft, count, sq.base_id,
                                          _KIT_TASK.get(slot.kit) or _TAG_TASK.get(slot.tag) or (_SO_SEAD_TASK if (obj.aim == "STANDOFF" and slot.role == Role.SEAD) else None) or (_ESC_TASK if slot.role == Role.ESCORT else None) or (_DEAD_TASK.get(slot.role) if obj.type == ObjectiveType.DEAD else None) or (_SETPIECE_TASK.get(slot.role) if pkg.extra.get("setpiece") else None) or _TASK[slot.role],
                                          is_pl, slot.tag, slot.kit, ""))
        pkg.support = self._support(pkg)
        pkg.jtac = obj.type in JTAC_OBJECTIVES
        return pkg

    def _land_raid_plan(self, number: int, obj):
        """Air raid on one of our airfields, a supply site, a garrison or friendly troops (raids.py): the raiders' field and type, how many, where they are going,
        the bearing they arrive on, and escorts that can reach."""
        from . import raids
        st = self.state
        tb = st.bases[obj.target_id]
        aim = getattr(obj, "aim", "") or ""
        ax, ay = raids.aim_xy(st, aim, tb)
        rnd = random.Random(f"{st.campaign_id}:{st.day}:{number}:{obj.target_id}:{aim}:raid")
        r = raids._reach(st, raids.aim_kind(aim), ax, ay, budget=False)
        if r is None:
            return None
        bw, raider = r[1], r[2]
        ba = st.assets[bw.base_asset_id]
        lo, hi = (self.d.raid_size if self.d else (2, 2))
        nb = max(2, min(rnd.randint(lo, hi), bw.available))
        nb -= nb % 2
        esc = None
        for w in sorted(st.enemy_air, key=lambda w: math.hypot(st.assets[w.base_asset_id].x - ax, st.assets[w.base_asset_id].y - ay)):
            a = st.assets[w.base_asset_id]
            if w is bw or w.available < 2 or a.destroyed:
                continue
            d_nm = math.hypot(a.x - ax, a.y - ay) / NM
            types = [t for t in w.general_types_up() if t in ENEMY_FIGHTERS and ENEMY_RADIUS_NM.get(t, 0) * 0.85 >= d_nm]
            if types:
                esc = (w.base_asset_id, rnd.choice(types)); break
        brg = math.degrees(math.atan2(ba.y - ay, ba.x - ax)) % 360          # they come from where they took off
        arm = 0
        if self.d and getattr(self.d, "raid_arm", 0) > 0 and not aim and raider == "Su_24M" and bw.available >= nb + 2:    # v0.41.84: a SEAD group ahead of the bombers
            n_ = raids.arm_jets(st, tb, bw.available, nb)                  # v0.41.94: sized like blue's salvo: 2 jets, or 4 against Patriot + HAWK / a full Patriot
            if n_ and rnd.random() < self.d.raid_arm:
                arm = n_
        arm_cover = 4 if (arm >= 4 and esc) else 0       # v0.41.116: a SEAD group of four or more brings its own fighters: a pair of escorts and a pair on a TARCAP station
        return {"arm": arm, "arm_cover": arm_cover, "land": True, "raider": raider, "brg": round((brg + rnd.uniform(-12, 12)) % 360, 1), "bombers": nb, "bomber_wing": bw.base_asset_id,
                "escort_wing": esc[0] if esc else "", "escort_type": esc[1] if esc else "",
                "escorts": (4 if nb >= 4 else 2) if esc else 0, "aim": aim, "dest": [ax, ay]}

    def _raid_plan(self, number: int, obj=None):
        """Bomber raid on the fleet: bearing it arrives on, how many bombers, and escorts that can really reach (range-limited)."""
        st = self.state
        if obj is not None and obj.target_id in st.bases and st.bases[obj.target_id].kind != BaseKind.CARRIER:
            return self._land_raid_plan(number, obj)
        from . import bombers
        cv = next((b for b in st.bases.values() if b.kind == BaseKind.CARRIER), None)
        dec = bombers.decide(st, self.d) if self.d is not None else {"mode": "hold"}
        if cv is None or dec["mode"] == "hold":
            return None
        rnd = random.Random(f"{st.campaign_id}:{st.day}:{number}:raid")
        return {"brg": round(rnd.uniform(8, 40), 1), "bombers": dec["n"], "bomber_wing": next(w.base_asset_id for w in st.enemy_air if "Tu_22M3" in w.types),
                "escort_wing": dec["wing"], "escort_type": dec["type"], "escorts": dec["escorts"], "mode": dec["mode"]}

    def _pick_squadron(self, slot: Slot, tx, ty, ledger: Ledger, lead_service):
        """Prefer the lead's service; cross over only when sound (same-service option missing, or the other base is >=30% closer)."""
        obj0_ = self._ctx[0] if self._ctx else None
        sweep_ = obj0_ is not None and is_sweep(obj0_)            # v0.41.15: a Fighter Sweep flies long-range fighters only (F-15C, F-14)
        cands = [sq for sq in self.state.squadrons.values()
                 if slot.role in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 2 and self._in_range(sq.id, tx, ty)
                 and (slot.kit != "JSOW" or sq.aircraft in JSOW_PER_JET) and (not sweep_ or sq.aircraft in LONG_RANGE_A2A)]
        if not cands:
            return None
        # TARCAP and sweep: the long-range shooters (F-15C, F-14) first, F-16 / F/A-18 behind them. The package escort (v0.41.1) the other
        # way round: F-16 / F/A-18 first (it stays with the package and fights close), an F-15C / F-14 only when none is free.
        obj_ = self._ctx[0] if self._ctx else None
        escort = slot.role in (Role.ESCORT, Role.SWEEP) and obj_ is not None and not is_sweep(obj_)
        long_first = slot.role in (Role.TARCAP, Role.ESCORT, Role.SWEEP) and not escort
        def key(sq):
            k = self._dist_nm(sq.id, tx, ty) - 40 * (ledger.free[sq.id] / max(1, sq.authorized))
            if long_first and sq.aircraft not in LONG_RANGE_A2A:
                k += A2A_SECONDARY_NM
            if escort and sq.aircraft in LONG_RANGE_A2A:
                k += A2A_SECONDARY_NM
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
        """v0.41.7: a fighter squadron AT this base (the carrier CAP flies off its own deck)."""
        cands = [sq for sq in self.state.squadrons.values() if sq.base_id == base.id and Role.CAP in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 2]
        return max(cands, key=lambda sq: (AIRCRAFT[sq.aircraft].service == lead_service, ledger.free.get(sq.id, 0))) if cands else None

    def _pick_cap_any(self, ledger: Ledger, lead_service):
        """The tanker CAP is mandatory: any fighter will do (it stays with the tanker, short of the scramble circles), range aside."""
        cands = [sq for sq in self.state.squadrons.values() if Role.CAP in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 2]
        if not cands:
            cands = [sq for sq in self.state.squadrons.values() if Role.CAP in AIRCRAFT[sq.aircraft].roles and sq.available >= 2]
        if not cands:
            return None
        return max(cands, key=lambda sq: (AIRCRAFT[sq.aircraft].service == lead_service, ledger.free.get(sq.id, 0)))

    def _support(self, pkg: Package) -> list:
        lead = pkg.player_flight or next((f for f in pkg.flights if not f.tag), pkg.flights[0])
        lead_home = AIRCRAFT[lead.aircraft].home
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
        elif lead_home == BaseKind.CARRIER:
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
        if AIRCRAFT[chosen.aircraft].home == BaseKind.CARRIER:
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
