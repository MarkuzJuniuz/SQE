"""The red air picture of a mission: the known CAP stations of the enemy's daily air plan, the alert aircraft that scramble from enemy fields, and the geometry they use (fleet keep-out, which side of the station the CAP leg runs).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
import copy
import math

from dcs import action, condition, mapping, planes, task, triggers
from dcs.unit import Skill

from . import reactive, redair
from . import threatmap as tm
from .difficulty import ai_skill
from .loadouts import ENEMY_FIGHTERS, enemy_cap_loadout
from .models import BaseKind, ObjectiveType, Role
from .routes import FT, NM, bearing, dist, offset
from .strike_tasks import KPH

RED_LONG_RANGE = {"Su_27"}    # v0.41.29: red's long-range class (XO 2026-10-16: the Su-27 only; the MiG-31 is not in rotation)
RED_CALLIN_ZONE_NM = 25       # ...where it engages inside this circle round the site
RED_CALLIN_NM = 50            # ...and a patrol is called to the SAM site it guards when blue comes this close to that site
CAP_FLEET_KEEPOUT_NM = 78      # Red's known CAP stations stay at least this far from any carrier: the ships' SM-2 reach 70 nm (measured: CAP pairs killed 51 to 67 nm out) + 8 nm margin (v0.41.76: was 90, hand-set)
RELIEF_HORIZON_S = 3600       # v0.41.77: a patrol's relief is flown in this mission when it is due within this long after the time on target (judgment call)
ALERT_REACH_NM = 130          # alert pairs come only from fields this close to the target (the far ones could not arrive in time)
A2A_ZONE_NM = {True: 25, False: 15}


class RedAirPicture:
    def _fighter_wings(self, tx, ty):
        st = self.state
        wings = [(w, st.assets[w.base_asset_id]) for w in st.enemy_air if w.available > 0 and not st.assets[w.base_asset_id].destroyed
                 and w.fighter_types()]
        wings.sort(key=lambda p: dist(p[1].x, p[1].y, tx, ty))
        return wings

    def _plan_cap_stations(self, package, tx, ty, geom, keepout) -> list:
        """Known enemy CAP stations: the enemy's own air plan for the day (redair.py) decides which patrol pairs are up at the time on target near the
        target or the route, and where (20-25 nm in front of their own base, or over the contested sector for a sweep). The stations here are only moved
        clear of the tanker, AWACS, HAVCAP and the fleet. How many enemy fighters there are overall is still the package's threat size; patrols
        fill the first places, the rest are alert aircraft."""
        self._red_sel = []
        n_fl = package.n_def // 2
        if package.objective.type == ObjectiveType.FLEET_DEFENSE or n_fl <= 0 or not self._fighter_wings(tx, ty):
            return []
        redair.ensure(self.state, self.d)
        tot_min = self._start_min + 20                              # the time on target is not known yet; a package is over the target about 20 minutes in
        self._red_sel = redair.pick(self.state, tot_min, [geom.push, geom.ip, (tx, ty)], tx, ty, max(1, math.ceil(n_fl / 2)))
        keepout = list(keepout) + self._fleet_keepout()
        out, kept = [], []
        pts_ = [geom.push, geom.ip, (tx, ty)]
        for f in self._red_sel:
            sx, sy = f["x"], f["y"]
            for kx, ky, knm in keepout:
                if dist(sx, sy, kx, ky) < knm * NM:
                    sx, sy = offset(kx, ky, bearing(kx, ky, sx, sy), knm * NM)
            # v0.41.75: the keep-out pushes a station AWAY from our marshal point, fields and carrier (130 nm round the boat): that is what put red's patrols
            # behind the target in XO's v0.41.74 run (station 36 nm past the SA-10). A patrol that ends up behind the target is not in the fight: left out.
            if redair.beyond_nm(sx, sy, pts_, tx, ty) > redair.BEHIND_NM:
                continue
            kept.append(f)
            out.append({"x": sx, "y": sy, "side": self._cap_side(sx, sy, tx, ty)})
        self._red_sel = kept
        return out

    def _spawn_red_relief(self, pf, cp, i, manifest, skill, tot_s, tx, ty, alt, spd) -> None:
        """v0.41.77, BARCAP step 3: a patrol's RELIEF. The planned chain (barcap.chain) has the next sortie of the same area start 10 minutes before the
        one on station leaves; when that falls inside this mission, the relief pair is flown: it waits on its field like an alert pair (hidden, put on the
        runway when called) and a timed trigger calls it so it reaches the station when its window opens. The pair on station stays until its own window
        ends, so the station is never empty. Not flown when the wing has no second pair, the airfield is gone, or the unit limit is reached."""
        st = self.state
        nxt = min((f for f in (st.red_air or {}).get("flights", []) if f.get("area") and f["area"] == pf.get("area") and f["kind"] == "CAP"
                   and f["id"] != pf["id"] and pf["start"] < f["start"] <= pf["end"]), key=lambda f: f["start"], default=None)
        if nxt is None:
            return
        t_arr = (nxt["start"] - self._start_min) * 60
        if t_arr <= 60 or t_arr > tot_s + RELIEF_HORIZON_S:
            return
        w, a = st.enemy_air_at(nxt["wing"]), st.assets.get(nxt["wing"])
        if w is None or a is None or a.destroyed or w.available_of(ENEMY_FIGHTERS) < 4 or self._counts()["units"] + 2 > self.o.max_units:
            return
        ap = self.t.airports.get(a.airport) if a.airport else None
        if ap is None:
            return
        tname = nxt["type"] if nxt["type"] in w.types_up else self.vrng.choice(w.fighter_types())
        load = enemy_cap_loadout(tname)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        sx, sy = cp["x"], cp["y"]
        g, _how = self._alert_group(self.red, f"Relief {i + 1}", getattr(planes, tname), ap, task.CAP, None, 2, (sx, sy))
        t_go = int(max(30, t_arr - dist(a.x, a.y, sx, sy) / spd - 120 - 90))          # flight time + the taxi the runway start no longer does + a minute's slack
        trig = triggers.TriggerOnce(comment=f"relief {g.name}")
        trig.add_condition(condition.TimeAfter(t_go))
        trig.add_action(action.SetFlag(self._alerts[-1]["f"]))
        self.m.triggerrules.triggers.append(trig)
        ct = task.ControlledTask(task.OrbitAction(int(alt), int(spd)))
        ct.stop_after_time(int(max(t_arr + 300, (nxt["end"] - self._start_min) * 60)))
        g.add_waypoint(pt(sx, sy), alt, spd, "CAP").tasks.append(ct)
        g.add_waypoint(pt(*offset(sx, sy, bearing(sx, sy, tx, ty) + cp.get("side", 90), 20 * NM)), alt, spd, "CAP2")
        gx, gy = sx, sy
        self._limit_engage(g, 0, None, (gx, gy, min(A2A_ZONE_NM[tname in RED_LONG_RANGE], self.o.enemy_cap_engage_nm or 999)))
        names = []
        for j, u in enumerate(g.units, 1):
            u.name = f"ENM-{a.id}-R{i}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
        g.set_skill(skill)
        if self.o.enemy_unlimited_fuel:
            g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
        manifest.add("enemy_air", w.base_asset_id, names, ac=tname)
        self._red_intel.append(f"Relief for that patrol: a pair of {tname.replace('_', '-')} from {self._short(a.name)} on station {redair.hhmm(nxt['start'])}.")

    def _spawn_red_standby(self, pf, cp, i, gname, bf, wings, manifest, skill, tot_s, tx, ty, alt, spd) -> None:
        """v0.41.79: the standby of a red patrol. The hook watches the pair (a jet down, winchester or bingo: the pair leaves) and COVER_DELAY_S later calls
        the NEAREST red field that has a spare pair (XO: "nearest field replaces"): it waits hidden like an alert pair, appears on the runway when
        called and flies to the patrol's station for the rest of its window. Not built when no field within reach has four fighters, or at the unit limit
        (the pair is still watched and sent home)."""
        sx, sy = cp["x"], cp["y"]
        end_s = int(max(tot_s + 300, (pf["end"] - self._start_min) * 60))
        ent = {"g": gname, "n": 2, "bf": bf, "rf": 0, "u": float(end_s)}
        self._cover.append(ent)
        cands = sorted(((dist(a_.x, a_.y, sx, sy), w_, a_) for w_, a_ in wings if w_.available_of(ENEMY_FIGHTERS) >= 4 and a_.airport), key=lambda c_: c_[0])
        if not cands or cands[0][0] > ALERT_REACH_NM * NM or self._counts()["units"] + 2 > self.o.max_units:
            return
        _d, w, a = cands[0]
        ap = self.t.airports.get(a.airport)
        if ap is None:
            return
        tname = pf["type"] if pf["type"] in w.types_up else self.vrng.choice(w.fighter_types())
        load = enemy_cap_loadout(tname)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        g, _how = self._alert_group(self.red, f"Standby {i + 1}", getattr(planes, tname), ap, task.CAP, None, 2, (sx, sy))
        ent["rf"] = self._alerts[-1]["f"]
        ct = task.ControlledTask(task.OrbitAction(int(alt), int(spd)))
        ct.stop_after_time(end_s + 900)
        g.add_waypoint(pt(sx, sy), alt, spd, "CAP").tasks.append(ct)
        g.add_waypoint(pt(*offset(sx, sy, bearing(sx, sy, tx, ty) + cp.get("side", 90), 20 * NM)), alt, spd, "CAP2")
        self._limit_engage(g, 0, None, (sx, sy, min(A2A_ZONE_NM[tname in RED_LONG_RANGE], self.o.enemy_cap_engage_nm or 999)))
        names = []
        for j, u in enumerate(g.units, 1):
            u.name = f"ENM-{a.id}-S{i}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
        g.set_skill(skill)
        if self.o.enemy_unlimited_fuel:
            g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
        manifest.add("enemy_air", w.base_asset_id, names, ac=tname)

    def _fleet_keepout(self) -> list:
        """Every carrier in the campaign, whichever package uses it: the escorts' SM-2s reach well past 50 nm, so Red's known CAP stays out of it."""
        return [(b.x, b.y, CAP_FLEET_KEEPOUT_NM) for b in self.state.bases.values() if b.kind == BaseKind.CARRIER]

    def _cap_side(self, sx, sy, tx, ty) -> int:
        """Which way the CAP racetrack leg runs from its station (+90 or -90 off the line to the target): the way that stays further from the fleet."""
        cvs = [(b.x, b.y) for b in self.state.bases.values() if b.kind == BaseKind.CARRIER]
        if not cvs:
            return 90
        h = bearing(sx, sy, tx, ty)
        far = lambda sd: min(dist(*offset(sx, sy, h + sd, 20 * NM), cx, cy) for cx, cy in cvs)
        return 90 if far(90) >= far(-90) else -90

    def _spawn_air_picture(self, package, tx, ty, tot_s, geom, manifest, keepout):
        """Known CAP flights are airborne from t=0 on briefed stations. The rest of the defenders are alert aircraft sitting on real
        enemy airfields; they take off (scramble) when the package is detected inside the field's detection zone."""
        if package.objective.type == ObjectiveType.FLEET_DEFENSE:
            return self._spawn_raid(package, tx, ty, tot_s, geom, manifest)
        st, d, r = self.state, self.d, self.vrng
        n_fl = package.n_def // 2
        if n_fl <= 0:
            return
        wings = self._fighter_wings(tx, ty)
        if not wings:
            return
        skill = getattr(Skill, ai_skill(self.o, "red", d), Skill.High)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        n_cap = len(self._cap_plan)                         # the planned patrol pairs that are up (redair.py); the rest of the defenders are alert aircraft
        alt, spd = 22000 * FT, 400 * KPH
        # v0.41.20: no needless banzai for red. Blue air-to-air jets in this fight (escorts, sweeps, support CAP) against red's doctrine (redair.commits)
        blue_aa = sum(f.count for f in package.flights if f.role in (Role.TARCAP, Role.ESCORT, Role.SWEEP, Role.CAP))
        tga_ = st.assets.get(package.objective.target_id) if package.objective.target_id else None
        from .war import covering_sams
        own_ = (tm.cluster_ids(tga_) | {x_.id for x_ in covering_sams(st, tga_)}) if tga_ is not None else set()   # the sites blue comes for: defended at any odds
        self._red_held = []
        for i in range(n_fl):
            if i < n_cap:
                pf_ = self._red_sel[i]
                w, a = st.enemy_air_at(pf_["wing"]), st.assets[pf_["wing"]]
                tname = pf_["type"] if pf_["type"] in w.types_up else r.choice(w.fighter_types())
                if pf_["kind"] == "SWEEP" and dist(pf_["x"], pf_["y"], tx, ty) <= 60 * NM and not redair.commits(d, [tname] * 2, blue_aa):
                    self._red_held.append({"id": pf_["id"], "why": "sweep"})      # outgunned: this sweep stays home today
                    continue
            else:
                near_ = [wa for wa in wings if dist(wa[1].x, wa[1].y, tx, ty) <= ALERT_REACH_NM * NM]   # v0.41.1: only fields that can reach the fight
                if not near_:
                    continue
                w, a = near_[i % len(near_)]
                tname = r.choice(w.fighter_types())
            cls = getattr(planes, tname)
            load = enemy_cap_loadout(tname)
            dd = dist(a.x, a.y, tx, ty)
            if i < n_cap:                                   # known CAP, on station from the start
                cp = self._cap_plan[i]
                sx, sy = cp["x"], cp["y"]
                for kx, ky, knm in keepout:                 # tanker / AWACS / HAVCAP stay well clear as well
                    if dist(sx, sy, kx, ky) < knm * NM:
                        sx, sy = offset(kx, ky, bearing(kx, ky, sx, sy), knm * NM)
                gx, gy, galt = self._sep(sx, sy, alt, bearing(sx, sy, tx, ty))
                g = self.m.flight_group(self.red, f"Bandit {i + 1}", cls, None, pt(gx, gy), altitude=galt, speed=spd, maintask=task.CAP, group_size=2)
                ct = task.ControlledTask(task.OrbitAction(int(alt), int(spd)))
                ct.stop_after_time(int(max(tot_s + 300, (pf_["end"] - self._start_min) * 60)))       # on station until its planned window ends
                self._flag_n += 1; bf_ = self._flag_n
                ct.stop_if_user_flag(bf_, True)                                                       # v0.41.79: the hook sends a pair home that lost a jet / is winchester / bingo
                g.add_waypoint(pt(sx, sy), alt, spd, "CAP").tasks.append(ct)
                bd_ = bearing(tx, ty, sx, sy)
                self._red_intel.append(f"Reported enemy {'fighter sweep' if pf_['kind'] == 'SWEEP' else 'patrol'}: a pair of {tname.replace('_', '-')} from "
                                       f"{self._short(a.name)}, {dist(sx, sy, tx, ty) / NM:.0f} nm {reactive.compass(bd_)} of the target, {redair.hhmm(pf_['start'])}-{redair.hhmm(pf_['end'])}.")
                g.add_waypoint(pt(*offset(sx, sy, bearing(sx, sy, tx, ty) + cp.get("side", 90), 20 * NM)), alt, spd, "CAP2")
                # the same rule as ours: a patrol engages inside a circle round its station, it does not chase a target home
                self._limit_engage(g, 0, None, (gx, gy, min(A2A_ZONE_NM[tname in RED_LONG_RANGE], self.o.enemy_cap_engage_nm or 999)))   # v0.41.29: by class (Su-27 25 nm, the rest 15)
                callin_ = pf_.get("gx") is not None and pf_["kind"] == "CAP"
                if callin_ and pf_.get("guard") not in own_:
                    mates_ = [q_["type"] for q_ in self._red_sel[:n_cap] if q_.get("guard") == pf_.get("guard") and q_["kind"] == "CAP"]
                    if not redair.commits(d, [t_ for t_ in mates_ for _ in (0, 1)], blue_aa):
                        callin_ = False                                     # outgunned and its site is not the target: it holds its station
                        self._red_held.append({"id": pf_["id"], "why": "callin"})
                if callin_:
                    # v0.41.10: called in. When blue comes within RED_CALLIN_NM of the SAM site this pair guards, it is sent to fight over the site
                    g.add_trigger_action(task.EngageTargetsInZone(mapping.Vector2(pf_["gx"], pf_["gy"]), int(RED_CALLIN_ZONE_NM * NM), [task.Targets.All.Air]))
                    zc_ = self.m.triggers.add_triggerzone(pt(pf_["gx"], pf_["gy"]), RED_CALLIN_NM * NM, True, f"callin {g.name}")
                    tc_ = triggers.TriggerOnce(comment=f"call in {g.name} to {pf_.get('guard')}")
                    tc_.add_condition(condition.PartOfCoalitionInZone("blue", zc_.id))
                    tc_.add_action(action.AITaskPush(g.id, 1))
                    self.m.triggerrules.triggers.append(tc_)
                    self._callins.append({"g": g.name, "site": pf_.get("guard")})
            else:                                           # alert: on the runway, scrambles when detected
                ap = self.t.airports.get(a.airport) if a.airport else None
                if ap is None:
                    continue
                g, how_ = self._alert_group(self.red, f"Alert {i + 1}", cls, ap, task.CAP, None, 2, (tx, ty))
                if how_ == "ramp":
                    g.add_trigger_action(task.StartCommand())
                    g.uncontrolled = True
                trig = triggers.TriggerOnce(comment=f"scramble {g.name}")
                if package.flights and any(fl.role == Role.CAS for fl in package.flights):
                    # friendly ground troops sit on the target, so a zone there would fire at once: scramble on a clock instead
                    t_go = max(5, int(tot_s - 120 - 90 - dd / (430 * 0.514444)))
                    trig.add_condition(condition.TimeAfter(t_go))
                else:
                    zx_, zy_, zr_ = self._field_zone(a, tx, ty)
                    zone = self.m.triggers.add_triggerzone(pt(zx_, zy_), zr_ * NM, True, f"detect {a.id}")
                    trig.add_condition(condition.PartOfCoalitionInZone("blue", zone.id))
                trig.add_action(action.SetFlag(self._alerts[-1]["f"]) if how_ == "rwy" else action.AITaskPush(g.id, 1))
                if how_ == "ramp":
                    trig.add_action(action.SetFlag(self._alerts[-1]["f"]))
                self.m.triggerrules.triggers.append(trig)
                ct = task.ControlledTask(task.OrbitAction(int(alt), int(spd)))
                ct.stop_after_time(int(tot_s + 3600))
                g.add_waypoint(pt(tx, ty), alt, spd, "INTERCEPT").tasks.append(ct)
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"ENM-{a.id}-{i}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            g.set_skill(skill)
            if self.o.enemy_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
            if not load:
                self.warns.append(f"{tname}: no air-to-air loadout found; spawned unarmed")
            manifest.add("enemy_air", w.base_asset_id, names, ac=tname)
            if i < n_cap and pf_["kind"] == "CAP":
                self._spawn_red_relief(pf_, self._cap_plan[i], i, manifest, skill, tot_s, tx, ty, alt, spd)
                self._spawn_red_standby(pf_, self._cap_plan[i], i, g.name, bf_, wings, manifest, skill, tot_s, tx, ty, alt, spd)
