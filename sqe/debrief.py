"""Mission -> campaign feedback loop.

1. The builder embeds LUA_HOOK in the .miz.
2. During flight it rewrites  <Saved Games>\\SQE\\SQE_state.json  every 30 s and on every kill/loss/landing.
3. The waiting window polls that file; Accept applies it to the campaign.

REQUIRES io/lfs un-sanitized in <DCS>\\Scripts\\MissionScripting.lua (Settings has a one-click patch helper).
"""
from __future__ import annotations
import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from .models import AssetKind
from .state import CampaignState

LUA_HOOK = r'''
-- SQE debrief hook | campaign __CAMPAIGN__ | sortie __SORTIE__ | package __PKG__
if not (io and lfs) then
  env.warning("SQE: io/lfs are sanitized; patch Scripts/MissionScripting.lua (SQE Settings has a helper)")
  trigger.action.outText("SQE: results cannot be saved (MissionScripting.lua not patched)", 30)
  return
end
local DIR = lfs.writedir() .. "SQE"
lfs.mkdir(DIR)
local OUT = DIR .. "\\SQE_state.json"
local DESPAWN = { __DESPAWN__ }
local PLAYER = "__PLAYER__"
local PGROUP = "__PGROUP__"
local SOUND = "__SOUND__"
local SOUND_YOU = "__SOUND_YOU__"
local AITEST = __AITEST__            -- all-AI test: nobody sits in a flight, so calls go to everyone
local CALLS = { __CALLS__ }
local UFLT = { __UFLT__ }
local ENEMYAIR = { __ENEMYAIR__ }
-- v0.41.217: declared up here, before the event handler that reads them (a local further down the file is invisible to it: "attempt to index global DMGL")
local AWUNIT = "__AWUNIT__"
local DMGL = { __DMGL__ }                  -- unit name -> spoken label of every blue aircraft that may call (the player's own jet is not in it)
local DMG_ON = __DMGON__
local awdown = false                       -- the AWACS is down: its calls stop
local dmgCall                              -- defined with the radio calls below
local SITES = { __SITES__ }
local RUINS = { __RUINS__ }
local GATES = { __GATES__ }
local pl = { takeoff = nil, landed = nil, ka = 0, kg = 0, ks = 0 }
local dead, ejected, landed, ended = {}, {}, {}, false
local aborted = {}
local gateLog = {}
local kills = {}
local shots = {}
local jams = {}
local TRACK = {}                  -- v0.41.43: group name -> {{t, x, z, alt_m, fuel_pct, kts}, ...} the lead's position every 30 s (flights and red patrols), for finding where a flight really went
local deaths = {}                 -- why each loss happened: last hit seen, last fuel and altitude sample (so an unexplained loss still tells something)
local LASTHIT = {}                -- unit name -> {by, w, t} of the last hit on it
local SAMPLE = {}                 -- unit name -> {fuel, alt, spd, t} sampled every 30 s for every aircraft
local JAMW = { __JAMW__ }          -- unit name -> {from, to} mission seconds the jammer runs (AI: the attack leg); absent = always on
local JAMS = { __JAMS__ }
local ALERTS = { __ALERTS__ }       -- alert / scramble groups: g = group, f = the flag their trigger sets when called, b = field, ty = type
local ALOG = {}                     -- group -> {called = t, air = t}
local COVER = { __COVER__ }          -- v0.41.79: CAP pairs with a standby: g = group, n = jets, bf = flag that sends the pair home (its orbit stops), rf = flag that calls the replacement, u = planned end (s)
local COVERLOG = {}                 -- group -> {why, t, replaced}
local CFG = '__CFG__'               -- the build's settings (splash damage, ECM script), raw JSON
local splashN, splashK = 0, 0          -- unit name -> 1 internal set, 2 ECM pod (ecm.py)
__JAMCFG__
local function esc(s) return (tostring(s):gsub('[%c"\\]', function(c) return string.format("\\u%04x", string.byte(c)) end)) end
local function list(t)
  local o = {}
  for k, _ in pairs(t) do o[#o + 1] = '"' .. esc(k) .. '"' end
  table.sort(o)
  return "[" .. table.concat(o, ",") .. "]"
end
local function killsJson()
  local o = {}
  for _, k in ipairs(kills) do
    o[#o + 1] = string.format('{"k":"%s","kt":"%s","v":"%s","vt":"%s","w":"%s","t":%d}', esc(k.k), esc(k.kt), esc(k.v), esc(k.vt), esc(k.w), k.t)
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function shotsJson()
  local o = {}
  for _, k in ipairs(shots) do
    local more = ""
    if k.km then more = string.format(',"km":%.1f,"alt":%d', k.km, math.floor(k.alt or 0)) end        -- shooter-to-target range (km) and shooter altitude (m) at launch
    if k.tx and k.tz then more = more .. string.format(',"tx":%d,"tz":%d', math.floor(k.tx), math.floor(k.tz)) end        -- the target's map position: its last known spot
    if k.left then more = more .. string.format(',"left":%d', k.left) end        -- v0.41.122: air-to-air missiles still on the shooter
    o[#o + 1] = string.format('{"t":%d,"ev":"%s","by":"%s","bt":"%s","w":"%s","tg":"%s","tt":"%s"%s}', k.t, k.ev, esc(k.by), esc(k.bt), esc(k.w), esc(k.tg), esc(k.tt), more)
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function jamsJson()
  local o = {}
  for _, k in ipairs(jams) do
    o[#o + 1] = string.format('{"t":%d,"by":"%s","w":"%s","tg":"%s","p":%.2f,"km":%.1f,"killed":%s}', k.t, esc(k.by), esc(k.w), esc(k.tg), k.p, k.km, tostring(k.killed))
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function num(x) if x then return string.format("%d", math.floor(x)) end return "null" end
local function deathsJson()
  local o = {}
  for _, k in ipairs(deaths) do
    o[#o + 1] = string.format('{"n":"%s","t":%d,"ev":"%s","by":"%s","w":"%s","ago":%s,"fuel":%s,"alt_m":%s,"kts":%s,"sample_age":%s,"x":%s,"z":%s,"ground_m":%s}',
      esc(k.n), k.t, esc(k.ev), esc(k.by), esc(k.w), num(k.ago), k.fuel and string.format("%.2f", k.fuel) or "null", num(k.alt), num(k.kts), num(k.sage), num(k.x), num(k.z), num(k.gh))
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function alertsJson()
  local o, now = {}, timer.getTime()
  for _, a in ipairs(ALERTS) do
    local l = ALOG[a.g] or {}
    local stuck = (l.called ~= nil and l.air == nil and now - l.called > 300)
    o[#o + 1] = string.format('{"g":"%s","b":"%s","ty":"%s","called":%s,"air":%s,"stuck":%s}', esc(a.g), esc(a.b), esc(a.ty), num(l.called), num(l.air), tostring(stuck))
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function coverJson()
  local o = {}
  for _, c in ipairs(COVER) do
    local l = COVERLOG[c.g]
    if l then o[#o + 1] = string.format('{"g":"%s","why":"%s","t":%d,"replaced":%s}', esc(c.g), esc(l.why), l.t, tostring(l.replaced and true or false)) end
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function tracksJson()
  local o = {}
  for gn, pts in pairs(TRACK) do
    local q = {}
    for _, e in ipairs(pts) do q[#q + 1] = string.format("[%d,%d,%d,%d,%d,%d]", e[1], e[2], e[3], e[4], e[5] or -1, e[6] or -1) end
    o[#o + 1] = string.format('"%s":[%s]', esc(gn), table.concat(q, ","))
  end
  return "{" .. table.concat(o, ",") .. "}"
end
local function gatesJson()
  local o = {}
  for _, e in ipairs(gateLog) do
    o[#o + 1] = string.format('{"site":"%s","grp":"%s","t":%d,"ran":%d,"radars":%d,"abort":%s,"cmd":%s,"by":"%s","d0":%s,"d1":%s}',
      esc(e.site), esc(e.grp), e.t, e.ran, e.radars, tostring(e.abort), tostring(e.cmd), esc(e.by or ""), num(e.d0), num(e.d1))
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function rgateJson()
  local o = {}
  if SQE_RGATE then
    for n, e in pairs(SQE_RGATE) do
      o[#o + 1] = string.format('"%s":{"open":%s,"abort":%s}', esc(n), num(e.open), num(e.abort))
    end
  end
  return "{" .. table.concat(o, ",") .. "}"
end
local scrubLog = {}                         -- v0.41.223: the package scrubs (see the PACKAGE SCRUB block at the end)
local function scrubJson()
  local o = {}
  for _, e in ipairs(scrubLog) do
    o[#o + 1] = string.format('{"pkg":"%s","t":%d,"why":"%s","n":%d}', esc(e.pkg), e.t, esc(e.why), e.n)
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function dump()
  local f = io.open(OUT, "w")
  if not f then return end
  f:write(string.format('{"campaign":"__CAMPAIGN__","sortie":__SORTIE__,"package":"__PKG__","mission_ended":%s,"time":%d,"dead":%s,"ejected":%s,"landed":%s,"player":{"takeoff":%s,"landed":%s,"ka":%d,"kg":%d,"ks":%d},"kills":%s,"aborted":%s,"gates":%s,"shots":%s,"jams":%s,"deaths":%s,"alerts":%s,"cover":%s,"scrub":%s,"tracks":%s,"rgate":%s,"cfg":%s,"splash":{"blasts":%d,"kills":%d}}',
    tostring(ended), math.floor(timer.getTime()), list(dead), list(ejected), list(landed),
    num(pl.takeoff), num(pl.landed), pl.ka, pl.kg, pl.ks, killsJson(), list(aborted), gatesJson(), shotsJson(), jamsJson(), deathsJson(), alertsJson(), coverJson(), scrubJson(), tracksJson(), rgateJson(), CFG, splashN, splashK))
  f:close()
end
local function nameOf(obj)
  if obj and obj.getName then
    local ok, n = pcall(function() return obj:getName() end)
    if ok then return n end
  end
end
local SITE_OF = {}
for _, s in ipairs(SITES) do
  s.nalive, s.ntrk, s.nrad, s.gone, s.said = #s.units, #s.trk, #s.trk + #s.srch, {}, {}
  for _, u in ipairs(s.units) do SITE_OF[u] = s end
end
local isTrk, isRad = {}, {}
for _, s in ipairs(SITES) do
  for _, u in ipairs(s.trk) do isTrk[u] = true; isRad[u] = true end
  for _, u in ipairs(s.srch) do isRad[u] = true end
end
local lastcall = {}
local function throttle(key, secs)
  local now = timer.getTime()
  if lastcall[key] and now - lastcall[key] < secs then return false end
  lastcall[key] = now
  return true
end
local say
local function siteDead(n)
  local s = SITE_OF[n]
  if not s or s.gone[n] then return end
  s.gone[n] = true
  s.nalive = s.nalive - 1
  if isTrk[n] then s.ntrk = s.ntrk - 1 end
  if isRad[n] then s.nrad = s.nrad - 1 end
  local who = s.last or s.who
  local blind = (#s.trk + #s.srch) > 0 and s.nrad == 0 and not s.said.blind
  local trk = #s.trk > 0 and s.ntrk == 0 and not s.said.trk
  if blind then
    s.said.blind = true; s.said.trk = true
    say(who .. ": " .. s.label .. " suppressed, all radars destroyed.")
  elseif trk then
    s.said.trk = true
    say(who .. ": track radar destroyed, " .. s.label .. ".")
  end
  if s.nalive <= 0 and s.prim and not s.said.dead then
    s.said.dead = true
    say(who .. ": target destroyed, " .. s.label .. ".")
  end
end
local function shotCall(e)
  local ok, d = pcall(function() return e.weapon:getDesc() end)
  if not ok or not d then return nil end
  local cat, gd, mc = d.category, d.guidance, d.missileCategory
  if cat == 1 then
    if mc == 1 then
      if gd == 3 then return "Fox 3" elseif gd == 4 then return "Fox 1" else return "Fox 2" end
    end
    local okn, tn = pcall(function() return e.weapon:getTypeName() end)
    if gd == 5 or (okn and tn and (string.find(tn, "AGM_88", 1, true) or string.find(tn, "AGM-88", 1, true))) then return "Magnum" end
    return "Rifle"
  elseif cat == 3 then
    return "Bombs away"
  end
  return nil
end
local function logShot(ev, e, by)
  local function tname(o) local ok, t = pcall(function() return o:getTypeName() end); if ok and t then return t end return "?" end
  local w, tg, tt = "?", "", ""
  local km, salt = nil, nil
  local tx, tz = nil, nil                                     -- the target's map position (last known)
  if e.weapon then
    local ok, t = pcall(function() return e.weapon:getTypeName() end); if ok and t then w = t end
    if ev == "shot" then
      local okt, tgo = pcall(function() return e.weapon:getTarget() end)
      if okt and tgo then
        tg = nameOf(tgo) or ""; tt = tname(tgo)
        local okp, tp = pcall(function() return tgo:getPoint() end)
        local oks, sp = pcall(function() return e.initiator:getPoint() end)
        if okp and tp then tx, tz = tp.x, tp.z end
        if okp and oks and tp and sp then km = math.sqrt((tp.x - sp.x) ^ 2 + (tp.z - sp.z) ^ 2) / 1000; salt = sp.y end
      end
    end
  end
  local left = nil                                            -- v0.41.122: air-to-air missiles the shooter still carries after this shot (to see when a pair goes winchester)
  if ev == "shot" and e.initiator then
    local oka, am = pcall(function() return e.initiator:getAmmo() end)
    if oka and am then
      left = 0
      for _, a in ipairs(am) do
        local d = a.desc
        if d and d.category == 1 and d.missileCategory == 1 then left = left + (a.count or 0) end
      end
    end
  end
  if ev == "hit" and e.target then
    local okc, cat = pcall(function() return e.target:getCategory() end)
    if okc and cat == Object.Category.SCENERY then return end        -- trees, houses, poles: pure noise in the log
    tg = nameOf(e.target) or ""; tt = tname(e.target)
    local okq, tq = pcall(function() return e.target:getPoint() end)
    if okq and tq then tx, tz = tq.x, tq.z end
  end
  if ev == "hit" and tg ~= "" then LASTHIT[tg] = { by = by or "?", w = w, t = timer.getTime() } end
  if #shots >= 2000 then return end   -- v0.41.6: was 600; busy runs reached 595
  shots[#shots + 1] = { t = math.floor(timer.getTime()), ev = ev, by = by or "?", bt = e.initiator and tname(e.initiator) or "?", w = w, tg = tg, tt = tt, km = km, alt = salt, tx = tx, tz = tz, left = left }
end
-- jamming: a radar-guided missile fired at an aircraft with jamming equipment may be defeated partway through its flight
-- v0.41.210 (XO 2026-10-30): the player's own jammer. ECMP "live": the F-16C's ECM lamp, written four times a second by sqe/data/sqe_ecm_export.lua (Export.lua) to
-- Logs\SQE_ecm.flag as "<0|1> <model time>"; a missing or stale file falls back to the attack-leg window below. ECMP "f10": an FC3 jet (nothing readable in its
-- cockpit): the F10 > Other commands ECM ON / ECM OFF set the flag (starts off).
local ECMP = "__ECMP__"
local FC3ECM = false
local ECMMSG = "__ECMMSG__" == "1"                      -- v0.41.213: Settings > Experimental > Show ECM status: the on-screen ECM messages
local function liveEcm()
  local ok, v = pcall(function()
    local f = io.open(lfs.writedir() .. [[Logs\SQE_ecm.flag]], "r")
    if not f then return nil end
    local s = f:read("*l"); f:close()
    local on, t = string.match(s or "", "^(%d)%s+([%d%.]+)")
    if not on or math.abs(timer.getTime() - tonumber(t)) > 5 then return nil end
    return on == "1"
  end)
  if ok then return v end
  return nil
end
local function jamOn(name)
  if name == PLAYER and ECMP ~= "" then
    if ECMP == "f10" then return FC3ECM end
    local v = liveEcm()
    if v ~= nil then return v end
  end
  local w = JAMW[name]
  if not w then return true end
  local t = timer.getTime()
  return t >= w[1] and t <= w[2]
end
if ECMP == "f10" then
  local tries = 0
  local function addF10()
    tries = tries + 1
    local g = Group.getByName(PGROUP)
    if not g then
      if tries < 60 then return timer.getTime() + 2 end
      return nil
    end
    local id = g:getID()
    missionCommands.addCommandForGroup(id, "ECM ON", nil, function() FC3ECM = true; if ECMMSG then trigger.action.outTextForGroup(id, "ECM on (F10)", 6) end end)
    missionCommands.addCommandForGroup(id, "ECM OFF", nil, function() FC3ECM = false; if ECMMSG then trigger.action.outTextForGroup(id, "ECM off (F10)", 6) end end)
    return nil
  end
  timer.scheduleFunction(addF10, nil, timer.getTime() + 1)
end
if ECMP == "live" and ECMMSG then                              -- v0.41.212 (XO): tell the pilot what SQE sees: once when the lamp file is first read, then on every on / off change
  local last = nil
  timer.scheduleFunction(function(_, t)
    local v = liveEcm()
    if v ~= nil and v ~= last then
      local g = Group.getByName(PGROUP)
      if g then
        trigger.action.outTextForGroup(g:getID(), (last == nil and "SQE sees your ECM lamp: " or "ECM ") .. (v and "on" or "off"), 6)
      end
      last = v
    end
    return t + 2
  end, nil, timer.getTime() + 5)
end
local function jamCheck(e, shooter)
  if not next(JAMS) or not e.weapon then return end
  local ok, d = pcall(function() return e.weapon:getDesc() end)
  if not ok or not d or d.category ~= 1 or (d.guidance ~= 3 and d.guidance ~= 4) then return end
  local okt, tgo = pcall(function() return e.weapon:getTarget() end)
  if not okt or not tgo then return end
  local tn = nameOf(tgo)
  if not tn then return end
  local okp, tp = pcall(function() return tgo:getPoint() end)
  local oks, sp = pcall(function() return e.initiator:getPoint() end)
  if not (okp and oks and tp and sp) then return end
  local dm = math.sqrt((tp.x - sp.x) ^ 2 + (tp.z - sp.z) ^ 2)
  if dm <= JC.burn then return end
  local p = 0
  if JAMS[tn] and jamOn(tn) then p = JC["p" .. JAMS[tn]] or 0 end
  if p < JC.cover then
    local tc = tgo:getCoalition()
    for name, tier in pairs(JAMS) do
      if tier >= 2 and name ~= tn and jamOn(name) then
        local u = Unit.getByName(name)
        if u and u:isExist() and u:getCoalition() == tc then
          local pp = u:getPoint()
          if math.sqrt((pp.x - tp.x) ^ 2 + (pp.z - tp.z) ^ 2) <= JC.coverM then p = math.max(p, JC.cover); break end
        end
      end
    end
  end
  if p <= 0 then return end
  p = p * math.min(1, (dm - JC.burn) / (JC.full - JC.burn))
  local killed = math.random() < p
  local wn = "?"
  local okw, t = pcall(function() return e.weapon:getTypeName() end); if okw and t then wn = t end
  if #jams < 200 then jams[#jams + 1] = { t = math.floor(timer.getTime()), by = shooter or "?", w = wn, tg = tn, p = p, km = dm / 1000, killed = killed } end
  if killed then
    local w = e.weapon
    timer.scheduleFunction(function()
      local okx, ex = pcall(function() return w:isExist() end)
      if okx and ex then pcall(function() w:destroy() end) end
    end, nil, timer.getTime() + math.max(1.5, dm / 800 * (0.3 + 0.4 * math.random())))
    if UFLT[tn] and throttle("jam:" .. tn, 8) then say(UFLT[tn] .. ": missile defeated.") end
  end
  dump()
end
-- splash damage (Settings, off by default): DCS often leaves a vehicle a few metres from a bomb untouched. When an air-to-ground weapon
-- (bomb, rocket, air-to-ground missile) reaches the ground, ground units within a blast radius scaled to its explosive mass (cube root,
-- like real overpressure) get a blast of their own, weaker with distance. A weapon that vanishes in the air (a JSOW opening, a missile
-- shot down) does nothing. Kills it causes are credited to the shooter (DCS gives them no initiator).
local SPLASH = __SPLASH__
local SPL = { k = 9.0, pow = 0.35, minkg = 1, maxr = 120, dt = 0.1 }
local SPLW, SPLBY = {}, {}
local function splashTrack(e, shooter)
  if not SPLASH or not e.weapon then return end
  local ok, d = pcall(function() return e.weapon:getDesc() end)
  if not ok or not d then return end
  local a2g = d.category == 3 or d.category == 2 or (d.category == 1 and (d.missileCategory == 4 or d.missileCategory == 5 or d.missileCategory == 6))
  if not a2g then return end
  local kg = (d.warhead and (d.warhead.explosiveMass or d.warhead.mass)) or 0
  if kg < SPL.minkg then return end
  local wn = "?"; pcall(function() wn = e.weapon:getTypeName() end)
  SPLW[#SPLW + 1] = { w = e.weapon, kg = kg, by = shooter or "?", wn = wn }
end
local function splashAt(p, s)
  local gh = land.getHeight({ x = p.x, y = p.z })
  if p.y - gh > 15 then return end                                   -- ended in the air: no ground blast
  local r = math.min(SPL.maxr, SPL.k * s.kg ^ (1 / 3))
  local now = timer.getTime()
  local hits = {}
  pcall(function()
    world.searchObjects(Object.Category.UNIT, { id = world.VolumeType.SPHERE, params = { point = { x = p.x, y = gh, z = p.z }, radius = r } },
      function(u)
        local ok, cat = pcall(function() return u:getDesc().category end)
        if ok and (cat == Unit.Category.GROUND_UNIT or cat == Unit.Category.SHIP) then hits[#hits + 1] = u end
        return true
      end)
  end)
  for _, u in ipairs(hits) do
    pcall(function()
      local up = u:getPoint()
      local d = math.sqrt((up.x - p.x) ^ 2 + (up.z - p.z) ^ 2)
      if d > 3 then                                                    -- the direct hit is DCS's own
        local f = 1 - d / r
        if f > 0 then
          SPLBY[u:getName()] = { by = s.by, w = "splash:" .. s.wn, t = now }
          trigger.action.explosion(up, s.kg * SPL.pow * f * f)
          splashN = splashN + 1
        end
      end
    end)
  end
end
if SPLASH then
  timer.scheduleFunction(function(_, t)
    local keep = {}
    for _, s in ipairs(SPLW) do
      local ok, ex = pcall(function() return s.w:isExist() end)
      if ok and ex then
        pcall(function() s.p = s.w:getPoint(); s.v = s.w:getVelocity() end)
        keep[#keep + 1] = s
      elseif s.p then
        local v = s.v or { x = 0, y = 0, z = 0 }
        pcall(splashAt, { x = s.p.x + v.x * SPL.dt, y = s.p.y + v.y * SPL.dt, z = s.p.z + v.z * SPL.dt }, s)
      end
    end
    SPLW = keep
    return t + SPL.dt
  end, nil, timer.getTime() + 1)
end
local H = {}
function H:onEvent(e)
  local id = e.id
  local n = nameOf(e.initiator)
  if id == world.event.S_EVENT_LAND or id == world.event.S_EVENT_RUNWAY_TOUCH then
    if n and not dead[n] then
      landed[n] = true
      if n == PLAYER then pl.landed = timer.getTime() end
      dump()
      if DESPAWN[n] then
        timer.scheduleFunction(function()
          local u = Unit.getByName(n)
          if u then u:destroy() end
        end, nil, timer.getTime() + 25)
      end
    end
  elseif id == world.event.S_EVENT_DEAD or id == world.event.S_EVENT_CRASH or id == world.event.S_EVENT_PILOT_DEAD then
    if n and not landed[n] then
      if not dead[n] and #deaths < 200 then
        local lh, sm, now = LASTHIT[n], SAMPLE[n], timer.getTime()
        local evn = (id == world.event.S_EVENT_CRASH) and "crash" or ((id == world.event.S_EVENT_PILOT_DEAD) and "pilot_dead" or "dead")
        deaths[#deaths + 1] = { n = n, t = math.floor(now), ev = evn, by = lh and lh.by or "", w = lh and lh.w or "", ago = lh and (now - lh.t) or nil,
                                fuel = sm and sm.fuel, alt = sm and sm.alt, kts = sm and sm.spd, sage = sm and (now - sm.t) or nil, x = sm and sm.x, z = sm and sm.z, gh = sm and sm.gh }
      end
      dead[n] = true; dump(); siteDead(n)
      if n == AWUNIT then awdown = true end                      -- the AWACS is gone: its calls stop (v0.41.215)
      local lh_ = LASTHIT[n]
      if DMGL[n] and lh_ and timer.getTime() - lh_.t < 90 then pcall(dmgCall, n, "down") end
    end
  elseif id == world.event.S_EVENT_TAKEOFF then
    if n == PLAYER and not pl.takeoff then pl.takeoff = timer.getTime(); dump() end
    local okg, gn = pcall(function() return e.initiator:getGroup():getName() end)
    if okg and gn and ALOG[gn] and not ALOG[gn].air then ALOG[gn].air = timer.getTime(); dump() end
  elseif id == world.event.S_EVENT_SHOT then
    logShot("shot", e, n)
    pcall(jamCheck, e, n)
    pcall(splashTrack, e, n)
    local lab = UFLT[n]
    if lab and e.weapon then
      local call = shotCall(e)
      if call and throttle("shot:" .. lab .. call, 6) then say(lab .. ": " .. call .. ".") end
    end
  elseif id == world.event.S_EVENT_HIT then
    logShot("hit", e, n)
    local tn = nameOf(e.target)
    local s = tn and SITE_OF[tn]
    local lab = UFLT[n]
    if s and lab then
      s.last = lab
      if throttle("hit:" .. lab, 15) then say(lab .. ": direct hit.") end
    end
    if tn and DMGL[tn] then pcall(dmgCall, tn, "hit") end
  elseif id == world.event.S_EVENT_KILL then
    -- v0.41.10+: only real targets count: units and static objects (fuel tanks, bunkers), never scenery (trees, houses the bombs also flatten)
    local okc, ocat = pcall(function() return e.target:getCategory() end)
    local real = okc and (ocat == Object.Category.UNIT or ocat == Object.Category.STATIC)
    if not real then return end
    if not n then                                                      -- a splash kill: DCS names no killer, the blast's shooter gets it
      local tn1 = nameOf(e.target)
      local sb = tn1 and SPLBY[tn1]
      if sb and timer.getTime() - sb.t < 10 then
        n = sb.by
        splashK = splashK + 1
        if n == PLAYER then pl.kg = pl.kg + 1; dump() end
      end
    end
    do
      local tn0 = nameOf(e.target)
      if tn0 and ocat == Object.Category.STATIC and not dead[tn0] then dead[tn0] = true; dump() end      -- v0.41.192: a building (supply site) counts dead on the kill even if DCS sends no DEAD event for a static
      if tn0 and #kills < 300 then
        local function tname(o) local ok, t = pcall(function() return o:getTypeName() end); if ok and t then return t end return "?" end
        local wn = "?"
        if e.weapon then local ok, t = pcall(function() return e.weapon:getTypeName() end); if ok and t then wn = t end end
        kills[#kills + 1] = { k = n or "?", kt = e.initiator and tname(e.initiator) or "?", v = tn0, vt = e.target and tname(e.target) or "?", w = wn, t = math.floor(timer.getTime()) }
        dump()
      end
    end
    if n == PLAYER then
      local ok, cat = pcall(function() return e.target:getDesc().category end)
      if ok then
        if cat == 0 or cat == 1 then pl.ka = pl.ka + 1 elseif cat == 3 then pl.ks = pl.ks + 1 else pl.kg = pl.kg + 1 end
      end
      dump()
    end
    local tn = nameOf(e.target)
    if UFLT[n] and tn and ENEMYAIR[tn] and throttle("splash:" .. n, 4) then say(UFLT[n] .. ": splash one.") end
  elseif id == world.event.S_EVENT_EJECTION then
    if n then ejected[n] = true; dump() end
    if n and DMGL[n] then pcall(dmgCall, n, "down") end
  elseif id == world.event.S_EVENT_MISSION_END then
    ended = true; dump()
  end
end
world.addEventHandler(H)
timer.scheduleFunction(function(_, t)
  for _, side in ipairs({ coalition.side.BLUE, coalition.side.RED }) do
    local okg, groups = pcall(function() return coalition.getGroups(side, Group.Category.AIRPLANE) end)
    if okg and groups then
      for _, g in ipairs(groups) do
        local oku, units = pcall(function() return g:getUnits() end)
        pcall(function()                                  -- v0.41.43: the lead's track (first unit that exists), at most 400 points a group
          for _, u0 in ipairs((oku and units) or {}) do
            if u0:isExist() then
              local gn, p0 = g:getName(), u0:getPoint()
              local tr = TRACK[gn] or {}
              TRACK[gn] = tr
              if #tr < 400 then
                local fu, kt = -1, -1                       -- v0.41.71: the lead's fuel (percent of internal) and speed (kts), to see why a flight does not go home
                pcall(function() fu = math.floor(u0:getFuel() * 100) end)
                pcall(function() local v0 = u0:getVelocity(); kt = math.floor(math.sqrt(v0.x ^ 2 + v0.y ^ 2 + v0.z ^ 2) * 1.944) end)
                tr[#tr + 1] = { math.floor(timer.getTime()), math.floor(p0.x), math.floor(p0.z), math.floor(p0.y), fu, kt }
              end
              break
            end
          end
        end)
        for _, u in ipairs((oku and units) or {}) do
          pcall(function()
            local un = u:getName()
            if un and u:isExist() then
              local p, v = u:getPoint(), u:getVelocity()
              local okh, gh = pcall(function() return land.getHeight({ x = p.x, y = p.z }) end)
              SAMPLE[un] = { fuel = u:getFuel(), alt = p.y, spd = math.sqrt(v.x ^ 2 + v.y ^ 2 + v.z ^ 2) * 1.944, t = timer.getTime(), x = p.x, z = p.z, gh = okh and gh or nil }
            end
          end)
        end
      end
    end
  end
  -- v0.41.169 (XO 2026-10-28): the CAS columns' tracks too: the friendly task forces and the red armor columns (lead unit, every 30 s, at most 120 points a group), to see where they stop and pass
  for _, side in ipairs({ coalition.side.BLUE, coalition.side.RED }) do
    pcall(function()
      for _, g in ipairs(coalition.getGroups(side, Group.Category.GROUND) or {}) do
        local gn = g:getName()
        if gn and (string.sub(gn, 1, 18) == "Friendly Task Forc" or string.sub(gn, 1, 6) == "armor_") then
          for _, u0 in ipairs(g:getUnits() or {}) do
            if u0:isExist() then
              local p0 = u0:getPoint()
              local tr = TRACK[gn] or {}
              TRACK[gn] = tr
              if #tr < 120 then
                local kt = -1
                pcall(function() local v0 = u0:getVelocity(); kt = math.floor(math.sqrt(v0.x ^ 2 + v0.y ^ 2 + v0.z ^ 2) * 1.944) end)
                tr[#tr + 1] = { math.floor(timer.getTime()), math.floor(p0.x), math.floor(p0.z), math.floor(p0.y), -1, kt }
              end
              break
            end
          end
        end
      end
    end)
  end
  dump(); return t + 30
end, nil, timer.getTime() + 30)
-- call-outs for the player's flight: scheduled radio calls from the other flights and the support aircraft, plus weapon and result calls
local said = {}
function say(text, you)
  if AITEST then
    trigger.action.outText(text, 8, false)
    local snd0 = (you and SOUND_YOU ~= "") and SOUND_YOU or SOUND
    if snd0 ~= "" then trigger.action.outSound(snd0) end
    return
  end
  local g = Group.getByName(PGROUP)
  if not g then return end
  local id = g:getID()
  trigger.action.outTextForGroup(id, text, 8, false)
  local snd = (you and SOUND_YOU ~= "") and SOUND_YOU or SOUND
  if snd ~= "" then trigger.action.outSoundForGroup(id, snd) end
end
-- v0.41.215 (XO 2026-10-30): AWACS calls need a tuned radio, and the other aircraft call their own damage.
-- TUNEF: user flags that the mission's cockpit-parameter triggers hold at 1 while one of the player's radios is on the AWACS frequency (empty: this jet cannot be read,
-- or the setting is off: always tuned). A call to the player from the AWACS that comes due while he is not tuned is held up to 60 s, with one on-screen note, then dropped.
local TUNEF = { __TUNEF__ }
local TUNEMHZ = "__TUNEMHZ__"
local AWL_UP = string.upper("__AWACS__")
local awnote = false
local function tuned()
  if #TUNEF == 0 then return true end
  for _, f in ipairs(TUNEF) do
    local ok, v = pcall(trigger.misc.getUserFlag, f)
    if ok and tonumber(v) == 1 then return true end
  end
  return false
end
local function isAw(text) return string.upper(string.sub(text or "", 1, #AWL_UP + 3)) == AWL_UP .. " TO" end
local function awHeld()
  if awnote then return end
  awnote = true
  local g = Group.getByName(PGROUP)
  if g then trigger.action.outTextForGroup(g:getID(), "AWACS calls are not reaching you: tune a radio to " .. TUNEMHZ .. " MHz.", 10, false) end
end
function sayAw(text, you)                  -- an AWACS call to the player: gone when the AWACS is down, held while he is not tuned
  if awdown then return true end
  if not tuned() then awHeld(); return false end
  say(text, you); return true
end
function tryCall(i, c, now)
  if said[i] or now < c.t then return end
  if isAw(c.text) then
    if awdown then said[i] = true; return end
    if not tuned() then
      awHeld()
      if now > c.t + 60 then said[i] = true end
      return
    end
  end
  said[i] = true; say(c.text, c.you)
end
local HITL = { "I'm hit.", "I've taken a hit.", "Taking damage.", "I'm hit, checking my systems.", "Hit, I'm hit." }
local DOWNL = { "Mayday, mayday, ejecting.", "Mayday, I'm going down.", "Punching out, punching out.", "I'm hit bad, ejecting.", "Mayday, mayday, mayday, going down." }
local SUPL = { "I'm hit, breaking off.", "Taking damage, leaving the track.", "I'm hit." }
local function pick(t) return t[math.random(#t)] end
local downSaid = {}
dmgCall = function(n, kind)               -- kind "hit" | "down": a blue aircraft calls its own damage, from a short random list ("*" before a label: tanker / AWACS)
  local lab = DMGL[n]
  if not DMG_ON or not lab or n == PLAYER then return end
  local sup = string.sub(lab, 1, 1) == "*"
  if sup then lab = string.sub(lab, 2) end
  if kind == "down" then
    if downSaid[n] then return end
    downSaid[n] = true
    say(lab .. ": " .. pick(DOWNL))
  elseif throttle("dmg:" .. n, 60) then
    say(lab .. ": " .. pick(sup and SUPL or HITL))
  end
end

pcall(function() math.randomseed(math.floor(timer.getAbsTime())) end)
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  for i, c in ipairs(CALLS) do tryCall(i, c, now) end
  return t + 2
end, nil, timer.getTime() + 5)
-- alert log (v0.40.8): when each alert / scramble group was called (its trigger's flag) and when it got airborne; one called and still on
-- the ground 5 minutes later is reported as stuck (a taxi jam)
for _, a in ipairs(ALERTS) do ALOG[a.g] = {} end
if #ALERTS > 0 then
  timer.scheduleFunction(function(_, t)
    for _, a in ipairs(ALERTS) do
      local l = ALOG[a.g]
      if not l.called then
        local v = 0
        pcall(function() v = trigger.misc.getUserFlag(a.f) end)
        if v > 0 then l.called = timer.getTime(); dump() end
      end
    end
    return t + 10
  end, nil, timer.getTime() + 10)
end
-- v0.41.79: CAP replacement. A covered pair (a red patrol, a blue base / carrier / HAVCAP / tanker CAP) is watched: if a jet of it is down, or its air-to-air
-- missiles are all gone (winchester), or a jet is at bingo fuel, the whole pair leaves (its orbit stops on the bf flag: a pair does not stay one jet short,
-- XO: "if one is shot down they bug out") and COVER_DELAY_S later the replacement is called (the rf flag; the nearest field's pair, or a pair that appears
-- behind the station). Nothing is called when the sortie is nearly over anyway (COVER_MIN_LEFT_S).
local COVER_DELAY_S = 150           -- the short delay between the pair leaving and the replacement being called (judgment call)
local COVER_MIN_LEFT_S = 600
local BINGO_FUEL = 0.20             -- fraction of internal fuel left (judgment call; DCS's own bingo is type-dependent)
local function aamCount(u)
  local n = 0
  pcall(function()
    for _, a in ipairs(u:getAmmo() or {}) do
      local d = a.desc or {}
      if d.category == 1 and d.missileCategory == 1 then n = n + (a.count or 0) end
    end
  end)
  return n
end
if #COVER > 0 then
  timer.scheduleFunction(function(_, t)
    local now, left = timer.getTime(), false
    for _, c in ipairs(COVER) do
      if not c.done then
        left = true
        local l = COVERLOG[c.g]
        if not l and now > c.u - COVER_MIN_LEFT_S then
          c.done = true                                  -- the sortie is nearly over: a pair that lands now is not a loss
        elseif not l then
          local g = Group.getByName(c.g)
          if g then
            local alive, why, aam = 0, nil, 0
            for _, u in ipairs(g:getUnits() or {}) do
              local ok, ex = pcall(function() return u:isExist() and u:getLife() > 0 end)
              if ok and ex then
                alive = alive + 1
                aam = aam + aamCount(u)
                local okf, fu = pcall(function() return u:getFuel() end)
                if okf and fu and fu < BINGO_FUEL and not why then why = "bingo" end
              end
            end
            if alive < c.n and not why then why = "lost" end
            if c.armed and alive > 0 and aam == 0 and not why then why = "winchester" end
            if aam > 0 then c.armed = true end
            if why and now > 120 then
              COVERLOG[c.g] = { why = why, t = math.floor(now), replaced = false }
              pcall(function() trigger.action.setUserFlag(c.bf, true) end)
              dump()
            end
          end
        else
          if not l.replaced and now - l.t >= COVER_DELAY_S then
            if c.rf > 0 and now <= c.u - COVER_MIN_LEFT_S then
              pcall(function() trigger.action.setUserFlag(c.rf, true) end)
              l.replaced = true
              dump()
            else
              c.done = true
            end
          end
          if l.replaced then c.done = true end
        end
      end
    end
    if left then return t + 10 end
    return nil
  end, nil, timer.getTime() + 20)
end
-- the runway queue (v0.40.7): alert groups at a field with no parking for their type wait hidden; when one is called (its trigger sets its
-- flag) it is put on the runway, at least RWY_STAGGER_S after the last group that went from there, and at your own field only once you
-- have left the runway (or 15 minutes in)
local RWYQ = { __RWYQ__ }
local PRWY = "__PRWY__"
local RWY_STAGGER_S = 60
local PHOME = __PHOME__             -- v0.41.97: your own field (nil off a carrier): a hot release there waits while you are on your way in to land
local HOME_NM = 10
local function playerInbound()
  if not PHOME or not pl.takeoff or pl.landed or dead[PLAYER] then return false end
  local inb = false
  pcall(function()
    local u = Unit.getByName(PLAYER)
    if not u or not u:isExist() then return end
    local p = u:getPoint()
    local d = math.sqrt((p.x - PHOME.x) ^ 2 + (p.z - PHOME.z) ^ 2)
    local agl = p.y - land.getHeight({ x = p.x, y = p.z })
    inb = d < HOME_NM * 1852 and agl < 1500 and (timer.getTime() - pl.takeoff) > 300
  end)
  return inb
end
local ALERT_TAXI_S = 120          -- v0.41.0: an alert pair appears on the runway this long after it is called (the taxi it no longer does)
local rwyLast = {}
if #RWYQ > 0 then
  timer.scheduleFunction(function(_, t)
    local now = timer.getTime()
    local pend = 0
    for _, q in ipairs(RWYQ) do
      if not q.done then
        pend = pend + 1
        local want = false
        if q.t then
          want = now >= q.t                      -- v0.41.96: a scheduled package flight, released at its time (no taxi delay)
        else
          pcall(function() want = trigger.misc.getUserFlag(q.f) > 0 end)
          if want and not q.wt then q.wt = now end
          want = want and q.wt and (now - q.wt >= ALERT_TAXI_S)
        end
        local free = (not rwyLast[q.b]) or (now - rwyLast[q.b] >= RWY_STAGGER_S)
        if q.b == PRWY and not (pl.takeoff or dead[PLAYER] or now > 900) then free = false end
        if q.t and q.b == PRWY and playerInbound() then free = false end
        if want and free then
          pcall(function() local g = Group.getByName(q.g); if g then g:activate() end end)
          rwyLast[q.b] = now; q.done = true
        end
      end
    end
    if pend == 0 then return nil end
    return t + 5
  end, nil, timer.getTime() + 5)
end
-- all packages complete: once the last TOT has passed and every AI package flight is landed, down or gone, AWACS says so, and repeats it
-- every 5 minutes (you may have stepped away). It never ends the mission: an End Mission trigger would throw you out while still flying.
local WATCH = { __WATCH__ }
local DONE_AFTER = __DONEAFTER__
local AWACS_LBL = "__AWACS__"
local function flightDone(name)
  local g = Group.getByName(name)
  if not g then return true end
  local ok, units = pcall(function() return g:getUnits() end)
  if not ok or not units or #units == 0 then return true end
  for _, u in ipairs(units) do
    local live = false
    pcall(function() live = u:isExist() and u:isActive() and u:inAir() end)
    if live then return false end
    local pending = false
    pcall(function() pending = u:isExist() and not u:isActive() end)       -- late-activated, not launched yet
    if pending then return false end
  end
  return true
end
timer.scheduleFunction(function(_, t)
  if timer.getTime() < DONE_AFTER + 120 then return t + 30 end
  for _, n in ipairs(WATCH) do
    if not flightDone(n) then return t + 30 end
  end
  local you = string.upper(PGROUP)
  if pl.landed then
    sayAw(AWACS_LBL .. " to " .. you .. ": all flights accounted for. Good work today. " .. AWACS_LBL .. " out.", true)
  else
    sayAw(AWACS_LBL .. " to " .. you .. ": all packages complete, no further tasking today. Return to base.", true)
  end
  return t + 300
end, nil, timer.getTime() + 60)
-- ruins of what earlier packages already hit: a few fires and smoke plumes (kept few for VR performance)
do
  local nid = 0
  timer.scheduleFunction(function()
    for _, r in ipairs(RUINS) do
      for i = 1, r.n do
        local a = r.s + (i - 1) * 2.1
        local d = (i == 1) and 0 or r.r
        local x, z = r.x + math.cos(a) * d, r.z + math.sin(a) * d
        local y = 0
        pcall(function() y = land.getHeight({x = x, y = z}) end)
        local v = {x = x, y = y, z = z}
        if r.pw > 0 then pcall(function() trigger.action.explosion(v, r.pw) end) end      -- v0.41.19: none at an airfield (pw 0)
        nid = nid + 1
        pcall(function() trigger.action.effectSmokeBig(v, r.p, r.dn, "sqe_ruin_" .. nid) end)
      end
    end
    return nil
  end, nil, timer.getTime() + 4)
end
-- DEAD gate: before the DEAD flight commits, the target site's radars are checked. Any still alive: the DEAD flight turns back
-- (the AI skips to its egress / return point; a human gets the call) and so do the escorts and sweeps of that package. The check fires
-- when the DEAD flight's lead is within GATE_M of the site (so a late flight is judged where it really is), or at the clock time as a
-- fallback (flight gone). Every gate is logged in the state file: when it ran, why, radars left, whether the command went through, and
-- the flight's distance to the target then and 60 s later.
local GATE_M = __GATEKM__ * 1000
local function gdist(grpName, tp)
  if not tp then return nil end
  local ok, d = pcall(function()
    local g = Group.getByName(grpName)
    local u = g and g:getUnit(1)
    if not u then return nil end
    local a = u:getPoint()
    return math.sqrt((a.x - tp.x) ^ 2 + (a.z - tp.z) ^ 2)
  end)
  if ok then return d end
  return nil
end
local gsites, gorder = {}, {}
for _, gt in ipairs(GATES) do
  local gs = gsites[gt.site]
  if not gs then gs = { site = gt.site, gates = {}, fall = 0, done = false }; gsites[gt.site] = gs; gorder[#gorder + 1] = gs end
  gs.gates[#gs.gates + 1] = gt
  if gt.t + 300 > gs.fall then gs.fall = gt.t + 300 end
end
local function sitePoint(s)
  if not s then return nil end
  for _, un in ipairs(s.units) do
    local u = Unit.getByName(un)
    if u then local ok, p = pcall(function() return u:getPoint() end); if ok and p then return p end end
  end
end
local HOLD_S = 720           -- an AI DEAD flight whose radars are still up holds this long (12 min) before it breaks off
local HOLD_CHECK_S = 30      -- and re-checks the radars (and, v0.41.203, the air) this often while it holds
local HOLD_FUEL = 0.30       -- below this fuel fraction the holding flight breaks off at once: it must have fuel for the strike and the way home
-- v0.41.203: the fighters-clear gate. The same gate that waits for a site's radars also waits for red fighters: a striker (or CAS flight) does not push
-- into a live air fight (XO's 2026-10-30 runs: the strike flights dropped their loads or bugged out under P-27 / P-33 shots). Red fighters in the air
-- within AIR_LEAD_M of the flight's lead or AIR_TGT_M of the target hold it outside the fight, for at most the gate's acap seconds, then it goes in.
local AIR_LEAD_M = 100000     -- judgment calls (the MiG-31's P-33 reaches about 120 km, the Su-27 / MiG-29's P-27 about 50 km at altitude)
local AIR_TGT_M = 60000
local function redFighterNear(p, r)
  if not p then return false end
  local found = false
  pcall(function()
    for _, g in ipairs(coalition.getGroups(coalition.side.RED, Group.Category.AIRPLANE) or {}) do
      for _, u in ipairs(g:getUnits() or {}) do
        if u:isExist() and u:inAir() and (u:hasAttribute("Fighters") or u:hasAttribute("Interceptors") or u:hasAttribute("Multirole fighters")) then
          local a = u:getPoint()
          if math.sqrt((a.x - p.x) ^ 2 + (a.z - p.z) ^ 2) <= r then found = true; return end
        end
      end
    end
  end)
  return found
end
local function leadPoint(grpName)
  local ok, p = pcall(function() local g = Group.getByName(grpName); local u = g and g:getUnit(1); return u and u:getPoint() end)
  if ok then return p end
end
local function airUp(gs)
  if redFighterNear(gs.tp, AIR_TGT_M) then return true end
  for _, gt in ipairs(gs.gates) do
    if gt.dead and redFighterNear(leadPoint(gt.grp), AIR_LEAD_M) then return true end
  end
  return false
end
local function whoOf(s) return (s and s.who) or "Strike" end
local function labelOf(s, gs) return (s and s.label) or gs.site end
local function airCap(gs)
  for _, gt in ipairs(gs.gates) do if gt.dead and (gt.acap or 0) > 0 then return gt.acap end end
  return 240
end
-- every SEAD flight of this site is down or gone (no airborne unit left): the blinding has failed and there is no reason to go in.
-- Only counts when the mission has SEAD flights on the site at all; an error reading a group counts it as still flying.
local function seadsGone(gs)
  local names, any = {}, false
  for _, gt in ipairs(gs.gates) do
    for _, n in ipairs(gt.seads or {}) do names[#names + 1] = n; any = true end
  end
  if not any then return false end
  for _, n in ipairs(names) do
    -- a late-activated SEAD flight that has not launched yet still exists (inactive): it is coming, not gone
    local ok, alive = pcall(function()
      local g = Group.getByName(n)
      if g == nil then return false end
      if g:getSize() > 0 then return true end
      local u = g:getUnit(1)
      return u ~= nil and not u:isActive()
    end)
    if not ok or alive then return false end
  end
  return true
end
-- a site is blind when its radars are all down (a Tor's radar rides on the launcher, so its vehicles count). The DEAD gate waits for the
-- target AND the Tors that cover it or the run in (gt.also): the same package is tasked against them.
local function siteBlind(id)
  for _, x in ipairs(SITES) do if x.id == id then return x.nrad <= 0 or x.nalive <= 0 end end
  return true
end
local function gateBlind(gs)
  return siteBlind(gs.site)      -- the target's own radars only: a Tor still up on the run-in no longer holds the strike (v0.39.22); the go call names it
end
local function torsUp(gs)
  for _, gt in ipairs(gs.gates) do
    for _, a in ipairs(gt.also or {}) do if not siteBlind(a) then return true end end
  end
  return false
end
local function siteOf(gs)
  for _, x in ipairs(SITES) do if x.id == gs.site then return x end end
end
local function breakOff(gs, why)
  local held = gs.holding
  gs.done = true
  gs.holding = false
  local s = siteOf(gs)
  if not aborted[gs.site] then
    aborted[gs.site] = true
    if why == "air-abort" then say(whoOf(s) .. ": abort, abort. " .. labelOf(s, gs) .. ", red fighters still up, flight break off.", gs.gates[1].you)
    else say(whoOf(s) .. ": abort, abort. " .. labelOf(s, gs) .. " radars still up, DEAD flight break off.", gs.gates[1].you) end
  end
  for _, gt in ipairs(gs.gates) do
    if gt.dead then
      local why_txt = ({ ["hold-timeout"] = "hold time is up", ["hold-fuel"] = "fuel is low", ["seads-gone"] = "the SEAD flights are down or gone", ["air-abort"] = "red fighters still in the air" })[why] or ("not blind in time (" .. why .. ")")
      say(whoOf(s) .. ": abort, RTB. " .. labelOf(s, gs) .. " " .. why_txt .. ".", gt.you)
    end
  end
  for _, gt in ipairs(gs.gates) do
    local e = { site = gt.site, grp = gt.grp, t = math.floor(gt.t), ran = math.floor(timer.getTime()), radars = s and s.nrad or -1, abort = true, cmd = false, by = why }
    gateLog[#gateLog + 1] = e
    e.tp = gs.tp
    e.d0 = gdist(gt.grp, e.tp)
    if gt.ai then
      local g = Group.getByName(gt.grp)
      if g and g:getController() then
        e.cmd = pcall(function()
          local c = g:getController()
          if held then c:resetTask() end        -- the hold pushed an orbit on top of the route: clear it, or the flight keeps circling (v0.39.21 run, Springfield 1)
          c:setCommand({ id = "SwitchWaypoint", params = { fromWaypointIndex = gt.from, goToWaypointIndex = gt.to } })
        end)
      end
      timer.scheduleFunction(function() e.d1 = gdist(gt.grp, e.tp); dump(); return nil end, nil, timer.getTime() + 60)
    end
  end
  dump()
end
local function resume(gs, how)
  gs.done = true
  gs.holding = false
  local s = siteOf(gs)
  how = how or "hold-resumed"
  for _, gt in ipairs(gs.gates) do
    local e = { site = gt.site, grp = gt.grp, t = math.floor(gt.t), ran = math.floor(timer.getTime()), radars = s and s.nrad or -1, abort = false, cmd = false, by = how, held = math.floor(timer.getTime() - gs.holdAt) }
    gateLog[#gateLog + 1] = e
    if gt.ai then
      local g = Group.getByName(gt.grp)
      if g and g:getController() then
        e.cmd = pcall(function()
          local c = g:getController()
          c:resetTask()
          c:setCommand({ id = "SwitchWaypoint", params = { fromWaypointIndex = gt.from, goToWaypointIndex = gt.from } })
        end)
      end
    end
  end
  for _, gt in ipairs(gs.gates) do
    if gt.dead then
      if gs.holdWhy == "air" then say(whoOf(s) .. ": " .. labelOf(s, gs) .. ", the air is clear. Go, go, go.", gt.you)
      else say(whoOf(s) .. ": " .. labelOf(s, gs) .. " radars are down. Go, go, go." .. (torsUp(gs) and " A Tor is still up on the run-in, watch it." or ""), gt.you) end
    end
  end
  dump()
end
local function holdGroups(gs)
  gs.holding = true
  gs.holdAt = timer.getTime()
  local s = siteOf(gs)
  gs.holdWhy = gateBlind(gs) and "air" or "radars"
  for _, gt in ipairs(gs.gates) do
    if gt.dead then
      if gs.holdWhy == "air" then say(whoOf(s) .. ": " .. labelOf(s, gs) .. ", red fighters still up ahead. Hold outside, rechecking.", gt.you)
      else say(whoOf(s) .. ": " .. labelOf(s, gs) .. " radars still up. Hold outside, rechecking.", gt.you) end
    end
  end
  for _, gt in ipairs(gs.gates) do
    if gt.ai and gt.dead then
      local g = Group.getByName(gt.grp)
      local ok, c = pcall(function() return g and g:getController() end)
      if g and ok and c then
        local okp, p = pcall(function() return g:getUnit(1):getPoint() end)
        if okp and p then
          pcall(function() c:pushTask({ id = "Orbit", params = { pattern = "Circle", point = { x = p.x, y = p.z }, radius = 6000, altitude = p.y, speed = 230 } }) end)
        end
      end
    end
  end
  dump()
end
local function holdFuelLow(gs)
  for _, gt in ipairs(gs.gates) do
    if gt.dead then
      local g = Group.getByName(gt.grp)
      local okf, f = pcall(function() return g:getUnit(1):getFuel() end)
      if okf and f and f < HOLD_FUEL then return true end
    end
  end
  return false
end
local function holdCheck(gs, t)
  if not gs.holding then return nil end
  local s = siteOf(gs)
  local blind = gateBlind(gs)
  if blind then
    if not airUp(gs) then resume(gs); return nil end
    -- the radars are down but red fighters are still about: wait for the air to clear, for at most the gate's cap; v0.41.205: then the flight goes home
    -- (no banzai: XO's 2026-10-30 runs lost the CAS flights pushing in under a full red air picture after the old "go in anyway")
    if timer.getTime() - gs.holdAt >= airCap(gs) or holdFuelLow(gs) then breakOff(gs, "air-abort"); return nil end
    return t + HOLD_CHECK_S
  end
  if timer.getTime() - gs.holdAt >= HOLD_S then breakOff(gs, "hold-timeout"); return nil end
  if seadsGone(gs) then breakOff(gs, "seads-gone"); return nil end
  if holdFuelLow(gs) then breakOff(gs, "hold-fuel"); return nil end
  return t + HOLD_CHECK_S
end
local function decide(gs, why)
  local s = siteOf(gs)
  local blind = gateBlind(gs)
  if not blind then
    local canHold = false
    for _, gt in ipairs(gs.gates) do if gt.dead then canHold = true end end
    if canHold and seadsGone(gs) then breakOff(gs, "seads-gone"); return end
    if canHold and why ~= "hold-timeout" and why ~= "hold-fuel" then
      if not gs.tp then gs.tp = sitePoint(s) end
      holdGroups(gs)
      timer.scheduleFunction(holdCheck, gs, timer.getTime() + HOLD_CHECK_S)
      return
    end
    breakOff(gs, why)
    return
  end
  local canHold2 = false
  for _, gt in ipairs(gs.gates) do if gt.dead then canHold2 = true end end
  if canHold2 and why ~= "hold-timeout" and why ~= "hold-fuel" and why ~= "clock" and airUp(gs) and not holdFuelLow(gs) then
    if not gs.tp then gs.tp = sitePoint(s) end
    holdGroups(gs)
    timer.scheduleFunction(holdCheck, gs, timer.getTime() + HOLD_CHECK_S)
    return
  end
  gs.done = true
  for _, gt in ipairs(gs.gates) do
    local e = { site = gt.site, grp = gt.grp, t = math.floor(gt.t), ran = math.floor(timer.getTime()), radars = s and s.nrad or -1, abort = false, cmd = false, by = why }
    gateLog[#gateLog + 1] = e
    e.tp = gs.tp
    e.d0 = gdist(gt.grp, e.tp)
  end
  if why == "dist" and not gs.rewatched then gs.watch = true end        -- v0.41.205: it keeps looking at the air until the flight commits (WATCH_COMMIT_M from the target)
  dump()
end
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  for i, c in ipairs(CALLS) do tryCall(i, c, now) end
  return t + 2
end, nil, timer.getTime() + 5)
-- ruins of what earlier packages already hit: a few fires and smoke plumes (kept few for VR performance)
do
  local nid = 0
  timer.scheduleFunction(function()
    for _, r in ipairs(RUINS) do
      for i = 1, r.n do
        local a = r.s + (i - 1) * 2.1
        local d = (i == 1) and 0 or r.r
        local x, z = r.x + math.cos(a) * d, r.z + math.sin(a) * d
        local y = 0
        pcall(function() y = land.getHeight({x = x, y = z}) end)
        local v = {x = x, y = y, z = z}
        if r.pw > 0 then pcall(function() trigger.action.explosion(v, r.pw) end) end      -- v0.41.19: none at an airfield (pw 0)
        nid = nid + 1
        pcall(function() trigger.action.effectSmokeBig(v, r.p, r.dn, "sqe_ruin_" .. nid) end)
      end
    end
    return nil
  end, nil, timer.getTime() + 4)
end
-- DEAD gate: before the DEAD flight commits, the target site's radars are checked. Any still alive: the DEAD flight turns back
-- (the AI skips to its egress / return point; a human gets the call) and so do the escorts and sweeps of that package. The check fires
-- when the DEAD flight's lead is within GATE_M of the site (so a late flight is judged where it really is), or at the clock time as a
-- fallback (flight gone). Every gate is logged in the state file: when it ran, why, radars left, whether the command went through, and
-- the flight's distance to the target then and 60 s later.
local ARM_S = 240            -- v0.41.205: the distance trigger waits until the lead is in the air and this close to the gate's clock time (a target near the base put
                             -- the lead inside the gate radius on the ramp, and the one-shot air check ran at 5 s with no red fighter up yet: XO's 2026-10-30 15:38 run)
local WATCH_COMMIT_M = 25000 -- after a clean check the flight is watched until it is this close to the target; red fighters that come up meanwhile hold it once
local function leadAirborne(grpName)
  local ok, r = pcall(function() local g = Group.getByName(grpName); local u = g and g:getUnit(1); return u and u:inAir() end)
  return ok and r or false
end
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  local left = false
  for _, gs in ipairs(gorder) do
    if gs.done and gs.watch and not gs.holding then
      left = true
      local close = false
      for _, gt in ipairs(gs.gates) do
        if gt.dead then local d = gdist(gt.grp, gs.tp); if (not d) or d <= WATCH_COMMIT_M then close = true end end
      end
      if close or now >= gs.fall + 600 then gs.watch = false
      elseif airUp(gs) and not holdFuelLow(gs) then
        gs.watch = false; gs.rewatched = true; gs.done = false
        holdGroups(gs)
        timer.scheduleFunction(holdCheck, gs, now + HOLD_CHECK_S)
      end
    end
    if not gs.done and not gs.holding then
      left = true
      local s
      for _, x in ipairs(SITES) do if x.id == gs.site then s = x end end
      if s and not gs.tp then gs.tp = sitePoint(s) end
      if not gs.tp and gs.gates[1].tx then gs.tp = { x = gs.gates[1].tx, z = gs.gates[1].tz } end          -- v0.41.203: a target with no live unit to read a position from
      if now >= gs.fall then
        decide(gs, "clock")
      else
        for _, gt in ipairs(gs.gates) do
          if gt.dead then
            -- the gate (and so any hold) is outside the reach of the target's own radars (gt.gm: 60 km for an SA-10) and of an SA-10
            -- umbrella covering it (gt.ux/uz/um): v0.39.21 run, Hornet 1 held 26 km from the Sukhumi SA-10 and was shot down in its orbit
            local d = gdist(gt.grp, gs.tp)
            local du = gt.ux and gdist(gt.grp, { x = gt.ux, z = gt.uz }) or nil
            local armed = leadAirborne(gt.grp) and now >= gt.t - ARM_S
            if (armed and d and d <= ((gt.gm and gt.gm > 0) and gt.gm or GATE_M)) or (du and du <= gt.um) then decide(gs, "dist"); break end
          end
        end
      end
    end
  end
  if left then return t + 5 end
  return nil
end, nil, timer.getTime() + 5)
-- v0.41.17: carrier recovery without the deck queue. An AI flight going home to the boat runs SQE_RECOVER at its recovery point 10 nm out:
-- every jet still flying counts as landed (debrief and war sim) and the group leaves the mission. Your own wingmen do the same once you
-- are both within CVREC.r of the boat after CVREC.t (you trap alone; DCS's carrier ATC queue is the problem, not the AI).
local CVREC = { __CVREC__ }
function SQE_RECOVER(gname)
  local g = Group.getByName(gname)
  if not g then return end
  for _, u in ipairs(g:getUnits() or {}) do
    local okn, un = pcall(function() return u:getName() end)
    if okn and un and not dead[un] then landed[un] = true end
  end
  dump()
  pcall(function() g:destroy() end)
end
-- v0.41.25: the recovery net. A flight sent home early (bingo, winchester) flies straight to its deck or field and never reaches its recovery
-- point: once its lead is within r of the carrier (where the boat is now) or the field, after its work is done, it is recovered all the same.
local RECOV = { __RECOV__ }
if #RECOV > 0 then
  timer.scheduleFunction(function(_, t)
    local left = false
    for _, r in ipairs(RECOV) do
      if not r.done then
        local g = Group.getByName(r.g)
        if not g then r.done = true
        else
          left = true
          if t >= r.t then
            local cp = { x = r.x, z = r.z }
            if r.cv ~= "" then
              local cv = Unit.getByName(r.cv)
              if cv then cp = cv:getPoint() end
            end
            -- any jet of the group, not only the lead (getUnit(1) is nil once the lead is gone)
            local near = false
            for _, u in ipairs(g:getUnits() or {}) do
              local okp, up = pcall(function() return u:getPoint() end)
              if okp and up and math.sqrt((up.x - cp.x) ^ 2 + (up.z - cp.z) ^ 2) <= r.r then near = true end
            end
            if near then                              -- v0.41.72: near the boat for r.dwell seconds (the pattern laps), then it counts as landed
              r.since = r.since or t
            else
              r.since = nil
            end
            if (near and t - r.since >= (r.dwell or 0)) or (r.t2 and t >= r.t2) then      -- v0.41.71: or still out STALE_S after its work was done
              r.done = true
              SQE_RECOVER(r.g)
            end
          end
        end
      end
    end
    if left then return t + 15 end
    return nil
  end, nil, timer.getTime() + 15)
end
if (CVREC.cv or CVREC.x) and not AITEST then
  timer.scheduleFunction(function(_, t)
    if t < (CVREC.t or 0) then return t + 10 end
    local cv = CVREC.cv and Unit.getByName(CVREC.cv)
    local me, g = Unit.getByName(PLAYER), Group.getByName(PGROUP)
    if not (me and g) or (CVREC.cv and not cv) then return t + 10 end
    local cp, mp = (cv and cv:getPoint()) or { x = CVREC.x, z = CVREC.z }, me:getPoint()
    local near = function(p) return math.sqrt((p.x - cp.x) ^ 2 + (p.z - cp.z) ^ 2) <= CVREC.r end
    if not near(mp) then return t + 10 end
    local left = false
    for _, u in ipairs(g:getUnits() or {}) do
      local okn, un = pcall(function() return u:getName() end)
      if okn and un and un ~= PLAYER and not dead[un] then
        if near(u:getPoint()) then landed[un] = true; dump(); pcall(function() u:destroy() end) else left = true end
      end
    end
    if left then return t + 10 end
    return nil
  end, nil, timer.getTime() + 10)
end
-- v0.41.223 (XO 2026-10-31): PACKAGE SCRUB. The package's AI flights go home together once the package can no longer do its job. Two triggers, one rule: a side of the
-- package (the strikers / CAS, or the covering fighters) that has lost SCRUB_FRAC of its jets. The strikers lost, before TOT + SCRUB_GRACE: nobody is left to protect or
-- suppress for, so the escorts, TARCAPs and SEAD go home (XO's 2026-10-31 run: the 2-ship striker lost its leader and DCS sent it home, the escorts went on to their
-- stations). The cover lost, before TOT - SCRUB_LEAD: the strikers have no one to hold the air for them, so they go home (the Gudauta CAS run of 2026-10-30).
-- The AWACS calls ABORT to the player when his own package is scrubbed. The player's own flight is never commanded. Each scrubbed AI flight is sent to its SCRUB
-- point (20 nm out from home, high enough to clear the ground) with SwitchWaypoint, after resetTask (a flight on a station or in a hold keeps circling otherwise).
local SCRUB = { __SCRUB__ }
local SCRUB_FRAC, SCRUB_GRACE, SCRUB_LEAD = __SCRUBFRAC__, __SCRUBGRACE__, __SCRUBLEAD__
local scrubbedPkg, scrubbedGrp = {}, {}
local function scrubCount(pkg, kind)
  local init, alive = 0, 0
  for _, f in ipairs(SCRUB) do
    if f.pkg == pkg and f.k == kind then
      for _, n in ipairs(f.units) do
        init = init + 1
        if not dead[n] and not ejected[n] then alive = alive + 1 end
      end
    end
  end
  return init, alive
end
local function scrubSay(text)                 -- the AWACS call to the player: retried for a minute if he is not tuned (sayAw drops it otherwise)
  if sayAw(text, true) then return end
  local tries = 0
  timer.scheduleFunction(function(_, t)
    tries = tries + 1
    if sayAw(text, true) or tries >= 12 then return nil end
    return t + 5
  end, nil, timer.getTime() + 5)
end
local function scrubGo(pkg, why, text)
  scrubbedPkg[pkg] = true
  local n, you = 0, false
  for _, f in ipairs(SCRUB) do
    if f.pkg == pkg then
      if f.you then you = true end
      if f.ai and f.to > 0 then
        scrubbedGrp[f.g] = true
        local ok = pcall(function()
          local g = Group.getByName(f.g)
          local c = g and g:getController()
          if not c then error("no group") end
          c:resetTask()
          c:setCommand({ id = "SwitchWaypoint", params = { fromWaypointIndex = 1, goToWaypointIndex = f.to } })
        end)
        if ok then n = n + 1 end
      end
    end
  end
  for _, gs in ipairs(gorder) do             -- a gate that watches only scrubbed flights is retired: its hold must not resume them toward the target
    local all = #gs.gates > 0
    for _, gt in ipairs(gs.gates) do if not scrubbedGrp[gt.grp] then all = false end end
    if all then gs.done = true; gs.holding = false; gs.watch = false end
  end
  scrubLog[#scrubLog + 1] = { pkg = pkg, t = math.floor(timer.getTime()), why = why, n = n }
  if you then scrubSay(string.upper(AWACS_LBL) .. " to " .. string.upper(PGROUP) .. ": ABORT, ABORT. " .. text .. ". Package, return to base.") end
  dump()
end
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  local tots = {}
  for _, f in ipairs(SCRUB) do tots[f.pkg] = f.tot end
  for pkg, tot in pairs(tots) do
    if not scrubbedPkg[pkg] then
      local mi, ma = scrubCount(pkg, "M")
      local ci, ca = scrubCount(pkg, "C")
      if mi > 0 and ma <= mi * SCRUB_FRAC and now < tot + SCRUB_GRACE then
        scrubGo(pkg, "strike", "Strike flight is down, mission cannot be completed")
      elseif ci > 0 and ca <= ci * SCRUB_FRAC and now < tot - SCRUB_LEAD then
        scrubGo(pkg, "cover", "Escort is down, package cannot go in")
      end
    end
  end
  return t + 5
end, nil, timer.getTime() + 30)
dump()
'''
SCRUB_LOSS_FRAC = 0.5          # v0.41.223: a side of a package (strikers, or the covering fighters) that has lost this share of its jets scrubs the package (judgment call: XO's run, a 2-ship that lost one went home; the Gudauta CAS escort was down to two of four)
SCRUB_STRIKE_GRACE_S = 180     # ...the strikers lost: scrub until this long after TOT (after that the strike is done or moot)
SCRUB_COVER_LEAD_S = 90        # ...the cover lost: scrub only until this long before TOT (strikers that have committed finish the job)
BINGO_PCT = 20            # v0.41.92: the hook's bingo for pairs (BINGO_FUEL in the Lua below); the debrief fuel lines use it
BINGO_REPORT_PCT = 35      # ...and report a flight that ended the mission at or under this much fuel


