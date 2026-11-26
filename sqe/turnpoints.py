"""Turnpoints: the points that route a flight round SAM rings (the planner calls them "AVD").

The kneeboard calls them TP1, TP2, ... in the order they are flown. The player's plain F-14B gets an F10 menu to steer to one (`rio_nav`).

Pure functions, no pydcs."""
from __future__ import annotations

PLANNER_NAME = "AVD"
HOME_NAMES = ("RTB", "RCV", "SCRUB")


def numbered(names: list) -> list:
    """`names` = the route's point names in flying order. -> one dict for each turnpoint: `index` (its place in `names`), `label` (TP1, TP2, ...)
    and `leg` ("before IP", or "to home base" for the way home)."""
    found = []
    for index, name in enumerate(names):
        if name != PLANNER_NAME:
            continue
        leg = "to home base"
        for later in names[index + 1:]:
            if later == PLANNER_NAME:
                continue
            if later not in HOME_NAMES:
                leg = "before " + later
            break
        found.append({"index": index, "label": "TP%d" % (len(found) + 1), "leg": leg})
    return found
