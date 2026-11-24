"""Threat map: SAM rings, the FLOT/gatekeeper rule, safe tanker stations, egress steering, corridor sites.

The rule that keeps the war logical: a target is only offered if the straight route to it does not cross an intact
SAM ring that sits IN FRONT of the target (closer to us by more than 15 nm). Blocking sites are promoted to DEAD
objectives instead, so the war advances belt by belt instead of jumping straight to deep targets.
"""
from __future__ import annotations
import math
from .models import AssetKind, BaseKind
from . import samtier
from .samtier import RANGE_NM, UMBRELLA_VARIANTS      # S90 P4: the long-range tier is data (samtier.py; a theatre pack names it); RANGE_NM is the one ring table
from .routes import AVOID_NM, RAID_SA11_NM, RAID_THREAT_OUT_NM, dist, offset

NM = 1852.0


def umbrella_site(state, target_asset, reach_km: float | None = None):
    """The live long-range site whose reach covers this target (the nearest one), or None. A target that is itself an SA-10 has no umbrella
    other than a second SA-10 nearby. `reach_km` None = each site's own reach (samtier)."""
    if target_asset is None:
        return None
    best, bd = None, None
    for a in state.assets.values():
        if a.id == target_asset.id or a.variant not in UMBRELLA_VARIANTS or a.destroyed:
            continue
        d = math.hypot(a.x - target_asset.x, a.y - target_asset.y)
        if d <= (samtier.get(a.variant, "reach_km") if reach_km is None else reach_km) * 1000 and (bd is None or d < bd):
            best, bd = a, d
    return best
SERIOUS_NM = 8          # shorter-ranged systems do not block routes (they only matter at the target)


def rings(state, min_range: float = SERIOUS_NM) -> list:
    out = []
    for a in state.assets.values():
        if a.kind == AssetKind.SAM and not a.destroyed and a.health > 0.30:
            r = RANGE_NM.get(a.variant, 0)
            if r >= min_range:
                out.append((a, r * NM))
    return out


def seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def poly_dist(px, py, pts) -> float:
    return min(seg_dist(px, py, *pts[i], *pts[i + 1]) for i in range(len(pts) - 1))


def cluster_ids(target_asset) -> set:
    return set() if target_asset is None else {target_asset.id, *target_asset.defended_by}


def raid_avoid_nm(variant: str) -> float:
    """How far a live SAM of this variant threatens a route for the carrier-raid setpiece: AVOID_NM's figure, bumped for the SA-11 (RAID_SA11_NM;
    v0.41.276, it engaged the raid's Tomcats at 23 to 26 nm). 0 for a variant AVOID_NM doesn't cover."""
    r = AVOID_NM.get(variant, 0.0)
    return max(r, RAID_SA11_NM) if variant == "SA-11" else r


def raid_inbound_sites(state, target_xy, brg, bomber_wing_id) -> list:
    """v0.41.287 (XO 2026-11-04: "every SAM threatening the intercept line", not just the minimum needed to open a lane): the live, undestroyed,
    unsuppressed red SAM sites whose reach (`raid_avoid_nm`) touches the carrier raid's straight way in -- the target out to RAID_THREAT_OUT_NM
    on `brg` (v0.41.289: the intercept band round RAID_IP_NEAR_NM plus the bombers' launch point; it was the route's outer point w1, 220 nm),
    never past 0.9 of the way to the bomber wing's field. Every one of these threatens the line, whether it sits on it or well back toward the
    target (a long-ranged site can still reach the lane from there). -> [(asset, nm), ...], order is state.assets' own."""
    ba = state.assets.get(bomber_wing_id)
    if ba is None:
        return []
    dx, dy = target_xy
    w1 = offset(dx, dy, brg, min(RAID_THREAT_OUT_NM * NM, 0.9 * dist(ba.x, ba.y, dx, dy)))
    out = []
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed or a.health <= 0.25 or getattr(a, "suppressed", False):
            continue
        r = raid_avoid_nm(a.variant)
        if r > 0 and seg_dist(a.x, a.y, dx, dy, w1[0], w1[1]) < r * NM:
            out.append((a, r))
    return out


def blockers(state, base_xy, target_xy, target_asset=None, margin_nm: float = 8, front_nm: float = 15) -> list:
    """Intact SAM sites the route crosses that are in front of the target (the FLOT/gatekeeper rule)."""
    bx, by = base_xy
    tx, ty = target_xy
    d_t = math.hypot(tx - bx, ty - by)
    skip = cluster_ids(target_asset)
    out = []
    for a, r in rings(state):
        if a.id in skip:
            continue
        if seg_dist(a.x, a.y, bx, by, tx, ty) < r + margin_nm * NM and math.hypot(a.x - bx, a.y - by) < d_t - front_nm * NM:
            out.append(a)
    return out


def fighter_bases(state) -> list:
    return [(state.assets[w.base_asset_id].x, state.assets[w.base_asset_id].y) for w in state.enemy_air
            if w.available > 0 and not state.assets[w.base_asset_id].destroyed]


