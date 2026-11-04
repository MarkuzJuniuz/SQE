"""Raid and reactive spawns: red bomber raids (their marshal, bend round blue defences, escorts, target) and the extra pairs that launch mid-mission (reactive dispatch).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o` and the other fields the builder sets up.
"""
from __future__ import annotations
import copy
import math
import random
import zlib

from dcs import action, condition, mapping, planes, statics, task, triggers
from dcs.translation import String
from dcs.mission import StartType
from dcs.point import PointAction
from dcs.unit import Skill
from dcs.unitgroup import VehicleGroup

from . import callsigns, reactive, scramble
from . import seacheck as seac
from . import threatmap as tm
from .difficulty import ai_skill
from .aircraft import AIRCRAFT
from .loadouts import ENEMY_FIGHTERS, enemy_arm_loadout, enemy_bomber_loadout, enemy_cap_loadout, enemy_dead_loadout, enemy_strike_loadout
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
RAID_ROUTE_SAMS = 5            # v0.41.256: red SAM sites along a fleet raid's way in that are built in the mission (judgment call: the default is 2; the unit limit still binds)
RAID_SWEEP_LEAD_S = 90        # ...and the raid's sweep escorts fly this far ahead of the first bomber group (judgment call)
RAID_HOLD_MAX_S = 600         # ...and one with plenty of time appears at most 10 min before it must push
RAID_EGRESS_NM = 30           # ...off target it turns 40 degrees off its way in and leaves this far before heading home     # a fighter on station engages only inside this circle round it (long-range shooters / the rest): no chasing
ARM_LAUNCH_NM = 40            # v0.41.84: a red SEAD pair fires its Kh-31P this far from the field (judgment call: inside the 60 nm the Kh-31 page gives, with margin for a low launch)
ARM_LEAD_S = 150              # ...and the bombers reach the target this long after the launch point: the Kh-31P needs about 90 s for 40 nm (from memory, about Mach 3, unchecked) and the bombers arrive about 60 s after impact (XO 2026-11-03: they ride the wave of missiles). Judgment call
ARM_TARCAP_BEHIND_NM = 8      # v0.41.116: the SEAD package's TARCAP holds this far back along the way in from the Kh-31P launch point (blue's TARCAP_BEHIND_NM; judgment call)...
ARM_TARCAP_LEAD_S = 120       # ...in on station this long before the missiles go (blue's TARCAP_LEAD_S)...
ARM_TARCAP_STAY_S = 600       # ...and holds this long after (the missiles are flying; judgment call)
DEAD_HOLD_NM = 48             # v0.41.117: the red DEAD flights hold this far out (8 nm outside the Patriot's 40 nm reach, raids.PATRIOT_NM) until the battery's radars are down (judgment call)
DEAD_GATE_CLEAR_NM = 8        # v0.41.128: the gate sits at least this far outside every live battery's reach (the same 8 nm as the field's own)
DEAD_HOLD_MAX_NM = 110        # ...but no farther out than this from the field (judgment call)
DEAD_HOLD_LAG_S = 60          # ...they reach the hold this long after the Kh-31P launch...
DEAD_GATE_WAIT_S = 1200       # ...and if the radars are not all dead this long after the launch (20 min, judgment call; blue's DEAD hold is 12 min, debrief.HOLD_S), they abort and go home
DEAD_ATTACK_WINDOW_S = 600    # ...the attack task runs this long once they go in
COVER_FIELDS_MAX = 4          # v0.41.220 (XO 2026-10-31): a raid scramble also builds the defences of the fields whose Patriot / HAWK cover the raid's target, nearest first, at most this many (units: a full field is about 30; judgment call)
RAID_SUPPLY_UNITS = 16        # ...and the supply sites round a raid's target are built before the raiders and the alert pairs, at most this many units (v0.41.221: a site's buildings count like wrecks, so that is a dozen sites or more; judgment call: the raid's own load had used the whole 250 before the late supply call)
COVER_AAA_NM = 5              # ...and a covering neighbour's AAA only when the target is this close to it (AAA reaches a few km, not 25 to 40 nm; judgment call)
GATE_ALT_STEP_M = 250          # v0.41.126: each group holding at the raid gate orbits this much higher than the one before (no two share a level)
GOTO_LUA_DELAY_S = 5          # the abort trigger waits for the Lua that defines SQE_GOTO (TimeAfter 1), like the call-in
GOTO_LUA = (
    "SQE_RGATE = SQE_RGATE or {}\n"
    "function SQE_GOTO(n, from, to)\n"
    "  local g = Group.getByName(n)\n"
    "  if g and g:getSize() > 0 then\n"
    "    pcall(function() g:getController():setCommand({id='SwitchWaypoint', params={fromWaypointIndex=from, goToWaypointIndex=to}}) end)\n"
    "    SQE_RGATE[n] = SQE_RGATE[n] or {}\n"
    "    SQE_RGATE[n].abort = math.floor(timer.getTime())\n"
    "    env.info('SQEGOTO ' .. n .. ' aborted at ' .. math.floor(timer.getTime()))\n"
    "  end\n"
    "end\n"
    "function SQE_GATE_OPEN(...)\n"
    "  for _, n in ipairs({...}) do\n"
    "    SQE_RGATE[n] = SQE_RGATE[n] or {}\n"
    "    SQE_RGATE[n].open = math.floor(timer.getTime())\n"
    "  end\n"
    "end\n"
)
RAID_LAUNCH_OUT_NM = 20       # v0.41.248 (XO 2026-11-03: the Tu-22M3s flew through the fighters to the carrier): a fleet raid LAUNCHES its anti-ship missiles from a point this far beyond
                              # the blue CAP station (on the raid's bearing), turns home at once and never goes nearer. Judgment call: the Kh-22's published range is up to 600 km (320 nm)
                              # for the M/MA variants (Wikipedia, Kh-22, medium firmness; no Tu-22M3-specific figure), so the launch ring is a game choice, set by where the fighters stand.
RAID_LAUNCH_MIN_NM = 100      # ...and never closer to the carrier than this (judgment call: outside FLEET_RAID_AVOID_NM 70, the cruiser's SM-2 reach measured in XO's runs, plus margin)
RAID_LAUNCH_WINDOW_S = 120    # ...the attack task runs this long after the bombers reach the launch point, then they go home even if a missile is left (judgment call; the time a full salvo takes is NOT measured: 8 JSOWs took 106 s in XO's Hornet run)

# v0.41.261 (XO 2026-11-03, the fleet-defence run: 24 Tu-22M3 fired their X-22s from 380 km, 87 s into the mission, and sank the carrier and all three escorts): a fleet raid ASSEMBLES
# before it comes in. Half of it is already airborne on its marshal; the rest take off from the bombers' field in batches and join; the whole raid pushes together; its marshal is
# outside the missiles' reach, and the "engage ships" order starts at the PUSH, not at the first waypoint (so nothing fires while it assembles). The weapons keep their full range.
# All the numbers are judgment calls (no measured takeoff times for the Tu-22M3 in XO's runs); tune in DCS. Doctrine support: CIMSEC, "Kamikazes: The Legacy of Soviet Naval Aviation,
# Pt. 2" (medium firmness, one article): a regiment's takeoff took about half an hour, then a cruise formation, the split about 500 km from the task force, and a salvo had to land
# within 1 min (best) or 2 min (satisfactory).
RAID_STAGE_ON = True          # False = the old raid (airborne at its marshal from the start, no runway takeoffs; the engage order still starts at the PUSH)
RAID_MARSHAL_FRAC = 0.5       # (no longer used by the fleet raid, see RAID_BOMBERS_UP) share of the groups already airborne on the marshal at the start
RAID_BOMBERS_UP = 1           # v0.41.274 (XO 2026-11-04: intelligence has spotted the movement): this many bomber groups (a pair each) are airborne on the marshal at the start...
RAID_GUARD_UP = 1             # ...with this many escort groups (up to 4 jets) guarding them; every other group takes off, the bombers first and the rest of the escorts last
RAID_MEET_LEAD_S = 120        # v0.41.280 (XO 2026-11-04: blue got over Mozdok while the bombers were still taking off and shot the raid on the ramp): the interceptors are timed to be on the intercept point this long before the bombers' planned arrival there (their push + the flight from the marshal). Judgment call
RAID_RAMP_START = True        # v0.41.277 (XO 2026-11-04: "if we stagger them during taxiing DCS will do fine"): the groups that take off start hot on the ramp and taxi out (a timed start), instead of appearing on the runway. False = the old runway start. A group the ramp has no parking for falls back to the runway
RAID_TAXI_S = 480             # ...the allowance for the taxi in the plan (v0.40.10 measured 3 to 11 min from the call to the air for alert pairs); judgment call, tune in DCS
RAID_WAIT_ALL = True          # XO 2026-11-04: no push until everybody is up: a staged group holds at the marshal until its planned time has passed AND every group that took off is at the marshal
RAID_ASM_ZONE_NM = 20         # ...at the marshal = inside this circle round it
RAID_ASM_MAX_S = 1800         # ...a safety net, not a rule: the hold ends this long after its planned time whether or not everybody is up (the Tu-22M3 burns about 0.6% fuel a minute in the cruise, more in the orbit; judgment call)
RAID_BOMBER_BATCH = 2         # bombers per runway batch (XO: 2 at a time for the big ones)
RAID_FIGHTER_BATCH = 4        # fighters per runway batch (XO: 4 at a time)
RAID_BOMBER_GAP_S = 120       # runway time one bomber batch takes before the next may go (not measured; the hook's alert stagger is 60 s)
RAID_FIGHTER_GAP_S = 60       # ... one fighter batch
RAID_FIRST_TAKEOFF_S = 30     # the first batch takes off this long after the mission starts
RAID_JOIN_S = 60              # the raid pushes this long after the last batch reaches the marshal
RAID_CLIMB_S = 180            # allowance for the climb from the runway to the marshal
RAID_STAGED_GAP_S = 15        # a staged raid's groups push this far apart (the salvo spread; the old raid used RAID_GROUP_GAP_S 60 s)
RAID_MSHL_STEP_M = 150        # each group orbits the marshal this much lower than the one before (no two share a level)
RAID_REACH_NM = 208           # how far the Tu-22M3's X-22 shoots as DCS flies it: 380 to 385 km (208 nm) in XO's 2026-11-03 run (measured)
RAID_MSHL_CLEAR_NM = 12       # the marshal stays this far outside that

