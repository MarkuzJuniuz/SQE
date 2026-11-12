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
from .loadouts import BOMBER_TYPES, ENEMY_FIGHTERS, enemy_arm_loadout, enemy_bomber_loadout, enemy_cap_loadout, enemy_land_bomber_loadout, enemy_strike_loadout
from .models import AssetKind, BaseKind, ObjectiveType, Role
from .red_air_picture import A2A_ZONE_NM, CALLIN_LUA, CALLIN_LUA_DELAY_S, CALLIN_MIN_NM, CALLIN_REACH_NM, RED_LONG_RANGE
from .support_caps import SUPPORT_CAP_ZONE_NM
from .routes import AVOID_NM, FT, NM, RAID_IP_NEAR_NM, RAID_SA11_NM, Wpt, avoid_circles, bearing, dist, offset
from .strike_tasks import KPH

F = VehicleGroup.Formation
BLUE_CALLIN_TAGS = ("BASECAP", "CVCAP")    # v0.41.112: the blue patrols that are called in with the alert pairs (the tanker / AWACS guards stay with their asset)
BLUE_CALLIN_CV_NM = 60        # the carrier CAP answers a hotspot at most this far from its station: the boat is not left bare (judgment call)
RAID_PUSH_NM = 10             # v0.41.29: a raid's PUSH, this far from its marshal toward the target (blue's is up to 10 nm)
RAID_MSHL_MIN_NM = 60         # ...its marshal is at least this far from the target (judgment call: well outside blue's Patriot reach)
RAID_MPS = 232.0              # a red raid's speed (450 kts), the same figure its placement always used
RAID_MIN_NM = 40              # ...a raid with no time to hold starts no closer than this to its target (it is late instead)
RAID_ESCORT_AHEAD_NM = 4.0    # v0.41.296 (XO 2026-11-05: "the Su-27s are in front of their package"; he first thought 10 nm too much): the fleet raid's escort group flies this far AHEAD of the bomber group it guards. JUDGMENT CALL: no public source gives a spacing (Chipman 1990 says Su-27s "may be tasked to escort" Badgers / Backfires; CIMSEC's Backfire piece has no formation detail)
RAID_ECHELON_NM = 1.5         # ...and the bomber groups of the fleet raid fly in a loose echelon: group by group this far to the side of the line (centred on it), each one RAID_GROUP_GAP_S behind the last. JUDGMENT CALL, same as above
RAID_GROUP_GAP_S = 60         # v0.41.108: the bomber groups of a big raid follow each other, this far apart (judgment call)
RAID_ROUTE_SAMS = 99            # v0.41.256: red SAM sites along a fleet raid's way in that are built in the mission (judgment call: the default is 2; the unit limit still binds)
RAID_SWEEP_LEAD_S = 90        # ...and the raid's sweep escorts fly this far ahead of the first bomber group (judgment call)
RAID_HOLD_MAX_S = 600         # ...and one with plenty of time appears at most 10 min before it must push
RAID_EGRESS_NM = 30           # ...off target it turns 40 degrees off its way in and leaves this far before heading home     # a fighter on station engages only inside this circle round it (long-range shooters / the rest): no chasing
ARM_LAUNCH_NM = 40            # v0.41.84: a red SEAD flight fires its Kh-31P this far from the SAM site (S36b: the standoff launch of the SEAD raid) (judgment call: inside the 60 nm the Kh-31 page gives, with margin for a low launch)
COVER_FIELDS_MAX = 4          # v0.41.220 (XO 2026-10-31): a raid scramble also builds the defences of the fields whose Patriot / HAWK cover the raid's target, nearest first, at most this many (units: a full field is about 30; judgment call)
RAID_SUPPLY_UNITS = 16        # ...and the supply sites round a raid's target are built before the raiders and the alert pairs, at most this many units (v0.41.221: a site's buildings count like wrecks, so that is a dozen sites or more; judgment call: the raid's own load had used the whole 250 before the late supply call)
COVER_AAA_NM = 5              # ...and a covering neighbour's AAA only when the target is this close to it (AAA reaches a few km, not 25 to 40 nm; judgment call)
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
RAID_EDGE = True              # v0.41.282 (XO 2026-11-04: "I give up with procedurally generated schedules"): the fleet raid is a SETPIECE. Its bombers and escorts spawn already airborne at the
                              # edge of the map on the raid's bearing (they came from Mozdok round the north, beyond the map), with no marshal, ramp, taxi or gate. They are activated once the
                              # SEAD flag is set AND the time has come that puts them on the intercept point RAID_MEET_LEAD_S after blue. Story, not simulation: judgment call
