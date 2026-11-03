"""Road-path probe (XO 2026-11-03, queue item m): does land.findPathOnRoads give usable road routes between far-apart places?

Builds one tiny Caucasus mission (a single Su-25T Player slot at Kutaisi, cold and dark, like the terrain probe). A mission-start script calls
land.findPathOnRoads for a list of airfield pairs (both 'roads' and 'railroads') and reports, for each pair, to dcs.log (lines start with `SQEROAD`):
  * whether the call exists and did not error, how many points came back, the path length against the straight-line distance,
  * the call time (os.clock, when the sandbox allows it),
  * the first and last points, and the largest gap between neighbouring points (so we know how dense the polyline is).
When io and lfs are available (SQE has patched MissionScripting.lua) it also writes the full polylines to <Saved Games>\\SQE\\SQE_roadpath_probe.json.
It also prints the result on screen for 60 s. Nothing here changes a campaign.

How XO runs it: python tools/road_path_probe.py OUT.miz  ->  start it in DCS (Fly), wait about a minute (the message says COMPLETE), send dcs.log
(grep SQEROAD) and, if it exists, SQE_roadpath_probe.json.
Source for the call: DCS scripting engine, land.findPathOnRoads(roadType, x1, y1, x2, y2) (from memory, UNVERIFIED: this probe is the test)."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

PAIRS = [                     # (label, airport name, airport name): short, medium and long hops, both coasts, the north and the mountain gap
    ("Kutaisi-Senaki", "Kutaisi", "Senaki-Kolkhi"),
    ("Batumi-Kobuleti", "Batumi", "Kobuleti"),
    ("Kobuleti-Kutaisi", "Kobuleti", "Kutaisi"),
    ("Krymsk-Gelendzhik", "Krymsk", "Gelendzhik"),
    ("Krymsk-Anapa", "Krymsk", "Anapa-Vityazevo"),
    ("Sochi-Gudauta", "Sochi-Adler", "Gudauta"),
    ("Gudauta-Sukhumi", "Gudauta", "Sukhumi-Babushara"),
    ("Sukhumi-Senaki", "Sukhumi-Babushara", "Senaki-Kolkhi"),
    ("Mozdok-Beslan", "Mozdok", "Beslan"),
    ("Mozdok-Nalchik", "Mozdok", "Nalchik"),
    ("Krymsk-Sochi", "Krymsk", "Sochi-Adler"),            # the long one: the coast road
    ("Kutaisi-Mozdok", "Kutaisi", "Mozdok"),              # across the mountains: expect no road or a very long detour
    ("Senaki-Vaziani", "Senaki-Kolkhi", "Vaziani"),         # XO 2026-11-03: the roads east of Senaki-Kolkhi toward Vaziani (blue supply spots)
    ("Kutaisi-Vaziani", "Kutaisi", "Vaziani"),
    ("Kutaisi-Tbilisi", "Kutaisi", "Tbilisi-Lochini"),
    ("Tbilisi-Vaziani", "Tbilisi-Lochini", "Vaziani"),
    ("Beslan-MinVody", "Beslan", "Mineralnye Vody"),        # the far north side of the mountains (red supply spots)
    ("Nalchik-MinVody", "Nalchik", "Mineralnye Vody"),
    ("Mozdok-MinVody", "Mozdok", "Mineralnye Vody"),
    ("Tbilisi-Beslan", "Tbilisi-Lochini", "Beslan"),        # over the pass (the Georgian Military Road, if DCS has it)
]

PROBE_LUA = r'''
-- SQE road-path probe: land.findPathOnRoads between airfield pairs; results to dcs.log (SQEROAD) and, if possible, a JSON file
local PAIRS = __PAIRS__
local function say(s) env.info("SQEROAD " .. s) end
local function dist(a, b) return math.sqrt((a.x - b.x)^2 + (a.y - b.y)^2) end
local function clock() if os and os.clock then return os.clock() end return nil end
local out, lines = {}, {}
if not (land and land.findPathOnRoads) then
  say("land.findPathOnRoads is MISSING in this DCS build")
  trigger.action.outText("SQE road probe: land.findPathOnRoads is missing.", 60)
  return
end
local function norm(p)                       -- a point may come back as {x=,y=} or {x=,z=} or {[1],[2]}
  if p.x ~= nil and p.y ~= nil then return {x = p.x, y = p.y} end
  if p.x ~= nil and p.z ~= nil then return {x = p.x, y = p.z} end
  if p[1] ~= nil and p[2] ~= nil then return {x = p[1], y = p[2]} end
  return nil
end
local function probe(kind, label, a, b)
  local t0 = clock()
  local ok, res = pcall(land.findPathOnRoads, kind, a[1], a[2], b[1], b[2])
  local dt = (t0 and clock()) and (clock() - t0) or nil
  if not ok then say(label .. " " .. kind .. " ERROR " .. tostring(res)); return nil end
  if type(res) ~= "table" then say(label .. " " .. kind .. " returned " .. type(res)); return nil end
  local pts = {}
  for _, p in ipairs(res) do local q = norm(p); if q then pts[#pts + 1] = q end end
  if #pts == 0 then say(label .. " " .. kind .. " no points (no road between them, or an unknown shape)"); return {kind = kind, n = 0} end
  local len, gap = 0, 0
  for i = 2, #pts do local d = dist(pts[i - 1], pts[i]); len = len + d; if d > gap then gap = d end end
  local straight = dist({x = a[1], y = a[2]}, {x = b[1], y = b[2]})
  say(string.format("%s %s points=%d length_km=%.1f straight_km=%.1f ratio=%.2f max_gap_m=%.0f call_s=%s first=(%.0f,%.0f) last=(%.0f,%.0f) start_err_m=%.0f end_err_m=%.0f",
    label, kind, #pts, len / 1000, straight / 1000, straight > 0 and len / straight or 0, gap, dt and string.format("%.3f", dt) or "n/a",
    pts[1].x, pts[1].y, pts[#pts].x, pts[#pts].y, dist(pts[1], {x = a[1], y = a[2]}), dist(pts[#pts], {x = b[1], y = b[2]})))
  return {kind = kind, n = #pts, length_m = len, straight_m = straight, max_gap_m = gap, pts = pts}
end
local done = 0
for _, pr in ipairs(PAIRS) do
  for _, kind in ipairs({"roads", "railroads"}) do
    local r = probe(kind, pr[1], pr[2], pr[3])
    if r then out[#out + 1] = {pair = pr[1], kind = kind, n = r.n, length_m = r.length_m, straight_m = r.straight_m, max_gap_m = r.max_gap_m, pts = r.pts}; done = done + 1 end
  end
end
-- optional file with the full polylines
if io and lfs then
  local ok, err = pcall(function()
    local dir = lfs.writedir() .. "SQE"; lfs.mkdir(dir)
    local f = io.open(dir .. "\\SQE_roadpath_probe.json", "w")
    f:write("[")
    for i, o in ipairs(out) do
      f:write((i > 1 and "," or "") .. string.format('{"pair":"%s","kind":"%s","n":%d,"length_m":%.0f,"straight_m":%.0f,"max_gap_m":%.0f,"pts":[', o.pair, o.kind, o.n, o.length_m or 0, o.straight_m or 0, o.max_gap_m or 0))
      for j, p in ipairs(o.pts or {}) do f:write((j > 1 and "," or "") .. string.format("[%.0f,%.0f]", p.x, p.y)) end
      f:write("]}")
    end
    f:write("]"); f:close()
  end)
  say(ok and "polylines written to SQE_roadpath_probe.json" or ("could not write the json file: " .. tostring(err)))
else
  say("io/lfs are sanitized: no json file (the dcs.log lines are the result)")
end
say("COMPLETE " .. done .. " results")
trigger.action.outText("SQE road probe COMPLETE: " .. done .. " results. Send dcs.log (SQEROAD lines).", 60)
'''


def probe_lua() -> str:
    from sqe import theatres
    t = theatres.terrain()
    rows = []
    for label, a, b in PAIRS:
        pa, pb = t.airports[a].position, t.airports[b].position
        rows.append('{"%s",{%d,%d},{%d,%d}}' % (label, round(pa.x), round(pa.y), round(pb.x), round(pb.y)))
    return PROBE_LUA.replace("__PAIRS__", "{" + ",".join(rows) + "}")


def make_probe(out_path) -> Path:
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
        ru = m.country("Russia")
        g = m.flight_group_from_airport(ru, "SQE road probe", Su_25T, m.terrain.airports["Kutaisi"], group_size=1, start_type=StartType.Cold)
        g.units[0].set_client()
        t = TriggerStart(comment="SQE road probe")
        t.add_action(DoScript(String(probe_lua())))
        m.triggerrules.triggers.append(t)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(out))
    return out


if __name__ == "__main__":
    p = make_probe(sys.argv[1] if len(sys.argv) > 1 else "SQE_road_probe.miz")
    print(f"wrote {p}: start it in DCS (Fly), wait for COMPLETE, send dcs.log (grep SQEROAD) and SQE_roadpath_probe.json if it exists")
