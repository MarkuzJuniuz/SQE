"""S90 J5b probe: the campaign start hour (pack key `start_hour`), proved with a dummy pack (tools only, nothing ships).

    python tools/start_hour_probe.py [seed ...] [--jobs N]

A temp pack `midnightpack` (the Caucasus renamed) sets `start_hour` 0. For each level and seed the probe checks (BAD lines otherwise):
  - the campaign stores `start_hour` 0, `clock.START_MIN` is 0, the turn label reads "Day 1, 00:00", turn 0 is a night turn and day 1 has six turns (turn 6 is Day 2, 00:00);
  - the first plan is for the 00:00 turn: every package starts between 00:00 and 03:59;
  - one mission built at turn 0 (night: its start time is in the package's window and before sunrise by `timeofday.is_night`) and, after two skipped turns, one at turn 2 (08:00, day: after sunrise, in the
    08:00 to 11:59 window); the .miz start time, the date and the briefing / kneeboard times agree with the package;
  - six skipped turns move the clock to Day 2, 00:00 (turn 6) and the war-log stamps read "[day 1 0000]" ... "[day 1 2000]";
  - the same pack with night ops OFF starts on the first day turn (turn 2, "Day 1, 08:00"): the two night turns were resolved at creation;
  - the campaign survives save and reopen with its start hour (the clock is put back to 08:00 between, so the load has to set it), an OLD save with no `start_hour` key loads as 8 and a Caucasus campaign made
    afterwards reads "Day 1, 08:00".
Exit 0 = all clean. One worker process per (level, seed); the output is the same either way."""
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_starthour_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def make_pack(root: Path) -> Path:
    pack = root / "packs"
    pack.mkdir(parents=True, exist_ok=True)
    src = ROOT / "sqe" / "data" / "theatres"
    d = json.loads((src / "caucasus.json").read_text(encoding="utf-8"))
    d["id"], d["name"] = "midnightpack", "Midnight start pack"
    d["start_hour"] = 0
    (pack / "midnightpack.json").write_text(json.dumps(d), encoding="utf-8")
    for f in src.glob("caucasus_*.json"):
        shutil.copy(f, pack / f.name.replace("caucasus_", "midnightpack_"))
    return pack


def mission_info(s):
    from dcs import lua
    M = lua.loads(zipfile.ZipFile(s.settings.sortie_miz).read("mission").decode("utf-8", "replace"))["mission"]
    t = int(M["start_time"])
    return t // 3600, (t % 3600) // 60, M["date"]