RAID_EDGE_MARGIN_NM = 10      # ...the spawn is this far inside the map edge
RAID_EDGE_MAX_NM = 330        # ...and at most this far from the carrier (judgment call: Tu-22M3 fuel for the way in plus the way home to Mozdok)
RAID_EDGE_MIN_ACT_S = 60      # ...the earliest activation; a spawn that would need to be earlier is moved in along the route instead
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
RAID_IP_MAX_NM = 210          # v0.41.301: was 185, the point moved out 25 nm. The longest dash from the hold point to the intercept point (v0.41.267: was 160, but the bombers' way in starts 160-165 nm out at Level 3: no point was ever in range; judgment call, tune in DCS)
RAID_BEND_MAX_NM = 280        # v0.41.268 (XO 2026-11-04): the longest dash by way of a blue field (hold -> field -> intercept point); judgment call from fuel at high and fast, tune in DCS
RAID_IP_STEP_NM = 5           # candidate points along the bombers' way in, this far apart
RAID_IP_LEG_NM = 10           # the orbit leg at the intercept point, across the bombers' line
RAID_IP_LANE_PTS = 12         # waypoint budget for the bends of the dash lane round SAM circles
                              # v0.41.287 (XO 2026-11-04: "every SAM threatening the intercept line"): RAID_BLOCK_MAX (the old cap of 2 blocking sites, PR 2) is retired;
                              # every live site tm.raid_inbound_sites finds now gets its own SEAD/DEAD flight, not just the minimum needed to open a lane
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
BUILDING_GAP_M = 55.0         # v0.41.295 (XO 2026-11-05: a depot's warehouses and ammo bunker overlapped, 30 to 38 m apart): the least distance between two buildings of one site, centre to centre. Judgment call: a DCS warehouse is about 30 to 40 m long; measured on XO's rsup_064


