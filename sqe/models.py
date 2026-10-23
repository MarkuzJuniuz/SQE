"""Plain data objects shared by every layer. Everything here is JSON-serializable."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum


class Role(str, Enum):
    CAS = "CAS"
    CAP = "CAP"
    TARCAP = "TARCAP"      # a station short of the target, first in, last out (was Role.ESCORT before v0.41.50)
    ESCORT = "ESCORT"      # stays with the strikers and leaves with them (was Role.SWEEP in a strike / DEAD / CAS package)
    SWEEP = "SWEEP"        # Fighter Sweep (COUNTER_AIR package) and the fleet-defence fighters
    SEAD = "SEAD"
    STRIKE = "STRIKE"


class BaseKind(str, Enum):
    AIRFIELD = "AIRFIELD"
    CARRIER = "CARRIER"


class RefuelMethod(str, Enum):
    BASKET = "BASKET"   # probe-and-drogue (Navy jets)
    BOOM = "BOOM"       # F-16 etc.


class AssetKind(str, Enum):
    ARMOR = "ARMOR"
    AIRFIELD = "AIRFIELD"
    SAM = "SAM"
    EWR = "EWR"
    C2 = "C2"
    DEPOT = "DEPOT"
    FUEL = "FUEL"


class ObjectiveType(str, Enum):
    CAS = "CAS"                # close air support on an enemy armor column (JTAC)
    STRIKE = "STRIKE"          # bomb a ground asset
    DEAD = "DEAD"              # destroy an air-defence site
    FLEET_DEFENSE = "FLEET_DEFENSE"  # intercept an enemy bomber raid on the fleet
    COUNTER_AIR = "COUNTER_AIR"  # sweep / hit an enemy airfield's air wing
    BARCAP = "BARCAP"          # defend a friendly base / the fleet


# DEAD packages by aim. "SEAD": HARMs suppress the radars, a Close DEAD package follows. "DEAD": that Close DEAD package (GBUs, radar gate).
# "STANDOFF": one package against a site under a long-range SAM (SA-10): HARM shooters and a Standoff DEAD flight of JSOWs, together.
# "" : the combined package the valve falls back to after repeated failed SEAD days.
SEAD_AIMS = ("SEAD", "STANDOFF")        # packages with HARM shooters timed on the salvo


def task_label(f, obj) -> str:
    """Short role label for package tables and the radio: SEAD, SO DEAD (Standoff DEAD, JSOW), DEAD (Close DEAD, GBU) or the role."""
    if getattr(f, "tag", ""):
        return f.tag
    if getattr(f, "kit", "") == "JSOW":
        return "SO DEAD" if obj.aim == "STANDOFF" else "JSOW"
    if f.role.value == "STRIKE" and obj.type.value == "DEAD":
        return "DEAD"
    return f.role.value                 # one name per job (v0.41.50): TARCAP, ESCORT, SWEEP, CAP, STRIKE, SEAD, CAS


@dataclass
class Base:
    id: str
    name: str
    kind: BaseKind
    x: float = 0.0              # DCS coords (x = north, y = east, metres). Carriers use these.
    y: float = 0.0
    airport: str | None = None  # pydcs airport name for AIRFIELD bases
    defense: float = 1.0        # air-defence strength (Patriot + AAA); the enemy can degrade it, it repairs daily


@dataclass
class Squadron:
    id: str
    name: str
    aircraft: str               # key into aircraft.AIRCRAFT, e.g. "F-14BU"
    base_id: str
    authorized: int
    available: int
    callsign: str = "Viper"
    reserve: int = 0            # aircraft pulled back to a rear field to recover (airwings.py); available is 0 while they rest
    rest_days: int = 0

    @property
    def readiness(self) -> float:
        return self.available / self.authorized if self.authorized else 0.0


@dataclass
class EnemyAsset:
    id: str
    name: str
    kind: AssetKind
    x: float
    y: float
    health: float = 1.0                 # 0..1, 0 = destroyed
    value: int = 5                      # planner priority weight
    defended_by: list[str] = field(default_factory=list)  # ids of SAM/EWR assets covering it
    airport: str | None = None          # AIRFIELD assets: pydcs airport name
    variant: str = ""                   # SAM/EWR flavour: "SA-2", "SA-6", "SA-11", "EWR"; ARMOR: "ARMOR" (moving column) or "GARRISON" (dug in)
    tier: int = 1                       # depth tier: 1 front, 2 Abkhazia, 3 coast / north Caucasus, 4 deep; gated by CampaignState.front
    guards: str = ""                    # GARRISON: id of the SAM site it protects
    suppressed: bool = False            # SAM: radars blinded today (SEAD worked, the launchers are still there); clears at end of day

    @property
    def destroyed(self) -> bool:
        return self.health <= 0.05


@dataclass
class RedSquadron:
    """One typed red squadron inside a wing (v0.41.52): one aircraft type each. v0.41.53: it has its own strength, so it loses jets by type, rests
    and returns on its own and replenishes on its own (airwings.py, war.py); the wing's totals are the sum of its squadrons."""
    id: str
    name: str
    aircraft: str               # pydcs plane class name, e.g. "MiG_29S"
    authorized: int
    available: int = -1         # serviceable jets (-1 = all of them, set in __post_init__)
    reserve: int = 0            # jets pulled back to a rear field to recover; available is 0 while they rest
    rest_days: int = 0
    role: str = ""              # v0.41.106: "escort" = the Mozdok escort squadron: escorts, Mozdok patrols and scrambles only, never sent afield as reinforcement

    def __post_init__(self):
        if self.available < 0:
            self.available = self.authorized


