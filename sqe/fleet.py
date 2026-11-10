"""The fleet can be sunk (v0.41.257, XO 2026-11-03).

A flown mission shows what really happened to the carrier group: the hook reports every ship that went down (the carrier is unit
"<base name> Unit #1", the three escorts "<base name> escort N Unit #1") and when. Until now the war log ignored it.

* Carrier sunk: everything aboard goes down with it: the aircraft that did not fly in the mission, and any that landed back on the deck
  before it sank. The aircraft still flying land at the nearest field and their squadron moves there (the same machinery as a fallen
  field: `Squadron.home_id`, the move nights). For SUNK_DAYS days the fleet is gone: no carrier launches, no fleet patrols, no support aircraft
  from the boat, no bomber raid on it, and it counts as ONE fallen base towards the defeat rule (one more fallen field and the campaign is lost).
  On day `returns_day` a new ship arrives "as new": air defence full, the carrier squadrons back at full strength, and they fly home.
* Escort ship sunk (the carrier afloat or not): the group's air defence is cut while it is out (ESCORT_DEFENSE per ship, the cruiser most),
  the ship is missing from the missions for ESCORT_DAYS days, then replaced.
* A raid nobody flew keeps the old "big hit" model (carrier_hit.py); it never sinks the ship.

Saved in `state.fleet` (older saves have none: nothing sunk). All numbers are judgment calls: no public figure applies to a game carrier, tune on XO's runs.
"""
from __future__ import annotations
import math

from .models import BaseKind

SUNK_DAYS = 7                  # the carrier group sails back in after this many days (XO: "1 week")
ESCORT_DAYS = 7                # a sunk escort is replaced after the same time
ESCORT_DEFENSE = (0.30, 0.25, 0.15)      # share of the group's air defence each escort carries: cruiser, destroyer, frigate (judgment call; the cruiser has the area-defence radar)
DEFENSE_FLOOR = 0.2            # the same floor as carrier_hit


def _f(state) -> dict:
    d = getattr(state, "fleet", None)
    if d is None:
        d = {}
        state.fleet = d
    return d


def carrier_base(state):
    """The carrier's Base, afloat or not (squadrons name it as their home)."""
    return next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)


def sunk(state) -> bool:
    return bool((getattr(state, "fleet", None) or {}).get("sunk_day"))


def carrier(state):
    """The carrier's Base, or None while it is sunk: the one place everything that plans with the boat asks."""
    return None if sunk(state) else carrier_base(state)


def is_sunk_base(state, base_id: str) -> bool:
    cv = carrier_base(state)
    return cv is not None and cv.id == base_id and sunk(state)


def days_left(state) -> int:
    f = getattr(state, "fleet", None) or {}
    return max(0, int(f.get("returns_day", 0)) - state.day) if f.get("sunk_day") else 0


def counts_as_fallen(state) -> int:
    """The sunk carrier is one lost base for the defeat rule while it is away (XO)."""
    return 1 if sunk(state) else 0


def escort_out(state, k: int) -> bool:
    return str(k) in ((getattr(state, "fleet", None) or {}).get("escorts") or {})


def unit_names(cv) -> tuple:
    """(carrier unit name, [escort unit names]) as the mission builder names them."""
    return f"{cv.name} Unit #1", [f"{cv.name} escort {k + 1} Unit #1" for k in range(len(ESCORT_DEFENSE))]


def _death_t(data: dict, name: str):
    return next((float(d["t"]) for d in (data.get("deaths") or []) if d.get("n") == name and d.get("t") is not None), None)


def sunk_in(state, data: dict) -> bool:
    """Did the carrier go down in this mission?"""
    cv = carrier_base(state)
    return cv is not None and not sunk(state) and unit_names(cv)[0] in set(data.get("dead", []))


def _cap(state) -> float:
    f = getattr(state, "fleet", None) or {}
    cut = sum(ESCORT_DEFENSE[int(k)] for k in (f.get("escorts") or {}))
    return max(DEFENSE_FLOOR, 1.0 - cut)


