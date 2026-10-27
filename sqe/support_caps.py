"""Support CAPs: the tanker CAP, HAVCAP, base CAP and carrier CAP of a mission (which ones, where they sit, their route), and moving the carrier group out of the fight.

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
import copy

from dcs import mapping, planes

from . import barcap, callsigns
from .support_assets import BY_CLASS as BY_CLASS_
from . import threatmap as tm
from .aircraft import AIRCRAFT
from .models import BaseKind
from .red_air_picture import ALERT_REACH_NM
from .routes import FT, NM, Wpt, avoid_circles, bearing, dist, offset, terrain_clear
from .strike_tasks import KPH

TANKER_COVER_NM = 30          # v0.41.26: a tanker track this close to a friendly field's Patriot (or the carrier group) counts as under friendly SAM cover
SUPPORT_CAP_ZONE_NM = 25      # v0.41.7: HAVCAP / tanker CAP / base CAP engage inside this circle round what they guard
TNKCAP_ZONE_NM = 40           # v0.41.26: the tanker CAP engages inside this circle round the tanker (an AMRAAM's reach), never further
CVCAP_ZONE_NM = 30            # v0.41.21: the carrier CAP engages within this of the boat (v0.41.14: 50; it reached out and set off red scrambles)
CAP_REACH_BEYOND_NM = 25     # v0.41.113: a base / carrier CAP's engage circle reaches this far past its station (judgment call)
CVCAP_NM = 12                 # v0.41.21: the carrier CAP orbits this far out from the boat toward the nearest enemy field (v0.41.7: 22)
CVCAP_DETECT_MARGIN_NM = 5    # v0.41.21: its orbit and engage circle stay this far outside every enemy field's scramble circle


class SupportCaps:
    @staticmethod
    def _gather_support(package, extras):
        """v0.41.9: the mission's support CAP comes from ALL its packages, one of each: a tanker CAP, a HAVCAP, a base CAP per home field and a carrier
        CAP per carrier. Yours first; what yours lacks comes from the first merged package that planned it. (A Fighter Sweep plans none, and merged
        packages' support flights were dropped, so with you on a sweep the tanker, AWACS and boat flew unguarded: the v0.41.8 Batumi run.)
        Returns a copy of the package with the extra flights added; the campaign plan is not changed."""
        key = lambda f_: (f_.tag, (getattr(f_, "guard", "") or f_.base_id) if f_.tag in ("BASECAP", "CVCAP") else "")
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
        """v0.41.7: the AWACS sits well back (its own anchor: where the marshal used to be, 90 nm from every enemy field) with its HAVCAP; the
        tanker sits FORWARD, on the way home (between the base and the egress point, clear of SAM rings and the enemy fields' scramble circles),
        with its own escort, so a flight short of fuel meets it before its own runway, not 50 nm behind it."""
        pt = lambda x, y: mapping.Point(x, y, self.t)
        st = self.state
        ax, ay = tm.safe_marshal(st, (g.bx, g.by), g.hdg)                   # the old flat-distance marshal spot: the AWACS's anchor
        tanker_xy, awacs_unit = None, None
        hav_xy = offset(ax, ay, g.hdg + 180, 8 * NM)
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
        cover_ = [(b_.x, b_.y, TANKER_COVER_NM) for b_ in st.bases.values()
                  if b_.kind == BaseKind.AIRFIELD and self.o.base_defenses and getattr(b_, "defense", 0) >= 0.15] + \
                 [(b_.x, b_.y, TANKER_COVER_NM) for b_ in st.bases.values() if b_.kind == BaseKind.CARRIER]
        fwd = tm.tanker_spot(st, (hx_, hy_), g.egr, (g.tx, g.ty), caps_, lanes_, cover_, track_hdg=g.hdg - 90)
        self._tanker_c = None
        for s in package.support:
            cls = getattr(planes, s.dcs_class)
            alt, spd, freq = s.altitude_ft * FT, s.speed_kts * KPH, plan.freq(s.slot)
            if s.slot == "AWACS":
                # racetrack runs sideways (parallel to the front), 40 nm long, centred behind its anchor
                x, y = offset(*offset(ax, ay, g.hdg + 180, 6 * NM), g.hdg - 90, 20 * NM)
                grp = self.m.awacs_flight(self.usa, f"{s.label} 1", cls, None, pt(x, y), race_distance=40 * NM, heading=int(g.hdg + 90) % 360,
                                          altitude=alt, speed=spd, frequency=freq)
                callsigns.apply(grp, s.label, 1, callsigns.AWACS); grp.units[0].name = f"{s.label} 1-1"
                self._support_units[BY_CLASS_.get(s.dcs_class, s.slot)] = grp.units[0].name
                awacs_unit = grp.units[0]
            else:
                if s.from_carrier:                                           # the recovery tanker stays with the boat
                    x, y = offset(*offset(g.bx, g.by, g.hdg + 180, 15 * NM), g.hdg - 90, 10 * NM); race = 20 * NM
                elif fwd is not None:
                    # a 30 nm racetrack across the route (in and out both cross it); a second tanker 15 nm nearer home
                    c_ = fwd if s.slot == "TANKER1" else offset(*fwd, bearing(*fwd, g.bx, g.by), 15 * NM)
                    race = 30 * NM
                    x, y = offset(*c_, g.hdg - 90, race / 2)
                    if s.slot == "TANKER1":
                        self._tanker_c = c_
                else:                                                        # nothing forward is clear: behind the AWACS anchor, as before
                    back = 12 if s.slot == "TANKER1" else 24
                    x, y = offset(*offset(ax, ay, g.hdg + 180, back * NM), g.hdg - 90, 15 * NM); race = 30 * NM
                    if s.slot == "TANKER1":
                        self._tanker_c = offset(x, y, g.hdg + 90, race / 2)
                grp = self.m.refuel_flight(self.usa, f"{s.label} 1", cls, None, pt(x, y), race_distance=race, heading=int(g.hdg + 90) % 360,
                                           altitude=alt, speed=spd, frequency=freq, tacanchannel=plan.tacan[s.slot])
                callsigns.apply(grp, s.label, 1, callsigns.TANKER); grp.units[0].name = f"{s.label} 1-1"
                self._support_units[BY_CLASS_.get(s.dcs_class, s.slot)] = grp.units[0].name
                if s.slot == "TANKER1":
                    tanker_xy = offset(x, y, g.hdg + 90, race / 2)
        return tanker_xy, awacs_unit, hav_xy

    def _barcap_circles(self, package, geom) -> list:
        """v0.41.138: the engage circles (x, y, radius nm) of this mission's BARCAPs (base CAP and carrier CAP), worked out the same way the flights
        get them (the route plan, then the SAM trim), so a TARCAP knows where the barrier circle is whatever order the flights are built in. Nothing is
        built or changed."""
        out = []
        for f in package.flights:
            if f.tag not in ("BASECAP", "CVCAP"):
                continue
            cz_, _, _ = self._support_cap_route(package, f, geom, None, 0, 0)
            z_ = self._clear_zone(cz_, package)
            if z_ is not None:
                out.append(z_)
        return out

    def _support_cap_route(self, package, f, geom, hav_xy, tot_s, rtb_s):
        """A support CAP's route: airborne on station for the whole package, one thing to guard. -> (cap_zone, wps, stop). Moved out of _spawn_flight in v0.41.54, unchanged."""
        st, o = self.state, self.o
        spec = AIRCRAFT[f.aircraft]
        base = st.bases[f.base_id]
        # v0.41.7: each guards one thing, from the side the threat comes from (the nearest enemy fighter field), and fights only inside
        # a circle round it. HAVCAP: the AWACS (well back). TNKCAP: the tanker (forward, on the way home). BASECAP: the home field. CVCAP: the boat.
        tc_ = getattr(self, "_tanker_c", None)
        if f.tag == "TNKCAP" and tc_ is not None:
            gx_, gy_ = tc_; thr_ = tm.nearest_threat_bearing(st, gx_, gy_, geom.hdg); sx, sy = offset(gx_, gy_, thr_, 5 * NM); zr_ = TNKCAP_ZONE_NM
        elif f.tag in ("HAVCAP", "TNKCAP"):
            gx_, gy_ = hav_xy; thr_ = geom.hdg; sx, sy = hav_xy; zr_ = SUPPORT_CAP_ZONE_NM
        elif f.tag == "CVCAP":
            # v0.41.74: the BARCAP area of the boat that faces the target (barcap.py); the boat may have been slid back for this sortie, so the
            # area's direction is used from where the boat is now. No area today (no hostile base reaches it): the old rule, toward the nearest enemy field.
            ar_ = barcap.facing_area(st, "blue", f.base_id, (geom.tx, geom.ty))
            gx_, gy_ = base.x, base.y
            thr_ = ar_["bearing"] if ar_ else tm.nearest_threat_bearing(st, gx_, gy_, geom.hdg)
            sx, sy = offset(gx_, gy_, thr_, (barcap.STATION_FLEET_NM if ar_ else CVCAP_NM) * NM); zr_ = CVCAP_ZONE_NM
        else:           # BASECAP: over the field it guards (v0.41.10: the one red is likeliest to raid), else its own
            gb_ = st.bases.get(getattr(f, "guard", "") or f.base_id, base)
            ar_ = barcap.facing_area(st, "blue", gb_.id, (geom.tx, geom.ty))                   # v0.41.74: its BARCAP area facing the target
            gx_, gy_ = gb_.x, gb_.y
            thr_ = ar_["bearing"] if ar_ else tm.nearest_threat_bearing(st, gx_, gy_, geom.hdg)
            sx, sy = offset(gx_, gy_, thr_, (barcap.STATION_BASE_NM if ar_ else 8) * NM); zr_ = SUPPORT_CAP_ZONE_NM
        # v0.41.13: the orbit stays 15 nm outside every SAM ring: step it back toward what it guards (2 nm at a time) until it is clear
        # (v0.41.12 run: the carrier CAP's F-14s were shot at on a station 22 nm toward Sukhumi)
        for _ in range(20):
            if self._sam_clear(sx, sy) or dist(sx, sy, gx_, gy_) < 2 * NM:
                break
            sx, sy = offset(sx, sy, bearing(sx, sy, gx_, gy_), 2 * NM)
        if f.tag in ("BASECAP", "CVCAP") and ar_:
            # v0.41.113: the engage circle is round the thing it guards, so a station pushed 25-35 nm out would sit at or past the circle's edge and the
            # pair could not shoot at the range that is the point of going forward: the circle reaches CAP_REACH_BEYOND_NM past the station (judgment call)
            zr_ = max(zr_, dist(sx, sy, gx_, gy_) / NM + CAP_REACH_BEYOND_NM)
        leg_ = 15 * NM
        if f.tag == "CVCAP":
            # v0.41.21: the carrier CAP is there to guard the boat, not to start fights: its orbit (both ends) and its engage circle stay outside
            # every enemy field's scramble circle, so it never sets off red's alert pairs ahead of the package (seen in the v0.41.19 runs)
            leg_ = 10 * NM
            det_ = [(fx_, fy_, tm.field_detect_nm((fx_, fy_), (geom.tx, geom.ty), st) + CVCAP_DETECT_MARGIN_NM) for fx_, fy_ in tm.fighter_bases(st)]
            out_ = lambda x_, y_: all(dist(x_, y_, fx_, fy_) >= r_ * NM for fx_, fy_, r_ in det_)
            for _ in range(20):
                if (out_(sx, sy) and out_(*offset(sx, sy, thr_ + 90, leg_))) or dist(sx, sy, gx_, gy_) < 2 * NM:
                    break
                sx, sy = offset(sx, sy, bearing(sx, sy, gx_, gy_), 2 * NM)
            room_ = min([(dist(gx_, gy_, fx_, fy_) / NM - r_) for fx_, fy_, r_ in det_] or [zr_])
            zr_ = max(10, min(zr_, room_))                      # the circle round the boat ends short of the nearest scramble circle
        cap_zone = (gx_, gy_, min(self.o.friendly_cap_engage_nm or 999, zr_))
        p = spec.profile
        wps = [Wpt("SPAWN", sx, sy, p.cap_alt_ft, p.cap_kts), Wpt("CAP1", sx, sy, p.cap_alt_ft, p.cap_kts, "", "CAPORBIT"),
               Wpt("CAP2", *offset(sx, sy, thr_ + 90, leg_), p.cap_alt_ft, p.cap_kts)]
        # v0.41.22: the way home bends round SAM sites too (the v0.41.21 scan: a tanker CAP flew home over an SA-2)
        home_ = Wpt("HOME", base.x, base.y, p.cap_alt_ft, p.cap_kts)
        wps = avoid_circles(wps + [home_], self._zone_sams(package, True), p.max_points, 3)[:-1]      # the CAP1-CAP2 orbit leg stays as it is
        stop = int(max(tot_s + o.cap_minutes * 60, rtb_s + 300))
        if not f.is_player or o.player_is_ai:
            terrain_clear(wps)                          # v0.41.49: a support CAP's legs clear the ridges too (the branch never ran the terrain check)
        return cap_zone, wps, stop
