"""Objective -> package. Threat-sized, joint only when sound, real callsigns, flights of 2 or 4."""
from __future__ import annotations
import copy
import math
import random
from dataclasses import dataclass, field, asdict
from . import threat
from . import threatmap as tm
from .loadouts import ENEMY_FIGHTERS, ENEMY_RADIUS_NM
from . import factions
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
    tag: str = ""                      # "" | HAVCAP | BASECAP (support flights: AI only)


TEMPLATES = {
    ObjectiveType.STRIKE: [Slot(Role.STRIKE, 4), Slot(Role.ESCORT, 2), Slot(Role.SEAD, 2, False, True)],
    # SEAD only blinds the radars; the DEAD flight (the strikers) kills the site right behind it. Both fly in the same package.
    ObjectiveType.DEAD: [Slot(Role.SEAD, 2), Slot(Role.STRIKE, 4), Slot(Role.ESCORT, 2)],
    ObjectiveType.COUNTER_AIR: [Slot(Role.SWEEP, 4), Slot(Role.STRIKE, 2, False)],
    ObjectiveType.BARCAP: [Slot(Role.CAP, 2), Slot(Role.CAP, 2, False)],
    ObjectiveType.CAS: [Slot(Role.CAS, 4), Slot(Role.ESCORT, 2, False), Slot(Role.SEAD, 2, False, True)],
    ObjectiveType.FLEET_DEFENSE: [Slot(Role.CAP, 4), Slot(Role.CAP, 2, False), Slot(Role.SWEEP, 2, False)],
}
_FLEET = (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE)
_TASK = {Role.STRIKE: "Strike target", Role.SEAD: "Suppress/destroy SAM", Role.ESCORT: "Escort package",
         Role.SWEEP: "Fighter sweep", Role.CAP: "Combat air patrol", Role.CAS: "Close air support"}
