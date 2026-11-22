"""Aircraft registry. Add a jet = add one AircraftSpec (+ loadouts in loadouts.py).

Service is derived from where the jet lives: carrier jets are Navy, runway jets are USAF.
A land-based type can never be based on a carrier (checked when a scenario loads).
"""
from __future__ import annotations
from dataclasses import dataclass, field, replace
from dcs import planes
from .models import Role, BaseKind, RefuelMethod


@dataclass
class RouteProfile:
    """Altitudes (ft) and ground speeds (kts) for the route planner. Waypoint speeds are ground speed."""
    depart_alt_ft: int = 8000
    depart_kts: int = 380
    dep_nm: float = 8.0              # DEP is this far from a land base (a carrier uses CARRIER_DEP_NM: the Case III 10 nm departure circle)
    aar_alt_ft: int = 20000
    aar_kts: int = 350
    marshal_alt_ft: int = 22000
    marshal_kts: int = 380
    cap_alt_ft: int = 25000
    cap_kts: int = 380
    cover_kts: int = 0               # S157: the TARCAP / escort / sweep station speed (0 = cap_kts); the BARCAP / support orbits keep cap_kts
    cap_leg_nm: int = 25
    alt_ft: dict = field(default_factory=lambda: {Role.STRIKE: 20000, Role.SEAD: 25000, Role.TARCAP: 24000,
                                                  Role.ESCORT: 26000, Role.SWEEP: 26000, Role.CAS: 9000})
    push_kts: int = 500
    ip_kts: int = 510
    attack_kts: int = 510
    egress_kts: int = 540
    push_nm: int = 60                # PUSH this far before the target
    ip_nm: int = 25
    egress_nm: int = 25
    max_points: int = 50
    med_alt_ft: int = 0              # MED tier altitude (0 = 60% of the role altitude, at least 10,000 ft)
    low_agl_ft: int = 500            # LOW tier: height above the ground, flown from the IP to the egress
    no_low: bool = False             # never planned LOW (FC3 F-15C)
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
    fc3: bool = False                 # Flaming Cliffs 3 jet: no radio presets / channels, plain frequencies only
    first_wp_label: str = ""          # label of the start point; the next point is then 1, 2, ... (0 for every jet except the F-14B, which stays 1 until checked in the cockpit)
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
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.TARCAP, _R.STRIKE}), RefuelMethod.BASKET, 2, 300, 450, True,
        RouteProfile(depart_alt_ft=6000, depart_kts=330, aar_alt_ft=20000, aar_kts=350,
                     marshal_alt_ft=24000, marshal_kts=380, cap_alt_ft=25000, cap_kts=400,
                     alt_ft={_R.STRIKE: 25000, _R.TARCAP: 33000, _R.ESCORT: 33000, _R.SWEEP: 33000, _R.SEAD: 25000, _R.CAS: 12000}, cover_kts=440,
                     push_kts=510, ip_kts=510, attack_kts=510, egress_kts=540, push_nm=70, ip_nm=25, egress_nm=30,
                     tgt_note="JDAM target. Release", special_points=("IP", "ST")),
        first_wp_label="0", bingo_lbs=3000, joker_lbs=4500),
    # S103c (XO 2026-11-18): the plain F-14B, the Syria 2000 Tomcat (research 3c: LANTIRN pod and laser-guided bombs since 1996, NO GPS bombs / JDAM, no Link 16; the B(U) above adds GPS and JDAM). pydcs `F_14B`:
    # the same ten pylons, Phoenix / Sparrow / Sidewinder, LANTIRN and GBU-10 / 12 / 16 / 24 (no GBU-31 / 38). Same roles, route profile and carrier jobs as the B(U): only the type and the STRIKE kit differ (laser
    # bombs, `loadouts._D["F-14B"]`). Neither F-14 has a pydcs datalink, so neither is ever a Link 16 member. The player waypoint scheme is NOT here (S103d); the B(U)'s special-point naming stays B(U)-only.
    "F-14B": AircraftSpec(
        "F-14B", "F-14B Tomcat", "F_14B", BaseKind.CARRIER,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.TARCAP, _R.STRIKE}), RefuelMethod.BASKET, 2, 300, 450, True,
        RouteProfile(depart_alt_ft=6000, depart_kts=330, aar_alt_ft=20000, aar_kts=350,
                     marshal_alt_ft=24000, marshal_kts=380, cap_alt_ft=25000, cap_kts=400,
                     alt_ft={_R.STRIKE: 25000, _R.TARCAP: 33000, _R.ESCORT: 33000, _R.SWEEP: 33000, _R.SEAD: 25000, _R.CAS: 12000}, cover_kts=440,
                     push_kts=510, ip_kts=510, attack_kts=510, egress_kts=540, push_nm=70, ip_nm=25, egress_nm=30,
                     tgt_note="Laser-guided target. Release", special_points=("IP", "ST")),
        first_wp_label="0", bingo_lbs=3000, joker_lbs=4500),
    "FA-18C": AircraftSpec(
        "FA-18C", "F/A-18C Hornet", "FA_18C_hornet", BaseKind.CARRIER,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.TARCAP, _R.STRIKE, _R.SEAD, _R.CAS}), RefuelMethod.BASKET, 1, 300, 450, True,
        RouteProfile(aar_alt_ft=20000, aar_kts=350, marshal_alt_ft=23000, push_kts=500, ip_kts=500,
                     attack_kts=500, egress_kts=540, push_nm=65), first_wp_label="0", bingo_lbs=2500, joker_lbs=3500),
    "F-16C": AircraftSpec(
        "F-16C", "F-16C Viper", "F_16C_50", BaseKind.AIRFIELD,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.TARCAP, _R.STRIKE, _R.SEAD, _R.CAS}), RefuelMethod.BOOM, 1, 280, 450, True,
        RouteProfile(aar_alt_ft=22000, aar_kts=350, marshal_alt_ft=21000), first_wp_label="0", bingo_lbs=2000, joker_lbs=3000),
    "F-15C": AircraftSpec(
        "F-15C", "F-15C Eagle", "F_15C", BaseKind.AIRFIELD,
        frozenset({_R.CAP, _R.SWEEP, _R.ESCORT, _R.TARCAP}), RefuelMethod.BOOM, 1, 400, 480, True,
        RouteProfile(no_low=True, aar_alt_ft=22000, aar_kts=350, marshal_alt_ft=27000, cap_alt_ft=28000, cap_kts=400,
                     alt_ft={_R.TARCAP: 33000, _R.ESCORT: 33000, _R.SWEEP: 33000, _R.STRIKE: 25000, _R.SEAD: 25000, _R.CAS: 12000}, cover_kts=460,
                     push_kts=520, ip_kts=520, attack_kts=520, egress_kts=550, push_nm=80),
        first_wp_label="0", fc3=True, bingo_lbs=3500, joker_lbs=5000),
    # v0.41.358 (F-15E phase, XO 2026-11-10): AI-only strike squadrons on the OLD AI model F_15E (not the RAZBAM F-15ESE module, so nobody needs to own it; pydcs gives it the callsigns Dude ... Tahoe).
    # Roles: STRIKE only (judgment call: it adds strike jets, never takes a fighter or HARM seat). Combat radius 450 nm = judgment call (the F-15E carries more than the F-15C's 400 here; public
    # figures for the F-15E vary widely with the load, "from memory" about 600 nm hi-lo-hi, so this stays in line with the table's game scale). Route values are the F-15C's strike values.
    "F-15E": AircraftSpec(
        "F-15E", "F-15E Strike Eagle", "F_15E", BaseKind.AIRFIELD,
        frozenset({_R.STRIKE}), RefuelMethod.BOOM, 2, 450, 480, False,
        RouteProfile(aar_alt_ft=22000, aar_kts=350, marshal_alt_ft=27000, cap_alt_ft=28000, cap_kts=400,
                     alt_ft={_R.STRIKE: 25000, _R.SEAD: 25000, _R.CAS: 12000},
                     push_kts=520, ip_kts=520, attack_kts=520, egress_kts=550, push_nm=80,
                     tgt_note="JDAM target. Release"),
        first_wp_label="0", bingo_lbs=3500, joker_lbs=5000),
    # S104 (XO 2026-11-17 / 18): the F-117A Nighthawk, blue's small AI-only night squadron (`sqe/f117.py`: night only, EWRs and SAM sites no red air covers). pydcs `F_117A`: Pinpoint Strike only, two bay stations (1, 2),
    # laser-guided GBU-10 / GBU-12 / GBU-27 only (no GPS weapon: NOT in JDAM_JETS), 8,255 kg of fuel, no pylons for tanks or missiles. AI-ONLY (player_flyable False; the DCS F-117A is not a flyable module of the
    # old AI model SQE uses, and the planner never offers its slot to a person). Role STRIKE only. Combat radius 450 nm: JUDGMENT CALL (no public combat-radius figure was found; Allied Force sorties flew from Aviano and
    # Spangdahlem on tanker-supported legs, the table runs in game scale like the F-15E's 450). Route values: a subsonic stealth jet (about Mach 0.9, so 480 kt ground speed at 22,000 ft; no supersonic dash),
    # the strike altitude of a laser-bomb jet; judgment calls. `no_low`: never a low-level run (the F-117 bombed from medium / high altitude at night; the LOW tier of the route planner is 500 ft AGL).
    "F-117A": AircraftSpec(
        "F-117A", "F-117A Nighthawk", "F_117A", BaseKind.AIRFIELD,
        frozenset({_R.STRIKE}), RefuelMethod.BOOM, 1, 450, 480, False,
        RouteProfile(no_low=True, aar_alt_ft=22000, aar_kts=330, marshal_alt_ft=22000, marshal_kts=330, alt_ft={_R.STRIKE: 22000},
                     push_kts=480, ip_kts=480, attack_kts=480, egress_kts=480, push_nm=60, ip_nm=25, egress_nm=25,
                     tgt_note="Laser-guided target. Release"),
        first_wp_label="0", bingo_lbs=2500, joker_lbs=3500),
    # v0.41.360 (campaign rules plan Phase 10c part 2, XO): roles CAS and STRIKE. The STRIKE role is conditional: the planner gives an A-10C squadron a STRIKE slot only on a plain supply strike
    # (fuel / depot) with no live SAM over the site or its run-in and no red fighter flight that can reach it (`packages.PackageBuilder._a10_supply_strike`, `STRIKE_CONDITIONAL`). Its tgt_note was
    # "CAS: check in with JTAC" and only the STRIKE route reads it (the CAS point has its own text), so it is the release note now.
    "A-10C": AircraftSpec(
        "A-10C", "A-10C Warthog", "A_10C_2", BaseKind.AIRFIELD,
        frozenset({_R.CAS, _R.STRIKE}), RefuelMethod.BOOM, 1, 230, 300, True,
        RouteProfile(depart_alt_ft=4000, depart_kts=250, dep_nm=6, low_agl_ft=300, aar_alt_ft=15000, aar_kts=270, marshal_alt_ft=10000,
                     marshal_kts=250, alt_ft={_R.CAS: 9000, _R.STRIKE: 9000}, push_kts=300, ip_kts=300,
                     attack_kts=300, egress_kts=330, push_nm=35, ip_nm=12, egress_nm=15,
                     tgt_note="Release"), first_wp_label="0", bingo_lbs=1500, joker_lbs=2500),
    # S103b (XO 2026-11-18): the A-10A, the Syria 2000 Warthog (no JDAM, no Litening pod: the Precision Engagement upgrade is 2005 to 2007, `syria-2000-research.md` section 3). pydcs `A_10A`: the Flaming Cliffs
    # level jet (FC3, like the F-15C: no cockpit presets, plain frequencies, F10 ECM switch, always counted tuned), so it is PLAYER-FLYABLE for anybody who owns FC3; the AI model is the same one. It takes
    # the same stores as the A-10C kit minus the targeting pod (pylon 10; the A_10A pylon tables carry the ALQ-184, AGM-65D, CBU-87 / 97, BRU-42 Mk-82 and AIM-9M of that kit with the same CLSIDs). Same
    # route profile, roles and refuelling profile as the A-10C (the airframe is the same). first_wp_label "0" is the F-15C's / A-10C's: NOT checked in an A-10A cockpit.
    "A-10A": AircraftSpec(
        "A-10A", "A-10A Warthog", "A_10A", BaseKind.AIRFIELD,
        frozenset({_R.CAS, _R.STRIKE}), RefuelMethod.BOOM, 1, 230, 300, True,
        RouteProfile(depart_alt_ft=4000, depart_kts=250, dep_nm=6, low_agl_ft=300, aar_alt_ft=15000, aar_kts=270, marshal_alt_ft=10000,
                     marshal_kts=250, alt_ft={_R.CAS: 9000, _R.STRIKE: 9000}, push_kts=300, ip_kts=300,
                     attack_kts=300, egress_kts=330, push_nm=35, ip_nm=12, egress_nm=15,
                     tgt_note="Release"), first_wp_label="0", fc3=True, bingo_lbs=1500, joker_lbs=2500),
}
# S103a (XO 2026-11-18): the A-10 and F-14 variants a campaign can be created with ("Era Equipment"), {key: label} in the order the picker shows them. The key is what the campaign
# state saves (`a10_variant`, `f14_variant`); today it is an AIRCRAFT key. The A-10A is S103b, the F-14B S103c, the A-10C II S103e. The A-10C key is today's `A_10C_2` model (DCS "A-10C II") and STAYS that
# (old saves, Caucasus identity). S103e (XO 2026-11-18): "A-10C2", labelled "A-10C II (late)", is a separate choice that flies the SAME pydcs `A_10C_2` model for now: the real A-10C II is about 2015 or later,
# out of era for 2000 and 2006, and a later job may map "A-10C" to pydcs `A_10C` (see changes-detail S103e for how the two pydcs models differ).
A10_VARIANTS = {"A-10A": "A-10A (FC3)", "A-10C": "A-10C", "A-10C2": "A-10C II (late)"}
F14_VARIANTS = {"F-14B": "F-14B", "F-14BU": "F-14B(U)"}
F14_KEYS = frozenset(F14_VARIANTS)             # S103c: every F-14 key: the places that meant "the F-14B(U)" test this
AIRCRAFT["A-10C2"] = replace(AIRCRAFT["A-10C"], key="A-10C2", display="A-10C II Warthog")        # S103e: the A-10C entry again (one source), its own key and name
JDAM_HOGS = frozenset({"A-10C", "A-10C2"})     # S103e: the Hogs with the Precision Engagement kit (JDAM / WCMD GUIDED kit, Litening pod); the A-10A has none
HOG_KEYS = frozenset(A10_VARIANTS)             # S103b: every A-10 key: the places that meant "the A-10C" (CAS master, tanker profile, slow climber, refit time) test this
STRIKE_CONDITIONAL = HOG_KEYS                  # v0.41.360: airframes whose STRIKE role is offered only on a clean supply strike (see the A-10C entry above)


