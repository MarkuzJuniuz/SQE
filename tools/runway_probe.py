"""Runway-cratering probe (XO 2026-11-03, queue idea "disable runways"): what does a bombed runway do to AI aircraft in DCS?

Builds one Caucasus mission around Senaki-Kolkhi (a blue field). Red Su-24Ms (SQE's own raid loadout and RunwayAttack task, two groups of four) bomb its runway
about 5 to 6 minutes in. Blue F-16C pairs wait on the ramp or arrive in the air and are released at set times, so the log shows when the field is closed and when it opens:
  * RWY-TO-A   takeoff at   2 min   (before the bombs: the control, it must leave normally)
  * RWY-TO-B   takeoff at  10 min   (after the bombs)
  * RWY-LD-1   lands    at  12 min   (arrives from 25 nm east: can AI land on a cratered runway?)
  * RWY-TO-C   takeoff at  30 min
  * RWY-TO-D   takeoff at  55 min   (inside the 60 minutes the forum threads report for a closed runway)
  * RWY-TO-E   takeoff at  70 min   (after them)
  * RWY-LD-2   lands    at  71 min
A mission-start script logs to dcs.log (lines start with `SQERWY`): every event of the RWY- aircraft (birth, engine start, takeoff, land, shot, hit, dead, crash), and every
20 s each RWY- group's lead (position, ground speed, in air or not, distance from the field), so a pair that sits on the ramp shows speed 0 for as long as it is stuck.
The player slot is an immortal F-16C in the air west of the field with unlimited fuel, only to watch (F2 / external views, or Tacview). Time acceleration (Ctrl-Z) shortens the wait.
Nothing here changes a campaign. Sources for the expectation (forum.dcs.world threads 160589 and 290358, medium firmness): a bomb on the runway or a path taxiway closes the
field for about 60 minutes whatever the damage, and AI then stop on the ground; nothing found on landing.

How XO runs it: python tools/runway_probe.py OUT.miz -> Fly it, let it run about 75 minutes of mission time (accelerate), send dcs.log (grep SQERWY)."""
from __future__ import annotations

import datetime
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIELD = "Senaki-Kolkhi"
NM = 1852.0
FT = 0.3048
KT = 0.514444 * 3.6                      # pydcs speeds are km/h
BOMB_START_NM = 40                       # the raiders appear this far east of the field (about 5 minutes at 450 kt)
WAVES = [                                # (group, kind, activation time in s)
    ("RWY-TO-A", "takeoff", 120),
    ("RWY-TO-B", "takeoff", 600),
    ("RWY-LD-1", "land", 720),
    ("RWY-TO-C", "takeoff", 1800),
    ("RWY-TO-D", "takeoff", 3300),
    ("RWY-TO-E", "takeoff", 4200),
    ("RWY-LD-2", "land", 4260),
]

PROBE_LUA = r'''
-- SQE runway probe: logs how the RWY- aircraft behave around a bombed runway (SQERWY lines in dcs.log)
local FIELD = "__FIELD__"
local NAMES = __NAMES__
local function say(s) env.info("SQERWY " .. s) end
local ab = Airbase.getByName(FIELD)
local fx, fz = 0, 0
if ab then local p = ab:getPoint(); fx, fz = p.x, p.z end
say(string.format("start: field=%s exists=%s coalition=%s", FIELD, tostring(ab ~= nil), ab and tostring(ab:getCoalition()) or "n/a"))
if ab then
  for _, fn in ipairs({"getLife", "getLife0", "getCategory", "getRunways", "isExist"}) do
    if ab[fn] then local ok, r = pcall(function() return ab[fn](ab) end); say("airbase:" .. fn .. " -> " .. (ok and tostring(r) or ("error " .. tostring(r)))) else say("airbase:" .. fn .. " missing") end
  end
end
local EV = {}
for _, n in ipairs({"BIRTH", "ENGINE_STARTUP", "ENGINE_SHUTDOWN", "TAKEOFF", "LAND", "SHOT", "HIT", "KILL", "DEAD", "CRASH", "EJECTION", "RUNWAY_TAKEOFF", "RUNWAY_TOUCH", "UNIT_LOST", "BASE_CAPTURED"}) do
  local id = world.event["S_EVENT_" .. n]; if id then EV[id] = n end
end
local H = {}
function H:onEvent(e)
  local nm = EV[e.id]; if not nm then return end
  local ini = e.initiator
  local uname = ""
  if ini and ini.getName then local ok, r = pcall(function() return ini:getName() end); uname = ok and tostring(r) or "" end
  if string.sub(uname, 1, 4) ~= "RWY-" then return end
  local place = ""
  if e.place and e.place.getName then local ok, r = pcall(function() return e.place:getName() end); place = ok and tostring(r) or "" end
  say(string.format("t=%d event=%s unit=%s place=%s", math.floor(timer.getTime()), nm, uname, place))
end
world.addEventHandler(H)
local function poll()
  for _, gn in ipairs(NAMES) do
    local g = Group.getByName(gn)
    if g and g:isExist() then
      local u = g:getUnit(1)
      if u and u:isExist() then
        local p, v = u:getPoint(), u:getVelocity()
        local sp = math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
        say(string.format("t=%d grp=%s alive=%d pos=(%.0f,%.0f) alt_m=%.0f speed_ms=%.1f inair=%s dist_nm=%.1f", math.floor(timer.getTime()), gn, g:getSize(),
          p.x, p.z, p.y, sp, tostring(u:inAir()), math.sqrt((p.x - fx)^2 + (p.z - fz)^2) / 1852))
      end
    end
  end
  return timer.getTime() + 20
end
timer.scheduleFunction(poll, nil, timer.getTime() + 20)
trigger.action.outText("SQE runway probe running: RWY-BOMB attacks " .. FIELD .. " in about 5 minutes. Accelerate time; send dcs.log (SQERWY lines).", 60)
'''


