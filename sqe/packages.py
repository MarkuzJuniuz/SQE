"""Objective -> package. Joint Navy/USAF packages happen only when they are sound (see _pick_squadron)."""
from __future__ import annotations
import math
from dataclasses import dataclass, field, asdict
from .aircraft import AIRCRAFT, AWACS_FOR, TANKER_FOR, RECOVERY_TANKER
from .models import Objective, ObjectiveType, Role, BaseKind, RefuelMethod
from .state import CampaignState

NM = 1852.0
MAX_FLIGHT = 4
CARRIER_PLAYER_FLIGHT_MAX = 2        # catapult spots are limited; keep the player's cat-start flight small
PLAYER_ROLE_PREFERENCE = {Role.STRIKE: 5, Role.SEAD: 4, Role.ESCORT: 3, Role.SWEEP: 2, Role.CAP: 1, Role.CAS: 0}
JTAC_OBJECTIVES = {ObjectiveType.CAS}


class NoPlayerSlot(Exception):
    pass


@dataclass
class Slot:
    role: Role
    size: int
    required: bool = True
    only_if_defended: bool = False


TEMPLATES = {
    ObjectiveType.STRIKE: [Slot(Role.STRIKE, 4), Slot(Role.ESCORT, 2), Slot(Role.SEAD, 2, False, True)],
    ObjectiveType.DEAD: [Slot(Role.SEAD, 4), Slot(Role.ESCORT, 2)],
    ObjectiveType.COUNTER_AIR: [Slot(Role.SWEEP, 4), Slot(Role.STRIKE, 2, False)],
    ObjectiveType.BARCAP: [Slot(Role.CAP, 2), Slot(Role.CAP, 2, False)],
    ObjectiveType.CAS: [Slot(Role.CAS, 4), Slot(Role.ESCORT, 2, False), Slot(Role.SEAD, 2, False, True)],
}


@dataclass
class FlightPlan:
    id: str
    callsign: str
    role: Role
    squadron_id: str
    aircraft: str
    count: int
    base_id: str
    task: str
    is_player: bool = False


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

    @property
    def player_flight(self):
        return next((f for f in self.flights if f.is_player), None)

    def player_options(self, aircraft_key: str) -> list:
        spec = AIRCRAFT[aircraft_key]
        return [f for f in self.flights if f.aircraft == aircraft_key and f.role in spec.roles]

    def services(self) -> set:
        return {AIRCRAFT[f.aircraft].service for f in self.flights}

    @property
    def joint(self) -> bool:
        return len(self.services()) > 1

    def to_dict(self) -> dict:
        return {"id": self.id, "number": self.number, "objective": self.objective.to_dict(),
                "flights": [{**asdict(f), "role": f.role.value} for f in self.flights],
                "support": [asdict(s) for s in self.support], "jtac": self.jtac,
                "jtac_laser_code": self.jtac_laser_code}

    @classmethod
    def from_dict(cls, d: dict) -> "Package":
        o = d["objective"]
        obj = Objective(o["id"], ObjectiveType(o["type"]), o["target_id"], o["priority"], o.get("description", ""))
        return cls(d["id"], d["number"], obj, [FlightPlan(**{**f, "role": Role(f["role"])}) for f in d["flights"]],
                   [SupportPlan(**s) for s in d["support"]], d.get("jtac", False), d.get("jtac_laser_code", 1688))


class Ledger:
    def __init__(self, state: CampaignState):
        self.free = {sid: s.available for sid, s in state.squadrons.items()}