@dataclass
class EnemyAirWing:
    """A red field's air wing: typed squadrons (`sqns`). `authorized`, `available`, `reserve` and `rest_days` are SUMS over the squadrons (v0.41.53);
    assigning `available` spreads the change over them (a loss comes off the strongest squadron first), so code that only knows the wing still works.
    Code that cares about the type uses `lose()`, `types_up`, `available_of()` and `replenish()`."""
    base_asset_id: str
    types: list[str]            # pydcs plane class names the wing's squadrons fly, e.g. ["MiG_29A", "F_4E"]
    squadrons: int = 1          # how many squadrons the wing is made of (equals len(sqns))
    sqns: list = field(default_factory=list)   # [RedSquadron], one type each

    @property
    def authorized(self) -> int:
        return sum(q.authorized for q in self.sqns)

    @property
    def available(self) -> int:
        return sum(q.available for q in self.sqns)

    @available.setter
    def available(self, v: int) -> None:
        """Spread a change in the wing's strength over its squadrons: a loss comes off the squadron with the most jets, a gain goes to the
        squadron furthest below strength that is not resting."""
        v = max(0, int(v))
        while self.available > v:
            self._take_from(self.sqns)
        while self.available < v:
            room = [q for q in self.sqns if not q.reserve and q.available < q.authorized]
            if not room:
                break
            max(room, key=lambda q: q.authorized - q.available).available += 1

    @staticmethod
    def _take_from(qs) -> bool:
        have = [q for q in qs if q.available > 0]
        if not have:
            return False
        max(have, key=lambda q: q.available).available -= 1
        return True

    @property
    def reserve(self) -> int:
        return sum(q.reserve for q in self.sqns)

    @property
    def rest_days(self) -> int:
        return max((q.rest_days for q in self.sqns), default=0)

    def lose(self, aircraft: str | None, n: int) -> int:
        """Remove n serviceable jets, those of `aircraft` first (a shot-down MiG-29S comes off the MiG-29S squadron), the rest from the strongest
        squadron. Returns how many were removed."""
        done = 0
        same = [q for q in self.sqns if aircraft and q.aircraft == aircraft]
        for _ in range(max(0, n)):
            if not (self._take_from(same) or self._take_from(self.sqns)):
                break
            done += 1
        return done

    def available_of(self, types) -> int:
        """Serviceable jets of the given aircraft types (a collection of pydcs class names)."""
        return sum(q.available for q in self.sqns if q.aircraft in types)

    @property
    def types_up(self) -> list:
        """Types that can put up a pair today: a squadron of that type with 2+ serviceable jets (in the wing's order, no repeats)."""
        return list(dict.fromkeys(q.aircraft for q in self.sqns if q.available >= 2))

    def fighter_types(self) -> list:
        """Fighter types that can put up a pair today; if none can (a flight planned earlier, losses since), every fighter type the wing has."""
        from .loadouts import ENEMY_FIGHTERS
        return [t for t in self.types_up if t in ENEMY_FIGHTERS] or [t for t in self.types if t in ENEMY_FIGHTERS]

    def general_types_up(self) -> list:
        """Like `types_up` but without the escort-only squadron: the types red may send afield as reinforcements."""
        return list(dict.fromkeys(q.aircraft for q in self.sqns if q.available >= 2 and q.role != "escort"))

    def replenish(self, n: int) -> None:
        """New jets for the squadrons that are not resting, one at a time to the one furthest below strength."""
        for _ in range(max(0, n)):
            room = [q for q in self.sqns if not q.reserve and q.available < q.authorized]
            if not room:
                break
            max(room, key=lambda q: q.authorized - q.available).available += 1

    def scatter(self, frac: float) -> None:
        """A cratered field: each squadron keeps int(available * frac) jets."""
        for q in self.sqns:
            q.available = int(q.available * frac)


