"""S158 (XO 2026-11-22): blue cover fighters COMMIT on red fighters, the way red's alert pairs are scripted to rush blue.

Why: in the T1 Syria tests red's fighters were scrambled and flown at blue (scripted intercepts), fired first from 44 to 56 km, and blue's TARCAPs, escorts and
sweeps kept cruising: they may only attack inside fixed engage circles, and those stop short of red's SAM cover, where red's stations sit.

What the mission script does, every COMMIT_STEP_S seconds, for each registered AI cover flight inside its window (its PUSH time to the end of its hold):
* it looks for a red airplane in the air within the flight's reach (`cover_reach_nm`, 40 nm for an F-15C) of its lead;
* the red jet must NOT be inside red SAM cover (circles built here from the live red SAM sites), and blue must "see" it: a blue AWACS is up, or the lead's
  own radar detects it;
* the nearest such jet's group gets an AttackGroup task pushed on top of the flight's route (the flight resumes its route when the attack ends);
* the flight breaks off (the task is popped) when the target flies into red SAM cover or beyond COMMIT_BREAK_FACTOR x the reach, or when the window ends.
Every commit and break-off is written to dcs.log as "SQECOMMIT ...".

Not verified in DCS: that popTask removes exactly the pushed attack (it only pops while the target is alive, when the attack should still be on top).
A Python mixin is not needed: `commit_lua` builds the text, the mission builder adds it as a DoScript (like SQE_CALLIN).
"""
from __future__ import annotations

from . import samtier
from . import threatmap as tm
from .models import AssetKind

BLUE_COMMIT = True              # switch: False = no commit script (the circles alone, as before S158)
COMMIT_STEP_S = 10              # how often the script looks (seconds). Judgment call: fast enough for jets closing at 1,000+ kt combined (about 5 km a step)
COMMIT_BREAK_FACTOR = 1.5       # break off when the target is this many times the reach away (it is running). Judgment call
SAM_RING_MARGIN_NM = 3.0        # a red jet this far outside a SAM ring still counts as under cover (scramble.STATION_RING_MARGIN_NM, the defender's margin)


def red_sam_circles(state) -> list:
    """[(x, z, radius m)] of red SAM cover a commit must not chase into: every live red SAM site with a ring of 3 nm or more, an umbrella SA-10 / SA-5 at its
    scramble_nm (the defender-station margin), the rest at their ring + SAM_RING_MARGIN_NM. Map x / y of SQE are DCS x / z."""
    circles = []
    for asset in state.assets.values():
        if asset.kind != AssetKind.SAM or asset.destroyed or asset.health <= 0.25:
            continue
        if getattr(asset, "suppressed", False):
            continue
        if asset.variant in tm.UMBRELLA_VARIANTS:
            radius_nm = samtier.get(asset.variant, "scramble_nm")
        else:
            ring_nm = tm.RANGE_NM.get(asset.variant, 0)
            if ring_nm < 3:
                continue
            radius_nm = ring_nm + SAM_RING_MARGIN_NM
        circles.append((asset.x, asset.y, radius_nm * 1852.0))
    return circles


def _lua_string(text) -> str:
    """A Lua string literal in double quotes."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def commit_lua(flights, sams) -> str:
    """The mission script. `flights`: [{"g": group name, "reach": metres, "t0": start s, "t1": end s}], `sams`: [(x, z, radius m)]."""
    flight_rows = []
    for flight in flights:
        flight_rows.append("{g=%s, reach=%d, t0=%d, t1=%d}" % (_lua_string(flight["g"]), int(flight["reach"]), int(flight["t0"]), int(flight["t1"])))
    sam_rows = []
    for x, z, radius in sams:
        sam_rows.append("{%d, %d, %d}" % (int(x), int(z), int(radius)))
    data = ("SQE_COMMIT = {step=%d, breakf=%s, flights={%s}, sams={%s}}"
            % (COMMIT_STEP_S, repr(float(COMMIT_BREAK_FACTOR)), ", ".join(flight_rows), ", ".join(sam_rows)))
    return data + "\n" + COMMIT_BODY


COMMIT_BODY = r"""
local C = SQE_COMMIT
local function inSam(p)
  for _, s in ipairs(C.sams) do
    local dx = p.x - s[1]
    local dz = p.z - s[2]
    if dx * dx + dz * dz < s[3] * s[3] then return true end
  end
  return false
