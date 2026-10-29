"""Threat-aware altitude profiles: HIGH / MED / LOW from the SAM picture.

Every package used to fly its role's fixed altitude. Now the planner looks at which live SAM sites cover the part of the route from the PUSH to
the egress (their ring, from threatmap.RANGE_NM), asks whether each of them can engage at each candidate altitude, and picks the altitude that
is least exposed. With no threat, or when nothing is better, the profile is exactly what it was before (the role altitude).

  * PUSH stays at the role altitude (the long cruise, easy on fuel); the tier applies from the IP to the egress.
  * With the ground-height scan (relief.py) a LOW flight is judged against what each radar can really see over the terrain, and MED is never planned below
    the minimum safe altitude of the IP-to-egress legs. Without it the old flat estimate applies.
  * A lower profile has to be clearly safer (MIN_GAIN) to be chosen; radar SAMs count half against a LOW flight (terrain masking, radar horizon).
  * LOW is flown as height above the ground (DCS "radio altitude"), so the flight follows the terrain.
  * Which tiers are open depends on the role and the jet: SEAD and escorts never go LOW, neither does a DEAD package (its target is a defended cluster), CAS only chooses between its usual altitude and LOW,
    a jet marked no_low (the FC3 F-15C) never does, and a cloud base under 2,000 ft closes LOW.

Pure planning (no pydcs). The engagement bands and weights below are hand-set approximations, not published figures: tune freely.
"""
from __future__ import annotations
from dataclasses import dataclass
from .models import AssetKind, Role
from . import relief, threatmap as tm

NM = 1852.0
# (lowest, highest) altitude in ft at which the system realistically engages. Hand-set.
ENVELOPE = {"AAA": (0, 10000), "MANPAD": (0, 10000), "SA-8": (0, 16000), "SA-15": (0, 20000), "SA-19": (0, 11000), "SA-3": (300, 45000),
            "SA-6": (300, 45000), "SA-11": (100, 70000), "SA-10": (200, 90000), "SA-2": (1500, 80000)}
# How much each system matters when it covers the route (the long-range ones hurt most).
WEIGHT = {"AAA": 1.0, "MANPAD": 1.0, "SA-8": 1.5, "SA-15": 2.0, "SA-19": 1.0, "SA-3": 1.5, "SA-6": 2.0, "SA-11": 2.5, "SA-10": 3.0, "SA-2": 1.5}
RADAR = {"SA-2", "SA-3", "SA-6", "SA-10", "SA-11"}         # radar-guided: terrain masking and the radar horizon cut their reach against a LOW flight
LOW_RADAR_FACTOR = 0.5
MIN_GAIN = 0.5                                              # a lower profile has to be at least this much safer than the role altitude
PENALTY = {"base": 0.0, "med": 0.25, "low": 0.75}          # a lower profile costs fuel and is harder to fly
COVER_MARGIN_NM = 2.0
LOW_MIN_CLOUD_FT = 2000


@dataclass
class Tier:
    label: str = "HIGH"
    alt_ft: int = 0
    rad: bool = False            # alt_ft is height above ground
    reason: str = ""             # one line for the kneeboard; empty when the profile did not change
    changed: bool = False


def label_for(alt_ft: int, rad: bool) -> str:
    return "LOW" if rad else ("HIGH" if alt_ft >= 18000 else "MED")


def candidates(p, role) -> list:
    """[(kind, alt_ft, rad)] open to this role and jet, the role's normal altitude first."""
    base = p.alt_ft.get(role, 20000)
    med = p.med_alt_ft or max(10000, int(round(base * 0.6 / 1000.0)) * 1000)
    out = [("base", base, False)]
    if role in (Role.STRIKE, Role.SEAD, Role.TARCAP) and med < base:
        out.append(("med", med, False))
    if role in (Role.STRIKE, Role.CAS) and not p.no_low:
        out.append(("low", p.low_agl_ft, True))
    return out


def covering(state, pts, tgt, skip=()) -> list:
    """Live SAM/AAA sites whose ring reaches the route from the PUSH on: [(asset, variant, where)]."""
    out = []
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed or a.id in skip:               # any site with a unit left counts (a mop-up target at 11% still shoots)
            continue
        r = tm.RANGE_NM.get(a.variant, 0)
        if r <= 0:
            continue
        reach = (r + COVER_MARGIN_NM) * NM
        if tm.poly_dist(a.x, a.y, pts) <= reach:
            near_tgt = ((a.x - tgt[0]) ** 2 + (a.y - tgt[1]) ** 2) ** 0.5 <= reach
            out.append((a, a.variant, "target" if near_tgt else "route"))
    out += _ground_aa(state, pts, tgt, skip)
    return out


