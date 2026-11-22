"""Route geometry and timing, BMS-style: everyone shares MARSHAL -> PUSH -> IP -> TARGET -> EGRESS.

Flights arrive at the marshal point, hold (stacked 1,000 ft apart), and leave together at the PUSH time.
Pure geometry, no pydcs mission objects, so the kneeboard and briefing reuse it.
"""
from __future__ import annotations
import heapq
import math
from dataclasses import dataclass
from . import samtier
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
    aim: tuple | None = None  # v0.41.299: a release point short of the target (JDAM, SLAM-ER): the (x, y) the bombing task is aimed at; None = this point itself
    hold_to: float | None = None  # S38: an AI SEAD's HARM point: the flight orbits here until this time (the strikers' time over target + a window), then goes on to EGR


@dataclass
class Geometry:
    bx: float; by: float; tx: float; ty: float
    hdg: float; d: float
    mshl: tuple; push: tuple; ip: tuple; egr: tuple; cap1: tuple; cap2: tuple
    dep: tuple = (0.0, 0.0)
    tier: object = None     # profiles.Tier: the altitude profile from the IP on (None = the role altitude); the player's flight
    tiers: dict = None      # {(role, id(profile)): Tier} one per kind of flight in the package (an escort never inherits a striker's LOW)
    ai_player: bool = False  # test mode: the player's slot is flown by the AI, so the player's flight gets the AI stand-off too
    stand: dict = None      # {(role, id(profile)): (x, y, [SAM types], nm short)} sweeps and escorts that stop at the edge of SAM cover
    cas_floor: tuple = None  # S31a: (ft, reason) an AI CAS flight flies from the IP on because short-range air defence reaches the target or the run-in (profiles.cas_floor); None = no floor
    sweep: bool = False     # a Fighter Sweep package: no marshal, DEP - PUSH - station - home
    jsow_keep: list = None  # [(x, y, nm)]: live SAMs a JSOW launch point stays this far from (v0.41.3; v0.41.46: nm is each entry's own ring, the target cluster's SAMs included)
    carrier: bool = False   # v0.41.12: the flight's base is a carrier (only then a DEP point after take-off)
    launch_nm: float = 0.0  # v0.41.299: a Standoff Strike's launch distance from the target (SLAM_LAUNCH_NM); 0 = the JSOW rule
    sa10_avoid: list = None # [(x, y, nm)]: live medium / long-range SAMs (not the target) an AI flight's route bends around (v0.41.11; all gate SAMs since v0.41.20)
    prefer: tuple = None    # S140e: (x, y) of red's nearest patrol station or fighter field seen from the target (`FighterStations._red_approach`): a detour with two ways of about the same length takes the side away from it
    shared: dict = None     # S140b2: {(start, end) of a lane-0 leg: its turn points}, the package's one PUSH -> IP detour (`shared_leg`); the builder gives each package's geometry one
    all_rings: list = None  # S140b1: [(x, y, nm)] EVERY live, unsuppressed SAM in AVOID_NM (the fighters' `_zone_sams` set, no skip): the rings an AI flight's transit, fighter and home legs go round


STANDOFF_EGRESS_NM = 25.0  # a HARM or JSOW flight egresses this far beyond its launch point, straight back out along its own approach
JSOW_AXIS_DEG = 30.0       # the JSOW flight's approach is this far off the HARM shooters' axis (side chosen by the builder, away from other SAM sites)
JSOW_LAUNCH_NM = 30.0      # an AI JSOW flight's launch point. v0.41.46 (was 20): XO's 2026-10-20 run, AGM-154As released from 20,000 ft at 45-65 km (24-35 nm), and a 20 nm point sat
                           # on the target's own SA-11 ring (about 19 nm): two Squids died to it. 30 nm is inside the release range seen and about 10 nm clear of that ring (judgment call)
JSOW_HIGH_ALT_FT = 33000      # ...and when it is pushed out past JSOW_LAUNCH_NM, the flight releases from this high
JSOW_MAX_NM = 45.0           # a JSOW launch point is never farther than this from its target (v0.41.3 run: AGM-154As released at 30-40 nm from 33,000 ft hit; was 40)
JSOW_KEEP_HIGH_NM = 40.0     # a pushed-out JSOW flight is high, where an SA-10 reaches farther: its launch point stays this far from one (v0.41.3 run: 30.6 nm lost all four)
JDAM_BREAK_NM = 12.0       # v0.41.312 (XO 2026-11-06): after the release the flight breaks away this far to the SIDE (about 90 degrees), not back along the approach (see JDAM_RELEASE_NM)
JDAM_RELEASE_NM = 5.0      # v0.41.312: was 8.0. XO's Viper 5 run (2026-11-05) never released: a U-turn at the release point makes the AI cut the corner 10 km short (the SLAM-ER Hornet cut 7.5 km short and still fired, its reach is 130 nm). A 90-degree break cuts about 4 to 7 km (turn radius at 420-500 kt, 45 degrees of bank: judgment call), so 5 nm keeps that turn inside the 9.3 nm cue.
                           # (older note, v0.41.299, XO 2026-11-05): an AI JDAM striker releases this far short of the target and turns home, instead of overflying it with the bomb task on the target waypoint.
                           # JUDGMENT CALL from published figures: DCS players' tests put the release cue at 9.3 nm (GBU-31, 30,000 ft, just under Mach 1) to 12.5 nm (GBU-38, 33,000 ft, just over Mach 1)
                           # (forum.dcs.world "jdam 31 distance reduced"); real JDAM: "up to approximately 15 miles" (GlobalSecurity). 8 nm sits inside the lowest of those. Nothing published on where the AI releases
JDAM_ALT_FT = 30000        # v0.41.299: ...from this height (the figures above are at 30,000 ft and up; range grows with release altitude). The LOW tier is closed to these flights: a JDAM released at 500 ft has almost no reach
SLAM_LAUNCH_NM = 120.0     # v0.41.299: a Standoff Strike's launch point (AGM-84H SLAM-ER, over 155 nm in the open sources; red alert pairs reach about 130 nm): judgment call, clamped to 0.8 of the route
LOW_LEG_NM = 30.0          # v0.41.16: a low-level (terrain-following) attack descends this far from the target
SWEEP_PUSH_NM = 15.0       # v0.41.12: a sweep's PUSH, this far from its base toward the target
AGM88_LAUNCH_NM = 35.0      # v0.41.11: 35 (was 30): the Sukhumi SA-10 engaged HARM shooters at 54-57 km (31 nm); the AI fires from 35-38 nm anyway.
                           # an AI SEAD flight's HARM launch point: at the edge of what an SA-10 first reaches (it opened fire at about 55 km in testing); 21 nm put the launch point deep inside it
CARRIER_DEP_NM = 10.0      # Case III: the departure circle is 10 nm from the boat, and the flight leaves on the briefed departure radial


