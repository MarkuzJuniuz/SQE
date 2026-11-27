"""CAS ground fight: the support force, the front battles on the map, the front air cover and the helpers that drive a column (road points, arrival speeds, land snapping).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.m`, `self.state`, `self.o`, `self.t` and the other fields the builder sets up.
The `CAS_*` / `FRONT_*` class constants stay in `MissionBuilder` (read here as `self.CAS_...`); the module-level constants stay in `mission_builder.py`:
each method imports what it uses at the start of its own body, so a probe's `mb.NAME = ...` still takes effect.
"""
from __future__ import annotations
import copy
import math

from dcs import action, condition, mapping, planes, task, triggers
from dcs.point import PointAction
from dcs.translation import String

from . import ground
from . import seacheck as seac
from . import threatmap as tm
from .aircraft import AIRCRAFT
from .loadouts import enemy_cap_loadout, enemy_strike_loadout
from .models import BaseKind, Role
from .routes import FT, NM, bearing, dist, offset
from .strike_tasks import KPH


def _scaled(comp, sc):
    """The company's (type, count) rows with every count scaled by `sc` (at least 1 each)."""
    return [(n_, max(1, int(round(c_ * sc)))) for n_, c_ in comp]


def _name_units(g, tag):
    """Name the group's units `<tag>|1`, `<tag>|2`, ... -> the names, in order."""
    names = []
    for k, u in enumerate(g.units, 1):
        u.name = f"{tag}|{k}"; names.append(u.name)
    return names


def _full_strength_count(names, strength):
    """S83 / S84: the size of the friendly force at full strength (its `base_count`), so the battle's losses read back as strength by one rule."""
    return max(len(names), round(len(names) / max(0.05, strength / ground.MAX_FORCE)))


def _arm_group(g, load, prefix, rename=None):
    """Name a strike group's units `<prefix>1`, `<prefix>2`, ... and give each its own copy of the loadout -> the names, in order."""
    names = []
    for j, u in enumerate(g.units, 1):
        wanted = f"{prefix}{j}"
        if rename is not None:                      # S219: red's aircraft may get Jester's names
            wanted = rename(wanted)
        u.name = wanted; u.pylons = copy.deepcopy(load); names.append(u.name)
    return names


def _commit(used, key):
    """Mark a pair of jets as committed to a strike in this mission (`used` counts jets per wing or squadron)."""
    used[key] = used.get(key, 0) + 2