GROUND_AA_KINDS = (AssetKind.ARMOR, AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT, AssetKind.AIRFIELD)   # sites that carry ZSU-23-4s, Strela / Osa and MANPADs
GROUND_AA_MERGE_M = 6000.0                                 # one cluster of vehicles and buildings counts as one AAA site


def _ground_aa(state, pts, tgt, skip=()) -> list:
    """Anti-aircraft that travels with columns, garrisons and the support sites. It only reaches a flight that is LOW (AAA / MANPAD envelope, 0-10,000 ft),
    so it keeps the 'go LOW' choice honest: a column's guns beside the target outweigh a SAM that the terrain hides. -> [(site, "AAA", where)]"""
    out, seen = [], []
    reach = (tm.RANGE_NM.get("AAA", 3) + COVER_MARGIN_NM) * NM
    for a in state.assets.values():
        if a.kind not in GROUND_AA_KINDS or a.destroyed or a.id in skip or getattr(a, "health", 1.0) <= 0.15:
            continue
        if any(((a.x - x) ** 2 + (a.y - y) ** 2) ** 0.5 < GROUND_AA_MERGE_M for x, y in seen):
            continue
        if tm.poly_dist(a.x, a.y, pts) <= reach:
            seen.append((a.x, a.y))
            near_tgt = ((a.x - tgt[0]) ** 2 + (a.y - tgt[1]) ** 2) ** 0.5 <= reach
            out.append((a, "AAA", "target" if near_tgt else "route"))
    return out


def hits(v: str, alt_ft: int) -> bool:
    lo, hi = ENVELOPE.get(v, (0, 40000))
    return lo <= alt_ft <= hi


def low_factor(a, v: str, route, agl_ft: float) -> float:
    """How much of its weight a radar SAM keeps against a LOW flight: the share of the route it can actually see (ground height measured by the
    scan, so a ridge in the way counts), never below 0.2; the flat LOW_RADAR_FACTOR when there is no relief file."""
    if route:
        f = relief.visible_fraction((a.x, a.y), route, agl_ft, tm.RANGE_NM.get(v, 0) * NM)
        if f is not None:
            return max(0.2, min(1.0, f))
    return LOW_RADAR_FACTOR


def exposure(sites, alt_ft: int, rad: bool = False, route=None) -> float:
    s = 0.0
    for a, v, _w in sites:
        if hits(v, alt_ft):
            s += WEIGHT.get(v, 1.0) * (low_factor(a, v, route, alt_ft) if (rad and v in RADAR) else 1.0)
    return s


def choose(state, role, p, pts, tgt, cloud_base_ft: float | None = None, skip=(), msa_ft: int | None = None) -> Tier:
    """pts: the route from PUSH to egress as [(x, y)]; tgt: (x, y); skip: asset ids that are the objective itself (a DEAD target is the site we are
    killing, so it does not push the package low). Returns the profile to fly."""
    cands = [c for c in candidates(p, role) if not (c[0] == "low" and cloud_base_ft is not None and cloud_base_ft < LOW_MIN_CLOUD_FT)
             and not (c[0] == "low" and skip)                                         # a DEAD package (the only one with a skip) never goes LOW: its target is a defended cluster
             and not (c[0] == "med" and msa_ft is not None and c[1] < msa_ft)]          # MED is dropped when it would sit below the safe altitude
    base = cands[0]
    t0 = Tier(label_for(base[1], base[2]), base[1], base[2])
    if len(cands) == 1:
        return t0
    sites = covering(state, pts, tgt, skip)
    if not sites:
        return t0
    score = lambda c: exposure(sites, c[1], c[2], pts[1:]) + PENALTY[c[0]]
    best = min(cands, key=lambda c: (score(c), cands.index(c)))
    if best is base or score(base) - score(best) < MIN_GAIN:
        return t0
    # name what the change actually gets away from: sites that engage the role altitude but not the new one (or only weakly)
    hit = sorted({(v, w) for _a, v, w in sites if hits(v, base[1]) and (not hits(v, best[1]) or (best[2] and v in RADAR))},
                 key=lambda t: -WEIGHT.get(t[0], 1.0))
    names = ", ".join(dict.fromkeys(v for v, _w in hit))
    where = "target" if any(w == "target" for _v, w in hit) else "route"
    lab = label_for(best[1], best[2])
    verb = "covers" if len({v for v, _w in hit}) == 1 else "cover"
    frm = "from the LOW point, 30 nm out" if best[2] else "from the IP"           # v0.41.16: the low leg starts 30 nm from the target
    return Tier(lab, best[1], best[2], f"{lab} {frm}: {names} {verb} the {where} at {label_for(base[1], base[2])} altitude.", True)


