"""Fighter station rules: engage circles, SAM-clear stations, hold times (TARCAP, escort, Fighter Sweep).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
from dcs import mapping, task

from . import threatmap as tm
from .aircraft import AIRCRAFT
from .models import AssetKind, ObjectiveType, Role
from .routes import AVOID_NM, NM, SA10_AVOID_NM, bearing, dist, offset, plan_route

TARCAP_MIN = 15               # ...and holds there this long, then goes home
ESCORT_AFTER_EGR_S = 120      # v0.41.40: an escort stays until the last striker has reached its egress point + this long (XO 2026-10-20: DEADers were left behind)
ESCORT_AFTER_TOT_S = 180      # an escort (ESCORT role) holds its station until this long after the TOT (the last ground-attack flight off target)
TARCAP_AFTER_TOT_S = 300      # v0.41.0: a TARCAP holds until this long after the TOT (the last ground-attack flight egressing), not a fixed 15 minutes
HOLD_AREA_KM = 60             # v0.41.10: packages whose targets are this close share their TARCAP / escort holds (the sweep area)
HOLD_EXTEND_MAX_S = 1800      # ...extended at most this much past their own package
LRA_BACK_NM = 8               # v0.41.139 (XO 2026-10-27): in a package with a short-range and a long-range fighter flight (TARCAP + escort), the long-range one stands this far behind the short-range one (away from the target)...
LRA_SIDE_NM = 6               # ...and this far to one side (judgment call: the sweep circles are 25 and 15 nm, so 10 nm between the two sets of jets; the lateral gap is for friendly-fire safety with active missiles in the air, DCS behaviour unverified)
LRA_SPLIT_MIN_NM = 12         # ...but only when the two stations are closer than this (the SAM-free runs put both on one point; with SAM rings in the way they are already 30 nm apart)
TARCAP_AXIS_SWINGS = tuple(v for k in range(0, 13) for v in ((0,) if k == 0 else (15 * k, -15 * k)))   # v0.41.119: degrees the TARCAP station may swing off the threat axis when SAM rings block it, smallest first, up to 180 (judgment call: a Sukhumi SA-10 sat on the axis in the 2026-10-22 probes, so the station takes the clear point nearest the axis; the old station is kept when that is no nearer)


def axis_station(centre, threat, jsow_xy, near_nm, min_jsow_nm, clear, cur=None):
    """v0.41.119 (XO 2026-10-22: the TARCAP sat on the sea side, about 90 degrees off red's approach): the station `near_nm` from the middle of the shooters'
    launch points (`centre`) on the bearing toward `threat` (where red's fighters come from), swung off that bearing by the smallest of
    TARCAP_AXIS_SWINGS that is `clear(x, y)` of SAM rings and at least `min_jsow_nm` from the JSOW launch point. With `cur` (the station it would
    replace) it returns None unless the new point is nearer the axis than `cur`. -> (x, y) or None."""
    b0 = bearing(centre[0], centre[1], threat[0], threat[1])
    cur_dev = abs((bearing(centre[0], centre[1], cur[0], cur[1]) - b0 + 180) % 360 - 180) if cur is not None else 999.0
    for sw in TARCAP_AXIS_SWINGS:
        if abs(sw) >= cur_dev:
            return None
        x, y = offset(centre[0], centre[1], b0 + sw, near_nm * NM)
        if jsow_xy is not None and dist(x, y, jsow_xy[0], jsow_xy[1]) < min_jsow_nm * NM:
            continue
        if clear(x, y):
            return (x, y)
    return None


class FighterStations:
    def _extend_holds(self, events, egr_events=()) -> None:
        """v0.41.10: a TARCAP / escort holds until the LAST package over its target area is off target (TOT + its after-time), not just its own
        package. The v0.41.8 sweep run: the F-15 TARCAPs went home 5 min after their own TOT while later packages were still coming through
        (1,600-2,500 s) and only the F-14s were left. At most HOLD_EXTEND_MAX_S longer; bingo fuel sends them home anyway."""
        for h in self._holds:
            hx, hy = h["tgt"]
            near_ = [t_ for (ex, ey), t_ in events if t_ is not None and dist(ex, ey, hx, hy) <= HOLD_AREA_KM * 1000]
            if h.get("first"):
                later_ = [t_ for t_ in near_ if t_ > h.get("eta", 0) + 60]
                last = min(later_) if later_ else 0
            else:
                last = max(near_ + [0])
            want = last + h["after"]
            if h["after"] == ESCORT_AFTER_TOT_S:         # an escort sticks to the last striker until it is out (egress point), like a shepherd
                eg_ = [t_ for (ex, ey), t_ in egr_events if dist(ex, ey, hx, hy) <= HOLD_AREA_KM * 1000]
                want = max(want, max(eg_ + [0]) + ESCORT_AFTER_EGR_S)
            new = int(min(h["end"] + HOLD_EXTEND_MAX_S, max(h["end"], want)))
            if new <= h["end"]:
                continue
            for ct_ in h["cts"]:
                ct_.stop_after_time(new)
            for ct_ in h["starts"]:
                ct_.start_after_time(new)
            h["end"] = new

    # ---- enemy air picture: what the intelligence briefing says is there IS there, from the first second ----------------------
    @staticmethod
    def _limit_engage(g, nm, until_s=None, zone=None):
        """Cap how far a patrol flight will go after a target (DCS 'engage targets within X'; 0 = unlimited) and, when until_s is given, how LONG:
        the engage task is wrapped so it stops at that mission time and the flight carries on along its route. The distance alone is no leash
        (DCS measures it from the aircraft, so a bandit running home is chased as far as it runs)."""
        if (not nm or nm <= 0) and until_s is None and zone is None:
            return
        meters = int(nm * 1852) if (nm and nm > 0) else None
        old = [t for t in g.points[0].tasks if getattr(t, "Id", "") in ("EngageTargets", "EngageTargetsInZone")]
        for t in old:
            g.points[0].tasks.remove(t)
        if zone is not None:                                        # engage only inside a circle (x, y, radius nm): the real leash
            et = task.EngageTargetsInZone(mapping.Vector2(zone[0], zone[1]), int(zone[2] * 1852), [task.Targets.All.Air])
        else:
            et = task.EngageTargets(meters, [task.Targets.All.Air])
        if until_s is not None:
            ct = task.ControlledTask(et)
            ct.stop_after_time(max(60, int(until_s)))
            et = ct
        g.points[0].tasks.insert(0, et)
        return et

    def _launch_points(self, package, geom) -> list:
        """v0.41.42: where this package's AI shooters launch (the HARM point, the JSOW launch point, else the IP), worked out from the same route
        planning the flights use, so the TARCAP / escort cover circle knows them whatever order the flights are built in."""
        out = []
        for f in package.flights:
            if f.tag or f.role not in (Role.SEAD, Role.STRIKE, Role.CAS) or (f.is_player and not self.o.player_is_ai):
                continue
            base = self.state.bases[f.base_id]
            try:
                wps = plan_route(f.role, (base.x, base.y), geom, AIRCRAFT[f.aircraft].profile, is_player=False, tanker_xy=None,
                                 jsow=getattr(f, "kit", "") == "JSOW", jsow_side=self._jsow_side(package, geom), keep_out=self._umbrella_keep(package),
                                 harm_deg=self._harm_deg(package, geom))
            except ValueError:
                continue
            lp_ = next((w for w in wps if w.action in ("SEAD", "JSOW")), None) or next((w for w in wps if w.name == "IP"), None)
            if lp_ is not None:
                out.append((lp_.x, lp_.y))
        return out

    def _stagger_stations(self, geom, package, tx, ty) -> None:
        """v0.41.139 (XO 2026-10-27, the engagement circle diagram): short-range shooters (MiG-29, F-16, F/A-18 ...) closer to red, long-range
        snipers (F-15C, F-14B) behind them and to one side, so their missiles are not in the air across each other's jets. In a package that has a
        TARCAP and an escort of different range classes, whose stations lie within LRA_SPLIT_MIN_NM of each other (in the SAM-free runs they are on the
        very same point), the long-range one moves LRA_BACK_NM back from the target and LRA_SIDE_NM sideways of the short-range one. Same class, or already
        apart: nothing moves. Only the station moves; its other fields stay."""
        from . import profiles
        from .packages import LONG_RANGE_A2A
        tcs = [x for x in package.flights if x.role == Role.TARCAP and not x.tag]
        ecs = [x for x in package.flights if x.role == Role.ESCORT and not x.tag]
        for a in tcs:
            ka = (a.role, id(AIRCRAFT[a.aircraft].profile))
            for b in ecs:
                kb = (b.role, id(AIRCRAFT[b.aircraft].profile))
                sa, sb = geom.stand.get(ka), geom.stand.get(kb)
                la, lb = a.aircraft in LONG_RANGE_A2A, b.aircraft in LONG_RANGE_A2A
                if sa is None or sb is None or la == lb or dist(sa[0], sa[1], sb[0], sb[1]) >= LRA_SPLIT_MIN_NM * NM:
                    continue
                (lk, ls, lf), (sx, sy) = ((ka, sa, a), (sb[0], sb[1])) if la else ((kb, sb, b), (sa[0], sa[1]))
                t_ = geom.tiers.get(lk)
                alt = t_.alt_ft if (t_ is not None and t_.changed) else AIRCRAFT[lf.aircraft].profile.alt_ft.get(lf.role, 20000)
                brg = bearing(sx, sy, tx, ty)                        # toward the target; "behind" is the other way, so it is never nearer the target than the short-range station
                sites = profiles._cover_sites(self.state, alt)
                room = lambda x, y: min([dist(x, y, c.x, c.y) - (SA10_AVOID_NM * NM if c.variant in tm.UMBRELLA_VARIANTS else r_) for c, r_ in sites] + [1e9])
                for back, side in ((LRA_BACK_NM, LRA_SIDE_NM), (LRA_BACK_NM, LRA_SIDE_NM / 2), (LRA_BACK_NM / 2, LRA_SIDE_NM), (0.0, LRA_SIDE_NM), (LRA_BACK_NM, 0.0)):
                    bx, by = offset(sx, sy, brg + 180, back * NM)
                    cands = [offset(bx, by, brg + 90, side * NM), offset(bx, by, brg - 90, side * NM)] if side else [(bx, by)]
                    ok = [c for c in cands if room(*c) > 0]
                    if ok:
                        x, y = max(ok, key=lambda c: room(*c))
                        geom.stand[lk] = (x, y, ls[2], dist(x, y, tx, ty) / NM) + tuple(ls[4:])
                        break

    def _red_approach(self, cx, cy):
        """v0.41.119: where red's fighters most likely come from, seen from (cx, cy): the nearest of red's planned patrol stations and its live
        fighter bases. None when there is neither."""
        pts = [(c_["x"], c_["y"]) for c_ in (getattr(self, "_cap_plan", None) or [])] + list(tm.fighter_bases(self.state))
        return min(pts, key=lambda q: dist(cx, cy, q[0], q[1])) if pts else None

    def _sam_clear(self, x, y) -> bool:
        """v0.41.14: a friendly orbit is clear of SAMs: 35 nm from every live SA-10 (the reach measured in the runs; the ring table says 48 nm, which
        put the carrier CAP back on the boat in v0.41.13) and 15 nm outside every other SAM ring."""
        st = self.state
        if getattr(self, "_rings_c", None) is None:
            self._rings_c = [(a, r_) for a, r_ in tm.rings(st, min_range=3) if a.variant not in tm.UMBRELLA_VARIANTS]
            self._sa10_c = [a for a in st.assets.values() if a.variant in tm.UMBRELLA_VARIANTS and not a.destroyed and a.health > 0.25]
        return (all(dist(x, y, a.x, a.y) >= r_ + 15 * NM for a, r_ in self._rings_c)
                and all(dist(x, y, a.x, a.y) >= SA10_AVOID_NM * NM for a in self._sa10_c))

    def _zone_sams(self, package, fighters: bool = False, long_only: bool = False):
        """v0.41.22: the live medium / long-range SAMs a blue circle or HARM point must stay out of. Fighters (v0.41.24): every SA-2/3/6/11/10.
        Shooters: every one except the sites the package's HARMs are tasked on (v0.41.25: its target's cluster and the umbrella SA-10; for a CAS
        escort also the sites covering the CAS target)."""
        st = self.state
        key = (getattr(package, "id", None), fighters, long_only)
        c_ = getattr(self, "_zsams_c", {})
        if key in c_:
            return c_[key]
        from .war import covering_sams
        tid_ = package.objective.target_id
        tga_ = st.assets.get(tid_) if tid_ else None
        skip = set()
        if tga_ is not None and not fighters:      # v0.41.24: fighters never fight over the package's own target SAMs (that is the shooters' job)
            um_ = tm.umbrella_site(st, tga_)
            # v0.41.25: only the sites the package's HARMs are actually tasked on: its target's cluster and the umbrella SA-10 (and, for a CAS
            # escort, the sites covering the CAS target). Every other site counts, even one whose reach takes in the target: the v0.41.24 run's
            # Gudauta SA-6 package fired from 30 nm of the Sukhumi S-300, which "covered" its target and so was skipped, and lost four Hornets.
            skip = tm.cluster_ids(tga_) | ({um_.id} if um_ else set())
            if package.objective.type == ObjectiveType.CAS:
                skip |= {x.id for x in covering_sams(st, tga_)}
        out = [(a.x, a.y, AVOID_NM[a.variant]) for a in st.assets.values()
               if a.kind == AssetKind.SAM and a.variant in AVOID_NM and not a.destroyed and a.health > 0.25 and not getattr(a, "suppressed", False)
               and a.id not in skip and (not long_only or a.variant in tm.UMBRELLA_VARIANTS)]      # v0.41.42: long_only = only the SA-10s keep a shooter-cover circle out
        c_[key] = out
        self._zsams_c = c_
        return out

    def _clear_zone(self, zone, package, floor_nm: float = 8.0, fighters: bool = True, long_only: bool = False):
        """v0.41.22: a blue air-to-air engage circle (x, y, radius nm) trimmed so it ends outside every SAM's reach it is not sent against
        (the v0.41.21 scan: about 300 of 700 fight circles reached into an SA-2 / SA-6 / SA-11, so a fight that started on a clean station was
        chased over a SAM). Never below floor_nm."""
        if zone is None:
            return None
        x, y, r = zone
        for sx, sy, snm in self._zone_sams(package, fighters, long_only):
            r = min(r, dist(x, y, sx, sy) / NM - snm)
        return (x, y, max(floor_nm, r))

    @staticmethod
    def _hold_end(stw, tot_s) -> int:
        """TARCAP / sweep: their time on station; escort: until the last ground-attack flight is off target."""
        t_end = (tot_s if tot_s is not None else stw.eta_s + 600)
        if stw.action == "SWEEP":
            return int(stw.eta_s + TARCAP_MIN * 60)
        if stw.action == "TARCAP":
            return int(max(stw.eta_s + TARCAP_MIN * 60, t_end + TARCAP_AFTER_TOT_S))      # v0.41.38 (XO): at least TARCAP_MIN (15) min on station, then until the last striker is off + 5 min
        return int(max(stw.eta_s + 120, t_end + ESCORT_AFTER_TOT_S))

    def _room(self, x, y, package, fighters: bool = True, long_only: bool = False) -> float:
        """v0.41.23: how far (nm) a circle centred here can reach before it touches a SAM (v0.41.24: for fighters, any SAM, the target's included)."""
        return min([dist(x, y, sx, sy) / NM - snm for sx, sy, snm in self._zone_sams(package, fighters, long_only)] + [999.0])

    def _cover_circle(self, pts, c0, package, want_nm, back_brg, floor_nm: float = 8.0, long_only: bool = False, max_nm: float = 999.0):
        """v0.41.23: a fight circle (x, y, radius nm) that takes in every point in `pts`, at want_nm at least, clear of every SAM the package is
        not sent against. The centre starts at c0 and moves up to 24 nm, toward back_brg first (our side), then up to 90 degrees off it, nearest
        first. No position covers everything: the one that covers the most points (the first ones first: launch points before the station) with
        the most room. Never smaller than floor_nm."""
        best = None
        for sh in self.COVER_SHIFTS:
            for tn in (self.COVER_TURNS if sh else (0,)):
                cx, cy = offset(c0[0], c0[1], back_brg + tn, sh * NM) if sh else c0
                room = min(self._room(cx, cy, package, long_only=long_only), max_nm)
                need = max(dist(cx, cy, px, py) / NM for px, py in pts) + 2
                r = max(want_nm, need)
                if room >= r:
                    return (cx, cy, r)
                cov = [dist(cx, cy, px, py) / NM + 2 <= room for px, py in pts]
                score = (sum(cov), tuple(cov), room)
                if best is None or score > best[0]:
                    best = (score, (cx, cy, max(floor_nm, min(r, room))))
        return best[1]

    def _sweep_station(self, so, tx, ty, home_xy, package=None):
        """v0.41.33 (XO 2026-10-16): a Fighter Sweep no longer baits red. v0.41.13 put its station INSIDE the nearest enemy field's scramble circle
        at the edge of SAM reach; the 2026-10-16 run lost two F-15Cs to the Sukhumi S-300 in 95 s (34 nm, 30,000 ft). Now the station is short of
        the known red flight the planner sent it after (package.extra["sweep_vs"], sweep.station_for): on its line toward home, clear of SAMs by the
        sweep's wider margins, outside red's scramble circles where it can be. No such flight (an old plan): it only backs out of SAM reach toward
        home. -> the station tuple with its x, y (and nm short of the target) replaced."""
        from . import sweep as sweep_
        st = self.state
        x, y = so[0], so[1]
        vs_ = (getattr(package, "extra", None) or {}).get("sweep_vs")
        p_ = sweep_.station_for(st, (vs_["x"], vs_["y"]), home_xy, tx, ty) if vs_ else None
        if p_ is None and vs_ and vs_.get("sx") is not None:
            p_ = (vs_["sx"], vs_["sy"])                           # v0.41.34: the station the planner checked
        if p_ is not None:
            x, y = p_
        else:
            for _ in range(60):
                if sweep_.clear_for_sweep(st, x, y) or dist(x, y, *home_xy) < 2 * NM:
                    break
                x, y = offset(x, y, bearing(x, y, *home_xy), 2 * NM)
        return (x, y, so[2], dist(x, y, tx, ty) / NM) + tuple(so[4:])
