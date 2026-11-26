"""Support CAPs: the tanker CAP, HVAACAP, base BARCAP and carrier BARCAP of a mission (which ones, where they sit, their route), and moving the carrier group out of the fight.

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
import copy

from dcs import mapping, planes

from . import barcap, blue_commit, callsigns
from .support_assets import BY_CLASS as BY_CLASS_, _support_airfield
from . import threatmap as tm
from .aircraft import AIRCRAFT
from .models import BaseKind
from .red_air_picture import ALERT_REACH_NM
from .routes import FT, NM, Wpt, avoid_circles, bearing, cap2_point, dist, offset, terrain_clear
from .strike_tasks import KPH

TANKER_COVER_NM = 30          # v0.41.26: a tanker track this close to a friendly field's Patriot (or the carrier group) counts as under friendly SAM cover
SUPPORT_CAP_ZONE_NM = 25      # v0.41.7: HVAACAP / tanker CAP / base BARCAP engage inside this circle round what they guard
LATE_TANKER_EGRESS_S = 600       # S193 PR 3 (judgment call, no source): the red raiders are this long past their time over the target before the danger counts as over (they turn for home and leave)
LATE_TANKER_LIMIT_S = 1800       # S193 PR 3 (judgment call): a late tanker that could only open later than this after the player's planned recovery is not flown at all
TKR_HVAACAP_ZONE_NM = 40           # v0.41.26: the tanker CAP engages inside this circle round the tanker (an AMRAAM's reach), never further
CARRIER_BARCAP_ZONE_NM = 30            # v0.41.21: the carrier BARCAP engages within this of the boat (v0.41.14: 50; it reached out and set off red scrambles)
CAP_REACH_BEYOND_NM = 25     # v0.41.113: a base / carrier BARCAP's engage circle reaches this far past its station (judgment call)
CARRIER_BARCAP_NM = 12                 # v0.41.21: the carrier BARCAP orbits this far out from the boat toward the nearest enemy field (v0.41.7: 22)
CARRIER_BARCAP_DETECT_MARGIN_NM = 5    # v0.41.21: its orbit and engage circle stay this far outside every enemy field's scramble circle


class SupportCaps:
    @staticmethod
    def _gather_support(package, extras):
        """v0.41.9: the mission's support CAP comes from ALL its packages, one of each: a tanker CAP, an HVAACAP, a base BARCAP per home field and a carrier
        CAP per carrier. Yours first; what yours lacks comes from the first merged package that planned it. (A Fighter Sweep plans none, and merged
        packages' support flights were dropped, so with you on a sweep the tanker, AWACS and boat flew unguarded: the v0.41.8 Batumi run.)
        Returns a copy of the package with the extra flights added; the campaign plan is not changed."""
        def key(f_):
            # one support CAP of each kind; a base or carrier BARCAP also by what it guards
            guarded_thing = ""
            if f_.tag in ("BASE_BARCAP", "CARRIER_BARCAP"):
                guarded_thing = getattr(f_, "guard", "") or f_.base_id
            return (f_.tag, guarded_thing)
        have = {key(f_) for f_ in package.flights if f_.tag}
        add = []
        for x in extras:
            for f_ in x.flights:
                if f_.tag and key(f_) not in have:
                    have.add(key(f_))
                    nf = copy.deepcopy(f_); nf.is_player = False
                    add.append(nf)
        if not add:
            return package
        used = {f_.callsign for f_ in package.flights} | {f_.callsign for x in extras for f_ in x.flights if not f_.tag}
        for nf in add:
            nm, no = nf.callsign.rsplit(" ", 1); no = int(no)
            while f"{nm} {no}" in used:
                no += 1
            nf.callsign = f"{nm} {no}"; used.add(nf.callsign)
        pk = copy.copy(package)
        pk.flights = list(package.flights) + add
        return pk

    def _pull_back_carriers(self, tx, ty):
        """Keep the carrier group out of the fight: slide it back (up to 60 nm, this sortie only) until it is far from the target and from
        every enemy fighter base, but only onto open water (>= 25 nm off the coast, 120 nm of clear sea ahead). If no such spot exists
        the carrier stays on its home station. Skipped when the carrier itself IS the objective (fleet defence)."""
        from .mission_builder import carrier_station       # lazy: the builder's module imports this one
        self._cv_hdg = {}
        for b in self.state.bases.values():
            if b.kind != BaseKind.CARRIER:
                continue
            away = (bearing(b.x, b.y, tx, ty) + 180) % 360
            home = (b.x, b.y)
            if not self._fleet_obj:
                found = carrier_station(self.state, b, tx, ty, self.o.carrier_min_enemy_nm)
                if found:
                    b.x, b.y = found[0], found[1]
                    self._cv_hdg[b.id] = found[2]
                    continue
            h = self._carrier_heading(home[0], home[1], away)
            if h is None:
                h = away
                self.warns.append(f"{b.name}: no clear 120 nm of sea ahead of the carrier; check its route in the editor.")
            self._cv_hdg[b.id] = h

    def _place_support(self, package, plan, g, extras=()):
        """v0.41.7: the AWACS sits well back (its own anchor: where the marshal used to be, 90 nm from every enemy field) with its HVAACAP; the
        tanker sits FORWARD, on the way home (between the base and the egress point, clear of SAM rings and the enemy fields' scramble circles),
        with its own escort, so a flight short of fuel meets it before its own runway, not 50 nm behind it."""
        def pt(x, y):
            return mapping.Point(x, y, self.t)
        st = self.state
        aw_ = tm.awacs_station(st)                                          # S19: one fixed station per state, not from the player's base or target
        ax, ay, fh = aw_ if aw_ is not None else (*tm.safe_marshal(st, (g.bx, g.by), g.hdg), g.hdg)
        self._awacs_fh = fh                                                 # the HVAACAP's route reads it too (_support_cap_route)
        first_station = tm.awacs_first_station(st)                          # S191: the tanker's fallback track hangs off the first station, not off the raid-shifted AWACS (it moved the tanker 75 to 110 nm with it)
        anchor_x, anchor_y = (first_station[0], first_station[1]) if first_station is not None else (ax, ay)
        tanker_xy, awacs_unit = None, None
        awacs_xy = offset(*offset(ax, ay, fh + 180, 6 * NM), fh - 90, 20 * NM) if any(s_.slot == "AWACS" for s_ in package.support) else None   # the AWACS track's start (set before the loop: the tanker fallback needs it)
        hav_xy = offset(ax, ay, fh + 180, 8 * NM)
        # v0.41.11: for the whole mission, not only your flight: from the middle of the fields the mission's flights fly home to (weighted by
        # aircraft), toward your package's egress. The v0.41.10 run put it in front of Batumi for your sweep, 40-50 nm off the Senaki flights' way home.
        hf_ = [(st.bases[f_.base_id], f_.count) for p_ in [package] + list(extras) for f_ in p_.flights
               if not f_.tag and f_.base_id in st.bases and st.bases[f_.base_id].kind == BaseKind.AIRFIELD]
        n_ = sum(c_ for _, c_ in hf_)
        hx_, hy_ = ((sum(b_.x * c_ for b_, c_ in hf_) / n_, sum(b_.y * c_ for b_, c_ in hf_) / n_) if n_ else (g.bx, g.by))
        # v0.41.26: a minimum distance from every danger (SAMs, scramble circles, red patrols, the lines red fighters fly in on), inside
        # friendly SAM cover where it can be (the XO's Nalchik run lost the tanker in the middle of the fight)
        caps_ = [(c_["x"], c_["y"]) for c_ in (getattr(self, "_cap_plan", None) or [])]
        tgts_ = [(g.tx, g.ty)] + [self._pkg_target_xy(p_) for p_ in extras if self._pkg_target_xy(p_)]
        lanes_ = [(fx_, fy_, tx_, ty_) for fx_, fy_ in tm.fighter_bases(st) for tx_, ty_ in tgts_
                  if dist(fx_, fy_, tx_, ty_) <= ALERT_REACH_NM * NM]
        # S193: a defended field, the carrier group, or a blue BARCAP area with a pair up this turn (XO: "barcap counts as cover")
        cover_ = tm.blue_cover_circles(st, TANKER_COVER_NM, tm.SUPPORT_CAP_COVER_NM, base_defenses=bool(self.o.base_defenses))
        raid_lines, sweep_lines = self._raid_route_lines([package] + list(extras))      # S188: the red raids' routes (S189: and the sweeps', apart), known before they are spawned
        tanker_report = {}
        fwd = tm.tanker_spot(st, (hx_, hy_), g.egr, (g.tx, g.ty), caps_, lanes_, cover_, track_hdg=g.hdg - 90, raid_lines=raid_lines, sweep_lines=sweep_lines, report=tanker_report)
        self._late_tankers = []                                              # S193 PR 3: tankers that wait on the ground until the raid window is over (see _finish_late_tankers)
        self._late_tanker_flag = None
        late_fwd = None
        if fwd is None and blue_commit.BLUE_COMMIT and any(s_.slot.startswith("TANKER") and not s_.from_carrier for s_ in package.support):
            # nothing is clear while the red raids and sweeps fly: take the spot that is best WITHOUT their routes (they are over when it launches); red patrols and lanes still count
            late_fwd = tm.tanker_spot(st, (hx_, hy_), g.egr, (g.tx, g.ty), caps_, lanes_, cover_, track_hdg=g.hdg - 90, report={})
        if tanker_report.get("case") == 2:
            self.warns.append("S193: the tanker track is under blue cover but %d nm inside a patrol, lane or raid distance (no covered spot is clear of them)" % round(-tanker_report["margin"]))
        awacs_track_points = [(ax, ay)]
        for awacs_side in (fh + 90, fh - 90):
            awacs_track_points.append(offset(ax, ay, awacs_side, 20 * NM))
        awacs_too_close = False
        for point_x, point_y in awacs_track_points:
            for line in raid_lines:
                if tm._seg_nm(point_x, point_y, *line) < tm.AWACS_RAID_NM:
                    awacs_too_close = True
            for line in sweep_lines:
                if tm._seg_nm(point_x, point_y, *line) < tm.AWACS_SWEEP_NM:
                    awacs_too_close = True
        if awacs_too_close:
            self.warns.append("S188: the AWACS station is within %d nm of a red raid's route or %d nm of a red sweep's (no clear spot behind it)" % (tm.AWACS_RAID_NM, tm.AWACS_SWEEP_NM))
        self._tanker_c = None
        self._tanker_race = 30 * NM
        for s in package.support:
            cls = getattr(planes, s.dcs_class)
            alt, spd, freq = s.altitude_ft * FT, s.speed_kts * KPH, plan.freq(s.slot)
            if s.slot == "AWACS":
                # racetrack runs sideways (parallel to the front), 40 nm long, centred behind its anchor
                x, y = offset(*offset(ax, ay, fh + 180, 6 * NM), fh - 90, 20 * NM)
                grp = self.m.awacs_flight(self.usa, f"{s.label} 1", cls, None, pt(x, y), race_distance=40 * NM, heading=int(fh + 90) % 360,
                                          altitude=alt, speed=spd, frequency=freq)
                callsigns.apply(grp, s.label, 1, callsigns.AWACS); grp.units[0].name = f"{s.label} 1-1"
                self._hvaa_groups.append(grp.name)             # S176b
                self._support_lbl[grp.units[0].name] = s.label.upper()
                self._support_units[BY_CLASS_.get(s.dcs_class, s.slot)] = grp.units[0].name
                awacs_unit = grp.units[0]
            else:
                if s.from_carrier:                                           # the recovery tanker stays with the boat
                    x, y = offset(*offset(g.bx, g.by, g.hdg + 180, 15 * NM), g.hdg - 90, 10 * NM); race = 20 * NM
                elif fwd is not None or late_fwd is not None:
                    # a 30 nm racetrack across the route (in and out both cross it); a second tanker 15 nm nearer home
                    station_ = fwd if fwd is not None else late_fwd
                    c_ = station_ if s.slot == "TANKER1" else offset(*station_, bearing(*station_, g.bx, g.by), 15 * NM)
                    race = 30 * NM
                    x, y = offset(*c_, g.hdg - 90, race / 2)
                    if s.slot == "TANKER1":
                        self._tanker_c = c_; self._tanker_race = race
                else:                                                        # nothing forward is clear: behind the AWACS anchor, as before
                    back = 12 if s.slot == "TANKER1" else 24
                    x, y = offset(*offset(anchor_x, anchor_y, g.hdg + 180, back * NM), g.hdg - 90, 15 * NM); race = 30 * NM
                    for more_back in range(0, 70, 10):             # S188: the fallback track also keeps tm.TANKER_RAID_NM from the red raids' routes: back along the axis until clear (stays where it was when none is)
                        trial_x, trial_y = offset(x, y, g.hdg + 180, more_back * NM)
                        trial_far_end = offset(trial_x, trial_y, g.hdg + 90, race)
                        too_close = False
                        for end_x, end_y in ((trial_x, trial_y), trial_far_end):
                            for line in raid_lines:
                                if tm._seg_nm(end_x, end_y, *line) < tm.TANKER_RAID_NM:
                                    too_close = True
                            for line in sweep_lines:
                                if tm._seg_nm(end_x, end_y, *line) < tm.TANKER_SWEEP_NM:
                                    too_close = True
                        if not too_close:
                            x, y = trial_x, trial_y
                            break
                    if awacs_xy is not None and dist(x, y, *awacs_xy) < 15 * NM:         # S19: the fixed AWACS must not sit on the tanker
                        x, y = offset(x, y, bearing(*awacs_xy, x, y) if dist(x, y, *awacs_xy) > 1 else g.hdg + 180, 15 * NM - dist(x, y, *awacs_xy))
                    if s.slot == "TANKER1":
                        self._tanker_c = offset(x, y, g.hdg + 90, race / 2); self._tanker_race = race
                grp = self.m.refuel_flight(self.usa, f"{s.label} 1", cls, None, pt(x, y), race_distance=race, heading=int(g.hdg + 90) % 360,
                                           altitude=alt, speed=spd, frequency=freq, tacanchannel=plan.tacan[s.slot])
                callsigns.apply(grp, s.label, 1, callsigns.TANKER); grp.units[0].name = f"{s.label} 1-1"
                self._hvaa_groups.append(grp.name)             # S176b
                self._support_lbl[grp.units[0].name] = s.label.upper()
                self._support_units[BY_CLASS_.get(s.dcs_class, s.slot)] = grp.units[0].name
                if fwd is None and late_fwd is not None and not s.from_carrier:
                    self._flag_n += 1                             # S193 PR 3: a late tanker: hidden until the raid window is over (the commit script sets this flag, an ME trigger activates the group)
                    late_flag = self._flag_n
                    self._late_flag(grp, late_flag)
                    centre_x, centre_y = offset(x, y, g.hdg + 90, race / 2)
                    support_base = _support_airfield(st)
                    transit_s = 0.0
                    if support_base is not None:
                        transit_s = dist(support_base.x, support_base.y, centre_x, centre_y) / max(spd, 1.0)
                    self._late_tankers.append({"g": grp.name, "flag": late_flag, "x": centre_x, "z": centre_y, "transit_s": transit_s, "label": s.label, "slot": s.slot})
                    if s.slot == "TANKER1":
                        self._late_tanker_flag = late_flag        # its HVAACAP guard waits for the same flag (mission_builder, where the guard is built)
                if s.slot == "TANKER1":
                    tanker_xy = offset(x, y, g.hdg + 90, race / 2)
        return tanker_xy, awacs_unit, hav_xy

    def _finish_late_tankers(self, manifest, clock) -> None:
        """S193 PR 3 (XO 2026-11-24: "the tanker would take off once the danger is done"). Called once the raids are spawned, before the commit scripts. A late tanker opens at the last red raid
        group's time over its target (`raid_arrive_s` in the manifest) + LATE_TANKER_EGRESS_S + its flight from the support field to its station; the commit script (blue_commit.py `lateTick`)
        then sets its flag when no red fighter is within HVAACAP's pull-back distance of the station. A tanker that could open only more than LATE_TANKER_LIMIT_S after the player's planned
        recovery is not flown (the group stays hidden, no flag). Tankers in SQE are placed in the air on their track, so activating the group is its launch: the transit time is added to the wait."""
        late = getattr(self, "_late_tankers", None)
        if not late:
            return
        arrivals = []
        for group in manifest.groups:
            if group.get("raid_arrive_s") is not None:
                arrivals.append(float(group["raid_arrive_s"]))
        if arrivals:
            window_end = max(arrivals) + LATE_TANKER_EGRESS_S
        else:
            window_end = float(getattr(self, "_last_striker_s", None) or 0.0) + LATE_TANKER_EGRESS_S
        exit_s = getattr(self, "_exit_s", None)
        for entry in late:
            entry["t"] = int(window_end + entry["transit_s"])
            entry["flown"] = exit_s is None or entry["t"] <= float(exit_s) + LATE_TANKER_LIMIT_S
            if entry["flown"]:
                self._red_intel.append("%s launches after the raid is over: on station about %s (it waits on the ground while red raids and sweeps are in the air)." % (entry["label"], clock(entry["t"])))
                self.warns.append("S193: %s is a late tanker: no covered spot is clear of this mission's red raids, so it launches about %s, when they are over and no red fighter is near its station." % (entry["label"], clock(entry["t"])))
            else:
                self._red_intel.append("No %s this mission: the red raids are not over until too late for your flight." % entry["label"])
                self.warns.append("S193: %s does not fly: the red raids are not over until about %s." % (entry["label"], clock(entry["t"])))

    def _barcap_circles(self, package, geom) -> list:
        """v0.41.138: the engage circles (x, y, radius nm) of this mission's BARCAPs (base BARCAP and carrier BARCAP), worked out the same way the flights
        get them (the route plan, then the SAM trim), so a TARCAP knows where the barrier circle is whatever order the flights are built in. Nothing is
        built or changed."""
        out = []
        for f in package.flights:
            if f.tag not in ("BASE_BARCAP", "CARRIER_BARCAP"):
                continue
            cz_, wps_, _ = self._support_cap_route(package, f, geom, None, 0, 0)
            z_ = self._clear_zone(cz_, package, hold=(wps_[1].x, wps_[1].y))
            if z_ is not None:
                out.append(z_)
        return out

    def _support_cap_route(self, package, f, geom, hav_xy, tot_s, rtb_s):
        """A support CAP's route: airborne on station for the whole package, one thing to guard. -> (cap_zone, wps, stop). Moved out of _spawn_flight in v0.41.54, unchanged."""
        st, o = self.state, self.o
        spec = AIRCRAFT[f.aircraft]
        base = st.bases[f.base_id]
        # v0.41.7: each guards one thing, from the side the threat comes from (the nearest enemy fighter field), and fights only inside
        # a circle round it. HVAACAP: the AWACS (well back). TKR_HVAACAP: the tanker (forward, on the way home). base BARCAP: the home field. Carrier BARCAP: the boat.
        tc_ = getattr(self, "_tanker_c", None)
        axis_ = None                                    # S9: the line CAP2 lies across (plus or minus 90); None = thr_
        if f.tag == "TKR_HVAACAP" and tc_ is not None:
            gx_, gy_ = tc_; thr_ = tm.nearest_threat_bearing(st, gx_, gy_, geom.hdg); sx, sy = offset(gx_, gy_, thr_, 5 * NM); zr_ = TKR_HVAACAP_ZONE_NM
            axis_ = geom.hdg                            # S9: CAP2 along the tanker's own track (it runs on hdg + 90), not across the threat
        elif f.tag in ("HVAACAP", "TKR_HVAACAP"):
            gx_, gy_ = hav_xy; thr_ = getattr(self, "_awacs_fh", geom.hdg) if f.tag == "HVAACAP" else geom.hdg; sx, sy = hav_xy; zr_ = SUPPORT_CAP_ZONE_NM
        elif f.tag == "CARRIER_BARCAP":
            # v0.41.74: the BARCAP area of the boat that faces the target (barcap.py); the boat may have been slid back for this sortie, so the
            # area's direction is used from where the boat is now. No area today (no hostile base reaches it): the old rule, toward the nearest enemy field.
            ar_ = barcap.facing_area(st, "blue", f.base_id, (geom.tx, geom.ty))
            gx_, gy_ = base.x, base.y
            thr_ = ar_["bearing"] if ar_ else tm.nearest_threat_bearing(st, gx_, gy_, geom.hdg)
            sx, sy = offset(gx_, gy_, thr_, (barcap.STATION_FLEET_NM if ar_ else CARRIER_BARCAP_NM) * NM); zr_ = CARRIER_BARCAP_ZONE_NM
        else:           # base BARCAP: over the field it guards (v0.41.10: the one red is likeliest to raid), else its own
            gb_ = st.bases.get(getattr(f, "guard", "") or f.base_id, base)
            ar_ = barcap.facing_area(st, "blue", gb_.id, (geom.tx, geom.ty))                   # v0.41.74: its BARCAP area facing the target
            gx_, gy_ = gb_.x, gb_.y
            thr_ = ar_["bearing"] if ar_ else tm.nearest_threat_bearing(st, gx_, gy_, geom.hdg)
            sx, sy = offset(gx_, gy_, thr_, (barcap.STATION_BASE_NM if ar_ else 8) * NM); zr_ = SUPPORT_CAP_ZONE_NM
        # v0.41.13: the orbit stays 15 nm outside every SAM ring: step it back toward what it guards (2 nm at a time) until it is clear
        # (v0.41.12 run: the carrier BARCAP's F-14s were shot at on a station 22 nm toward Sukhumi)
        for _ in range(20):
            if self._sam_clear(sx, sy) or dist(sx, sy, gx_, gy_) < 2 * NM:
                break
            sx, sy = offset(sx, sy, bearing(sx, sy, gx_, gy_), 2 * NM)
        if f.tag in ("BASE_BARCAP", "CARRIER_BARCAP") and ar_:
            # v0.41.113: the engage circle is round the thing it guards, so a station pushed 25-35 nm out would sit at or past the circle's edge and the
            # pair could not shoot at the range that is the point of going forward: the circle reaches CAP_REACH_BEYOND_NM past the station (judgment call)
            zr_ = max(zr_, dist(sx, sy, gx_, gy_) / NM + CAP_REACH_BEYOND_NM)
        leg_ = 15 * NM
        if f.tag == "CARRIER_BARCAP":
            # v0.41.21: the carrier BARCAP is there to guard the boat, not to start fights: its orbit (both ends) and its engage circle stay outside
            # every enemy field's scramble circle, so it never sets off red's alert pairs ahead of the package (seen in the v0.41.19 runs)
            leg_ = 10 * NM
            det_ = [(fx_, fy_, tm.field_detect_nm((fx_, fy_), (geom.tx, geom.ty), st) + CARRIER_BARCAP_DETECT_MARGIN_NM) for fx_, fy_ in tm.fighter_bases(st)]
            def out_(x_, y_):
                # True when the point is outside every enemy field's scramble circle
                for field_x, field_y, field_r in det_:
                    if not dist(x_, y_, field_x, field_y) >= field_r * NM:
                        return False
                return True
            for _ in range(20):
                if (out_(sx, sy) and out_(*offset(sx, sy, thr_ + 90, leg_))) or dist(sx, sy, gx_, gy_) < 2 * NM:
                    break
                sx, sy = offset(sx, sy, bearing(sx, sy, gx_, gy_), 2 * NM)
            room_ = min([(dist(gx_, gy_, fx_, fy_) / NM - r_) for fx_, fy_, r_ in det_] or [zr_])
            zr_ = max(10, min(zr_, room_))                      # the circle round the boat ends short of the nearest scramble circle
        cap_zone = (gx_, gy_, min(self.o.friendly_cap_engage_nm or 999, zr_))
        p = spec.profile
        # S9 (v0.41.350): the leg wished for this job, across the axis, shortened until clear; None = today's point (the floor leg_ on thr_ + 90)
        from .mission_builder import CAP_SPREAD_NM          # here, not at the top: mission_builder imports this module
        wish_ = CAP_SPREAD_NM[f.tag]
        if f.tag == "TKR_HVAACAP" and tc_ is not None:
            wish_ = min(wish_, getattr(self, "_tanker_race", 30 * NM) / NM)
        elif f.tag == "HVAACAP":
            wish_ = min(wish_, 40)                      # the AWACS track is 40 nm
        if f.tag == "CARRIER_BARCAP":
            def clear_(x_, y_):
                if not (out_(x_, y_) and self._sam_clear(x_, y_)):
                    return -1.0
                return 0.0
        else:
            def clear_(x_, y_):
                if self._sam_clear(x_, y_):
                    return 0.0
                return -1.0
        c2_ = cap2_point(sx, sy, thr_ if axis_ is None else axis_, wish_, clear_, floor_nm=leg_ / NM)
        if c2_ is None:
            c2_ = offset(sx, sy, thr_ + 90, leg_)
        wps = [Wpt("SPAWN", sx, sy, p.cap_alt_ft, p.cap_kts), Wpt("CAP1", sx, sy, p.cap_alt_ft, p.cap_kts, "", "CAPORBIT"),
               Wpt("CAP2", *c2_, p.cap_alt_ft, p.cap_kts)]
        # v0.41.22: the way home bends round SAM sites too (the v0.41.21 scan: a tanker CAP flew home over an SA-2)
        home_ = Wpt("HOME", base.x, base.y, p.cap_alt_ft, p.cap_kts)
        wps = avoid_circles(wps + [home_], self._zone_sams(package, True), p.max_points, 3)[:-1]      # the CAP1-CAP2 orbit leg stays as it is
        stop = int(max(tot_s + o.cap_minutes * 60, rtb_s + 300))
        if not f.is_player or o.player_is_ai:
            terrain_clear(wps)                          # v0.41.49: a support CAP's legs clear the ridges too (the branch never ran the terrain check)
        return cap_zone, wps, stop
