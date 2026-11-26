-- SQE F-14 RIO Navigation (experimental): presses the Jester commands the mission asks for in your F-14B or F-14B(U) (F10 > Other > Work the waypoints, and Turnpoints).
--
-- The mission writes one line into Logs\SQE_turnpoints.req ("SQERIO <count> <time> <delay>,<command>,<value>;..."): in your Saved Games\DCS folder in single player,
-- in the sibling DCS_Server folder when the sortie runs on the DCS dedicated server on this PC. This script reads it and sends the commands to the cockpit's command device.
-- When the F-14B's destination knob moves without such a command (you, or Jester at your request) it writes Logs\SQE_turnpoints.ovr beside the request, and the mission
-- stops working your waypoints. It does nothing in any other aircraft.
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
  state = { next_poll = 0, seen = {}, steps = {}, request_path = nil, expected = nil, sent_at = nil, moved_at = nil, overrides = 0 }
end
reset()

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

local function add_step(due, command, value)
  state.steps[#state.steps + 1] = { due = due, command = command, value = value }
end

-- the commands of one request, in order, each `delay` seconds after the one before it
local function plan_request(text, now)
  local list = string.match(text, "^SQERIO %d+ %d+ (.+)$")
  if not list then return false end
  local due = now
  if #state.steps > 0 then due = state.steps[#state.steps].due + 1 end
  for delay, command, value in string.gmatch(list, "([%d%.]+),(%d+),([%d%.%-]+)") do
    due = due + tonumber(delay)
    add_step(due, tonumber(command), tonumber(value))
  end
  return true
end

-- a mission built before S210 asks for one turnpoint like this (as flown in the test of 2026-11-24)
local function plan_old_turnpoint(zone, now)
  state.steps = {}
  add_step(now, DEST_KNOB, FIX_POINT)
  add_step(now + 3, PICK_WAYPOINT, FIX_POINT)
  add_step(now + 5, ENTER_FROM_ZONE, zone / 100)
end

-- What a file holds when we first look is old (an earlier flight): only a change after that is a request.
local function poll(now)
  for _, path in ipairs(request_paths()) do
    local text = read_text(path)
    if state.seen[path] == nil then
      state.seen[path] = text
    elseif state.seen[path] ~= text then
      state.seen[path] = text
      if plan_request(text, now) then
        state.request_path = path
      else
        local zone = tonumber(string.match(text, "^SQETP (%d+) "))
        if zone and zone >= 1 and zone <= 99 then plan_old_turnpoint(zone, now) end
      end
    end
  end
end

local function knob_position()
  local ok, value = pcall(function() return GetDevice(0):get_argument_value(DEST_ARGUMENT) end)
  if ok and type(value) == "number" then return math.floor(value * 100 + 0.5) end
  return nil
end

local function knob_step_waiting()
  for _, step in ipairs(state.steps) do
    if step.command == DEST_KNOB then return true end
  end
  return false
end

local function report_override()
  if not state.request_path then return end
  state.overrides = state.overrides + 1
  local file = io.open((string.gsub(state.request_path, "%.req$", ".ovr")), "w")
  if file then
    file:write(string.format("SQEOVR %d %.0f", state.overrides, LoGetModelTime() or 0))
    file:close()
  end
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
    report_override()
  end
end

local function tick()
  local now = LoGetModelTime()
  if not now then return end
  local me = LoGetSelfData()
  local in_tomcat = me and string.sub(tostring(me.Name), 1, #AIRCRAFT_PREFIX) == AIRCRAFT_PREFIX
  if now >= state.next_poll then
    state.next_poll = now + POLL_S
    poll(now)
    if in_tomcat then watch_knob(now) end
  end
  local step = state.steps[1]
  if step and now >= step.due then
    table.remove(state.steps, 1)
    if in_tomcat then
      if step.command == DEST_KNOB then
        state.sent_at, state.moved_at, state.expected = now, nil, knob_position()
      end
      GetDevice(COMMAND_DEVICE):performClickableAction(step.command, step.value)
    end
  end
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
  pcall(tick)
end