# v0.41.376 (S10): the layout of a supply site's buildings, (u, v) in metres from the block centre, per part in SUPPLY_BUILDINGS / SUPPLY_PLANTS order (a damaged
# site uses the first n). u along the road, v away from it. SOURCES (rules section 6): ammunition is stored in earth-covered magazines kept apart by the DoD
# explosives safety standards (DoD Manual 6055.09, now DESR 6055.09; intermagazine distances are set by full-scale test and depend on the explosive weight and the
# magazines' orientation; an older Army lesson gives 235 ft (72 m) for 10,000 lb net explosive weight; firmness: MEDIUM that magazines stand apart by 70 m and up,
# LOW on any exact figure, the tables were not read). Fuel farms are rows of tanks with the pump house at one end (general practice, no figure). JUDGMENT CALLS:
# warehouses and tanks 70 m apart in a row (DCS building 30 to 40 m long, `BUILDING_GAP_M` 55 m least gap); bunkers dispersed 170 and 280 m out from the row.
SITE_LAYOUT = {
    AssetKind.DEPOT: [(-40, 0), (-90, 170), (40, 0), (90, 280)],            # warehouse, bunker, warehouse, bunker
    AssetKind.FUEL: [(-105, 0), (-35, 0), (35, 0), (110, 0)],               # three tanks in a row, the store at the end
    "REFINERY": [(-140, 0), (-70, 0), (0, 0), (70, 0), (140, 0)],
    "FACTORY": [(-140, 0), (-70, 0), (0, 0), (70, 0), (140, 0)],
}


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
        staged_ok = RAID_STAGE_ON and (not bool(ex.get("land"))) and cvg is not None and not aim and apt_r is not None and not self._raid_edge_on(package)
        if self._raid_edge_on(package):
            mshl = self._raid_edge(dx, dy, ex["brg"])                       # v0.41.282: the bombers' way in starts at the map edge
        if staged_ok:
            mshl = self._raid_marshal_out(mshl, ba, w1, dx, dy)          # v0.41.261: outside the missiles' reach
        return ba, w1, mshl, staged_ok, apt_r

    def _raid_edge_on(self, package) -> bool:
        """v0.41.282: a carrier raid by the bomber wing (not a land raid, not an aimed one) is the edge-spawn setpiece."""
        ex = package.extra or {}
        cvb = self.state.bases.get(package.objective.target_id)
        return bool(RAID_EDGE and cvb is not None and self.ship.get(cvb.id) is not None and not ex.get("land") and not (ex.get("aim") or "")
                    and ex.get("bomber_wing") and ex.get("brg") is not None)

    def _raid_edge(self, dx, dy, brg):
        """The point where the ray from the carrier on `brg` leaves the map (RAID_EDGE_MARGIN_NM inside it), at most RAID_EDGE_MAX_NM out."""
        b = self.t.bounds                                      # x runs north (bottom..top), y east (left..right)
        m = RAID_EDGE_MARGIN_NM * NM
        c, s_ = math.cos(math.radians(brg)), math.sin(math.radians(brg))
        ts = []
        if c > 1e-6:
            ts.append((b.top - m - dx) / c)
        elif c < -1e-6:
            ts.append((b.bottom + m - dx) / c)
        if s_ > 1e-6:
            ts.append((b.right - m - dy) / s_)
        elif s_ < -1e-6:
            ts.append((b.left + m - dy) / s_)
        ts = [t_ for t_ in ts if t_ > 0]
        t = min(min(ts) if ts else 0.0, RAID_EDGE_MAX_NM * NM)
        return offset(dx, dy, brg, t)

    def _raid_edge_spawn(self, package, edge_xy, V):
        """v0.41.282: where the setpiece's raiders appear and when they may. Blue's intercept-point time was recorded by the interceptors' routes (`_edge_blue`, built first); the
        bombers must be on the point RAID_MEET_LEAD_S after that. From the map edge when the flight there takes less than that, else moved in along the line (never earlier
        than RAID_EDGE_MIN_ACT_S). -> (spawn xy, earliest activation s). The SEAD flag is a second condition on top of the time (see `_late_edge`)."""
        rsp = (getattr(self, "_rsp", {}) or {}).get(package.id) or {}
        ip = (rsp.get("ip") or {}).get("ip")
        tb = (getattr(self, "_edge_blue", {}) or {}).get(package.id)
        if ip is None or tb is None:
            return edge_xy, float(RAID_EDGE_MIN_ACT_S)
        t_arr = tb + RAID_MEET_LEAD_S
        d_ip = dist(edge_xy[0], edge_xy[1], ip[0], ip[1])
        d_sp = min(d_ip, max(0.0, V * (t_arr - RAID_EDGE_MIN_ACT_S)))
        xy = edge_xy if d_sp >= d_ip else offset(ip[0], ip[1], bearing(ip[0], ip[1], edge_xy[0], edge_xy[1]), d_sp)
        return xy, max(float(RAID_EDGE_MIN_ACT_S), t_arr - d_sp / V)

    def _late_edge(self, g, seconds, flag) -> None:
        """Late activation for a setpiece group: the time has passed AND the SEAD flag is set (both conditions in one trigger)."""
        g.late_activation = True
        trig = triggers.TriggerOnce(comment=f"setpiece {g.name}")
        trig.add_condition(condition.TimeAfter(int(seconds)))
        if flag:
            trig.add_condition(condition.FlagIsTrue(int(flag)))
        trig.add_action(action.ActivateGroup(g.id))
        self.m.triggerrules.triggers.append(trig)

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
        """v0.41.287 (XO 2026-11-04: "every SAM threatening the intercept line", not the old minimal-combo search, PR 2/v0.41.267): every live red
        SAM site whose reach touches the bombers' straight way in (`tm.raid_inbound_sites`) is ignored for the lane geometry (so none counts as
        live) and gets its own SEAD/DEAD flight -- not just the fewest sites needed to open a lane.
        -> (site ids, intercept result with those sites ignored or None). ([], result) when nothing threatens the line (the result may still be
        None: no SAM-free point at all, not this package's problem to fix)."""
        ex = package.extra or {}
        cvb = self.state.bases.get(package.objective.target_id)
        if cvb is None or ex.get("bomber_wing") not in self.state.assets or ex.get("brg") is None:
            return [], self._raid_intercept(package, geom, hold)
        dx, dy = ex.get("dest") or (cvb.x, cvb.y)
        ids = [a.id for a, _r in tm.raid_inbound_sites(self.state, (dx, dy), ex["brg"], ex["bomber_wing"])]
        if not ids:
            return [], self._raid_intercept(package, geom, hold)
        ip = self._raid_intercept(package, geom, hold, ignore=ids)
        if ip is not None:
            return ids, ip
        if ex.get("land") or ex.get("aim"):
            return ids, None
        return ids, self._raid_bent(package, geom, hold, ignore=ids)

    def _raid_ip_points(self, package, w1, mshl) -> list:
        """v0.41.289 (XO 2026-11-04: the battle where his ruler is, not out over the featureless steppe): the candidate intercept points on the bombers' way in, NEAREST
        FIRST: on the raid's bearing from RAID_IP_NEAR_NM out to the route's outer point w1, then on from w1 toward the marshal, every RAID_IP_STEP_NM.
        -> [((x, y), nm from w1; negative = inside it), ...]. (Before: the same line from w1 out only, searched furthest first.)"""
        ex = package.extra or {}
        cvb = self.state.bases[package.objective.target_id]
        dx, dy = ex.get("dest") or (cvb.x, cvb.y)
        step = RAID_IP_STEP_NM * NM
        d_w1 = dist(dx, dy, w1[0], w1[1])
        out = []
        s = min(RAID_IP_NEAR_NM * NM, d_w1)
        while s < d_w1 - 1:
            out.append((offset(dx, dy, ex["brg"], s), (s - d_w1) / NM))
            s += step
        L = dist(w1[0], w1[1], mshl[0], mshl[1])
        if L >= 1:
            ux, uy = (mshl[0] - w1[0]) / L, (mshl[1] - w1[1]) / L
            out += [((w1[0] + ux * k * step, w1[1] + uy * k * step), k * RAID_IP_STEP_NM) for k in range(int(L / step) + 1)]
        else:
            out.append((tuple(w1), 0.0))
        return out

    def _raid_bent(self, package, geom, hold, ignore=()):
        """v0.41.268 (PR 3; XO 2026-11-04: "the F-14s have so much time to wait on orbit they could overfly on blue bases and get closer"): the intercept lane when none is clear
        straight from the hold point. The dash goes hold -> a blue field -> the intercept point, each leg bent round the SAM circles; the point is (v0.41.289) the NEAREST from RAID_IP_NEAR_NM out on the bombers'
        way in that some field reaches within RAID_BEND_MAX_NM (the shortest way by field when several do). Same result shape as `_raid_intercept`, plus "via": [(x, y, field name)].
        v0.41.287: `ignore` = sites the raid SEAD is sent against (treated as dead for this geometry, as `_raid_intercept` already does).
        -> dict or None (no field, or no point reachable: the interceptors hold at their station)."""
        ex = package.extra or {}
        if ex.get("land") or ex.get("aim"):
            return None
        try:
            ba, w1, mshl, staged_ok, apt_r = self._raid_axis(package, (hold[0], hold[1]))
        except (KeyError, AttributeError):
            return None
        circles = [(cx, cy, r) for i_, cx, cy, r in self._raid_circles(package) if i_ not in ignore]
        fields = [b for b in self.state.bases.values() if b.kind == BaseKind.AIRFIELD and b.id not in self.state.assets
                  and not any(dist(b.x, b.y, cx, cy) < r * NM for cx, cy, r in circles)]
        if not fields:
            return None
        for P, s_nm in self._raid_ip_points(package, w1, mshl):          # v0.41.289: nearest first, from RAID_IP_NEAR_NM
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
            perp = ex["brg"] + 90                                           # v0.41.289: across the bombers' line (bearing w1 -> marshal breaks for a point inside w1)
            for sgn in (1, -1):
                P2 = offset(P[0], P[1], perp if sgn > 0 else perp + 180, RAID_IP_LEG_NM * NM)
                if not any(dist(P2[0], P2[1], cx, cy) < r * NM for cx, cy, r in circles):
                    return {"ip": P, "ip2": P2, "lane": xy[1:-1], "from_w1_nm": round(s_nm), "via": [(b.x, b.y, b.name)], "path_nm": round(_n / NM)}
        return None

    def _raid_intercept(self, package, geom, hold, ignore=()):
        """v0.41.265: where the fleet raid's interceptors dash to. On the bombers' way in (marshal to the route's outer point `w1`, beyond which they are in range of the fleet),
        the point (v0.41.289: nearest first from RAID_IP_NEAR_NM, `_raid_ip_points`; was the furthest out from w1) that (a) is outside every live SAM's circle the fighters keep out of (`_zone_sams`), (b) is at most RAID_IP_MAX_NM from the hold point `hold`, and
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
        for P, s_nm in self._raid_ip_points(package, w1, mshl):          # v0.41.289: nearest first, from RAID_IP_NEAR_NM (was: furthest out first, from w1)
            if dist(hold[0], hold[1], P[0], P[1]) > RAID_IP_MAX_NM * NM or any(dist(P[0], P[1], cx, cy) < r * NM for cx, cy, r in circles):
                continue
            pts = avoid_circles([Wpt("HOLD", hold[0], hold[1], 0, 0), Wpt("IP", P[0], P[1], 0, 0)], circles, RAID_IP_LANE_PTS, 1)
            xy = [(w.x, w.y) for w in pts]
            if not all(self._seg_clear(xy[i], xy[i + 1], circles) for i in range(len(xy) - 1)):
                continue
            perp = ex["brg"] + 90                                           # v0.41.289: across the bombers' line
            for sgn in (1, -1):
                P2 = offset(P[0], P[1], perp if sgn > 0 else perp + 180, RAID_IP_LEG_NM * NM)
                if not any(dist(P2[0], P2[1], cx, cy) < r * NM for cx, cy, r in circles):
                    return {"ip": P, "ip2": P2, "lane": xy[1:-1], "from_w1_nm": round(s_nm)}
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
        unseen_ = not getattr(self, "_detect_full", True)                               # v0.41.346 (Phase 7a): an unseen package (detection.cast = "barcap") draws no red reactive pair (blue's pairs below are unchanged)
        picks = reactive.plan_red(st, d, rr, tx, ty, base_n, blue_f, used, ENEMY_FIGHTERS, bearing, self._hold_drawn) if not (fleet_obj or unseen_) else []
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
            self._alerts[-1]["sq"] = pk.get("sq", "")
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
            manifest.add("enemy_air", a.id, names, ac=pk["type"], grp=g.name)
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
        side = 1
        if rh is not None:
            side = 1 if zlib.crc32(aim.encode()) % 2 == 0 else -1                # one side per site, the same every build
            bx, by = offset(cx, cy, rh + 90 * side, ROAD_OFF_M)
            if not seac.site_ok(bx, by):                                         # that side is sea or water: the other side
                side = -side
                bx, by = offset(cx, cy, rh + 90 * side, ROAD_OFF_M)
            if not seac.site_ok(bx, by):
                rh = None
        ring = BUILDING_GAP_M / (2 * math.sin(math.pi / n)) if n > 1 else 0.0      # v0.41.295: the old ring, kept as the last fallback
        # v0.41.376 (XO musing 2, S10): rows, not a ring. u runs along the road (`rh`, else `hdg`), v away from it. See SITE_LAYOUT.
        axis = rh if rh is not None else hdg
        away = axis + 90 * side
        lay = SITE_LAYOUT.get(variant) or SITE_LAYOUT.get(kind) or []
        def at(ox, oy, u, v):
            x, y = offset(ox, oy, axis if u >= 0 else axis + 180, abs(u))
            return offset(x, y, away if v >= 0 else away + 180, abs(v))
        spots = None
        if len(lay) >= n:
            cands = [(bx, by)] + [offset(bx, by, ang, rad) for rad in (60.0, 120.0, 200.0, 300.0) for ang in range(0, 360, 45)]      # not in the water: the whole layout moves, never squeezed
            for ox, oy in cands:
                cand = [at(ox, oy, u, v) for u, v in lay[:n]]
                if all(seac.site_ok(x, y) for x, y in cand):
                    spots = cand
                    break
        if spots is None:                                                          # nothing fits: the old ring, as before
            spots = [offset(bx, by, k * (360 / n) + hdg, ring) for k in range(n)]
            if not all(seac.site_ok(x, y) for x, y in spots):
                for ang in range(0, 360, 45):
                    bx2, by2 = offset(bx, by, ang, ring + 30.0)
                    cand = [offset(bx2, by2, k * (360 / n) + hdg, ring) for k in range(n)]
                    if all(seac.site_ok(x, y) for x, y in cand):
                        spots = cand
                        break
        for k, vt in enumerate(parts[:n]):
            x, y = spots[k]
            nm = f"{aim}|b{k + 1}"          # b: never clashes with a guard vehicle `<aim>|<n>` in the same site
            sg = self.m.static_group(country, nm, vt, mapping.Point(x, y, self.t), heading=hdg + (k * 37 % 61 - 30))      # a little turn per building, so a site does not look like a parade
            sg.units[0].name = nm
            names.append(nm)
            self._bld_xy.setdefault(aim, []).append((x, y))          # v0.41.309: where each building stands, for the SLAM-ER aim points
        return names

    def _spawn_raid_target(self, package, base, aim, dx, dy, manifest):
        """Put the thing under attack on the map: a field's garrison, a fuel farm / depot, or a column of friendly troops. They are what the
        raiders bomb, so the intercepting player sees what is at stake. Small groups (a handful of vehicles or statics)."""
        from . import raids, ground
        st, d, r = self.state, self.d, self.vrng
        kind = raids.aim_kind(aim)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        if kind == "sam":                               # S36b: the SAM site under SEAD attack is already on the map (the field's batteries)
            return
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

    # ---- bomber raid on the fleet: already en route from the first second, along a real path from their base ----------------
    def _spawn_raid(self, package, sx_, sy_, tot_s, geom, manifest):
        st, d, r = self.state, self.d, self.vrng
        ex = package.extra
        if not ex:
            return
        cvb = st.bases[package.objective.target_id]
        aim = ex.get("aim", "") or ""
        sead_r = bool(ex.get("sead"))                            # S36b (XO 2026-11-11): a SEAD raid on a blue SAM site: its "bombers" are the SEAD flights, they fire from standoff and turn home
        launch_ = None
        dx, dy = (ex.get("dest") or (cvb.x, cvb.y))              # where the raiders are going: the field, a supply site, a garrison or a sector
        cvg = self.ship.get(cvb.id)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        station = (sx_, sy_)
        ba, w1, mshl, staged_ok, apt_r = self._raid_axis(package, station)          # v0.41.265: one place for the marshal and the outer point (the interceptors' dash point uses them too)
        V = RAID_MPS
        edge = self._raid_edge_on(package)
        t_act = 0.0
        if edge:
            mshl, t_act = self._raid_edge_spawn(package, mshl, RAID_MPS)          # v0.41.282: the setpiece: appears at the map edge, once SEAD is done
        edge_flag = ((getattr(self, "_rsp", {}) or {}).get(package.id) or {}).get("flag")
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
            if sead_r:                                          # the way in without the points inside the launch ring, ending on the Kh-31P launch point ARM_LAUNCH_NM from the site
                pts_ = self._arm_pts(path, dx, dy)
                launch_ = offset(dx, dy, bearing(dx, dy, *pts_[-1]), ARM_LAUNCH_NM * NM)
                path = pts_ + [launch_]
                t_tgt = arrive + dist(sx_, sy_, *launch_) / V
        if standoff:
            # v0.41.256 (XO 2026-11-03: no SAMs across the mountains, so blue's F-15s could bum-rush the bombers): the red SAM sites whose ring touches the bombers' way in
            # (the route starts at most 220 nm from the fleet) are live in the mission, RAID_ROUTE_SAMS of them beyond the ones already built; the unit limit still binds
            near_ = ((getattr(self, "_rsp", {}) or {}).get(package.id) or {}).get("ip")                  # v0.41.285 (XO 2026-11-04): every route SAM is live; the unit limit trims the ones furthest from the intercept point
            self._spawn_opfor_ground(package, dx, dy, manifest, list(path), route_sites=RAID_ROUTE_SAMS, route_near=(near_["ip"] if near_ else launch), all_sams=bool(ex.get("setpiece")))
        ox, oy = launch if standoff else (launch_ if launch_ is not None else (dx, dy))               # where the route ends: the launch point, else the target
        L = sum(dist(*path[i], *path[i + 1]) for i in range(len(path) - 1))
        stg = self._raid_stage(ex, ba, path, arrive, V, dx, dy, L) if (staged_ok and standoff) else None
        t_leave = stg["T_push"] if stg else t_tgt - L / V      # v0.41.261: a staged raid pushes when it has assembled (and blue's CAP is up), see _raid_stage
        hold_until, act_ = None, 0.0
        if edge:                                               # v0.41.282: appears at the start of its route, activated at t_act (and the SEAD flag)
            back_ = L
            (sx, sy), remaining = path[0], path[1:]
            hit_s = t_act + L / V
        elif t_leave >= 0:                                       # it holds at its marshal until it must push, appearing at most RAID_HOLD_MAX_S before
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

        fin_ = "ARM" if sead_r else ("BASE" if bool(ex.get("land")) else ("LAUNCH" if standoff else "FLEET"))
        sead_tgt = (self.base_ad.get(cvb.id) or {}).get(aim.rsplit("_", 1)[1]) if sead_r else None          # the site's mission group (Patriot "pat", HAWK "hawk")
        back0 = 0.0 if hold_until is not None else back_
        def start_at(shift_s):
            """Where a group starts and which points it still has to fly, `shift_s` seconds later (+) or earlier (-) than the raid's lead."""
            if edge:                                           # later: behind the spawn point on the line; earlier: that far ahead along the route
                if shift_s >= 0:
                    p0 = path[0]
                    return (offset(p0[0], p0[1], bearing(path[1][0], path[1][1], p0[0], p0[1]), shift_s * V) if shift_s else p0), path[1:], None, t_act
                p_, si = tm.point_back_along(path, min(L, max(RAID_MIN_NM * NM * 0.5, L + shift_s * V)))
                return p_, path[max(1, si):], None, t_act
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

        mshl_lvl = [0]                                         # S26: the next free marshal level for an unstaged group

        def build_group(name, cls, count, task_cls, bomber=False, shift=0.0, behind_nm=0.0, lateral_nm=0.0):
            pos, rem, hold, act = start_at(shift)
            if behind_nm and rem:
                pos = offset(pos[0], pos[1], bearing(rem[0][0], rem[0][1], pos[0], pos[1]), behind_nm * NM)      # (negative: ahead of its start)
            if lateral_nm and edge and rem:                    # v0.41.296: the echelon: the whole route is shifted to the side, leg by leg, not only the start
                _prev, _rem2 = pos, []
                for q in rem:
                    _rem2.append(offset(q[0], q[1], bearing(_prev[0], _prev[1], q[0], q[1]) + 90, lateral_nm * NM)); _prev = q
                pos = offset(pos[0], pos[1], bearing(pos[0], pos[1], rem[0][0], rem[0][1]) + 90, lateral_nm * NM)
                rem = _rem2
            nm_ = (["PUSH"] + ["ING"] * (len(rem) - 2) + [fin_]) if hold is not None else (["ING"] * (len(rem) - 1) + [fin_])
            sl = stg["plan"].get(name) if (stg and hold is not None) else None          # v0.41.261: a staged raid's group: on the marshal from the start, or off the runway
            m_alt = alt - (sl["mk"] * RAID_MSHL_STEP_M if sl else 0.0)
            if sl is None and hold is not None:                # S26 (run 12-38-58: three groups on one marshal point at one level collided at t=0): an unstaged group on the marshal gets its own level too
                m_alt = alt - mshl_lvl[0] * RAID_MSHL_STEP_M
                mshl_lvl[0] += 1
            r_alt = m_alt if (sl or m_alt != alt) else alt     # v0.41.263: a staged group keeps its own level the whole way (they used to climb to one common level and meet)
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
            for k, q in enumerate(rem):
                wp = g.add_waypoint(pt(*q), r_alt, 450 * KPH, nm_[k])
                if k == len(rem) - 1 and bomber:
                    if sead_r:                                  # S36b: the SEAD flight fires its Kh-31P at the site's radars from the launch point (an ARM task on the site's group), then turns home
                        wp.tasks.append(task.OptROE(task.OptROE.Values.OpenFire))
                        if sead_tgt is not None:
                            ca_ = task.ControlledTask(task.AttackGroup(sead_tgt.id, weapon_type=task.WeaponType.ARM, group_attack=True))
                            ca_.stop_after_time(int(hit_s + shift + ARM_WINDOW_S)); wp.tasks.append(ca_)
                    elif land and apt is not None:
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
            for k, q in enumerate(home_):
                g.add_waypoint(pt(*q), r_alt, 450 * KPH, "RTB" if k == len(home_) - 1 else "AVD")
            g.points[0].tasks.append(task.OptRTBOnBingoFuel(True))
            g.set_skill(skill)
            if edge:
                self._late_edge(g, act, edge_flag)
            elif act >= 30 and not g.late_activation:
                self._late(g, act)
            return g

        def sizes(n, cap=4):
            """pydcs makes one group of at most 4: a bigger raid is several groups of nearly equal size (12 -> 4+4+4, 6 -> 3+3). A staged raid's bombers go in pairs (RAID_BOMBER_BATCH)."""
            k = max(1, math.ceil(n / cap))
            return [n // k + (1 if i < n % k else 0) for i in range(k)]

        if land:
            cls_b, task_b = getattr(planes, ex.get("raider", "Su_24M")), (task.SEAD if sead_r else (task.GroundAttack if aim else task.RunwayAttack))
            load = enemy_arm_loadout(ex.get("raider", "Su_24M")) if sead_r else (enemy_land_bomber_loadout("Tu_22M3") if ex.get("raider") == "Tu_22M3" else enemy_strike_loadout(ex.get("raider", "Su_24M")))      # v0.41.355 (Phase 10a): the Tu-22M3 land strike carries OFAB-250 racks, no Kh-22, no anti-ship task
        else:
            cls_b, task_b = planes.Tu_22M3, task.AntishipStrike
            load = enemy_bomber_loadout("Tu_22M3")
        if not load:
            self.warns.append(f"{ex.get('raider', 'Tu-22M3')}: no bomb or missile found; the raid is unarmed.")
        bomber_gs, nb_ = [], 0
        gap_ = RAID_STAGED_GAP_S if stg else RAID_GROUP_GAP_S
        bsz_ = sizes(ex["bombers"], RAID_BOMBER_BATCH if stg else 4)
        lat_ = [(i_ - (len(bsz_) - 1) / 2.0) * RAID_ECHELON_NM if len(bsz_) > 1 else 0.0 for i_ in range(len(bsz_))]         # v0.41.296: echelon, centred on the route
        for gi, n_ in enumerate(bsz_):         # v0.41.108: a big raid is several groups, a minute apart on the same route
            g = build_group(f"Raid Bomber {gi + 1}", cls_b, n_, task_b, bomber=True, shift=gi * gap_, lateral_nm=lat_[gi])
            names = []
            for u in g.units:
                nb_ += 1
                u.name = f"RAID-B-{nb_}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", ex["bomber_wing"], names, ac=ex.get("raider", "Tu_22M3"), raid_base=cvb.id, raid_aim=aim, raid_label=package.objective.description.replace("Intercept a raid on ", "").replace("Intercept an air attack on ", ""),
                         raid_arrive_s=float(hit_s + gi * gap_), raid_group=g.name)
            bomber_gs.append(g)
        self._spawn_raid_target(package, cvb, aim, dx, dy, manifest)
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
                    eg = build_group(f"Raid Sweep {ei + 1}", getattr(planes, ex["escort_type"]), n_, task.FighterSweep, shift=-RAID_SWEEP_LEAD_S - 15 * ei)
                else:
                    ci = ei - n_sweep
                    bg = bomber_gs[ci * len(bomber_gs) // max(1, len(esz) - n_sweep)]
                    eg = build_group(f"Raid Escort {ci + 1}", getattr(planes, ex["escort_type"]), n_, task.Escort, shift=bomber_gs.index(bg) * gap_, behind_nm=(-RAID_ESCORT_AHEAD_NM if edge else 3), lateral_nm=lat_[bomber_gs.index(bg)])
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