def era_aircraft(key: str, a10: str | None = None, f14: str | None = None) -> str:
    """The airframe a theatre pack's squadron slot flies in a campaign with these Era Equipment choices: a slot that names an A-10 (or F-14) key flies the chosen variant, every other key is itself.
    None = no choice (the pack's own key)."""
    if a10 and key in A10_VARIANTS:
        return a10
    if f14 and key in F14_VARIANTS:
        return f14
    return key


@dataclass(frozen=True)
class SupportSpec:
    dcs_class: str
    label: str
    altitude_ft: int
    speed_kts: int


AWACS_FOR = {BaseKind.CARRIER: SupportSpec("E_2C", "Magic", 25000, 300),
             BaseKind.AIRFIELD: SupportSpec("E_3A", "Overlord", 30000, 400)}
# Basket tanker speed matters: AI Tomcats fail to plug the drogue when the tanker is set slow (DCS forums).
# v0.41.335 (decision 11): the probe-and-drogue jets (F-14, F/A-18C) are refuelled by the Navy's S-3B, never a land tanker (no KC-135MPRS in the force); the S-3B's altitude and
# speed are judgment calls (the recovery orbit's 6000 ft / 250 kts is too low and slow for a strike package; unchecked in DCS)
TANKER_FOR = {RefuelMethod.BASKET: SupportSpec("S_3B_Tanker", "Shell", 12000, 300),
              RefuelMethod.BOOM: SupportSpec("KC_135", "Arco", 22000, 350)}
RECOVERY_TANKER = SupportSpec("S_3B_Tanker", "Shell", 6000, 250)