def _jamcfg() -> str:
    from . import ecm
    return (f"local JC = {{ p1={ecm.P_SELF[1]}, p2={ecm.P_SELF[2]}, cover={ecm.P_COVER}, coverM={ecm.COVER_NM * 1852:.0f}, "
            f"burn={ecm.BURN_KM * 1000:.0f}, full={ecm.FULL_KM * 1000:.0f} }}")


def _lua_str(s: str) -> str:
    return str(s).replace("\\", "/").replace('"', "'")


def _lq(s) -> str:
    return '"' + _lua_str(s).replace("\n", " ") + '"'


def _umbrella_lua(x: dict) -> str:
    """The gate's umbrella fields for the hook (the SA-10 covering its target), or nothing."""
    if x.get("ux") is None:
        return ""
    return ", ux=%.1f, uz=%.1f, um=%d" % (float(x["ux"]), float(x["uz"]), int(x["um"]))


def lua_hook(campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "", group: str = "",
             calls: list | None = None, wps: list | None = None, sound: str = "", sound_you: str = "", flights: dict | None = None,
             enemy_air: list | None = None, sites: list | None = None, ruins: list | None = None, gates: list | None = None, ai_test: bool = False, gate_km: float = 40, jams: dict | None = None, jamw: dict | None = None,
             watch: list | None = None, done_after: float = 0, awacs: str = "AWACS", splash: bool = False,
             rwyq: list | None = None, prwy: str = "", alerts: list | None = None, cfg: dict | None = None, cover: list | None = None, ecm_player: str = "", ecm_msg: bool = True,
             tune_flags: list | None = None, tune_mhz: float = 0.0, awacs_unit: str = "", dmg: dict | None = None, dmg_on: bool = False, scrub: list | None = None) -> str:
    tbl = ", ".join(f'["{n}"]=true' for n in despawn_names)
    cl = ", ".join(f'{{t={float(c[0]):.0f}, text="{_lua_str(c[1])}", you={"true" if (len(c) > 2 and c[2]) else "false"}}}' for c in (calls or []))
    uf = ", ".join(f"[{_lq(k)}]={_lq(v)}" for k, v in (flights or {}).items())
    ea = ", ".join(f"[{_lq(n)}]=true" for n in (enemy_air or []))
    lst = lambda xs: "{" + ", ".join(_lq(x) for x in xs) + "}"
    sc = ", ".join(f'{{pkg={_lq(x["pkg"])}, g={_lq(x["grp"])}, k={_lq(x["k"])}, units={lst(x["units"])}, to={int(x["to"])}, ai={"true" if x["ai"] else "false"}, '
                    f'you={"true" if x["you"] else "false"}, tot={float(x["tot"]):.0f}}}' for x in (scrub or []))
    st = ", ".join(f'{{id={_lq(x["id"])}, label={_lq(x["label"])}, who={_lq(x["who"])}, prim={"true" if x["prim"] else "false"}, '
                   f'units={lst(x["units"])}, trk={lst(x["trk"])}, srch={lst(x["srch"])}}}' for x in (sites or []))
    ru = ", ".join(f'{{x={r["x"]:.1f}, z={r["z"]:.1f}, n={int(r["n"])}, r={float(r["r"]):.0f}, p={int(r["p"])}, dn={float(r["dn"]):.2f}, pw={int(r["pw"])}, s={float(r["s"]):.2f}}}'
                   for r in (ruins or []))
    gt = ", ".join(f'{{t={float(x["t"]):.0f}, site={_lq(x["site"])}, grp={_lq(x["grp"])}, from={int(x["from"])}, to={int(x["to"])}, ai={"true" if x["ai"] else "false"}, dead={"true" if x.get("dead") else "false"}, you={"true" if x.get("you") else "false"}, seads={{{", ".join(_lq(n) for n in x.get("seads", []))}}}, also={{{", ".join(_lq(n) for n in x.get("also", []))}}}, gm={int(x.get("gm") or 0)}, acap={int(x.get("acap") or 0)}{_umbrella_lua(x)}{(", tx=%.1f, tz=%.1f" % (float(x["tx"]), float(x["tz"]))) if x.get("tx") is not None else ""}}}'
                   for x in (gates or []))
    return (LUA_HOOK.replace("__SCRUB__", sc).replace("__SCRUBFRAC__", repr(float(SCRUB_LOSS_FRAC))).replace("__SCRUBGRACE__", f"{float(SCRUB_STRIKE_GRACE_S):.0f}").replace("__SCRUBLEAD__", f"{float(SCRUB_COVER_LEAD_S):.0f}")
            .replace("__GATEKM__", str(int(gate_km))).replace("__AITEST__", "true" if ai_test else "false").replace("__GATES__", gt).replace("__RUINS__", ru).replace("__CAMPAIGN__", campaign_id).replace("__SORTIE__", str(sortie))
            .replace("__PKG__", package_id).replace("__DESPAWN__", tbl).replace("__PLAYER__", player_name)
            .replace("__PGROUP__", _lua_str(group)).replace("__SOUND__", sound).replace("__SOUND_YOU__", sound_you).replace("__CALLS__", cl).replace("__UFLT__", uf)
            .replace("__ENEMYAIR__", ea).replace("__SITES__", st).replace("__JAMCFG__", _jamcfg()).replace("__ECMP__", ecm_player if ecm_player in ("live", "f10") else "").replace("__ECMMSG__", "1" if ecm_msg else "0")
            .replace("__TUNEF__", ", ".join(str(int(f)) for f in (tune_flags or []))).replace("__TUNEMHZ__", f"{float(tune_mhz):.3f}").replace("__AWUNIT__", _lua_str(awacs_unit))
            .replace("__DMGL__", ", ".join(f"[{_lq(k)}]={_lq(v)}" for k, v in (dmg or {}).items())).replace("__DMGON__", "true" if dmg_on else "false").replace("__JAMS__", ", ".join(f"[{_lq(k)}]={int(v)}" for k, v in (jams or {}).items()))
            .replace("__JAMW__", ", ".join(f"[{_lq(k)}]={{{float(a):.0f}, {float(b):.0f}}}" for k, (a, b) in (jamw or {}).items()))
            .replace("__WATCH__", ", ".join(_lq(n) for n in (watch or []))).replace("__DONEAFTER__", f"{float(done_after):.0f}").replace("__AWACS__", _lua_str(awacs)).replace("__SPLASH__", "true" if splash else "false")
            .replace("__RWYQ__", ", ".join(f'{{g={_lq(q["g"])}, f={int(q["f"])}, b={_lq(q["b"])}' + (f', t={int(q["t"])}' if q.get("t") is not None else '') + '}' for q in (rwyq or []))).replace("__PRWY__", _lua_str(prwy))
            .replace("__COVER__", ", ".join(f'{{g={_lq(c["g"])}, n={int(c["n"])}, bf={int(c["bf"])}, rf={int(c["rf"])}, u={float(c["u"]):.0f}}}' for c in (cover or [])))
            .replace("__ALERTS__", ", ".join(f'{{g={_lq(a["g"])}, f={int(a["f"])}, b={_lq(a["b"])}, ty={_lq(a["ty"])}}}' for a in (alerts or [])))
            .replace("__PHOME__", ("{ x = %.1f, z = %.1f }" % tuple((cfg or {})["phome"])) if (cfg or {}).get("phome") else "nil")
            .replace("__CVREC__", _cvrec_lua((cfg or {}).get("cvrec")))
            .replace("__RECOV__", _recov_lua((cfg or {}).get("recov")))
            .replace("__CFG__", json.dumps({k: v for k, v in (cfg or {}).items() if k not in ("cvrec", "recov")}).replace("'", "")))


