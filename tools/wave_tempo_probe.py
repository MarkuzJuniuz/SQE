"""S110 probe: the war's tempo before and after the four launch waves (tools only, nothing ships).

    python tools/wave_tempo_probe.py [--jobs N] [--days 7] [--out FILE.json]       run the cases, print the table (and save the numbers)
    python tools/wave_tempo_probe.py compare BEFORE.json AFTER.json                 the two tables side by side and the deltas

Cases: Caucasus L1 / L2 / L3 and Syria L2 / L3, seeds 3 and 7. The player is idle (Skip Turn) for `--days` days; per case it counts, from the planner's own output:
  pk/day, pk/night      packages planned per day turn / per night turn (mean)
  jets/day              jets launched per day (every sortie the turn committed: packages and standing patrols, blue + red)
  waves                 packages per launch wave, wave 1 / 2 / 3 / 4 (the planner's own `wave`)
  starts                packages per hour after the turn opens, 0-59 / 60-119 / 120-179 / 180-239 (the start times the player sees)
  short                 required seats no squadron could fill (`pb.short` each turn, added up)
  blue cap, red cap     standing patrol + guard pairs a turn (blue: BARCAP and AWACS / tanker guards), red CAP pairs a turn
  raids/day             red raids booked a day (`st.raids["booked"]`)
  ready                 mean ready blue jets at the start of a turn
  blue lost, red lost   jets lost in the sorties after `--days` days
Run it on a CLEAN WORKTREE of the branch before the change (SQE_PROBE_REPO=<worktree>, the code is imported from there; this file always comes from the tools folder it sits in) and on the change; compare.
One worker process per case (rules section 4: use all the cores); each case is pinned like miz_identity and has its own temp folder, so the output is the same serial or parallel and on every run."""
import collections
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_wavetempo_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(os.environ.get("SQE_PROBE_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))

CASES = [("caucasus", 1, 3), ("caucasus", 1, 7), ("caucasus", 2, 3), ("caucasus", 2, 7), ("caucasus", 3, 3), ("caucasus", 3, 7),
         ("syria", 2, 3), ("syria", 2, 7), ("syria", 3, 3), ("syria", 3, 7)]
BLUE_CAP_KINDS = ("BASE_BARCAP", "CARRIER_BARCAP", "HAVCAP", "TKR_HAVCAP")


def one_case(task) -> dict:
    theatre, level, seed, days = task
    parallel.pin_task(f"wave:{theatre}:{level}:{seed}")
    from sqe import clock, engine, ground, refit
    from sqe.settings import AppSettings
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    turns = {}                                                       # turn -> numbers of the LAST plan of that turn (a replan replaces it)
    sorties = collections.defaultdict(int)                           # day -> jets launched
    lost = {"blue": 0, "red": 0}
    shorts = {}
    cur = {"short": 0}

    _note = ground.note_shortfall

    def note(st, short):
        cur["short"] = len(short)
        return _note(st, short)
    ground.note_shortfall = note

    _ct = refit.commit_turn

    def commit(state, sl, rng=None):
        for s in sl:
            sorties[state.day] += int(s["flew"])
            lost[s["side"]] += int(s["lost"])
        return _ct(state, sl, rng)
    refit.commit_turn = commit

    _pt = engine.Session.plan_turn

    def plan(self):
        st = self.state
        ready = sum(int(q.available) for q in st.squadrons.values())
        cur["short"] = 0
        r = _pt(self)
        turn = st.turn
        t0 = clock.minute(turn) - clock.day_start_minute(st.day)
        pk = list(st.plan or [])
        bf = [f for f in ((st.barcap or {}).get("blue_flights") or []) if f.get("turn") == turn]
        rf = [f for f in ((st.red_air or {}).get("flights") or []) if f.get("turn") == turn and f.get("kind") == "CAP"]
        starts = collections.Counter()
        for p in pk:
            s = p.get("start") or "00:00"
            starts[max(0, min(3, (int(s[:2]) * 60 + int(s[3:5]) - t0) // 60))] += 1
        turns[turn] = {"day": st.day, "night": bool(clock.is_night_turn(turn)), "pk": len(pk), "ready": ready, "short": cur["short"],
                       "waves": dict(collections.Counter(int((p.get("extra") or {}).get("wave", 1)) for p in pk)), "starts": dict(starts),
                       "bcap": sum(1 for f in bf if f["kind"] in BLUE_CAP_KINDS), "rcap": len(rf), "raids": len((st.raids or {}).get("booked") or {})}
        return r
    engine.Session.plan_turn = plan

    s = engine.Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new(f"W{theatre[:1]}{level}{seed}", "F-16C", level, seed=seed, theatre=theatre)
    n = 0
    while s.state.day <= days and s.state.status == "ACTIVE" and n < 400:
        s.skip_turn()
        n += 1
    return {"case": f"{theatre} L{level} s{seed}", "turns": n, "final_day": s.state.day, "status": s.state.status, "per_turn": {str(k): v for k, v in turns.items()},
            "jets_by_day": {str(k): v for k, v in sorted(sorties.items())}, "lost": lost}


def digest(r: dict) -> dict:
    """The numbers of one case as the table prints them."""
    pt = list(r["per_turn"].values())
    day = [t for t in pt if not t["night"]]
    night = [t for t in pt if t["night"]]
    mean = lambda xs: (sum(xs) / len(xs)) if xs else 0.0
    waves, starts = [0] * 4, [0] * 4
    for t in pt:
        for w, c in t["waves"].items():
            waves[min(3, int(w) - 1)] += c
        for h, c in t["starts"].items():
            starts[int(h)] += c
    full = [d for d in r["jets_by_day"] if int(d) < r["final_day"]]              # complete days only
    nd = max(1, len({t["day"] for t in pt}))
    return {"case": r["case"], "pk_day": mean([t["pk"] for t in day]), "pk_night": mean([t["pk"] for t in night]), "jets_day": mean([r["jets_by_day"][d] for d in full]) if full else 0.0,
            "waves": waves, "starts": starts, "short": sum(t["short"] for t in pt), "bcap": mean([t["bcap"] for t in pt]), "rcap": mean([t["rcap"] for t in pt]),
            "raids_day": sum(t["raids"] for t in pt) / nd, "ready": mean([t["ready"] for t in pt]), "blue_lost": r["lost"]["blue"], "red_lost": r["lost"]["red"], "turns": r["turns"]}


COLS = [("pk_day", "pk/day", 5.2), ("pk_night", "pk/nt", 5.2), ("jets_day", "jets/day", 8.1), ("short", "short", 5.0), ("bcap", "bcap/t", 6.2), ("rcap", "rcap/t", 6.2),
        ("raids_day", "raid/d", 6.2), ("ready", "ready", 6.1), ("blue_lost", "b.lost", 6.0), ("red_lost", "r.lost", 6.0)]


def row(d: dict) -> str:
    out = f"{d['case']:<18}"
    for k, _h, w in COLS:
        out += f" {d[k]:>{int(w)}.{int(round((w % 1) * 10))}f}"
    return out + "  waves " + "/".join(str(x) for x in d["waves"]) + "  starts " + "/".join(str(x) for x in d["starts"])


def table(ds: list) -> str:
    head = f"{'case':<18}" + "".join(f" {h:>{int(w)}}" for _k, h, w in COLS)
    return "\n".join([head] + [row(d) for d in ds])


def compare(a: list, b: list) -> str:
    out = ["BEFORE", table(a), "", "AFTER", table(b), "", "DELTA (after - before; percent for the rates)"]
    out.append(f"{'case':<18}" + "".join(f" {h:>{int(w)}}" for _k, h, w in COLS))
    tot_a, tot_b = collections.defaultdict(float), collections.defaultdict(float)
    for x, y in zip(a, b):
        line = f"{x['case']:<18}"
        for k, _h, w in COLS:
            tot_a[k] += x[k]
            tot_b[k] += y[k]
            line += f" {y[k] - x[k]:>+{int(w)}.{int(round((w % 1) * 10))}f}"
        out.append(line)
    out.append("")
    out.append("ALL CASES (sum): " + ", ".join(f"{h} {tot_a[k]:.1f} -> {tot_b[k]:.1f} ({(100 * (tot_b[k] - tot_a[k]) / tot_a[k]) if tot_a[k] else 0:+.0f}%)" for k, h, _w in COLS))
    flags = []
    for k in ("pk_day", "jets_day"):
        if tot_a[k] and tot_b[k] > tot_a[k] * 1.25:
            flags.append(f"FLAG: {k} is up more than 25%")
    if tot_b["short"] > tot_a["short"]:
        flags.append("FLAG: required seats short rose")
    return "\n".join(out + flags)


def main(argv) -> int:
    if argv and argv[0] == "compare":
        a, b = (json.load(open(p)) for p in argv[1:3])
        print(compare([digest(r) for r in a], [digest(r) for r in b]))
        return 0
    jobs, argv = parallel.pop_jobs(argv)
    days, outp = 7, None
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])
    if "--out" in argv:
        outp = argv[argv.index("--out") + 1]
    t0 = time.time()
    res = parallel.map_cases(one_case, [(t, lv, sd, days) for t, lv, sd in CASES], jobs, TMP)
    res.sort(key=lambda r: r["case"])
    print(f"repo {ROOT}   {len(res)} cases, {parallel.map_cases.workers} worker(s), {time.time() - t0:.0f} s, {days} days each")
    print(table([digest(r) for r in res]))
    if outp:
        json.dump(res, open(outp, "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
