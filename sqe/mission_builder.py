"""Package -> SQE_Sortie.miz (terrain, date and airfields come from the campaign's theatre pack).

* Your flight (and wingmen) sit hot on the catapult/runway; the F-14B(U) INS is pre-aligned.
* Every other friendly flight is already airborne and holds at MARSHAL until PUSH (a clock time; nobody waits for anybody).
* Enemy defenders are late-activated and arrive at the target at TOT +/- 1-2 minutes, from the ENEMY side.
* Tanker/AWACS sit well back from enemy bases with a HAVCAP; carriers always have escorts; coalition bases always have SAM/AAA.
* SAM sites and armor columns are single groups (a battery needs its radar and launchers in one group).
"""
from __future__ import annotations
import copy
import datetime
import hashlib
import math
import random
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from dcs import action, condition, mapping, planes, ships, task, triggers, vehicles
from dcs.mission import Mission, StartType
from dcs.point import PointAction
from . import theatres, weather
from dcs.unit import Skill
from dcs.unitgroup import VehicleGroup

from . import briefing as brief, callsigns, carcass, ground, profiles, relief, sams
from . import seacheck as seac
from . import threatmap as tm
from .aircraft import AIRCRAFT
from .debrief import Manifest, install_hook
from .difficulty import Difficulty
from .fighter_stations import FighterStations, ESCORT_AFTER_TOT_S, TARCAP_AFTER_TOT_S
from .support_caps import SupportCaps
from .red_air_picture import RedAirPicture, A2A_ZONE_NM
from .raid_spawns import RaidSpawns
from .strike_tasks import StrikeTasks, DEAD_GATE_KM, SEAD_WAVE_KM, TRACK_RADARS, SEARCH_RADARS, KPH
from .kneeboard import latlon, render_pages
from .loadouts import LoadoutLibrary, enemy_cap_loadout, ENEMY_FIGHTERS
from .models import SEAD_AIMS, AssetKind, BaseKind, ObjectiveType, Role, task_label
TARCAP_LEAD_S = 0             # v0.41.1: a TARCAP arrives WITH the first flight it covers (the HARM shooters): the SAM has to split its attention,
                              # and its exposure ends with the HARM salvo. v0.41.0's 5-minute head start let the SA-10 kill six waiting Eagles.
FIELD_DETECT_NM = tm.FIELD_DETECT_NM   # an alert field scrambles when blue comes within this of the field (less for fields close to the fight)
RUNWAY_HALF_LEN_M = 2600.0    # v0.41.48: ground groups keep out of a corridor this far either side of the airfield reference point along each runway heading (pydcs has only the heading; judgment call, long enough for the longest Caucasus strips)
RUNWAY_HALF_WIDTH_M = 120.0   # ...and this far either side of the centreline (runway about 45-60 m wide plus a margin; judgment call)
TARCAP_BEHIND_NM = 16         # v0.41.43: with a JSOW flight the TARCAP holds this far behind the JSOW launch point, further back (stepped) until it is outside live medium-range SAM rings (judgment call)
ESCORT_BEHIND_NM = 8          # v0.41.42: a package escort in a Standoff DEAD stations itself this far behind the JSOW flight's launch point (judgment call)
TARCAP_COVER_MAX_NM = 35      # v0.41.42: the TARCAP / escort circle round the shooters' launch points is at most this big (judgment call; was 20 nm wanted, moved off every SAM)
COVER_ZONE_NM = 20            # v0.41.0: a TARCAP / escort engages inside this circle round the package's launch points (where the shooters are)
LATE_ATTACK_S = 600           # v0.41.16: an AI strike flight drops only within this of its TOT
CV_RECOVER_NM = 10            # v0.41.17: AI carrier flights (and your wingmen) are recovered this far from the boat instead of joining the deck queue
RCV_NM = 8                    # v0.41.10: an AI flight's recovery entry point, this far from its field...
RCV_SPREAD = (0, 30, -30, 60, -60)    # ...on its own bearing (degrees off the way it comes home), by stack slot
SA10_REACH_NM = 31            # v0.41.14: the farthest an SA-10 fired at our jets in the runs (54-57 km)
RED_KEEP_NM = 45              # v0.41.10: red patrol stations keep this far from our marshal point and fields (was 120 / 80)
SWEEP_AFTER_TOT_S = 120       # v0.41.13: a sweep holds until 2 min after the first package it covers is over the target
HOMEWARD_ENGAGE_NM = 20       # v0.41.5: after its hold a TARCAP / escort / sweep still engages air within this of itself on the way home
from .packages import LONG_RANGE_A2A     # the long-range shooters; F-16 and F/A-18 are secondary air-to-air
STAGGER = {Role.SWEEP: -90, Role.ESCORT: -90, Role.SEAD: -60, Role.TARCAP: -TARCAP_LEAD_S}      # seconds relative to the strikers' push (BMS-style)


SEAD_ENGAGE_NM = 30            # a SEAD flight, or a fighter held at its stand-off point, engages only what is within this of that point
DEAD_SEAD_LEAD_S = 300         # in a DEAD package the SEAD flight is on the site this long before the DEAD flight
JSOW_TRAIL_S = 120             # v0.41.11: a Standoff DEAD's JSOW flight pushes this long after its HARM shooters, so it reaches SA-10 range once the
                               # HARMs have landed (about 2 min of flight). Was 0 (together): the v0.41.10 run, the SA-10 fired at the JSOW jets while the HARMs were in the air
                               # (on two axes), the HARMs go first, the JSOWs land a few minutes later on a radar that is dead or has shut down.
                               # v0.39.19 had the JSOW flight 160 s ahead so the WEAPONS would land together: it went in alone and died (v0.39.19 run, Viper 2).
A2G_ROLES = (Role.STRIKE, Role.SEAD, Role.CAS)
NATIVE_ECM = {"F-15C"}         # jets with a jammer that switch DCS's ECM on over the attack leg (the ECM script counts the F-15C too since v0.40.9)
AAM_WEAPONS = 264241152       # DCS weapon flags: air-to-air missiles (a Fighter Sweep's RTB when out of ammo)
# DCS weapon flags for "RTB when out of ammo": bombs (guided, iron, cluster), air-to-ground missiles (HARM, JSOW, Maverick) and rockets.
# Not guns and not air-to-air missiles, so a flight goes home once its air-to-ground load is gone.
A2G_WEAPONS = 14 | 240 | 768 | 4161536 | 30720
# Air-to-ground jets whose loadouts carry radar missiles (AIM-120, AIM-54; checked in loadouts.py): after the attack they may shoot back.
SHOOTS_BACK = {"F-16C", "FA-18C", "F-14BU"}
SPAWN_SEP_M = 2000            # airborne flights never appear closer than this to each other (same height band, same minute)


def carrier_heading(x, y, prefer):
    """A heading with 120 nm of open sea ahead (and 8 nm off the coast all the way), nearest to `prefer`. None if there is none."""
    for d in (0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90, 120, -120, 150, -150, 180):
        h = (prefer + d) % 360
        if seac.clear_run(x, y, h, 120 * NM, 8 * NM):
            return h
    return None


def carrier_station(state, b, tx, ty, min_enemy_nm) -> tuple | None:
    """Where the carrier sits for a sortie against (tx, ty): slid back along the line of retreat (up to 60 nm, swinging up to 110 degrees)
    onto open water, at least min_enemy_nm from the target and every enemy fighter base. (x, y, heading), or None = it stays home.
    The mission builder moves the carrier here; the planner uses the same spot to time the carrier's SEAD packages (v0.39.22)."""
    enemies = tm.fighter_bases(state)
    need = min_enemy_nm * NM
    away = (bearing(b.x, b.y, tx, ty) + 180) % 360
    for nm in range(0, 66, 10):
        for da in ((0,) if nm == 0 else (0, 25, -25, 50, -50, 80, -80, 110, -110)):
            x, y = offset(b.x, b.y, away + da, nm * NM)
            if not seac.open_water(x, y, 25 * NM):
                continue
            if dist(x, y, tx, ty) >= need and all(dist(x, y, ex, ey) >= need for ex, ey in enemies):
                h = carrier_heading(x, y, away)
                if h is not None:
                    return (x, y, h)
    return None


def stagger(package, role) -> int:
    """SEAD leads the strikers by five minutes in a DEAD package (the radars must be blind before the DEAD flight commits); the sweep and the
    escorts keep their usual 30 s spacing around it: the sweep ahead, the escorts behind."""
    if package.objective.type == ObjectiveType.DEAD and package.objective.aim == "DEAD":      # the DEAD stage: the SEAD package went in 25 min earlier
        return {Role.SWEEP: -60, Role.ESCORT: -60, Role.TARCAP: -TARCAP_LEAD_S}.get(role, 0)
    if package.objective.type == ObjectiveType.DEAD:
        jsow = package.objective.aim in SEAD_AIMS and any(getattr(f, "kit", "") == "JSOW" for f in package.flights)
        if jsow and role == Role.STRIKE:                     # the JSOW flight (Standoff DEAD): with the HARM shooters, on its own axis
            return -DEAD_SEAD_LEAD_S + JSOW_TRAIL_S
        if role == Role.SEAD:
            return -DEAD_SEAD_LEAD_S
        if role in (Role.ESCORT, Role.SWEEP):
            return -DEAD_SEAD_LEAD_S - 30
        if role == Role.TARCAP:                              # TARCAP: on station before anyone else
            return -DEAD_SEAD_LEAD_S - TARCAP_LEAD_S
    return STAGGER.get(role, 0)
from .packages import Package, folded_n_def
from .radio import RadioCfg, RadioLayout, RadioPlan, apply_player_presets, build_radio_plan
from .routes import jsow_launch_xy, JSOW_KEEP_HIGH_NM, AVOID_NM, avoid_circles, HARM_LAUNCH_NM, OBJECTIVE_ACTIONS, NM, FT, Wpt, assign_times, bearing, dist, hold_leave_s, in_progress, leg_seconds, make_geometry, objective_wp, offset, plan_route, terrain_clear, home_leg_ft
from .state import CampaignState

F = VehicleGroup.Formation
MAIN_TASK = {Role.CAP: task.CAP, Role.TARCAP: task.CAP, Role.ESCORT: task.FighterSweep, Role.SWEEP: task.FighterSweep, Role.SEAD: task.SEAD,
             Role.STRIKE: task.PinpointStrike, Role.CAS: task.CAS}
ARMOR_DENSITY = (0.5, 1.5)    # vehicles in a front-line column = the base mix x (0.5 + 1.5 x the sector's enemy strength): 2x at full strength, 1x at 33%
                              # killed CAP pairs 51 to 67 nm out; 70 is just past that)
LASER = ["1688", "1687", "1686", "1685", "1684", "1683", "1682", "1681"]


@dataclass
class MissionOptions:
    launch_offset_s: int = 60           # takeoff buffer: you are on the cat/runway at start; the briefed takeoff is this many SECONDS in (negative = hurry)
    hold_minutes: int = 2               # slack at MARSHAL before PUSH, minutes. Negative = you must be quicker than the natural pace
    cap_minutes: int = 40               # time on station for CAP flights
    ai_unlimited_fuel: bool = True      # Retribution-style: ON until the push, OFF for the combat leg, ON again from egress
    enemy_unlimited_fuel: bool = False
    ai_despawn_on_land: bool = True
    base_defenses: bool = True
    carrier_escorts: bool = True
    enemy_cap_engage_nm: int = 50       # enemy patrol fighters chase no further than this (0 = unlimited); v0.41.61: fixed, no settings box
    friendly_cap_engage_nm: int = 50    # HAVCAP / BASECAP likewise (0 = unlimited); v0.41.61: fixed, no settings box
    fighter_engage_nm: int = 40         # AI escorts and sweeps chase no further than this (0 = unlimited)
    fighter_engage_minutes: int = 5     # AI escorts, sweeps, SEAD stop engaging this many minutes after the TOT and fly on (alert pairs: +5). 0 = no time limit
    player_is_ai: bool = False          # test: your own flight is built as an AI flight (no player / client slot) and gets the AI behaviour too (stand-off, engage window)
    fighter_standoff: bool = True       # AI escorts and sweeps stop short of live SAM cover instead of flying into it
    f14_special_names: bool = True
    weather_mode: str = "clear"         # see weather.py: clear | procedural | scattered | broken | overcast | rain | storm
    reactive: bool = True               # extra enemy fighters / blue alert pairs that launch during the sortie (reactive.py)
    ai_land_carrier: str = "always"     # v0.41.18: AI recovery short of a carrier: always | home (your deck only) | never
    ai_land_field: str = "never"        # v0.41.18: the same for airfields
    splash_damage: bool = True          # blasts on ground units near an air-to-ground weapon's impact (the hook)
    ecm_script: bool = False            # SQE's own jamming model in the mission hook (ecm.py). Off: DCS's own ECM, the AI decides when it is locked
    carcasses: bool = True              # dead wrecks at damaged / destroyed ground sites (see carcass.py)
    carcass_weight: float = 0.25        # how much of a live unit one wreck counts toward the unit limit
    carcass_range_nm: int = 40          # only sites this close to the route get wrecks
    full_map: bool = False              # stress test: build everything that exists (see _spawn_everything); the unit limit is off
    max_units: int = 250                # the mission's unit limit (wrecks are trimmed, furthest first, to fit under it)
    merge_enemy_pct: int = 100          # folded packages: biggest enemy-air need + this % of the others'
    carrier_min_enemy_nm: int = 150     # the carrier group is moved back along the line of retreat until it is at least this far from the fight
    player_is_client: bool = False
    carrier_speed_kts: int = 15
    carrier_tacan: str = "74X"
    carrier_icls: int = 11
    carrier_link4_mhz: int = 336
    carrier_atc_mhz: float = 305.0
    layout: RadioLayout = field(default_factory=RadioLayout)


class _Veh:
    """Case-insensitive vehicle lookup (pydcs forks rename a few classes)."""
    def __init__(self, ns): self._ns = ns

    def __getattr__(self, name):
        for a in dir(self._ns):
            if a.lower() == name.lower():
                return getattr(self._ns, a)
        raise AttributeError(name)


_AD, _UN, _AR = _Veh(vehicles.AirDefence), _Veh(vehicles.Unarmed), _Veh(vehicles.Armor)


def _vt(name):
    for ns in (_AD, _UN, _AR):
        try:
            return getattr(ns, name)
        except AttributeError:
            continue
    return None


SITES = {
    "AAA":    [("ZU_23_Emplacement", 3), ("Ural_375_ZU_23", 2), ("ZSU_23_4_Shilka", 1)],
    "MANPAD": [("SA_18_Igla_manpad", 4), ("SA_18_Igla_comm", 1)],
    "SA-2":   [("S_75M_Volhov", 4), ("SNR_75V", 1), ("ZSU_23_4_Shilka", 1)],
    "SA-3":   [("x_5p73_s_125_ln", 4), ("snr_s_125_tr", 1), ("p_19_s_125_sr", 1)],
    "SA-6":   [("Kub_2P25_ln", 3), ("Kub_1S91_str", 1), ("ZSU_23_4_Shilka", 1)],
    "SA-11":  [("SA_11_Buk_LN_9A310M1", 3), ("SA_11_Buk_SR_9S18M1", 1), ("SA_11_Buk_CC_9S470M1", 1)],
    "SA-10":  [("S_300PS_5P85C_ln", 2), ("S_300PS_5P85D_ln", 2), ("S_300PS_40B6M_tr", 1), ("S_300PS_64H6E_sr", 1), ("S_300PS_54K6_cp", 1)],
    "SA-15":  [("Tor_9A331", 2), ("ZSU_23_4_Shilka", 1)],
    "SA-19":  [("x_2S6_Tunguska", 2)],
    "SA-8":   [("Osa_9A33_ln", 2)],
    "EWR":    [("x_1L13_EWR", 1)], "EWR55": [("x_55G6_EWR", 1)],
}
SOFT = {
    AssetKind.C2:    [("ZIL_131_KUNG", 2), ("Ural_375", 3), ("ZSU_23_4_Shilka", 2)],
    AssetKind.FUEL:  [("ATZ_10", 4), ("Ural_375", 2), ("ZSU_23_4_Shilka", 1)],
    AssetKind.DEPOT: [("Ural_375", 6), ("KAMAZ_Truck", 2), ("ZSU_23_4_Shilka", 2)],
    AssetKind.AIRFIELD: [("ZSU_23_4_Shilka", 2), ("Ural_375", 3)],
    AssetKind.ARMOR: [("T_72B", 4), ("BMP_2", 3), ("BTR_80", 2), ("ZSU_23_4_Shilka", 1)],
}


@dataclass
class BuildResult:
    miz: Path
    manifest: Manifest
    radio: RadioPlan
    waypoints: list
    package: Package
    timeline: dict
    text: dict
    counts: dict = field(default_factory=dict)
    whois: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    seed: str = ""
    merged: list = field(default_factory=list)      # extra packages folded into this mission


