"""F-14 RIO Radar (experimental, S219): "Hunt Bandit" has Jester lock a red aircraft for the player.

The mission names the red aircraft `AirTarget01` to `AirTarget99`, because Jester's lock order takes only such a name (set command 10024, Heatblur manual "Jester / Iceman set commands"). The
player calls from F10 > Other > RIO Enhancements; this mission script picks the nearest red aircraft the radar should be able to see and asks the export script on the player's PC
(`data/sqe_f14_radar_export.lua`) to send the order. The export script reports from the radar display whether it locked. Flown facts (probe 2026-11-26): the order locks the named aircraft only,
within a few seconds, and does not lock what the radar cannot see (out of range, behind); it takes the radar out of TWS into PD-STT; and it appears to stay armed, so every hunt ends with a release.

Pure functions, no pydcs.
"""
from __future__ import annotations

from .rio_nav import MENU_LUA, MENU_TITLE

REQUEST_FILE = "SQE_radar.req"
RESULT_FILE = "SQE_radar.res"
# The three calls were checked against a VAICOM phrase list (2026-11-26): no phrase starts with "Hunt"; "Break Lock", "Lock Target", "Next Target" and "Bandit" are all taken.
HUNT_TITLE = "Hunt Bandit"
NEXT_TITLE = "Hunt Next"
OFF_TITLE = "Hunt Off"
MAX_NAMES = 99                       # the lock order's range: AirTarget01 to AirTarget99
AZIMUTH_DEG = 65                     # the AWG-9 antenna's azimuth limit either side (Heatblur manual, "AZ SCAN": the scan centre moves within 65 degrees of the centreline)
ELEVATION_DEG = 60                   # judgment call: no figure found in the manual; Jester refuses what the radar cannot see anyway
RANGE_NM = 60                        # judgment call: how far a hunt looks
LOCK_WAIT_S = 6                      # a lock came within 3 s in the probe flight (once 19 s)
MAX_TRIES = 4