def _recov_lua(rs) -> str:
    """v0.41.25: the recovery net's entries as a Lua list: group, carrier unit ("" for a field), x / z, radius (m), earliest time (s)."""
    return ", ".join(f'{{ g={_lq(r["g"])}, cv={_lq(r.get("cv") or "")}, x={float(r["x"]):.1f}, z={float(r["z"]):.1f}, r={float(r["r"]):.0f}, '
                     f't={float(r["t"]):.0f}, t2={float(r.get("t2", r["t"] + 1e6)):.0f}, dwell={float(r.get("dwell", 0)):.0f} }}' for r in (rs or []))


def _cvrec_lua(cv) -> str:
    """v0.41.17: the carrier recovery watch for your wingmen: the carrier unit, the radius (m) and the earliest time (s)."""
    if not cv:
        return ""
    if cv.get("cv"):
        return f'cv={_lq(cv["cv"])}, r={float(cv.get("r", 18520)):.0f}, t={float(cv.get("t", 0)):.0f}'
    return f'x={float(cv["x"]):.1f}, z={float(cv["z"]):.1f}, r={float(cv.get("r", 18520)):.0f}, t={float(cv.get("t", 0)):.0f}'


def install_hook(mission, campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "",
                 group: str = "", calls: list | None = None, wps: list | None = None, sound: str = "", sound_you: str = "", flights: dict | None = None,
                 enemy_air: list | None = None, sites: list | None = None, ruins: list | None = None, gates: list | None = None, ai_test: bool = False, gate_km: float = 40, jams: dict | None = None, jamw: dict | None = None,
                 watch: list | None = None, done_after: float = 0, awacs: str = "AWACS", splash: bool = False,
                 rwyq: list | None = None, prwy: str = "", alerts: list | None = None, cfg: dict | None = None, cover: list | None = None, ecm_player: str = "", ecm_msg: bool = True,
                 tune_flags: list | None = None, tune_mhz: float = 0.0, awacs_unit: str = "", dmg: dict | None = None, dmg_on: bool = False, scrub: list | None = None) -> None:
    """Embed the results hook. NOTE: DoScript needs String(<the script itself>), NOT mission.string(...): the latter stores a
    translation KEY and DCS then tries to run the key's name as code ('DictKey_Translation_5: = expected')."""
    from dcs.triggers import TriggerStart
    from dcs.action import DoScript
    from dcs.translation import String
    t = TriggerStart(comment="SQE debrief hook")
    t.add_action(DoScript(String(lua_hook(campaign_id, sortie, package_id, despawn_names, player_name, group, calls, wps, sound, sound_you, flights, enemy_air, sites, ruins, gates, ai_test, gate_km, jams, jamw, watch, done_after, awacs, splash, rwyq, prwy, alerts, cfg, cover, ecm_player, ecm_msg, tune_flags, tune_mhz, awacs_unit, dmg, dmg_on, scrub))))
    mission.triggerrules.triggers.append(t)


