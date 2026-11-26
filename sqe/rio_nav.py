"""F-14 RIO Navigation (experimental, S210): Jester works the player's steerpoints through the flight, and types or flies direct to a turnpoint on request.

The mission script made here decides everything (which point is next, the "RIO: ..." messages, when to switch itself off); it writes the cockpit commands into a request file.
The export script on the player's PC (`data/sqe_f14_turnpoints_export.lua`) only presses them, and reports back through a second file when the destination knob moves without it (plain F-14B).

Heatblur's Jester commands: 10017 destination knob, 10018 pick the point to enter, 10019 enter from a trigger zone (F-14A/B); 10037 select a waypoint, 10042 direct-to (F-14B(U)).

Pure functions, no pydcs."""
from __future__ import annotations

REQUEST_FILE = "SQE_turnpoints.req"       # the same file as the Turnpoints feature before it: the installed script's Remove button deletes it
OVERRIDE_FILE = "SQE_turnpoints.ovr"
TOGGLE_TITLE = "Work the waypoints: on / off"
TURNPOINTS_TITLE = "Turnpoints"
MENU_PAGE = 9                              # DCS shows ten entries in a menu; the tenth is the door to the next page
MAX_ZONES = 99

# not steerpoints: the climb-out (XO: Jester starts at MSHL) and the card's reference rows
NOT_LEGS = ("TAKEOFF", "DEP", "SPAWN", "DIVERT", "TKR", "BULLS", "SCRUB")
SAME_PLACE_M = 150.0                       # a card row and a point in the jet are the same point when this close

# plain F-14B destination knob positions (Heatblur's list: 0.1 to 0.3 waypoints 1 to 3, 0.4 fix point, 0.5 IP, 0.6 ST, 0.7 home base)
KNOB_FP = 0.4
KNOB_HOME = 0.7
KNOB_NAV_POINT = {"IP": 0.5, "ST": 0.6}    # DP and HA exist in the jet but the knob cannot select them


def zone_name(number: int) -> str:
    return "WaypointZone%02d" % number


def leg_kind(name: str) -> str:
    if name == "MSHL":
        return "mshl"
    if name == "CAP1":
        return "cap1"
    if name == "CAP2":
        return "cap2"
    if name == "TGT":
        return "tgt"
    return "route"


def _near(ax: float, ay: float, bx: float, by: float) -> bool:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 <= SAME_PLACE_M


def plain_legs(rows: list, labels: dict, points: list, nav_points: list, turnpoint_zones: dict) -> tuple:
    """The plain F-14B: one leg for each card row that is a steerpoint. `rows` = (name, x, y, planned seconds) of the card; `labels` = row index -> card name (TP1 ...);
    `points` = (x, y) of the points in the jet, the takeoff first and the landing last; `nav_points` = (code, x, y); `turnpoint_zones` = row index -> zone number already made for a turnpoint.
    -> (legs, zones) where zones = [(zone number, x, y)] still to be made. A point the knob cannot reach gets a zone: Jester types it into the fix point. CAP2 is left out (it sits in DP)."""
    legs = []
    new_zones = []
    zone_number = len(turnpoint_zones)
    for index, row in enumerate(rows):
        name, x, y, planned_s = row
        if name in NOT_LEGS or name == "CAP2":
            continue
        knob = None
        zone = None
        for slot in range(1, len(points) - 1):
            if slot <= 3 and _near(x, y, points[slot][0], points[slot][1]):
                knob = 0.1 * slot
                break
        if knob is None and name == "RTB" and len(points) > 1:
            knob = KNOB_HOME
        if knob is None:
            for code, nav_x, nav_y in nav_points:
                if code in KNOB_NAV_POINT and _near(x, y, nav_x, nav_y):
                    knob = KNOB_NAV_POINT[code]
                    break
        if knob is None:
            zone = turnpoint_zones.get(index)
            if zone is None and zone_number < MAX_ZONES:
                zone_number += 1
                zone = zone_number
                new_zones.append((zone, x, y))
            if zone is None:
                continue
        legs.append({"name": labels.get(index, name), "kind": leg_kind(name), "x": x, "y": y, "t": planned_s, "knob": knob, "zone": zone, "num": None, "row": index})
    return legs, new_zones


