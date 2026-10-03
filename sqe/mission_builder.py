"""Package -> SQE_Sortie.miz (Caucasus).

* Your flight (and wingmen) sit hot on the runway / carrier catapult, INS pre-aligned for the F-14B(U).
* Every other friendly flight is already airborne on the way to the MARSHAL point and holds there until PUSH.
* AI flights get unlimited fuel and despawn after landing (both switchable), so AI fuel/landing bugs can't bite.
* Only what the package needs is spawned: your flights, support, the target area, the SAMs that cover it,
  and enemy fighters sized from the abstract war.
"""
from __future__ import annotations
import copy
import datetime
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from dcs import mapping, planes, ships, task, vehicles
from dcs.mission import Mission, StartType
from dcs.point import PointAction
from dcs.terrain import Caucasus
from dcs.unit import Skill

from . import briefing as brief
from .aircraft import AIRCRAFT
from .debrief import Manifest, install_hook
from .difficulty import Difficulty
from .kneeboard import render_pages
from .loadouts import LoadoutLibrary, enemy_cap_loadout, ENEMY_FIGHTERS
from .models import AssetKind, BaseKind, ObjectiveType, Role
from .packages import Package
from .radio import RadioCfg, RadioLayout, RadioPlan, apply_player_presets, build_radio_plan
from .routes import (NM, FT, Wpt, assign_times, bearing, dist, leg_seconds, make_geometry, offset, plan_route)
from .state import CampaignState

KPH = 1.852
MAIN_TASK = {Role.CAP: task.CAP, Role.ESCORT: task.CAP, Role.SWEEP: task.FighterSweep, Role.SEAD: task.SEAD,
             Role.STRIKE: task.PinpointStrike, Role.CAS: task.CAS}


@dataclass
class MissionOptions:
    start_hour: int = 9
    start_minute: int = 0
    launch_offset_min: int = 5          # you are ready on the cat/runway at start; briefed launch is this many minutes in
    hold_minutes: int = 8               # buffer at MARSHAL before PUSH
    cap_minutes: int = 40               # time on station for CAP flights
    ai_unlimited_fuel: bool = True
    enemy_unlimited_fuel: bool = False
    ai_despawn_on_land: bool = True
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
        raise AttributeError(f"{self._ns.__name__} has no vehicle {name!r}")


