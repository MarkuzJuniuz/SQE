"""Call-in probe, version 4 (XO 2026-10-22): can a CAP pair be jumped to a hotspot leg of its route when called, and come back?

Run 3 showed the flag-released route works (V3: flew to the hotspot, orbited, flew home) but a pair that is NOT called would also fly the hotspot leg when
its shift ends. So this version tests three ways to jump a pair to a waypoint ONLY when it is called. Every pair has the same route:
  1 spawn (8 nm short), 2 STATION (racetrack orbit), 3 STATION2, 4 END (60 nm west: stands in for the landing), 5 HOTSPOT (orbit 240 s), 6 BACK (orbit).
  V0 = control, never called (should stay on its racetrack).
  V4 = at t = 60 s Lua `SwitchWaypoint` command, from waypoint 2 to waypoint 5.
  V5 = at t = 60 s a pushed `GoToWaypoint` task (AITaskPush), from 2 to 5.
  V6 = like V4 but with a wrong `from` (waypoint 1): does `from` matter?
Every 20 s each pair logs `SQEPROBE2 t=<s> <name> dS=<nm from its station> dH=<nm from its hotspot> hdg=<deg> n=<jets>` to dcs.log.
XO: start the mission, let it run about 18 minutes (time acceleration is fine), send dcs.log (grep SQEPROBE2).
Usage: python tools/callin_probe.py OUT_DIR"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from dcs import action, condition, mapping, planes, task, triggers
from dcs.mission import Mission, StartType
from dcs.terrain import caucasus
from dcs.translation import String
from dcs.unit import Skill

NM = 1852.0
ALT, SPD = 6700.0, 780.0                       # 22,000 ft, 780 km/h (pydcs wants km/h; the orbit action wants m/s)
SPD_MS = int(SPD / 3.6)


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    m = Mission(caucasus.Caucasus())
    m.start_time = datetime.datetime(2006, 6, 12, 9, 0)
    red, blue = m.country("Russia"), m.country("USA")
    ap = m.terrain.airports["Kutaisi"]
    ax, ay = ap.position.x, ap.position.y
    pt = lambda x, y: mapping.Point(x, y, m.terrain)
    p = m.flight_group_from_airport(blue, "Probe Player", planes.F_16C_50, ap, maintask=task.CAP, start_type=StartType.Cold, group_size=1)
    p.units[0].skill = Skill.Player
    names = {}
    for i, key in enumerate(("V0", "V4", "V5", "V6")):
        sx, sy = ax + 60 * NM * (i - 1.5), ay + 20 * NM          # stations 60 nm apart, north-south
        hx, hy = sx, sy + 40 * NM                             # hotspot 40 nm east of the station
        names[key] = (sx, sy, hx, hy)
        # the bait: an immortal tanker the AI cannot see, on the hotspot (marks the place)
        t = m.flight_group(blue, f"BAIT-{key}", planes.KC_135, None, pt(hx, hy), altitude=ALT, speed=SPD, maintask=task.Refueling)
        ot = task.ControlledTask(task.OrbitAction(int(ALT), SPD_MS)); ot.stop_after_time(7200)
        t.add_waypoint(pt(hx, hy), ALT, SPD, "BAIT").tasks.append(ot)
        t.points[0].tasks.append(task.SetImmortalCommand(True))
        t.points[0].tasks.append(task.SetInvisibleCommand(True))
        g = m.flight_group(red, f"PROBE-{key}", planes.Su_27, None, pt(sx, sy - 8 * NM), altitude=ALT, speed=SPD, maintask=task.CAP, group_size=2)
        g.set_skill(Skill.High)
        g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
        o1 = task.ControlledTask(task.OrbitAction(int(ALT), SPD_MS)); o1.stop_after_time(7200)
        g.add_waypoint(pt(sx, sy), ALT, SPD, "STATION").tasks.append(o1)                  # waypoint 2
        g.add_waypoint(pt(sx, sy + 20 * NM), ALT, SPD, "STATION2")                        # 3
        g.add_waypoint(pt(sx, sy - 60 * NM), ALT, SPD, "END")                             # 4
        o2 = task.ControlledTask(task.OrbitAction(int(ALT), SPD_MS)); o2.stop_after_time(240)
        g.add_waypoint(pt(hx, hy), ALT, SPD, "HOTSPOT").tasks.append(o2)                  # 5
        o3 = task.ControlledTask(task.OrbitAction(int(ALT), SPD_MS)); o3.stop_after_time(7200)
        g.add_waypoint(pt(sx, sy), ALT, SPD, "BACK").tasks.append(o3)                     # 6
        tr = triggers.TriggerOnce(comment=f"call in {key}")
        tr.add_condition(condition.TimeAfter(60))
        if key in ("V4", "V6"):
            frm = 2 if key == "V4" else 1
            tr.add_action(action.DoScript(String(
                f"local g=Group.getByName('PROBE-{key}'); g:getController():setCommand({{id='SwitchWaypoint',params={{fromWaypointIndex={frm},goToWaypointIndex=5}}}}); "
                f"env.info('SQEPROBE2 command sent PROBE-{key}')")))
        elif key == "V5":
            g.add_trigger_action(task.GoToWaypoint(2, 5))
            tr.add_action(action.AITaskPush(g.id, 1))
        if key != "V0":
            m.triggerrules.triggers.append(tr)
    pts = ",".join(f'{{"PROBE-{k}",{v[0]:.0f},{v[1]:.0f},{v[2]:.0f},{v[3]:.0f}}}' for k, v in names.items())
    lua = ("SQEP={" + pts + "};"
           "function SQEP_log() for _,r in ipairs(SQEP) do local g=Group.getByName(r[1]); local n=0; local ds,dh,hd=-1,-1,-1;"
           "if g and g:isExist() then local u=g:getUnit(1); n=g:getSize(); if u then local q=u:getPoint(); local o=u:getPosition().x; hd=math.deg(math.atan2(o.z,o.x))%360;"
           "ds=math.sqrt((q.x-r[2])^2+(q.z-r[3])^2)/1852; dh=math.sqrt((q.x-r[4])^2+(q.z-r[5])^2)/1852 end end;"
           "env.info(string.format('SQEPROBE2 t=%d %s dS=%.0f dH=%.0f hdg=%.0f n=%d',timer.getTime(),r[1],ds,dh,hd,n)) end return timer.getTime()+20 end;"
           "timer.scheduleFunction(SQEP_log,nil,timer.getTime()+5)")
    st = triggers.TriggerOnce(comment="probe log"); st.add_condition(condition.TimeAfter(1)); st.add_action(action.DoScript(String(lua)))
    m.triggerrules.triggers.append(st)
    m.set_description_text("Call-in probe. AI only: three red pairs (and a control that is not) are called to a hotspot at t=60 s. Let it run 18 minutes, then send dcs.log (grep SQEPROBE2).")
    path = out_dir / "Callin_Probe.miz"
    m.save(str(path))
    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    print(build(Path(sys.argv[1])))
