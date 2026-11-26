"""F-14 RIO Navigation (experimental, S210): Jester works the player's steerpoints through the flight, and types or flies direct to a turnpoint on request.

The mission script made here decides everything (which point is next, the "RIO: ..." messages, when to switch itself off); it writes the cockpit commands into a request file.
The export script on the player's PC (`data/sqe_f14_turnpoints_export.lua`) presses them, and reports back through a second file when you take the navigation over (plain F-14B: the destination knob moves;
F-14B(U): the display's waypoint or steering mode changes, or a TACAN / steering button is pressed) or when the jet did not take an order.

F-14B(U) sequencing (S210b): between the points where Jester waits, the jet is left in AUTO sequencing and steps on by itself; no order is sent for an ordinary leg, the mission script only follows
where the flight is. At a waiting point (the marshal until its leave time, a station until its exit time, TGT on a strike) the jet is held in MANUAL. Each request ends with "HOLD:n/n/n", the waiting
points' waypoint numbers, so the export script can switch to manual the moment the jet steps onto one.

The player's calls are F10 > Other > RIO Navigation: "Your Nav" (Jester works the waypoints, as from the mission start) and "My Nav" (he stops). Home base (the RTB leg) ends his work: he goes
direct to it, holds the F-14B(U) in manual and hands the nav back.

F-14B(U), a point that is gone (a direct to the tanker deletes home base): when the jet refuses a direct-to, he asks the export script to load the flight plan again (command 2, the CDNU's keys,
probe 2026-11-26) and orders the same point once more. Only while he has the nav, or just after handing it back at TGT, home base or a turnpoint; once for each order.

F-14B(U), probe flown 2026-11-26 and Heatblur's CDNU manual: direct-to a later waypoint DELETES the ones in between (the one you leave goes to history; the last 5 history points can be flown to again).
Nothing here steers to a station's far end before its near end, so a point still needed is never jumped. In Destination steering the HUD ignores direct-to, so switching on first steps out of it
(command 1, done by the export script).

Heatblur's Jester commands: 10017 destination knob, 10018 pick the point to enter, 10019 enter from a trigger zone (F-14A/B); 10037 select a waypoint, 10042 direct-to, 10043 sequencing (1.0 manual, 0.33 auto),
10045 EGI or TACAN (F-14B(U)).

Pure functions, no pydcs."""
from __future__ import annotations

REQUEST_FILE = "SQE_turnpoints.req"       # the same file as the Turnpoints feature before it: the installed script's Remove button deletes it
OVERRIDE_FILE = "SQE_turnpoints.ovr"
MENU_TITLE = "RIO Navigation"
YOUR_NAV_TITLE = "Your Nav"
MY_NAV_TITLE = "My Nav"
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
    if name == "RTB":
        return "home"
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
    """The F-14B(U): every route point is a numbered waypoint in the jet, in flight plan order; the number is its place in `points` (the takeoff is 0). A row with no point there is left out.
    Every card row after RTB (DIVERT, TKR, BULLS) is a point after the landing one, so RTB is that many places before the end."""
    legs = []
    for index, row in enumerate(rows):
        name, x, y, planned_s = row
        if name in NOT_LEGS:
            continue
        number = None
        if name == "RTB":
            rows_after = len(rows) - 1 - index
            number = len(points) - 1 - rows_after
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
local SEQUENCING, MANUAL, AUTO = 10043, 1.0, 0.33
local NO_ACCESS = "Waypoint work needs DCS scripting access (SQE Settings, DCS Integration)."
local release = false                      -- F-14B(U): the waypoint work went off, tell the export script there is nothing left to hold
local RESTORE, RESTORE_S, REFUSAL_S = 2, 35, 90
local last_order = nil                     -- F-14B(U): the last direct-to he ordered, so he can order it again after loading the flight plan
local restoring_until = 0
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

-- F-14B(U): the points where Jester waits for the clock or for you; the jet is held there in manual sequencing
local function is_waiting(leg)
  if not BU or not leg then return false end
  if leg.kind == "mshl" then return LEAVE ~= nil end
  if leg.kind == "cap1" or leg.kind == "cap2" then return true end
  if leg.kind == "tgt" then return STRIKE end
  if leg.kind == "home" then return true end
  return false
end

