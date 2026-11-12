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
from dcs.translation import String
from dcs.point import PointAction
from . import theatres, weather
from dcs.unit import Skill
from dcs.unitgroup import VehicleGroup

from . import barcap, briefing as brief, callsigns, carcass, detection, ground, profiles, relief, runways, sams
from . import seacheck as seac
from . import pydcs_patch
from . import threatmap as tm
from .aircraft import AIRCRAFT

TUNE_PARAMS = {"F-16C": ("COMM1_FREQ",), "A-10C": ("UHF_FREQ",), "FA-18C": ("COMM1_FREQ", "COMM2_FREQ"), "F-14BU": ("COMM1_FREQ", "COMM2_FREQ")}   # v0.41.215: the player's radios SQE can read (XO's probes 2026-10-28 / 30); the F-15C (FC3) has none
TUNE_BAND_MHZ = 0.05            # v0.41.215: tuned = within this much of the AWACS frequency (judgment call; the probe used 0.1)
from .debrief import Manifest, install_hook
from .difficulty import Difficulty, ai_skill
from .fighter_stations import FighterStations, ESCORT_AFTER_TOT_S, TARCAP_AFTER_TOT_S, axis_station, ENGAGE_LEAD_S
from .support_caps import SupportCaps
from .red_air_picture import RedAirPicture, A2A_ZONE_NM
from .raid_spawns import RAID_MEET_LEAD_S, RAID_MPS, RAID_SUPPLY_UNITS, SUPPLY_BUILDINGS, RaidSpawns, supply_parts
from . import road_sites
from .strike_tasks import StrikeTasks, DEAD_GATE_KM, SEAD_WAVE_KM, TRACK_RADARS, SEARCH_RADARS, KPH
from . import kneeboard
from .kneeboard import latlon, render_pages
from .loadouts import LoadoutLibrary, enemy_cap_loadout, ENEMY_FIGHTERS
from .models import SEAD_AIMS, AssetKind, BaseKind, ObjectiveType, Role, task_label
pydcs_patch.install()           # v0.41.66: pydcs's scattered formation could loop forever and freeze a build (sqe/pydcs_patch.py)

TARCAP_LEAD_S = 120           # v0.41.115 (was 0; XO 2026-10-22: fighters in first, BMS-style): a TARCAP arrives this long before the first flight it covers. 2 min, not
                              # v0.41.0's 5-minute head start, which let the SA-10 kill six waiting Eagles (judgment call). v0.41.1 had it arrive WITH the HARM shooters.
FIELD_DETECT_NM = tm.FIELD_DETECT_NM   # an alert field scrambles when blue comes within this of the field (less for fields close to the fight)
RUNWAY_HALF_LEN_M = 2600.0    # v0.41.48: ground groups keep out of a corridor this far either side of the airfield reference point along each runway heading (pydcs has only the heading; judgment call, long enough for the longest Caucasus strips)
ILS_DUMMY_MODES = ("on",)           # S32 (XO 2026-11-11): one mode, on or off (Settings > ils_dummy; "off" builds none and keeps the old ILS-friendly wind window)
ILS_DUMMY_TYPE = planes.Christen_Eagle_II     # S32: a small aircraft (a 2 m high biplane) so it hardly shows (v0.41.395: standing on the grass beside the threshold, runways.ils_dummy_point); it is invisible to AI and sensors, immortal and never started (DCS cannot hide its model). v0.41.336 had an F-16C beside the threshold. Judgment call; DCS test pending
PARKED_MAX = 8               # v0.41.297 (XO 2026-11-05: a counter-air strike has nothing to hit, the ramp is empty): at most this many parked jets (v0.41.324: real units, was 12 statics) stand on the target field's ramp. Judgment call: a statics-count cap for VR; the wing's true strength stays in the state (a static costs `carcass_weight` of a unit)
RUNWAY_HALF_WIDTH_M = 120.0   # ...and this far either side of the centreline (runway about 45-60 m wide plus a margin; judgment call)
SCRUB_POINT_NM = 20           # v0.41.223: a package flight's SCRUB point (where a scrubbed flight goes first) sits this far from its home field, on the bearing of its route's last point (the same shape as the stand-off ABORT point)
BLUE_BASE_DEF_SKILL = "Excellent"   # v0.41.222 (XO 2026-10-31): blue's base Patriot / HAWK / AAA are always the top DCS skill, whatever the Blue skill setting or the level says. Why: under "level" they were left at pydcs's Average while red's sites run at the level's skill (High on L3), and XO saw them barely fire. Judgment call (no public figure for operator quality).
CAP_SPREAD_NM = {"TARCAP": 15, "ESCORT": 10, "SWEEP": 20,
                 "BASECAP": 25, "CVCAP": 30, "HAVCAP": 20, "TNKCAP": 20}   # S9 (v0.41.350): the support CAPs, used by support_caps (judgment calls, no public figure); Phase 8 (v0.41.349): the race-track leg from CAP1 (the station) to CAP2, across the threat axis. Judgment calls: no public leg length found (FAA anchor tracks of about 50 nm are civil)
CAP2_ROOM_NM = 8             # Phase 8: CAP2 must have at least this much SAM room (nm to the nearest SAM ring), or as much as the station itself has when that is less (8 is the cover circle's own floor)
TARCAP_BEHIND_NM = 8          # v0.41.43 (16; v0.41.115: 8, XO 2026-10-22: it sat 56 nm from red's patrols, too far to snipe): with a JSOW flight the TARCAP holds this far behind the JSOW launch point, further back (stepped) until it is outside live medium-range SAM rings (judgment call)
TARCAP_FWD_NM = 20           # v0.41.120: the TARCAP's engage circle tries to reach this far past its station toward red (judgment call: red's alert pairs held 24 nm from the station in XO's 2026-10-23 run)
TARCAP_NEAR_STRIKE_NM = 22   # v0.41.181 (XO 2026-10-28): a STRIKE package's TARCAP holds this far from the shooters' middle (was 26 for all); judgment call: it protects the package, it does not hunt red's patrols
TARCAP_FWD_CAS_NM = 10      # v0.41.181: engage reach past the station for a CAS / strike package's TARCAP (20 for SEAD / DEAD, unchanged); judgment call from two CAS runs where the Eagles pushed out into red's scrambles and lost 9-10 to R-27ERs
TARCAP_FWD_STRIKE_NM = 12
TARCAP_NEAR_NM = 18          # v0.41.168 (XO 2026-10-27: 16, the TARCAP dived into red's BARCAP swarm; 26 is a judgment call between the old 16 and the 56 nm that was too far to snipe). v0.41.118: ...then it moves in toward the middle of the shooters' launch points until it is this far from it (judgment call: AIM-54 / AIM-120 reach covers the HARM point from there; still outside the SAM rings and TARCAP_BEHIND_NM from the JSOW point)
ESCORT_BEHIND_NM = 8          # v0.41.42: a package escort in a Standoff DEAD stations itself this far behind the JSOW flight's launch point (judgment call)
TARCAP_PKG_ZONE_NM = 15       # v0.41.185 (XO 2026-10-28: the CAS / strike TARCAP goes maverick): the circle of a CAS or strike TARCAP is this big and does not reach out to the BARCAP circle (judgment call)
TARCAP_COVER_MAX_NM = 35      # v0.41.42: the TARCAP / escort circle round the shooters' launch points is at most this big (judgment call; was 20 nm wanted, moved off every SAM)
TARCAP_BARCAP_OVERLAP_NM = 4   # v0.41.138: the TARCAP circle reaches this far (less 2 nm of margin) inside the nearest BARCAP circle, so there is no unguarded strip between them (judgment call: a few miles so a bandit crossing from one to the other is always inside one)
COVER_ZONE_NM = 20            # v0.41.0: a TARCAP / escort engages inside this circle round the package's launch points (where the shooters are)
SLAM_AIMS = 2                # v0.41.309: aim points (buildings) of a SLAM-ER launch, a missile each per jet's two (the Standoff Strike kit carries two AGM-84H a jet)
SLAM_ATTACK_S = 240           # the SLAM-ER launch window after the launch point's ETA, then return fire. Was 90 (v0.41.309; XO's run fired its four in 20 s). v0.41.362: 240 (judgment call): XO's run 2026-11-10 22-33-46 reached the SLAM point about 95 s after the window closed, the marshal exit costing about 55 s; 240 is that plus margin. The JSOW window is 240 too
LATE_ATTACK_S = 600           # v0.41.16: an AI strike flight drops only within this of its TOT
RAMP_CLUSTER_M = 250          # v0.41.328: the parking slots this close to the ramp middle give the pass its heading (judgment call: the parked jets stood in about 300 m)
RAMP_AXIS_MIN_M = 150          # v0.41.326: a ramp line shorter than this is bombed from any heading (judgment call)
CV_PATTERN_NM = 6             # v0.41.72: an AI carrier flight within this of the boat...
CV_PATTERN_S = 90             # ...for this long (about two laps of the pattern) is recovered
CV_RECOVER_NM = 10            # v0.41.17: AI carrier flights (and your wingmen) are recovered this far from the boat instead of joining the deck queue
CV_RCV_NM = 30            # v0.41.127 (XO 2026-10-23: F-14s flew 65 nm home at 2,000 ft): a flight going home to the boat keeps its height to a point this far out, then descends (judgment call)
CV_RCV_FT = 10000         # ...and crosses that point at this height (the Marshal stack is lower; judgment call)
RCV_NM = 8                    # v0.41.10: an AI flight's recovery entry point, this far from its field...
HOME_SAM_VARIANTS = ("SA-15", "SA-8", "SA-19", "AAA", "MANPAD")     # S33 (XO 2026-11-11): the short-range air defence an AI fighter's way home stays high over
HOME_RING_MARGIN_NM = 3.0     # ...its ring (threatmap.RANGE_NM) plus this counts as touching the leg (judgment call, the same size as the CAS DEAD rule)
HOME_FLOOR_MARGIN_FT = 4000   # ...and the leg stays this far above the highest ceiling (profiles.ENVELOPE) among the rings it crosses (judgment call: Tor 20,000 -> 24,000 ft)
HOME_FLOOR_NAME = "HFLR"      # ...at one point named so (no other code looks for it)
RCV_SPREAD = (0, 30, -30, 60, -60)    # ...on its own bearing (degrees off the way it comes home), by stack slot
SA10_REACH_NM = 31            # v0.41.14: the farthest an SA-10 fired at our jets in the runs (54-57 km)
SWEEP_AFTER_TOT_S = 120       # v0.41.13: a sweep holds until 2 min after the first package it covers is over the target
HOMEWARD_ENGAGE_NM = 20       # v0.41.5: after its hold a TARCAP / escort / sweep still engages air within this of itself on the way home
from .packages import LONG_RANGE_A2A     # the long-range shooters; F-16 and F/A-18 are secondary air-to-air
RAID_RUSH_KTS = 500         # v0.41.256: the raid SEAD flies at least this fast to its HARM point (judgment call: a loaded Hornet's cruise-to-dash; XO: as fast as they can)
RAID_F14_HOLD_FT = 30000    # v0.41.256 (XO 2026-11-03): the F-14 raid CAP holds high, where a jet burns least and a Phoenix leaves with the most energy (judgment call; fuel flow not checked)
RAID_F14_DASH_FT = 35000    # ...and crosses high
RAID_F14_HOLD_KTS = 300     # ...at an endurance speed while it waits
RAID_F14_DASH_KTS = 500     # ...and dashes at this speed once the gate opens (judgment call; v0.41.286 XO 2026-11-04: was 650, "shouldn't be gas-guzzling in afterburners all the way", and the intercept point is now short of the mountains, so the lane is shorter)
RAID_OTHER_DASH_KTS = 500   # v0.41.286: was 600 (see RAID_F14_DASH_KTS). v0.41.265: the Hornets and Eagles that dash with them (judgment call; the F-14 is the fastest of the three at altitude)
RAID_SEAD_LEAD_S = 240      # v0.41.256: the raid SEAD's HARMs land this long before the interceptors are due on station (judgment call; v0.41.255 had 180)
RAID_SEAD_DONE_S = 150      # v0.41.283 (XO 2026-11-04): when the player is not the raid SEAD flyer the SEAD is already done: its HARMs landed this long before the mission starts (judgment call)
RAID_SCRIPT_KILL = 0.5      # (OLD SAVES ONLY since v0.41.357: a carrier raid with a prep record, `extra["prep_rec"]`, has no scripted result, see `_raid_prep_standing`) ...and this share of the live site's launchers and vehicles is destroyed at second 2, with all its tracking radars (a scripted result; judgment call)
RAID_PLAYER_WAIT_S = 300    # v0.41.284 (XO 2026-11-04: "it's unrealistic if red will wait forever"): when the player flies the raid SEAD, red's raiders spawn this long after his HARMs, the radars dead or not (judgment call; "5 minutes?")
RAID_DASH_WAIT_S = 180      # v0.41.256: the interceptors cross this long after the HARMs if the tracking radars are not all dead by then (judgment call)
RAID_HEAD_S = 300         # v0.41.278 (XO 2026-11-04: "intelligence is intelligence. Must've put two and two together"): the AI interceptors of the fleet-defence raid spawn this far along their route, as if they had launched this long before the mission began. A player's flight is not moved. Judgment call: ~50 nm at the dash speed; 0 = they start at the field
RAID_SAM_RESERVE = 50    # v0.41.291 (XO 2026-11-04: spawn every red SAM, "trim the furthest when over budget"): the carrier-defence setpiece's extra SAM sites stop this many units short of the limit, so the relief sorties, standby pairs and wrecks built after them still fit. Judgment call from probes: the old build spent 36 to 50 units after its SAMs.
RAID_F14_HOLD = False     # v0.41.276 (XO 2026-11-04: "the interceptors should just fly fast and bend away from SAMs"): False = the fleet-defence F-14s and F-15s have no HOLD and no gate: they leave at the start, fly the SAM-bending lane at the dash speed and wait on the intercept point. True = the v0.41.256 hold-then-dash with the SEAD gate.
STAGGER = {Role.SWEEP: -90, Role.ESCORT: -90, Role.SEAD: -60, Role.TARCAP: -TARCAP_LEAD_S}      # seconds relative to the strikers' push (BMS-style)


SEAD_ENGAGE_NM = 30            # a SEAD flight, or a fighter held at its stand-off point, engages only what is within this of that point
DEAD_SEAD_LEAD_S = 300         # in a DEAD package the SEAD flight is on the site this long before the DEAD flight
JSOW_TRAIL_S = -30             # v0.41.195 (XO 2026-10-29: SEAD and DEAD should fire as one salvo, JSOWs a few seconds after the HARMs; the HARMs, being faster, draw the SAMs' attention first): was 120. In his run the JSOWs began launching 150-200 s after the HARMs (HARMs 545-682 s, JSOWs 752-904 s), so the push moves 150 s earlier (negative = ahead of the SEAD push). A judgment call from one run; retune after the next. v0.41.11 (below) is why it was 120: a Standoff DEAD's JSOW flight pushes this long after its HARM shooters, so it reaches SA-10 range once the
                               # HARMs have landed (about 2 min of flight). Was 0 (together): the v0.41.10 run, the SA-10 fired at the JSOW jets while the HARMs were in the air
                               # (on two axes), the HARMs go first, the JSOWs land a few minutes later on a radar that is dead or has shut down.
                               # v0.39.19 had the JSOW flight 160 s ahead so the WEAPONS would land together: it went in alone and died (v0.39.19 run, Viper 2).
SEAD_LEAD_S = 90               # S38 (XO run 2026-11-11 16-53: the SEAD came 5.4 min ahead of the strikers, no radar was up, it left, SA-11 + Tor killed the strikers): in a STRIKE / CAS package the SEAD's HARM point is timed to this long before the strikers' time over target, not to the push. Judgment call: the HARMs go as the strikers commit and the SAMs come up on their approach (JP 3-01 / JP 3-09: SEAD works the window the package is in; no public figure for the lead)
SEAD_WINDOW_S = 120            # S38: ...and the SEAD stays on station (orbit at the HARM point) until the last striker's time over target plus this, its ARM tasks live for the whole window. Judgment call
SEAD_HOLD_KTS = 350            # S38: the SEAD's orbit speed at the HARM point (the attack speed would make the circle huge). Judgment call
A2G_ROLES = (Role.STRIKE, Role.SEAD, Role.CAS)
NATIVE_ECM = {"F-15C"}         # jets with a jammer that switch DCS's ECM on over the attack leg (the ECM script counts the F-15C too since v0.40.9)
AAM_WEAPONS = 264241152       # DCS weapon flags: air-to-air missiles (a Fighter Sweep's RTB when out of ammo)
# DCS weapon flags for "RTB when out of ammo": bombs (guided, iron, cluster), air-to-ground missiles (HARM, JSOW, Maverick) and rockets.
# Not guns and not air-to-air missiles, so a flight goes home once its air-to-ground load is gone.
A2G_WEAPONS = 14 | 240 | 768 | 4161536 | 30720
# Air-to-ground jets whose loadouts carry radar missiles (AIM-120, AIM-54; checked in loadouts.py): after the attack they may shoot back.
SHOOTS_BACK = {"F-16C", "FA-18C", "F-14BU", "F-15E"}
RELIEF_BACK_NM = 12            # v0.41.78: a relief sortie appears this far behind its station (toward its base) and flies up to it (judgment call)
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
from .routes import cap2_point, jsow_launch_xy, SLAM_LAUNCH_NM, JSOW_KEEP_HIGH_NM, SA10_AVOID_NM, SA10_STATION_NM, AVOID_NM, avoid_circles, AGM88_LAUNCH_NM, OBJECTIVE_ACTIONS, NM, FT, Wpt, assign_times, bearing, dist, hold_leave_s, in_progress, leg_seconds, make_geometry, objective_wp, offset, plan_route, terrain_clear, home_leg_ft
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
    hot_ramp_scrambles: bool = False    # v0.41.80: alert / scramble pairs at land fields start hot on the ramp (see _alert_group)
    hot_runway_starts: bool = False     # v0.41.96: AI package flights from land fields other than yours start on the runway (see _hot_slot)
    hot_runway_own_field: bool = False  # v0.41.99: with hot_runway_starts: also flights at the player's own field (see _hot_slot)
    ai_unlimited_fuel: bool = True      # Retribution-style: ON until the push, OFF for the combat leg, ON again from egress
    enemy_unlimited_fuel: bool = False
    ai_despawn_on_land: bool = True
    ai_skill_red: str = "level"            # v0.41.70: see difficulty.ai_skill
    ai_skill_blue: str = "level"
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
    ils_dummy: str = "on"               # v0.41.336, S32: "off" | "on" (see settings.ils_dummy and ILS_DUMMY below); "on" also means the real regional wind
    reactive: bool = True               # extra enemy fighters / blue alert pairs that launch during the sortie (reactive.py)
    ai_land_carrier: str = "always"     # v0.41.18: AI recovery short of a carrier: always | home (your deck only) | never
    ai_land_field: str = "never"        # v0.41.18: the same for airfields
    splash_damage: bool = True          # blasts on ground units near an air-to-ground weapon's impact (the hook)
    awacs_tuned: bool = True            # v0.41.215: the AWACS calls need a tuned radio (the cockpit-parameter triggers, tune_triggers)
    damage_calls: bool = True           # v0.41.215: damage / mayday calls from the other aircraft
    ecm_status: bool = True             # v0.41.213: the on-screen ECM messages (F-16C lamp, FC3 F10 calls); only with ecm_script
    ecm_script: bool = False            # SQE's own jamming model in the mission hook (ecm.py). Off: DCS's own ECM, the AI decides when it is locked
    carcasses: bool = True              # dead wrecks at damaged / destroyed ground sites (see carcass.py)
    carcass_weight: float = 0.25        # how much of a live unit one wreck or one live static building counts toward the unit limit (v0.41.221: the buildings too; the name stays until refactor week)
    carcass_range_nm: int = 40          # only sites this close to the route get wrecks
    full_map: bool = False              # stress test: build everything that exists (see _spawn_everything); the unit limit is off
    max_units: int = 250                # the unit limit of the BASE mission (wrecks are trimmed, furthest first, to fit under it); merged packages' units do not count (v0.41.104)
    unit_ceiling: int = 0               # most units in total, merged packages included (0 = sqe/data/limits.json, 500); a runaway guard
    merge_radius_nm: int = 15           # v0.41.209 (XO): also the radius inside which every supply site (fuel farm, depot, both sides) is built round the target: the performance knob
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
    AssetKind.FUEL:  [("ZSU_23_4_Shilka", 1)],      # v0.41.192: the buildings are statics (raid_spawns.SUPPLY_BUILDINGS); only the guard is a vehicle group
    AssetKind.DEPOT: [("ZSU_23_4_Shilka", 2)],
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


def home_floor_exit(path, rings):
    """S33: where an AI fighter's way home leaves the last short-range air-defence ring. `path` = [(x, y), ...] (route end, SCRUB, RCV), `rings` = [(x, y, r_m), ...].
    -> (distance along the path in m, the leg index it falls on, the point (x, y), the indexes of the rings the path touches) or None when no ring touches the path.
    A ring that contains the path's end counts as exiting at the end."""
    best, hit = None, []
    cum = 0.0
    segs = []
    for i in range(len(path) - 1):
        (ax, ay), (bx, by) = path[i], path[i + 1]
        L = math.hypot(bx - ax, by - ay)
        segs.append((cum, L, ax, ay, bx, by))
        cum += L
    for n, (cx, cy, r) in enumerate(rings):
        last = None
        for si, (c0, L, ax, ay, bx, by) in enumerate(segs):
            if L <= 0:
                continue
            dx, dy = (bx - ax) / L, (by - ay) / L
            fx, fy = ax - cx, ay - cy
            b = fx * dx + fy * dy
            disc = b * b - (fx * fx + fy * fy - r * r)
            if disc < 0:
                continue
            u1, u2 = -b - math.sqrt(disc), -b + math.sqrt(disc)
            if u2 < 0 or u1 > L:
                continue
            last = (c0 + min(u2, L), si, ax + dx * min(u2, L), ay + dy * min(u2, L))
        if last is not None:
            hit.append(n)
            if best is None or last[0] > best[0]:
                best = last
    return None if best is None else (best[0], best[1], (best[2], best[3]), hit)


