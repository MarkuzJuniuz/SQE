"""Raid SEAD and the F-14 raid shape: the carrier-raid setpiece's SEAD flights (scripted result or flown), their sites, route, prep record and kills.

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o`, `self.warns`, `self._spawn_flight`
and the other fields the builder sets up. The constants (`RAID_RUSH_KTS`, `RAID_F14_HOLD_FT`, `RAID_SEAD_LEAD_S`, `TRACK_RADARS`, ...) stay in `mission_builder.py`:
each method imports what it uses at the start of its own body, so a probe's `mb.NAME = ...` still takes effect.
"""
from __future__ import annotations
import copy

from dcs import action, condition, triggers
from dcs.translation import String

from . import threatmap as tm
from .aircraft import AIRCRAFT
from .models import AssetKind, BaseKind, ObjectiveType, Role
from .routes import NM, Wpt, assign_times, bearing, dist, leg_seconds, make_geometry, objective_wp, offset, plan_route


class RaidSead:
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
        mshl = tm.safe_marshal(st, (base.x, base.y), bearing(base.x, base.y, tx, ty), (tx, ty), refs=[(base.x, base.y)])
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
        from .mission_builder import RAID_F14_DASH_FT, RAID_F14_DASH_KTS, RAID_OTHER_DASH_KTS, RAID_F14_HOLD_FT, RAID_F14_HOLD_KTS, RAID_F14_HOLD  # the builder's module imports this one
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
        from .mission_builder import RAID_RUSH_KTS  # the builder's module imports this one
        tw = objective_wp(wps)
        for w in wps:
            if w is tw:
                break
            if w.speed_kts > 0:
                w.speed_kts = max(w.speed_kts, RAID_RUSH_KTS)

    def _raid_sead_route(self, package, f, site, cap_tot_s):
        """The stand-in SEAD package, geometry and rush route of one raid SEAD flight on `site`. -> (sp, g2, push, tg, rtb)."""
        from .mission_builder import RAID_SEAD_DONE_S, RAID_SEAD_LEAD_S  # the builder's module imports this one
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
        from .mission_builder import RAID_SCRIPT_KILL  # the builder's module imports this one
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
        from .mission_builder import TRACK_RADARS, RAID_DASH_WAIT_S, RAID_PLAYER_WAIT_S  # the builder's module imports this one
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
