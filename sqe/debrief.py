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
local deaths = {}                 -- why each loss happened: last hit seen, last fuel and altitude sample (so an unexplained loss still tells something)
local LASTHIT = {}                -- unit name -> {by, w, t} of the last hit on it
local SAMPLE = {}                 -- unit name -> {fuel, alt, spd, t} sampled every 30 s for every aircraft
local JAMW = { __JAMW__ }          -- unit name -> {from, to} mission seconds the jammer runs (AI: the attack leg); absent = always on
local JAMS = { __JAMS__ }          -- unit name -> 1 internal set, 2 ECM pod (ecm.py)
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
    o[#o + 1] = string.format('{"n":"%s","t":%d,"ev":"%s","by":"%s","w":"%s","ago":%s,"fuel":%s,"alt_m":%s,"kts":%s,"sample_age":%s}',
      esc(k.n), k.t, esc(k.ev), esc(k.by), esc(k.w), num(k.ago), k.fuel and string.format("%.2f", k.fuel) or "null", num(k.alt), num(k.kts), num(k.sage))
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function gatesJson()
  local o = {}
  for _, e in ipairs(gateLog) do
    o[#o + 1] = string.format('{"site":"%s","grp":"%s","t":%d,"ran":%d,"radars":%d,"abort":%s,"cmd":%s,"by":"%s","d0":%s,"d1":%s}',
      esc(e.site), esc(e.grp), e.t, e.ran, e.radars, tostring(e.abort), tostring(e.cmd), esc(e.by or ""), num(e.d0), num(e.d1))
  end
  return "[" .. table.concat(o, ",") .. "]"
end
local function dump()
  local f = io.open(OUT, "w")
  if not f then return end
  f:write(string.format('{"campaign":"__CAMPAIGN__","sortie":__SORTIE__,"package":"__PKG__","mission_ended":%s,"time":%d,"dead":%s,"ejected":%s,"landed":%s,"player":{"takeoff":%s,"landed":%s,"ka":%d,"kg":%d,"ks":%d},"kills":%s,"aborted":%s,"gates":%s,"shots":%s,"jams":%s,"deaths":%s}',
    tostring(ended), math.floor(timer.getTime()), list(dead), list(ejected), list(landed),
    num(pl.takeoff), num(pl.landed), pl.ka, pl.kg, pl.ks, killsJson(), list(aborted), gatesJson(), shotsJson(), jamsJson(), deathsJson()))
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
    say(who .. ": " .. s.label .. " blinded, all radars destroyed.")
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
  if ev == "hit" and e.target then
    local okc, cat = pcall(function() return e.target:getCategory() end)
    if okc and cat == Object.Category.SCENERY then return end        -- trees, houses, poles: pure noise in the log
    tg = nameOf(e.target) or ""; tt = tname(e.target)
    local okq, tq = pcall(function() return e.target:getPoint() end)
    if okq and tq then tx, tz = tq.x, tq.z end
  end
  if ev == "hit" and tg ~= "" then LASTHIT[tg] = { by = by or "?", w = w, t = timer.getTime() } end
  if #shots >= 600 then return end
  shots[#shots + 1] = { t = math.floor(timer.getTime()), ev = ev, by = by or "?", bt = e.initiator and tname(e.initiator) or "?", w = w, tg = tg, tt = tt, km = km, alt = salt, tx = tx, tz = tz }
end
-- jamming: a radar-guided missile fired at an aircraft with jamming equipment may be defeated partway through its flight
local function jamOn(name)                  -- future: the player's cockpit switch (export script) feeds this
  local w = JAMW[name]
  if not w then return true end
  local t = timer.getTime()
  return t >= w[1] and t <= w[2]
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
                                fuel = sm and sm.fuel, alt = sm and sm.alt, kts = sm and sm.spd, sage = sm and (now - sm.t) or nil }
      end
      dead[n] = true; dump(); siteDead(n)
    end
  elseif id == world.event.S_EVENT_TAKEOFF then
    if n == PLAYER and not pl.takeoff then pl.takeoff = timer.getTime(); dump() end
  elseif id == world.event.S_EVENT_SHOT then
    logShot("shot", e, n)
    pcall(jamCheck, e, n)
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
  elseif id == world.event.S_EVENT_KILL then
    do
      local tn0 = nameOf(e.target)
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
        for _, u in ipairs((oku and units) or {}) do
          pcall(function()
            local un = u:getName()
            if un and u:isExist() then
              local p, v = u:getPoint(), u:getVelocity()
              SAMPLE[un] = { fuel = u:getFuel(), alt = p.y, spd = math.sqrt(v.x ^ 2 + v.y ^ 2 + v.z ^ 2) * 1.944, t = timer.getTime() }
            end
          end)
        end
      end
    end
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
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  for i, c in ipairs(CALLS) do
    if not said[i] and now >= c.t then said[i] = true; say(c.text, c.you) end
  end
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
        pcall(function() trigger.action.explosion(v, r.pw) end)
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
  for _, un in ipairs(s.units) do
    local u = Unit.getByName(un)
    if u then local ok, p = pcall(function() return u:getPoint() end); if ok and p then return p end end
  end