SUPPORT_FIELD_COVER_NM = 30      # S193: a support track this close to a defended blue field (defense >= 0.15) or to the carrier group is under blue cover (the tanker's v0.41.26 figure, `support_caps.TANKER_COVER_NM`)
SUPPORT_CAP_COVER_NM = 25        # S193 (judgment call, no source): ...and this close to a blue BARCAP area that has a pair planned THIS turn (XO 2026-11-24: "barcap counts as cover")
TANKER_SOFT_FLOOR_NM = 25         # S193 (judgment call): a covered tanker spot may sit inside a patrol / lane / raid / sweep limit, but not by more than this: further in, a clear spot without cover is better
AWACS_COVER_MARGIN_CAP_NM = 20   # S193 (judgment call): a covered AWACS spot clear of the raid / sweep lines by more than this is as good as any other: the nearest to the first station wins then


def blue_cover_circles(state, field_nm: float = SUPPORT_FIELD_COVER_NM, cap_nm: float = SUPPORT_CAP_COVER_NM, base_defenses: bool = True) -> list:
    """S193: [(x, y, nm)] the places a support aircraft counts as under blue cover: every defended blue airfield (`defense` 0.15 or more, only when `base_defenses` is on) and
    every carrier within `field_nm`, and every blue BARCAP area with a pair planned this turn (`state.barcap["blue_flights"]`, HVAACAP guards left out: they follow the support) within `cap_nm`.
    Reads the state only (the AWACS station is the same for every package of a turn)."""
    circles = []
    for base in state.bases.values():
        if base.kind == BaseKind.CARRIER:
            circles.append((base.x, base.y, field_nm))
        elif base.kind == BaseKind.AIRFIELD and base_defenses and getattr(base, "defense", 0) >= 0.15:
            circles.append((base.x, base.y, field_nm))
    barcap_state = getattr(state, "barcap", None) or {}
    areas = {}
    for area in barcap_state.get("blue") or []:
        areas[area["id"]] = area
    used_areas = set()
    for flight in barcap_state.get("blue_flights") or []:
        area_id = flight.get("area")
        if area_id in areas and area_id not in used_areas and flight.get("turn") == state.turn and flight.get("kind") not in ("HVAACAP", "TKR_HVAACAP"):
            used_areas.add(area_id)
            circles.append((areas[area_id]["x"], areas[area_id]["y"], cap_nm))
    return circles


def in_blue_cover(circles, x, y) -> bool:
    for circle_x, circle_y, circle_nm in circles:
        if math.hypot(x - circle_x, y - circle_y) / NM <= circle_nm:
            return True
    return False


def awacs_first_station(state):
    """S19 (v0.41.369, XO 2026-11-11): the AWACS's first station -> (x, y, front_hdg), before this turn's raids move it (S188, S191). It starts from the support field
    (support_assets._support_airfield), faces red's live fighter fields (else red's assets, else north) and sits BEHIND that field, clear of enemy fields and SAM rings
    (safe_marshal). It reads only the state. None when no support field exists. S191: the tanker's fallback track hangs off THIS point, so a raid-driven AWACS move does not drag the tanker."""
    from .support_assets import _support_airfield
    b = _support_airfield(state)
    if b is None:
        return None
    pts = fighter_bases(state) or [(a.x, a.y) for a in state.assets.values() if not a.destroyed]
    if pts:
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        fh = math.degrees(math.atan2(cy - b.y, cx - b.x)) % 360
    else:
        fh = 0.0
    x, y = safe_marshal(state, (b.x, b.y), fh)
    return x, y, fh


def awacs_station(state):
    """S19 (XO 2026-11-11): the AWACS's one fixed station -> (x, y, front_hdg), the same for every package of a turn and for its guard: the first station
    (`awacs_first_station`) moved off this turn's raid and sweep lines (`_awacs_clear_of_raids`, S188, S191). It reads only the state: not the player, the package or its target.
    (DCS detects by the radar's own range, so the distance to the fight does not matter.) None when no support field exists."""
    first = awacs_first_station(state)
    if first is None:
        return None
    x, y, fh = first
    covered_spot = _awacs_under_cover(state, x, y, fh)
    if covered_spot is not None:
        return covered_spot[0], covered_spot[1], fh
    x, y = _awacs_clear_of_raids(state, x, y, fh)      # S193: only when no covered spot exists: the S191 move away from red is the last resort
    return x, y, fh


AWACS_RAID_NM = 40          # S188: the AWACS racetrack stays this far from the lines this turn's red raids fly (escort fighters' radar and missile reach plus the AWACS's turn-away time; judgment call, no source: S174 and S183 runs lost it to raid escorts)
AWACS_SWEEP_NM = 100        # S189 (XO 2026-11-24, fair play: red sweeps may hunt the tanker and the AWACS, so they keep their distance): the AWACS racetrack stays this far from the route a red sweep flies (its field to the raid's target). Measured in the S174 and S183 runs: a red sweep shot the AWACS and the tanker while 93 to 217 km (50 to 117 nm) from its own bombers; 100 nm is round the farthest of them, judgment call
TANKER_SWEEP_NM = 100       # S189: ...and the same for a tanker track
AWACS_FAN_DEG = 90          # S191 (replaces S188's straight-back search, AWACS_RAID_BACK_MAX_NM 60 / AWACS_RAID_BACK_STEP_NM 10): a spot is tried this many degrees either side of the back axis (away from red)...
AWACS_FAN_STEP_DEG = 15     # ...in steps of this many degrees...
AWACS_FAN_MAX_NM = 150      # ...and out to this far from the first station (measured, S191: on Caucasus Level 3 a clear spot was never within 60 nm straight back, 45 of 62 raid turns; a fan finds one on every turn, moves of 70 to 100 nm)...
AWACS_FAN_STEP_NM = 10      # ...in steps of this many nm
AWACS_MAP_MARGIN_NM = 20    # S191: a spot stays this far inside the map edge (judgment call: the racetrack is 40 nm long and the AWACS must not sit on the edge)
AWACS_RED_MIN_NM = 90       # S191: and at least this far from red's nearest fighter field, as `safe_marshal`'s own flat rule (and never nearer to red than the first station: without that rule the nearest clear spot swung east toward Tbilisi, 78 nm from red)
TANKER_RAID_NM = 50         # S188: a tanker track stays this far from the lines the mission's red raids fly: 40 nm (escort fighters' radar and missile reach plus the tanker's turn-away time, judgment call) plus 10 nm because the real escort and sweep routes lie up to 10 nm nearer than the straight field-to-target line (measured in the S174 mission: line 44.4 nm, route 34.3 nm). The S174 run lost Arco 1 to escorts that started 25 km from the track


