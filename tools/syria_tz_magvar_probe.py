"""Syria time zone and magnetic variation probe (S90, XO 2026-11-18; tools only, nothing ships, no change in play).

  python tools/syria_tz_magvar_probe.py make OUT.miz       e.g. C:\\temp\\SQE_Syria_TZ_MagVar.miz, then copy to <Saved Games>\\DCS\\Missions\\Probes

Two numbers the Syria pack needs (`tz` of the stub is 2.0, `mag_var_deg` is a guess of about 4 E):

MAGNETIC VARIATION, automatic. The mission script asks every airbase for its runways (`Airbase:getRunways()`: runway name, a magnetic number such as "05", and `course`, a radian angle)
and logs one line per runway: `SQEMAGV rwy <airbase> name=<N> course_deg=<raw>`. The runway names are magnetic, the course is true, so (true course) minus (name x 10) is the variation,
each runway good to +-5 degrees (the name is rounded to 10); the mean over about 40 runways is good to a degree or two. DCS's sign convention for `course` is not known, so the raw value
is logged and `python tools/syria_tz_magvar_probe.py analyze dcs.log` reads it with both signs: the right sign gives differences that cluster, the wrong one scatters.

TIME ZONE, by eye (DCS has no sun-position API). The mission starts on 21 June at 05:00 LOCAL, you sit in a parked F-16 at Bassel Al-Assad (Latakia, 35.4 N 35.95 E). The sun rises at about
02:25 UTC there (solar noon 09:37 UTC, day length 14 h 24 min, +-5 min, computed, not looked up), so:
  tz UTC+2 (the stub): sunrise 04:27 local, at 05:00 the sun is about 33 minutes up: a sun disk low over the sea / mountains to the east-north-east.
  tz UTC+3:            sunrise 05:27 local, at 05:00 the sun is about 27 minutes BELOW the horizon: bright dawn sky (civil twilight), but no sun disk.
A one-hour test, not a fine one; look east. (The plan note of 2026-11-18 had light / dark the wrong way round: at 05:00 a visible sun means UTC+2.)
The script also logs the mission date and start time (`SQEMAGV time ...`)."""
from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import logging
import math
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LUA = r'''
-- SQE Syria time zone / magnetic variation probe: runways of every airbase to dcs.log, prefix SQEMAGV
local function say(s) env.info("SQEMAGV " .. s) end
local function run()
  say(string.format("time abs=%.0f mission_start=%s", timer.getAbsTime(), tostring(timer.getTime0 and timer.getTime0() or "?")))
  local n, rw = 0, 0
  for _, ab in ipairs(world.getAirbases()) do
    local ok, err = pcall(function()
      local d = ab:getDesc()
      if d and d.category ~= 0 then return end                  -- airfields only (not helipads, ships)
      n = n + 1
      if not ab.getRunways then say("Airbase:getRunways is MISSING"); return end
      for _, r in ipairs(ab:getRunways() or {}) do
        rw = rw + 1
        say(string.format("rwy %s name=%s course_deg=%.2f length=%s", ab:getName(), tostring(r.Name), (r.course or 0) * 180 / math.pi, tostring(r.length)))
      end
    end)
    if not ok then say("error " .. tostring(err)) end
  end
  say("DONE airfields=" .. n .. " runways=" .. rw)
  trigger.action.outText("SQE Syria probe: runway data logged (" .. rw .. " runways). Now look EAST: a sun disk above the horizon means UTC+2, only a bright dawn sky and no sun means UTC+3. Then send dcs.log (grep SQEMAGV).", 600)
end
timer.scheduleFunction(function() local ok, err = pcall(run); if not ok then say("script error " .. tostring(err)) end end, nil, timer.getTime() + 5)
'''


def _build(out: Path) -> Path:
    from dcs import planes
    from dcs.action import DoScript
    from dcs.mission import Mission, StartType
    from dcs.terrain import Syria
    from dcs.translation import String
    from dcs.triggers import TriggerStart
    m = Mission(Syria())
    m.start_time = datetime.datetime(2000, 6, 21, 5, 0)
    g = m.flight_group_from_airport(m.country("USA"), "Probe slot", planes.F_16C_50, m.terrain.airports["Bassel Al-Assad"], group_size=1, start_type=StartType.Cold)
    g.units[0].set_client()
    t = TriggerStart(comment="SQE Syria TZ / magvar probe")
    t.add_action(DoScript(String(LUA)))
    m.triggerrules.triggers.append(t)
    m.set_sortie_text("SQE Syria time zone / magnetic variation probe")
    m.set_description_text("Start 21 June 05:00 local at Latakia. Look east: a sun disk above the horizon = UTC+2, no sun disk (bright dawn sky) = UTC+3. "
                           "The runway data for the magnetic variation is logged by itself: send dcs.log (grep SQEMAGV).")
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    return out


def build(out) -> Path:
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated livery files
        return _build(Path(out))


def analyze(log_path) -> None:
    """Read the SQEMAGV rwy lines of a dcs.log; for each sign of `course`, the true course minus the runway number x 10, folded to -180..180, and its spread."""
    rows = []
    for line in Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.search(r"SQEMAGV rwy (.+?) name=(\S+) course_deg=(-?[\d.]+)", line)
        if m:
            num = re.match(r"\d+", m.group(2))
            if num:
                rows.append((m.group(1), int(num.group()) * 10.0, float(m.group(3))))
    print(f"{len(rows)} runways")
    if not rows:
        return
    for label, sign in (("course as logged", 1), ("course negated", -1)):
        d = [((sign * c - n + 180) % 360) - 180 for _a, n, c in rows]
        print(f"{label}: mean {statistics.mean(d):+.1f}, median {statistics.median(d):+.1f}, stdev {statistics.pstdev(d):.1f} degrees (true minus magnetic; a good reading has stdev near 3)")
    print("the sign with the small stdev is the right one; its mean is the variation (positive = east)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["make", "analyze"])
    ap.add_argument("path")
    a = ap.parse_args()
    if a.cmd == "make":
        p = build(a.path)
        print(f"wrote {p}: copy to C:\\Users\\<you>\\Saved Games\\DCS\\Missions\\Probes, fly it (the Bassel Al-Assad slot), look east, send dcs.log (grep SQEMAGV)")
    else:
        analyze(a.path)


if __name__ == "__main__":
    main()
