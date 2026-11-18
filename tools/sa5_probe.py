"""SA-5 range probe (S90, J6, XO 2026-11-18; tools only, nothing ships, no change in play).

How far out, and how high / low, does a DCS SA-5 site (S-200 "Gammon") shoot and hit? SQE plans with a range for it that nobody has measured. One Syria mission,
no SQE campaign, no player flight (one parked client slot at Incirlik, only so DCS lets you press Fly):

  python tools/sa5_probe.py make OUT.miz        e.g. C:\\temp\\SQE_SA5_Probe.miz, then copy to <Saved Games>\\DCS\\Missions\\Probes

The site (red, Syria, 12 km south-west of Tiyas at x -68100, y 149400, on land 1.5 km clear of the sea, 20 m of relief in 2 km, checked on the syria4 scan):
  6 x S_200_Launcher ("S-200_Launcher", SA-5 Gammon, pydcs: weapon reach 255 km)
  1 x RPC_5N62V     ("Square Pair" tracking radar, pydcs: detection 400 km)
  1 x RLS_19J6      (ST-68U "Tin Shield" search radar, pydcs: detection 150 km)
That is the whole SA-5 set pydcs has (the same three units the DCS Mission Editor lists under SAM SA-5). The site has no command post and no other radar: if DCS needs one
the first run shows it (no SHOT lines although a pair is inside 150 km). Radars and launchers sit in a ring (launchers 90 m out, the two radars 25 m from the centre).

Four blue F-16C pairs fly straight at the site from 180 nm, one pair per altitude, on four bearings 30 degrees apart (tracks meet only at the site, over flat desert),
450 kt ground speed, ROE weapons hold, reaction to threat none, ECM never used, no weapons loaded. They start 12 minutes apart (35,000 ft first, 500 ft last) so one pair is past
the site before the next arrives: the site's single tracking radar then measures one pair at a time. The high pairs fly at the AGL over the site as MSL (barometric),
the 5,000 and 500 ft pairs at radar altitude with a waypoint every 15 nm. Each flies on 40 nm past the site.
  35,000 ft  bearing 150 from the site   20,000 ft  bearing 120   5,000 ft  bearing 180   500 ft  bearing 090 (the smoothest ground)
(The bearing is part of the altitude: the ground differs, so compare altitudes first and read terrain masking in only after.)

The mission script (DoScript at start) writes to dcs.log with the prefix SQESA5:
  SQESA5 SHOT   t=<s> launcher=<unit> weapon=<type> target=<unit> slant_nm=<..> tgt_msl_ft=<..> tgt_agl_ft=<..>
  SQESA5 HIT    t=<s> weapon=<type> target=<unit> slant_nm=<..> tgt_msl_ft=<..> tgt_agl_ft=<..>        (the missile's last position to the target)
  SQESA5 KILL / DEAD  t=<s> ...
  SQESA5 DETECT t=<s> target=<unit> slant_nm=<..> tgt_agl_ft=<..>   the first time the site's radar controller lists a unit of that pair (if the API gives it)
  SQESA5 TRACK  t=<s> <pair> lead slant_nm=<..> msl_ft=<..> agl_ft=<..>   every 30 s per pair while it is within 200 nm of the site
  SQESA5 SUMMARY  at 80 minutes: per pair the first DETECT, first SHOT, last SHOT range, hits and kills.
Fly the mission, sit in the slot (or watch F10 / spectator), Ctrl+Z accelerates time; after about 75 minutes send dcs.log (grep SQESA5)."""
from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import logging
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SITE = (-68100.0, 149400.0)          # DCS x (north), y (east), metres; 12 km SSW of Tiyas (-58907, 157071)
NM = 1852.0
FT = 0.3048
START_NM = 180.0                     # where each pair starts
BEYOND_NM = 40.0                     # how far past the site the route goes
SPEED_KT = 450.0
STAGGER_S = 12 * 60
# (label, altitude ft AGL over the site, bearing from the site in degrees (true, 0 = north, 90 = east), radar altitude?, waypoint spacing nm)
PAIRS = [("35k", 35000, 150, False, 60.0), ("20k", 20000, 120, False, 60.0), ("5k", 5000, 180, True, 15.0), ("500ft", 500, 90, True, 15.0)]
SITE_GROUND_M = 540.0                # ground at the site (scan relief), so the barometric altitude of the high pairs is AGL over the site

