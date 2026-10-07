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


@dataclass
class Geometry:
    bx: float; by: float; tx: float; ty: float
    hdg: float; d: float
    mshl: tuple; push: tuple; ip: tuple; egr: tuple; cap1: tuple; cap2: tuple
    dep: tuple = (0.0, 0.0)


def make_geometry(bx, by, tx, ty, p: RouteProfile, mshl: tuple | None = None) -> Geometry:
    """mshl: where the package marshals. It is chosen by the caller BEHIND the base (away from the enemy) so the departure and
    the hold are in friendly, defended airspace; the route then runs marshal -> PUSH -> IP -> target."""
    d = dist(bx, by, tx, ty)
    hdg = bearing(bx, by, tx, ty)
    # PUSH sits just ahead of home plate (well out from the target); the long straight cruise to the IP is the ingress
    ip_d = max(d - p.ip_nm * NM, 0.5 * d)
    push_d = max(2 * NM, min(12 * NM, 0.15 * d, ip_d - 8 * NM))
    at = lambda dd: offset(bx, by, hdg, dd)
    if mshl is None:
        mshl = offset(bx, by, hdg + 180, 25 * NM)
    cap_d = max(0.45 * d, min(60 * NM, d))
    cap1 = at(cap_d)
    dep = offset(bx, by, bearing(bx, by, *mshl), min(8 * NM, 0.4 * dist(bx, by, *mshl)))
    return Geometry(bx, by, tx, ty, hdg, d, mshl, at(push_d), at(ip_d),
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
    wp.append(Wpt("PUSH", *g.push, alt, p.push_kts, "Push on time, check in with AWACS"))
    wp.append(Wpt("IP", *g.ip, alt, p.ip_kts, "Weapons armed, master arm"))
    if role == Role.STRIKE:
        wp.append(Wpt("TGT", g.tx, g.ty, alt, p.attack_kts, p.tgt_note, "BOMB"))
    elif role == Role.SEAD:
        wp.append(Wpt("SEAD", *offset(g.tx, g.ty, g.hdg + 180, max(8, p.ip_nm - 4) * NM), alt, p.attack_kts, "HARM launch point", "SEAD"))
    elif role == Role.SWEEP:
        wp.append(Wpt("TGT", g.tx, g.ty, alt, p.attack_kts + 30, "SWEEP: clear the airspace", "SWEEP"))
    elif role == Role.CAS:
        wp.append(Wpt("TGT", g.tx, g.ty, alt, p.attack_kts, "CAS: check in with JTAC (COMM1 CH4)", "CAS"))
    else:
        wp.append(Wpt("TGT", g.tx, g.ty, alt, p.attack_kts, "ESCORT: cover the strikers over target", "ESCORT"))
    wp.append(Wpt("EGR", *g.egr, alt, p.egress_kts, "Exit threat area"))
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