def apply_debrief(state, manifest, data: dict) -> list:
    """-> log lines for the ships lost in a flown mission; applies the sinking (see the module doc)."""
    cv = carrier_base(state)
    if cv is None or sunk(state):
        return []
    cv_name, esc_names = unit_names(cv)
    dead = set(data.get("dead", []))
    new_esc = [k for k, n in enumerate(esc_names) if n in dead and not escort_out(state, k)]
    sank = cv_name in dead
    if not sank and not new_esc:
        return []
    f = _f(state)
    esc = f.setdefault("escorts", {})
    for k in new_esc:
        esc[str(k)] = state.day + ESCORT_DAYS
    head = ([f"{cv.name.split('(')[0].strip()} sunk"] if sank else []) + ([f"{len(new_esc)} escort{'s' if len(new_esc) > 1 else ''} sunk"] if new_esc else [])
    lines = ["Fleet losses: " + ", ".join(head) + ". We mourn the crews."]
    if new_esc and not sank:
        cv.defense = min(cv.defense, _cap(state))
        lines.append(f"   the group's air defence is down to {cv.defense:.0%} until the escorts are replaced in {ESCORT_DAYS} days")
    if not sank:
        return lines
    f["sunk_day"], f["returns_day"] = state.day, state.day + SUNK_DAYS
    for k in range(len(esc_names)):                                    # the whole group is rebuilt with the ship
        esc.pop(str(k), None)
    t_sink = _death_t(data, cv_name)
    lost_set = set(data.get("dead", [])) | set(data.get("ejected", []))
    landings = data.get("landings") or {}
    from . import ground, raids
    dest = raids._nearest_field(state, cv.x, cv.y)
    for sq in sorted((s for s in state.squadrons.values() if s.base_id == cv.id), key=lambda s: s.id):
        units = [u for g in manifest.groups if g["kind"] == "friendly" and g.get("squadron") == sq.id for u in g["units"]]
        flying = [u for u in units if u not in lost_set]
        aboard = [u for u in flying if u in landings and t_sink is not None and float(landings[u].get("t", 1e9)) <= t_sink
                  and (not landings[u].get("p") or cv.name in landings[u]["p"])]
        left_ = max(0, sq.available - len(flying))                    # the aircraft that never flew today: on deck or in the hangar
        down = left_ + len(aboard)
        survivors = len(flying) - len(aboard)
        sq.available = max(0, survivors)
        sq.reserve = sq.rest_days = sq.move_days = sq.move_until = 0
        txt = f"   {sq.name}: {down} aircraft went down with the ship"
        if dest is not None:
            sq.home_id = sq.home_id or cv.id
            sq.base_id = dest.id
            txt += (f"; {sq.available} landed at {dest.name}" + ground._settle(state, sq, math.hypot(dest.x - cv.x, dest.y - cv.y))) if sq.available else "; none got away"
        lines.append(txt)
    cv.defense = DEFENSE_FLOOR
    lines.append(f"Carrier sunk, returning in {SUNK_DAYS} days.")
    return lines


def step(state) -> list:
    """Once a day, at the planning: the sunk carrier comes back as new on its day; escorts are replaced; defence stays capped while escorts are out."""
    f = getattr(state, "fleet", None)
    if not f:
        return []
    cv = carrier_base(state)
    lines = []
    if cv is None:
        state.fleet = {}
        return lines
    if f.get("sunk_day") and state.day >= int(f.get("returns_day", 0)):
        lines.append(f"{cv.name} is back on station: a new ship, a new air group, the escorts with it.")
        cv.defense = 1.0
        from . import support_assets as sa_
        for a in sa_.ensure(state).values():
            if a.get("base_id") == cv.id:
                a["available"] = a["authorized"]
                a.pop("clk", None)                                  # the new ship's airframes are all ready (support_assets clock)
        for sq in state.squadrons.values():
            if sq.home_id == cv.id:
                sq.base_id, sq.home_id = cv.id, ""
                lines.append(f"   {sq.name} flies home to {cv.name} at full strength ({sq.authorized})")
            if sq.base_id == cv.id:                                    # every carrier squadron is back at its authorized strength
                sq.available, sq.reserve, sq.rest_days, sq.move_days, sq.move_until = sq.authorized, 0, 0, 0, 0
        state.fleet = {}
        return lines
    back = [k for k, d in list((f.get("escorts") or {}).items()) if state.day >= int(d)]
    for k in back:
        f["escorts"].pop(k)
        cv.defense = min(1.0, cv.defense + ESCORT_DEFENSE[int(k)])
        lines.append(f"A replacement escort has joined {cv.name}")
    if f.get("escorts"):
        cv.defense = min(cv.defense, _cap(state))
    if not f.get("escorts") and not f.get("sunk_day"):
        state.fleet = {}
    return lines


def status_line(state):
    """One Overview line, or None."""
    f = getattr(state, "fleet", None) or {}
    cv = carrier_base(state)
    if cv is None:
        return None
    if f.get("sunk_day"):
        n = days_left(state)
        return f"{cv.name} is SUNK: it returns in {n} day{'s' if n != 1 else ''}; it counts as a lost base until then"
    if f.get("escorts"):
        n = len(f["escorts"])
        return f"{n} escort ship{'s' if n > 1 else ''} of {cv.name} lost: the group's air defence is cut until they are replaced"
    return None
