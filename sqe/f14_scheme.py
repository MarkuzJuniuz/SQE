"""S103d: the player's waypoint scheme of the plain F-14B (the F-14A/B has THREE numbered waypoints).

Heatblur's manual (Mission Editor page, "Waypoints Types (F-14A/B Only)") and XO's probe of 2026-11-18 (slot B-B, `tools/f14b_wp_probe.py`): waypoints 1 to 3 are the route points of the Mission Editor,
the landing waypoint is the Home Base, and every other point is a Navigation Target Point named by a code (FP, IP, ST, DP, HA, DLWP1-3, DLST, DLFP; pydcs `group.add_nav_target_point`). Plain waypoints
4 and up, and a second point with the same code, read wrong in the probe (slot B-A): this module only CHOOSES; `MissionBuilder._f14ab_scheme` applies the choice to the player's own group.

Which planner point becomes which (SQE's judgment call, the route shape itself is unchanged: the whole route stays on the kneeboard):
  ground jobs (STRIKE, SEAD, CAS):  waypoint 1 = PUSH (else MSHL, else the first point), 2 = IP (else the HARM / release point, else TGT), 3 = EGR (else the last point);
                                    ST = the TGT point; IP as a nav target point only when IP is not already waypoint 2.
  fighter jobs (TARCAP, escort, sweep, BARCAP, fleet defence):  1 = PUSH (else MSHL, else the first point), 2 = the station (the orbit point CAP1), 3 = EGR (else the last point);
                                    DP = what the flight covers (the package's target, the fleet or the field, from the caller), HA = the nearest live SAM site (from the caller).
Every other planner point (DEP, MSHL, AVD, DESC, LOW, REL, CAP2, ...) and the trailing DIVERT / TKR / BULLS are card-only: the tanker is found by its TACAN (COMMS), the bullseye is in the jet.
Pure functions, no pydcs."""
from __future__ import annotations

GROUND_ROLES = ("STRIKE", "SEAD", "CAS")
MAX_WAYPOINTS = 3


def choose(route: list, ground: bool) -> tuple:
    """route = the planner points between takeoff and landing (objects with .name, .action, .orbit). -> (keep, st, ip): `keep` = ascending indices of the (at most 3) points that stay numbered waypoints,
    `st` = index of the surface target point (ground jobs; None otherwise), `ip` = index of an IP that is NOT kept (it becomes the IP nav target point; None otherwise)."""
    n = len(route)
    if n == 0:
        return [], None, None
    names = [w.name for w in route]

    def at(*cands):
        for c in cands:
            if c in names:
                return names.index(c)
        return None

    st = next((i for i, w in enumerate(route) if w.name == "TGT"), None) if ground else None
    first = at("PUSH", "MSHL")
    if first is None:
        first = 0
    last = at("EGR")
    if last is None:
        last = n - 1
    if ground:
        mid = at("IP", "SEAD", "JSOW", "SLAM", "REL", "LOW", "TGT")
    else:
        mid = next((i for i, w in enumerate(route) if getattr(w, "orbit", False)), None)
        if mid is None:
            mid = at("CAP1", "TGT")
    keep = []
    for i in (first, mid, last):
        if i is not None and i not in keep:
            keep.append(i)
    others = [i for i in range(n) if i not in keep]
    while len(keep) < min(MAX_WAYPOINTS, n) and others:         # a route with no EGR or no distinct middle point: fill from what is left, spread along the route
        i = others[len(others) // 2]
        keep.append(i)
        others.remove(i)
    keep = sorted(keep)[:MAX_WAYPOINTS]
    ip = at("IP")
    return keep, st, (ip if ip is not None and ground and ip not in keep else None)
