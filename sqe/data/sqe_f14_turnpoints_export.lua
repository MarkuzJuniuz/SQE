-- SQE F-14 RIO Navigation (experimental): presses what the mission asks for in your F-14B or F-14B(U) (F10 > Other > RIO Navigation, and Turnpoints).
--
-- The mission writes one line into Logs\SQE_turnpoints.req ("SQERIO <count> <time> <delay>,<command>,<value>;... HOLD:<n>/<n>"): in your Saved Games\DCS folder in single player,
-- in the sibling DCS_Server folder when the sortie runs on the DCS dedicated server on this PC. This script reads it and sends the commands to the cockpit.
-- When you take the navigation over, it writes Logs\SQE_turnpoints.ovr beside the request and the mission stops working your waypoints:
--   F-14B:    the destination knob moves without such a command;
--   F-14B(U): the waypoint or the steering mode on the display changes without one, or you press a TACAN or steering button. It also reports an order the jet did not take.
--             In auto sequencing the jet moving on to the next waypoint is its own step, not a change of yours.
-- On the F-14B(U) it first takes the jet out of Destination steering (the PTID's steering push button), sets EGI and manual sequencing.
-- HOLD lists the waypoints Jester waits at: when the jet steps onto one in auto sequencing, this script switches it to manual so it does not step past.
-- A direct-to deletes the waypoints it jumps over. When the mission asks, this script loads the mission's flight plan again with the CDNU's keys, reading the screen before each one
-- and stopping if it is not the page it expects.
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
local RESTORE = 2                 -- not a cockpit command: the mission asks for the F-14B(U) flight plan to be loaded again
local CDNU_DEVICE = 81
-- the keys that load MAIN FPL again (probe 2026-11-26), each with what the screen must show before it is pressed
local RESTORE_KEYS = {
  { key = 3055, screen = {} },                                              -- IDX, from any page
  { key = 3064, screen = { "Index", "MDL" } },                              -- LSK 5: the data loader
  { key = 3062, screen = { "LOAD FPLN" } },                                 -- LSK 3: flight plan select
  { key = 3060, screen = { "Flt Pln Select", "*MAIN FPL" } },               -- LSK 1: the mission's plan, whose data then loads
  { key = 3067, screen = { "ACTIVATE FPLN", "*MAIN FPL" }, after_s = 7 },   -- LSK 8, once it has loaded (about 4 s in the probe)
  { key = 3067, screen = { "CONFIRM ACTIVATE" } },                          -- LSK 8 again (the words blink)
}
local KEY_GAP_S = 1
local PAGE_WAIT_S = 15            -- how long after a key the expected page may take
local AFTER_RELOAD_S = 6
local LOOK_S = 0.25
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
            next_due = 0, selected = nil, watch = nil, tid_indication = TID_INDICATION, log_started = false,
            sequencing = nil, mode_shown = false, mode_check_at = 0, holds = {}, held = nil }
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

