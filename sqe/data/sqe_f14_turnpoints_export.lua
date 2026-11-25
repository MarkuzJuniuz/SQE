-- SQE F-14B Turnpoints (experimental): puts the turnpoint you pick in F10 > Other > Turnpoints into your F-14B's fix point (FP) and turns the DEST knob to it.
--
-- The mission writes one line ("SQETP <zone number> <time>") into Logs\SQE_turnpoints.req: in your Saved Games\DCS folder in single player, in the sibling
-- DCS_Server folder when the sortie runs on the DCS dedicated server on this PC. This script reads it and sends Heatblur's Jester commands to the cockpit's
-- command device: DEST knob to FP, pick FP, enter the coordinates from trigger zone WaypointZoneNN. It does nothing in any other aircraft.
--
-- HOW TO INSTALL: SQE does it for you (Settings > DCS integration > Install Turnpoints Script). By hand: copy THIS file to
-- Saved Games\DCS\Scripts\sqe_f14_turnpoints_export.lua and add at the END of Saved Games\DCS\Scripts\Export.lua (create it if it does not exist; this file
-- chains the previous export functions instead of replacing them):
--   --[[SQE F14 TURNPOINTS EXPORT]]dofile(lfs.writedir() .. [[Scripts\sqe_f14_turnpoints_export.lua]])
-- Remove the line (and the file) to uninstall.

local lfs = require("lfs")

local AIRCRAFT = "F-14B"
local COMMAND_DEVICE = 1          -- the F-14's PROXY device (its devices.lua: "hardcoded device ID of 1 is used by mission files")
local DEST_KNOB, PICK_WAYPOINT, ENTER_FROM_ZONE = 10017, 10018, 10019
local FIX_POINT = 0.4
local POLL_S = 0.5

local state = { next_poll = 0, seen = {}, steps = {} }
local previous_start = LuaExportStart
local previous_stop = LuaExportStop
local previous_after_frame = LuaExportAfterNextFrame

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

-- The commands for one request, a few seconds apart (as flown in the test of 2026-11-24).
local function plan_steps(zone, now)
  state.steps = {
    { due = now, command = DEST_KNOB, value = FIX_POINT },
    { due = now + 3, command = PICK_WAYPOINT, value = FIX_POINT },
    { due = now + 5, command = ENTER_FROM_ZONE, value = zone / 100 },
  }
end

-- What a file holds when we first look is old (an earlier flight): only a change after that is a request.
local function poll(now)
  for _, path in ipairs(request_paths()) do
    local text = read_text(path)
    if state.seen[path] == nil then
      state.seen[path] = text
    elseif state.seen[path] ~= text then
      state.seen[path] = text
      local zone = tonumber(string.match(text, "^SQETP (%d+) "))
      if zone and zone >= 1 and zone <= 99 then
        plan_steps(zone, now)
      end
    end
  end
end

local function tick()
  local now = LoGetModelTime()
  if not now then return end
  if now >= state.next_poll then
    state.next_poll = now + POLL_S
    poll(now)
  end
  local step = state.steps[1]
  if step and now >= step.due then
    table.remove(state.steps, 1)
    local me = LoGetSelfData()
    if me and me.Name == AIRCRAFT then
      GetDevice(COMMAND_DEVICE):performClickableAction(step.command, step.value)
    end
  end
end

local function reset()
  state.next_poll, state.seen, state.steps = 0, {}, {}
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
