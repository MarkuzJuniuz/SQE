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
local X1, Y1 = __X1__, __Y1__
local HSTEP, HNX, HNY = __HSTEP__, __HNX__, __HNY__
local DIR = lfs.writedir() .. "SQE"
lfs.mkdir(DIR)
local OUT = DIR .. "\\__FILE__"
local ROUT = DIR .. "\\__RFILE__"
local DOUT = DIR .. "\\__DFILE__"
local RSTEP = __RSTEP__
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
  local road_pass
  local function finish2()
    local f = io.open(ROUT, "w")
    if not f then trigger.action.outText("SQE terrain probe: cannot write " .. ROUT, 90) return end
    f:write('{"terrain":"__NAME__","x0":' .. X0 .. ',"y0":' .. Y0 .. ',"step":' .. HSTEP .. ',"nx":' .. HNX .. ',"ny":' .. HNY .. ',"unit":10,"max":["')
    f:write(table.concat(mx, '","'))
    f:write('"],"mean":["')
    f:write(table.concat(mn, '","'))
    f:write('"]}')
    f:close()
    trigger.action.outText("SQE ground height done. Now finding roads; do not leave this mission yet.", 15)
    road_pass()
  end
  road_pass = function()
    -- Roads: land.getClosestPointOnRoads('roads', x, y) is a nearest-road search that costs ~90 ms when no road is near (measured in DCS), so the whole map
    -- (97,500 points) would take hours. Only the places the war touches are scanned: a disc around every airfield of the theatre plus points along the
    -- front line, water skipped, in three passes (coarse, medium, fine); the roads file is written after every pass, so any finished pass is usable.
    -- DCS's mission environment has NO clock (os is not there): time is read from a file (write a tiny file, ask lfs for its modification time, whole seconds),
    -- and the work is cut into slices of 1 to 2 s per timer tick (DCS's anti-freeze hands out ticks rarely while the scan loads the sim).
    local WALLF = DIR .. "\\SQE_clock.tmp"
    local function wall()
      local f = io.open(WALLF, "w")
      if not f then return nil end
      f:write("x"); f:close()
      local okw, m = pcall(lfs.attributes, WALLF, "modification")
      return okw and m or nil
    end
    local function say(m)
      trigger.action.outText(m, 12)
      if env and env.info then env.info("SQE road scan: " .. m) end
    end
    local pts, seen = {}, {}
    local function write_roads(step)
      if #pts == 0 then return false end
      local f = io.open(DOUT, "w")
      if not f then return false end
      f:write('{"terrain":"__NAME__","step":' .. step .. ',"pts":[' .. table.concat(pts, ",") .. ']}')
      f:close()
      return true
    end
    local function finish_all(why)
      local ok = #pts > 0
      trigger.action.outText("SQE terrain scan COMPLETE (land, ground height" .. (ok and ", roads" or ("; roads not available" .. (why and (": " .. why) or ""))) .. "). You can leave this mission and quit to the menu. Restart SQE or just build your next sortie.", 3600)
    end
    local ANAMES, FRONT, RRAD = __ANCHORS__, __FRONT__, __RRAD__
    local pos = {}
    local okb, abl = pcall(world.getAirbases)
    if okb and abl then
      for _, ab in ipairs(abl) do
        local okn, nm = pcall(ab.getName, ab)
        local okp, p = pcall(ab.getPoint, ab)
        if okn and okp and nm and p then pos[nm] = {p.x, p.z} end
      end
    end
    local anch = {}
    for _, nm in ipairs(ANAMES) do if pos[nm] then anch[#anch + 1] = pos[nm] end end
    for k = 1, #FRONT - 1 do
      local a, b = pos[FRONT[k]], pos[FRONT[k + 1]]
      if a and b then
        local n = math.max(1, math.floor(math.sqrt((b[1] - a[1]) ^ 2 + (b[2] - a[2]) ^ 2) / 12000))
        for q = 1, n - 1 do anch[#anch + 1] = {a[1] + (b[1] - a[1]) * q / n, a[2] + (b[2] - a[2]) * q / n} end
      end
    end
    for _, e in ipairs(__EXTRA__) do anch[#anch + 1] = {e[1], e[2]} end        -- v0.41.187: the ground-war sector centres (columns, forward garrisons, depots sit there)
    if #anch == 0 then finish_all("no airfields found") return end
    local lists, have = {{}, {}, {}}, {}
    local ni, nj = math.floor((X1 - X0) / RSTEP), math.floor((Y1 - Y0) / RSTEP)
    for _, a in ipairs(anch) do
      for i = math.max(0, math.floor((a[1] - RRAD - X0) / RSTEP)), math.min(ni - 1, math.floor((a[1] + RRAD - X0) / RSTEP)) do
        for j = math.max(0, math.floor((a[2] - RRAD - Y0) / RSTEP)), math.min(nj - 1, math.floor((a[2] + RRAD - Y0) / RSTEP)) do
          local key = i * 100000 + j
          if not have[key] then
            local x, y = X0 + (i + 0.5) * RSTEP, Y0 + (j + 0.5) * RSTEP
            if (x - a[1]) ^ 2 + (y - a[2]) ^ 2 <= RRAD ^ 2 then
              have[key] = true
              local okw, sf = pcall(land.getSurfaceType, {x = x, y = y})
              if not (okw and sf == ST.WATER) then
                local L = lists[(i % 4 == 0 and j % 4 == 0) and 1 or ((i % 2 == 0 and j % 2 == 0) and 2 or 3)]
                L[#L + 1] = {x, y}
              end
            end
          end
        end
      end
    end
    local PSTEP = {RSTEP * 4, RSTEP * 2, RSTEP}
    if #lists[1] == 0 then finish_all("no land points near the airfields") return end
    say(string.format("road scan area: %d airfield and front points, %d km around each. Passes: %d + %d + %d sample points.", #anch, RRAD / 1000, #lists[1], #lists[2], #lists[3]))
    local function main_scan()
      local pk, ci, lastpct, t_start, w_start = 1, 1, -10, timer.getTime(), wall()
      timer.scheduleFunction(function(_, t)
        local w0, nc, chk, wprev = wall(), 0, 5, nil
        while true do
          local L = lists[pk]
          if ci > #L then
            local okf = write_roads(PSTEP[pk])
            say(string.format("road pass %d of 3 done: %d road points%s.%s", pk, #pts, okf and ", roads file written" or "", pk < 3 and " You can leave now, or wait for the finer passes." or ""))
            pk = pk + 1; ci = 1; lastpct = -10
            if pk > 3 then finish_all(nil) return nil end
            break
          end
          local pt = L[ci]
          ci = ci + 1; nc = nc + 1
          local okc, rx, ry = pcall(land.getClosestPointOnRoads, "roads", pt[1], pt[2])
          if okc and rx and ry and math.abs(rx - pt[1]) <= PSTEP[pk] * 2 and math.abs(ry - pt[2]) <= PSTEP[pk] * 2 then
            local kx, ky = math.floor(rx / 50 + 0.5) * 50, math.floor(ry / 50 + 0.5) * 50
            local key = kx .. ":" .. ky
            if not seen[key] then seen[key] = true; pts[#pts + 1] = "[" .. kx .. "," .. ky .. "]" end
          end
          if nc % chk == 0 then
            local w = w0 and wall()
            if w then
              if w - w0 >= 1 then break end
              if w == wprev then chk = math.min(200, chk * 2) else chk = math.max(5, math.floor(chk / 2)) end
              wprev = w
            elseif nc >= 40 then break end
          end
        end
        if pk <= 3 then
          local pct = math.floor(100 * (ci - 1) / #lists[pk])
          if pct >= lastpct + 10 then
            lastpct = pct
            trigger.action.outText(string.format("SQE road scan, pass %d of 3: %d%%", pk, pct), 8)
            if env and env.info then env.info(string.format("SQE road scan: pass %d %d%% points=%d mission_s=%.1f wall_s=%s", pk, pct, #pts, t - t_start, (w_start and w0) and tostring(w0 - w_start) or "n/a")) end
          end
        end
        return t + 0.05
      end, nil, timer.getTime() + 1)
    end
    local TESTS, ti = {lists[1][1], lists[1][math.ceil(#lists[1] / 2)], lists[1][#lists[1]]}, 0
    local function next_test()
      if ti >= #TESTS then main_scan() return end
      ti = ti + 1
      local x, y = TESTS[ti][1], TESTS[ti][2]
      say(string.format("road test %d of %d: calling now at %d, %d. A call can take a while; if this stays the last message for minutes, DCS is stuck in that call.", ti, #TESTS, x, y))
      timer.scheduleFunction(function()
        local w0 = wall()
        local okc, rx, ry = pcall(land.getClosestPointOnRoads, "roads", x, y)
        local w1 = wall()
        say(string.format("road test %d: %s, about %d s", ti, okc and (rx and "road found" or "no road") or "error", (w0 and w1) and (w1 - w0) or 0))
        next_test()
        return nil
      end, nil, timer.getTime() + 2)
    end
    next_test()
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
    dfile = sc.get("roads_file") or sc["file"].replace("terrain", "roads")
    return (PROBE_LUA.replace("__DFILE__", dfile).replace("__RSTEP__", str(int(sc.get("road_step", 2000)))).replace("__X1__", str(X1)).replace("__Y1__", str(Y1)).replace("__HSTEP__", str(HS)).replace("__HNX__", str(hnx)).replace("__HNY__", str(hny)).replace("__RFILE__", rfile).replace("__X0__", str(X0)).replace("__Y0__", str(Y0)).replace("__STEP__", str(STEP))
            .replace("__ANCHORS__", _lua_list(_airports(th))).replace("__FRONT__", _lua_list(_front_chain(th))).replace("__EXTRA__", _lua_xy(_sector_anchors(th))).replace("__RRAD__", str(int(sc.get("road_radius_m", 25000))))
            .replace("__NX__", str(nx)).replace("__NY__", str(ny)).replace("__FILE__", sc["file"]).replace("__NAME__", th["name"]))


def _lua_xy(pts) -> str:
    return "{" + ",".join("{%d,%d}" % (round(x), round(y)) for x, y in pts) + "}"


def _sector_anchors(th: dict) -> list:
    """v0.41.187 (XO 2026-10-28): the centres of the ground-war sectors, on the longest chain (the one that holds every sector), as the campaign builder
    places them (even steps along the axis between the chain's airfields, moved onto land when a terrain scan exists). XO's 2026-10-28 roads file had no
    point at all in the Gelendzhik - Sochi sectors: the sector centres lie up to 40 km from the straight line between two airfields (the coast bends),
    so the discs round the airfields and the line did not reach them. [] when the theatre has no chain or pydcs cannot give the airfield positions."""
    try:
        from . import theatres, ground, seacheck
        fr = th.get("front") or {}
        chain, legs = list(fr.get("chain") or []), list(fr.get("leg_zones") or [])
        if len(chain) < 2 or len(legs) != len(chain) - 1:
            return []
        t = theatres.terrain()
        axis = []
        for n in chain:
            a = t.airports[n["airport"]].position
            axis.append([a.x, a.y])
        return [tuple(seacheck.snap_to_land(c[0], c[1])) for c in ground.zone_centers(axis, legs)]
    except Exception:
        return []


def _lua_list(names) -> str:
    return "{" + ",".join('"' + str(n).replace('"', "") + '"' for n in names) + "}"


def _airports(th: dict) -> list:
    """Airfields of the theatre (both sides) plus the front-line ends: the places the war touches."""
    out = [f["airport"] for f in list(th.get("blue_fields", [])) + list(th.get("red_fields", [])) if f.get("airport")]
    out += _front_chain(th)
    return list(dict.fromkeys(out))


def _front_chain(th: dict) -> list:
    fr = th.get("front", {}) or {}
    return [n["airport"] for n in (fr.get("chain") or []) if n.get("airport")]


def make_probe(out_path, seat: bool = True) -> Path:
    import contextlib
    import io
    import logging
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated DCS livery files
        return _make_probe(out_path, seat)


def _make_probe(out_path, seat: bool = True) -> Path:
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
    if seat:
        g.units[0].set_client()               # the player slot DCS needs to enter the mission; seat=False leaves only an AI aircraft (experimental)
    t = TriggerStart(comment="SQE terrain probe")
    t.add_action(DoScript(String(probe_lua())))
    m.triggerrules.triggers.append(t)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out_path))
    return out_path
