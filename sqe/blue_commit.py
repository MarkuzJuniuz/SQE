"""S158 / S160 (XO 2026-11-22): fighters of BOTH sides commit on enemy fighters in reach, outside the other side's SAM cover.

S158 gave blue's TARCAPs, station escorts and sweeps a commit script (test T1fix5 Syria on the dedicated server: blue 3 lost, red 11, against 18 / 9 before).
S160 (same script, both sides):
* the SAM rule tests the SHOOTER: a flight may commit on an enemy jet under SAM cover as long as its own lead is outside the enemy SAM circles; it breaks off
  when its lead enters one (shoot into the umbrella from outside, never fly into it). T1fix5: a Su-27 sat 5 to 8 nm inside a SAM circle from 55 to 19 km and
  shot down Chevy 1-1 because the old rule (target outside cover) refused the commit;
* at most COMMIT_MAX_PER_TARGET flights on one enemy group (T1fix5: four flights piled onto one MiG-29 pair);
* S160b (T1fix6): a break-off buffer (SAM_BREAK_BUFFER_NM) with hysteresis (commit only beyond SAM_COMMIT_BUFFER_NM), a cool-down before a recommit on the same
  group (COMMIT_COOLDOWN_S), and a "hurt" break-off when the flight lost a jet since it committed (then COMMIT_HURT_COOLDOWN_S);
* an optional leash round an anchor point (HAVCAPs: they must not leave the tanker / AWACS for long; S160c: the base / carrier BARCAP guards too);
* S160c: a flight that breaks off "hurt" commits on nothing for COMMIT_HURT_QUIET_S;
* every air-to-air AI flight is registered (blue: station cover, support CAPs, alert pairs, raid interceptors, cover flights without a station; red: patrols,
  alert pairs, reliefs, standbys, raid-defence reinforcements). Red's raid escorts and sweeps are NOT registered (they fly Escort / FighterSweep with the bombers).

Every COMMIT_STEP_S seconds, for each flight in its window whose lead is in the air: the nearest enemy airplane in the air within reach (and within leash +
reach of the anchor, if leashed), seen by the side (an own AWACS, for red also an own EWR, else the flight's own radar), whose group has fewer than
COMMIT_MAX_PER_TARGET flights on it, gets an AttackGroup pushed on top of the flight's route. Break off: target group gone ("dead": cleared, no pop), the lead
within SAM_BREAK_BUFFER_NM of an enemy SAM circle ("sam"), the flight lost a jet ("hurt"), the target beyond COMMIT_BREAK_FACTOR x reach ("far"), the lead beyond the leash ("leash"), the window over ("window"):
popTask (only while the target lives, when the attack should be on top). Every commit / break-off goes to dcs.log as "SQECOMMIT <side> ...".

Not verified in DCS: that popTask removes exactly the pushed attack; that red EWRs carry the "EWR" attribute (if not, red falls back to AWACS / own radar).
"""
from __future__ import annotations

from . import samtier
from . import threatmap as tm
from .models import AssetKind

BLUE_COMMIT = True              # switch: blue's commit script
RED_COMMIT = True               # switch: red's commit script (S160, XO 2026-11-22: "apply it to red too")
COMMIT_STEP_S = 10              # how often the script looks (seconds). Judgment call: about 5 km of closure a step at 1,000 kt combined
COMMIT_BREAK_FACTOR = 1.5       # break off when the target is this many times the reach away (it is running). Judgment call
COMMIT_MAX_PER_TARGET = 2       # S160: at most this many flights on one enemy group. Judgment call (T1fix5: four on one pair)
SAM_BREAK_BUFFER_NM = 5.0       # S160b: break off when the lead is within this of an enemy SAM circle (T1fix6: flights broke off with the missile already in flight). Judgment call
SAM_COMMIT_BUFFER_NM = 8.0      # S160b: commit only when the lead is more than this outside every enemy SAM circle: 3 nm of hysteresis, so a flight does not flap on the line. Judgment call
COMMIT_COOLDOWN_S = 120         # S160b: no recommit on the same group this long after a sam / far / leash break-off (T1fix6: Enfield 1 / 2 flapped four times on Alert 12). Judgment call
COMMIT_HURT_COOLDOWN_S = 300    # S160b: ...and this long after a flight lost a jet and broke off (reason hurt). Judgment call
SAM_RING_MARGIN_NM = 3.0        # an enemy SAM ring counts this much bigger (scramble.STATION_RING_MARGIN_NM, the defender's margin)
HAVCAP_REACH_NM = 25            # S160: a tanker / AWACS guard commits only this far (judgment call; its normal circle is the guard ring)
HAVCAP_LEASH_NM = 30            # ...and never more than this from its station (judgment call: it must stay with what it guards)
BARCAP_REACH_NM = 30            # S160c (T1fix7 Caucasus: two F-14BU carrier BARCAP jets, reach 45 nm, fought away from the fleet and died): a base / carrier BARCAP guard commits only this far (judgment call, like HAVCAP_REACH_NM)
BARCAP_LEASH_FLEET_NM = 25      # ...and never more than this from its station. A carrier station is `barcap.STATION_FLEET_NM` 35 nm out; 35 + 25 = 60 nm from the boat stays inside the ships' SM-2 reach (`barcap.FLEET_REACH_NM` 70, measured 51 to 67 nm). Judgment call
BARCAP_LEASH_BASE_NM = 15       # ...a base station is `barcap.STATION_BASE_NM` 25 nm out; 25 + 15 = 40 nm from the field, the Patriot's ring (HAWK edge inside it). Judgment call
COMMIT_HURT_QUIET_S = 300       # S160c (T1fix7 Syria: Alert 10 broke off "hurt", then went straight for the strikers and a Tiyas MiG-29 killed Viper 3-4): after a hurt break-off the flight commits on NOTHING for this long, not only on the group it left. Both sides. Judgment call
RED_REACH_EXTRA_NM = 10         # S160: red's reach = its engage circle (`a2a_zone_nm`) + this, at most RED_REACH_MAX_NM (judgment call:
RED_REACH_MAX_NM = 35           # the R-27ER first shots in the T1 runs were 24 to 58 km)