class MissionBuilder(StrikeTasks, FighterStations, SupportCaps, RedAirPicture, RaidSpawns):
    def __init__(self, state: CampaignState, d: Difficulty, opts: MissionOptions | None = None,
                 loadouts: LoadoutLibrary | None = None, rng: random.Random | None = None):
        self.state, self.d = state, d
        self.o = opts or MissionOptions()
        self.lo = loadouts or LoadoutLibrary()
        self.rng = rng or random.Random()
        self._runway_busy = set()                                      # bases whose runway / catapult already holds a group at mission start
        self._rwyq, self._flag_n, self._prwy, self._alerts = [], 9000, "", []
        self._launch_pts = {}                                          # package id -> [(x, y)] where its HARM / JSOW / strike flights launch (the cover zone)             # alert groups waiting for a runway (the hook lines them up), trigger flags, your runway
        self._air_spawns = []                                          # [(x, y, alt_m, t)]: where and when each airborne flight appears, so no two appear on top of each other

    # =====================================================================================================
    def build(self, package: Package, out_path, extras: list | tuple = (), ruins: list | tuple = (), preroll: dict | None = None) -> BuildResult:
        """extras: other packages (AI only) folded into this mission: same area, starting at or after yours. They share the ground world,
        the support aircraft and the enemy air picture, and fly live with their own push, TOT and stagger."""
        o = self.o
        st = self.state = copy.copy(self.state)                       # a private view: the carrier may be moved back for this sortie only
        st.bases = {k: copy.copy(v) for k, v in st.bases.items()}
        pf = package.player_flight
        if pf is None:
            raise ValueError("choose your flight first")
        warns: list = []
        self.warns = warns
        self._anchor_id = package.id
        self._fcalls, self._ulabels, self._pkg_who = [], {}, {}
        self._gates = []                                                # DEAD flights that turn back when the site's radars are still up
        self._sead_grps = {}                                            # site id -> the SEAD flights' group names (all merged packages); the gate aborts when they are all down
        self._blind_site = None
        extras = [x for x in extras if any(not f.tag for f in x.flights)]
        ruins = [x for x in ruins if any(not f.tag for f in x.flights)]
        self._preroll, self._ruin_sites = dict(preroll or {}), []
        from . import terrainmask
        if not terrainmask.available():
            warns.append("ground sites were placed with the rough built-in coastline (it can be 1-3 km off, and it has no rivers): run the terrain scan once (Settings) for exact placement")
        package = self._gather_support(package, extras)
        air_pkg = copy.copy(package)
        air_pkg.n_def = folded_n_def(package, extras, o.merge_enemy_pct)       # enemy air: the biggest package's need plus a share of the others'
        out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)

        theatres.use(st.theatre)
        m = Mission(theatres.terrain())
        self.m, self.t = m, m.terrain
        self.usa, self.red = m.country("USA"), m.country("Russia")
        date = st.campaign_date()
        hh, mm = int(package.start[:2]), int(package.start[3:5])
        start = datetime.datetime(date.year, date.month, date.day, hh, mm)
        self._start_min, self._red_intel, self._red_sel = hh * 60 + mm, [], []
        m.start_time = start
        clock = lambda s: (start + datetime.timedelta(seconds=s)).strftime("%H:%M:%S")
        date_str = start.strftime("%d %b %Y").upper()
        self.wx = weather.for_package(st, o.weather_mode, theatres.active(), package.start)
        self.wx_notes = []
        self._weather(m, date)

        tx, ty = self._target_xy(package)
        self._fleet_obj = package.objective.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE)
        self._pull_back_carriers(tx, ty)
        tx, ty = self._target_xy(package)
        seed = f"{st.campaign_id}:{st.day}:{st.sortie_counter + 1}:{package.number}"   # every FLY re-rolls the layout
        self.vrng = random.Random(seed)
        self.seed_code = hashlib.md5(seed.encode()).hexdigest()[:5].upper()
        self.site_pos, self.armor_id, self.armor_center = {}, None, None
        self._svc_k, self.cas_tot = {}, None
        tx, ty = self._jitter_primary(package, tx, ty)
        pbase = st.bases[pf.base_id]
        pspec = AIRCRAFT[pf.aircraft]
        fleet_obj = package.objective.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE)
        tgt_asset = None if fleet_obj else st.assets[package.objective.target_id]
        mshl_xy = tm.safe_marshal(st, (pbase.x, pbase.y), bearing(pbase.x, pbase.y, tx, ty), (tx, ty))
        geom = make_geometry(pbase.x, pbase.y, tx, ty, pspec.profile, mshl_xy, carrier=pbase.kind == BaseKind.CARRIER)
        # enemy CAP stations are planned first so the egress can stay clear of them too (they sit 20-25 nm in front of their own base)
        # v0.41.10: red patrols keep RED_KEEP_NM from our marshal point and fields (was 120 / 80 nm: with the marshal 15 nm behind the base
        # since v0.41.6, 120 nm pushed red's patrols back past Sukhumi and Gudauta, and they never came to their SAMs' help)
        keep0 = [(geom.mshl[0], geom.mshl[1], RED_KEEP_NM)]
        for bid in dict.fromkeys(f.base_id for f in package.flights):
            keep0.append((st.bases[bid].x, st.bases[bid].y, 130 if st.bases[bid].kind == BaseKind.CARRIER else RED_KEEP_NM))
        self._cap_plan = self._plan_cap_stations(air_pkg, tx, ty, geom, keep0)
        if tgt_asset is not None:                      # steer the egress away from SAM rings and CAP
            skip = {tgt_asset.id} if package.objective.type == ObjectiveType.DEAD else set()      # a DEAD target is the one thing we are killing
            avoid = [(c["x"], c["y"], 35) for c in self._cap_plan] + [(ex, ey, 40) for ex, ey in tm.fighter_bases(st)]
            geom.egr = (tm.first_safe_egress(st, tx, ty, geom.hdg, skip, avoid=avoid) or
                        tm.first_safe_egress(st, tx, ty, geom.hdg, skip) or
                        tm.safe_egress(st, tx, ty, geom.hdg, pspec.profile.egress_nm, tm.cluster_ids(tgt_asset)) or geom.egr)
        manifest = Manifest(st.campaign_id, st.sortie_counter + 1, package.id, st.day)
        manifest.cur_pkg = package.id
        self.groups_by_asset, self.flight_groups = {}, []

        # ---- bases, base defenses, carrier + escorts --------------------------------------------------------
        self.ship, self.apt = {}, {}
        self._main_base = pbase.id                    # your home field (AI landing setting); since v0.41.30 every field gets the same air defence
        for bs in st.bases.values():
            if bs.kind == BaseKind.AIRFIELD:
                self.t.airports[bs.airport].set_blue()
        for a in st.assets.values():
            if a.kind == AssetKind.AIRFIELD and a.airport:
                self.t.airports[a.airport].set_red()
        # v0.41.28: a raid scramble also builds the field the raid is coming for (the XO's Kobuleti run: the raided field had no defences
        # because nothing launched from it)
        raided_ = [package.objective.target_id] if (package.objective.type == ObjectiveType.FLEET_DEFENSE and package.objective.target_id in st.bases) else []
        for bid in dict.fromkeys([f.base_id for f in package.flights] + raided_ + [f.base_id for x in list(extras) + list(ruins) for f in x.flights if not f.tag]):
            self._place_base(st.bases[bid], tx, ty)
        atc = (o.carrier_atc_mhz if pbase.kind == BaseKind.CARRIER else self.t.airports[pbase.airport].atc_radio.uhf_hz / 1e6)

        # ---- enemy ground: everything the route touches is live from the first second ----------------------------------
        polyline = [(pbase.x, pbase.y), geom.mshl, geom.push, geom.ip, (tx, ty), geom.egr]
        self._poly = polyline
        self._spawn_opfor_ground(package, tx, ty, manifest, polyline)
        if o.full_map:
            self._spawn_everything(package, manifest, tx, ty)

        # ---- radios + support -----------------------------------------------------------------------------------------
        div = self._divert(pbase)
        div_mhz = self.t.airports[div.airport].atc_radio.uhf_hz / 1e6 if div.airport else None
        atc_vhf = (self.t.airports[pbase.airport].atc_radio.vhf_high_hz / 1e6) if (pbase.kind != BaseKind.CARRIER and getattr(self.t.airports[pbase.airport], "atc_radio", None)
                                                                              and self.t.airports[pbase.airport].atc_radio.vhf_high_hz) else None
        div_vhf = (self.t.airports[div.airport].atc_radio.vhf_high_hz / 1e6) if (div.airport and getattr(self.t.airports[div.airport], "atc_radio", None)
                                                                          and self.t.airports[div.airport].atc_radio.vhf_high_hz) else None
        plan = build_radio_plan(package, st, atc, self.rng, o.layout, RadioCfg(o.carrier_tacan, o.carrier_link4_mhz), div_mhz, div.name, atc_vhf, div_vhf)
        tanker_xy, awacs_unit, hav_xy = self._place_support(package, plan, geom, extras)

        # ---- timeline: YOUR times. Roles are staggered around the strikers' push (sweep, SEAD, escorts go first) ---------
        launch_s = float(o.launch_offset_s)
        skip1 = {tgt_asset.id} if (tgt_asset is not None and package.objective.type == ObjectiveType.DEAD) else ()
        geom.tier = self._pick_tier(geom, pf.role, pspec.profile, tx, ty, skip1)
        self._flight_plans(geom, package, tx, ty, skip1)
        pw = plan_route(pf.role, (pbase.x, pbase.y), geom, pspec.profile, is_player=True, tanker_xy=None, jsow=getattr(pf, "kit", "") == "JSOW",
                        jsow_side=self._jsow_side(package, geom), keep_out=self._umbrella_keep(package), harm_deg=self._harm_deg(package, geom))
        dep_s = launch_s + 60 + dist(pbase.x, pbase.y, pw[0].x, pw[0].y) / (pspec.profile.depart_kts * 0.514444) * 1.12     # roll + climb-out to the first point (DEP off a carrier, else the marshal)
        self._dep_s = dep_s
        assign_times(pw, dep_s)
        mshl = next((w for w in pw if w.action in ("HOLD", "CAPORBIT")), pw[-1])
        k = pw.index(mshl)
        leg_m = leg_seconds(mshl, pw[k + 1]) if (mshl.action == "HOLD" and k + 1 < len(pw)) else 0.0
        player_push = math.ceil((mshl.eta_s + (0 if pf.role == Role.CAP else o.hold_minutes * 60) + leg_m) / 60.0) * 60.0
        player_push = max(player_push, math.ceil((dep_s + 120) / 60.0) * 60.0)
        leave_s = hold_leave_s(pw, player_push)
        P0 = player_push - stagger(package, pf.role)                         # the strikers' push; everyone else is relative to it
        push_of = lambda f: P0 + (0 if f.tag else stagger(package, f.role))
        assign_times(pw, dep_s, player_push)
        tgt = objective_wp(pw) or pw[-1]
        egr = next((w for w in pw if w.name == "EGR"), pw[-1])
        rtb_s = egr.eta_s + leg_seconds(egr, Wpt("RTB", pbase.x, pbase.y, 0, 300))
        tl = {"launch": clock(launch_s), "marshal": clock(mshl.eta_s), "push": clock(player_push), "tot": clock(tgt.eta_s),
              "egress": clock(egr.eta_s), "rtb": clock(rtb_s), "push_s": player_push, "tot_s": tgt.eta_s, "rtb_s": rtb_s}

        # ---- friendly flights --------------------------------------------------------------------------------------------
        despawn, pkg_table = [], []
        self._sup_cts = []                                                   # HAVCAP / base CAP orbit tasks: their stop time is extended once the merged packages are known
        self._striker_egr = []                                               # v0.41.40: [((x, y), egress time)] of this mission's strikers
        self._holds = []                                                     # v0.41.10: TARCAP / escort holds, extended to the last package over their target area
        self._snipe_at = {}                                                  # v0.41.10: id(group) -> the station waypoint where max-range shots begin
        self._callins = []
        self._recov = []                                                     # v0.41.25: the recovery net (see _recov_net)                                                   # v0.41.10: red patrols called in to the SAM site they guard
        self._launch_pts[package.id] = self._launch_points(package, geom)    # v0.41.42: known before any flight is built (an escort / TARCAP may be built first)
        striker_tots = []                                                    # v0.41.38: each ground-attack flight's own target time (strike / SEAD / CAS), for the TARCAP hold
        for idx, f in enumerate(package.flights):
            g, tot_f = self._spawn_flight(package, f, plan, geom, tanker_xy, hav_xy, push_of(f), tgt.eta_s, rtb_s, idx, manifest, despawn)
            if f.is_player:
                tot_f = tgt.eta_s
            if f.role in (Role.STRIKE, Role.SEAD, Role.CAS) and not f.tag and tot_f:
                striker_tots.append(float(tot_f))
            if f.role == Role.CAS and tot_f:
                self.cas_tot = tot_f
            pkg_table.append({"callsign": f.callsign, "role": task_label(f, package.objective), "push": clock(push_of(f)) if not f.tag else "-",
                              "tot": clock(tot_f) if tot_f else "-", "you": f.is_player})
        whois = self._datalinks(package)

        # ---- enemy air picture (known CAP airborne from the start + alert aircraft that scramble when detected) ----
        keep = [(geom.mshl[0], geom.mshl[1], RED_KEEP_NM)] + [(p[0], p[1], 100) for p in (hav_xy,) if p is not None] + \
               [(p[0], p[1], 60) for p in (tanker_xy,) if p is not None]          # v0.41.7: the tanker is forward; 100 nm round it pushed red's patrols out of the fight
        for bid in dict.fromkeys(f.base_id for f in package.flights):
            keep.append((st.bases[bid].x, st.bases[bid].y, 130 if st.bases[bid].kind == BaseKind.CARRIER else RED_KEEP_NM))
        keep += self._fleet_keepout()
        self._spawn_air_picture(air_pkg, tx, ty, tgt.eta_s, geom, manifest, keep)
        self._spawn_cas_support(package, plan, geom, manifest)
        self._harm_refs = []                                           # [(x, y, t)]: SEAD waves timed in this mission; merged SEAD packages on the same ground match them
        if package.objective.type == ObjectiveType.DEAD and package.objective.aim in SEAD_AIMS and package.objective.target_id:
            hs_ = self._harm_time(package, geom, pbase, P0)
            if hs_ is not None:
                t_ = st.assets[package.objective.target_id]
                self._harm_refs.append((t_.x, t_.y, hs_))
        merged = self._add_merged(package, extras, P0, manifest, despawn, atc, div_mhz, div.name, clock, ruins)
        # HAVCAP and base CAP guard the tanker, AWACS and home field: they stay until the last flight of ANY package in this mission is home
        # (they used to leave 40 min after your TOT, so later merged packages flew with the tanker and AWACS unguarded)
        last_home = max([m_["rtb_s"] for m_ in merged if not m_.get("struck")] + [rtb_s]) + 300
        for ct_ in self._sup_cts:
            if last_home > ct_.params.get("stopCondition", {}).get("time", 0):
                ct_.stop_after_time(int(last_home))
        # v0.41.38 (XO 2026-10-20): a TARCAP / escort stays until the LAST ground-attack flight of its own package is off target (+ the usual after-time),
        # not just until its own station time (when the player flew the TARCAP, tgt was the TARCAP's own station: it left 7.5 min after arriving)
        own_ = [((tx, ty), max(striker_tots))] if striker_tots else []
        self._last_striker_s = max(striker_tots) if striker_tots else None
        self._extend_holds([((tx, ty), tgt.eta_s)] + own_ + [(m_["txy"], m_["tot_s"]) for m_ in merged if not m_.get("struck") and m_.get("txy")],
                           egr_events=self._striker_egr)
        manifest.cur_pkg = ""
        self._intel = ([geom.tier.reason] if geom.tier.reason else []) + list(self._red_intel)
        self._spawn_reactive(package, extras, tx, ty, tgt.eta_s, geom, manifest, despawn)
        self._dry_pass()
        self._place_carcasses()
        manifest.merged = [{k: v for k, v in m_.items() if k in ("id", "number", "objective", "type", "tot_s", "rtb_s")} for m_ in merged if not m_.get("struck")]
        bx, by = geom.push
        m.coalition["blue"].bullseye = {"x": bx, "y": by}

        # ---- waypoint table as the jet numbers it ------------------------------------------------------------------------------
        to_note = self._short(pbase.name)
        if pbase.kind == BaseKind.CARRIER:                       # Case III wording: the leg to DEP is the departure radial
            to_note += f", depart radial {int(bearing(pbase.x, pbase.y, *geom.dep)):03d}"
        rows = [("TAKEOFF", pbase.x, pbase.y, launch_s, "", "", to_note)]
        for w in pw:
            rows.append((w.name, w.x, w.y, w.eta_s, "AGL 0" if w.agl else (f"{w.alt_ft}AGL" if w.rad else f"{w.alt_ft // 1000}K"), w.speed_kts, w.note))
        rows.append(("RTB", pbase.x, pbase.y, rtb_s, "-", 300, self._rtb_note(pspec, pbase)))
        n_route = len(rows)
        rows.append(("DIVERT", div.x, div.y, 0, "-", "", div.name))
        if tanker_xy:
            rows.append(("TKR", tanker_xy[0], tanker_xy[1], 0, f"{pspec.profile.aar_alt_ft // 1000}K", pspec.profile.aar_kts, "Top off. See COMMS for TACAN"))
        rows.append(("BULLS", bx, by, 0, "", "", "Bullseye reference"))
        player_wps = [Wpt(r[0], r[1], r[2], 0 if (r[4] in ("", "-", "AGL 0") or str(r[4]).endswith("AGL")) else int(str(r[4]).rstrip("K")) * 1000,
                          int(r[5]) if str(r[5]).isdigit() else 0, r[6]) for r in rows]
        self._trailing_steerpoints(package, rows[n_route:], pspec)
        kn_rows, hook_wps = [], []
        for i, r in enumerate(rows, 1):
            leg = ""
            if i < n_route:
                nx = rows[i]
                leg = f"{int(bearing(r[1], r[2], nx[1], nx[2])):03d}/{dist(r[1], r[2], nx[1], nx[2]) / NM:.0f}"
            tstr = ""
            if r[3]:
                tstr = clock(r[3])                                  # every time on the card is hh:mm:ss
            win = {"PUSH": "+/-30s", "TGT": "+/-1m", "SEAD": "+/-1m"}.get(r[0], "")
            if r[0] == "MSHL":
                win = f"hold to {clock(leave_s)}"
            kn_rows.append({"wp": pspec.wp_label(i), "name": r[0], "time": tstr, "alt": r[4], "kts": str(r[5]), "leg": leg, "win": win,
                            "note": r[6] if r[0] in ("TGT", "TKR", "RTB", "DIVERT", "TAKEOFF") else ""})
            if r[0] not in ("TAKEOFF", "DIVERT", "TKR", "BULLS"):
                hook_wps.append((pspec.wp_label(i), r[0], r[1], r[2]))

        # ---- codes, fuel, text, hook, kneeboard -----------------------------------------------------------------------------
        mode3 = self._mode3(package, pf)
        laser = self._laser(package, pf)
        x = {"date": date_str, "mode3": mode3, "laser": laser, "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}",
             "bullseye": latlon(bx, by, self.t), "divert": div.name, "weather": weather.describe(self.wx), "weather_short": weather.metar(self.wx), "wx_notes": self.wx_notes,
             "link16": any(r["stn"] != "-" for r in whois), "pkg_table": pkg_table,
             "n_def": air_pkg.n_def, "intel": self._intel, "merged_nums": [m_["number"] for m_ in merged if not m_.get("struck")]}
        text = brief.build_text(st, package, tl, plan, self.rng, (tx, ty), x)
        m.set_description_text(text["full"])
        m.set_description_bluetask_text(text["blue_task"])
        m.set_sortie_text(f"{date_str}  day {st.day}: {package.objective.description}")
        awl = next((s.label for s in package.support if s.slot == "AWACS"), "AWACS")
        calls = []
        t1 = next((s for s in package.support if s.slot == "TANKER1"), None)
        if t1 is not None:
            calls.append((25, f"{t1.label.upper()} to {pf.callsign.upper()}: on station, TACAN {plan.tacan.get('TANKER1', '')}, " + (f"{plan.freq('TANKER1'):.3f}." if pspec.fc3 else f"{plan.where('TANKER1')}.")))
        calls.append((P0, f"{awl.upper()} to {pf.callsign.upper()}: package, push, push, push."))
        if tgt.eta_s - 300 > 60:
            calls.append((tgt.eta_s - 300, f"{awl.upper()} to {pf.callsign.upper()}: five minutes to TOT."))
        calls += self._fcalls
        with tempfile.TemporaryDirectory(prefix="sqe_kb_") as td:
            sound, sound_you = self._squelch(td)
            for gt_ in self._gates:                                    # every SEAD flight of this mission on the site, merged packages included (they spawned above)
                gt_["seads"] = list(self._sead_grps.get(gt_["site"], []))
            install_hook(m, st.campaign_id, manifest.sortie, package.id, despawn if o.ai_despawn_on_land else [], manifest.player_unit,
                         group=pf.callsign, calls=[(t_, x_, f"TO {pf.callsign.upper()}:" in x_.upper()) for t_, x_ in calls], wps=[], sound=sound, sound_you=sound_you, flights=self._ulabels,
                         enemy_air=[u for g_ in manifest.groups if g_["kind"] == "enemy_air" for u in g_["units"]],
                         sites=self._hook_sites(manifest), ruins=self._ruin_sites, gates=self._gates, ai_test=bool(o.player_is_ai), gate_km=DEAD_GATE_KM, jams=(self._jams if o.ecm_script else {}), jamw=(self._jamw if o.ecm_script else {}),
                         watch=[g_.name for f_, g_ in self.flight_groups if not f_.tag and not f_.is_player],
                         done_after=max([float(tgt.eta_s)] + [float(m_["tot_s"]) for m_ in (merged or [])]), awacs=awl.upper(), splash=bool(o.splash_damage),
                         rwyq=self._rwyq, prwy=self._prwy, alerts=self._alerts,
                         cfg={"splash_damage": bool(o.splash_damage), "ecm_script": bool(o.ecm_script), "version": __import__("sqe").__version__,
                              # v0.41.17: your wingmen leave at the boat (10 nm) once you are back, after your TOT
                              "cvrec": self._wing_recovery(pbase, tgt.eta_s), "recov": list(self._recov)})
            tdata = ""
            if pf.role in (Role.STRIKE, Role.SEAD, Role.CAS):
                tdata = f"TARGET  {latlon(tx, ty, self.t)}   ({package.objective.description})"
            ctx = {"date": date_str, "callsign": f"{pf.callsign}-1", "role": task_label(pf, package.objective), "objective": package.objective.description,
                   "comm1": plan.comm1, "comm2": plan.comm2, "fc3": pspec.fc3, "waypoints": kn_rows, "jet": pspec.display,
                   "numbering": (f"{pspec.first_wp_label} for the start point, then 1, 2, 3..." if pspec.first_wp_label else "waypoint 1 = start point"),
                   "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}", "weather": weather.metar(self.wx), "mode3": mode3, "laser": laser,
                   "bullseye": latlon(bx, by, self.t), "whois": whois, "threats": text["threats"], "n_def": air_pkg.n_def, "target_data": tdata,
                   "others": [{"line": f"#{m_['number']} {m_['type']}: {m_['objective']}", "push": m_["push"], "tot": m_["tot"], "rtb": m_["rtb"], "flights": m_["flights"],
                               "status": ("already struck, heading home; its target is in ruins" if m_.get("struck") else "airborne when you start" if m_.get("underway") else "")} for m_ in merged],
                   "intel": [l_.replace(" are within reach of the target area and may be sent to reinforce.", " may reinforce.").replace(" are on cockpit alert and may launch to help.", " on alert, may launch.") for l_ in self._intel],
                   "zulu_note": self._zulu_note(), "msa": relief.msa_ft(polyline)}
            for pg in render_pages(td, ctx):
                m.add_aircraft_kneeboard(pspec.dcs_type, pg)
            warns += list(dict.fromkeys(self.lo.warnings))
            counts = self._counts()
            self._free_locked_speeds(m)
            self._add_ship_warehouses(m)
            self._save_without_carrier_slots(m, out_path)
        return BuildResult(out_path, manifest, plan, player_wps, package, tl, text, counts, whois, warns, self.seed_code, merged)

    def _skip_landing(self, base) -> bool:
        """v0.41.18: does an AI flight going home to this base get recovered short of it instead of landing (Settings: AI landings)?"""
        mode = (self.o.ai_land_carrier if base.kind == BaseKind.CARRIER else self.o.ai_land_field) or "never"
        return mode == "always" or (mode == "home" and base.id == getattr(self, "_main_base", None))

    def _wing_recovery(self, pbase, tot_s):
        """v0.41.18: the hook's watch on your wingmen: recovered at your home base (10 nm) once you are back after your TOT, when that base type is
        set to skip landings (always / home both apply: it is your home). None otherwise."""
        o = self.o
        if o.player_is_ai or not self._skip_landing(pbase):
            return None
        if pbase.kind == BaseKind.CARRIER:
            return {"cv": self.ship[pbase.id].units[0].name, "r": CV_RECOVER_NM * NM, "t": float(tot_s or 0)} if pbase.id in self.ship else None
        p = self.apt[pbase.id].position
        return {"x": p.x, "z": p.y, "r": CV_RECOVER_NM * NM, "t": float(tot_s or 0)}

    def _add_merged(self, anchor, extras, P0, manifest, despawn, atc, div_mhz, div_name, clock, ruins=()) -> list:
        """Fold extra packages into this mission. Their flights are AI, airborne on their own schedule (late-activated so they push at
        THEIR time), with their own geometry, route and TOT. Support (tanker, AWACS, HAVCAP, base CAP) is shared, so tag flights are skipped."""
        from types import SimpleNamespace
        st = self.state
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        used = {f.callsign for f in anchor.flights}
        out = []
        ruin_ids = {x.id for x in ruins}
        for k, x in enumerate(list(extras) + [r for r in ruins if r.id not in {e.id for e in extras}]):
            xp = copy.deepcopy(x)
            xp.flights = [f for f in xp.flights if not f.tag]
            for f in xp.flights:
                f.is_player = False
                nm, no = f.callsign.rsplit(" ", 1)
                no = int(no)
                while f"{nm} {no}" in used:           # callsigns must be unique across the whole mission
                    no += 1
                f.callsign = f"{nm} {no}"; used.add(f.callsign)
            manifest.cur_pkg = xp.id
            # the flight the package's timeline is built on; a SEAD package's JSOW slingers never lead it (its event is the HARM salvo, which they are timed to)
            lead = max(xp.flights, key=lambda f: ({Role.STRIKE: 3, Role.SEAD: 3, Role.CAS: 3}.get(f.role, 1) if getattr(f, "kit", "") != "JSOW" else 2) * 10 + f.count)
            base2, spec2 = st.bases[lead.base_id], AIRCRAFT[lead.aircraft]
            tx2, ty2 = self._target_xy(xp)
            tx2, ty2 = self._jitter_primary(xp, tx2, ty2)
            tgt2 = st.assets[xp.objective.target_id]
            mshl2 = tm.safe_marshal(st, (base2.x, base2.y), bearing(base2.x, base2.y, tx2, ty2), (tx2, ty2))
            geom2 = make_geometry(base2.x, base2.y, tx2, ty2, spec2.profile, mshl2, carrier=base2.kind == BaseKind.CARRIER)
            skip = {tgt2.id} if xp.objective.type == ObjectiveType.DEAD else set()
            geom2.egr = (tm.first_safe_egress(st, tx2, ty2, geom2.hdg, skip) or
                         tm.safe_egress(st, tx2, ty2, geom2.hdg, spec2.profile.egress_nm, tm.cluster_ids(tgt2)) or geom2.egr)
            # timeline: this package pushes (start difference) minutes after yours. An EARLIER package has a negative offset: it is already underway when the mission starts.
            P0x = P0 + (hm(xp) - hm(anchor)) * 60.0
            geom2.tier = self._pick_tier(geom2, lead.role, spec2.profile, tx2, ty2, {tgt2.id} if xp.objective.type == ObjectiveType.DEAD else ())
            self._flight_plans(geom2, xp, tx2, ty2, {tgt2.id} if xp.objective.type == ObjectiveType.DEAD else ())
            pw2 = plan_route(lead.role, (base2.x, base2.y), geom2, spec2.profile, is_player=True, tanker_xy=None, jsow=getattr(lead, "kit", "") == "JSOW",
                             keep_out=self._umbrella_keep(xp))
            assign_times(pw2, 0.0, P0x + stagger(xp, lead.role))
            pu = next((w for w in pw2 if w.name == "PUSH"), None)
            if pu is not None and P0x + stagger(xp, lead.role) < pu.eta_s:            # it pushes before it could even have reached its marshal point in this timeline: shift the whole leg after PUSH
                sh = (P0x + stagger(xp, lead.role)) - pu.eta_s
                for w in pw2:
                    w.eta_s += sh
            tg2 = objective_wp(pw2) or pw2[-1]
            if xp.objective.type == ObjectiveType.DEAD and xp.objective.aim in SEAD_AIMS and tg2.action == "SEAD":
                # the builder's sync: a SEAD package on the same ground as one already timed in this mission reaches its HARM point with it.
                # The planner's estimate can be minutes off (v0.39.21 run: it timed the USAF package from Kutaisi, the mission flew it from Senaki,
                # and the Navy HARMs came 3.7 minutes after the USAF ones); here the real routes are known.
                ref_ = next((r for r in self._harm_refs if dist(r[0], r[1], tgt2.x, tgt2.y) <= SEAD_WAVE_KM * 1000), None)
                if ref_ is None:
                    self._harm_refs.append((tgt2.x, tgt2.y, tg2.eta_s))
                elif abs(ref_[2] - tg2.eta_s) >= 5:
                    dt_ = ref_[2] - tg2.eta_s
                    P0x += dt_
                    for w in pw2:
                        w.eta_s += dt_
            eg2 = next((w for w in pw2 if w.name == "EGR"), pw2[-1])
            rtb2 = eg2.eta_s + leg_seconds(eg2, Wpt("RTB", base2.x, base2.y, 0, 300))
            struck = tg2.eta_s < -60
            if xp.id in ruin_ids and not struck:
                continue                                       # an earlier package that has not struck yet and is not a merge candidate: left to the war sim
            ruined = False
            if struck and xp.id in self._preroll and xp.objective.type not in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE) \
                    and xp.objective.target_id not in self.groups_by_asset and len(self._ruin_sites) < 3:
                self._add_ruin(xp, tx2, ty2, self._preroll[xp.id], manifest)
                ruined = True
                if rtb2 <= 0:
                    continue                                   # struck and already landed: just the ruins, no aircraft
            elif rtb2 <= 0 or struck:                          # it has already struck and gone home before the mission starts: not flown, the war sim resolves it
                if xp.id not in ruin_ids:
                    self.warns.append(f"package #{xp.number} had already finished before your start and is not in this mission")
                continue
            if not ruined:
                self._spawn_opfor_ground(xp, tx2, ty2, manifest, [(base2.x, base2.y), geom2.mshl, geom2.push, geom2.ip, (tx2, ty2), geom2.egr])
            freqs = [SimpleNamespace(callsign=f.callsign, mhz=round(128.0 + 0.5 * ((k * 7 + i * 3) % 18), 1)) for i, f in enumerate(xp.flights)]
            plan2 = SimpleNamespace(package_flights=freqs, freq=lambda slot, _k=k: 252.0 + 3.5 * (_k + 1))
            tots = []
            cas_tot = None
            for i, f in enumerate(xp.flights):
                psh = P0x + stagger(xp, f.role)
                g, tot_f = self._spawn_flight(xp, f, plan2, geom2, None, None, psh, tg2.eta_s, rtb2, i, manifest, despawn)
                if tot_f:
                    tots.append(tot_f)
                if f.role == Role.CAS and tot_f:
                    cas_tot = tot_f
            if xp.objective.type == ObjectiveType.CAS and xp.jtac:
                self.armor_id = xp.objective.target_id
                self.armor_center = self.site_pos.get(self.armor_id)
                self.cas_tot = cas_tot
                self._spawn_cas_support(xp, plan2, geom2, manifest)
            tot = max(tots) if tots else tg2.eta_s
            out.append({"id": xp.id, "number": xp.number, "objective": xp.objective.description, "type": xp.objective.type.value, "txy": (tx2, ty2),
                        "start": xp.start, "push": clock(P0x), "tot": clock(tot), "rtb": clock(rtb2), "tot_s": tot, "rtb_s": rtb2, "underway": P0x < 0, "struck": ruined,
                        "flights": ", ".join(f"{f.callsign} {f.count}x{f.aircraft}" for f in xp.flights)})
        return out

    def _start_for(self, key) -> StartType:
        """The first group at a base starts on the runway (or catapult); every other one starts hot on the ramp and taxis. v0.39.24 run: two
        Tomcat alert pairs were both put on the carrier's catapult and three of the four jets were destroyed at mission start."""
        if key in self._runway_busy:
            return StartType.Warm
        self._runway_busy.add(key)
        return StartType.Runway

    def _alert_group(self, side, name, typ, ap, maintask, start, size, toward, key=None):
        """An alert / scramble group: hot on the ramp, held, and it taxis when called (v0.40.7; the runway stays free for flights that are
        scheduled to take off). A field with no parking for the type: the group waits, hidden, for the runway instead, and the mission
        hook lines it up there when it is called, at least RWY_STAGGER_S after the last group that went from that runway (and only once you
        have left it, at your own field). -> (group, "ramp" | "rwy")"""
        # v0.41.0: no taxiing. The v0.40.10 run's ramp starts took 3 to 11 minutes from the call to the air and two pairs at Sukhumi never
        # made it (DCS AI taxiing); the runway-queued pairs were airborne in about 45 s. Every alert pair now waits hidden and appears on the
        # runway ALERT_TAXI_S after it is called (the taxi it would have done), RWY_STAGGER_S apart at one runway.
        g = self.m.flight_group_from_airport(side, name, typ, ap, maintask=maintask, start_type=StartType.Runway, group_size=size)
        g.late_activation = True
        self._note_alert(name, ap.name, typ)
        self._rwyq.append({"g": name, "f": self._flag_n, "b": key or f"{side.name}:{ap.name}"})
        return g, "rwy"

    def _note_alert(self, name, where, typ) -> int:
        """A trigger flag for this alert group (its scramble trigger sets it) and its line in the hook's alert log."""
        self._flag_n += 1
        self._alerts.append({"g": name, "f": self._flag_n, "b": where, "ty": getattr(typ, "id", str(typ))})
        return self._flag_n

    def _from_airport(self, side, name, typ, ap, maintask, start, size, quiet=False):
        """None when the runway is taken and the field has no parking for this type: a second group on the runway would collide with the first."""
        try:
            return self.m.flight_group_from_airport(side, name, typ, ap, maintask=maintask, start_type=start, group_size=size)
        except Exception:
            if not quiet:
                self.warns.append(f"{name} left out: {ap.name} has its runway taken and no parking for the type")
            return None

    def _clear_spawn(self, s0, wps, act_s) -> None:
        """Two flights on the same route and schedule (the two SEAD flights of a package already underway) used to appear at the same point
        and height and fly into each other at mission start: v0.39.24 run, 4 pairs collided in the first 2 minutes and 9 jets were lost."""
        nxt = next((w for w in wps[1:] if dist(s0.x, s0.y, w.x, w.y) > 100), None)
        hdg = bearing(s0.x, s0.y, nxt.x, nxt.y) if nxt is not None else 0.0
        s0.x, s0.y, alt = self._sep(s0.x, s0.y, s0.alt_ft * FT, hdg, act_s)
        s0.alt_ft = alt / FT

    def _sep(self, x0, y0, a0, hdg, t=0.0):
        """An airborne group's spawn point, moved 2 km to the side and 1000 ft up (further if needed) when another group would appear within
        2 km and 300 m of it, within 90 s of it. Both coalitions share the list: a mid-air at spawn kills either side."""
        for k in range(12):
            x, y = offset(x0, y0, hdg + 90, SPAWN_SEP_M * ((k + 1) // 2) * (1 if k % 2 else -1)) if k else (x0, y0)
            alt = a0 + 1000 * FT * ((k + 1) // 2)
            if not any(dist(x, y, ox, oy) < SPAWN_SEP_M and abs(alt - oa) < 300 and abs(t - ot) < 90 for ox, oy, oa, ot in self._air_spawns):
                break
        self._air_spawns.append((x, y, alt, t))
        return x, y, alt

    def _add_ruin(self, xp, x, y, roll, manifest) -> None:
        """Smoke and fire where an earlier package already struck. Success: a destroyed site (three plumes, big fire). Failure: a single small fire.
        Kept to a handful of effects so VR performance is untouched. The roll was made in advance and is applied to the war at debrief."""
        ok = bool(roll.get("success"))
        if xp.objective.type == ObjectiveType.DEAD and roll.get("dead") and not roll.get("killed"):
            ok = False
        if xp.objective.type == ObjectiveType.DEAD and not roll.get("dead") and roll.get("blinded"):
            ok = False                                         # a SEAD-only package blinds the radars; it does not leave a burning site
        # v0.41.19: an airfield's ruins are smoke only, no blast: the blast at 4 s killed the Gudauta airbase object in DCS, which then started
        # nobody there (its alert pairs stuck in the v0.41.12 and v0.41.14 runs)
        af_ = xp.objective.type == ObjectiveType.COUNTER_AIR or any(dist(x, y, b.x, b.y) < 6000 for b in self.state.assets.values() if b.kind == AssetKind.AIRFIELD)
        self._ruin_sites.append({"x": x, "z": y, "n": 3 if ok else 1, "r": 110 if ok else 40, "p": 2 if ok else 3, "dn": 0.9 if ok else 0.6,
                                 "pw": 0 if af_ else (120 if ok else 40), "s": self.vrng.uniform(0, 6.28)})
        manifest.ruins.append({"id": xp.id, "number": xp.number})

    def _dry_pass(self) -> None:
        """Last step before saving: any ground group with a unit (or a driving destination) in the water is moved as a whole, as little as possible,
        to where all of it is on dry land. The JTAC moves with its task force. Uses the DCS terrain scan when present, otherwise the rough coastline."""
        from . import seacheck, terrainmask
        dry = lambda x, y: seacheck.site_ok(x, y, 150.0)
        groups = []
        for coal in self.m.coalition.values():
            for c in coal.countries.values():
                groups += list(getattr(c, "vehicle_group", []))
        shifts = {}

        def pts(g):
            return [(u.position.x, u.position.y) for u in g.units] + ([(g.points[-1].position.x, g.points[-1].position.y)] if len(g.points) > 1 else [])

        def fits(g, dx, dy):
            return all(dry(px + dx, py + dy) for px, py in pts(g))

        order = sorted(groups, key=lambda g: g.name.startswith("Axeman"))        # task forces before their JTAC
        for g in order:
            if not g.units:
                continue
            dx = dy = 0.0
            if g.name.startswith("Axeman "):
                tf = shifts.get("Friendly Task Force " + g.name.split()[1].split("-")[0])
                if tf:
                    dx, dy = tf
                    self._translate(g, dx, dy)
                    dx = dy = 0.0
            if fits(g, 0, 0):
                continue
            found = None
            r = 250.0
            while r <= 8000.0 and found is None:
                for k in range(24):
                    a = math.radians(k * 15)
                    sx, sy = r * math.cos(a), r * math.sin(a)
                    if fits(g, sx, sy):
                        found = (sx, sy)
                        break
                r += 250.0
            if found is None:
                self.warns.append(f"{g.name}: could not find dry ground for the whole group; check it in the editor")
                continue
            self._translate(g, *found)
            shifts[g.name] = found

    @property
    def _jams(self) -> dict:
        return self.__dict__.setdefault("_jams_d", {})

    @property
    def _jamw(self) -> dict:
        return self.__dict__.setdefault("_jamw_d", {})

    def _note_jam(self, u) -> None:
        """Remember what jamming equipment this unit has (ecm.py) for the hook's missile roll."""
        from . import ecm
        t = ecm.tier(getattr(u, "type", ""), getattr(u, "pylons", None))
        if t:
            self._jams[u.name] = t

    def _hook_sites(self, manifest) -> list:
        """Enemy sites the call-outs track: units, radars, the package they belong to and who reports on them."""
        out = []
        fallback = next(iter(self._pkg_who.values()), "STRIKE")
        for g in manifest.groups:
            if g["kind"] != "asset":
                continue
            prim_pkgs = g.get("primary_pkgs") or []
            who = next((self._pkg_who[p_] for p_ in (prim_pkgs or [g.get("pkg", "")]) if p_ in self._pkg_who), fallback)
            out.append({"id": g["ref"], "label": g.get("label", g["ref"]), "who": who, "prim": bool(g.get("primary") or prim_pkgs),
                        "units": g["units"], "trk": g.get("trk", []), "srch": g.get("srch", [])})
        return out

    def _squelch(self, folder) -> tuple:
        """Two short beeps bundled into the mission, played with the radio call-outs: a single 1 kHz tone (0.2 s) for calls to anyone else, and a
        double higher tone for calls addressed to the player's flight. Returns the in-mission file names ('' on failure)."""
        try:
            import struct
            import wave
            rate = 22050

            def tone(freq, secs, amp=11000):
                out = bytearray()
                for i in range(int(rate * secs)):
                    t = i / rate
                    env = min(1.0, t / 0.01, (secs - t) / 0.03)              # short fade in / out so it does not click
                    out += struct.pack("<h", int(math.sin(2 * math.pi * freq * t) * amp * max(0.0, env)))
                return bytes(out)

            def put(name, data):
                p = Path(folder) / name
                with wave.open(str(p), "wb") as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(data)
                self.m.map_resource.add_resource_file(str(p))
                return "l10n/DEFAULT/" + name
            gap = bytes(2 * int(rate * 0.05))
            return put("sqe_beep.wav", tone(1000, 0.20)), put("sqe_beep_you.wav", tone(1500, 0.09) + gap + tone(1500, 0.09))
        except Exception:
            self.warns.append("radio beep sound could not be bundled; call-outs are text only")
            return "", ""

    # =====================================================================================================
    def _weather(self, m, date):
        try:
            weather.apply(m, self.wx)
        except Exception as ex:
            self.warns.append(f"could not set the weather ({ex}); the mission keeps pydcs's clear default")

    def _counts(self) -> dict:
        """Units for the VR budget. A dead static (wreck) is cheap, so it counts `carcass_weight` of a unit; 'wrecks' is how many there are."""
        g = u = w = 0
        for coal in self.m.coalition.values():
            for c in coal.countries.values():
                for attr in ("plane_group", "helicopter_group", "vehicle_group", "ship_group", "static_group"):
                    for grp in getattr(c, attr, []):
                        if attr == "static_group" and getattr(grp, "dead", False):
                            w += len(grp.units)
                            continue
                        g += 1; u += len(grp.units)
        return {"groups": g, "units": u + int(math.ceil(w * self.o.carcass_weight)), "wrecks": w}

    def _place_carcasses(self) -> None:
        """Wrecks for every damaged or destroyed ground site near the route. Trimmed to what fits under the unit limit: the furthest
        from the route go first, and this runs after everything live is placed, so wrecks never push a flight out."""
        o, st = self.o, self.state
        if not o.carcasses:
            return
        w = max(0.05, float(o.carcass_weight))
        budget = int(max(0, o.max_units - self._counts()["units"]) / w)
        if budget <= 0:
            return
        ok = lambda x, y: seac.site_ok(x, y, 60.0)
        cands = []
        for a in st.assets.values():
            if a.kind == AssetKind.AIRFIELD or a.health >= 0.999:
                continue
            dnm = tm.poly_dist(a.x, a.y, self._poly) / NM
            if dnm > o.carcass_range_nm:
                continue
            centre = self.site_pos.get(a.id) or carcass.stable_center(a, st.campaign_id, ok)
            for k, wr in enumerate(carcass.wrecks_for(a, st.campaign_id, centre, SITES, SOFT, ok)):
                cands.append((dnm, a.id, k, wr))
        cands.sort(key=lambda c: (c[0], c[1], c[2]))
        placed = 0
        for dnm, aid, k, wr in cands[:budget]:
            vt = _vt(wr["type"])
            if vt is None:
                continue
            self.m.static_group(self.red, f"WRECK {aid} {k + 1}", vt, mapping.Point(wr["x"], wr["y"], self.t), heading=wr["hdg"], dead=True)
            placed += 1
        if len(cands) > placed:
            self.warns.append(f"{len(cands) - placed} wrecks left out to stay under the {o.max_units}-unit limit (furthest from your route first)")

    def _target_xy(self, package):
        o = package.objective
        if o.type == ObjectiveType.FLEET_DEFENSE:           # CAP station on the bearing the raid will arrive on
            c = self.state.bases[o.target_id]
            cx_, cy_ = package.extra.get("dest") or (c.x, c.y)
            brg_ = package.extra.get("brg", 20.0)
            # v0.41.28: the station steps back toward what it guards (2 nm at a time, at least 10 nm out) until it is clear of red SAMs, the
            # same rule as the support CAPs (_sam_clear): the scramblers meet the raid on our side of the SAM belt, not over it
            for nm_ in range(40 if package.extra.get("land") else 85, 9, -2):
                sx_, sy_ = offset(cx_, cy_, brg_, nm_ * NM)
                if self._sam_clear(sx_, sy_):
                    break
            return sx_, sy_
        if o.type == ObjectiveType.BARCAP:
            b = self.state.bases[o.target_id]
            air = [a for a in self.state.assets.values() if a.kind == AssetKind.AIRFIELD and not a.destroyed]
            n = min(air, key=lambda a: dist(b.x, b.y, a.x, a.y))
            return offset(b.x, b.y, bearing(b.x, b.y, n.x, n.y), 60 * NM)
        a = self.state.assets[o.target_id]
        return a.x, a.y

    @staticmethod
    def _short(name):
        n = name.split("(")[0].strip()
        return n[:-3].strip() if n.endswith(" AB") else n

    def _rtb_note(self, spec, pbase=None):
        nm = self._short(pbase.name) if pbase is not None else ""
        if spec.home == BaseKind.CARRIER:
            return f"{nm}: Case I TACAN {self.o.carrier_tacan} ICLS {self.o.carrier_icls}".lstrip(": ")
        return (f"{nm}: Land. Tower, ATC frequency" if spec.fc3 else f"{nm}: Land. Tower COMM2 CH2").lstrip(": ")

    def _divert(self, pbase):
        fields = [b for b in self.state.bases.values() if b.kind == BaseKind.AIRFIELD and b.id != pbase.id]
        return min(fields, key=lambda b: dist(b.x, b.y, pbase.x, pbase.y))

    def _mode3(self, package, pf) -> str:
        i = package.flights.index(pf)
        return f"4{package.number % 8}{i % 8}{(i + package.number) % 8}"

    def _laser(self, package, pf) -> str:
        if pf.role == Role.CAS:
            return str(package.jtac_laser_code)
        return LASER[package.flights.index(pf) % 8]

    # ---- bases -------------------------------------------------------------------------------------------------------
    def _carrier_heading(self, x, y, prefer):
        return carrier_heading(x, y, prefer)

    def _platoon(self, country, name, comp, x, y, heading, formation, scale=1.0):
        types = []
        for vname, n in comp:
            vt = _vt(vname)
            if vt is None:
                self.warns.append(f"unknown vehicle {vname}; skipped")
                continue
            types += [vt] * max(1, round(n * scale))
        if not types:
            return None
        return self.m.vehicle_group_platoon(country, name, types, mapping.Point(x, y, self.t), heading=int(heading) % 360, formation=formation)

    def _place_base(self, base, tx, ty):
        o = self.o
        if base.kind == BaseKind.AIRFIELD:
            self.apt[base.id] = self.t.airports[base.airport]
            bt = sams.blue_battery(base, self.state)            # v0.41.30: doctrinal batteries, every field alike; v0.41.62: read from the field's three sites (sams.py)
            if o.base_defenses and (bt["patriot_ln"] or bt["aaa"] or bt["hawk"]):
                p = self.apt[base.id].position
                # v0.41.7: the Patriot faces the threat (the nearest enemy fighter field; was a direction picked from the base's name: a Patriot
                # radar covers about 120 degrees, so a raid from the wrong side met none). Short-range sites on both sides of the field, and a
                # HAWK battery as the middle layer at your home field. A degraded field (below 0.6) keeps the Patriot with 1 launcher and one site.
                ang = tm.nearest_threat_bearing(self.state, p.x, p.y, bearing(p.x, p.y, tx, ty))
                dry = lambda a0, d0: next(((px, py) for k in range(12) for px, py in [offset(p.x, p.y, a0 + (30 * ((k + 1) // 2)) * (1 if k % 2 else -1), d0)]
                                           if seac.site_ok(px, py, 300.0) and not self._on_runway(px, py, 150.0)), offset(p.x, p.y, a0, d0))           # the nearest bearing that is dry land
                sites_ = sams.blue_sites(self.state, base)
                def site_at(key, a0, d0):               # v0.41.64: the site's own position (doctrinal bearing + seeded jitter, sams.place_blue_site); the old search if it falls on a runway
                    a_ = sites_.get(key)
                    px, py = (a_.x, a_.y) if a_ is not None else sams.place_blue_site(self.state, base, key)
                    return (px, py) if seac.site_ok(px, py, 300.0) and not self._on_runway(px, py, 150.0) else dry(a0, d0)
                x, y = site_at("pat", ang, 4500)
                if bt["patriot_ln"]:
                    self._platoon(self.usa, f"BASEDEF {base.name} Patriot", [("Patriot_str", 1), ("Patriot_ECS", 1), ("Patriot_cp", 1),
                                  ("Patriot_EPP", 1), ("Patriot_ln", bt["patriot_ln"])], x, y, ang, F.Star)
                x, y = site_at("aaa", ang + 120, 3500)
                if bt["aaa"]:
                    self._platoon(self.usa, f"BASEDEF {base.name} AAA", [("Vulcan", 2), ("M1097_Avenger", 2 if bt["aaa"] >= 2 else 1)], x, y, ang, F.Line)
                if bt["aaa"] >= 2:
                    x, y = site_at("aaa2", ang - 120, 3500)
                    self._platoon(self.usa, f"BASEDEF {base.name} AAA 2", [("Vulcan", 1), ("M1097_Avenger", 2)], x, y, ang, F.Line)
                if bt["hawk"]:
                    x, y = site_at("hawk", ang + 50, 6000)
                    self._platoon(self.usa, f"BASEDEF {base.name} HAWK", [("Hawk_sr", 1), ("Hawk_tr", sams.BLUE_HAWK_TR), ("Hawk_pcp", 1), ("Hawk_cwar", 1),
                                  ("Hawk_ln", sams.BLUE_HAWK_LN)], x, y, ang, F.Star)
            return
        hdg = getattr(self, '_cv_hdg', {}).get(base.id)
        if hdg is None:
            hdg = (bearing(base.x, base.y, tx, ty) + 180) % 360
        pos = mapping.Point(base.x, base.y, self.t)
        cv = self.m.ship_group(self.usa, base.name, ships.Stennis, pos, heading=hdg)      # legacy free CVN-74: no deck crew
        cv.add_waypoint(pos.point_from_heading(hdg, 120 * NM), speed=o.carrier_speed_kts * KPH)
        uid = cv.units[0].id
        p0 = cv.points[0]
        p0.add_task(task.ActivateBeaconCommand(channel=int(o.carrier_tacan[:-1]), modechannel=o.carrier_tacan[-1], callsign="STN", unit_id=uid, aa=False))
        p0.add_task(task.ActivateICLSCommand(channel=o.carrier_icls, unit_id=uid))
        p0.add_task(task.ActivateLink4Command(frequency=o.carrier_link4_mhz, unit_id=uid))
        p0.add_task(task.ActivateACLSCommand(unit_id=uid))
        cv.set_frequency(int(o.carrier_atc_mhz * 1e6))
        self.ship[base.id] = cv
        if o.carrier_escorts:      # the fleet is never alone: a cruiser and two escorts station-keeping on the carrier
            for k, (cls, ang, nm) in enumerate(((ships.TICONDEROG, 40, 3.0), (ships.USS_Arleigh_Burke_IIa, -40, 3.0), (ships.PERRY, 180, 3.5))):
                ex, ey = offset(base.x, base.y, hdg + ang, nm * NM)
                ep = mapping.Point(ex, ey, self.t)
                eg = self.m.ship_group(self.usa, f"{base.name} escort {k + 1}", cls, ep, heading=hdg)
                eg.add_waypoint(ep.point_from_heading(hdg, 120 * NM), speed=o.carrier_speed_kts * KPH)

    # ---- enemy ground: every mission re-rolls layout, mix and posture (seeded by campaign/day/sortie) ----------
    def _nearest_airfield(self, x, y):
        return min((b for b in self.state.bases.values() if b.kind == BaseKind.AIRFIELD), key=lambda b: dist(b.x, b.y, x, y))

    def _site_center(self, a):
        if a.id in self.site_pos:
            return self.site_pos[a.id]
        r = self.vrng
        if a.kind == AssetKind.AIRFIELD:
            pos = (a.x, a.y)
        elif a.kind == AssetKind.ARMOR and a.variant == "GARRISON":
            pos = offset(a.x, a.y, r.uniform(0, 360), r.uniform(0, 400))
        elif a.kind == AssetKind.ARMOR:       # the column sits somewhere along its axis of advance
            fb = self._nearest_airfield(a.x, a.y)
            pos = offset(a.x, a.y, bearing(a.x, a.y, fb.x, fb.y), r.uniform(-1500, 1500))
        else:
            pos = offset(a.x, a.y, r.uniform(0, 360), r.uniform(0, 900))
        if a.kind != AssetKind.AIRFIELD and not seac.site_ok(pos[0], pos[1], min(600.0, seac.SITE_MARGIN)):
            pos = (a.x, a.y)                  # the random shift would put it in the sea: keep the site where it is (it is on land)
        pos = self._off_runway(pos[0], pos[1], 150.0 + 20.0 * len(SITES.get(a.variant) or SOFT.get(a.kind) or []))      # v0.41.48
        self.site_pos[a.id] = pos
        return pos

    def _on_runway(self, x, y, margin):
        """v0.41.48: True when a group centred here (its footprint about `margin` m) would sit on a runway and block the side that uses it.
        pydcs gives each runway only a heading, so the strip is modelled as a corridor through the airfield reference point:
        RUNWAY_HALF_LEN_M each way, RUNWAY_HALF_WIDTH_M either side, plus the group's own margin (a judgment call, not a surveyed runway)."""
        for ap in self.t.airports.values():
            ax, ay = ap.position.x, ap.position.y
            if abs(x - ax) > RUNWAY_HALF_LEN_M + margin + 500 or abs(y - ay) > RUNWAY_HALF_LEN_M + margin + 500:
                continue
            for rw in ap.runways:
                h = math.radians(rw.heading)
                dx, dy = x - ax, y - ay
                along = dx * math.cos(h) + dy * math.sin(h)
                across = -dx * math.sin(h) + dy * math.cos(h)
                if abs(along) < RUNWAY_HALF_LEN_M + margin and abs(across) < RUNWAY_HALF_WIDTH_M + margin:
                    return True
        return False

    def _off_runway(self, x, y, margin):
        """Move a site centre sideways, off any runway corridor, to the nearest clear dry spot (unchanged when already clear)."""
        if not self._on_runway(x, y, margin):
            return (x, y)
        for d in range(150, 2401, 150):
            for ang in range(0, 360, 30):
                px, py = offset(x, y, ang, d)
                if not self._on_runway(px, py, margin) and seac.site_ok(px, py, min(600.0, seac.SITE_MARGIN)):
                    return (px, py)
        return (x, y)

    def _jitter_primary(self, package, tx, ty):
        o = package.objective
        if o.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            return tx, ty
        return self._site_center(self.state.assets[o.target_id])

    def _vary_comp(self, a, comp):
        r, out = self.vrng, []
        for name, n in comp:
            if a.kind in (AssetKind.SAM, AssetKind.EWR) and n >= 3:
                n = max(2, n + r.choice([-1, 0, 0, 1]))
            elif a.kind in (AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT, AssetKind.AIRFIELD):
                n = max(1, n + r.randint(-1, 2))
            out.append((name, n))
        if a.kind == AssetKind.SAM and r.random() < 0.45:
            out.append((r.choice(["ZSU_23_4_Shilka", "SA_18_Igla_manpad", "Ural_375_ZU_23"]), r.randint(1, 2)))
        if a.kind in (AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT) and r.random() < 0.5:
            out.append(("Ural_375", r.randint(1, 3)))
        return out

    def _garrison_comp(self):
        """A dug-in garrison: fewer vehicles than a column, no one is advancing. Bigger at higher difficulty."""
        r, k = self.vrng, self.d.garrison_size
        comp = [(r.choice(["T_72B", "T_80B"]), max(1, round(r.randint(2, 3) * k))), (r.choice(["BMP_2", "BMP_1"]), max(1, round(r.randint(1, 2) * k))),
                ("ZSU_23_4_Shilka", 1), ("Ural_375", r.randint(0, 1))]
        if self.d.level >= 3:
            comp.append(("Strela_10M3", 1))
        return comp

    def _armor_comp(self):
        r = self.vrng
        comp = [(r.choice(["T_72B", "T_72B", "T_80B", "T_80UD"]), r.randint(3, 6)), (r.choice(["BMP_2", "BMP_1", "BMP_3"]), r.randint(2, 5)),
                (r.choice(["BTR_80", "BTR_70", "BTR_60"]), r.randint(1, 3)), ("ZSU_23_4_Shilka", r.randint(0, 2)), ("Ural_375", r.randint(0, 3))]
        if r.random() < 0.4:
            comp.append((r.choice(["Strela_10M3", "Osa_9A33_ln"]), 1))       # mobile air defence travelling with the column
        return [(n, c) for n, c in comp if c > 0]

    def _spawn_everything(self, package, manifest, tx, ty) -> None:
        """Full-map stress test: no restrictions. Every live enemy site, column, garrison, support site and early-warning radar is built; every friendly
        airfield gets its defences, garrison and supply sites; every friendly sector with troops gets its column; every planned enemy patrol is
        airborne at its station. The target and your package are unchanged. A mission this size may not load well in VR: that is the point."""
        st, d = self.state, self.d
        for a in sorted(st.assets.values(), key=lambda a: a.id):
            if a.destroyed or a.id in self.groups_by_asset:
                continue
            comp = SITES.get(a.variant) if a.kind in (AssetKind.SAM, AssetKind.EWR) else SOFT.get(a.kind)
            if comp:
                self._spawn_site(a, comp, manifest, primary=False)
        for b in st.bases.values():
            if b.kind == BaseKind.AIRFIELD and b.id not in self.apt:
                self._place_base(b, tx, ty)
        home = min((b for b in st.bases.values() if b.kind == BaseKind.AIRFIELD), key=lambda b: dist(b.x, b.y, tx, ty), default=None)
        if home is not None:
            for aim, ba in sorted(st.blue_assets.items()):
                if ba.destroyed:
                    continue
                base = st.bases.get(ba.guards) or home
                self._spawn_raid_target(package, base, aim, ba.x, ba.y, manifest)
            g = st.ground or {}
            for i, v in enumerate(g.get("blue", [])):
                if v > 0 and i < len(g.get("centers", [])):
                    c = g["centers"][i]
                    self._spawn_raid_target(package, home, f"sector:{i}", float(c[0]), float(c[1]), manifest)
        skill = getattr(Skill, d.enemy_skill, Skill.High)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        for n, pf in enumerate((st.red_air or {}).get("flights", [])):
            a = st.assets.get(pf["wing"])
            if a is None or a.destroyed or pf["type"] not in ENEMY_FIGHTERS:
                continue
            fx_, fy_, fa_ = self._sep(pf["x"], pf["y"], 22000 * FT, 0.0)
            g = self.m.flight_group(self.red, f"FM Bandit {n + 1}", getattr(planes, pf["type"]), None, pt(fx_, fy_), altitude=fa_, speed=400 * KPH,
                                    maintask=task.CAP, group_size=2)
            g.set_skill(skill)
            load = enemy_cap_loadout(pf["type"])
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"ENM-FM-{pf['wing']}-{n}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", pf["wing"], names, ac=pf["type"])

    def _spawn_opfor_ground(self, package, tx, ty, manifest, polyline=None):
        st, obj = self.state, package.objective
        from .war import blinded_today
        # the DEAD stage of a SEAD-first pair: if the SEAD package blinded the site (the day's verdict), its radars are already gone when the mission starts
        self._blind_site = obj.target_id if (obj.type == ObjectiveType.DEAD and obj.aim == "DEAD" and blinded_today(st, obj.target_id)) else None
        if obj.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            tgt, relevant = None, []            # no ground target, but enemy SAMs whose rings touch the route / station stay live
        else:
            tgt = st.assets[obj.target_id]
            dfn = sorted((st.assets[i] for i in tgt.defended_by if not st.assets[i].destroyed), key=lambda x: dist(x.x, x.y, tgt.x, tgt.y))
            relevant = [tgt] + dfn[:2]                                                   # the two nearest defenders; more only costs VR frame rate
            relevant += [g for g in st.assets.values() if g.guards == tgt.id]            # a SAM site's dug-in garrison is part of its cluster
        if polyline:                         # every SAM site whose ring touches the route is live from the start
            relevant += tm.corridor_sam_sites(st, polyline, tgt)
        ewrs = sorted((a for a in st.assets.values() if a.kind == AssetKind.EWR and not a.destroyed),
                      key=lambda a: tm.poly_dist(a.x, a.y, polyline) if polyline else dist(a.x, a.y, tx, ty))
        relevant += [a for a in ewrs[:2] if (tm.poly_dist(a.x, a.y, polyline) if polyline else 0) < 80 * NM]
        seen = set()
        for a in relevant:
            if a.id in seen or a.destroyed:
                continue
            seen.add(a.id)
            is_tgt = tgt is not None and a.id == tgt.id
            if a.id in self.groups_by_asset:           # already live for another package of this mission: shared world, never twice
                if is_tgt:
                    manifest.mark_primary(a.id, manifest.cur_pkg or package.id)
                continue
            comp = SITES.get(a.variant) if a.kind in (AssetKind.SAM, AssetKind.EWR) else SOFT.get(a.kind)
            if comp:
                self._spawn_site(a, comp, manifest, primary=is_tgt)

    def _spawn_site(self, a, comp, manifest, primary):
        """ONE group per site: a SAM battery needs its search/track radars, launchers and command post together."""
        r = self.vrng
        skill = getattr(Skill, self.d.enemy_skill, Skill.High)
        garrison = a.kind == AssetKind.ARMOR and a.variant == "GARRISON"
        comp = (self._garrison_comp() if garrison else self._armor_comp()) if a.kind == AssetKind.ARMOR else self._vary_comp(a, comp)
        cx, cy = self._site_center(a)
        base_count = sum(n for vname, n in comp if _vt(vname) is not None)
        if garrison:
            fb = self._nearest_airfield(cx, cy)
            heading, form = int(bearing(cx, cy, fb.x, fb.y)), r.choice([F.Rectangle, F.Scattered, F.Star])
        elif a.kind == AssetKind.ARMOR:
            fb = self._nearest_airfield(cx, cy)
            heading, form = int(bearing(cx, cy, fb.x, fb.y)), r.choice([F.Line, F.Rectangle, F.Line])
        else:
            heading, form = r.randint(0, 359), r.choice([F.Star, F.Scattered, F.Rectangle])
        column = a.kind == AssetKind.ARMOR and not garrison and ground.zone_of(self.state, a.id) is not None
        scale = (ARMOR_DENSITY[0] + ARMOR_DENSITY[1] * a.health) if column else a.health         # a front-line column is as dense as its sector is strong
        g = self._platoon(self.red, a.id, comp, cx, cy, heading, form, scale=scale)
        if g is None:
            return
        if column:
            base_count = max(1, round(len(g.units) / max(0.05, a.health)))                      # the count at full health, so losses read back as health
        if a.kind == AssetKind.SAM and (a.suppressed or a.id == self._blind_site):
            gone = [u for u in g.units if str(getattr(u, "type", "")) in TRACK_RADARS | SEARCH_RADARS]
            for u in gone:
                g.units.remove(u)
            base_count = max(1, base_count - len(gone))      # the radars were already destroyed: not damage this mission caused
        if a.kind != AssetKind.SAM:
            self._ground_orders(g)                      # v0.41.39: armour columns and garrisons fight on explicit orders
        names = []
        for k, u in enumerate(g.units, 1):
            u.name = f"{a.id}|{k}"
            try:
                u.skill = skill
            except Exception:
                pass
            names.append(u.name)
        self.groups_by_asset[a.id] = g
        if a.kind == AssetKind.ARMOR:
            self.armor_id, self.armor_center = a.id, (cx, cy)
        mine = bool(primary) and (not manifest.cur_pkg or manifest.cur_pkg == self._anchor_id)
        trk = [u.name for u in g.units if str(getattr(u, "type", "")) in TRACK_RADARS]
        srch = [u.name for u in g.units if str(getattr(u, "type", "")) in SEARCH_RADARS]
        manifest.add("asset", a.id, names, base_count=base_count, health_before=a.health, primary=mine, label=a.name, trk=trk, srch=srch,
                     primary_pkgs=[manifest.cur_pkg] if (primary and manifest.cur_pkg) else [])

    # ---- support: tanker + AWACS well back from the enemy, with a HAVCAP at the same spot ----------------------------
    def _safe_station(self, g):
        st = self.state
        enemies = [(st.assets[w.base_asset_id].x, st.assets[w.base_asset_id].y) for w in st.enemy_air
                   if w.available > 0 and not st.assets[w.base_asset_id].destroyed]
        bx, by = g.bx, g.by
        mx, my = g.mshl
        x = y = 0
        for f in (0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.1):
            x, y = bx + (mx - bx) * f, by + (my - by) * f
            if not enemies or min(dist(x, y, ex, ey) for ex, ey in enemies) / NM >= 120:
                break
        return x, y

    def _pkg_target_xy(self, package):
        """(x, y) of a package's ground target, or None (fleet / base patrols)."""
        a = self.state.assets.get(package.objective.target_id) if package.objective.target_id else None
        return (a.x, a.y) if a is not None else None

    # ---- friendly flights -------------------------------------------------------------------------------------------------
    def _pt(self, x, y):
        """A map point in this theatre's coordinates (was a lambda inside _spawn_flight)."""
        return mapping.Point(x, y, self.t)

    def _spawn_flight(self, package, f, plan, geom, tanker_xy, hav_xy, push_s, tot_s, rtb_s, idx, manifest, despawn):
        st, o = self.state, self.o
        spec = AIRCRAFT[f.aircraft]
        base = st.bases[f.base_id]
        past_push, act_s = False, 0
        csname, fno = f.callsign.rsplit(" ", 1)
        fno = int(fno)

        cap_zone = None
        if f.tag:       # support CAP: airborne on station for the whole package
            cap_zone, wps, stop = self._support_cap_route(package, f, geom, hav_xy, tot_s, rtb_s)
        else:
            r_ = self._flight_route(package, f, geom, idx, push_s, tot_s)
            if r_ is None:
                return None, None                          # already back on the ground
            wps, act_s, past_push, stop = r_

        g, first, cs_names = self._make_group(f, spec, base, wps, act_s, csname, fno)
        names, run_t0 = self._dress_group(package, f, spec, g, wps, push_s, tot_s, cs_names)
        stw = next((w for w in wps if w.action in ("TARCAP", "ESCORT", "SWEEP") and w.orbit), None)
        hold_end = self._hold_end(stw, tot_s) if stw is not None else None
        self._engage_tasks(package, f, g, wps, stw, hold_end, cap_zone, stop, tot_s, geom, base)
        self._crew_setup(f, spec, g, names, plan, manifest, despawn, past_push)
        self._announce(package, f, g, names, wps, push_s, manifest)
        armor, ai_sead, ai_a2g = self._roe_defaults(package, f, g)
        special = self._f14_special_namer(wps) if (f.is_player and f.aircraft == "F-14BU" and o.f14_special_names) else None
        self._attach_waypoints(package, f, g, wps, first, ai_a2g, ai_sead, run_t0, push_s, tot_s, stop, hold_end, stw, armor, special)
        if f.role == Role.SEAD and package.objective.target_id:
            self._sead_grps.setdefault(package.objective.target_id, []).append(g.name)
        gate = self._dead_gate(package, f, g, wps, first, stw, tot_s, base)
        self._home_leg(f, g, base, wps, idx, hold_end, stop, special)
        if gate is not None:
            if gate["to"] is None:
                gate["to"] = len(g.points)                              # the landing point
            self._gates.append(gate)
        tw = None if f.tag else objective_wp(wps)
        if tw is not None and f.role in (Role.STRIKE, Role.SEAD, Role.CAS):
            egr_ = next((w.eta_s for w in wps if w.name == "EGR"), None)          # v0.41.40: when this striker is OUT, for the escorts to wait on
            self._striker_egr.append(((geom.tx, geom.ty), float(egr_ if egr_ is not None else tw.eta_s + 180)))
        return g, (tw.eta_s if tw is not None else None)

    def _flight_route(self, package, f, geom, idx, push_s, tot_s):
        """Everyone else's route: plan_route, terrain, times. -> (wps, act_s, past_push, stop), or None when the flight is already back on the ground. Moved out of _spawn_flight in v0.41.54, unchanged."""
        o = self.o
        spec = AIRCRAFT[f.aircraft]
        base = self.state.bases[f.base_id]
        past_push, act_s = False, 0
        sp = None
        if not f.is_player:
            sp = self._spawn_point(f, base, geom)
        wps = plan_route(f.role, (base.x, base.y), geom, spec.profile, is_player=f.is_player, tanker_xy=None, stack_idx=idx,
                         spawn=sp[0] if sp else None, spawn_alt_ft=sp[1] if sp else 0, spawn_kts=sp[2] if sp else 0,
                         jsow=getattr(f, "kit", "") == "JSOW", jsow_side=self._jsow_side(package, geom), keep_out=self._umbrella_keep(package), harm_deg=self._harm_deg(package, geom))
        if self._raid_cap(package, f):
            # v0.41.28: a raid scramble's way out to its station bends round red SAMs like a strike's (the orbit leg stays as it is)
            k1_ = next((i for i, w in enumerate(wps) if w.action == "CAPORBIT"), None)
            if k1_:
                wps = avoid_circles(wps[:k1_ + 1], self._zone_sams(package, True), spec.profile.max_points - (len(wps) - k1_ - 1), 1) + wps[k1_ + 1:]
        if not f.is_player or o.player_is_ai:
            terrain_clear(wps)                          # an AI flight climbs on its own schedule: its altitudes must clear the ridges on each leg
        if f.is_player:
            assign_times(wps, self._dep_s, push_s)
            act_s = 0
        else:
            assign_times(wps, 0.0)                      # natural pace from the spawn
            hold_i = next((i for i, w in enumerate(wps) if w.action == "HOLD"), None)
            nat = wps[hold_i + 1].eta_s if hold_i is not None else next((w.eta_s for w in wps if w.action == "CAPORBIT"), wps[-1].eta_s)
            act_raw = int(push_s - nat - (120 if hold_i is not None else 60))      # arrive ~2 min early, hold, push on time
            act_s = max(0, act_raw)
            assign_times(wps, float(act_raw), push_s)
            if act_raw < 0:                              # its schedule began before the mission did (an earlier package folded in): it is already underway
                # v0.41.23: its time on station counts: the points after the station come that much later, and a flight still within its
                # hold starts on its station (it was placed as if it never loitered: past its station, already on its way home)
                leave_ = {}
                si_ = next((i for i, w in enumerate(wps) if w.action in ("TARCAP", "ESCORT", "SWEEP") and w.orbit), None)
                if si_ is not None:
                    lv_ = self._hold_end(wps[si_], tot_s)
                    dw_ = max(0, lv_ - wps[si_].eta_s)
                    for w in wps[si_ + 1:]:
                        w.eta_s += dw_
                    leave_[si_] = lv_
                wps = in_progress(wps, (base.x, base.y), leave_)
                if wps is None:                          # already back on the ground
                    return None
                past_push = not any(w.name == "PUSH" for w in wps)
        stop = int(tot_s + o.cap_minutes * 60)
        return wps, act_s, past_push, stop

    def _make_group(self, f, spec, base, wps, act_s, csname, fno):
        """The DCS group: hot on the runway for your own flight, already airborne for an AI flight, facing its way; callsigns. -> (g, first, cs_names)."""
        pt = self._pt
        if f.is_player:       # hot on the runway / catapult
            if base.kind == BaseKind.CARRIER:
                g = self.m.flight_group_from_unit(self.usa, f.callsign, spec.dcs_type, self.ship[base.id], maintask=MAIN_TASK[f.role],
                                                  start_type=StartType.Runway, group_size=f.count)
            else:
                g = self.m.flight_group_from_airport(self.usa, f.callsign, spec.dcs_type, self.apt[base.id], maintask=MAIN_TASK[f.role],
                                                     start_type=StartType.Runway, group_size=f.count)
            self._runway_busy.add(("blue", base.id))
            self._prwy = f"{self.usa.name}:{self.apt[base.id].name}" if base.kind != BaseKind.CARRIER else f"carrier:{base.id}"
            first = 0
        else:                 # already airborne
            s0 = wps[0]
            self._clear_spawn(s0, wps, act_s)
            g = self.m.flight_group(self.usa, f.callsign, spec.dcs_type, None, pt(s0.x, s0.y), altitude=s0.alt_ft * FT,
                                    speed=s0.speed_kts * KPH, maintask=MAIN_TASK[f.role], group_size=f.count)
            first = 1
        if not f.tag and not f.is_player and act_s > 0:
            self._late(g, act_s)                                # they 'depart' on their own schedule, not at mission start
        if first == 1 and not f.tag:                            # face the way they are going (in-flight groups spawn pointing north)
            nxt = next((w for w in wps[1:] if dist(wps[0].x, wps[0].y, w.x, w.y) > 100), None)
            if nxt is not None:
                hdg = bearing(wps[0].x, wps[0].y, nxt.x, nxt.y)
                for u_ in g.units:
                    u_.heading = hdg
        cs_names = callsigns.apply(g, csname, fno, callsigns.table(f.aircraft))
        return g, first, cs_names

    def _dress_group(self, package, f, spec, g, wps, push_s, tot_s, cs_names):
        """Loadout (weather-adapted), unit names, jammer windows, skill, bingo return, and where this package's shooters launch. -> (names, run_t0)."""
        o = self.o
        load = self.lo.for_role(f.aircraft, f.role, getattr(f, "kit", ""))
        if self.wx.mode != "clear":
            load, wnotes, _k, _d = weather.adapt(spec.dcs_type, load, self.wx)
            if wnotes and not f.tag:
                self.wx_notes.append(f"{f.callsign}: " + "; ".join(sorted(set(wnotes))))
        names = []
        for i, u in enumerate(g.units):
            u.name = cs_names[i]; names.append(u.name)
            u.pylons = copy.deepcopy(load); self._note_jam(u)
        run_t0 = run_t1 = None
        if f.is_player and o.ecm_script and self._jams.get(names[0]):
            # your jammer, until the hook can read your switch: the script counts it on over the attack leg only, PUSH to egress, like the AI's
            p0_ = float(push_s)
            p1_ = float(next((w.eta_s for w in wps if w.name == "EGR"), (tot_s if tot_s is not None else push_s) + 900))
            for un_ in names:
                self._jamw[un_] = (p0_, p1_)
        if not f.tag and not f.is_player and (self._jams.get(names[0]) or f.aircraft in NATIVE_ECM):
            run_t0 = float(push_s)                                            # the jammers run for the attack leg only: PUSH to EGR
            run_t1 = float(next((w.eta_s for w in wps if w.name == "EGR"), (tot_s if tot_s is not None else push_s) + 900))
            if o.ecm_script:
                for un_ in names:
                    self._jamw[un_] = (run_t0, run_t1)
            if f.is_player and f.aircraft == "F-14BU":
                u.set_property("INSAlignmentStored", True)
        g.set_skill(Skill.High)
        # v0.41.11: every AI flight goes home on bingo fuel; v0.41.16: your own flight too (it applies to your AI wingmen: in the v0.41.14 run they
        # queued at the tanker until they flamed out)
        g.points[0].tasks.append(task.OptRTBOnBingoFuel(True))
        if not f.tag and f.role in (Role.SEAD, Role.STRIKE, Role.CAS) and f.is_player and not o.player_is_ai:      # where this package's shooters launch: the TARCAP / escort cover zone (AI flights: _launch_points, before the loop)
            lp_ = next((w for w in wps if w.action in ("SEAD", "JSOW")), None) or next((w for w in wps if w.name == "IP"), None)
            if lp_ is not None:
                self._launch_pts.setdefault(package.id, []).append((lp_.x, lp_.y))
        return names, run_t0

    def _engage_tasks(self, package, f, g, wps, stw, hold_end, cap_zone, stop, tot_s, geom, base):
        """How the flight fights: the engage circles, hold and homeward fight, ROE and range options. One branch for support CAPs, one for stations, one for other AI fighters, one for raid scrambles."""
        st, o = self.state, self.o
        if f.tag:
            czone_ = self._clear_zone(cap_zone, package)
            self._limit_engage(g, self.o.friendly_cap_engage_nm, None, czone_)
            # v0.41.14: support CAP snipes (maximum range: the bandits turn defensive before they reach what it guards) and goes home when its
            # air-to-air missiles are gone (the SAMs and the boat's SM-2s cover what it guards)
            g.points[0].tasks.append(task.OptAAMissileAttackRange(task.OptAAMissileAttackRange.Values.MaxRange))
            if f.tag == "TNKCAP":
                # v0.41.26: the tanker CAP was timid in the XO's Nalchik run. Radar searching all the time, so it shoots first at maximum range
                # at anything coming at the tanker; the circle round the tanker (TNKCAP_ZONE_NM) keeps it with the tanker.
                # v0.41.35: NO explicit weapons free any more. Weapons free = "engage any enemy group in contact" (ME docs), which overrides the
                # circle: in all three of XO's runs of 2026-10-16/17 the tanker CAP (the only support CAP with it) ran 50-78 nm out into the
                # Sukhumi S-300, and the v0.41.34 pull-back could not stop it (the option outlives a new route). Default ROE, like the others.
                g.points[0].tasks.append(task.OptRadarUsing(task.OptRadarUsing.Values.UseForContinuousSearch))
            rtbt_ = task.OptRTBOnOutOfAmmo(); rtbt_.params["action"]["params"]["value"] = AAM_WEAPONS
            g.points[0].tasks.append(rtbt_)
        elif stw is not None and (not f.is_player or o.player_is_ai):
            # no chasing. A sweep engages inside a circle round its station (25 nm for the long-range shooters, 15 for the rest). A TARCAP or
            # escort covers the package: the circle is round the package's launch points (HARM / JSOW points, or the IP), COVER_ZONE_NM, and
            # always takes in its own station. Until the hold ends.
            back_ = bearing(stw.x, stw.y, base.x, base.y)
            cover_lo_ = False
            if stw.action == "SWEEP" or not self._launch_pts.get(package.id):
                # v0.41.10: a sweep engages within 25 nm whatever it flies (the v0.41.8 F-16 sweep, 15 nm, never fired while MiGs went past it)
                zone_ = (stw.x, stw.y, A2A_ZONE_NM[True] if stw.action == "SWEEP" else A2A_ZONE_NM[f.aircraft in LONG_RANGE_A2A])
                if stw.action == "SWEEP":
                    # v0.41.14: the circle stops short of every live SA-10's reach (31 nm measured): the v0.41.13 sweep chased a MiG to 10 nm of
                    # the Sukhumi SA-10 and lost Venom 9-2. Let red come out to it.
                    d10_ = min([dist(stw.x, stw.y, a.x, a.y) / NM for a in st.assets.values()
                                if a.variant in tm.UMBRELLA_VARIANTS and not a.destroyed and a.health > 0.25] + [999.0])
                    zone_ = (zone_[0], zone_[1], max(8.0, min(zone_[2], d10_ - SA10_REACH_NM)))
                # v0.41.23: moved, not only shrunk: the circle's centre may shift (toward home or to either side) to keep its full size clear of
                # SAMs, as long as it still takes in the station
                # v0.41.33: a sweep's circle also takes in the red station it was sent after (sweep.station_for puts it REACH_NM away), as far
                # as that stays clear of SAMs (its own station first)
                vs_ = package.extra.get("sweep_vs") if stw.action == "SWEEP" else None
                cpts_ = [(stw.x, stw.y)] + ([(vs_["x"], vs_["y"])] if vs_ else [])
                c0_ = ((stw.x + vs_["x"]) / 2, (stw.y + vs_["y"]) / 2) if vs_ else (stw.x, stw.y)
                zone_ = self._cover_circle(cpts_, c0_, package, zone_[2], back_)
            else:
                lp_ = self._launch_pts[package.id]
                cx_, cy_ = sum(p_[0] for p_ in lp_) / len(lp_), sum(p_[1] for p_ in lp_) / len(lp_)
                # v0.41.23: the TARCAP's circle covers the package's launch points and its own station, at COVER_ZONE_NM at least, placed where
                # that circle is clear of every SAM the package is not sent against (v0.41.22 only shrank it: 44% trimmed, 9% down to 8 nm)
                zone_ = self._cover_circle(list(lp_) + [(stw.x, stw.y)], (cx_, cy_), package, COVER_ZONE_NM, bearing(cx_, cy_, stw.x, stw.y),
                                           long_only=True, max_nm=TARCAP_COVER_MAX_NM)
                cover_lo_ = True            # v0.41.42 (XO): the circle takes in the shooters first; only an SA-10 keeps it out (an SA-11 / SA-6 no longer pushes it off the launch points)
            zct_ = self._limit_engage(g, 0, hold_end, self._clear_zone(zone_, package, long_only=cover_lo_))
            hold_ = None
            if hold_end is not None:
                hold_ = {"cts": [zct_], "starts": [], "tgt": (geom.tx, geom.ty), "end": int(hold_end), "eta": int(stw.eta_s),
                         "first": stw.action == "SWEEP",           # v0.41.13: a sweep holds until the FIRST package it covers is over the target
                         "after": SWEEP_AFTER_TOT_S if stw.action == "SWEEP" else TARCAP_AFTER_TOT_S if stw.action == "TARCAP" else ESCORT_AFTER_TOT_S}
                self._holds.append(hold_)
            if hold_end is not None:
                # v0.41.5: on the way home the flight still fights what comes within HOMEWARD_ENGAGE_NM of it. In the v0.41.4 run a lone MiG-29 chased
                # Springfield (F-14s, 5 of about 40 missiles fired) home after the hold ended and fired four R-27s while they only defended.
                # v0.41.15: a fixed circle over the way home (station to home field), not one that moves with the jet: the v0.41.14 run, flights
                # chasing a MiG north under the moving 20 nm circle ended up over Gudauta and Sochi
                hcx_, hcy_ = (stw.x + base.x) / 2, (stw.y + base.y) / 2
                hr_ = dist(stw.x, stw.y, base.x, base.y) / 2 + HOMEWARD_ENGAGE_NM * NM
                circles_ = [(hcx_, hcy_, hr_ / NM)]
                if self._room(hcx_, hcy_, package) < hr_ / NM - 0.5:
                    # v0.41.23: one big circle would reach a SAM (v0.41.22 cut 136 of 320 short, 60 down to 20 nm): up to three smaller circles
                    # along the way home instead, each HOMEWARD_ENGAGE_NM where it can be, each clear of SAMs (moved toward home if need be)
                    leg_nm_ = dist(stw.x, stw.y, base.x, base.y) / NM
                    n_ = max(2, min(3, math.ceil(leg_nm_ / (2 * HOMEWARD_ENGAGE_NM)) + 1))
                    hb_ = bearing(stw.x, stw.y, base.x, base.y)
                    circles_ = []
                    for k_ in range(n_):
                        px_, py_ = offset(stw.x, stw.y, hb_, leg_nm_ * k_ / (n_ - 1) * NM)
                        circles_.append(self._cover_circle([(px_, py_)], (px_, py_), package, HOMEWARD_ENGAGE_NM, hb_))
                for k_, (cx2_, cy2_, cr_) in enumerate(circles_):
                    hw_ = task.ControlledTask(task.EngageTargetsInZone(mapping.Vector2(cx2_, cy2_), int(cr_ * NM), [task.Targets.All.Air]))
                    hw_.start_after_time(int(hold_end)); g.points[0].tasks.insert(1 + k_, hw_)
                    if hold_ is not None:
                        hold_["starts"].append(hw_)
            rtb_a = task.OptRTBOnOutOfAmmo(); rtb_a.params["action"]["params"]["value"] = AAM_WEAPONS
            if stw.action != "SWEEP":    # (a sweep gets it below): out of air-to-air missiles, the homeward fight is over
                g.points[0].tasks.append(rtb_a)
            # snipe: fire at maximum range, radar searching all the time (red's warning receivers light up and it turns away early). AI
            # launch behaviour still varies by type in DCS (forum reports), so the shot log is the check.
            # v0.41.10: on the way out, closer shots (halfway between max range and the no-escape zone): fewer, surer missiles, kept for the
            # station. Maximum range from the station on (set at that waypoint below). Out of fuel: home (v0.41.8 run: Venom 9-4 flamed out).
            g.points[0].tasks.append(task.OptAAMissileAttackRange(task.OptAAMissileAttackRange.Values.HalfWayRMaxNoEsc))
            self._snipe_at[id(g)] = stw
            g.points[0].tasks.append(task.OptRadarUsing(task.OptRadarUsing.Values.UseForContinuousSearch))
            if stw.action == "SWEEP":    # a sweep goes home once its air-to-air missiles are gone
                rtb_ = task.OptRTBOnOutOfAmmo(); rtb_.params["action"]["params"]["value"] = AAM_WEAPONS
                g.points[0].tasks.append(rtb_)
        elif (not f.is_player or o.player_is_ai) and f.role in (Role.TARCAP, Role.ESCORT, Role.SWEEP, Role.SEAD):
            m_ = self.o.fighter_engage_minutes
            zone = None
            if self.o.fighter_engage_nm > 0:                        # a leash: engage only what is inside a circle around the hold / SEAD point (DCS's distance limit moves with the aircraft)
                zw = next((w for w in wps if w.orbit), None) or next((w for w in wps if w.action == "SEAD"), None) or objective_wp(wps)
                if zw is not None:
                    zone = (zw.x, zw.y, min(self.o.fighter_engage_nm, SEAD_ENGAGE_NM) if (zw.orbit or f.role == Role.SEAD) else self.o.fighter_engage_nm)
            self._limit_engage(g, self.o.fighter_engage_nm if f.role != Role.SEAD else 0, (tot_s + m_ * 60) if (m_ > 0 and tot_s is not None) else None,
                               self._clear_zone(zone, package, fighters=f.role != Role.SEAD))
        elif self._raid_cap(package, f):
            # v0.41.28: a raid scramble follows the TARCAP rules. It engages only inside a circle that takes in its station and the place the
            # raid is going (25 nm round the long-range shooters, 15 for the rest, larger when it must reach both), moved / trimmed clear of red
            # SAMs. No chasing (the XO's Kobuleti run: Eagles went to dogfight range and lost to Fulcrums). Max-range shots, radar on,
            # home once its air-to-air missiles are gone.
            cw_ = next((w for w in wps if w.action == "CAPORBIT"), None)
            if cw_ is not None:
                cb_ = st.bases[package.objective.target_id]
                dx_, dy_ = package.extra.get("dest") or (cb_.x, cb_.y)
                zone_ = self._cover_circle([(cw_.x, cw_.y), (dx_, dy_)], ((cw_.x + dx_) / 2, (cw_.y + dy_) / 2), package,
                                           A2A_ZONE_NM[f.aircraft in LONG_RANGE_A2A], bearing(cw_.x, cw_.y, dx_, dy_))
                self._limit_engage(g, 0, stop, self._clear_zone(zone_, package))
            g.points[0].tasks.append(task.OptAAMissileAttackRange(task.OptAAMissileAttackRange.Values.MaxRange))
            g.points[0].tasks.append(task.OptRadarUsing(task.OptRadarUsing.Values.UseForContinuousSearch))
            rtbr_ = task.OptRTBOnOutOfAmmo(); rtbr_.params["action"]["params"]["value"] = AAM_WEAPONS
            g.points[0].tasks.append(rtbr_)

    def _crew_setup(self, f, spec, g, names, plan, manifest, despawn, past_push):
        """Your own seat and radio presets, or an AI flight's frequency, despawn on landing and fuel."""
        o = self.o
        if f.is_player:
            u0 = g.units[0]
            if not o.player_is_ai:                              # test mode: the slot stays an AI aircraft, so nothing has to be changed in the editor
                u0.set_client() if o.player_is_client else u0.set_player()
            if spec.fc3:
                pass                                           # FC3 radios have no presets or channels: frequencies are on the kneeboard
            elif not (hasattr(spec.dcs_type, "panel_radio") and spec.dcs_type.panel_radio and apply_player_presets(u0, plan, o.layout)):
                self.warns.append(f"{spec.display}: COMM1 presets can't be set automatically; set them from the kneeboard comms page.")
            try:
                g.set_frequency(plan.freq("FLIGHT"), radio_id=o.layout.comm2_radio_id)
            except Exception:
                g.set_frequency(plan.freq("FLIGHT"))
            manifest.player_unit = u0.name
            g.points[0].ETA = 0; g.points[0].ETA_locked = True       # takeoff pinned at mission start. If it is unlocked while PUSH / the target are locked, DCS back-computes a start time from them and holds the player ("Flight is delayed to start"). The kneeboard still shows the buffered takeoff time.
        else:
            g.set_frequency(next((e.mhz for e in plan.package_flights if e.callsign == f.callsign), 130.0))
            if o.ai_despawn_on_land:
                despawn.extend(names)
            if o.ai_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(not past_push))      # already past its PUSH point: the combat leg burns real fuel

    def _announce(self, package, f, g, names, wps, push_s, manifest):
        """Record the flight in the manifest and queue the radio calls (on station / pushing / egressing)."""
        manifest.add("friendly", f.id, names, squadron=f.squadron_id, callsign=f.callsign, player=f.is_player)
        self.flight_groups.append((f, g))
        # who speaks: every AI aircraft (your own wingmen included, never you) is announced by callsign; extra packages carry a package prefix
        pfx = "" if package.id == self._anchor_id else f"P{package.number} "
        for i, un in enumerate(names):
            if not (f.is_player and i == 0):
                self._ulabels[un] = pfx + un.upper()
        lab = pfx + f.callsign.upper()
        if not f.is_player:
            if f.tag:
                self._fcalls.append((60.0, f"{lab}: on station."))
            else:
                self._pkg_who.setdefault(package.id, lab)
                cap = next((w.eta_s for w in wps if w.action == "CAPORBIT"), None)
                egr = next((w.eta_s for w in wps if w.name == "EGR"), None)
                if cap is not None:
                    if cap > 10:
                        self._fcalls.append((float(cap), f"{lab}: on station."))
                else:
                    if push_s > 10:
                        self._fcalls.append((float(push_s), f"{lab}: pushing."))
                    if egr is not None and egr > 10:
                        self._fcalls.append((float(egr), f"{lab}: off target, egressing."))

    def _roe_defaults(self, package, f, g):
        """Rules of engagement for ground-attack and SEAD jets (restricted, return fire, out-of-ammo return). -> (armor, ai_sead, ai_a2g)."""
        o = self.o
        armor = self.groups_by_asset.get(package.objective.target_id)
        ai_sead = (f.role == Role.SEAD or getattr(f, "kit", "") == "JSOW") and not f.tag and (not f.is_player or o.player_is_ai)
        if ai_sead:         # a SEAD (or JSOW) jet's job is the radar, not the fighters: v0.39.9 run, both Hornet SEAD flights chased MiGs into Tor and SA-11 range and died 150 s before their HARM point
            g.points[0].tasks.append(task.OptROE(task.OptROE.Values.ReturnFire))        # shoots back when shot at; weapons free again at the HARM point (below)
        # Every AI ground-attack flight (strike, DEAD, SEAD, JSOW, CAS) stays on its job: v0.39.23 run, strikers with nothing but guns left
        # turned on fresh MiGs and Su-27s and most of the coalition's air losses were these flights never leaving after their task.
        # On the way in: evade, never attack aircraft. After the attack (EGR): a jet with radar missiles shoots back at whoever shoots it,
        # a jet without them (the Hog) stays restricted and relies on the air cover. Out of air-to-ground weapons: home.
        ai_a2g = not f.tag and (not f.is_player or o.player_is_ai) and (f.role in A2G_ROLES or getattr(f, "kit", "") == "JSOW")
        if ai_a2g:
            g.points[0].tasks.append(task.OptRestrictAirToAirAttack(True))
            rtb = task.OptRTBOnOutOfAmmo(); rtb.params["action"]["params"]["value"] = A2G_WEAPONS
            g.points[0].tasks.append(rtb)
            if not ai_sead:
                g.points[0].tasks.append(task.OptROE(task.OptROE.Values.ReturnFire))    # weapons free again at the attack point (below)
        return armor, ai_sead, ai_a2g

    def _attach_waypoints(self, package, f, g, wps, first, ai_a2g, ai_sead, run_t0, push_s, tot_s, stop, hold_end, stw, armor, special):
        """Add each route point to the group with its tasks: ETAs, ROE, ECM, fuel, orbits, bombs, JSOW, CAS, SEAD attacks."""
        o = self.o
        pt = self._pt
        for w in wps[first:]:
            wp = g.add_waypoint(pt(w.x, w.y), w.alt_ft * FT, w.speed_kts * KPH, w.name)
            if w.rad:
                wp.alt_type = "RADIO"                                 # LOW tier: height above the ground
            if f.is_player:
                if w.agl:
                    wp.alt, wp.alt_type = 0, "RADIO"                 # on the ground: sensors and weapons slave to the target
                self._set_eta(wp, w, wps)
                if special:
                    nm = special(w)
                    if nm:
                        wp.name = nm
                if not o.player_is_ai:                                       # all-AI test: the player's flight now gets the AI tasks below, like any AI flight
                    if w.action == "BOMB":
                        wp.tasks.append(task.Bombing(pt(w.x, w.y), group_attack=True))
                    continue
            if ai_a2g and w.name == "EGR":
                wp.tasks.append(task.OptROE(task.OptROE.Values.ReturnFire))                      # and no chasing on the way home either
                if f.aircraft in SHOOTS_BACK:
                    wp.tasks.append(task.OptRestrictAirToAirAttack(False))                       # self-defence only: return fire, at whoever shoots
            if ai_a2g and not ai_sead and w.action in ("BOMB", "CAS"):
                wp.tasks.append(task.OptROE(task.OptROE.Values.WeaponFree))                      # the ground target; aircraft stay off limits (restricted)
            if run_t0 is not None:
                if w is wps[first]:
                    wp.tasks.append(task.OptECMUsing(task.OptECMUsing.Values.NeverUse))          # jammers off until the attack leg
                if w.name == "PUSH":
                    # the ECM script models jamming itself (always on over the attack leg). Without it, DCS's own ECM: the AI switches it on only
                    # when a radar has locked it, which is close to the action. Burn-through is not modelled by DCS's AI choice; on the way in
                    # and out it stays off, so it never gives the formation away from afar.
                    wp.tasks.append(task.OptECMUsing(task.OptECMUsing.Values.AlwaysUse if o.ecm_script else task.OptECMUsing.Values.UseIfOnlyLockByRadar))
                elif w.name == "EGR":
                    wp.tasks.append(task.OptECMUsing(task.OptECMUsing.Values.NeverUse))
            if o.ai_unlimited_fuel and w.name in ("PUSH", "CAP1"):
                wp.tasks.insert(0, task.SetUnlimitedFuelCommand(False))          # the combat leg burns real fuel
            if o.ai_unlimited_fuel and w.name == "EGR":
                wp.tasks.insert(0, task.SetUnlimitedFuelCommand(True))           # and the trip home is free again
            if w.action == "HOLD":
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct.stop_after_time(int(hold_leave_s(wps, push_s))); wp.tasks.append(ct)
            elif w.action == "CAPORBIT":
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH)))
                ct.stop_after_time(stop); wp.tasks.append(ct)
                if f.tag:
                    self._sup_cts.append(ct)
            elif w.orbit:                                                    # fighters held short of live SAM cover / on their station
                if self._snipe_at.get(id(g)) is w:                              # v0.41.10: on station: maximum-range shots (snipe) from here on
                    wp.tasks.append(task.OptAAMissileAttackRange(task.OptAAMissileAttackRange.Values.MaxRange))
                # v0.41.43: a Circle, not DCS's default Race-Track. A race-track runs from this point to the NEXT waypoint, which here is RTB:
                # 2026-10-20 tracks show Springfield 7 / Hornet 6 flying 57-60 nm from their station to RTB and back (the "north to south" orbit)
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct.stop_after_time(hold_end if (w is stw and hold_end is not None) else stop); wp.tasks.append(ct)
                if w is stw and self._holds and self._holds[-1]["end"] == hold_end and ct not in self._holds[-1]["cts"]:
                    self._holds[-1]["cts"].append(ct)
            elif w.action == "BOMB":
                # v0.41.16: the attack is only good until LATE_ATTACK_S after its TOT; later, the flight flies on to its egress and home (the
                # v0.41.14 run: the lead, alone after its wingmen flamed out, bombed 30 min late and met a live SA-6)
                bct_ = task.ControlledTask(task.Bombing(pt(w.x, w.y), group_attack=True))
                bct_.stop_after_time(int(w.eta_s + LATE_ATTACK_S)); wp.tasks.append(bct_)
            elif w.action == "JSOW":
                self._jsow_tasks(wp, f, armor, package, w.eta_s)
            elif w.action == "CAS":
                self._cas_tasks(wp, w, armor, tot_s)
            elif w.action == "SEAD" and armor is not None:                 # 'armor' is simply the target asset's group here
                self._sead_attack_tasks(package, f, wp, w, armor)

    def _home_leg(self, f, g, base, wps, idx, hold_end, stop, special):
        """The way home: the recovery entry point, landing or deck recovery."""
        o = self.o
        pt = self._pt
        if base.kind == BaseKind.AIRFIELD:
            if not f.is_player or o.player_is_ai:
                # v0.41.10: staggered recovery. Each AI flight comes home through its own entry point, 8 nm out on its own bearing and height, so the
                # flights do not all arrive over the field at once (two F-15 wingmen collided low and slow on the way home in two runs)
                lp_ = g.points[-1].position
                rb_ = bearing(base.x, base.y, lp_.x, lp_.y) + RCV_SPREAD[idx % len(RCV_SPREAD)]
                rx_, ry_ = offset(base.x, base.y, rb_, RCV_NM * NM)
                rcv_alt_ = home_leg_ft((lp_.x, lp_.y), (rx_, ry_), 3000 + 1000 * (idx % 4))      # v0.41.49: the home leg clears the ridges (was a fixed 3,000-6,000 ft)
                rcvp_ = g.add_waypoint(pt(rx_, ry_), rcv_alt_ * FT, 300 * KPH, "RCV")
                if self._skip_landing(base):          # v0.41.18: recovered at its entry point instead of landing (setting "AI landings: airfields")
                    rcvp_.tasks.append(task.RunScript(f"SQE_RECOVER('{g.name}')"))
                    self._recov_net(g, f, None, base.x, base.y, wps, hold_end, stop)
            if (f.is_player and not o.player_is_ai) or not self._skip_landing(base):
                g.land_at(self.apt[base.id])
            if special:
                g.points[-1].name = "RTBXHB"
        elif (not f.is_player or o.player_is_ai) and self._skip_landing(base):
            # v0.41.17: an AI flight going home to the boat is recovered at a point CV_RECOVER_NM out: it counts as landed and leaves the mission
            # (SQE_RECOVER in the hook). DCS's carrier landing queue ran an F-14 dry and stacks AI in your pattern.
            lp_ = g.points[-1].position
            rx_, ry_ = offset(base.x, base.y, bearing(base.x, base.y, lp_.x, lp_.y), CV_RECOVER_NM * NM)
            rcv_ = g.add_waypoint(pt(rx_, ry_), 2000 * FT, 300 * KPH, "RTBXHB" if special else "RTB")
            rcv_.tasks.append(task.RunScript(f"SQE_RECOVER('{g.name}')"))
            self._recov_net(g, f, self.ship[base.id].units[0].name if base.id in self.ship else None, base.x, base.y, wps, hold_end, stop)
        else:
            rtb = g.add_waypoint(pt(base.x, base.y), 600, 300 * KPH, "RTBXHB" if special else "RTB")
            rtb.type, rtb.action = "Land", PointAction.Landing
            rtb.link_unit = rtb.helipad = self.ship[base.id].units[0].id
        # v0.41.32: used to force the player's landing point speed free here ("so it never closes a locked-speed run"), but the trailing
        # DIVERT/TKR/BULLS steerpoints are appended later (_trailing_steerpoints) with no time lock of their own, so this point was never
        # followed by a locked-time point and the ME refused the save ("Viper 2: Waypoint 8 ... not surrounded by waypoints with locked
        # time!"). land_at() already leaves the landing point's speed locked, which is safe; _free_locked_speeds frees a speed lock only
        # where the ME actually needs one, after every trailing point exists.

    @staticmethod
    def _add_ship_warehouses(m):
        """The Mission Editor writes a warehouse entry for every ship (keyed by unit id) and pydcs writes none. A carrier with no entry leaves the
        player's aircraft with no warehouse to spawn from, which dropped the player into the F10 map until the mission was resaved in the editor."""
        for coal_name, coal in (("blue", m.coalition.get("blue")), ("red", m.coalition.get("red"))):
            if coal is None:
                continue
            for country in coal.countries.values():
                for sg in country.ship_group:
                    for u in sg.units:
                        m.warehouses.warehouses[u.id] = {
                            "jet_fuel": {"InitFuel": 100}, "gasoline": {"InitFuel": 100}, "diesel": {"InitFuel": 100}, "methanol_mixture": {"InitFuel": 100},
                            "unlimitedFuel": True, "unlimitedMunitions": True, "unlimitedAircrafts": True,
                            "OperatingLevel_Air": 10, "OperatingLevel_Eqp": 10, "OperatingLevel_Fuel": 10,
                            "aircrafts": {}, "weapons": {}, "suppliers": {}, "allowHotStart": False, "dynamicCargo": True, "dynamicSpawn": False,
                            "periodicity": 30, "size": 100, "speed": 16.666666, "coalition": coal_name}

    @staticmethod
    def _save_without_carrier_slots(m, out_path):
        """pydcs writes allowLso / allowAirboss = true for every carrier, which adds "LSO" and "Air Boss" client slots to the slot list when you
        fly from the boat. SQE has no use for them, so they are written as false (the pinned pydcs is left unmodified; we wrap its dict() for the save)."""
        from dcs import unit as dcs_unit
        orig = dcs_unit.Ship.dict
        def patched(self):
            d = orig(self)
            if "allowLso" in d:
                d["allowLso"] = False
            if "allowAirboss" in d:
                d["allowAirboss"] = False
            return d
        dcs_unit.Ship.dict = patched
        try:
            m.save(str(out_path))
        finally:
            dcs_unit.Ship.dict = orig

    @staticmethod
    def _free_locked_speeds(m):
        """Mission Editor refuses to save a route where every point between two time-locked points has a locked speed (free the first one),
        and the mirror: any point with BOTH speed and time free needs a time-locked point on each side, so a point past the last time-locked
        waypoint (the tail after a station, or the trailing DIVERT/TKR/BULLS steerpoints on the player's own route) can never be both-unlocked
        (lock its speed; v0.41.32, "Viper 2: Waypoint 8 ..."). Runs last, after every point (including the trailing steerpoints) is in place."""
        for co in m.coalition.values():
            for c in co.countries.values():
                for grp in list(c.plane_group) + list(c.helicopter_group):
                    p = grp.points
                    L = [i for i, x in enumerate(p) if getattr(x, "ETA_locked", False)]
                    for a, b in zip(L, L[1:]):
                        mid = p[a + 1:b]
                        if mid and all(getattr(x, "speed_locked", False) for x in mid):
                            mid[0].speed_locked = False
                    tail = p[(L[-1] + 1):] if L else p[1:]
                    for x in tail:
                        if not getattr(x, "ETA_locked", False) and not getattr(x, "speed_locked", False):
                            x.speed_locked = True

    @staticmethod
    def _f14_special_namer(wps):
        """F-14B(U) (ED mission-editor naming): a waypoint whose name carries 'X' + a code is also a special point the jet can select
        (IP, ST = target, HB = home base, B = bullseye; X1..X3 = priority points). Each code may appear only once, otherwise the jet ignores
        the duplicates, so every code is handed out to the first matching planner waypoint only. Untested in the cockpit (a Settings toggle)."""
        by = {}
        for w in wps:
            by.setdefault(w.name, w)
        tgt = next((w for w in wps if w.action in OBJECTIVE_ACTIONS), None)
        plan = {}
        if "IP" in by:
            plan[id(by["IP"])] = "IPXIP"
        if tgt is not None:
            plan[id(tgt)] = "TGTXST"
        if "RTB" in by:
            plan[id(by["RTB"])] = "RTBXHB"
        if "BULLS" in by:
            plan[id(by["BULLS"])] = "BULLSXB"
        for nm, code in (("DEP", "DEPX1"), ("MSHL", "MSHLX2"), ("PUSH", "PUSHX3")):
            if nm in by and id(by[nm]) not in plan:
                plan[id(by[nm])] = code
        return lambda w: plan.get(id(w))

    @staticmethod
    def _set_eta(wp, w, wps):
        """Write the planned time on the waypoint so the jet's own TOS / TOT page (F-16 CRUS) shows the kneeboard time instead of the mission start.
        Only PUSH and the objective point are time-locked; speed is left free on points between two locked ones (as Retribution does)."""
        wp.ETA = max(0, int(w.eta_s))
        # v0.41.2: a TARCAP / escort / sweep station is not time-locked. Its route goes PUSH -> station -> home, so a locked station put the
        # landing point (speed locked) straight after a locked time, and DCS refused the mission ("Viper 3: All waypoints (5-5) have locked
        # speed and surrounded by waypoints 4 and 5 with locked time"). PUSH stays locked: that is the time you have to hit.
        # v0.41.60: "a station" is a waypoint that orbits (TARCAP / ESCORT / SWEEP stations) or a TARCAP's own point; before the rename this was the action list
        # ("TARCAP", "ESCORT", "SWEEPSTN"). A flight with no station of its own (stand-off setting off, fleet-defence fighters) still flies its ESCORT / SWEEP point to a time.
        locked = w.name == "PUSH" or (w.action in OBJECTIVE_ACTIONS and not (w.orbit or w.action == "TARCAP"))
        wp.ETA_locked = locked
        idx = {x.name: i for i, x in enumerate(wps)}
        lo = idx.get("PUSH"); hi = next((i for i, x in enumerate(wps) if x.action in OBJECTIVE_ACTIONS), None)
        here = idx.get(w.name)
        between = lo is not None and hi is not None and here is not None and lo < here < hi
        wp.speed_locked = not between
        if lo is not None and here is not None and here == lo - 1 and here >= 1 and w.name != "TAKEOFF":
            wp.speed_locked = False       # the Mission Editor refuses takeoff(locked) .. PUSH(locked) with every point between at locked speed; the leg into PUSH stays free

    def _spawn_point(self, f, base, geom):
        """Where an AI flight 'just departed': a pretend-DEP point behind the base. Carrier jets and land jets start differently and
        flights of the same service are spaced a few miles apart (slow climb-out, lateral offset) so nobody stacks on anybody."""
        navy = base.kind == BaseKind.CARRIER
        k = self._svc_k.get(navy, 0)
        self._svc_k[navy] = k + 1
        brg = bearing(base.x, base.y, *geom.mshl)
        room = max(4.0, dist(base.x, base.y, *geom.mshl) / NM - 9.0)
        along = min(room, 4.0 + 3.0 * k)
        x, y = offset(base.x, base.y, brg, along * NM)
        x, y = offset(x, y, brg + 90, (1.5 if k % 2 else -1.5) * NM * (1 + k // 2))
        return (x, y), (2500 if navy else 4500), (300 if navy else 360)

    def _trailing_steerpoints(self, package, rows, spec):
        """DIVERT, TKR and BULLSEYE come after RTB on the player's group, like Retribution (tanker/bullseye last)."""
        pf = package.player_flight
        g = next(gr for fl, gr in self.flight_groups if fl is pf)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        for name, x, y, _t, alt, kts, _n in rows:
            a = 20000 * FT if name == "TKR" else 5000 * FT
            g.add_waypoint(pt(x, y), a, (spec.profile.aar_kts if name == "TKR" else 300) * KPH, name)

    # ---- Link 16 / SADL: the package flies as one network ------------------------------------------------------------------
    def _datalinks(self, package) -> list:
        stn = {}
        whois = []
        for f, g in self.flight_groups:               # your own flight is one network: wingmen are members of each other (blue on the HSD/TAD)
            for u1 in g.units:
                if getattr(u1, "datalink", None) is None:
                    continue
                if len(g.units) > 1:
                    try:
                        u1.datalink.settings.flight_lead = (u1 is g.units[0])
                    except Exception:
                        pass
                for u2 in g.units:
                    if u1 is not u2 and getattr(u2, "datalink", None) is not None:
                        u1.datalink.network.add_member(u2.id)
        for f, g in self.flight_groups:
            lead = g.units[0]
            lead_stn = "-"
            for i, u in enumerate(g.units, 1):
                dl = getattr(u, "datalink", None)
                if dl is None:
                    continue
                lt = dl.link_type.name
                stn[lt] = stn.get(lt, 0) + 1
                code = f"{stn[lt]:05o}" if lt == "LINK16" else f"{stn[lt]:04o}"
                u.set_property("STN_L16" if lt == "LINK16" else "SADL_TN", code)
                nm = u.callsign_dict["name"]
                u.set_property("VoiceCallsignLabel", (nm[0] + nm[:-2][-1]).upper())
                u.set_property("VoiceCallsignNumber", nm[-2:])
                if i == 1:
                    lead_stn = code
            pidx = package.flights.index(f)
            whois.append({"cs": f"{f.callsign}-1..{f.count}", "ac": f.aircraft, "role": (f.tag or f.role.value)[:7],
                          "m3": f"4{package.number % 8}{pidx % 8}{(pidx + package.number) % 8}", "stn": lead_stn, "you": f.is_player})
        # v0.41.41 (XO 2026-10-20): the AWACS is neither member nor donor. Members are your wing (above); donors are the Link 16 capable flights
        # of the SAME package (their leads), nothing from other packages and no support aircraft
        mine = {id(f_) for f_ in package.flights if not f_.tag}
        for f, g in self.flight_groups:
            if id(f) not in mine:
                continue
            for u in g.units:
                dl = getattr(u, "datalink", None)
                if dl is None:
                    continue
                net = dl.network
                for of, og in self.flight_groups:
                    if of is f or id(of) not in mine:
                        continue
                    odl = getattr(og.units[0], "datalink", None)
                    if odl is None or odl.link_type != dl.link_type:
                        continue
                    if not net.add_donor(og.units[0].id):
                        net.add_member(og.units[0].id)
        return whois

    # ---- CAS: both columns drive into contact so the clash is under way at the CAS TOT (+/- 30 s) -------------------------
    def _translate(self, g, dx, dy):
        for u in g.units:
            u.position = mapping.Point(u.position.x + dx, u.position.y + dy, self.t)
        for p in g.points:
            p.position = mapping.Point(p.position.x + dx, p.position.y + dy, self.t)

    @staticmethod
    def _ground_orders(g):
        """v0.41.39: explicit orders on a ground group: weapons free, alarm state red (radars up, guns manned). Left at the default a group may sit
        at 'auto' and hold fire on aircraft parked in range; set here it engages whatever it sees. The Mission Editor has no target-priority
        order for ground units, so 'other ground units before parked jets' is not enforced: DCS picks the target (usually the nearest threat)."""
        if any(isinstance(t_, task.OptROE) for t_ in g.points[0].tasks):
            return
        g.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponFree))
        g.points[0].tasks.append(task.OptAlarmState(2))

    def _drive(self, g, via, speed_ms):
        for q in via:
            g.add_waypoint(mapping.Point(q[0], q[1], self.t), PointAction.OffRoad, speed_ms * 3.6)
        self._ground_orders(g)

    def _spawn_cas_support(self, package, plan, geom, manifest):
        if not package.jtac:
            return
        r = self.vrng
        cx, cy = self.armor_center or (geom.tx, geom.ty)
        fb = self._nearest_airfield(cx, cy)
        brg = bearing(cx, cy, fb.x, fb.y)                         # towards our side
        tot = float(self.cas_tot or 1500.0)
        t_contact = max(300.0, tot - 15.0)                        # guns are firing as the CAS flight arrives
        v = max(2.5, min(8.0, 9000.0 / t_contact))                # m/s, a believable advance
        dist_run = v * t_contact + 1500.0                         # each side starts this far from the contact point
        enemy = self.groups_by_asset.get(self.armor_id) if self.armor_id else None
        static = bool(self.armor_id) and self.state.assets[self.armor_id].variant == "GARRISON"      # dug in: our troops come to it
        if enemy is not None and not static:
            ex, ey = offset(cx, cy, brg + 180, dist_run)
            self._translate(enemy, ex - cx, ey - cy)
            self._drive(enemy, [offset(cx, cy, brg, 2500)], v)
        fx, fy = offset(cx, cy, brg + r.uniform(-6, 6), dist_run)
        comp = [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(2, 3)), ("M1043_HMMWV_Armament", r.randint(1, 2))]
        sc = ground.blue_scale(self.state, self.armor_id or "")          # the friendly force is as strong as Blue is in this sector
        comp = [(n_, max(1, int(round(c_ * sc)))) for n_, c_ in comp]
        g = self._platoon(self.usa, f"Friendly Task Force {package.number}", comp, fx, fy, (int(brg) + 180) % 360, F.Rectangle)
        if g is not None:
            names = []
            for k, u in enumerate(g.units, 1):
                u.name = f"TF{package.number}|{k}"; names.append(u.name)
            self._drive(g, [offset(cx, cy, brg + (0 if static else 180), 2000 if static else 2500)], v)
            manifest.add("friendly_ground", self.armor_id or "", names)
        jx, jy = offset(fx, fy, brg + 90, 120)
        jt = self.m.vehicle_group(self.usa, f"Axeman {package.number}-1", _UN.Hummer, mapping.Point(jx, jy, self.t), heading=(int(brg) + 180) % 360, group_size=1)
        jt.units[0].name = f"JTAC-{package.id}"
        p0 = jt.points[0]
        p0.tasks.append(task.FAC(callsign=1, frequency=int(plan.freq("JTAC") * 1e6), modulation=task.Modulation.AM, number=1))
        p0.tasks.append(task.SetInvisibleCommand(True))
        p0.tasks.append(task.SetImmortalCommand(True))
        jt.add_waypoint(mapping.Point(*offset(cx, cy, brg, 3800), self.t), PointAction.OffRoad, v * 3.6)

    HARM_AXES = (0, 15, -15, 30, -30)                        # v0.41.24: degrees the HARM axis may turn off the package's own axis

    JSOW_AXES = (30, -30, 50, -50, 15, -15, 70, -70)       # v0.41.22: degrees off the HARM shooters' axis, tried in this order

    # ---- late activation helper ------------------------------------------------------------------------------------------------
    def _late(self, g, seconds):
        g.late_activation = True
        trig = triggers.TriggerOnce(comment=f"activate {g.name}")
        trig.add_condition(condition.TimeAfter(int(seconds)))
        trig.add_action(action.ActivateGroup(g.id))
        self.m.triggerrules.triggers.append(trig)

    def _field_zone(self, a, tx, ty):
        """v0.41.1: an alert field scrambles on what ITS radar sees: a circle round the field (not round the target), sized by how far the
        field is from the fight (FIELD_DETECT_NM at most). The v0.41.0 Batumi run: an earlier package already airborne inside one big circle
        round the target scrambled all 20 pairs from six fields 10 s into the mission. -> (x, y, radius nm)"""
        return a.x, a.y, tm.field_detect_nm((a.x, a.y), (tx, ty), self.state)

    # ---- reactive dispatch: enemy reinforcements and blue alert pairs launched during the sortie ---------------------------------
    def _pick_tier(self, geom, role, profile, tx, ty, skip=()):
        """The altitude profile for this package from the SAM picture (profiles.py); the role altitude when nothing is better."""
        pts = [geom.push, geom.ip, (tx, ty), geom.egr]
        return profiles.choose(self.state, role, profile, pts, (tx, ty), getattr(self.wx, "ceiling_ft", None), skip, relief.msa_ft(pts[1:]))

    def _flight_plans(self, geom, package, tx, ty, skip=()):
        """Per kind of flight: its own altitude tier, and for AI escorts and sweeps the point short of live SAM cover where they stop.
        Keyed (role, profile) like routes.plan_route looks them up. The player's own route is never cut short; a package whose job IS the sweep
        (COUNTER_AIR) goes in as before."""
        geom.tiers, geom.stand = {}, {}
        geom.ai_player = bool(self.o.player_is_ai)
        from .packages import is_sweep
        geom.sweep = is_sweep(package.objective)
        tid_ = package.objective.target_id
        tt_ = self.state.assets.get(tid_) if tid_ else None
        geom.jsow_keep = [(a.x, a.y, max(HARM_LAUNCH_NM, JSOW_KEEP_HIGH_NM)) for a in self.state.assets.values()            # every live SA-10 near the target, itself included (v0.41.46: 40 nm, as the loop used to force)
                          if tt_ is not None and a.variant in tm.UMBRELLA_VARIANTS and not a.destroyed and not getattr(a, "suppressed", False)
                          and dist(a.x, a.y, tt_.x, tt_.y) <= (tm.UMBRELLA_KM / 1.852 + HARM_LAUNCH_NM) * NM]
        # v0.41.46: the target site's own live SAMs too (SA-11 20 nm, SA-6 16, SA-2 26, SA-3 15: AVOID_NM, reach plus margin): the 2026-10-20 run's JSOW point sat
        # 19.6 nm from the Gudauta SA-11 it was shooting at and lost two jets to it
        if tt_ is not None:
            own_ = tm.cluster_ids(tt_)
            geom.jsow_keep += [(a.x, a.y, AVOID_NM[a.variant]) for a in self.state.assets.values()
                               if a.id in own_ and a.kind == AssetKind.SAM and a.variant in AVOID_NM and a.variant not in tm.UMBRELLA_VARIANTS
                               and not a.destroyed and a.health > 0.05 and not getattr(a, "suppressed", False)]
        # v0.41.11: every other live SA-10 within 150 nm: AI strike / SEAD / CAS routes bend around it (routes.avoid_circles)
        um_ = tm.umbrella_site(self.state, tt_) if tt_ is not None else None             # the one the HARMs go for: the flights must come to it
        # v0.41.20: every live medium / long-range SAM (SA-2/3/6/11/10), each by its own reach (AVOID_NM). A site whose circle holds the target
        # itself is the one this package comes for (its DEAD, or the site a CAS escort's HARMs keep quiet): no bending round that one
        geom.sa10_avoid = [(a.x, a.y, AVOID_NM[a.variant]) for a in self.state.assets.values()
                           if a.kind == AssetKind.SAM and a.variant in AVOID_NM and not a.destroyed and a.health > 0.25 and not getattr(a, "suppressed", False)
                           and a.id not in (tid_, getattr(um_, "id", None)) and dist(a.x, a.y, tx, ty) <= 150 * NM
                           and dist(a.x, a.y, tx, ty) > (AVOID_NM[a.variant] + 3) * NM]
        pts = [geom.push, geom.ip, (tx, ty)]
        for f in package.flights:
            if f.tag:
                continue
            prof = AIRCRAFT[f.aircraft].profile
            key = (f.role, id(prof))
            if key not in geom.tiers:
                geom.tiers[key] = self._pick_tier(geom, f.role, prof, tx, ty, skip)
            if key in geom.stand or not self.o.fighter_standoff or f.role not in (Role.TARCAP, Role.ESCORT, Role.SWEEP):
                continue
            if package.objective.type in (ObjectiveType.COUNTER_AIR, ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE) and not geom.sweep:
                continue
            # TARCAP and ESCORT roles: a station of their own, for you and for the AI alike (v0.40.1)
            t = geom.tiers[key]
            geom.stand[key] = profiles.station(self.state, pts, t.alt_ft if t.changed else prof.alt_ft.get(f.role, 20000), geom.egr)
            if geom.sweep:
                geom.stand[key] = self._sweep_station(geom.stand[key], tx, ty, pts[0], package)
            elif f.role in (Role.ESCORT, Role.SWEEP, Role.TARCAP) and any(getattr(x_, "kit", "") == "JSOW" for x_ in package.flights):
                # v0.41.42 (XO 2026-10-20): the package escort shepherds the JSOW flight, not the HARM shooters' station: it holds ESCORT_BEHIND_NM
                # behind the JSOW launch point (on its own axis), where the JSOW jets release and turn home (the 2026-10-20 run lost all five to MiG-29s
                # with the escort 20 nm away). Not kept out of SAM cover: that is the shepherd's risk. It leaves from the station, not by the package egress.
                jx_, jy_ = jsow_launch_xy(geom, self._jsow_side(package, geom))
                ax_ = bearing(tx, ty, jx_, jy_)
                if f.role == Role.ESCORT:                  # the package escort (before v0.41.50 the SWEEP role)
                    ex_, ey_ = offset(jx_, jy_, ax_, ESCORT_BEHIND_NM * NM)
                else:
                    # v0.41.43 (XO 2026-10-20): the TARCAP overwatches from just behind the JSOW flight (where it used to turn round with the HARM shooters),
                    # TARCAP_BEHIND_NM back, and further back (1 nm steps, at most 14 more) until it is outside every live medium / long-range SAM ring plus
                    # the stand-off margin. The JSOW point itself is already 40 nm from every SA-10, so the SA-10 rule holds.
                    sites_ = profiles._cover_sites(self.state, t.alt_ft if t.changed else prof.alt_ft.get(f.role, 20000))
                    back_ = TARCAP_BEHIND_NM
                    while True:
                        ex_, ey_ = offset(jx_, jy_, ax_, back_ * NM)
                        if back_ >= TARCAP_BEHIND_NM + 14 or all(dist(ex_, ey_, a_.x, a_.y) > r_ for a_, r_ in sites_):
                            break
                        back_ += 1.0
                geom.stand[key] = (ex_, ey_, [], dist(ex_, ey_, tx, ty) / NM, False)

    RECOV_NET_NM = 12          # v0.41.25: a homebound AI flight this close to its deck / field counts as recovered, waypoint reached or not

    def _recov_net(self, g, f, cv_unit, x, y, wps, hold_end, stop) -> None:
        """v0.41.25: the safety net for SQE_RECOVER. A flight sent home early (bingo, out of missiles) flies straight to its deck or field and
        never passes its recovery point, so it never ran SQE_RECOVER (the v0.41.24 run: Hornets circling the boat). The hook recovers the group
        once its lead is within RECOV_NET_NM of the carrier (where it is now, not where it started) or the field, after its work is done."""
        t_ = max(float(wps[-1].eta_s) if wps else 0.0, float(hold_end or 0), float(stop) if f.tag else 0.0)
        self._recov.append({"g": g.name, "cv": cv_unit or "", "x": float(x), "z": float(y), "r": self.RECOV_NET_NM * NM, "t": t_})

    COVER_SHIFTS = (0, 4, 8, 12, 16, 20, 24)                 # v0.41.23: nm the centre may move, toward our side first, then sideways
    COVER_TURNS = (0, 30, -30, 60, -60, 90, -90)

    def _zulu_note(self) -> str:
        tz = float(theatres.active().get("tz", 0) or 0)
        return "Times are local. Zulu = local" + (f" - {tz:g} h." if tz > 0 else f" + {-tz:g} h." if tz < 0 else " (no offset).")

