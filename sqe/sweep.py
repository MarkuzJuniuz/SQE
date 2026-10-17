"""v0.41.33: Fighter Sweep against known enemy air in the open (XO 2026-10-16).

A sweep is a separate package that hunts enemy fighters. It is no longer sent to bait red (v0.41.13 put its station inside the nearest red
field's scramble circle, at the very edge of SAM reach; XO's run of 2026-10-16 22:15 lost two F-15Cs of Dodge 2 to the Sukhumi S-300 in the
first 95 seconds, shot from 34 nm at 30,000 ft). The rules now:

* Command sends a sweep only against a KNOWN enemy flight (red's own air plan for the day, state.red_air: its patrol pairs and sweeps, each
  with a station and a time window) that sits out in the open: not under SAM cover. Until such a flight exists, the packages' own TARCAP and
  escorts carry the fight.
* The sweep's station is short of that flight, on the line from it toward the sweep's home, far enough back that SAMs cannot reach the sweep
  (wider margins than other flights: SWEEP_SA10_NM, SWEEP_RING_MARGIN_NM), close enough that the flight is inside the sweep's fight circle.

Doctrine: AFDP 3-01 (Counterair): a sweep is "an offensive mission by fighter aircraft to seek out and destroy enemy aircraft ... in a
designated area", and "the need for fighter sweep missions ... will depend on the air and missile threat". That supports the trigger (a known
air threat). Keeping the sweep out of SAM reach is not in the doctrine: it is a judgment call from XO's runs (DCS AI fighters do not evade
SAMs well, so the plan has to keep them out of reach).

Pure planning, no pydcs.
"""
from __future__ import annotations
from .models import AssetKind, BaseKind
from .routes import AVOID_NM, NM, bearing, dist, offset
from . import threatmap as tm

SWEEP_SA10_NM = 45.0         # judgment call: the 2026-10-16 run's S-300 hit an F-15C at 30,000 ft from 34 nm (62.9 km), past the 35 nm route rule
SWEEP_RING_MARGIN_NM = 20.0  # judgment call: other SAM rings (threatmap.RANGE_NM) plus this (the old sweep rule was +15)
OPEN_MARGIN_NM = 12.0        # a red flight is "in the open" this far outside every SAM's reach (routes.AVOID_NM, already reach plus a margin):
                             # judgment call, so the sweep's fight circle (SAM-clear by AVOID_NM) can take in both its station and the red one
AREA_NM = 80.0               # a red station this close to a covered package's target counts as that area's air threat
REACH_NM = 20.0              # the sweep's station sits this far short of the red station (inside its 25 nm fight circle, room to spare)
WINDOW_BEFORE_MIN = 10       # the red flight must be up in the window from this long before the first covered package starts...
WINDOW_AFTER_MIN = 60        # ...to this long after it (the sweep's time out, on station and back in the fight circle)


def _sams(state) -> list:
    return [a for a in state.assets.values()
            if a.kind == AssetKind.SAM and not a.destroyed and a.health > 0.25 and not getattr(a, "suppressed", False)]


def in_open(state, x, y) -> bool:
    """A red station out in the open: outside every live medium / long-range SAM's reach (AVOID_NM) by OPEN_MARGIN_NM."""
    return all(dist(x, y, a.x, a.y) >= (AVOID_NM[a.variant] + OPEN_MARGIN_NM) * NM for a in _sams(state) if a.variant in AVOID_NM)


def clear_for_sweep(state, x, y) -> bool:
    """A sweep's station: SWEEP_SA10_NM from every live SA-10, SWEEP_RING_MARGIN_NM outside every other SAM ring of 3 nm or more."""
    for a in _sams(state):
        if a.variant in tm.UMBRELLA_VARIANTS:
            if dist(x, y, a.x, a.y) < SWEEP_SA10_NM * NM:
                return False
        elif tm.RANGE_NM.get(a.variant, 0) >= 3 and dist(x, y, a.x, a.y) < (tm.RANGE_NM[a.variant] + SWEEP_RING_MARGIN_NM) * NM:
            return False
    return True


def _scramble_free(state, x, y, tx, ty) -> bool:
    """Outside every red field's scramble circle (the sweep does not set off red's alert pairs: no baiting)."""
    return all(dist(x, y, ex, ey) > tm.field_detect_nm((ex, ey), (tx, ty), state) * NM for ex, ey in tm.fighter_bases(state))


def station_for(state, red_xy, home_xy, tx, ty):
    """The sweep's station against a red flight at red_xy: on the line from it toward home, REACH_NM short of it first, then further back or
    swung up to 60 degrees off that line, nearest first; clear of SAMs (clear_for_sweep), outside red's scramble circles where it can be.
    -> (x, y) or None (no clear station within reach of the red flight)."""
    rx, ry = red_xy
    b0 = bearing(rx, ry, *home_xy)
    cands = [offset(rx, ry, b0 + ang, rr * NM) for rr in (REACH_NM, REACH_NM - 4, REACH_NM + 4)
             for ang in (0, 15, -15, 30, -30, 45, -45, 60, -60)]
    clear = [p for p in cands if clear_for_sweep(state, *p)]
    if not clear:
        return None
    return next((p for p in clear if _scramble_free(state, p[0], p[1], tx, ty)), clear[0])


def _home_guess(state, x, y):
    """The nearest friendly airfield or carrier (the planner does not know the sweep's base until the package is built)."""
    bs = [b for b in state.bases.values() if b.kind in (BaseKind.AIRFIELD, BaseKind.CARRIER)]
    b = min(bs, key=lambda b: dist(b.x, b.y, x, y), default=None)
    return (b.x, b.y) if b is not None else (x, y)


def candidates(state, tx, ty) -> list:
    """Red's planned flights near this area that a sweep could take: patrol pairs and sweeps in the open with a clear station short of them."""
    out = []
    for f in (getattr(state, "red_air", None) or {}).get("flights", []):
        if f.get("kind") not in ("CAP", "SWEEP"):
            continue
        a = state.assets.get(f.get("wing"))
        if a is None or a.destroyed:
            continue
        if dist(f["x"], f["y"], tx, ty) > AREA_NM * NM or not in_open(state, f["x"], f["y"]):
            continue
        if station_for(state, (f["x"], f["y"]), _home_guess(state, f["x"], f["y"]), tx, ty) is None:
            continue
        out.append(f)
    return out


def up_in(f, lo_min: int, hi_min: int) -> bool:
    """Is this red flight up at some time in [lo_min, hi_min] (minutes of the day; its window may run past midnight)?"""
    for s in (0, 1440, -1440):
        if f["start"] + s <= hi_min and f["end"] + s >= lo_min:
            return True
    return False


def pick(state, tx, ty, first_start_min: int):
    """The red flight this sweep goes after: a candidate up in its window, nearest the area first. None: no sweep today."""
    lo, hi = first_start_min - WINDOW_BEFORE_MIN, first_start_min + WINDOW_AFTER_MIN
    c = [f for f in candidates(state, tx, ty) if up_in(f, lo, hi)]
    return min(c, key=lambda f: (dist(f["x"], f["y"], tx, ty), f["id"])) if c else None
