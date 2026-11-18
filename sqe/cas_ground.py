"""CAS ground fight: the support force, the front battles on the map, the front air cover and the helpers that drive a column (road points, patrol legs, land snapping).

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
from dcs.unit import Skill

from . import ground
from . import seacheck as seac
from . import threatmap as tm
from .aircraft import AIRCRAFT
from .difficulty import ai_skill
from .loadouts import enemy_cap_loadout, enemy_strike_loadout
from .models import BaseKind, Role
from .routes import FT, NM, bearing, dist, offset
from .strike_tasks import KPH


class CasGround:
    # ---- CAS: both columns drive into contact so the clash is under way at the CAS TOT (+/- 30 s) -------------------------
    def _translate(self, g, dx, dy):
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
        for q in via:
            g.add_waypoint(mapping.Point(q[0], q[1], self.t), PointAction.OffRoad, speed_ms * 3.6)
        self._ground_orders(g)

    def _road_pt(self, x, y):
        """v0.41.180: the nearest road point within CAS_ROAD_SNAP_M, else None (no road scan, or no road that close)."""
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

    def _patrol_via(self, start, away_brg, final, speed_ms, t_arrive):
        """v0.41.190: the route points for a column that must take about t_arrive seconds to get from `start` to `final` at speed_ms: out `away_brg` and back
        (half the extra distance each way, at most CAS_PATROL_MAX_M), then on to `final`. Just [final] when no leg is needed."""
        direct = math.hypot(final[0] - start[0], final[1] - start[1])
        leg = (speed_ms * t_arrive - direct) / 2.0
        if leg < self.CAS_PATROL_MIN_M:
            return [final]
        return [offset(start[0], start[1], away_brg, min(leg, self.CAS_PATROL_MAX_M)), start, final]

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

    def _leg_on_land(self, a, b, step_m=250.0):
        """v0.41.384: True when the straight leg a -> b stays on land (sampled every step_m)."""
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        n = max(1, int(d // step_m))
        return all(seac.is_land(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1))

    def _spawn_cas_support(self, package, plan, geom, manifest):
        from .mission_builder import F, _UN  # the builder's module imports this one
        if not package.jtac:
            return
        r = self.vrng
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
        tot = float(self.cas_tot or 1500.0)
        t_contact = max(300.0, tot - 15.0)                        # guns are firing as the CAS flight arrives
        dist_run = min(8.0 * t_contact + 1500.0, self.CAS_APPROACH_M)      # the friendly force starts this far from the contact point
        v = max(2.5, min(8.0, (dist_run - self.CAS_TF_STOP_M) / t_contact))   # m/s, a believable advance
        enemy = self.groups_by_asset.get(tid) if tid else None
        static = bool(tid) and self.state.assets[tid].variant == "GARRISON"      # dug in: our troops come to it
        if enemy is not None and not static:
            # v0.41.137: the column stays where the CAS flight is sent. It used to start up to 10 km back and drive 13 km to be at the CAS point
            # at the TOT; any shortfall in DCS's real speed (slopes, a long mixed column, stopping to fight) left it kilometres from the point
            t_arr_ = max(0.0, t_contact - self.CAS_ARRIVE_LEAD_S)
            self._drive_road(enemy, [self._cas_land(q_) for q_ in self._patrol_via((cx, cy), brg + 180, offset(cx, cy, brg, self.CAS_ENEMY_ADVANCE_M), min(v, 3.5), t_arr_)], min(v, 3.5))   # v0.41.190: a patrol leg away from us first; v0.41.384: every point on land
        stop_ = [self._cas_land(offset(cx, cy, brg, 2000 if static else self.CAS_TF_STOP_M))]      # v0.41.384 (S29): on land
        bj_ = r.uniform(-6, 6)
        fx, fy = offset(cx, cy, brg + bj_, dist_run)
        if not static:
            rp_ = self._road_pt(fx, fy)                           # v0.41.180: the task force starts on a road too, and meets the column along it
            if rp_ is not None:
                fx, fy = rp_
        fx, fy = self._cas_land((fx, fy))                         # v0.41.384 (S29, XO 2026-11-11 run: a garrison near the coast put the column afloat)
        if static and not self._leg_on_land((fx, fy), stop_[0]):
            # v0.41.384: the straight off-road leg to the stop crosses water: try other start bearings, keep the first whose leg is dry (else the snapped start)
            for da_ in (10, -10, 20, -20, 30, -30, 45, -45, 60, -60):
                c_ = self._cas_land(offset(cx, cy, brg + bj_ + da_, dist_run))
                if self._leg_on_land(c_, stop_[0]):
                    fx, fy = c_
                    break
        comp = [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(2, 3)), ("M1043_HMMWV_Armament", r.randint(1, 2))]
        sc = ground.blue_scale(self.state, tid or "")          # the friendly force is as strong as Blue is in this sector
        comp = [(n_, max(1, int(round(c_ * sc)))) for n_, c_ in comp]
        gname_, utag_ = (f"Blue Company {z_ + 1}", f"BC{z_ + 1}") if first_ else (f"Friendly Task Force {package.number}", f"TF{package.number}")
        g = self._platoon(self.usa, gname_, comp, fx, fy, (int(brg) + 180) % 360, F.Rectangle)
        names = []
        if g is not None:
            self._tf_names[str(package.number)] = gname_
            for k, u in enumerate(g.units, 1):
                u.name = f"{utag_}|{k}"; names.append(u.name)
            # v0.41.157 (XO's 15:38 run: the task force reached the column 12 minutes after the A-10s, then drove 2.5 km past it): it stops CAS_TF_STOP_M (v0.41.179: 1.5 km, was 400 m) short of the
            # contact point (static garrison: 2 km short) and holds, weapons free, so the survivors come to it; and it drives CAS_TF_SPEED_MARGIN faster than the
            # plan, because DCS runs a mixed off-road column about 30% slower (measured in that run)
            v_tf_ = min(8.0, v * self.CAS_TF_SPEED_MARGIN)
            via_ = [self._cas_land(q_) for q_ in self._patrol_via((fx, fy), brg, stop_[0], v_tf_, max(0.0, t_contact - self.CAS_ARRIVE_LEAD_S))]   # v0.41.190: our column also drives a patrol leg (away from the enemy) first; v0.41.384: on land
            if static:
                self._drive(g, via_, v_tf_)
            else:
                self._drive_road(g, via_, v_tf_)
        jx, jy = self._cas_land(offset(fx, fy, brg + 90, 120))
        jt = self.m.vehicle_group(self.usa, f"Axeman {package.number}-1", _UN.Hummer, mapping.Point(jx, jy, self.t), heading=(int(brg) + 180) % 360, group_size=1)
        jt.units[0].name = f"JTAC-{package.id}"
        p0 = jt.points[0]
        p0.tasks.append(task.FAC(callsign=1, frequency=int(plan.freq("JTAC") * 1e6), modulation=task.Modulation.AM, number=1))
        # S80 (XO 2026-11-14): the JTAC is a real vehicle of the company, not magic: visible and mortal. If it dies, the flight loses its controller.
        jt.add_waypoint(mapping.Point(*self._cas_land(offset(cx, cy, brg, 3800)), self.t), PointAction.OffRoad, v * 3.6)
        names.append(jt.units[0].name)
        if names:
            bs_ = ground.blue_strength(self.state, z_) if z_ is not None else 0.0
            manifest.add("friendly_ground", tid or "", names, sector=z_,
                         base_count=max(len(names), round(len(names) / max(0.05, bs_ / ground.MAX_FORCE))) if z_ is not None else len(names))      # S84: its size at full strength, so the CAS battle's losses read back as strength by the same rule as a front battle's
        if g is not None and enemy is not None:
            self._cas_battle_rule(package, enemy, [n_ for n_ in names if n_.startswith(("TF", "BC"))], t_contact)
            zc_ = ground.zone_of(self.state, tid or "")
            if zc_ is not None:
                self._spawn_front_air(zc_, enemy, g, t_contact, manifest)

    def _stage_front_battles(self, package, manifest, tx, ty, route=None, t_s=900.0):
        """S81 (XO 2026-11-14): the ground war is on the map under any flight. Each sector within the merge radius of the target where both sides still have a force
        (and that is no CAS package's own battle) gets the red column, the sector's real armour asset, so a strike on it counts as always, and a blue company
        sized by the sector's Blue strength, facing each other across the line; the stronger side creeps forward, weapons free. At most FRONT_BATTLES_MAX, nearest
        first, only while the unit limit has room. The blue company is scenery for the ground war: its losses are named in the debrief but do not change the
        Blue strength (the daily fight already decides that; only a CAS battle is decided by the air power)."""
        from .mission_builder import F, SOFT  # the builder's module imports this one
        st, o = self.state, self.o
        g = getattr(st, "ground", None)
        if not g or not g.get("centers") or not ground.active(st):
            return
        R = max(5.0, float(o.merge_radius_nm)) * NM
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
        for d_, i, a in sorted(cands, key=lambda c_: c_[0]):
            if built >= self.FRONT_BATTLES_MAX:
                break
            r = self.vrng
            rs, bs = ground.red_strength(st, i), ground.blue_strength(st, i)
            sc = ground.blue_scale(st, a.id)
            comp = [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(2, 3)), ("M1043_HMMWV_Armament", r.randint(1, 2))]
            need = sum(max(1, int(round(n_ * sc))) for _, n_ in comp) + (0 if a.id in self.groups_by_asset else sum(n_ for _, n_ in SOFT.get(a.kind, [])) + 2)
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
            comp = [(n_, max(1, int(round(c_ * sc)))) for n_, c_ in comp]
            bg = self._platoon(self.usa, f"Blue Company {i + 1}", comp, bx, by, (int(brg_rb) + 180) % 360, F.Rectangle)
            if bg is None:
                continue
            names = []
            for k, u in enumerate(bg.units, 1):
                u.name = f"BC{i + 1}|{k}"; names.append(u.name)
            hold_, stance_ = True, "hold"
            if rs > bs * self.FRONT_RATIO and fresh:
                self._drive_road(red, [offset(rx, ry, brg_rb, self.FRONT_ADVANCE_M)], 3.5); hold_, stance_ = False, "red"
            elif bs > rs * self.FRONT_RATIO:
                self._drive_road(bg, [offset(bx, by, brg_rb + 180, self.FRONT_ADVANCE_M)], 3.5); hold_, stance_ = False, "blue"
            if hold_:
                self._ground_orders(bg)
            manifest.add("friendly_ground", f"sector:{i}", names, label=g["names"][i], sector=i, stance=stance_,
                         base_count=max(len(names), round(len(names) / max(0.05, ground.blue_strength(st, i) / ground.MAX_FORCE))))      # S83: its size at full strength, so losses read back as strength
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
        pt = self._pt
        rx, ry = red_g.units[0].position.x, red_g.units[0].position.y
        bx, by = blue_g.units[0].position.x, blue_g.units[0].position.y
        t0 = max(0.0, float(t_s) - 240.0)
        used = self.__dict__.setdefault("_front_air_used", {})            # jets already committed to a strike in this mission: a pair is never flown twice
        skill_r = getattr(Skill, ai_skill(self.o, "red", self.d), Skill.High)
        for s_ in strikes:
            if self._units_room() < 6:
                self.warns.append("Front air strike left out to stay under the unit limit")
                return
            if s_["side"] == "red":
                wing = st.enemy_air_at(s_["wing"])
                at_ = s_.get("type")
                if wing is None or not at_ or wing.available_of((at_,)) - used.get(("w", s_["wing"], at_), 0) < 2 or not hasattr(planes, at_):
                    continue
                sx, sy = offset(rx, ry, bearing(bx, by, rx, ry), 40 * NM)         # behind their own column, 40 nm out
                g = self.m.flight_group(self.red, f"Red Strike {i + 1}", getattr(planes, at_), None, pt(sx, sy), altitude=12000 * FT, speed=400 * KPH,
                                        maintask=task.CAS, group_size=2)
                g.set_skill(skill_r)
                used[("w", s_["wing"], at_)] = used.get(("w", s_["wing"], at_), 0) + 2
                load = enemy_strike_loadout(at_)
                names = []
                for j, u in enumerate(g.units, 1):
                    u.name = f"ENM-FS-{s_['wing']}-{i}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name)
                tw = g.add_waypoint(pt(bx, by), 9000 * FT, 450 * KPH)
                tw.tasks.append(task.AttackGroup(blue_g.id, group_attack=True))
                apt_r = self.t.airports.get(getattr(st.assets.get(s_["wing"]), "airport", None) or "")
                if apt_r is not None:
                    g.land_at(apt_r)                                              # S84: home to its own field after the pass
                else:
                    g.add_waypoint(pt(sx, sy), 12000 * FT, 450 * KPH)
                self._late(g, t0, "front strike")
                manifest.add("enemy_air", s_["wing"], names, ac=at_)
                if s_.get("esc") and s_.get("esc_type") and hasattr(planes, s_["esc_type"]) and self._units_room() >= 4:
                    ew = st.enemy_air_at(s_["esc"])
                    if ew is not None and ew.available_of((s_["esc_type"],)) - used.get(("w", s_["esc"], s_["esc_type"]), 0) >= 2:
                        used[("w", s_["esc"], s_["esc_type"])] = used.get(("w", s_["esc"], s_["esc_type"]), 0) + 2
                        eg = self.m.flight_group(self.red, f"Red Cover {i + 1}", getattr(planes, s_["esc_type"]), None, pt(*offset(rx, ry, bearing(bx, by, rx, ry), 15 * NM)),
                                                 altitude=20000 * FT, speed=420 * KPH, maintask=task.CAP, group_size=2)
                        eg.set_skill(skill_r)
                        eload, en_ = enemy_cap_loadout(s_["esc_type"]), []
                        for j, u in enumerate(eg.units, 1):
                            u.name = f"ENM-FC-{s_['esc']}-{i}-{j}"; u.pylons = copy.deepcopy(eload); en_.append(u.name)
                        ew_ = eg.add_waypoint(pt(*offset(bx, by, bearing(rx, ry, bx, by) + 180, 5 * NM)), 20000 * FT, 450 * KPH)
                        ew_.tasks.append(task.EngageTargetsInZone(mapping.Vector2(bx, by), int(25 * NM), [task.Targets.All.Air]))
                        self._late(eg, t0, "front cover")
                        manifest.add("enemy_air", s_["esc"], en_, ac=s_["esc_type"])
            else:
                q = st.squadrons.get(s_.get("sq"))
                spec = AIRCRAFT.get(q.aircraft) if q is not None else None
                if q is None or spec is None or q.available - used.get(("q", q.id), 0) < 2 or q.base_id not in st.bases:
                    continue
                used[("q", q.id)] = used.get(("q", q.id), 0) + 2
                sx, sy = offset(bx, by, bearing(rx, ry, bx, by), 40 * NM)         # behind our own company
                g = self.m.flight_group(self.usa, f"Front Strike {i + 1}", spec.dcs_type, None, pt(sx, sy), altitude=12000 * FT, speed=400 * KPH,
                                        maintask=task.CAS, group_size=2)
                load = self.lo.for_role(q.aircraft, Role.CAS, "")
                names = []
                for j, u in enumerate(g.units, 1):
                    u.name = f"FS{i + 1}|{j}"; u.pylons = copy.deepcopy(load); names.append(u.name)
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
