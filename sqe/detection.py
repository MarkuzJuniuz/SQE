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


def red_covered(state, x: float, y: float) -> bool:
    """A live early-warning radar of red's within EWR_COVER_NM of the point."""
    lim = EWR_COVER_NM * NM
    for a in state.assets.values():
        if a.kind == AssetKind.EWR and not a.destroyed and a.health > ground.DOWN_HEALTH and ((a.x - x) ** 2 + (a.y - y) ** 2) ** 0.5 <= lim:
            return True
    return False


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


def verdict(package) -> str:
    """The stored verdict; "full" when none is stored."""
    return (getattr(package, "extra", None) or {}).get("detect", "full")


def unseen(package) -> bool:
    return verdict(package) == "barcap"


def any_full(package, extras=()) -> bool:
    """A merged mission: red scrambles if ANY package in it was seen."""
    return any(not unseen(p) for p in [package, *extras])