# v0.41.265 (XO 2026-11-04, the fleet-defence run: the Tomcats' dash went to the point they already held, and the Hornets and Eagles never moved up): the interceptors' dash point
# (TGT) is on the BOMBERS' own way in, between their marshal and the missiles' ring, as far out as red's SAM circles and the fighters' own range allow, so the raid passes through the
# fighters' engage circle before it fires. All judgment calls (no source for a fighter dash distance; the concept is the Cold War carrier "outer air battle": fighters stationed up
# the threat axis, cued by AEW; real distances not looked up yet): tune in DCS.
RAID_SA11_NM = 26             # v0.41.276: the interceptors keep this far from a live SA-11 (AVOID_NM says 20). Judgment call: in XO's 2026-11-04 run the SA-11s engaged the Tomcats at 23 to 26 nm (shots of 42 to 49 km measured by the hook)
RAID_IP_MAX_NM = 185          # the longest dash from the hold point to the intercept point (v0.41.267: was 160, but the bombers' way in starts 160-165 nm out at Level 3: no point was ever in range; judgment call, tune in DCS)
RAID_BEND_MAX_NM = 280        # v0.41.268 (XO 2026-11-04): the longest dash by way of a blue field (hold -> field -> intercept point); judgment call from fuel at high and fast, tune in DCS
RAID_IP_STEP_NM = 5           # candidate points along the bombers' way in, this far apart
RAID_IP_LEG_NM = 10           # the orbit leg at the intercept point, across the bombers' line
RAID_IP_LANE_PTS = 12         # waypoint budget for the bends of the dash lane round SAM circles
RAID_BLOCK_MAX = 2            # v0.41.267 (XO 2026-11-04, PR 2): the most SAM sites the raid SEAD goes for (one 4-ship each; the setpiece lists two SEAD flights): the ones that stop the interceptors' lane
ARM_WINDOW_S = 240            # ...the ARM task runs this long (the missile's flight)
FLEET_RAID_AVOID_NM = 70      # v0.41.31: a red raid's route keeps this far from the carrier group (measured in XO's runs: the cruiser's SM-2s


SUPPLY_BUILDINGS = {      # v0.41.192: what a supply site looks like on the map, for both sides (fuel: tanks and a store; depot: warehouses and ammo bunkers)
    AssetKind.DEPOT: [statics.Warehouse.Warehouse, statics.Warehouse._Ammunition_depot, statics.Warehouse.Warehouse, statics.Warehouse._Ammunition_depot],
    AssetKind.FUEL: [statics.Warehouse.Tank, statics.Warehouse.Tank_2, statics.Warehouse.Tank_3, statics.Warehouse.Warehouse],
}
SUPPLY_PLANTS = {         # v0.41.241 (queue item i): the big sites of the road net look different. Keyed by the asset's variant; a refinery is a FUEL site, a factory a DEPOT one.
    "REFINERY": [statics.Fortification.Chemical_tank_A, statics.Fortification.Fuel_tank, statics.Warehouse.Tank, statics.Warehouse.Tank_2, statics.Fortification.Boiler_house_A],
    "FACTORY": [statics.Fortification.Workshop_A, statics.Fortification.Tech_combine, statics.Fortification.Hangar_A, statics.Fortification.Repair_workshop, statics.Warehouse.Warehouse],
}


ROAD_OFF_M = 100.0            # v0.41.259: the centre of a supply site's block of buildings is this far to one side of the road (judgment call: no public figure; tanks need access and firebreaks; the road heading is rough, see road_front.heading_at)
ROAD_BLOCK_M = 40.0           # ... and the buildings stand within this radius of that centre, so the nearest is about 60 m off the road


