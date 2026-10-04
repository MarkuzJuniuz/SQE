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
from .aircraft import AIRCRAFT
from .debrief import Manifest, install_hook
from .difficulty import Difficulty
from .kneeboard import latlon, render_pages
from .loadouts import LoadoutLibrary, enemy_cap_loadout, ENEMY_FIGHTERS
from .models import AssetKind, BaseKind, ObjectiveType, Role
from .packages import Package
from .radio import RadioCfg, RadioLayout, RadioPlan, apply_player_presets, build_radio_plan
from .routes import NM, FT, Wpt, assign_times, bearing, dist, leg_seconds, make_geometry, offset, plan_route
from .state import CampaignState

KPH = 1.852
F = VehicleGroup.Formation
MAIN_TASK = {Role.CAP: task.CAP, Role.ESCORT: task.CAP, Role.SWEEP: task.FighterSweep, Role.SEAD: task.SEAD,
             Role.STRIKE: task.PinpointStrike, Role.CAS: task.CAS}
TEMP_C = {1: 6, 2: 6, 3: 9, 4: 12, 5: 17, 6: 21, 7: 24, 8: 24, 9: 20, 10: 16, 11: 11, 12: 8}   # coastal Black Sea, approximate
LASER = ["1688", "1687", "1686", "1685", "1684", "1683", "1682", "1681"]


@dataclass
class MissionOptions:
    launch_offset_min: int = 5          # you are ready on the cat/runway at start; briefed launch is this many minutes in
    hold_minutes: int = 8               # buffer at MARSHAL before PUSH
    cap_minutes: int = 40               # time on station for CAP flights
    ai_unlimited_fuel: bool = True
    enemy_unlimited_fuel: bool = False
    ai_despawn_on_land: bool = True
    base_defenses: bool = True
    carrier_escorts: bool = True
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