def red_sam_circles(state) -> list:
    """[(x, z, radius m)] of RED SAM cover blue's fighters must not fly into: every live red SAM site with a ring of 3 nm or more, an umbrella SA-10 / SA-5 at
    its scramble_nm (the defender-station margin), the rest at their ring + SAM_RING_MARGIN_NM. Map x / y of SQE are DCS x / z."""
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


def blue_sam_circles(state) -> list:
    """[(x, z, radius m)] of BLUE cover red's fighters must not fly into: blue's SAM sites and the carrier groups (`barcap._enemy_rings(state, "red")`, the
    rings red's patrols are already kept out of), each SAM_RING_MARGIN_NM bigger."""
    from .barcap import _enemy_rings
    circles = []
    for x, y, reach_m in _enemy_rings(state, "red"):
        circles.append((x, y, reach_m + SAM_RING_MARGIN_NM * 1852.0))
    return circles


def red_reach_nm(type_name) -> float:
    """S160: a red fighter's commit reach: its engage circle + RED_REACH_EXTRA_NM, at most RED_REACH_MAX_NM."""
    from .red_air_picture import a2a_zone_nm
    return min(RED_REACH_MAX_NM, a2a_zone_nm(type_name) + RED_REACH_EXTRA_NM)


def _lua_string(text) -> str:
    """A Lua string literal in double quotes."""
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def commit_lua(side, flights, sams) -> str:
    """The mission script for one side ("blue" or "red").
    `flights`: [{"g": group name, "reach": m, "t0": s, "t1": s, optional "ax", "az", "leash" (m)}], `sams`: [(x, z, radius m)] of the ENEMY's cover."""
    if side == "blue":
        own, enemy, table, ewr = "BLUE", "RED", "SQE_COMMIT_BLUE", "false"
    else:
        own, enemy, table, ewr = "RED", "BLUE", "SQE_COMMIT_RED", "true"
    flight_rows = []
    for flight in flights:
        leash = int(flight.get("leash") or 0)
        flight_rows.append("{g=%s, reach=%d, t0=%d, t1=%d, ax=%d, az=%d, leash=%d}" % (
            _lua_string(flight["g"]), int(flight["reach"]), int(flight["t0"]), int(flight["t1"]),
            int(flight.get("ax") or 0), int(flight.get("az") or 0), leash))
    sam_rows = []
    for x, z, radius in sams:
        sam_rows.append("{%d, %d, %d}" % (int(x), int(z), int(radius)))
    data = ("%s = {side=%s, own=%s, enemy=%s, ewr=%s, step=%d, breakf=%s, maxper=%d, brk=%d, cmt=%d, cool=%d, hurtcool=%d, hurtquiet=%d, flights={%s}, sams={%s}}"
            % (table, _lua_string(side), _lua_string(own), _lua_string(enemy), ewr, COMMIT_STEP_S, repr(float(COMMIT_BREAK_FACTOR)),
               COMMIT_MAX_PER_TARGET, int(SAM_BREAK_BUFFER_NM * 1852), int(SAM_COMMIT_BUFFER_NM * 1852), COMMIT_COOLDOWN_S, COMMIT_HURT_COOLDOWN_S, COMMIT_HURT_QUIET_S,
               ", ".join(flight_rows), ", ".join(sam_rows)))
    return data + "\n" + COMMIT_BODY.replace("__TABLE__", table)