@dataclass
class Manifest:
    campaign_id: str
    sortie: int
    package_id: str
    day: int
    player_unit: str = ""
    built_at: float = field(default_factory=time.time)
    groups: list = field(default_factory=list)
    cur_pkg: str = ""                      # package whose groups are being added right now (merged missions hold several)
    merged: list = field(default_factory=list)   # extra packages folded into this mission: id, number, objective, tot_s...
    ruins: list = field(default_factory=list)    # earlier packages whose strike is shown as ruins: id, number

    def add(self, kind: str, ref: str, units: list, **extra) -> None:
        if self.cur_pkg:
            extra.setdefault("pkg", self.cur_pkg)
        self.groups.append({"kind": kind, "ref": ref, "units": units, **extra})

    def mark_primary(self, ref: str, pkg_id: str) -> None:
        """A target that is already live (spawned for another package of this mission) is also this package's primary target."""
        for g in self.groups:
            if g["kind"] == "asset" and g["ref"] == ref:
                g.setdefault("primary_pkgs", [])
                if pkg_id not in g["primary_pkgs"]:
                    g["primary_pkgs"].append(pkg_id)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def read_state_file(path: Path, manifest: Manifest, min_mtime: float | None = None) -> tuple:
    """-> (status, data). status: 'none' | 'stale' | 'mismatch' | 'busy' | 'ok'."""
    path = Path(path)
    if not path.exists():
        return "none", None
    if min_mtime is not None and path.stat().st_mtime < min_mtime:
        return "stale", None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "busy", None                   # DCS is mid-write; try again next poll
    if data.get("campaign") != manifest.campaign_id or data.get("sortie") != manifest.sortie:
        return "mismatch", data
    return "ok", data