def raid_lines_from_booked(state) -> tuple:
    """S188: -> (raid lines, sweep lines), each [(x1, y1, x2, y2)]: straight lines from each red wing a raid booked this turn (`state.raids["booked"]`) to the raid's target; raider, escort and pooled wings
    in the first list, sweep wings (`sweep_wing`, `sweep_pool`; S189) in the second. Reads the state only (the AWACS station must be the same for every package of a turn). An unbent line: the S171 ring
    bends move a route only a few nm, and the margin covers it."""
    lines = []
    sweep_lines = []
    booked = (getattr(state, "raids", None) or {}).get("booked") or {}
    for oid in sorted(booked):
        plan = booked[oid]
        dest = plan.get("dest")
        if not dest or not plan.get("land"):
            continue
        wing_ids = {plan.get("bomber_wing"), plan.get("escort_wing")}
        for partner in (plan.get("pool") or []):
            wing_ids.add(partner.get("wing"))
        for partner in (plan.get("esc_pool") or []):
            wing_ids.add(partner.get("wing"))
        sweep_ids = {plan.get("sweep_wing")}
        for partner in (plan.get("sweep_pool") or []):
            sweep_ids.add(partner.get("wing"))
        wing_ids -= sweep_ids
        for wing_id in sorted(w for w in wing_ids if w):
            field = state.assets.get(wing_id)
            if field is None:
                continue
            lines.append((field.x, field.y, float(dest[0]), float(dest[1])))
        for wing_id in sorted(w for w in sweep_ids if w):
            field = state.assets.get(wing_id)
            if field is None:
                continue
            sweep_lines.append((field.x, field.y, float(dest[0]), float(dest[1])))
    return lines, sweep_lines


def _awacs_racetrack_margin_nm(x, y, fh, lines, sweep_lines) -> float:
    """S191: how far (nm) the AWACS racetrack (the station and both ends, 20 nm either side) is clear of this turn's red lines: the smallest of (distance - AWACS_RAID_NM) to every raid line and
    (distance - AWACS_SWEEP_NM) to every sweep line. >= 0 means clear; 1e9 when there are no lines."""
    side = math.radians(fh + 90)
    points = [(x, y), (x + 20 * NM * math.cos(side), y + 20 * NM * math.sin(side)), (x - 20 * NM * math.cos(side), y - 20 * NM * math.sin(side))]
    worst = 1e9
    for point_x, point_y in points:
        for line in lines:
            worst = min(worst, _seg_nm(point_x, point_y, *line) - AWACS_RAID_NM)
        for line in sweep_lines:
            worst = min(worst, _seg_nm(point_x, point_y, *line) - AWACS_SWEEP_NM)
    return worst


def _awacs_under_cover(state, x, y, fh):
    """S193 (XO 2026-11-24: "let them go back closer to SAM protection and CAP protection"): the AWACS station under blue cover. -> (x, y), or None when no covered spot passes the hard limits
    (the caller then runs the S191 move away from red). The first station (x, y) stays when it is covered and its racetrack is clear of this turn's raid / sweep lines. Otherwise: spots on three
    rings (the centre, half way, 5 nm inside the edge) round every cover circle (`blue_cover_circles`) in 30 degree steps, within `AWACS_FAN_MAX_NM` of the first station, inside the map
    (`AWACS_MAP_MARGIN_NM`), outside SAM rings and red fields (`spot_slack`), at least `AWACS_RED_MIN_NM` and no nearer to red's nearest fighter field than the first station. The best spot:
    the racetrack margin to the raid / sweep lines capped at `AWACS_COVER_MARGIN_CAP_NM` (a covered spot is never given up for more margin than that), then the smallest move. Reads the state only."""
    circles = blue_cover_circles(state)
    if not circles:
        return None
    lines, sweep_lines = raid_lines_from_booked(state)
    first_margin = _awacs_racetrack_margin_nm(x, y, fh, lines, sweep_lines)
    first_covered = in_blue_cover(circles, x, y)
    if first_covered and first_margin >= 0:
        return x, y
    from . import theatres
    top, bottom, left, right = theatres.map_edges()
    edge = AWACS_MAP_MARGIN_NM * NM
    red_fields = fighter_bases(state)
    least_red_nm = AWACS_RED_MIN_NM
    if red_fields:
        least_red_nm = max(AWACS_RED_MIN_NM, min(math.hypot(field_x - x, field_y - y) for field_x, field_y in red_fields) / NM)
    candidates = []
    if first_covered:
        candidates.append((x, y))
    for circle_x, circle_y, circle_nm in circles:
        for ring_nm in (0.0, circle_nm / 2.0, circle_nm - 5.0):
            for bearing_deg in range(0, 360, 30):
                if ring_nm == 0.0 and bearing_deg > 0:
                    break
                heading = math.radians(bearing_deg)
                candidates.append((circle_x + ring_nm * NM * math.cos(heading), circle_y + ring_nm * NM * math.sin(heading)))
    best = None
    for spot_x, spot_y in candidates:
        move_nm = math.hypot(spot_x - x, spot_y - y) / NM
        if move_nm > AWACS_FAN_MAX_NM:
            continue
        if not (bottom + edge <= spot_x <= top - edge and left + edge <= spot_y <= right - edge):
            continue
        if red_fields and min(math.hypot(field_x - spot_x, field_y - spot_y) for field_x, field_y in red_fields) / NM < least_red_nm:
            continue
        if spot_slack(state, spot_x, spot_y, (x, y)) < 0:
            continue
        margin = _awacs_racetrack_margin_nm(spot_x, spot_y, fh, lines, sweep_lines)
        score = (min(margin, AWACS_COVER_MARGIN_CAP_NM), -move_nm)
        if best is None or score > best[0]:
            best = (score, spot_x, spot_y)
    if best is None:
        return None
    return best[1], best[2]