SA5_LUA = r'''
-- SQE SA-5 range probe: logs SHOT / HIT / KILL / DETECT / TRACK to dcs.log, prefix SQESA5
local SITE = "SA5 Site"
local PAIRS = {"35k", "20k", "5k", "500ft"}
local T0 = timer.getTime()
local seen, stats = {}, {}
for _, p in ipairs(PAIRS) do stats[p] = {detect = nil, shot = 0, first_shot = nil, last_shot = nil, hit = 0, kill = 0} end
local function say(s) env.info("SQESA5 " .. s) end
local function nm(a, b) return math.sqrt((a.x - b.x)^2 + (a.y - b.y)^2 + (a.z - b.z)^2) / 1852 end
local function agl_ft(p) return (p.y - land.getHeight({x = p.x, y = p.z})) / 0.3048 end
local function pair_of(name) if not name then return nil end for _, p in ipairs(PAIRS) do if string.find(name, "Probe " .. p .. " ", 1, true) then return p end end return nil end
local function site_pt() local g = Group.getByName(SITE); if g then local u = g:getUnit(1); if u and u:isExist() then return u:getPoint() end end return nil end
local function nameof(o) if o and o.isExist and o:isExist() then return o:getName() end return "?" end
local function tnow() return string.format("%.0f", timer.getTime() - T0) end

local H = {}
function H:onEvent(e)
  local ok, err = pcall(function()
    local id = e.id
    if id == world.event.S_EVENT_SHOT and e.weapon then
      local init = e.initiator
      local la = init and init:isExist() and init:getGroup() and init:getGroup():getName()
      if la ~= SITE then return end
      local tgt = nil
      local okt, t = pcall(function() return e.weapon:getTarget() end)
      if okt then tgt = t end
      local tp = tgt and tgt:isExist() and tgt:getPoint() or nil
      local ip = init:getPoint()
      local pr = pair_of(nameof(tgt))
      if pr then stats[pr].shot = stats[pr].shot + 1
        local r = nm(ip, tp); stats[pr].first_shot = stats[pr].first_shot or r; stats[pr].last_shot = r end
      say(string.format("SHOT t=%s launcher=%s weapon=%s target=%s slant_nm=%s tgt_msl_ft=%s tgt_agl_ft=%s", tnow(), nameof(init), e.weapon:getTypeName(), nameof(tgt),
        tp and string.format("%.1f", nm(ip, tp)) or "?", tp and string.format("%.0f", tp.y / 0.3048) or "?", tp and string.format("%.0f", agl_ft(tp)) or "?"))
    elseif id == world.event.S_EVENT_HIT then
      local tgt, w = e.target, e.initiator
      local wn = (e.weapon and e.weapon:getTypeName()) or (w and w.getTypeName and w:getTypeName()) or "?"
      local tp = tgt and tgt:isExist() and tgt:getPoint() or nil
      local sp = site_pt()
      local pr = pair_of(nameof(tgt))
      if pr then stats[pr].hit = stats[pr].hit + 1 end
      say(string.format("HIT t=%s weapon=%s target=%s slant_nm=%s tgt_msl_ft=%s tgt_agl_ft=%s", tnow(), wn, nameof(tgt), (tp and sp) and string.format("%.1f", nm(sp, tp)) or "?",
        tp and string.format("%.0f", tp.y / 0.3048) or "?", tp and string.format("%.0f", agl_ft(tp)) or "?"))
    elseif world.event.S_EVENT_KILL and id == world.event.S_EVENT_KILL then
      local pr = pair_of(nameof(e.target)); if pr then stats[pr].kill = stats[pr].kill + 1 end
      say(string.format("KILL t=%s by=%s target=%s", tnow(), nameof(e.initiator), nameof(e.target)))
    elseif id == world.event.S_EVENT_DEAD then
      if pair_of(nameof(e.initiator)) then say(string.format("DEAD t=%s unit=%s", tnow(), nameof(e.initiator))) end
    end
  end)
  if not ok then say("handler error: " .. tostring(err)) end
end
world.addEventHandler(H)

local function tick(_, t)
  local sp = site_pt()
  if sp then
    for _, p in ipairs(PAIRS) do
      local lead = Unit.getByName("Probe " .. p .. " 1-1")
      if lead and lead:isExist() then
        local lp = lead:getPoint(); local r = nm(sp, lp)
        if r < 200 and (math.floor(t) % 30) < 5 then
          say(string.format("TRACK t=%s %s lead slant_nm=%.1f msl_ft=%.0f agl_ft=%.0f", tnow(), p, r, lp.y / 0.3048, agl_ft(lp)))
        end
      end
    end
    local g = Group.getByName(SITE)
    local c = g and g:getController()
    if c then
      local okd, list = pcall(function() return c:getDetectedTargets(Controller.Detection.RADAR) end)
      if okd and type(list) == "table" then
        for _, d in ipairs(list) do
          local o = d.object
          local pr = pair_of(nameof(o))
          if pr and not stats[pr].detect then
            local op = o:getPoint(); stats[pr].detect = nm(sp, op)
            say(string.format("DETECT t=%s target=%s slant_nm=%.1f tgt_agl_ft=%.0f", tnow(), nameof(o), stats[pr].detect, agl_ft(op)))
          end
        end
      end
    end
  end
  return t + 5
end
timer.scheduleFunction(tick, nil, timer.getTime() + 5)

timer.scheduleFunction(function()
  for _, p in ipairs(PAIRS) do
    local s = stats[p]
    say(string.format("SUMMARY %s detect_nm=%s shots=%d first_shot_nm=%s last_shot_nm=%s hits=%d kills=%d", p, s.detect and string.format("%.1f", s.detect) or "none", s.shot,
      s.first_shot and string.format("%.1f", s.first_shot) or "none", s.last_shot and string.format("%.1f", s.last_shot) or "none", s.hit, s.kill))
  end
end, nil, timer.getTime() + 4800)
say("armed: site " .. SITE .. ", pairs " .. table.concat(PAIRS, " "))
'''