_SCRIPT = r"""
-- SQE F-14 RIO Radar (S219). Reads and writes plain text files only; nothing read is run as code.
if not (io and lfs) then
  trigger.action.outTextForGroup(__GROUP__, "RIO: the radar calls need mission scripting access. Open SQE before the mission.", 20)
  return
end

local PLAYER, GROUP = __UNIT__, __GROUP__
local request_path = lfs.writedir() .. [[Logs\__REQUEST__]]
local result_path = lfs.writedir() .. [[Logs\__RESULT__]]
local requests = 0
local hunt = nil          -- the aircraft being asked for or held: { number, name, asked_at, locked, count }
local tried = {}
local tries = 0
local word = "Got one"

local function say(text, seconds)
  trigger.action.outTextForGroup(GROUP, "RIO: " .. text, seconds or 12)
end

-- orders = "command:value command:value"
local function send(orders)
  requests = requests + 1
  local file = io.open(request_path, "w")
  if not file then return requests end
  file:write(string.format("SQERAD %d %d %s", requests, math.floor(timer.getTime()), orders))
  file:close()
  return requests
end

local function release()
  send("10024:0.0 10025:1.0")
  hunt = nil
end

local function result()
  local file = io.open(result_path, "r")
  if not file then return nil end
  local text = file:read("*a") or ""
  file:close()
  local count, state = string.match(text, "^SQERES (%d+) (%a+)")
  return tonumber(count), state
end

local function dot(a, b)
  return a.x * b.x + a.y * b.y + a.z * b.z
end

-- red aircraft the radar should be able to see, the nearest first
local function candidates()
  local me = Unit.getByName(PLAYER)
  if not me or not me:isExist() then return {} end
  local position = me:getPosition()
  local here = position.p
  local found = {}
  for number = 1, __MAX_NAMES__ do
    local name = string.format("AirTarget%02d", number)
    local unit = Unit.getByName(name)
    if unit and unit:isExist() and unit:getLife() > 1 and unit:inAir() then
      local there = unit:getPoint()
      local d = { x = there.x - here.x, y = there.y - here.y, z = there.z - here.z }
      local ahead, up, right = dot(d, position.x), dot(d, position.y), dot(d, position.z)
      local azimuth = math.deg(math.atan2(right, ahead))
      local elevation = math.deg(math.atan2(up, math.sqrt(ahead * ahead + right * right)))
      local range = math.sqrt(dot(d, d)) / 1852
      if math.abs(azimuth) <= __AZIMUTH__ and math.abs(elevation) <= __ELEVATION__ and range <= __RANGE__
         and land.isVisible({ x = here.x, y = here.y + 2, z = here.z }, { x = there.x, y = there.y + 2, z = there.z }) then
        found[#found + 1] = { number = number, name = name, range = range }
      end
    end
  end
  table.sort(found, function(a, b) return a.range < b.range end)
  return found
end

-- "Su-27, 020 for 28, angels 24."
local function describe(name)
  local me, unit = Unit.getByName(PLAYER), Unit.getByName(name)
  if not me or not unit then return "bandit." end
  local here, there = me:getPoint(), unit:getPoint()
  local bearing = (math.deg(math.atan2(there.z - here.z, there.x - here.x)) - __MAGVAR__) % 360
  local range = math.sqrt((there.x - here.x) ^ 2 + (there.z - here.z) ^ 2) / 1852
  return string.format("%s, %03.0f for %.0f, angels %.0f.", unit:getTypeName(), bearing, range, there.y * 3.28084 / 1000)
end

local function ask_next()
  for _, entry in ipairs(candidates()) do
    if not tried[entry.name] and tries < __MAX_TRIES__ then
      tried[entry.name] = true
      tries = tries + 1
      hunt = { number = entry.number, name = entry.name, asked_at = timer.getTime(), locked = false }
      hunt.count = send(string.format("10024:%.2f", entry.number / 100))
      return
    end
  end
  release()
  say("Nothing I can lock ahead.")
end

-- drop whatever is held, then ask a second later, so an old lock is not mistaken for the new one
local function start(excluded, reply)
  release()
  tried = {}
  if excluded then tried[excluded] = true end
  tries = 0
  word = reply
  timer.scheduleFunction(function() ask_next() end, nil, timer.getTime() + 1)
end

local function hunt_bandit()
  start(nil, "Got one")
end

local function hunt_next()
  local current = hunt and hunt.name or nil
  start(current, "Next one")
end

local function hunt_off()
  tried = {}
  release()
  say("Letting him go.")
end

local function tick()
  if not hunt then return end
  local count, state = result()
  local unit = Unit.getByName(hunt.name)
  local alive = unit and unit:isExist() and unit:getLife() > 1
  if hunt.locked then
    if not alive or (count == hunt.count and state == "lost") then
      release()
      say("Lost him.")
    end
    return
  end
  if count == hunt.count and state == "locked" then
    hunt.locked = true
    say(word .. ". " .. describe(hunt.name), 15)
  elseif count == hunt.count and state == "blind" then
    -- the display could not be read: say whom he was told to lock, and leave it to the pilot
    hunt.locked = true
    say("Going for " .. describe(hunt.name) .. " Check your lock.", 15)
  elseif not alive or timer.getTime() - hunt.asked_at > __LOCK_WAIT__ then
    ask_next()
  end
end

for _, path in ipairs({ request_path, result_path }) do
  -- both empty at the start: what they hold then is from an earlier flight, and an old "locked" would match a new request's number
  local file = io.open(path, "w")
  if file then file:close() end
end
__MENU_LUA__missionCommands.addCommandForGroup(GROUP, "__HUNT__", rio_menu, hunt_bandit)
missionCommands.addCommandForGroup(GROUP, "__NEXT__", rio_menu, hunt_next)
missionCommands.addCommandForGroup(GROUP, "__OFF__", rio_menu, hunt_off)
timer.scheduleFunction(function(_, t)
  local ok, problem = pcall(tick)
  if not ok then env.info("SQE RIO radar: " .. tostring(problem)) end
  return t + 0.5
end, nil, timer.getTime() + 1)
"""


def _lua_text(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def mission_script(group_id: int, unit_name: str, magvar_deg: float) -> str:
    """The mission script for the player's F-14. `magvar_deg`: the theatre's magnetic variation, east positive (the bearing in the message is magnetic)."""
    values = {"__GROUP__": str(group_id), "__UNIT__": _lua_text(unit_name), "__MAGVAR__": "(%.2f)" % magvar_deg,
              "__REQUEST__": REQUEST_FILE, "__RESULT__": RESULT_FILE, "__MENU_TITLE__": MENU_TITLE, "__HUNT__": HUNT_TITLE, "__NEXT__": NEXT_TITLE, "__OFF__": OFF_TITLE,
              "__MAX_NAMES__": str(MAX_NAMES), "__AZIMUTH__": str(AZIMUTH_DEG), "__ELEVATION__": str(ELEVATION_DEG), "__RANGE__": str(RANGE_NM),
              "__LOCK_WAIT__": str(LOCK_WAIT_S), "__MAX_TRIES__": str(MAX_TRIES)}
    script = _SCRIPT.replace("__MENU_LUA__", MENU_LUA)          # first: the menu text has a mark of its own
    for mark, value in values.items():
        script = script.replace(mark, value)
    return script


# The name an airborne red aircraft gets when this mission has RIO Radar.
def target_name(number: int) -> str:
    return "AirTarget%02d" % number