COMMIT_BODY = r"""
local C = __TABLE__
C.count = {}
for _, f0 in ipairs(C.flights) do f0.cool = {} end
local OWN = coalition.side[C.own]
local ENEMY = coalition.side[C.enemy]
local function inSam(p, buffer)
  for _, s in ipairs(C.sams) do
    local dx = p.x - s[1]
    local dz = p.z - s[2]
    local r = s[3] + buffer
    if dx * dx + dz * dz < r * r then return true end
  end
  return false
end
local function liveCount(g)
  local n = 0
  for _, u in ipairs(g:getUnits()) do
    if u and u:isExist() then n = n + 1 end
  end
  return n
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
local function sideSees()
  for _, g in ipairs(coalition.getGroups(OWN, Group.Category.AIRPLANE)) do
    if g and g:isExist() then
      for _, u in ipairs(g:getUnits()) do
        if u and u:isExist() and u:hasAttribute("AWACS") then return true end
      end
    end
  end
  if C.ewr then
    for _, g in ipairs(coalition.getGroups(OWN, Group.Category.GROUND)) do
      if g and g:isExist() then
        for _, u in ipairs(g:getUnits()) do
          if u and u:isExist() and u:hasAttribute("EWR") then return true end
        end
      end
    end
  end
  return false
end
local function leashed(f)
  return f.leash and f.leash > 0
end
local function anchorDist(f, p)
  local dx = p.x - f.ax
  local dz = p.z - f.az
  return math.sqrt(dx * dx + dz * dz)
end
local NOWT = 0
local function nearestEnemy(f, group, lead, seenBySide)
  local lp = lead:getPoint()
  local best, bestD = nil, nil
  for _, eg in ipairs(coalition.getGroups(ENEMY, Group.Category.AIRPLANE)) do
    if eg and eg:isExist() and (C.count[eg:getName()] or 0) < C.maxper and not (f.cool[eg:getName()] and f.cool[eg:getName()] > NOWT) then
      for _, u in ipairs(eg:getUnits()) do
        if u and u:isExist() and u:inAir() then
          local p = u:getPoint()
          local d = dist(lp, p)
          local inLeash = true
          if leashed(f) and anchorDist(f, p) > f.leash + f.reach then inLeash = false end
          if d <= f.reach and inLeash then
            local seen = seenBySide
            if not seen then
              local ok, res = pcall(function() return group:getController():isTargetDetected(u, Controller.Detection.RADAR) end)
              seen = ok and res and true or false
            end
            if seen and (bestD == nil or d < bestD) then best, bestD = eg, d end
          end
        end
      end
    end
  end
  return best, bestD
end
local function targetState(f, lp)
  local tg = Group.getByName(f.on)
  if not tg or not tg:isExist() then return "dead" end
  local nearest = nil
  for _, u in ipairs(tg:getUnits()) do
    if u and u:isExist() then
      local d = dist(lp, u:getPoint())
      if nearest == nil or d < nearest then nearest = d end
    end
  end
  if nearest == nil then return "dead" end
  if liveCount(Group.getByName(f.g)) < f.units0 then return "hurt" end
  if inSam(lp, C.brk) then return "sam" end
  if leashed(f) and anchorDist(f, lp) > f.leash then return "leash" end
  if nearest > f.reach * C.breakf then return "far" end
  return "on"
end
local function breakOff(f, g, why, now)
  if why ~= "dead" then
    pcall(function() g:getController():popTask() end)
  end
  C.count[f.on] = math.max(0, (C.count[f.on] or 1) - 1)
  if why == "sam" or why == "far" or why == "leash" then f.cool[f.on] = now + C.cool end
  if why == "hurt" then
    f.cool[f.on] = now + C.hurtcool
    f.quiet = now + C.hurtquiet
  end
  env.info("SQECOMMIT " .. C.side .. " " .. f.g .. " breaks off " .. f.on .. " (" .. why .. ") at " .. math.floor(now))
  f.on = nil
end
local function tick(_, t)
  local now = timer.getTime()
  NOWT = now
  local seenBySide = sideSees()
  for _, f in ipairs(C.flights) do
    if not f.cool then f.cool = {} end
    local g = Group.getByName(f.g)
    if g and g:isExist() then
      local lead = firstUnit(g)
      if lead then
        local lp = lead:getPoint()
        if f.on and now > f.t1 then
          breakOff(f, g, "window", now)
        elseif f.on then
          local st = targetState(f, lp)
          if st ~= "on" then breakOff(f, g, st, now) end
        end
        local free = not f.on and now >= f.t0 and now <= f.t1 and lead:inAir() and not inSam(lp, C.cmt)
        if free and f.quiet and now < f.quiet then free = false end
        if free and leashed(f) and anchorDist(f, lp) > f.leash then free = false end
        if free then
          local eg, d = nearestEnemy(f, g, lead, seenBySide)
          if eg then
            local task = {id = "AttackGroup", params = {groupId = eg:getID(), groupAttack = true, expend = "Auto", attackQtyLimit = false}}
            local ok = pcall(function() g:getController():pushTask(task) end)
            if ok then
              f.on = eg:getName()
              f.units0 = liveCount(g)
              C.count[f.on] = (C.count[f.on] or 0) + 1
              env.info("SQECOMMIT " .. C.side .. " " .. f.g .. " commits on " .. f.on .. " at " .. math.floor(d / 1000) .. " km, t " .. math.floor(now))
            end
          end
        end
      end
    end
  end
  return now + C.step
end
timer.scheduleFunction(tick, nil, timer.getTime() + 5)
env.info("SQECOMMIT " .. C.side .. " armed: " .. #C.flights .. " flights, " .. #C.sams .. " SAM circles")
"""
