"""Road-network scan (queue item m, step 2; XO 2026-11-03).

  python tools/road_net_scan.py make OUT.miz       a tiny DCS mission (one Su-25T slot at Kutaisi) that runs land.findPathOnRoads between neighbouring
                                                   airfields and the ground-war sector centres and writes <Saved Games>\\SQE\\SQE_roadnet_<theatre>.json
  python tools/road_net_scan.py build RAW.json     turns that file into sqe/data/theatres/<theatre>_roads_net.json (simplified routes) and adds the
                                                   "road" supply spots to <theatre>_sites.json (see sqe/roadnet.py)

How XO runs it: fly the mission once (Fly > the slot), wait for the COMPLETE message (a few seconds to a minute), send `SQE_roadnet_caucasus.json` and
dcs.log (grep SQEROADNET). If an airfield point is cut off from the road net (Batumi, Kobuleti, Gelendzhik gave nothing in the 2026-11-03 probe) the
script retries from points 1.5 and 3.5 km round it, so a pair only fails when no road is within reach."""
from __future__ import annotations

import datetime
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NEIGHBOURS = 3                # every anchor is joined to its nearest N others
EXTRA_PAIRS = [               # the long hops that the nearest-neighbour graph may miss (names as pydcs spells them); from the 2026-11-03 probe
    ("Kutaisi", "Mozdok"), ("Tbilisi-Lochini", "Beslan"), ("Krymsk", "Sochi-Adler"), ("Senaki-Kolkhi", "Vaziani"),
    ("Kutaisi", "Tbilisi-Lochini"), ("Beslan", "Mineralnye Vody"), ("Sukhumi-Babushara", "Senaki-Kolkhi"),
]

SCAN_LUA = r'''
-- SQE road-network scan: land.findPathOnRoads between neighbouring anchors; raw polylines to SQE_roadnet_<theatre>.json, summary to dcs.log (SQEROADNET)
local PAIRS = __PAIRS__
local THEATRE = "__THEATRE__"
local MIN_STEP = 60                          -- keep a point only if it is this far from the last kept one (the last point is always kept)
local function say(s) env.info("SQEROADNET " .. s) end
if not (land and land.findPathOnRoads) then say("land.findPathOnRoads is MISSING"); return end
local function norm(p)
  if p.x ~= nil and p.y ~= nil then return {p.x, p.y} end
  if p.x ~= nil and p.z ~= nil then return {p.x, p.z} end
  if p[1] ~= nil and p[2] ~= nil then return {p[1], p[2]} end
  return nil
end
local function try(a, b)
  local ok, res = pcall(land.findPathOnRoads, "roads", a[1], a[2], b[1], b[2])
  if not ok or type(res) ~= "table" then return nil end
  local pts = {}
  for _, p in ipairs(res) do local q = norm(p); if q then pts[#pts + 1] = q end end
  if #pts < 2 then return nil end
  return pts
end
local function ring(p, r, k) local ang = k * math.pi / 4; return {p[1] + r * math.cos(ang), p[2] + r * math.sin(ang)} end
local function path(a, b)
  local pts = try(a, b)
  if pts then return pts, "direct" end
  for _, r in ipairs({1500, 3500}) do
    for k = 0, 7 do pts = try(ring(a, r, k), b); if pts then return pts, "start+" .. r end end
    for k = 0, 7 do pts = try(a, ring(b, r, k)); if pts then return pts, "end+" .. r end end
  end
  return nil
end
local out, ok_n, fail = {}, 0, {}
for _, pr in ipairs(PAIRS) do
  local pts, how = path(pr[2], pr[3])
  if pts then
    local kept, last = {pts[1]}, pts[1]
    for i = 2, #pts do
      local p = pts[i]
      if i == #pts or math.sqrt((p[1] - last[1])^2 + (p[2] - last[2])^2) >= MIN_STEP then kept[#kept + 1] = p; last = p end
    end
    out[#out + 1] = {pair = pr[1], kind = "roads", pts = kept}
    ok_n = ok_n + 1
    say(pr[1] .. " ok (" .. how .. ") points=" .. #pts .. " kept=" .. #kept)
  else
    fail[#fail + 1] = pr[1]
    say(pr[1] .. " NO ROAD PATH")
  end
end
local wrote = false
if io and lfs then
  local ok, err = pcall(function()
    local dir = lfs.writedir() .. "SQE"; lfs.mkdir(dir)
    local f = io.open(dir .. "\\SQE_roadnet_" .. THEATRE .. ".json", "w")
    f:write("[")
    for i, o in ipairs(out) do
      f:write((i > 1 and "," or "") .. string.format('{"pair":"%s","kind":"roads","pts":[', o.pair))
      for j, p in ipairs(o.pts) do f:write((j > 1 and "," or "") .. string.format("[%.0f,%.0f]", p[1], p[2])) end
      f:write("]}")
    end
    f:write("]"); f:close()
  end)
  wrote = ok
  say(ok and "file written" or ("could not write the file: " .. tostring(err)))
else
  say("io/lfs are sanitized: no file written")
end
say("COMPLETE ok=" .. ok_n .. " failed=" .. #fail .. (#fail > 0 and (" (" .. table.concat(fail, ", ") .. ")") or ""))
trigger.action.outText("SQE road scan COMPLETE: " .. ok_n .. " routes, " .. #fail .. " without a road" .. (wrote and ". File written." or ". NO FILE (send dcs.log)."), 90)
'''