def make_geometry(bx, by, tx, ty, p: RouteProfile, mshl: tuple | None = None, carrier: bool = False, vary_deg: float = 0.0) -> Geometry:
    """mshl: where the package marshals. It is chosen by the caller BEHIND the base (away from the enemy) so the departure and
    the hold are in friendly, defended airspace; the route then runs marshal -> PUSH -> IP -> target."""
    d = dist(bx, by, tx, ty)
    hdg = bearing(bx, by, tx, ty)
    # PUSH is ~10 nm from the marshal point toward the target (as in BMS); the long straight cruise from there to the IP is the ingress
    ip_d = max(d - p.ip_nm * NM, 0.5 * d)
    at = lambda dd: offset(bx, by, hdg, dd)
    if mshl is None:
        mshl = offset(bx, by, hdg + 180, 15 * NM)
    ip_xy = at(ip_d) if not vary_deg else offset(tx, ty, hdg + 180 + vary_deg, p.ip_nm * NM)       # S104c: an F-117A sortie comes in on its own bearing (`f117.approach_deg`), 0 = the straight line as every other flight
    push_nm = max(2.0, min(10.0, 0.4 * dist(*mshl, *ip_xy) / NM))
    push_xy = offset(*mshl, bearing(*mshl, tx, ty), push_nm * NM)
    cap_d = max(0.45 * d, min(60 * NM, d))
    cap1 = at(cap_d)
    # DEP: where the flight is established and on its way. 10 nm from a carrier (the departure radial points at the marshal), 8 nm from a
    # land base (6 for slow types), on the straight line to the marshal point and never beyond 40% of the way there.
    dep_nm = CARRIER_DEP_NM if carrier else p.dep_nm
    dep = offset(bx, by, bearing(bx, by, *mshl), min(dep_nm * NM, 0.4 * dist(bx, by, *mshl)))
    g_ = Geometry(bx, by, tx, ty, hdg, d, mshl, push_xy, ip_xy,
                  offset(tx, ty, hdg + (100 if vary_deg >= 0 else -100), p.egress_nm * NM), cap1, offset(*cap1, hdg + 90, p.cap_leg_nm * NM), dep)
    g_.carrier = bool(carrier)
    return g_


def jsow_launch_nm(g, jsow_side: float) -> float:
    """How far (nm) from the target an AI JSOW flight's launch point sits on its own axis. v0.41.3: it stays as far from every live long-range SAM as
    the HARM point does (the v0.41.1 runs lost whole JSOW flights to the SA-10s at 13-24 nm), moving out along its axis up to JSOW_MAX_NM (the glide
    range from altitude); v0.41.4: 40 nm from an SA-10, not the HARM shooters' 30, because the JSOW jets go in at 33,000 ft.
    v0.41.42: pulled out of plan_route so the builder can ask where the JSOW flight will launch (the escort stations itself there)."""
    if g.launch_nm > 0:                                      # v0.41.299: a Standoff Strike launches from as far out as the route allows (no SAM keep-out: the job exists only without SAM trouble)
        return max(8.0, min(g.launch_nm, g.d / NM * 0.8 - 6))
    nm = max(8.0, min(JSOW_LAUNCH_NM, g.d / NM * 0.8 - 6))
    if g.jsow_keep:
        jh_ = g.hdg + 180 + JSOW_AXIS_DEG * jsow_side
        while nm < JSOW_MAX_NM and any(dist(*offset(g.tx, g.ty, jh_, nm * NM), kx, ky) < knm * NM for kx, ky, knm in g.jsow_keep):
            nm += 1.0
    return nm


def jsow_launch_xy(g, jsow_side: float) -> tuple:
    """The (x, y) of an AI JSOW flight's launch point for this geometry."""
    return offset(g.tx, g.ty, g.hdg + 180 + JSOW_AXIS_DEG * jsow_side, jsow_launch_nm(g, jsow_side) * NM)


CAP2_FLOOR_NM = 5.0        # Phase 8: the shortest race-track leg worth flying


def cap2_point(sx: float, sy: float, axis_deg: float, leg_nm: float, margin, floor_nm: float = CAP2_FLOOR_NM, sides=(90.0, -90.0)):
    """Phase 8 (campaign rules plan, decision 22): the far end (CAP2) of a station's race-track. It lies `leg_nm` from the station (sx, sy), across the
    axis (`axis_deg` plus or minus 90; S141c: `sides` lists the offsets to try, both by default). `margin(x, y)` is how far inside the clear area that point is, in nm (zero or more = clear). All sides are tried;
    the one with more margin wins. When neither side is clear the leg is halved, down to `floor_nm`. -> (x, y), or None when even the floor leg is not clear.
    No job specifics here: the TARCAP / escort / sweep station and, later, the support CAPs (queue S9) all call it."""
    nm = max(float(leg_nm), floor_nm)
    while True:
        best = None
        for side in sides:
            x, y = offset(sx, sy, axis_deg + side, nm * NM)
            m = margin(x, y)
            if m >= 0 and (best is None or m > best[0]):
                best = (m, (x, y))
        if best is not None:
            return best[1]
        if nm <= floor_nm:
            return None
        nm = max(floor_nm, nm / 2.0)


