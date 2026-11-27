"""Red detection by early-warning radar (v0.41.346, campaign rules plan Phase 7a).

Red sees a blue package coming when one of its early-warning radars (AssetKind.EWR) is alive within EWR_COVER_NM of the target. An unseen package still
has a chance of being met in full (red guesses, XO's notes 2026-11-08). The verdict is cast ONCE per package at plan time (`Session.plan_turn`, next to
the SEAD dice) and stored in `package.extra["detect"]`, "full" or "barcap". The war sim (`WarSimulator.odds`, `_red_reaction`) and the mission builder (alert,
standby, relief and reactive pairs) read that one stored answer, so a package the sim calls unseen never meets a full scramble in DCS, or the other way round.
A package with no stored verdict (an old save, a raid, a patrol) reads as "full", today's behaviour.

* "full": red answers as it always did: the planned CAP picture, alert pairs, standby and relief pairs, reactive pairs.
* "barcap": red's planned CAP picture and sweeps still fly (they are on station anyway), but nothing is scrambled for THIS package, and the war sim
  multiplies the red air cover by BARCAP_ONLY_AIR and draws no reaction pair from the hold.
"""
from __future__ import annotations
import math
import random

from .models import AssetKind, ObjectiveType
from . import ground

NM = 1852.0
EWR_COVER_NM = 120          # judgment call (plan section 7): the 1L13 / 55G6 are long-range VHF sets, from memory well over this against high targets; one export table gives about 135 nm
                            # against a fighter at 10 km and about 27 nm at 500 m, so 120 is a conservative middle for strikers that come in low
UNSEEN_GUESS = 0.25         # chance red meets an unseen package in full anyway (XO notes 2026-11-08; judgment call)
UNSEEN_GUESS_SUPPLY = 0.10  # the same for a supply target (fuel, depot): nothing to defend there that red would guess at (judgment call)
BARCAP_ONLY_AIR = 0.4       # war sim: red's air-cover term against a package it did not see (judgment call)

JUDGED = (ObjectiveType.STRIKE, ObjectiveType.DEAD, ObjectiveType.CAS, ObjectiveType.COUNTER_AIR)    # blue packages against red; BARCAP and FLEET_DEFENSE get no verdict


def red_covered(state, x: float, y: float, exclude: str | None = None) -> bool:
    """A live early-warning radar of red's within EWR_COVER_NM of the point. `exclude`: an EWR id to leave out, as if dead (nothing is mutated)."""
    lim = EWR_COVER_NM * NM
    for a in state.assets.values():
        if a.id != exclude and a.kind == AssetKind.EWR and not a.destroyed and a.health > ground.DOWN_HEALTH and ((a.x - x) ** 2 + (a.y - y) ** 2) ** 0.5 <= lim:
            return True
    return False


TARGET_KINDS = (AssetKind.SAM, AssetKind.FUEL, AssetKind.DEPOT, AssetKind.C2, AssetKind.ARMOR, AssetKind.AIRFIELD)


def gap_share(state, ewr) -> float:
    """v0.41.347: share (0 to 1) of red's live targets (SAM, fuel, depot, C2, armor, airfield) that are covered now but would be uncovered with this EWR dead."""
    tg = [a for a in state.assets.values() if a.kind in TARGET_KINDS and not a.destroyed]
    if not tg:
        return 0.0
    n = sum(1 for a in tg if red_covered(state, a.x, a.y) and not red_covered(state, a.x, a.y, exclude=ewr.id))
    return n / len(tg)


def cast(state, package) -> str | None:
    """"full" or "barcap" for a blue package against red; None for a package that gets no verdict."""
    obj = package.objective
    if obj.type not in JUDGED or obj.target_id not in state.assets:
        return None
    t = state.assets[obj.target_id]
    if red_covered(state, t.x, t.y):
        return "full"
    p = UNSEEN_GUESS_SUPPLY if t.kind in ground.SUPPLY_KINDS else UNSEEN_GUESS
    rng = random.Random(f"{state.campaign_id}:{state.turn}:{obj.id}:detect")
    return "full" if rng.random() < p else "barcap"


BLUE_COVER_KEYS = ("bl_e3", "bl_e2")      # Phase 7b: blue's early-warning aircraft (the E-3 and the carrier's E-2C)


def blue_covered(state, turn: int) -> bool:
    """v0.41.348 (Phase 7b): blue sees red's raids when an E-3 or E-2C is on orbit in this turn (the theatre is small, plan section 7). Reads the day's windows `support_assets.plan` stored; no plan at all
    (an old save) says covered."""
    from . import clock
    fl = (getattr(state, "barcap", None) or {}).get("support_flights")
    if not fl:
        return True
    lo = clock.minute(turn) - clock.day_start_minute(clock.day_of(turn))
    hi = lo + clock.TURN_MIN
    return any(e > lo and s < hi for k in BLUE_COVER_KEYS for s, e in fl.get(k, []))


def is_raid(state, package) -> bool:
    """A red raid built from `raids.turn_raids` (id obj-t<turn>-r<n> / -s<n>, booked); not the carrier raid setpiece."""
    import re
    oid = package.objective.id or ""
    return bool(re.match(r"^obj-t\d+-[rs]\d+$", oid)) and oid in ((getattr(state, "raids", None) or {}).get("booked") or {})