-- F-14B(U): their waypoint numbers, for the export script (none once the work is off)
local function hold_part()
  if not BU then return "" end
  local numbers = {}
  if on then
    for _, leg in ipairs(legs) do
      if is_waiting(leg) then numbers[#numbers + 1] = tostring(leg.num) end
    end
  end
  return " HOLD:" .. table.concat(numbers, "/")
end

local function flush()
  if (#outbox == 0 and not release) or not can_write() then return end
  count = count + 1
  write_file("__REQUEST__", string.format("SQERIO %d %d %s", count, math.floor(timer.getTime()), table.concat(outbox, ";") .. hold_part()))
  outbox, release = {}, false
end

-- F-14B(U), before steering: out of Destination steering and into manual sequencing (command 1, done by the export script; it must come first), then EGI
local function set_up_bu()
  press(0, 1, 0)
  press(1, 10045, 0)
end

local function type_into_fix_point(zone, first_delay)
  press(first_delay, 10018, 0.4)
  press(2, 10019, zone / 100)
  typed_zone = zone
end

-- F-14B(U): go direct to a waypoint, to be held there in manual or flown on in auto sequencing
local function send_order(order)
  if order.manual then
    press(0, SEQUENCING, MANUAL)               -- manual first: the jet must not step past the point
    press(1, 10037, order.num / 100)
    press(2, 10042, 1)
  else
    press(0, 10037, order.num / 100)
    press(2, 10042, 1)
    press(1, SEQUENCING, AUTO)                 -- and from here the jet sequences itself
  end
  order.until_s = timer.getTime() + REFUSAL_S  -- a refusal reported until then is about this order
  last_order = order
end

local function steer_to(leg)
  if BU then
    send_order({ num = leg.num, name = leg.name, manual = is_waiting(leg) })
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
  release = BU
  say(why)
end

-- `forced`: switching on, or keeping up with the clock
local function select_leg(index, forced)
  local leg = legs[index]
  if not leg then return end
  -- the F-14B(U) steps from point to point by itself: it needs an order only into or out of a waiting point, or when forced
  local order = true
  if BU and not forced then
    order = is_waiting(leg) or is_waiting(legs[current])
  end
  current, closest = index, nil
  selected_at = timer.getTime()
  local note = nil
  if order then note = steer_to(leg) end
  -- type the next hand-entered point now, while the fix point is not the one in use: Jester is slow
  local following = legs[index + 1]
  if not BU and leg.knob and leg.knob ~= 0.4 and following and following.zone and typed_zone ~= following.zone then
    type_into_fix_point(following.zone, 4)
  end
  if STRIKE and leg.kind == "tgt" then
    after_target = true
    turn_off("Next steerpoint: " .. leg.name .. ". Your nav: hand it back after your run.")
    return
  end
  if leg.kind == "home" then                   -- home base ends the work
    turn_off("Next steerpoint: " .. leg.name .. ". Home base: your nav.")
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
    say(NO_ACCESS)
    return
  end
  on = true
  catching = now > 180
  if BU then set_up_bu() end
  select_leg(leg_by_clock(now), true)
end

local function advance(forced)
  local leg = legs[current]
  if current >= #legs then return end
  if (leg.kind == "cap1" or leg.kind == "cap2") and EXIT and timer.getTime() >= EXIT then
    select_leg(math.min(station_end(current), #legs), forced)
  else
    select_leg(current + 1, forced)
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
    advance(true)                              -- switched on mid-flight and still behind the plan: keep up with the clock
  end
end

-- what the export script saw, in words
local function off_reason(reason)
  if reason == "button" then return "Your nav. You changed the navigation source." end
  if reason == "unable" then
    local name = "the waypoint"
    if last_order then name = last_order.name end
    return "Your nav. The jet still will not go direct to " .. name .. "."
  end
  if reason == "page" then return "Your nav. The CDNU was not on the page I expected, so I stopped the reload." end
  if reason == "mode" then return "Your nav. I could not leave Destination steering." end
  if reason == "sequence" then return "Your nav. The jet did not change between manual and auto sequencing." end
  return "Your nav. You took the steerpoint."
end

-- the export script says you took over, the jet did not take an order, or the reload stopped
local function reported(reason)
  local order = last_order
  local recent = order ~= nil and timer.getTime() < order.until_s
  if BU and reason == "unable" and order and not order.retried and (on or recent) then
    order.retried = true                       -- once for each order
    say("The jet no longer has " .. order.name .. ". Reloading the flight plan: about half a minute.", 30)
    press(0, RESTORE, 0)
    send_order(order)
    restoring_until = timer.getTime() + RESTORE_S
  elseif on then
    turn_off(off_reason(reason))
    last_order = nil
  elseif recent and (reason == "unable" or reason == "page") then
    say(off_reason(reason))                    -- he had handed the nav back (TGT, home base, a turnpoint) and could not get you there
    last_order = nil
  end
end

local function tick()
  local unit = Unit.getByName(UNIT)
  local now = timer.getTime()
  if unit and unit:isExist() then
    if not started and now >= 30 then
      started = true
      if on then switch_on(now) end
    elseif started then
      if can_write() then
        local text = read_file("__OVERRIDE__")
        if text ~= "" and text ~= last_override then
          last_override = text
          reported(string.match(text, "(%a+)%s*$"))
        end
      end
      if on and now >= restoring_until then follow(unit) end      -- he does not move on while he is reloading
    end
  end
  flush()
end

-- "Your Nav": Jester takes the waypoints. Said while he has them, he only repeats the current steerpoint.
local function your_nav()
  if on and started then
    local leg = legs[current]
    if leg then say("I have the nav. Current steerpoint: " .. leg.name) end
    return
  end
  if not can_write() then
    say(NO_ACCESS)
    return
  end
  started = true
  last_order, restoring_until = nil, 0
  last_override = read_file("__OVERRIDE__")
  say("I have the nav.")
  switch_on(timer.getTime())
  flush()
end

-- "My Nav": you take them back (said before he starts, he does not start)
local function my_nav()
  last_order, restoring_until = nil, 0
  if on then
    turn_off("Your nav.")
  else
    release = BU                               -- stops a reload he started for TGT, home base or a turnpoint
    say("Your nav.")
  end
end

local function turnpoint(item)
  if not can_write() then
    say("Turnpoints need DCS scripting access (SQE Settings, DCS Integration).")
    return
  end
  if on then turn_off("Your nav. You picked a turnpoint.") end
  if BU then
    set_up_bu()
    restoring_until = 0
    send_order({ num = item.num, name = item.label, manual = true })
    say(item.label .. " (" .. item.note .. "): direct to waypoint " .. item.num .. ". The F-14B(U) drops the waypoints you jump over.", 20)
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
local nav_menu = missionCommands.addSubMenuForGroup(GROUP, "__MENU_TITLE__")      -- made first, so it is listed above Turnpoints
missionCommands.addCommandForGroup(GROUP, "__YOUR_NAV__", nav_menu, your_nav)
missionCommands.addCommandForGroup(GROUP, "__MY_NAV__", nav_menu, my_nav)
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
    `exit_s` = when it leaves its station (None when it has none). `strike`: switch off once TGT is selected (home base always ends the work)."""
    leg_lines = []
    for leg in legs:
        leg_lines.append("  { name = %s, kind = %s, x = %.1f, y = %.1f, t = %d, knob = %s, zone = %s, num = %s },"
                         % (_lua_value(leg["name"]), _lua_value(leg["kind"]), leg["x"], leg["y"], int(leg["t"] or 0), _lua_value(leg["knob"]), _lua_value(leg["zone"]), _lua_value(leg["num"])))
    turnpoint_lines = []
    for item in turnpoint_items:
        turnpoint_lines.append("  { label = %s, note = %s, zone = %s, num = %s }," % (_lua_value(item["label"]), _lua_value(item["note"]), _lua_value(item.get("zone")), _lua_value(item.get("num"))))
    values = {"__LEGS__": "\n".join(leg_lines), "__TURNPOINTS__": "\n".join(turnpoint_lines), "__GROUP__": str(group_id), "__UNIT__": _lua_value(unit_name), "__BU__": _lua_value(bu),
              "__STRIKE__": _lua_value(strike), "__LEAVE__": _lua_value(None if leave_s is None else int(leave_s)), "__EXIT__": _lua_value(None if exit_s is None else int(exit_s)),
              "__REQUEST__": REQUEST_FILE, "__OVERRIDE__": OVERRIDE_FILE, "__MENU_TITLE__": MENU_TITLE, "__YOUR_NAV__": YOUR_NAV_TITLE, "__MY_NAV__": MY_NAV_TITLE, "__TURNPOINTS_TITLE__": TURNPOINTS_TITLE, "__PAGE__": str(MENU_PAGE)}
    script = _SCRIPT
    for mark, value in values.items():
        script = script.replace(mark, value)
    return script