def plan_route(role: Role, own_base: tuple, g: Geometry, p: RouteProfile, *, is_player: bool,
               tanker_xy: tuple | None, stack_idx: int = 0, spawn: tuple | None = None, spawn_alt_ft: int = 0,
               spawn_kts: int = 0, jsow: bool = False, jsow_side: float = 0, keep_out=None, agm88_deg: float = 0, rel: str = "") -> list[Wpt]:
    """Waypoints from start (takeoff for the player, an in-air 'just departed' spawn for AI) to egress. RTB is added by the builder."""
    wp: list[Wpt] = []
    bx, by = own_base
    if is_player and g.carrier:
        # v0.41.12: only off the carrier (the Case I/III departure radial). From a land base the first point after take-off is the marshal
        # point: the DEP 6 nm out at 8,000 ft, with PUSH a mile on at 26,000 ft, asked for a steep climb and a turn back over the field
        # v0.41.36: (XO) Fixed the issue where player flights from land bases show SPAWN
        # (the two unexplained crashes 3-5 min after take-off were both runway starts out of Batumi)
        wp.append(Wpt("DEP", *g.dep, p.depart_alt_ft, p.depart_kts, "Climb out, check in with AWACS"))
    elif not is_player:
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
    so = None if (is_player and not g.ai_player) else (g.stand or {}).get(key)
    ialt, irad = (t.alt_ft, t.rad) if (t is not None and t.changed) else (alt, False)          # the tier applies from the IP on
    human = is_player and not g.ai_player                    # a person flies it; in the all-AI test the player's flight is routed and tasked like any AI flight
    if role == Role.CAS and not human and g.cas_floor:        # S31a: AI CAS over short-range air defence: high from the IP, never the LOW tier (a person's route stays as it is)
        ialt, irad = max(g.cas_floor[0], ialt if not irad else 0), False
    agm88_nm = max(8.0, min(AGM88_LAUNCH_NM, g.d / NM * 0.8 - 6))        # on short routes it still leaves the IP ahead of the base
    ip_xy = g.ip
    jsow_nm = jsow_launch_nm(g, jsow_side) if (jsow and role == Role.STRIKE and not human) else max(8.0, min(JSOW_LAUNCH_NM, g.d / NM * 0.8 - 6))
    agm88_ax = g.hdg + 180 + (agm88_deg if role == Role.SEAD and not human else 0)    # v0.41.24: the builder may turn the HARM axis off a neighbouring SAM
    if role == Role.SEAD and not human and keep_out:          # under an umbrella (an SA-10 covering the target): the HARM point stays out of its reach too
        # v0.41.24: keep_out may be a list of circles (the umbrella and every other SAM the package is not sent against)
        kos_ = [keep_out] if isinstance(keep_out, tuple) else list(keep_out)
        while agm88_nm < AGM88_LAUNCH_NM + 40 and any(dist(*offset(g.tx, g.ty, agm88_ax, agm88_nm * NM), kx, ky) < knm * NM for kx, ky, knm in kos_):
            agm88_nm += 1.0
    jsow_hdg = g.hdg + 180 + JSOW_AXIS_DEG * jsow_side         # the JSOW flight comes in on its own axis, off the HARM shooters' (multi-axis)
    # v0.41.299: a release point short of the target ("JDAM": 8 nm; "SLAM": the Standoff Strike's launch point), straight in along the package axis
    rel_on = bool(rel) and role == Role.STRIKE and not human and not jsow
    rel_hdg = g.hdg + 180
    rel_nm = ((max(4.0, min(JDAM_RELEASE_NM, g.d / NM * 0.5)) if rel == "JDAM" else jsow_launch_nm(g, 0.0)) if rel_on else 0.0)
    if (role == Role.SEAD or (jsow and role == Role.STRIKE)) and not human:      # the IP sits 6 nm before the launch point (farther out than the usual IP)
        far = offset(g.tx, g.ty, agm88_ax if role == Role.SEAD else jsow_hdg, ((agm88_nm if role == Role.SEAD else jsow_nm) + 6) * NM)
        if dist(g.tx, g.ty, *far) > dist(g.tx, g.ty, *g.ip):
            ip_xy = far
    elif rel_on and rel == "SLAM":                              # the IP 6 nm before the launch point; a JDAM release keeps the usual IP (it is farther out already)
        far = offset(g.tx, g.ty, rel_hdg, (rel_nm + 6) * NM)
        if dist(g.tx, g.ty, *far) > dist(g.tx, g.ty, *g.ip):
            ip_xy = far
    if human and g.all_rings and role in (Role.STRIKE, Role.SEAD):
        ip_xy = ip_outside(g, ip_xy)                             # S140c (XO 2026-11-22): a person's IP is the point where he gets ready to shoot: outside the rings that hold the target
    # v0.41.10: deconfliction. AI flights cross PUSH and EGR on their own lane, 1.5 nm apart sideways by stack slot (at most 4.5 nm), so a
    # package's flights do not all converge on one point at one height
    lane = 0.0 if human or not stack_idx else (1 if stack_idx % 2 else -1) * min(4.5, 1.5 * ((stack_idx + 1) // 2))
    lane_xy = lambda xy: offset(xy[0], xy[1], g.hdg + 90, lane * NM) if lane else xy
    egr_xy = lambda xy: out_of_rings(xy, g.all_rings) if g.all_rings else xy      # S140b2 / S140c: an egress point never sits inside a live ring (a person's route too: the mission is the same)
    wp.append(Wpt("PUSH", *lane_xy(g.push), alt, p.push_kts, "Push on time, check in with AWACS"))
    st_ = (g.stand or {}).get(key) if role in (Role.TARCAP, Role.ESCORT, Role.SWEEP) else None
    if st_ is not None and len(st_) >= 5:
        # TARCAP and ESCORT (the package escort): a station of their own, short of the target and outside live SAM cover,
        # where they hold and shoot at what comes in range without chasing it. No IP. The TARCAP gets there first, holds its time and goes
        # home from the station; the escort holds until the last ground-attack flight is off target and leaves by the package egress when
        # that leg is clear of SAM cover (from the station otherwise). The same route for you and for the AI.
        sx_, sy_, names_, short_, egr_ok_ = st_[:5]
        why_ = f", outside {'/'.join(names_)} cover" if names_ else ""
        if g.sweep:                                            # Fighter Sweep: no marshal, straight out, station, 15 minutes or Winchester, home
            wp = [w for w in wp if w.name != "MSHL"]
            for w_ in wp:                                      # v0.41.12: its PUSH lies ahead of the base, toward the station: it climbs straight out
                if w_.name == "PUSH":
                    w_.x, w_.y = offset(bx, by, g.hdg, SWEEP_PUSH_NM * NM)
            wp.append(Wpt("CAP1", sx_, sy_, alt, p.cap_kts, f"SWEEP: station {short_:.0f} nm short of the target{why_}; clear the air, do not chase", "SWEEP", orbit=True))
        elif role == Role.TARCAP:
            wp.append(Wpt("CAP1", sx_, sy_, alt, p.cap_kts, f"TARCAP: on station {short_:.0f} nm short of the target{why_}; hold and shoot, do not chase", "TARCAP", orbit=True))
        else:
            wp.append(Wpt("CAP1", sx_, sy_, alt, p.cap_kts, f"ESCORT: hold {short_:.0f} nm short of the target{why_} until the strikers are off; do not chase", "ESCORT", orbit=True))
            if egr_ok_:
                wp.append(Wpt("EGR", *egr_xy(g.egr), ialt, p.egress_kts, "Exit with the package", rad=irad))
        if g.all_rings:                                         # S140b1 / S140c: PUSH -> station round every live ring, for a person's route too (the leg after the station is the builder's: CAP2 comes first)
            ci_ = next(k for k, w in enumerate(wp) if w.orbit)
            wp[:ci_ + 1] = avoid_circles(wp[:ci_ + 1], g.all_rings, p.max_points - (len(wp) - ci_ - 1), 1, edge=True, start=own_base, prefer=g.prefer)
        if len(wp) + 2 > p.max_points:
            raise ValueError(f"route has {len(wp) + 2} points but the airframe holds {p.max_points}")
        return wp
    if jsow and role == Role.STRIKE and not human and jsow_nm > JSOW_LAUNCH_NM:
        ialt, irad = max(ialt, JSOW_HIGH_ALT_FT), False         # a long JSOW shot goes from high up (the glide range grows with release altitude)
    if irad and dist(*ip_xy, g.tx, g.ty) > (LOW_LEG_NM + 3) * NM:
        # v0.41.16: the low leg starts LOW_LEG_NM from the target, not at the IP. The IP sits half way out on long routes (70 nm in the v0.41.14
        # Gudauta fuel-farm run): three of four F-16s flamed out at 500 ft before the target. Cruise to the IP, descend at "LOW".
        wp.append(Wpt("IP", *ip_xy, alt, p.ip_kts, "Weapons armed, master arm"))
        lx, ly = offset(g.tx, g.ty, bearing(g.tx, g.ty, *ip_xy), LOW_LEG_NM * NM)
        wp.append(Wpt("LOW", lx, ly, ialt, p.ip_kts, "Descend: low-level run in", rad=True))
    else:
        if irad and not human:
            # S28 (XO run 2026-11-11 13-30-36: Hornet 5 reached the gate with 42% fuel): with the IP within LOW_LEG_NM + 3 of the target there is no LOW point, so PUSH
            # (high) straight to the IP (152 m radar altitude) made DCS slope the descent over the whole long leg, 400 km at 150 m. A "DESC" point at cruise altitude
            # LOW_LEG_NM before the IP starts the descent there. AI only (a player keeps the old waypoints). Skipped when the airframe has no room for one more point.
            pu_ = next((w for w in wp if w.name == "PUSH"), None)
            if (pu_ is not None and dist(pu_.x, pu_.y, *ip_xy) > (LOW_LEG_NM + 3) * NM
                    and len(wp) + 1 + 2 + 2 <= p.max_points):          # + this point, TGT and EGR, the builder's two
                dx_, dy_ = offset(*ip_xy, bearing(*ip_xy, pu_.x, pu_.y), LOW_LEG_NM * NM)
                wp.append(Wpt("DESC", dx_, dy_, alt, p.ip_kts, "Start the descent: low-level run in"))
        wp.append(Wpt("IP", *ip_xy, ialt, p.ip_kts, "Weapons armed, master arm", rad=irad))
    # The player's TGT is on the ground target at 0 AGL so pods, weapons and the WSO / Jester can slave to it. The wingmen follow the player, and AI-only flights
    # never get a ground-level point (they would descend to it).
    if role == Role.STRIKE and jsow and not human:             # a JSOW slinger never crosses the site: it releases from its launch point and goes home
        wp.append(Wpt("JSOW", *offset(g.tx, g.ty, jsow_hdg, jsow_nm * NM), ialt, p.attack_kts, "JSOW launch point", "JSOW", rad=irad))
    elif rel_on:                                                # v0.41.299: releases from here, bomb task aimed at the target; the flight never crosses it
        wp.append(Wpt("SLAM" if rel == "SLAM" else "REL", *offset(g.tx, g.ty, rel_hdg, rel_nm * NM), ialt, p.attack_kts,
                      ("Standoff Strike launch point: SLAM-ER on the target, then home" if rel == "SLAM" else f"JDAM release point, {rel_nm:.0f} nm short of the target: release and turn home"),
                      "BOMB", rad=irad, aim=(g.tx, g.ty)))
    elif role == Role.STRIKE:
        wp.append(Wpt("TGT", g.tx, g.ty, 0 if human else ialt, p.attack_kts, p.tgt_note, "BOMB", agl=human, rad=irad and not human))
    elif role == Role.SEAD and human:
        wp.append(Wpt("TGT", g.tx, g.ty, 0, p.attack_kts, "SEAD site", "SEAD", agl=True))
    elif role == Role.SEAD:
        wp.append(Wpt("SEAD", *offset(g.tx, g.ty, agm88_ax, agm88_nm * NM), ialt, p.attack_kts, "HARM launch point", "SEAD", rad=irad))
    elif role in (Role.ESCORT, Role.SWEEP) and so:
        nm_ = "ESCORT" if role == Role.ESCORT else "SWEEP"        # v0.41.60: one name per job (this branch is the old 4-tuple stop-short point; no station reaches it any more)
        wp.append(Wpt("CAP1", so[0], so[1], alt, p.cap_kts, f"{nm_}: stop here, {so[3]:.0f} nm short of the target, outside {'/'.join(so[2])} cover", nm_, orbit=True))
    elif role in (Role.ESCORT, Role.SWEEP):
        nm_ = "ESCORT" if role == Role.ESCORT else "SWEEP"        # a flight with no station of its own (stand-off setting off, or fleet-defence fighters)
        wp.append(Wpt("TGT", g.tx, g.ty, alt, p.attack_kts + 30, f"{nm_}: " + ("cover the strikers over target" if role == Role.ESCORT else "clear the airspace"), nm_))
    elif role == Role.CAS:
        wp.append(Wpt("TGT", g.tx, g.ty, 0 if human else ialt, p.attack_kts, "CAS: check in with JTAC (COMM1 CH3)", "CAS", agl=human, rad=irad and not human))
    elif so:
        wp.append(Wpt("CAP1", so[0], so[1], ialt, p.cap_kts, f"TARCAP: hold here, {so[3]:.0f} nm short of the target, outside {'/'.join(so[2])} cover", "TARCAP", rad=irad, orbit=True))
    else:
        wp.append(Wpt("TGT", g.tx, g.ty, ialt, p.attack_kts, "TARCAP: cover the strikers over target", "TARCAP", rad=irad))
    standoff = not human and (role == Role.SEAD or (jsow and role == Role.STRIKE) or rel_on)
    if standoff:
        # a HARM or JSOW flight fires from stand-off range and goes home the way it came. The package egress lies beyond the target for the
        # strikers that overfly it: in the v0.39.21 run the JSOW Hornets released, then crossed the Sukhumi cluster to it and met the Su-27s.
        sax = agm88_ax if role == Role.SEAD else (rel_hdg if rel_on else jsow_hdg)
        snm = (agm88_nm if role == Role.SEAD else (rel_nm if rel_on else jsow_nm)) + STANDOFF_EGRESS_NM
        if rel_on:
            snm = min(snm, max(rel_nm + 4.0, g.d / NM * 0.9))        # never past the flight's own base
        if rel_on and rel == "JDAM":                              # v0.41.312: break to the side (about 90 degrees) so the AI does not cut a U-turn corner short of the release point
            rx_, ry_ = offset(g.tx, g.ty, rel_hdg, rel_nm * NM)
            best_ = None
            for sd_ in (1, -1):                                   # the side that stays clearer of the SAM rings the route already avoids (right when equal or none)
                e_ = offset(rx_, ry_, g.hdg + 90 * sd_, JDAM_BREAK_NM * NM)
                clr_ = min((dist(*e_, kx, ky) - knm * NM for kx, ky, knm in (g.sa10_avoid or [])), default=0.0)
                if best_ is None or clr_ > best_[0]:
                    best_ = (clr_, e_)
            wp.append(Wpt("EGR", *egr_xy(best_[1]), ialt, p.egress_kts, "Exit: break away to the side, then home", rad=irad))
        else:
            wp.append(Wpt("EGR", *egr_xy(offset(g.tx, g.ty, sax, snm * NM)), ialt, p.egress_kts, "Exit: back out along the approach", rad=irad))
    elif not (so and role in (Role.ESCORT, Role.SWEEP, Role.TARCAP)):         # a stand-off fighter never crosses the target area: it goes home from its hold
        wp.append(Wpt("EGR", *egr_xy(lane_xy(g.egr)), ialt + (1000 * (stack_idx % 3) if lane else 0), p.egress_kts, "Exit threat area", rad=irad))
    ip_i = next((k for k, w in enumerate(wp) if w.name == "IP"), None)
    if not human and g.sa10_avoid and role in (Role.STRIKE, Role.SEAD, Role.CAS):
        # the attack legs (IP -> TGT / launch point -> EGR): the rings the flight is not sent against, as before S140b1 (a ring that holds the target is the one it comes for)
        k0 = next((k for k, w in enumerate(wp) if w.name == "PUSH"), 1)
        avoid_circles(wp, g.sa10_avoid, p.max_points, (k0 if ip_i is None else ip_i) + 1)
    if g.all_rings and role in (Role.STRIKE, Role.SEAD, Role.CAS) and ip_i is not None:
        # S140b1 (plan 2.2): the transit legs (SPAWN -> MSHL -> PUSH -> IP) go round every live ring, the flight's own target's too; a leg that starts or ends inside a ring takes its edge
        pu_i = next((k for k, w in enumerate(wp) if w.name == "PUSH"), None)
        if pu_i is not None and ip_i == pu_i + 1:
            # S140b2 (plan 2.4): the PUSH -> IP detour is one path for the whole package (lane 0), every flight's copy shifted by its lane
            pts_ = shared_leg(g, wp[pu_i], wp[ip_i], lane, p.max_points - len(wp) - 2)
            if pts_:
                pa_, pb_ = wp[pu_i], wp[ip_i]
                wp[ip_i:ip_i] = [Wpt("AVD", x, y, max(pa_.alt_ft, pb_.alt_ft), pa_.speed_kts, "Around a SAM site", rad=pa_.rad) for x, y in pts_]
            wp[:pu_i + 1] = avoid_circles(wp[:pu_i + 1], g.all_rings, p.max_points - (len(wp) - pu_i - 1), 1, edge=True, start=own_base, prefer=g.prefer)
        else:
            wp[:ip_i + 1] = avoid_circles(wp[:ip_i + 1], g.all_rings, p.max_points - (len(wp) - ip_i - 1), 1, edge=True, start=own_base, prefer=g.prefer)
    elif g.all_rings and role in (Role.TARCAP, Role.ESCORT, Role.SWEEP):
        avoid_circles(wp, g.all_rings, p.max_points, 1, edge=True, start=own_base, prefer=g.prefer)      # a fighter has no ring of its own: every leg of its route (no station here, so no orbit leg)
    if len(wp) + 2 > p.max_points:
        raise ValueError(f"route has {len(wp) + 2} points but the airframe holds {p.max_points}")
    return wp


SA10_AVOID_NM = samtier.get("SA-10", "avoid_nm")       # v0.41.11 (S90 P4: the figures live in samtier.SYSTEMS, one row per umbrella system): an AI flight's route keeps this far from a live SA-10 that is not its target (the v0.41.10 run: two JSOW
                           # flights bound for Gudauta passed 31 nm from the Sukhumi SA-10 and were shot at from 57 km)
SA10_STATION_NM = samtier.get("SA-10", "station_nm")     # v0.41.194 (XO 2026-10-29: Dodge 4's TARCAP orbit swung from 39 to 30 nm of the Sukhumi SA-10 and both Eagles died): a fighter STATION keeps this far from a live SA-10 so the orbit's near end (about 5-9 nm closer than its centre) stays outside SA10_AVOID_NM. Judgment call.
AVOID_NM = {"SA-10": SA10_AVOID_NM, "SA-11": 20.0, "SA-2": 26.0, "SA-6": 16.0, "SA-3": 15.0, "SA-5": samtier.get("SA-5", "avoid_nm")}    # v0.41.20: every gate SAM, by its reach plus a margin


def ring_nm(variant: str):
    """S140b1 (XO 2026-11-22): the ring the SQE map draws and the briefing quotes for a SAM variant is the ring the routes keep out of (`AVOID_NM`: SA-10 35, SA-5 71, SA-2 26, SA-11 20, SA-6 16, SA-3 15), else
    `samtier.RANGE_NM` (a system no route ring covers). `samtier.RANGE_NM` itself is unchanged: stations, the dormant wake, the F-117 and the threat math read it. None for a variant with neither."""
    return AVOID_NM.get(variant, samtier.RANGE_NM.get(variant))


RAID_SA11_NM = 26.0        # v0.41.276: the carrier raid's interceptors keep this far from a live SA-11 (AVOID_NM says 20). Judgment call: in XO's 2026-11-04 run the SA-11s
                           # engaged the Tomcats at 23 to 26 nm (shots of 42 to 49 km measured by the hook). Lives here (not raid_spawns.py) so threatmap.py can share it
                           # without a circular import (v0.41.287).
RAID_IP_NEAR_NM = 145.0    # v0.41.301 (XO 2026-11-05, his ruler on the run: fight 190-193 nm out, "push it 25 nm further" so the interceptors do not run dry on the X-22 barrage; the Tu-22M3 fires from its 205 nm reach before the Phoenixes fly at 190, so 145 puts the fight near 215 nm, past that reach: judgment call). Was 120. Older note: v0.41.293 (XO 2026-11-04, ruler 50.05 nm on his screenshot: "move the battlesite closer by 50nm"): was 170. The fight sat about 62 nm beyond the point (the Phoenixes fly 79 nm out from the dash), so 120 should put it near 182 nm: ESTIMATE, XO to check. Before: v0.41.289 (XO 2026-11-04: "make the actual battle where the ruler is"; beyond it the map is featureless): the carrier raid's interceptors meet the
                           # bombers from this far out, nearest point first (before: the furthest point out from 220 nm). Judgment call from XO's F10 ruler, measured at 165 to 175 nm
                           # from the carrier on his screenshot (fitted to 10 airfields). Inside the Tu-22M3's 208 nm X-22 reach on purpose: the carrier group takes the first salvos.
RAID_THREAT_OUT_NM = 165.0 # v0.41.301: was 140, moves out with the point. v0.41.293: was 190, moves in with the point. ...and the SEAD threat line (threatmap.raid_inbound_sites) runs from the target this far out: the intercept band plus the 20 nm the bombers launch
                           # beyond the fighters' station (raid_spawns.RAID_LAUNCH_OUT_NM). Was the route's outer point w1, 220 nm.


AVOID_MARGIN_NM = 2.0      # S140a: a turn point sits this far outside the ring it bends round. Source: today's value (v0.41.11 put its one turn point 2 nm outside the ring); kept so the rings keep the same clearance
AVOID_CORNERS = 12         # S140a: a ring is a 12-corner polygon for the path search; its flats (not its corners) sit AVOID_MARGIN_NM outside the ring. Judgment call: 12 corners overshoot the shortest tangent by under 2 nm on a 35 nm ring
AVOID_ROUNDS = 40          # S140a: most rounds of "search, then add the rings the best path still touches"
AVOID_TOUCH_M = 50.0       # a segment touches a ring when its closest point is this much inside the ring edge (a corner on the polygon is margin_nm outside, so it never counts)


def _seg_hits(p, q, circles) -> list:
    """Indexes of the circles (x, y, r metres) that the segment p -> q touches (its closest point lies inside r - AVOID_TOUCH_M)."""
    ax, ay = p
    vx, vy = q[0] - ax, q[1] - ay
    L2 = vx * vx + vy * vy
    hit = []
    for i, (cx, cy, r) in enumerate(circles):
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((cx - ax) * vx + (cy - ay) * vy) / L2))
        if math.hypot(ax + t * vx - cx, ay + t * vy - cy) < r - AVOID_TOUCH_M:
            hit.append(i)
    return hit


