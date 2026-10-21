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
        if stw.action == "SWEEPSTN":
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
