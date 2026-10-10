"""Route geometry and timing, BMS-style: everyone shares MARSHAL -> PUSH -> IP -> TARGET -> EGRESS.

Flights arrive at the marshal point, hold (stacked 1,000 ft apart), and leave together at the PUSH time.
Pure geometry, no pydcs mission objects, so the kneeboard and briefing reuse it.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from .aircraft import RouteProfile
from .models import Role

NM = 1852.0
FT = 0.3048
KT = 0.514444


def bearing(x1, y1, x2, y2) -> float:
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 360


def offset(x, y, hdg_deg, dist_m):
    h = math.radians(hdg_deg)
    return x + dist_m * math.cos(h), y + dist_m * math.sin(h)


def dist(x1, y1, x2, y2) -> float:
    return math.hypot(x2 - x1, y2 - y1)


@dataclass
class Wpt:
    name: str
    x: float
    y: float
    alt_ft: int
    speed_kts: int
    note: str = ""
    action: str = ""        # "" | HOLD | BOMB | SEAD | SWEEP | CAS | ESCORT | CAPORBIT
    eta_s: float = 0.0      # seconds after mission start (filled by assign_times)
    agl: bool = False       # altitude is metres/feet above ground (the player's TGT sits on the ground so sensors and weapons can slave to it)
    rad: bool = False       # alt_ft is height above the ground (the LOW tier): DCS "radio altitude", so the flight follows the terrain
    orbit: bool = False     # a fighter stand-off point: the flight holds here (an orbit) instead of flying on to the target


@dataclass
class Geometry:
    bx: float; by: float; tx: float; ty: float
    hdg: float; d: float
    mshl: tuple; push: tuple; ip: tuple; egr: tuple; cap1: tuple; cap2: tuple
    dep: tuple = (0.0, 0.0)
    tier: object = None     # profiles.Tier: the altitude profile from the IP on (None = the role altitude); the player's flight
    tiers: dict = None      # {(role, id(profile)): Tier} one per kind of flight in the package (an escort never inherits a striker's LOW)
    stand: dict = None      # {(role, id(profile)): (x, y, [SAM types], nm short)} sweeps and escorts that stop at the edge of SAM cover


CARRIER_DEP_NM = 10.0      # Case III: the departure circle is 10 nm from the boat, and the flight leaves on the briefed departure radial


def make_geometry(bx, by, tx, ty, p: RouteProfile, mshl: tuple | None = None, carrier: bool = False) -> Geometry:
    """mshl: where the package marshals. It is chosen by the caller BEHIND the base (away from the enemy) so the departure and
    the hold are in friendly, defended airspace; the route then runs marshal -> PUSH -> IP -> target."""
    d = dist(bx, by, tx, ty)
    hdg = bearing(bx, by, tx, ty)
    # PUSH is ~10 nm from the marshal point toward the target (as in BMS); the long straight cruise from there to the IP is the ingress
    ip_d = max(d - p.ip_nm * NM, 0.5 * d)
    at = lambda dd: offset(bx, by, hdg, dd)
    if mshl is None:
        mshl = offset(bx, by, hdg + 180, 15 * NM)
    ip_xy = at(ip_d)
    push_nm = max(2.0, min(10.0, 0.4 * dist(*mshl, *ip_xy) / NM))
    push_xy = offset(*mshl, bearing(*mshl, tx, ty), push_nm * NM)
    cap_d = max(0.45 * d, min(60 * NM, d))
    cap1 = at(cap_d)
    # DEP: where the flight is established and on its way. 10 nm from a carrier (the departure radial points at the marshal), 8 nm from a
    # land base (6 for slow types), on the straight line to the marshal point and never beyond 40% of the way there.
    dep_nm = CARRIER_DEP_NM if carrier else p.dep_nm
    dep = offset(bx, by, bearing(bx, by, *mshl), min(dep_nm * NM, 0.4 * dist(bx, by, *mshl)))
    return Geometry(bx, by, tx, ty, hdg, d, mshl, push_xy, ip_xy,
                    offset(tx, ty, hdg + 100, p.egress_nm * NM), cap1, offset(*cap1, hdg + 90, p.cap_leg_nm * NM), dep)


def plan_route(role: Role, own_base: tuple, g: Geometry, p: RouteProfile, *, is_player: bool,
               tanker_xy: tuple | None, stack_idx: int = 0, spawn: tuple | None = None, spawn_alt_ft: int = 0,
               spawn_kts: int = 0) -> list[Wpt]:
    """Waypoints from start (takeoff for the player, an in-air 'just departed' spawn for AI) to egress. RTB is added by the builder."""
    wp: list[Wpt] = []
    bx, by = own_base
    if is_player:
        wp.append(Wpt("DEP", *g.dep, p.depart_alt_ft, p.depart_kts, "Climb out, check in with AWACS"))
    else:
        sx, sy = spawn if spawn else g.dep
        wp.append(Wpt("SPAWN", sx, sy, spawn_alt_ft or p.depart_alt_ft, spawn_kts or p.depart_kts, "Airborne start"))

    if role == Role.CAP:
        alt = p.cap_alt_ft + 1000 * stack_idx
        wp.append(Wpt("CAP1", *g.cap1, alt, p.cap_kts, f"Racetrack, {p.cap_leg_nm}nm legs", "CAPORBIT"))
        wp.append(Wpt("CAP2", *g.cap2, alt, p.cap_kts))
        return wp

    wp.append(Wpt("MSHL", *g.mshl, p.marshal_alt_ft + 1000 * stack_idx, p.marshal_kts,
                  "Hold here until PUSH time", "HOLD"))
    alt = p.alt_ft.get(role, 20000)
    key = (role, id(p))
    t = g.tiers.get(key) if g.tiers else g.tier                # per kind of flight when the builder worked them out; the single tier otherwise
    so = None if is_player else (g.stand or {}).get(key)
    ialt, irad = (t.alt_ft, t.rad) if (t is not None and t.changed) else (alt, False)          # the tier applies from the IP on
    wp.append(Wpt("PUSH", *g.push, alt, p.push_kts, "Push on time, check in with AWACS"))
    wp.append(Wpt("IP", *g.ip, ialt, p.ip_kts, "Weapons armed, master arm", rad=irad))
    # The player's TGT is on the ground target at 0 AGL so pods, weapons and the WSO / Jester can slave to it. The wingmen follow the player, and AI-only flights
    # never get a ground-level point (they would descend to it).
    if role == Role.STRIKE:
        wp.append(Wpt("TGT", g.tx, g.ty, 0 if is_player else ialt, p.attack_kts, p.tgt_note, "BOMB", agl=is_player, rad=irad and not is_player))
    elif role == Role.SEAD and is_player:
        wp.append(Wpt("TGT", g.tx, g.ty, 0, p.attack_kts, "SEAD site. You set standoff", "SEAD", agl=True))
    elif role == Role.SEAD:
        wp.append(Wpt("SEAD", *offset(g.tx, g.ty, g.hdg + 180, max(8, p.ip_nm - 4) * NM), ialt, p.attack_kts, "HARM launch point", "SEAD", rad=irad))
    elif role == Role.SWEEP and so:
        wp.append(Wpt("TGT", so[0], so[1], alt, p.cap_kts, f"SWEEP: stop here, {so[3]:.0f} nm short of the target, outside {'/'.join(so[2])} cover", "SWEEP", orbit=True))
    elif role == Role.SWEEP:
        wp.append(Wpt("TGT", g.tx, g.ty, alt, p.attack_kts + 30, "SWEEP: clear the airspace", "SWEEP"))
    elif role == Role.CAS:
        wp.append(Wpt("TGT", g.tx, g.ty, 0 if is_player else ialt, p.attack_kts, "CAS: check in with JTAC (COMM1 CH4)", "CAS", agl=is_player, rad=irad and not is_player))
    elif so:
        wp.append(Wpt("TGT", so[0], so[1], ialt, p.cap_kts, f"ESCORT: hold here, {so[3]:.0f} nm short of the target, outside {'/'.join(so[2])} cover", "ESCORT", rad=irad, orbit=True))
    else:
        wp.append(Wpt("TGT", g.tx, g.ty, ialt, p.attack_kts, "ESCORT: cover the strikers over target", "ESCORT", rad=irad))
    if not (so and role in (Role.SWEEP, Role.ESCORT)):         # a stand-off flight never crosses the target area: it goes home from its hold
        wp.append(Wpt("EGR", *g.egr, ialt, p.egress_kts, "Exit threat area", rad=irad))
    if len(wp) + 2 > p.max_points:
        raise ValueError(f"route has {len(wp) + 2} points but the airframe holds {p.max_points}")
    return wp


def leg_seconds(a: Wpt, b: Wpt, climb: bool = False) -> float:
    v = max(120, (a.speed_kts + b.speed_kts) / 2) * KT
    return dist(a.x, a.y, b.x, b.y) / v * (1.12 if climb else 1.04)


def assign_times(wps: list[Wpt], t0: float, push_s: float | None = None) -> None:
    """Fill eta_s along the route starting at t0. At a HOLD point the flight waits so that it CROSSES THE NEXT POINT (PUSH)
    exactly at push_s: it leaves the hold at push_s minus the leg time."""
    t = t0
    for i, w in enumerate(wps):
        if i > 0:
            t += leg_seconds(wps[i - 1], w, climb=(i == 1))
        w.eta_s = t
        if w.action == "HOLD" and push_s is not None:
            leave = push_s - (leg_seconds(w, wps[i + 1]) if i + 1 < len(wps) else 0)
            t = max(t, leave)


def hold_leave_s(wps: list[Wpt], push_s: float) -> float:
    """When a flight must leave its HOLD point to cross the next point at push_s."""
    for i, w in enumerate(wps):
        if w.action == "HOLD":
            return push_s - (leg_seconds(w, wps[i + 1]) if i + 1 < len(wps) else 0)
    return push_s


OBJECTIVE_ACTIONS = ("BOMB", "SEAD", "SWEEP", "CAS", "ESCORT", "CAPORBIT")


def objective_wp(wps: list[Wpt]) -> Wpt | None:
    """The waypoint a flight is on station at for TOT purposes (target / HARM point / CAP station)."""
    return next((w for w in wps if w.action in OBJECTIVE_ACTIONS), None)


def _floor_ft(x: float, y: float) -> int:
    """Lowest altitude (MSL) a flight may be spawned at: 1,500 ft over the highest ground near that point, or 6,000 ft without a ground-height scan."""
    from . import relief
    h = relief.max_near_m(x, y, 5 * NM)
    return 6000 if h is None else int(math.ceil((h / FT + 1500) / 500.0) * 500)


def in_progress(wps: list[Wpt], home: tuple) -> list[Wpt] | None:
    """A flight whose schedule started BEFORE the mission did. `wps` already carries absolute times (assign_times, first point at a negative time).
    Returns the route as it stands at mission time 0: a SPAWN point where the flight is by then (interpolated along its leg, or at the hold point
    if it is still holding) followed by the points it still has to fly. None if it is already back on the ground."""
    hx, hy = home
    rtb = Wpt("RTB", hx, hy, 0, 300)
    end_t = wps[-1].eta_s + leg_seconds(wps[-1], rtb)
    if end_t <= 0:
        return None
    pts = list(wps) + [rtb]
    pts[-1].eta_s = end_t
    for i in range(len(wps)):
        a, b = pts[i], pts[i + 1]
        ts = a.eta_s
        if a.action == "HOLD":
            ts = b.eta_s - leg_seconds(a, b)                       # when it leaves the hold
            if a.eta_s <= 0 < ts:                                  # still orbiting at the marshal point
                return [Wpt("SPAWN", a.x, a.y, max(a.alt_ft, _floor_ft(a.x, a.y)) if a.rad else a.alt_ft, a.speed_kts)] + list(wps[i:])
        te = b.eta_s
        if ts <= 0 < te:
            f = (0 - ts) / max(1.0, te - ts)
            sp = Wpt("SPAWN", a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f, max(_floor_ft(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f), int(a.alt_ft + (b.alt_ft - a.alt_ft) * f)) if (a.rad or b.rad) else int(a.alt_ft + (b.alt_ft - a.alt_ft) * f), a.speed_kts)
            return [sp] + list(wps[i + 1:])
    return None