# ---- fighters stand off from live SAM cover ---------------------------------------------------------------------------------------
STANDOFF_MARGIN_NM = 5.0       # stop this far outside the ring of the first live SAM that can reach the flight's altitude
                                # v0.41.37: 5 nm outside medium/short-range SAM rings
STANDOFF_MIN_SHORT_NM = 4.0     # only worth moving if the stand-off point is at least this far short of the target


def standoff(state, pts, alt_ft: int, margin_nm: float = STANDOFF_MARGIN_NM):
    """Where a sweep or an escort should stop so it never flies into the umbrella of a live SAM site: the last point on the route (PUSH -> IP -> target,
    walked in 1 nm steps) outside every ring (plus the margin) of a SAM that can engage `alt_ft`. -> (x, y, [variants that stopped it], nm short of the
    target) or None when the route is clear of live SAM cover, the flight already starts inside it, or the stop would be hardly short of the target."""
    sites = []
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed:                  # any site with a unit left shoots: a mop-up target at 11% still has its radar and launchers
            continue
        r = tm.RANGE_NM.get(a.variant, 0)
        if r <= 0 or not hits(a.variant, alt_ft):
            continue
        sites.append((a, a.variant, (r + margin_nm) * NM))
    if not sites or len(pts) < 2:
        return None
    path = []
    for p0, p1 in zip(pts, pts[1:]):
        d = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
        n = max(1, int(d // NM))
        path += [(p0[0] + (p1[0] - p0[0]) * k / n, p0[1] + (p1[1] - p0[1]) * k / n) for k in range(n)]
    path.append(pts[-1])
    def cover(pt):
        return [(a, v) for a, v, reach in sites if ((a.x - pt[0]) ** 2 + (a.y - pt[1]) ** 2) ** 0.5 <= reach]
    if cover(path[0]):
        return None
    for i, pt in enumerate(path):
        c = cover(pt)
        if c:
            stop = path[i - 1]
            short = ((stop[0] - pts[-1][0]) ** 2 + (stop[1] - pts[-1][1]) ** 2) ** 0.5 / NM
            if short < STANDOFF_MIN_SHORT_NM:
                return None
            names = sorted({v for _a, v in c}, key=lambda v: -WEIGHT.get(v, 1.0))
            return stop[0], stop[1], names, short
    return None


STATION_SHORT_NM = 12.0
STATION_FRAC = 0.85             # against a long-range SAM: the station sits this fraction of its reach from it (about 36 nm for an SA-10).
                                # v0.41.1: 0.62 (30 nm) was inside where the SA-10 really engaged (59-61 km) and it killed six Eagles there
                                # v0.41.37: 0.85 of the long-range SAM reach (40 nm from SA-10)

STATION_OFFSET_NM = 9.0         # ...moved this far sideways toward the nearest enemy airfield
LONG_RANGE_NM = 30.0            # a SAM that reaches this far counts as long-range for the station rule


def _long_range_threat(state, tgt, alt_ft):
    """The live long-range SAM (reach >= LONG_RANGE_NM, able to engage alt_ft) whose ring covers the target, longest reach first. -> (asset, nm) or None"""
    best = None
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed or getattr(a, "suppressed", False):
            continue
        r = tm.RANGE_NM.get(a.variant, 0)
        if r < LONG_RANGE_NM or not hits(a.variant, alt_ft):
            continue
        if ((a.x - tgt[0]) ** 2 + (a.y - tgt[1]) ** 2) ** 0.5 > r * NM:
            continue
        if best is None or r > best[1]:
            best = (a, r)
    return best


def _nearest_enemy_field(state, x, y):
    fl = [a for a in state.assets.values() if a.kind == AssetKind.AIRFIELD and not a.destroyed]
    return min(fl, key=lambda a: (a.x - x) ** 2 + (a.y - y) ** 2) if fl else None         # a TARCAP / escort station with no SAM cover in the way: this far short of the target, on the run-in


def _cover_sites(state, alt_ft, margin_nm=STANDOFF_MARGIN_NM):
    out = []
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed:
            continue
        r = tm.RANGE_NM.get(a.variant, 0)
        if r > 0 and hits(a.variant, alt_ft):
            out.append((a, (r + margin_nm) * NM))
    return out


def leg_clear(state, p0, p1, alt_ft) -> bool:
    """Does the straight leg p0 -> p1 stay outside every live SAM ring (plus the margin) that reaches alt_ft?"""
    sites = _cover_sites(state, alt_ft)
    d = ((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5
    n = max(1, int(d // NM))
    for k in range(n + 1):
        x, y = p0[0] + (p1[0] - p0[0]) * k / n, p0[1] + (p1[1] - p0[1]) * k / n
        if any(((a.x - x) ** 2 + (a.y - y) ** 2) ** 0.5 <= reach for a, reach in sites):
            return False
    return True


CAS_STATION_NM = 30.0           # v0.41.177 (XO 2026-10-28, 3 CAS runs): a CAS TARCAP / escort under a long-range SAM sits this far from the CAS target, on the push side (v0.41.181: 25, was 20, XO: it protects the package, it does not hunt) (judgment call: AIM-120 / AIM-7 reach covers the A-10s from there; the old rule left it 35-40 nm away and it never fired)
CAS_STATION_SWINGS = tuple(range(0, 181, 15))


def cas_station(state, pts, alt_ft: int, egr=None):
    """v0.41.177: a CAS fighter station within reach of the A-10s. Candidate points CAS_STATION_NM from the target, swung off the push bearing
    (15 degrees at a time, either side, up to 180); the first one outside every live SAM ring wins, else the one with the most room. Same tuple as station()."""
    import math
    tx, ty = pts[-1]
    px, py = pts[0]
    b0 = math.atan2(py - ty, px - tx)
    sites = _cover_sites(state, alt_ft)
    best = None
    for sw in CAS_STATION_SWINGS:
        for sgn in ((1,) if sw in (0, 180) else (1, -1)):
            b = b0 + math.radians(sw * sgn)
            x, y = tx + math.cos(b) * CAS_STATION_NM * NM, ty + math.sin(b) * CAS_STATION_NM * NM
            room = min((((a.x - x) ** 2 + (a.y - y) ** 2) ** 0.5 - r for a, r in sites), default=1e9)
            if room > 0:
                best = (x, y, room)
                break
            if best is None or room > best[2]:
                best = (x, y, room)
        if best is not None and best[2] > 0:
            break
    x, y = best[0], best[1]
    lr = _long_range_threat(state, pts[-1], alt_ft)
    names = [lr[0].variant] if lr else []
    ok = egr is not None and leg_clear(state, (x, y), egr, alt_ft)
    return x, y, names, CAS_STATION_NM, ok


def station(state, pts, alt_ft: int, egr=None):
    """A TARCAP's or an escort's own station: the stand-off point when live SAM cover is in the way, else STATION_SHORT_NM short of the
    target on the run-in (never behind the first point). -> (x, y, [variants], nm short of the target, package egress clear from there)."""
    so = standoff(state, pts, alt_ft)
    lr = _long_range_threat(state, pts[-1], alt_ft)
    if lr is not None:
        # v0.41.0: against a long-range SAM (an SA-10) the stand-off edge left the TARCAP ~20 nm behind the HARM shooters it covers (v0.40.10 run:
        # the F-15Cs never fired). Now it sits STATION_FRAC of that SAM's reach from it, on our side (toward the first route point), level with
        # the HARM shooters, and STATION_OFFSET_NM toward the nearest enemy airfield, between the threat and the package.
        a, reach_nm = lr
        px, py = pts[0]
        d0 = ((px - a.x) ** 2 + (py - a.y) ** 2) ** 0.5 or 1.0
        ux, uy = (px - a.x) / d0, (py - a.y) / d0
        r = STATION_FRAC * reach_nm * NM
        x, y = a.x + ux * r, a.y + uy * r
        fld = _nearest_enemy_field(state, x, y)
        if fld is not None:
            vx, vy = -uy, ux                                   # perpendicular to the SAM -> station line; pick the side the field is on
            sgn = 1.0 if ((fld.x - x) * vx + (fld.y - y) * vy) >= 0 else -1.0
            x, y = x + sgn * vx * STATION_OFFSET_NM * NM, y + sgn * vy * STATION_OFFSET_NM * NM
        tx, ty = pts[-1]
        names, short = [a.variant], ((x - tx) ** 2 + (y - ty) ** 2) ** 0.5 / NM
    elif so:
        x, y, names, short = so
    else:
        tx, ty = pts[-1]
        px, py = pts[-2]
        leg = ((tx - px) ** 2 + (ty - py) ** 2) ** 0.5 / NM
        short = min(STATION_SHORT_NM, max(0.0, leg - 1.0)) if leg > 0 else 0.0
        f = short / leg if leg > 0 else 0.0
        x, y, names = tx + (px - tx) * f, ty + (py - ty) * f, []
    ok = egr is not None and leg_clear(state, (x, y), egr, alt_ft)
    return x, y, names, short, ok
