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
    ai_player: bool = False  # test mode: the player's slot is flown by the AI, so the player's flight gets the AI stand-off too
    stand: dict = None      # {(role, id(profile)): (x, y, [SAM types], nm short)} sweeps and escorts that stop at the edge of SAM cover
    sweep: bool = False     # a Fighter Sweep package: no marshal, DEP - PUSH - station - home
    jsow_keep: list = None  # [(x, y, nm)]: live long-range SAMs a JSOW launch point stays this far from (v0.41.3)


STANDOFF_EGRESS_NM = 25.0  # a HARM or JSOW flight egresses this far beyond its launch point, straight back out along its own approach
JSOW_AXIS_DEG = 30.0       # the JSOW flight's approach is this far off the HARM shooters' axis (side chosen by the builder, away from other SAM sites)
JSOW_LAUNCH_NM = 20.0      # an AI JSOW flight's launch point (the AGM-154A glides about this far from 20,000 ft); it releases from there and turns home
JSOW_HIGH_ALT_FT = 33000      # ...and when it is pushed out past JSOW_LAUNCH_NM, the flight releases from this high
JSOW_MAX_NM = 45.0           # a JSOW launch point is never farther than this from its target (v0.41.3 run: AGM-154As released at 30-40 nm from 33,000 ft hit; was 40)
JSOW_KEEP_HIGH_NM = 40.0     # a pushed-out JSOW flight is high, where an SA-10 reaches farther: its launch point stays this far from one (v0.41.3 run: 30.6 nm lost all four)
HARM_LAUNCH_NM = 30.0      # an AI SEAD flight's HARM launch point: at the edge of what an SA-10 first reaches (it opened fire at about 55 km in testing); 21 nm put the launch point deep inside it
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
               spawn_kts: int = 0, jsow: bool = False, jsow_side: int = 0, keep_out: tuple | None = None) -> list[Wpt]:
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
    so = None if (is_player and not g.ai_player) else (g.stand or {}).get(key)
    ialt, irad = (t.alt_ft, t.rad) if (t is not None and t.changed) else (alt, False)          # the tier applies from the IP on
    human = is_player and not g.ai_player                    # a person flies it; in the all-AI test the player's flight is routed and tasked like any AI flight
    harm_nm = max(8.0, min(HARM_LAUNCH_NM, g.d / NM * 0.8 - 6))        # on short routes it still leaves the IP ahead of the base
    ip_xy = g.ip
    jsow_nm = max(8.0, min(JSOW_LAUNCH_NM, g.d / NM * 0.8 - 6))
    if jsow and role == Role.STRIKE and not human and g.jsow_keep:
        # v0.41.3: the JSOW launch point stays as far from every live long-range SAM as the HARM point does (the v0.41.1 runs lost whole JSOW
        # flights to the SA-10s at 13-24 nm). It moves out along its own axis, up to JSOW_MAX_NM from the target (the glide range from altitude).
        jh_ = g.hdg + 180 + JSOW_AXIS_DEG * jsow_side
        # v0.41.4: 40 nm, not the HARM shooters' 30: the JSOW jets go in at 33,000 ft and run in on their releases past the launch point.
        while jsow_nm < JSOW_MAX_NM and any(dist(*offset(g.tx, g.ty, jh_, jsow_nm * NM), kx, ky) < max(knm, JSOW_KEEP_HIGH_NM) * NM for kx, ky, knm in g.jsow_keep):
            jsow_nm += 1.0
    if role == Role.SEAD and not human and keep_out:          # under an umbrella (an SA-10 covering the target): the HARM point stays out of its reach too
        kx, ky, knm = keep_out
        while harm_nm < HARM_LAUNCH_NM + 40 and dist(*offset(g.tx, g.ty, g.hdg + 180, harm_nm * NM), kx, ky) < knm * NM:
            harm_nm += 1.0
    jsow_hdg = g.hdg + 180 + JSOW_AXIS_DEG * jsow_side         # the JSOW flight comes in on its own axis, off the HARM shooters' (multi-axis)
    if (role == Role.SEAD or (jsow and role == Role.STRIKE)) and not human:      # the IP sits 6 nm before the launch point (farther out than the usual IP)
        far = offset(g.tx, g.ty, g.hdg + 180 if role == Role.SEAD else jsow_hdg, ((harm_nm if role == Role.SEAD else jsow_nm) + 6) * NM)
        if dist(g.tx, g.ty, *far) > dist(g.tx, g.ty, *g.ip):
            ip_xy = far
    wp.append(Wpt("PUSH", *g.push, alt, p.push_kts, "Push on time, check in with AWACS"))
    st_ = (g.stand or {}).get(key) if role in (Role.ESCORT, Role.SWEEP) else None
    if st_ is not None and len(st_) >= 5:
        # TARCAP (ESCORT role) and ESCORT (SWEEP role, package escort): a station of their own, short of the target and outside live SAM cover,
        # where they hold and shoot at what comes in range without chasing it. No IP. The TARCAP gets there first, holds its time and goes
        # home from the station; the escort holds until the last ground-attack flight is off target and leaves by the package egress when
        # that leg is clear of SAM cover (from the station otherwise). The same route for you and for the AI.
        sx_, sy_, names_, short_, egr_ok_ = st_[:5]
        why_ = f", outside {'/'.join(names_)} cover" if names_ else ""
        if g.sweep:                                            # Fighter Sweep: no marshal, straight out, station, 15 minutes or Winchester, home
            wp = [w for w in wp if w.name != "MSHL"]
            wp.append(Wpt("TGT", sx_, sy_, alt, p.cap_kts, f"SWEEP: station {short_:.0f} nm short of the target{why_}; clear the air, do not chase", "SWEEPSTN", orbit=True))
        elif role == Role.ESCORT:
            wp.append(Wpt("TGT", sx_, sy_, alt, p.cap_kts, f"TARCAP: on station {short_:.0f} nm short of the target{why_}; hold and shoot, do not chase", "TARCAP", orbit=True))
        else:
            wp.append(Wpt("TGT", sx_, sy_, alt, p.cap_kts, f"ESCORT: hold {short_:.0f} nm short of the target{why_} until the strikers are off; do not chase", "ESCORT", orbit=True))
            if egr_ok_:
                wp.append(Wpt("EGR", *g.egr, ialt, p.egress_kts, "Exit with the package", rad=irad))
        if len(wp) + 2 > p.max_points:
            raise ValueError(f"route has {len(wp) + 2} points but the airframe holds {p.max_points}")
        return wp
    if jsow and role == Role.STRIKE and not human and jsow_nm > JSOW_LAUNCH_NM:
        ialt, irad = max(ialt, JSOW_HIGH_ALT_FT), False         # a long JSOW shot goes from high up (the glide range grows with release altitude)
    wp.append(Wpt("IP", *ip_xy, ialt, p.ip_kts, "Weapons armed, master arm", rad=irad))
    # The player's TGT is on the ground target at 0 AGL so pods, weapons and the WSO / Jester can slave to it. The wingmen follow the player, and AI-only flights
    # never get a ground-level point (they would descend to it).
    if role == Role.STRIKE and jsow and not human:             # a JSOW slinger never crosses the site: it releases from its launch point and goes home
        wp.append(Wpt("JSOW", *offset(g.tx, g.ty, jsow_hdg, jsow_nm * NM), ialt, p.attack_kts, "JSOW launch point", "JSOW", rad=irad))
    elif role == Role.STRIKE:
        wp.append(Wpt("TGT", g.tx, g.ty, 0 if human else ialt, p.attack_kts, p.tgt_note, "BOMB", agl=human, rad=irad and not human))
    elif role == Role.SEAD and human:
        wp.append(Wpt("TGT", g.tx, g.ty, 0, p.attack_kts, "SEAD site. You set standoff", "SEAD", agl=True))
    elif role == Role.SEAD:
        wp.append(Wpt("SEAD", *offset(g.tx, g.ty, g.hdg + 180, harm_nm * NM), ialt, p.attack_kts, "HARM launch point", "SEAD", rad=irad))
    elif role == Role.SWEEP and so:
        wp.append(Wpt("TGT", so[0], so[1], alt, p.cap_kts, f"SWEEP: stop here, {so[3]:.0f} nm short of the target, outside {'/'.join(so[2])} cover", "SWEEP", orbit=True))
    elif role == Role.SWEEP:
        wp.append(Wpt("TGT", g.tx, g.ty, alt, p.attack_kts + 30, "SWEEP: clear the airspace", "SWEEP"))
    elif role == Role.CAS:
        wp.append(Wpt("TGT", g.tx, g.ty, 0 if human else ialt, p.attack_kts, "CAS: check in with JTAC (COMM1 CH3)", "CAS", agl=human, rad=irad and not human))
    elif so:
        wp.append(Wpt("TGT", so[0], so[1], ialt, p.cap_kts, f"ESCORT: hold here, {so[3]:.0f} nm short of the target, outside {'/'.join(so[2])} cover", "ESCORT", rad=irad, orbit=True))
    else:
        wp.append(Wpt("TGT", g.tx, g.ty, ialt, p.attack_kts, "ESCORT: cover the strikers over target", "ESCORT", rad=irad))
    standoff = not human and (role == Role.SEAD or (jsow and role == Role.STRIKE))
    if standoff:
        # a HARM or JSOW flight fires from stand-off range and goes home the way it came. The package egress lies beyond the target for the
        # strikers that overfly it: in the v0.39.21 run the JSOW Hornets released, then crossed the Sukhumi cluster to it and met the Su-27s.
        sax = g.hdg + 180 if role == Role.SEAD else jsow_hdg
        snm = (harm_nm if role == Role.SEAD else jsow_nm) + STANDOFF_EGRESS_NM
        wp.append(Wpt("EGR", *offset(g.tx, g.ty, sax, snm * NM), ialt, p.egress_kts, "Exit: back out along the approach", rad=irad))
    elif not (so and role in (Role.SWEEP, Role.ESCORT)):         # a stand-off fighter never crosses the target area: it goes home from its hold
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


OBJECTIVE_ACTIONS = ("BOMB", "JSOW", "SEAD", "SWEEP", "CAS", "ESCORT", "TARCAP", "SWEEPSTN", "CAPORBIT")


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