_AD, _UN, _AR = _Veh(vehicles.AirDefence), _Veh(vehicles.Unarmed), _Veh(vehicles.Armor)
SITES = {
    "AAA":    [("ZU_23_Emplacement", 3), ("Ural_375_ZU_23", 2), ("ZSU_23_4_Shilka", 1)],
    "MANPAD": [("SA_18_Igla_manpad", 4), ("SA_18_Igla_comm", 1)],
    "SA-2":   [("S_75M_Volhov", 4), ("SNR_75V", 1), ("ZSU_23_4_Shilka", 1)],
    "SA-3":   [("x_5p73_s_125_ln", 4), ("snr_s_125_tr", 1), ("p_19_s_125_sr", 1)],
    "SA-6":   [("Kub_2P25_ln", 3), ("Kub_1S91_str", 1), ("ZSU_23_4_Shilka", 1)],
    "SA-11":  [("SA_11_Buk_LN_9A310M1", 3), ("SA_11_Buk_SR_9S18M1", 1), ("SA_11_Buk_CC_9S470M1", 1)],
    "SA-10":  [("S_300PS_5P85C_ln", 2), ("S_300PS_5P85D_ln", 2), ("S_300PS_40B6M_tr", 1), ("S_300PS_64H6E_sr", 1),
               ("S_300PS_54K6_cp", 1)],
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
    warnings: list = field(default_factory=list)


class MissionBuilder:
    def __init__(self, state: CampaignState, d: Difficulty, opts: MissionOptions | None = None,
                 loadouts: LoadoutLibrary | None = None, rng: random.Random | None = None):
        self.state, self.d = state, d
        self.o = opts or MissionOptions()
        self.lo = loadouts or LoadoutLibrary()
        self.rng = rng or random.Random()

    # =============================================================================================
    def build(self, package: Package, out_path: str | Path) -> BuildResult:
        st, o = self.state, self.o
        pf = package.player_flight
        if pf is None:
            raise ValueError("choose your flight first")
        warns: list = []
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        m = Mission(Caucasus())
        self.m, self.t = m, m.terrain
        self.usa, self.red = m.country("USA"), m.country("Russia")
        start = datetime.datetime(2024, 6, 12, o.start_hour, o.start_minute)
        m.start_time = start
        clock = lambda s: (start + datetime.timedelta(seconds=s)).strftime("%H:%M:%S")
        self.warns = warns

        tx, ty = self._target_xy(package)
        pbase = st.bases[pf.base_id]
        pspec = AIRCRAFT[pf.aircraft]
        geom = make_geometry(pbase.x, pbase.y, tx, ty, pspec.profile)
        manifest = Manifest(st.campaign_id, st.sortie_counter + 1, package.id, st.day)

        # ---- bases (all airfields get a coalition; carrier only if someone flies from it) ------------------
        self.ship, self.apt = {}, {}
        for b in st.bases.values():
            if b.kind == BaseKind.AIRFIELD:
                self.t.airports[b.airport].set_blue()
        for a in st.assets.values():
            if a.kind == AssetKind.AIRFIELD and a.airport:
                self.t.airports[a.airport].set_red()
        for bid in {f.base_id for f in package.flights}:
            self._place_base(st.bases[bid], tx, ty)
        atc = (o.carrier_atc_mhz if pbase.kind == BaseKind.CARRIER else self.t.airports[pbase.airport].atc_radio.uhf_hz / 1e6)

        rcfg = RadioCfg(o.carrier_tacan, o.carrier_link4_mhz)
        plan = build_radio_plan(package, st, atc, self.rng, o.layout, rcfg)

        # ---- support ---------------------------------------------------------------------------------------------
        tanker_xy = self._place_support(package, plan, geom)

        # ---- timeline (player first, it defines PUSH and TOT) -------------------------------------------------
        launch_s = o.launch_offset_min * 60.0
        pw = plan_route(pf.role, (pbase.x, pbase.y), geom, pspec.profile, is_player=True, tanker_xy=tanker_xy)
        assign_times(pw, launch_s)
        mshl = next((w for w in pw if w.action in ("HOLD", "CAPORBIT")), pw[-1])
        push_s = math.ceil((mshl.eta_s + (0 if pf.role == Role.CAP else o.hold_minutes * 60)) / 60.0) * 60.0
        assign_times(pw, launch_s, push_s)
        tgt = next((w for w in pw if w.action in ("BOMB", "SEAD", "SWEEP", "CAS") or w.name in ("ESC", "CAP1")), pw[-1])
        egr = next((w for w in pw if w.name == "EGR"), pw[-1])
        rtb_s = egr.eta_s + leg_seconds(egr, Wpt("RTB", pbase.x, pbase.y, 0, 300))
        tl = {"launch": clock(launch_s), "marshal": clock(mshl.eta_s), "push": clock(push_s), "tot": clock(tgt.eta_s),
              "egress": clock(egr.eta_s), "rtb": clock(rtb_s), "push_s": push_s, "tot_s": tgt.eta_s}

        # ---- friendly flights ---------------------------------------------------------------------------------------
        despawn, player_wps = [], []
        for idx, f in enumerate(package.flights):
            wps = self._spawn_flight(package, f, plan, geom, tanker_xy, push_s, tgt.eta_s, idx, manifest, despawn)
            if f.is_player:
                player_wps = wps
        # use the timed player waypoints (assign_times already ran) for the kneeboard
        for w, tw in zip(player_wps, pw):
            w.eta_s = tw.eta_s
        player_wps = pw + [Wpt("RTB", pbase.x, pbase.y, 0, 300, self._rtb_note(pspec), "", rtb_s)]

        if package.jtac:
            self._spawn_jtac(package, plan, geom, manifest)
        self._spawn_opfor(package, tx, ty, manifest)

        # ---- briefing, hook, kneeboard ---------------------------------------------------------------------------
        text = brief.build_text(st, package, tl, plan, player_wps, self.rng, (tx, ty))
        m.set_description_text(text["full"])
        m.set_description_bluetask_text(text["blue_task"])
        m.set_sortie_text(f"Day {st.day}: {package.objective.description}")
        install_hook(m, st.campaign_id, manifest.sortie, package.id, despawn if o.ai_despawn_on_land else [])
        import tempfile
        with tempfile.TemporaryDirectory(prefix="sqe_kb_") as td:      # kneeboard PNGs never touch your Missions folder
            for pg in render_pages(td, package, plan, player_wps, self.t, st, tl, clock, text["threats"],
                                   st.bases[pf.base_id].name):
                m.add_aircraft_kneeboard(pspec.dcs_type, pg)
            warns += [w for w in dict.fromkeys(self.lo.warnings)]
            m.save(str(out_path))
        return BuildResult(out_path, manifest, plan, player_wps, package, tl, text, warns)

    # =============================================================================================
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
            return f"Case I | TACAN {self.o.carrier_tacan} | ICLS {self.o.carrier_icls} | ATC COMM1 CH1"
        return "Land | tower on COMM1 CH1"

    def _place_base(self, base, tx, ty):
        o = self.o
        if base.kind == BaseKind.AIRFIELD:
            self.apt[base.id] = self.t.airports[base.airport]
            return
        hdg = (bearing(base.x, base.y, tx, ty) + 180) % 360
        pos = mapping.Point(base.x, base.y, self.t)
        cv = self.m.ship_group(self.usa, base.name, ships.Stennis, pos, heading=hdg)   # legacy free CVN-74, no deck crew
        cv.add_waypoint(pos.point_from_heading(hdg, 120 * NM), speed=o.carrier_speed_kts * KPH)
        uid = cv.units[0].id
        p0 = cv.points[0]
        p0.add_task(task.ActivateBeaconCommand(channel=int(o.carrier_tacan[:-1]), modechannel=o.carrier_tacan[-1],
                                               callsign="STN", unit_id=uid, aa=False))
        p0.add_task(task.ActivateICLSCommand(channel=o.carrier_icls, unit_id=uid))
        p0.add_task(task.ActivateLink4Command(frequency=o.carrier_link4_mhz, unit_id=uid))
        p0.add_task(task.ActivateACLSCommand(unit_id=uid))
        cv.set_frequency(int(o.carrier_atc_mhz * 1e6))
        self.ship[base.id] = cv

    def _place_support(self, package, plan, g):
        pt = lambda x, y: mapping.Point(x, y, self.t)
        tanker_xy = None
        for s in package.support:
            cls = getattr(planes, s.dcs_class)
            alt, spd, freq = s.altitude_ft * FT, s.speed_kts * KPH, plan.freq(s.slot)
            name = f"{s.label} {package.number}-1"
            if s.slot == "AWACS":
                x, y = offset(g.bx, g.by, g.hdg, min(0.25 * g.d, 80 * NM))
                x, y = offset(x, y, g.hdg + 90, 20 * NM)
                self.m.awacs_flight(self.usa, name, cls, None, pt(x, y), race_distance=60 * NM, heading=int(g.hdg),
                                    altitude=alt, speed=spd, frequency=freq)
            elif s.from_carrier:
                x, y = offset(g.bx, g.by, g.hdg + 180, 15 * NM)
                self._tanker(s, cls, x, y, g, alt, spd, freq, plan, name, 20 * NM)
            else:
                to_m = bearing(g.bx, g.by, *g.mshl)
                dm = dist(g.bx, g.by, *g.mshl)
                x, y = offset(g.bx, g.by, to_m, max((0.5 if s.slot == "TANKER1" else 0.85) * dm, 40 * NM))
                x, y = offset(x, y, to_m - 90 if s.slot == "TANKER1" else to_m + 90, 15 * NM)
                self._tanker(s, cls, x, y, g, alt, spd, freq, plan, name, 40 * NM)
                if s.slot == "TANKER1":
                    tanker_xy = (x, y)
        return tanker_xy

    def _tanker(self, s, cls, x, y, g, alt, spd, freq, plan, name, race):
        self.m.refuel_flight(self.usa, name, cls, None, mapping.Point(x, y, self.t), race_distance=race,
                             heading=int(g.hdg), altitude=alt, speed=spd, frequency=freq, tacanchannel=plan.tacan[s.slot])

    # ---- friendly flights -------------------------------------------------------------------------------------
    def _spawn_flight(self, package, f, plan, geom, tanker_xy, push_s, tot_s, idx, manifest, despawn) -> list:
        st, o = self.state, self.o
        spec = AIRCRAFT[f.aircraft]
        base = st.bases[f.base_id]
        pt = lambda x, y: mapping.Point(x, y, self.t)
        wps = plan_route(f.role, (base.x, base.y), geom, spec.profile, is_player=f.is_player,
                         tanker_xy=tanker_xy if f.is_player else None, stack_idx=idx)
        assign_times(wps, 0.0 if not f.is_player else o.launch_offset_min * 60.0, push_s)

        if f.is_player:       # hot on the runway / catapult
            if base.kind == BaseKind.CARRIER:
                g = self.m.flight_group_from_unit(self.usa, f.callsign, spec.dcs_type, self.ship[base.id],
                                                  maintask=MAIN_TASK[f.role], start_type=StartType.Runway, group_size=f.count)
            else:
                g = self.m.flight_group_from_airport(self.usa, f.callsign, spec.dcs_type, self.apt[base.id],
                                                     maintask=MAIN_TASK[f.role], start_type=StartType.Runway, group_size=f.count)
            first = 0
        else:                 # already airborne on the way to the marshal point
            s0 = wps[0]
            g = self.m.flight_group(self.usa, f.callsign, spec.dcs_type, None, pt(s0.x, s0.y),
                                    altitude=s0.alt_ft * FT, speed=s0.speed_kts * KPH, maintask=MAIN_TASK[f.role],
                                    group_size=f.count)
            first = 1
        names = []
        load = self.lo.for_role(f.aircraft, f.role)
        for i, u in enumerate(g.units, 1):
            u.name = f"{f.id}-{i}"
            names.append(u.name)
            u.pylons = copy.deepcopy(load)
            if f.is_player and f.aircraft == "F-14BU":
                u.set_property("INSAlignmentStored", True)
        g.set_skill(Skill.High)
        if f.is_player:
            u0 = g.units[0]
            u0.set_client() if o.player_is_client else u0.set_player()
            apply_player_presets(u0, plan, o.layout)
            g.set_frequency(plan.freq("FLIGHT"), radio_id=o.layout.comm2_radio_id)
            manifest.player_unit = u0.name
        else:
            g.set_frequency(next((e.mhz for e in plan.package_flights if e.callsign == f.callsign), 130.0))
            if o.ai_despawn_on_land:
                despawn.extend(names)
            if o.ai_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
        manifest.add("friendly", f.id, names, squadron=f.squadron_id, callsign=f.callsign, player=f.is_player)

        for w in wps[first:]:
            wp = g.add_waypoint(pt(w.x, w.y), w.alt_ft * FT, w.speed_kts * KPH, w.name)
            if f.is_player:
                if w.action == "BOMB":
                    wp.tasks.append(task.Bombing(pt(w.x, w.y), group_attack=True))
                continue
            if w.action == "HOLD":
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH),
                                                          pattern=task.OrbitAction.OrbitPattern.Circle))
                ct.stop_after_time(int(push_s))
                wp.tasks.append(ct)
            elif w.action == "CAPORBIT":
                ct = task.ControlledTask(task.OrbitAction(int(w.alt_ft * FT), int(w.speed_kts * KPH)))
                ct.stop_after_time(int(tot_s + o.cap_minutes * 60))
                wp.tasks.append(ct)
            elif w.action == "BOMB":
                wp.tasks.append(task.Bombing(pt(w.x, w.y), group_attack=True))
            elif w.action == "CAS":
                try:
                    wp.tasks.append(task.EngageTargetsInZone(mapping.Point(w.x, w.y, self.t), 8000,
                                                             [task.Targets.All.GroundUnits.GroundVehicles]))
                except Exception:
                    self.warns.append("CAS engage task could not be attached; A-10s will use their default behavior.")
        if base.kind == BaseKind.AIRFIELD:
            g.land_at(self.apt[base.id])
        else:
            cvu = self.ship[base.id].units[0]
            rtb = g.add_waypoint(pt(base.x, base.y), 600, 300 * KPH, "RTB")
            rtb.type, rtb.action = "Land", PointAction.Landing
            rtb.link_unit = rtb.helipad = cvu.id
        return wps

    # ---- JTAC -----------------------------------------------------------------------------------------------------------
    def _spawn_jtac(self, package, plan, geom, manifest):
        x, y = offset(geom.tx, geom.ty, geom.hdg + 180, 6 * NM)
        g = self.m.vehicle_group(self.usa, f"Axeman {package.number}-1", _UN.Hummer, mapping.Point(x, y, self.t),
                                 heading=int(geom.hdg), group_size=1)
        g.units[0].name = f"JTAC-{package.id}"
        p0 = g.points[0]
        p0.tasks.append(task.FAC(callsign=1, frequency=int(plan.freq("JTAC") * 1e6), modulation=task.Modulation.AM, number=1))
        p0.tasks.append(task.SetInvisibleCommand(True))
        p0.tasks.append(task.SetImmortalCommand(True))

    # ---- OpFor ----------------------------------------------------------------------------------------------------------------
    def _spawn_opfor(self, package, tx, ty, manifest):
        st = self.state
        obj = package.objective
        relevant, primary = [], None
        if obj.type != ObjectiveType.BARCAP:
            tgt = st.assets[obj.target_id]
            primary = tgt.id
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
                self._spawn_site(a, comp, manifest, primary=(a.id == primary))
        self._spawn_enemy_cap(tx, ty, manifest)

    def _spawn_site(self, a, comp, manifest, primary):
        total = sum(n for _, n in comp)
        names, k = [], 0
        skill = getattr(Skill, self.d.enemy_skill, Skill.High)
        line = a.kind == AssetKind.ARMOR
        for vname, n in comp:
            vtype = getattr(_AD, vname, None) if hasattr(vehicles.AirDefence, vname) or vname.lower() in {x.lower() for x in dir(vehicles.AirDefence)} else None
            if vtype is None:
                for ns in (_UN, _AR):
                    try:
                        vtype = getattr(ns, vname); break
                    except AttributeError:
                        continue
            if vtype is None:
                self.warns.append(f"unknown vehicle {vname}; skipped")
                continue
            for _ in range(max(1, round(n * a.health))):
                k += 1
                if line:
                    x, y = offset(a.x, a.y, 90, 45 * k)
                    ang = 0
                else:
                    ang = 360.0 * k / (total + 1)
                    x, y = offset(a.x, a.y, ang, 80 + 25 * k)
                g = self.m.vehicle_group(self.red, f"{a.id}-{k}", vtype, mapping.Point(x, y, self.t), heading=int(ang), group_size=1)
                g.units[0].name = f"{a.id}|{k}"
                try:
                    g.units[0].skill = skill
                except Exception:
                    pass
                names.append(g.units[0].name)
        manifest.add("asset", a.id, names, base_count=total, health_before=a.health, primary=primary)

    def _spawn_enemy_cap(self, tx, ty, manifest):
        st, d = self.state, self.d
        near = [(w, st.assets[w.base_asset_id]) for w in st.enemy_air
                if w.available > 0 and not st.assets[w.base_asset_id].destroyed
                and dist(st.assets[w.base_asset_id].x, st.assets[w.base_asset_id].y, tx, ty) < 150 * NM]
        near.sort(key=lambda p: dist(p[1].x, p[1].y, tx, ty))
        if not near:
            return
        avail = sum(w.available for w, _ in near)
        n = max(1, min(4, round(d.enemy_cap_per_air * avail)))
        skill = getattr(Skill, d.enemy_skill, Skill.High)
        for i in range(n):
            w, a = near[i % len(near)]
            fighters = [t for t in w.types if t in ENEMY_FIGHTERS] or ["MiG_29A"]
            tname = self.rng.choice(fighters)
            ang = bearing(a.x, a.y, tx, ty)
            p1 = offset(a.x, a.y, ang, 30 * NM)
            p2 = offset(*p1, ang + 90, 25 * NM)
            g = self.m.patrol_flight(self.red, f"Bandit {i + 1}", getattr(planes, tname), None,
                                     mapping.Point(*p1, self.t), mapping.Point(*p2, self.t), speed=700, altitude=7500, group_size=2)
            load = enemy_cap_loadout(tname)
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"ENM-{a.id}-{i}-{j}"
                u.pylons = copy.deepcopy(load)
                names.append(u.name)
            g.set_skill(skill)
            if self.o.enemy_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
            if not load:
                self.warns.append(f"{tname}: no air-to-air loadout found; spawned unarmed")
            manifest.add("enemy_air", w.base_asset_id, names)