class MissionBuilder:
    def __init__(self, state: CampaignState, d: Difficulty, opts: MissionOptions | None = None,
                 loadouts: LoadoutLibrary | None = None, rng: random.Random | None = None):
        self.state, self.d = state, d
        self.o = opts or MissionOptions()
        self.lo = loadouts or LoadoutLibrary()
        self.rng = rng or random.Random()

    # =====================================================================================================
    def build(self, package: Package, out_path) -> BuildResult:
        st, o = self.state, self.o
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
        pbase = st.bases[pf.base_id]
        pspec = AIRCRAFT[pf.aircraft]
        geom = make_geometry(pbase.x, pbase.y, tx, ty, pspec.profile)
        manifest = Manifest(st.campaign_id, st.sortie_counter + 1, package.id, st.day)
        self.groups_by_asset, self.flight_groups = {}, []

        # ---- bases, base defenses, carrier + escorts --------------------------------------------------------
        self.ship, self.apt = {}, {}
        for b in st.bases.values():
            if b.kind == BaseKind.AIRFIELD:
                self.t.airports[b.airport].set_blue()
        for a in st.assets.values():
            if a.kind == AssetKind.AIRFIELD and a.airport:
                self.t.airports[a.airport].set_red()
        for bid in dict.fromkeys(f.base_id for f in package.flights):
            self._place_base(st.bases[bid], tx, ty)
        atc = (o.carrier_atc_mhz if pbase.kind == BaseKind.CARRIER else self.t.airports[pbase.airport].atc_radio.uhf_hz / 1e6)

        # ---- enemy ground (SAM sites, armor, targets) -----------------------------------------------------------
        self._spawn_opfor_ground(package, tx, ty, manifest)

        # ---- radios + support -----------------------------------------------------------------------------------------
        plan = build_radio_plan(package, st, atc, self.rng, o.layout, RadioCfg(o.carrier_tacan, o.carrier_link4_mhz))
        tanker_xy, awacs_unit, hav_xy = self._place_support(package, plan, geom)

        # ---- timeline (the player defines PUSH and TOT) -------------------------------------------------------------
        launch_s = o.launch_offset_min * 60.0
        pw = plan_route(pf.role, (pbase.x, pbase.y), geom, pspec.profile, is_player=True, tanker_xy=None)
        assign_times(pw, launch_s)
        mshl = next((w for w in pw if w.action in ("HOLD", "CAPORBIT")), pw[-1])
        push_s = math.ceil((mshl.eta_s + (0 if pf.role == Role.CAP else o.hold_minutes * 60)) / 60.0) * 60.0
        assign_times(pw, launch_s, push_s)
        tgt = next((w for w in pw if w.action in ("BOMB", "SEAD", "SWEEP", "CAS") or w.name in ("ESC", "CAP1")), pw[-1])
        egr = next((w for w in pw if w.name == "EGR"), pw[-1])
        rtb_s = egr.eta_s + leg_seconds(egr, Wpt("RTB", pbase.x, pbase.y, 0, 300))
        tl = {"launch": clock(launch_s), "marshal": clock(mshl.eta_s), "push": clock(push_s), "tot": clock(tgt.eta_s),
              "egress": clock(egr.eta_s), "rtb": clock(rtb_s), "push_s": push_s, "tot_s": tgt.eta_s, "rtb_s": rtb_s}

        # ---- friendly flights --------------------------------------------------------------------------------------------
        despawn, ai_regular = [], 0
        for idx, f in enumerate(package.flights):
            self._spawn_flight(package, f, plan, geom, tanker_xy, hav_xy, push_s, tgt.eta_s, rtb_s, idx, manifest, despawn)
        whois = self._datalinks(package, awacs_unit)

        # ---- enemy fighters, JTAC, bullseye -----------------------------------------------------------------------------
        self._spawn_defenders(package, tx, ty, tgt.eta_s, geom, manifest)
        if package.jtac:
            self._spawn_jtac(package, plan, geom)
        bx, by = geom.push
        m.coalition["blue"].bullseye = {"x": bx, "y": by}

        # ---- waypoint table as the jet numbers it ------------------------------------------------------------------------------
        div = self._divert(pbase)
        rtb_note = self._rtb_note(pspec)
        rows = [("TAKEOFF", pbase.x, pbase.y, launch_s, "", "", pbase.name)]
        for w in pw:
            rows.append((w.name, w.x, w.y, w.eta_s, f"{w.alt_ft // 1000}K", w.speed_kts, w.note))
        rows.append(("RTB", pbase.x, pbase.y, rtb_s, "-", 300, rtb_note))
        rows.append(("DIVERT", div.x, div.y, 0, "-", "", div.name))
        if tanker_xy:
            rows.append(("TKR", tanker_xy[0], tanker_xy[1], 0, f"{pspec.profile.aar_alt_ft // 1000}K", pspec.profile.aar_kts, "Top off. See COMMS for TACAN"))
        rows.append(("BULLS", bx, by, 0, "", "", "Bullseye reference"))
        player_wps = [Wpt(r[0], r[1], r[2], 0 if r[4] in ("", "-") else int(str(r[4]).rstrip("K")) * 1000,
                          int(r[5]) if str(r[5]).isdigit() else 0, r[6]) for r in rows]
        self._trailing_steerpoints(package, rows[-3:], pspec)
        kn_rows = []
        for i, r in enumerate(rows, 1):
            kn_rows.append({"wp": pspec.wp_label(i), "name": r[0], "time": clock(r[3])[:5] if r[3] else "", "alt": r[4], "kts": str(r[5]),
                            "pos": latlon(r[1], r[2], self.t), "note": r[6] if r[0] in ("TGT", "CAS", "TKR", "RTB") else ""})

        # ---- codes, fuel, text, hook, kneeboard -----------------------------------------------------------------------------
        mode3 = self._mode3(package, pf)
        laser = self._laser(package, pf)
        x = {"date": date_str, "mode3": mode3, "laser": laser, "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}",
             "bullseye": latlon(bx, by, self.t), "divert": div.name, "weather": "clear skies, unrestricted visibility",
             "link16": any(r["stn"] != "-" for r in whois)}
        text = brief.build_text(st, package, tl, plan, self.rng, (tx, ty), x)
        m.set_description_text(text["full"])
        m.set_description_bluetask_text(text["blue_task"])
        m.set_sortie_text(f"{date_str}  day {st.day}: {package.objective.description}")
        install_hook(m, st.campaign_id, manifest.sortie, package.id, despawn if o.ai_despawn_on_land else [], manifest.player_unit)
        ctx = {"date": date_str, "callsign": f"{pf.callsign}-1", "role": pf.role.value, "objective": package.objective.description,
               "comm1": plan.comm1, "comm2": plan.comm2, "waypoints": kn_rows, "jet": pspec.display,
               "numbering": ("B for the start point, then 1, 2, 3..." if pspec.first_wp_label else "waypoint 1 = start point"),
               "timeline": {k: tl[k] for k in ("launch", "marshal", "push", "tot", "egress", "rtb")},
               "bingo": f"{pspec.bingo_lbs:,}", "joker": f"{pspec.joker_lbs:,}", "weather": "CLEAR", "mode3": mode3, "laser": laser,
               "bulls_short": "last WP", "bullseye": latlon(bx, by, self.t), "whois": whois, "threats": text["threats"], "n_def": package.n_def}
        with tempfile.TemporaryDirectory(prefix="sqe_kb_") as td:
            for pg in render_pages(td, ctx):
                m.add_aircraft_kneeboard(pspec.dcs_type, pg)
            warns += list(dict.fromkeys(self.lo.warnings))
            counts = self._counts()
            m.save(str(out_path))
        return BuildResult(out_path, manifest, plan, player_wps, package, tl, text, counts, whois, warns)

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

    # ---- enemy ground -----------------------------------------------------------------------------------------------------
    def _spawn_opfor_ground(self, package, tx, ty, manifest):
        st, obj = self.state, package.objective
        if obj.type == ObjectiveType.BARCAP:
            return
        tgt = st.assets[obj.target_id]
        relevant = [tgt] + [st.assets[i] for i in tgt.defended_by]
        ewrs = [a for a in st.assets.values() if a.kind == AssetKind.EWR and not a.destroyed]
        if ewrs:
            relevant.append(min(ewrs, key=lambda a: dist(a.x, a.y, tx, ty)))
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
        skill = getattr(Skill, self.d.enemy_skill, Skill.High)
        base_count = sum(n for vname, n in comp if _vt(vname) is not None)
        form = F.Line if a.kind == AssetKind.ARMOR else F.Star
        g = self._platoon(self.red, a.id, comp, a.x, a.y, 90, form, scale=a.health)
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
        pt = lambda x, y: mapping.Point(x, y, self.t)
        cx, cy = self._safe_station(g)
        tanker_xy, awacs_unit = None, None
        hav_xy = offset(cx, cy, g.hdg + 45, 8 * NM)
        for s in package.support:
            cls = getattr(planes, s.dcs_class)
            alt, spd, freq = s.altitude_ft * FT, s.speed_kts * KPH, plan.freq(s.slot)
            if s.slot == "AWACS":
                x, y = offset(cx, cy, g.hdg + 90, 20 * NM)
                grp = self.m.awacs_flight(self.usa, f"{s.label} 1", cls, None, pt(x, y), race_distance=60 * NM, heading=int(g.hdg),
                                          altitude=alt, speed=spd, frequency=freq)
                callsigns.apply(grp, s.label, 1, callsigns.AWACS); grp.units[0].name = f"{s.label} 1-1"
                awacs_unit = grp.units[0]
            else:
                if s.from_carrier:
                    x, y = offset(g.bx, g.by, g.hdg + 180, 15 * NM); race = 20 * NM
                else:
                    x, y = offset(cx, cy, g.hdg - 90 if s.slot == "TANKER1" else g.hdg - 90, (10 if s.slot == "TANKER1" else 22) * NM); race = 40 * NM
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
            wps = plan_route(f.role, (base.x, base.y), geom, spec.profile, is_player=f.is_player, tanker_xy=None, stack_idx=idx)
            assign_times(wps, 0.0 if not f.is_player else o.launch_offset_min * 60.0, push_s)
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
            if w.action == "HOLD":
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct.stop_after_time(int(push_s)); wp.tasks.append(ct)
            elif w.action == "CAPORBIT":
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH)))
                ct.stop_after_time(stop); wp.tasks.append(ct)
            elif w.action == "BOMB":
                wp.tasks.append(task.Bombing(pt(w.x, w.y), group_attack=True))
            elif w.action == "CAS":
                if armor is not None:       # explicit attack order on the armor column (one group), then search the zone
                    wp.tasks.append(task.AttackGroup(armor.id, group_attack=True))
                wp.tasks.append(task.EngageTargetsInZone(pt(w.x, w.y), 8000, [task.Targets.All.GroundUnits.GroundVehicles]))
        if base.kind == BaseKind.AIRFIELD:
            g.land_at(self.apt[base.id])
        else:
            rtb = g.add_waypoint(pt(base.x, base.y), 600, 300 * KPH, "RTB")
            rtb.type, rtb.action = "Land", PointAction.Landing
            rtb.link_unit = rtb.helipad = self.ship[base.id].units[0].id
        return g

    def _trailing_steerpoints(self, package, rows, spec):
        """DIVERT, TKR and BULLSEYE come after RTB on the player's group, like Retribution (tanker/bullseye last)."""
        pf = package.player_flight
        g = next(gr for fl, gr in self.flight_groups if fl is pf)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        for name, x, y, _, alt, kts, _ in rows:
            a = 20000 * FT if name == "TKR" else 5000 * FT
            g.add_waypoint(pt(x, y), a, (spec.profile.aar_kts if name == "TKR" else 300) * KPH, name)

    # ---- Link 16 / SADL: the package flies as one network ------------------------------------------------------------------
    def _datalinks(self, package, awacs_unit) -> list:
        stn = {}
        whois = []
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

    # ---- JTAC -----------------------------------------------------------------------------------------------------------------
    def _spawn_jtac(self, package, plan, geom):
        x, y = offset(geom.tx, geom.ty, geom.hdg + 180, 6 * NM)
        g = self.m.vehicle_group(self.usa, "Axeman 1", _UN.Hummer, mapping.Point(x, y, self.t), heading=int(geom.hdg), group_size=1)
        g.units[0].name = f"JTAC-{package.id}"
        p0 = g.points[0]
        p0.tasks.append(task.FAC(callsign=1, frequency=int(plan.freq("JTAC") * 1e6), modulation=task.Modulation.AM, number=1))
        p0.tasks.append(task.SetInvisibleCommand(True))
        p0.tasks.append(task.SetImmortalCommand(True))

    # ---- enemy fighters: organised, late-activated, from the enemy side, arriving at TOT +/- 1-2 min ----------------
    def _spawn_defenders(self, package, tx, ty, tot_s, geom, manifest):
        st, d = self.state, self.d
        n_fl = package.n_def // 2
        if n_fl <= 0:
            return
        wings = [(w, st.assets[w.base_asset_id]) for w in st.enemy_air if w.available > 0 and not st.assets[w.base_asset_id].destroyed]
        wings.sort(key=lambda p: dist(p[1].x, p[1].y, tx, ty))
        if not wings:
            return
        skill = getattr(Skill, d.enemy_skill, Skill.High)
        speed_ms, pt = 232.0, (lambda x, y: mapping.Point(x, y, self.t))
        for i in range(n_fl):
            w, a = wings[i % len(wings)]
            fighters = [t for t in w.types if t in ENEMY_FIGHTERS] or ["MiG_29A"]
            tname = self.rng.choice(fighters)
            dd = dist(a.x, a.y, tx, ty)
            if dd < 25 * NM:      # their airfield is at the target: they scramble from beyond it, on the far side from us
                sx, sy = offset(tx, ty, geom.hdg, 12 * NM)
            else:
                sx, sy = offset(a.x, a.y, bearing(a.x, a.y, tx, ty), min(0.85 * dd, 60 * NM))
            arrive = tot_s + self.rng.uniform(-120, 120)
            spawn_s = max(30.0, arrive - dist(sx, sy, tx, ty) / speed_ms)
            g = self.m.flight_group(self.red, f"Bandit {i + 1}", getattr(planes, tname), None, pt(sx, sy), altitude=22000 * FT,
                                    speed=450 * KPH, maintask=task.CAP, group_size=2)
            load = enemy_cap_loadout(tname)
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"ENM-{a.id}-{i}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name)
            g.set_skill(skill)
            wp = g.add_waypoint(pt(tx, ty), 22000 * FT, 450 * KPH, "TGT")
            ct = task.ControlledTask(task.OrbitAction(int(22000 * FT), int(450 * KPH)))
            ct.stop_after_time(int(tot_s + 1500)); wp.tasks.append(ct)
            g.add_waypoint(pt(*offset(tx, ty, bearing(tx, ty, a.x, a.y), 25 * NM)), 22000 * FT, 450 * KPH, "EXT")
            if d.enemy_skill and self.o.enemy_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
            g.late_activation = True
            trig = triggers.TriggerOnce(comment=f"activate {g.name}")
            trig.add_condition(condition.TimeAfter(int(spawn_s)))
            trig.add_action(action.ActivateGroup(g.id))
            self.m.triggerrules.triggers.append(trig)
            if not load:
                self.warns.append(f"{tname}: no air-to-air loadout found; spawned unarmed")
            manifest.add("enemy_air", w.base_asset_id, names)