AVOID_SIDE_PCT = 10.0      # S140e: going round a ring on the far side of the leg is taken when it is within this percent of the shortest path and keeps the leg farther from `prefer` (red's fighters). Judgment call (plan 2.8)


def safe_path(a, b, circles, margin_nm: float | None = None, prefer=None):
    """S140e: `_safe_path`, and with `prefer` ((x, y) of red's nearest patrol station or fighter field) the other side of the first ring the shortest path bends round when that path is at most AVOID_SIDE_PCT percent
    longer and passes farther from `prefer` (ties keep the shortest). `prefer` None (the default) = `_safe_path` exactly."""
    best = _safe_path(a, b, circles, margin_nm)
    if prefer is None or not best:
        return best
    mg = AVOID_MARGIN_NM if margin_nm is None else margin_nm
    live = [(cx, cy, r * NM) for cx, cy, r in circles
            if math.hypot(a[0] - cx, a[1] - cy) >= r * NM and math.hypot(b[0] - cx, b[1] - cy) >= r * NM]
    cx, cy, r = min(live, key=lambda c: abs(math.hypot(best[0][0] - c[0], best[0][1] - c[1]) - (c[2] + mg * NM)))      # the ring the first turn point belongs to
    side = lambda p: (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) > 0
    alt = _safe_path(a, b, circles, margin_nm, ban=((cx, cy, r), side(best[0])))
    if not alt:
        return best
    length = lambda pts: sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip([tuple(a)] + list(pts), list(pts) + [tuple(b)]))
    if length(alt) > length(best) * (1 + AVOID_SIDE_PCT / 100.0):
        return best
    near = lambda pts: min(_seg_dist(p, q, prefer) for p, q in zip([tuple(a)] + list(pts), list(pts) + [tuple(b)]))
    return alt if near(alt) > near(best) + 1.0 else best