def _pt(m, x, y):
    from dcs import mapping
    return mapping.Point(x, y, m.terrain)


def make_probe(out_path) -> Path:
    import contextlib
    import io
    import logging
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    from dcs import action, condition, planes, task, triggers
    from dcs.mission import Mission, StartType
    from dcs.translation import String
    from sqe import theatres
    from sqe.loadouts import enemy_strike_loadout
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        m = Mission(theatres.terrain())
        m.start_time = datetime.datetime(2004, 6, 12, 12, 0)
        usa, ru = m.country("USA"), m.country("Russia")
        ap = m.terrain.airports[FIELD]
        ap.set_blue()
        fx, fy = ap.position.x, ap.position.y
        at = lambda brg, nm: (fx + nm * NM * math.cos(math.radians(brg)), fy + nm * NM * math.sin(math.radians(brg)))   # DCS: x north, y east

        # ---- the raiders: two groups of four Su-24M, SQE's own raid loadout and runway-attack task, coming in from the east
        load = enemy_strike_loadout("Su_24M")
        for k in range(2):
            sx, sy = at(90, BOMB_START_NM + 6 * k)
            g = m.flight_group(ru, f"RWY-BOMB-{k + 1}", planes.Su_24M, None, _pt(m, sx, sy), altitude=9000 * FT, speed=450 * KT, maintask=task.RunwayAttack, group_size=4)
            w = g.add_waypoint(_pt(m, fx, fy), 9000 * FT, 450 * KT, "RUNWAY")
            w.tasks.append(task.BombingRunway(airport_id=ap.id))
            ex, ey = at(270, 35)
            g.add_waypoint(_pt(m, ex, ey), 12000 * FT, 450 * KT, "EGRESS")
            g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
            g.points[0].tasks.append(task.SetImmortalCommand(True))          # v0.41.253: the probe measures the runway, so the raiders cannot be shot down
            for j, u in enumerate(g.units, 1):
                u.name = f"RWY-BOMB-{k + 1}-{j}"
                u.pylons = {i: dict(v) for i, v in load.items()}
            if k:
                g.late_activation = True
                t = triggers.TriggerOnce(comment="second raid group")
                t.add_condition(condition.TimeAfter(60))
                t.add_action(action.ActivateGroup(g.id))
                m.triggerrules.triggers.append(t)

        # ---- the blue pairs: takeoff waves from the ramp, landing waves from the air
        for name, kind, when in WAVES:
            if kind == "takeoff":
                g = m.flight_group_from_airport(usa, name, planes.F_16C_50, ap, maintask=task.CAP, start_type=StartType.Warm, group_size=2)
                cx, cy = at(270, 30)
                g.add_waypoint(_pt(m, cx, cy), 10000 * FT, 400 * KT, "CAP")
                g.land_at(ap)
            else:
                sx, sy = at(90, 25)
                g = m.flight_group(usa, name, planes.F_16C_50, None, _pt(m, sx, sy), altitude=6000 * FT, speed=350 * KT, maintask=task.CAP, group_size=2)
                g.land_at(ap)
            g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
            g.points[0].tasks.append(task.OptROE(task.OptROE.Values.WeaponHold))          # v0.41.253: the victims never engage the raiders
            g.points[0].tasks = [t_ for t_ in g.points[0].tasks if getattr(t_, "Id", "") not in ("EngageTargets",)]
            for j, u in enumerate(g.units, 1):
                u.name = f"{name}-{j}"
            g.late_activation = True
            t = triggers.TriggerOnce(comment=f"release {name}")
            t.add_condition(condition.TimeAfter(when))
            t.add_action(action.ActivateGroup(g.id))
            m.triggerrules.triggers.append(t)

        # ---- the watcher: an immortal F-16C west of the field, only to look from
        wx, wy = at(270, 15)
        g = m.flight_group(usa, "RWY watcher", planes.F_16C_50, None, _pt(m, wx, wy), altitude=15000 * FT, speed=350 * KT, maintask=task.CAP, group_size=1)
        g.units[0].set_client()
        g.add_waypoint(_pt(m, *at(270, 10)), 15000 * FT, 350 * KT, "WATCH")
        g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
        g.points[0].tasks.append(task.SetImmortalCommand(True))

        names = ["RWY-BOMB-1", "RWY-BOMB-2"] + [n for n, _k, _t in WAVES]
        lua = PROBE_LUA.replace("__FIELD__", FIELD).replace("__NAMES__", "{" + ",".join(f'"{n}"' for n in names) + "}")
        t = triggers.TriggerStart(comment="SQE runway probe")
        t.add_action(action.DoScript(String(lua)))
        m.triggerrules.triggers.append(t)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(out))
    return out


if __name__ == "__main__":
    p = make_probe(sys.argv[1] if len(sys.argv) > 1 else "SQE_runway_probe.miz")
    print(f"wrote {p}: Fly it, accelerate time for about 75 minutes of mission time, send dcs.log (grep SQERWY)")