def _point(m, x: float, y: float):
    from dcs import mapping
    return mapping.Point(x, y, m.terrain)


def _along(bearing_deg: float, dist_m: float) -> tuple:
    b = math.radians(bearing_deg)
    return SITE[0] + dist_m * math.cos(b), SITE[1] + dist_m * math.sin(b)


def _build(out: Path) -> Path:
    from dcs import planes, task, vehicles
    from dcs.action import DoScript
    from dcs.mission import Mission, StartType
    from dcs.terrain import Syria
    from dcs.translation import String
    from dcs.triggers import TriggerStart
    m = Mission(Syria())
    m.start_time = datetime.datetime(2026, 6, 21, 12, 0)
    blue, red = m.country("USA"), m.country("Syria")
    # the site: launchers in a ring round two radars
    sx, sy = SITE
    pos = [("Search", vehicles.AirDefence.RLS_19J6, sx + 25, sy), ("Track", vehicles.AirDefence.RPC_5N62V, sx - 25, sy)]
    pos += [(f"Launcher {i + 1}", vehicles.AirDefence.S_200_Launcher, sx + 90 * math.cos(math.radians(60 * i)), sy + 90 * math.sin(math.radians(60 * i))) for i in range(6)]
    vg = None
    for nm_, typ, x, y in pos:
        if vg is None:
            vg = m.vehicle_group(red, "SA5 Site", typ, _point(m, x, y), heading=0, group_size=1)
            vg.units[0].name = f"SA5 {nm_}"
            continue
        v = m.vehicle(f"SA5 {nm_}", typ)
        v.position.x, v.position.y, v.heading = x, y, 0
        vg.add_unit(v)
    # the Search radar first so DCS names the group by it; units keep their own names
    for i, (label, agl_ft, brg, radar_alt, step_nm) in enumerate(PAIRS):
        alt_m = agl_ft * FT if radar_alt else agl_ft * FT + SITE_GROUND_M
        sp = _along(brg, START_NM * NM)
        g = m.flight_group(blue, f"Probe {label}", planes.F_16C_50, None, _point(m, *sp), altitude=alt_m, speed=SPEED_KT * 1.852, maintask=task.CAP, group_size=2)
        g.start_time = i * STAGGER_S
        for k, u in enumerate(g.units):
            u.name = f"Probe {label} 1-{k + 1}"
            u.pylons = {}
        for d_nm in [START_NM - j * step_nm for j in range(1, int(START_NM / step_nm) + 1)] + [-BEYOND_NM]:      # distance from the site (negative = past it): every step_nm to the site, then 40 nm beyond
            p = _along(brg, d_nm * NM)
            wp = g.add_waypoint(_point(m, *p), alt_m, SPEED_KT * 1.852, f"{label} {d_nm:.0f}")
            wp.alt_type = "RADIO" if radar_alt else "BARO"
        if radar_alt:
            g.points[0].alt_type = "RADIO"
        g.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponHold))
        g.points[0].tasks.append(task.OptReactOnThreat(task.OptReactOnThreat.Values.NoReaction))
        g.points[0].tasks.append(task.OptECMUsing(task.OptECMUsing.Values.NeverUse))
    slot = m.flight_group_from_airport(blue, "Probe slot", planes.F_16C_50, m.terrain.airports["Incirlik"], group_size=1, start_type=StartType.Cold)
    slot.units[0].set_client()
    t = TriggerStart(comment="SQE SA-5 probe")
    t.add_action(DoScript(String(SA5_LUA)))
    m.triggerrules.triggers.append(t)
    m.set_sortie_text("SQE SA-5 range probe")
    m.set_description_text("SA-5 range probe: four F-16C pairs (35,000 / 20,000 / 5,000 / 500 ft AGL, 12 minutes apart) fly at one SA-5 site from 180 nm, weapons hold, no ECM, no reaction. "
                           "Sit in the Incirlik slot, Ctrl+Z to speed up, after about 75 minutes send dcs.log (grep SQESA5).")
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    return out


def build(out) -> Path:
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated livery files
        return _build(Path(out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["make"])
    ap.add_argument("out")
    a = ap.parse_args()
    p = build(a.out)
    print(f"wrote {p}: copy to C:\\Users\\<you>\\Saved Games\\DCS\\Missions\\Probes, fly it (the Incirlik slot), Ctrl+Z, send dcs.log after about 75 minutes (grep SQESA5)")


if __name__ == "__main__":
    main()
