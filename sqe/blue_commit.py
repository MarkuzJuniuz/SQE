"""S158 / S160 (XO 2026-11-22): fighters of BOTH sides commit on enemy fighters in reach, outside the other side's SAM cover.

S158 gave blue's TARCAPs, station escorts and sweeps a commit script (test T1fix5 Syria on the dedicated server: blue 3 lost, red 11, against 18 / 9 before).
S160 (same script, both sides):
* the SAM rule tests the SHOOTER: a flight may commit on an enemy jet under SAM cover as long as its own lead is outside the enemy SAM circles; it breaks off
  when its lead enters one (shoot into the umbrella from outside, never fly into it). T1fix5: a Su-27 sat 5 to 8 nm inside a SAM circle from 55 to 19 km and
  shot down Chevy 1-1 because the old rule (target outside cover) refused the commit;
* at most COMMIT_MAX_PER_TARGET flights on one enemy group (T1fix5: four flights piled onto one MiG-29 pair);
* S160b (T1fix6): a break-off buffer (SAM_BREAK_BUFFER_NM) with hysteresis (commit only beyond SAM_COMMIT_BUFFER_NM), a cool-down before a recommit on the same
  group (COMMIT_COOLDOWN_S), and a "hurt" break-off when the flight lost a jet since it committed (then COMMIT_HURT_COOLDOWN_S);
* an optional leash round an anchor point (HVAACAPs: they must not leave the tanker / AWACS for long; S160c: the base / carrier BARCAP guards too);
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
COMMIT_ALT_FT = 30000             # S168: the altitude blue's cover fighters fly at (F-15C 33,000 ft, the rest 25,000 to 30,000): the commit script's SAM rings are the rings against a jet this high (`samtier.ring_nm`)
SAM_RING_MARGIN_NM = 3.0        # an enemy SAM ring counts this much bigger (scramble.STATION_RING_MARGIN_NM, the defender's margin)
HVAACAP_REACH_NM = 30            # S160: a tanker / AWACS guard commits only this far (judgment call; its normal circle is the guard ring). S176a (v0.41.616): was 25 (46 km); red's escorts fired R-27ERs first from 41 to 56 km in 8 of 14 HVAACAP fights while the guard committed at 42 to 43 km (37 server runs, `.claude/s176-barcap-hvaacap-evidence.md`); 30 nm = the base / carrier BARCAP reach. Judgment call
HVAACAP_LEASH_NM = 30            # ...and never more than this from its station (judgment call: it must stay with what it guards)
# S176b (XO 2026-11-24: "tanker pilots should be able to move away from danger ... let them save themselves if they need to move off track"): a tanker or an AWACS
# pulls back from enemy fighters. The idea is the brevity pair RETROGRADE ("Withdraw(ing) while executing defensive procedures in response to a threat") and
# SCRAM ("FRIENDLY asset is in immediate danger. Withdraw clear in the direction indicated for survival"), ATP 1-02.1 (2023). The distances are judgment calls
# (no public figure found): the S174 / S177 / S182 server runs lost the tanker to raid escorts about 7 minutes after they came within 40 nm.
HVAA_SCRAM_NM = 60              # an enemy fighter in the air this close: the aircraft leaves its track (an R-27ER shot from about 25 to 30 nm in the runs: 60 nm is about 4 minutes of closure)
HVAA_RETRO_NM = 40              # it flies this far straight away from that fighter and orbits there
HVAA_CLEAR_NM = 80              # no enemy fighter within this for HVAA_QUIET_S: it goes back to its track
HVAA_QUIET_S = 300
HVAA_REPLAN_S = 120             # while away and still threatened, a new point away from the nearest fighter at most this often
BARCAP_REACH_NM = 30            # S160c (T1fix7 Caucasus: two F-14BU carrier BARCAP jets, reach 45 nm, fought away from the fleet and died): a base / carrier BARCAP guard commits only this far (judgment call, like HVAACAP_REACH_NM)
BARCAP_LEASH_FLEET_NM = 25      # ...and never more than this from its station. A carrier station is `barcap.STATION_FLEET_NM` 35 nm out; 35 + 25 = 60 nm from the boat stays inside the ships' SM-2 reach (`barcap.FLEET_REACH_NM` 78, measured p90 77.5 nm in S168). Judgment call
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
            ring_nm = samtier.ring_nm(asset.variant, COMMIT_ALT_FT)
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


def commit_lua(side, flights, sams, hvaa=None) -> str:
    """The mission script for one side ("blue" or "red").
    `flights`: [{"g": group name, "reach": m, "t0": s, "t1": s, optional "ax", "az", "leash" (m), optional "bx", "bz" (the far end of the patrol's race-track; the leash is round the segment)}], `sams`: [(x, z, radius m)] of the ENEMY's cover."""
    if side == "blue":
        own, enemy, table, ewr = "BLUE", "RED", "SQE_COMMIT_BLUE", "false"
    else:
        own, enemy, table, ewr = "RED", "BLUE", "SQE_COMMIT_RED", "true"
    flight_rows = []
    for flight in flights:
        leash = int(flight.get("leash") or 0)
        anchor_x = int(flight.get("ax") or 0)
        anchor_z = int(flight.get("az") or 0)
        # S176a: the far end of the race-track; a flight without one has a leash round a point (both ends the same)
        end_x = anchor_x
        end_z = anchor_z
        if flight.get("bx") is not None and flight.get("bz") is not None:
            end_x = int(flight["bx"])
            end_z = int(flight["bz"])
        flight_rows.append("{g=%s, reach=%d, t0=%d, t1=%d, ax=%d, az=%d, bx=%d, bz=%d, leash=%d}" % (
            _lua_string(flight["g"]), int(flight["reach"]), int(flight["t0"]), int(flight["t1"]),
            anchor_x, anchor_z, end_x, end_z, leash))
    hvaa_rows = []                  # S176b: the group names of the side's tankers and AWACS that may pull back
    for group_name in (hvaa or []):
        hvaa_rows.append("{g=%s}" % _lua_string(group_name))
    sam_rows = []
    for x, z, radius in sams:
        sam_rows.append("{%d, %d, %d}" % (int(x), int(z), int(radius)))
    data = ("%s = {side=%s, own=%s, enemy=%s, ewr=%s, step=%d, breakf=%s, maxper=%d, brk=%d, cmt=%d, cool=%d, hurtcool=%d, hurtquiet=%d, flights={%s}, sams={%s}}"
            % (table, _lua_string(side), _lua_string(own), _lua_string(enemy), ewr, COMMIT_STEP_S, repr(float(COMMIT_BREAK_FACTOR)),
               COMMIT_MAX_PER_TARGET, int(SAM_BREAK_BUFFER_NM * 1852), int(SAM_COMMIT_BUFFER_NM * 1852), COMMIT_COOLDOWN_S, COMMIT_HURT_COOLDOWN_S, COMMIT_HURT_QUIET_S,
               ", ".join(flight_rows), ", ".join(sam_rows)))
    data += ("\n%s.hvaa = {%s}\n%s.scram = %d\n%s.retro = %d\n%s.clear = %d\n%s.hvaaquiet = %d\n%s.replan = %d"
             % (table, ", ".join(hvaa_rows), table, int(HVAA_SCRAM_NM * 1852), table, int(HVAA_RETRO_NM * 1852), table, int(HVAA_CLEAR_NM * 1852),
                table, HVAA_QUIET_S, table, HVAA_REPLAN_S))
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
  -- S176a: the leash is round the patrol's own race-track, the segment from its station (ax, az) to its far end (bx, bz): the distance to
  -- the nearest point of that segment. Measured from the station alone, a base BARCAP (25 nm leg, 15 nm leash) could not commit for 40 % of a lap.
  local end_x = f.bx or f.ax
  local end_z = f.bz or f.az
  local sx = end_x - f.ax
  local sz = end_z - f.az
  local length2 = sx * sx + sz * sz
  local along = 0
  if length2 > 0 then
    along = ((p.x - f.ax) * sx + (p.z - f.az) * sz) / length2
    if along < 0 then along = 0 end
    if along > 1 then along = 1 end
  end
  local dx = p.x - (f.ax + along * sx)
  local dz = p.z - (f.az + along * sz)
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
-- S176b: a tanker or an AWACS pulls back from enemy fighters (RETROGRADE / SCRAM) and goes back to its track when they are gone.
local function nearestFighter(p)
  local best = nil
  local bestPoint = nil
  for _, eg in ipairs(coalition.getGroups(ENEMY, Group.Category.AIRPLANE)) do
    if eg and eg:isExist() then
      for _, u in ipairs(eg:getUnits()) do
        if u and u:isExist() and u:inAir() and (u:hasAttribute("Fighters") or u:hasAttribute("Interceptors") or u:hasAttribute("Multirole fighters")) then
          local up = u:getPoint()
          local d = dist(p, up)
          if best == nil or d < best then
            best = d
            bestPoint = up
          end
        end
      end
    end
  end
  return best, bestPoint
end
local function pullBack(h, g, lead, p, threat, d, now)
  local dx = p.x - threat.x
  local dz = p.z - threat.z
  local length = math.sqrt(dx * dx + dz * dz)
  if length < 1 then return end
  local v = lead:getVelocity()
  local speed = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
  local point = {x = p.x + dx / length * C.retro, y = p.z + dz / length * C.retro}
  local task = {id = "Orbit", params = {pattern = "Circle", point = point, speed = speed, altitude = p.y}}
  if h.away then pcall(function() g:getController():popTask() end) end
  local ok = pcall(function() g:getController():pushTask(task) end)
  if ok then
    if not h.away then
      env.info("SQECOMMIT " .. C.side .. " " .. h.g .. " pulls back, fighter at " .. math.floor(d / 1000) .. " km, t " .. math.floor(now))
      pcall(function() trigger.action.outTextForCoalition(OWN, string.upper(h.g) .. ": moving off track, bandits " .. math.floor(d / 1852) .. " miles.", 10) end)
    end
    h.away = true
    h.pushed = now
    h.clearAt = nil
  end
end
local function hvaaTick(now, seenBySide)
  for _, h in ipairs(C.hvaa or {}) do
    local g = Group.getByName(h.g)
    if g and g:isExist() then
      local lead = firstUnit(g)
      if lead and lead:inAir() then
        local p = lead:getPoint()
        local d, threat = nearestFighter(p)
        local known = seenBySide or (d ~= nil and d <= C.scram / 2)      -- the side's radar picture, or close enough for its own warning receiver
        if not h.away then
          if d ~= nil and known and d <= C.scram then pullBack(h, g, lead, p, threat, d, now) end
        elseif d ~= nil and d <= C.scram and now - (h.pushed or 0) >= C.replan then
          pullBack(h, g, lead, p, threat, d, now)
        elseif d == nil or d > C.clear then
          if not h.clearAt then h.clearAt = now + C.hvaaquiet end
          if now >= h.clearAt then
            pcall(function() g:getController():popTask() end)
            h.away = false
            h.clearAt = nil
            env.info("SQECOMMIT " .. C.side .. " " .. h.g .. " returns to its track at " .. math.floor(now))
            pcall(function() trigger.action.outTextForCoalition(OWN, string.upper(h.g) .. ": back on track.", 10) end)
          end
        else
          h.clearAt = nil
        end
      end
    end
  end
end
local function tick(_, t)
  local now = timer.getTime()
  NOWT = now
  local seenBySide = sideSees()
  pcall(hvaaTick, now, seenBySide)      -- S176b: never lets an error here stop the commits
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