def _awacs_clear_of_raids(state, x, y, fh):
    """S188, S191: the AWACS station moved off this turn's red raid and sweep lines until its racetrack (the station and both ends, 20 nm either side) is `AWACS_RAID_NM` / `AWACS_SWEEP_NM` clear of them.
    The search is a fan behind the first station (x, y): `AWACS_FAN_DEG` either side of the back axis (away from red, `fh` + 180) in `AWACS_FAN_STEP_DEG` steps, out to `AWACS_FAN_MAX_NM` in
    `AWACS_FAN_STEP_NM` steps. A spot must also be clear of SAM rings and red fields (`spot_slack`), inside the map (`AWACS_MAP_MARGIN_NM`), and no nearer to red's nearest fighter field than the first
    station and not nearer than `AWACS_RED_MIN_NM`. The smallest move that is clear wins; at that distance the straight-back spot (what S188 chose), else the one with the larger margin. When no spot is
    clear, the allowed spot with the largest margin (never worse than the first station). Unchanged when no raid is booked or when the first station is already clear. Reads only the state."""
    lines, sweep_lines = raid_lines_from_booked(state)
    if not lines and not sweep_lines:
        return x, y
    start_margin = _awacs_racetrack_margin_nm(x, y, fh, lines, sweep_lines)
    if start_margin >= 0:
        return x, y
    from . import theatres
    top, bottom, left, right = theatres.map_edges()
    edge = AWACS_MAP_MARGIN_NM * NM
    red_fields = fighter_bases(state)
    start_to_red_nm = 0.0
    if red_fields:
        start_to_red_nm = min(math.hypot(field_x - x, field_y - y) for field_x, field_y in red_fields) / NM
    least_red_nm = max(AWACS_RED_MIN_NM, start_to_red_nm)
    best_any = (start_margin, x, y)                  # the fallback when nothing is clear: the largest margin, never below the first station's own
    back_heading = fh + 180
    deltas = [0]
    delta = AWACS_FAN_STEP_DEG
    while delta <= AWACS_FAN_DEG:
        deltas.append(delta)
        deltas.append(-delta)
        delta += AWACS_FAN_STEP_DEG
    back_nm = AWACS_FAN_STEP_NM
    while back_nm <= AWACS_FAN_MAX_NM:
        clear_here = None                            # (straight back first, margin, x, y) of the best clear spot at this distance
        for delta in deltas:
            heading = math.radians(back_heading + delta)
            spot_x = x + back_nm * NM * math.cos(heading)
            spot_y = y + back_nm * NM * math.sin(heading)
            if not (bottom + edge <= spot_x <= top - edge and left + edge <= spot_y <= right - edge):
                continue
            if red_fields and min(math.hypot(field_x - spot_x, field_y - spot_y) for field_x, field_y in red_fields) / NM < least_red_nm:
                continue
            if spot_slack(state, spot_x, spot_y, (x, y)) < 0:
                continue
            margin = _awacs_racetrack_margin_nm(spot_x, spot_y, fh, lines, sweep_lines)
            if margin > best_any[0]:
                best_any = (margin, spot_x, spot_y)
            if margin >= 0:
                candidate = (delta == 0, margin, spot_x, spot_y)
                if clear_here is None or candidate[:2] > clear_here[:2]:
                    clear_here = candidate
        if clear_here is not None:
            return clear_here[2], clear_here[3]
        back_nm += AWACS_FAN_STEP_NM
    return best_any[1], best_any[2]


def tanker_station(state, base_xy, toward_xy, min_enemy_nm: float = 150, ring_margin_nm: float = 20):
    """A tanker track behind the FLOT: far from enemy fighter bases and outside every SAM ring. None if no such spot."""
    bx, by = base_xy
    mx, my = toward_xy
    enemies = fighter_bases(state)
    rs = rings(state, min_range=3)
    for f in (0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.1):
        x, y = bx + (mx - bx) * f, by + (my - by) * f
        if enemies and min(math.hypot(x - ex, y - ey) for ex, ey in enemies) / NM < min_enemy_nm:
            continue
        if any(math.hypot(x - a.x, y - a.y) < r + ring_margin_nm * NM for a, r in rs):
            continue
        return x, y
    return None