def _spread(total: int, weights: list) -> list:
    """Split `total` over `weights` in proportion (largest remainder), never more than the weight itself."""
    s = sum(weights) or 1
    out = [min(w, int(total * w / s)) for w in weights]
    for i in sorted(range(len(weights)), key=lambda i: -(total * weights[i] / s - out[i])):
        if sum(out) >= total:
            break
        if out[i] < weights[i]:
            out[i] += 1
    return out


def wing_from_dict(w: dict) -> "EnemyAirWing":
    """Load a red wing from a saved dict. Saves from before v0.41.53 keep available / reserve / rest_days on the wing: they are spread over the
    squadrons in proportion to size. Saves from before v0.41.52 have no squadrons: one per type, the jets split evenly."""
    sq = [dict(q) for q in (w.get("sqns") or [])]
    types = list(w.get("types") or [])
    if not sq:
        n = max(1, len(types)); auth = int(w.get("authorized", 0))
        for k, t in enumerate(types or ["MiG_29A"]):
            sq.append({"id": f"{w['base_asset_id']}_{k + 1}", "name": f"{w['base_asset_id']} {k + 1}", "aircraft": t, "authorized": auth // n + (1 if k < auth % n else 0)})
    if any("available" not in q for q in sq):
        auth = [int(q["authorized"]) for q in sq]
        res = _spread(int(w.get("reserve", 0)), auth)
        av = _spread(int(w.get("available", sum(auth))), [a - r for a, r in zip(auth, res)])
        for q, a, r in zip(sq, av, res):
            q["available"], q["reserve"], q["rest_days"] = a, r, (int(w.get("rest_days", 0)) if r else 0)
    keep = {"id", "name", "aircraft", "authorized", "available", "reserve", "rest_days", "role"}
    sqns = [RedSquadron(**{k: v for k, v in q.items() if k in keep}) for q in sq]
    return EnemyAirWing(w["base_asset_id"], types, len(sqns), sqns)


@dataclass
class Objective:
    id: str
    type: ObjectiveType
    target_id: str              # asset id (or base id for BARCAP)
    priority: float
    description: str = ""
    aim: str = ""               # FLEET_DEFENSE raids: what the raiders are after. "" = the airfield itself, else a blue asset id ("bfuel_...", "bdepot_fwd", "bgar_...") or "sector:N"

    def to_dict(self):
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class PlayerProfile:
    aircraft: str               # "F-14BU", "F-16C"
    squadron_id: str
    callsign: str = "Hammer"
    flight_number: int = 1
