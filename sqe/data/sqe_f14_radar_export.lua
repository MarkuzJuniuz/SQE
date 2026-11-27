-- SQE F-14 RIO Radar export script (S219, experimental). Installed by SQE: Settings > DCS Integration. One line at the end of Export.lua loads it.
-- The mission writes "SQERAD <count> <time> <command>:<value> ..." into Logs\SQE_radar.req (in your Saved Games\DCS folder in single player, DCS_Server for your own server).
-- This script sends those set commands to the F-14 (Jester's lock order 10024 and break lock 10025), watches the radar mode on the TID and answers in Logs\SQE_radar.res:
-- "SQERES <count> locked", "SQERES <count> lost", or "SQERES <count> blind" when the display cannot be read. It acts only in an F-14 and only when the mission asks.
-- What it did is logged in Logs\SQE_rio_radar.log.

local lfs = require("lfs")

local COMMAND_DEVICE = 1          -- the F-14's proxy device (its devices.lua: the device set commands go to)
local LOCK_ORDER = 10024
local LAST_INDICATION = 40
local POLL_S = 0.2
local ORDER_GAP_S = 0.3
local WATCH_S = 7                 -- how long a lock order is watched for a lock (the mission gives up after 6)
local LOST_AFTER = 5              -- this many looks without single-target track = the lock is gone (1 s)

local state = {}
local previous_start = LuaExportStart
local previous_stop = LuaExportStop
local previous_after_frame = LuaExportAfterNextFrame

local function reset()
  state = { next_poll = 0, seen = {}, queue = {}, next_send = 0, watch = nil, page = nil, log_started = false }
end

local function log(text)
  local mode = "a"
  if not state.log_started then mode = "w" end
  local file = io.open(lfs.writedir() .. [[Logs\SQE_rio_radar.log]], mode)
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
  return { own .. [[Logs\SQE_radar.req]], parent_folder(own) .. [[DCS_Server\Logs\SQE_radar.req]] }
end

local function read_text(path)
  local file = io.open(path, "r")
  if not file then return "" end
  local text = file:read("*a") or ""
  file:close()
  return text
end

local function answer(path, count, word)
  local file = io.open((string.gsub(path, "%.req$", ".res")), "w")
  if file then
    file:write(string.format("SQERES %d %s", count, word))
    file:close()
  end
  log("reported " .. count .. " " .. word)
end

-- "locked" (a single-target track mode is on the display), "search" (a search mode is), or nil when no radar mode can be read
local function radar_mode()
  local function look(number)
    local ok, text = pcall(list_indication, number)
    if not ok or type(text) ~= "string" then return nil end
    if string.find(text, "PDSTT", 1, true) or string.find(text, "PSTT", 1, true) then return "locked" end
    if string.find(text, "TWSA ", 1, true) or string.find(text, "TWSM ", 1, true) or string.find(text, "RWS ", 1, true) or string.find(text, "PDSRCH", 1, true) or string.find(text, "PSRCH", 1, true) then return "search" end
    return nil
  end
  if state.page then
    local mode = look(state.page)
    if mode then return mode end
  end
  for number = 0, LAST_INDICATION do
    local mode = look(number)
    if mode then
      state.page = number
      return mode
    end
  end
  return nil
end

local function send_next(now)
  local order = state.queue[1]
  if not order or now < state.next_send then return end
  table.remove(state.queue, 1)
  local ok, problem = pcall(function() GetDevice(COMMAND_DEVICE):performClickableAction(order.command, order.value) end)
  if ok then
    log(string.format("sent %d %.2f", order.command, order.value))
  else
    log("send failed: " .. tostring(problem))
  end
  state.next_send = now + ORDER_GAP_S
  -- watch for the lock from the moment the order is in the jet
  if order.watch then
    state.watch = { path = order.path, count = order.count, started = now, locked = false, seen_mode = false, misses = 0 }
  end
end

-- What a file holds when we first look is old (an earlier flight): only a change after that is a request.
local function poll(now)
  for _, path in ipairs(request_paths()) do
    local text = read_text(path)
    if state.seen[path] == nil then
      state.seen[path] = text
    elseif state.seen[path] ~= text then
      state.seen[path] = text
      local count = tonumber(string.match(text, "^SQERAD (%d+) "))
      if count then
        log("request: " .. text)
        state.queue, state.watch = {}, nil
        for command, value in string.gmatch(text, "(%d+):(%-?[%d%.]+)") do
          local number = tonumber(command)
          if number == LOCK_ORDER or number == 10025 then
            local amount = tonumber(value)
            state.queue[#state.queue + 1] = { command = number, value = amount, watch = number == LOCK_ORDER and amount > 0, path = path, count = count }
          end
        end
      end
    end
  end
end

local function watch(now)
  local current = state.watch
  if not current then return end
  local mode = radar_mode()
  if mode then current.seen_mode = true end
  if not current.locked then
    if mode == "locked" then
      current.locked = true
      answer(current.path, current.count, "locked")
    elseif now - current.started > WATCH_S then
      state.watch = nil
    elseif not current.seen_mode and now - current.started > 2 then
      state.watch = nil
      answer(current.path, current.count, "blind")
    end
  else
    if mode == "locked" then
      current.misses = 0
    else
      current.misses = current.misses + 1
      if current.misses >= LOST_AFTER then
        state.watch = nil
        answer(current.path, current.count, "lost")
      end
    end
  end
end

local function tick()
  local now = LoGetModelTime()
  if not now then return end
  local me = LoGetSelfData()
  if not me or string.sub(tostring(me.Name), 1, 4) ~= "F-14" then return end
  send_next(now)
  if now < state.next_poll then return end
  state.next_poll = now + POLL_S
  poll(now)
  watch(now)
end

reset()

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
  if not ok then pcall(log, "error " .. tostring(problem)) end
end
