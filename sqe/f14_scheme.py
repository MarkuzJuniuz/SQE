"""S103e: the player's waypoint scheme of the plain F-14B (the F-14A/B has THREE numbered waypoints).

Heatblur's manual (Mission Editor page, "Waypoints Types (F-14A/B Only)") and XO's probe of 2026-11-18 (slot B-B, `.claude/crew-chief-internal/tools/f14b_wp_probe.py`): waypoints 1 to 3 are the route points of the Mission Editor,
the landing waypoint is the Home Base, and every other point is a Navigation Target Point named by a code (FP, IP, ST, DP, HA, DLWP1-3, DLST, DLFP; pydcs `group.add_nav_target_point`). Plain waypoints
4 and up, and a second point with the same code, read wrong in the probe (slot B-A): this module only CHOOSES; `MissionBuilder._f14ab_scheme` applies the choice to the player's own group.

Which planner point becomes which (XO 2026-11-21, from his Jester screenshot: the pilot's destination menu offers WPT 1-3, FIXED POINT, INITIAL POINT, SURFACE TARGET, HOME BASE and MAN; DP / HA are not selectable, DP is gone, HA stays as a nav point in case the HSD shows it; FP is not used, it is the INS fix point). The card reads in the order you fly it; the route shape itself is unchanged, the whole route stays on the kneeboard, only DEP is left off it:
  every job:  waypoint 1 = MSHL, 2 = PUSH (a Fighter Sweep has no marshal, so its PUSH is waypoint 1), 3 = EGR when the route has one (else empty); HA = the nearest live SAM site (from the caller; the card's "hostile area").
  ground (STRIKE):  IP = the IP;  ST = TGT.  DESC, LOW, REL / JSOW / SLAM are card-only (the last two and DESC are AI-only anyway).
  fighter jobs with a station (TARCAP, escort, sweep, fleet defence):  DP = CAP2 (the other end of the racetrack).  With an EGR (an escort): 3 = EGR and IP = CAP1; without one: 3 = CAP1.  ST = the package's ground target where it has one (a TARCAP or escort of a strike, DEAD or CAS package).  A BARCAP has no MSHL or PUSH: CAP1 and CAP2 are waypoints 1 and 2, no IP / DP / ST.
  a fighter job with no station (it flies a strike-shaped route):  IP = its IP point, ST = TGT, 3 = EGR.
Every other planner point (DEP, AVD, ...) and the trailing DIVERT / TKR / BULLS are card-only: the tanker is found by its TACAN (COMMS), the bullseye is in the jet.
Pure functions, no pydcs."""
from __future__ import annotations

GROUND_ROLES = ("STRIKE", "SEAD", "CAS")
MAX_WAYPOINTS = 3


def choose(route: list, ground: bool) -> tuple:
    """route = the planner points between takeoff and landing (objects with .name, .action, .orbit). -> (keep, st, ip, dp): `keep` = ascending indices of the (at most 3) points that stay numbered waypoints,
    `st` = index written as the ST nav point (a strike's TGT), `ip` = index written as the IP nav point (a strike's IP, an escort's CAP1 when EGR is waypoint 3), `dp` = index written as the DP nav point
    (CAP2 of a fighter's station); any may be None, and one that is also a kept point is not written again (a BARCAP's CAP1 / CAP2)."""
    names = [w.name for w in route]

    def at(*cands):
        for c in cands:
            if c in names:
                return names.index(c)
        return None

    if not route:
        return [], None, None, None
    mshl, push, egr = at("MSHL"), at("PUSH"), at("EGR")
    pick = [mshl, push, egr]
    dp = None
    if ground:
        ip, st = at("IP"), at("TGT")
    else:
        mid = next((i for i, w in enumerate(route) if getattr(w, "orbit", False)), None)
        if mid is None:
            mid = at("CAP1")
        if mid is not None:
            st = None                                           # XO 2026-11-21: a station fighter's ST is the package's ground target (the caller adds it), never CAP2
            dp = at("CAP2")
            if mshl is None and push is None:                   # a BARCAP: no marshal or push, the racetrack ends are waypoints 1 and 2
                pick, ip, dp = [mid, dp], None, None
            elif egr is not None:                               # an escort with a station and an egress: IP = CAP1 (flown before the egress), waypoint 3 = EGR
                ip = mid
            else:                                               # no egress: waypoint 3 = the station (CAP1)
                pick, ip = [mshl, push, mid], None
        else:                                                   # a fighter job with no station flies a strike-shaped route
            ip, st = at("IP"), at("TGT")
    keep = []
    for i in pick:
        if i is not None and i not in keep:
            keep.append(i)
    if not keep:                                                # nothing to number: the first real point (not the climb-out) so the jet has a waypoint at all
        keep = [next((i for i, nm in enumerate(names) if nm not in ("DEP", "SPAWN")), 0)]
    return sorted(keep)[:MAX_WAYPOINTS], st, ip, dp
