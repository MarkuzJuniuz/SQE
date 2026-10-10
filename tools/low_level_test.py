"""Developer tool: builds SQE_LowLevelTest.miz, an AI-only mission that shows whether DCS AI really flies low-level waypoints over mountains.

Four AI flights of two F-16Cs start near Gudauta and fly north-east to Nalchik, straight across the main Caucasus ridge (4 parallel tracks 5 km apart):
  Low-Dense-500    waypoints every 12 km, 500 ft above the ground (DCS "radio" altitude)
  Low-Sparse-500   only a start, a middle and an end point, 500 ft above the ground (does it follow the terrain BETWEEN points?)
  Low-Dense-1000   waypoints every 12 km, 1,000 ft above the ground
  High-Control     20,000 ft above sea level: the control flight that should simply clear everything
A parked Su-25T (free with DCS World) at Sochi-Adler is your seat: spawn in, then use the F11 free camera or Tacview to watch.

A script in the mission measures the real ground under every aircraft every 5 seconds (land.getHeight) and reports height above ground, the lowest
approach, and any crash. It prints the summary on screen every 30 s and, when DCS scripting is not sanitized (SQE patches MissionScripting.lua while it is
open), appends every sample to <Saved Games>\\SQE\\SQE_lowtest_log.txt.

Usage: python tools/low_level_test.py [out.miz]
"""
from __future__ import annotations
import contextlib
import datetime
import io
import logging
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dcs import mapping, planes, task                                 # noqa: E402
from dcs.mission import Mission, StartType                            # noqa: E402
from dcs.planes import F_16C_50, Su_25T                               # noqa: E402
from dcs.translation import String                                    # noqa: E402
from dcs.triggers import TriggerStart                                 # noqa: E402
from dcs.action import DoScript                                       # noqa: E402

FT, KT = 0.3048, 1.852                                                # feet -> m, knots -> km/h
START_LL, END_LL = (43.10, 40.58), (43.51, 43.64)                     # Gudauta -> Nalchik: across the main ridge
SPACING_M, TRACK_OFFSET_M = 12_000.0, 5_000.0
FLIGHTS = [("Low-Dense-500", "RADIO", 500, True), ("Low-Sparse-500", "RADIO", 500, False),
           ("Low-Dense-1000", "RADIO", 1000, True), ("High-Control", "BARO", 20000, True)]

LUA = r'''
-- SQE low-level test: measures the real ground under each aircraft
local NAMES = { __NAMES__ }
local SX, SY, EX, EY = __SX__, __SY__, __EX__, __EY__
local LOG = nil
if io and lfs then
  lfs.mkdir(lfs.writedir() .. "SQE")
  LOG = lfs.writedir() .. "SQE\\SQE_lowtest_log.txt"
  local f = io.open(LOG, "w"); if f then f:write("t_s,flight,unit,x,y,alt_msl_ft,ground_ft,agl_ft,kts\n"); f:close() end
end
local FT = 3.28084
local function I(x) return math.floor(x + 0.5) end          -- whole numbers for %d (Lua 5.3+ refuses floats there)
local stat = {}
for _, n in ipairs(NAMES) do stat[n] = { minagl = 1e9, maxagl = -1e9, n = 0, lost = 0, last = "" } end
local lines = {}
local function say(s, t) trigger.action.outText(s, t or 20) end
-- what is the ground like along the route? (so the numbers below can be read against it)
local function route_profile()
  local d = math.sqrt((EX - SX) ^ 2 + (EY - SY) ^ 2)
  local steps, hi, hx, hy = math.floor(d / 1000), 0, 0, 0
  for i = 0, steps do
    local f = i / steps
    local x, y = SX + (EX - SX) * f, SY + (EY - SY) * f
    local h = land.getHeight({ x = x, y = y })
    if h > hi then hi, hx, hy = h, x, y end
  end
  say(string.format("Route Gudauta -> Nalchik: %d km, highest ground on the centre line %d m (%d ft).", I(d / 1000), I(hi), I(hi * FT)), 40)
end
local function sample()
  local t = timer.getTime()
  for _, n in ipairs(NAMES) do
    local g = Group.getByName(n)
    local s = stat[n]
    if g and g:isExist() then
      for _, u in ipairs(g:getUnits() or {}) do
        local p = u:getPoint()
        local gr = land.getHeight({ x = p.x, y = p.z })
        local agl = (p.y - gr) * FT
        local v = u:getVelocity()
        local kts = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z) * 1.94384
        s.n = s.n + 1
        if agl < s.minagl then s.minagl = agl end
        if agl > s.maxagl then s.maxagl = agl end
        s.last = string.format("now %d ft AGL, %d ft MSL, %d kt", I(agl), I(p.y * FT), I(kts))
        if LOG then
          local f = io.open(LOG, "a")
          if f then f:write(string.format("%d,%s,%s,%d,%d,%d,%d,%d,%d\n", I(t), n, u:getName(), I(p.x), I(p.z), I(p.y * FT), I(gr * FT), I(agl), I(kts))); f:close() end
        end
      end
    end
  end
  return t + 5
end
local function report()
  for _, n in ipairs(NAMES) do
    local s = stat[n]
    if s.n > 0 then
      say(string.format("%s: lowest %d ft AGL, highest %d ft AGL, %s%s", n, I(s.minagl), I(s.maxagl), s.last, s.lost > 0 and (", LOST " .. s.lost) or ""), 28)
    end
  end
  return timer.getTime() + 30
end
local H = {}
function H:onEvent(e)
  if e.id == world.event.S_EVENT_CRASH or e.id == world.event.S_EVENT_DEAD or e.id == world.event.S_EVENT_UNIT_LOST then
    local u = e.initiator
    if u and u.getGroup then
      local ok, g = pcall(function() return u:getGroup() end)
      if ok and g and stat[g:getName()] then
        local p = u:getPoint()
        local gr = land.getHeight({ x = p.x, y = p.z })
        stat[g:getName()].lost = stat[g:getName()].lost + 1
        say(string.format("%s LOST: %s at %d ft MSL, ground %d ft (%d ft above it), t=%d s", g:getName(), u:getName(), I(p.y * FT), I(gr * FT), I((p.y - gr) * FT), I(timer.getTime())), 60)
        if LOG then local f = io.open(LOG, "a"); if f then f:write(string.format("%d,%s,%s,LOST,,%d,%d,%d,\n", I(timer.getTime()), g:getName(), u:getName(), I(p.y * FT), I(gr * FT), I((p.y - gr) * FT))); f:close() end end
      end
    end
  end
end
world.addEventHandler(H)
timer.scheduleFunction(function() route_profile() end, nil, timer.getTime() + 3)
timer.scheduleFunction(function(_, t) return sample() end, nil, timer.getTime() + 5)
timer.scheduleFunction(function(_, t) return report() end, nil, timer.getTime() + 30)
say("SQE low-level test: four AI F-16 pairs fly Gudauta -> Nalchik across the main Caucasus ridge. Use F11 (free camera) or Tacview to watch.", 30)
'''


