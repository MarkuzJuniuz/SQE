"""What a blue Patriot or HAWK battery is made of, and which parts of it are gone (S216, XO 2026-11-26: "instead of just tracking percentages we'll track the units themselves").

A blue site's `lost_parts` (on its EnemyAsset) is {DCS type: [the campaign day each one was lost, ...]}. A flown mission writes the units that really died; the war sim picks which
parts die when its damage reaches a battery; the next mission is built without them; parts are replaced over time. `health` stays the summary everything else reads and is always
worked out here: the share of the parts standing, or at most BLIND_HEALTH while the battery cannot fire. AAA sites and red's sites have no record (one figure, as before).
"""
from __future__ import annotations
import math

BLIND_HEALTH = 0.10      # a battery that cannot fire reads at most this: under sams.BLUE_MIN_DEF (nothing counts as standing) and above destroyed (judgment call)
PART_DAYS = 1            # days a lost launcher, control station, command post or power plant takes to replace (judgment call; a radar takes an order from home, sams.order_days)
RADARS = ("Patriot str", "Hawk sr", "Hawk tr", "Hawk cwar")

# The order parts die in when an anti-radiation or stand-off missile gets through: the radars first (it is what they home on and aim at), then launchers.
ARM_ORDER = {
    "pat": ["Patriot str"] + ["Patriot ln"] * 8 + ["Patriot ECS", "Patriot cp", "Patriot EPP"],
    "hawk": ["Hawk sr", "Hawk tr", "Hawk cwar", "Hawk tr"] + ["Hawk ln"] * 6 + ["Hawk pcp"],
}
# ...and when bombs or ground troops wear a battery down (also how an older save's single figure becomes parts): launchers go first and the battery can fire as long as possible
# (judgment call: it keeps the older rule's shape, a weakened battery with its radar and fewer launchers).
WEAR_ORDER = {
    "pat": ["Patriot ln"] * 6 + ["Patriot cp", "Patriot EPP", "Patriot ECS"] + ["Patriot ln"] * 2 + ["Patriot str"],
    "hawk": ["Hawk ln"] * 4 + ["Hawk pcp", "Hawk cwar", "Hawk tr"] + ["Hawk ln"] * 2 + ["Hawk sr", "Hawk tr"],
}
# The order a rebuilt or arriving battery's parts come in: what it needs to fire first.
RESTORE_ORDER = {
    "pat": ["Patriot str", "Patriot ln", "Patriot ECS", "Patriot cp", "Patriot EPP"] + ["Patriot ln"] * 7,
    "hawk": ["Hawk tr", "Hawk sr", "Hawk ln", "Hawk tr", "Hawk cwar", "Hawk pcp"] + ["Hawk ln"] * 5,
}
# What a part is called in the log
PART_WORDS = {"Patriot str": "radar", "Patriot ECS": "control station", "Patriot cp": "command post", "Patriot EPP": "power plant", "Patriot ln": "launcher",
              "Hawk sr": "search radar", "Hawk tr": "tracking radar", "Hawk cwar": "acquisition radar", "Hawk pcp": "command post", "Hawk ln": "launcher"}


def key_of(site):
    """"pat" or "hawk" for a blue battery that has a parts record, None for anything else (AAA, red's sites)."""
    if site is None or not str(site.id).startswith("bsam_"):
        return None
    key = str(site.id).rsplit("_", 1)[1]
    if key in ARM_ORDER:
        return key
    return None


def full_parts(key: str) -> list:
    """[(DCS type, how many)] a full battery has, in the order the mission lays them out."""
    from . import sams
    if key == "pat":
        return [("Patriot str", 1), ("Patriot ECS", 1), ("Patriot cp", 1), ("Patriot EPP", 1), ("Patriot ln", sams.BLUE_PATRIOT_LN)]
    return [("Hawk sr", 1), ("Hawk tr", sams.BLUE_HAWK_TR), ("Hawk pcp", 1), ("Hawk cwar", 1), ("Hawk ln", sams.BLUE_HAWK_LN)]


