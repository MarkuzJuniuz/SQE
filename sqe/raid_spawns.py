"""Raid and reactive spawns: red bomber raids (their marshal, bend round blue defences, escorts, target) and the extra pairs that launch mid-mission (reactive dispatch).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
import copy
import random

from dcs import action, condition, mapping, planes, statics, task, triggers
from dcs.mission import StartType
from dcs.point import PointAction
from dcs.unit import Skill
from dcs.unitgroup import VehicleGroup

from . import callsigns, reactive, scramble
from . import threatmap as tm
from .difficulty import ai_skill
from .aircraft import AIRCRAFT
from .loadouts import ENEMY_FIGHTERS, enemy_arm_loadout, enemy_bomber_loadout, enemy_cap_loadout, enemy_strike_loadout
from .models import AssetKind, BaseKind, ObjectiveType, Role
from .red_air_picture import A2A_ZONE_NM, RED_LONG_RANGE
from .routes import AVOID_NM, FT, NM, Wpt, avoid_circles, bearing, dist, offset
from .strike_tasks import KPH

F = VehicleGroup.Formation
RAID_PUSH_NM = 10             # v0.41.29: a raid's PUSH, this far from its marshal toward the target (blue's is up to 10 nm)
RAID_MSHL_MIN_NM = 60         # ...its marshal is at least this far from the target (judgment call: well outside blue's Patriot reach)
RAID_MPS = 232.0              # a red raid's speed (450 kts), the same figure its placement always used
RAID_MIN_NM = 40              # ...a raid with no time to hold starts no closer than this to its target (it is late instead)
RAID_HOLD_MAX_S = 600         # ...and one with plenty of time appears at most 10 min before it must push
RAID_EGRESS_NM = 30           # ...off target it turns 40 degrees off its way in and leaves this far before heading home     # a fighter on station engages only inside this circle round it (long-range shooters / the rest): no chasing
ARM_LAUNCH_NM = 40            # v0.41.84: a red SEAD pair fires its Kh-31P this far from the field (judgment call: inside the 60 nm the Kh-31 page gives, with margin for a low launch)
ARM_LEAD_S = 150              # ...and the bombers reach the target this long after the launch point (judgment call)
ARM_WINDOW_S = 240            # ...the ARM task runs this long (the missile's flight)
FLEET_RAID_AVOID_NM = 70      # v0.41.31: a red raid's route keeps this far from the carrier group (measured in XO's runs: the cruiser's SM-2s


class RaidSpawns:
    def _raid_marshal(self, ba, w1, station, dx, dy):
        """v0.41.29: where a red raid marshals: on its way in (field -> w1 -> station), inside the cover of a live red SAM site and at least
        RAID_MSHL_MIN_NM from its target; the one deepest on red's side. None found: just off its own field, toward the target. The mirror of
        blue marshalling behind its own field in friendly, defended airspace."""
        def proj(px, py, a, b):                               # the point on a-b nearest to (px, py)
            vx, vy = b[0] - a[0], b[1] - a[1]
            L2 = vx * vx + vy * vy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / L2))
            return a[0] + t * vx, a[1] + t * vy
        legs = [((ba.x, ba.y), w1), (w1, station)]
        best = None
        for s_ in self.state.assets.values():
            if s_.kind != AssetKind.SAM or s_.variant not in AVOID_NM or s_.destroyed or s_.health <= 0.25:
                continue
            for a, b in legs:
                q = proj(s_.x, s_.y, a, b)
                cover = AVOID_NM[s_.variant] - 2
                if dist(q[0], q[1], s_.x, s_.y) <= cover * NM and dist(q[0], q[1], dx, dy) >= RAID_MSHL_MIN_NM * NM:
                    if best is None or dist(q[0], q[1], dx, dy) > dist(best[0], best[1], dx, dy):
                        best = q
        if best is not None:
            return best
        h_ = bearing(ba.x, ba.y, *w1)
        return offset(ba.x, ba.y, h_, min(10 * NM, 0.3 * dist(ba.x, ba.y, *w1)))

    def _raid_bend(self, pts, raided):
        """v0.41.29: a red raid's legs bend round blue's Patriot fields (raids.PATRIOT_NM; the field it raids is the one it goes for, so not that
        one), and (v0.41.31) round the carrier group (FLEET_RAID_AVOID_NM). Only fields whose defences are standing (defense >= 0.15, the rule _place_base builds by). -> the points with turn points added."""
        from .raids import PATRIOT_NM
        circles = [(b.x, b.y, PATRIOT_NM) for b in self.state.bases.values()
                   if b.kind == BaseKind.AIRFIELD and b.id != raided.id and b.defense >= 0.15]
        # v0.41.31: and round the carrier group (its escorts' SM-2s), unless the fleet is what it is raiding
        circles += [(b.x, b.y, FLEET_RAID_AVOID_NM) for b in self.state.bases.values() if b.kind == BaseKind.CARRIER and b.id != raided.id]
        if not circles or len(pts) < 2:
            return list(pts)
        wps = [Wpt("P", x, y, 20000, 450) for x, y in pts]
        for _ in range(4):                  # a leg straight through a big circle needs more than one turn point (two passes per call)
            n0 = len(wps)
            avoid_circles(wps, circles, 24, 1)
            if len(wps) == n0:
                break
        return [(w.x, w.y) for w in wps]

    def _raid_cap(self, package, f) -> bool:
        """v0.41.28: an AI fighter of a raid intercept (FLEET_DEFENSE, not a support CAP): TARCAP rules for its route and engage circle."""
        return (package.objective.type == ObjectiveType.FLEET_DEFENSE and f.role == Role.CAP and not f.tag
                and (not f.is_player or self.o.player_is_ai) and package.objective.target_id in self.state.bases)

    def _spawn_reactive(self, package, extras, tx, ty, tot_s, geom, manifest, despawn) -> None:
        o, st, d = self.o, self.state, self.d
        if not o.reactive:
            return
        rr = random.Random(self.seed_code + ":react")
        fight = {Role.CAP, Role.TARCAP, Role.ESCORT, Role.SWEEP}
        pkgs = [package] + list(extras)
        blue_f = sum(f.count for pk in pkgs for f in pk.flights if f.role in fight and not f.tag)
        used = {}
        for g in manifest.groups:
            if g["kind"] == "enemy_air":
                used[g["ref"]] = used.get(g["ref"], 0) + len(g["units"])
        base_n = sum(used.values())
        fleet_obj = package.objective.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE)
        picks = reactive.plan_red(st, d, rr, tx, ty, base_n, blue_f, used, ENEMY_FIGHTERS, bearing) if not fleet_obj else []
        skill = getattr(Skill, ai_skill(self.o, "red", d), Skill.High)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        alt, spd = 22000 * FT, 400 * KPH
        placed_red, seen_src = 0, set()
        for k, pk in enumerate(picks, 1):
            if self._counts()["units"] + pk["size"] > o.max_units:
                self.warns.append("enemy reinforcements left out to stay under the unit limit")
                break
            a = st.assets[pk["base"]]
            ap = self.t.airports.get(a.airport) if a.airport else None
            if ap is None:
                continue
            cls = getattr(planes, pk["type"])
            load = enemy_cap_loadout(pk["type"])
            g, how_ = self._alert_group(self.red, f"Reinforce {k}", cls, ap, task.CAP, None, pk["size"], (tx, ty))
            if how_ == "ramp":
                g.add_trigger_action(task.StartCommand())
                g.uncontrolled = True
            trig = triggers.TriggerOnce(comment=f"reinforce {g.name}")
            delay = int(rr.uniform(60, 240))
            if any(fl.role == Role.CAS for fl in package.flights):
                trig.add_condition(condition.TimeAfter(max(5, int(tot_s - 120 - 90 - pk["nm"] * NM / (430 * 0.514444))) + delay))
            else:
                zx_, zy_, zr_ = self._field_zone(a, tx, ty)
                zone = self.m.triggers.add_triggerzone(pt(zx_, zy_), zr_ * NM, True, f"reinforce {a.id} {k}")
                trig.add_condition(condition.PartOfCoalitionInZone("blue", zone.id))
                trig.add_condition(condition.TimeAfter(delay))
            trig.add_action(action.SetFlag(self._alerts[-1]["f"]) if how_ == "rwy" else action.AITaskPush(g.id, 1))
            if how_ == "ramp":
                trig.add_action(action.SetFlag(self._alerts[-1]["f"]))
            self.m.triggerrules.triggers.append(trig)
            ct = task.ControlledTask(task.OrbitAction(int(alt), int(spd)))
            ct.stop_after_time(int(tot_s + 3600))
            (ix_, iy_), _why = scramble.red_station(st, (a.x, a.y), tx, ty)              # v0.41.91: a defensive station, then home
            g.add_waypoint(pt(ix_, iy_), alt, spd, "INTERCEPT").tasks.append(ct)
            self._land_home(g, ap)
            self._limit_engage(g, o.enemy_cap_engage_nm)
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"ENM-{a.id}-R{k}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            g.set_skill(skill)
            if o.enemy_unlimited_fuel:
                g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
            manifest.add("enemy_air", a.id, names, ac=pk["type"])
            placed_red += pk["size"]
            if a.id not in seen_src:
                seen_src.add(a.id)
                self._intel.append(f"Enemy fighters at {self._short(a.name)} ({reactive.compass(pk['brg'])} of the target) are within reach of the target area and may be sent to reinforce.")

        # ---- blue alert pairs ---------------------------------------------------------------------------------------------------
        raid_x = next((x for x in extras if x.objective.type == ObjectiveType.FLEET_DEFENSE), None)
        n_pairs = reactive.blue_pairs(rr, base_n + placed_red, blue_f, fleet_obj, raid_x is not None)
        if not n_pairs:
            return
        dpt = (tx, ty) if (fleet_obj or raid_x is None) else self._target_xy(raid_x)
        committed = {}
        for f_, _g in self.flight_groups:
            committed[f_.squadron_id] = committed.get(f_.squadron_id, 0) + f_.count
        srcs = reactive.blue_sources(st, AIRCRAFT, fight, committed, *dpt)
        taken = {(g_.name) for g_ in getattr(self.usa, "plane_group", [])}
        for k in range(n_pairs):
            if not srcs:
                break
            sq, base, nm, free = srcs[0]
            if self._counts()["units"] + 2 > o.max_units:
                self.warns.append("blue alert aircraft left out to stay under the unit limit")
                break
            if base.kind == BaseKind.CARRIER:
                carrier = self.ship.get(base.id)
                if carrier is None:
                    srcs = srcs[1:]
                    continue
            elif base.id not in self.apt:
                self._place_base(base, tx, ty)
            spec = AIRCRAFT[sq.aircraft]
            fno = next((n for n in range(9, 0, -1) if f"{sq.callsign} {n}" not in taken), None)
            if fno is None:
                break
            label = f"{sq.callsign} {fno}"
            taken.add(label)
            if base.kind == BaseKind.CARRIER:            # hidden until called, then on the catapult (the same queue as a runway)
                g = self.m.flight_group_from_unit(self.usa, label, spec.dcs_type, self.ship[base.id], maintask=task.CAP, start_type=StartType.Runway, group_size=2)
                g.late_activation = True
                how_ = "rwy"
                self._note_alert(label, base.name, spec.dcs_type)
                self._rwyq.append({"g": label, "f": self._flag_n, "b": f"carrier:{base.id}"})
            else:
                g, how_ = self._alert_group(self.usa, label, spec.dcs_type, self.apt[base.id], task.CAP, None, 2, dpt)
            if how_ == "ramp":
                g.add_trigger_action(task.StartCommand())
                g.uncontrolled = True
            trig = triggers.TriggerOnce(comment=f"alert {label}")
            if fleet_obj or raid_x is not None:
                zone = self.m.triggers.add_triggerzone(pt(*dpt), 120 * NM, True, f"alert {label}")
                trig.add_condition(condition.PartOfCoalitionInZone("red", zone.id))
            else:
                trig.add_condition(condition.TimeAfter(max(5, int(tot_s - 240 - nm * NM / (420 * 0.514444)))))
            trig.add_action(action.SetFlag(self._alerts[-1]["f"]) if how_ == "rwy" else action.AITaskPush(g.id, 1))
            if how_ == "ramp":
                trig.add_action(action.SetFlag(self._alerts[-1]["f"]))
            self.m.triggerrules.triggers.append(trig)
            p_ = spec.profile
            ct = task.ControlledTask(task.OrbitAction(int(p_.cap_alt_ft * FT), int(p_.cap_kts * KPH)))
            ct.stop_after_time(int(tot_s + o.cap_minutes * 60))
            sx_, sy_ = scramble.blue_station(st, dpt[0], dpt[1], scramble.raid_origin(st, raid_x or package, dpt[0], dpt[1]))[0]    # v0.41.91: forward, under our own cover
            g.add_waypoint(pt(sx_, sy_), p_.cap_alt_ft * FT, p_.cap_kts * KPH, "CAP").tasks.append(ct)
            self._limit_engage(g, o.friendly_cap_engage_nm, (tot_s + (o.fighter_engage_minutes + 5) * 60) if o.fighter_engage_minutes > 0 else None)
            if base.kind == BaseKind.AIRFIELD:
                g.land_at(self.apt[base.id])
            else:
                rtb = g.add_waypoint(pt(base.x, base.y), 600, 300 * KPH, "RTB")
                rtb.type, rtb.action = "Land", PointAction.Landing
                rtb.link_unit = rtb.helipad = self.ship[base.id].units[0].id
            cs = callsigns.apply(g, sq.callsign, fno, callsigns.table(sq.aircraft))
            load = self.lo.for_role(sq.aircraft, Role.CAP)
            names = []
            for i, u in enumerate(g.units):
                u.name = cs[i]; u.pylons = copy.deepcopy(load); names.append(u.name); self._ulabels[u.name] = u.name.upper(); self._note_jam(u)
            g.set_skill(getattr(Skill, ai_skill(self.o, "blue", self.d), Skill.High))
            g.set_frequency(130.0)
            manifest.add("friendly", f"alert_{sq.id}_{fno}", names, squadron=sq.id, callsign=label, player=False)
            if self.o.ai_despawn_on_land:
                despawn.extend(names)
            committed[sq.id] = committed.get(sq.id, 0) + 2
            srcs = reactive.blue_sources(st, AIRCRAFT, fight, committed, *dpt)
            self._intel.append(f"Alert fighters of {sq.name} ({self._short(base.name)}) are on cockpit alert and may launch to help.")

    # ---- what the raiders are going for: the friendly garrison, supply site or troops they will bomb ---------------------------
    def _spawn_raid_target(self, package, base, aim, dx, dy, manifest):
        """Put the thing under attack on the map: a field's garrison, a fuel farm / depot, or a column of friendly troops. They are what the
        raiders bomb, so the intercepting player sees what is at stake. Small groups (a handful of vehicles or statics)."""
        from . import raids, ground
        st, d, r = self.state, self.d, self.vrng
        kind = raids.aim_kind(aim)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        if kind == "supply":
            a = st.blue_assets[aim]
            hdg = r.randint(0, 359)
            if a.kind == AssetKind.DEPOT:
                parts = [statics.Warehouse.Warehouse, statics.Warehouse._Ammunition_depot, statics.Warehouse.Warehouse]
            else:
                parts = [statics.Warehouse.Tank, statics.Warehouse.Tank_2, statics.Warehouse.Tank_3, statics.Warehouse.Warehouse]
            names = []
            for k, vt in enumerate(parts):
                x, y = offset(a.x, a.y, k * (360 / len(parts)) + hdg, 40 + 12 * k)
                nm = f"{aim}|{k + 1}"
                self.m.static_group(self.usa, nm, vt, pt(x, y), heading=hdg)
                names.append(nm)
            manifest.add("blue_site", aim, names, label=a.name)
            return
        if kind == "sector":
            i = int(aim.split(":")[1])
            sc = max(0.5, min(1.5, ground.blue_strength(st, i) / 50.0))
            comp = [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(1, 2)), ("M1043_HMMWV_Armament", 1), ("M1097_Avenger", 1)]
            scale, label, head = sc, st.ground["names"][i], r.randint(0, 359)
        else:
            gar = st.blue_assets.get(aim if kind == "garrison" else f"bgar_{base.id}")
            if gar is None or gar.destroyed:
                return
            comp = [("M_1_Abrams", r.randint(1, 2)), ("M_2_Bradley", r.randint(1, 2)), ("Vulcan", 1), ("M1097_Avenger", 1), ("M_818", 1)]
            scale, label, head = d.blue_garrison_size * max(0.5, gar.health), gar.name, r.randint(0, 359)
            aim = gar.id
            dx, dy = gar.x, gar.y
        g = self._platoon(self.usa, f"Friendly {label}", comp, dx, dy, head, F.Star if kind != "sector" else F.Line, scale=scale)
        if g is None:
            return
        self._ground_orders(g)                          # v0.41.39
        names = []
        for k, u in enumerate(g.units, 1):
            u.name = f"{aim}|{k}"; names.append(u.name)
        manifest.add("blue_site", aim, names, label=label)

    def _spawn_raid_arm(self, package, ex, cvb, path, V, t_tgt, alt, skill, home_, dx, dy, manifest):
        """v0.41.84: a Kh-31P SEAD pair flies the raid's way in, fires at the field's Patriot (else HAWK) from ARM_LAUNCH_NM, then turns away.
        It reaches the launch point ARM_LEAD_S ahead of the bombers' TOT."""
        ad = self.base_ad.get(cvb.id) or {}
        tg = ad.get("pat") or ad.get("hawk")
        if tg is None:
            return
        pt = lambda x, y: mapping.Point(x, y, self.t)
        tgt = (dx, dy)
        pts = list(path[:-1])
        while len(pts) > 1 and dist(*pts[-1], *tgt) <= (ARM_LAUNCH_NM + 10) * NM:
            pts.pop()
        launch = offset(dx, dy, bearing(dx, dy, *pts[-1]), ARM_LAUNCH_NM * NM)
        pa = pts + [launch]
        L = sum(dist(*pa[i], *pa[i + 1]) for i in range(len(pa) - 1))
        t_arm = t_tgt - ARM_LEAD_S
        t_leave = t_arm - L / V
        hold_until, act_ = None, 0.0
        if t_leave >= 0:
            (sx, sy), remaining = pa[0], pa[1:]
            hold_until, act_ = t_leave, max(0.0, t_leave - RAID_HOLD_MAX_S)
        else:
            (sx, sy), seg_i = tm.point_back_along(pa, min(L, max((ARM_LAUNCH_NM + 10) * NM, V * t_arm)))
            remaining = pa[seg_i:]
        alt = alt
        g = self.m.flight_group(self.red, "Raid SEAD 1", planes.Su_24M, None, pt(sx, sy), altitude=alt, speed=450 * KPH, maintask=task.SEAD, group_size=ex["arm"])
        if hold_until is not None:
            ct_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
            ct_.stop_after_time(int(hold_until)); g.points[0].tasks.append(ct_)
            g.points[0].name = "MSHL"
        for k, q in enumerate(remaining):
            wp = g.add_waypoint(pt(*q), alt, 450 * KPH, "ARM" if k == len(remaining) - 1 else "ING")
            if k == len(remaining) - 1:
                wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
                ca_ = task.ControlledTask(task.AttackGroup(tg.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                ca_.stop_after_time(int(t_arm) + ARM_WINDOW_S); wp.tasks.append(ca_)
        back_ = offset(*launch, bearing(*launch, *pts[-1]), 20 * NM)          # off the launch point away from the field, then home
        g.add_waypoint(pt(*back_), alt, 450 * KPH, "EGR")
        for k, q in enumerate(home_):
            g.add_waypoint(pt(*q), alt, 450 * KPH, "RTB" if k == len(home_) - 1 else "AVD")
        g.points[0].tasks.append(task.OptRTBOnBingoFuel(True))
        g.set_skill(skill)
        if act_ >= 30:
            self._late(g, act_)
        load = enemy_arm_loadout("Su_24M")
        names = []
        for j, u in enumerate(g.units, 1):
            u.name = f"RAID-S-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
        if not load:
            self.warns.append("Su-24M: no Kh-31P found; the red SEAD pair is unarmed.")
        manifest.add("enemy_air", ex["bomber_wing"], names, ac="Su_24M")

    # ---- bomber raid on the fleet: already en route from the first second, along a real path from their base ----------------
    def _spawn_raid(self, package, sx_, sy_, tot_s, geom, manifest):
        st, d, r = self.state, self.d, self.vrng
        ex = package.extra
        if not ex:
            return
        cvb = st.bases[package.objective.target_id]
        aim = ex.get("aim", "") or ""
        dx, dy = (ex.get("dest") or (cvb.x, cvb.y))              # where the raiders are going: the field, a supply site, a garrison or a sector
        cvg = self.ship.get(cvb.id)
        ba = st.assets[ex["bomber_wing"]]
        pt = lambda x, y: mapping.Point(x, y, self.t)
        station = (sx_, sy_)
        w1 = offset(dx, dy, ex["brg"], min(220 * NM, 0.9 * dist(ba.x, ba.y, dx, dy)))
        V = RAID_MPS
        arrive = tot_s + r.uniform(60, 150)                    # at the station: 1-2.5 min after our scramble's TOT
        t_tgt = arrive + dist(sx_, sy_, dx, dy) / V            # the raid's own TOT
        # v0.41.29: the raid flies blue's shape. Marshal on red's side (in a red SAM's cover along its way in, else just off its field), PUSH,
        # ingress bent round blue's Patriot fields (not the one it is raiding), the target at its TOT, then egress and home.
        mshl = self._raid_marshal(ba, w1, station, dx, dy)
        lane = [mshl, offset(*mshl, bearing(*mshl, *(w1 if dist(*mshl, *w1) > 15 * NM else station)), RAID_PUSH_NM * NM)]
        if dist(*mshl, dx, dy) > dist(*w1, dx, dy) + 15 * NM:
            lane.append(w1)
        lane = self._raid_bend(lane, cvb) + [station]
        path = lane + [(dx, dy)]
        L = sum(dist(*path[i], *path[i + 1]) for i in range(len(path) - 1))
        t_leave = t_tgt - L / V
        hold_until, act_ = None, 0.0
        if t_leave >= 0:                                       # it holds at its marshal until it must push, appearing at most RAID_HOLD_MAX_S before
            (sx, sy), remaining = path[0], path[1:]
            hold_until, act_ = t_leave, max(0.0, t_leave - RAID_HOLD_MAX_S)
            hit_s = t_tgt
        else:                                                  # no time to hold: already on its way in, but never closer than RAID_MIN_NM (then it is late)
            back_ = min(L, max(RAID_MIN_NM * NM, V * t_tgt))
            (sx, sy), seg_i = tm.point_back_along(path, back_)
            remaining = path[seg_i:]
            hit_s = back_ / V
        names_ = ["PUSH"] + ["ING"] * (len(remaining) - 2) + ["BASE" if bool(ex.get("land")) else "FLEET"] if hold_until is not None else \
                 ["ING"] * (len(remaining) - 1) + ["BASE" if bool(ex.get("land")) else "FLEET"]
        egr_ = offset(dx, dy, bearing(dx, dy, *remaining[-2] if len(remaining) > 1 else (sx, sy)) + 40, RAID_EGRESS_NM * NM)
        home_ = self._raid_bend([egr_, (ba.x, ba.y)], cvb)[1:]           # turn points round blue's Patriot fields, then its own field
        skill = getattr(Skill, ai_skill(self.o, "red", d), Skill.High)
        land = bool(ex.get("land"))
        alt = ((12000 if ex.get("raider") == "Su_25" else 20000) if land else 30000) * FT
        apt = self.t.airports.get(cvb.airport) if (land and cvb.airport and not aim) else None

        def build_group(name, cls, count, task_cls, pos, bomber=False):
            g = self.m.flight_group(self.red, name, cls, None, pt(*pos), altitude=alt, speed=450 * KPH, maintask=task_cls, group_size=count)
            if hold_until is not None:                         # its marshal: orbit until it must push
                ct_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct_.stop_after_time(int(hold_until)); g.points[0].tasks.append(ct_)
                g.points[0].name = "MSHL"
            for k, q in enumerate(remaining):
                wp = g.add_waypoint(pt(*q), alt, 450 * KPH, names_[k])
                if k == len(remaining) - 1 and bomber:
                    if land and apt is not None:
                        wp.tasks.append(task.BombingRunway(airport_id=apt.id))
                    elif land and aim:
                        wp.tasks.append(task.Bombing(mapping.Vector2(dx, dy)))
                    elif cvg is not None and cls is planes.Tu_22M3:
                        wp.tasks.append(task.AttackGroup(cvg.id))
            g.add_waypoint(pt(*egr_), alt, 450 * KPH, "EGR")
            for k, q in enumerate(home_):
                g.add_waypoint(pt(*q), alt, 450 * KPH, "RTB" if k == len(home_) - 1 else "AVD")
            g.points[0].tasks.append(task.OptRTBOnBingoFuel(True))
            g.set_skill(skill)
            if act_ >= 30:
                self._late(g, act_)
            return g

        if land:
            g = build_group("Raid Bomber 1", getattr(planes, ex.get("raider", "Su_24M")), ex["bombers"], task.GroundAttack if aim else task.RunwayAttack, (sx, sy), bomber=True)
            load = enemy_strike_loadout(ex.get("raider", "Su_24M"))
        else:
            g = build_group("Raid Bomber 1", planes.Tu_22M3, ex["bombers"], task.AntishipStrike, (sx, sy), bomber=True)
            load = enemy_bomber_loadout("Tu_22M3")
        names = []
        for j, u in enumerate(g.units, 1):
            u.name = f"RAID-B-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
        if not load:
            self.warns.append(f"{ex.get('raider', 'Tu-22M3')}: no bomb or missile found; the raid is unarmed.")
        manifest.add("enemy_air", ex["bomber_wing"], names, ac=ex.get("raider", "Tu_22M3"), raid_base=cvb.id, raid_aim=aim, raid_label=package.objective.description.replace("Intercept a raid on ", "").replace("Intercept an air attack on ", ""),
                     raid_arrive_s=float(hit_s))
        self._spawn_raid_target(package, cvb, aim, dx, dy, manifest)
        if land and ex.get("arm") and not aim:
            self._spawn_raid_arm(package, ex, cvb, path, V, t_tgt, alt, skill, home_, dx, dy, manifest)
        if ex.get("escorts"):
            back = offset(sx, sy, bearing(remaining[0][0], remaining[0][1], sx, sy), 3 * NM)
            eg = build_group("Raid Escort 1", getattr(planes, ex["escort_type"]), ex["escorts"], task.Escort, back)
            # v0.41.29: the escorts stay with the bombers and fight only what comes within their class's reach of them (Su-27 25 nm, the rest
            # 15 nm), up to the bombers' egress point; home once their air-to-air missiles are gone. No chasing.
            esc_nm_ = A2A_ZONE_NM[ex["escort_type"] in RED_LONG_RANGE]
            eg.points[0].tasks = [t_ for t_ in eg.points[0].tasks if getattr(t_, "Id", "") != "Escort"]      # pydcs's default escort task has no group
            eg.points[0].tasks.insert(0, task.EscortTaskAction(group_id=g.id, engagement_max_dist=int(esc_nm_ * NM), lastwpt=len(g.points) - 1 - len(home_),
                                                                targets=[task.Targets.All.Air.id], position={"x": -1000, "y": 300, "z": 500}))
            from .mission_builder import AAM_WEAPONS            # lazy: the builder's module imports this one
            rtbe_ = task.OptRTBOnOutOfAmmo(); rtbe_.params["action"]["params"]["value"] = AAM_WEAPONS
            eg.points[0].tasks.append(rtbe_)
            eload = enemy_cap_loadout(ex["escort_type"])
            en = []
            for j, u in enumerate(eg.units, 1):
                u.name = f"RAID-E-{j}"; u.pylons = copy.deepcopy(eload); en.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", ex["escort_wing"], en, ac=ex["escort_type"])