_DEAD_TASK = {Role.SEAD: "SEAD: blind the radars ahead of the DEAD flight", Role.STRIKE: "DEAD: destroy the SAM site (follow the SEAD flight in)"}
_TAG_TASK = {"HAVCAP": "HAVCAP (guards tanker and AWACS)", "BASECAP": "Base CAP"}


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
        obj = Objective(o["id"], ObjectiveType(o["type"]), o["target_id"], o["priority"], o.get("description", ""))
        return cls(d["id"], d["number"], obj, [FlightPlan(**{**f, "role": Role(f["role"])}) for f in d["flights"]],
                   [SupportPlan(**s) for s in d["support"]], d.get("jtac", False), d.get("jtac_laser_code", 1688),
                   d.get("start", "09:00"), d.get("n_def", 0), d.get("extra", {}))


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

    def _defended(self, obj) -> bool:
        if obj.type in _FLEET:
            return False
        a = self.state.assets[obj.target_id]
        return any(not self.state.assets[d].destroyed for d in a.defended_by)

    # ---- slot list sized to the threat ---------------------------------------------------------------------
    def _slots(self, obj, defended, n_fl) -> list:
        slots = [copy.copy(s) for s in TEMPLATES[obj.type] if not (s.only_if_defended and not defended)]
        if obj.type in (ObjectiveType.STRIKE, ObjectiveType.DEAD, ObjectiveType.CAS):
            req = threat.fighters_required(n_fl)
            slots = [s for s in slots if s.role != Role.ESCORT]
            if req:
                slots.append(Slot(Role.ESCORT, min(4, req), True))
                if req > 4:
                    slots.append(Slot(Role.SWEEP, min(4, req - 4), False))
        if obj.type not in _FLEET:
            slots.append(Slot(Role.CAP, 2, False, tag="HAVCAP"))
        return slots

    def build(self, obj: Objective, number: int, ledger: Ledger, *, for_player: bool) -> Package:
        st = self.state
        tx, ty = self.target_xy(obj)
        self._ctx = (obj, None if obj.type in _FLEET else self.state.assets[obj.target_id])
        iads = self.d.iads if self.d else 0.5
        extra = {}
        if obj.type == ObjectiveType.FLEET_DEFENSE:
            extra = self._raid_plan(number, obj) or {}
            n_fl = extra.get("escorts", 0) // 2
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
            ok = [i for i, s in enumerate(slots) if not s.tag and s.role in spec.roles
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

        # support CAP: HAVCAP guards the tanker/AWACS; BASECAP guards the strike/CAS flights' home field
        prim = st.bases[chosen[0][1].base_id]
        anchor = next((st.bases[sq.base_id] for _, sq, _, pl in chosen if pl), prim)
        dnm = math.hypot(tx - prim.x, ty - prim.y) / NM
        wanted = [("HAVCAP", anchor)] if obj.type not in _FLEET else []
        if obj.type == ObjectiveType.CAS or (obj.type not in _FLEET and dnm < 100):
            wanted.append(("BASECAP", prim))
        for tag, base in wanted:
            sq = self._pick_cap_near(base, ledger, lead_service) or (self._pick_cap_any(ledger, lead_service) if tag == "HAVCAP" else None)
            if sq:
                ledger.free[sq.id] -= 2
                chosen.append((Slot(Role.CAP, 2, False, tag=tag), sq, 2, False))

        used, n = {}, 0
        for slot, sq, count, is_pl in chosen:
            n += 1
            used[sq.callsign] = used.get(sq.callsign, 0) + 1
            pkg.flights.append(FlightPlan(f"{pkg.id}-f{n}", f"{sq.callsign} {used[sq.callsign]}", slot.role, sq.id,
                                          sq.aircraft, count, sq.base_id,
                                          _TAG_TASK.get(slot.tag) or (_DEAD_TASK.get(slot.role) if obj.type == ObjectiveType.DEAD else None) or _TASK[slot.role], is_pl, slot.tag))
        pkg.support = self._support(pkg)
        pkg.jtac = obj.type in JTAC_OBJECTIVES
        return pkg

    def _land_raid_plan(self, number: int, obj):
        """Su-24M raid on one of our airfields (raids.py): the raiders' field, how many, the bearing they arrive on, and escorts that can reach."""
        from .difficulty import get as _get
        st = self.state
        tb = st.bases[obj.target_id]
        rnd = random.Random(f"{st.campaign_id}:{st.day}:{number}:{obj.target_id}:raid")
        cands = []
        for w in st.enemy_air:
            a = st.assets[w.base_asset_id]
            if factions.striker() in w.types and w.available >= 2 and not a.destroyed and math.hypot(a.x - tb.x, a.y - tb.y) / NM <= ENEMY_RADIUS_NM.get(factions.striker(), 300) * 0.85:
                cands.append((math.hypot(a.x - tb.x, a.y - tb.y), w))
        if not cands:
            return None
        bw = min(cands, key=lambda c: c[0])[1]
        ba = st.assets[bw.base_asset_id]
        lo, hi = (self.d.raid_size if self.d else (2, 2))
        nb = max(2, min(rnd.randint(lo, hi), bw.available))
        nb -= nb % 2
        esc = None
        for w in sorted(st.enemy_air, key=lambda w: math.hypot(st.assets[w.base_asset_id].x - tb.x, st.assets[w.base_asset_id].y - tb.y)):
            a = st.assets[w.base_asset_id]
            if w is bw or w.available < 2 or a.destroyed:
                continue
            d_nm = math.hypot(a.x - tb.x, a.y - tb.y) / NM
            types = [t for t in w.types if t in ENEMY_FIGHTERS and ENEMY_RADIUS_NM.get(t, 0) * 0.85 >= d_nm]
            if types:
                esc = (w.base_asset_id, rnd.choice(types)); break
        brg = math.degrees(math.atan2(ba.y - tb.y, ba.x - tb.x)) % 360          # they come from where they took off
        return {"land": True, "raider": factions.striker(), "brg": round((brg + rnd.uniform(-12, 12)) % 360, 1), "bombers": nb, "bomber_wing": bw.base_asset_id,
                "escort_wing": esc[0] if esc else "", "escort_type": esc[1] if esc else "",
                "escorts": (4 if nb >= 4 else 2) if esc else 0}

    def _raid_plan(self, number: int, obj=None):
        """Bomber raid on the fleet: bearing it arrives on, how many bombers, and escorts that can really reach (range-limited)."""
        st = self.state
        if obj is not None and obj.target_id in st.bases and st.bases[obj.target_id].kind != BaseKind.CARRIER:
            return self._land_raid_plan(number, obj)
        bw = next((w for w in st.enemy_air if factions.bomber() and factions.bomber() in w.types and w.available >= 2 and not st.assets[w.base_asset_id].destroyed), None)
        cv = next((b for b in st.bases.values() if b.kind == BaseKind.CARRIER), None)
        if bw is None or cv is None:
            return None
        rnd = random.Random(f"{st.campaign_id}:{st.day}:{number}:raid")
        nb = 4 if bw.available >= 6 else 2
        esc = None
        for w in sorted(st.enemy_air, key=lambda w: math.hypot(st.assets[w.base_asset_id].x - cv.x, st.assets[w.base_asset_id].y - cv.y)):
            a = st.assets[w.base_asset_id]
            if w is bw or w.available < 2 or a.destroyed:
                continue
            d_nm = math.hypot(a.x - cv.x, a.y - cv.y) / NM
            types = [t for t in w.types if t in ENEMY_FIGHTERS and ENEMY_RADIUS_NM.get(t, 0) * 0.85 >= d_nm]
            if types:
                esc = (w.base_asset_id, rnd.choice(types)); break
        return {"brg": round(rnd.uniform(8, 40), 1), "bombers": nb, "bomber_wing": bw.base_asset_id,
                "escort_wing": esc[0] if esc else "", "escort_type": esc[1] if esc else "",
                "escorts": (4 if nb >= 4 else 2) if esc else 0}

    def _pick_squadron(self, slot: Slot, tx, ty, ledger: Ledger, lead_service):
        """Prefer the lead's service; cross over only when sound (same-service option missing, or the other base is >=30% closer)."""
        cands = [sq for sq in self.state.squadrons.values()
                 if slot.role in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 2 and self._in_range(sq.id, tx, ty)]
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

    def _pick_cap_any(self, ledger: Ledger, lead_service):
        """HAVCAP is mandatory: any fighter will do (it stays with the tanker, which stays behind the FLOT), range aside."""
        cands = [sq for sq in self.state.squadrons.values() if Role.CAP in AIRCRAFT[sq.aircraft].roles and ledger.free[sq.id] >= 2]
        if not cands:
            cands = [sq for sq in self.state.squadrons.values() if Role.CAP in AIRCRAFT[sq.aircraft].roles and sq.available >= 2]
        if not cands:
            return None
        return max(cands, key=lambda sq: (AIRCRAFT[sq.aircraft].service == lead_service, ledger.free.get(sq.id, 0)))

    def _support(self, pkg: Package) -> list:
        lead = pkg.player_flight or next((f for f in pkg.flights if not f.tag), pkg.flights[0])
        lead_home = AIRCRAFT[lead.aircraft].home
        awacs = AWACS_FOR.get(lead_home)      # E-2C for Navy leads (F-14 Link-4), E-3 for USAF leads; none in a WWII faction
        out = [SupportPlan("AWACS", awacs.dcs_class, awacs.label, awacs.altitude_ft, awacs.speed_kts)] if awacs else []
        methods: list = []
        for f in sorted((f for f in pkg.flights if not f.tag), key=lambda f: f is not lead):
            m = AIRCRAFT[f.aircraft].refuel
            if m not in methods and m in TANKER_FOR:          # RefuelMethod.NONE (warbirds, most mods) never gets a tanker
                methods.append(m)
        if not methods:
            return out
        t1 = TANKER_FOR[methods[0]]
        out.append(SupportPlan("TANKER1", t1.dcs_class, t1.label, t1.altitude_ft, t1.speed_kts, methods[0].value))
        if len(methods) > 1:
            t2 = TANKER_FOR[methods[1]]
            out.append(SupportPlan("TANKER2", t2.dcs_class, "Arco" if t2.label == t1.label else t2.label,
                                   t2.altitude_ft, t2.speed_kts, methods[1].value))
        elif lead_home == BaseKind.CARRIER and RECOVERY_TANKER:
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