def one_case(task) -> dict:
    level, seed = task
    parallel.pin_task(f"starthour:{level}:{seed}")
    from sqe import theatres, clock, timeofday
    from sqe.engine import Session
    from sqe.settings import AppSettings
    theatres.EXTRA_DIRS.append(str(make_pack(TMP)))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    tag = f"L{level} s{seed}"
    bad, lines = [], []
    s = mk()
    s.new(f"Mn{level}{seed}", "F-16C", level, seed=seed, theatre="midnightpack", night_ops=True)
    st = s.state
    if st.start_hour != 0 or clock.START_MIN != 0:
        bad.append(f"{tag}: start_hour {st.start_hour}, clock.START_MIN {clock.START_MIN}")
    if s.turn_label() != "Day 1, 00:00" or not clock.is_night_turn(0) or clock.day_of(5) != 1 or clock.day_of(6) != 2 or clock.first_turn(2) != 6:
        bad.append(f"{tag}: the clock is wrong: label {s.turn_label()!r}, night {clock.is_night_turn(0)}, day_of(5) {clock.day_of(5)}, day_of(6) {clock.day_of(6)}, first_turn(2) {clock.first_turn(2)}")
    pk = s.packages()
    starts = sorted(p.start for p in pk)
    if not pk or any(not ("00:00" <= p.start <= "03:59") for p in pk):
        bad.append(f"{tag}: the first plan is not for the 00:00 turn: starts {starts}")
    lines.append(f"{tag}: Day 1 00:00, {len(pk)} packages, starts {starts[:4]}")

    def build(label, lo, hi, night_expected):
        fl = [p for p in s.packages() if s.flyable(p)]
        if not fl:
            lines.append(f"{tag}: {label}: nothing flyable this turn")
            return
        p = fl[0]
        s.ai_test = True
        s.fly(p.number, s.flyable(p)[0].id)
        h, m, date = mission_info(s)
        stamp = f"{h:02d}:{m:02d}"
        if stamp != p.start or not (lo <= stamp <= hi):
            bad.append(f"{tag}: {label}: the .miz starts at {stamp}, the package at {p.start}, the turn's window is {lo} to {hi}")
        d0 = st.campaign_date()
        if (date["Year"], date["Month"], date["Day"]) != (d0.year, d0.month, d0.day):
            bad.append(f"{tag}: {label}: the .miz date {date} is not the campaign date {d0}")
        if timeofday.is_night(d0, p.start) != night_expected:
            bad.append(f"{tag}: {label}: {p.start} on {d0} is {'night' if not night_expected else 'day'} by the sun tables, expected the other")
        lines.append(f"{tag}: {label}: mission #{p.number} {p.objective.type.value} start {stamp} (night {timeofday.is_night(d0, p.start)})")
    build("turn 0 (night)", "00:00", "03:59", True)
    s.skip_turn(); s.skip_turn()
    if s.turn_label() != "Day 1, 08:00":
        bad.append(f"{tag}: after two skips the label is {s.turn_label()!r}")
    build("turn 2 (day)", "08:00", "11:59", False)
    for _ in range(4):
        s.skip_turn()
    if s.turn_label() != "Day 2, 00:00" or st.day != 2 or st.turn != 6:
        bad.append(f"{tag}: after six skips: label {s.turn_label()!r}, day {st.day}, turn {st.turn}")
    stamps = sorted({x[7:11] for x in st.log if x.startswith("[day 1 ")})
    if stamps != ["0000", "0400", "0800", "1200", "1600", "2000"]:
        bad.append(f"{tag}: the war-log stamps of day 1 are {stamps}, expected the six turn starts 0000 .. 2000")
    path = str(TMP / "saves" / f"mn{level}{seed}.sqe")
    s.save(path)
    clock.use(8)                                                                       # the load has to put the campaign's own start hour back
    s2 = mk()
    s2.open(path)
    if s2.state.start_hour != 0 or clock.START_MIN != 0 or s2.turn_label() != "Day 2, 00:00":
        bad.append(f"{tag}: reopened: start_hour {s2.state.start_hour}, START_MIN {clock.START_MIN}, label {s2.turn_label()!r}")
    d = s2.state.to_dict()
    d.pop("start_hour")                                                                # an old save: no key
    from sqe.state import CampaignState
    old = CampaignState.from_dict(d)
    if old.start_hour != 8 or clock.START_MIN != 480:
        bad.append(f"{tag}: an old save without start_hour loads as {old.start_hour}, START_MIN {clock.START_MIN}")

    s4 = mk()                                                                          # night ops off: the night turns are resolved at creation
    s4.new(f"Mf{level}{seed}", "F-16C", level, seed=seed, theatre="midnightpack", night_ops=False)
    if s4.turn_label() != "Day 1, 08:00" or s4.state.turn != 2:
        bad.append(f"{tag}: night ops off: the campaign starts at {s4.turn_label()!r} (turn {s4.state.turn}), expected Day 1, 08:00 (turn 2)")
    lines.append(f"{tag}: night ops off starts at {s4.turn_label()} with {len(s4.packages())} packages")

    theatres.use("caucasus")
    s3 = mk()
    s3.new(f"Cc{level}{seed}", "F-16C", level, seed=seed)
    if s3.state.start_hour != 8 or clock.START_MIN != 480 or s3.turn_label() != "Day 1, 08:00" or not all("08:00" <= p.start <= "11:59" for p in s3.packages()):
        bad.append(f"{tag}: the Caucasus campaign: start_hour {s3.state.start_hour}, label {s3.turn_label()!r}")
    return {"tag": tag, "bad": bad, "lines": lines}


def bad_values() -> tuple:
    from sqe import theatres
    base = json.loads((ROOT / "sqe" / "data" / "theatres" / "caucasus.json").read_text(encoding="utf-8"))
    bad = []
    for v in (3, 24, -4, "0", True, 8.5):
        d = json.loads(json.dumps(base))
        d["start_hour"] = v
        try:
            theatres._validate(d, "probe")
        except ValueError as e:
            if "start_hour" not in str(e):
                bad.append(f"bad start_hour {v!r}: the error does not name the key")
        else:
            bad.append(f"bad start_hour {v!r}: accepted")
    return bad, 6


def main(seeds, jobs=None) -> int:
    res = parallel.map_cases(one_case, [(lv, sd) for lv in (1, 2, 3) for sd in seeds], jobs, TMP)
    bad = []
    for r in res:
        print("\n".join(r["lines"]))
        bad += r["bad"]
    b, n = bad_values()
    bad += b
    print(f"{n} bad-value cases fed to the pack loader")
    print(f"{len(res)} campaigns ({parallel.map_cases.workers} worker(s))")
    for x in bad:
        print("BAD", x)
    print("CLEAN" if not bad else f"{len(bad)} BAD")
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main([int(a) for a in _args] or [3, 7], _jobs))