# S181 P2: an AWACS sees a raid only within its radar's reach of its own orbit (it was the whole theatre)
E3_RADAR_NM = 220.0         # the E-3's radar sees low-flying targets beyond 250 statute miles = 217 nm (USAF E-3 Sentry fact sheet; medium to high firmness)
E2C_RADAR_NM = 160.0        # the E-2C's APS-145: no primary figure found (secondary sources say 300+ miles, low firmness); judgment call, kept well inside the E-3's
RAID_SEEN_WAY_IN_NM = 100.0 # a raid is seen when its target or any point of this last stretch of its way in lies inside a radar's reach (judgment call: time enough to scramble)
RADAR_NM = {"bl_e3": E3_RADAR_NM, "bl_e2": E2C_RADAR_NM}
E3_COVERS_THEATRE = ("bl_e3",)   # these see every raid while up (see raid_covered); E3_RADAR_NM is kept for a later two-orbit E-3


def _on_orbit(state, key: str, turn: int) -> bool:
    """Is an airframe of this asset on orbit at some time in this turn (the day's windows `support_assets.plan` stored)?"""
    from . import clock
    fl = (getattr(state, "barcap", None) or {}).get("support_flights") or {}
    lo = clock.minute(turn) - clock.day_start_minute(clock.day_of(turn))
    hi = lo + clock.TURN_MIN
    for start, end in fl.get(key, []):
        if end > lo and start < hi:
            return True
    return False


def _station_of(state, key: str):
    """Where this AWACS orbits -> (x, y) or None: the E-3 on its turn's station (`threatmap.awacs_station`), the E-2C over the carrier."""
    from . import threatmap
    from .models import BaseKind
    if key == "bl_e3":
        station = threatmap.awacs_station(state)
        if station is None:
            return None
        return station[0], station[1]
    for base in state.bases.values():
        if base.kind == BaseKind.CARRIER:
            return base.x, base.y
    return None


def _distance_to_leg(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """Metres from the point (px, py) to the nearest point of the straight leg a -> b."""
    dx = bx - ax
    dy = by - ay
    squared = dx * dx + dy * dy
    share = 0.0
    if squared > 0:
        share = ((px - ax) * dx + (py - ay) * dy) / squared
    share = max(0.0, min(1.0, share))
    return math.hypot(ax + share * dx - px, ay + share * dy - py)


def _raid_way_in(state, package):
    """The raid's last RAID_SEEN_WAY_IN_NM stretch -> (start x, start y, target x, target y), from its bomber wing's field to the booked target; None when it cannot be told."""
    plan = ((getattr(state, "raids", None) or {}).get("booked") or {}).get(package.objective.id) or {}
    dest = plan.get("dest")
    field = state.assets.get(plan.get("bomber_wing") or "")
    if not dest or field is None:
        return None
    tx = float(dest[0])
    ty = float(dest[1])
    length = math.hypot(tx - field.x, ty - field.y)
    stretch = RAID_SEEN_WAY_IN_NM * NM
    if length <= stretch:
        return field.x, field.y, tx, ty
    share = 1.0 - stretch / length
    return field.x + (tx - field.x) * share, field.y + (ty - field.y) * share, tx, ty


def raid_covered(state, package, turn: int) -> bool:
    """S181 P2: is this raid inside the reach of an AWACS on orbit this turn? No support plan at all (an old save) says covered; a raid whose way in cannot be told falls back to
    the old rule (any AWACS up covers it)."""
    fl = (getattr(state, "barcap", None) or {}).get("support_flights")
    if not fl:
        return True
    way_in = _raid_way_in(state, package)
    for key in BLUE_COVER_KEYS:
        if not _on_orbit(state, key, turn):
            continue
        # The E-3 up covers the whole theatre, as before: SQE flies one E-3 station, kept back for its safety, where an air force would fly a second orbit over a front
        # this wide (probe 2026-11-27: measured from that one station, 31 to 33 % of Syria's raids went unseen with the E-3 up). Judgment call; only the E-2C is limited.
        if key in E3_COVERS_THEATRE:
            return True
        if way_in is None:
            return True
        station = _station_of(state, key)
        if station is None:
            continue
        reach_m = RADAR_NM[key] * NM
        if _distance_to_leg(station[0], station[1], *way_in) <= reach_m:
            return True
    return False


def blue_cast(state, package, turn: int) -> str:
    """"seen" or "unseen" for a red raid. Covered (S181 P2: inside an AWACS's reach): seen. Not covered: seen anyway with UNSEEN_GUESS (seeded per campaign, turn, raid)."""
    if raid_covered(state, package, turn):
        return "seen"
    rng = random.Random(f"{state.campaign_id}:{turn}:{package.objective.id}:detect")
    return "seen" if rng.random() < UNSEEN_GUESS else "unseen"


def verdict(package) -> str:
    """The stored verdict; "full" when none is stored."""
    return (getattr(package, "extra", None) or {}).get("detect", "full")


def unseen(package) -> bool:
    return verdict(package) == "barcap"


def any_full(package, extras=()) -> bool:
    """A merged mission: red scrambles if ANY package in it was seen."""
    return any(not unseen(p) for p in [package, *extras])