end
local HOLD_S = 720           -- an AI DEAD flight whose radars are still up holds this long (12 min) before it breaks off
local HOLD_CHECK_S = 60      -- and re-checks the radars this often while it holds
local HOLD_FUEL = 0.30       -- below this fuel fraction the holding flight breaks off at once: it must have fuel for the strike and the way home
-- every SEAD flight of this site is down or gone (no airborne unit left): the blinding has failed and there is no reason to go in.
-- Only counts when the mission has SEAD flights on the site at all; an error reading a group counts it as still flying.
local function seadsGone(gs)
  local names, any = {}, false
  for _, gt in ipairs(gs.gates) do
    for _, n in ipairs(gt.seads or {}) do names[#names + 1] = n; any = true end
  end
  if not any then return false end
  for _, n in ipairs(names) do
    local ok, alive = pcall(function() local g = Group.getByName(n); return g ~= nil and g:getSize() > 0 end)
    if not ok or alive then return false end
  end
  return true
end
local function siteOf(gs)
  for _, x in ipairs(SITES) do if x.id == gs.site then return x end end
end
local function breakOff(gs, why)
  gs.done = true
  gs.holding = false
  local s = siteOf(gs)
  if not aborted[gs.site] then
    aborted[gs.site] = true
    say(s.who .. ": abort, abort. " .. s.label .. " radars still up, DEAD flight break off.", gs.gates[1].you)
  end
  for _, gt in ipairs(gs.gates) do
    if gt.dead then
      local why_txt = ({ ["hold-timeout"] = "hold time is up", ["hold-fuel"] = "fuel is low", ["seads-gone"] = "the SEAD flights are down or gone" })[why] or ("not blind in time (" .. why .. ")")
      say(s.who .. ": abort, RTB. " .. s.label .. " " .. why_txt .. ".", gt.you)
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
        e.cmd = pcall(function() g:getController():setCommand({ id = "SwitchWaypoint", params = { fromWaypointIndex = gt.from, goToWaypointIndex = gt.to } }) end)
      end
      timer.scheduleFunction(function() e.d1 = gdist(gt.grp, e.tp); dump(); return nil end, nil, timer.getTime() + 60)
    end
  end
  dump()
end
local function resume(gs)
  gs.done = true
  gs.holding = false
  local s = siteOf(gs)
  for _, gt in ipairs(gs.gates) do
    local e = { site = gt.site, grp = gt.grp, t = math.floor(gt.t), ran = math.floor(timer.getTime()), radars = s and s.nrad or -1, abort = false, cmd = false, by = "hold-resumed", held = math.floor(timer.getTime() - gs.holdAt) }
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
    if gt.dead then say(s.who .. ": " .. s.label .. " radars are down. Go, go, go.", gt.you) end
  end
  dump()
end
local function holdGroups(gs)
  gs.holding = true
  gs.holdAt = timer.getTime()
  local s = siteOf(gs)
  for _, gt in ipairs(gs.gates) do
    if gt.dead then say(s.who .. ": " .. s.label .. " radars still up. Hold outside, rechecking.", gt.you) end
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
  local blind = (not s) or s.nrad <= 0 or s.nalive <= 0
  if blind then resume(gs); return nil end
  if timer.getTime() - gs.holdAt >= HOLD_S then breakOff(gs, "hold-timeout"); return nil end
  if seadsGone(gs) then breakOff(gs, "seads-gone"); return nil end
  if holdFuelLow(gs) then breakOff(gs, "hold-fuel"); return nil end
  return t + HOLD_CHECK_S
end
local function decide(gs, why)
  local s = siteOf(gs)
  local blind = (not s) or s.nrad <= 0 or s.nalive <= 0
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
  gs.done = true
  for _, gt in ipairs(gs.gates) do
    local e = { site = gt.site, grp = gt.grp, t = math.floor(gt.t), ran = math.floor(timer.getTime()), radars = s and s.nrad or -1, abort = false, cmd = false, by = why }
    gateLog[#gateLog + 1] = e
    e.tp = gs.tp
    e.d0 = gdist(gt.grp, e.tp)
  end
  dump()
end
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  for i, c in ipairs(CALLS) do
    if not said[i] and now >= c.t then said[i] = true; say(c.text, c.you) end
  end
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
        pcall(function() trigger.action.explosion(v, r.pw) end)
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
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  local left = false
  for _, gs in ipairs(gorder) do
    if not gs.done and not gs.holding then
      left = true
      local s
      for _, x in ipairs(SITES) do if x.id == gs.site then s = x end end
      if s and not gs.tp then gs.tp = sitePoint(s) end
      if now >= gs.fall then
        decide(gs, "clock")
      else
        for _, gt in ipairs(gs.gates) do
          if gt.dead then
            local d = gdist(gt.grp, gs.tp)
            if d and d <= GATE_M then decide(gs, "dist"); break end
          end
        end
      end
    end
  end
  if left then return t + 5 end
  return nil
end, nil, timer.getTime() + 5)
dump()
'''


def _jamcfg() -> str:
    from . import ecm
    return (f"local JC = {{ p1={ecm.P_SELF[1]}, p2={ecm.P_SELF[2]}, cover={ecm.P_COVER}, coverM={ecm.COVER_NM * 1852:.0f}, "
            f"burn={ecm.BURN_KM * 1000:.0f}, full={ecm.FULL_KM * 1000:.0f} }}")


def _lua_str(s: str) -> str:
    return str(s).replace("\\", "/").replace('"', "'")


def _lq(s) -> str:
    return '"' + _lua_str(s).replace("\n", " ") + '"'


def lua_hook(campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "", group: str = "",
             calls: list | None = None, wps: list | None = None, sound: str = "", sound_you: str = "", flights: dict | None = None,
             enemy_air: list | None = None, sites: list | None = None, ruins: list | None = None, gates: list | None = None, ai_test: bool = False, gate_km: float = 40, jams: dict | None = None, jamw: dict | None = None) -> str:
    tbl = ", ".join(f'["{n}"]=true' for n in despawn_names)
    cl = ", ".join(f'{{t={float(c[0]):.0f}, text="{_lua_str(c[1])}", you={"true" if (len(c) > 2 and c[2]) else "false"}}}' for c in (calls or []))
    uf = ", ".join(f"[{_lq(k)}]={_lq(v)}" for k, v in (flights or {}).items())
    ea = ", ".join(f"[{_lq(n)}]=true" for n in (enemy_air or []))
    lst = lambda xs: "{" + ", ".join(_lq(x) for x in xs) + "}"
    st = ", ".join(f'{{id={_lq(x["id"])}, label={_lq(x["label"])}, who={_lq(x["who"])}, prim={"true" if x["prim"] else "false"}, '
                   f'units={lst(x["units"])}, trk={lst(x["trk"])}, srch={lst(x["srch"])}}}' for x in (sites or []))
    ru = ", ".join(f'{{x={r["x"]:.1f}, z={r["z"]:.1f}, n={int(r["n"])}, r={float(r["r"]):.0f}, p={int(r["p"])}, dn={float(r["dn"]):.2f}, pw={int(r["pw"])}, s={float(r["s"]):.2f}}}'
                   for r in (ruins or []))
    gt = ", ".join(f'{{t={float(x["t"]):.0f}, site={_lq(x["site"])}, grp={_lq(x["grp"])}, from={int(x["from"])}, to={int(x["to"])}, ai={"true" if x["ai"] else "false"}, dead={"true" if x.get("dead") else "false"}, you={"true" if x.get("you") else "false"}, seads={{{", ".join(_lq(n) for n in x.get("seads", []))}}}}}'
                   for x in (gates or []))
    return (LUA_HOOK.replace("__GATEKM__", str(int(gate_km))).replace("__AITEST__", "true" if ai_test else "false").replace("__GATES__", gt).replace("__RUINS__", ru).replace("__CAMPAIGN__", campaign_id).replace("__SORTIE__", str(sortie))
            .replace("__PKG__", package_id).replace("__DESPAWN__", tbl).replace("__PLAYER__", player_name)
            .replace("__PGROUP__", _lua_str(group)).replace("__SOUND__", sound).replace("__SOUND_YOU__", sound_you).replace("__CALLS__", cl).replace("__UFLT__", uf)
            .replace("__ENEMYAIR__", ea).replace("__SITES__", st).replace("__JAMCFG__", _jamcfg()).replace("__JAMS__", ", ".join(f"[{_lq(k)}]={int(v)}" for k, v in (jams or {}).items()))
            .replace("__JAMW__", ", ".join(f"[{_lq(k)}]={{{float(a):.0f}, {float(b):.0f}}}" for k, (a, b) in (jamw or {}).items())))


def install_hook(mission, campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "",
                 group: str = "", calls: list | None = None, wps: list | None = None, sound: str = "", sound_you: str = "", flights: dict | None = None,
                 enemy_air: list | None = None, sites: list | None = None, ruins: list | None = None, gates: list | None = None, ai_test: bool = False, gate_km: float = 40, jams: dict | None = None, jamw: dict | None = None) -> None:
    """Embed the results hook. NOTE: DoScript needs String(<the script itself>), NOT mission.string(...): the latter stores a
    translation KEY and DCS then tries to run the key's name as code ('DictKey_Translation_5: = expected')."""
    from dcs.triggers import TriggerStart
    from dcs.action import DoScript
    from dcs.translation import String
    t = TriggerStart(comment="SQE debrief hook")
    t.add_action(DoScript(String(lua_hook(campaign_id, sortie, package_id, despawn_names, player_name, group, calls, wps, sound, sound_you, flights, enemy_air, sites, ruins, gates, ai_test, gate_km, jams, jamw))))
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
                        nb.defense = max(0.0, nb.defense - 0.10)
                        out["lines"].append(f"The position was overrun; the column presses on toward {nb.name}")
        elif g["kind"] == "asset":
            a = state.assets[g["ref"]]
            frac = (len(g["units"]) - len(dead)) / max(1, g["base_count"])
            before = a.health
            from . import ground as _gr2
            a.health = _gr2.column_health(state, a, before, frac)
            dmg = before - a.health
            out["red_assets"].append({"name": a.name, "before": before, "after": a.health})
            if g.get("primary"):
                out["target_damage"] = 1 - (a.health / before) if before > 0 else 0.0
            if dmg > 0:
                out["lines"].append(f"{a.name}: {before:.0%} -> {a.health:.0%}")
            rad = list(g.get("trk") or []) + list(g.get("srch") or [])
            if a.kind.value == "SAM" and rad and all(u in lost for u in rad) and not a.destroyed:
                a.suppressed = True               # SEAD worked: the radars are gone, but the launchers are still there
                out["lines"].append(f"{a.name}: radars destroyed, launchers intact. SUPPRESSED, not dead: it needs a DEAD strike to finish it.")
        elif g["kind"] == "enemy_air":
            w = state.enemy_air_at(g["ref"])
            if w and dead:
                w.available = max(0, w.available - len(dead))
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
            if alive and t_now >= g.get("raid_arrive_s", 0.0):
                from . import raids as _rd
                import random as _rnd
                out["lines"].append(f"Raid on {where}: {len(alive)} attack aircraft got through")
                out["lines"] += [x.strip() for x in _rd.hit(state, g["raid_base"], wing, _rnd.Random(f"{state.campaign_id}:{state.day}:through"), len(alive), g.get("raid_aim", ""))]
            elif alive:
                from . import raids as _rd
                import random as _rnd
                rr = _rnd.Random(f"{state.campaign_id}:{state.day}:early")
                if rr.random() < 0.5:
                    out["lines"].append(f"Raid: you left before the raiders arrived; {len(alive)} got through to {where}")
                    out["lines"] += [x.strip() for x in _rd.hit(state, g["raid_base"], wing, rr, len(alive), g.get("raid_aim", ""))]
                else:
                    out["lines"].append("Raid: you left before the raiders arrived; the defences stopped them")
            else:
                out["lines"].append(f"Raid on {where}: stopped, no bombs fell")
    for ref in data.get("aborted", []) or []:
        a = state.assets.get(ref)
        if a is not None:
            out["lines"].append(f"DEAD called off on {a.name}: its radars were still up when the strike flight reached the gate, so it turned back without attacking.")
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
        out["packages"].append({"number": m["number"], "objective": m["objective"], "damage": dmg, "lost": n_lost, "total": tot, "resolved": done})
        out["lines"].append(f"Package #{m['number']} ({m['objective']}): " + (f"target damage {dmg:.0%}, lost {n_lost}/{tot} aircraft" if done and dmg is not None else
                            (f"flown to the end: lost {n_lost}/{tot} aircraft" if done else "you were out of the mission before its strike; it is resolved by the war simulation")))
    # SEAD first: a SEAD package that was really flown settles whether the site is blind (the DEAD stage and the failed-days count read it)
    from .war import note_sead as _note_sead
    t_end2 = float(data.get("time", 0) or 0)
    flown_ids = [data.get("package")] + [m["id"] for m in manifest.merged if t_end2 >= m["tot_s"] + 90]
    for pk in state.plan:
        o_ = pk.get("objective", {})
        if pk.get("id") in flown_ids and o_.get("type") == "DEAD" and o_.get("aim") == "SEAD" and o_.get("target_id") in state.assets:
            a_ = state.assets[o_["target_id"]]
            _note_sead(state, a_.id, bool(a_.suppressed or a_.destroyed))
            out["lines"].append(f"SEAD on {a_.name}: " + ("its radars are out; the DEAD package can go in" if (a_.suppressed or a_.destroyed) else "its radars are still up; the DEAD package will not commit"))
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