def tally(state: CampaignState, manifest: Manifest, data: dict) -> dict:
    """Live casualty counts for the waiting window."""
    lost = set(data.get("dead", [])) | set(data.get("ejected", []))
    t = {"blue_air_total": 0, "blue_air_lost": 0, "blue_ground_total": 0, "blue_ground_lost": 0, "red_air_total": 0, "red_air_lost": 0,
         "red_ground_total": 0, "red_ground_lost": 0, "landed": 0, "red_landed": 0}
    down = set(data.get("landed", []))
    for g in manifest.groups:
        n_dead = sum(1 for u in g["units"] if u in lost)
        if g["kind"] == "friendly":
            t["landed"] += sum(1 for u in g["units"] if u in down)      # this side only: the raw list also holds red aircraft that landed
            t["blue_air_total"] += len(g["units"]); t["blue_air_lost"] += n_dead
        elif g["kind"] == "friendly_ground":
            t["blue_ground_total"] += len(g["units"]); t["blue_ground_lost"] += n_dead
        elif g["kind"] == "enemy_air":
            t["red_landed"] += sum(1 for u in g["units"] if u in down)
            t["red_air_total"] += len(g["units"]); t["red_air_lost"] += n_dead
        elif g["kind"] == "asset":
            t["red_ground_total"] += len(g["units"]); t["red_ground_lost"] += n_dead
    return t