def supply_parts(kind, variant: str = "") -> list:
    """The static buildings of a supply site: the plant's own set for a refinery / factory, else the kind's (fuel farm / depot)."""
    return SUPPLY_PLANTS.get(variant) or SUPPLY_BUILDINGS.get(kind) or []


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

    def _raid_marshal_out(self, mshl, ba, w1, dx, dy):
        """v0.41.261: a staged fleet raid's marshal stays outside the missiles' reach (RAID_REACH_NM + RAID_MSHL_CLEAR_NM from the target): the marshal found by
        `_raid_marshal` when it is far enough, else the point on the way from the field to `w1` that is, nearest to w1; the field itself when even that is inside."""
        need = (RAID_REACH_NM + RAID_MSHL_CLEAR_NM) * NM
        if dist(mshl[0], mshl[1], dx, dy) >= need:
            return mshl
        best = None
        for k in range(0, 101):
            q = (ba.x + (w1[0] - ba.x) * k / 100.0, ba.y + (w1[1] - ba.y) * k / 100.0)
            if dist(q[0], q[1], dx, dy) >= need:
                best = q
        return best if best is not None else (ba.x, ba.y)

    @staticmethod
    def _ring_dist(path, dx, dy, ring_m):
        """The distance along `path` to the first point within ring_m of (dx, dy); 0 when it starts inside, the whole length when it never gets in."""
        run = 0.0
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            L = dist(a[0], a[1], b[0], b[1])
            n = max(1, int(L // 1000))
            for k in range(n + 1):
                q = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                if dist(q[0], q[1], dx, dy) <= ring_m:
                    return run + L * k / n
            run += L
        return run

    def _raid_stage(self, ex, ba, path, arrive, V, dx, dy, L):
        """v0.41.261: the plan of a staged fleet raid: which groups start airborne on the marshal and which take off (and when), and the time it pushes. -> dict
        {"plan": {group name: {"rwy": bool, "t": takeoff s | None, "mk": marshal level}}, "T_push": s, "fly_s": s}.
        The push is when the raid would reach the missiles' ring as blue's CAP comes on station (the old rule reached the launch point then), but no earlier than the
        last batch has joined plus RAID_JOIN_S: a raid that cannot assemble in time is late, not thin."""
        def split(n, cap):
            k = max(1, math.ceil(n / cap))
            return [n // k + (1 if i < n % k else 0) for i in range(k)]
        nb, ne = int(ex["bombers"]), int(ex.get("escorts", 0) or 0)
        nbg = len(split(nb, RAID_BOMBER_BATCH)) if nb else 0
        esz = split(ne, RAID_FIGHTER_BATCH) if ne else []
        n_sweep = len(esz) // 2 if len(esz) >= 3 else (1 if (ex.get("mass") and len(esz) >= 2) else 0)
        fighters = [f"Raid Sweep {i + 1}" for i in range(n_sweep)] + [f"Raid Escort {i + 1}" for i in range(len(esz) - n_sweep)]
        bombers = [f"Raid Bomber {i + 1}" for i in range(nbg)]
        guards = ([n for n in fighters if "Escort" in n] or fighters)[:RAID_GUARD_UP]          # the guard is an escort group, not a sweep
        up_b = bombers[:RAID_BOMBERS_UP]
        queue = [(n, RAID_BOMBER_GAP_S) for n in bombers if n not in up_b] + [(n, RAID_FIGHTER_GAP_S) for n in fighters if n not in guards]          # bombers first, the rest of the escorts last
        offs, o = {}, 0.0
        for n, gap in queue:
            offs[n] = o
            o += gap
        o_last = max(offs.values(), default=0.0)
        fly_s = dist(ba.x, ba.y, path[0][0], path[0][1]) / (V * 0.85) + RAID_CLIMB_S + (RAID_TAXI_S if RAID_RAMP_START else 0.0)
        T_asm = (RAID_FIRST_TAKEOFF_S + o_last + fly_s + RAID_JOIN_S) if queue else 0.0
        t_want = arrive - self._ring_dist(path, dx, dy, RAID_REACH_NM * NM) / V
        T_push = max(t_want, T_asm)
        t0 = T_push - RAID_JOIN_S - fly_s - o_last
        plan, mk = {}, 0
        for n in fighters + bombers:
            on = n in offs
            plan[n] = {"rwy": on, "t": (t0 + offs[n]) if on else None, "mk": mk}
            mk += 1
        return {"plan": plan, "T_push": T_push, "fly_s": fly_s}

    def _raid_axis(self, package, station):
        """The first part of a fleet raid's geometry, shared by the raid itself and by the interceptors' dash point: -> (ba, w1, mshl, staged_ok, apt_r), where `ba` is the bomber
        wing's field asset, `w1` the route's outer point (at most 220 nm from the target), `mshl` the marshal (outside the missiles' reach for a staged raid)."""
        st, ex = self.state, package.extra
        cvb = st.bases[package.objective.target_id]
        aim = ex.get("aim", "") or ""
        dx, dy = (ex.get("dest") or (cvb.x, cvb.y))
        cvg = self.ship.get(cvb.id)
        ba = st.assets[ex["bomber_wing"]]
        w1 = offset(dx, dy, ex["brg"], min(220 * NM, 0.9 * dist(ba.x, ba.y, dx, dy)))
        mshl = self._raid_marshal(ba, w1, station, dx, dy)
        apt_r = self.t.airports.get(ba.airport) if getattr(ba, "airport", None) else None
        staged_ok = RAID_STAGE_ON and (not bool(ex.get("land"))) and cvg is not None and not aim and apt_r is not None
        if staged_ok:
            mshl = self._raid_marshal_out(mshl, ba, w1, dx, dy)          # v0.41.261: outside the missiles' reach
        return ba, w1, mshl, staged_ok, apt_r

    @staticmethod
    def _seg_clear(a, b, circles) -> bool:
        """True when the segment a-b stays outside every (x, y, nm) circle (a hair of slack: the avoid circles already carry a margin)."""
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy
        for cx, cy, r in circles:
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cx - a[0]) * vx + (cy - a[1]) * vy) / L2))
            if dist(a[0] + t * vx, a[1] + t * vy, cx, cy) < r * NM - 0.5 * NM:
                return False
        return True

    def _raid_circles(self, package) -> list:
        """(id, x, y, nm) of the live SAM circles the interceptors keep out of (the same filter as `_zone_sams` for fighters, with the site ids)."""
        return [(a.id, a.x, a.y, max(AVOID_NM[a.variant], RAID_SA11_NM) if a.variant == "SA-11" else AVOID_NM[a.variant]) for a in self.state.assets.values()
                if a.kind == AssetKind.SAM and a.variant in AVOID_NM and not a.destroyed and a.health > 0.25 and not getattr(a, "suppressed", False)]

    def _raid_blockers(self, package, geom, hold) -> tuple:
        """v0.41.267 (PR 2): the SAM sites that stop the interceptors' dash, as many as the raid SEAD can take (RAID_BLOCK_MAX). Greedy: while `_raid_intercept` finds no
        lane, take the circle the straight line from the hold point to the furthest SAM-free point on the bombers' way in cuts deepest, as if it were already dead.
        -> (site ids, intercept result with those sites ignored or None). ([], result) when the lane is already clear; ([], None) when there is no SAM-free point at all."""
        ip = self._raid_intercept(package, geom, hold)
        if ip is not None:
            return [], ip
        ex = package.extra or {}
        if ex.get("land") or ex.get("aim"):
            return [], self._raid_bent(package, geom, hold)
        try:
            ba, w1, mshl, staged_ok, apt_r = self._raid_axis(package, (hold[0], hold[1]))
        except (KeyError, AttributeError):
            return [], self._raid_bent(package, geom, hold)
        circ = self._raid_circles(package)
        L = dist(w1[0], w1[1], mshl[0], mshl[1])
        if L < 5 * NM:
            return [], self._raid_bent(package, geom, hold)
        ux, uy = (mshl[0] - w1[0]) / L, (mshl[1] - w1[1]) / L
        target = None
        for k in range(int(L / (RAID_IP_STEP_NM * NM)), -1, -1):
            P = (w1[0] + ux * k * RAID_IP_STEP_NM * NM, w1[1] + uy * k * RAID_IP_STEP_NM * NM)
            if dist(hold[0], hold[1], P[0], P[1]) <= RAID_IP_MAX_NM * NM and not any(dist(P[0], P[1], cx, cy) < r * NM for _i, cx, cy, r in circ):
                target = P
                break
        if target is None:
            return [], self._raid_bent(package, geom, hold)
        vx, vy = target[0] - hold[0], target[1] - hold[1]
        L2 = vx * vx + vy * vy
        deep = []                                                          # the circles the straight line to the SAM-free point cuts into, deepest first
        for i_, cx, cy, r in circ:
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cx - hold[0]) * vx + (cy - hold[1]) * vy) / L2))
            d_ = dist(hold[0] + t * vx, hold[1] + t * vy, cx, cy) - r * NM        # negative: the line is inside the circle
            if d_ < 0:
                deep.append((d_, i_))
        deep.sort()
        ids = [i_ for _d, i_ in deep][:6]
        import itertools
        for n in range(1, RAID_BLOCK_MAX + 1):                            # fewest flights first: one site, then pairs
            for combo in itertools.combinations(ids, n):
                ip = self._raid_intercept(package, geom, hold, ignore=combo)
                if ip is not None:
                    return list(combo), ip
        return [], self._raid_bent(package, geom, hold)                                                    # not clearable with the flights the setpiece has: the SEAD keeps its old single site

    def _raid_bent(self, package, geom, hold):
        """v0.41.268 (PR 3; XO 2026-11-04: "the F-14s have so much time to wait on orbit they could overfly on blue bases and get closer"): the intercept lane when none is clear
        straight from the hold point. The dash goes hold -> a blue field -> the intercept point, each leg bent round the SAM circles; the point is the furthest out on the bombers'
        way in that some field reaches within RAID_BEND_MAX_NM (the shortest way by field when several do). Same result shape as `_raid_intercept`, plus "via": [(x, y, field name)].
        -> dict or None (no field, or no point reachable: the interceptors hold at their station)."""
        ex = package.extra or {}
        if ex.get("land") or ex.get("aim"):
            return None
        try:
            ba, w1, mshl, staged_ok, apt_r = self._raid_axis(package, (hold[0], hold[1]))
        except (KeyError, AttributeError):
            return None
        circles = [(cx, cy, r) for _i, cx, cy, r in self._raid_circles(package)]
        L = dist(w1[0], w1[1], mshl[0], mshl[1])
        if L < 5 * NM:
            return None
        fields = [b for b in self.state.bases.values() if b.kind == BaseKind.AIRFIELD and b.id not in self.state.assets
                  and not any(dist(b.x, b.y, cx, cy) < r * NM for cx, cy, r in circles)]
        if not fields:
            return None
        ux, uy = (mshl[0] - w1[0]) / L, (mshl[1] - w1[1]) / L
        for k in range(int(L / (RAID_IP_STEP_NM * NM)), -1, -1):
            s_ = k * RAID_IP_STEP_NM * NM
            P = (w1[0] + ux * s_, w1[1] + uy * s_)
            if any(dist(P[0], P[1], cx, cy) < r * NM for cx, cy, r in circles):
                continue
            best = None
            for b in fields:
                leg1 = avoid_circles([Wpt("HOLD", hold[0], hold[1], 0, 0), Wpt("BASE", b.x, b.y, 0, 0)], circles, RAID_IP_LANE_PTS, 1)
                leg2 = avoid_circles([Wpt("BASE", b.x, b.y, 0, 0), Wpt("IP", P[0], P[1], 0, 0)], circles, RAID_IP_LANE_PTS, 1)
                xy = [(w.x, w.y) for w in leg1] + [(w.x, w.y) for w in leg2[1:]]
                if not all(self._seg_clear(xy[i], xy[i + 1], circles) for i in range(len(xy) - 1)):
                    continue
                n_ = sum(dist(xy[i][0], xy[i][1], xy[i + 1][0], xy[i + 1][1]) for i in range(len(xy) - 1))
                if n_ <= RAID_BEND_MAX_NM * NM and (best is None or n_ < best[0]):
                    best = (n_, b, xy)
            if best is None:
                continue
            _n, b, xy = best
            perp = bearing(w1[0], w1[1], mshl[0], mshl[1]) + 90
            for sgn in (1, -1):
                P2 = offset(P[0], P[1], perp if sgn > 0 else perp + 180, RAID_IP_LEG_NM * NM)
                if not any(dist(P2[0], P2[1], cx, cy) < r * NM for cx, cy, r in circles):
                    return {"ip": P, "ip2": P2, "lane": xy[1:-1], "from_w1_nm": round(s_ / NM), "via": [(b.x, b.y, b.name)], "path_nm": round(_n / NM)}
        return None

    def _raid_intercept(self, package, geom, hold, ignore=()):
        """v0.41.265: where the fleet raid's interceptors dash to. On the bombers' way in (marshal to the route's outer point `w1`, beyond which they are in range of the fleet),
        the point furthest out that (a) is outside every live SAM's circle the fighters keep out of (`_zone_sams`), (b) is at most RAID_IP_MAX_NM from the hold point `hold`, and
        (c) can be reached from the hold along a lane that bends round those circles (`avoid_circles`) and ends clear. The orbit there is a short leg across the bombers' line.
        -> {"ip": (x, y), "ip2": (x, y), "lane": [(x, y), ...] bends only, hold and ip excluded} or None (no such point: the interceptors keep their old shape)."""
        ex = package.extra or {}
        if ex.get("land") or ex.get("aim"):
            return None
        try:
            ba, w1, mshl, staged_ok, apt_r = self._raid_axis(package, (hold[0], hold[1]))
        except (KeyError, AttributeError):
            return None
        circles = [(cx, cy, r) for i_, cx, cy, r in self._raid_circles(package) if i_ not in ignore]          # (v0.41.267: `ignore` = sites the raid SEAD is sent against)
        L = dist(w1[0], w1[1], mshl[0], mshl[1])
        if L < 5 * NM:
            return None
        ux, uy = (mshl[0] - w1[0]) / L, (mshl[1] - w1[1]) / L          # from w1 back toward the marshal
        for k in range(int(L / (RAID_IP_STEP_NM * NM)), -1, -1):        # furthest out first
            s_ = k * RAID_IP_STEP_NM * NM
            P = (w1[0] + ux * s_, w1[1] + uy * s_)
            if dist(hold[0], hold[1], P[0], P[1]) > RAID_IP_MAX_NM * NM or any(dist(P[0], P[1], cx, cy) < r * NM for cx, cy, r in circles):
                continue
            pts = avoid_circles([Wpt("HOLD", hold[0], hold[1], 0, 0), Wpt("IP", P[0], P[1], 0, 0)], circles, RAID_IP_LANE_PTS, 1)
            xy = [(w.x, w.y) for w in pts]
            if not all(self._seg_clear(xy[i], xy[i + 1], circles) for i in range(len(xy) - 1)):
                continue
            perp = bearing(w1[0], w1[1], mshl[0], mshl[1]) + 90
            for sgn in (1, -1):
                P2 = offset(P[0], P[1], perp if sgn > 0 else perp + 180, RAID_IP_LEG_NM * NM)
                if not any(dist(P2[0], P2[1], cx, cy) < r * NM for cx, cy, r in circles):
                    return {"ip": P, "ip2": P2, "lane": xy[1:-1], "from_w1_nm": round(s_ / NM)}
        return None

    def _raid_hold_xy(self, package, geom):
        """The leashed station of a fleet raid's interceptors (the first point of the racetrack that `_leash_fleet_cap` walks clear of the SAMs): their hold point."""
        pts = [Wpt("CAP1", geom.cap1[0], geom.cap1[1], 0, 0, "", "CAPORBIT"), Wpt("CAP2", geom.cap2[0], geom.cap2[1], 0, 0)]
        self._leash_fleet_cap(pts, 0, geom.tx, geom.ty)
        return (pts[0].x, pts[0].y)

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

    def _raid_launch(self, package, station, w1=None):
        """v0.41.248: where a raid on the FLEET fires from: on the raid's bearing, RAID_LAUNCH_OUT_NM beyond the blue CAP `station`, not closer than RAID_LAUNCH_MIN_NM
        to the carrier, not past the route's outer point `w1`. None for a land raid. The raid's own route and the CAP's engage circle (so the fighters may fight up to
        the launch point) both use it."""
        ex = package.extra or {}
        cv = self.state.bases.get(package.objective.target_id)
        if ex.get("land") or ex.get("aim") or cv is None or cv.kind != BaseKind.CARRIER:
            return None
        dx, dy = ex.get("dest") or (cv.x, cv.y)
        if w1 is None:
            ba = self.state.assets[ex["bomber_wing"]]
            w1 = offset(dx, dy, ex["brg"], min(220 * NM, 0.9 * dist(ba.x, ba.y, dx, dy)))
        d_l = max(dist(station[0], station[1], dx, dy) + RAID_LAUNCH_OUT_NM * NM, RAID_LAUNCH_MIN_NM * NM)
        d_l = min(d_l, max(dist(*w1, dx, dy) - 5 * NM, RAID_LAUNCH_MIN_NM * NM * 0.5))
        return offset(dx, dy, ex["brg"], d_l)

    def _raid_dests(self, packages) -> list:
        """v0.41.220: where each raid scramble's raiders are going (the field, supply site, garrison or sector: `extra["dest"]`, else the field itself), for the
        packages that are raid scrambles (FLEET_DEFENSE with a raid in `extra`)."""
        out = []
        for p in packages:
            if p.objective.type != ObjectiveType.FLEET_DEFENSE or not p.extra or p.objective.target_id not in self.state.bases:
                continue
            c = self.state.bases[p.objective.target_id]
            d_ = p.extra.get("dest") or (c.x, c.y)
            if all(dist(d_[0], d_[1], q[0], q[1]) > 1.0 for q in out):
                out.append((float(d_[0]), float(d_[1])))
        return out

    def _raid_cover_bases(self, packages) -> dict:
        """v0.41.220 (XO 2026-10-31: a raid target was built but the base's SAMs and nearby sites were not): {base id: (x, y)} of every field whose live Patriot
        (PATRIOT_NM) or HAWK (HAWK_NM) covers a raid scramble's target, the point being what `_place_base` measures the reach from. The war sim and the raid gate
        already count these fields (`raids.covering_fields`); the mission now builds them, nearest first, at most COVER_FIELDS_MAX per raid."""
        from .raids import covering_fields
        out = {}
        for x, y in self._raid_dests(packages):
            for b in covering_fields(self.state, x, y)[:COVER_FIELDS_MAX]:
                out.setdefault(b.id, (x, y))
        return out

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
        if k1 is None or k1 + 1 >= len(wps):
            return
        tx, ty = geom.tx, geom.ty
        if tb is None or tb.kind != BaseKind.AIRFIELD:
            self._leash_fleet_cap(wps, k1, tx, ty)
            return
        (sx, sy), _why = scramble.blue_station(st, tx, ty, scramble.raid_origin(st, package, tx, ty))
        leg = max(dist(wps[k1].x, wps[k1].y, wps[k1 + 1].x, wps[k1 + 1].y), 5 * NM)
        wps[k1].x, wps[k1].y = sx, sy
        wps[k1 + 1].x, wps[k1 + 1].y = offset(sx, sy, bearing(sx, sy, tx, ty) + 90, leg)

    def _leash_fleet_cap(self, wps, k1, tx, ty) -> None:
        """v0.41.255 (XO 2026-11-03, the carrier-raid run: the Tomcats' racetrack ended 17 nm from the Sukhumi SA-10 and the CAP flew in its reach).
        The fleet raid's CAP racetrack is walked back toward the fleet, 2 nm at a time, until both ends are clear of live SA-10s and SAM rings
        (scramble.clear_for_station). Same orbit leg and heading; no clear spot = left as is. Judgment call: the 45 nm SA-10 figure is SQE's own station margin."""
        a, b = wps[k1], wps[k1 + 1]
        leg_b, leg_d = bearing(a.x, a.y, b.x, b.y), dist(a.x, a.y, b.x, b.y)
        home_b = bearing(a.x, a.y, tx, ty)
        d0 = dist(a.x, a.y, tx, ty)
        for step in range(0, int(d0 / (2 * NM)) + 1):
            x, y = offset(a.x, a.y, home_b, step * 2 * NM)
            x2, y2 = offset(x, y, leg_b, leg_d)
            if scramble.clear_for_station(self.state, x, y) and scramble.clear_for_station(self.state, x2, y2):
                break
        else:
            return
        a.x, a.y, b.x, b.y = x, y, x2, y2

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
    def _place_buildings(self, country, aim, kind, cx, cy, hdg, scale=1.0, variant=""):
        """v0.41.192 (XO 2026-10-29: a fuel farm or depot is buildings, not trucks): the static buildings of a supply site, for either side. Returns their
        unit names `<aim>|b<n>` (the debrief reports a static's death by its UNIT name, so the unit is named, not only the group). `scale` < 1 leaves out
        some of them (a site already damaged); at least one stays."""
        parts = supply_parts(kind, variant)
        n = max(1, round(len(parts) * scale)) if parts else 0
        names = []
        from . import road_front, theatres
        rh = road_front.heading_at(theatres.active(), cx, cy) if n else None     # v0.41.259 (XO 2026-11-03): the buildings stand in one block beside the road, not on it
        bx, by = cx, cy
        if rh is not None:
            side = 1 if zlib.crc32(aim.encode()) % 2 == 0 else -1                # one side per site, the same every build
            bx, by = offset(cx, cy, rh + 90 * side, ROAD_OFF_M)
            if not seac.site_ok(bx, by):                                         # that side is sea or water: the other side
                bx, by = offset(cx, cy, rh - 90 * side, ROAD_OFF_M)
            if not seac.site_ok(bx, by):
                rh = None
        for k, vt in enumerate(parts[:n]):
            if rh is None:
                x, y = offset(cx, cy, k * (360 / len(parts)) + hdg, 40 + 12 * k)
            else:
                x, y = offset(bx, by, k * (360 / len(parts)) + hdg, min(ROAD_BLOCK_M, 18.0 + 6.0 * k))
            nm = f"{aim}|b{k + 1}"          # b: never clashes with a guard vehicle `<aim>|<n>` in the same site
            sg = self.m.static_group(country, nm, vt, mapping.Point(x, y, self.t), heading=hdg)
            sg.units[0].name = nm
            names.append(nm)
        return names

    def _spawn_raid_target(self, package, base, aim, dx, dy, manifest):
        """Put the thing under attack on the map: a field's garrison, a fuel farm / depot, or a column of friendly troops. They are what the
        raiders bomb, so the intercepting player sees what is at stake. Small groups (a handful of vehicles or statics)."""
        from . import raids, ground
        st, d, r = self.state, self.d, self.vrng
        kind = raids.aim_kind(aim)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        if kind == "supply":
            a = st.blue_assets[aim]
            names = self._place_buildings(self.usa, aim, a.kind, a.x, a.y, r.randint(0, 359), variant=a.variant)
            manifest.add("blue_site", aim, names, label=a.name, health_before=a.health)          # v0.41.241: the debrief reads the buildings back
            self._supply_built.add(aim)
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
        manifest.add("blue_site", aim, names, label=label, health_before=(st.blue_assets[aim].health if aim in st.blue_assets else None))

    @staticmethod
    def _arm_pts(path, dx, dy, fx=None, fy=None):
        """The raid's way in without the points near the field (inside ARM_LAUNCH_NM + 10): the SEAD / DEAD flights and the gate use these. With (fx, fy), the
        points near that other field are dropped too (a SEAD group for a neighbouring battery)."""
        pts = list(path[:-1])
        near = lambda q: dist(*q, dx, dy) <= (ARM_LAUNCH_NM + 10) * NM or (fx is not None and dist(*q, fx, fy) <= (ARM_LAUNCH_NM + 10) * NM)
        while len(pts) > 1 and near(pts[-1]):
            pts.pop()
        return pts

    def _raid_gate_new(self, cvb, path, dx, dy, t_tgt):
        """v0.41.126 (XO 2026-10-23: red plans like blue, nobody flies into a Patriot's reach before the radars are down): the raid's gate. One point
        DEAD_HOLD_NM from the field (8 nm outside the Patriot's 40 nm reach) on the way in, one user flag the mission sets when every Patriot / HAWK
        radar is dead, and the time DEAD_GATE_WAIT_S after the Kh-31P launch when the groups that wait there give up and go home. The bombers, the sweep and
        the escorts hold there, and so do the DEAD flights. None: the field has no radars to wait for."""
        from .raids import covering_fields
        radars = []
        for f_ in [cvb] + [f for f in covering_fields(self.state, dx, dy) if f.id != cvb.id]:      # v0.41.129: every covering field's radars, not only the raided field's
            ad_ = self.base_ad.get(f_.id) or {}
            radars += [u for k_ in ("pat", "hawk") if ad_.get(k_) is not None for u in ad_[k_].units if u.type in ("Patriot str", "Hawk tr")]
        if not radars:
            return None
        pts = self._arm_pts(path, dx, dy)
        self._flag_n += 1
        t_arm = t_tgt - ARM_LEAD_S
        # v0.41.128 (XO's run: the gate sat 28 nm from the NEIGHBOUR field's Patriot and shot the held bombers): out along the way in until the point is clear
        # of every live battery, DEAD_GATE_CLEAR_NM outside its reach (Patriot / HAWK reach from raids), at most DEAD_HOLD_MAX_NM from the field
        from .raids import HAWK_NM, PATRIOT_NM
        from .sams import blue_battery
        bats = []
        for b_ in self.state.bases.values():
            if b_.kind == BaseKind.AIRFIELD:
                bt_ = blue_battery(b_, self.state)
                r_ = max(PATRIOT_NM if bt_["patriot_ln"] else 0, HAWK_NM if bt_["hawk"] else 0)
                if r_:
                    bats.append((b_.x, b_.y, r_))
        brg_, nm_ = bearing(dx, dy, *pts[-1]), DEAD_HOLD_NM
        while nm_ < DEAD_HOLD_MAX_NM:
            hx_, hy_ = offset(dx, dy, brg_, nm_ * NM)
            if all(dist(hx_, hy_, bx_, by_) >= (r_ + DEAD_GATE_CLEAR_NM) * NM for bx_, by_, r_ in bats):
                break
            nm_ += 4
        return {"flag": self._flag_n, "radars": radars, "hold": offset(dx, dy, brg_, nm_ * NM), "nm": nm_,
                "t_abort": t_arm + DEAD_GATE_WAIT_S, "calls": [], "names": [], "n": 0}

    def _raid_asm_triggers(self, asm, path, pt) -> None:
        """v0.41.277 (XO 2026-11-04: "no push until everybody is up"): one trigger per staged group. Its flag is set when the group's planned leave time has passed AND every group
        that took off has a unit inside the marshal circle (conditions in one trigger are all required). A second trigger sets the same flag RAID_ASM_MAX_S after the planned
        time, so a group that never gets off the ground cannot hold the raid until its fuel is gone."""
        if not asm["groups"]:
            return
        zone = self.m.triggers.add_triggerzone(pt(*path[0]), RAID_ASM_ZONE_NM * NM, True, "raid marshal")
        for name_, g_, flag_, leave_ in asm["groups"]:
            tr = triggers.TriggerOnce(comment=f"raid {name_} pushes: planned time and everybody up")
            tr.add_condition(condition.TimeAfter(int(leave_)))
            for gu in asm["up"]:
                tr.add_condition(condition.PartOfGroupInZone(gu.id, zone.id))
            tr.add_action(action.SetFlag(flag_))
            self.m.triggerrules.triggers.append(tr)
            t2 = triggers.TriggerOnce(comment=f"raid {name_} pushes: the wait is over")
            t2.add_condition(condition.TimeAfter(int(leave_ + RAID_ASM_MAX_S)))
            t2.add_action(action.SetFlag(flag_))
            self.m.triggerrules.triggers.append(t2)

    def _raid_clock_prep(self, package, sx_, sy_, tot_s) -> None:
        """v0.41.280: the fleet raid's push time, known BEFORE the interceptors are built (they are built first, the raiders after). It repeats the first half of `_spawn_raid`
        (marshal, lane, launch point, assembly plan) without building anything, and draws the raid's arrival jitter here so `_spawn_raid` uses the same number. Stores
        `self._rclock[package.id] = {"t_leave", "mshl", "u"}`; nothing when the package is not a staged fleet raid (the interceptors then keep their head start)."""
        ex = package.extra or {}
        try:
            cvb = self.state.bases[package.objective.target_id]
            station = (sx_, sy_)
            aim = ex.get("aim", "") or ""
            if ex.get("land") or aim or self.ship.get(cvb.id) is None or not ex.get("bomber_wing"):
                return
            dx, dy = (ex.get("dest") or (cvb.x, cvb.y))
            ba, w1, mshl, staged_ok, apt_r = self._raid_axis(package, station)
            V = RAID_MPS
            u = self.vrng.uniform(60, 150)
            if not hasattr(self, "_rclock"):
                self._rclock = {}
            self._rclock[package.id] = {"u": u, "mshl": mshl, "t_leave": None}
            arrive = tot_s + u
            lane = [mshl, offset(*mshl, bearing(*mshl, *(w1 if dist(*mshl, *w1) > 15 * NM else station)), RAID_PUSH_NM * NM)]
            if dist(*mshl, dx, dy) > dist(*w1, dx, dy) + 15 * NM:
                lane.append(w1)
            launch = self._raid_launch(package, station, w1)
            path = self._raid_bend(lane, cvb) + [launch]
            L = sum(dist(*path[i], *path[i + 1]) for i in range(len(path) - 1))
            stg = self._raid_stage(ex, ba, path, arrive, V, dx, dy, L) if staged_ok else None
            self._rclock[package.id]["t_leave"] = stg["T_push"] if stg else arrive - L / V
        except (KeyError, AttributeError, TypeError, IndexError):
            return

    def _raid_gate_join(self, gate, g, wp, fighter_nm=None):
        """A group that holds at the gate: its GATE waypoint (or its first point, when it appears there) orbits until the gate's flag is set, at its own level
        (GATE_ALT_STEP_M apart); a fighter group also engages air inside its class's circle meanwhile. The abort sends it to its first leg home, past the EGR
        point (that one is on the field's side of the gate)."""
        alt_ = int(wp.alt + gate["n"] * GATE_ALT_STEP_M)
        gate["n"] += 1
        wp.alt = alt_
        og_ = task.ControlledTask(task.OrbitAction(alt_, int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
        og_.stop_if_user_flag(gate["flag"], True)
        if fighter_nm:
            wp.tasks.append(task.EngageTargetsInZone(mapping.Vector2(wp.position.x, wp.position.y), int(fighter_nm * NM), [task.Targets.All.Air]))
        wp.tasks.append(og_)
        gate["names"].append(g.name)

    def _raid_gate_close(self, gate):
        """Every group has joined: the open trigger (every radar dead sets the flag), the Lua that defines SQE_GOTO / SQE_GATE_OPEN, and the abort trigger."""
        tg_open = triggers.TriggerOnce(comment="red DEAD gate open")
        for u in gate["radars"]:
            tg_open.add_condition(condition.UnitDead(u.id))
        tg_open.add_action(action.SetFlag(gate["flag"]))
        tg_open.add_action(action.DoScript(String("if SQE_GATE_OPEN then SQE_GATE_OPEN(" + ",".join(f"'{n}'" for n in gate["names"]) + ") end")))
        self.m.triggerrules.triggers.append(tg_open)
        if not getattr(self, "_goto_lua", False):
            t0 = triggers.TriggerOnce(comment="define SQE_GOTO")
            t0.add_condition(condition.TimeAfter(1))
            t0.add_action(action.DoScript(String(GOTO_LUA)))
            self.m.triggerrules.triggers.append(t0)
            self._goto_lua = True
        ta = triggers.TriggerOnce(comment="red DEAD gate abort")
        ta.add_condition(condition.TimeAfter(max(GOTO_LUA_DELAY_S, int(gate["t_abort"]))))
        ta.add_condition(condition.FlagIsFalse(gate["flag"]))
        for gname, home_idx in gate["calls"]:
            ta.add_action(action.DoScript(String(f"SQE_GOTO('{gname}',1,{home_idx})")))
        self.m.triggerrules.triggers.append(ta)

    def _spawn_raid_arm(self, package, ex, cvb, path, V, t_tgt, alt, skill, home_, dx, dy, manifest):
        """v0.41.84: a Kh-31P SEAD pair flies the raid's way in, fires at the field's Patriot (else HAWK) from ARM_LAUNCH_NM, then turns away.
        It reaches the launch point ARM_LEAD_S ahead of the bombers' TOT. v0.41.129: one SEAD group for every field whose battery covers the target
        (`ex["arm_fields"]`, [[field id, jets]], nearest first; a package without the list sends all `ex["arm"]` jets at the raided field), each firing
        from ARM_LAUNCH_NM from its own field. Returns the raided field's route, launch point and batteries for the DEAD flights and the cover."""
        ad = self.base_ad.get(cvb.id) or {}
        if not (ad.get("pat") or ad.get("hawk")):
            return None
        plan = [(self.state.bases.get(fid), int(n)) for fid, n in (ex.get("arm_fields") or [])]
        plan = [(f, n) for f, n in plan if f is not None and n > 0] or [(cvb, int(ex["arm"]))]
        pt = lambda x, y: mapping.Point(x, y, self.t)
        t_arm = t_tgt - ARM_LEAD_S
        alt = alt
        k_ = 0
        geo = None
        for fld, n_arm in plan:
            ad_f = self.base_ad.get(fld.id) or {}
            tg = ad_f.get("pat") or ad_f.get("hawk")
            if tg is None:
                continue
            # v0.41.94: four jets against both batteries fly as two pairs, the first on the Patriot, the second on the HAWK; four against a lone (full) Patriot
            # fly as one group of four on it (8 Kh-31P); v0.41.116: eight are two four-jet flights, the first on the Patriot, the second on the HAWK
            pairs = [(tg, n_arm)]
            if n_arm >= 8:
                pairs = [(ad_f.get("pat") or tg, 4), (ad_f.get("hawk") or ad_f.get("pat") or tg, 4)]
            elif n_arm >= 4 and ad_f.get("pat") and ad_f.get("hawk"):
                pairs = [(ad_f["pat"], 2), (ad_f["hawk"], 2)]
            pts = self._arm_pts(path, dx, dy, fld.x, fld.y)
            launch = offset(fld.x, fld.y, bearing(fld.x, fld.y, *pts[-1]), ARM_LAUNCH_NM * NM)
            pa = pts + [launch]
            L = sum(dist(*pa[i], *pa[i + 1]) for i in range(len(pa) - 1))
            t_leave = t_arm - L / V
            hold_until, act_ = None, 0.0
            if t_leave >= 0:
                (sx, sy), remaining = pa[0], pa[1:]
                hold_until, act_ = t_leave, max(0.0, t_leave - RAID_HOLD_MAX_S)
            else:
                (sx, sy), seg_i = tm.point_back_along(pa, min(L, max((ARM_LAUNCH_NM + 10) * NM, V * t_arm)))
                remaining = pa[seg_i:]
            for tgt_, n_jets in pairs:
                k_ += 1
                g = self.m.flight_group(self.red, f"Raid SEAD {k_}", planes.Su_24M, None, pt(sx, sy), altitude=alt + (k_ - 1) * 600, speed=450 * KPH, maintask=task.SEAD, group_size=n_jets)     # each flight 600 m above the last: they share a route
                if hold_until is not None:
                    ct_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                    ct_.stop_after_time(int(hold_until)); g.points[0].tasks.append(ct_)
                    g.points[0].name = "MSHL"
                for k, q in enumerate(remaining):
                    wp = g.add_waypoint(pt(*q), alt + (k_ - 1) * 600, 450 * KPH, "ARM" if k == len(remaining) - 1 else "ING")
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
                    u.name = f"RAID-S-{k_}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
                if not load:
                    self.warns.append("Su-24M: no Kh-31P found; the red SEAD pair is unarmed.")
                manifest.add("enemy_air", ex["bomber_wing"], names, ac="Su_24M")
            if geo is None:                                      # the first (nearest) field's route and launch point: the DEAD flights and the cover use these
                geo = {"pts": pts, "launch": launch, "t_arm": t_arm, "ad": ad_f}
        if geo is None:
            return None
        if ex.get("arm_cover") and ex.get("escort_type"):
            self._spawn_arm_cover(ex, path, geo["pts"], geo["launch"], V, t_arm, alt, skill, home_, manifest, dx, dy)
        return geo

    def _spawn_raid_dead(self, ex, geo, gate, path, V, alt, skill, home_, dx, dy, manifest) -> None:
        """v0.41.117 (XO 2026-10-22: red's DEAD package, 4 + 4 Su-24M with their own escort and TARCAP, waiting for the gate): flights of KAB-500Kr (TV-guided
        500 kg bomb, seeker 15 to 17 km: Wikipedia) fly the SEAD flights' way in to a GATE point DEAD_HOLD_NM from the field, outside the Patriot's reach, and
        orbit there until the field's air-defence radars (Patriot str, HAWK tr) are all dead (a user flag the mission sets). Then they go in on the
        Patriot / HAWK groups (AttackGroup, guided bombs). If the radars are not all dead DEAD_GATE_WAIT_S after the Kh-31P launch, a Lua SwitchWaypoint
        (SQE_GOTO) sends them home: no banzai. v0.41.126: the gate (raid gate, `gate`) is shared with the raid's bombers, sweep and escorts. The first flight takes the Patriot, the second the HAWK (or the Patriot)."""
        pt = lambda x, y: mapping.Point(x, y, self.t)
        ad, pts, t_arm = geo["ad"], geo["pts"], geo["t_arm"]
        n = int(ex["dead"])
        tgts = [(ad.get("pat") or ad.get("hawk"), min(4, n))]
        if n > 4:
            tgts.append((ad.get("hawk") or ad.get("pat") or tgts[0][0], n - 4))
        hold = gate["hold"]
        pa = [q for q in pts if dist(*q, dx, dy) > gate["nm"] * NM] + [hold]
        Lp = sum(dist(*pa[i], *pa[i + 1]) for i in range(len(pa) - 1))
        t_hold = t_arm + DEAD_HOLD_LAG_S
        t_abort = gate["t_abort"]
        t_go = t_hold - Lp / V
        if t_go >= 0:
            (sx, sy), remaining = pa[0], pa[1:]
            hold_until, act_ = t_go, max(0.0, t_go - RAID_HOLD_MAX_S)
        else:
            (sx, sy), seg_i = tm.point_back_along(pa, min(Lp, max(gate["nm"] * NM * 0.5, V * t_hold)))
            remaining, hold_until, act_ = pa[seg_i:], None, 0.0
        if not remaining:
            remaining = [pa[-1]]
        load = enemy_dead_loadout("Su_24M")
        if not load:
            self.warns.append("Su-24M: no KAB-500Kr found; the red DEAD flights are unarmed.")
        for gi, (tg_, nj) in enumerate(tgts):
            gname = f"Raid DEAD {gi + 1}"
            g = self.m.flight_group(self.red, gname, planes.Su_24M, None, pt(sx, sy), altitude=alt - 900 - gi * 600, speed=450 * KPH, maintask=task.GroundAttack, group_size=nj)
            if hold_until is not None:
                ct_ = task.ControlledTask(task.OrbitAction(int(alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                ct_.stop_after_time(int(hold_until)); g.points[0].tasks.append(ct_)
                g.points[0].name = "MSHL"
            for k, q in enumerate(remaining):
                wp = g.add_waypoint(pt(*q), alt - gi * 600, 450 * KPH, "GATE" if k == len(remaining) - 1 else "ING")
                if k == len(remaining) - 1:
                    self._raid_gate_join(gate, g, wp)                                    # holds here until the radars are down
            w_t = g.add_waypoint(pt(tg_.units[0].position.x, tg_.units[0].position.y), max(3000.0, alt * 0.5) - gi * 600, 450 * KPH, "DEAD")       # the TV bombs go in at about 10,000 ft
            w_t.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
            ca_ = task.ControlledTask(task.AttackGroup(tg_.id, weapon_type=task.WeaponType.GuidedBombs, group_attack=True))
            ca_.stop_after_time(int(t_abort + DEAD_ATTACK_WINDOW_S)); w_t.tasks.append(ca_)
            back_ = offset(dx, dy, bearing(dx, dy, *pts[-1]), 20 * NM)
            g.add_waypoint(pt(*back_), alt, 450 * KPH, "EGR")
            gate["calls"].append((gname, len(g.points) + 1))                      # the abort: the first leg home, past the EGR point
            for k, q in enumerate(home_):
                g.add_waypoint(pt(*q), alt, 450 * KPH, "RTB" if k == len(home_) - 1 else "AVD")
            g.points[0].tasks.append(task.OptRTBOnBingoFuel(True))
            g.set_skill(skill)
            if act_ >= 30:
                self._late(g, act_)
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"RAID-D-{gi + 1}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", ex["bomber_wing"], names, ac="Su_24M")
        if ex.get("dead_cover") and ex.get("escort_type"):
            tar_ = offset(dx, dy, bearing(dx, dy, *pts[-1]), (gate["nm"] + ARM_TARCAP_BEHIND_NM) * NM)          # the TARCAP: back along the way in from the hold
            self._spawn_arm_cover(ex, path, pts, hold, V, t_hold, alt, skill, home_, manifest, dx, dy, jobs=("Raid DEAD Escort", "Raid DEAD TARCAP"), pfx=("DE", "DT"),
                                  on_s=t_hold - ARM_TARCAP_LEAD_S, off_s=t_abort + 300, sta_tarcap=tar_)

    def _spawn_arm_cover(self, ex, path, pts, launch, V, t_arm, alt, skill, home_, manifest, dx, dy, jobs=("Raid SEAD Escort", "Raid SEAD TARCAP"),
                         pfx=("SE", "ST"), on_s=None, off_s=None, sta_tarcap=None) -> None:
        """v0.41.116 (XO 2026-10-22: red's SEAD package is blue's shape: the HARM flights, a TARCAP and an escort): two fighters (the escort) hold a station
        on the Kh-31P launch point, two (the TARCAP) one ARM_TARCAP_BEHIND_NM back along the way in. Both fly the SEAD flights' route, are in on station
        ARM_TARCAP_LEAD_S before the missiles go, engage air inside their class's circle, and stay until ARM_TARCAP_STAY_S after (out of AAMs: home).
        A real EscortTaskAction on the SEAD group is not used: the SEAD flights are late-activated and shift with the hold, so a plain station is steadier."""
        pt = lambda x, y: mapping.Point(x, y, self.t)
        cls = getattr(planes, ex["escort_type"])
        load = enemy_cap_loadout(ex["escort_type"])
        zone_nm = A2A_ZONE_NM[ex["escort_type"] in RED_LONG_RANGE]
        from .mission_builder import AAM_WEAPONS            # lazy: the builder's module imports this one
        bk = sta_tarcap or offset(*launch, bearing(*launch, *pts[-1]), ARM_TARCAP_BEHIND_NM * NM)           # the TARCAP station: back along the way in
        t_on = max(0.0, (t_arm - ARM_TARCAP_LEAD_S) if on_s is None else on_s)                  # v0.41.117: the DEAD package's cover passes its own times and stations
        for job in jobs:
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
                    oc_.stop_after_time(int(off_s if off_s is not None else t_arm + ARM_TARCAP_STAY_S)); wp.tasks.append(oc_)
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
                u.name = f"RAID-{pfx[0] if job.endswith('Escort') else pfx[1]}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
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
        pt = lambda x, y: mapping.Point(x, y, self.t)
        station = (sx_, sy_)
        ba, w1, mshl, staged_ok, apt_r = self._raid_axis(package, station)          # v0.41.265: one place for the marshal and the outer point (the interceptors' dash point uses them too)
        V = RAID_MPS
        u_ = (getattr(self, "_rclock", {}).get(package.id) or {}).get("u")          # (v0.41.280: drawn earlier by `_raid_clock_prep`, the same number)
        arrive = tot_s + (u_ if u_ is not None else r.uniform(60, 150))                    # at the station: 1-2.5 min after our scramble's TOT
        t_tgt = arrive + dist(sx_, sy_, dx, dy) / V            # the raid's own TOT
        # v0.41.29: the raid flies blue's shape. Marshal on red's side (in a red SAM's cover along its way in, else just off its field), PUSH,
        # ingress bent round blue's Patriot fields (not the one it is raiding), the target at its TOT, then egress and home.
        lane = [mshl, offset(*mshl, bearing(*mshl, *(w1 if dist(*mshl, *w1) > 15 * NM else station)), RAID_PUSH_NM * NM)]
        if dist(*mshl, dx, dy) > dist(*w1, dx, dy) + 15 * NM:
            lane.append(w1)
        # v0.41.248 (XO 2026-11-03): a raid on the FLEET launches from a stand-off point and turns home; it never flies to the carrier. The point is on the raid's
        # bearing, RAID_LAUNCH_OUT_NM beyond the blue CAP station (so the fighters meet it before it fires), at least RAID_LAUNCH_MIN_NM from the carrier, and no farther
        # than the route's own outer point. The bombers reach it when the scramble's CAP is on station (`arrive`).
        standoff = (not bool(ex.get("land"))) and cvg is not None and not aim
        launch = self._raid_launch(package, station, w1) if standoff else None
        if standoff:
            t_tgt = arrive                                      # (the launch point, not the carrier)
            lane = self._raid_bend(lane, cvb) + [launch]
            path = lane
        else:
            lane = self._raid_bend(lane, cvb) + [station]
            path = lane + [(dx, dy)]
        if standoff:
            # v0.41.256 (XO 2026-11-03: no SAMs across the mountains, so blue's F-15s could bum-rush the bombers): the red SAM sites whose ring touches the bombers' way in
            # (the route starts at most 220 nm from the fleet) are live in the mission, RAID_ROUTE_SAMS of them beyond the ones already built; the unit limit still binds
            self._spawn_opfor_ground(package, dx, dy, manifest, list(path), route_sites=RAID_ROUTE_SAMS)
        ox, oy = launch if standoff else (dx, dy)               # where the route ends: the launch point, else the target
        L = sum(dist(*path[i], *path[i + 1]) for i in range(len(path) - 1))
        stg = self._raid_stage(ex, ba, path, arrive, V, dx, dy, L) if (staged_ok and standoff) else None
        t_leave = stg["T_push"] if stg else t_tgt - L / V      # v0.41.261: a staged raid pushes when it has assembled (and blue's CAP is up), see _raid_stage
        hold_until, act_ = None, 0.0
        if t_leave >= 0:                                       # it holds at its marshal until it must push, appearing at most RAID_HOLD_MAX_S before
            (sx, sy), remaining = path[0], path[1:]
            hold_until, act_ = t_leave, max(0.0, t_leave - RAID_HOLD_MAX_S)
            hit_s = t_leave + L / V
        else:                                                  # no time to hold: already on its way in, but never closer than RAID_MIN_NM (then it is late)
            back_ = min(L, max(RAID_MIN_NM * NM, V * t_tgt))
            (sx, sy), seg_i = tm.point_back_along(path, back_)
            remaining = path[seg_i:]
            hit_s = back_ / V
        egr_ = offset(ox, oy, bearing(ox, oy, *remaining[-2] if len(remaining) > 1 else (sx, sy)) + 40, RAID_EGRESS_NM * NM)
        home_ = self._raid_bend([egr_, (ba.x, ba.y)], cvb)[1:]           # turn points round blue's Patriot fields, then its own field
        skill = getattr(Skill, ai_skill(self.o, "red", d), Skill.High)
        land = bool(ex.get("land"))
        alt = ((12000 if ex.get("raider") == "Su_25" else 20000) if land else 30000) * FT
        apt = self.t.airports.get(cvb.airport) if (land and cvb.airport and not aim) else None

        fin_ = "BASE" if bool(ex.get("land")) else ("LAUNCH" if standoff else "FLEET")
        # v0.41.126: a raid with SEAD in front of it waits for the radars to go down: its bombers, sweep and escorts hold at the gate, DEAD_HOLD_NM out
        # v0.41.240 (XO 2026-11-03: the bombers never got their clear and the escorts melted at the gate): only the DEAD package waits for the radars. The
        # bombers, sweep and escorts fly the clock: they reach the target ARM_LEAD_S after the Kh-31P launch point, about 60 s after the missiles land, so the
        # SAM crews have to split fire between the missiles and the bombers. No radar-dead condition, no abort for them.
        gate = self._raid_gate_new(cvb, path, dx, dy, t_tgt) if (land and ex.get("arm") and ex.get("dead") and not aim) else None
        back0 = 0.0 if hold_until is not None else back_
        def start_at(shift_s):
            """Where a group starts and which points it still has to fly, `shift_s` seconds later (+) or earlier (-) than the raid's lead."""
            if hold_until is not None:
                h = max(0.0, hold_until + shift_s)
                return path[0], path[1:], h, max(0.0, h - RAID_HOLD_MAX_S)
            b = min(L, max(RAID_MIN_NM * NM * 0.5, back0 + shift_s * V))
            p_, si = tm.point_back_along(path, b)
            return p_, path[si:], None, 0.0

        asm = {"groups": [], "up": [], "pos": None}              # v0.41.277: the staged groups (name, group, flag, planned leave) and the ones that take off

        def hold_stop(ct_, g_, name_, hold_, from_ground=False):
            """A staged group's marshal orbit ends at its planned time (the old rule) or, with RAID_WAIT_ALL, on its own flag, which `asm_triggers` sets once that time has passed
            and everybody who took off is at the marshal."""
            if stg and RAID_WAIT_ALL and name_ in stg["plan"]:
                self._flag_n += 1
                ct_.stop_if_user_flag(self._flag_n, True)
                asm["groups"].append((name_, g_, self._flag_n, float(hold_)))
                if from_ground:
                    asm["up"].append(g_)
            else:
                ct_.stop_after_time(int(hold_))

        def build_group(name, cls, count, task_cls, bomber=False, shift=0.0, behind_nm=0.0, gated=False, fighter_nm=None):
            pos, rem, hold, act = start_at(shift)
            gi_, at_gate = None, False
            if gated and gate is not None:
                # v0.41.126: the way in has a GATE point DEAD_HOLD_NM out, before the first point inside that circle; a group that would appear inside it starts at the gate
                gd_ = gate["nm"] * NM
                if dist(pos[0], pos[1], dx, dy) <= gd_:
                    pos, at_gate = gate["hold"], True
                else:
                    gi_ = next((i for i, q in enumerate(rem) if dist(q[0], q[1], dx, dy) <= gd_), len(rem) - 1)
                    rem = rem[:gi_] + [gate["hold"]] + rem[gi_:]
            if behind_nm and rem:
                pos = offset(pos[0], pos[1], bearing(rem[0][0], rem[0][1], pos[0], pos[1]), behind_nm * NM)
            nm_ = (["PUSH"] + ["ING"] * (len(rem) - 2) + [fin_]) if hold is not None else (["ING"] * (len(rem) - 1) + [fin_])
            sl = stg["plan"].get(name) if (stg and hold is not None) else None          # v0.41.261: a staged raid's group: on the marshal from the start, or off the runway
            m_alt = alt - (sl["mk"] * RAID_MSHL_STEP_M if sl else 0.0)
            r_alt = m_alt if sl else alt                       # v0.41.263: a staged group keeps its own level the whole way (they used to climb to one common level and meet)
            g = None
            if sl is not None and sl["rwy"]:
                ramp_ = False
                g = self._from_airport(self.red, name, cls, apt_r, task_cls, StartType.Warm, count, quiet=True) if RAID_RAMP_START else None          # v0.41.277: hot on the ramp, started by a timer
                if g is not None:
                    ramp_ = True
                else:
                    g = self._from_airport(self.red, name, cls, apt_r, task_cls, StartType.Runway, count, quiet=True)
                if g is not None:
                    mw = g.add_waypoint(pt(*pos), m_alt, 450 * KPH, "MSHL")
                    ct_ = task.ControlledTask(task.OrbitAction(int(m_alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                    hold_stop(ct_, g, name, hold, True); mw.tasks.append(ct_)
                    if ramp_:
                        g.add_trigger_action(task.StartCommand())
                        g.uncontrolled = True
                        trs_ = triggers.TriggerOnce(comment=f"start {name}")
                        trs_.add_condition(condition.TimeAfter(int(max(5.0, sl["t"]))))
                        trs_.add_action(action.AITaskPush(g.id, 1))
                        self.m.triggerrules.triggers.append(trs_)
                    else:
                        self._late(g, max(5.0, sl["t"]), "take off")
                    asm["pos"] = pos
                    act = 0.0
                else:
                    sl = None
            if g is None:
                if sl is not None:                             # on the marshal from the start, side by side and one level apart
                    h_ = bearing(rem[0][0], rem[0][1], pos[0], pos[1]) + 90
                    pos = offset(pos[0], pos[1], h_, ((sl["mk"] % 4) - 1.5) * 600.0)
                    act = 0.0
                g = self.m.flight_group(self.red, name, cls, None, pt(*pos), altitude=m_alt, speed=450 * KPH, maintask=task_cls, group_size=count)
                if hold is not None:                           # its marshal: orbit until it must push
                    ct_ = task.ControlledTask(task.OrbitAction(int(m_alt), int(450 * KPH), pattern=task.OrbitAction.OrbitPattern.Circle))
                    hold_stop(ct_, g, name, hold, False); g.points[0].tasks.append(ct_)
                    g.points[0].name = "MSHL"
            if at_gate:
                g.points[0].name = "GATE"
                self._raid_gate_join(gate, g, g.points[0], fighter_nm)
            for k, q in enumerate(rem):
                wp = g.add_waypoint(pt(*q), r_alt, 450 * KPH, "GATE" if k == gi_ else nm_[k])
                if k == gi_:
                    self._raid_gate_join(gate, g, wp, fighter_nm)
                if k == len(rem) - 1 and bomber:
                    if land and apt is not None:
                        wp.tasks.append(task.BombingRunway(airport_id=apt.id))
                    elif land and aim:
                        wp.tasks.append(task.Bombing(mapping.Vector2(dx, dy)))
                    elif cvg is not None and cls is planes.Tu_22M3:
                        ca_ = task.ControlledTask(task.AttackGroup(cvg.id, group_attack=True, expend=task.Expend.All) if standoff else task.AttackGroup(cvg.id))      # v0.41.248: the whole group fires everything at once (XO: saturate, then home)
                        if standoff:                           # v0.41.248: fire from the launch point, then leave; the task ends after the window whatever is left
                            ca_.stop_after_time(int(hit_s + shift + RAID_LAUNCH_WINDOW_S))
                        wp.tasks.append(ca_)
            if bomber and standoff and cls is planes.Tu_22M3:
                # v0.41.261 (XO 2026-11-03: "they don't get that shoot-at-ships order on the start"): pydcs puts the anti-ship "engage ships" order on the FIRST point, so a raid
                # fired from wherever it was the moment the carrier was in range (380 km, 87 s into the run). It now starts at the PUSH, the first point after the marshal.
                eng_ = [t_ for t_ in g.points[0].tasks if getattr(t_, "Id", "") == "EngageTargets"]
                if eng_ and len(g.points) > 1:
                    g.points[0].tasks = [t_ for t_ in g.points[0].tasks if t_ not in eng_]
                    pi_ = next((i_ for i_, p_ in enumerate(g.points) if getattr(p_, "name", "") == "PUSH"), None)
                    if pi_ is None:
                        pi_ = 2 if (sl is not None and sl["rwy"]) else 1
                    for t_ in reversed(eng_):
                        g.points[pi_].tasks.insert(0, t_)
            g.add_waypoint(pt(*egr_), r_alt, 450 * KPH, "EGR")
            if gate is not None and name in gate["names"]:
                gate["calls"].append((name, len(g.points) + 1))        # the abort: the first leg home, past the EGR point
            for k, q in enumerate(home_):
                g.add_waypoint(pt(*q), r_alt, 450 * KPH, "RTB" if k == len(home_) - 1 else "AVD")
            g.points[0].tasks.append(task.OptRTBOnBingoFuel(True))
            g.set_skill(skill)
            if act >= 30 and not g.late_activation:
                self._late(g, act)
            return g

        def sizes(n, cap=4):
            """pydcs makes one group of at most 4: a bigger raid is several groups of nearly equal size (12 -> 4+4+4, 6 -> 3+3). A staged raid's bombers go in pairs (RAID_BOMBER_BATCH)."""
            k = max(1, math.ceil(n / cap))
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
        gap_ = RAID_STAGED_GAP_S if stg else RAID_GROUP_GAP_S
        for gi, n_ in enumerate(sizes(ex["bombers"], RAID_BOMBER_BATCH if stg else 4)):         # v0.41.108: a big raid is several groups, a minute apart on the same route
            g = build_group(f"Raid Bomber {gi + 1}", cls_b, n_, task_b, bomber=True, shift=gi * gap_)
            names = []
            for u in g.units:
                nb_ += 1
                u.name = f"RAID-B-{nb_}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", ex["bomber_wing"], names, ac=ex.get("raider", "Tu_22M3"), raid_base=cvb.id, raid_aim=aim, raid_label=package.objective.description.replace("Intercept a raid on ", "").replace("Intercept an air attack on ", ""),
                         raid_arrive_s=float(hit_s + gi * gap_), raid_group=g.name)
            bomber_gs.append(g)
        self._spawn_raid_target(package, cvb, aim, dx, dy, manifest)
        if land and ex.get("arm") and not aim:
            geo_ = self._spawn_raid_arm(package, ex, cvb, path, V, t_tgt, alt, skill, home_, dx, dy, manifest)
            if geo_ and gate is not None and ex.get("dead"):  # v0.41.117: the DEAD package, gated on the battery's radars
                self._spawn_raid_dead(ex, geo_, gate, path, V, alt, skill, home_, dx, dy, manifest)
        if ex.get("escorts"):
            # v0.41.108: the escorts of a big raid split in two jobs. Half (at least 3 groups) fly a sweep RAID_SWEEP_LEAD_S ahead of the bombers on the same
            # route and fight what they meet; the rest escort the bomber groups (spread over them). A small raid keeps its single escort group.
            esz = sizes(ex["escorts"], RAID_FIGHTER_BATCH)
            n_sweep = len(esz) // 2 if len(esz) >= 3 else (1 if (ex.get("mass") and len(esz) >= 2) else 0)        # v0.41.156: a mass raid (8 or more bombers) always opens with a sweep
            eload = enemy_cap_loadout(ex["escort_type"])
            from .mission_builder import AAM_WEAPONS            # lazy: the builder's module imports this one
            esc_nm_ = A2A_ZONE_NM[ex["escort_type"] in RED_LONG_RANGE]
            ne_ = 0
            for ei, n_ in enumerate(esz):
                if ei < n_sweep:
                    eg = build_group(f"Raid Sweep {ei + 1}", getattr(planes, ex["escort_type"]), n_, task.FighterSweep, shift=-RAID_SWEEP_LEAD_S - 15 * ei, fighter_nm=esc_nm_)
                else:
                    ci = ei - n_sweep
                    bg = bomber_gs[ci * len(bomber_gs) // max(1, len(esz) - n_sweep)]
                    eg = build_group(f"Raid Escort {ci + 1}", getattr(planes, ex["escort_type"]), n_, task.Escort, shift=bomber_gs.index(bg) * gap_, behind_nm=3)
                    # v0.41.29: the escorts stay with the bombers and fight only what comes within their class's reach of them (Su-27 25 nm, the rest
                    # 15 nm), up to the bombers' egress point; home once their air-to-air missiles are gone. No chasing.
                    eg.points[0].tasks = [t_ for t_ in eg.points[0].tasks if getattr(t_, "Id", "") != "Escort"]      # pydcs's default escort task has no group
                    if standoff:
                        # v0.41.255 (XO 2026-11-03, the carrier-raid run: the Su-27 escorts split from the bombers): the fleet raid's escorts fly the bombers' own
                        # route and clock (same shift, 3 nm behind) and engage only inside a circle round themselves, a waypoint at a time, so a fight cannot
                        # pull them off the route (no Escort task: that one lets them chase out to its distance and they never come back)
                        for k_, pt_ in enumerate(eg.points[:len(eg.points) - len(home_)]):
                            if str(getattr(pt_, "type", "")) == "TakeOff":          # (a staged escort starts on the runway: no fighting zone round the field)
                                continue
                            pt_.tasks.append(task.EngageTargetsInZone(mapping.Vector2(pt_.position.x, pt_.position.y), int(esc_nm_ * NM), [task.Targets.All.Air]))
                    else:
                        eg.points[0].tasks.insert(0, task.EscortTaskAction(group_id=bg.id, engagement_max_dist=int(esc_nm_ * NM), lastwpt=len(bg.points) - 1 - len(home_),
                                                                            targets=[task.Targets.All.Air.id], position={"x": -1000, "y": 300, "z": 500}))
                rtbe_ = task.OptRTBOnOutOfAmmo(); rtbe_.params["action"]["params"]["value"] = AAM_WEAPONS
                eg.points[0].tasks.append(rtbe_)
                en = []
                for u in eg.units:
                    ne_ += 1
                    u.name = f"RAID-E-{ne_}"; u.pylons = copy.deepcopy(eload); en.append(u.name); self._note_jam(u)
                manifest.add("enemy_air", ex["escort_wing"], en, ac=ex["escort_type"])
        self._raid_asm_triggers(asm, path, pt)
        if gate is not None:
            self._raid_gate_close(gate)