def build(out: Path) -> Path:
    import logging as _lg
    _lg.getLogger("pydcs").setLevel(_lg.CRITICAL)
    from dcs import terrain as T
    terr = T.Caucasus()
    P = lambda ll: mapping.Point.from_latlng(mapping.LatLng(*ll), terr)
    s, e = P(START_LL), P(END_LL)
    m = Mission(terr)
    m.start_time = datetime.datetime(2004, 6, 12, 9, 0)
    usa = m.country("USA")
    d = math.hypot(e.x - s.x, e.y - s.y)
    ux, uy = (e.x - s.x) / d, (e.y - s.y) / d                                     # along the route
    px, py = -uy, ux                                                              # across it
    hdg = math.degrees(math.atan2(uy, ux)) % 360
    names = []
    for k, (name, alt_type, alt_ft, dense) in enumerate(FLIGHTS):
        off = (k - 1.5) * TRACK_OFFSET_M
        pt = lambda f: mapping.Point(s.x + ux * d * f + px * off, s.y + uy * d * f + py * off, terr)
        n_legs = max(1, int(d // SPACING_M)) if dense else 2
        alt_m, spd = alt_ft * FT, 450 * KT
        g = m.flight_group(usa, name, F_16C_50, None, pt(0.0), altitude=alt_m, speed=spd, maintask=task.CAP, group_size=2)
        for u in g.units:
            u.heading = hdg
        g.points[0].alt_type = alt_type
        for i in range(1, n_legs + 1):
            wp = g.add_waypoint(pt(i / n_legs), alt_m, spd, f"{name} {i}")
            wp.alt_type = alt_type
        names.append(name)
    # your seat: a parked Su-25T at Sochi-Adler (free with DCS World)
    apt = terr.airports["Sochi-Adler"]
    seat = m.flight_group_from_airport(usa, "Observer", Su_25T, apt, group_size=1, start_type=StartType.Cold)
    seat.units[0].set_client()
    lua = (LUA.replace("__NAMES__", ", ".join(f'"{n}"' for n in names)).replace("__SX__", str(int(s.x))).replace("__SY__", str(int(s.y)))
           .replace("__EX__", str(int(e.x))).replace("__EY__", str(int(e.y))))
    t = TriggerStart(comment="SQE low-level test")
    t.add_action(DoScript(String(lua)))
    m.triggerrules.triggers.append(t)
    out.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        m.save(str(out))
    return out


if __name__ == "__main__":
    o = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("SQE_LowLevelTest.miz")
    print(build(o))
