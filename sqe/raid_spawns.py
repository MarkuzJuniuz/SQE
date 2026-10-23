"""Raid and reactive spawns: red bomber raids (their marshal, bend round blue defences, escorts, target) and the extra pairs that launch mid-mission (reactive dispatch).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
import copy
import math
import random

from dcs import action, condition, mapping, planes, statics, task, triggers
from dcs.translation import String
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
from .red_air_picture import A2A_ZONE_NM, CALLIN_LUA, CALLIN_LUA_DELAY_S, CALLIN_MIN_NM, CALLIN_REACH_NM, RED_LONG_RANGE
from .support_caps import SUPPORT_CAP_ZONE_NM
from .routes import AVOID_NM, FT, NM, Wpt, avoid_circles, bearing, dist, offset
from .strike_tasks import KPH

F = VehicleGroup.Formation
BLUE_CALLIN_TAGS = ("BASECAP", "CVCAP")    # v0.41.112: the blue patrols that are called in with the alert pairs (the tanker / AWACS guards stay with their asset)
BLUE_CALLIN_CV_NM = 60        # the carrier CAP answers a hotspot at most this far from its station: the boat is not left bare (judgment call)
RAID_PUSH_NM = 10             # v0.41.29: a raid's PUSH, this far from its marshal toward the target (blue's is up to 10 nm)
RAID_MSHL_MIN_NM = 60         # ...its marshal is at least this far from the target (judgment call: well outside blue's Patriot reach)
RAID_MPS = 232.0              # a red raid's speed (450 kts), the same figure its placement always used
RAID_MIN_NM = 40              # ...a raid with no time to hold starts no closer than this to its target (it is late instead)
RAID_GROUP_GAP_S = 60         # v0.41.108: the bomber groups of a big raid follow each other, this far apart (judgment call)
RAID_SWEEP_LEAD_S = 90        # ...and the raid's sweep escorts fly this far ahead of the first bomber group (judgment call)
RAID_HOLD_MAX_S = 600         # ...and one with plenty of time appears at most 10 min before it must push
RAID_EGRESS_NM = 30           # ...off target it turns 40 degrees off its way in and leaves this far before heading home     # a fighter on station engages only inside this circle round it (long-range shooters / the rest): no chasing
ARM_LAUNCH_NM = 40            # v0.41.84: a red SEAD pair fires its Kh-31P this far from the field (judgment call: inside the 60 nm the Kh-31 page gives, with margin for a low launch)
ARM_LEAD_S = 150              # ...and the bombers reach the target this long after the launch point (judgment call)
ARM_TARCAP_BEHIND_NM = 8      # v0.41.116: the SEAD package's TARCAP holds this far back along the way in from the Kh-31P launch point (blue's TARCAP_BEHIND_NM; judgment call)...
ARM_TARCAP_LEAD_S = 120       # ...in on station this long before the missiles go (blue's TARCAP_LEAD_S)...
ARM_TARCAP_STAY_S = 600       # ...and holds this long after (the missiles are flying; judgment call)
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
            if pk["size"] > self._units_room():
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
        self._blue_callins(package, raid_x, fleet_obj, tx, ty, tot_s)
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
            if 2 > self._units_room():
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

    def _raid_cap_station(self, package, geom, wps) -> None:
        """v0.41.114 (XO 2026-10-22, the Kobuleti run): a raid scramble's CAP racetrack sat on the line from the PLAYER's base to the target (37 nm west of the
        field over the sea, 32 nm off the raid's way in). It now sits where an alert pair would: up the raid's way in, as far forward as our own air defence
        still covers it and clear of red's SAM rings (scramble.blue_station). Land fields only: the carrier keeps its old geometry."""
        st = self.state
        tb = st.bases.get(package.objective.target_id)
        k1 = next((i for i, w in enumerate(wps) if w.action == "CAPORBIT"), None)
        if tb is None or tb.kind != BaseKind.AIRFIELD or k1 is None or k1 + 1 >= len(wps):
            return
        tx, ty = geom.tx, geom.ty
        (sx, sy), _why = scramble.blue_station(st, tx, ty, scramble.raid_origin(st, package, tx, ty))
        leg = max(dist(wps[k1].x, wps[k1].y, wps[k1 + 1].x, wps[k1 + 1].y), 5 * NM)
        wps[k1].x, wps[k1].y = sx, sy
        wps[k1 + 1].x, wps[k1 + 1].y = offset(sx, sy, bearing(sx, sy, tx, ty) + 90, leg)

    def _blue_callins(self, package, raid_x, fleet_obj, tx, ty, tot_s) -> None:
        """v0.41.112 (XO 2026-10-22): the BASECAP call-in, blue side. In a defensive mission (a raid on blue, or the fleet under attack) the blue
        base and carrier CAPs that can reach the hotspot (where the alert pairs would station themselves) are called to it when red comes within
        120 nm of the target (the alert pairs' own trigger), stay a while, then fly back to their station until their shift ends. Same Lua call as
        red's (red_air_picture.py): the route has a hotspot leg AFTER the home leg, a SwitchWaypoint jumps the pair onto it."""
        if not (fleet_obj or raid_x is not None):
            return
        st, o = self.state, self.o
        dpt = (tx, ty) if (fleet_obj or raid_x is None) else self._target_xy(raid_x)
        (hx, hy), _why = scramble.blue_station(st, dpt[0], dpt[1], scramble.raid_origin(st, raid_x or package, dpt[0], dpt[1]))
        calls = []
        for f, g in list(self.flight_groups):
            if f.tag not in BLUE_CALLIN_TAGS or f.is_player or len(g.points) < 3:
                continue
            c1 = next((p_ for p_ in g.points if p_.name == "CAP1"), None)
            c2 = next((p_ for p_ in g.points if p_.name == "CAP2"), None)
            ct = next((t_ for t_ in (c1.tasks if c1 is not None else []) if isinstance(t_, task.ControlledTask)), None)
            if c2 is None or ct is None:
                continue
            sx, sy = c1.position.x, c1.position.y
            reach = BLUE_CALLIN_CV_NM if f.tag == "CVCAP" else CALLIN_REACH_NM
            if not (CALLIN_MIN_NM <= dist(sx, sy, hx, hy) / NM <= reach):
                continue
            sc = ct.params.get("stopCondition", {})
            end_s = int(sc.get("time", tot_s + o.cap_minutes * 60))
            if sc.get("userFlag"):
                bf_ = int(sc["userFlag"])
            else:                                                  # a relief has no watch flag of its own: one that is never set
                self._flag_n += 1
                bf_ = self._flag_n
            base = st.bases[f.base_id]
            alt, spd = c1.alt, c1.speed * 3.6                      # pydcs keeps the speed in m/s; _arm_callin takes km/h
            n0 = len(self._hot_calls)
            self._arm_callin(g, None, (sx, sy), (hx, hy), SUPPORT_CAP_ZONE_NM, alt, spd, end_s, tot_s, bf_, {}, tx, ty,
                             cap2=(c2.position.x, c2.position.y), land=lambda g_, b_=base: self._blue_back_home(g_, b_))
            calls.append(self._hot_calls.pop())
            assert len(self._hot_calls) == n0
        if not calls:
            return
        pt = lambda x, y: mapping.Point(x, y, self.t)
        if not self._callin_lua:
            t0 = triggers.TriggerOnce(comment="define SQE_CALLIN")
            t0.add_condition(condition.TimeAfter(1))
            t0.add_action(action.DoScript(String(CALLIN_LUA)))
            self.m.triggerrules.triggers.append(t0)
            self._callin_lua = True
        t1 = triggers.TriggerOnce(comment="call in the blue patrols")
        zone = self.m.triggers.add_triggerzone(pt(*dpt), 120 * NM, True, "callin blue")
        t1.add_condition(condition.PartOfCoalitionInZone("red", zone.id))
        t1.add_condition(condition.TimeAfter(CALLIN_LUA_DELAY_S))
        for c in calls:
            t1.add_action(action.DoScript(String(self._callin_call(c))))
        self.m.triggerrules.triggers.append(t1)

    def _blue_back_home(self, g, base) -> None:
        """The second way home of a called-in blue patrol (after its shift): the field's landing, or its recovery entry point when this base type
        skips landings; the boat's deck. The recovery net of the first home leg still covers the group."""
        pt = lambda x, y: mapping.Point(x, y, self.t)
        if base.kind == BaseKind.AIRFIELD:
            if self._skip_landing(base):
                lp_ = g.points[-1].position
                rx_, ry_ = offset(base.x, base.y, bearing(base.x, base.y, lp_.x, lp_.y), 8 * NM)
                rcv = g.add_waypoint(pt(rx_, ry_), 3000 * FT, 300 * KPH, "RCV")
                rcv.tasks.append(task.RunScript(f"SQE_RECOVER('{g.name}')"))
            else:
                g.land_at(self.apt[base.id])
        else:
            rtb = g.add_waypoint(pt(base.x, base.y), 600, 300 * KPH, "RTB")
            rtb.type, rtb.action = "Land", PointAction.Landing
            rtb.link_unit = rtb.helipad = self.ship[base.id].units[0].id

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
        # v0.41.94: four jets against both batteries fly as two pairs, the first on the Patriot, the second on the HAWK; four against a lone (full) Patriot
        # fly as one group of four on it (8 Kh-31P)
        pairs = [(tg, int(ex["arm"]))]
        if int(ex["arm"]) >= 8:                                  # v0.41.116: two four-jet flights, the first on the Patriot, the second on the HAWK
            pairs = [(ad.get("pat") or tg, 4), (ad.get("hawk") or ad.get("pat") or tg, 4)]
        elif int(ex["arm"]) >= 4 and ad.get("pat") and ad.get("hawk"):
            pairs = [(ad["pat"], 2), (ad["hawk"], 2)]
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
        for gi, (tgt_, n_jets) in enumerate(pairs):
            g = self.m.flight_group(self.red, f"Raid SEAD {gi + 1}", planes.Su_24M, None, pt(sx, sy), altitude=alt + gi * 600, speed=450 * KPH, maintask=task.SEAD, group_size=n_jets)     # the second pair 600 m higher: they share a route
            if hold_until is not None:
                ct_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct_.stop_after_time(int(hold_until)); g.points[0].tasks.append(ct_)
                g.points[0].name = "MSHL"
            for k, q in enumerate(remaining):
                wp = g.add_waypoint(pt(*q), alt + gi * 600, 450 * KPH, "ARM" if k == len(remaining) - 1 else "ING")
                if k == len(remaining) - 1:
                    wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
                    ca_ = task.ControlledTask(task.AttackGroup(tgt_.id, weapon_type=task.WeaponType.ARM, group_attack=True))
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
                u.name = f"RAID-S-{gi + 1}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            if not load:
                self.warns.append("Su-24M: no Kh-31P found; the red SEAD pair is unarmed.")
            manifest.add("enemy_air", ex["bomber_wing"], names, ac="Su_24M")
        if ex.get("arm_cover") and ex.get("escort_type"):
            self._spawn_arm_cover(ex, path, pts, launch, V, t_arm, alt, skill, home_, manifest, dx, dy)

    def _spawn_arm_cover(self, ex, path, pts, launch, V, t_arm, alt, skill, home_, manifest, dx, dy) -> None:
        """v0.41.116 (XO 2026-10-22: red's SEAD package is blue's shape: the HARM flights, a TARCAP and an escort): two fighters (the escort) hold a station
        on the Kh-31P launch point, two (the TARCAP) one ARM_TARCAP_BEHIND_NM back along the way in. Both fly the SEAD flights' route, are in on station
        ARM_TARCAP_LEAD_S before the missiles go, engage air inside their class's circle, and stay until ARM_TARCAP_STAY_S after (out of AAMs: home).
        A real EscortTaskAction on the SEAD group is not used: the SEAD flights are late-activated and shift with the hold, so a plain station is steadier."""
        pt = lambda x, y: mapping.Point(x, y, self.t)
        cls = getattr(planes, ex["escort_type"])
        load = enemy_cap_loadout(ex["escort_type"])
        zone_nm = A2A_ZONE_NM[ex["escort_type"] in RED_LONG_RANGE]
        from .mission_builder import AAM_WEAPONS            # lazy: the builder's module imports this one
        bk = offset(*launch, bearing(*launch, *pts[-1]), ARM_TARCAP_BEHIND_NM * NM)           # the TARCAP station: back along the way in
        t_on = max(0.0, t_arm - ARM_TARCAP_LEAD_S)
        for job in ("Raid SEAD Escort", "Raid SEAD TARCAP"):
            pa = [q for q in pts] + [bk if job.endswith("TARCAP") else launch]
            if job.endswith("TARCAP"):
                pa = [q for q in pts if dist(*q, dx, dy) > dist(*bk, dx, dy)] + [bk] or [bk]
            Lp = sum(dist(*pa[i], *pa[i + 1]) for i in range(len(pa) - 1))
            t_go = t_on - Lp / V
            if t_go >= 0:
                (sx, sy), remaining = pa[0], pa[1:]
                hold_until, act_ = t_go, max(0.0, t_go - RAID_HOLD_MAX_S)
            else:
                (sx, sy), seg_i = tm.point_back_along(pa, min(Lp, max(ARM_LAUNCH_NM * NM * 0.5, V * t_on)))
                remaining, hold_until, act_ = pa[seg_i:], None, 0.0
            if not remaining:
                remaining = [pa[-1]]
            g = self.m.flight_group(self.red, job, cls, None, pt(sx, sy), altitude=alt + 300, speed=450 * KPH, maintask=task.CAP, group_size=2)
            if hold_until is not None:
                ct_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct_.stop_after_time(int(hold_until)); g.points[0].tasks.append(ct_)
                g.points[0].name = "MSHL"
            for k, q in enumerate(remaining):
                last = k == len(remaining) - 1
                wp = g.add_waypoint(pt(*q), alt + 300, 450 * KPH, ("TARCAP" if job.endswith("TARCAP") else "ESCORT") if last else "ING")
                if last:
                    wp.tasks.append(task.EngageTargetsInZone(mapping.Vector2(*q), int(zone_nm * NM), [task.Targets.All.Air]))
                    oc_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH)))
                    oc_.stop_after_time(int(t_arm + ARM_TARCAP_STAY_S)); wp.tasks.append(oc_)
            back_ = offset(*launch, bearing(*launch, *pts[-1]), 20 * NM)
            g.add_waypoint(pt(*back_), alt, 450 * KPH, "EGR")
            for k, q in enumerate(home_):
                g.add_waypoint(pt(*q), alt, 450 * KPH, "RTB" if k == len(home_) - 1 else "AVD")
            g.points[0].tasks.append(task.OptRTBOnBingoFuel(True))
            rtbe_ = task.OptRTBOnOutOfAmmo(); rtbe_.params["action"]["params"]["value"] = AAM_WEAPONS
            g.points[0].tasks.append(rtbe_)
            g.set_skill(skill)
            if act_ >= 30:
                self._late(g, act_)
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"RAID-{'SE' if job.endswith('Escort') else 'ST'}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", ex["escort_wing"], names, ac=ex["escort_type"])

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
        egr_ = offset(dx, dy, bearing(dx, dy, *remaining[-2] if len(remaining) > 1 else (sx, sy)) + 40, RAID_EGRESS_NM * NM)
        home_ = self._raid_bend([egr_, (ba.x, ba.y)], cvb)[1:]           # turn points round blue's Patriot fields, then its own field
        skill = getattr(Skill, ai_skill(self.o, "red", d), Skill.High)
        land = bool(ex.get("land"))
        alt = ((12000 if ex.get("raider") == "Su_25" else 20000) if land else 30000) * FT
        apt = self.t.airports.get(cvb.airport) if (land and cvb.airport and not aim) else None

        fin_ = "BASE" if bool(ex.get("land")) else "FLEET"
        back0 = 0.0 if hold_until is not None else back_
        def start_at(shift_s):
            """Where a group starts and which points it still has to fly, `shift_s` seconds later (+) or earlier (-) than the raid's lead."""
            if hold_until is not None:
                h = max(0.0, hold_until + shift_s)
                return path[0], path[1:], h, max(0.0, h - RAID_HOLD_MAX_S)
            b = min(L, max(RAID_MIN_NM * NM * 0.5, back0 + shift_s * V))
            p_, si = tm.point_back_along(path, b)
            return p_, path[si:], None, 0.0

        def build_group(name, cls, count, task_cls, bomber=False, shift=0.0, behind_nm=0.0):
            pos, rem, hold, act = start_at(shift)
            if behind_nm and rem:
                pos = offset(pos[0], pos[1], bearing(rem[0][0], rem[0][1], pos[0], pos[1]), behind_nm * NM)
            nm_ = (["PUSH"] + ["ING"] * (len(rem) - 2) + [fin_]) if hold is not None else (["ING"] * (len(rem) - 1) + [fin_])
            g = self.m.flight_group(self.red, name, cls, None, pt(*pos), altitude=alt, speed=450 * KPH, maintask=task_cls, group_size=count)
            if hold is not None:                               # its marshal: orbit until it must push
                ct_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct_.stop_after_time(int(hold)); g.points[0].tasks.append(ct_)
                g.points[0].name = "MSHL"
            for k, q in enumerate(rem):
                wp = g.add_waypoint(pt(*q), alt, 450 * KPH, nm_[k])
                if k == len(rem) - 1 and bomber:
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
            if act >= 30:
                self._late(g, act)
            return g

        def sizes(n):
            """pydcs makes one group of at most 4: a bigger raid is several groups of nearly equal size (12 -> 4+4+4, 6 -> 3+3)."""
            k = max(1, math.ceil(n / 4))
            return [n // k + (1 if i < n % k else 0) for i in range(k)]

        if land:
            cls_b, task_b = getattr(planes, ex.get("raider", "Su_24M")), (task.GroundAttack if aim else task.RunwayAttack)
            load = enemy_strike_loadout(ex.get("raider", "Su_24M"))
        else:
            cls_b, task_b = planes.Tu_22M3, task.AntishipStrike
            load = enemy_bomber_loadout("Tu_22M3")
        if not load:
            self.warns.append(f"{ex.get('raider', 'Tu-22M3')}: no bomb or missile found; the raid is unarmed.")
        bomber_gs, nb_ = [], 0
        for gi, n_ in enumerate(sizes(ex["bombers"])):         # v0.41.108: a big raid is several groups, a minute apart on the same route
            g = build_group(f"Raid Bomber {gi + 1}", cls_b, n_, task_b, bomber=True, shift=gi * RAID_GROUP_GAP_S)
            names = []
            for u in g.units:
                nb_ += 1
                u.name = f"RAID-B-{nb_}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", ex["bomber_wing"], names, ac=ex.get("raider", "Tu_22M3"), raid_base=cvb.id, raid_aim=aim, raid_label=package.objective.description.replace("Intercept a raid on ", "").replace("Intercept an air attack on ", ""),
                         raid_arrive_s=float(hit_s + gi * RAID_GROUP_GAP_S))
            bomber_gs.append(g)
        self._spawn_raid_target(package, cvb, aim, dx, dy, manifest)
        if land and ex.get("arm") and not aim:
            self._spawn_raid_arm(package, ex, cvb, path, V, t_tgt, alt, skill, home_, dx, dy, manifest)
        if ex.get("escorts"):
            # v0.41.108: the escorts of a big raid split in two jobs. Half (at least 3 groups) fly a sweep RAID_SWEEP_LEAD_S ahead of the bombers on the same
            # route and fight what they meet; the rest escort the bomber groups (spread over them). A small raid keeps its single escort group.
            esz = sizes(ex["escorts"])
            n_sweep = len(esz) // 2 if len(esz) >= 3 else 0
            eload = enemy_cap_loadout(ex["escort_type"])
            from .mission_builder import AAM_WEAPONS            # lazy: the builder's module imports this one
            esc_nm_ = A2A_ZONE_NM[ex["escort_type"] in RED_LONG_RANGE]
            ne_ = 0
            for ei, n_ in enumerate(esz):
                if ei < n_sweep:
                    eg = build_group(f"Raid Sweep {ei + 1}", getattr(planes, ex["escort_type"]), n_, task.FighterSweep, shift=-RAID_SWEEP_LEAD_S - 15 * ei)
                else:
                    ci = ei - n_sweep
                    bg = bomber_gs[ci * len(bomber_gs) // max(1, len(esz) - n_sweep)]
                    eg = build_group(f"Raid Escort {ci + 1}", getattr(planes, ex["escort_type"]), n_, task.Escort, shift=bomber_gs.index(bg) * RAID_GROUP_GAP_S, behind_nm=3)
                    # v0.41.29: the escorts stay with the bombers and fight only what comes within their class's reach of them (Su-27 25 nm, the rest
                    # 15 nm), up to the bombers' egress point; home once their air-to-air missiles are gone. No chasing.
                    eg.points[0].tasks = [t_ for t_ in eg.points[0].tasks if getattr(t_, "Id", "") != "Escort"]      # pydcs's default escort task has no group
                    eg.points[0].tasks.insert(0, task.EscortTaskAction(group_id=bg.id, engagement_max_dist=int(esc_nm_ * NM), lastwpt=len(bg.points) - 1 - len(home_),
                                                                        targets=[task.Targets.All.Air.id], position={"x": -1000, "y": 300, "z": 500}))
                rtbe_ = task.OptRTBOnOutOfAmmo(); rtbe_.params["action"]["params"]["value"] = AAM_WEAPONS
                eg.points[0].tasks.append(rtbe_)
                en = []
                for u in eg.units:
                    ne_ += 1
                    u.name = f"RAID-E-{ne_}"; u.pylons = copy.deepcopy(eload); en.append(u.name); self._note_jam(u)
                manifest.add("enemy_air", ex["escort_wing"], en, ac=ex["escort_type"])
