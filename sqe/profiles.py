"""Threat-aware altitude profiles: HIGH / MED / LOW from the SAM picture.

Every package used to fly its role's fixed altitude. Now the planner looks at which live SAM sites cover the part of the route from the PUSH to
the egress (their ring, from threatmap.RANGE_NM), asks whether each of them can engage at each candidate altitude, and picks the altitude that
is least exposed. With no threat, or when nothing is better, the profile is exactly what it was before (the role altitude).

  * PUSH stays at the role altitude (the long cruise, easy on fuel); the tier applies from the IP to the egress.
  * A lower profile has to be clearly safer (MIN_GAIN) to be chosen; radar SAMs count half against a LOW flight (terrain masking, radar horizon).
  * LOW is flown as height above the ground (DCS "radio altitude"), so the flight follows the terrain.
  * Which tiers are open depends on the role and the jet: SEAD and escorts never go LOW, CAS only chooses between its usual altitude and LOW,
    a jet marked no_low (the FC3 F-15C) never does, and a cloud base under 2,000 ft closes LOW.

Pure planning (no pydcs). The engagement bands and weights below are hand-set approximations, not published figures: tune freely.
"""
from __future__ import annotations
from dataclasses import dataclass
from .models import AssetKind, Role
from . import threatmap as tm

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
    if role in (Role.STRIKE, Role.SEAD, Role.ESCORT) and med < base:
        out.append(("med", med, False))
    if role in (Role.STRIKE, Role.CAS) and not p.no_low:
        out.append(("low", p.low_agl_ft, True))
    return out


def covering(state, pts, tgt, skip=()) -> list:
    """Live SAM/AAA sites whose ring reaches the route from the PUSH on: [(asset, variant, where)]."""
    out = []
    for a in state.assets.values():
        if a.kind != AssetKind.SAM or a.destroyed or a.health <= 0.25 or a.id in skip:
            continue
        r = tm.RANGE_NM.get(a.variant, 0)
        if r <= 0:
            continue
        reach = (r + COVER_MARGIN_NM) * NM
        if tm.poly_dist(a.x, a.y, pts) <= reach:
            near_tgt = ((a.x - tgt[0]) ** 2 + (a.y - tgt[1]) ** 2) ** 0.5 <= reach
            out.append((a, a.variant, "target" if near_tgt else "route"))
    return out


def hits(v: str, alt_ft: int) -> bool:
    lo, hi = ENVELOPE.get(v, (0, 40000))
    return lo <= alt_ft <= hi


def exposure(sites, alt_ft: int, rad: bool = False) -> float:
    s = 0.0
    for _a, v, _w in sites:
        if hits(v, alt_ft):
            s += WEIGHT.get(v, 1.0) * (LOW_RADAR_FACTOR if (rad and v in RADAR) else 1.0)
    return s


def choose(state, role, p, pts, tgt, cloud_base_ft: float | None = None, skip=()) -> Tier:
    """pts: the route from PUSH to egress as [(x, y)]; tgt: (x, y); skip: asset ids that are the objective itself (a DEAD target is the site we are
    killing, so it does not push the package low). Returns the profile to fly."""
    cands = [c for c in candidates(p, role) if not (c[0] == "low" and cloud_base_ft is not None and cloud_base_ft < LOW_MIN_CLOUD_FT)]
    base = cands[0]
    t0 = Tier(label_for(base[1], base[2]), base[1], base[2])
    if len(cands) == 1:
        return t0
    sites = covering(state, pts, tgt, skip)
    if not sites:
        return t0
    score = lambda c: exposure(sites, c[1], c[2]) + PENALTY[c[0]]
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
    return Tier(lab, best[1], best[2], f"{lab} from the IP: {names} {verb} the {where} at {label_for(base[1], base[2])} altitude.", True)
