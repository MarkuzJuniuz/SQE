"""S111 probe: Lutorin's works (Syria), played idle on the real sim (tools only, nothing ships).

    python tools/works_probe.py [--levels 2,3] [--pushes 1.0,2.0] [--rebuild L:DAYS,...] [--damage X] [--te off|on|decay] [--seeds N] [--days D] [--jobs N]

For every (level, push, seed) it makes a Syria campaign (Tactical Edge off by default; `on` = Tactical Edge on; `decay` = on with the decay), then plays Skip Turn until the war ends or --days days (default 240) and prints the end
(VICTORY / DEFEAT / still ACTIVE), the day, how many works stood at the end and what the war log said. The works' `push` (red's strength added by the works standing) and `rebuild_days` are the pack's `works.levels`
values; this tool overrides them per case, so the values are picked from the sim. Idle = every turn is a Skip Turn, so with Tactical Edge on the red surge runs (nobody flies). One worker process per case
(--jobs N; --jobs 1 = one process); the output is the same either way. Exit 0 always (it measures, it does not assert)."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_works_")
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def one_case(task) -> dict:
    level, push, reb, te, seed, days, dmg = task
    parallel.pin_task(f"works:{level}:{push}:{reb}:{te}:{seed}")
    from sqe import theatres, ground, works
    from sqe.engine import Session
    from sqe.settings import AppSettings
    theatres.use("syria")
    lv = theatres.active()["works"]["levels"][str(level)]
    if dmg is not None:
        lv["damage"] = dmg
    if push is not None:
        lv["push"] = push
    if reb is not None:
        lv["rebuild_days"] = reb
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new(f"W{level}{seed}", "F-16C", level, seed=seed, theatre="syria", tactical_edge=te != "off", tactical_edge_decay=te == "decay")
    st = s.state
    d0 = st.day
    first_down = None
    while st.status == "ACTIVE" and st.day - d0 < days:
        s.skip_turn()
        if first_down is None and works.standing(st) < len(works.ids(st)):
            first_down = st.day - d0
    why = next((x for x in reversed(st.log) if x.startswith(("VICTORY", "DEFEAT"))), "")
    return {"key": (level, push, reb, te, seed), "status": st.status, "days": st.day - d0, "standing": works.standing(st), "total": len(works.ids(st)),
            "first_down": first_down, "fallen": ground.fallen_count(st), "built": int((st.ground.get("works") or {}).get("built", 0)), "why": why[:80]}


def main(argv, jobs=None) -> int:
    a = list(argv)
    opt = {"--levels": "2,3", "--pushes": "", "--rebuild": "", "--te": "off", "--seeds": "6", "--days": "240", "--damage": ""}
    for k in opt:
        if k in a:
            i = a.index(k)
            opt[k] = a[i + 1]
            del a[i:i + 2]
    levels = [int(x) for x in opt["--levels"].split(",")]
    pushes = [float(x) for x in opt["--pushes"].split(",")] if opt["--pushes"] else [None]
    rebs = {int(k): float(v) for k, v in (p.split(":") for p in opt["--rebuild"].split(","))} if opt["--rebuild"] else {}
    tes = opt["--te"].split(",")
    tasks = [(lv, ps, rebs.get(lv), te, sd, int(opt["--days"]), float(opt["--damage"]) if opt["--damage"] else None) for lv in levels for te in tes for ps in pushes for sd in range(1, int(opt["--seeds"]) + 1)]
    t0 = time.time()
    res = sorted(parallel.map_cases(one_case, tasks, jobs, TMP), key=lambda r: tuple(str(x) for x in r["key"]))
    for r in res:
        k = r["key"]
        print(f"L{k[0]} push {k[1]} rebuild {k[2]} TE {k[3]} seed {k[4]}: {r['status']:8} day {r['days']:>3} works {r['standing']}/{r['total']} first down day {r['first_down']} rebuilt {r['built']} fallen {r['fallen']} {r['why']}")
    print()
    groups = sorted({r["key"][:4] for r in res}, key=lambda k: tuple(str(x) for x in k))
    for g in groups:
        rs = [r for r in res if r["key"][:4] == g]
        n = len(rs)
        v, d_, ac = (sum(r["status"] == s for r in rs) for s in ("VICTORY", "DEFEAT", "ACTIVE"))
        med = lambda st_: (sorted(r["days"] for r in rs if r["status"] == st_)[sum(1 for r in rs if r["status"] == st_) // 2] if any(r["status"] == st_ for r in rs) else 0)
        print(f"L{g[0]} push {g[1]} rebuild {g[2]} TE {g[3]}: {n} runs, blue wins {v} ({100 * v // n}%), red wins {d_} ({100 * d_ // n}%), undecided {ac}; median day blue {med('VICTORY')}, red {med('DEFEAT')}")
    print(f"{len(res)} campaigns, {parallel.map_cases.workers} worker(s), {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main(_args, _jobs))
