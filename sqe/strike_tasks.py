"""Strike, SEAD, DEAD and CAS tasking: the HARM / JSOW / bombing / CAS parts of the mission builder.

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o`, `self.groups_by_asset`
and the other fields the builder sets up; nothing here is called from outside the builder.
"""
from __future__ import annotations
import dataclasses
import math
import random

from dcs import mapping, task

from . import threatmap as tm
from . import samtier
from .aircraft import AIRCRAFT
from .loadouts import JSOW_PER_JET, JDAM_JETS, PEN_PER_JET, gbu_count
from . import profiles
from .models import SEAD_AIMS, AssetKind, ObjectiveType, Role
from .routes import AVOID_NM, FT, AGM88_LAUNCH_NM, JDAM_ALT_FT, JSOW_AXIS_DEG, JSOW_LAUNCH_NM, NM, assign_times, bearing, dist, objective_wp, offset, plan_route

JSOW_ATTACK_S = 240           # a JSOW slinger's release tasks end this long after the launch point's ETA, and it turns for home. Was 120 (v0.41.46; XO's run: releases came 25-60 s before the point). v0.41.362: 240 (judgment call): same marshal-exit lateness as the SLAM-ER (XO's run 2026-11-10 22-33-46, about 95 s late), plus margin
JSOW_AIM_ERR_M = 100           # a JSOW's aim point is the radar's last-known position give or take this much (the targeting is not perfect)
DEAD_GATE_BEFORE_TGT_S = 75    # fallback: if the DEAD flight never gets close, the radars are checked this long before its planned target time
AIR_GATE_KM = 100              # v0.41.214 (XO): was 70, the hold sits outside the MiG-31's P-33 reach (about 120 km) of the fight; judgment call. v0.41.203 text: 70               # v0.41.203: a strike / CAS flight with no radar site to wait on checks the air this far from its target (km); the hold, if any, is out here, short of the fight
AIR_HOLD_STRIKE_S = 900        # v0.41.235 (XO 2026-11-03): was 360; 15 min, the air fight takes time on every level. ...and holds at most this long (old judgment call: the Day-2 fight of XO's 2026-10-30 run lasted about that), then goes home (v0.41.205: it used to go in all the same and was shot down)
AIR_HOLD_CAS_S = 900           # v0.41.235 (XO 2026-11-03): was 240, the same 15 min as strikers now (XO overrides the old 'troops are waiting' shorter hold)
DEAD_GATE_KM = 40              # the radars are checked when the DEAD flight's lead is this close to the site (km); any still up and the package turns back
SA10_GATE_KM = samtier.get("SA-10", "gate_km")              # (S90 P4: per umbrella system in samtier.SYSTEMS) ...but never inside an SA-10's reach (55 km): against an SA-10 target, or under an SA-10 umbrella, the gate (and so the hold
                               # orbit) is this far from the SA-10. v0.39.21 run: Hornet 1 held 40 km from the Sukhumi SA-6, 26 km from the SA-10, and was shot down there
SEAD_WAVE_KM = 60              # SEAD packages in one mission whose targets are this close together reach their HARM points at the same moment (the builder's sync)
TRACK_RADARS = {"SNR_75V", "snr s-125 tr", "Kub 1S91 str", "S-300PS 40B6M tr", "Tor 9A331", "RPC_5N62V"}          # fire-control / track radars (unit type names as DCS stores them).
# The Tor carries its radar on the launcher: the vehicle IS the radar, so a Tor battery is blind only when its vehicles are down.
TOR_VARIANTS = {"SA-15"}       # point defences that cover a long-range site and shoot down HARMs, GBUs and JSOWs aimed at it
TOR_COVER_KM = 12.0           # a Tor this close to a SEAD/DEAD target, or to the strike leg into it, is part of the job: HARMs and JSOWs go at it, the DEAD gate waits for it
SEARCH_RADARS = {"p-19 s-125 sr", "SA-11 Buk SR 9S18M1", "S-300PS 64H6E sr", "1L13 EWR", "55G6 EWR", "RLS_19J6"}      # S90 P3b: + the SA-5's ST-68U "Tin Shield"
CAS_ZONE_M = 9000              # the AI CAS engage circle around TGT (m): the column stays within about 2 km of the point (CAS_ENEMY_ADVANCE_M, CAS_PATROL_MAX_M); S92 tried 18000 and put it back (a wider circle only adds neighbouring air defence)
KPH = 1.852


def _expend_for(each):
    """The DCS `Expend` quantity for `each` bombs per aim point: four, two, else one."""
    return task.Expend.Four if each >= 4 else (task.Expend.Two if each >= 2 else task.Expend.One)


def _span(pts):
    """The largest distance between two of the points (0.0 for none)."""
    return max((dist(p[0], p[1], q[0], q[1]) for p in pts for q in pts), default=0.0)