def kill_log(manifest: Manifest, data: dict) -> list[str]:
    """'12:34 MiG-29S (Bandit 2-1) killed by F-16C (Viper 1-1) with AIM-120C' for every kill the hook saw."""
    label = {}
    for g in manifest.groups:
        lab = g.get("callsign") or ""
        for i, u in enumerate(g["units"]):
            label[u] = f"{lab}-{i + 1}" if lab and g.get("kind") in ("friendly",) else (lab or "")
    def who(unit, typ):
        l = label.get(unit, "")
        return f"{typ} ({l})" if l else typ
    out = []
    for k in data.get("kills", []) or []:
        t = int(k.get("t", 0))
        w = k.get("w", "?")
        by = who(k.get("k", "?"), k.get("kt", "?")) if k.get("k", "?") != "?" else "unknown"
        out.append(f"{t // 60:02d}:{t % 60:02d}  {who(k.get('v', '?'), k.get('vt', '?'))} killed by {by}" + (f" [{w}]" if w not in ("?", "") else ""))
    return out


def apply_debrief(state: CampaignState, manifest: Manifest, data: dict) -> dict:
    """Player-flown package: results are applied 1:1 (no dice). Returns a structured outcome for the debrief screen."""
    lost = set(data.get("dead", [])) | set(data.get("ejected", []))
    lost_all = lost
    landed = set(data.get("landed", []))
    out = {"blue_losses": [], "red_assets": [], "red_air_lost": 0, "blue_air_lost": 0, "target_damage": 0.0,
           "lines": [], "ended": bool(data.get("mission_ended")), "objective": "", "objective_type": "",
           "player": "airborne", "package_id": manifest.package_id}
    for g in manifest.groups:
        dead = [u for u in g["units"] if u in lost]
        if g["kind"] == "friendly":
            sq = state.squadrons[g["squadron"]]
            sq.available = max(0, sq.available - len(dead))
            out["blue_air_lost"] += len(dead)
            if dead:
                out["blue_losses"].append({"callsign": g.get("callsign", g["ref"]), "lost": len(dead), "total": len(g["units"])})
                out["lines"].append(f"{g.get('callsign', g['ref'])}: lost {len(dead)}/{len(g['units'])} ({sq.name}: {sq.available}/{sq.authorized} left)")
        elif g["kind"] == "friendly_ground":
            out["ground_total"] = out.get("ground_total", 0) + len(g["units"]); out["ground_lost"] = out.get("ground_lost", 0) + len(dead)
            if g["units"]:
                out["lines"].append(f"Friendly troops: lost {len(dead)} of {len(g['units'])} vehicles")
                from . import ground as _gr
                gl = _gr.blue_losses(state, g.get("ref", ""), len(dead), len(g["units"])) if dead else None
                if gl:                                                  # the ground war takes the loss from that sector's Blue strength
                    out["lines"].append(gl)
                elif len(dead) * 2 >= len(g["units"]) and g.get("ref") in state.assets and not _gr.active(state):      # the position is overrun
                    a0 = state.assets[g["ref"]]
                    fields = [b for b in state.bases.values() if b.kind.value == "AIRFIELD"]
                    if fields:
                        nb = min(fields, key=lambda b: (b.x - a0.x) ** 2 + (b.y - a0.y) ** 2)
                        from . import sams as _sams
                        _sams.hit_field(state, nb, 0.10)
                        out["lines"].append(f"The position was overrun; the column presses on toward {nb.name}")
        elif g["kind"] == "asset":
            a = state.assets[g["ref"]]
            frac = (len(g["units"]) - len(dead)) / max(1, g["base_count"])
            before = a.health
            from . import ground as _gr2
            a.health = _gr2.column_health(state, a, before, frac)
            dmg = before - a.health
            ra_ = {"name": a.name, "before": before, "after": a.health, "kind": a.kind.value, "primary": bool(g.get("primary")),
                   "destroyed": bool(a.destroyed or a.health <= _gr2.DOWN_HEALTH)}          # v0.41.171: tempo credits (tempo.credits)
            out["red_assets"].append(ra_)
            if g.get("primary"):
                out["target_damage"] = 1 - (a.health / before) if before > 0 else 0.0
            if dmg > 0:
                out["lines"].append(f"{a.name}: {before:.0%} -> {a.health:.0%}")
            rad = list(g.get("trk") or []) + list(g.get("srch") or [])
            if a.kind.value == "SAM" and rad and all(u in lost for u in rad) and not a.destroyed:
                a.suppressed = True; ra_["suppressed"] = True               # SEAD worked: the radars are gone, but the launchers are still there
                out["lines"].append(f"{a.name}: radars destroyed, launchers intact. SUPPRESSED, not dead: it needs a DEAD strike to finish it.")
        elif g["kind"] == "support":                              # v0.41.87: a tanker / AWACS shot down comes off its asset
            if dead:
                from . import support_assets as _sa
                ln = _sa.lose(state, g.get("label", ""), len(dead))
                if ln:
                    out["lines"].append(ln)
        elif g["kind"] == "enemy_air":
            w = state.enemy_air_at(g["ref"])
            if w and dead:
                w.lose(g.get("ac"), len(dead))                    # v0.41.53: the loss comes off the squadron that flew that type
                out["red_air_lost"] += len(dead)
                out["lines"].append(f"{len(dead)} enemy aircraft from {state.assets[g['ref']].name} destroyed")
    # a raid you were sent to stop: bombers still alive when they reached their base got through
    t_now = float(data.get("time", 0) or 0)
    for g in manifest.groups:
        if g["kind"] == "enemy_air" and g.get("raid_base") and g["raid_base"] in state.bases:
            alive = [u for u in g["units"] if u not in lost]
            where = g.get("raid_label") or state.bases[g["raid_base"]].name
            wing = state.enemy_air_at(g["ref"])
            if len(alive) < len(g["units"]):
                out["lines"].append(f"Raid: {len(g['units']) - len(alive)} of {len(g['units'])} attack aircraft shot down")
            rg_ = (data.get("rgate") or {}).get(g.get("raid_group", ""), {}) if g.get("raid_gate_s") is not None else {}
            arrive_ = g.get("raid_arrive_s", 0.0)
            if rg_.get("open") is not None:                       # v0.41.126: held at the gate until the radars went down: it can arrive no sooner than that plus the leg in
                arrive_ = max(arrive_, float(rg_["open"]) + float(g["raid_gate_s"]))
            if alive and g.get("raid_gate_s") is not None and rg_.get("abort") is not None and rg_.get("open") is None:
                out["lines"].append(f"Raid on {where}: the radars were still up, so the attack aircraft turned back at the gate; no bombs fell")
            elif alive and g.get("raid_gate_s") is not None and rg_.get("open") is None:
                out["lines"].append(f"Raid on {where}: the attack aircraft were still held outside the defences; no bombs fell")
            elif alive and t_now >= arrive_:
                from . import raids as _rd
                import random as _rnd
                out["lines"].append(f"Raid on {where}: {len(alive)} attack aircraft got through")
                out["lines"] += [x.strip() for x in _rd.hit(state, g["raid_base"], wing, _rnd.Random(f"{state.campaign_id}:{state.day}:through"), len(alive), g.get("raid_aim", ""), g.get("ac"))]
            elif alive:
                from . import raids as _rd
                import random as _rnd
                rr = _rnd.Random(f"{state.campaign_id}:{state.day}:early")
                if rr.random() < 0.5:
                    out["lines"].append(f"Raid: you left before the raiders arrived; {len(alive)} got through to {where}")
                    out["lines"] += [x.strip() for x in _rd.hit(state, g["raid_base"], wing, rr, len(alive), g.get("raid_aim", ""), g.get("ac"))]
                else:
                    out["lines"].append("Raid: you left before the raiders arrived; the defences stopped them")
            else:
                out["lines"].append(f"Raid on {where}: stopped, no bombs fell")
    follow_ = any((p_.get("objective") or {}).get("after") for p_ in (state.plan or []) if p_.get("id") == data.get("package"))      # v0.41.158: a strike / CAS behind a SEAD
    for ref in data.get("aborted", []) or []:
        a = state.assets.get(ref)
        if a is not None:
            out["lines"].append((f"Attack called off behind {a.name}" if follow_ else f"DEAD called off on {a.name}") +
                                ": its radars were still up when the strike flight reached the gate, so it turned back without attacking.")
    # alert / scramble groups (v0.40.8): called, airborne, or stuck on the ground; and the build's settings, so test runs can be told apart
    ms_ = lambda t_: f"{int(t_) // 60:d}:{int(t_) % 60:02d}"                  # v0.41.208 (XO): scrambles are numbered in the order the build lists them (the briefing's QRA list uses the same numbers)
    for n_, al in enumerate(data.get("alerts", []) or [], 1):
        if al.get("called") is None:
            continue
        who_ = f"Scramble {n_} ({al.get('ty', '?')}, {al.get('b', '?')})"
        if al.get("air") is not None:
            out["lines"].append(f"{who_}: ordered {ms_(al['called'])}, airborne +{ms_(al['air'] - al['called'])}")
        else:
            out["lines"].append(f"{who_}: ordered {ms_(al['called'])}, " + ("NEVER GOT AIRBORNE (stuck on the ground)" if al.get("stuck") else "not airborne yet when the mission ended"))
    # v0.41.92: fuel. The lead's fuel is tracked every 30 s (`tracks`: [t, x, z, alt_m, fuel_%, kts]); a flight that ended the mission low explains the
    # pairs that went home early (bingo). Reported for every AI group that was airborne and ended at BINGO_REPORT_PCT or less.
    ty_ = {a_["g"]: a_.get("ty", "") for a_ in (data.get("alerts") or [])}
    for gn_, tr_ in sorted((data.get("tracks") or {}).items()):
        fl_ = [p_ for p_ in tr_ if len(p_) >= 6 and p_[3] > 300 and p_[5] > 120 and 0 <= p_[4] <= 100]
        if len(fl_) < 4:
            continue
        last_ = fl_[-1]
        if last_[4] > BINGO_REPORT_PCT:
            continue
        cross_ = next((p_ for p_ in fl_ if p_[4] <= BINGO_PCT), None)
        out["lines"].append(f"Fuel: {gn_}{' (' + ty_[gn_] + ')' if ty_.get(gn_) else ''} airborne {int(fl_[0][0]) // 60}-{int(last_[0]) // 60} min, fuel {fl_[0][4]}% to {last_[4]}%"
                            + (f", at bingo ({BINGO_PCT}%) from {int(cross_[0]) // 60} min" if cross_ else ""))
    cf_ = data.get("cfg") or {}
    if cf_:
        sp_ = data.get("splash") or {}
        out["lines"].append(f"Settings: splash damage {'ON' if cf_.get('splash_damage') else 'off'}" +
                            (f" ({sp_.get('blasts', 0)} blasts, {sp_.get('kills', 0)} kills)" if cf_.get("splash_damage") else "") +
                            f", ECM script {'ON' if cf_.get('ecm_script') else 'off'}, build v{cf_.get('version', '?')}")
    # merged missions: one line per folded-in package, from what really happened (reported only if its strike time was reached)
    t_end = float(data.get("time", 0) or 0)
    out["packages"] = []
    for m in manifest.merged:
        dmg = None
        for g in manifest.groups:
            if g["kind"] == "asset" and m["id"] in (g.get("primary_pkgs") or []):
                a = state.assets[g["ref"]]
                dmg = 1 - (a.health / g["health_before"]) if g.get("health_before") else 0.0
        fl = [g for g in manifest.groups if g["kind"] == "friendly" and g.get("pkg") == m["id"]]
        n_lost = sum(1 for g in fl for u in g["units"] if u in lost_all)
        tot = sum(len(g["units"]) for g in fl)
        done = t_end >= m["tot_s"] + 90
        if str(m.get("objective", "")).startswith("Fighter Sweep"):
            dmg = None                                       # a sweep fights the air over the target area; the target itself is the strikers' job
        out["packages"].append({"number": m["number"], "objective": m["objective"], "damage": dmg, "lost": n_lost, "total": tot, "resolved": done})
        out["lines"].append(f"Package #{m['number']} ({m['objective']}): " + (f"target damage {dmg:.0%}, lost {n_lost}/{tot} aircraft" if done and dmg is not None else
                            (f"flown to the end: lost {n_lost}/{tot} aircraft" if done else "you were out of the mission before its strike; it is resolved by the war simulation")))
    # SEAD first: a SEAD package that was really flown settles whether the site is blind (the DEAD stage and the failed-days count read it)
    from .war import note_sead as _note_sead
    t_end2 = float(data.get("time", 0) or 0)
    flown_ids = [data.get("package")] + [m["id"] for m in manifest.merged if t_end2 >= m["tot_s"] + 90]
    for pk in state.plan:
        o_ = pk.get("objective", {})
        if pk.get("id") in flown_ids and o_.get("type") == "DEAD" and o_.get("aim") in ("SEAD", "STANDOFF") and o_.get("target_id") in state.assets:
            a_ = state.assets[o_["target_id"]]
            _note_sead(state, a_.id, bool(a_.suppressed or a_.destroyed))
            out["lines"].append(f"SEAD on {a_.name}: " + (("its radars are out" + ("" if o_.get("aim") == "STANDOFF" else "; the Close DEAD package can go in")) if (a_.suppressed or a_.destroyed) else ("its radars are still up" + ("" if o_.get("aim") == "STANDOFF" else "; the Close DEAD package will not commit"))))
    pdat = data.get("player") or {}
    t0, t1 = pdat.get("takeoff"), pdat.get("landed")
    flight_s = (t1 - t0) if (t0 is not None and t1 is not None) else ((data.get("time", 0) - t0) if t0 is not None else 0)
    out["pilot"] = {"flight_s": max(0, int(flight_s)), "ka": int(pdat.get("ka", 0)), "kg": int(pdat.get("kg", 0)),
                    "ks": int(pdat.get("ks", 0)), "landed": t1 is not None}
    pu = manifest.player_unit
    if pu in data.get("ejected", []):
        out["player"] = "ejected"
    elif pu in data.get("dead", []):
        out["player"] = "lost"
    elif pu in landed:
        out["player"] = "recovered"
    out["kill_log"] = kill_log(manifest, data)
    for ln in out["lines"]:
        state.note(ln)
    if not out["lines"]:
        out["lines"].append("No changes to the campaign.")
    return out