class MissionBuilder(StrikeTasks, FighterStations, SupportCaps, RedAirPicture, RaidSpawns):
    def __init__(self, state: CampaignState, d: Difficulty, opts: MissionOptions | None = None,
                 loadouts: LoadoutLibrary | None = None, rng: random.Random | None = None):
        self.state, self.d = state, d
        self.o = opts or MissionOptions()
        self.lo = loadouts or LoadoutLibrary()
        self.rng = rng or random.Random()
        self._runway_busy = set()                                      # bases whose runway / catapult already holds a group at mission start
        self._rwyq, self._flag_n, self._prwy, self._alerts = [], 9000, "", []
        self._raid_n = {"bu": 0, "eu": 0, "bg": 0, "sw": 0, "es": 0}            # S47: raid unit numbers (bomber, escort) and group numbers (bomber, sweep, escort), one count per mission so folded raids never repeat a name
        self._ecm_player = ""                           # v0.41.210: how the hook learns the player's jammer: "live" (F-16C lamp via Export.lua), "f10" (FC3 jet), "" (old attack-leg window)
        self._raid_xy = []                              # v0.41.220: where each raid scramble's raiders are going (the supply circle runs round these too)
        self._bld_xy = {}                   # v0.41.309: supply site id -> where its buildings stand (`_place_buildings`), the Standoff Strike aims at them
        self._ramp_tasks = []               # v0.41.329: the counter-air Bombing tasks made before the jets spawn; `_retarget_ramp_tasks` re-aims them
        self._ramp_pts = []                 # v0.41.313: the parked static jets' positions of this mission (counter-air strike)
        self._supply_built = set()                      # v0.41.209: blue supply sites already put on the map this mission (a raid target is one)
        self._rwy_rel, self._hot = {}, None                            # v0.41.96: release times already given per runway; the hot-runway slot of the flight being built
        self._launch_pts = {}                                          # package id -> [(x, y)] where its HARM / JSOW / strike flights launch (the cover zone)             # alert groups waiting for a runway (the hook lines them up), trigger flags, your runway
        self._air_spawns = []                                          # [(x, y, alt_m, t)]: where and when each airborne flight appears, so no two appear on top of each other

    # =====================================================================================================
    def build(self, package: Package, out_path, extras: list | tuple = (), ruins: list | tuple = (), preroll: dict | None = None) -> BuildResult:
        """extras: other packages (AI only) folded into this mission: same area, starting at or after yours. They share the ground world,
        the support aircraft and the enemy air picture, and fly live with their own push, TOT and stagger."""
        o = self.o
        tm.set_ramp_lead(bool(getattr(o, "hot_ramp_scrambles", False)))          # v0.41.92: bigger scramble circles when the pairs taxi from the ramp
        st = self.state = copy.copy(self.state)                       # a private view: the carrier may be moved back for this sortie only
        st.bases = {k: copy.copy(v) for k, v in st.bases.items()}
        pf = package.player_flight
        if pf is None:
            raise ValueError("choose your flight first")
        warns: list = []
        self.warns = warns
        self._anchor_id = package.id
        self._fcalls, self._ulabels, self._pkg_who = [], {}, {}
        self._support_lbl = {}                                          # v0.41.215: tanker / AWACS unit name -> its label, for the damage calls
        self._gates = []                                                # DEAD flights that turn back when the site's radars are still up
        self._route_end = {}                                            # v0.41.223: group name -> where its route ended before the SCRUB point was added (the home leg is built from there)
        self._cas_floors = {}                                           # S31a: package id -> the AI CAS attack floor in ft (0 = none)
        self._scrub = []                                                # v0.41.223: every package flight for the hook's package scrub (group, unit names, kind, SCRUB point)
        self._sead_grps = {}                                            # site id -> the SEAD flights' group names (all merged packages); the gate aborts when they are all down
        self._blind_site = set()
        extras = [x for x in extras if any(not f.tag for f in x.flights)]
        self._extras = list(extras)
        ruins = [x for x in ruins if any(not f.tag for f in x.flights)]
        self._preroll, self._ruin_sites = dict(preroll or {}), []
        self._detect_full = detection.any_full(package, extras)           # v0.41.346 (Phase 7a): red scrambles for this mission only if it saw ANY package in it (the stored verdict, `detection.cast`)
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
        self.wx = weather.for_package(st, o.weather_mode, theatres.active(), package.start, o.ils_dummy in ILS_DUMMY_MODES)
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
        # v0.41.76: no fixed keep-outs round our marshal point, fields or carrier any more (v0.41.10: 45 / 130 nm): red's patrol stations are BARCAP
        # stations (barcap.py), clear of blue's SAM rings and the ships' reach (CAP_FLEET_KEEPOUT_NM, applied in `_plan_cap_stations`).
        keep0 = []
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
        self._support_units = {}                       # v0.41.87: support asset key -> its aircraft's unit name in this mission
        self.base_ad = {}                              # v0.41.84: base id -> {"pat": group, "hawk": group} (blue field air defence, the targets of a red SEAD pair)

        # ---- bases, base defenses, carrier + escorts --------------------------------------------------------
        self.ship, self.apt = {}, {}
        self._main_base = pbase.id                    # your home field (AI landing setting); since v0.41.30 every field gets the same air defence
        for bs in st.bases.values():
            if bs.kind == BaseKind.AIRFIELD:
                self.t.airports[bs.airport].set_blue()
        for a in st.assets.values():
            if a.kind == AssetKind.AIRFIELD and a.airport:
                self.t.airports[a.airport].set_red()
        # v0.41.282 (XO 2026-11-04): every red-held field in the theatre data is red in every mission, also the ones this level's roster left out (they stayed neutral, and
        # long-legged jets that RTB to the nearest field landed on them)
        blue_aps_ = {bs.airport for bs in st.bases.values() if bs.kind == BaseKind.AIRFIELD}      # (a field we took is a blue base: it stays blue)
        for f_ in theatres.active().get("red_fields", []):
            if f_.get("airport") in self.t.airports and f_["airport"] not in blue_aps_:
                self.t.airports[f_["airport"]].set_red()
        # v0.41.286 (XO 2026-11-04): and the fields beyond the mountains that are not part of the war (Mineralnye Vody and the Krasnodar / Anapa / Novorossiysk fields): a jet
        # that runs dry or is chased north landed on a neutral one. Mission-only list, no campaign asset
        for ap_ in theatres.active().get("red_extra_airports", []):
            if ap_ in self.t.airports:
                self.t.airports[ap_].set_red()
        # v0.41.28: a raid scramble also builds the field the raid is coming for (the XO's Kobuleti run: the raided field had no defences
        # because nothing launched from it)
        raided_ = [package.objective.target_id] if (package.objective.type == ObjectiveType.FLEET_DEFENSE and package.objective.target_id in st.bases) else []
        for bid in dict.fromkeys([f.base_id for f in package.flights] + raided_ + [f.base_id for x in list(extras) + list(ruins) for f in x.flights if not f.tag]):
            self._place_base(st.bases[bid], tx, ty)
        # v0.41.220 (XO 2026-10-31): a raid scramble also builds the neighbouring fields whose Patriot / HAWK cover the raid's target (the war sim and the raid gate already
        # count them; before, only the raided field and the fields with flights were built, so the target stood alone)
        self._raid_xy = self._raid_dests([package] + list(extras))
        for bid, near_ in self._raid_cover_bases([package] + list(extras)).items():
            if bid not in self.apt and bid in st.bases:
                self._place_base(st.bases[bid], tx, ty, near=near_)
        for cvb_ in st.bases.values():                  # v0.41.209 (XO 2026-10-30): the carrier group is always in the mission (4 ships, about 100 nm out); it was built only when a flight used the boat
            if cvb_.kind == BaseKind.CARRIER and cvb_.id not in self.ship:
                self._place_base(cvb_, tx, ty)
        self._spawn_ils_dummies()                       # v0.41.336 (XO 2026-11-09): one dummy per blue ILS field keeps the ILS runway active whatever the wind
        self._crater_blasts = self._crater_points()     # v0.41.336: closed fields get a few scripted blasts on the runway (the hook fires them)
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
        for key_, nm_ in self._support_units.items():                          # v0.41.87: a support aircraft shot down comes off its asset (debrief)
            manifest.add("support", key_, [nm_], label=nm_.rsplit(" ", 1)[0])

        # ---- timeline: YOUR times. Roles are staggered around the strikers' push (sweep, SEAD, escorts go first) ---------
        launch_s = float(o.launch_offset_s)
        skip1 = {tgt_asset.id} if (tgt_asset is not None and package.objective.type == ObjectiveType.DEAD) else ()
        geom.tier = self._pick_tier(geom, pf.role, pspec.profile, tx, ty, skip1)
        self._flight_plans(geom, package, tx, ty, skip1)
        pkg_p, geom_p, psite = package, geom, None           # v0.41.284: the player flying the raid SEAD gets the SEAD job on a raid site (his own stand-in package and geometry), like the AI SEAD flights
        if self._raid_player_sead(package):
            psite = self._raid_player_site(package, geom, pf)
            if psite is not None:
                pkg_p, geom_p = self._raid_sead_geom(package, pf, psite)
        pw = plan_route(pf.role, (pbase.x, pbase.y), geom_p, pspec.profile, is_player=True, tanker_xy=None, jsow=getattr(pf, "kit", "") == "JSOW",
                        jsow_side=self._jsow_side(pkg_p, geom_p), keep_out=self._umbrella_keep(pkg_p), agm88_deg=self._agm88_deg(pkg_p, geom_p))
        if package.objective.type == ObjectiveType.FLEET_DEFENSE and pf.role == Role.CAP and (package.extra or {}).get("setpiece") and not pf.tag:
            self._raid_cap_station(package, geom, pw)               # v0.41.256: your racetrack is walked back clear of the SAMs like your wingmen's, and the card shows it
        self._add_cap2(pkg_p, pw, pspec, geom_p)               # Phase 8: the card shows CAP1 and CAP2, the same points the flight is built with
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
        push_of = lambda f: self._push_adj.get(id(f), P0 + (0 if f.tag else stagger(package, f.role)))
        assign_times(pw, dep_s, player_push)
        tgt = objective_wp(pw) or pw[-1]
        ptot = tgt.eta_s + RAID_SEAD_LEAD_S if psite is not None else tgt.eta_s          # v0.41.284: the time the raid's other flights work to: the interceptors are due on station RAID_SEAD_LEAD_S after your HARMs
        egr = next((w for w in pw if w.name == "EGR"), pw[-1])
        rtb_s = egr.eta_s + leg_seconds(egr, Wpt("RTB", pbase.x, pbase.y, 0, 300))
        self._p_times = (float(launch_s), float(rtb_s))                 # v0.41.97: your takeoff and landing, for the hot starts at your own field
        tl = {"launch": clock(launch_s), "marshal": clock(mshl.eta_s), "push": clock(player_push), "tot": clock(tgt.eta_s),
              "egress": clock(egr.eta_s), "rtb": clock(rtb_s), "push_s": player_push, "tot_s": tgt.eta_s, "rtb_s": rtb_s}

        # ---- friendly flights --------------------------------------------------------------------------------------------
        despawn, pkg_table = [], []
        self._sup_cts = []                                                   # HAVCAP / base CAP orbit tasks: their stop time is extended once the merged packages are known
        self._cover = []                                                     # v0.41.79: [{g, n, bf, rf, u}] the CAP pairs the hook watches (debrief.py COVER)
        self._relief_src = {}                                                # v0.41.78: callsign -> what _spawn_flight needs to build that support CAP's relief sorties
        self._relief_names = []                                              # relief flights built so far (their callsigns are taken)
        self._ct_flight = {}                                                 # id(orbit task) -> callsign of the support CAP it belongs to
        self._striker_egr = []                                               # v0.41.40: [((x, y), egress time)] of this mission's strikers
        self._striker_tgt = {}                                               # S38: package id -> its STRIKE / CAS flights' time over target, for the SEAD's window
        self._push_adj = {}                                                  # S38: id(flight) -> the push time an AI SEAD actually uses (timed to the strikers, not the push)
        self._holds = []                                                     # v0.41.10: TARCAP / escort holds, extended to the last package over their target area
        self._snipe_at = {}                                                  # v0.41.10: id(group) -> the station waypoint where max-range shots begin
        self._callins = []
        self._callin_lua = False                                           # v0.41.112: SQE_CALLIN is defined in the mission (red's wiring or blue's)
        self._hold_drawn = {}                                                # v0.41.343 (Phase 6a): red squadron id -> hold jets this build's scrambles drew (reserve.pick_red_hold)
        self._hot_calls, self._hot_flag = [], 0                              # v0.41.111: the BASECAP call-in (red_air_picture.py)
        self._recov = []                                                     # v0.41.25: the recovery net (see _recov_net)                                                   # v0.41.10: red patrols called in to the SAM site they guard
        self._launch_pts[package.id] = self._launch_points(package, geom)    # v0.41.42: known before any flight is built (an escort / TARCAP may be built first)
        self._barcap_zones = self._barcap_circles(package, geom)             # v0.41.138: the BARCAP circles a TARCAP's circle must meet (whatever order the flights are built in)
        striker_tots = []                                                    # v0.41.38: each ground-attack flight's own target time (strike / SEAD / CAS), for the TARCAP hold
        if package.objective.type == ObjectiveType.FLEET_DEFENSE and package.objective.target_id in st.bases:
            if not self._raid_edge_on(package):                              # (v0.41.282: the edge-spawn setpiece has no push time: it is timed to blue instead)
                self._raid_clock_prep(package, tx, ty, tgt.eta_s)             # v0.41.280: the raid's push time, known before the interceptors are built
            self._raid_sead_prep(package, geom, ptot, manifest)          # v0.41.256: the SEAD's site and the interceptors' DASH flag exist before the CAP flights are built
        for idx, f in enumerate(package.flights):
            if self._raid_sead(package, f):                  # v0.41.255: its own SEAD job on the SAMs over the raid's launch point
                g, tot_f = self._spawn_raid_sead(package, f, plan, geom, idx, ptot, manifest, despawn)
                if g is None:
                    continue
                pkg_table.append({"callsign": f.callsign, "role": "SEAD", "push": "-", "tot": clock(tot_f) if tot_f else "-", "you": False})
                continue
            g, tot_f = self._spawn_flight((pkg_p if f.is_player else package), f, plan, (geom_p if f.is_player else geom), tanker_xy, hav_xy, push_of(f), (tgt.eta_s if f.is_player else ptot), rtb_s, idx, manifest, despawn)
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
        keep = [(p[0], p[1], 100) for p in (hav_xy,) if p is not None]          # v0.41.76: only the AWACS anchor / HAVCAP is kept clear of red's patrols (the tanker picks its own spot clear of them, threatmap.tanker_spot)
        keep += self._fleet_keepout()
        self._spawn_air_picture(air_pkg, tx, ty, ptot, geom, manifest, keep)
        self._spawn_cas_support(package, plan, geom, manifest)
        self._agm88_refs = []                                           # [(x, y, t)]: SEAD waves timed in this mission; merged SEAD packages on the same ground match them
        if package.objective.type == ObjectiveType.DEAD and package.objective.aim in SEAD_AIMS and package.objective.target_id:
            hs_ = self._agm88_time(package, geom, pbase, P0)
            if hs_ is not None:
                t_ = st.assets[package.objective.target_id]
                self._agm88_refs.append((t_.x, t_.y, hs_))
        merged = self._add_merged(package, extras, P0, manifest, despawn, atc, div_mhz, div.name, clock, ruins)
        # HAVCAP and base CAP guard the tanker, AWACS and home field: they stay until the last flight of ANY package in this mission is home
        # (they used to leave 40 min after your TOT, so later merged packages flew with the tanker and AWACS unguarded)
        last_home = max([m_["rtb_s"] for m_ in merged if not m_.get("struck")] + [rtb_s]) + 300
        for ct_ in self._sup_cts:
            src_ = self._relief_src.get(self._ct_flight.get(id(ct_)))
            if src_ is None:
                if last_home > ct_.params.get("stopCondition", {}).get("time", 0):
                    ct_.stop_after_time(int(last_home))
                continue
            full_ = int(max(src_["full"], last_home))
            if full_ <= src_["end"]:                                         # its first sortie covers the whole mission
                ct_.stop_after_time(full_)
            else:
                self._spawn_reliefs(src_, full_, manifest, despawn)          # v0.41.78: the rest of the time is flown by relief sorties
            self._spawn_replacement(src_, min(full_, src_["end"]), full_, manifest, despawn)         # v0.41.79: one standby pair per support CAP
        # v0.41.38 (XO 2026-10-20): a TARCAP / escort stays until the LAST ground-attack flight of its own package is off target (+ the usual after-time),
        # not just until its own station time (when the player flew the TARCAP, tgt was the TARCAP's own station: it left 7.5 min after arriving)
        own_ = [((tx, ty), max(striker_tots))] if striker_tots else []
        self._last_striker_s = max(striker_tots) if striker_tots else None
        self._extend_holds([((tx, ty), ptot)] + own_ + [(m_["txy"], m_["tot_s"]) for m_ in merged if not m_.get("struck") and m_.get("txy")],
                           egr_events=self._striker_egr)
        manifest.cur_pkg = ""
        self._intel = ([geom.tier.reason] if geom.tier.reason else []) + ([geom.cas_floor[1]] if geom.cas_floor else []) + list(self._red_intel)
        self._spawn_supply_in_radius(package, tx, ty, manifest, only_raid=True, max_units=RAID_SUPPLY_UNITS)       # v0.41.220: what a raid scramble is about is built before the raiders and the alert pairs use the unit limit
        self._spawn_reactive(package, extras, tx, ty, ptot, geom, manifest, despawn)
        self._spawn_parked_jets(package, manifest)
        self._dry_pass()
        self._spawn_supply_in_radius(package, tx, ty, manifest)
        self._place_carcasses()
        manifest.merged = [{k: v for k, v in m_.items() if k in ("id", "number", "objective", "type", "tot_s", "rtb_s", "unseen")} for m_ in merged if not m_.get("struck")]
        bx, by = geom.push
        m.coalition["blue"].bullseye = {"x": bx, "y": by}

        # ---- waypoint table as the jet numbers it ------------------------------------------------------------------------------
        to_note = self._short(pbase.name)
        if pbase.kind == BaseKind.CARRIER:                       # Case III wording: the leg to DEP is the departure radial
            to_note += f", depart radial {int(bearing(pbase.x, pbase.y, *geom_p.dep)):03d}"
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
                            "note": r[6] if (r[0] in ("TGT", "TKR", "RTB", "DIVERT", "TAKEOFF") or (r[0] == "CAP1" and any(w_.orbit for w_ in pw))) else ""})
            if r[0] not in ("TAKEOFF", "DIVERT", "TKR", "BULLS"):
                hook_wps.append((pspec.wp_label(i), r[0], r[1], r[2]))

        # ---- codes, fuel, text, hook, kneeboard -----------------------------------------------------------------------------
        mode3 = self._mode3(package, pf)
        laser = self._laser(package, pf)
        x = {"date": date_str, "mode3": mode3, "laser": laser, "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}",
             "bullseye": latlon(bx, by, self.t), "divert": div.name, "weather": weather.describe(self.wx), "weather_short": weather.metar(self.wx), "wx_notes": self.wx_notes,
             "link16": any(r["stn"] != "-" for r in whois), "pkg_table": pkg_table,
             "n_def": air_pkg.n_def, "intel": self._intel, "ecm_player": self._ecm_player, "qra": [f"Scramble {n_} ({a_['ty']}, {a_['b']})" for n_, a_ in enumerate(self._alerts, 1)], "merged_nums": [m_["number"] for m_ in merged if not m_.get("struck") and not m_.get("unseen")]}      # v0.41.351: a raid blue did not detect is never named
        _ta = st.assets.get(package.objective.target_id)       # v0.41.175: a target line for the briefing: where it is, from your home field, what is there
        if package.objective.type in (ObjectiveType.STRIKE, ObjectiveType.CAS, ObjectiveType.DEAD, ObjectiveType.COUNTER_AIR):
            x["target_line"] = (f"Target position {latlon(tx, ty, self.t)}, bearing {int(bearing(pbase.x, pbase.y, tx, ty)):03d} degrees, "
                                f"{dist(pbase.x, pbase.y, tx, ty) / NM:.0f} nm from {pbase.name}."
                                + (f" {_ta.name} stands at {_ta.health:.0%} strength." if _ta is not None else "")
                                + self._ramp_line(package, manifest))
        tune_flags, tune_mhz = [], 0.0
        if o.awacs_tuned and not o.player_is_ai and any(s.slot == "AWACS" for s in package.support):
            tune_mhz = float(plan.freq("AWACS"))
            tune_flags = self._tune_triggers(pf.aircraft, tune_mhz)           # v0.41.215: [] for a jet whose radio cannot be read: always counts as tuned
        if tune_flags:
            x["tune_mhz"] = tune_mhz
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
                         enemy_air=[u for g_ in manifest.groups if g_["kind"] == "enemy_air" for u in g_["units"]],      # v0.41.324: the parked jets are real aircraft now: kills on them are attributed like any red jet
                         sites=self._hook_sites(manifest), ruins=self._ruin_sites, gates=self._gates, ai_test=bool(o.player_is_ai), gate_km=DEAD_GATE_KM, jams=(self._jams if o.ecm_script else {}), jamw=(self._jamw if o.ecm_script else {}),
                         watch=[g_.name for f_, g_ in self.flight_groups if not f_.tag and (not f_.is_player or o.player_is_ai)],      # v0.41.317: the all-AI test flight is watched too (AWACS said "no further tasking" while it was still inbound)
                        
                         done_after=max([float(ptot)] + [float(m_["tot_s"]) for m_ in (merged or [])]), awacs=awl.upper(), splash=bool(o.splash_damage),
                         rwyq=self._rwyq, prwy=self._prwy, alerts=self._alerts, cover=self._cover, ecm_player=self._ecm_player, ecm_msg=bool(o.ecm_status),
                         scrub=self._scrub, tune_flags=tune_flags, tune_mhz=tune_mhz, awacs_unit=f"{awl} 1-1" if any(s.slot == "AWACS" for s in package.support) else "",
                         dmg=({**self._ulabels, **{k: "*" + v for k, v in self._support_lbl.items()}} if o.damage_calls else {}), dmg_on=bool(o.damage_calls),
                         cfg={"splash_damage": bool(o.splash_damage), "ecm_script": bool(o.ecm_script), "version": __import__("sqe").__version__,
                              # v0.41.17: your wingmen leave at the boat (10 nm) once you are back, after your TOT
                              "cvrec": self._wing_recovery(pbase, ptot), "recov": list(self._recov),
                              "phome": ([self._pt(pbase.x, pbase.y).x, self._pt(pbase.x, pbase.y).y] if pbase.kind == BaseKind.AIRFIELD else None),
                              "rwys": runways.fields_for_hook(st, self.t), "craters": self._crater_blasts})
            tdata = ""
            if pf.role in (Role.STRIKE, Role.SEAD, Role.CAS):
                tdata = f"TARGET  {latlon(tx, ty, self.t)}   ({package.objective.description})"
            ctx = {"date": date_str, "callsign": f"{pf.callsign}-1", "role": task_label(pf, package.objective), "objective": package.objective.description,
                   "comm1": plan.comm1, "comm2": plan.comm2, "fc3": pspec.fc3, "waypoints": kn_rows, "jet": pspec.display,
                   "numbering": (f"{pspec.first_wp_label} for the start point, then 1, 2, 3..." if pspec.first_wp_label else "waypoint 1 = start point"),
                   "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}", "weather": weather.metar(self.wx), "mode3": mode3, "laser": laser,
                   "bullseye": latlon(bx, by, self.t), "whois": whois, "threats": text["threats"], "n_def": air_pkg.n_def, "target_data": tdata,
                   "others": [{"line": f"#{m_['number']} {m_['type']}: {m_['objective']}", "push": m_["push"], "tot": m_["tot"], "rtb": m_["rtb"], "flights": m_["flights"],
                               "status": ("already struck, heading home; its target is in ruins" if m_.get("struck") else "airborne when you start" if m_.get("underway") else "")} for m_ in merged if not m_.get("unseen")],
                   "intel": [l_.replace(" are within reach of the target area and may be sent to reinforce.", " may reinforce.").replace(" are on cockpit alert and may launch to help.", " on alert, may launch.") for l_ in self._intel],
                   "zulu_note": self._zulu_note(), "msa": relief.msa_ft(polyline),
                   "nav": [ln_ for ln_ in (self._nav_row("HOME", pbase), self._nav_row("DIVERT", div)) if ln_]}
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
        self._merged_units = getattr(self, "_merged_units", 0)
        prev_ = self._counts()["units"]
        for k, x in enumerate(list(extras) + [r for r in ruins if r.id not in {e.id for e in extras}]):
            now_ = self._counts()["units"]                  # what the previous package brought (flights, its sites, ruins) is exempt from the base limit
            self._merged_units += now_ - prev_
            prev_ = now_
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
            raid2 = xp.objective.type == ObjectiveType.FLEET_DEFENSE            # v0.41.101: a raid scramble folded in: its target is a field, not an asset
            tgt2 = st.assets.get(xp.objective.target_id) if raid2 else st.assets[xp.objective.target_id]
            if tgt2 is None:
                tgt2 = SimpleNamespace(id=xp.objective.target_id, x=tx2, y=ty2)
            mshl2 = tm.safe_marshal(st, (base2.x, base2.y), bearing(base2.x, base2.y, tx2, ty2), (tx2, ty2))
            geom2 = make_geometry(base2.x, base2.y, tx2, ty2, spec2.profile, mshl2, carrier=base2.kind == BaseKind.CARRIER)
            skip = {tgt2.id} if xp.objective.type == ObjectiveType.DEAD else set()
            if not raid2:
                geom2.egr = (tm.first_safe_egress(st, tx2, ty2, geom2.hdg, skip) or
                             tm.safe_egress(st, tx2, ty2, geom2.hdg, spec2.profile.egress_nm, tm.cluster_ids(tgt2)) or geom2.egr)
            # timeline: this package pushes (start difference) minutes after yours. An EARLIER package has a negative offset: it is already underway when the mission starts.
            P0x = P0 + (hm(xp) - hm(anchor)) * 60.0
            geom2.tier = self._pick_tier(geom2, lead.role, spec2.profile, tx2, ty2, {tgt2.id} if xp.objective.type == ObjectiveType.DEAD else ())
            self._flight_plans(geom2, xp, tx2, ty2, {tgt2.id} if xp.objective.type == ObjectiveType.DEAD else ())
            pw2 = plan_route(lead.role, (base2.x, base2.y), geom2, spec2.profile, is_player=True, tanker_xy=None, jsow=getattr(lead, "kit", "") == "JSOW",
                             keep_out=self._umbrella_keep(xp))
            self._add_cap2(xp, pw2, spec2, geom2)
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
                ref_ = next((r for r in self._agm88_refs if dist(r[0], r[1], tgt2.x, tgt2.y) <= SEAD_WAVE_KM * 1000), None)
                if ref_ is None:
                    self._agm88_refs.append((tgt2.x, tgt2.y, tg2.eta_s))
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
            if not ruined and not raid2:
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
            if raid2:
                self._spawn_raid(xp, tx2, ty2, tg2.eta_s, geom2, manifest)       # the raiders themselves, timed to the scramble's station
            if xp.objective.type == ObjectiveType.CAS and xp.jtac:
                self.armor_id = xp.objective.target_id
                self.armor_center = self.site_pos.get(self.armor_id)
                self.cas_tot = cas_tot
                self._spawn_cas_support(xp, plan2, geom2, manifest)
            tot = max(tots) if tots else tg2.eta_s
            out.append({"id": xp.id, "number": xp.number, "objective": xp.objective.description, "type": xp.objective.type.value, "txy": (tx2, ty2),
                        "start": xp.start, "push": clock(P0x), "tot": clock(tot), "rtb": clock(rtb2), "tot_s": tot, "rtb_s": rtb2, "underway": P0x < 0, "struck": ruined, "unseen": bool((xp.extra or {}).get("unseen_raid")),
                        "flights": ", ".join(f"{f.callsign} {f.count}x{f.aircraft}" for f in xp.flights)})
        self._merged_units += self._counts()["units"] - prev_
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
        # v0.41.80 (XO's experiment, optional setting): at a LAND field the pair may instead wait hot on the ramp, uncontrolled, and taxi when called
        # (AITaskPush StartCommand). Not at your own field (your ramp start is there), and only when the field has parking for the type; otherwise
        # the hidden runway start above.
        if getattr(self.o, "hot_ramp_scrambles", False) and not key and self._prwy != f"{self.usa.name}:{ap.name}":
            g = self._from_airport(side, name, typ, ap, maintask, StartType.Warm, size, quiet=True)
            if g is not None:
                self._note_alert(name, ap.name, typ)
                return g, "ramp"
        g = self.m.flight_group_from_airport(side, name, typ, ap, maintask=maintask, start_type=StartType.Runway, group_size=size)
        g.late_activation = True
        self._note_alert(name, ap.name, typ)
        self._rwyq.append({"g": name, "f": self._flag_n, "b": key or f"{side.name}:{ap.name}"})
        return g, "rwy"

    def _call_by_flag(self, g, how, flag) -> None:
        """v0.41.80: a pair the hook calls by a flag (a relief, a standby): on the hidden runway start the hook puts it on the runway itself; a hot ramp
        pair is started by a trigger when the flag is set."""
        if how != "ramp":
            return
        g.add_trigger_action(task.StartCommand())
        g.uncontrolled = True
        trig = triggers.TriggerOnce(comment=f"start {g.name}")
        trig.add_condition(condition.FlagIsTrue(int(flag)))
        trig.add_action(action.AITaskPush(g.id, 1))
        self.m.triggerrules.triggers.append(trig)

    def _note_alert(self, name, where, typ) -> int:
        """A trigger flag for this alert group (its scramble trigger sets it) and its line in the hook's alert log."""
        self._flag_n += 1
        self._alerts.append({"g": name, "f": self._flag_n, "b": where, "ty": getattr(typ, "id", str(typ)), "sq": ""})
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

    def _units_room(self) -> float:
        """Units still free (v0.41.104): the base mission's limit counts everything except what merged packages brought (self._merged_units), and the
        total never goes past the ceiling in sqe/data/limits.json."""
        from . import limits
        u = self._counts()["units"]
        ceil_ = self.o.unit_ceiling or limits.unit_ceiling()
        if self.o.max_units >= 10 ** 5:                            # full-map stress test: no limit at all
            return float(10 ** 9)
        return min(self.o.max_units - u, ceil_ - u)          # v0.41.131: the whole mission counts again

    def _counts(self) -> dict:
        """Units for the VR budget. A dead static (wreck) and a live static (a supply site's building) are cheap, no AI and they never move, so both count
        `carcass_weight` of a unit (v0.41.221, XO 2026-10-31: the buildings used to count whole units); 'wrecks' and 'statics' are how many there are."""
        g = u = w = n_s = 0
        for coal in self.m.coalition.values():
            for c in coal.countries.values():
                for attr in ("plane_group", "helicopter_group", "vehicle_group", "ship_group", "static_group"):
                    for grp in getattr(c, attr, []):
                        if attr == "static_group":
                            if getattr(grp, "dead", False):
                                w += len(grp.units)
                            else:
                                n_s += len(grp.units); g += 1
                            continue
                        g += 1; u += len(grp.units)
        return {"groups": g, "units": u + int(math.ceil((w + n_s) * self.o.carcass_weight)), "wrecks": w, "statics": n_s}

    def _spawn_supply_in_radius(self, package, tx, ty, manifest, only_raid: bool = False, max_units: int | None = None) -> None:
        """v0.41.209 (XO 2026-10-30): every live supply site (fuel farm, depot) of BOTH sides inside the merge radius round the target is in the mission, so a
        pilot who flies past a depot sees it. The radius is the Settings > Mission Build merge radius (the performance knob). Built last (after every flight and
        patrol), nearest first, while the unit limit has room: the rest are left out with a warning, and nothing else is pushed out for them (wrecks fit after).
        v0.41.220 (XO 2026-10-31): a raid scramble's target gets the same circle (`self._raid_xy`; the CAP station that centres the mission is up to 40 nm out from
        it). `only_raid` measures from the raid targets only and `max_units` caps what that call builds: the first call runs BEFORE the raiders and the alert pairs,
        because the raid's own load had already used the whole unit limit and the sites round its target were the first thing left out."""
        st, o = self.state, self.o
        if o.full_map:
            return
        R = max(5.0, float(o.merge_radius_nm)) * NM
        centres = list(getattr(self, "_raid_xy", [])) + ([] if only_raid else [(tx, ty)])
        if not centres:
            return
        cands = []
        for a in st.assets.values():
            if a.kind in SUPPLY_BUILDINGS and not a.destroyed and a.id not in self.groups_by_asset:
                cands.append((min(dist(a.x, a.y, cx, cy) for cx, cy in centres), a.id, "red", a))
        for aid, a in st.blue_assets.items():
            if a.kind in SUPPLY_BUILDINGS and not a.destroyed and aid not in self._supply_built:
                cands.append((min(dist(a.x, a.y, cx, cy) for cx, cy in centres), aid, "blue", a))
        cands = sorted((c for c in cands if c[0] <= R), key=lambda c: (c[0], c[1]))
        if not cands:
            return
        home = min((b for b in st.bases.values() if b.kind == BaseKind.AIRFIELD), key=lambda b: dist(b.x, b.y, tx, ty), default=None)
        built = used = 0
        for d_, aid, side, a in cands:
            need = math.ceil(len(supply_parts(a.kind, a.variant)) * o.carcass_weight) + ((road_sites.guard_units(a, self.d.level) if road_sites.is_road(a) else 1) if side == "red" else 0)         # v0.41.221: the buildings count like wrecks (carcass_weight), and red's Shilka guard is a whole unit
            if self._units_room() < need or (max_units is not None and used + need > max_units):
                break
            if side == "red":
                self._spawn_site(a, SOFT.get(a.kind), manifest, primary=False)
            elif home is not None:
                self._spawn_raid_target(package, home, aid, a.x, a.y, manifest)
            built += 1
            used += need
        if built < len(cands) and max_units is None:
            self.warns.append(f"{len(cands) - built} supply sites inside the {o.merge_radius_nm} nm merge radius left out to stay under the {o.max_units}-unit limit (furthest first)")

    def _place_carcasses(self) -> None:
        """Wrecks for every damaged or destroyed ground site near the route. Trimmed to what fits under the unit limit: the furthest
        from the route go first, and this runs after everything live is placed, so wrecks never push a flight out."""
        o, st = self.o, self.state
        if not o.carcasses:
            return
        w = max(0.05, float(o.carcass_weight))
        budget = int(max(0, self._units_room()) / w)
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
        if (pbase.kind if pbase is not None else spec.home) == BaseKind.CARRIER:
            return f"{nm}: Case I TACAN {self.o.carrier_tacan} ICLS {self.o.carrier_icls}".lstrip(": ")
        return (f"{nm}: Land. Tower, ATC frequency" if spec.fc3 else f"{nm}: Land. Tower COMM2 CH2").lstrip(": ")

    def _divert(self, pbase):
        fields = [b for b in self.state.bases.values() if b.kind == BaseKind.AIRFIELD and b.id != pbase.id]
        fields = [b for b in fields if not runways.is_closed(self.state, b.id)] or fields          # v0.41.254: not a cratered field (unless every other one is)
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

    def _platoon(self, country, name, comp, x, y, heading, formation, scale=1.0, spacing=None, base_def=False):
        types = []
        for vname, n in comp:
            vt = _vt(vname)
            if vt is None:
                self.warns.append(f"unknown vehicle {vname}; skipped")
                continue
            types += [vt] * max(1, round(n * scale))
        if not types:
            return None
        g = self.m.vehicle_group_platoon(country, name, types, mapping.Point(x, y, self.t), heading=int(heading) % 360, formation=formation)
        if spacing and formation == F.Star:                  # pydcs lays a star out 20 m apart; a wider one for SAM batteries
            g.formation_star(int(heading) % 360, spacing)
        bs = ai_skill(self.o, "blue", self.d, ground=True) if country is self.usa else None      # v0.41.70: blue base defences follow the Blue skill when it is set
        if base_def:                                         # v0.41.222 (XO 2026-10-31): blue's base SAMs and AAA are always Excellent, whatever the Blue skill setting says
            bs = BLUE_BASE_DEF_SKILL
        if bs:
            g.set_skill(getattr(Skill, bs, Skill.High))
        return g

    def _place_base(self, base, tx, ty, near=None):
        """v0.41.220: `near` = (x, y) of a raid target this field is built to cover (a neighbour of the raided field): it then gets only what reaches that point, the
        Patriot inside PATRIOT_NM, the HAWK inside HAWK_NM, the AAA inside COVER_AAA_NM (a full field is about 30 units)."""
        o = self.o
        from . import fleet as _fleet
        if base.kind == BaseKind.CARRIER and _fleet.sunk(self.state):      # v0.41.257: the ship is on the bottom: no carrier group in the mission
            return
        if base.kind == BaseKind.AIRFIELD:
            self.apt[base.id] = self.t.airports[base.airport]
            bt = dict(sams.blue_battery(base, self.state))      # v0.41.30: doctrinal batteries, every field alike; v0.41.62: read from the field's three sites (sams.py)
            if near is not None:                                 # v0.41.220: a covering neighbour builds only what reaches the raid's target
                from .raids import HAWK_NM, PATRIOT_NM
                from .raid_spawns import COVER_AAA_NM
                dn_ = dist(base.x, base.y, near[0], near[1]) / NM
                if dn_ > PATRIOT_NM:
                    bt["patriot_ln"] = 0
                if dn_ > HAWK_NM:
                    bt["hawk"] = False
                if dn_ > COVER_AAA_NM:
                    bt["aaa"] = 0
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
                    self.base_ad.setdefault(base.id, {})["pat"] = self._platoon(self.usa, f"BASEDEF {base.name} Patriot", [("Patriot_str", 1), ("Patriot_ECS", 1), ("Patriot_cp", 1),
                                  ("Patriot_EPP", 1), ("Patriot_ln", bt["patriot_ln"])], x, y, ang, F.Star, spacing=sams.BLUE_SPACING_M, base_def=True)
                x, y = site_at("aaa", ang + 120, 3500)
                if bt["aaa"]:
                    self._platoon(self.usa, f"BASEDEF {base.name} AAA", [("Vulcan", 2), ("M1097_Avenger", 2 if bt["aaa"] >= 2 else 1)], x, y, ang, F.Line, base_def=True)
                if bt["aaa"] >= 2:
                    x, y = site_at("aaa2", ang - 120, 3500)
                    self._platoon(self.usa, f"BASEDEF {base.name} AAA 2", [("Vulcan", 1), ("M1097_Avenger", 2)], x, y, ang, F.Line, base_def=True)
                if bt["hawk"]:
                    x, y = site_at("hawk", ang + 50, 6000)
                    self.base_ad.setdefault(base.id, {})["hawk"] = self._platoon(self.usa, f"BASEDEF {base.name} HAWK", [("Hawk_sr", 1), ("Hawk_tr", sams.BLUE_HAWK_TR), ("Hawk_pcp", 1), ("Hawk_cwar", 1),
                                  ("Hawk_ln", sams.BLUE_HAWK_LN)], x, y, ang, F.Star, spacing=sams.BLUE_SPACING_M, base_def=True)
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
                if _fleet.escort_out(self.state, k):               # v0.41.257: a sunk escort is missing until it is replaced
                    continue
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

    GUARD_CLEAR_M = 70.0        # v0.41.376 (S10): the guard group's centre is at least this far beyond the nearest building (a Star group is about 60 m across; judgment call)

    def _guard_spot(self, aim, cx, cy):
        """v0.41.376 (S10): where a supply site's guard group stands: just outside the buildings (`_bld_xy`), on the side of the nearest blue airfield (red's threat
        axis: the front is where blue's fighters come from). The next sides round if that spot is water or too close to a building; (cx, cy) if none works."""
        bl = self._bld_xy.get(aim) or []
        if not bl:
            return cx, cy
        mx, my = sum(p[0] for p in bl) / len(bl), sum(p[1] for p in bl) / len(bl)
        fb = self._nearest_airfield(mx, my)
        t0 = bearing(mx, my, fb.x, fb.y)
        for da in (0, 45, -45, 90, -90, 135, -135, 180):
            t = t0 + da
            ux, uy = offset(0.0, 0.0, t, 1.0)               # unit step of that bearing
            ext = max((p[0] - mx) * ux + (p[1] - my) * uy for p in bl)
            gx, gy = offset(mx, my, t, max(0.0, ext) + self.GUARD_CLEAR_M)
            if seac.site_ok(gx, gy) and min(dist(gx, gy, p[0], p[1]) for p in bl) >= self.GUARD_CLEAR_M * 0.9:
                return gx, gy
        return cx, cy

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
        if o.type == ObjectiveType.COUNTER_AIR and o.aim != "SWEEP":          # v0.41.297: a counter-air strike goes for the ramp, where the jets park, not the airfield's reference point (the garrison)
            r_ = self._ramp_xy(self.state.assets[o.target_id])
            if r_ is not None:
                return r_
        return self._site_center(self.state.assets[o.target_id])

    def _ramp_xy(self, a):
        """The middle of an airfield's aircraft ramp: the parking slot nearest to the centre of all its airplane slots (a real paved spot). None: no airport or no airplane slots."""
        ap = self.t.airports.get(a.airport) if getattr(a, "airport", None) else None
        slots = [q for q in (ap.parking_slots if ap else []) if q.airplanes]
        if not slots:
            return None
        cx_ = sum(q.position.x for q in slots) / len(slots); cy_ = sum(q.position.y for q in slots) / len(slots)
        q = min(slots, key=lambda q_: dist(q_.position.x, q_.position.y, cx_, cy_))
        return q.position.x, q.position.y

    @staticmethod
    def _ramp_line(package, manifest) -> str:
        """v0.41.308 (XO 2026-11-05): a counter-air strike says how many jets stand on the target's ramp in THIS mission (the parked statics, not the wing's total: some are airborne or over the cap)."""
        o = package.objective
        if o.type != ObjectiveType.COUNTER_AIR or o.aim == "SWEEP":
            return ""
        n = sum(len(g["units"]) for g in manifest.groups if g["kind"] == "enemy_air" and g.get("parked") and g["ref"] == o.target_id)
        return f" {n} aircraft stand parked on the ramp." if n else " No aircraft are parked on the ramp today."

    def _spawn_ils_dummies(self) -> None:
        """v0.41.336 (XO 2026-11-09, campaign rules plan decisions 49 and 51; NOT TESTED IN DCS): DCS lights the ILS only on the runway it counts as active, and the wind picks that
        runway; with the real regional wind the ILS end is often the tailwind end. XO's workaround: an invisible, immortal, uncontrolled aircraft at the ILS runway's threshold.
        One dummy (one unit) for each blue field that has an ILS (`runways.ILS_RUNWAY`) and is not cratered. Settings > ils_dummy picks the placement: "beside" (next to the
        threshold, off the pavement) or "on" (on the pavement); "off" builds none. Never in the manifest, the hook or the debrief.
        S32 (XO 2026-11-11): one mode, on or off. v0.41.395: the dummy is a small aircraft (`ILS_DUMMY_TYPE`) cold on the grass beside the ILS runway's threshold, 100 m off the centreline and turned across the runway (`runways.ils_dummy_point`), not on a ramp slot.
        Not tested in DCS: whether the ILS lights for an aircraft parked there is the open question."""
        mode = self.o.ils_dummy
        if mode not in ILS_DUMMY_MODES:
            return
        st = self.state
        for b in st.bases.values():
            num = runways.ILS_RUNWAY.get(getattr(b, "airport", None) or "")
            if b.kind != BaseKind.AIRFIELD or num is None or runways.is_closed(st, b.id):
                continue
            ap = self.t.airports.get(b.airport)
            spot = runways.ils_dummy_point(ap, num) if ap is not None else None
            if spot is None or self._units_room() < 1:
                continue
            x, y, hdg = spot
            try:
                g = self.m.flight_group_inflight(self.usa, f"ILS dummy {b.id}", ILS_DUMMY_TYPE, self._pt(x, y), 0, 0, None, 1)
            except Exception as ex:
                self.warns.append(f"ILS dummy for {b.name} could not be built ({ex})")
                continue
            p0 = g.points[0]
            p0.type, p0.action = "TakeOffGround", PointAction.FromGroundArea          # a cold aircraft standing on the ground at this spot, not an air start
            p0.alt = int(relief.ground_m(x, y) or 0)
            p0.tasks = []
            p0.ETA, p0.ETA_locked, p0.speed_locked = 0, True, True                    # DESIGN_NOTES section 8: the first point is time- and speed-locked, like every takeoff point
            p0.add_task(task.SetInvisibleCommand(True))                               # XO's note: invisible to optics, sensors and radar ...
            p0.add_task(task.SetImmortalCommand(True))                                # ... and immortal, so nothing can break it
            g.uncontrolled = True                                                    # never starts, taxis or calls
            g.hidden = True
            g.units[0].heading = hdg % 360.0                           # across the runway heading, like a parked aircraft

    def _crater_points(self) -> list:
        """v0.41.336 (XO 2026-11-09): [[x, z, power], ...] scripted blasts along the runway of every cratered field (`runways.crater_points`, for show: the hook fires them a few
        seconds into the mission). A closed runway stays closed in SQE's own state either way; this only makes it look hit. Seeded by the field and the turn it was hit."""
        st, out = self.state, []
        for fid in sorted(runways.closed_ids(st)):
            o_ = st.bases.get(fid) or st.assets.get(fid)
            ap = self.t.airports.get(getattr(o_, "airport", None) or "")
            if ap is None:
                continue
            turn = (st.ground or {}).get("craters", {}).get(fid, {}).get("turn", 0)
            for x, y in runways.crater_points(st, fid, ap, random.Random(f"{st.campaign_id}:crater:{fid}:{turn}")):
                out.append([round(x, 1), round(y, 1), runways.CRATER_POWER])
        return out

    def _spawn_parked_jets(self, package, manifest) -> None:
        """v0.41.297 (XO 2026-11-05, "if those jets are really available on that field then spawn them parked"): a counter-air strike (not the sweep) finds the target field's jets
        parked on the ramp, as real uncontrolled aircraft on free parking spots. How many: the wing's serviceable jets of each type, minus the jets this mission launches from that field
        (alert pairs, raid and CAP flights are in `manifest` by now: they are in the air, not on the ramp), at most PARKED_MAX, the free parking spots, and what the unit limit leaves.
        They are an `enemy_air` group of the wing marked `parked`, so a destroyed one comes off the wing in the debrief like a shot-down flight."""
        o = package.objective
        if o.type != ObjectiveType.COUNTER_AIR or o.aim == "SWEEP":
            return
        st = self.state
        a = st.assets.get(o.target_id)
        w = st.enemy_air_at(o.target_id) if a is not None else None
        ap = self.t.airports.get(a.airport) if (a is not None and getattr(a, "airport", None)) else None
        if w is None or ap is None or a.destroyed:
            return
        left = {}
        for q in w.sqns:
            left[q.aircraft] = left.get(q.aircraft, 0) + q.available
        for g in manifest.groups:                                               # in the air, not parked
            if g["kind"] == "enemy_air" and g["ref"] == a.id and not g.get("parked"):
                for _ in g["units"]:
                    t_ = g.get("ac") if left.get(g.get("ac"), 0) > 0 else max(left, key=left.get, default=None)
                    if t_ is not None and left.get(t_, 0) > 0:
                        left[t_] -= 1
        # a mixed wing parks its types in turn, so a cut at PARKED_MAX keeps the mix
        pools = {t_: n_ for t_, n_ in left.items() if n_ > 0}
        seq = []
        while pools and len(seq) < PARKED_MAX:
            for t_ in list(pools):
                seq.append(t_); pools[t_] -= 1
                if pools[t_] <= 0:
                    del pools[t_]
        rw_h = ap.runways[0].heading if ap.runways else 0.0
        made, names_by = 0, {}
        for t_ in seq:
            cls = getattr(planes, t_, None)
            if cls is None or self._units_room() < 1:
                continue
            slot = ap.free_parking_slot(cls)
            if slot is None:
                continue
            # v0.41.324 (XO 2026-11-06, "put untasked real jets"): a real, cold, uncontrolled aircraft on its parking spot. A destroyed static gave the hook no name
            # it could count; a real unit dies like any other aircraft. One group each, named for the ramp (a full unit each in the unit budget).
            nm = f"PARK {a.id}|{made + 1}"
            try:
                pg = self.m.flight_group_from_airport(self.red, nm, cls, ap, start_type=StartType.Cold, group_size=1, parking_slots=[slot])
            except Exception:
                continue
            made += 1
            pg.uncontrolled = True
            pg.units[0].name = nm
            self._ramp_pts.append((slot.position.x, slot.position.y))        # v0.41.313: where the JSOW-As of a Standoff Counter-Air aim
            names_by.setdefault(t_, []).append(nm)
        for t_, names in names_by.items():
            manifest.add("enemy_air", a.id, names, ac=t_, parked=True)
        self._retarget_ramp_tasks()

    def _retarget_ramp_tasks(self) -> None:
        """v0.41.329 (XO 2026-11-06: "no way to aim at the parked jets once they are spawned?"): the strike flights are built before the jets exist, so their bomb tasks were made on
        an estimate (the ramp slots' middle). Now the jets are placed: every counter-air bomb task made by `_bomb_task` is pointed at the middle of the real jets and, when they stand
        in a line longer than `RAMP_AXIS_MIN_M`, given the heading along it. DCS takes one point per task, so it is the middle of the cluster, not one jet. No jets: unchanged."""
        pts_ = list(self._ramp_pts)
        if not pts_ or not self._ramp_tasks:
            return
        cx_, cy_ = sum(q[0] for q in pts_) / len(pts_), sum(q[1] for q in pts_) / len(pts_)
        span_ = max((dist(p[0], p[1], q[0], q[1]) for p in pts_ for q in pts_), default=0.0)
        cx_, cy_ = min(pts_, key=lambda q: dist(q[0], q[1], cx_, cy_))       # v0.41.331 (XO): aim at the jet nearest the middle, not at the empty middle
        dir_ = None
        if span_ >= RAMP_AXIS_MIN_M:
            p1_, p2_ = max(((p, q) for p in pts_ for q in pts_), key=lambda pq: dist(pq[0][0], pq[0][1], pq[1][0], pq[1][1]))
            dir_ = int(round(math.degrees(math.atan2(p2_[1] - p1_[1], p2_[0] - p1_[0])))) % 360
        for bt_ in self._ramp_tasks:
            bt_.params["x"], bt_.params["y"] = cx_, cy_
            bt_.params["directionEnabled"] = dir_ is not None
            bt_.params["direction"] = dir_ if dir_ is not None else 0

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
        if a.kind == AssetKind.C2 and r.random() < 0.5:
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
        skill = getattr(Skill, ai_skill(self.o, "red", d), Skill.High)
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

    def _spawn_opfor_ground(self, package, tx, ty, manifest, polyline=None, route_sites=None, route_near=None, all_sams=False):
        st, obj = self.state, package.objective
        from .war import blinded_today
        # the DEAD stage of a SEAD-first pair: if the SEAD package blinded the site (the day's verdict), its radars are already gone when the mission starts
        self._blind_site = {obj.target_id} if (obj.type == ObjectiveType.DEAD and obj.aim == "DEAD" and blinded_today(st, obj.target_id)) else set()
        fol_ = []
        if obj.type in (ObjectiveType.STRIKE, ObjectiveType.CAS) and obj.after:      # v0.41.158: behind a SEAD: the sites it waits on are live in this mission, those the SEAD blinded without their radars
            from .war import after_sites, site_blind_today
            fol_ = [st.assets[x] for x in after_sites(obj) if x in st.assets and not st.assets[x].destroyed]
            staged_ = {x.objective.target_id for x in getattr(self, "_extras", []) if x.objective.type == ObjectiveType.DEAD and x.objective.aim in SEAD_AIMS}
            self._blind_site |= {a.id for a in fol_ if site_blind_today(st, a.id) and a.id not in staged_}      # a SEAD flown in this mission blinds it for real
        if obj.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            tgt, relevant = None, []            # no ground target, but enemy SAMs whose rings touch the route / station stay live
        else:
            tgt = st.assets[obj.target_id]
            dfn = sorted((st.assets[i] for i in tgt.defended_by if not st.assets[i].destroyed), key=lambda x: dist(x.x, x.y, tgt.x, tgt.y))
            relevant = [tgt] + dfn[:2]                                                   # the two nearest defenders; more only costs VR frame rate
            relevant += [g for g in st.assets.values() if g.guards == tgt.id]            # a SAM site's dug-in garrison is part of its cluster
            relevant += fol_
        extra_ids_ = set()                   # v0.41.291: the SAM sites `all_sams` adds beyond the route's own (they leave RAID_SAM_RESERVE units free for the flights built after)
        if polyline:                         # every SAM site whose ring touches the route is live from the start
            cs_ = tm.corridor_sam_sites(st, polyline, tgt, **({"max_route": route_sites} if route_sites else {}))
            if all_sams:                     # v0.41.291 (XO 2026-11-04: "spawn all red SAMs", the carrier-defence setpiece only): every live SAM site, not just the ones whose ring touches the route
                have_ = {a_.id for a_ in cs_}
                extra_ = [a_ for a_ in st.assets.values() if a_.kind == AssetKind.SAM and not a_.destroyed and a_.id not in have_]
                cs_ = cs_ + extra_
                extra_ids_ = {a_.id for a_ in extra_}
            if route_near is not None:                                  # v0.41.285: nearest to this point first, so the unit limit trims the furthest (see `_spawn_raid`)
                cs_.sort(key=lambda a_: (a_.id in extra_ids_, dist(a_.x, a_.y, route_near[0], route_near[1])))      # (v0.41.291: the route's own sites first, then the extras `all_sams` adds)
            route_ids = {a_.id for a_ in cs_}
            relevant += cs_
        ewrs = sorted((a for a in st.assets.values() if a.kind == AssetKind.EWR and not a.destroyed),
                      key=lambda a: tm.poly_dist(a.x, a.y, polyline) if polyline else dist(a.x, a.y, tx, ty))
        relevant += [a for a in ewrs[:2] if (tm.poly_dist(a.x, a.y, polyline) if polyline else 0) < 80 * NM]
        seen = set()
        cut_ = False                                                    # v0.41.285: once a route site does not fit, the rest of them (further out) are left out too
        cut_names_ = []
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
            if route_near is not None and a.id in route_ids and a.id not in self.groups_by_asset and (cut_ or self._units_room() < sum(n_ for _, n_ in (comp or [])) + 2 + (RAID_SAM_RESERVE if a.id in extra_ids_ else 0)):
                cut_ = True
                if all_sams:
                    cut_names_.append(a.name)                            # one warning for the whole tail (v0.41.291: up to every SAM site is a candidate)
                else:
                    self.warns.append(f"{a.name}: left out to stay under the unit limit (furthest from the intercept point first)")
                continue
            if comp and route_sites and self._units_room() < sum(n_ for _, n_ in comp) + 2:
                self.warns.append(f"{a.name}: left out to stay under the unit limit")        # v0.41.256: the raid's extra route sites never push the mission over it
                continue
            if comp:
                self._spawn_site(a, comp, manifest, primary=is_tgt)
        if cut_names_:
            self.warns.append(f"{len(cut_names_)} SAM sites left out to stay under the {self.o.max_units}-unit limit (furthest from the intercept point first): " + ", ".join(cut_names_[:6]) + (", ..." if len(cut_names_) > 6 else ""))

    def _spawn_site(self, a, comp, manifest, primary):
        """ONE group per site: a SAM battery needs its search/track radars, launchers and command post together."""
        r = self.vrng
        skill = getattr(Skill, ai_skill(self.o, "red", self.d), Skill.High)
        garrison = a.kind == AssetKind.ARMOR and a.variant == "GARRISON"
        comp = (self._garrison_comp() if garrison else self._armor_comp()) if a.kind == AssetKind.ARMOR else (
            road_sites.guard_comp(a, self.d.level) if road_sites.is_road(a) else self._vary_comp(a, comp))        # v0.41.241: a road site's guard follows its level and variant
        cx, cy = self._site_center(a)
        base_count = sum(n for vname, n in comp if _vt(vname) is not None)
        bld = []
        if a.kind in SUPPLY_BUILDINGS:                  # v0.41.192: fuel farm / depot = real buildings, guarded by the Shilka group
            bld = self._place_buildings(self.red, a.id, a.kind, cx, cy, r.randint(0, 359), scale=a.health, variant=a.variant)
            base_count += len(supply_parts(a.kind, a.variant))
            gx, gy = self._guard_spot(a.id, cx, cy)         # v0.41.376 (S10): the guard stands at the edge of the layout facing blue, not inside it
            cx, cy = gx, gy
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
        if bld:
            scale = 1.0                                 # the guard is always there; the damage shows in the buildings
        g = self._platoon(self.red, a.id, comp, cx, cy, heading, form, scale=scale)
        if g is None:
            return
        if column:
            base_count = max(1, round(len(g.units) / max(0.05, a.health)))                      # the count at full health, so losses read back as health
        if a.kind == AssetKind.SAM and (a.suppressed or a.id in self._blind_site):
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
        names += bld
        self.groups_by_asset[a.id] = g
        if a.kind == AssetKind.ARMOR:
            self.armor_id, self.armor_center = a.id, (cx, cy)
        mine = bool(primary) and (not manifest.cur_pkg or manifest.cur_pkg == self._anchor_id)
        trk = [u.name for u in g.units if str(getattr(u, "type", "")) in TRACK_RADARS]
        srch = [u.name for u in g.units if str(getattr(u, "type", "")) in SEARCH_RADARS]
        manifest.add("asset", a.id, names, base_count=base_count, health_before=a.health, primary=mine, label=a.name, trk=trk, srch=srch,
                     primary_pkgs=[manifest.cur_pkg] if (primary and manifest.cur_pkg) else [])

    # ---- support: tanker + AWACS well back from the enemy, with a HAVCAP at the same spot ----------------------------
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
        self._hot = None
        csname, fno = f.callsign.rsplit(" ", 1)
        fno = int(fno)

        cap_zone = None
        if f.tag:       # support CAP: airborne on station for the whole package
            cap_zone, wps, stop = self._support_cap_route(package, f, geom, hav_xy, tot_s, rtb_s)
            stop, act_s = self._support_sortie(package, f, wps, stop, (plan, geom, tanker_xy, hav_xy, push_s, tot_s, rtb_s, idx))
        else:
            r_ = self._flight_route(package, f, geom, idx, push_s, tot_s)
            if r_ is None:
                return None, None                          # already back on the ground
            wps, act_s, past_push, stop = r_
            push_s = self._push_adj.get(id(f), push_s)             # S38

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
        self._scrub_point(package, f, g, base, wps, tot_s)
        self._home_leg(f, g, base, wps, idx, hold_end, stop, special)
        if gate is not None and gate.get("ai") and gate.get("dead"):
            self._gate_stop_slack(g, int(gate.get("acap") or 0))
        if gate is not None:
            if gate["to"] is None:
                gate["to"] = len(g.points)                              # the landing point
            self._gates.append(gate)
        tw = None if f.tag else objective_wp(wps)
        if tw is not None and f.role in (Role.STRIKE, Role.CAS) and getattr(f, "kit", "") != "JSOW":
            self._striker_tgt.setdefault(package.id, []).append(float(tw.eta_s))            # S38
        if tw is not None and f.role in (Role.STRIKE, Role.SEAD, Role.CAS):
            egr_ = next((w.eta_s for w in wps if w.name == "EGR"), None)          # v0.41.40: when this striker is OUT, for the escorts to wait on
            self._striker_egr.append(((geom.tx, geom.ty), float(egr_ if egr_ is not None else tw.eta_s + 180)))
        return g, (tw.eta_s if tw is not None else None)

    def _gate_stop_slack(self, g, slack_s):
        """v0.41.363 (attack fix plan, Stage B1): an AI gated STRIKE / CAS flight may hold up to the gate's cap (acap) outside the fight, but its attack
        tasks stop at TOT + LATE_ATTACK_S (bombs) or TGT ETA + 420 / + 1080 (CAS): a long hold expired them even when the hold itself worked. So their
        stop times grow by the cap. Only ground attack ControlledTasks that already have a stop time; never the Orbit / ROE / ECM tasks."""
        if slack_s <= 0:
            return
        for pt_ in g.points:
            for t_ in pt_.tasks:
                if getattr(t_, "Id", "") != "ControlledTask":
                    continue
                st_ = t_.params.get("stopCondition", {})
                inner_ = t_.params.get("task", {})
                if "time" not in st_ or inner_.get("id") not in ("Bombing", "CarpetBombing", "AttackGroup", "EngageTargetsInZone"):
                    continue
                if inner_["id"] == "EngageTargetsInZone" and "Air" in (inner_.get("params", {}).get("targetTypes") or []):
                    continue
                st_["time"] = int(st_["time"]) + slack_s

    def _support_sortie(self, package, f, wps, full_stop, ctx):
        """v0.41.78: a support CAP sortie flies only its airframe's time on station (barcap.endurance_min); the rest of the mission is covered by relief
        sorties built after the merged packages are known (_spawn_reliefs). -> (stop, act_s) for THIS sortie. A relief (f.relief set) is air-spawned
        RELIEF_BACK_NM behind its station and late-activated so it arrives on station HANDOVER_MIN before the sortie it replaces leaves."""
        rel = getattr(f, "relief", None)
        if rel is not None:
            base = self.state.bases[f.base_id]
            s0 = wps[0]
            back = min(RELIEF_BACK_NM * NM, max(0.0, dist(s0.x, s0.y, base.x, base.y) - 2 * NM))
            if back > 0:
                s0.x, s0.y = offset(s0.x, s0.y, bearing(s0.x, s0.y, base.x, base.y), back)
            lead = int(back / NM / max(1.0, s0.speed_kts) * 3600) + 30
            if rel.get("flag"):                                               # v0.41.79: a replacement is called by the hook, not by the clock
                return int(rel["end"]), 0
            return int(rel["end"]), max(1, int(rel["start"]) - lead)
        e_ = int(barcap.endurance_min(f.aircraft, f.tag == "TNKCAP") * 60)
        self._flag_n += 1
        self._relief_src[f.callsign] = {"package": package, "f": f, "ctx": ctx, "full": int(full_stop), "end": min(int(full_stop), e_), "E": e_, "bf": self._flag_n}
        return min(int(full_stop), e_), 0

    def _spawn_replacement(self, src, end_s, full, manifest, despawn):
        """v0.41.79: the standby for one support CAP's first sortie. The hook watches the pair: a jet down, winchester or bingo sends the whole pair
        home and, COVER_DELAY_S later, calls this copy of the flight (a pair that appears RELIEF_BACK_NM behind the station, as a relief does) to take
        the station for the rest of the sortie plus the handover. One standby per CAP (the chain's later sorties are watched for nothing yet).
        Not built when the unit limit is reached: the pair is still watched and sent home, only nothing replaces it."""
        f0 = src["f"]
        ent = {"g": f0.callsign, "n": int(f0.count), "bf": src["bf"], "rf": 0, "u": float(end_s)}
        used = {x.callsign for x in src["package"].flights} | {x.callsign for x in self._relief_names} | {x.callsign for x, _g in self.flight_groups}
        free = next((f"{c_} {n}" for c_ in [f0.callsign.rsplit(" ", 1)[0]] + [c for c in callsigns.table(f0.aircraft)] for n in range(1, 10) if f"{c_} {n}" not in used), None)
        if free is not None and f0.count <= self._units_room():
            self._flag_n += 1
            nf = copy.deepcopy(f0)
            nf.callsign, nf.is_player = free, False
            nf.relief = {"k": 0, "start": 0, "end": int(min(full, end_s + barcap.HANDOVER_MIN * 60)), "flag": self._flag_n}
            self._relief_names.append(nf)
            plan, geom, tanker_xy, hav_xy, push_s, tot_s, rtb_s, idx = src["ctx"]
            self._spawn_flight(src["package"], nf, plan, geom, tanker_xy, hav_xy, push_s, tot_s, rtb_s, idx, manifest, despawn)
            ent["rf"] = self._flag_n
        else:
            self.warns.append(f"{f0.callsign}: no standby pair (unit limit or no free callsign)")
        self._cover.append(ent)

    def _spawn_reliefs(self, src, full, manifest, despawn):
        """v0.41.78: the relief sorties of one support CAP: sortie k starts k * (E - HANDOVER_MIN) after the mission began and flies E minutes (the last
        one only to `full`, the time the mission needs cover until). Each is a copy of the flight with its own callsign, late-activated, on the same
        station. The background war does not track these (no replacement of losses yet: v0.41.79)."""
        f0, package, E = src["f"], src["package"], src["E"]
        step = E - barcap.HANDOVER_MIN * 60
        used = {x.callsign for x in package.flights} | {x.callsign for x in getattr(self, "_relief_names", [])} | {x.callsign for x, _g in self.flight_groups}
        names = getattr(self, "_relief_names", None)
        if names is None:
            names = self._relief_names = []
        k, start = 1, step
        while start < full - 300:
            if f0.count > self._units_room():
                self.warns.append(f"{f0.callsign}: relief sorties left out to stay under the {self.o.max_units}-unit limit")
                break
            nf = copy.deepcopy(f0)
            nm, no = f0.callsign.rsplit(" ", 1)
            alln = used | {x.callsign for x in names}
            free = next((f"{c_} {n}" for c_ in [nm] + [c for c in callsigns.table(f0.aircraft) if c != nm] for n in range(1, 10) if f"{c_} {n}" not in alln), None)
            if free is None:                                              # every name of the type taken nine times over: not reachable with real flight counts
                self.warns.append(f"{f0.callsign}: no free callsign for its relief")
                break
            nf.callsign = free
            nf.is_player = False
            nf.relief = {"k": k, "start": int(start), "end": int(min(start + E, full))}
            names.append(nf)
            plan, geom, tanker_xy, hav_xy, push_s, tot_s, rtb_s, idx = src["ctx"]
            self._spawn_flight(package, nf, plan, geom, tanker_xy, hav_xy, push_s, tot_s, rtb_s, idx, manifest, despawn)
            k += 1
            start += step

    def _add_cap2(self, package, wps, spec, geom) -> bool:
        """Phase 8 (v0.41.349, campaign rules plan decision 22): the far end of a TARCAP / escort / sweep station's race-track, a point (CAP2) right after the station
        (CAP1). It lies CAP_SPREAD_NM[job] from the station across the line to the target, on the side with more SAM room, the leg halved (floor 5 nm) until it is clear.
        No clear point, or no room in the airframe's route: nothing is added and the station keeps its circle. The point is never an objective (no action, no orbit):
        the station stays the one place the flight is timed to. -> True when CAP2 was added."""
        k = next((i for i, w in enumerate(wps) if w.orbit and w.action in CAP_SPREAD_NM), None)
        if k is None or any(w.name == "CAP2" for w in wps):
            return False
        if len(wps) + 1 + 2 > spec.profile.max_points:
            return False
        st_ = wps[k]
        need_ = min(CAP2_ROOM_NM, self._room(st_.x, st_.y, package))
        xy = cap2_point(st_.x, st_.y, bearing(st_.x, st_.y, geom.tx, geom.ty), CAP_SPREAD_NM[st_.action], lambda x, y: self._room(x, y, package) - need_)
        if xy is None:
            return False
        wps.insert(k + 1, Wpt("CAP2", xy[0], xy[1], st_.alt_ft, st_.speed_kts))
        return True

    def _flight_route(self, package, f, geom, idx, push_s, tot_s):
        """Everyone else's route: plan_route, terrain, times. -> (wps, act_s, past_push, stop), or None when the flight is already back on the ground. Moved out of _spawn_flight in v0.41.54, unchanged."""
        o = self.o
        spec = AIRCRAFT[f.aircraft]
        base = self.state.bases[f.base_id]
        past_push, act_s = False, 0
        sp = None
        if not f.is_player:
            sp = self._spawn_point(f, base, geom)
        wps = plan_route(f.role, (base.x, base.y), geom, self._flight_profile(f, package), is_player=f.is_player, tanker_xy=None, stack_idx=idx,
                         spawn=sp[0] if sp else None, spawn_alt_ft=sp[1] if sp else 0, spawn_kts=sp[2] if sp else 0,
                         jsow=getattr(f, "kit", "") == "JSOW", jsow_side=self._jsow_side(package, geom), keep_out=self._umbrella_keep(package), agm88_deg=self._agm88_deg(package, geom),
                         rel=self._rel_kind(package, f))
        if getattr(f, "rush", False):
            self._rush_speeds(wps)                                    # v0.41.256: the raid SEAD
        shaped_, meet_ = False, None
        if self._raid_cap(package, f):
            k0_ = next((i for i, w in enumerate(wps) if w.action == "CAPORBIT"), None)
            o12_ = ((wps[k0_].x, wps[k0_].y), (wps[k0_ + 1].x, wps[k0_ + 1].y)) if (k0_ is not None and k0_ + 1 < len(wps)) else None
            self._raid_cap_station(package, geom, wps)                # v0.41.114: the station up the raid's way in, not on the player's line
            rsp_ = getattr(self, "_rsp", {}).get(package.id)
            ip_ = (rsp_ or {}).get("ip")
            if o12_ is not None and rsp_ is not None and (f.aircraft.startswith("F-14") or ip_ is not None) and (package.extra or {}).get("setpiece"):
                wps = self._raid_f14_shape(wps, k0_, o12_, ip_, idx, f.aircraft.startswith("F-14"))      # v0.41.256: HOLD (high, slow) -> PUSH -> IP -> TGT, the intercept point (v0.41.265: on the bombers' way in, for every raid CAP)
                if RAID_F14_HOLD:
                    f.gate_flag = rsp_["flag"]
                push_s = rsp_["t_flag"]                                   # the briefed push is the gate's own latest time
                shaped_ = True
                rc_ = getattr(self, "_rclock", {}).get(package.id)
                if rc_ and rc_.get("t_leave") is not None and ip_ is not None and not RAID_F14_HOLD:
                    # v0.41.280: be on the intercept point RAID_MEET_LEAD_S before the bombers get there (their push + the flight from the marshal)
                    meet_ = rc_["t_leave"] + dist(rc_["mshl"][0], rc_["mshl"][1], ip_["ip"][0], ip_["ip"][1]) / RAID_MPS - RAID_MEET_LEAD_S
            # v0.41.28: a raid scramble's way out to its station bends round red SAMs like a strike's (the orbit leg stays as it is)
            k1_ = next((i for i, w in enumerate(wps) if w.action == "CAPORBIT"), None)
            if k1_ and not shaped_:                                   # (an F-14's crossing leg goes toward the SAMs on purpose, once the gate opens)
                wps = avoid_circles(wps[:k1_ + 1], self._zone_sams(package, True), spec.profile.max_points - (len(wps) - k1_ - 1), 1) + wps[k1_ + 1:]
        self._add_cap2(package, wps, spec, geom)          # Phase 8: before the terrain check and the times, so both count it
        if not f.is_player or o.player_is_ai:
            terrain_clear(wps)                          # an AI flight climbs on its own schedule: its altitudes must clear the ridges on each leg
        if f.is_player:
            assign_times(wps, self._dep_s, push_s)
            act_s = 0
        else:
            assign_times(wps, 0.0)                      # natural pace from the spawn
            push_s, sead_hold_ = self._sead_window(package, f, wps, push_s)          # S38
            hold_i = next((i for i, w in enumerate(wps) if w.action == "HOLD"), None)
            nat = wps[hold_i + 1].eta_s if hold_i is not None else next((w.eta_s for w in wps if w.action == "CAPORBIT"), next(w for w in reversed(wps) if w.name != "CAP2").eta_s)      # Phase 8: a sweep (no hold) is timed to its station, not to CAP2 behind it
            act_raw = int(push_s - nat - (120 if hold_i is not None else 60))      # arrive ~2 min early, hold, push on time
            if shaped_ and not RAID_F14_HOLD:
                act_raw = int(meet_ - nat) if meet_ is not None else -RAID_HEAD_S     # v0.41.280: timed to the raid; without a raid clock the v0.41.278 head start (already airborne)
            act_s = max(0, act_raw)
            assign_times(wps, float(act_raw), push_s)
            if sead_hold_ is not None:
                sw_ = next(w for w in wps if w.action == "SEAD")
                dw_ = max(0.0, sead_hold_ - sw_.eta_s)
                for w in wps[wps.index(sw_) + 1:]:
                    w.eta_s += dw_                       # EGR and home come after the window
                sw_.hold_to = sead_hold_
            if shaped_ and self._raid_edge_on(package):               # v0.41.282: when blue is on the intercept point; the setpiece's raiders are timed to the last of them
                tw_ = next((w for w in wps if w.name == "TGT" and w.action == "CAPORBIT"), None)
                if tw_ is not None:
                    eb_ = self.__dict__.setdefault("_edge_blue", {})
                    eb_[package.id] = max(eb_.get(package.id, 0.0), float(tw_.eta_s))
            self._hot = self._hot_slot(package, f, base, wps, act_raw, hold_i is not None)
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

    def _sead_window(self, package, f, wps, push_s):
        """S38: an AI SEAD flight in a STRIKE / CAS package works the strikers' window (a radar that is off is not suppressed: SAMs come up when the strikers appear). Its HARM point
        is timed SEAD_LEAD_S before the first striker's time over target (never earlier than the old push-relative time: only delays the push) and it holds there until the last
        striker's time over target + SEAD_WINDOW_S. -> (push_s, hold_to or None). Strikers not built yet (no time recorded) or no PUSH / SEAD point: unchanged. Natural-pace etas expected in wps."""
        tg = self._striker_tgt.get(package.id)
        if (f.role != Role.SEAD or f.tag or getattr(f, "kit", "") == "JSOW" or package.objective.type not in (ObjectiveType.STRIKE, ObjectiveType.CAS) or not tg):
            return push_s, None
        sw = next((w for w in wps if w.action == "SEAD"), None)
        pu = next((w for w in wps if w.name == "PUSH"), None)
        if sw is None or pu is None:
            return push_s, None
        new = min(tg) - SEAD_LEAD_S - (sw.eta_s - pu.eta_s)
        push_s = max(push_s, new)
        self._push_adj[id(f)] = push_s
        return push_s, max(tg) + SEAD_WINDOW_S

    HOT_ROLL_S = 45          # v0.41.96: runway start to wheels up (alert pairs measured about 45 s in v0.41.0 runs); judgment call for full packages
    HOT_CLIMB_KTS = 300      # average speed from the runway to the pretend-DEP point (climbing), judgment call
    HOT_HOME_S = 600         # v0.41.97: no runway release at your own field this close to your planned landing (judgment call)
    RWY_GAP_S = 60           # the hook's RWY_STAGGER_S: releases from one runway are at least this far apart

    def _tune_triggers(self, aircraft: str, mhz: float) -> list:
        """v0.41.215 (XO 2026-10-30): one flag per readable radio of the player's jet, set while that radio is within TUNE_BAND_MHZ of the AWACS frequency
        (Mission Editor "Cockpit Parameter is in range" triggers; probed in DCS 2026-10-28 / 30: F-16C COMM1, F/A-18C and F-14B COMM1 + COMM2, A-10C UHF).
        A jet not in TUNE_PARAMS (the FC3 F-15C) gets no flags and counts as always tuned. A radio tuned to another band reads far outside the window."""
        flags = []
        for name in TUNE_PARAMS.get(aircraft, ()):
            self._flag_n += 1
            fl = self._flag_n
            flags.append(fl)
            lo, hi = mhz - TUNE_BAND_MHZ, mhz + TUNE_BAND_MHZ
            for rng_, want_set in (((lo, hi), True), (("0.000001", lo - 0.1), False), ((hi + 0.1, "1000000000000"), False)):
                t = triggers.TriggerContinious(comment=f"SQE tuned {name} {'on' if want_set else 'off'}")
                t.add_condition(condition.CockpitParamInRange(name, f"{float(rng_[0]):.6f}" if not isinstance(rng_[0], str) else rng_[0], f"{float(rng_[1]):.6f}" if not isinstance(rng_[1], str) else rng_[1]))
                t.add_condition(condition.FlagIsFalse(fl) if want_set else condition.FlagIsTrue(fl))
                t.add_action(action.SetFlag(fl) if want_set else action.ClearFlag(fl))
                self.m.triggerrules.triggers.append(t)
        return flags

    def _hot_slot(self, package, f, base, wps, act_raw, held):
        """v0.41.96: may this AI flight start on the runway instead of airborne, and when is it released? Only package flights from LAND fields
        other than yours, with the setting on. The flight is due at its first point (the pretend DEP) at act_raw; the runway start adds the roll
        and the climb-out to it, so it is released that much earlier. The route already has a margin before the push (2 min with a hold, 1 min
        without; the flight arrives early and waits), and up to margin - 30 s of lateness (a runway shared with an earlier release) is taken out of
        that margin. Anything that cannot be released in time stays an airborne spawn. -> {"t", "b"} or None"""
        if not getattr(self.o, "hot_runway_starts", False) or f.is_player or f.tag or base.kind != BaseKind.AIRFIELD:
            return None
        if base.id not in self.apt or act_raw < 0:
            return None
        own = base.id == getattr(self, "_main_base", None)
        if own and not getattr(self.o, "hot_runway_own_field", False):
            return None                  # v0.41.99: your own field only with the sub-setting
        p_launch, p_rtb = getattr(self, "_p_times", (0.0, 1e9))
        if any(x is not f and x.callsign == f.callsign for x in package.flights):
            return None                  # a guard shares this callsign (v0.41.88): the hook finds a group by name, so it stays an airborne spawn
        lead = self.HOT_ROLL_S + 15 + dist(base.x, base.y, wps[0].x, wps[0].y) / NM / self.HOT_CLIMB_KTS * 3600
        slack = (120 if held else 60) - 30
        want = act_raw - lead
        used = self._rwy_rel.setdefault(base.id, [])
        t = max(0.0, want)
        if own:
            # v0.41.97: your own field. Nothing is released before you are rolling (the hook also waits until you have taken off) and nothing
            # in the last HOT_HOME_S before you land: that one stays an airborne spawn.
            if not used:
                used.append(p_launch)
            t = max(t, p_launch + self.RWY_GAP_S)
        while t <= want + slack + 1e-6:
            if own and t > p_rtb - self.HOT_HOME_S:
                return None
            if all(abs(t - u) >= self.RWY_GAP_S for u in used):
                used.append(t)
                return {"t": int(t), "b": f"{self.usa.name}:{self.apt[base.id].name}"}
            t += 5
        return None

    def _hot_group(self, f, spec, base):
        """The runway-start group for a hot-runway flight, or None (no room: it spawns airborne after all). Built once per flight."""
        if self._hot.get("g") is None:
            self._hot["g"] = self._from_airport(self.usa, f.callsign, spec.dcs_type, self.apt[base.id], MAIN_TASK[f.role], StartType.Runway, f.count, quiet=True) or False
        return self._hot["g"] or None

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
        elif self._hot is not None and self._hot_group(f, spec, base) is not None:
            g = self._hot_group(f, spec, base)             # v0.41.96: hot on the runway; the hook puts it there at its release time
            g.late_activation = True
            self._rwyq.append({"g": f.callsign, "f": 0, "t": self._hot["t"], "b": self._hot["b"]})
            first = 0
        else:                 # already airborne
            s0 = wps[0]
            self._clear_spawn(s0, wps, act_s)
            g = self.m.flight_group(self.usa, f.callsign, spec.dcs_type, None, pt(s0.x, s0.y), altitude=s0.alt_ft * FT,
                                    speed=s0.speed_kts * KPH, maintask=MAIN_TASK[f.role], group_size=f.count)
            first = 1
        if (not f.tag or getattr(f, "relief", None)) and not f.is_player and act_s > 0 and not (self._hot is not None and g.late_activation):
            self._late(g, act_s, "support relief" if f.tag else "activate")                                # they 'depart' on their own schedule, not at mission start
        if getattr(f, "relief", None) and f.relief.get("flag") and not f.is_player:
            self._late_flag(g, f.relief["flag"])                # v0.41.79: a replacement waits hidden until the hook calls it
        if first == 1 and (not f.tag or getattr(f, "relief", None)):   # face the way they are going (in-flight groups spawn pointing north)
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
        kit_ = getattr(f, "kit", "") or ("FLEET" if (f.aircraft == "F-14BU" and f.role in (Role.CAP, Role.SWEEP) and (package.extra or {}).get("setpiece")) else "")      # v0.41.271: 6 Phoenix for the fleet-defence Tomcats
        if not kit_ and f.role == Role.CAS and f.aircraft == "A-10C" and not f.tag and (not f.is_player or o.player_is_ai) and self._cas_floors.get(package.id, 0) > 0:
            kit_ = "GUIDED"                                                   # S31a part A2: an AI A-10 attacking from the high floor carries guided bombs, not Mavericks / unguided cluster (a person's flight keeps the stock CAS loadout)
        load = self.lo.for_role(f.aircraft, f.role, kit_)
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
            if not o.player_is_ai:                                            # v0.41.210 (XO): read the player's own jammer: the F-16C's lamp (Export.lua flag file), or F10 ECM ON / OFF for an FC3 jet
                self._ecm_player = "live" if f.aircraft == "F-16C" else ("f10" if AIRCRAFT[f.aircraft].fc3 else "")
        if not f.tag and not f.is_player and (self._jams.get(names[0]) or f.aircraft in NATIVE_ECM):
            run_t0 = float(push_s)                                            # the jammers run for the attack leg only: PUSH to EGR
            run_t1 = float(next((w.eta_s for w in wps if w.name == "EGR"), (tot_s if tot_s is not None else push_s) + 900))
            if o.ecm_script:
                for un_ in names:
                    self._jamw[un_] = (run_t0, run_t1)
            if f.is_player and f.aircraft == "F-14BU":
                u.set_property("INSAlignmentStored", True)
        g.set_skill(getattr(Skill, ai_skill(self.o, "blue", self.d), Skill.High))
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
            czone_ = self._clear_zone(cap_zone, package, hold=(wps[1].x, wps[1].y) if len(wps) > 1 and f.tag in ("BASECAP", "CVCAP") else None)
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
                # v0.41.120 (XO 2026-10-23 run: red's pairs held 24 nm from the F-14 station, outside its 15 nm circle, and nobody fired): the circle also tries to
                # reach TARCAP_FWD_NM past the station toward red's nearest patrol station or fighter base (last in the list: the launch points and the station
                # come first, and the circle is never bigger than TARCAP_COVER_MAX_NM)
                fpts_ = []
                thr_ = self._red_approach(stw.x, stw.y) if stw.action == "TARCAP" else None
                fwd_nm_ = {ObjectiveType.CAS: TARCAP_FWD_CAS_NM, ObjectiveType.STRIKE: TARCAP_FWD_STRIKE_NM}.get(package.objective.type, TARCAP_FWD_NM)
                if thr_ is not None and dist(stw.x, stw.y, *thr_) > fwd_nm_ * NM:
                    fpts_ = [offset(stw.x, stw.y, bearing(stw.x, stw.y, *thr_), fwd_nm_ * NM)]
                # v0.41.138 (XO 2026-10-27, engagement circles): the circle meets the nearest BARCAP circle (a point just inside its edge, listed after the
                # station and before the forward point, so the shooters and the station come first and the reach toward red is what gives way). A TARCAP
                # is wanted at the sweep size for its type (25 nm long-range shooters, 15 nm the rest); the launch points still make it bigger.
                bpts_, want_ = [], COVER_ZONE_NM
                if stw.action == "TARCAP":
                    want_ = A2A_ZONE_NM[f.aircraft in LONG_RANGE_A2A]
                    pkg_zone_ = package.objective.type in (ObjectiveType.CAS, ObjectiveType.STRIKE)      # v0.41.185: protects the package, does not hunt
                    if pkg_zone_:
                        want_ = min(want_, TARCAP_PKG_ZONE_NM)
                    bz_ = [] if pkg_zone_ else [z_ for z_ in getattr(self, "_barcap_zones", []) if dist(stw.x, stw.y, z_[0], z_[1]) / NM > z_[2] - TARCAP_BARCAP_OVERLAP_NM]
                    if bz_:
                        bx_, by_, br_ = min(bz_, key=lambda z_: dist(stw.x, stw.y, z_[0], z_[1]) / NM - z_[2])
                        bpts_ = [offset(bx_, by_, bearing(bx_, by_, stw.x, stw.y), max(0.0, br_ - TARCAP_BARCAP_OVERLAP_NM) * NM)]
                zone_ = self._cover_circle(list(lp_) + [(stw.x, stw.y)] + bpts_ + fpts_, (cx_, cy_), package, want_, bearing(cx_, cy_, stw.x, stw.y),
                                           long_only=True, max_nm=TARCAP_COVER_MAX_NM)
                cover_lo_ = True            # v0.41.42 (XO): the circle takes in the shooters first; only an SA-10 keeps it out (an SA-11 / SA-6 no longer pushes it off the launch points)
            zct_ = self._limit_engage(g, 0, hold_end, self._clear_zone(zone_, package, long_only=cover_lo_))
            if stw.action in ("SWEEP", "ESCORT") and hold_end is not None and stw.eta_s - ENGAGE_LEAD_S > 0 and hasattr(zct_, "start_after_time"):
                zct_.start_after_time(int(stw.eta_s - ENGAGE_LEAD_S))      # v0.41.314 (XO 2026-11-06 run: the sweep's engage zone was live from takeoff, it ran down the Su-27s at 880 kt, 250 km out, hit bingo, went home 14 min before the TOT)
            hold_ = None
            if hold_end is not None:
                hold_ = {"cts": [zct_], "starts": [], "tgt": (geom.tx, geom.ty), "end": int(hold_end), "eta": int(stw.eta_s),
                         "gate_s": self._gate_slack_s(package),     # v0.41.315: the strikers may sit at a gate this long before TOT; the cover stays for it
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
                lp_ = self._raid_launch(package, (cw_.x, cw_.y))             # v0.41.248: a fleet raid fires from its launch point: the leash takes it in
                if lp_ is not None:
                    dx_, dy_ = lp_
                    ipz_ = ((getattr(self, "_rsp", {}).get(package.id) or {}).get("ip") or {}).get("ip")
                    if ipz_ is not None:                                         # v0.41.265: the circle that opens at the dash is round the intercept point, where the dash ends
                        dx_, dy_ = ipz_
                zone_ = self._cover_circle([(cw_.x, cw_.y), (dx_, dy_)], ((cw_.x + dx_) / 2, (cw_.y + dy_) / 2), package,
                                           A2A_ZONE_NM[f.aircraft in LONG_RANGE_A2A], bearing(cw_.x, cw_.y, dx_, dy_))
                dash_ = (getattr(self, "_rsp", {}).get(package.id) or None) if lp_ is not None else None
                if dash_ is not None:
                    # v0.41.256 (XO 2026-11-03: the Tomcats were killed by the SAMs and the missiles got through; "the gating perfect"): until the SEAD's verdict the
                    # interceptors fight only inside a SAM-clear circle round their leashed station, where the Kh-22s come to them. The DASH flag (the site's tracking
                    # radars dead, or the wait after the HARMs, see `_raid_sead_prep`) then swaps it for the full circle out to the launch point: they cross, as fast as they can.
                    if RAID_F14_HOLD:
                        hw_ = next((w for w in wps if w.action == "HOLD"), cw_)              # an F-14's hold is its own point (`_raid_f14_shape`)
                        hold_ = self._clear_zone((hw_.x, hw_.y, A2A_ZONE_NM[f.aircraft in LONG_RANGE_A2A]), package)
                        et_ = self._limit_engage(g, 0, stop, hold_)
                        if et_ is None:
                            et_ = task.ControlledTask(task.EngageTargetsInZone(mapping.Vector2(hold_[0], hold_[1]), int(hold_[2] * 1852), [task.Targets.All.Air]))
                            g.points[0].tasks.insert(0, et_)
                        if isinstance(et_, task.ControlledTask):
                            et_.stop_if_user_flag(dash_["flag"], True)
                    dash_t = task.ControlledTask(task.EngageTargetsInZone(mapping.Vector2(zone_[0], zone_[1]), int(zone_[2] * 1852), [task.Targets.All.Air]))
                    if RAID_F14_HOLD:
                        dash_t.start_if_user_flag(dash_["flag"], True)                     # (v0.41.276: with no hold the full circle, SAM-clear, is on from the start)
                    if stop is not None:
                        dash_t.stop_after_time(max(60, int(stop)))
                    g.points[0].tasks.insert(1 if RAID_F14_HOLD else 0, dash_t)
                else:
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

    def _raid_sead_any(self, package, f) -> bool:
        """A SEAD flight of the carrier-raid setpiece, yours or the AI's."""
        return (package.objective.type == ObjectiveType.FLEET_DEFENSE and f.role == Role.SEAD and not f.tag
                and package.objective.target_id in self.state.bases and bool((package.extra or {}).get("setpiece")))

    def _raid_sead(self, package, f) -> bool:
        """v0.41.255: a SEAD flight of the carrier-raid setpiece (AI): it does not fly the fleet's route but its own HARM job."""
        return self._raid_sead_any(package, f) and not f.is_player

    def _raid_player_sead(self, package) -> bool:
        pf = package.player_flight
        return pf is not None and self._raid_sead_any(package, pf)

    def _raid_player_site(self, package, geom, pf):
        """v0.41.284: the raid site the player's SEAD flight goes for: the n-th SEAD flight takes the n-th site, as for the AI flights. None when no site reaches the raid."""
        flights = [f_ for f_ in package.flights if self._raid_sead_any(package, f_)]
        sites, _ip = self._raid_sead_sites(package, geom, self._raid_hold_xy(package, geom))
        sites = sites[:max(1, len(flights))]
        if not sites:
            return None
        return sites[flights.index(pf) % len(sites)]

    def _raid_sead_geom(self, package, f, site):
        """The stand-in SEAD package and its geometry for one raid SEAD flight (yours or the AI's) on `site`. -> (sp, g2)."""
        from .models import Objective
        st = self.state
        sp = copy.copy(package)
        sp.objective = Objective(f"{package.objective.id}-sead", ObjectiveType.DEAD, site.id, package.objective.priority, "SEAD for the raid intercept", "SEAD")
        sp.flights = [f]
        base, spec = st.bases[f.base_id], AIRCRAFT[f.aircraft]
        tx, ty = site.x, site.y
        mshl = tm.safe_marshal(st, (base.x, base.y), bearing(base.x, base.y, tx, ty), (tx, ty))
        g2 = make_geometry(base.x, base.y, tx, ty, spec.profile, mshl, carrier=base.kind == BaseKind.CARRIER)
        g2.egr = (tm.first_safe_egress(st, tx, ty, g2.hdg, {site.id}) or tm.safe_egress(st, tx, ty, g2.hdg, spec.profile.egress_nm, tm.cluster_ids(site)) or g2.egr)
        g2.tier = self._pick_tier(g2, Role.SEAD, spec.profile, tx, ty, {site.id})
        self._flight_plans(g2, sp, tx, ty, {site.id})
        return sp, g2

    def _raid_sead_site(self, package, geom):
        """The live red SAM site to put the HARMs on: the one whose reach takes in the raid's launch point (the long-range one first, then the nearest).
        None when no site reaches it. Judgment call: reach + 10 nm margin (no source, a HARM shot is fired from outside the ring)."""
        pts = [Wpt("CAP1", geom.cap1[0], geom.cap1[1], 0, 0, "", "CAPORBIT"), Wpt("CAP2", geom.cap2[0], geom.cap2[1], 0, 0)]
        self._leash_fleet_cap(pts, 0, geom.tx, geom.ty)
        lp = self._raid_launch(package, (pts[0].x, pts[0].y)) or (geom.tx, geom.ty)
        best = []
        for a in self.state.assets.values():
            rng = tm.RANGE_NM.get(a.variant, 0)
            if a.kind != AssetKind.SAM or a.destroyed or a.health <= 0.25 or rng < 12:
                continue
            d_ = dist(a.x, a.y, lp[0], lp[1]) / NM
            if d_ <= rng + 10:
                best.append((0 if a.variant in tm.UMBRELLA_VARIANTS else 1, d_, a.id))
        best.sort()
        return self.state.assets[best[0][2]] if best else None

    def _raid_sead_sites(self, package, geom, hold) -> tuple:
        """v0.41.287 (XO 2026-11-04): the sites the raid SEAD goes for: every one that threatens the intercept line (`_raid_blockers`, now every
        threatening site, not just the minimum to open a lane), else the old single site (the one whose reach takes in the launch point).
        -> (sites, intercept result with them ignored or None)."""
        ids, ip = self._raid_blockers(package, geom, hold)
        sites = [self.state.assets[i] for i in ids if i in self.state.assets]
        if not sites:
            one = self._raid_sead_site(package, geom)
            sites = [one] if one is not None else []
        return sites, ip

    def _raid_f14_shape(self, wps, k1, o12, ip=None, idx=0, f14=True):
        """v0.41.256 (XO 2026-11-03: the F-14 is what the intercept was made for): a raid CAP holds at its leashed station (HOLD, RAID_F14_HOLD_FT, slow), then at the push
        (the gate's own latest time, or earlier when the flag sets) dashes high and fast (PUSH, IP) to TGT and orbits there. `o12`: the racetrack as it was before the leash.
        v0.41.265 (XO 2026-11-04: the dash went to the point the F-14 already held): `ip` is the intercept point on the bombers' way in (`_raid_intercept`): the dash flies its
        lane (bends round the SAM circles), TGT is the point, CAP2 the short leg across the bombers' line. The Hornets and Eagles fly it too (`f14` False: slower dash); `idx` stacks
        a package's flights (1,000 ft and 1.5 nm apart). -> the new waypoint list."""
        a = wps[k1]
        (x1, y1), (x2, y2) = o12
        dft = RAID_F14_DASH_FT + (idx * 1000)
        dkt = RAID_F14_DASH_KTS if f14 else RAID_OTHER_DASH_KTS
        lat = (idx % 4 - 1.5) * 1.5 * NM
        if ip is not None:
            lane = list(ip["lane"]) + [ip["ip"]]
            hb = bearing(a.x, a.y, lane[0][0], lane[0][1])
            d = dist(a.x, a.y, lane[0][0], lane[0][1])
        else:
            lane = None
            hb = bearing(a.x, a.y, x1, y1)
            d = dist(a.x, a.y, x1, y1)
        hold = Wpt("HOLD", a.x, a.y, RAID_F14_HOLD_FT + idx * 1000, RAID_F14_HOLD_KTS, "Hold here, outside the SAM rings; SEAD is working the radars. Push at the time or the AWACS call", "HOLD")
        mid = [Wpt("PUSH", *offset(a.x, a.y, hb, min(1 * NM, d)), dft, dkt)]
        hold_l = [hold] if RAID_F14_HOLD else []          # v0.41.276: no hold: the route goes straight from the climb-out onto the lane
        if lane is not None:
            vias = {(round(v[0]), round(v[1])): v[2] for v in ip.get("via", [])}       # v0.41.268: the field the bent lane goes over
            for q in lane[:-1]:
                vn = vias.get((round(q[0]), round(q[1])))
                mid.append(Wpt("BASE", q[0], q[1], dft, dkt, "Over " + vn + ", then on to the intercept point") if vn else Wpt("AVD", q[0], q[1], dft, dkt, "Around a SAM site"))
            px, py = lane[-1]
            pb = bearing(*(lane[-2] if len(lane) > 1 else (a.x, a.y)), px, py)
            px, py = offset(px, py, pb + 90, lat)
            if dist(*(lane[-2] if len(lane) > 1 else (a.x, a.y)), px, py) > 8 * NM:
                mid.append(Wpt("IP", *offset(px, py, pb + 180, 3 * NM), dft, dkt))
            tgt = Wpt("TGT", px, py, dft, 450, "Intercept point, on the bombers' way in: engage them at max range", "CAPORBIT")
            q2 = offset(ip["ip2"][0], ip["ip2"][1], pb + 90, lat)
            cap2 = Wpt("CAP2", q2[0], q2[1], dft, 450)
            return wps[:k1] + hold_l + mid + [tgt, cap2] + wps[k1 + 2:]
        if d > 8 * NM:
            mid.append(Wpt("IP", *offset(x1, y1, hb + 180, 3 * NM), dft, dkt))
        tgt = Wpt("TGT", x1, y1, dft, 450, "Intercept point: engage the bombers at max range", "CAPORBIT")
        cap2 = Wpt("CAP2", x2, y2, dft, 450)
        return wps[:k1] + hold_l + mid + [tgt, cap2] + wps[k1 + 2:]

    def _rush_speeds(self, wps) -> None:
        """v0.41.256 (XO 2026-11-03: get the SEADs to their targets as fast as they can): every point before the objective flies at least RAID_RUSH_KTS."""
        tw = objective_wp(wps)
        for w in wps:
            if w is tw:
                break
            if w.speed_kts > 0:
                w.speed_kts = max(w.speed_kts, RAID_RUSH_KTS)

    def _raid_sead_route(self, package, f, site, cap_tot_s):
        """The stand-in SEAD package, geometry and rush route of one raid SEAD flight on `site`. -> (sp, g2, push, tg, rtb)."""
        st = self.state
        sp, g2 = self._raid_sead_geom(package, f, site)
        base, spec = st.bases[f.base_id], AIRCRAFT[f.aircraft]
        pw = plan_route(Role.SEAD, (base.x, base.y), g2, spec.profile, is_player=True, tanker_xy=None, keep_out=self._umbrella_keep(sp))
        self._rush_speeds(pw)
        assign_times(pw, 0.0)                                    # as early as the route allows: no hold
        pu = next((w for w in pw if w.name == "PUSH"), None)
        push = (pu.eta_s if pu is not None else 0.0) + 60.0      # (the flight route keeps a minute of margin before the push)
        assign_times(pw, 0.0, push)
        tg = objective_wp(pw) or pw[-1]
        sh = ((-float(RAID_SEAD_DONE_S) if self._raid_scripted(package) else float(cap_tot_s) - RAID_SEAD_LEAD_S)) - tg.eta_s       # the HARMs land RAID_SEAD_LEAD_S before the interceptors are due on station; a pair that would be late is
        for w in pw:                                                  # already underway at the start (an earlier package folded in), flying the rush speeds
            w.eta_s += sh
        push += sh
        eg = next((w for w in pw if w.name == "EGR"), pw[-1])
        rtb = eg.eta_s + leg_seconds(eg, Wpt("RTB", base.x, base.y, 0, 300))
        return sp, g2, push, tg, rtb

    def _raid_scripted(self, package) -> bool:
        """v0.41.283 (XO 2026-11-04): the SEAD is a scripted result, already done when the mission starts, unless the player flies the raid SEAD himself."""
        pf = package.player_flight
        return pf is None or pf.role != Role.SEAD

    @staticmethod
    def _raid_prep_rec(package) -> bool:
        """v0.41.357 (Phase 10b part 2): the carrier raid was planned with the SEAD prep of the turn before on record (`packages.build` sets `extra["prep_rec"]`). A save with no record: False, the old scripted result."""
        return bool((package.extra or {}).get("prep_rec"))

    def _raid_prep_standing(self, package, geom, manifest):
        """v0.41.357 (Phase 10b part 2, XO decision 32: the intercept always takes the pre-mission's result): the SAM picture of the raid mission is what the prep left in the assets.
        A site the prep destroyed is not built, one it suppressed is built blind (`_spawn_site`: `a.suppressed`, the radars are gone), one it did not touch is built live and shoots. No
        scripted blow-up, no SEAD seats in the raid package. The live threatening sites (`_raid_blockers`: live, unsuppressed, reach on the bombers' lane) are built here, first, so the unit
        limit never trims them (`_spawn_raid` builds the other SAM sites after the flights); the interceptors' lane is still worked out as if they were out (`_raid_blockers` `ignore`): they
        fly it and take the fire. The raiders' flag is set at second 5, as the scripted result did (the SEAD was flown, or resolved, the turn before). -> the `_rsp` record (`flag`, `t_flag`, `ip`, `sites`)."""
        from .models import Objective
        ids, ip_ = self._raid_blockers(package, geom, self._raid_hold_xy(package, geom))
        sites = [self.state.assets[i] for i in ids if i in self.state.assets]
        for st_ in sites:
            sp = copy.copy(package)
            sp.objective = Objective(f"{package.objective.id}-live", ObjectiveType.DEAD, st_.id, package.objective.priority, "SAM site the prep left standing", "SEAD")
            sp.flights = []
            self._spawn_opfor_ground(sp, st_.x, st_.y, manifest, [(st_.x, st_.y), (st_.x, st_.y)])
        if ip_ is None:
            self.warns.append("Raid interceptors: no SAM-clear intercept point on the bombers' way in; they hold at their station.")
            if not sites:
                return None
        self._flag_n += 1
        flag = self._flag_n
        t2 = triggers.TriggerOnce(comment="raid: the prep stands, interceptors cross")
        t2.add_condition(condition.TimeAfter(5))
        t2.add_action(action.SetFlag(flag))
        t2.add_action(action.DoScript(String('trigger.action.outTextForCoalition(coalition.side.BLUE, "AWACS: Raid inbound. Interceptors, cleared to push toward the launch point.", 15)')))
        self.m.triggerrules.triggers.append(t2)
        return {"site": sites[0] if sites else None, "sites": sites, "agm88_s": 0.0, "flag": flag, "t_flag": 5.0, "ip": ip_}

    def _raid_script_kills(self, grp, radars, comment) -> None:
        """At second 2 the site's tracking radars and RAID_SCRIPT_KILL of its other units blow up (the HARMs and the strike that already happened). At least one unit is left. OLD SAVES ONLY (v0.41.357): a raid planned with the prep record never gets here (`_raid_prep_standing`)."""
        units = list(grp.units) if grp is not None else []
        rad_ = {id(u) for u in radars}
        rest = [u for u in units if id(u) not in rad_]
        n_ = int(len(rest) * RAID_SCRIPT_KILL)
        names = [u.name for u in radars] + [u.name for u in rest[:n_]]
        if len(names) >= len(units):
            names = names[:max(0, len(units) - 1)]
        if not names:
            return
        lua = "".join(f'local u=Unit.getByName("{n_.replace(chr(34), "")}") if u then trigger.action.explosion(u:getPoint(), 300) end ' for n_ in names)
        tr = triggers.TriggerOnce(comment=comment)
        tr.add_condition(condition.TimeAfter(2))
        tr.add_action(action.DoScript(String(lua)))
        self.m.triggerrules.triggers.append(tr)

    def _raid_sead_prep(self, package, geom, cap_tot_s, manifest):
        """v0.41.256, once per carrier-raid mission, before its flights are built: the SAM site the raid SEAD goes for (built live now), when the HARMs land, and the
        DASH flag the interceptors wait on. The flag is set when the site's tracking radars are all dead, or RAID_DASH_WAIT_S after the HARMs (and never before the
        interceptors are due on station). -> {"site", "agm88_s", "flag"} or None (no SEAD flight, or no site reaches the launch point)."""
        c_ = self.__dict__.setdefault("_rsp", {})
        if package.id in c_:
            return c_[package.id]
        c_[package.id] = None
        if self._raid_prep_rec(package):                                   # v0.41.357 (Phase 10b part 2): the prep of the turn before stands: no SEAD seats, no scripted result
            c_[package.id] = self._raid_prep_standing(package, geom, manifest)
            return c_[package.id]
        f0 = next((f for f in package.flights if self._raid_sead_any(package, f)), None)
        n_sead = sum(1 for f in package.flights if self._raid_sead_any(package, f))
        setp_ = bool((package.extra or {}).get("setpiece"))
        sites, ip_ = self._raid_sead_sites(package, geom, self._raid_hold_xy(package, geom)) if (f0 is not None or setp_) else ([], None)
        sites = sites[:max(1, n_sead)] if f0 is not None else []          # v0.41.267: one flight per site; a site without a flight is left alone
        if not sites:
            # v0.41.290 (XO 2026-11-04: "it's a setpiece, none of the old things matter"): the interceptors' dash to the intercept point does not depend on a SEAD job. With no SAM
            # to work (or no SEAD flight) the point is kept and there is no DASH flag to wait on; before, this returned None and the interceptors held at the station over the water.
            if setp_ and ip_ is not None:
                c_[package.id] = {"site": None, "sites": [], "agm88_s": 0.0, "flag": None, "t_flag": float(cap_tot_s) + 60.0, "ip": ip_}
                return c_[package.id]
            if setp_:
                self.warns.append("Raid interceptors: no SAM-clear intercept point on the bombers' way in; they hold at their station.")
            return None
        site = sites[0]
        base = self.state.bases[f0.base_id]
        scripted = self._raid_scripted(package)
        radars, tg_s = [], 0.0
        for st_ in sites:                                                  # v0.41.267: every site is built live; the dash flag waits for the tracking radars of ALL of them
            sp, g2, push, tg, rtb = self._raid_sead_route(package, f0, st_, cap_tot_s)
            self._spawn_opfor_ground(sp, st_.x, st_.y, manifest, [(base.x, base.y), g2.mshl, g2.push, g2.ip, (st_.x, st_.y), g2.egr])
            tg_s = max(tg_s, tg.eta_s)
            grp = self.groups_by_asset.get(st_.id)
            site_radars = [u for u in (grp.units if grp is not None else []) if str(getattr(u, "type", "")) in TRACK_RADARS]
            radars += site_radars
            if scripted:
                self._raid_script_kills(grp, site_radars, f"scripted SEAD result {st_.id}")
        self._flag_n += 1
        flag = self._flag_n
        if radars:
            t_ = triggers.TriggerOnce(comment="raid SEAD: tracking radars dead, interceptors cross")
            for u in radars:
                t_.add_condition(condition.UnitDead(u.id))
            t_.add_action(action.SetFlag(flag))
            self.m.triggerrules.triggers.append(t_)
        t2 = triggers.TriggerOnce(comment="raid SEAD: wait over, interceptors cross")
        t_flag = 5 if scripted else int(max(tg_s + (RAID_DASH_WAIT_S if package.player_flight is None or not self._raid_player_sead(package) else RAID_PLAYER_WAIT_S), float(cap_tot_s) + 60))          # (scripted: the radars are blown at second 2, the flag follows)
        t2.add_condition(condition.TimeAfter(t_flag))
        t2.add_action(action.SetFlag(flag))
        say_ = String('trigger.action.outTextForCoalition(coalition.side.BLUE, "AWACS: SEAD complete. Interceptors, cleared to push toward the launch point.", 15)')
        t2.add_action(action.DoScript(say_))
        self.m.triggerrules.triggers.append(t2)
        if radars:
            t_.add_action(action.DoScript(say_))
        if ip_ is None:                                                    # v0.41.265: where the interceptors dash to, on the bombers' way in (v0.41.267: lane worked out as if the sites above were dead)
            self.warns.append("Raid interceptors: no SAM-clear intercept point on the bombers' way in; they hold at their station.")
        c_[package.id] = {"site": site, "sites": sites, "agm88_s": tg_s, "flag": flag, "t_flag": float(t_flag), "ip": ip_}
        return c_[package.id]

    def _spawn_raid_sead(self, package, f, plan, geom, idx, cap_tot_s, manifest, despawn):
        """v0.41.255 (XO 2026-11-03, the carrier-raid run: the Tomcats flew into the Sukhumi SA-10): the SEAD flights of the setpiece are flown as a normal
        SEAD job on the site covering the raid's launch point (its own geometry, HARM point and tasks, in a stand-in DEAD/SEAD package). v0.41.256: they go
        as fast as they can (RAID_RUSH_KTS, no wait for the interceptors; the interceptors wait for them instead, see `_raid_sead_prep`).
        -> (group, HARM time) or (None, None) when no site reaches the launch point."""
        prep = self._raid_sead_prep(package, geom, cap_tot_s, manifest)
        if prep is None or not prep.get("sites"):          # (v0.41.290: a prep with no site only carries the intercept point)
            return None, None
        f.rush = True
        ordn = [f_ for f_ in package.flights if self._raid_sead_any(package, f_)].index(f)          # v0.41.267: the n-th SEAD flight takes the n-th site
        sites = prep.get("sites") or [prep["site"]]
        if ordn >= len(sites):                                                                       # v0.41.284 (XO 2026-11-04: "if multiple SAMs then SEAD is sized to it"): no site, no flight
            return None, None
        sp, g2, push, tg, rtb = self._raid_sead_route(package, f, sites[ordn % len(sites)], cap_tot_s)
        return self._spawn_flight(sp, f, plan, g2, None, None, push, tg.eta_s, rtb, idx, manifest, despawn)

    def _bomb_task(self, package, w):
        """The bombing task at a BOMB waypoint. v0.41.254: a runway strike (a STRIKE with aim RUNWAY) uses DCS's BombingRunway on the target field, so the
        flight lays its bombs along the strip; every other strike bombs the point."""
        o_ = package.objective
        a_ = self.state.assets.get(o_.target_id)
        ap_ = self.t.airports.get(a_.airport) if (o_.aim == "RUNWAY" and a_ is not None and a_.airport) else None
        if ap_ is not None:
            return task.BombingRunway(airport_id=ap_.id, expend=task.Expend.All, group_attack=True)
        if o_.type == ObjectiveType.COUNTER_AIR and o_.aim not in ("SWEEP", "STANDOFF") and w.name != "SLAM":
            # v0.41.316 (XO 2026-11-06: cluster bombs are not aimed at single things, and the AI F-16s with CBU-103s flew over the ramp without a release): an area
            # (carpet) attack over the middle of the parked jets, as long as the ramp is wide (judgment call, clamped; DCS behaviour on static aircraft unverified)
            pts_ = list(getattr(self, "_ramp_pts", []) or [])
            if pts_:
                cx_, cy_ = sum(q[0] for q in pts_) / len(pts_), sum(q[1] for q in pts_) / len(pts_)
                span_ = max((dist(p[0], p[1], q[0], q[1]) for p in pts_ for q in pts_), default=0.0)
            else:
                # v0.41.328 (XO's run: the strike flights are built BEFORE the parked jets spawn, so this list is empty here and the aim fell back to the airfield point, 1.2 km short
                # of the jets): the middle of the field's real parking slots, and the line of the slots within `RAMP_CLUSTER_M` of it for the heading
                ra_ = self.state.assets.get(o_.target_id)
                r_ = self._ramp_xy(ra_) if ra_ is not None else None
                if r_ is not None:
                    cx_, cy_ = r_
                    ap2_ = self.t.airports.get(ra_.airport) if getattr(ra_, "airport", None) else None
                    pts_ = [(q.position.x, q.position.y) for q in (ap2_.parking_slots if ap2_ else []) if q.airplanes and dist(q.position.x, q.position.y, cx_, cy_) <= RAMP_CLUSTER_M]
                    span_ = max((dist(p[0], p[1], q[0], q[1]) for p in pts_ for q in pts_), default=0.0)
                else:
                    cx_, cy_ = w.aim or (w.x, w.y)
                    span_ = 0.0
            # v0.41.323 (XO's L3 run: the carpet task's aim point was the ramp, but the CBU jets looped 6 to 20 km off it and dropped on the depot guards): the plain point
            # bomb task at the middle of the ramp, the same task that put the GBU-31s on their aim point. The cluster bombs' bomblets cover the ramp. `span_` is unused now.
            # v0.41.326 (XO 2026-11-06: cover more of the ramp): the pass runs ALONG the line of parked jets, so one run lays the bombs down its length. DCS takes one aim point and
            # one attack heading per task (no per-jet points, no release spacing from a script). Heading = the bearing between the two jets furthest apart (x north, y east),
            # only when the ramp is longer than `RAMP_AXIS_MIN_M` (judgment call); otherwise the plain point as before. Not seen in DCS.
            dir_ = None
            if pts_ and span_ >= RAMP_AXIS_MIN_M:
                p1_, p2_ = max(((p, q) for p in pts_ for q in pts_), key=lambda pq: dist(pq[0][0], pq[0][1], pq[1][0], pq[1][1]))
                dir_ = int(round(math.degrees(math.atan2(p2_[1] - p1_[1], p2_[0] - p1_[0])))) % 360
            bt2_ = task.Bombing(self._pt(cx_, cy_), weapon_type=task.WeaponType.Auto, expend=task.Expend.All, group_attack=True, direction=dir_)
            self._ramp_tasks.append(bt2_)
            return bt2_
        wt_ = task.WeaponType.CruiseMissile if w.name == "SLAM" else task.WeaponType.Auto         # v0.41.302: the Standoff Strike's SLAM-ER is a missile; XO's run: the default filter fired nothing
        return task.Bombing(self._pt(*(w.aim or (w.x, w.y))), weapon_type=wt_, expend=task.Expend.All, group_attack=True)       # v0.41.299: a release point (JDAM, SLAM-ER) bombs the target, not itself

    def _slam_aims(self, package, w) -> list:
        """v0.41.309 (XO 2026-11-05: "how do we make the 18 just focus on their target? one hit the bunker, the rest targeted god knows what"): the aim points of a SLAM-ER
        launch: up to `SLAM_AIMS` of the target site's buildings (the first one, then the one furthest from it), a missile each. A single Bombing task on the site's centre
        sent one missile at the guard vehicles and left the rest to hunt radars under weapons free (XO's run). No buildings known: the waypoint's own aim point."""
        spots = list(self._bld_xy.get(package.objective.target_id) or [])
        if len(spots) > SLAM_AIMS:
            far = max(spots[1:], key=lambda s_: dist(s_[0], s_[1], spots[0][0], spots[0][1]))
            spots = [spots[0], far][:SLAM_AIMS]
        return spots or [tuple(w.aim or (w.x, w.y))]

    def _bomb_tasks(self, package, w) -> list:
        """The bombing tasks of a BOMB waypoint: one, except a SLAM-ER launch (`_slam_aims`: one Bombing task per aim point, one missile each, over once `SLAM_ATTACK_S` has passed)."""
        if w.name != "SLAM":
            return [self._bomb_task(package, w)]
        out = []
        for x_, y_ in self._slam_aims(package, w):
            ct_ = task.ControlledTask(task.Bombing(self._pt(x_, y_), weapon_type=task.WeaponType.CruiseMissile, expend=task.Expend.One, group_attack=True))
            if w.eta_s is not None:
                ct_.stop_after_time(int(w.eta_s + SLAM_ATTACK_S))
            out.append(ct_)
        if w.eta_s is not None:
            rf_ = task.ControlledTask(task.OptROE(task.OptROE.Values.ReturnFire)); rf_.start_after_time(int(w.eta_s + SLAM_ATTACK_S))      # then no more hunting, as with the JSOWs
            out.append(rf_)
        return out

    def _attach_waypoints(self, package, f, g, wps, first, ai_a2g, ai_sead, run_t0, push_s, tot_s, stop, hold_end, stw, armor, special):
        """Add each route point to the group with its tasks: ETAs, ROE, ECM, fuel, orbits, bombs, JSOW, CAS, SEAD attacks."""
        o = self.o
        pt = self._pt
        # v0.41.322 (XO 2026-11-06: the AI F-16s with GBU-31 / CBU-103 crossed the target at 20,000 ft and never released): a waypoint's task only starts when the jet
        # reaches that waypoint, and the TGT waypoint IS the target, so the bomb task started with no run-in left. DCS forum threads on AI bombing runs (forum.dcs.world
        # topic 241006, 369730: "task on the IP, 25 to 30 nm out") put it on the approach point. So an AI striker's bomb task sits on the IP, aimed at the target.
        ip_tgt_ = None
        ca_ramp_ = package.objective.type == ObjectiveType.COUNTER_AIR and package.objective.aim not in ("SWEEP", "STANDOFF")      # v0.41.325
        if ai_a2g and f.role == Role.STRIKE and not f.tag and package.objective.aim != "STANDOFF":       # S27 (runs 13-01-59 and 13-11-32: the runway strikers turned 8 to 12 km short of TGT and dropped nothing): runway strikes take the IP rule too, BombingRunway starts on the IP
            ws_ = list(wps[first:])
            tg_i = next((k for k, w_ in enumerate(ws_) if w_.name == "TGT" and w_.action == "BOMB"), None)
            if tg_i is not None and tg_i >= 1 and ws_[tg_i - 1].name in ("IP", "LOW") and ws_[tg_i].eta_s is not None:
                ip_tgt_ = ws_[tg_i]
        # Stage C (2026-11-11, run 00-06-03): same fault for AI CAS: Hawg 1 passed 3 nm from its column and fired nothing, because AttackGroup / EngageTargetsInZone
        # on TGT start only overhead, with no run-in. Judgment (same shape as the strike fault above, not an ED statement): they sit on the IP, stop times still from the TGT ETA.
        ip_cas_ = None
        if ai_a2g and f.role == Role.CAS and not f.tag:
            ws_ = list(wps[first:])
            tg_i = next((k for k, w_ in enumerate(ws_) if w_.name == "TGT" and w_.action == "CAS"), None)
            if tg_i is not None and tg_i >= 1 and ws_[tg_i - 1].name in ("IP", "LOW") and ws_[tg_i].eta_s is not None:
                ip_cas_ = ws_[tg_i]
                ip_cas_ip_ = ws_[tg_i - 1]
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
                        wp.tasks += self._bomb_tasks(package, w)
                    continue
            if ai_a2g and w.name == "EGR":
                wp.tasks.append(task.OptROE(task.OptROE.Values.ReturnFire))                      # and no chasing on the way home either
                if f.aircraft in SHOOTS_BACK:
                    wp.tasks.append(task.OptRestrictAirToAirAttack(False))                       # self-defence only: return fire, at whoever shoots
            if ai_a2g and not ai_sead and w.action in ("BOMB", "CAS"):
                # S30 (XO run 2026-11-11 14-07-37: two of four SLAM-ERs went at radiating EWRs under Weapon Free): the SLAM point is Open Fire, designated target only (not flown)
                wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire if (w.action == "BOMB" or w.name == "SLAM") else task.OptROE.Values.WeaponFree))   # the ground target; aircraft stay off limits (restricted); v0.41.396: every AI strike attacks its designated point only (runs 17-09-47, 18-24-28: Weapon Free bombed depots and SAMs near the IP); CAS stays Weapon Free
            if ip_tgt_ is not None and w.name == "IP":
                wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))   # v0.41.322: the attack starts here, on the way in; v0.41.396: designated target only for every strike (XO: no hunting)
                bip_ = task.ControlledTask(self._bomb_task(package, ip_tgt_))
                bip_.stop_after_time(int(ip_tgt_.eta_s + LATE_ATTACK_S)); wp.tasks.append(bip_)
            if ip_cas_ is not None and w is ip_cas_ip_:
                wp.tasks.append(task.OptROE(task.OptROE.Values.WeaponFree))           # Stage C: the attack starts here, on the way in
                self._cas_tasks(wp, ip_cas_, armor, tot_s, self._cas_floors.get(package.id, 0))
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
                ct.stop_after_time(int(hold_leave_s(wps, push_s)))
                if getattr(f, "gate_flag", None):
                    ct.stop_if_user_flag(f.gate_flag, True)          # v0.41.256: the raid interceptors' hold ends when the SEAD gate opens
                wp.tasks.append(ct)
            elif w.action == "CAPORBIT":
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH)))
                ct.stop_after_time(stop); wp.tasks.append(ct)
                if f.tag and not getattr(f, "relief", None):
                    self._sup_cts.append(ct)
                    self._ct_flight[id(ct)] = f.callsign
                    bf_ = (self._relief_src.get(f.callsign) or {}).get("bf")
                    if bf_:
                        ct.stop_if_user_flag(bf_, True)              # v0.41.79: the hook sends a pair home when it loses a jet / is winchester / bingo
            elif w.orbit:                                                    # fighters held short of live SAM cover / on their station
                if self._snipe_at.get(id(g)) is w:                              # v0.41.10: on station: maximum-range shots (snipe) from here on
                    wp.tasks.append(task.OptAAMissileAttackRange(task.OptAAMissileAttackRange.Values.MaxRange))
                # v0.41.43: a Circle, not DCS's default Race-Track. A race-track runs from this point to the NEXT waypoint, which here is RTB:
                # 2026-10-20 tracks show Springfield 7 / Hornet 6 flying 57-60 nm from their station to RTB and back (the "north to south" orbit)
                # Phase 8: with CAP2 next, the default Race-Track runs station -> CAP2 and back (that is what it is for); without, the Circle stays
                k_ = next((i_ for i_, x_ in enumerate(wps) if x_ is w), None)
                race_ = k_ is not None and k_ + 1 < len(wps) and wps[k_ + 1].name == "CAP2"
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH)) if race_
                                         else task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct.stop_after_time(hold_end if (w is stw and hold_end is not None) else stop); wp.tasks.append(ct)
                if w is stw and self._holds and self._holds[-1]["end"] == hold_end and ct not in self._holds[-1]["cts"]:
                    self._holds[-1]["cts"].append(ct)
            elif w.action == "BOMB":
                # v0.41.16: the attack is only good until LATE_ATTACK_S after its TOT; later, the flight flies on to its egress and home (the
                # v0.41.14 run: the lead, alone after its wingmen flamed out, bombed 30 min late and met a live SA-6)
                if w.name == "SLAM":
                    wp.tasks += self._bomb_tasks(package, w)
                elif w is not ip_tgt_:                                                   # v0.41.322: that task is on the IP
                    bct_ = task.ControlledTask(self._bomb_task(package, w))
                    bct_.stop_after_time(int(w.eta_s + LATE_ATTACK_S)); wp.tasks.append(bct_)
            elif w.action == "JSOW":
                self._jsow_tasks(wp, f, armor, package, w.eta_s)
            elif w.action == "CAS" and w is not ip_cas_:                     # Stage C: with an IP before it, those tasks are on the IP
                self._cas_tasks(wp, w, armor, tot_s, self._cas_floors.get(package.id, 0))
            elif w.action == "SEAD" and armor is not None:                 # 'armor' is simply the target asset's group here
                self._sead_attack_tasks(package, f, wp, w, armor)
                if w.hold_to is not None:                                   # S38: the HARM point is a hold until the strikers are through (the ARM tasks above stay live: their stops are 180 to 780 s after the point)
                    oc_ = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(SEAD_HOLD_KTS * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                    oc_.stop_after_time(int(w.hold_to)); wp.tasks.append(oc_)

    def _scrub_point(self, package, f, g, base, wps, tot_s):
        """v0.41.223 (XO 2026-10-31): the package scrub's part of the route. Every non-support package flight is recorded for the hook (`self._scrub`); an AI flight also gets a
        SCRUB point before its home leg, the point a scrubbed flight is sent to (the stand-off ABORT point when it already has one). The hook does the rest (debrief.py)."""
        if f.tag or f.role not in (Role.STRIKE, Role.CAS, Role.SEAD, Role.TARCAP, Role.ESCORT, Role.SWEEP) or not wps:
            return
        kind = "M" if f.role in (Role.STRIKE, Role.CAS) else "C" if f.role in (Role.TARCAP, Role.ESCORT, Role.SWEEP) else "O"
        ai = bool(not f.is_player or self.o.player_is_ai)
        to = 0
        if ai:
            from types import SimpleNamespace
            self._route_end[g.name] = SimpleNamespace(x=g.points[-1].position.x, y=g.points[-1].position.y)      # _home_leg builds the recovery point from the route's real end
            if getattr(g.points[-1], "name", "") == "ABORT":
                to = len(g.points)
            else:
                lw = wps[-1]
                bx, by = offset(base.x, base.y, bearing(base.x, base.y, lw.x, lw.y), SCRUB_POINT_NM * NM)
                alt_ = home_leg_ft((lw.x, lw.y), (bx, by), min(lw.alt_ft, 9000))      # clears the ground between the route's last point and here
                g.add_waypoint(self._pt(bx, by), alt_ * FT, 320 * KPH, "SCRUB")
                to = len(g.points)
        self._scrub.append({"pkg": package.id, "grp": g.name, "k": kind, "units": [u.name for u in g.units], "to": to, "ai": ai, "you": bool(f.is_player),
                            "tot": float(tot_s if tot_s is not None else 86400)})

    def _home_floor(self, f, g, wps, rcv_xy, rcv_ft):
        """S33 (XO 2026-11-11, run 14-35-51: Ford 8 flew home down to 295 m past a Tor site and both jets died). An AI fighter flight (TARCAP / escort / sweep / fleet defence;
        never a player's own flight, whose route stays as it is) keeps its height over the live, unsuppressed short-range air defence (SA-15, SA-8, SA-19, AAA, MANPAD: their ring
        from threatmap.RANGE_NM plus HOME_RING_MARGIN_NM) along its way home: route end -> SCRUB -> RCV. One point (HOME_FLOOR_NAME) goes where the way home leaves the last
        ring, at the highest ceiling among the rings it touches (profiles.ENVELOPE) plus HOME_FLOOR_MARGIN_FT, so DCS starts the descent to the RCV only there. A flight already
        above the floor and below that point keeps its height (no climb); one inside the ceiling climbs to the floor. Where a ring reaches past the SCRUB point or the RCV, those
        points are raised to the floor instead (the point goes on the SCRUB -> RCV leg, or nowhere when the ring holds the RCV itself). -> the RCV altitude in ft to use."""
        o = self.o
        if f.tag or f.role not in (Role.TARCAP, Role.ESCORT, Role.SWEEP) or not wps or (f.is_player and not o.player_is_ai):
            return rcv_ft
        a_ = self._route_end.get(g.name)
        if a_ is None:
            return rcv_ft
        pts_ = g.points
        scr_ = pts_[-1] if getattr(pts_[-1], "name", "") == "SCRUB" else None
        path = [(a_.x, a_.y)] + ([(scr_.position.x, scr_.position.y)] if scr_ is not None else []) + [rcv_xy]
        sites = [a for a in self.state.assets.values() if a.kind == AssetKind.SAM and a.variant in HOME_SAM_VARIANTS and not a.destroyed and not a.suppressed]
        rings = [(a.x, a.y, (tm.RANGE_NM.get(a.variant, 0) + HOME_RING_MARGIN_NM) * NM) for a in sites]
        ex = home_floor_exit(path, rings)
        if ex is None:
            return rcv_ft
        ceil_ = max(profiles.ENVELOPE[sites[n].variant][1] for n in ex[3])
        floor_ = ceil_ + HOME_FLOOR_MARGIN_FT
        end_ft = wps[-1].alt_ft
        alt_ = end_ft if ceil_ + 1000 <= end_ft < floor_ else floor_          # a flight already clear of the ceiling does not climb; one under the floor never dives below it
        total_ = sum(math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]) for i in range(len(path) - 1))
        seg_ = ex[1] if scr_ is not None else 0                               # 0 = route end -> SCRUB (-> RCV when there is no SCRUB), 1 = SCRUB -> RCV
        if scr_ is not None and seg_ == 1:
            scr_.alt = max(scr_.alt, alt_ * FT)                                # the ring reaches past the SCRUB point: that point stays high too
        room_ = len(pts_) + 1 + 1 + 1 + 2 <= AIRCRAFT[f.aircraft].profile.max_points          # this point, RCV, the landing and the builder's spare
        if ex[0] >= total_ - 100:
            return max(rcv_ft, alt_)                                          # the ring holds the RCV itself: the floor runs up to it
        if not room_:
            return rcv_ft
        spd_ = scr_.speed if scr_ is not None else 320 * KPH
        g.add_waypoint(self._pt(*ex[2]), alt_ * FT, spd_, HOME_FLOOR_NAME)
        if scr_ is not None and seg_ == 0:
            pts_.insert(len(pts_) - 2, pts_.pop())                            # in front of the SCRUB point (it moved one place down: the hook's "to" follows)
            for r_ in reversed(self._scrub):
                if r_["grp"] == g.name:
                    if r_["to"]:
                        r_["to"] += 1
                    break
        return rcv_ft

    def _home_leg(self, f, g, base, wps, idx, hold_end, stop, special):
        """The way home: the recovery entry point, landing or deck recovery."""
        o = self.o
        pt = self._pt
        if base.kind == BaseKind.AIRFIELD:
            if not f.is_player or o.player_is_ai:
                # v0.41.10: staggered recovery. Each AI flight comes home through its own entry point, 8 nm out on its own bearing and height, so the
                # flights do not all arrive over the field at once (two F-15 wingmen collided low and slow on the way home in two runs)
                lp_ = self._route_end.get(g.name) or g.points[-1].position
                rb_ = bearing(base.x, base.y, lp_.x, lp_.y) + RCV_SPREAD[idx % len(RCV_SPREAD)]
                rx_, ry_ = offset(base.x, base.y, rb_, RCV_NM * NM)
                rcv_alt_ = home_leg_ft((lp_.x, lp_.y), (rx_, ry_), 3000 + 1000 * (idx % 4))      # v0.41.49: the home leg clears the ridges (was a fixed 3,000-6,000 ft)
                rcv_alt_ = self._home_floor(f, g, wps, (rx_, ry_), rcv_alt_)      # S33: an AI fighter stays high over short-range air defence on the way home
                rcvp_ = g.add_waypoint(pt(rx_, ry_), rcv_alt_ * FT, 300 * KPH, "RCV")
                if self._skip_landing(base):          # v0.41.18: recovered at its entry point instead of landing (setting "AI landings: airfields")
                    rcvp_.tasks.append(task.RunScript(f"SQE_RECOVER('{g.name}')"))
                    self._recov_net(g, f, None, base.x, base.y, wps, hold_end, stop)
            if (f.is_player and not o.player_is_ai) or not self._skip_landing(base):
                g.land_at(self.apt[base.id])
            if special:
                g.points[-1].name = "RTBXHB"
        if base.kind != BaseKind.AIRFIELD and base.id in self.ship and (not f.is_player or o.player_is_ai):          # v0.41.132: the player's own flight keeps its route
            lp_ = self._route_end.get(g.name) or g.points[-1].position
            if dist(base.x, base.y, lp_.x, lp_.y) > (CV_RCV_NM + 10) * NM:          # else it is already close: no extra point
                cx_, cy_ = offset(base.x, base.y, bearing(base.x, base.y, lp_.x, lp_.y), CV_RCV_NM * NM)
                g.add_waypoint(pt(cx_, cy_), self._home_floor(f, g, wps, (cx_, cy_), CV_RCV_FT) * FT, 300 * KPH, "RCV")      # S33: the floor over short-range air defence
        if base.kind == BaseKind.AIRFIELD:
            pass
        elif (not f.is_player or o.player_is_ai) and self._skip_landing(base):
            # v0.41.72 (XO 2026-10-21: "pretend they still land, but if the don't-land switch is on they are despawned after a few rounds on their
            # pattern"): an AI flight going home to the boat gets the real Land waypoint tied to the ship, so DCS homes on the moving boat itself (the
            # fixed RTB point of v0.41.17 missed a boat that had steamed on). The hook removes it, counted as landed, once it has been within
            # CV_PATTERN_NM of the boat for CV_PATTERN_S seconds, and a flight that never gets there is recovered after RECOV_STALE_S.
            rtb = g.add_waypoint(pt(base.x, base.y), 600, 300 * KPH, "RTBXHB" if special else "RTB")
            rtb.type, rtb.action = "Land", PointAction.Landing
            rtb.link_unit = rtb.helipad = self.ship[base.id].units[0].id
            self._recov_net(g, f, self.ship[base.id].units[0].name if base.id in self.ship else None, base.x, base.y, wps, hold_end, stop,
                            r_nm=CV_PATTERN_NM, dwell_s=CV_PATTERN_S)
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
                        elif not mid and getattr(p[b], "speed_locked", False):
                            p[b].speed_locked = False        # v0.41.393: two time-locked points side by side (takeoff, PUSH of a sweep with no marshal point): the Editor counts the second one, so its speed is freed
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
        # v0.41.392: a CAP / sweep station (CAP1, action CAPORBIT) is a station too: locked, it followed the locked takeoff or PUSH with nothing between
        # ("Wolf 1: All waypoints (2-2) have locked speed and surrounded by waypoints 1 and 2 with locked time"). The raid's TGT CAPORBIT intercept point stays locked.
        station = w.orbit or w.action == "TARCAP" or (w.action == "CAPORBIT" and w.name == "CAP1")
        locked = w.name == "PUSH" or (w.action in OBJECTIVE_ACTIONS and not station)
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

    def _drive(self, g, via, speed_ms, road: bool = False):
        for q in via:
            g.add_waypoint(mapping.Point(q[0], q[1], self.t), PointAction.OffRoad, speed_ms * 3.6)
        self._ground_orders(g)

    CAS_ROAD_SNAP_M = 1500.0      # v0.41.180 (XO 2026-10-28): a CAS column's start and stop points move onto a road this close (judgment call)

    def _road_pt(self, x, y):
        """v0.41.180: the nearest road point within CAS_ROAD_SNAP_M, else None (no road scan, or no road that close)."""
        from . import roads
        return roads.snap(x, y, self.CAS_ROAD_SNAP_M) if roads.available() else None

    def _drive_road(self, g, via, speed_ms) -> bool:
        """v0.41.180: drive the group to `via` on roads ("On Road": DCS routes it along them, as a column) when each point has a road close by;
        else the old straight off-road drive. -> True when it went by road."""
        pts = [self._road_pt(*q) for q in via]
        if not pts or any(p_ is None for p_ in pts):
            self._drive(g, via, speed_ms)
            return False
        for q in pts:
            g.add_waypoint(mapping.Point(q[0], q[1], self.t), PointAction.OnRoad, speed_ms * 3.6)
        self._ground_orders(g)
        return True

    CAS_APPROACH_M = 4200.0       # v0.41.193 (XO 2026-10-29 run: the columns started 1.7 km apart and fought from second 34, 14 minutes before the CAS TOT; was 2500): v0.41.137: the friendly task force starts at most this far from the contact point (v0.41.170: 6000; XO 2026-10-28 run: it stalled 0.7 km out, 11 min in, and never met the column; judgment call, closer hides the stall)
    CAS_TF_STOP_M = 2700          # v0.41.193: was 1500, so with the red column's 1200 m creep the two finish 1.5 km apart (before: 300 m) and start 4.2 km apart, outside gun range until they arrive. v0.41.179 (XO 2026-10-28; was 400 m): the task force stops this far short of the contact point. Three runs ended with the columns at 190-400 m, in forest, and no fire from either side (DCS trees block ground line of sight, unproven); a test of whether more room lets them fight. Judgment call.
    CAS_TF_SPEED_MARGIN = 1.3     # v0.41.157: the friendly task force drives this much faster than the plan (judgment call, from one DCS run: it took about 36% longer than planned)
    CAS_PATROL_MAX_M = 900.0      # v0.41.190 (XO 2026-10-29 run: the red column and the task force were in gun range at 6 min, the Mavericks came at 14): each column first drives an out-and-back "patrol" leg of at most this length away from the other, so it reaches the meeting at about the CAS TOT (judgment call)
    CAS_PATROL_MIN_M = 150.0      # a shorter leg is skipped
    CAS_ARRIVE_LEAD_S = 60.0      # the columns meet this long before the CAS flight arrives

    def _patrol_via(self, start, away_brg, final, speed_ms, t_arrive):
        """v0.41.190: the route points for a column that must take about t_arrive seconds to get from `start` to `final` at speed_ms: out `away_brg` and back
        (half the extra distance each way, at most CAS_PATROL_MAX_M), then on to `final`. Just [final] when no leg is needed."""
        direct = math.hypot(final[0] - start[0], final[1] - start[1])
        leg = (speed_ms * t_arrive - direct) / 2.0
        if leg < self.CAS_PATROL_MIN_M:
            return [final]
        return [offset(start[0], start[1], away_brg, min(leg, self.CAS_PATROL_MAX_M)), start, final]

    CAS_ENEMY_ADVANCE_M = 1200.0  # v0.41.137: the enemy column creeps this far toward us; it never starts far from the CAS point

    CAS_COAST_M = 150.0           # v0.41.384 (S29): a CAS column's or the JTAC's start, stop and patrol points keep this far from the sea (judgment call; SITE_MARGIN 1500 m would push a coastal column far inland)
    CAS_LAND_SEARCH_M = 6000.0    # v0.41.384: how far a point may be moved to reach land (a column is never thrown further, e.g. across a bay)

    def _cas_land(self, p):
        """v0.41.384 (S29): the point moved onto land (CAS_COAST_M from the sea) when it is in the water or on the beach (nearest 200 m ring with a good point, seacheck.site_ok); the point itself when it is fine or nothing is found."""
        if seac.site_ok(p[0], p[1], self.CAS_COAST_M):
            return (p[0], p[1])
        r_ = 200.0                                                # finer rings than seacheck.snap_to_land's 1 km: a column should move metres, not kilometres off its line
        while r_ <= self.CAS_LAND_SEARCH_M:
            best = None
            for k in range(24):
                a_ = math.radians(k * 15)
                x_, y_ = p[0] + r_ * math.cos(a_), p[1] + r_ * math.sin(a_)
                if seac.site_ok(x_, y_, self.CAS_COAST_M):
                    cd_ = seac.coast_distance(x_, y_)
                    if best is None or cd_ > best[0]:
                        best = (cd_, x_, y_)
            if best is not None:
                return (best[1], best[2])
            r_ += 200.0
        return (p[0], p[1])

    def _leg_on_land(self, a, b, step_m=250.0):
        """v0.41.384: True when the straight leg a -> b stays on land (sampled every step_m)."""
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(d // step_m))
        return all(seac.is_land(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1))

    def _spawn_cas_support(self, package, plan, geom, manifest):
        if not package.jtac:
            return
        r = self.vrng
        # v0.41.137: the CAS TARGET's own group and centre (not "the last armour group spawned": a CAS package also builds the target's defenders,
        # and a garrison or a neighbouring column built after it used to take the place of the target here)
        tid = package.objective.target_id
        cx, cy = self.site_pos.get(tid) or (geom.tx, geom.ty)
        fb = self._nearest_airfield(cx, cy)
        brg = bearing(cx, cy, fb.x, fb.y)                         # towards our side
        tot = float(self.cas_tot or 1500.0)
        t_contact = max(300.0, tot - 15.0)                        # guns are firing as the CAS flight arrives
        dist_run = min(8.0 * t_contact + 1500.0, self.CAS_APPROACH_M)      # the friendly force starts this far from the contact point
        v = max(2.5, min(8.0, (dist_run - self.CAS_TF_STOP_M) / t_contact))   # m/s, a believable advance
        enemy = self.groups_by_asset.get(tid) if tid else None
        static = bool(tid) and self.state.assets[tid].variant == "GARRISON"      # dug in: our troops come to it
        if enemy is not None and not static:
            # v0.41.137: the column stays where the CAS flight is sent. It used to start up to 10 km back and drive 13 km to be at the CAS point
            # at the TOT; any shortfall in DCS's real speed (slopes, a long mixed column, stopping to fight) left it kilometres from the point
            t_arr_ = max(0.0, t_contact - self.CAS_ARRIVE_LEAD_S)
            self._drive_road(enemy, [self._cas_land(q_) for q_ in self._patrol_via((cx, cy), brg + 180, offset(cx, cy, brg, self.CAS_ENEMY_ADVANCE_M), min(v, 3.5), t_arr_)], min(v, 3.5))   # v0.41.190: a patrol leg away from us first; v0.41.384: every point on land
        stop_ = [self._cas_land(offset(cx, cy, brg, 2000 if static else self.CAS_TF_STOP_M))]      # v0.41.384 (S29): on land
        bj_ = r.uniform(-6, 6)
        fx, fy = offset(cx, cy, brg + bj_, dist_run)
        if not static:
            rp_ = self._road_pt(fx, fy)                           # v0.41.180: the task force starts on a road too, and meets the column along it
            if rp_ is not None:
                fx, fy = rp_
        fx, fy = self._cas_land((fx, fy))                         # v0.41.384 (S29, XO 2026-11-11 run: a garrison near the coast put the column afloat)
        if static and not self._leg_on_land((fx, fy), stop_[0]):
            # v0.41.384: the straight off-road leg to the stop crosses water: try other start bearings, keep the first whose leg is dry (else the snapped start)
            for da_ in (10, -10, 20, -20, 30, -30, 45, -45, 60, -60):
                c_ = self._cas_land(offset(cx, cy, brg + bj_ + da_, dist_run))
                if self._leg_on_land(c_, stop_[0]):
                    fx, fy = c_
                    break
        comp = [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(2, 3)), ("M1043_HMMWV_Armament", r.randint(1, 2))]
        sc = ground.blue_scale(self.state, tid or "")          # the friendly force is as strong as Blue is in this sector
        comp = [(n_, max(1, int(round(c_ * sc)))) for n_, c_ in comp]
        g = self._platoon(self.usa, f"Friendly Task Force {package.number}", comp, fx, fy, (int(brg) + 180) % 360, F.Rectangle)
        if g is not None:
            names = []
            for k, u in enumerate(g.units, 1):
                u.name = f"TF{package.number}|{k}"; names.append(u.name)
            # v0.41.157 (XO's 15:38 run: the task force reached the column 12 minutes after the A-10s, then drove 2.5 km past it): it stops CAS_TF_STOP_M (v0.41.179: 1.5 km, was 400 m) short of the
            # contact point (static garrison: 2 km short) and holds, weapons free, so the survivors come to it; and it drives CAS_TF_SPEED_MARGIN faster than the
            # plan, because DCS runs a mixed off-road column about 30% slower (measured in that run)
            v_tf_ = min(8.0, v * self.CAS_TF_SPEED_MARGIN)
            via_ = [self._cas_land(q_) for q_ in self._patrol_via((fx, fy), brg, stop_[0], v_tf_, max(0.0, t_contact - self.CAS_ARRIVE_LEAD_S))]   # v0.41.190: our column also drives a patrol leg (away from the enemy) first; v0.41.384: on land
            if static:
                self._drive(g, via_, v_tf_)
            else:
                self._drive_road(g, via_, v_tf_)
            manifest.add("friendly_ground", tid or "", names)
        jx, jy = self._cas_land(offset(fx, fy, brg + 90, 120))
        jt = self.m.vehicle_group(self.usa, f"Axeman {package.number}-1", _UN.Hummer, mapping.Point(jx, jy, self.t), heading=(int(brg) + 180) % 360, group_size=1)
        jt.units[0].name = f"JTAC-{package.id}"
        p0 = jt.points[0]
        p0.tasks.append(task.FAC(callsign=1, frequency=int(plan.freq("JTAC") * 1e6), modulation=task.Modulation.AM, number=1))
        p0.tasks.append(task.SetInvisibleCommand(True))
        p0.tasks.append(task.SetImmortalCommand(True))
        jt.add_waypoint(mapping.Point(*self._cas_land(offset(cx, cy, brg, 3800)), self.t), PointAction.OffRoad, v * 3.6)

    AGM88_AXES = (0, 15, -15, 30, -30)                        # v0.41.24: degrees the HARM axis may turn off the package's own axis

    JSOW_AXES = (30, -30, 50, -50, 15, -15, 70, -70)       # v0.41.22: degrees off the HARM shooters' axis, tried in this order

    # ---- late activation helper ------------------------------------------------------------------------------------------------
    def _late_flag(self, g, flag):
        g.late_activation = True
        trig = triggers.TriggerOnce(comment=f"support replacement {g.name}")
        trig.add_condition(condition.FlagIsTrue(int(flag)))
        trig.add_action(action.ActivateGroup(g.id))
        self.m.triggerrules.triggers.append(trig)

    def _late(self, g, seconds, label="activate"):
        g.late_activation = True
        trig = triggers.TriggerOnce(comment=f"{label} {g.name}")
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
        geom.launch_nm = SLAM_LAUNCH_NM if (package.objective.type == ObjectiveType.STRIKE and package.objective.aim == "STANDOFF") else 0.0      # v0.41.299: the Standoff Strike's launch distance
        from .packages import is_sweep
        geom.sweep = is_sweep(package.objective)
        geom.cas_floor = profiles.cas_floor(self.state, [geom.ip, (tx, ty), geom.egr]) if package.objective.type == ObjectiveType.CAS else None      # S31a
        self._cas_floors[package.id] = geom.cas_floor[0] if geom.cas_floor else 0
        tid_ = package.objective.target_id
        tt_ = self.state.assets.get(tid_) if tid_ else None
        geom.jsow_keep = [(a.x, a.y, max(AGM88_LAUNCH_NM, JSOW_KEEP_HIGH_NM)) for a in self.state.assets.values()            # every live SA-10 near the target, itself included (v0.41.46: 40 nm, as the loop used to force)
                          if tt_ is not None and a.variant in tm.UMBRELLA_VARIANTS and not a.destroyed and not getattr(a, "suppressed", False)
                          and dist(a.x, a.y, tt_.x, tt_.y) <= (tm.UMBRELLA_KM / 1.852 + AGM88_LAUNCH_NM) * NM]
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
            prof = self._flight_profile(f, package)                                   # v0.41.299: a JDAM / SLAM-ER striker has its own (high, no LOW) profile
            key = (f.role, id(prof))
            if key not in geom.tiers:
                geom.tiers[key] = self._pick_tier(geom, f.role, prof, tx, ty, skip)
            if key in geom.stand or not self.o.fighter_standoff or f.role not in (Role.TARCAP, Role.ESCORT, Role.SWEEP):
                continue
            if package.objective.type in (ObjectiveType.COUNTER_AIR, ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE) and not geom.sweep:
                continue
            # TARCAP and ESCORT roles: a station of their own, for you and for the AI alike (v0.40.1)
            t = geom.tiers[key]
            alt_ = t.alt_ft if t.changed else prof.alt_ft.get(f.role, 20000)
            geom.stand[key] = profiles.station(self.state, pts, alt_, geom.egr)
            if package.objective.type == ObjectiveType.CAS and not geom.sweep and profiles._long_range_threat(self.state, pts[-1], alt_) is not None:
                geom.stand[key] = profiles.cas_station(self.state, pts, alt_, geom.egr)       # v0.41.177: close enough to cover the A-10s
            if geom.sweep:
                geom.stand[key] = self._sweep_station(geom.stand[key], tx, ty, pts[0], package)
            elif f.role in (Role.ESCORT, Role.SWEEP, Role.TARCAP) and any(getattr(x_, "kit", "") in ("JSOW", "SLAM") for x_ in package.flights):      # v0.41.299: the SLAM-ER flight is shepherded the same way
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
                    # v0.41.118 (XO 2026-10-22 run: a red Su-27 pair killed two Hornets at the HARM point 36 nm from the TARCAP and was not engaged for 150 s):
                    # from there the TARCAP moves toward the middle of the shooters' launch points, 1 nm at a time, until it is TARCAP_NEAR_NM from it, never
                    # closer than TARCAP_BEHIND_NM to the JSOW point and never into a SAM ring (the step back's rings, but an SA-10 at SA10_AVOID_NM (35 nm, the reach measured in
                    # the runs) instead of its 48 nm table ring + 5, which held the TARCAP 53 nm from the SA-10 while the HARM point is 36 nm from it)
                    near_nm_ = TARCAP_NEAR_STRIKE_NM if package.objective.type == ObjectiveType.STRIKE else TARCAP_NEAR_NM
                    lps_ = self._launch_pts.get(package.id) or self._launch_points(package, geom)       # the stations are planned before _launch_pts is filled in
                    if lps_:
                        mx_, my_ = sum(q_[0] for q_ in lps_) / len(lps_), sum(q_[1] for q_ in lps_) / len(lps_)
                        while dist(ex_, ey_, mx_, my_) > near_nm_ * NM:
                            nx_, ny_ = offset(ex_, ey_, bearing(ex_, ey_, mx_, my_), 1.0 * NM)
                            if dist(nx_, ny_, jx_, jy_) < TARCAP_BEHIND_NM * NM or not all(dist(nx_, ny_, a_.x, a_.y) > (SA10_STATION_NM * NM if a_.variant in tm.UMBRELLA_VARIANTS else r_) for a_, r_ in sites_):
                                break
                            ex_, ey_ = nx_, ny_
                        # v0.41.119 (XO 2026-10-22: the TARCAP sat on the sea side, about 90 degrees off the way red comes, so it could not snipe): the station is then put
                        # near_nm_ from the shooters' middle on the bearing toward red's nearest patrol station or fighter base, swung off it (15 degrees at a time,
                        # 180 at most, so the clear point nearest the axis) as far as the SAM rings and the JSOW distance force; the station above stays when that is no nearer the axis
                        thr_ = self._red_approach(mx_, my_)
                        if thr_ is not None:
                            ax2_ = axis_station((mx_, my_), thr_, (jx_, jy_), near_nm_, TARCAP_BEHIND_NM,
                                                lambda x_, y_: all(dist(x_, y_, a_.x, a_.y) > (SA10_STATION_NM * NM if a_.variant in tm.UMBRELLA_VARIANTS else r_) for a_, r_ in sites_), (ex_, ey_))
                            if ax2_ is not None:
                                ex_, ey_ = ax2_
                geom.stand[key] = (ex_, ey_, [], dist(ex_, ey_, tx, ty) / NM, False)
        if not geom.sweep:
            self._stagger_stations(geom, package, tx, ty)        # v0.41.139 (XO 2026-10-27): a long-range TARCAP stands behind and to one side of a short-range escort

    RECOV_STALE_S = 1500       # v0.41.71: a homebound AI flight still out this long after its work is done is recovered where it is (XO's 2026-10-21 run: nine Navy jets
                               # followed the tanker for 15 minutes and never landed). A judgment call: the flight home is 5-10 minutes.
    RECOV_NET_NM = 12          # v0.41.25: a homebound AI flight this close to its deck / field counts as recovered, waypoint reached or not

    def _recov_net(self, g, f, cv_unit, x, y, wps, hold_end, stop, r_nm=None, dwell_s=0) -> None:
        """v0.41.25: the safety net for SQE_RECOVER. A flight sent home early (bingo, out of missiles) flies straight to its deck or field and
        never passes its recovery point, so it never ran SQE_RECOVER (the v0.41.24 run: Hornets circling the boat). The hook recovers the group
        once its lead is within RECOV_NET_NM of the carrier (where it is now, not where it started) or the field, after its work is done."""
        t_ = max(float(wps[-1].eta_s) if wps else 0.0, float(hold_end or 0), float(stop) if f.tag else 0.0)
        self._recov.append({"g": g.name, "cv": cv_unit or "", "x": float(x), "z": float(y), "r": (r_nm or self.RECOV_NET_NM) * NM, "t": t_, "t2": t_ + self.RECOV_STALE_S, "dwell": float(dwell_s)})

    COVER_SHIFTS = (0, 4, 8, 12, 16, 20, 24)                 # v0.41.23: nm the centre may move, toward our side first, then sideways
    COVER_TURNS = (0, 30, -30, 60, -60, 90, -90)

    def _nav_row(self, label, b) -> str:
        """v0.41.177: one kneeboard line of approach aids for a home / divert base: a land field's ILS (with its runway), TACAN, NDB / VOR; the boat's TACAN and ICLS."""
        if b is None:
            return ""
        if b.kind == BaseKind.CARRIER:
            return f"{label:<6} {b.name.upper()[:14]}  TACAN {self.o.carrier_tacan}  ICLS {self.o.carrier_icls}  Case I"
        ln = kneeboard.nav_line(b.airport)
        return f"{label:<6} {ln}" if ln else ""

    def _zulu_note(self) -> str:
        tz = float(theatres.active().get("tz", 0) or 0)
        return "Times are local. Zulu = local" + (f" - {tz:g} h." if tz > 0 else f" + {-tz:g} h." if tz < 0 else " (no offset).")