class PackageBuilder:
    def __init__(self, state: CampaignState):
        self.state = state

    def target_xy(self, obj: Objective):
        if obj.type == ObjectiveType.BARCAP:
            b = self.state.bases[obj.target_id]
            return b.x, b.y
        a = self.state.assets[obj.target_id]
        return a.x, a.y

    def _dist_nm(self, sq_id, tx, ty) -> float:
        b = self.state.bases[self.state.squadrons[sq_id].base_id]
        return math.hypot(tx - b.x, ty - b.y) / NM

    def _in_range(self, sq_id, tx, ty) -> bool:
        return self._dist_nm(sq_id, tx, ty) <= AIRCRAFT[self.state.squadrons[sq_id].aircraft].combat_radius_nm

    def _defended(self, obj) -> bool:
        if obj.type == ObjectiveType.BARCAP:
            return False
        a = self.state.assets[obj.target_id]
        return any(not self.state.assets[d].destroyed for d in a.defended_by)

    def build(self, obj: Objective, number: int, ledger: Ledger, *, for_player: bool) -> Package:
        st = self.state
        tx, ty = self.target_xy(obj)
        defended = self._defended(obj)
        pkg = Package(id=f"pkg{number}", number=number, objective=obj)
        pp = st.player
        slots = [s for s in TEMPLATES[obj.type] if not (s.only_if_defended and not defended)]

        player_idx = None
        lead_service = None
        if for_player and pp:
            psq = st.squadrons[pp.squadron_id]
            spec = AIRCRAFT[psq.aircraft]
            ok = [i for i, s in enumerate(slots) if s.role in spec.roles and self._in_range(psq.id, tx, ty)
                  and ledger.free[psq.id] >= 1]
            if not ok:
                raise NoPlayerSlot(f"{psq.name} cannot fly any role in: {obj.description}")
            player_idx = max(ok, key=lambda i: PLAYER_ROLE_PREFERENCE[slots[i].role])
            lead_service = spec.service

        n = 0
        for i, slot in enumerate(slots):
            sq = st.squadrons[pp.squadron_id] if i == player_idx else self._pick_squadron(slot, tx, ty, ledger, lead_service)
            if sq is None:
                continue
            count = min(slot.size, MAX_FLIGHT, ledger.free[sq.id])
            base = st.bases[sq.base_id]
            if i == player_idx and base.kind == BaseKind.CARRIER:
                count = min(count, CARRIER_PLAYER_FLIGHT_MAX)
            if count < 1:
                continue
            ledger.free[sq.id] -= count
            lead_service = lead_service or AIRCRAFT[sq.aircraft].service
            n += 1
            pkg.flights.append(FlightPlan(f"{pkg.id}-f{n}", f"{sq.callsign} {number}-{n}", slot.role, sq.id,
                                          sq.aircraft, count, base.id, _TASK[slot.role], i == player_idx))
        if not pkg.flights:
            raise NoPlayerSlot("no squadron could fly this objective")
        pkg.support = self._support(pkg)
        pkg.jtac = obj.type in JTAC_OBJECTIVES
        return pkg

    def _pick_squadron(self, slot: Slot, tx, ty, ledger: Ledger, lead_service: str | None):
        """Prefer the lead's service. Cross over to the other service only when it is sound:
        the same-service option is missing/busy/out of range, or the other service's base is >=30% closer."""
        cands = [sq for sq in self.state.squadrons.values()
                 if slot.role in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 1 and self._in_range(sq.id, tx, ty)]
        if not cands:
            return None
        key = lambda sq: self._dist_nm(sq.id, tx, ty) - 40 * (ledger.free[sq.id] / max(1, sq.authorized))
        if lead_service is None:
            return min(cands, key=key)
        same = [c for c in cands if AIRCRAFT[c.aircraft].service == lead_service]
        cross = [c for c in cands if AIRCRAFT[c.aircraft].service != lead_service]
        bs = min(same, key=key) if same else None
        bc = min(cross, key=key) if cross else None
        if bs and (not bc or self._dist_nm(bc.id, tx, ty) > 0.7 * self._dist_nm(bs.id, tx, ty)):
            return bs
        return bc or bs

    def _support(self, pkg: Package) -> list:
        st = self.state
        lead = pkg.player_flight or pkg.flights[0]
        lead_home = AIRCRAFT[lead.aircraft].home
        awacs = AWACS_FOR[lead_home]      # E-2C for Navy leads (F-14 Link-4 expects one), E-3 for USAF leads
        out = [SupportPlan("AWACS", awacs.dcs_class, awacs.label, awacs.altitude_ft, awacs.speed_kts)]
        methods: list = []
        for f in sorted(pkg.flights, key=lambda f: f is not lead):
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
        return out

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


_TASK = {Role.STRIKE: "Strike target", Role.SEAD: "Suppress/destroy SAM", Role.ESCORT: "Escort package",
         Role.SWEEP: "Fighter sweep", Role.CAP: "Combat air patrol", Role.CAS: "Close air support"}