class CasGround:
    # ---- CAS: both columns drive into contact so the clash is under way at the CAS TOT (+/- 30 s) -------------------------
    def _translate(self, g, dx, dy):
        """Move every unit and route point of the group by (dx, dy)."""
        for u in g.units:
            u.position = mapping.Point(u.position.x + dx, u.position.y + dy, self.t)
        for p in g.points:
            p.position = mapping.Point(p.position.x + dx, p.position.y + dy, self.t)

    @staticmethod
    def _ground_orders(g):
        """v0.41.39: explicit orders on a ground group: weapons free, alarm state red (radars up, guns manned). Left at the default a group may sit
        at 'auto' and hold fire on aircraft parked in range; set here it engages whatever it sees. The Mission Editor has no target-priority
        order for ground units, so 'other ground units before parked jets' is not enforced: DCS picks the target (usually the nearest threat)."""
        if any(isinstance(t_, task.OptROE) for t_ in g.points[0].tasks):
            return
        g.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponFree))
        g.points[0].tasks.append(task.OptAlarmState(2))

    def _drive(self, g, via, speed_ms, road: bool = False):
        # S226: an off-road leg is a straight line for DCS, so no leg may cross the sea
        start = (g.points[0].position.x, g.points[0].position.y)
        for q in self._dry_via(start, via):
            g.add_waypoint(mapping.Point(q[0], q[1], self.t), PointAction.OffRoad, speed_ms * 3.6)
        self._ground_orders(g)

    def _road_pt(self, x, y):
        """v0.41.180: the nearest road point within CAS_ROAD_SNAP_M, else None (the theatre ships no road net, or no road that close)."""
        from . import roads
        return roads.snap(x, y, self.CAS_ROAD_SNAP_M) if roads.available() else None

    def _drive_road(self, g, via, speed_ms) -> bool:
        """v0.41.180: drive the group to `via` on roads ("On Road": DCS routes it along them, as a column) when each point has a road close by;
        else the old straight off-road drive. -> True when it went by road."""
        pts = [self._road_pt(*q) for q in via]
        if not pts or any(p_ is None for p_ in pts):
            self._drive(g, via, speed_ms)
            return False
        for q in pts:
            g.add_waypoint(mapping.Point(q[0], q[1], self.t), PointAction.OnRoad, speed_ms * 3.6)
        self._ground_orders(g)
        return True

    @staticmethod
    def _route_length(g) -> float:
        """Metres along the group's route points as built (road points snapped), start to end."""
        length = 0.0
        for number in range(1, len(g.points)):
            here = g.points[number - 1].position
            there = g.points[number].position
            length += math.hypot(there.x - here.x, there.y - here.y)
        return length

    def _time_column(self, g, t_arrive, top_ms):
        """S228 (v0.41.190's out-and-back patrol leg was skipped by DCS): set the group's driving speed so it reaches its last point at about mission second
        t_arrive in DCS: the route as built divided by t_arrive, divided again by CAS_DCS_SPEED_SHARE (DCS drives slower than set), never above top_ms
        nor below CAS_COLUMN_MIN_MS. Where even the floor speed would get it there early by CAS_HOLD_MIN_S or more, it first holds where it stands
        (a Hold task with a time stop on its first point). No time left: top speed, no hold."""
        if len(g.points) < 2:
            return
        length = self._route_length(g)
        speed = top_ms
        if t_arrive > 0:
            speed = length / t_arrive / self.CAS_DCS_SPEED_SHARE
            speed = min(top_ms, speed)
            speed = max(self.CAS_COLUMN_MIN_MS, speed)
        for point in g.points[1:]:
            point.speed = speed
        drive_s = length / (speed * self.CAS_DCS_SPEED_SHARE)
        wait_s = t_arrive - drive_s
        if wait_s < self.CAS_HOLD_MIN_S:
            return
        hold = task.ControlledTask(task.Hold())
        hold.stop_after_time(int(wait_s))
        g.points[0].tasks.append(hold)

    def _cas_land(self, p):
        """v0.41.384 (S29): the point moved onto land (CAS_COAST_M from the sea) when it is in the water or on the beach (nearest 200 m ring with a good point, seacheck.site_ok); the point itself when it is fine or nothing is found."""
        if seac.site_ok(p[0], p[1], self.CAS_COAST_M):
            return (p[0], p[1])
        r_ = 200.0                                                # finer rings than seacheck.snap_to_land's 1 km: a column should move metres, not kilometres off its line
        while r_ <= self.CAS_LAND_SEARCH_M:
            best = None
            for k in range(24):
                a_ = math.radians(k * 15)
                x_, y_ = p[0] + r_ * math.cos(a_), p[1] + r_ * math.sin(a_)
                if seac.site_ok(x_, y_, self.CAS_COAST_M):
                    cd_ = seac.coast_distance(x_, y_)
                    if best is None or cd_ > best[0]:
                        best = (cd_, x_, y_)
            if best is not None:
                return (best[1], best[2])
            r_ += 200.0
        return (p[0], p[1])

    def _dry_part(self, a, b):
        """S226: how far the straight leg a -> b can be driven before it meets the sea -> (point, whole). A dry leg gives (b, True);
        a wet one gives the last point before the water that keeps CAS_COAST_M from it (a itself when there is none) and False."""
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        steps = max(1, int(math.ceil(length / self.CAS_LEG_STEP_M)))
        last_good = (a[0], a[1])
        for step in range(1, steps + 1):
            x = a[0] + (b[0] - a[0]) * step / steps
            y = a[1] + (b[1] - a[1]) * step / steps
            if seac.in_sea(x, y):
                return last_good, False
            if seac.site_ok(x, y, self.CAS_COAST_M):
                last_good = (x, y)
        return (b[0], b[1]), True

    def _dry_via(self, start, via):
        """S226: the route points a column at `start` may drive through so that no leg crosses the sea. A wet patrol point is left out (the
        column goes straight on); a wet last leg is cut at the last dry point; nothing is left when the column cannot move at all."""
        points = []
        here = (start[0], start[1])
        for number, wanted in enumerate(via):
            if math.hypot(wanted[0] - here[0], wanted[1] - here[1]) < 1.0:
                continue
            reached, whole = self._dry_part(here, wanted)
            if whole:
                points.append(reached)
                here = reached
                continue
            is_last = number == len(via) - 1
            if is_last and math.hypot(reached[0] - here[0], reached[1] - here[1]) >= self.CAS_SHORTEST_LEG_M:
                points.append(reached)
                here = reached
        return points

    def _blue_company_roll(self):
        """The blue company's composition as the dice give it: Abrams 1-2, Bradley 2-3, Humvee 1-2 (three `vrng` draws, in this order). Scale it with `_scaled`."""
        r = self.vrng
        return [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(2, 3)), ("M1043_HMMWV_Armament", r.randint(1, 2))]

    def _spawn_cas_support(self, package, plan, geom, manifest):
        if not package.jtac:
            return
        z_ = ground.zone_of(self.state, package.objective.target_id or "")
        first_ = z_ is not None and z_ not in self._cas_zones     # S84: the sector's own company, the same "Blue Company N" a front battle shows; a second CAS package on one sector keeps its own name
        if z_ is not None:
            self._cas_zones.add(z_)                               # S81: this sector's battle is the CAS package's own
        # v0.41.137: the CAS TARGET's own group and centre (not "the last armour group spawned": a CAS package also builds the target's defenders,
        # and a garrison or a neighbouring column built after it used to take the place of the target here)
        tid = package.objective.target_id
        cx, cy = self.site_pos.get(tid) or (geom.tx, geom.ty)
        fb = self._nearest_airfield(cx, cy)
        brg = bearing(cx, cy, fb.x, fb.y)                         # towards our side
        t_contact, dist_run, v = self._cas_kinematics()
        enemy = self.groups_by_asset.get(tid) if tid else None
        static = bool(tid) and self.state.assets[tid].variant == "GARRISON"      # dug in: our troops come to it
        if enemy is not None and not static:
            self._drive_cas_enemy(enemy, cx, cy, brg, v, t_contact)
        fx, fy, stop = self._cas_tf_start(cx, cy, brg, dist_run, static)
        g, names = self._cas_task_force(package, z_, first_, tid, brg, fx, fy, stop, v, t_contact, static)
        names.append(self._cas_jtac(package, plan, fx, fy, cx, cy, brg, v))
        if names:
            bs_ = ground.blue_strength(self.state, z_) if z_ is not None else 0.0
            manifest.add("friendly_ground", tid or "", names, sector=z_,
                         base_count=_full_strength_count(names, bs_) if z_ is not None else len(names))      # S84: its size at full strength, so the CAS battle's losses read back as strength by the same rule as a front battle's
        if g is not None and enemy is not None:
            self._cas_battle_rule(package, enemy, [n_ for n_ in names if n_.startswith(("TF", "BC"))], t_contact)
            zc_ = ground.zone_of(self.state, tid or "")
            if zc_ is not None:
                self._spawn_front_air(zc_, enemy, g, t_contact, manifest)

    def _cas_kinematics(self):
        """-> (t_contact, dist_run, v): the contact time (guns firing as the CAS flight arrives), how far from the contact point the friendly force starts, and its advance speed in m/s."""
        tot = float(self.cas_tot or 1500.0)
        t_contact = max(300.0, tot - 15.0)                        # guns are firing as the CAS flight arrives
        dist_run = min(8.0 * t_contact + 1500.0, self.CAS_APPROACH_M)      # the friendly force starts this far from the contact point
        v = max(2.5, min(8.0, (dist_run - self.CAS_TF_STOP_M) / t_contact))   # m/s, a believable advance
        return t_contact, dist_run, v

    def _drive_cas_enemy(self, enemy, cx, cy, brg, v, t_contact):
        # v0.41.137: the column stays where the CAS flight is sent. It used to start up to 10 km back and drive 13 km to be at the CAS point
        # at the TOT; any shortfall in DCS's real speed (slopes, a long mixed column, stopping to fight) left it kilometres from the point
        t_arr_ = max(0.0, t_contact - self.CAS_ARRIVE_LEAD_S)
        # S228: straight to its point at a speed that gets it there at t_arr_ in DCS (v0.41.190's out-and-back patrol leg was skipped by DCS); v0.41.384: on land
        final = self._cas_land(offset(cx, cy, brg, self.CAS_ENEMY_ADVANCE_M))
        top_ms = min(v, 3.5)
        self._drive_road(enemy, [final], top_ms)
        self._time_column(enemy, t_arr_, top_ms)

    def _tf_start_at(self, cx, cy, bearing_deg, distance_m, static):
        """A possible start of the friendly task force: that far out on that bearing, on a road when it drives (not for a garrison) and on land."""
        fx, fy = offset(cx, cy, bearing_deg, distance_m)
        if not static:
            road_point = self._road_pt(fx, fy)                    # v0.41.180: the task force starts on a road too, and meets the column along it
            if road_point is not None:
                fx, fy = road_point
        return self._cas_land((fx, fy))                           # v0.41.384 (S29, XO 2026-11-11 run: a garrison near the coast put the column afloat)

    def _tf_dry_start(self, cx, cy, bearing_deg, dist_run, static, stop, turns):
        """A start with a dry straight leg to `stop`: at the full approach distance first, then nearer, on each turn off the bearing -> (x, y) or None."""
        for share in self.CAS_TF_START_SHARES:
            for turn in turns:
                point = self._tf_start_at(cx, cy, bearing_deg + turn, dist_run * share, static)
                if not seac.in_sea(*point) and self._dry_part(point, stop)[1]:
                    return point
        return None

    def _cas_tf_start(self, cx, cy, brg, dist_run, static):
        """-> (fx, fy, stop): where the friendly task force starts (on a road, on land, and with a dry straight leg to the stop) and its stop point."""
        stop_m = 2000 if static else self.CAS_TF_STOP_M
        wanted = offset(cx, cy, brg, stop_m)
        stop = self._cas_land(wanted)                             # v0.41.384 (S29): on land
        jitter = self.vrng.uniform(-6, 6)
        first = self._tf_start_at(cx, cy, brg + jitter, dist_run, static)
        if not seac.in_sea(*first) and self._dry_part(first, stop)[1]:
            return first[0], first[1], stop
        # S226: the straight leg to the stop crosses the sea. Where the stop is about where it was meant to be, look for another start for it.
        if math.hypot(stop[0] - wanted[0], stop[1] - wanted[1]) <= self.CAS_STOP_SLIP_M:
            point = self._tf_dry_start(cx, cy, brg + jitter, dist_run, static, stop, self.CAS_LEG_BEARINGS_DEG)
            if point is not None:
                return point[0], point[1], stop
        # Else the whole approach swings round onto land, along the coast: the stop keeps its distance from the target (the target stays put).
        for turn in self.CAS_APPROACH_TURNS_DEG:
            other = offset(cx, cy, brg + turn, stop_m)
            if not seac.site_ok(other[0], other[1], self.CAS_COAST_M):
                continue
            point = self._tf_dry_start(cx, cy, brg + turn, dist_run, static, other, (0,) + self.CAS_LEG_BEARINGS_DEG[:4])
            if point is not None:
                return point[0], point[1], other
        return stop[0], stop[1], stop                             # no dry way in: the task force waits at its stop

    def _cas_task_force(self, package, z_, first_, tid, brg, fx, fy, stop, v, t_contact, static):
        """Build the friendly company at (fx, fy), name its units and drive it to `stop` -> (group or None, unit names)."""
        from .mission_builder import F  # the builder's module imports this one
        comp = self._blue_company_roll()
        sc = ground.blue_scale(self.state, tid or "")          # the friendly force is as strong as Blue is in this sector
        gname_, utag_ = (f"Blue Company {z_ + 1}", f"BC{z_ + 1}") if first_ else (f"Friendly Task Force {package.number}", f"TF{package.number}")
        g = self._platoon(self.usa, gname_, _scaled(comp, sc), fx, fy, (int(brg) + 180) % 360, F.Rectangle)
        names = []
        if g is not None:
            self._tf_names[str(package.number)] = gname_
            names = _name_units(g, utag_)
            # v0.41.157 (XO's 15:38 run: the task force reached the column 12 minutes after the A-10s, then drove 2.5 km past it): it stops CAS_TF_STOP_M (v0.41.179: 1.5 km, was 400 m) short of the
            # contact point (static garrison: 2 km short) and holds, weapons free, so the survivors come to it.
            # S228: it drives straight to its stop at a speed that gets it there at the meeting time in DCS (DCS drives slower than set: CAS_DCS_SPEED_SHARE);
            # the old out-and-back patrol leg (v0.41.190) was skipped by DCS. v0.41.384: on land
            t_arrive = max(0.0, t_contact - self.CAS_ARRIVE_LEAD_S)
            stop_on_land = self._cas_land(stop)
            top_ms = 8.0
            via_ = [stop_on_land]
            if static:
                self._drive(g, via_, top_ms)
            else:
                self._drive_road(g, via_, top_ms)
            self._time_column(g, t_arrive, top_ms)
        return g, names

    def _cas_jtac(self, package, plan, fx, fy, cx, cy, brg, v):
        """The JTAC's own Humvee beside the task force (S80: a real vehicle, visible and mortal; if it dies the flight loses its controller) -> its unit name."""
        from .mission_builder import _UN  # the builder's module imports this one
        jx, jy = self._cas_land(offset(fx, fy, brg + 90, 120))
        jt = self.m.vehicle_group(self.usa, f"Axeman {package.number}-1", _UN.Hummer, mapping.Point(jx, jy, self.t), heading=(int(brg) + 180) % 360, group_size=1)
        jt.units[0].name = f"JTAC-{package.id}"
        p0 = jt.points[0]
        p0.tasks.append(task.FAC(callsign=1, frequency=int(plan.freq("JTAC") * 1e6), modulation=task.Modulation.AM, number=1))
        # S80 (XO 2026-11-14): the JTAC is a real vehicle of the company, not magic: visible and mortal. If it dies, the flight loses its controller.
        jt.add_waypoint(mapping.Point(*self._jtac_stop((jx, jy), cx, cy, brg), self.t), PointAction.OffRoad, v * 3.6)
        return jt.units[0].name

    def _jtac_stop(self, start, cx, cy, brg):
        """Where the JTAC drives: CAS_JTAC_STOP_M from the target toward our side. S226: the point must be about where it was meant to be
        (not snapped back toward the enemy from out of the sea) and have a dry leg to it; else another bearing, else the JTAC stays put."""
        own_side = bearing(cx, cy, start[0], start[1]) - brg                  # the side the task force came in from, when its approach was swung round
        for turn in (0,) + self.CAS_LEG_BEARINGS_DEG + (own_side,):
            wanted = offset(cx, cy, brg + turn, self.CAS_JTAC_STOP_M)
            point = self._cas_land(wanted)
            if math.hypot(point[0] - wanted[0], point[1] - wanted[1]) <= self.CAS_STOP_SLIP_M and self._dry_part(start, point)[1]:
                return point
        return start

    def _front_advance(self, start, heading_deg):
        """S226: where the attacking side of a front battle creeps to: FRONT_ADVANCE_M on that heading, cut at the water; None when it cannot move."""
        wanted = offset(start[0], start[1], heading_deg, self.FRONT_ADVANCE_M)
        reached, _whole = self._dry_part(start, wanted)
        if math.hypot(reached[0] - start[0], reached[1] - start[1]) < self.CAS_SHORTEST_LEG_M:
            return None
        return reached

    def _stage_front_battles(self, package, manifest, tx, ty, route=None, t_s=900.0):
        """S81 (XO 2026-11-14): the ground war is on the map under any flight. Each sector within the target area radius of the target where both sides still have a force
        (and that is no CAS package's own battle) gets the red column, the sector's real armour asset, so a strike on it counts as always, and a blue company
        sized by the sector's Blue strength, facing each other across the line; the stronger side creeps forward, weapons free. At most FRONT_BATTLES_MAX, nearest
        first, only while the unit limit has room. The blue company is scenery for the ground war: its losses are named in the debrief but do not change the
        Blue strength (the daily fight already decides that; only a CAS battle is decided by the air power)."""
        from .mission_builder import F, SOFT  # the builder's module imports this one
        st, o = self.state, self.o
        g = getattr(st, "ground", None)
        if not g or not g.get("centers") or not ground.active(st):
            return
        R = max(5.0, float(o.target_area_radius_nm)) * NM
        cands = []
        for i in range(ground.n_zones(g)):
            if i in self._cas_zones or ground.red_strength(st, i) < ground.MIN_FORCE or ground.blue_strength(st, i) < ground.MIN_FORCE:
                continue
            a = st.assets.get(f"armor_{i + 1}")
            if a is None or a.destroyed or a.health <= ground.DOWN_HEALTH:
                continue
            cx, cy = g["centers"][i]
            d_ = min(dist(cx, cy, tx, ty), tm.poly_dist(cx, cy, route) if route and len(route) > 1 else 1e18)          # near the target or along your route
            if d_ <= R:
                cands.append((d_, i, a))
        built = 0
        # Nearest candidate first.
        def candidate_distance(candidate):
            return candidate[0]

        for d_, i, a in sorted(cands, key=candidate_distance):
            if built >= self.FRONT_BATTLES_MAX:
                break
            rs, bs = ground.red_strength(st, i), ground.blue_strength(st, i)
            sc = ground.blue_scale(st, a.id)
            comp = _scaled(self._blue_company_roll(), sc)
            need = sum(n_ for _, n_ in comp) + (0 if a.id in self.groups_by_asset else sum(n_ for _, n_ in SOFT.get(a.kind, [])) + 2)
            if self._units_room() < need:
                self.warns.append(f"Front battle at {g['names'][i]} left out to stay under the unit limit")
                continue
            fresh = a.id not in self.groups_by_asset
            if fresh:
                self._spawn_site(a, SOFT.get(a.kind), manifest, primary=False)
            red = self.groups_by_asset.get(a.id)
            if red is None or not red.units:
                continue
            rx, ry = red.units[0].position.x, red.units[0].position.y
            bx, by = ground.fwd_pos(g, i, "blue", st)
            brg_rb = bearing(rx, ry, bx, by)                         # from the red column toward our company
            bg = self._platoon(self.usa, f"Blue Company {i + 1}", comp, bx, by, (int(brg_rb) + 180) % 360, F.Rectangle)
            if bg is None:
                continue
            names = _name_units(bg, f"BC{i + 1}")
            hold_, stance_ = True, "hold"
            if rs > bs * self.FRONT_RATIO and fresh:
                advance = self._front_advance((rx, ry), brg_rb)
                if advance is not None:
                    self._drive_road(red, [advance], 3.5)
                    hold_, stance_ = False, "red"
            elif bs > rs * self.FRONT_RATIO:
                advance = self._front_advance((bx, by), brg_rb + 180)
                if advance is not None:
                    self._drive_road(bg, [advance], 3.5)
                    hold_, stance_ = False, "blue"
            if hold_:
                self._ground_orders(bg)
            manifest.add("friendly_ground", f"sector:{i}", names, label=g["names"][i], sector=i, stance=stance_,
                         base_count=_full_strength_count(names, ground.blue_strength(st, i)))      # S83: its size at full strength, so losses read back as strength
            self._spawn_front_air(i, red, bg, t_s, manifest)
            built += 1

    def _spawn_front_air(self, i, red_g, blue_g, t_s, manifest):
        """S82 (XO 2026-11-14): the day's air strikes over a battle, from real jets. The daily ground fight records each strike it sent on sector i
        (ground._record_strike): red's from a real wing (type and escort as it chose them), blue's from a real squadron with a pair serviceable. Here each one is
        spawned over the battle t_s - 240 s in, attacks the other side's company, and its losses come off that wing or squadron like any other. No strike
        recorded, none serviceable, or no room under the unit limit: nothing is spawned."""
        st = self.state
        strikes = [s_ for s_ in (st.ground or {}).get("air_today", []) if s_.get("sector") == i][:2]
        if not strikes or not red_g.units or not blue_g.units:
            return
        t0 = max(0.0, float(t_s) - 240.0)
        used = self.__dict__.setdefault("_front_air_used", {})            # jets already committed to a strike in this mission: a pair is never flown twice
        skill_r = self._red_skill()
        for s_ in strikes:
            if self._units_room() < 6:
                self.warns.append("Front air strike left out to stay under the unit limit")
                return
            if s_["side"] == "red":
                self._front_strike_red(s_, i, red_g, blue_g, t0, used, skill_r, manifest)
            else:
                self._front_strike_blue(s_, i, red_g, blue_g, t0, used, manifest)

    def _front_strike_red(self, s_, i, red_g, blue_g, t0, used, skill_r, manifest):
        """One recorded red strike over sector i: a pair from its wing behind their own column, attacking the blue company, home after the pass; then its cover, if any."""
        st, pt = self.state, self._pt
        rx, ry = red_g.units[0].position.x, red_g.units[0].position.y
        bx, by = blue_g.units[0].position.x, blue_g.units[0].position.y
        wing = st.enemy_air_at(s_["wing"])
        at_ = s_.get("type")
        if wing is None or not at_ or wing.available_of((at_,)) - used.get(("w", s_["wing"], at_), 0) < 2 or not hasattr(planes, at_):
            return
        sx, sy = offset(rx, ry, bearing(bx, by, rx, ry), 40 * NM)         # behind their own column, 40 nm out
        g = self.m.flight_group(self.red, f"Red Strike {i + 1}", getattr(planes, at_), None, pt(sx, sy), altitude=12000 * FT, speed=400 * KPH,
                                maintask=task.CAS, group_size=2)
        g.set_skill(skill_r)
        _commit(used, ("w", s_["wing"], at_))
        names = _arm_group(g, enemy_strike_loadout(at_, "troops"), f"ENM-FS-{s_['wing']}-{i}-", self._red_unit_name)          # B3: red's front-line strike goes at blue troops: the cluster-bomb kit of `loadouts.STRIKE_KITS`
        tw = g.add_waypoint(pt(bx, by), 9000 * FT, 450 * KPH)
        tw.tasks.append(task.AttackGroup(blue_g.id, group_attack=True))
        apt_r = self.t.airports.get(getattr(st.assets.get(s_["wing"]), "airport", None) or "")
        if apt_r is not None:
            g.land_at(apt_r)                                              # S84: home to its own field after the pass
        else:
            g.add_waypoint(pt(sx, sy), 12000 * FT, 450 * KPH)
        self._late(g, t0, "front strike")
        manifest.add("enemy_air", s_["wing"], names, ac=at_)
        self._front_cover_red(s_, i, red_g, blue_g, t0, used, skill_r, manifest)

    def _front_cover_red(self, s_, i, red_g, blue_g, t0, used, skill_r, manifest):
        """The recorded escort of a red strike: a pair from its own wing, if one is serviceable and there is room, on station behind the column and engaging air targets over the battle."""
        if not (s_.get("esc") and s_.get("esc_type") and hasattr(planes, s_["esc_type"]) and self._units_room() >= 4):
            return
        st, pt = self.state, self._pt
        rx, ry = red_g.units[0].position.x, red_g.units[0].position.y
        bx, by = blue_g.units[0].position.x, blue_g.units[0].position.y
        ew = st.enemy_air_at(s_["esc"])
        if ew is not None and ew.available_of((s_["esc_type"],)) - used.get(("w", s_["esc"], s_["esc_type"]), 0) >= 2:
            _commit(used, ("w", s_["esc"], s_["esc_type"]))
            eg = self.m.flight_group(self.red, f"Red Cover {i + 1}", getattr(planes, s_["esc_type"]), None, pt(*offset(rx, ry, bearing(bx, by, rx, ry), 15 * NM)),
                                     altitude=20000 * FT, speed=420 * KPH, maintask=task.CAP, group_size=2)
            eg.set_skill(skill_r)
            en_ = _arm_group(eg, enemy_cap_loadout(s_["esc_type"]), f"ENM-FC-{s_['esc']}-{i}-", self._red_unit_name)
            ew_ = eg.add_waypoint(pt(*offset(bx, by, bearing(rx, ry, bx, by) + 180, 5 * NM)), 20000 * FT, 450 * KPH)
            ew_.tasks.append(task.EngageTargetsInZone(mapping.Vector2(bx, by), int(25 * NM), [task.Targets.All.Air]))
            self._late(eg, t0, "front cover")
            manifest.add("enemy_air", s_["esc"], en_, ac=s_["esc_type"])

    def _front_strike_blue(self, s_, i, red_g, blue_g, t0, used, manifest):
        """One recorded blue strike over sector i: a pair from its squadron behind our own company, attacking the red column, home after the pass (a carrier squadron holds)."""
        st, pt = self.state, self._pt
        rx, ry = red_g.units[0].position.x, red_g.units[0].position.y
        bx, by = blue_g.units[0].position.x, blue_g.units[0].position.y
        q = st.squadrons.get(s_.get("sq"))
        spec = AIRCRAFT.get(q.aircraft) if q is not None else None
        if q is None or spec is None or q.available - used.get(("q", q.id), 0) < 2 or q.base_id not in st.bases:
            return
        _commit(used, ("q", q.id))
        sx, sy = offset(bx, by, bearing(rx, ry, bx, by), 40 * NM)         # behind our own company
        g = self.m.flight_group(self.usa, f"Front Strike {i + 1}", spec.dcs_type, None, pt(sx, sy), altitude=12000 * FT, speed=400 * KPH,
                                maintask=task.CAS, group_size=2)
        names = _arm_group(g, self.lo.for_role(q.aircraft, Role.CAS, ""), f"FS{i + 1}|")
        tw = g.add_waypoint(pt(rx, ry), 9000 * FT, 450 * KPH)
        tw.tasks.append(task.AttackGroup(red_g.id, group_attack=True))
        qb_ = st.bases[q.base_id]
        apt_b = self.apt.get(q.base_id) or (self.t.airports.get(qb_.airport) if qb_.airport else None)
        if qb_.kind == BaseKind.AIRFIELD and apt_b is not None:
            g.land_at(apt_b)                                              # S84: home to its own field after the pass (a carrier squadron holds, as before)
        else:
            g.add_waypoint(pt(sx, sy), 12000 * FT, 450 * KPH)
        self._late(g, t0, "front strike")
        manifest.add("friendly", f"front-{i}-{q.id}", names, squadron=q.id, callsign=f"Front Strike {i + 1}", player=False)


    def _cas_battle_rule(self, package, enemy, blue_names, t_contact):
        """S80: the CAS battle is decided by what the air power did to the red column, with no dice. CAS_DECIDE_S after the contact time a trigger counts the red
        column's living vehicles. Below CAS_BREAK_FRAC of them: the advance is broken, the column halts. Above it: the line is overrun, and a script blows up
        CAS_OVERRUN_MIN..CAS_OVERRUN_MAX of our task force (more when the red column is stronger), one vehicle every CAS_OVERRUN_GAP_S seconds. The debrief reads those deaths
        like any others, so the ground war loses the Blue strength (ground.blue_losses)."""
        if not blue_names or not getattr(enemy, "units", None):
            return
        rn, bn = len(enemy.units), len(blue_names)
        names = ", ".join('"%s"' % n_ for n_ in blue_names)
        lua = (
            'local RED, RN, BN = "%s", %d, %d\n'
            'local names = {%s}\n'
            'local g = Group.getByName(RED)\n'
            'local alive = 0\n'
            'if g then for _, u in ipairs(g:getUnits() or {}) do if u:isExist() and u:getLife() > 1 then alive = alive + 1 end end end\n'
            'local f = alive / RN\n'
            'if f < %.2f then\n'
            '  if g then pcall(trigger.action.groupStopMoving, RED) end\n'
            '  trigger.action.outTextForCoalition(coalition.side.BLUE, "JTAC: the enemy attack is broken. Their column has stopped.", 20)\n'
            'else\n'
            '  local n = math.ceil(#names * (%.2f + (%.2f - %.2f) * math.min(1, (f - %.2f) / (1 - %.2f))))\n'
            '  trigger.action.outTextForCoalition(coalition.side.BLUE, "JTAC: the line is giving way. We need that column stopped NOW.", 20)\n'
            '  for k = 1, math.min(n, #names) do\n'
            '    timer.scheduleFunction(function(nm) local u = Unit.getByName(nm); if u and u:isExist() then trigger.action.explosion(u:getPoint(), 200) end end, names[k], timer.getTime() + %d * k)\n'
            '  end\n'
            'end\n'
        ) % (enemy.name, rn, bn, names, self.CAS_BREAK_FRAC, self.CAS_OVERRUN_MIN, self.CAS_OVERRUN_MAX, self.CAS_OVERRUN_MIN, self.CAS_BREAK_FRAC,
             self.CAS_BREAK_FRAC, self.CAS_OVERRUN_GAP_S)
        tr = triggers.TriggerOnce(comment=f"CAS battle {package.number}")
        tr.add_condition(condition.TimeAfter(int(t_contact + self.CAS_DECIDE_S)))
        tr.add_action(action.DoScript(String(lua)))
        self.m.triggerrules.triggers.append(tr)
