"""A one-off DCS mission that measures the map. Fly it once (Fly > any slot): a script samples land.getSurfaceType over the whole
theatre and writes <Saved Games>\\SQE\\SQE_terrain_<theatre>.json, which terrainmask.py reads, then samples land.getHeight on a coarser grid
(highest and average ground per cell) and writes SQE_relief_<theatre>.json, which relief.py reads. The mission has nothing in it but one
parked Su-25T (free with DCS World); no Eagle Dynamics data is copied, only the answers DCS gives. The area, grid and file name come
from the active theatre pack (the "scan" block)."""
from __future__ import annotations
from pathlib import Path

def _scan() -> dict:
    from . import theatres
    return theatres.active()["scan"]

PROBE_LUA = r'''
-- SQE terrain probe: samples the surface type over the map and writes the terrain scan file
if not (io and lfs) then
  trigger.action.outText("SQE terrain probe: io/lfs are sanitized. Start SQE (it patches MissionScripting.lua while open) or use Settings > patch, then restart this mission.", 90)
  return
end
local X0, Y0, STEP, NX, NY = __X0__, __Y0__, __STEP__, __NX__, __NY__
local HSTEP, HNX, HNY = __HSTEP__, __HNX__, __HNY__
local DIR = lfs.writedir() .. "SQE"
lfs.mkdir(DIR)
local OUT = DIR .. "\\__FILE__"
local ROUT = DIR .. "\\__RFILE__"
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
local function relief_pass()
  -- highest and average ground per cell, from a 3 x 3 sample inside each cell; heights in units of 10 m
  local mx, mn, nxt2, per2 = {}, {}, 0, 4
  local function hrow(i)
    local x0 = X0 + i * HSTEP
    local a, b = {}, {}
    for j = 0, HNY - 1 do
      local y0, hi, sum = Y0 + j * HSTEP, 0, 0
      for u = 0, 2 do
        for v = 0, 2 do
          local h = land.getHeight({x = x0 + (u + 0.5) * HSTEP / 3, y = y0 + (v + 0.5) * HSTEP / 3})
          if h < 0 then h = 0 end
          if h > hi then hi = h end
          sum = sum + h
        end
      end
      a[#a + 1] = math.ceil(hi / 10)
      b[#b + 1] = math.floor(sum / 9 / 10 + 0.5)
    end
    mx[#mx + 1] = table.concat(a, " ")
    mn[#mn + 1] = table.concat(b, " ")
  end
  local function finish2()
    local f = io.open(ROUT, "w")
    if not f then trigger.action.outText("SQE terrain probe: cannot write " .. ROUT, 90) return end
    f:write('{"terrain":"__NAME__","x0":' .. X0 .. ',"y0":' .. Y0 .. ',"step":' .. HSTEP .. ',"nx":' .. HNX .. ',"ny":' .. HNY .. ',"unit":10,"max":["')
    f:write(table.concat(mx, '","'))
    f:write('"],"mean":["')
    f:write(table.concat(mn, '","'))
    f:write('"]}')
    f:close()
    trigger.action.outText("SQE terrain scan COMPLETE (land and ground height). You can leave this mission and quit to the menu. Restart SQE or just build your next sortie.", 3600)
  end
  timer.scheduleFunction(function(_, t)
    for _ = 1, per2 do
      if nxt2 >= HNX then finish2() return nil end
      hrow(nxt2)
      nxt2 = nxt2 + 1
    end
    if (nxt2 % 50) < per2 then trigger.action.outText(string.format("SQE ground height scan: %d%%", math.floor(100 * nxt2 / HNX)), 5) end
    return t + 0.05
  end, nil, timer.getTime() + 1)
end
local function finish()
  local f = io.open(OUT, "w")
  if not f then trigger.action.outText("SQE terrain probe: cannot write " .. OUT, 90) return end
  f:write('{"terrain":"__NAME__","x0":' .. X0 .. ',"y0":' .. Y0 .. ',"step":' .. STEP .. ',"nx":' .. NX .. ',"ny":' .. NY .. ',"rows":["')
  f:write(table.concat(rows, '","'))
  f:write('"]}')
  f:close()
  trigger.action.outText("SQE land and water scan done. Now measuring ground height; do not leave this mission yet.", 15)
  relief_pass()
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
trigger.action.outText("SQE terrain scan started. Do not leave this mission until it says COMPLETE (about two minutes).", 15)
'''


def probe_lua() -> str:
    from . import theatres
    sc, th = _scan(), theatres.active()
    X0, X1, Y0, Y1, STEP = sc["x0"], sc["x1"], sc["y0"], sc["y1"], sc["step"]
    nx, ny = (X1 - X0) // STEP, (Y1 - Y0) // STEP
    HS = int(sc.get("height_step", 1000))
    hnx, hny = (X1 - X0) // HS, (Y1 - Y0) // HS
    rfile = sc.get("relief_file") or sc["file"].replace("terrain", "relief")
    return (PROBE_LUA.replace("__HSTEP__", str(HS)).replace("__HNX__", str(hnx)).replace("__HNY__", str(hny)).replace("__RFILE__", rfile).replace("__X0__", str(X0)).replace("__Y0__", str(Y0)).replace("__STEP__", str(STEP))
            .replace("__NX__", str(nx)).replace("__NY__", str(ny)).replace("__FILE__", sc["file"]).replace("__NAME__", th["name"]))


def make_probe(out_path) -> Path:
    import contextlib
    import io
    import logging
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated DCS livery files
        return _make_probe(out_path)


def _make_probe(out_path) -> Path:
    from dcs.mission import Mission, StartType
    from . import theatres
    from dcs.planes import Su_25T
    from dcs.triggers import TriggerStart
    from dcs.action import DoScript
    from dcs.translation import String
    import datetime
    m = Mission(theatres.terrain())
    m.start_time = datetime.datetime(2004, 6, 12, 12, 0)
    ru = m.country("Russia")
    apt = m.terrain.airports[_scan()["probe_airport"]]
    g = m.flight_group_from_airport(ru, "SQE terrain probe", Su_25T, apt, group_size=1, start_type=StartType.Cold)
    g.units[0].set_client()
    t = TriggerStart(comment="SQE terrain probe")
    t.add_action(DoScript(String(probe_lua())))
    m.triggerrules.triggers.append(t)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return out_path