def anchors() -> list:
    """[(name, x, y)]: every airfield of the active terrain plus the ground-war sector centres."""
    from sqe import terrainprobe, theatres
    t = theatres.terrain()
    out = [(n, a.position.x, a.position.y) for n, a in t.airports.items()]
    th = theatres.active()
    out += [(f"sector{i + 1}", x, y) for i, (x, y) in enumerate(terrainprobe._sector_anchors(th))]
    return out


def pairs(anch=None, k: int = NEIGHBOURS, extra=EXTRA_PAIRS) -> list:
    """[(label, (x, y), (x, y))]: each anchor to its k nearest others, plus the extra long hops; each pair once."""
    anch = anch or anchors()
    pos = {n: (x, y) for n, x, y in anch}
    seen, out = set(), []

    def add(a, b):
        key = tuple(sorted((a, b)))
        if a == b or key in seen or a not in pos or b not in pos:
            return
        seen.add(key)
        out.append((f"{a}~{b}", pos[a], pos[b]))
    for n, x, y in anch:
        near = sorted((m for m, _, _ in anch if m != n), key=lambda m: math.hypot(pos[m][0] - x, pos[m][1] - y))
        for m in near[:k]:
            add(n, m)
    for a, b in extra:
        add(a, b)
    return out


def scan_lua() -> str:
    from sqe import theatres
    rows = ['{"%s",{%d,%d},{%d,%d}}' % (lab.replace('"', ""), round(a[0]), round(a[1]), round(b[0]), round(b[1])) for lab, a, b in pairs()]
    return SCAN_LUA.replace("__PAIRS__", "{" + ",".join(rows) + "}").replace("__THEATRE__", theatres.active()["id"])


def make(out_path) -> Path:
    import contextlib
    import io
    import logging
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    from dcs.action import DoScript
    from dcs.mission import Mission, StartType
    from dcs.planes import Su_25T
    from dcs.translation import String
    from dcs.triggers import TriggerStart
    from sqe import theatres
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        m = Mission(theatres.terrain())
        m.start_time = datetime.datetime(2004, 6, 12, 12, 0)
        g = m.flight_group_from_airport(m.country("Russia"), "SQE road scan", Su_25T, m.terrain.airports["Kutaisi"], group_size=1, start_type=StartType.Cold)
        g.units[0].set_client()
        t = TriggerStart(comment="SQE road scan")
        t.add_action(DoScript(String(scan_lua())))
        m.triggerrules.triggers.append(t)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(out))
    return out


def build(raw_path) -> dict:
    import json
    from sqe import roadnet, theatres
    th = theatres.active()
    return roadnet.build_net(json.loads(Path(raw_path).read_text(encoding="utf-8")), th["_dir"], th["id"])


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "make":
        p = make(sys.argv[2])
        print(f"wrote {p} with {len(pairs())} pairs: fly it once, wait for COMPLETE, send SQE_roadnet_<theatre>.json and dcs.log (grep SQEROADNET)")
    elif len(sys.argv) >= 3 and sys.argv[1] == "build":
        print(build(sys.argv[2]))
    else:
        print(__doc__)