end
local function dist(a, b)
  local dx = a.x - b.x
  local dz = a.z - b.z
  return math.sqrt(dx * dx + dz * dz)
end
local function firstUnit(g)
  for _, u in ipairs(g:getUnits()) do
    if u and u:isExist() then return u end
  end
  return nil
end
local function awacsUp()
  for _, g in ipairs(coalition.getGroups(coalition.side.BLUE, Group.Category.AIRPLANE)) do
    if g and g:isExist() then
      for _, u in ipairs(g:getUnits()) do
        if u and u:isExist() and u:hasAttribute("AWACS") then return true end
      end
    end
  end
  return false
end
local function nearestRed(group, lead, reach, awacs)
  local lp = lead:getPoint()
  local best, bestD = nil, nil
  for _, rg in ipairs(coalition.getGroups(coalition.side.RED, Group.Category.AIRPLANE)) do
    if rg and rg:isExist() then
      for _, u in ipairs(rg:getUnits()) do
        if u and u:isExist() and u:inAir() then
          local p = u:getPoint()
          local d = dist(lp, p)
          if d <= reach and not inSam(p) then
            local seen = awacs
            if not seen then
              local ok, res = pcall(function() return group:getController():isTargetDetected(u, Controller.Detection.RADAR) end)
              seen = ok and res and true or false
            end
            if seen and (bestD == nil or d < bestD) then best, bestD = rg, d end
          end
        end
      end
    end
  end
  return best, bestD
end
local function targetState(name, lp, reach)
  local tg = Group.getByName(name)
  if not tg or not tg:isExist() then return "dead" end
  local nearest = nil
  for _, u in ipairs(tg:getUnits()) do
    if u and u:isExist() then
      local p = u:getPoint()
      local d = dist(lp, p)
      if nearest == nil or d < nearest.d then nearest = {d = d, p = p} end
    end
  end
  if nearest == nil then return "dead" end
  if inSam(nearest.p) then return "sam" end
  if nearest.d > reach * C.breakf then return "far" end
  return "on"
end
local function breakOff(f, g, why, now)
  if why ~= "dead" then
    pcall(function() g:getController():popTask() end)
  end
  env.info("SQECOMMIT " .. f.g .. " breaks off " .. f.on .. " (" .. why .. ") at " .. math.floor(now))
  f.on = nil
end
local function tick(_, t)
  local now = timer.getTime()
  local awacs = awacsUp()
  for _, f in ipairs(C.flights) do
    local g = Group.getByName(f.g)
    if g and g:isExist() then
      local lead = firstUnit(g)
      if lead then
        local lp = lead:getPoint()
        if f.on and now > f.t1 then
          breakOff(f, g, "window", now)
        elseif f.on then
          local st = targetState(f.on, lp, f.reach)
          if st ~= "on" then breakOff(f, g, st, now) end
        end
        if not f.on and now >= f.t0 and now <= f.t1 then
          local rg, d = nearestRed(g, lead, f.reach, awacs)
          if rg then
            local task = {id = "AttackGroup", params = {groupId = rg:getID(), groupAttack = true, expend = "Auto", attackQtyLimit = false}}
            local ok = pcall(function() g:getController():pushTask(task) end)
            if ok then
              f.on = rg:getName()
              env.info("SQECOMMIT " .. f.g .. " commits on " .. f.on .. " at " .. math.floor(d / 1000) .. " km, t " .. math.floor(now))
            end
          end
        end
      end
    end
  end
  return now + C.step
end
timer.scheduleFunction(tick, nil, timer.getTime() + 5)
env.info("SQECOMMIT armed: " .. #C.flights .. " flights, " .. #C.sams .. " SAM circles")
"""