def bu_legs(rows: list, labels: dict, points: list) -> list:
    """The F-14B(U): every route point is a numbered waypoint in the jet; the number is its place in `points` (the takeoff is 0). A row with no point there is left out."""
    legs = []
    for index, row in enumerate(rows):
        name, x, y, planned_s = row
        if name in NOT_LEGS:
            continue
        number = None
        if name == "RTB":
            number = len(points) - 1
        else:
            for slot in range(1, len(points)):
                if _near(x, y, points[slot][0], points[slot][1]):
                    number = slot
                    break
        if number is None or number > 99:
            continue
        legs.append({"name": labels.get(index, name), "kind": leg_kind(name), "x": x, "y": y, "t": planned_s, "knob": None, "zone": None, "num": number, "row": index})
    return legs


def _lua_value(value) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"')
    if isinstance(value, float):
        return "%.3f" % value
    return str(value)


_SCRIPT = r"""
local legs = {
__LEGS__
}
local turnpoints = {
__TURNPOINTS__
}
local GROUP, UNIT, BU, STRIKE, LEAVE, EXIT = __GROUP__, __UNIT__, __BU__, __STRIKE__, __LEAVE__, __EXIT__
local NM = 1852
local on, started, current, closest, catching, after_target, typed_zone = true, false, 0, nil, false, false, nil
local outbox, count, last_override = {}, 0, ""
local selected_at = 0

local function say(text, seconds)
  trigger.action.outTextForGroup(GROUP, "RIO: " .. text, seconds or 12)
end

local function can_write()
  return io ~= nil and lfs ~= nil
end

local function file_path(name)
  return lfs.writedir() .. "Logs\\" .. name
end

local function write_file(name, text)
  local file = io.open(file_path(name), "w")
  if not file then return false end
  file:write(text)
  file:close()
  return true
end

local function read_file(name)
  local file = io.open(file_path(name), "r")
  if not file then return "" end
  local text = file:read("*a") or ""
  file:close()
  return text
end

-- a step: seconds after the one before it, command, value
local function press(delay, command, value)
  outbox[#outbox + 1] = string.format("%g,%d,%.2f", delay, command, value)
end

local function flush()
  if #outbox == 0 or not can_write() then return end
  count = count + 1
  write_file("__REQUEST__", string.format("SQERIO %d %d %s", count, math.floor(timer.getTime()), table.concat(outbox, ";")))
  outbox = {}
end

local function type_into_fix_point(zone, first_delay)
  press(first_delay, 10018, 0.4)
  press(2, 10019, zone / 100)
  typed_zone = zone
end

local function steer_to(leg)
  if BU then
    press(0, 10037, leg.num / 100)
    press(2, 10042, 1)
  elseif leg.knob then
    press(0, 10017, leg.knob)
  elseif typed_zone == leg.zone then
    press(0, 10017, 0.4)                       -- typed ahead of time: only the knob
  else
    press(0, 10017, 0.4)
    type_into_fix_point(leg.zone, 3)
    return "Jester is typing it into the fix point: wait until the range stops changing."
  end
  return nil
end

local function turn_off(why)
  on = false
  say(why)
end

local function select_leg(index)
  local leg = legs[index]
  if not leg then return end
  current, closest = index, nil
  selected_at = timer.getTime()
  local note = steer_to(leg)
  -- type the next hand-entered point now, while the fix point is not the one in use: Jester is slow
  local following = legs[index + 1]
  if not BU and leg.knob and leg.knob ~= 0.4 and following and following.zone and typed_zone ~= following.zone then
    type_into_fix_point(following.zone, 4)
  end
  if STRIKE and leg.kind == "tgt" then
    after_target = true
    turn_off("Next steerpoint: " .. leg.name .. ". Waypoint work off on TGT: switch it back on after your run.")
    return
  end
  say("Next steerpoint: " .. leg.name .. (note and (". " .. note) or ""))
end

local function station_end(index)
  -- the first leg after the station that `index` belongs to
  local after = index
  while legs[after] and (legs[after].kind == "cap1" or legs[after].kind == "cap2") do after = after + 1 end
  return after
end

local function target_index()
  for index, leg in ipairs(legs) do
    if leg.kind == "tgt" then return index end
  end
  return nil
end

-- where the plan says we should be steering at this moment
local function leg_by_clock(now)
  local chosen = nil
  for index, leg in ipairs(legs) do
    if leg.kind == "mshl" and LEAVE and now < LEAVE then return index end
    if leg.kind == "cap1" and leg.t > 0 and now >= leg.t and (not EXIT or now < EXIT) then return index end   -- on station by now (and not yet due to leave)
    local station_over = (leg.kind == "cap1" or leg.kind == "cap2") and EXIT and now >= EXIT
    if not chosen and leg.kind ~= "mshl" and not station_over and (leg.t <= 0 or leg.t > now) then chosen = index end
  end
  chosen = chosen or #legs
  local target = target_index()
  if after_target and target and chosen <= target then chosen = math.min(target + 1, #legs) end
  return chosen
end

local function switch_on(now)
  if not can_write() then
    on = false
    say("Waypoint work needs DCS scripting access (SQE Settings, DCS Integration).")
    return
  end
  on = true
  catching = now > 180
  select_leg(leg_by_clock(now))
end

local function advance()
  local leg = legs[current]
  if current >= #legs then return end
  if (leg.kind == "cap1" or leg.kind == "cap2") and EXIT and timer.getTime() >= EXIT then
    select_leg(math.min(station_end(current), #legs))
  else
    select_leg(current + 1)
  end
end

local function follow(unit)
  local leg = legs[current]
  if not leg then return end
  local now = timer.getTime()
  local place = unit:getPoint()
  local distance = math.sqrt((place.x - leg.x) ^ 2 + (place.z - leg.y) ^ 2)
  closest = math.min(closest or distance, distance)
  local passed = distance < 3 * NM or (closest < 10 * NM and distance > closest + NM)
  if leg.kind == "mshl" and LEAVE then
    if now >= LEAVE then advance() end
    return
  end
  if leg.kind == "cap1" or leg.kind == "cap2" then   -- a station is left at its exit time only; with no exit time on the card, only you move him on
    if EXIT and now >= EXIT then
      advance()
    elseif BU then                             -- the two ends in turn until the exit time (the plain F-14B holds the first: its knob cannot reach the second)
      local other = nil
      if leg.kind == "cap1" and legs[current + 1] and legs[current + 1].kind == "cap2" then
        other = current + 1
      elseif leg.kind == "cap2" and legs[current - 1] and legs[current - 1].kind == "cap1" then
        other = current - 1
      end
      if other then
        -- the ends can be close together: "reached" is within a third of the leg between them (3 nm at most), and never within 30 s of the last change
        local length = math.sqrt((legs[other].x - leg.x) ^ 2 + (legs[other].y - leg.y) ^ 2)
        if distance < math.min(3 * NM, length / 3) and now - selected_at >= 30 then
          select_leg(other)
        end
      end
    end
    return
  end
  if passed then
    catching = false
    advance()
  elseif catching and leg.t > 0 and now > leg.t then
    advance()                                  -- switched on mid-flight and still behind the plan: keep up with the clock
  end
end

local function tick()
  local unit = Unit.getByName(UNIT)
  local now = timer.getTime()
  if unit and unit:isExist() then
    if not started and now >= 30 then
      started = true
      if on then switch_on(now) end
    elseif started and on then
      if not BU and can_write() then
        local text = read_file("__OVERRIDE__")
        if text ~= "" and text ~= last_override then
          last_override = text
          turn_off("Waypoint work off: you took the steerpoint.")
        end
      end
      if on then follow(unit) end
    end
  end
  flush()
end

local function toggle()
  if on and started then
    turn_off("Waypoint work off.")
  else
    started = true
    if can_write() then last_override = read_file("__OVERRIDE__") end
    switch_on(timer.getTime())
    flush()
  end
end

local function turnpoint(item)
  if not can_write() then
    say("Turnpoints need DCS scripting access (SQE Settings, DCS Integration).")
    return
  end
  if on then turn_off("Waypoint work off: you took the steerpoint.") end
  if BU then
    press(0, 10037, item.num / 100)
    press(2, 10042, 1)
    say(item.label .. " (" .. item.note .. "): direct to waypoint " .. item.num .. ".", 20)
  else
    press(0, 10017, 0.4)
    type_into_fix_point(item.zone, 3)
    say(item.label .. " (" .. item.note .. "): Jester is typing it into the fix point (FP). He is slow: wait until the range stops changing.", 20)
  end
  flush()
end

if can_write() then
  write_file("__REQUEST__", "")
  write_file("__OVERRIDE__", "")
end
missionCommands.addCommandForGroup(GROUP, "__TOGGLE__", nil, toggle)
if #turnpoints > 0 then
  local menu = missionCommands.addSubMenuForGroup(GROUP, "__TURNPOINTS_TITLE__")
  local on_page = 0
  for _, item in ipairs(turnpoints) do
    if on_page == __PAGE__ then
      menu = missionCommands.addSubMenuForGroup(GROUP, "More Turnpoints", menu)
      on_page = 0
    end
    missionCommands.addCommandForGroup(GROUP, item.label, menu, turnpoint, item)
    on_page = on_page + 1
  end
end
timer.scheduleFunction(function(_, t)
  local ok, problem = pcall(tick)
  if not ok then env.info("SQE RIO navigation: " .. tostring(problem)) end
  return t + 1
end, nil, timer.getTime() + 1)
"""