def _seg_dist(p, q, c) -> float:
    """Distance from the point c to the segment p -> q."""
    vx, vy = q[0] - p[0], q[1] - p[1]
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((c[0] - p[0]) * vx + (c[1] - p[1]) * vy) / L2))
    return math.hypot(p[0] + t * vx - c[0], p[1] + t * vy - c[1])


def _safe_path(a, b, circles, margin_nm: float | None = None, ban=None):
    """S140a: the turn points between a and b (x, y in metres) that keep the leg out of every circle (x, y, nm): [] when the straight leg is clear,
    None when there is no way round. Shortest path over a visibility graph (Lozano-Perez and Wesley 1979, the visibility-graph method), searched with A*.
    Each circle is a polygon of AVOID_CORNERS corners whose flats lie `margin_nm` outside it; a corner inside any circle is not a node. Lazy: only the
    circles the current best path touches are obstacles, and the search repeats until the path touches none (None after AVOID_ROUNDS rounds, or when a
    path still touches a circle with every touched circle already an obstacle). A circle that holds a or b is left out of the leg (the leg has to start
    or end there; S140b handles those legs): v0.41.11 could still bend such a leg when the closest point lay mid-leg. Ties break by node index, so
    the result is the same on every run. Ported from the probes/s140/crossings.py prototype. S140d1: `margin_nm` None = AVOID_MARGIN_NM as it stands now (`trim_margin` lowers it for one build). S140e: `ban` = ((x, y, r metres), side)
    leaves out the corners of that ring on that side of the line a -> b (the far-side search of `safe_path`)."""
    margin_nm = AVOID_MARGIN_NM if margin_nm is None else margin_nm
    live = [(cx, cy, r * NM) for cx, cy, r in circles
            if math.hypot(a[0] - cx, a[1] - cy) >= r * NM and math.hypot(b[0] - cx, b[1] - cy) >= r * NM]
    if not live:
        return []
    path = [tuple(a), tuple(b)]
    active: set = set()
    for _ in range(AVOID_ROUNDS):
        hit = set()
        for i in range(len(path) - 1):
            hit.update(_seg_hits(path[i], path[i + 1], live))
        if not hit:
            return path[1:-1]
        if hit <= active:
            return None
        active |= hit
        obs = [live[i] for i in sorted(active)]
        nodes = [tuple(a), tuple(b)]
        for cx, cy, r in obs:
            R = (r + margin_nm * NM) / math.cos(math.pi / AVOID_CORNERS)
            for k in range(AVOID_CORNERS):
                ang = 2 * math.pi * k / AVOID_CORNERS
                pt = (cx + R * math.cos(ang), cy + R * math.sin(ang))
                if ban is not None and (cx, cy, r) == ban[0] and ((b[0] - a[0]) * (pt[1] - a[1]) - (b[1] - a[1]) * (pt[0] - a[0]) > 0) == ban[1]:
                    continue
                if not any(math.hypot(pt[0] - ox, pt[1] - oy) < orr for ox, oy, orr in live):
                    nodes.append(pt)
        n = len(nodes)
        best, prev, done = {0: 0.0}, {}, set()
        heap = [(math.hypot(b[0] - a[0], b[1] - a[1]), 0)]
        found = False
        while heap:
            _, u = heapq.heappop(heap)
            if u in done:
                continue
            done.add(u)
            if u == 1:
                found = True
                break
            ux, uy = nodes[u]
            for v in range(n):
                if v in done:
                    continue
                vx, vy = nodes[v]
                d = best[u] + math.hypot(vx - ux, vy - uy)
                if d >= best.get(v, 1e18):
                    continue
                if _seg_hits(nodes[u], nodes[v], obs):
                    continue
                best[v], prev[v] = d, u
                heapq.heappush(heap, (d + math.hypot(b[0] - vx, b[1] - vy), v))
        if not found:
            return None
        k, path = 1, [nodes[1]]
        while k != 0:
            k = prev[k]
            path.append(nodes[k])
        path.reverse()
    return None