local function add_step(delay, command, value, device)
  if #state.steps == 0 then state.next_due = (LoGetModelTime() or 0) + delay end
  state.steps[#state.steps + 1] = { delay = delay, command = command, value = value, device = device }
end

-- a push button: down now, up a moment later
local function push(device, command, now)
  GetDevice(device):performClickableAction(command, 1)
  state.held = { device = device, command = command, up_at = now + PRESS_RELEASE_S }
end

local function let_go()
  if state.held then
    GetDevice(state.held.device):performClickableAction(state.held.command, 0)
    state.held = nil
  end
end

-- forget what is queued, without leaving a button pushed in
local function drop_steps()
  let_go()
  state.steps = {}
end

-- F-14B(U): the sequencing mode we have set ("MAN" or "AUTO"); the display has ORDER_WAIT_S to show it
local function expect_sequencing(mode, now)
  state.sequencing = mode
  state.mode_shown = false
  state.mode_check_at = now + ORDER_WAIT_S
end

-- in auto sequencing the jet moves on to the next waypoint by itself
local function jet_stepped(watch, mode, waypoint)
  return mode == "AUTO" and state.sequencing == "AUTO" and waypoint == watch.waypoint + 1
end

-- what the display says against what we set: the reason to stop, or nil
local function judge_display(now, watch, mode, waypoint)
  if not OWN_MODES[mode] then return "steer" end
  if waypoint ~= watch.waypoint then
    if not jet_stepped(watch, mode, waypoint) then return "steer" end
    watch.waypoint = waypoint
    log("the jet sequenced to " .. waypoint)
  end
  if state.sequencing then
    if mode == state.sequencing then
      state.mode_shown = true
    elseif state.mode_shown then
      return "steer"
    elseif now >= state.mode_check_at then
      return "sequence"
    end
  end
  -- a waypoint Jester waits at: stop the jet stepping past it
  if mode == "AUTO" and state.sequencing == "AUTO" and state.holds[waypoint] then
    log("waypoint " .. waypoint .. " is one to wait at: manual sequencing")
    add_step(0, STEERING_MODE, MANUAL_SEQUENCING)
  end
  return nil
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
    if not reason and mode then reason = judge_display(now, watch, mode, waypoint) end
  else
    if mode and OWN_MODES[mode] and (waypoint == watch.waypoint or jet_stepped(watch, mode, waypoint)) then
      watch.confirmed = true
      for _, number in ipairs(PILOT_BUTTONS) do
        watch.buttons[number] = argument(number)
      end
      log("the display shows " .. shown)
      reason = judge_display(now, watch, mode, waypoint)
    elseif mode and now >= watch.check_at then
      reason = "unable"
    end
  end
  if not reason then return false end
  log("the display shows " .. tostring(shown) .. ", we expect " .. tostring(state.sequencing) .. " " .. watch.waypoint)
  state.watch = nil
  report_override(reason)
  return true
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
  drop_steps()
  add_step(0, DEST_KNOB, FIX_POINT)
  add_step(3, PICK_WAYPOINT, FIX_POINT)
  add_step(2, ENTER_FROM_ZONE, zone / 100)
end

-- the waypoints Jester waits at: "HOLD:2/5/6" at the end of a request (a mission built before this has none)
local function holds_of(text)
  local holds = {}
  local list = string.match(text, "HOLD:([%d/]*)")
  if list then
    for number in string.gmatch(list, "%d+") do holds[tonumber(number)] = true end
  end
  return holds
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
        state.holds = holds_of(text)
        -- A line with no commands says the work is off: stop whatever is queued (a flight plan reload included).
        if string.match(text, "^SQERIO %d+ %d+ +HOLD:[%d/]*%s*$") then
          drop_steps()
          state.watch = nil
          log("request: " .. text)
        else
          -- A set-up or a reload starts afresh. Any other order is dropped if you took over just before it arrived.
          local first = tonumber(string.match(text, "^SQERIO %d+ %d+ [%d%.]+,(%d+),"))
          local starting = first == SETUP_BU or first == RESTORE
          if starting then
            drop_steps()
            state.watch, state.sequencing = nil, nil
          end
          if starting or not check_bu(now, true) then
            state.watch = nil
            log("request: " .. text)
            plan_request(text)
          end
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
      push(PTID_DEVICE, PTID_STEERING_BUTTON, now)
      state.next_due = now + PRESS_SETTLE_S
      return
    end
    log("steering still shows " .. shown)
    state.steps = {}
    report_override("mode")
    return
  end
  table.remove(state.steps, 1)
  expect_sequencing("MAN", now)
  if mode ~= "MAN" then insert_step(1, 1, STEERING_MODE, MANUAL_SEQUENCING) end
  if state.steps[1] then state.next_due = now + state.steps[1].delay end
end

local function send_step(now, step)
  if step.command == DEST_KNOB then
    state.sent_at, state.moved_at, state.expected = now, nil, knob_position()
  end
  GetDevice(step.device or COMMAND_DEVICE):performClickableAction(step.command, step.value)
  log(string.format("sent %d %.2f", step.command, step.value))
  if step.command == STEERING_MODE then
    if step.value >= MANUAL_SEQUENCING then
      expect_sequencing("MAN", now)
    else
      expect_sequencing("AUTO", now)
    end
  end
  if step.command == SELECT_WAYPOINT then state.selected = math.floor(step.value * 100 + 0.5) end
  if step.command == DIRECT_TO and state.selected then
    state.watch = { waypoint = state.selected, check_at = now + ORDER_WAIT_S, confirmed = false, buttons = {} }
  end
end

-- is there a display that shows all of these words? (the CDNU: its element ids are random, so match by text)
local function screen_shows(words)
  if #words == 0 then return true end
  for number = 0, LAST_INDICATION do
    local ok, text = pcall(list_indication, number)
    if ok and type(text) == "string" then
      local all = true
      for _, word in ipairs(words) do
        if not string.find(text, word, 1, true) then all = false end
      end
      if all then return true end
    end
  end
  return false
end

-- F-14B(U): load the flight plan again, one key at a time
local function restore_plan(now, step)
  local stage = step.stage or 1
  local press = RESTORE_KEYS[stage]
  if not press then
    log("the flight plan was loaded again")
    table.remove(state.steps, 1)
    state.sequencing = nil
    if state.steps[1] then state.next_due = now + state.steps[1].delay end
    return
  end
  step.since = step.since or now
  if now - step.since < (press.after_s or 0) then return end
  if not screen_shows(press.screen) then
    state.next_due = now + LOOK_S
    if now - step.since > PAGE_WAIT_S then
      log("the CDNU does not show " .. table.concat(press.screen, " + ") .. ": stopping the reload")
      drop_steps()
      report_override("page")
    end
    return
  end
  log("reload: key " .. press.key)
  push(CDNU_DEVICE, press.key, now)
  step.stage = stage + 1
  step.since = now
  if RESTORE_KEYS[step.stage] then
    state.next_due = now + KEY_GAP_S
  else
    state.next_due = now + AFTER_RELOAD_S
  end
end

local function run_steps(now, in_tomcat)
  if state.held then
    if now >= state.held.up_at then let_go() end
    return
  end
  local step = state.steps[1]
  if not step then return end
  if now < state.next_due then return end
  if in_tomcat and step.command == SETUP_BU then
    set_up_bu(now, step)
    return
  end
  if in_tomcat and step.command == RESTORE then
    restore_plan(now, step)
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