def safe_egress(state, tx, ty, hdg, egr_nm, skip_ids=()):
    """Pick the egress bearing that stays clear of live SAM rings (target cluster excluded)."""
    rs = [(a, r) for a, r in rings(state) if a.id not in skip_ids]
    best, best_clear = None, -1e18
    for off in (100, -100, 150, -150, 60, -60, 180):
        h = math.radians(hdg + off)
        x, y = tx + egr_nm * NM * math.cos(h), ty + egr_nm * NM * math.sin(h)
        clear = min((math.hypot(x - a.x, y - a.y) - r for a, r in rs), default=1e12)
        if clear > 5 * NM:
            return x, y
        if clear > best_clear:
            best, best_clear = (x, y), clear
    return best


MAX_ROUTE_SITES = 2     # SAM sites that merely touch the route (not the target's own cluster) that are spawned: keeps VR frame rate sane


def corridor_sam_sites(state, polyline, target_asset, margin_nm: float = 10, max_route: int = MAX_ROUTE_SITES) -> list:
    """The target's own SAM cluster, plus the few live sites whose ring reaches deepest into the route corridor."""
    skip = cluster_ids(target_asset)
    out, route = [], []
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed:
            continue
        r = RANGE_NM.get(a.variant, 0) * NM
        near_target = target_asset is not None and math.hypot(a.x - target_asset.x, a.y - target_asset.y) < 12_000
        if a.id in skip or near_target:
            out.append(a)
        elif r >= SERIOUS_NM * NM and poly_dist(a.x, a.y, polyline) < r + margin_nm * NM:
            route.append((r - poly_dist(a.x, a.y, polyline), a))
    def first_field(row):
        return row[0]
    route.sort(key=first_field, reverse=True)
    return out + [a for _, a in route[:max_route]]


def point_back_along(poly, d_back: float):
    """Position d_back metres back from the END of a polyline, and the heading to the next point."""
    pts = list(poly)
    remaining = d_back
    for i in range(len(pts) - 1, 0, -1):
        (x1, y1), (x0, y0) = pts[i], pts[i - 1]
        seg = math.hypot(x1 - x0, y1 - y0)
        if remaining <= seg:
            f = 1.0 - remaining / max(seg, 1e-9)
            return (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f), i
        remaining -= seg
    return pts[0], 1


FIELD_DETECT_NM = 60.0      # an alert field scrambles when blue comes within this of the field (less for fields close to the fight)
MARSHAL_STANDOFF_NM = (85, 95, 105, 120, 140, 165, 195, 230)   # S77: the mission marshal's distances from the target, nearest first (judgment call: BMS-style push 10 nm out, a long ingress, still over friendly ground)
MARSHAL_MIN_NM = 40          # S97: the nearest the marshal goes to the target (judgment call: PUSH is 10 nm out and the IP 12 nm, so 40 nm leaves a real ingress)
MARSHAL_STEP_NM = 10         # S97: the stand-off steps outward by this when a spot fails the field / SAM / ridge tests
MARSHAL_LEG_MAX_FT = 8000.0   # S88: the highest ground within 5 nm of the straight leg from a flight's base to the marshal (judgment call: an A-10C climbs about 5 m/s, so it cannot clear 2,000 m ridges 25 km out)
MARSHAL_FIELD_MARGIN_NM = 10.0   # v0.41.6: a marshal point stays this far outside every enemy field's detection circle


FIELD_SAM_NM = 15.0         # v0.41.8: a live long-range SAM this close to an enemy field is its radar...
FIELD_SAM_DETECT_NM = 50.0  # ...and the field then sees this far (the v0.41.6 Gudauta run: the stand-off wave stayed outside a 29 nm circle,
                            # HARMed and bombed the SA-10 next to the field, and not one alert pair was called)


RAMP_LEAD_NM = 30.0         # v0.41.92: extra scramble-circle radius when alert pairs wait hot on the ramp and taxi (see set_ramp_lead)
_LEAD_NM = 0.0              # the lead in force for the mission being built (MissionBuilder.build sets it from the hot-ramp setting)


def set_ramp_lead(on: bool) -> None:
    """v0.41.92: hot-ramp pairs take 5 to 9 minutes from the call to the air (XO's 2026-10-21 runs: 324 to 566 s at Gudauta, 283 and 290 s at Nalchik;
    the hidden runway start is about 2 minutes), so with the setting on the circles are larger by what blue covers in the 4 extra minutes
    (about 500 kt = 8 nm a minute, 30 nm). Judgment call from those runs. Planning keep-outs (marshal, sweep, carrier BARCAP) read the same radius."""
    global _LEAD_NM
    _LEAD_NM = RAMP_LEAD_NM if on else 0.0


def field_detect_nm(field_xy, target_xy, state=None) -> float:
    """v0.41.1: the radius of an enemy field's scramble circle, round the field itself, sized by how far it is from the fight.
    v0.41.8: with state given, a field with a live long-range SAM (an SA-10) within FIELD_SAM_NM sees at least FIELD_SAM_DETECT_NM."""
    d = math.hypot(field_xy[0] - target_xy[0], field_xy[1] - target_xy[1]) / NM
    r = max(25.0, min(FIELD_DETECT_NM, 0.6 * d + 15.0))
    if _LEAD_NM:
        r = max(r, min(r + _LEAD_NM, 0.85 * d + 15.0))              # never past what the fight's own distance justifies
    if state is not None and any(a.variant in UMBRELLA_VARIANTS and not a.destroyed and a.health > 0.30
                                 and math.hypot(a.x - field_xy[0], a.y - field_xy[1]) / NM <= FIELD_SAM_NM for a in state.assets.values()):
        r = max(r, FIELD_SAM_DETECT_NM)
    return r


