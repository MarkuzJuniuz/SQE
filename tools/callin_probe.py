"""Call-in probe (XO 2026-10-22): can a CAP pair be sent to a hotspot and come back to its station?

One AI-only test mission (plus a parked Player slot so DCS lets you start). Three red Su-27 pairs orbit on their own stations, each with an
immortal blue tanker orbiting on a "hotspot" 40 nm to the east. At t = 60 s the mission calls all three in, each a different way:
  V1 = pushed task: EngageTargetsInZone wrapped in a ControlledTask that stops after 240 s (AITaskPush), the pair should fly out, then resume its orbit.
  V2 = pushed task, plain EngageTargetsInZone (what the red SAM-guard call-in does today): does it ever come back?
  V3 = route: orbit waits on a flag; the flag releases it to a hotspot waypoint (orbit 240 s), then a waypoint back on the station.
Every 20 s each pair logs `SQEPROBE2 t=<s> <name> dS=<nm from its station> dH=<nm from its hotspot>` to dcs.log.
XO: start the mission, let it run about 12 minutes (time acceleration is fine), send dcs.log (grep SQEPROBE2).
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
ALT, SPD = 6700.0, 220.0                       # 22,000 ft, about 430 kt


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
    for i, (key, label) in enumerate((("V1", "pushed timed"), ("V2", "pushed plain"), ("V3", "route + flag"))):
        sx, sy = ax + 60 * NM * (i - 1), ay + 20 * NM          # stations 60 nm apart, north-south
        hx, hy = sx, sy + 40 * NM                             # hotspot 40 nm east of the station
        names[key] = (sx, sy, hx, hy)
        # the bait: an immortal tanker on the hotspot
        t = m.flight_group(blue, f"BAIT-{key}", planes.KC_135, None, pt(hx, hy), altitude=ALT, speed=SPD, maintask=task.Refueling)
        t.units[0].skill = Skill.High
        ot = task.ControlledTask(task.OrbitAction(int(ALT), int(SPD))); ot.stop_after_time(7200)
        t.add_waypoint(pt(hx, hy), ALT, SPD, "BAIT").tasks.append(ot)
        t.points[0].tasks.append(task.SetImmortalCommand(True))
        # the pair
        g = m.flight_group(red, f"PROBE-{key}", planes.Su_27, None, pt(sx, sy), altitude=ALT, speed=SPD, maintask=task.CAP, group_size=2)
        g.set_skill(Skill.High)
        g.points[0].tasks.append(task.SetUnlimitedFuelCommand(True))
        flag = 310 + i
        if key == "V3":
            o1 = task.ControlledTask(task.OrbitAction(int(ALT), int(SPD))); o1.stop_after_time(7200); o1.stop_if_user_flag(flag, True)
            g.add_waypoint(pt(sx, sy), ALT, SPD, "STATION").tasks.append(o1)
            o2 = task.ControlledTask(task.OrbitAction(int(ALT), int(SPD))); o2.stop_after_time(240)
            g.add_waypoint(pt(hx, hy), ALT, SPD, "HOTSPOT").tasks.append(o2)
            o3 = task.ControlledTask(task.OrbitAction(int(ALT), int(SPD))); o3.stop_after_time(7200)
            g.add_waypoint(pt(sx, sy), ALT, SPD, "BACK").tasks.append(o3)
            tr = triggers.TriggerOnce(comment="call in V3"); tr.add_condition(condition.TimeAfter(60)); tr.add_action(action.SetFlag(flag))
        else:
            o1 = task.ControlledTask(task.OrbitAction(int(ALT), int(SPD))); o1.stop_after_time(7200)
            g.add_waypoint(pt(sx, sy), ALT, SPD, "STATION").tasks.append(o1)
            g.add_waypoint(pt(sx, sy + 20 * NM), ALT, SPD, "STATION2")
            eng = task.EngageTargetsInZone(mapping.Vector2(hx, hy), int(25 * NM), [task.Targets.All.Air])
            if key == "V1":
                ct = task.ControlledTask(eng); ct.stop_after_time(240); g.add_trigger_action(ct)
            else:
                g.add_trigger_action(eng)
            tr = triggers.TriggerOnce(comment=f"call in {key}"); tr.add_condition(condition.TimeAfter(60)); tr.add_action(action.AITaskPush(g.id, 1))
        m.triggerrules.triggers.append(tr)
    pts = ",".join(f'{{"PROBE-{k}",{v[0]:.0f},{v[1]:.0f},{v[2]:.0f},{v[3]:.0f}}}' for k, v in names.items())
    lua = ("SQEP={" + pts + "};"
           "function SQEP_log() for _,r in ipairs(SQEP) do local g=Group.getByName(r[1]); local n=0; local ds,dh=-1,-1;"
           "if g and g:isExist() then local u=g:getUnit(1); n=g:getSize(); if u then local q=u:getPoint();"
           "ds=math.sqrt((q.x-r[2])^2+(q.z-r[3])^2)/1852; dh=math.sqrt((q.x-r[4])^2+(q.z-r[5])^2)/1852 end end;"
           "env.info(string.format('SQEPROBE2 t=%d %s dS=%.0f dH=%.0f n=%d',timer.getTime(),r[1],ds,dh,n)) end return timer.getTime()+20 end;"
           "timer.scheduleFunction(SQEP_log,nil,timer.getTime()+5)")
    st = triggers.TriggerOnce(comment="probe log"); st.add_condition(condition.TimeAfter(1)); st.add_action(action.DoScript(String(lua)))
    m.triggerrules.triggers.append(st)
    m.set_description_text("Call-in probe. AI only: three red pairs are called to a hotspot at t=60 s. Let it run 12 minutes, then send dcs.log (grep SQEPROBE2).")
    path = out_dir / "Callin_Probe.miz"
    m.save(str(path))
    return path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    print(build(Path(sys.argv[1])))
