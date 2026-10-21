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
class EnemyAirWing:
    base_asset_id: str
    types: list[str]            # pydcs plane class names, e.g. ["MiG_29A", "F_4E"]
    authorized: int
    available: int
    squadrons: int = 1          # how many squadrons the wing is made of (display / flavour)
    reserve: int = 0            # aircraft pulled back to a rear field to recover (airwings.py); available is 0 while they rest
    rest_days: int = 0


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