def package_refs(state, flights) -> list:
    """S77: where a package's flights come from: the (x, y) of the base of every flight that is not a support patrol (HVAACAP, BARCAP), one entry per flight. safe_marshal takes it as `refs`."""
    return [(state.bases[f.base_id].x, state.bases[f.base_id].y) for f in flights if not getattr(f, 'tag', '') and getattr(f, 'base_id', None) in state.bases]


MARSHAL_SLOW_CLIMBERS = frozenset({"A-10C", "A-10A", "A-10C2"})   # S95: the jets the ridge test (MARSHAL_LEG_MAX_FT) is for: they climb too slowly to clear a ridge on the way to the marshal
MARSHAL_MAX_NM = {"A-10C": 120, "A-10A": 120, "A-10C2": 120}                # S95 (judgment call): the farthest stand-off a package with this jet gets (a Hog's fuel is the limit: S93, a 230 nm marshal cost it the sortie)


def package_marshal(state, base_xy, hdg_to_target, target_xy, flights):
    """S95: the package's marshal. `refs` is every flight's base (the axis); the ridge test uses only the slow climbers' bases, the stand-off is capped by the shortest-legged jet."""
    fl = [f for f in flights if not getattr(f, 'tag', '')]
    slow = [(state.bases[f.base_id].x, state.bases[f.base_id].y) for f in fl if getattr(f, 'aircraft', '') in MARSHAL_SLOW_CLIMBERS and getattr(f, 'base_id', None) in state.bases]
    caps = [MARSHAL_MAX_NM[f.aircraft] for f in fl if getattr(f, 'aircraft', '') in MARSHAL_MAX_NM]
    return safe_marshal(state, base_xy, hdg_to_target, target_xy, refs=package_refs(state, flights), ridge_refs=slow, max_nm=min(caps) if caps else None)


def safe_marshal(state, base_xy, hdg_to_target, target_xy=None, min_enemy_nm: float = 90, ring_margin_nm: float = 20, refs=None, ridge_refs=None, max_nm=None):
    """Marshal point BEHIND the base: clear of enemy fighter fields and at least ring_margin_nm outside every SAM ring.
    v0.41.6: with the target known, a field only needs the marshal outside its own scramble circle (field_detect_nm) plus a margin, not a flat
    90 nm (which sent the Senaki Vipers 54 nm south to hold, then back north past their own base). Without it, the old flat distance.
    Tries close-in first, directly behind, then swings to the sides. Returns the best spot found (never None)."""
    bx, by = base_xy
    enemies = [(ex, ey, (field_detect_nm((ex, ey), target_xy, state) + MARSHAL_FIELD_MARGIN_NM) if target_xy is not None else min_enemy_nm)
               for ex, ey in fighter_bases(state)]
    rs = rings(state, min_range=3)
    if target_xy is not None:
        # S77 (XO 2026-11-14): the marshal serves the MISSION, not whoever flies it: a spot a fixed stand-off from the target on the axis toward the
        # nearest friendly airfield, the same for every flight and every base (it used to sit 15-62 nm behind the player's own base).
        tx, ty = target_xy
        # The axis: toward where the package's flights come from (`refs`: the mean direction from the target to each flight's base, so a package
        # from two sides gets the middle), else toward the nearest friendly airfield, else straight behind `base_xy`. Bearings as in `back` below.
        axis = None
        ux = uy = 0.0
        for rx, ry in (refs or []):
            dd = math.hypot(rx - tx, ry - ty)
            if dd > 1.0:
                ux += (rx - tx) / dd; uy += (ry - ty) / dd
        if math.hypot(ux, uy) > 0.2 * max(len(refs or []), 1):
            axis = math.degrees(math.atan2(uy, ux)) % 360
        if axis is None:
            fx = [(math.hypot(b.x - tx, b.y - ty), b.x, b.y) for b in state.bases.values()
                  if b.kind == BaseKind.AIRFIELD and not getattr(b, "divert", False)]
            axis = math.degrees(math.atan2(min(fx)[2] - ty, min(fx)[1] - tx)) % 360 if fx else (hdg_to_target + 180) % 360
        from . import relief
        legs = list(ridge_refs if ridge_refs is not None else (refs or [base_xy]))      # S95: only the slow climbers' legs are tested; None = every flight's (the old way)
        # S97 (XO 2026-11-16): the search starts near the base that is closest to the target (+10 nm), not at a fixed 85 nm that put the marshal 50 nm past a
        # nearby base; never nearer than MARSHAL_MIN_NM nor farther than the old first ring to start from. The field / SAM / ridge tests are what keep it safe.
        near_nm = min([math.hypot(rx - tx, ry - ty) / NM for rx, ry in (refs or [base_xy])] or [MARSHAL_STANDOFF_NM[0]])
        first_nm = min(MARSHAL_STANDOFF_NM[0], max(MARSHAL_MIN_NM, near_nm + 10))
        rings_nm = []
        k = first_nm
        while k <= MARSHAL_STANDOFF_NM[-1]:
            rings_nm.append(k)
            k += MARSHAL_STEP_NM
        best, best_key = None, None
        for nm in rings_nm:
            if max_nm is not None and nm > max_nm and best is not None:
                break                                                                          # S95: never beyond the range cap (the first ring is always tried)
            for ang in (0, 35, -35, 70, -70, 105, -105):
                h = math.radians(axis + ang)
                x, y = tx + nm * NM * math.cos(h), ty + nm * NM * math.sin(h)
                slack = min([(math.hypot(x - ex, y - ey) / NM) - need for ex, ey, need in enemies] +
                            [(math.hypot(x - a.x, y - a.y) - r) / NM - ring_margin_nm for a, r in rs] + [1e9])
                # S88: the flight climbs straight from its base to the marshal: no spot behind high ground (2026-11-15 run: four A-10Cs hit the Lesser Caucasus)
                hi = max([relief.leg_max_ft(r_, (x, y)) or 0.0 for r_ in legs], default=0.0)
                ok_ = hi <= MARSHAL_LEG_MAX_FT
                if ok_ and slack >= 0:
                    return x, y
                # nothing passes both tests: out of every ring first (slack >= 0), then the lowest ridge, then the nearest (the first seen); S95: it used to keep the highest slack = the farthest spot
                key = (slack >= 0, -hi if slack >= 0 else slack)
                if best_key is None or key > best_key:
                    best, best_key = (x, y), key
        return best
    back = hdg_to_target + 180
    best, best_slack = None, -1e18
    for nm in (15, 20, 25, 32, 40, 50, 62):
        for ang in (0, 35, -35, 70, -70, 105, -105):
            h = math.radians(back + ang)
            x, y = bx + nm * NM * math.cos(h), by + nm * NM * math.sin(h)
            slack = min([(math.hypot(x - ex, y - ey) / NM) - need for ex, ey, need in enemies] +
                        [(math.hypot(x - a.x, y - a.y) - r) / NM - ring_margin_nm for a, r in rs] + [1e9])
            if slack >= 0:
                return x, y
            if slack > best_slack:
                best, best_slack = (x, y), slack
    return best


