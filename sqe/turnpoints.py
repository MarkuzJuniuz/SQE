"""Turnpoints: the points that route a flight round SAM rings (the planner calls them "AVD").

The kneeboard calls them TP1, TP2, ... in the order they are flown. For the player's plain F-14B, which cannot hold them, an F10 menu has Jester
type one into the fix point (FP): the mission writes a one-line request file and `data/sqe_f14_turnpoints_export.lua` (Export.lua, on the player's PC)
reads it and presses the cockpit's command device. The mission cannot send those commands itself on a dedicated server.

Pure functions, no pydcs."""
from __future__ import annotations

PLANNER_NAME = "AVD"
HOME_NAMES = ("RTB", "RCV", "SCRUB")
REQUEST_FILE = "SQE_turnpoints.req"
MENU_TITLE = "Turnpoints"
MENU_PAGE = 9          # DCS shows ten entries in a menu; the tenth is the door to the next page
MAX_ZONES = 99         # Jester reads zones WaypointZone01 to WaypointZone99


def zone_name(number: int) -> str:
    return "WaypointZone%02d" % number


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


_MENU_LUA = """local GROUP = %d
local PAGE = %d
local function request_path() return lfs.writedir() .. [[Logs\\%s]] end
local function write_request(text)
  local file = io.open(request_path(), "w")
  file:write(text)
  file:close()
end
pcall(write_request, "")
local function send(item)
  local ok = pcall(write_request, string.format("SQETP %%d %%.2f", item.zone, timer.getTime()))
  if ok then
    trigger.action.outTextForGroup(GROUP, item.label .. ": Jester is typing it into the fix point (FP). He is slow: wait until the range stops changing.", 20)
  else
    trigger.action.outTextForGroup(GROUP, "Turnpoints need DCS scripting access (SQE Settings, DCS Integration).", 15)
  end
end
local items = {
%s
}
local menu = missionCommands.addSubMenuForGroup(GROUP, "%s")
local on_page = 0
for _, item in ipairs(items) do
  if on_page == PAGE then
    menu = missionCommands.addSubMenuForGroup(GROUP, "More Turnpoints", menu)
    on_page = 0
  end
  missionCommands.addCommandForGroup(GROUP, item.label, menu, send, item)
  on_page = on_page + 1
end
"""


def menu_lua(group_id: int, points: list) -> str:
    """The mission script that adds F10 > Other > Turnpoints for the player's group. `points` = `numbered()` rows; the nth one is zone n."""
    lines = []
    for number, point in enumerate(points[:MAX_ZONES], 1):
        lines.append('  { zone = %d, label = "%s (%s)" },' % (number, point["label"], point["leg"]))
    return _MENU_LUA % (group_id, MENU_PAGE, REQUEST_FILE, "\n".join(lines), MENU_TITLE)
