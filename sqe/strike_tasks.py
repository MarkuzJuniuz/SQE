"""Strike, SEAD, DEAD and CAS tasking: the HARM / JSOW / bombing / CAS parts of the mission builder.

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o`, `self.groups_by_asset`
and the other fields the builder sets up; nothing here is called from outside the builder.
"""
from __future__ import annotations
import math
import random

from dcs import mapping, task

from . import threatmap as tm
from .aircraft import AIRCRAFT
from .loadouts import JSOW_PER_JET
from .models import SEAD_AIMS, AssetKind, ObjectiveType, Role
from .routes import AVOID_NM, FT, HARM_LAUNCH_NM, JSOW_AXIS_DEG, JSOW_LAUNCH_NM, NM, assign_times, bearing, dist, objective_wp, offset, plan_route

JSOW_ATTACK_S = 120           # v0.41.46: a JSOW slinger's release tasks end this long after the launch point's ETA, and it turns for home (judgment call; XO's run: releases came 25-60 s before the point)
JSOW_AIM_ERR_M = 100           # a JSOW's aim point is the radar's last-known position give or take this much (the targeting is not perfect)
DEAD_GATE_BEFORE_TGT_S = 75    # fallback: if the DEAD flight never gets close, the radars are checked this long before its planned target time
AIR_GATE_KM = 100              # v0.41.214 (XO): was 70, the hold sits outside the MiG-31's P-33 reach (about 120 km) of the fight; judgment call. v0.41.203 text: 70               # v0.41.203: a strike / CAS flight with no radar site to wait on checks the air this far from its target (km); the hold, if any, is out here, short of the fight
AIR_HOLD_STRIKE_S = 360        # ...and holds at most this long (judgment call: the Day-2 fight of XO's 2026-10-30 run lasted about that), then goes home (v0.41.205: it used to go in all the same and was shot down)
AIR_HOLD_CAS_S = 240           # CAS holds less: the troops on the ground are waiting (judgment call)
DEAD_GATE_KM = 40              # the radars are checked when the DEAD flight's lead is this close to the site (km); any still up and the package turns back
SA10_GATE_KM = 60              # ...but never inside an SA-10's reach (55 km): against an SA-10 target, or under an SA-10 umbrella, the gate (and so the hold
                               # orbit) is this far from the SA-10. v0.39.21 run: Hornet 1 held 40 km from the Sukhumi SA-6, 26 km from the SA-10, and was shot down there