def spot_slack(state, x, y, target_xy, ring_margin_nm: float = 20, field_margin_nm: float = MARSHAL_FIELD_MARGIN_NM) -> float:
    """v0.41.7: how far (nm) a friendly orbit at (x, y) is clear of every SAM ring (plus ring_margin_nm) and every enemy field's scramble circle
    (plus field_margin_nm). >= 0 means clear."""
    fs = [math.hypot(x - ex, y - ey) / NM - field_detect_nm((ex, ey), target_xy, state) - field_margin_nm for ex, ey in fighter_bases(state)]
    rs = [(math.hypot(x - a.x, y - a.y) - r) / NM - ring_margin_nm for a, r in rings(state, min_range=3)]
    return min(fs + rs + [1e9])


def nearest_threat_bearing(state, x, y, fallback: float) -> float:
    """v0.41.7: the bearing from (x, y) to the nearest enemy fighter field (where raids and chasers come from); fallback when there is none."""
    fb = fighter_bases(state)
    if not fb:
        return fallback
    ex, ey = None, None
    nearest_base_m = None
    for fighter_base in fb:
        fighter_base_m = math.hypot(fighter_base[0] - x, fighter_base[1] - y)
        if nearest_base_m is None or fighter_base_m < nearest_base_m:
            ex, ey = fighter_base
            nearest_base_m = fighter_base_m
    return math.degrees(math.atan2(ey - y, ex - x)) % 360


TANKER_CAP_NM = 40          # v0.41.26: a tanker track stays this far from every red patrol station
TANKER_LANE_NM = 25         # ...and this far from the line an enemy field's fighters fly to the fight
TANKER_MARGIN_NM = 20       # ...and this far outside every SAM ring and every enemy field's scramble circle (v0.41.7: 15)


def _seg_nm(px, py, ax, ay, bx, by) -> float:
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(ax + t * vx - px, ay + t * vy - py) / NM