def _edge_point(c, p, margin_nm: float):
    """The point of circle c's edge (+ margin) nearest to p (x, y metres); a p at the centre goes east."""
    cx, cy, r = c
    d = math.hypot(p[0] - cx, p[1] - cy)
    ux, uy = ((p[0] - cx) / d, (p[1] - cy) / d) if d > 1.0 else (1.0, 0.0)
    return (cx + ux * (r + margin_nm) * NM, cy + uy * (r + margin_nm) * NM)


def _ring_exit(p, circles, skip, margin_nm: float) -> list:
    """[the nearest point outside every ring (+ margin) to a position p that sits in one] or [] when p is in none (not counting the rings whose index is in `skip`: the ones the leg's other end sits in too).
    Where the rings overlap p lies in their union, and the nearest way out is the nearest point of the union's edge: the radial edge point of one ring, or a place where two inflated rings cross
    (hopping from ring to ring by each one's own nearest edge zig-zags: the first S140b1 run added 184 nm to a sweep that started in a cluster)."""
    live = [(cx, cy, (r + margin_nm) * NM) for i, (cx, cy, r) in enumerate(circles) if i not in skip]
    if not any(math.hypot(p[0] - cx, p[1] - cy) < rr - margin_nm * NM for cx, cy, rr in live):
        return []
    cand = [_edge_point((cx, cy, (rr / NM) - margin_nm), p, margin_nm) for cx, cy, rr in live]
    for i in range(len(live)):
        x1, y1, r1 = live[i]
        for j in range(i + 1, len(live)):
            x2, y2, r2 = live[j]
            d = math.hypot(x2 - x1, y2 - y1)
            if d < 1.0 or d >= r1 + r2 or d <= abs(r1 - r2):
                continue
            al = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
            h = math.sqrt(max(0.0, r1 * r1 - al * al))
            mx, my = x1 + al * (x2 - x1) / d, y1 + al * (y2 - y1) / d
            cand.append((mx + h * (y2 - y1) / d, my - h * (x2 - x1) / d))
            cand.append((mx - h * (y2 - y1) / d, my + h * (x2 - x1) / d))
    good = [q for q in cand if all(math.hypot(q[0] - cx, q[1] - cy) >= rr - 1.0 for cx, cy, rr in live)]
    return [min(good, key=lambda q: (math.hypot(q[0] - p[0], q[1] - p[1]), q))] if good else []


EDGE_GAIN_NM = 4.0         # S140b1: a leg with an end inside a ring takes the ring's edge only when that cuts the distance flown inside rings by at least this much. Judgment call: without it, short legs between
                           # two points in a cluster of overlapping rings (an IP, the target, the egress point) zig-zagged in and out of the cluster and added up to 87 nm to a sweep


def _inside_m(path, circles) -> float:
    """Metres of the polyline `path` ((x, y) points) that lie inside at least one circle (x, y, nm): the union of the chords of each leg."""
    tot = 0.0
    for p, q in zip(path, path[1:]):
        vx, vy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(vx, vy)
        if L < 1.0:
            continue
        iv = []
        for cx, cy, r in circles:
            fx, fy = p[0] - cx, p[1] - cy
            b_ = 2 * (fx * vx + fy * vy)
            c_ = fx * fx + fy * fy - (r * NM) ** 2
            disc = b_ * b_ - 4 * L * L * c_
            if disc <= 0:
                continue
            s = math.sqrt(disc)
            t0, t1 = max(0.0, (-b_ - s) / (2 * L * L)), min(1.0, (-b_ + s) / (2 * L * L))
            if t1 > t0:
                iv.append((t0, t1))
        end = 0.0
        for t0, t1 in sorted(iv):
            if t1 > end:
                tot += (t1 - max(t0, end)) * L
                end = t1
    return tot


