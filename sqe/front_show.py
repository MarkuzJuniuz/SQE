"""S233 (XO 2026-11-27 / 28, "the ground war feels like a wall decor"): the front battle gets two layers.

The SHOW: behind each side's line a gun battery and (by level) rocket launchers fire into the other side's line on a timetable, and smoke columns burn at both lines.
In DCS this is mostly a show: in the S233 server probes (2026-11-28, `test-runs/S233-probe/REPORT.md`) five gun runs killed one vehicle in all but knocked down
9 to 48 trees and buildings each, which is what a pilot sees. ED's own F-16C Caucasus Free Flight does the same: guns firing into smoke columns.
The FIGHT: the two sides stand FRONT_GAP_M apart, too far to see each other through the trees (the probes: no shot at 1.5 or 2.0 km, fire from 0:12 at 1.0 km),
so a balanced sector is an artillery duel; the stronger side creeps forward (`MissionBuilder.FRONT_ADVANCE_M`) into direct-fire range. A group down to half its
vehicles or fewer breaks contact and pulls back FALLBACK_M (the probes: both red platoons fell back at 2 of 4 and lived to the end) instead of dying to the last jeep.

Ground units only: no player flight is scripted by this (rules section 9). Pure functions, no pydcs: the builder places the groups (`cas_ground`), this writes the script.
"""
from __future__ import annotations

FRONT_GAP_M = 2000.0          # blue company to red column: no direct fire at this gap in forested ground (S233 probes), the creep (1,200 m) brings the attacker to about 800 m
GUNS_BACK_M = 10000.0         # each side's battery this far behind its line (S233 probe; tube artillery sits roughly 5 to 15 km back: from memory, medium-low firmness)
MLRS_BACK_M = 14000.0         # rocket launchers further back (S233 probe; judgment call)
SHOW_SLIP_M = 1000.0          # a battery whose spot had to move further than this to reach land is left out
BATTERY_SPACING_M = 60        # tubes / launchers side by side this far apart across the firing direction (server run S233a: packed 20 m apart, a Grad salvo killed the launcher beside it; the probes used 60 m)
GUNS_PER_SIDE = 3            # tubes in each battery (judgment call: the probe used 4; 3 keeps the unit count down)
MLRS_BLUE = {1: 1, 2: 2, 3: 3}   # blue's launchers by level (S233 prompt, XO: "Blue should always MLRS these but scaled for the level"; counts a judgment call)
MLRS_RED = {1: 0, 2: 0, 3: 2}    # red's launchers: Level 3 only (XO: "even MLRS for red L3")
BLUE_GUN, RED_GUN = "M_109", "SAU_Gvozdika"       # M109 and 2S1 Gvozdika, as in the probes
BLUE_MLRS, RED_MLRS = "MLRS", "Grad_URAL"         # M270 and BM-21 Grad
# The timetable (seconds from the mission start), as flown in the probes: the guns obey a fire order about 2:40 after it (first shells 3:41 / 4:13)
GUN_PERIOD_S, GUN_FIRST_S = 180, (60, 90)          # blue, red
MLRS_PERIOD_S, MLRS_FIRST_S = 600, (240, 300)
GUN_SPREAD_M, GUN_RADIUS_M, GUN_ROUNDS = 150, 60, 8
MLRS_SPREAD_M, MLRS_RADIUS_M, MLRS_ROUNDS = 300, 200, 12
FALLBACK_M = 800.0            # how far a broken group pulls back (S233 probe)
SMOKE_BEHIND_M = 250.0        # smoke columns this far behind each line, where the other side's shells fall (judgment call)
SMOKE_SIDE_M = 200.0          # ...and this far to either side
SMOKE_PRESETS = (6, 1)        # DCS big-smoke presets: 6 medium smoke, 1 small smoke and fire
SMOKE_DENSITY = 0.5


def lua_text(text: str) -> str:
    """A Lua string literal for `text` (group names may hold any character)."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def gun_plan(group_name: str, targets: list, side: str, kind: str) -> dict:
    """One battery's timetable: who fires, at which groups, how often. `side` "blue" / "red", `kind` "guns" / "mlrs"."""
    first_index = 0 if side == "blue" else 1
    if kind == "mlrs":
        return {"name": group_name, "targets": list(targets), "period": MLRS_PERIOD_S, "first": MLRS_FIRST_S[first_index],
                "spread": MLRS_SPREAD_M, "radius": MLRS_RADIUS_M, "rounds": MLRS_ROUNDS}
    return {"name": group_name, "targets": list(targets), "period": GUN_PERIOD_S, "first": GUN_FIRST_S[first_index],
            "spread": GUN_SPREAD_M, "radius": GUN_RADIUS_M, "rounds": GUN_ROUNDS}


