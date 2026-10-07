"""Package -> SQE_Sortie.miz (Caucasus, 2004).

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
from dcs.terrain import Caucasus
from dcs.unit import Skill
from dcs.unitgroup import VehicleGroup

from . import briefing as brief, callsigns
from . import threatmap as tm
from .aircraft import AIRCRAFT
from .debrief import Manifest, install_hook
from .difficulty import Difficulty
from .kneeboard import latlon, render_pages
from .loadouts import LoadoutLibrary, enemy_bomber_loadout, enemy_cap_loadout, ENEMY_FIGHTERS
from .models import AssetKind, BaseKind, ObjectiveType, Role
STAGGER = {Role.SWEEP: -90, Role.SEAD: -60, Role.ESCORT: -30}      # seconds relative to the strikers' push (BMS-style)
from .packages import Package
from .radio import RadioCfg, RadioLayout, RadioPlan, apply_player_presets, build_radio_plan
from .routes import NM, FT, Wpt, assign_times, bearing, dist, hold_leave_s, leg_seconds, make_geometry, objective_wp, offset, plan_route
from .state import CampaignState

KPH = 1.852
F = VehicleGroup.Formation
MAIN_TASK = {Role.CAP: task.CAP, Role.ESCORT: task.CAP, Role.SWEEP: task.FighterSweep, Role.SEAD: task.SEAD,
             Role.STRIKE: task.PinpointStrike, Role.CAS: task.CAS}
TEMP_C = {1: 6, 2: 6, 3: 9, 4: 12, 5: 17, 6: 21, 7: 24, 8: 24, 9: 20, 10: 16, 11: 11, 12: 8}   # coastal Black Sea, approximate
LASER = ["1688", "1687", "1686", "1685", "1684", "1683", "1682", "1681"]


@dataclass
class MissionOptions:
    launch_offset_min: int = 3          # you are ready on the cat/runway at start; briefed launch is this many minutes in
    hold_minutes: int = 2               # slack at MARSHAL before PUSH, minutes. Negative = you must be quicker than the natural pace
    cap_minutes: int = 40               # time on station for CAP flights
    ai_unlimited_fuel: bool = True      # Retribution-style: ON until the push, OFF for the combat leg, ON again from egress
    enemy_unlimited_fuel: bool = False
    ai_despawn_on_land: bool = True
    base_defenses: bool = True
    carrier_escorts: bool = True
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


class MissionBuilder:
    def __init__(self, state: CampaignState, d: Difficulty, opts: MissionOptions | None = None,
                 loadouts: LoadoutLibrary | None = None, rng: random.Random | None = None):
        self.state, self.d = state, d
        self.o = opts or MissionOptions()
        self.lo = loadouts or LoadoutLibrary()
        self.rng = rng or random.Random()

    # =====================================================================================================
    def build(self, package: Package, out_path) -> BuildResult:
        o = self.o
        st = self.state = copy.copy(self.state)                       # a private view: the carrier may be moved back for this sortie only
        st.bases = {k: copy.copy(v) for k, v in st.bases.items()}
        pf = package.player_flight
        if pf is None:
            raise ValueError("choose your flight first")
        warns: list = []
        self.warns = warns
        out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)

        m = Mission(Caucasus())
        self.m, self.t = m, m.terrain
        self.usa, self.red = m.country("USA"), m.country("Russia")
        date = st.campaign_date()
        hh, mm = int(package.start[:2]), int(package.start[3:5])
        start = datetime.datetime(date.year, date.month, date.day, hh, mm)
        m.start_time = start
        clock = lambda s: (start + datetime.timedelta(seconds=s)).strftime("%H:%M:%S")
        date_str = start.strftime("%d %b %Y").upper()
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
        mshl_xy = tm.safe_marshal(st, (pbase.x, pbase.y), bearing(pbase.x, pbase.y, tx, ty))
        geom = make_geometry(pbase.x, pbase.y, tx, ty, pspec.profile, mshl_xy)
        if tgt_asset is not None:                      # steer the egress away from SAM rings
            skip = {tgt_asset.id} if package.objective.type == ObjectiveType.DEAD else set()      # a DEAD target is the one thing we are killing
            geom.egr = (tm.first_safe_egress(st, tx, ty, geom.hdg, skip) or
                        tm.safe_egress(st, tx, ty, geom.hdg, pspec.profile.egress_nm, tm.cluster_ids(tgt_asset)) or geom.egr)
        manifest = Manifest(st.campaign_id, st.sortie_counter + 1, package.id, st.day)
        self.groups_by_asset, self.flight_groups = {}, []

        # ---- bases, base defenses, carrier + escorts --------------------------------------------------------
        self.ship, self.apt = {}, {}
        for bs in st.bases.values():
            if bs.kind == BaseKind.AIRFIELD:
                self.t.airports[bs.airport].set_blue()
        for a in st.assets.values():
            if a.kind == AssetKind.AIRFIELD and a.airport:
                self.t.airports[a.airport].set_red()
        for bid in dict.fromkeys(f.base_id for f in package.flights):
            self._place_base(st.bases[bid], tx, ty)
        atc = (o.carrier_atc_mhz if pbase.kind == BaseKind.CARRIER else self.t.airports[pbase.airport].atc_radio.uhf_hz / 1e6)

        # ---- enemy ground: everything the route touches is live from the first second ----------------------------------
        polyline = [(pbase.x, pbase.y), geom.mshl, geom.push, geom.ip, (tx, ty), geom.egr]
        self._spawn_opfor_ground(package, tx, ty, manifest, polyline)

        # ---- radios + support -----------------------------------------------------------------------------------------
        div = self._divert(pbase)
        div_mhz = self.t.airports[div.airport].atc_radio.uhf_hz / 1e6 if div.airport else None
        plan = build_radio_plan(package, st, atc, self.rng, o.layout, RadioCfg(o.carrier_tacan, o.carrier_link4_mhz), div_mhz, div.name)
        tanker_xy, awacs_unit, hav_xy = self._place_support(package, plan, geom)

        # ---- timeline: YOUR times. Roles are staggered around the strikers' push (sweep, SEAD, escorts go first) ---------
        launch_s = o.launch_offset_min * 60.0
        pw = plan_route(pf.role, (pbase.x, pbase.y), geom, pspec.profile, is_player=True, tanker_xy=None)
        dep_s = launch_s + 60 + dist(pbase.x, pbase.y, *geom.dep) / (pspec.profile.depart_kts * 0.514444) * 1.12     # roll + climb-out to DEP
        assign_times(pw, dep_s)
        mshl = next((w for w in pw if w.action in ("HOLD", "CAPORBIT")), pw[-1])
        k = pw.index(mshl)
        leg_m = leg_seconds(mshl, pw[k + 1]) if (mshl.action == "HOLD" and k + 1 < len(pw)) else 0.0
        player_push = math.ceil((mshl.eta_s + (0 if pf.role == Role.CAP else o.hold_minutes * 60) + leg_m) / 60.0) * 60.0
        player_push = max(player_push, math.ceil((dep_s + 120) / 60.0) * 60.0)
        leave_s = hold_leave_s(pw, player_push)
        P0 = player_push - STAGGER.get(pf.role, 0)                         # the strikers' push; everyone else is relative to it
        push_of = lambda f: P0 + (0 if f.tag else STAGGER.get(f.role, 0))
        assign_times(pw, dep_s, player_push)
        tgt = objective_wp(pw) or pw[-1]
        egr = next((w for w in pw if w.name == "EGR"), pw[-1])
        rtb_s = egr.eta_s + leg_seconds(egr, Wpt("RTB", pbase.x, pbase.y, 0, 300))
        tl = {"launch": clock(launch_s), "marshal": clock(mshl.eta_s), "push": clock(player_push), "tot": clock(tgt.eta_s),
              "egress": clock(egr.eta_s), "rtb": clock(rtb_s), "push_s": player_push, "tot_s": tgt.eta_s, "rtb_s": rtb_s}

        # ---- friendly flights --------------------------------------------------------------------------------------------
        despawn, pkg_table = [], []
        for idx, f in enumerate(package.flights):
            g, tot_f = self._spawn_flight(package, f, plan, geom, tanker_xy, hav_xy, push_of(f), tgt.eta_s, rtb_s, idx, manifest, despawn)
            if f.is_player:
                tot_f = tgt.eta_s
            if f.role == Role.CAS and tot_f:
                self.cas_tot = tot_f
            pkg_table.append({"callsign": f.callsign, "role": (f.tag or f.role.value), "push": clock(push_of(f)) if not f.tag else "-",
                              "tot": clock(tot_f) if tot_f else "-", "you": f.is_player})
        whois = self._datalinks(package, awacs_unit)

        # ---- enemy air picture (known CAP airborne from the start + alert aircraft that scramble when detected) ----
        keep = [(geom.mshl[0], geom.mshl[1], 100)] + [(p[0], p[1], 100) for p in (tanker_xy, hav_xy) if p is not None]
        for bid in dict.fromkeys(f.base_id for f in package.flights):
            keep.append((st.bases[bid].x, st.bases[bid].y, 130 if st.bases[bid].kind == BaseKind.CARRIER else 80))
        self._spawn_air_picture(package, tx, ty, tgt.eta_s, geom, manifest, keep)
        self._spawn_cas_support(package, plan, geom, manifest)
        bx, by = geom.push
        m.coalition["blue"].bullseye = {"x": bx, "y": by}

        # ---- waypoint table as the jet numbers it ------------------------------------------------------------------------------
        rows = [("TAKEOFF", pbase.x, pbase.y, launch_s, "", "", pbase.name)]
        for w in pw:
            rows.append((w.name, w.x, w.y, w.eta_s, f"{w.alt_ft // 1000}K", w.speed_kts, w.note))
        rows.append(("RTB", pbase.x, pbase.y, rtb_s, "-", 300, self._rtb_note(pspec)))
        n_route = len(rows)
        rows.append(("DIVERT", div.x, div.y, 0, "-", "", div.name))
        if tanker_xy:
            rows.append(("TKR", tanker_xy[0], tanker_xy[1], 0, f"{pspec.profile.aar_alt_ft // 1000}K", pspec.profile.aar_kts, "Top off. See COMMS for TACAN"))
        rows.append(("BULLS", bx, by, 0, "", "", "Bullseye reference"))
        player_wps = [Wpt(r[0], r[1], r[2], 0 if r[4] in ("", "-") else int(str(r[4]).rstrip("K")) * 1000,
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
                tstr = clock(r[3]) if r[0] in ("PUSH", "TGT", "SEAD", "CAP1") else clock(r[3])[:5]
            win = {"PUSH": "+/-30s", "TGT": "+/-1m", "SEAD": "+/-1m"}.get(r[0], "")
            if r[0] == "MSHL":
                win = f"hold to {clock(leave_s)[:5]}"
            kn_rows.append({"wp": pspec.wp_label(i), "name": r[0], "time": tstr, "alt": r[4], "kts": str(r[5]), "leg": leg, "win": win,
                            "note": r[6] if r[0] in ("TGT", "TKR", "RTB", "DIVERT") else ""})
            if r[0] not in ("TAKEOFF", "DIVERT", "TKR", "BULLS"):
                hook_wps.append((pspec.wp_label(i), r[0], r[1], r[2]))

        # ---- codes, fuel, text, hook, kneeboard -----------------------------------------------------------------------------
        mode3 = self._mode3(package, pf)
        laser = self._laser(package, pf)
        x = {"date": date_str, "mode3": mode3, "laser": laser, "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}",
             "bullseye": latlon(bx, by, self.t), "divert": div.name, "weather": "clear skies, unrestricted visibility",
             "link16": any(r["stn"] != "-" for r in whois), "pkg_table": pkg_table}
        text = brief.build_text(st, package, tl, plan, self.rng, (tx, ty), x)
        m.set_description_text(text["full"])
        m.set_description_bluetask_text(text["blue_task"])
        m.set_sortie_text(f"{date_str}  day {st.day}: {package.objective.description}")
        awl = next((s.label for s in package.support if s.slot == "AWACS"), "AWACS")
        calls = []
        t1 = next((s for s in package.support if s.slot == "TANKER1"), None)
        if t1 is not None:
            calls.append((25, f"{t1.label} 1-1: on station, TACAN {plan.tacan.get('TANKER1', '')}, COMM1 channel 3."))
        calls.append((P0, f"{awl} 1-1: package, push, push, push."))
        if tgt.eta_s - 300 > 60:
            calls.append((tgt.eta_s - 300, f"{awl} 1-1: five minutes to TOT."))
        with tempfile.TemporaryDirectory(prefix="sqe_kb_") as td:
            sound = self._squelch(td)
            install_hook(m, st.campaign_id, manifest.sortie, package.id, despawn if o.ai_despawn_on_land else [], manifest.player_unit,
                         group=pf.callsign, calls=calls, wps=hook_wps, sound=sound)
            tdata = ""
            if pf.role in (Role.STRIKE, Role.SEAD, Role.CAS):
                tdata = f"TARGET  {latlon(tx, ty, self.t)}   ({package.objective.description})"
            ctx = {"date": date_str, "callsign": f"{pf.callsign}-1", "role": pf.role.value, "objective": package.objective.description,
                   "comm1": plan.comm1, "comm2": plan.comm2, "waypoints": kn_rows, "jet": pspec.display,
                   "numbering": ("B for the start point, then 1, 2, 3..." if pspec.first_wp_label else "waypoint 1 = start point"),
                   "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}", "weather": "CLEAR", "mode3": mode3, "laser": laser,
                   "bullseye": latlon(bx, by, self.t), "whois": whois, "threats": text["threats"], "n_def": package.n_def, "target_data": tdata}
            for pg in render_pages(td, ctx):
                m.add_aircraft_kneeboard(pspec.dcs_type, pg)
            warns += list(dict.fromkeys(self.lo.warnings))
            counts = self._counts()
            m.save(str(out_path))
        return BuildResult(out_path, manifest, plan, player_wps, package, tl, text, counts, whois, warns, self.seed_code)

    def _squelch(self, folder) -> str:
        """A short radio squelch bundled into the mission; played with each call-out. Returns the in-mission file name ('' on failure)."""
        try:
            import struct
            import wave
            rr = random.Random(7)
            p = Path(folder) / "sqe_squelch.wav"
            with wave.open(str(p), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
                n = int(22050 * 0.45)
                frames = bytearray()
                for i in range(n):
                    t = i / 22050.0
                    env = 1.0 if t < 0.10 else (0.12 if t < 0.34 else max(0.0, 1.0 - (t - 0.34) / 0.11))
                    frames += struct.pack("<h", int(rr.uniform(-1, 1) * 9000 * env))
                w.writeframes(bytes(frames))
            self.m.map_resource.add_resource_file(str(p))
            return "l10n/DEFAULT/sqe_squelch.wav"
        except Exception:
            self.warns.append("radio squelch sound could not be bundled; call-outs are text only")
            return ""

    # =====================================================================================================
    def _weather(self, m, date):
        w = m.weather
        try:
            w.clouds_density = 0; w.enable_fog = False; w.enable_dust = False; w.visibility_distance = 80000
            w.season_temperature = float(TEMP_C[date.month]); w.qnh = 760
        except Exception:
            self.warns.append("could not set clear weather explicitly (pydcs defaults are already clear)")

    def _counts(self) -> dict:
        g = u = 0
        for coal in self.m.coalition.values():
            for c in coal.countries.values():
                for attr in ("plane_group", "helicopter_group", "vehicle_group", "ship_group", "static_group"):
                    for grp in getattr(c, attr, []):
                        g += 1; u += len(grp.units)
        return {"groups": g, "units": u}

    def _target_xy(self, package):
        o = package.objective
        if o.type == ObjectiveType.FLEET_DEFENSE:           # CAP station on the bearing the raid will arrive on
            c = self.state.bases[o.target_id]
            return offset(c.x, c.y, package.extra.get("brg", 20.0), 85 * NM)
        if o.type == ObjectiveType.BARCAP:
            b = self.state.bases[o.target_id]
            air = [a for a in self.state.assets.values() if a.kind == AssetKind.AIRFIELD and not a.destroyed]
            n = min(air, key=lambda a: dist(b.x, b.y, a.x, a.y))
            return offset(b.x, b.y, bearing(b.x, b.y, n.x, n.y), 60 * NM)
        a = self.state.assets[o.target_id]
        return a.x, a.y

    def _rtb_note(self, spec):
        if spec.home == BaseKind.CARRIER:
            return f"Case I, TACAN {self.o.carrier_tacan}, ICLS {self.o.carrier_icls}"
        return "Land. Tower on COMM1 CH1"

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
    def _pull_back_carriers(self, tx, ty):
        """Keep the carrier group out of the fight: slide it back along the line of retreat (up to 60 nm, this sortie only) until it
        is far from the target and from every enemy fighter base. Skipped when the carrier itself IS the objective (fleet defence)."""
        if self._fleet_obj:
            return
        enemies = tm.fighter_bases(self.state)
        need = self.o.carrier_min_enemy_nm * NM
        for b in self.state.bases.values():
            if b.kind != BaseKind.CARRIER:
                continue
            brg = (bearing(b.x, b.y, tx, ty) + 180) % 360
            x0, y0 = b.x, b.y
            x, y = x0, y0
            for nm in range(0, 66, 10):
                x, y = offset(x0, y0, brg, nm * NM)
                if dist(x, y, tx, ty) >= need and all(dist(x, y, ex, ey) >= need for ex, ey in enemies):
                    break
            b.x, b.y = x, y

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
            if o.base_defenses and base.defense >= 0.15:
                p = self.apt[base.id].position
                ang = sum(ord(c) for c in base.id) % 360
                full = base.defense >= 0.6
                x, y = offset(p.x, p.y, ang, 4500)
                self._platoon(self.usa, f"BASEDEF {base.name} Patriot", [("Patriot_str", 1), ("Patriot_ECS", 1), ("Patriot_cp", 1),
                              ("Patriot_EPP", 1), ("Patriot_ln", 3 if full else 1)], x, y, ang, F.Star)
                x, y = offset(p.x, p.y, ang + 120, 3500)
                self._platoon(self.usa, f"BASEDEF {base.name} AAA", [("Vulcan", 2), ("M1097_Avenger", 2 if full else 1)], x, y, ang, F.Line)
            return
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
        elif a.kind == AssetKind.ARMOR:       # the column sits somewhere along its axis of advance
            fb = self._nearest_airfield(a.x, a.y)
            pos = offset(a.x, a.y, bearing(a.x, a.y, fb.x, fb.y), r.uniform(-1500, 1500))
        else:
            pos = offset(a.x, a.y, r.uniform(0, 360), r.uniform(0, 900))
        self.site_pos[a.id] = pos
        return pos

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

    def _armor_comp(self):
        r = self.vrng
        comp = [(r.choice(["T_72B", "T_72B", "T_80B", "T_80UD"]), r.randint(3, 6)), (r.choice(["BMP_2", "BMP_1", "BMP_3"]), r.randint(2, 5)),
                (r.choice(["BTR_80", "BTR_70", "BTR_60"]), r.randint(1, 3)), ("ZSU_23_4_Shilka", r.randint(0, 2)), ("Ural_375", r.randint(0, 3))]
        if r.random() < 0.4:
            comp.append((r.choice(["Strela_10M3", "Osa_9A33_ln"]), 1))       # mobile air defence travelling with the column
        return [(n, c) for n, c in comp if c > 0]

    def _spawn_opfor_ground(self, package, tx, ty, manifest, polyline=None):
        st, obj = self.state, package.objective
        if obj.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            return
        tgt = st.assets[obj.target_id]
        relevant = [tgt] + [st.assets[i] for i in tgt.defended_by]
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
            comp = SITES.get(a.variant) if a.kind in (AssetKind.SAM, AssetKind.EWR) else SOFT.get(a.kind)
            if comp:
                self._spawn_site(a, comp, manifest, primary=(a.id == tgt.id))

    def _spawn_site(self, a, comp, manifest, primary):
        """ONE group per site: a SAM battery needs its search/track radars, launchers and command post together."""
        r = self.vrng
        skill = getattr(Skill, self.d.enemy_skill, Skill.High)
        comp = self._armor_comp() if a.kind == AssetKind.ARMOR else self._vary_comp(a, comp)
        cx, cy = self._site_center(a)
        base_count = sum(n for vname, n in comp if _vt(vname) is not None)
        if a.kind == AssetKind.ARMOR:
            fb = self._nearest_airfield(cx, cy)
            heading, form = int(bearing(cx, cy, fb.x, fb.y)), r.choice([F.Line, F.Rectangle, F.Line])
        else:
            heading, form = r.randint(0, 359), r.choice([F.Star, F.Scattered, F.Rectangle])
        g = self._platoon(self.red, a.id, comp, cx, cy, heading, form, scale=a.health)
        if g is None:
            return
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
        manifest.add("asset", a.id, names, base_count=base_count, health_before=a.health, primary=primary)

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

    def _place_support(self, package, plan, g):
        """Tanker, AWACS and HAVCAP sit around the rear marshal point: as close to home as it gets, behind the base, far from the enemy."""
        pt = lambda x, y: mapping.Point(x, y, self.t)
        cx, cy = g.mshl
        tanker_xy, awacs_unit = None, None
        hav_xy = offset(cx, cy, g.hdg + 45, 8 * NM)
        for s in package.support:
            cls = getattr(planes, s.dcs_class)
            alt, spd, freq = s.altitude_ft * FT, s.speed_kts * KPH, plan.freq(s.slot)
            if s.slot == "AWACS":
                x, y = offset(cx, cy, g.hdg + 90, 22 * NM)
                grp = self.m.awacs_flight(self.usa, f"{s.label} 1", cls, None, pt(x, y), race_distance=60 * NM, heading=int(g.hdg),
                                          altitude=alt, speed=spd, frequency=freq)
                callsigns.apply(grp, s.label, 1, callsigns.AWACS); grp.units[0].name = f"{s.label} 1-1"
                awacs_unit = grp.units[0]
            else:
                if s.from_carrier:
                    x, y = offset(g.bx, g.by, g.hdg + 180, 15 * NM); race = 20 * NM
                else:
                    x, y = offset(cx, cy, g.hdg - 90, (14 if s.slot == "TANKER1" else 28) * NM); race = 40 * NM
                grp = self.m.refuel_flight(self.usa, f"{s.label} 1", cls, None, pt(x, y), race_distance=race, heading=int(g.hdg),
                                           altitude=alt, speed=spd, frequency=freq, tacanchannel=plan.tacan[s.slot])
                callsigns.apply(grp, s.label, 1, callsigns.TANKER); grp.units[0].name = f"{s.label} 1-1"
                if s.slot == "TANKER1":
                    tanker_xy = (x, y)
        return tanker_xy, awacs_unit, hav_xy

    # ---- friendly flights -------------------------------------------------------------------------------------------------
    def _spawn_flight(self, package, f, plan, geom, tanker_xy, hav_xy, push_s, tot_s, rtb_s, idx, manifest, despawn):
        st, o = self.state, self.o
        spec = AIRCRAFT[f.aircraft]
        base = st.bases[f.base_id]
        pt = lambda x, y: mapping.Point(x, y, self.t)
        csname, fno = f.callsign.rsplit(" ", 1)
        fno = int(fno)

        if f.tag:       # HAVCAP / BASECAP: airborne on station for the whole package
            sx, sy = hav_xy if f.tag == "HAVCAP" else offset(base.x, base.y, geom.hdg, 8 * NM)
            p = spec.profile
            wps = [Wpt("SPAWN", sx, sy, p.cap_alt_ft, p.cap_kts), Wpt("CAP1", sx, sy, p.cap_alt_ft, p.cap_kts, "", "CAPORBIT"),
                   Wpt("CAP2", *offset(sx, sy, geom.hdg + 90, 20 * NM), p.cap_alt_ft, p.cap_kts)]
            stop = int(max(tot_s + o.cap_minutes * 60, rtb_s + 300))
        else:
            sp = None
            if not f.is_player:
                sp = self._spawn_point(f, base, geom)
            wps = plan_route(f.role, (base.x, base.y), geom, spec.profile, is_player=f.is_player, tanker_xy=None, stack_idx=idx,
                             spawn=sp[0] if sp else None, spawn_alt_ft=sp[1] if sp else 0, spawn_kts=sp[2] if sp else 0)
            if f.is_player:
                assign_times(wps, o.launch_offset_min * 60.0, push_s)
                act_s = 0
            else:
                assign_times(wps, 0.0)                      # natural pace from the spawn
                hold_i = next((i for i, w in enumerate(wps) if w.action == "HOLD"), None)
                nat = wps[hold_i + 1].eta_s if hold_i is not None else next((w.eta_s for w in wps if w.action == "CAPORBIT"), wps[-1].eta_s)
                act_s = max(0, int(push_s - nat - (120 if hold_i is not None else 60)))      # arrive ~2 min early, hold, push on time
                assign_times(wps, float(act_s), push_s)
            stop = int(tot_s + o.cap_minutes * 60)

        if f.is_player:       # hot on the runway / catapult
            if base.kind == BaseKind.CARRIER:
                g = self.m.flight_group_from_unit(self.usa, f.callsign, spec.dcs_type, self.ship[base.id], maintask=MAIN_TASK[f.role],
                                                  start_type=StartType.Runway, group_size=f.count)
            else:
                g = self.m.flight_group_from_airport(self.usa, f.callsign, spec.dcs_type, self.apt[base.id], maintask=MAIN_TASK[f.role],
                                                     start_type=StartType.Runway, group_size=f.count)
            first = 0
        else:                 # already airborne
            s0 = wps[0]
            g = self.m.flight_group(self.usa, f.callsign, spec.dcs_type, None, pt(s0.x, s0.y), altitude=s0.alt_ft * FT,
                                    speed=s0.speed_kts * KPH, maintask=MAIN_TASK[f.role], group_size=f.count)
            first = 1
        if not f.tag and not f.is_player and act_s > 0:
            self._late(g, act_s)                                # they 'depart' on their own schedule, not at mission start
        cs_names = callsigns.apply(g, csname, fno, callsigns.table(f.aircraft))
        load = self.lo.for_role(f.aircraft, f.role)
        names = []
        for i, u in enumerate(g.units):
            u.name = cs_names[i]; names.append(u.name)
            u.pylons = copy.deepcopy(load)
            if f.is_player and f.aircraft == "F-14BU":
                u.set_property("INSAlignmentStored", True)
        g.set_skill(Skill.High)

        if f.is_player:
            u0 = g.units[0]
            u0.set_client() if o.player_is_client else u0.set_player()
            if not (hasattr(spec.dcs_type, "panel_radio") and spec.dcs_type.panel_radio and apply_player_presets(u0, plan, o.layout)):
                self.warns.append(f"{spec.display}: COMM1 presets can't be set automatically; set them from the kneeboard comms page.")
            try:
                g.set_frequency(plan.freq("FLIGHT"), radio_id=o.layout.comm2_radio_id)
            except Exception:
                g.set_frequency(plan.freq("FLIGHT"))
            manifest.player_unit = u0.name
        else:
            g.set_frequency(next((e.mhz for e in plan.package_flights if e.callsign == f.callsign), 130.0))
            if o.ai_despawn_on_land:
                despawn.extend(names)
            if o.ai_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
        manifest.add("friendly", f.id, names, squadron=f.squadron_id, callsign=f.callsign, player=f.is_player)
        self.flight_groups.append((f, g))

        armor = self.groups_by_asset.get(package.objective.target_id)
        for w in wps[first:]:
            wp = g.add_waypoint(pt(w.x, w.y), w.alt_ft * FT, w.speed_kts * KPH, w.name)
            if f.is_player:
                if w.action == "BOMB":
                    wp.tasks.append(task.Bombing(pt(w.x, w.y), group_attack=True))
                continue
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
            elif w.action == "BOMB":
                wp.tasks.append(task.Bombing(pt(w.x, w.y), group_attack=True))
            elif w.action == "CAS":
                self._cas_tasks(wp, w, armor, tot_s)
            elif w.action == "SEAD" and armor is not None:                 # 'armor' is simply the target asset's group here
                ct = task.ControlledTask(task.AttackGroup(armor.id, weapon_type=task.WeaponType.Auto, group_attack=True))
                ct.stop_after_time(int(w.eta_s) + 600)
                wp.tasks.append(task.OptROE(task.OptROE.Values.WeaponFree)); wp.tasks.append(ct)
        if base.kind == BaseKind.AIRFIELD:
            g.land_at(self.apt[base.id])
        else:
            rtb = g.add_waypoint(pt(base.x, base.y), 600, 300 * KPH, "RTB")
            rtb.type, rtb.action = "Land", PointAction.Landing
            rtb.link_unit = rtb.helipad = self.ship[base.id].units[0].id
        tw = None if f.tag else objective_wp(wps)
        return g, (tw.eta_s if tw is not None else None)

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

    def _cas_tasks(self, wp, w, armor, tot_s):
        """AI CAS: look at the fight, attack the column, then keep working the zone. Time-boxed so they eventually go home."""
        t0 = int(w.eta_s)
        wp.tasks.append(task.OptROE(task.OptROE.Values.WeaponFree))
        if armor is not None:
            ct = task.ControlledTask(task.AttackGroup(armor.id, weapon_type=task.WeaponType.Auto, group_attack=False))
            ct.stop_after_time(t0 + 420)
            wp.tasks.append(ct)
        ct2 = task.ControlledTask(task.EngageTargetsInZone(mapping.Point(w.x, w.y, self.t), 9000, [task.Targets.All.GroundUnits.GroundVehicles]))
        ct2.stop_after_time(t0 + 1080)
        wp.tasks.append(ct2)

    def _trailing_steerpoints(self, package, rows, spec):
        """DIVERT, TKR and BULLSEYE come after RTB on the player's group, like Retribution (tanker/bullseye last)."""
        pf = package.player_flight
        g = next(gr for fl, gr in self.flight_groups if fl is pf)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        for name, x, y, _t, alt, kts, _n in rows:
            a = 20000 * FT if name == "TKR" else 5000 * FT
            g.add_waypoint(pt(x, y), a, (spec.profile.aar_kts if name == "TKR" else 300) * KPH, name)

    # ---- Link 16 / SADL: the package flies as one network ------------------------------------------------------------------
    def _datalinks(self, package, awacs_unit) -> list:
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
        for f, g in self.flight_groups:
            for u in g.units:
                dl = getattr(u, "datalink", None)
                if dl is None:
                    continue
                net = dl.network
                if awacs_unit is not None and dl.link_type.name == "LINK16":
                    net.add_donor(awacs_unit.id)
                for of, og in self.flight_groups:
                    if of is f:
                        continue
                    odl = getattr(og.units[0], "datalink", None)
                    if odl is None or odl.link_type != dl.link_type:
                        continue
                    ok = bool(net.has_donors and net.add_donor(og.units[0].id))
                    if not ok:
                        net.add_member(og.units[0].id)
        return whois

    # ---- CAS: both columns drive into contact so the clash is under way at the CAS TOT (+/- 30 s) -------------------------
    def _translate(self, g, dx, dy):
        for u in g.units:
            u.position = mapping.Point(u.position.x + dx, u.position.y + dy, self.t)
        for p in g.points:
            p.position = mapping.Point(p.position.x + dx, p.position.y + dy, self.t)

    def _drive(self, g, via, speed_ms):
        for q in via:
            g.add_waypoint(mapping.Point(q[0], q[1], self.t), PointAction.OffRoad, speed_ms * 3.6)
        g.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponFree))
        g.points[0].tasks.append(task.OptAlarmState(2))

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
        if enemy is not None:
            ex, ey = offset(cx, cy, brg + 180, dist_run)
            self._translate(enemy, ex - cx, ey - cy)
            self._drive(enemy, [offset(cx, cy, brg, 2500)], v)
        fx, fy = offset(cx, cy, brg + r.uniform(-6, 6), dist_run)
        comp = [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(2, 3)), ("M1043_HMMWV_Armament", r.randint(1, 2))]
        g = self._platoon(self.usa, "Friendly Task Force", comp, fx, fy, (int(brg) + 180) % 360, F.Rectangle)
        if g is not None:
            names = []
            for k, u in enumerate(g.units, 1):
                u.name = f"TF|{k}"; names.append(u.name)
            self._drive(g, [offset(cx, cy, brg + 180, 2500)], v)
            manifest.add("friendly_ground", self.armor_id or "", names)
        jx, jy = offset(fx, fy, brg + 90, 120)
        jt = self.m.vehicle_group(self.usa, "Axeman 1", _UN.Hummer, mapping.Point(jx, jy, self.t), heading=(int(brg) + 180) % 360, group_size=1)
        jt.units[0].name = f"JTAC-{package.id}"
        p0 = jt.points[0]
        p0.tasks.append(task.FAC(callsign=1, frequency=int(plan.freq("JTAC") * 1e6), modulation=task.Modulation.AM, number=1))
        p0.tasks.append(task.SetInvisibleCommand(True))
        p0.tasks.append(task.SetImmortalCommand(True))
        jt.add_waypoint(mapping.Point(*offset(cx, cy, brg, 3800), self.t), PointAction.OffRoad, v * 3.6)

    # ---- late activation helper ------------------------------------------------------------------------------------------------
    def _late(self, g, seconds):
        g.late_activation = True
        trig = triggers.TriggerOnce(comment=f"activate {g.name}")
        trig.add_condition(condition.TimeAfter(int(seconds)))
        trig.add_action(action.ActivateGroup(g.id))
        self.m.triggerrules.triggers.append(trig)

    # ---- enemy air picture: what the intelligence briefing says is there IS there, from the first second ----------------------
    def _spawn_air_picture(self, package, tx, ty, tot_s, geom, manifest, keepout):
        """Known CAP flights are airborne from t=0 on briefed stations. The rest of the defenders are alert aircraft sitting on real
        enemy airfields; they take off (scramble) when the package is detected inside the field's detection zone."""
        if package.objective.type == ObjectiveType.FLEET_DEFENSE:
            return self._spawn_raid(package, tx, ty, tot_s, geom, manifest)
        st, d, r = self.state, self.d, self.vrng
        n_fl = package.n_def // 2
        if n_fl <= 0:
            return
        wings = [(w, st.assets[w.base_asset_id]) for w in st.enemy_air if w.available > 0 and not st.assets[w.base_asset_id].destroyed
                 and any(t in ENEMY_FIGHTERS for t in w.types)]
        wings.sort(key=lambda p: dist(p[1].x, p[1].y, tx, ty))
        if not wings:
            return
        skill = getattr(Skill, d.enemy_skill, Skill.High)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        n_cap = max(1, math.ceil(n_fl / 2))
        alt, spd = 22000 * FT, 400 * KPH
        for i in range(n_fl):
            w, a = wings[i % len(wings)]
            tname = r.choice([t for t in w.types if t in ENEMY_FIGHTERS])
            cls = getattr(planes, tname)
            load = enemy_cap_loadout(tname)
            dd = dist(a.x, a.y, tx, ty)
            if i < n_cap:                                   # known CAP, on station from the start
                if dd < 25 * NM:
                    sx, sy = offset(tx, ty, geom.hdg + r.uniform(-30, 30), 15 * NM)
                else:
                    sx, sy = offset(tx, ty, bearing(tx, ty, a.x, a.y) + r.uniform(-20, 20), min(0.7 * dd, r.uniform(40, 60) * NM))
                for kx, ky, knm in keepout:                 # never park a CAP near the marshal, the tanker, AWACS, our fields or the carrier group
                    if dist(sx, sy, kx, ky) < knm * NM:
                        sx, sy = offset(kx, ky, bearing(kx, ky, sx, sy), knm * NM)
                g = self.m.flight_group(self.red, f"Bandit {i + 1}", cls, None, pt(sx, sy), altitude=alt, speed=spd, maintask=task.CAP, group_size=2)
                ct = task.ControlledTask(task.OrbitAction(int(alt), int(spd)))
                ct.stop_after_time(int(tot_s + 3600))
                g.add_waypoint(pt(sx, sy), alt, spd, "CAP").tasks.append(ct)
                g.add_waypoint(pt(*offset(sx, sy, bearing(sx, sy, tx, ty) + 90, 20 * NM)), alt, spd, "CAP2")
            else:                                           # alert: on the runway, scrambles when detected
                ap = self.t.airports.get(a.airport) if a.airport else None
                if ap is None:
                    continue
                g = self.m.flight_group_from_airport(self.red, f"Alert {i + 1}", cls, ap, maintask=task.CAP, start_type=StartType.Runway, group_size=2)
                g.add_trigger_action(task.StartCommand())
                g.uncontrolled = True
                radius = max(20.0, min(70.0, dist(a.x, a.y, *geom.push) / NM - 8.0)) * NM      # never trips before the package pushes
                zone = self.m.triggers.add_triggerzone(pt(a.x, a.y), radius, True, f"detect {a.id}")
                trig = triggers.TriggerOnce(comment=f"scramble {g.name}")
                trig.add_condition(condition.PartOfCoalitionInZone("blue", zone.id))
                trig.add_action(action.AITaskPush(g.id, 1))
                self.m.triggerrules.triggers.append(trig)
                ct = task.ControlledTask(task.OrbitAction(int(alt), int(spd)))
                ct.stop_after_time(int(tot_s + 3600))
                g.add_waypoint(pt(tx, ty), alt, spd, "INTERCEPT").tasks.append(ct)
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"ENM-{a.id}-{i}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name)
            g.set_skill(skill)
            if self.o.enemy_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
            if not load:
                self.warns.append(f"{tname}: no air-to-air loadout found; spawned unarmed")
            manifest.add("enemy_air", w.base_asset_id, names)

    # ---- bomber raid on the fleet: already en route from the first second, along a real path from their base ----------------
    def _spawn_raid(self, package, sx_, sy_, tot_s, geom, manifest):
        st, d, r = self.state, self.d, self.vrng
        ex = package.extra
        if not ex:
            return
        cvb = st.bases[package.objective.target_id]
        cvg = self.ship.get(cvb.id)
        ba = st.assets[ex["bomber_wing"]]
        pt = lambda x, y: mapping.Point(x, y, self.t)
        station = (sx_, sy_)
        w1 = offset(cvb.x, cvb.y, ex["brg"], min(220 * NM, 0.9 * dist(ba.x, ba.y, cvb.x, cvb.y)))
        poly = [(ba.x, ba.y), w1, station]
        arrive = tot_s + r.uniform(60, 150)
        path_len = dist(*poly[0], *poly[1]) + dist(*poly[1], *poly[2])
        (sx, sy), seg_i = tm.point_back_along(poly, min(232.0 * arrive, 0.97 * path_len))
        remaining = poly[seg_i:] + [(cvb.x, cvb.y)]
        skill = getattr(Skill, d.enemy_skill, Skill.High)
        alt = 30000 * FT

        def build_group(name, cls, count, task_cls, pos):
            g = self.m.flight_group(self.red, name, cls, None, pt(*pos), altitude=alt, speed=450 * KPH, maintask=task_cls, group_size=count)
            for k, q in enumerate(remaining):
                wp = g.add_waypoint(pt(*q), alt, 450 * KPH, "STN" if k < len(remaining) - 1 else "FLEET")
                if k == len(remaining) - 1 and cvg is not None and cls is planes.Tu_22M3:
                    wp.tasks.append(task.AttackGroup(cvg.id))
            g.set_skill(skill)
            return g

        g = build_group("Raid Bomber 1", planes.Tu_22M3, ex["bombers"], task.AntishipStrike, (sx, sy))
        load = enemy_bomber_loadout("Tu_22M3")
        names = []
        for j, u in enumerate(g.units, 1):
            u.name = f"RAID-B-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name)
        if not load:
            self.warns.append("Tu-22M3: no anti-ship weapon found; the raid has no missiles.")
        manifest.add("enemy_air", ex["bomber_wing"], names)
        if ex.get("escorts"):
            back = offset(sx, sy, bearing(remaining[0][0], remaining[0][1], sx, sy), 3 * NM)
            eg = build_group("Raid Escort 1", getattr(planes, ex["escort_type"]), ex["escorts"], task.CAP, back)
            eload = enemy_cap_loadout(ex["escort_type"])
            en = []
            for j, u in enumerate(eg.units, 1):
                u.name = f"RAID-E-{j}"; u.pylons = copy.deepcopy(eload); en.append(u.name)
            manifest.add("enemy_air", ex["escort_wing"], en)