def safe_path_edge(a, b, circles, margin_nm: float | None = None, prefer=None):
    """S140b1 (plan 2.2, last row): `safe_path` for a leg that may start or end INSIDE a ring (a blue base near the front, an IP inside the target's ring on a transit leg). Such a ring is
    entered or left by the shortest way: the leg runs round to the point of the ring's edge (+ margin) nearest the inside end and goes straight in (or goes straight out to it, then on). A ring that
    holds both ends stays as it is (the leg lies inside it). Only when it pays: the edge route has to cut the distance flown inside rings by EDGE_GAIN_NM against the plain `safe_path` (which leaves
    the rings that hold an end out of it), else the plain one stands. The same shape as `safe_path` (the turn points, [] when none, None when there is no way round), the edge points included."""
    margin_nm = AVOID_MARGIN_NM if margin_nm is None else margin_nm
    plain = safe_path(a, b, circles, margin_nm, prefer)
    both = {i for i, (cx, cy, r) in enumerate(circles) if math.hypot(a[0] - cx, a[1] - cy) < r * NM and math.hypot(b[0] - cx, b[1] - cy) < r * NM}
    out_a = _ring_exit(a, circles, both, margin_nm)
    out_b = _ring_exit(b, circles, both, margin_nm)
    if not out_a and not out_b:
        return plain
    mid = safe_path(out_a[-1] if out_a else tuple(a), out_b[-1] if out_b else tuple(b), circles, margin_nm, prefer)
    if mid is None:
        return plain
    edge = out_a + mid + out_b[::-1]
    if plain is None:
        return edge
    pa, pe = [tuple(a)] + plain + [tuple(b)], [tuple(a)] + edge + [tuple(b)]
    return edge if _inside_m(pe, circles) <= _inside_m(pa, circles) - EDGE_GAIN_NM * NM else plain


def avoid_circles(wp: list, circles: list, max_points: int, first: int, edge: bool = False, start: tuple | None = None, prefer=None) -> list:
    """v0.41.11: bend the legs from index `first` on around each circle (x, y, nm); one turn point 2 nm outside the circle, two passes at most.
    S140a: the shortest path round the circles (`safe_path`): each leg from index `first` on gets as many turn points as it needs, from the end of the
    list backwards, never past the airframe's waypoint limit. A leg with no way round, or with more turn points than the limit allows, stays as it is.
    S140b1: `edge=True` routes a leg that starts or ends inside a ring by the ring's edge too (`safe_path_edge`); the default leaves such a leg straight, as before. `start` = (x, y) of the
    airfield the flight takes off from: a route that begins with neither SPAWN nor DEP (the all-AI test's own flight: the take-off belongs to the group) gets it as its missing first point
    while the legs are routed, so the leg out to the marshal point is routed too.
    S140e: `prefer` (x, y) = red's nearest patrol station or fighter field: a leg whose two ways round a ring are within AVOID_SIDE_PCT percent takes the side away from it.
    Changes `wp` in place and returns it."""
    path_ = (lambda a, b, c: safe_path_edge(a, b, c, prefer=prefer)) if edge else (lambda a, b, c: safe_path(a, b, c, prefer=prefer))
    lead = None
    if start is not None and wp and wp[0].name not in ("SPAWN", "DEP"):
        lead = Wpt("BASE", start[0], start[1], wp[0].alt_ft, wp[0].speed_kts, rad=wp[0].rad)
        wp.insert(0, lead)
        first = 1 if first <= 1 else first + 1
        max_points -= 1
    i = len(wp) - 1
    while i >= max(1, first):
        a, b = wp[i - 1], wp[i]
        pts = path_((a.x, a.y), (b.x, b.y), circles)
        if pts and len(wp) + len(pts) + 2 <= max_points:
            alt = max(a.alt_ft, b.alt_ft)
            wp[i:i] = [Wpt("AVD", x, y, alt, a.speed_kts, "Around a SAM site", rad=a.rad) for x, y in pts]
        i -= 1
    if lead is not None:
        wp.remove(lead)
    return wp


IP_MOVE_MAX_NM = 60.0      # S140c: a person's strike / SEAD IP moves out along the run-in at most to this far from the target; no clear point within it (or short of the PUSH): the IP stays. Judgment call, counted by the probe


def ip_outside(g, ip_xy):
    """S140c (XO 2026-11-22, plan 4 answer 2): a person's strike / SEAD IP lies outside every ring that holds the target (+ AVOID_MARGIN_NM): out along the run-in (bearing target -> IP) in 1 nm steps to the
    first clear point, at most IP_MOVE_MAX_NM from the target and 5 nm short of the PUSH; else ip_xy again. TGT is not touched and nothing is tasked (Human-Flown rule: route shape only)."""
    hold = [(cx, cy, r) for cx, cy, r in (g.all_rings or []) if math.hypot(g.tx - cx, g.ty - cy) < r * NM]
    clear = lambda p: all(math.hypot(p[0] - cx, p[1] - cy) >= (r + AVOID_MARGIN_NM) * NM for cx, cy, r in hold)
    if not hold or clear(ip_xy):
        return ip_xy
    hdg, d = bearing(g.tx, g.ty, *ip_xy), math.hypot(ip_xy[0] - g.tx, ip_xy[1] - g.ty)
    limit = min(IP_MOVE_MAX_NM * NM, math.hypot(g.push[0] - g.tx, g.push[1] - g.ty) - 5 * NM)
    while d + NM <= limit:
        d += NM
        p = offset(g.tx, g.ty, hdg, d)
        if clear(p):
            return p
    return ip_xy


FUEL_ROUTE_FACTOR = 2.4    # S140d1: a built route (every leg, turn points and the way home included, plus the minutes held at the marshal point and on a station at cruise speed) may be this many times the jet's
                           # combat radius (x 1.5 where the planner judged a tanker fits, x PEN_REACH for the PEN kit). JUDGMENT CALL, set so nothing is dropped at today's routes: the S140 probe's worst route is
                           # 2.17 x its combat radius (2.3 in the first probe, before the leg rules), the median 0.3 to 0.8. Raise or lower it here.


def route_nm(pts) -> float:
    """S140d1: the length in nm of the polyline through `pts` (objects with x, y in metres)."""
    return sum(math.hypot(b.x - a.x, b.y - a.y) for a, b in zip(pts, pts[1:])) / NM


def routed_nm(a, b, circles):
    """S140d1: the length in nm of the safe path a -> b (x, y metres; `safe_path_edge` round the circles (x, y, nm)): the straight distance plus what the turn points add. None when there is no way round."""
    pts = safe_path_edge(a, b, circles)
    if pts is None:
        return None
    path = [tuple(a)] + list(pts) + [tuple(b)]
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(path, path[1:])) / NM


class trim_margin:
    """S140d1 (ladder rung 2): `with trim_margin():` the turn points of every route built inside it keep `margin_nm` (default 0) outside the rings instead of AVOID_MARGIN_NM; the rings are already the reach plus a
    margin in AVOID_NM. Restores the margin on exit."""
    def __init__(self, margin_nm: float = 0.0):
        self.m = margin_nm

    def __enter__(self):
        global AVOID_MARGIN_NM
        self.old, AVOID_MARGIN_NM = AVOID_MARGIN_NM, self.m
        return self

    def __exit__(self, *a):
        global AVOID_MARGIN_NM
        AVOID_MARGIN_NM = self.old
        return False


EGR_MOVE_MAX_NM = 40.0     # S140b2: an AI flight's egress point inside a ring moves at most this far out of it; farther (a ring cluster with no edge near) it stays where it was. Judgment call, counted by the probe


def out_of_rings(xy, circles, max_nm: float = EGR_MOVE_MAX_NM, margin_nm: float | None = None):
    """S140b2: the point xy (x, y metres) itself when it lies in no ring (x, y, nm), else the nearest point outside every ring + margin (`_ring_exit`); xy again when that is more than max_nm away."""
    e = _ring_exit(xy, circles, (), AVOID_MARGIN_NM if margin_nm is None else margin_nm)
    return e[0] if (e and math.hypot(e[0][0] - xy[0], e[0][1] - xy[1]) <= max_nm * NM) else xy