def lost_count(site, part: str) -> int:
    return len((site.lost_parts or {}).get(part, []))


def standing(site) -> dict:
    """{DCS type: how many are there} for the parts still standing, only the types with at least one."""
    found = {}
    for part, count in full_parts(key_of(site)):
        left = count - lost_count(site, part)
        if left > 0:
            found[part] = left
    return found


def _total(key: str) -> int:
    total = 0
    for _part, count in full_parts(key):
        total += count
    return total


def share(site) -> float:
    """The share of the battery's parts that are standing."""
    if site.lost_parts is None:
        return float(site.health)
    left = 0
    for count in standing(site).values():
        left += count
    return left / _total(key_of(site))


def can_fire(site) -> bool:
    """True when a blue site can engage. Patriot: its radar and a launcher. HAWK: a tracking radar, a radar to find with (search or acquisition) and a launcher
    (judgment call). A site without a record (AAA, red's, a battery nothing has loaded yet): it is not destroyed."""
    if key_of(site) is None or site.lost_parts is None:
        return not site.destroyed
    there = standing(site)
    if key_of(site) == "pat":
        return bool(there.get("Patriot str")) and bool(there.get("Patriot ln"))
    finds = there.get("Hawk sr", 0) + there.get("Hawk cwar", 0)
    return bool(there.get("Hawk tr")) and finds > 0 and bool(there.get("Hawk ln"))


def refresh(site) -> None:
    """Work `health` out from the parts."""
    value = share(site)
    if not can_fire(site) and value > 0:
        value = min(value, BLIND_HEALTH)
    site.health = value


def lose(site, part: str, day: int) -> bool:
    """One more `part` is gone. False when there was none left."""
    if site.lost_parts is None:
        site.lost_parts = {}
    for name, count in full_parts(key_of(site)):
        if name == part and lost_count(site, part) < count:
            site.lost_parts.setdefault(part, []).append(int(day))
            refresh(site)
            return True
    return False


def regain(site, part: str) -> bool:
    """One lost `part` is back (the one lost longest ago). False when none was lost."""
    days = (site.lost_parts or {}).get(part)
    if not days:
        return False
    days.remove(min(days))
    if not days:
        del site.lost_parts[part]
    refresh(site)
    return True


def set_share(site, target: float, day: int, order: dict = WEAR_ORDER) -> None:
    """Bring the battery to the share `target` of its parts: damage kills them in `order`, a gain brings them back in RESTORE_ORDER.
    Any damage that reaches a battery costs at least one part (the count is rounded down)."""
    key = key_of(site)
    if site.lost_parts is None:
        site.lost_parts = {}
    total = _total(key)
    wanted = int(math.floor(max(0.0, min(1.0, target)) * total + 1e-6))
    left = 0
    for count in standing(site).values():
        left += count
    for part in order[key]:
        if left <= wanted:
            break
        if lose(site, part, day):
            left -= 1
    for part in RESTORE_ORDER[key]:
        if left >= wanted:
            break
        if regain(site, part):
            left += 1
    refresh(site)


def start_record(site, day: int) -> None:
    """Give a battery its parts record from the single figure it has (a new campaign: full; an older save: worn by that much)."""
    if key_of(site) is None or site.lost_parts is not None:
        return
    target = float(site.health)
    site.lost_parts = {}
    set_share(site, target, day)


def restamp(site, day: int) -> None:
    """Every part still missing counts as lost on `day` (a rebuilt battery's missing parts are ordered from now)."""
    for days in (site.lost_parts or {}).values():
        for number in range(len(days)):
            days[number] = int(day)


def repair(site, day: int, radar_days: float) -> list:
    """The replacements that have arrived by `day`: a radar `radar_days` after it was lost, anything else PART_DAYS after. -> the words of what came back."""
    arrived = []
    for part in list((site.lost_parts or {}).keys()):
        wait = PART_DAYS
        if part in RADARS:
            wait = radar_days
        for lost_day in list(site.lost_parts.get(part, [])):
            if day - lost_day >= wait and regain(site, part):
                arrived.append(PART_WORDS[part])
    return arrived
