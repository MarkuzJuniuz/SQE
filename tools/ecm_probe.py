"""ECM switch probe (XO 2026-10-28): can the mission, or DCS's Export environment, tell that the player's ECM is on?

Two parts (see also tools/ecm_export_logger.lua, the discovery logger):
  1. This script builds one tiny Caucasus mission per jet (a single Player slot at Kutaisi, hot start, a red SA-6 site 30 km away for the "does DCS
     jam on its own" flight). The mission holds
       * Mission Editor "cockpit parameter" triggers for a list of CANDIDATE parameter names (we do not know the real ones per module). For each name
         a flag-gated edge trigger fires once per CHANGE of the value's band (ZERO / LOW / MID / HIGH / OTHER) as an on-screen message and a dcs.log line:
         `SQEPROBE PARAM <name> band <band>`; a name that never fires is not a real parameter for this jet;
       * a side-test script (mission scripting environment) that every 2 s samples the player's jet: every external draw argument 0..999
         (`getDrawArgumentValue`), `getRadar()`, `getSensors()` and `getAmmo()`, and logs CHANGES: `SQEPROBE DRAWARG`, `SQEPROBE RADAR`,
         `SQEPROBE SENSORS`, `SQEPROBE AMMO`. Expect nothing for an ECM pod; it is a cheap check.
  2. tools/ecm_export_logger.lua is the discovery tool: it logs EVERY cockpit parameter that changes (through `list_cockpit_params()`), with a time,
     so pressing the ECM binding shows which parameter that button moves, with no guessing.
How XO runs it: fly each jet, follow the protocol printed in the mission briefing (toggle ECM on, wait 10 s, off, wait 10 s, three times; then press
other ECM-panel buttons one at a time and note what you pressed, in order), then send dcs.log (grep SQEPROBE) and, if the Export logger is installed,
Saved Games\\DCS\\Logs\\SQE_cockpit_changes.log.
Usage:  python tools/ecm_probe.py OUT_DIR            (all jets)     python tools/ecm_probe.py OUT_DIR f15 a10
Public source for the idea: the ME conditions "Cockpit Parameter is in range / equal to" (pydcs `CockpitParamInRange`). Nothing here is verified in DCS yet."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from dcs import action, condition, mapping, planes, task, triggers, vehicles
from dcs.mission import Mission, StartType
from dcs.terrain import caucasus
from dcs.translation import String
from dcs.unit import Skill

JETS = {"f16": ("F-16C", planes.F_16C_50), "fa18": ("FA-18C", planes.FA_18C_hornet), "f14": ("F-14B", planes.F_14B),
        "a10": ("A-10C", planes.A_10C_2), "f15": ("F-15C", planes.F_15C)}
# Guesses only: DCS-BIOS-style names do not carry over to the ME's cockpit parameters, and ME parameter names are not published per module.
CANDIDATES = [
    "ECM_SW", "ECM_MODE", "ECM_POWER", "ECM_PWR", "ECM_STBY", "ECM_POD", "ECM_SELECT", "ECM_STATUS", "ECM_LIGHT", "ECM_PANEL", "ECM_JAMMER", "ECM_ON",
    "ECM", "ECMPOD", "ECM_POD_MODE", "ECM_POD_PWR", "JAMMER", "JAMMER_ON", "JAMMER_MODE", "JAM_ON", "ALQ_STATUS", "ALQ_MODE", "ALQ_POWER", "ALQ131", "ALQ_131",
    "ALQ_131_MODE", "ALQ_131_PWR", "ALQ_184", "ALQ_184_MODE", "ALQ_165", "ALQ_135", "ALQ_135_MODE", "ASPJ", "ASPJ_MODE", "ASPJ_PWR", "ASPJ_ECM", "EWMS", "EWMS_MODE",
    "EW_ECM", "EWS_ECM", "EWS_MODE", "EWS_PWR", "TEWS", "TEWS_MODE", "TEWS_ECM", "INTERNAL_ECM", "INT_ECM", "DECM", "DECM_MODE", "ECM_PRG", "RWR_ECM", "CMS_ECM",
    "ECM_AUTO", "ECM_REC", "ECM_XMIT", "ECM_TRANSMIT", "TRANSMIT", "XMIT", "ECM_XMIT_SW", "ECM_JETT", "ECM_DISPENSE"]
BANDS = [("ZERO", -0.05, 0.05), ("LOW", 0.05, 0.4), ("MID", 0.4, 0.8), ("HIGH", 0.8, 1.5), ("OTHER", 1.5, 1e9)]

SIDE_TEST_LUA = r'''
local pname = "%(unit)s"
local last, lastr, lasts, lasta = {}, nil, nil, nil
local function dump(t, d)
  if type(t) ~= "table" then return tostring(t) end
  if (d or 0) > 3 then return "{...}" end
  local keys = {}
  for k in pairs(t) do keys[#keys + 1] = tostring(k) end
  table.sort(keys)
  local out = {}
  for _, k in ipairs(keys) do
    local v = t[k]; if v == nil then v = t[tonumber(k)] end
    out[#out + 1] = k .. "=" .. dump(v, (d or 0) + 1)
  end
  return "{" .. table.concat(out, ",") .. "}"
end
local function scan()
  local u = Unit.getByName(pname)
  if u and u:isExist() then
    for a = 0, 999 do
      local ok, v = pcall(u.getDrawArgumentValue, u, a)
      if ok and type(v) == "number" then
        v = math.floor(v * 1000 + 0.5) / 1000
        if last[a] ~= nil and last[a] ~= v then env.info("SQEPROBE DRAWARG " .. a .. " " .. last[a] .. " -> " .. v) end
        last[a] = v
      end
    end
    local okr, r1, r2 = pcall(u.getRadar, u)
    local rs = okr and (tostring(r1) .. " | " .. dump(r2)) or ("error " .. tostring(r1))
    if rs ~= lastr then env.info("SQEPROBE RADAR " .. rs); lastr = rs end
    local oks, s = pcall(u.getSensors, u)
    local ss = oks and dump(s) or ("error " .. tostring(s))
    if ss ~= lasts then env.info("SQEPROBE SENSORS " .. ss); lasts = ss end
    local oka, am = pcall(u.getAmmo, u)
    local as = oka and dump(am) or ("error " .. tostring(am))
    if as ~= lasta then env.info("SQEPROBE AMMO " .. as); lasta = as end
  end
  return timer.getTime() + 2
end
timer.scheduleFunction(scan, nil, timer.getTime() + 5)
env.info("SQEPROBE side-test script started for " .. pname)
'''

PROTOCOL = ("ECM probe, {label}. WARM START at Kutaisi (cold ramp, systems powered up by you). Fly or sit on the ramp, it does not matter. PROTOCOL: (1) 60 s with nothing touched. (2) ECM ON, wait 10 s, "
            "ECM OFF, wait 10 s; three times. (3) Then press each other button on the ECM / EW panel ONE at a time with 10 s between, and write down the order "
            "you pressed them. (4) Optional: climb, head for the red SA-6 site 30 km NE of Kutaisi with ECM on, then repeat with ECM off, and note if it fired. "
            "Send dcs.log (lines with SQEPROBE) and Saved Games\\DCS\\Logs\\SQE_cockpit_changes.log if the Export logger is installed.")


def build(key: str, out_dir: Path) -> Path:
    label, cls = JETS[key]
    out_dir.mkdir(parents=True, exist_ok=True)
    m = Mission(caucasus.Caucasus())
    m.start_time = datetime.datetime(2006, 6, 12, 9, 0)
    blue, red = m.country("USA"), m.country("Russia")
    ap = m.terrain.airports["Kutaisi"]
    g = m.flight_group_from_airport(blue, f"Probe {label}", cls, ap, maintask=task.CAP, start_type=StartType.Warm, group_size=1)
    g.units[0].skill = Skill.Player
    g.units[0].name = f"Probe {label} 1-1"
    sx, sy = ap.position.x + 21000, ap.position.y + 21000
    types = [vehicles.AirDefence.Kub_1S91_str, vehicles.AirDefence.Kub_2P25_ln, vehicles.AirDefence.Kub_2P25_ln, vehicles.AirDefence.Kub_2P25_ln]
    m.vehicle_group_platoon(red, "Probe SA-6", types, mapping.Point(sx, sy, m.terrain), heading=0)

    flag = [200]

    def edge(text, conds, extra_cond, extra_action):
        t = triggers.TriggerContinious(comment=text)           # fires on every CHANGE (flag-gated), not once
        for c in conds + [extra_cond]:
            t.add_condition(c)
        t.add_action(action.MessageToAll(String(text), 6))
        t.add_action(action.DoScript(String(f'env.info("SQEPROBE {text}")')))
        t.add_action(extra_action)
        m.triggerrules.triggers.append(t)

    for name in CANDIDATES:
        for band, lo, hi in BANDS:
            f = flag[0]; flag[0] += 1
            edge(f"PARAM {name} band {band}", [condition.CockpitParamInRange(name, f"{lo}", f"{hi}")], condition.FlagIsFalse(f), action.SetFlag(f))
            # clear the flag when the value leaves this band (below or above it), so a return to the band fires again
            for side, (clo, chi) in (("below", (-1e9, lo)), ("above", (hi, 1e9))):
                t = triggers.TriggerContinious(comment=f"clear {name} {band} {side}")
                t.add_condition(condition.FlagIsTrue(f))
                t.add_condition(condition.CockpitParamInRange(name, f"{clo}", f"{chi}"))
                t.add_action(action.ClearFlag(f))
                m.triggerrules.triggers.append(t)

    st = triggers.TriggerOnce(comment="side tests")
    st.add_condition(condition.TimeAfter(3))
    st.add_action(action.DoScript(String(SIDE_TEST_LUA % {"unit": g.units[0].name})))
    st.add_action(action.MessageToAll(String(f"ECM probe: side-test script started. {PROTOCOL.format(label=label)[:230]}"), 25))
    m.triggerrules.triggers.append(st)
    m.set_description_text(PROTOCOL.format(label=label))
    path = out_dir / f"ECM_Probe_{label}.miz"
    m.save(str(path))
    return path


def main(argv) -> int:
    if not argv:
        print(__doc__); return 2
    out = Path(argv[0])
    keys = argv[1:] or list(JETS)
    for k in keys:
        print(build(k, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