def shared_leg(g, a: Wpt, b: Wpt, lane_nm: float, room: int):
    """S140b2 (plan 2.4): the turn points of the leg a (a PUSH point) -> b (its IP) for one flight of a package, from the package's ONE lane-0 path: `safe_path_edge` from g.push (computed once,
    cached in g.shared), each point shifted by the flight's lane (`lane_nm`, the offset of its PUSH from g.push, sideways to the package axis). A shifted point that falls inside a ring is pushed
    radially out to the ring edge + margin. When the shifted path still flies more distance inside rings than the lane-0 path (+ 1 nm), the flight takes its own path from its own PUSH.
    [] when the leg is clear or the airframe has no room for the points (`room` = points left); None when there is no way round."""
    rings = g.all_rings
    a0 = tuple(g.push)
    cache = g.shared if g.shared is not None else {}
    key = (round(a0[0]), round(a0[1]), round(b.x), round(b.y), AVOID_MARGIN_NM)
    if key not in cache:
        cache[key] = safe_path_edge(a0, (b.x, b.y), rings, prefer=g.prefer)
    base = cache[key]
    if not base or not lane_nm:
        return base if (not base or len(base) <= room) else []
    pts = []
    for x, y in base:
        x, y = offset(x, y, g.hdg + 90, lane_nm * NM)
        for cx, cy, r in rings:
            d = math.hypot(x - cx, y - cy)
            if d < (r + AVOID_MARGIN_NM) * NM:
                x, y = _edge_point((cx, cy, r), (x, y), AVOID_MARGIN_NM)
        pts.append((x, y))
    full0, full = [a0] + list(base) + [(b.x, b.y)], [(a.x, a.y)] + pts + [(b.x, b.y)]
    if _inside_m(full, rings) > _inside_m(full0, rings) + NM:
        own = safe_path_edge((a.x, a.y), (b.x, b.y), rings, prefer=g.prefer)
        return own if (own is None or len(own) <= room) else []
    return pts if len(pts) <= room else []


def leg_seconds(a: Wpt, b: Wpt, climb: bool = False) -> float:
    v = max(120, (a.speed_kts + b.speed_kts) / 2) * KT
    return dist(a.x, a.y, b.x, b.y) / v * (1.12 if climb else 1.04)


def hold_next(wps: list[Wpt], i: int) -> int:
    """S140b1: the index of the point a flight leaving the HOLD point wps[i] has to cross at push time: the PUSH after it (the turn points of a transit leg round a SAM ring can sit between), else the next point."""
    return next((k for k in range(i + 1, len(wps)) if wps[k].name == "PUSH"), i + 1)


def hold_leg_s(wps: list[Wpt], i: int) -> float:
    """S140b1: the seconds from the HOLD point wps[i] to `hold_next`, over every point between; 0 at the end of the route."""
    return sum(leg_seconds(wps[k], wps[k + 1]) for k in range(i, min(hold_next(wps, i), len(wps) - 1)))


def assign_times(wps: list[Wpt], t0: float, push_s: float | None = None) -> None:
    """Fill eta_s along the route starting at t0. At a HOLD point the flight waits so that it CROSSES THE NEXT POINT (PUSH)
    exactly at push_s: it leaves the hold at push_s minus the leg time (S140b1: the whole way to PUSH, turn points included)."""
    t = t0
    for i, w in enumerate(wps):
        if i > 0:
            t += leg_seconds(wps[i - 1], w, climb=(i == 1))
        w.eta_s = t
        if w.action == "HOLD" and push_s is not None:
            leave = push_s - hold_leg_s(wps, i)
            t = max(t, leave)


def hold_leave_s(wps: list[Wpt], push_s: float) -> float:
    """When a flight must leave its HOLD point to cross the PUSH after it at push_s."""
    for i, w in enumerate(wps):
        if w.action == "HOLD":
            return push_s - hold_leg_s(wps, i)
    return push_s


OBJECTIVE_ACTIONS = ("BOMB", "JSOW", "SEAD", "SWEEP", "CAS", "ESCORT", "TARCAP", "CAPORBIT")


def objective_wp(wps: list[Wpt]) -> Wpt | None:
    """The waypoint a flight is on station at for TOT purposes (target / HARM point / CAP station)."""
    return next((w for w in wps if w.action in OBJECTIVE_ACTIONS), None)


def _floor_ft(x: float, y: float) -> int:
    """Lowest altitude (MSL) a flight may be spawned at: 1,500 ft over the highest ground near that point, or 6,000 ft without a ground-height scan."""
    from . import relief
    h = relief.max_near_m(x, y, 5 * NM)
    return 6000 if h is None else int(math.ceil((h / FT + 1500) / 500.0) * 500)


def terrain_clear(wps: list[Wpt]) -> int:
    """AI flights hold the altitude of their last waypoint until they get to the next one, so a leg over mountains needs its START altitude above
    the ridges on it. Lifts every waypoint (not the LOW tier, which follows the ground, and not a ground point) to the minimum safe altitude of
    the leg it starts, and the end of the leg to the same, so a descent never ends in a hillside. Returns how many waypoints it lifted.
    Without a ground-height scan nothing changes. A person flying the flight reads the MSA on the kneeboard instead."""
    from . import relief
    if not relief.available():
        return 0
    n = 0
    for a, b in zip(wps, wps[1:]):
        h = relief.leg_max_ft((a.x, a.y), (b.x, b.y))
        if h is None:
            continue
        need = int(math.ceil((h + (2000 if h > 5000 else 1000)) / 500.0) * 500)
        for w in (a, b):
            if w.rad or w.agl or w.alt_ft >= need:
                continue
            w.alt_ft = need
            n += 1
    return n


def home_leg_ft(a: tuple, b: tuple, alt_ft: float) -> int:
    """v0.41.49: the altitude an AI flight's recovery point (RCV) needs so the leg a -> b home clears the ground. The RCV point is added after
    terrain_clear runs, at a fixed 3,000-6,000 ft, and an AI flight drops to the next point's altitude right after the last one: XO's 2026-10-20
    run had Venom 5-2 level at 3,000 ft MSL for 100 nm over rising ground and lost with nobody shooting. Same margin as terrain_clear (1,000 ft, 2,000 ft over
    mountains), capped at 20,000 ft. Without a ground-height scan the altitude is unchanged."""
    from . import relief
    h = relief.leg_max_ft(a, b)
    if h is None:
        return int(alt_ft)
    need = int(math.ceil((h + (2000 if h > 5000 else 1000)) / 500.0) * 500)
    return int(min(20000, max(alt_ft, need)))


def in_progress(wps: list[Wpt], home: tuple, leave: dict | None = None) -> list[Wpt] | None:
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
        if a.action == "HOLD" or (leave and i in leave):
            # when it leaves the hold (the marshal point) or, v0.41.23, its station (the caller's leave times)
            ts = leave[i] if (leave and i in leave) else b.eta_s - leg_seconds(a, b)
            if a.eta_s <= 0 < ts:                                  # still orbiting there
                return [Wpt("SPAWN", a.x, a.y, max(a.alt_ft, _floor_ft(a.x, a.y)) if a.rad else a.alt_ft, a.speed_kts)] + list(wps[i:])
        te = b.eta_s
        if ts <= 0 < te:
            f = (0 - ts) / max(1.0, te - ts)
            sp = Wpt("SPAWN", a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f, max(_floor_ft(a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f), int(a.alt_ft + (b.alt_ft - a.alt_ft) * f)) if (a.rad or b.rad) else int(a.alt_ft + (b.alt_ft - a.alt_ft) * f), a.speed_kts)
            return [sp] + list(wps[i + 1:])
    return None
