"""Fighter station rules: engage circles, SAM-clear stations, hold times (TARCAP, escort, Fighter Sweep).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
import math

from dcs import mapping, task

from . import threatmap as tm
from . import samtier
from .aircraft import AIRCRAFT
from .loadouts import JSOW_FLIGHT_KITS
from .models import AssetKind, ObjectiveType, Role
from .routes import AVOID_NM, NM, bearing, dist, offset, plan_route

TARCAP_MIN = 15               # ...and holds there this long, then goes home
HOLD_FLOOR_MIN = 5            # S140d1: ladder rung 4, a TARCAP / sweep that cannot fit its fuel holds this long instead of TARCAP_MIN (it still stays until the last striker is off). Judgment call: the cover must be on station
                              # COVER_ONSTATION_S (120 s) before the first IP and long enough to be worth the trip; nothing in the probes reaches this rung
ESCORT_AFTER_EGR_S = 120      # v0.41.40: an escort stays until the last striker has reached its egress point + this long (XO 2026-10-20: DEADers were left behind)
ESCORT_AFTER_TOT_S = 180      # an escort (ESCORT role) holds its station until this long after the TOT (the last ground-attack flight off target)
TARCAP_AFTER_TOT_S = 300      # v0.41.0: a TARCAP holds until this long after the TOT (the last ground-attack flight egressing), not a fixed 15 minutes
HOLD_AREA_KM = 60             # v0.41.10: packages whose targets are this close share their TARCAP / escort holds (the sweep area)
ENGAGE_LEAD_S = 240           # v0.41.314: a sweep / escort starts hunting this long before it reaches its station, not from takeoff (judgment call, ~35 nm at cruise; XO's run: engage live from the spawn point burned the fuel in afterburner)
GATE_AIR_HOLD_S = 900          # v0.41.315: = strike_tasks.AIR_HOLD_STRIKE_S, the longest the fighters-clear gate holds strikers (keep the two in step)
GATE_RADAR_HOLD_S = 720        # ...= the Lua hook HOLD_S, the longest a DEAD flight holds for the radars
HOLD_EXTEND_MAX_S = 1800      # ...extended at most this much past their own package
LRA_BACK_NM = 8               # v0.41.139 (XO 2026-10-27): in a package with a short-range and a long-range fighter flight (TARCAP + escort), the long-range one stands this far behind the short-range one (away from the target)...
LRA_SIDE_NM = 6               # ...and this far to one side (judgment call: the sweep circles are 25 and 15 nm, so 10 nm between the two sets of jets; the lateral gap is for friendly-fire safety with active missiles in the air, DCS behaviour unverified)
LRA_SPLIT_MIN_NM = 12         # ...but only when the two stations are closer than this (the SAM-free runs put both on one point; with SAM rings in the way they are already 30 nm apart)
TRANSIT_CIRCLES_MAX = 4       # S156: at most this many engage circles along a cover flight's way from PUSH to its station (4 x 2 x 25 nm covers a 200 nm leg). Judgment call
COVER_AXIS_SPLIT_NM = 10.0    # S154: flights whose launch points (or IPs) are farther apart than this are on different axes, each with its own cover. The JSOW flight flies
                              # 30 deg off the HARM axis (routes.JSOW_AXIS_DEG): at a 30 nm launch range that is about 15 nm apart; two SEAD lanes are 1.5 to 4.5 nm apart. Judgment call
OVERWATCH_FAR_MAX_NM = 60     # S163: when nothing is clear within the 20 nm cap, a cover station may stand up to this far behind the protect point. Judgment call (XO's prompt, 2026-11-22): beyond the AIM-120's reach the cover cannot protect, so the caller reports the distance
def _axis_swings() -> tuple:
    """0, then +15 and -15, +30 and -30 ... up to +180 and -180 degrees: the smallest swing first."""
    swings = [0]
    for step in range(1, 13):
        swings.append(15 * step)
        swings.append(-15 * step)
    return tuple(swings)


# v0.41.119: degrees the TARCAP station may swing off the threat axis when SAM rings block it, smallest first, up to 180 (judgment call: a Sukhumi SA-10 sat on the axis in the 2026-10-22 probes, so the station takes the clear point nearest the axis; the old station is kept when that is no nearer)
TARCAP_AXIS_SWINGS = _axis_swings()


def axis_station(centre, threat, jsow_xy, near_nm, min_jsow_nm, clear, cur=None):
    """v0.41.119 (XO 2026-10-22: the TARCAP sat on the sea side, about 90 degrees off red's approach): the station `near_nm` from the middle of the shooters'
    launch points (`centre`) on the bearing toward `threat` (where red's fighters come from), swung off that bearing by the smallest of
    TARCAP_AXIS_SWINGS that is `clear(x, y)` of SAM rings and at least `min_jsow_nm` from the JSOW launch point. With `cur` (the station it would
    replace) it returns None unless the new point is nearer the axis than `cur`. -> (x, y) or None."""
    b0 = bearing(centre[0], centre[1], threat[0], threat[1])
    if cur is not None:
        cur_dev = abs((bearing(centre[0], centre[1], cur[0], cur[1]) - b0 + 180) % 360 - 180)      # how far the station it would replace is off the axis
    else:
        cur_dev = 999.0
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
    @staticmethod
    def _gate_slack_s(package) -> int:
        """v0.41.315 (XO 2026-11-06 run: the cover left at TOT + 4 min, the strikers sat at the fighters-clear gate until t=2260 and bombed at 2600, 12 min
        after the cover went home). A package whose strikers can be held at a gate (a strike / CAS with the air gate, a DEAD with the radar gate) keeps
        its cover up for the longest hold the gate allows: AIR_HOLD_STRIKE_S for the air gate, HOLD_S (12 min, in the Lua hook) for the radar gate.
        A stand-off job and the SEAD aims have no gate."""
        o = package.objective
        if o.aim in ("STANDOFF", "SEAD"):
            is_standoff_strike = o.type == ObjectiveType.STRIKE and o.aim == "STANDOFF"
            has_kit_flight = False
            for flight in package.flights:
                if getattr(flight, "kit", ""):
                    has_kit_flight = True
            if not is_standoff_strike or has_kit_flight:      # S60: a stand-off EWR strike with no kit flight (a person's) keeps the air gate's slack
                return 0
        if o.type in (ObjectiveType.STRIKE, ObjectiveType.CAS):
            return GATE_AIR_HOLD_S
        if o.type == ObjectiveType.DEAD:
            return GATE_RADAR_HOLD_S
        return 0

    def _extend_holds(self, events, egr_events=()) -> None:
        """v0.41.10: a TARCAP / escort holds until the LAST package over its target area is off target (TOT + its after-time), not just its own
        package. The v0.41.8 sweep run: the F-15 TARCAPs went home 5 min after their own TOT while later packages were still coming through
        (1,600-2,500 s) and only the F-14s were left. At most HOLD_EXTEND_MAX_S longer; bingo fuel sends them home anyway."""
        for h in self._holds:
            hx, hy = h["tgt"]
            near_times = []                                    # when each package over this area is off target
            for (event_x, event_y), event_time in events:
                if event_time is not None and dist(event_x, event_y, hx, hy) <= HOLD_AREA_KM * 1000:
                    near_times.append(event_time)
            if h.get("first"):
                later_times = []
                for event_time in near_times:
                    if event_time > h.get("eta", 0) + 60:
                        later_times.append(event_time)
                if later_times:
                    last = min(later_times)
                else:
                    last = 0
            else:
                last = max(near_times + [0])
            want = last + h["after"] + h.get("gate_s", 0)
            if h["after"] == ESCORT_AFTER_TOT_S:         # an escort sticks to the last striker until it is out (egress point), like a shepherd
                egress_times = []
                for (event_x, event_y), event_time in egr_events:
                    if dist(event_x, event_y, hx, hy) <= HOLD_AREA_KM * 1000:
                        egress_times.append(event_time)
                want = max(want, max(egress_times + [0]) + ESCORT_AFTER_EGR_S)
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
        if nm and nm > 0:
            meters = int(nm * 1852)
        else:
            meters = None
        old = []
        for t in g.points[0].tasks:
            if getattr(t, "Id", "") in ("EngageTargets", "EngageTargetsInZone"):
                old.append(t)
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
                wps = plan_route(f.role, (base.x, base.y), geom, self._flight_profile(f, package), is_player=False, tanker_xy=None,
                                 jsow=getattr(f, "kit", "") in JSOW_FLIGHT_KITS, jsow_side=self._jsow_side(package, geom), keep_out=self._umbrella_keep(package),
                                 agm88_deg=self._agm88_deg(package, geom), rel=self._rel_kind(package, f))
            except ValueError:
                continue
            launch_point = None                                # the HARM or JSOW launch point, else the IP
            for w in wps:
                if w.action in ("SEAD", "JSOW"):
                    launch_point = w
                    break
            if launch_point is None:
                for w in wps:
                    if w.name == "IP":
                        launch_point = w
                        break
            if launch_point is not None:
                out.append((launch_point.x, launch_point.y))
        return out

    def _station_clear(self, x, y, sites) -> bool:
        """S141b: True when (x, y) is outside every live medium / long-range SAM ring in `sites` (`profiles._cover_sites`), an SA-10 / SA-5 at its station_nm instead of its table ring + margin
        (v0.41.118: the TARCAP / escort station rule, so the orbit's near end stays outside the avoid ring)."""
        for site, ring_m in sites:
            if site.variant in tm.UMBRELLA_VARIANTS:
                ring_m = samtier.get(site.variant, "station_nm") * NM      # an SA-10 / SA-5 keeps its own station ring, not the table ring
            if not dist(x, y, site.x, site.y) > ring_m:
                return False
        return True

    def _overwatch_station(self, package, geom, f, alt_ft, pp, back_nm):
        """S141b (XO 2026-11-22: TARCAPs and station escorts guard the package): the overwatch station of a TARCAP / station escort. P = the package's protect point nearest red's approach
        (`_red_approach` of their centre); walking from P along red's line AWAY from red, 1 nm at a time, 0 to `back_nm`, the first point outside every SAM ring (`_station_clear`, the JSOW
        branch's own test at the flight's altitude). The flight then faces red nose-on and shoots past the package. None when there is no red approach, no point or nothing clear
        within `back_nm` (the caller keeps today's station). Prototype: the S141 probe's `candoverwatch`."""
        from . import profiles
        pp = list(pp or [])
        self._ow_why = "no protect points"                  # why it fell back (probe)
        if not pp:
            return None
        sum_x = 0.0
        sum_y = 0.0
        for protect_point in pp:
            sum_x += protect_point[0]
            sum_y += protect_point[1]
        cx, cy = sum_x / len(pp), sum_y / len(pp)
        thr = self._red_approach(cx, cy)
        self._ow_why = "no red approach point"
        if thr is None:
            return None
        px, py = pp[0]                                      # the protect point nearest red's approach
        nearest_m = dist(px, py, thr[0], thr[1])
        for protect_point in pp[1:]:
            distance_m = dist(protect_point[0], protect_point[1], thr[0], thr[1])
            if distance_m < nearest_m:
                px, py = protect_point
                nearest_m = distance_m
        b = bearing(thr[0], thr[1], px, py)
        sites = profiles._cover_sites(self.state, alt_ft)
        for n in range(0, int(back_nm) + 1):
            x, y = offset(px, py, b, n * NM)
            if self._station_clear(x, y, sites):
                self._ow_why = ""
                return (x, y)
        # S163: nothing clear within the cap. Try further back instead of keeping the old station inside a live ring.
        far_point = self._overwatch_far_back(px, py, b, back_nm, sites)
        if far_point is not None:
            self._ow_why = ""
            self._ow_far = "back"
            return far_point
        self._ow_why = "nothing clear within the far cap"
        return None

    def _overwatch_far_back(self, px, py, bearing_back, back_nm, sites):
        """S163 (tests T4 / T4b: a live Buk at the Sukhumi fuel farm covered every point within the 20 nm cap): the same walk as `_overwatch_station`,
        one nm at a time, but from the cap out to OVERWATCH_FAR_MAX_NM. The first point outside every ring, or None."""
        for n in range(int(back_nm) + 1, OVERWATCH_FAR_MAX_NM + 1):
            x, y = offset(px, py, bearing_back, n * NM)
            if self._station_clear(x, y, sites):
                return (x, y)
        return None

    def _protect_points(self, package, geom) -> list:
        """v0.41.546 (S137, XO 2026-11-21: tethered aggression): the points the package's TARCAP / escort protect, round which their engage circle is
        centred: for every ground-attack flight (STRIKE / CAS, a person's own flight too: the mission is the same) its IP, its TGT and the point
        after it (the egress turn). A stand-off flight (SEAD, a JSOW kit, the SLAM point) gives only its launch point: its TGT lies in the SAM belt.
        Empty when nothing plans (the caller falls back to the launch points). S154: the same points as `_protect_points_by_flight`, in one list."""
        out = []
        for points in self._protect_points_by_flight(package, geom):
            out.extend(points)
        return out

    def _cover_axes(self, flight_points) -> list:
        """S154 (test T1 Syria: the JSOW flight flew 30 degrees off the HARM axis, 42 km from the SEAD flights, and the cover guarded only the SEAD side).
        The package's protect points as axes, the most exposed axis first. `flight_points` is one list of points per flight (`_protect_points_by_flight`).
        Flights whose first points (launch point or IP) lie within COVER_AXIS_SPLIT_NM of each other share an axis. The most exposed axis is the one whose
        centre is nearest its own red approach (`_red_approach`). -> a list of point lists; one axis when everything flies together."""
        axes = []                       # each item: {"first": (x, y) of the axis's first flight, "points": [...]}
        for points in flight_points:
            if not points:
                continue
            first = points[0]
            home = None
            for axis in axes:
                if dist(first[0], first[1], axis["first"][0], axis["first"][1]) <= COVER_AXIS_SPLIT_NM * NM:
                    home = axis
                    break
            if home is None:
                axes.append({"first": first, "points": list(points)})
            else:
                home["points"].extend(points)
        scored = []
        for index, axis in enumerate(axes):
            total_x = 0.0
            total_y = 0.0
            for point in axis["points"]:
                total_x += point[0]
                total_y += point[1]
            centre_x = total_x / len(axis["points"])
            centre_y = total_y / len(axis["points"])
            threat = self._red_approach(centre_x, centre_y)
            if threat is None:
                distance = float("inf")
            else:
                distance = dist(centre_x, centre_y, threat[0], threat[1])
            scored.append((distance, index, axis["points"]))
        scored.sort()                   # nearest to red first; the index breaks ties, so the lists themselves are never compared
        result = []
        for distance, index, points in scored:
            result.append(points)
        return result

    def _transit_circles(self, package, wps, stw, base, reach_nm) -> list:
        """S156 (XO 2026-11-22, test T1fix2 Syria: two Su-27s shot the F-15C TARCAP from 43 to 28 km while staying outside every engage circle, and it never
        fired back): engage circles along the flight's own route from PUSH to its station, so it fights what comes within its reach on the way in, not only round
        the package. Fixed circles, not a circle that moves with the jet (a moving one chases: v0.41.15). Each is reach_nm, moved / trimmed clear of SAMs like the
        other circles. At most TRANSIT_CIRCLES_MAX, spread evenly. -> [(x, y, radius nm)]; empty when there is no PUSH before the station."""
        push_index = None
        station_index = None
        for index, w in enumerate(wps):
            if w.name == "PUSH" and push_index is None:
                push_index = index
            if w is stw:
                station_index = index
        if push_index is None or station_index is None or station_index <= push_index:
            return []
        leg = wps[push_index:station_index + 1]
        total_m = 0.0
        for a, b in zip(leg, leg[1:]):
            total_m += dist(a.x, a.y, b.x, b.y)
        if total_m < 1.0:
            return []
        count = math.ceil(total_m / (2 * reach_nm * NM))
        count = max(1, min(TRANSIT_CIRCLES_MAX, count))
        circles = []
        for k in range(count):
            want_m = total_m * (k + 0.5) / count          # the middle of each of `count` equal stretches of the leg
            point = self._point_along(leg, want_m)
            back = bearing(point[0], point[1], base.x, base.y)
            zone = self._cover_circle([point], point, package, reach_nm, back)
            zone = self._clear_zone(zone, package)
            if zone is not None:
                circles.append(zone)
        return circles

    @staticmethod
    def _point_along(points, want_m):
        """S156: the point `want_m` metres along the line through `points` (route points with .x / .y); the last point when the line is shorter."""
        walked = 0.0
        for a, b in zip(points, points[1:]):
            step = dist(a.x, a.y, b.x, b.y)
            if step > 0 and walked + step >= want_m:
                share = (want_m - walked) / step
                return (a.x + (b.x - a.x) * share, a.y + (b.y - a.y) * share)
            walked += step
        last = points[-1]
        return (last.x, last.y)

    def _protect_points_by_flight(self, package, geom) -> list:
        """S154: `_protect_points`, one list per ground-attack flight (flights with nothing to protect are left out)."""
        out = []
        for f in package.flights:
            if f.tag or f.role not in (Role.SEAD, Role.STRIKE, Role.CAS):
                continue
            base = self.state.bases[f.base_id]
            try:
                wps = plan_route(f.role, (base.x, base.y), geom, self._flight_profile(f, package), is_player=False, tanker_xy=None,
                                 jsow=getattr(f, "kit", "") in JSOW_FLIGHT_KITS, jsow_side=self._jsow_side(package, geom), keep_out=self._umbrella_keep(package),
                                 agm88_deg=self._agm88_deg(package, geom), rel=self._rel_kind(package, f))
            except ValueError:
                continue
            lp_ = next((w for w in wps if w.action in ("SEAD", "JSOW")), None) or next((w for w in wps if w.name == "IP"), None)
            standoff_ = f.role == Role.SEAD or getattr(f, "kit", "") in JSOW_FLIGHT_KITS or any(w.name == "SLAM" for w in wps)
            flight_points = []
            if standoff_:
                if lp_ is not None:
                    flight_points.append((lp_.x, lp_.y))
            else:
                ti_ = next((k for k, w in enumerate(wps) if w.name == "TGT"), None)
                if ti_ is None:
                    if lp_ is not None:
                        flight_points.append((lp_.x, lp_.y))
                else:
                    ip_ = next((w for w in wps[:ti_] if w.name == "IP"), None)
                    for w in (ip_, wps[ti_], wps[ti_ + 1] if ti_ + 1 < len(wps) else None):
                        if w is not None:
                            flight_points.append((w.x, w.y))
            if flight_points:
                out.append(flight_points)
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
            ka = self._stand_key(a, AIRCRAFT[a.aircraft].profile, geom)          # S231b: the player's own station when it has one
            for b in ecs:
                kb = self._stand_key(b, AIRCRAFT[b.aircraft].profile, geom)
                sa, sb = geom.stand.get(ka), geom.stand.get(kb)
                la, lb = a.aircraft in LONG_RANGE_A2A, b.aircraft in LONG_RANGE_A2A
                if sa is None or sb is None or la == lb or dist(sa[0], sa[1], sb[0], sb[1]) >= LRA_SPLIT_MIN_NM * NM:
                    continue
                (lk, ls, lf), (sx, sy) = ((ka, sa, a), (sb[0], sb[1])) if la else ((kb, sb, b), (sa[0], sa[1]))
                t_ = geom.tiers.get(lk)
                alt = t_.alt_ft if (t_ is not None and t_.changed) else AIRCRAFT[lf.aircraft].profile.alt_ft.get(lf.role, 20000)
                brg = bearing(sx, sy, tx, ty)                        # toward the target; "behind" is the other way, so it is never nearer the target than the short-range station
                sites = profiles._cover_sites(self.state, alt)
                def room(x, y):
                    # the least distance to the edge of a SAM site's keep-out circle (an umbrella site: its station ring; others: their own ring); 1e9 with no site
                    least_room = 1e9
                    for site, site_ring in sites:
                        ring_edge_m = site_ring
                        if site.variant in tm.UMBRELLA_VARIANTS:
                            ring_edge_m = samtier.get(site.variant, "station_nm") * NM
                        site_room = dist(x, y, site.x, site.y) - ring_edge_m
                        if site_room < least_room:
                            least_room = site_room
                    return least_room
                for back, side in ((LRA_BACK_NM, LRA_SIDE_NM), (LRA_BACK_NM, LRA_SIDE_NM / 2), (LRA_BACK_NM / 2, LRA_SIDE_NM), (0.0, LRA_SIDE_NM), (LRA_BACK_NM, 0.0)):
                    bx, by = offset(sx, sy, brg + 180, back * NM)
                    cands = [offset(bx, by, brg + 90, side * NM), offset(bx, by, brg - 90, side * NM)] if side else [(bx, by)]
                    ok = [c for c in cands if room(*c) > 0]
                    if ok:
                        x, y = None, None
                        most_room = None
                        for candidate_xy in ok:
                            candidate_room = room(*candidate_xy)
                            if most_room is None or candidate_room > most_room:
                                x, y = candidate_xy
                                most_room = candidate_room
                        geom.stand[lk] = (x, y, ls[2], dist(x, y, tx, ty) / NM) + tuple(ls[4:])
                        break

    def _red_approach(self, cx, cy):
        """v0.41.119: where red's fighters most likely come from, seen from (cx, cy): the nearest of red's planned patrol stations and its live
        fighter bases. None when there is neither."""
        pts = [(c_["x"], c_["y"]) for c_ in (getattr(self, "_cap_plan", None) or [])] + list(tm.fighter_bases(self.state))
        nearest_point = None
        nearest_point_m = None
        for candidate_point in pts:
            candidate_m = dist(cx, cy, candidate_point[0], candidate_point[1])
            if nearest_point_m is None or candidate_m < nearest_point_m:
                nearest_point = candidate_point
                nearest_point_m = candidate_m
        return nearest_point

    def _sam_clear(self, x, y) -> bool:
        """v0.41.14: a friendly orbit is clear of SAMs: 35 nm from every live SA-10 (the reach measured in the runs; the ring table says 48 nm, which
        put the carrier CAP back on the boat in v0.41.13) and 15 nm outside every other SAM ring."""
        st = self.state
        if getattr(self, "_rings_c", None) is None:
            self._rings_c = [(a, r_) for a, r_ in tm.rings(st, min_range=3) if a.variant not in tm.UMBRELLA_VARIANTS]
            self._sa10_c = [a for a in st.assets.values() if a.variant in tm.UMBRELLA_VARIANTS and not a.destroyed and a.health > 0.25]
        return (all(dist(x, y, a.x, a.y) >= r_ + 15 * NM for a, r_ in self._rings_c)
                and all(dist(x, y, a.x, a.y) >= samtier.get(a.variant, "station_nm") * NM for a in self._sa10_c))

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

    def _clear_zone(self, zone, package, floor_nm: float = 8.0, fighters: bool = True, long_only: bool = False, hold=None):
        """v0.41.22: a blue air-to-air engage circle (x, y, radius nm) trimmed so it ends outside every SAM's reach it is not sent against
        (the v0.41.21 scan: about 300 of 700 fight circles reached into an SA-2 / SA-6 / SA-11, so a fight that started on a clean station was
        chased over a SAM). Never below floor_nm."""
        if zone is None:
            return None
        x, y, r = zone
        r0 = r
        sams = self._zone_sams(package, fighters, long_only)
        for sx, sy, snm in sams:
            r = min(r, dist(x, y, sx, sy) / NM - snm)
        if hold is not None and dist(x, y, hold[0], hold[1]) / NM > max(floor_nm, r):
            # v0.41.177 (XO 2026-10-28, run 3: Dodge 5's orbit sat 22.7 nm from the centre of a circle the SA-10 trim had cut to 17 nm, so the pair was
            # fighting outside its zone and chased into the SA-10): when the trim leaves the CAP's own orbit point outside the circle, the circle is
            # centred on the orbit point instead, as big as the SAMs allow (floor_nm at least)
            x, y = hold
            r = min([r0] + [dist(x, y, sx, sy) / NM - snm for sx, sy, snm in sams])
        return (x, y, max(floor_nm, r))

    @staticmethod
    def _hold_end(stw, tot_s, short: bool = False) -> int:
        """TARCAP / sweep: their time on station; escort: until the last ground-attack flight is off target. `short` (S140d1, ladder rung 4): HOLD_FLOOR_MIN instead of TARCAP_MIN."""
        t_end = (tot_s if tot_s is not None else stw.eta_s + 600)
        mn = HOLD_FLOOR_MIN if short else TARCAP_MIN
        if stw.action == "SWEEP":
            return int(stw.eta_s + mn * 60)
        if stw.action == "TARCAP":
            return int(max(stw.eta_s + mn * 60, t_end + TARCAP_AFTER_TOT_S))      # v0.41.38 (XO): at least TARCAP_MIN (15) min on station, then until the last striker is off + 5 min
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
