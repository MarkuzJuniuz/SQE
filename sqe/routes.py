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
    action: str = ""        # "" | HOLD | BOMB | SEAD | SWEEP | CAS | CAPORBIT
    eta_s: float = 0.0      # seconds after mission start (filled by assign_times)


@dataclass
class Geometry:
    bx: float; by: float; tx: float; ty: float
    hdg: float; d: float
    mshl: tuple; push: tuple; ip: tuple; egr: tuple; cap1: tuple; cap2: tuple


def make_geometry(bx, by, tx, ty, p: RouteProfile) -> Geometry:
    d = dist(bx, by, tx, ty)
    hdg = bearing(bx, by, tx, ty)
    push_d = max(d - p.push_nm * NM, 0.55 * d)
    mshl_d = max(push_d - 45 * NM, 0.30 * d)
    ip_d = max(d - p.ip_nm * NM, push_d + 0.4 * (d - push_d))
    at = lambda dd: offset(bx, by, hdg, dd)
    cap_d = max(0.45 * d, min(60 * NM, d))
    cap1 = at(cap_d)
    return Geometry(bx, by, tx, ty, hdg, d, at(mshl_d), at(push_d), at(ip_d),
                    offset(tx, ty, hdg + 100, p.egress_nm * NM), cap1, offset(*cap1, hdg + 90, p.cap_leg_nm * NM))


def plan_route(role: Role, own_base: tuple, g: Geometry, p: RouteProfile, *, is_player: bool,
               tanker_xy: tuple | None, stack_idx: int = 0) -> list[Wpt]:
    """Waypoints from start (takeoff for the player, an in-air spawn for AI) to egress. RTB is added by the builder."""
    wp: list[Wpt] = []
    bx, by = own_base
    if is_player:
        wp.append(Wpt("DEP", *offset(bx, by, bearing(bx, by, *g.mshl), min(10 * NM, 0.15 * g.d)),
                      p.depart_alt_ft, p.depart_kts, "Climb out, check in with AWACS"))
        if tanker_xy:
            wp.append(Wpt("TKR", *tanker_xy, p.aar_alt_ft, p.aar_kts, "Top off if needed"))
    else:
        tgt_pt = g.cap1 if role == Role.CAP else g.mshl
        dd = dist(bx, by, *tgt_pt)
        f = min(0.65, max(0.2, 1.0 - (min(90 * NM, max(25 * NM, 0.4 * dd)) / max(dd, 1))))
        sx, sy = bx + (tgt_pt[0] - bx) * f, by + (tgt_pt[1] - by) * f
        wp.append(Wpt("SPAWN", sx, sy, p.marshal_alt_ft - 3000, p.depart_kts + 100, "Airborne start"))

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
        wp.append(Wpt("SEAD", *offset(g.tx, g.ty, g.hdg + 180, 30 * NM), alt, p.attack_kts, "HARM launch point", "SEAD"))
    elif role == Role.SWEEP:
        wp.append(Wpt("SWP", g.tx, g.ty, alt, p.attack_kts + 30, "Clear the airspace", "SWEEP"))
    elif role == Role.CAS:
        wp.append(Wpt("CAS", g.tx, g.ty, alt, p.attack_kts, "Check in with JTAC (COMM1 CH4)", "CAS"))
    else:
        wp.append(Wpt("ESC", g.tx, g.ty, alt, p.attack_kts, "Escort over target", ""))
    wp.append(Wpt("EGR", *g.egr, alt, p.egress_kts, "Exit threat area"))
    if len(wp) + 2 > p.max_points:
        raise ValueError(f"route has {len(wp) + 2} points but the airframe holds {p.max_points}")
    return wp


def leg_seconds(a: Wpt, b: Wpt, climb: bool = False) -> float:
    v = max(120, (a.speed_kts + b.speed_kts) / 2) * KT
    return dist(a.x, a.y, b.x, b.y) / v * (1.12 if climb else 1.04)


def assign_times(wps: list[Wpt], t0: float, push_s: float | None = None) -> None:
    """Fill eta_s along the route starting at t0. A HOLD point waits until push_s, then everything after shifts."""
    t = t0
    for i, w in enumerate(wps):
        if i > 0:
            t += leg_seconds(wps[i - 1], w, climb=(i == 1))
        if w.action == "HOLD" and push_s is not None:
            w.eta_s = t
            t = max(t, push_s)
        else:
            w.eta_s = t
