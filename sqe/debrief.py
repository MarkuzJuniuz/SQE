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
local CALLS = { __CALLS__ }
local UFLT = { __UFLT__ }
local ENEMYAIR = { __ENEMYAIR__ }
local SITES = { __SITES__ }
local pl = { takeoff = nil, landed = nil, ka = 0, kg = 0, ks = 0 }
local dead, ejected, landed, ended = {}, {}, {}, false
local function esc(s) return (tostring(s):gsub('[%c"\\]', function(c) return string.format("\\u%04x", string.byte(c)) end)) end
local function list(t)
  local o = {}
  for k, _ in pairs(t) do o[#o + 1] = '"' .. esc(k) .. '"' end
  table.sort(o)
  return "[" .. table.concat(o, ",") .. "]"
end
local function num(x) if x then return string.format("%d", math.floor(x)) end return "null" end
local function dump()
  local f = io.open(OUT, "w")
  if not f then return end
  f:write(string.format('{"campaign":"__CAMPAIGN__","sortie":__SORTIE__,"package":"__PKG__","mission_ended":%s,"time":%d,"dead":%s,"ejected":%s,"landed":%s,"player":{"takeoff":%s,"landed":%s,"ka":%d,"kg":%d,"ks":%d}}',
    tostring(ended), math.floor(timer.getTime()), list(dead), list(ejected), list(landed),
    num(pl.takeoff), num(pl.landed), pl.ka, pl.kg, pl.ks))
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
    if n and not landed[n] then dead[n] = true; dump(); siteDead(n) end
  elseif id == world.event.S_EVENT_TAKEOFF then
    if n == PLAYER and not pl.takeoff then pl.takeoff = timer.getTime(); dump() end
  elseif id == world.event.S_EVENT_SHOT then
    local lab = UFLT[n]
    if lab and e.weapon then
      local call = shotCall(e)
      if call and throttle("shot:" .. lab .. call, 6) then say(lab .. ": " .. call .. ".") end
    end
  elseif id == world.event.S_EVENT_HIT then
    local tn = nameOf(e.target)
    local s = tn and SITE_OF[tn]
    local lab = UFLT[n]
    if s and lab then
      s.last = lab
      if throttle("hit:" .. lab, 15) then say(lab .. ": direct hit.") end
    end
  elseif id == world.event.S_EVENT_KILL then
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
timer.scheduleFunction(function(_, t) dump(); return t + 30 end, nil, timer.getTime() + 30)
-- call-outs for the player's flight: scheduled radio calls from the other flights and the support aircraft, plus weapon and result calls
local said = {}
function say(text)
  local g = Group.getByName(PGROUP)
  if not g then return end
  local id = g:getID()
  trigger.action.outTextForGroup(id, text, 8, false)
  if SOUND ~= "" then trigger.action.outSoundForGroup(id, SOUND) end
end
timer.scheduleFunction(function(_, t)
  local now = timer.getTime()
  for i, c in ipairs(CALLS) do
    if not said[i] and now >= c.t then said[i] = true; say(c.text) end
  end
  return t + 2
end, nil, timer.getTime() + 5)
dump()
'''


def _lua_str(s: str) -> str:
    return str(s).replace("\\", "/").replace('"', "'")


def _lq(s) -> str:
    return '"' + _lua_str(s).replace("\n", " ") + '"'


def lua_hook(campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "", group: str = "",
             calls: list | None = None, wps: list | None = None, sound: str = "", flights: dict | None = None,
             enemy_air: list | None = None, sites: list | None = None) -> str:
    tbl = ", ".join(f'["{n}"]=true' for n in despawn_names)
    cl = ", ".join(f'{{t={float(t):.0f}, text="{_lua_str(x)}"}}' for t, x in (calls or []))
    uf = ", ".join(f"[{_lq(k)}]={_lq(v)}" for k, v in (flights or {}).items())
    ea = ", ".join(f"[{_lq(n)}]=true" for n in (enemy_air or []))
    lst = lambda xs: "{" + ", ".join(_lq(x) for x in xs) + "}"
    st = ", ".join(f'{{id={_lq(x["id"])}, label={_lq(x["label"])}, who={_lq(x["who"])}, prim={"true" if x["prim"] else "false"}, '
                   f'units={lst(x["units"])}, trk={lst(x["trk"])}, srch={lst(x["srch"])}}}' for x in (sites or []))
    return (LUA_HOOK.replace("__CAMPAIGN__", campaign_id).replace("__SORTIE__", str(sortie))
            .replace("__PKG__", package_id).replace("__DESPAWN__", tbl).replace("__PLAYER__", player_name)
            .replace("__PGROUP__", _lua_str(group)).replace("__SOUND__", sound).replace("__CALLS__", cl).replace("__UFLT__", uf)
            .replace("__ENEMYAIR__", ea).replace("__SITES__", st))


def install_hook(mission, campaign_id: str, sortie: int, package_id: str, despawn_names: list, player_name: str = "",
                 group: str = "", calls: list | None = None, wps: list | None = None, sound: str = "", flights: dict | None = None,
                 enemy_air: list | None = None, sites: list | None = None) -> None:
    """Embed the results hook. NOTE: DoScript needs String(<the script itself>), NOT mission.string(...): the latter stores a
    translation KEY and DCS then tries to run the key's name as code ('DictKey_Translation_5: = expected')."""
    from dcs.triggers import TriggerStart
    from dcs.action import DoScript
    from dcs.translation import String
    t = TriggerStart(comment="SQE debrief hook")
    t.add_action(DoScript(String(lua_hook(campaign_id, sortie, package_id, despawn_names, player_name, group, calls, wps, sound, flights, enemy_air, sites))))
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
         "red_ground_total": 0, "red_ground_lost": 0, "landed": len(data.get("landed", []))}
    for g in manifest.groups:
        n_dead = sum(1 for u in g["units"] if u in lost)
        if g["kind"] == "friendly":
            t["blue_air_total"] += len(g["units"]); t["blue_air_lost"] += n_dead
        elif g["kind"] == "friendly_ground":
            t["blue_ground_total"] += len(g["units"]); t["blue_ground_lost"] += n_dead
        elif g["kind"] == "enemy_air":
            t["red_air_total"] += len(g["units"]); t["red_air_lost"] += n_dead
        elif g["kind"] == "asset":
            t["red_ground_total"] += len(g["units"]); t["red_ground_lost"] += n_dead
    return t


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
                if len(dead) * 2 >= len(g["units"]) and g.get("ref") in state.assets:      # the position is overrun
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
            a.health = max(0.0, min(before, frac))
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
    for ln in out["lines"]:
        state.note(ln)
    if not out["lines"]:
        out["lines"].append("No changes to the campaign.")
    return out