class StrikeTasks:
    def _sead_attack_tasks(self, package, f, wp, w, armor):
        """The HARM attack tasks of a SEAD flight's attack waypoint: its own site, neighbouring sites, covering Tors, the umbrella."""
        # The whole site, not one radar: an S-300 track radar only radiates while it is tracking, so a HARM task aimed at it
        # has nothing to shoot at (v0.39.7 run: the SEAD pair never fired). Aimed at the group, the AI fires at whatever radiates (an escort CAS SEAD did).
        # The launchers are still the DEAD flight's job: HARMs only kill what radiates.
        # v0.41.6: OPEN FIRE, not weapon free: only the groups tasked below (its own site, the Tors that guard it, the umbrella). Weapon free,
        # Viper 5-2 fired at another package's SA-6 from 89 km; the radar went quiet and the HARM homed on Squid 1-4's radar instead.
        wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
        # v0.41.24: no clear HARM axis: the neighbouring sites still in reach of the launch point get these HARMs first
        for nid_ in getattr(self, "_agm88_threat", {}).get(package.id, []):
            ng_ = self.groups_by_asset.get(nid_)
            if ng_ is not None:
                cth = task.ControlledTask(task.AttackGroup(ng_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                cth.stop_after_time(int(w.eta_s) + 300); wp.tasks.append(cth)
        if package.objective.type in (ObjectiveType.CAS, ObjectiveType.STRIKE):
            # v0.41.167: a STRIKE escort too (L2 run: the supply-depot strike's HARMs were aimed at the depot, the SA-2/SA-3 stayed up and killed 3 jets)
            # v0.41.20: a CAS escort: HARMs on the SA-2/3/6 sites that cover the CAS target, through the whole CAS window
            from .war import covering_sams
            for cs_ in covering_sams(self.state, self.state.assets[package.objective.target_id], short=package.objective.type == ObjectiveType.CAS):
                cg_ = self.groups_by_asset.get(cs_.id)
                if cg_ is not None:
                    ctc = task.ControlledTask(task.AttackGroup(cg_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                    ctc.stop_after_time(int(w.eta_s) + 900); wp.tasks.append(ctc)
        # The package's second SEAD flight opens on the Tors that guard the site (they shoot the HARMs down, v0.39.16 run), then joins on the site.
        seads_ = [x for x in package.flights if x.role == Role.SEAD and not x.tag]
        if len(seads_) > 1 and any(x is f or x.id == f.id for x in seads_[1:]):
            for _, tg_ in self._cover_tors(package):
                ctt = task.ControlledTask(task.AttackGroup(tg_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                ctt.stop_after_time(int(w.eta_s) + 180); wp.tasks.append(ctt)
            # v0.41.4: ...then it waits on the umbrella too. In the v0.41.3 run the Gudauta SA-10 stayed quiet through the first HARM flight's
            # window (one HARM went at it), lit up a minute later and killed the whole JSOW flight; a second flight still holding HARMs for it covers that.
            um_ = tm.umbrella_site(self.state, self.state.assets.get(package.objective.target_id))
            ug_ = self.groups_by_asset.get(um_.id) if um_ else None
            if ug_ is not None and um_.id != package.objective.target_id:
                ctu = task.ControlledTask(task.AttackGroup(ug_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                ctu.stop_after_time(int(w.eta_s) + 420); wp.tasks.append(ctu)
            # v0.41.22: no clear JSOW axis: the neighbouring sites that still reach the JSOW launch point get this flight's HARMs as well
            for nid_ in getattr(self, "_jsow_threat", {}).get(package.id, []):
                ng_ = self.groups_by_asset.get(nid_)
                if ng_ is not None:
                    ctn = task.ControlledTask(task.AttackGroup(ng_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                    ctn.stop_after_time(int(w.eta_s) + 420); wp.tasks.append(ctn)
        elif seads_ and (seads_[0] is f or seads_[0].id == f.id):
            # the first HARM flight opens on the umbrella (the SA-10 covering this target): it reaches every jet in the wave, so it goes first
            um_ = tm.umbrella_site(self.state, self.state.assets.get(package.objective.target_id))
            ug_ = self.groups_by_asset.get(um_.id) if um_ else None
            if ug_ is not None:
                ctu = task.ControlledTask(task.AttackGroup(ug_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                ctu.stop_after_time(int(w.eta_s) + 180); wp.tasks.append(ctu)
        ct = task.ControlledTask(task.AttackGroup(armor.id, weapon_type=task.WeaponType.ARM, group_attack=True))
        ct.stop_after_time(int(w.eta_s) + 600)
        wp.tasks.append(ct)
        for _, tg_ in self._cover_tors(package):            # a second pass at the Tors that guard the site, with whatever HARMs are left
            ct2 = task.ControlledTask(task.AttackGroup(tg_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
            ct2.stop_after_time(int(w.eta_s) + 780); wp.tasks.append(ct2)

    def _dead_gate(self, package, f, g, wps, first, stw, tot_s, base):
        """The radar gate for a Close DEAD package's strikers and covering fighters. -> the gate dict, or None."""
        st, o = self.state, self.o
        pt = self._pt
        gate = None
        obj_ = package.objective
        # v0.41.158: a STRIKE / CAS behind a SEAD (obj.after) gates on the long-reach site(s) it waits on, the way a Close DEAD gates on its target: the first of
        # them whose radars are still up in this mission (the SEAD's verdict failed), else the first. The radars of the others are already out (_blind_sites).
        fol_ = obj_.type in (ObjectiveType.STRIKE, ObjectiveType.CAS) and bool(obj_.after)
        gsite_ = obj_.target_id
        if fol_:
            from .war import after_sites, site_blind_today
            live_ = [x for x in after_sites(obj_) if x in self.state.assets and not self.state.assets[x].destroyed]
            gsite_ = next((x for x in live_ if not site_blind_today(self.state, x)), live_[0] if live_ else "")
        air_only_ = (not fol_) and obj_.type in (ObjectiveType.STRIKE, ObjectiveType.CAS) and f.role in (Role.STRIKE, Role.CAS) and (obj_.aim != "STANDOFF" or not any(getattr(x_, "kit", "") for x_ in package.flights))      # v0.41.203: the fighters-clear gate on its own; S60: a stand-off EWR strike a person flies (no kit flight, plain GBUs) keeps it
        if (not f.tag and ((obj_.type == ObjectiveType.DEAD and obj_.aim not in SEAD_AIMS) or fol_ or air_only_) and gsite_ and tot_s is not None
                and f.role in (Role.STRIKE, Role.CAS, Role.TARCAP, Role.ESCORT, Role.SWEEP) and tot_s - DEAD_GATE_BEFORE_TGT_S > 10
                and (f.role in (Role.STRIKE, Role.CAS) or stw is None)):               # a TARCAP / escort on its own station is already outside the threat
            # radar gate: the DEAD flight, and its escorts and sweeps, break off if the site's radars are still up when the DEAD flight commits
            added = [w.name for w in wps[first:]]
            n0_ = len(g.points) - len(added)                           # points before the first one added above (the start point)
            tw_ = objective_wp(wps)
            ti_ = next((k for k, w in enumerate(wps[first:]) if w is tw_), 1)
            ai_ = bool(not f.is_player or o.player_is_ai)
            # Lua route indices are 1-based. The abort goes to the point AFTER egress (the way home). Pointing at EGR itself sent the
            # v0.39.16 run's Viper 1 back over the target (39.8 to 33.8 km in 60 s, GBUs dropped, a jet lost to the Tor).
            to_ = (n0_ + added.index("EGR") + 2) if "EGR" in added else None
            if to_ is None and ai_ and wps[first:]:
                lw = wps[-1]                                            # a stand-off flight has no egress: a return point on the way home, so the turn-back
                bx, by = offset(base.x, base.y, bearing(base.x, base.y, lw.x, lw.y), 20 * NM)   # does not cut straight from cruise altitude to the runway
                g.add_waypoint(pt(bx, by), min(lw.alt_ft, 9000) * FT, 320 * KPH, "ABORT")
                to_ = len(g.points)
            leg_ = [(w.x, w.y) for w in wps if w.name in ("IP", "TGT", "REL")]
            also_ = [a_.id for a_, _ in self._cover_tors(package, leg_)]          # the route check: the Tors that cover the site or the run in
            tga_ = st.assets.get(gsite_)
            um_ = tm.umbrella_site(st, tga_)
            gm_ = samtier.get(tga_.variant, "gate_km") if (tga_ is not None and tga_.variant in tm.UMBRELLA_VARIANTS) else (AIR_GATE_KM if air_only_ else DEAD_GATE_KM)
            gate = {"t": tot_s - DEAD_GATE_BEFORE_TGT_S, "site": gsite_, "grp": g.name, "also": also_, "gm": gm_ * 1000,
                    "ux": um_.x if um_ else None, "uz": um_.y if um_ else None, "um": samtier.get(um_.variant, "gate_km") * 1000 if um_ else None,
                    "from": n0_ + max(0, ti_ - 1) + 1, "to": to_, "ai": ai_, "dead": f.role in (Role.STRIKE, Role.CAS), "you": bool(f.is_player), "pkg": package.id,
                    "acap": AIR_HOLD_CAS_S if f.role == Role.CAS else AIR_HOLD_STRIKE_S, "tx": tga_.x if tga_ is not None else None, "tz": tga_.y if tga_ is not None else None}
        return gate

    def _cas_tasks(self, wp, w, armor, tot_s, floor_ft=0, per_unit=False):
        """AI CAS: look at the fight, attack the column, then keep working the zone. Time-boxed so they eventually go home.
        `w` is the TGT point (position and ETA); `wp` is the point the tasks go on (the IP before it since Stage C, else TGT). Open Fire is set by the caller (S92).
        S92 `per_unit` (a moving column with the stock Maverick + cluster kit): the air defence travelling with the column is attacked unit by unit first, missile
        vehicles with a Maverick (ASM), guns with cluster bombs, each at the floor altitude; then the whole group for the rest."""
        t0 = int(w.eta_s)
        if armor is not None:
            alt_m = int(floor_ft * 0.3048) if floor_ft else None
            if per_unit:
                for u_, cls_, _f, _n in profiles.column_ad_units(armor):
                    cu = task.ControlledTask(task.AttackUnit(u_.id, weapon_type=task.WeaponType.ASM if cls_ == "sam" else task.WeaponType.ClusterBombs,
                                                             group_attack=False, altitude_enabled=bool(alt_m), altitude=alt_m or 0))
                    cu.stop_after_time(t0 + 420)
                    wp.tasks.append(cu)
            # S31a: over short-range air defence the attack altitude is set to the floor (AttackGroup altitude, metres), or the AI dives to its own delivery height. EngageTargetsInZone has no altitude parameter.
            ct = task.ControlledTask(task.AttackGroup(armor.id, weapon_type=task.WeaponType.Auto, group_attack=False, altitude=alt_m))
            ct.stop_after_time(t0 + 420)
            wp.tasks.append(ct)
        ct2 = task.ControlledTask(task.EngageTargetsInZone(mapping.Point(w.x, w.y, self.t), CAS_ZONE_M, [task.Targets.All.GroundUnits.GroundVehicles]))
        ct2.stop_after_time(t0 + 1080)
        wp.tasks.append(ct2)

    def _cas_done(self, package, f, g, armor, ai_a2g):
        """S93 (XO 2026-11-16, run 19-23-07): the target group is the CAS objective. Record an AI CAS flight for the hook, which sends it to its EGR point once the group
        is done (or the flight strays from it): see the CAS DONE block in debrief.py. The EGR point also runs SQE_PASSED, so a flight already past it is left alone.
        AI scripting only (a person's flight is not commanded); the route itself is unchanged."""
        if not ai_a2g or f.role != Role.CAS or f.tag or armor is None or not getattr(armor, "units", None):
            return
        ei_ = next((i_ for i_, p_ in enumerate(g.points) if getattr(p_, "name", "") == "EGR"), None)
        if ei_ is None:
            return
        g.points[ei_].tasks.append(task.RunScript(f"SQE_PASSED('{g.name}')"))
        u0_ = armor.units[0].position
        self._casdone.append({"grp": g.name, "units": [u_.name for u_ in armor.units], "to": ei_ + 1, "tx": float(u0_.x), "tz": float(u0_.y)})

    def _agm88_time(self, package, geom, base, P0):
        """When this package's AI HARM flights reach their HARM point in this mission (push time + the push-to-HARM-point leg on its geometry)."""
        sf = next((f for f in package.flights if f.role == Role.SEAD and not f.tag), None)
        if sf is None:
            return None
        from .mission_builder import stagger                # the builder's module imports this one, so it is imported here, when called
        spec = AIRCRAFT[sf.aircraft]
        wps = plan_route(Role.SEAD, (base.x, base.y), geom, spec.profile, is_player=False, tanker_xy=None, keep_out=self._umbrella_keep(package), agm88_deg=self._agm88_deg(package, geom))
        assign_times(wps, 0.0, P0 + stagger(package, Role.SEAD))
        tw = objective_wp(wps)
        return tw.eta_s if tw is not None and tw.action == "SEAD" else None

    def _umbrella_keep(self, package):
        """plan_route's keep_out for a package's HARM point: the umbrella SA-10's reach (AGM88_LAUNCH_NM) when the target sits under one and,
        v0.41.24, every other live SA-2/3/6/11/10 the package is not sent against, by its reach (the v0.41.23 run: a Gudauta SEAD flight's HARM
        point sat 30 nm from the Sukhumi S-300 another package was attacking, and three Hornets died to it). None when there is nothing to keep out of."""
        if not package.objective.target_id or package.objective.target_id not in self.state.assets:
            return None
        out = []
        if package.objective.type == ObjectiveType.DEAD:
            um = tm.umbrella_site(self.state, self.state.assets.get(package.objective.target_id))
            if um:
                out.append((um.x, um.y, samtier.get(um.variant, "harm_nm")))
        out += self._zone_sams(package)
        return out or None

    def _agm88_deg(self, package, geom) -> float:
        """v0.41.24: the HARM shooters' approach, in degrees off the package axis: the first of 0, 15, 30 either side whose launch point (pushed
        out as plan_route pushes it, up to 40 nm further) and IP clear the umbrella and every other SAM the package is not sent against. None
        clear: the one with the most room, and the package's HARM flights also fire on the sites still in reach (self._agm88_threat)."""
        tid = package.objective.target_id
        if not tid or tid not in self.state.assets:
            return 0
        c_ = getattr(self, "_agm88_c", {})
        if package.id in c_:
            return c_[package.id]
        kos = self._umbrella_keep(package) or []
        h0 = max(8.0, min(AGM88_LAUNCH_NM, geom.d / NM * 0.8 - 6))
        def place(deg):
            ax = geom.hdg + 180 + deg
            hn = h0
            while hn < AGM88_LAUNCH_NM + 40 and any(dist(*offset(geom.tx, geom.ty, ax, hn * NM), kx, ky) < knm * NM for kx, ky, knm in kos):
                hn += 1.0
            pts = [offset(geom.tx, geom.ty, ax, (hn + k) * NM) for k in (0, 6)]
            return pts, min((dist(x, y, kx, ky) / NM - knm for x, y in pts for kx, ky, knm in kos), default=999.0)
        best = None
        for deg in self.AGM88_AXES:
            pts, sl = place(deg)
            if sl >= 0:
                best = (deg, sl, pts)
                break
            if best is None or sl > best[1]:
                best = (deg, sl, pts)
        if best[1] < 0:
            zs = self._zone_sams(package)
            ids = [a.id for a in self.state.assets.values() if (a.x, a.y, AVOID_NM.get(a.variant)) in zs
                   and any(dist(x, y, a.x, a.y) < AVOID_NM[a.variant] * NM for x, y in best[2])]
            self._agm88_threat = getattr(self, "_agm88_threat", {})
            self._agm88_threat[package.id] = ids
        c_[package.id] = best[0]
        self._agm88_c = c_
        return best[0]

    def _rel_kind(self, package, f) -> str:
        """v0.41.299 (XO 2026-11-05): "SLAM" for a Standoff Strike's SLAM-ER flight, "JDAM" for an AI striker that drops JDAMs (F-16C, F/A-18C, F-14B) on a strike or a counter-air
        strike (not a runway strike: it lays its bombs along the strip), else "". These flights release short of the target (routes.plan_route `rel`) and fly the high profile. A person's
        own flight is never one (he flies the run himself); in the all-AI test it is."""
        if f.tag or f.role != Role.STRIKE or (f.is_player and not self.o.player_is_ai):
            return ""
        if getattr(f, "kit", "") == "SLAM":
            return "SLAM"
        o = package.objective
        if getattr(f, "kit", "") or f.aircraft not in JDAM_JETS or o.aim == "RUNWAY":
            return ""
        return ""        # v0.41.317 (XO 2026-11-06, three runs, no guided-bomb release): "JDAM" is retired. A quiet-run striker flies a target waypoint on the target with the plain bomb task and its jet's own profile, as before v0.41.299; the AI works out its own release. Only the Standoff Strike (SLAM) is told where to launch.

    def _flight_profile(self, f, package):
        """The route profile a flight is planned with. A release-point striker (_rel_kind) gets its jet's profile with the strike altitude raised to JDAM_ALT_FT and the LOW tier closed
        (a JDAM released at 500 ft has almost no reach); one copy per jet, so the (role, profile) keys of the tier table stay stable. Everyone else: the jet's own profile."""
        p = AIRCRAFT[f.aircraft].profile
        if not self._rel_kind(package, f):
            return p
        cache = self.__dict__.setdefault("_rel_profiles", {})
        q = cache.get(f.aircraft)
        if q is None:
            base_ = p.alt_ft.get(Role.STRIKE, 20000)
            q = cache[f.aircraft] = dataclasses.replace(p, alt_ft={**p.alt_ft, Role.STRIKE: max(base_, JDAM_ALT_FT)}, no_low=True,
                                                        med_alt_ft=p.med_alt_ft or max(10000, int(round(base_ * 0.6 / 1000.0)) * 1000))
        return q

    def _jsow_side(self, package, geom) -> float:
        """The JSOW flight's approach, as a multiple of JSOW_AXIS_DEG off the HARM shooters' axis. v0.41.22: the first axis (30, 50, 15 or
        70 degrees either side) whose launch point and IP sit outside the reach of every other live SA-2/3/6/11/10 (the v0.41.21 scan: JSOW flights
        launched 20 nm from a neighbouring SA-2 nobody was suppressing). None clear: the axis with the most room, and the package's second HARM
        flight is also tasked on the sites still in reach (self._jsow_threat)."""
        tid = package.objective.target_id
        if package.objective.aim not in SEAD_AIMS or package.objective.type != ObjectiveType.DEAD or not tid:        # v0.41.299: a Standoff Strike (STRIKE, aim STANDOFF) has no HARM shooters to come in beside
            return 0
        c_ = getattr(self, "_jsow_c", {})
        if package.id in c_:
            return c_[package.id]
        st = self.state
        tga_ = st.assets[tid]
        um_ = tm.umbrella_site(st, tga_)
        skip = tm.cluster_ids(tga_) | ({um_.id} if um_ else set())
        sams = [a for a in st.assets.values() if a.kind == AssetKind.SAM and a.variant in AVOID_NM and not a.destroyed and a.health > 0.25
                and not getattr(a, "suppressed", False) and a.id not in skip]
        jn = max(8.0, min(JSOW_LAUNCH_NM, geom.d / NM * 0.8 - 6))
        def slack(deg):
            pts = [offset(geom.tx, geom.ty, geom.hdg + 180 + deg, (jn + k) * NM) for k in (0, 6)]      # the launch point and the IP 6 nm before it
            return min((dist(x, y, a.x, a.y) / NM - AVOID_NM[a.variant] for x, y in pts for a in sams), default=999.0)
        best = None
        for deg in self.JSOW_AXES:
            sl = slack(deg)
            if sl >= 0:
                best = (deg, sl)
                break
            if best is None or sl > best[1]:
                best = (deg, sl)
        deg = best[0]
        if best[1] < 0:
            pts = [offset(geom.tx, geom.ty, geom.hdg + 180 + deg, (jn + k) * NM) for k in (0, 6)]
            self._jsow_threat = getattr(self, "_jsow_threat", {})
            self._jsow_threat[package.id] = [a.id for a in sams if any(dist(x, y, a.x, a.y) < AVOID_NM[a.variant] * NM for x, y in pts)]
        c_[package.id] = deg / JSOW_AXIS_DEG
        self._jsow_c = c_
        return c_[package.id]

    def _cover_tors(self, package, leg=None) -> list:
        """The Tor batteries in this mission that cover the package's target site: within TOR_COVER_KM of the site, or of the strike leg into it
        (leg = [(x, y), ...], e.g. IP to target). Returns [(asset, group)]; only batteries that are live in this mission (a group to task)."""
        tid = package.objective.target_id
        if not tid or tid not in self.state.assets:
            return []
        t, out = self.state.assets[tid], []
        for aid, g in self.groups_by_asset.items():
            a = self.state.assets.get(aid)
            if a is None or aid == tid or a.variant not in TOR_VARIANTS or a.destroyed:
                continue
            near = dist(a.x, a.y, t.x, t.y) <= TOR_COVER_KM * 1000
            if not near and leg and len(leg) >= 2:
                near = tm.poly_dist(a.x, a.y, leg) <= TOR_COVER_KM * 1000
            if near:
                out.append((a, g))
        return sorted(out, key=lambda ag: dist(ag[0].x, ag[0].y, t.x, t.y))

    def _jsow_ramp_tasks(self, wp, f, package, eta_s=None) -> None:
        """v0.41.313 (XO 2026-11-06): the JSOW-As of a Standoff Counter-Air, one per aim point: the first parked jet and the one furthest from it (the JSOW's cluster
        submunitions cover the spots between), else the middle of the ramp. Same attack window and timed return fire as the other JSOW releases."""
        pts = list(getattr(self, "_ramp_pts", []) or [])
        if not pts:
            r_ = self._ramp_xy(self.state.assets[package.objective.target_id])
            pts = [r_ if r_ is not None else self._jitter_primary(package, 0.0, 0.0)]
        n_ = max(1, JSOW_PER_JET.get(f.aircraft, 2))
        aims = [pts[0]]
        if len(pts) > 1 and n_ > 1:
            aims.append(max(pts, key=lambda q: math.hypot(q[0] - pts[0][0], q[1] - pts[0][1])))
        each = max(1, n_ // len(aims))
        exp = task.Expend.Four if each >= 4 else (task.Expend.Two if each >= 2 else task.Expend.One)
        wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))   # v0.41.327 (XO): designated points only, no hunting
        if eta_s is not None:
            rf_ = task.ControlledTask(task.OptROE(task.OptROE.Values.ReturnFire)); rf_.start_after_time(int(eta_s + JSOW_ATTACK_S)); wp.tasks.append(rf_)
        for x, y in aims:
            bt_ = task.ControlledTask(task.Bombing(mapping.Point(x, y, self.t), expend=exp, group_attack=True))
            if eta_s is not None:
                bt_.stop_after_time(int(eta_s + JSOW_ATTACK_S))
            wp.tasks.append(bt_)

    def _pen_runway_tasks(self, wp, f, package, eta_s=None) -> None:
        """S51 (S50 probe): the AGM-154C of the F-15E's PEN kit on the runway, one Bombing task per weapon of the flight (Expend One, group attack, the stop time ETA + JSOW_ATTACK_S), each at
        the field's reference point (the airport's position, the point the hook's runway rectangle is centred on) plus its own random error up to JSOW_AIM_ERR_M: the probe's own tasks, 8 of 8
        JSOW-Cs landed in the rectangle. One aim point, so the AI's habit of putting several weapons on the first aim points of a flight does not matter. ROE Open Fire (designated points only, as
        the other AI strikes since v0.41.396 and the ramp JSOWs; the probe itself ran Weapon Free), Return Fire once the window ends."""
        a_ = self.state.assets.get(package.objective.target_id)
        ap_ = self.t.airports.get(a_.airport) if (a_ is not None and getattr(a_, "airport", None)) else None
        if ap_ is not None:
            cx, cy = ap_.position.x, ap_.position.y
        elif a_ is not None:
            cx, cy = a_.x, a_.y
        else:
            return
        rng = random.Random(f"{self.state.campaign_id}:{package.id}:{f.id}:pen")
        wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
        if eta_s is not None:
            rf_ = task.ControlledTask(task.OptROE(task.OptROE.Values.ReturnFire)); rf_.start_after_time(int(eta_s + JSOW_ATTACK_S)); wp.tasks.append(rf_)
        for _ in range(max(1, f.count * PEN_PER_JET.get(f.aircraft, 2))):
            ang, d = rng.uniform(0, 2 * math.pi), JSOW_AIM_ERR_M * math.sqrt(rng.random())
            bt_ = task.ControlledTask(task.Bombing(mapping.Point(cx + math.cos(ang) * d, cy + math.sin(ang) * d, self.t), expend=task.Expend.One, group_attack=True))
            if eta_s is not None:
                bt_.stop_after_time(int(eta_s + JSOW_ATTACK_S))
            wp.tasks.append(bt_)

    def _ewr_units(self, package, site=None) -> list:
        """S60: the early-warning radar vehicles of an EWR strike's target (the group's units of an EWR type), else the group's first unit. [] when the group is not built."""
        site = site if site is not None else self.groups_by_asset.get(package.objective.target_id)
        us_ = list(getattr(site, "units", None) or [])
        radars_ = [u for u in us_ if str(getattr(u, "type", "")) in SEARCH_RADARS]
        return radars_[:1] or us_[:1]

    def _ewr_standoff_tasks(self, wp, f, site, package, eta_s=None) -> None:
        """S60 (XO 2026-11-12: EWR strikes are stand-off only): the stand-off weapons of an EWR strike (the F-15E's JSOW-C or the F-16's JSOW-A) on the EWR vehicle: one Bombing task per weapon of the
        flight (Expend One, group attack, the stop time ETA + JSOW_ATTACK_S, as the runway JSOW-Cs of S51), each aimed at the radar's position plus its own random error up to JSOW_AIM_ERR_M. Not at the
        covering Tors or the site's other vehicles (an EWR has none that matter). ROE Open Fire, designated points only (as every AI strike since v0.41.396), Return Fire once the window ends."""
        us_ = self._ewr_units(package, site)
        a_ = self.state.assets.get(package.objective.target_id)
        pts_ = [(u.position.x, u.position.y) for u in us_] or ([(a_.x, a_.y)] if a_ is not None else [])
        if not pts_:
            return
        per_ = (PEN_PER_JET if getattr(f, "kit", "") == "PEN" else JSOW_PER_JET).get(f.aircraft, 2)
        rng = random.Random(f"{self.state.campaign_id}:{package.id}:{f.id}:ewr")
        wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
        if eta_s is not None:
            rf_ = task.ControlledTask(task.OptROE(task.OptROE.Values.ReturnFire)); rf_.start_after_time(int(eta_s + JSOW_ATTACK_S)); wp.tasks.append(rf_)
        for _ in range(max(1, f.count * per_)):
            cx, cy = pts_[0]
            ang, d = rng.uniform(0, 2 * math.pi), JSOW_AIM_ERR_M * math.sqrt(rng.random())
            bt_ = task.ControlledTask(task.Bombing(mapping.Point(cx + math.cos(ang) * d, cy + math.sin(ang) * d, self.t), expend=task.Expend.One, group_attack=True))
            if eta_s is not None:
                bt_.stop_after_time(int(eta_s + JSOW_ATTACK_S))
            wp.tasks.append(bt_)

    def _jsow_tasks(self, wp, f, site, package, eta_s=None) -> None:
        """A JSOW slinger's attack from its launch point: one release per radar of the target site (search and track radars; the first two
        vehicles of a site whose radars ride on the launchers), aimed at the radar's last-known position give or take JSOW_AIM_ERR_M. The
        flight's JSOWs are shared out between the aim points. A radar that shuts down to dodge the HARMs is still where it was last seen."""
        if package.objective.type == ObjectiveType.COUNTER_AIR and package.objective.aim != "SWEEP":
            self._jsow_ramp_tasks(wp, f, package, eta_s)               # v0.41.313: a Standoff Counter-Air aims at the jets parked on the ramp, not at a SAM site
            return
        if package.objective.type == ObjectiveType.STRIKE and package.objective.aim == "STANDOFF" and getattr(f, "kit", "") in ("JSOW", "PEN"):
            self._ewr_standoff_tasks(wp, f, site, package, eta_s)      # S60: the EWR strike (the only STRIKE + STANDOFF job with a JSOW / PEN flight): every weapon on the EWR vehicle
            return
        if package.objective.type == ObjectiveType.STRIKE and package.objective.aim == "RUNWAY":
            self._pen_runway_tasks(wp, f, package, eta_s)              # S51: the F-15E's standoff runway crater: every JSOW-C at the middle of the runway
            return
        if site is None or not site.units:
            return
        radars = [u for u in site.units if str(getattr(u, "type", "")) in TRACK_RADARS | SEARCH_RADARS]
        aims = radars[:3] or list(site.units)[:2]
        aims += [g_.units[0] for _, g_ in self._cover_tors(package) if g_.units]          # and the Tors that guard it (they shoot JSOWs down)
        if package.objective.aim == "STANDOFF":            # Standoff DEAD: the launchers too (the site is only dead when they are)
            # v0.41.47: two JSOWs a jet (the Hornet kit went from four to two), so two aim points: the covering Tor first (it shoots JSOWs and HARMs down), then a
            # launcher, then the radars (the HARM flights go for those). Before: two radars, the Tors, the launchers, up to four.
            tors_ = [g_.units[0] for _, g_ in self._cover_tors(package) if g_.units]
            lnx_ = [u for u in site.units if u not in radars and u not in tors_ and " ln" in str(getattr(u, "type", "")).lower()]
            aims = (tors_[:1] + lnx_[:1] + (radars[:3] or list(site.units)[:2]) + tors_[1:] + lnx_[1:])[:JSOW_PER_JET.get(f.aircraft, 2)]
        each = max(1, JSOW_PER_JET.get(f.aircraft, 2) // len(aims))
        exp = task.Expend.Four if each >= 4 else (task.Expend.Two if each >= 2 else task.Expend.One)
        rng = random.Random(f"{self.state.campaign_id}:{package.id}:{f.id}:jsow")
        wp.tasks.append(task.OptROE(task.OptROE.Values.WeaponFree))
        if eta_s is not None:      # v0.41.47: when the window ends the jet stops hunting: weapons free sent XO's 2026-10-20 Squids on for a third salvo at 21 nm of the SAMs
            rf_ = task.ControlledTask(task.OptROE(task.OptROE.Values.ReturnFire)); rf_.start_after_time(int(eta_s + JSOW_ATTACK_S)); wp.tasks.append(rf_)
        for u in aims:
            a, d = rng.uniform(0, 2 * math.pi), JSOW_AIM_ERR_M * math.sqrt(rng.random())
            x, y = u.position.x + math.cos(a) * d, u.position.y + math.sin(a) * d
            bt_ = task.ControlledTask(task.Bombing(mapping.Point(x, y, self.t), expend=exp, group_attack=True))
            if eta_s is not None:                                  # v0.41.46: no pressing on for a second salvo: Squid 2 flew to 14 nm of the SA-11 for its second JSOW
                bt_.stop_after_time(int(eta_s + JSOW_ATTACK_S))
            wp.tasks.append(bt_)

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
            cx_, cy_, pts_, span_ = self._ramp_aim(package, w)
            # v0.41.323 (XO's L3 run: the carpet task's aim point was the ramp, but the CBU jets looped 6 to 20 km off it and dropped on the depot guards): the plain point
            # bomb task at the middle of the ramp, the same task that put the GBU-31s on their aim point. The cluster bombs' bomblets cover the ramp. `span_` is unused now.
            # v0.41.326 (XO 2026-11-06: cover more of the ramp): the pass runs ALONG the line of parked jets, so one run lays the bombs down its length. DCS takes one aim point and
            # one attack heading per task (no per-jet points, no release spacing from a script). Heading = the bearing between the two jets furthest apart (x north, y east),
            # only when the ramp is longer than `RAMP_AXIS_MIN_M` (judgment call); otherwise the plain point as before. Not seen in DCS.
            dir_ = self._ramp_heading(pts_, span_)
            bt2_ = task.Bombing(self._pt(cx_, cy_), weapon_type=task.WeaponType.Auto, expend=task.Expend.All, group_attack=True, direction=dir_)
            self._ramp_tasks.append(bt2_)
            return bt2_
        wt_ = task.WeaponType.CruiseMissile if w.name == "SLAM" else task.WeaponType.Auto         # v0.41.302: the Standoff Strike's SLAM-ER is a missile; XO's run: the default filter fired nothing
        return task.Bombing(self._pt(*(w.aim or (w.x, w.y))), weapon_type=wt_, expend=task.Expend.All, group_attack=True)       # v0.41.299: a release point (JDAM, SLAM-ER) bombs the target, not itself

    def _ramp_aim(self, package, w):
        """(cx, cy, pts, span) of a counter-air bomb task: the middle and spread of `_ramp_pts`, or of the field's real parking slots when that list is empty, or the waypoint's own aim."""
        from .mission_builder import RAMP_CLUSTER_M                # the builder's module imports this one, so it is imported here, when called
        o_ = package.objective
        pts_ = list(getattr(self, "_ramp_pts", []) or [])
        if pts_:
            cx_, cy_ = sum(q[0] for q in pts_) / len(pts_), sum(q[1] for q in pts_) / len(pts_)
            span_ = _span(pts_)
        else:
            # v0.41.328 (XO's run: the strike flights are built BEFORE the parked jets spawn, so this list is empty here and the aim fell back to the airfield point, 1.2 km short
            # of the jets): the middle of the field's real parking slots, and the line of the slots within `RAMP_CLUSTER_M` of it for the heading
            ra_ = self.state.assets.get(o_.target_id)
            r_ = self._ramp_xy(ra_) if ra_ is not None else None
            if r_ is not None:
                cx_, cy_ = r_
                ap2_ = self.t.airports.get(ra_.airport) if getattr(ra_, "airport", None) else None
                pts_ = [(q.position.x, q.position.y) for q in (ap2_.parking_slots if ap2_ else []) if q.airplanes and dist(q.position.x, q.position.y, cx_, cy_) <= RAMP_CLUSTER_M]
                span_ = _span(pts_)
            else:
                cx_, cy_ = w.aim or (w.x, w.y)
                span_ = 0.0
        return cx_, cy_, pts_, span_

    @staticmethod
    def _ramp_heading(pts, span):
        """The attack heading along the line of parked jets (the bearing between the two furthest apart), or None when the ramp is shorter than `RAMP_AXIS_MIN_M`."""
        from .mission_builder import RAMP_AXIS_MIN_M                # the builder's module imports this one, so it is imported here, when called
        if pts and span >= RAMP_AXIS_MIN_M:
            p1_, p2_ = max(((p, q) for p in pts for q in pts), key=lambda pq: dist(pq[0][0], pq[0][1], pq[1][0], pq[1][1]))
            return int(round(math.degrees(math.atan2(p2_[1] - p1_[1], p2_[0] - p1_[0])))) % 360
        return None

    def _stop_at(self, task_, stop_s):
        """`task_` wrapped in a ControlledTask that stops `stop_s` seconds into the mission."""
        ct_ = task.ControlledTask(task_)
        ct_.stop_after_time(int(stop_s))
        return ct_

    def _stopped_bombing(self, x, y, expend, stop_s):
        """A plain Bombing task (auto weapon, group attack) at (x, y) that stops at `stop_s`."""
        return self._stop_at(task.Bombing(self._pt(x, y), weapon_type=task.WeaponType.Auto, expend=expend, group_attack=True), stop_s)

    def _gbu_total(self, f):
        """How many GBUs the flight's jets carry in the strike loadout (`loadouts.gbu_count`)."""
        return gbu_count(self.lo.for_role(f.aircraft, f.role, ""))

    def _slam_aims(self, package, w) -> list:
        """v0.41.309 (XO 2026-11-05: "how do we make the 18 just focus on their target? one hit the bunker, the rest targeted god knows what"): the aim points of a SLAM-ER
        launch: up to `SLAM_AIMS` of the target site's buildings (the first one, then the one furthest from it), a missile each. A single Bombing task on the site's centre
        sent one missile at the guard vehicles and left the rest to hunt radars under weapons free (XO's run). No buildings known: the waypoint's own aim point."""
        from .mission_builder import SLAM_AIMS                # the builder's module imports this one, so it is imported here, when called
        aim = tuple(w.aim or (w.x, w.y))
        a_ = self.state.assets.get(package.objective.target_id)
        if a_ is not None and a_.kind == AssetKind.EWR:                  # S60: an EWR strike: both missiles of a jet on the radar vehicle itself (it is a vehicle: no buildings; the waypoint's aim is the site's centre)
            us_ = self._ewr_units(package)
            return [(us_[0].position.x, us_[0].position.y)] * SLAM_AIMS if us_ else [aim] * SLAM_AIMS
        spots = list(self._bld_xy.get(package.objective.target_id) or [])
        if len(spots) > SLAM_AIMS:
            far = max(spots[1:], key=lambda s_: dist(s_[0], s_[1], spots[0][0], spots[0][1]))
            spots = [spots[0], far][:SLAM_AIMS]
        return spots or [aim]

    def _bomb_tasks(self, package, w) -> list:
        """The bombing tasks of a BOMB waypoint: one, except a SLAM-ER launch (`_slam_aims`: one Bombing task per aim point, one missile each, over once `SLAM_ATTACK_S` has passed)."""
        from .mission_builder import SLAM_ATTACK_S                # the builder's module imports this one, so it is imported here, when called
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

    def _gbu_spread_tasks(self, package, f, w, stop_s):
        """S67 (XO run 2026-11-12 22-47-24: eight GBU-31s of Viper 8 all landed within 2 to 49 m of the one aim point, one of three Tanks died): an AI JDAM striker on a supply
        site spreads its bombs over the site's buildings. One Bombing task per aim point (up to the GBUs a jet carries, `loadouts.gbu_count`; the building spots by farthest-point
        spread, the first the one nearest the site's centre), `Expend` the jet's bombs divided by the aim points, the last one `All` (the remainder). Each task stops at `stop_s`
        like the single task. None = today's single task: not a plain-GBU strike on a supply site, or fewer than two building spots known."""
        o_ = package.objective
        if (f.role != Role.STRIKE or f.tag or getattr(f, "kit", "") or f.aircraft not in JDAM_JETS or o_.type != ObjectiveType.STRIKE
                or o_.aim in ("RUNWAY", "STANDOFF", "SWEEP") or w.name == "SLAM"):
            return None
        spots = list(self._bld_xy.get(o_.target_id) or [])
        if len(spots) < 2:
            return None
        n_ = self._gbu_total(f)
        k_ = min(n_, len(spots))
        if k_ < 2:
            return None
        cen_ = (sum(s_[0] for s_ in spots) / len(spots), sum(s_[1] for s_ in spots) / len(spots))
        chosen = [min(spots, key=lambda s_: dist(s_[0], s_[1], cen_[0], cen_[1]))]
        while len(chosen) < k_:
            rest = [s_ for s_ in spots if s_ not in chosen]
            chosen.append(max(rest, key=lambda s_: min(dist(s_[0], s_[1], c_[0], c_[1]) for c_ in chosen)))
        each = n_ // k_
        exp = _expend_for(each)
        out = []
        for i_, (x_, y_) in enumerate(chosen):
            out.append(self._stopped_bombing(x_, y_, (task.Expend.All if i_ == k_ - 1 else exp), stop_s))
        return out

    def _runway_bomb_tasks(self, package, f, stop_s):
        """S70 (XO run 2026-11-13_00-15-28, the third run in a row: the AI runway strikers ran in to 7 nm of the field at 20,000 ft and turned for home without releasing; the GBU-31s all came back, the
        BombingRunway task gave up at the release point): an AI runway strike drops with plain Bombing tasks, the task every other AI strike uses, one per aim point (up to three, `RUNWAY_AIM_STEP_M`
        apart along the runway axis about the airfield reference point, which is what the hook's runway rectangle is centred on), the jet's GBUs divided between them (as `_gbu_spread_tasks`), the last
        one `All`. Each stops at `stop_s`. Heading: the airport's first runway. None = not an AI runway strike on a field with a pydcs airport (the caller falls back). Scripting only: a person's flight keeps `_bomb_task`'s BombingRunway."""
        from .mission_builder import RUNWAY_AIM_STEP_M                # the builder's module imports this one, so it is imported here, when called
        o_ = package.objective
        a_ = self.state.assets.get(o_.target_id)
        ap_ = self.t.airports.get(a_.airport) if (o_.aim == "RUNWAY" and o_.type == ObjectiveType.STRIKE and a_ is not None and getattr(a_, "airport", None)) else None
        if ap_ is None or f.role != Role.STRIKE or f.tag or getattr(f, "kit", ""):
            return None
        try:
            hdg_ = math.radians(float(ap_.runways[0].main.heading))
        except (IndexError, AttributeError, TypeError, ValueError):
            return None
        cx_, cy_ = ap_.position.x, ap_.position.y
        n_ = self._gbu_total(f) if f.aircraft in JDAM_JETS else 0
        k_ = max(1, min(n_, 3))
        offs_ = [(i_ - (k_ - 1) / 2.0) * RUNWAY_AIM_STEP_M for i_ in range(k_)]
        each_ = n_ // k_ if n_ else 0
        exp_ = _expend_for(each_)
        out = []
        for i_, d_ in enumerate(offs_):          # (x north, y east; the heading is compass degrees: along = dx cos h + dy sin h, the hook's own convention)
            out.append(self._stopped_bombing(cx_ + d_ * math.cos(hdg_), cy_ + d_ * math.sin(hdg_), (task.Expend.All if (i_ == k_ - 1 or not n_) else exp_), stop_s))
        return out

    def _ai_bomb_tasks(self, package, f, w, stop_s) -> list:
        """The AI flight's bomb tasks at a BOMB waypoint, each stopping at `stop_s`: the plain tasks along a runway (`_runway_bomb_tasks`), the spread over a supply site's buildings (`_gbu_spread_tasks`), else the single task."""
        rw_ = self._runway_bomb_tasks(package, f, stop_s)
        if rw_ is not None:
            return rw_
        sp_ = self._gbu_spread_tasks(package, f, w, stop_s)
        if sp_ is not None:
            return sp_
        return [self._stop_at(self._bomb_task(package, w), stop_s)]