def tanker_spot(state, base_xy, egr_xy, target_xy, caps=(), lanes=(), cover=(), half_track_nm: float = 15, track_hdg: float | None = None, raid_lines=(), sweep_lines=(), report=None):
    """v0.41.26: the tanker track centre. Between the action and home, where the package can use it, but a minimum distance from every danger:
    TANKER_MARGIN_NM outside every SAM ring and every enemy field's scramble circle, TANKER_CAP_NM from every red patrol station (caps: [(x, y)]),
    TANKER_LANE_NM from the lines red fighters fly in on (lanes: [(field x, y, target x, y)]), S188: TANKER_RAID_NM from the raids' routes (raid_lines: [(x1, y1, x2, y2)]), both ends of the racetrack included.
    S193 (XO 2026-11-24: a tanker out where there is no cover is no use): the SAM rings and scramble circles stay hard; the other distances are goals. The order of choice, all on the line from
    home to the egress point (so within reach of the flights): (1) a spot under cover (cover: [(x, y, nm)]) that is clear of everything, furthest forward; (2) a spot under cover that is not clear:
    the one with the largest margin (the least bad distance to a patrol, lane, raid or sweep), at most `TANKER_SOFT_FLOOR_NM` inside a limit; (3) a clear spot with no cover, furthest forward; (4) behind the home field (up to 40 nm); None
    when nothing is clear. `report` (a dict, optional) gets `case` (1 to 4) and `margin` (nm, negative = inside a limit). The XO's Nalchik run: the tanker sat in the middle of the fight and was shot down."""
    bx, by = base_xy
    ex, ey = egr_xy
    h = math.degrees(math.atan2(ey - by, ex - bx))
    th = h + 90 if track_hdg is None else track_hdg

    def track_ends(x, y):
        return [(x, y), (x + half_track_nm * NM * math.cos(math.radians(th)), y + half_track_nm * NM * math.sin(math.radians(th))),
                (x - half_track_nm * NM * math.cos(math.radians(th)), y - half_track_nm * NM * math.sin(math.radians(th)))]

    def hard_ok(x, y):
        for px, py in track_ends(x, y):
            if spot_slack(state, px, py, target_xy, TANKER_MARGIN_NM, TANKER_MARGIN_NM) < 0:
                return False
        return True

    def margin_nm(x, y):
        """The smallest of (distance - limit) over both ends and every patrol, lane, raid and sweep: >= 0 means clear of all of them."""
        worst = 1e9
        for px, py in track_ends(x, y):
            for cx, cy in caps:
                worst = min(worst, math.hypot(px - cx, py - cy) / NM - TANKER_CAP_NM)
            for fx, fy, gx, gy in lanes:
                worst = min(worst, _seg_nm(px, py, fx, fy, gx, gy) - TANKER_LANE_NM)
            for fx, fy, gx, gy in raid_lines:               # S188: the red raids' own routes
                worst = min(worst, _seg_nm(px, py, fx, fy, gx, gy) - TANKER_RAID_NM)
            for fx, fy, gx, gy in sweep_lines:              # S189: the red sweeps' routes (they hunt)
                worst = min(worst, _seg_nm(px, py, fx, fy, gx, gy) - TANKER_SWEEP_NM)
        return worst

    def covered(x, y):
        for cover_x, cover_y, cover_nm in cover:
            if math.hypot(x - cover_x, y - cover_y) / NM <= cover_nm:
                return True
        return False

    clear_covered = []
    soft_covered = []
    clear_open = []
    for k, f in enumerate((0.5, 0.45, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05, 0.0)):
        cx, cy = bx + (ex - bx) * f, by + (ey - by) * f
        for side in (0, 10, -10, 20, -20, 30, -30):
            x, y = cx + side * NM * math.cos(math.radians(h + 90)), cy + side * NM * math.sin(math.radians(h + 90))
            if not hard_ok(x, y):
                continue
            margin = margin_nm(x, y)
            is_covered = covered(x, y)
            if margin >= 0 and is_covered:
                clear_covered.append((k, abs(side), x, y, margin))
            elif is_covered and margin >= -TANKER_SOFT_FLOOR_NM:
                soft_covered.append((-margin, k, abs(side), x, y, margin))
            elif margin >= 0:
                clear_open.append((k, abs(side), x, y, margin))
    if clear_covered:
        clear_covered.sort()
        if report is not None:
            report["case"], report["margin"] = 1, clear_covered[0][4]
        return clear_covered[0][2], clear_covered[0][3]
    if soft_covered:
        soft_covered.sort()
        if report is not None:
            report["case"], report["margin"] = 2, soft_covered[0][5]
        return soft_covered[0][3], soft_covered[0][4]
    if clear_open:
        clear_open.sort()
        if report is not None:
            report["case"], report["margin"] = 3, clear_open[0][4]
        return clear_open[0][2], clear_open[0][3]
    for back in (5, 10, 15, 20, 25, 30, 35, 40):
        for side in (0, 10, -10, 20, -20):
            x = bx - back * NM * math.cos(math.radians(h)) + side * NM * math.cos(math.radians(h + 90))
            y = by - back * NM * math.sin(math.radians(h)) + side * NM * math.sin(math.radians(h + 90))
            if hard_ok(x, y) and margin_nm(x, y) >= 0:
                if report is not None:
                    report["case"], report["margin"] = 4, margin_nm(x, y)
                return x, y
    return None


def first_safe_egress(state, tx, ty, hdg_to_target, skip_ids=(), min_nm: float = 8, max_nm: float = 60, margin_nm: float = 4, avoid=()):
    """EGR = the FIRST safe point after the target: the closest point (8 nm and out) that is clear of every live SAM ring (plus a margin).
    Bearings that turn for home are tried first; among equals, the one farther from enemy fighter bases wins (away from their CAP).
    avoid = [(x, y, nm)] extra keep-out circles (enemy CAP stations, fighter bases).
    Returns None when nothing within max_nm is clear (the caller falls back to safe_egress)."""
    rs = [(a, r) for a, r in rings(state, min_range=3) if a.id not in skip_ids]
    enemies = fighter_bases(state)
    best, best_score = None, 1e18
    for k, off in enumerate((150, -150, 120, -120, 180, 90, -90, 60, -60)):
        h = math.radians(hdg_to_target + off)
        r = min_nm
        while r <= max_nm:
            x, y = tx + r * NM * math.cos(h), ty + r * NM * math.sin(h)
            if all(math.hypot(x - a.x, y - a.y) >= rr + margin_nm * NM for a, rr in rs) and \
                    all(math.hypot(x - ax, y - ay) >= anm * NM for ax, ay, anm in avoid):
                far = min((math.hypot(x - ex, y - ey) for ex, ey in enemies), default=0) / NM
                score = r - 0.08 * min(far, 150) + 0.4 * k
                if score < best_score:
                    best, best_score = (x, y), score
                break
            r += 2
    return best
