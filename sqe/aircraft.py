"""Aircraft registry. Add a jet = add one AircraftSpec (+ loadouts in loadouts.py).

Service is derived from where the jet lives: carrier jets are Navy, runway jets are USAF.
A land-based type can never be based on a carrier (checked when a scenario loads).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from dcs import planes
from .models import Role, BaseKind, RefuelMethod


@dataclass
class RouteProfile:
    """Altitudes (ft) and ground speeds (kts) for the route planner. Waypoint speeds are ground speed."""
    depart_alt_ft: int = 8000
    depart_kts: int = 380
    aar_alt_ft: int = 20000
    aar_kts: int = 350
    marshal_alt_ft: int = 22000
    marshal_kts: int = 380
    cap_alt_ft: int = 25000
    cap_kts: int = 380
    cap_leg_nm: int = 25
    alt_ft: dict = field(default_factory=lambda: {Role.STRIKE: 20000, Role.SEAD: 25000, Role.ESCORT: 24000,
                                                  Role.SWEEP: 26000, Role.CAS: 9000})
    push_kts: int = 500
    ip_kts: int = 510
    attack_kts: int = 510
    egress_kts: int = 540
    push_nm: int = 60                # PUSH this far before the target
    ip_nm: int = 25
    egress_nm: int = 25
    max_points: int = 50
    tgt_note: str = "Release"
    special_points: tuple = ()


@dataclass(frozen=True)
class AircraftSpec:
    key: str
    display: str
    dcs_class: str
    home: BaseKind
    roles: frozenset
    refuel: RefuelMethod
    crew: int
    combat_radius_nm: int
    cruise_kts: int
    player_flyable: bool = False
    profile: RouteProfile = field(default_factory=RouteProfile)
    first_wp_label: str = ""          # label of the start point; the next point is then 1, 2, ... (F-15C: 'B'; F-16C: '0')
    bingo_lbs: int = 2500             # starting estimates: tune to your own flying
    joker_lbs: int = 3500
    # Intra-flight frequency band (MHz). Must be a band ONLY the COMM2 radio covers (VHF), because DCS puts a
    # group's frequency on the first radio able to tune it; UHF would overwrite a COMM1 preset.
    comm2_band_mhz: tuple = (127.0, 137.0)

    def wp_label(self, me_index: int) -> str:
        """Label the cockpit uses for mission-editor waypoint number me_index (1 = start point)."""
        if self.first_wp_label:
            return self.first_wp_label if me_index == 1 else str(me_index - 1)
        return str(me_index)

    @property
    def service(self) -> str:
        return "Navy" if self.home == BaseKind.CARRIER else "USAF"

    @property
    def dcs_type(self):
        return getattr(planes, self.dcs_class)


_R = Role
AIRCRAFT: dict[str, AircraftSpec] = {
    "F-14BU": AircraftSpec(
        "F-14BU", "F-14B(U) Tomcat", "F_14BU", BaseKind.CARRIER,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.STRIKE}), RefuelMethod.BASKET, 2, 300, 450, True,
        RouteProfile(depart_alt_ft=6000, depart_kts=330, aar_alt_ft=20000, aar_kts=350,
                     marshal_alt_ft=24000, marshal_kts=380, cap_alt_ft=25000, cap_kts=400,
                     alt_ft={_R.STRIKE: 25000, _R.ESCORT: 26000, _R.SWEEP: 28000, _R.SEAD: 25000, _R.CAS: 12000},
                     push_kts=510, ip_kts=510, attack_kts=510, egress_kts=540, push_nm=70, ip_nm=25, egress_nm=30,
                     tgt_note="JDAM target: coords below. Release", special_points=("IP", "ST")),
        bingo_lbs=3000, joker_lbs=4500),
    "FA-18C": AircraftSpec(
        "FA-18C", "F/A-18C Hornet", "FA_18C_hornet", BaseKind.CARRIER,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.STRIKE, _R.SEAD}), RefuelMethod.BASKET, 1, 300, 450, True,
        RouteProfile(aar_alt_ft=20000, aar_kts=350, marshal_alt_ft=23000, push_kts=500, ip_kts=500,
                     attack_kts=500, egress_kts=540, push_nm=65), bingo_lbs=2500, joker_lbs=3500),
    "F-16C": AircraftSpec(
        "F-16C", "F-16C Viper", "F_16C_50", BaseKind.AIRFIELD,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.STRIKE, _R.SEAD}), RefuelMethod.BOOM, 1, 280, 450, True,
        RouteProfile(aar_alt_ft=22000, aar_kts=350, marshal_alt_ft=21000), first_wp_label="0", bingo_lbs=2000, joker_lbs=3000),
    "F-15C": AircraftSpec(
        "F-15C", "F-15C Eagle", "F_15C", BaseKind.AIRFIELD,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT}), RefuelMethod.BOOM, 1, 400, 480, True,
        RouteProfile(aar_alt_ft=22000, aar_kts=350, marshal_alt_ft=27000, cap_alt_ft=28000, cap_kts=400,
                     alt_ft={_R.ESCORT: 27000, _R.SWEEP: 30000, _R.STRIKE: 25000, _R.SEAD: 25000, _R.CAS: 12000},
                     push_kts=520, ip_kts=520, attack_kts=520, egress_kts=550, push_nm=80),
        first_wp_label="B", bingo_lbs=3500, joker_lbs=5000),
    "A-10C": AircraftSpec(
        "A-10C", "A-10C Warthog", "A_10C_2", BaseKind.AIRFIELD,
        frozenset({_R.CAS}), RefuelMethod.BOOM, 1, 230, 300, True,
        RouteProfile(depart_alt_ft=4000, depart_kts=250, aar_alt_ft=15000, aar_kts=270, marshal_alt_ft=10000,
                     marshal_kts=250, alt_ft={_R.CAS: 9000, _R.STRIKE: 9000}, push_kts=300, ip_kts=300,
                     attack_kts=300, egress_kts=330, push_nm=35, ip_nm=12, egress_nm=15,
                     tgt_note="CAS: check in with JTAC"), bingo_lbs=1500, joker_lbs=2500),
}


@dataclass(frozen=True)
class SupportSpec:
    dcs_class: str
    label: str
    altitude_ft: int
    speed_kts: int


AWACS_FOR = {BaseKind.CARRIER: SupportSpec("E_2C", "Magic", 25000, 300),
             BaseKind.AIRFIELD: SupportSpec("E_3A", "Overlord", 30000, 400)}
# Basket tanker speed matters: AI Tomcats fail to plug the drogue when the tanker is set slow (DCS forums).
TANKER_FOR = {RefuelMethod.BASKET: SupportSpec("KC135MPRS", "Texaco", 20000, 350),
              RefuelMethod.BOOM: SupportSpec("KC_135", "Arco", 22000, 350)}
RECOVERY_TANKER = SupportSpec("S_3B_Tanker", "Shell", 6000, 250)