SEAD_WAVE_KM = 60              # SEAD packages in one mission whose targets are this close together reach their HARM points at the same moment (the builder's sync)
TRACK_RADARS = {"SNR_75V", "snr s-125 tr", "Kub 1S91 str", "S-300PS 40B6M tr", "Tor 9A331"}          # fire-control / track radars (unit type names as DCS stores them).
# The Tor carries its radar on the launcher: the vehicle IS the radar, so a Tor battery is blind only when its vehicles are down.
TOR_VARIANTS = {"SA-15"}       # point defences that cover a long-range site and shoot down HARMs, GBUs and JSOWs aimed at it
TOR_COVER_KM = 12.0           # a Tor this close to a SEAD/DEAD target, or to the strike leg into it, is part of the job: HARMs and JSOWs go at it, the DEAD gate waits for it
SEARCH_RADARS = {"p-19 s-125 sr", "SA-11 Buk SR 9S18M1", "S-300PS 64H6E sr", "1L13 EWR", "55G6 EWR"}
KPH = 1.852


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
        for nid_ in getattr(self, "_harm_threat", {}).get(package.id, []):
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
        air_only_ = (not fol_) and obj_.type in (ObjectiveType.STRIKE, ObjectiveType.CAS) and f.role in (Role.STRIKE, Role.CAS)      # v0.41.203: the fighters-clear gate on its own
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
            leg_ = [(w.x, w.y) for w in wps if w.name in ("IP", "TGT")]
            also_ = [a_.id for a_, _ in self._cover_tors(package, leg_)]          # the route check: the Tors that cover the site or the run in
            tga_ = st.assets.get(gsite_)
            um_ = tm.umbrella_site(st, tga_)
            gm_ = SA10_GATE_KM if (tga_ is not None and tga_.variant in tm.UMBRELLA_VARIANTS) else (AIR_GATE_KM if air_only_ else DEAD_GATE_KM)
            gate = {"t": tot_s - DEAD_GATE_BEFORE_TGT_S, "site": gsite_, "grp": g.name, "also": also_, "gm": gm_ * 1000,
                    "ux": um_.x if um_ else None, "uz": um_.y if um_ else None, "um": SA10_GATE_KM * 1000 if um_ else None,
                    "from": n0_ + max(0, ti_ - 1) + 1, "to": to_, "ai": ai_, "dead": f.role in (Role.STRIKE, Role.CAS), "you": bool(f.is_player), "pkg": package.id,
                    "acap": AIR_HOLD_CAS_S if f.role == Role.CAS else AIR_HOLD_STRIKE_S, "tx": tga_.x if tga_ is not None else None, "tz": tga_.y if tga_ is not None else None}
        return gate

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

    def _harm_time(self, package, geom, base, P0):
        """When this package's AI HARM flights reach their HARM point in this mission (push time + the push-to-HARM-point leg on its geometry)."""
        sf = next((f for f in package.flights if f.role == Role.SEAD and not f.tag), None)
        if sf is None:
            return None
        from .mission_builder import stagger                # the builder's module imports this one, so it is imported here, when called
        spec = AIRCRAFT[sf.aircraft]
        wps = plan_route(Role.SEAD, (base.x, base.y), geom, spec.profile, is_player=False, tanker_xy=None, keep_out=self._umbrella_keep(package), harm_deg=self._harm_deg(package, geom))
        assign_times(wps, 0.0, P0 + stagger(package, Role.SEAD))
        tw = objective_wp(wps)
        return tw.eta_s if tw is not None and tw.action == "SEAD" else None

    def _umbrella_keep(self, package):
        """plan_route's keep_out for a package's HARM point: the umbrella SA-10's reach (HARM_LAUNCH_NM) when the target sits under one and,
        v0.41.24, every other live SA-2/3/6/11/10 the package is not sent against, by its reach (the v0.41.23 run: a Gudauta SEAD flight's HARM
        point sat 30 nm from the Sukhumi S-300 another package was attacking, and three Hornets died to it). None when there is nothing to keep out of."""
        if not package.objective.target_id or package.objective.target_id not in self.state.assets:
            return None
        out = []
        if package.objective.type == ObjectiveType.DEAD:
            um = tm.umbrella_site(self.state, self.state.assets.get(package.objective.target_id))
            if um:
                out.append((um.x, um.y, HARM_LAUNCH_NM))
        out += self._zone_sams(package)
        return out or None

    def _harm_deg(self, package, geom) -> float:
        """v0.41.24: the HARM shooters' approach, in degrees off the package axis: the first of 0, 15, 30 either side whose launch point (pushed
        out as plan_route pushes it, up to 40 nm further) and IP clear the umbrella and every other SAM the package is not sent against. None
        clear: the one with the most room, and the package's HARM flights also fire on the sites still in reach (self._harm_threat)."""
        tid = package.objective.target_id
        if not tid or tid not in self.state.assets:
            return 0
        c_ = getattr(self, "_harm_c", {})
        if package.id in c_:
            return c_[package.id]
        kos = self._umbrella_keep(package) or []
        h0 = max(8.0, min(HARM_LAUNCH_NM, geom.d / NM * 0.8 - 6))
        def place(deg):
            ax = geom.hdg + 180 + deg
            hn = h0
            while hn < HARM_LAUNCH_NM + 40 and any(dist(*offset(geom.tx, geom.ty, ax, hn * NM), kx, ky) < knm * NM for kx, ky, knm in kos):
                hn += 1.0
            pts = [offset(geom.tx, geom.ty, ax, (hn + k) * NM) for k in (0, 6)]
            return pts, min((dist(x, y, kx, ky) / NM - knm for x, y in pts for kx, ky, knm in kos), default=999.0)
        best = None
        for deg in self.HARM_AXES:
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
            self._harm_threat = getattr(self, "_harm_threat", {})
            self._harm_threat[package.id] = ids
        c_[package.id] = best[0]
        self._harm_c = c_
        return best[0]

    def _jsow_side(self, package, geom) -> float:
        """The JSOW flight's approach, as a multiple of JSOW_AXIS_DEG off the HARM shooters' axis. v0.41.22: the first axis (30, 50, 15 or
        70 degrees either side) whose launch point and IP sit outside the reach of every other live SA-2/3/6/11/10 (the v0.41.21 scan: JSOW flights
        launched 20 nm from a neighbouring SA-2 nobody was suppressing). None clear: the axis with the most room, and the package's second HARM
        flight is also tasked on the sites still in reach (self._jsow_threat)."""
        tid = package.objective.target_id
        if package.objective.aim not in SEAD_AIMS or not tid:
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

    def _jsow_tasks(self, wp, f, site, package, eta_s=None) -> None:
        """A JSOW slinger's attack from its launch point: one release per radar of the target site (search and track radars; the first two
        vehicles of a site whose radars ride on the launchers), aimed at the radar's last-known position give or take JSOW_AIM_ERR_M. The
        flight's JSOWs are shared out between the aim points. A radar that shuts down to dodge the HARMs is still where it was last seen."""
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
