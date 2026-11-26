-- SQE F-14 RIO Navigation (experimental): presses what the mission asks for in your F-14B or F-14B(U) (F10 > Other > Work the Waypoints, and Turnpoints).
--
-- The mission writes one line into Logs\SQE_turnpoints.req ("SQERIO <count> <time> <delay>,<command>,<value>;..."): in your Saved Games\DCS folder in single player,
-- in the sibling DCS_Server folder when the sortie runs on the DCS dedicated server on this PC. This script reads it and sends the commands to the cockpit.
-- When you take the navigation over, it writes Logs\SQE_turnpoints.ovr beside the request and the mission stops working your waypoints:
--   F-14B:    the destination knob moves without such a command;
--   F-14B(U): the waypoint or the steering mode on the display changes without one, or you press a TACAN or steering button. It also reports an order the jet did not take.
-- On the F-14B(U) it first takes the jet out of Destination steering (the PTID's steering push button), sets EGI and manual sequencing.
-- What it sends and sees is logged in Logs\SQE_rio_navigation.log (started afresh each flight). It does nothing in any other aircraft.
--
-- HOW TO INSTALL: SQE does it for you (Settings > DCS integration > Install RIO Navigation). By hand: copy THIS file to
-- Saved Games\DCS\Scripts\sqe_f14_turnpoints_export.lua and add at the END of Saved Games\DCS\Scripts\Export.lua (create it if it does not exist; this file
-- chains the previous export functions instead of replacing them):
--   --[[SQE F14 TURNPOINTS EXPORT]]dofile(lfs.writedir() .. [[Scripts\sqe_f14_turnpoints_export.lua]])
-- Remove the line (and the file) to uninstall.

local lfs = require("lfs")

local AIRCRAFT_PREFIX = "F-14B"   -- the F-14B and the F-14B(U)
local COMMAND_DEVICE = 1          -- the F-14's PROXY device (its devices.lua: "hardcoded device ID of 1 is used by mission files")
local DEST_KNOB, PICK_WAYPOINT, ENTER_FROM_ZONE = 10017, 10018, 10019
local SELECT_WAYPOINT, DIRECT_TO, STEERING_MODE = 10037, 10042, 10043
local MANUAL_SEQUENCING = 1.0
local SETUP_BU = 1                -- not a cockpit command: the mission asks for the F-14B(U) set-up below
local PTID_DEVICE, PTID_STEERING_BUTTON = 43, 3904   -- the F-14B(U)'s PTID and its push button 9, which steps the steering mode (probe 2026-11-26)
local DISPLAY_PRESSES_MAX = 5
local PRESS_RELEASE_S = 0.3
local PRESS_SETTLE_S = 3
local TID_INDICATION = 29         -- the display that carries the steering mode and waypoint as "MAN 03" (element TID_MENU_9)
local LAST_INDICATION = 40
local OWN_MODES = { AUTO = true, MAN = true, OFLY = true }   -- steering to the waypoint a direct-to sets; DEST, LP, TGT steer elsewhere
local ORDER_WAIT_S = 12           -- Jester is slow: how long after a direct-to the display must show it
local PILOT_BUTTONS = { 1002, 1003, 292, 135 }               -- front TACAN and Destination steering, front and back TACAN / EGI
local DEST_ARGUMENT = 51          -- the destination knob's cockpit argument (draw_args.lua TID_dest_mode)
local FIX_POINT = 0.4
local POLL_S = 0.5
local KNOB_WAIT_S = 20            -- how long after our knob command the knob may still be on its way
local KNOB_STILL_S = 3            -- ...and how long it must rest before its position counts as ours

local state = {}
local previous_start = LuaExportStart
local previous_stop = LuaExportStop
local previous_after_frame = LuaExportAfterNextFrame

local function reset()
  state = { next_poll = 0, seen = {}, steps = {}, request_path = nil, expected = nil, sent_at = nil, moved_at = nil, overrides = 0,
            next_due = 0, selected = nil, watch = nil, tid_indication = TID_INDICATION, log_started = false }
end
reset()

local function log(text)
  local mode = "a"
  if not state.log_started then mode = "w" end
  local file = io.open(lfs.writedir() .. [[Logs\SQE_rio_navigation.log]], mode)
  if not file then return end
  state.log_started = true
  file:write(string.format("%.1f %s\n", LoGetModelTime() or 0, text))
  file:close()
end

-- "C:\Users\You\Saved Games\DCS\" -> "C:\Users\You\Saved Games\"
local function parent_folder(path)
  return (string.gsub(path, "[^\\/]+[\\/]*$", ""))
end

local function request_paths()
  local own = lfs.writedir()
  return { own .. [[Logs\SQE_turnpoints.req]], parent_folder(own) .. [[DCS_Server\Logs\SQE_turnpoints.req]] }
end

local function read_text(path)
  local file = io.open(path, "r")
  if not file then return "" end
  local text = file:read("*a") or ""
  file:close()
  return text
end

local function argument(number)
  local ok, value = pcall(function() return GetDevice(0):get_argument_value(number) end)
  if ok and type(value) == "number" then return value end
  return nil
end

local function report_override(reason)
  if not state.request_path then return end
  state.overrides = state.overrides + 1
  local file = io.open((string.gsub(state.request_path, "%.req$", ".ovr")), "w")
  if file then
    file:write(string.format("SQEOVR %d %.0f %s", state.overrides, LoGetModelTime() or 0, reason))
    file:close()
  end
  log("reported: " .. reason)
end

-- the steering mode and waypoint number on the display ("MAN 03" -> "MAN", 3), or nil when the display does not show them
local function steering_on_display()
  local function read(number)
    local ok, text = pcall(list_indication, number)
    if not ok or type(text) ~= "string" then return nil end
    return string.match(text, "TID_MENU_9\r?\n([^\r\n]*)")
  end
  local shown = read(state.tid_indication)
  if not shown then
    for number = 0, LAST_INDICATION do
      shown = read(number)
      if shown then
        state.tid_indication = number
        break
      end
    end
  end
  if not shown then return nil end
  local mode = string.match(shown, "^(%a+)")
  local waypoint = tonumber(string.match(shown, "(%d+)"))
  return mode, waypoint, shown
end

-- F-14B(U): has somebody else changed the navigation (or the jet not taken our order)? Reports it once and stops watching.
local function check_bu(now, read_display)
  local watch = state.watch
  if not watch then return false end
  local mode, waypoint, shown = nil, nil, nil
  if read_display then mode, waypoint, shown = steering_on_display() end
  local reason = nil
  if watch.confirmed then
    for _, number in ipairs(PILOT_BUTTONS) do
      local value = argument(number)
      if value and watch.buttons[number] and math.abs(value - watch.buttons[number]) > 0.05 then
        reason = "button"
      end
    end
    if not reason and mode and (not OWN_MODES[mode] or waypoint ~= watch.waypoint) then reason = "steer" end
  else
    if mode and OWN_MODES[mode] and waypoint == watch.waypoint then
      watch.confirmed = true
      for _, number in ipairs(PILOT_BUTTONS) do
        watch.buttons[number] = argument(number)
      end
      log("the display shows " .. shown)
    elseif mode and now >= watch.check_at then
      reason = "unable"
    end
  end
  if not reason then return false end
  log("the display shows " .. tostring(shown) .. ", we sent waypoint " .. watch.waypoint)
  state.watch = nil
  report_override(reason)
  return true
end

local function add_step(delay, command, value, device)
  if #state.steps == 0 then state.next_due = (LoGetModelTime() or 0) + delay end
  state.steps[#state.steps + 1] = { delay = delay, command = command, value = value, device = device }
end

-- put a step in front of the queue (used by the F-14B(U) set-up)
local function insert_step(position, delay, command, value, device)
  table.insert(state.steps, position, { delay = delay, command = command, value = value, device = device })
end

-- the commands of one request, in order, each `delay` seconds after the one before it
local function plan_request(text)
  local list = string.match(text, "^SQERIO %d+ %d+ (.+)$")
  if not list then return false end
  local first = true
  for delay, command, value in string.gmatch(list, "([%d%.]+),(%d+),([%d%.%-]+)") do
    local wait = tonumber(delay)
    if first and #state.steps > 0 then wait = wait + 1 end
    first = false
    add_step(wait, tonumber(command), tonumber(value))
  end
  return true
end

-- a mission built before S210 asks for one turnpoint like this (as flown in the test of 2026-11-24)
local function plan_old_turnpoint(zone)
  state.steps = {}
  add_step(0, DEST_KNOB, FIX_POINT)
  add_step(3, PICK_WAYPOINT, FIX_POINT)
  add_step(2, ENTER_FROM_ZONE, zone / 100)
end

-- What a file holds when we first look is old (an earlier flight): only a change after that is a request.
local function poll(now)
  for _, path in ipairs(request_paths()) do
    local text = read_text(path)
    if state.seen[path] == nil then
      state.seen[path] = text
    elseif state.seen[path] ~= text then
      state.seen[path] = text
      if string.match(text, "^SQERIO ") then
        state.request_path = path
        -- A set-up (switching on, or a turnpoint) starts afresh. Any other order is dropped if you took over just before it arrived.
        local starting = string.match(text, "^SQERIO %d+ %d+ [%d%.]+," .. SETUP_BU .. ",")
        if starting then
          state.watch, state.steps = nil, {}
        end
        if starting or not check_bu(now, true) then
          state.watch = nil
          log("request: " .. text)
          plan_request(text)
        end
      else
        local zone = tonumber(string.match(text, "^SQETP (%d+) "))
        if zone and zone >= 1 and zone <= 99 then plan_old_turnpoint(zone) end
      end
    end
  end
end

local function knob_position()
  local value = argument(DEST_ARGUMENT)
  if value then return math.floor(value * 100 + 0.5) end
  return nil
end

local function knob_step_waiting()
  for _, step in ipairs(state.steps) do
    if step.command == DEST_KNOB then return true end
  end
  return false
end

-- after our command the knob's resting place is remembered; any later move is somebody else's
local function watch_knob(now)
  local position = knob_position()
  if not position then return end
  if state.sent_at then
    if position ~= state.expected then
      state.expected = position
      state.moved_at = now
    end
    if (state.moved_at and now - state.moved_at >= KNOB_STILL_S) or now - state.sent_at >= KNOB_WAIT_S then
      state.sent_at, state.moved_at, state.expected = nil, nil, position
    end
  elseif state.expected and position ~= state.expected and not knob_step_waiting() then
    state.expected = position
    report_override("knob")
  end
end

-- F-14B(U) set-up, one look at a time: press the steering button until the display steers to our waypoints, then manual sequencing
local function set_up_bu(now, step)
  local mode, _, shown = steering_on_display()
  if mode and not OWN_MODES[mode] then
    step.presses = (step.presses or 0) + 1
    if step.presses <= DISPLAY_PRESSES_MAX then
      log("steering shows " .. shown .. ": pressing the steering button")
      GetDevice(PTID_DEVICE):performClickableAction(PTID_STEERING_BUTTON, 1)
      step.release_at = now + PRESS_RELEASE_S
      state.next_due = now + PRESS_SETTLE_S
      return
    end
    log("steering still shows " .. shown)
    state.steps = {}
    report_override("mode")
    return
  end
  table.remove(state.steps, 1)
  if mode ~= "MAN" then insert_step(1, 1, STEERING_MODE, MANUAL_SEQUENCING) end
  if state.steps[1] then state.next_due = now + state.steps[1].delay end
end

local function send_step(now, step)
  if step.command == DEST_KNOB then
    state.sent_at, state.moved_at, state.expected = now, nil, knob_position()
  end
  GetDevice(step.device or COMMAND_DEVICE):performClickableAction(step.command, step.value)
  log(string.format("sent %d %.2f", step.command, step.value))
  if step.command == SELECT_WAYPOINT then state.selected = math.floor(step.value * 100 + 0.5) end
  if step.command == DIRECT_TO and state.selected then
    state.watch = { waypoint = state.selected, check_at = now + ORDER_WAIT_S, confirmed = false, buttons = {} }
  end
end

local function run_steps(now, in_tomcat)
  local step = state.steps[1]
  if not step then return end
  if step.release_at then
    if now >= step.release_at then
      GetDevice(PTID_DEVICE):performClickableAction(PTID_STEERING_BUTTON, 0)
      step.release_at = nil
    end
    return
  end
  if now < state.next_due then return end
  if in_tomcat and step.command == SETUP_BU then
    set_up_bu(now, step)
    return
  end
  table.remove(state.steps, 1)
  if state.steps[1] then state.next_due = now + state.steps[1].delay end
  if in_tomcat then send_step(now, step) end
end

local function tick()
  local now = LoGetModelTime()
  if not now then return end
  local me = LoGetSelfData()
  local in_tomcat = me and string.sub(tostring(me.Name), 1, #AIRCRAFT_PREFIX) == AIRCRAFT_PREFIX
  local read_display = false
  if now >= state.next_poll then
    state.next_poll = now + POLL_S
    read_display = true
    poll(now)
    if in_tomcat then watch_knob(now) end
  end
  run_steps(now, in_tomcat)
  -- the buttons every frame (a TACAN button springs back), the display twice a second
  if in_tomcat and state.watch and #state.steps == 0 then check_bu(now, read_display) end
end

function LuaExportStart()
  if previous_start then pcall(previous_start) end
  reset()
end

function LuaExportStop()
  reset()
  if previous_stop then pcall(previous_stop) end
end

function LuaExportAfterNextFrame()
  if previous_after_frame then pcall(previous_after_frame) end
  local ok, problem = pcall(tick)
  if not ok and not state.problem_logged then
    state.problem_logged = true
    pcall(log, "error: " .. tostring(problem))
  end
end