def script(seed: int, guns: list, smoke: list, fallback: list) -> str:
    """The front script: `guns` [gun_plan], `smoke` [(x, y, preset)], `fallback` [(group name, back x, back y)]. Same seed and plans = the same fire."""
    gun_rows = []
    for plan in guns:
        target_names = []
        for name in plan["targets"]:
            target_names.append(lua_text(name))
        gun_rows.append("{name = %s, targets = {%s}, period = %d, first = %d, spread = %d, radius = %d, rounds = %d}" % (
            lua_text(plan["name"]), ", ".join(target_names), plan["period"], plan["first"], plan["spread"], plan["radius"], plan["rounds"]))
    smoke_rows = []
    for number, (x, y, preset) in enumerate(smoke, 1):
        smoke_rows.append("{x = %.1f, y = %.1f, preset = %d, name = %s}" % (x, y, preset, lua_text("SQE front smoke %d" % number)))
    fallback_rows = []
    for name, x, y in fallback:
        fallback_rows.append("{name = %s, x = %.1f, y = %.1f}" % (lua_text(name), x, y))
    text = _SCRIPT
    text = text.replace("__SEED__", str(int(seed) % 2147483646 + 1))
    text = text.replace("__GUNS__", "{" + ", ".join(gun_rows) + "}")
    text = text.replace("__SMOKE__", "{" + ", ".join(smoke_rows) + "}")
    text = text.replace("__FALLBACK__", "{" + ", ".join(fallback_rows) + "}")
    text = text.replace("__DENSITY__", "%.2f" % SMOKE_DENSITY)
    return text


_SCRIPT = r"""
-- SQE front battle (S233): the guns' timetable, the smoke at the lines, and a broken group pulling back. Ground units only.
-- math.randomseed is nil in DCS's mission environment (S233 probe, 2026-11-27), so the shots are spread by a small seeded generator of our own.
local seed = __SEED__
local function next_random(top)
  seed = (seed * 16807) % 2147483647
  local fraction = seed / 2147483647
  if top then
    return math.floor(fraction * top) + 1
  end
  return fraction
end

local guns = __GUNS__
local smoke = __SMOKE__
local fallback = __FALLBACK__

-- the live units of the groups a battery fires at
local function live_targets(names)
  local out = {}
  for _, name in ipairs(names) do
    local group = Group.getByName(name)
    if group and group:isExist() then
      for _, unit in ipairs(group:getUnits() or {}) do
        if unit and unit:isExist() then
          out[#out + 1] = unit
        end
      end
    end
  end
  return out
end

local function fire(plan)
  local group = Group.getByName(plan.name)
  if group and group:isExist() and group:getSize() > 0 then
    local targets = live_targets(plan.targets)
    if #targets > 0 then
      local spot = targets[next_random(#targets)]:getPoint()
      local angle = next_random() * 2 * math.pi
      local reach = next_random() * plan.spread
      local point = {x = spot.x + reach * math.cos(angle), y = spot.z + reach * math.sin(angle)}
      group:getController():pushTask({id = "FireAtPoint", params = {point = point, radius = plan.radius, expendQty = plan.rounds, expendQtyEnabled = true}})
    end
  end
  return timer.getTime() + plan.period
end

for _, plan in ipairs(guns) do
  timer.scheduleFunction(function() return fire(plan) end, nil, timer.getTime() + plan.first)
end

for _, column in ipairs(smoke) do
  local ground = land.getHeight({x = column.x, y = column.y})
  trigger.action.effectSmokeBig({x = column.x, y = ground, z = column.y}, column.preset, __DENSITY__, column.name)
end

-- a group down to half its vehicles or fewer drives back to its fallback point, off road, and holds there
local start_size = {}
local pulled_back = {}
local function check_fallback()
  for _, plan in ipairs(fallback) do
    if not pulled_back[plan.name] then
      local group = Group.getByName(plan.name)
      if group and group:isExist() then
        local size = group:getSize()
        if start_size[plan.name] == nil then
          start_size[plan.name] = size
        elseif size > 0 and size * 2 <= start_size[plan.name] then
          local lead = group:getUnit(1)
          if lead and lead:isExist() then
            local here = lead:getPoint()
            local route = {points = {
              {x = here.x, y = here.z, type = "Turning Point", action = "Off Road", speed = 10, speed_locked = true},
              {x = plan.x, y = plan.y, type = "Turning Point", action = "Off Road", speed = 10, speed_locked = true},
            }}
            group:getController():setTask({id = "Mission", params = {route = route}})
            pulled_back[plan.name] = true
            env.info(string.format("SQE front: %s pulls back with %d of %d", plan.name, size, start_size[plan.name]))
          end
        end
      end
    end
  end
  return timer.getTime() + 10
end
timer.scheduleFunction(check_fallback, nil, timer.getTime() + 2)
"""
