"""A one-off DCS mission that measures the map. Fly it once (Fly > any slot): a script samples land.getSurfaceType over the whole
theatre and writes <Saved Games>\\SQE\\SQE_terrain_caucasus.json, which terrainmask.py reads. The mission has nothing in it but one
parked Su-25T (free with DCS World, like the Caucasus map); no Eagle Dynamics data is copied, only the answers DCS gives."""
from __future__ import annotations
from pathlib import Path

X0, X1, Y0, Y1, STEP = -430000, 70000, 190000, 970000, 250      # x north, y east: Black Sea coast to Mozdok, Maykop to Tbilisi

PROBE_LUA = r'''
-- SQE terrain probe: samples the surface type over the map and writes SQE_terrain_caucasus.json
if not (io and lfs) then
  trigger.action.outText("SQE terrain probe: io/lfs are sanitized. Start SQE (it patches MissionScripting.lua while open) or use Settings > patch, then restart this mission.", 90)
  return
end
local X0, Y0, STEP, NX, NY = __X0__, __Y0__, __STEP__, __NX__, __NY__
local DIR = lfs.writedir() .. "SQE"
lfs.mkdir(DIR)
local OUT = DIR .. "\\SQE_terrain_caucasus.json"
local ST = land.SurfaceType
local rows, nxt, per = {}, 0, 4
local H = STEP / 4
local OFFS = { {-H, -H}, {-H, H}, {H, -H}, {H, H} }
local function scan(i)
  local x = X0 + (i + 0.5) * STEP
  local out, prev, run = {}, nil, 0
  for j = 0, NY - 1 do
    -- four samples per cell (125 m apart) so that narrow rivers are not stepped over
    local c, y = "l", Y0 + (j + 0.5) * STEP
    for _, o in ipairs(OFFS) do
      local s = land.getSurfaceType({x = x + o[1], y = y + o[2]})
      if s == ST.WATER then c = "w" break
      elseif s == ST.SHALLOW_WATER then c = "s" end
    end
    if c == prev then run = run + 1 else
      if prev then out[#out + 1] = prev .. run end
      prev, run = c, 1
    end
  end
  out[#out + 1] = prev .. run
  return table.concat(out, " ")
end
local function finish()
  local f = io.open(OUT, "w")
  if not f then trigger.action.outText("SQE terrain probe: cannot write " .. OUT, 90) return end
  f:write('{"terrain":"Caucasus","x0":' .. X0 .. ',"y0":' .. Y0 .. ',"step":' .. STEP .. ',"nx":' .. NX .. ',"ny":' .. NY .. ',"rows":["')
  f:write(table.concat(rows, '","'))
  f:write('"]}')
  f:close()
  trigger.action.outText("SQE terrain scan COMPLETE. You can leave this mission and quit to the menu. Restart SQE or just build your next sortie.", 3600)
end
timer.scheduleFunction(function(_, t)
  for _ = 1, per do
    if nxt >= NX then finish() return nil end
    rows[#rows + 1] = scan(nxt)
    nxt = nxt + 1
  end
  if (nxt % 160) < per then trigger.action.outText(string.format("SQE terrain scan: %d%%", math.floor(100 * nxt / NX)), 5) end
  return t + 0.05
end, nil, timer.getTime() + 3)
trigger.action.outText("SQE terrain scan started. Do not leave this mission until it says COMPLETE (about a minute).", 15)
'''


def probe_lua() -> str:
    nx, ny = (X1 - X0) // STEP, (Y1 - Y0) // STEP
    return (PROBE_LUA.replace("__X0__", str(X0)).replace("__Y0__", str(Y0)).replace("__STEP__", str(STEP))
            .replace("__NX__", str(nx)).replace("__NY__", str(ny)))


def make_probe(out_path) -> Path:
    from dcs.mission import Mission, StartType
    from dcs.terrain import Caucasus
    from dcs.planes import Su_25T
    from dcs.triggers import TriggerStart
    from dcs.action import DoScript
    from dcs.translation import String
    import datetime
    m = Mission(Caucasus())
    m.start_time = datetime.datetime(2004, 6, 12, 12, 0)
    ru = m.country("Russia")
    apt = m.terrain.airports["Sochi-Adler"]
    g = m.flight_group_from_airport(ru, "SQE terrain probe", Su_25T, apt, group_size=1, start_type=StartType.Cold)
    g.units[0].set_client()
    t = TriggerStart(comment="SQE terrain probe")
    t.add_action(DoScript(String(probe_lua())))
    m.triggerrules.triggers.append(t)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return out_path
