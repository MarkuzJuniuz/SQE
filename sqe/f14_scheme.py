"""S103e: the player's waypoint scheme of the plain F-14B (the F-14A/B has THREE numbered waypoints).

Heatblur's manual (Mission Editor page, "Waypoints Types (F-14A/B Only)") and XO's probe of 2026-11-18 (slot B-B, `.claude/crew-chief-internal/tools/f14b_wp_probe.py`): waypoints 1 to 3 are the route points of the Mission Editor,
the landing waypoint is the Home Base, and every other point is a Navigation Target Point named by a code (FP, IP, ST, DP, HA, DLWP1-3, DLST, DLFP; pydcs `group.add_nav_target_point`). Plain waypoints
4 and up, and a second point with the same code, read wrong in the probe (slot B-A): this module only CHOOSES; `MissionBuilder._f14ab_scheme` applies the choice to the player's own group.

Which planner point becomes which (XO 2026-11-20, the card reads in the order you fly it; the route shape itself is unchanged, the whole route stays on the kneeboard, only DEP is left off it):
  every job:  waypoint 1 = MSHL, 2 = PUSH (a job with neither, a BARCAP, starts at its station; a Fighter Sweep has no marshal, so its PUSH is waypoint 1); HA = the nearest live SAM site (from the caller; the card's "hostile area").
  ground (STRIKE):  3 = IP (else TGT);  ST = TGT (when IP is waypoint 3);  DP = EGR.  Release / JSOW / SLAM points, DESC and LOW are card-only (FP is not used: it is the INS fix point).
  fighter jobs (TARCAP, escort, sweep, BARCAP, fleet defence):  3 = the station (CAP1), also written as the IP nav point (same place; the card shows 3);  DP = CAP2 (else the EGR).
                    A fighter job with no station (it flies a strike-shaped route): 3 = TGT, IP = its own IP point, DP = EGR.
Every other planner point (DEP, AVD, ...) and the trailing DIVERT / TKR / BULLS are card-only: the tanker is found by its TACAN (COMMS), the bullseye is in the jet.
Pure functions, no pydcs."""
from __future__ import annotations

GROUND_ROLES = ("STRIKE", "SEAD", "CAS")
MAX_WAYPOINTS = 3


def choose(route: list, ground: bool) -> tuple:
    """route = the planner points between takeoff and landing (objects with .name, .action, .orbit). -> (keep, st, ip, dp): `keep` = ascending indices of the (at most 3) points that stay numbered waypoints,
    `st` = index of the surface target point (ground jobs; None otherwise), `ip` = index written as the IP nav point (a fighter's station, which is also kept; None otherwise),
    `dp` = index written as the DP nav point (CAP2, else EGR; None when the route has neither)."""
    names = [w.name for w in route]

    def at(*cands):
        for c in cands:
            if c in names:
                return names.index(c)
        return None

    if not route:
        return [], None, None, None
    pick = [at("MSHL"), at("PUSH")]
    st = ip = dp = None
    egr = at("EGR")
    if ground:
        pick.append(at("IP", "TGT"))
        tgt = at("TGT")
        st = tgt if tgt is not None and tgt not in pick else None
        dp = egr
    else:
        mid = next((i for i, w in enumerate(route) if getattr(w, "orbit", False)), None)
        if mid is None:
            mid = at("CAP1")
        if mid is not None:
            pick.append(mid)
            ip = mid                                            # the station is waypoint 3 and also the IP nav point (same place)
        else:                                                   # a fighter job with no station (a sweep with no clear one) flies a strike-shaped route: its own IP is the IP nav point, the target waypoint 3
            pick.append(at("TGT"))
            ip = at("IP")
        cap2 = at("CAP2")
        dp = cap2 if cap2 is not None else egr
    keep = []
    for i in pick:
        if i is not None and i not in keep:
            keep.append(i)
    if not keep:                                                # no MSHL, PUSH or station: the first real point (not the climb-out) so the jet has a waypoint at all
        keep = [next((i for i, nm in enumerate(names) if nm not in ("DEP", "SPAWN")), 0)]
    keep = sorted(keep)[:MAX_WAYPOINTS]
    if dp in keep:
        dp = None
    if st in keep:
        st = None
    return keep, st, ip, dp
