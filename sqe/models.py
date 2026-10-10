"""Plain data objects shared by every layer. Everything here is JSON-serializable."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum


class Role(str, Enum):
    CAS = "CAS"
    CAP = "CAP"
    SWEEP = "SWEEP"
    ESCORT = "ESCORT"
    SEAD = "SEAD"
    STRIKE = "STRIKE"


class BaseKind(str, Enum):
    AIRFIELD = "AIRFIELD"
    CARRIER = "CARRIER"


class RefuelMethod(str, Enum):
    BASKET = "BASKET"   # probe-and-drogue (Navy jets)
    BOOM = "BOOM"       # F-16 etc.
    NONE = "NONE"       # no air-to-air refuelling (warbirds, most trainers and many mods): never gets a tanker


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
class EnemyAirWing:
    base_asset_id: str
    types: list[str]            # pydcs plane class names, e.g. ["MiG_29A", "F_4E"]
    authorized: int
    available: int
    squadrons: int = 1          # how many squadrons the wing is made of (display / flavour)


@dataclass
class Objective:
    id: str
    type: ObjectiveType
    target_id: str              # asset id (or base id for BARCAP)
    priority: float
    description: str = ""

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