def mission_script(group_id: int, unit_name: str, bu: bool, strike: bool, legs: list, turnpoint_items: list, leave_s, exit_s) -> str:
    """The mission script for the player's F-14. `legs` from `plain_legs` / `bu_legs`; `turnpoint_items` = [{"label", "note", "zone" (plain) , "num" (B(U))}]; `leave_s` = when the flight leaves its marshal;
    `exit_s` = when it leaves its station (None when it has none). `strike`: switch off once TGT is selected."""
    leg_lines = []
    for leg in legs:
        leg_lines.append("  { name = %s, kind = %s, x = %.1f, y = %.1f, t = %d, knob = %s, zone = %s, num = %s },"
                         % (_lua_value(leg["name"]), _lua_value(leg["kind"]), leg["x"], leg["y"], int(leg["t"] or 0), _lua_value(leg["knob"]), _lua_value(leg["zone"]), _lua_value(leg["num"])))
    turnpoint_lines = []
    for item in turnpoint_items:
        turnpoint_lines.append("  { label = %s, note = %s, zone = %s, num = %s }," % (_lua_value(item["label"]), _lua_value(item["note"]), _lua_value(item.get("zone")), _lua_value(item.get("num"))))
    values = {"__LEGS__": "\n".join(leg_lines), "__TURNPOINTS__": "\n".join(turnpoint_lines), "__GROUP__": str(group_id), "__UNIT__": _lua_value(unit_name), "__BU__": _lua_value(bu),
              "__STRIKE__": _lua_value(strike), "__LEAVE__": _lua_value(None if leave_s is None else int(leave_s)), "__EXIT__": _lua_value(None if exit_s is None else int(exit_s)),
              "__REQUEST__": REQUEST_FILE, "__OVERRIDE__": OVERRIDE_FILE, "__TOGGLE__": TOGGLE_TITLE, "__TURNPOINTS_TITLE__": TURNPOINTS_TITLE, "__PAGE__": str(MENU_PAGE)}
    script = _SCRIPT
    for mark, value in values.items():
        script = script.replace(mark, value)
    return script
