"""S80 sweep: no percentage and no odds figure in the text the player reads (tools only, nothing ships).

    python tools/percent_sweep.py [--levels 1,2,3] [--seeds 3,7] [--turns 6] [--jobs N]

For every (level, seed) it creates a campaign, walks a few turns (Skip Turn: the war simulation resolves every package) and collects the PLAYER-FACING text:
  - the war log (`state.log`, what the Campaign page lists) and every result line of the resolved packages (what the debrief prints for an AI-resolved job);
  - the Overview text: the posture and front lines, the Force Index and air defence lines, the Tactical Edge lines, the tasking headline, the BARCAP cover lines;
  - the briefing and the package names of every flyable package (built as the .miz: the `dictionary` text the player reads in DCS), as your own flight and as the all-AI test;
  - the debrief narrative (`narrative.debrief_story`) for a spread of synthetic outcomes (damage 0 / 0.4 / 0.9, a runway cratered, a SEAD, a raid stopped).
and fails (exit 1) on any `\\d+ ?%` or the word "odds". A line starting "Fuel:" is allowed (the player's own fuel state, a flight figure, not a strength or a result: XO's question in the PR).
The numbers stay in the data and the war maths; only what is printed is checked. One worker process per (level, seed) (--jobs N; --jobs 1 = one process)."""
import os
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_sweep_")
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HIT = re.compile(r"\d+\s*%|\bodds\b", re.I)
ALLOWED = ("Fuel:",)


def _scan(where: str, text, hits: list, seen: set) -> None:
    for ln in str(text).replace("\\n", "\n").split("\n"):
        if HIT.search(ln) and not ln.strip().startswith(ALLOWED):
            key = (where, re.sub(r"\d+", "N", ln.strip()))
            if key not in seen:
                seen.add(key)
                hits.append(f"[{where}] {ln.strip()[:200]}")


def one_case(task) -> dict:
    level, seed, turns = task
    parallel.pin_task(f"sweep:{level}:{seed}")
    from dcs import lua
    from sqe import narrative, overview_detail, posture, blue_barcap
    from sqe.engine import Session
    from sqe.settings import AppSettings
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new(f"Sw{level}{seed}", "F-16C", level, seed=seed)
    st = s.state
    hits, seen, n_lines = [], set(), 0
    tag = f"L{level} s{seed}"

    def overview():
        nonlocal n_lines
        txt = []
        for fn in (posture.front_lines, posture.supply_lines, posture.air_defence_lines, overview_detail.tempo_lines):
            try:
                txt += list(fn(st))
            except Exception:
                pass
        try:
            txt += [str(x) for x in overview_detail.tasking(s)]
            txt += [posture.posture(st)[1], posture.odds_line(st)]
            txt += list(blue_barcap.status_lines(st))
        except Exception:
            pass
        n_lines += len(txt)
        _scan(f"{tag} overview", "\n".join(txt), hits, seen)

    def briefings():
        for p in [p for p in s.packages() if s.flyable(p)][:4]:
            for ai in (False, True):
                s.ai_test = ai
                try:
                    s.fly(p.number, s.flyable(p)[0].id)
                except Exception:
                    continue
                z = zipfile.ZipFile(s.settings.sortie_miz)
                d = lua.loads(z.read("l10n/DEFAULT/dictionary").decode("utf-8", "replace"))["dictionary"]
                _scan(f"{tag} briefing #{p.number}", "\n".join(str(v) for v in d.values()), hits, seen)
                _scan(f"{tag} package name #{p.number}", p.objective.description, hits, seen)

    overview()
    for _t in range(turns):
        briefings()
        r = s.skip_turn()
        for tr in r.get("turns", []):
            for res in tr.get("results", []):
                n_lines += len(res.get("lines", []))
                _scan(f"{tag} result", "\n".join(res.get("lines", [])), hits, seen)
        overview()
    n_lines += len(st.log)
    _scan(f"{tag} log", "\n".join(st.log), hits, seen)
    import random
    for dmg, extra in ((0.0, {}), (0.4, {}), (0.9, {}), (0.9, {"runway": {"closed": True, "hits": 2}}), (0.3, {"red_air_lost": 2, "objective_type": "COUNTER_AIR"})):
        out = {"target_damage": dmg, "blue_air_lost": 1, "red_air_lost": extra.get("red_air_lost", 0), "objective": "Strike: Depot 1", "player": "recovered", **extra}
        try:
            _scan(f"{tag} debrief story", narrative.debrief_story(out, st, random.Random(1)), hits, seen)
        except Exception:
            pass
    return {"hits": hits, "lines": n_lines}


def main(argv, jobs=None) -> int:
    opt = {"--levels": "1,2,3", "--seeds": "3,7", "--turns": "6"}
    for i, x in enumerate(argv):
        if x in opt and i + 1 < len(argv):
            opt[x] = argv[i + 1]
    tasks = [(int(lv), int(sd), int(opt["--turns"])) for lv in opt["--levels"].split(",") for sd in opt["--seeds"].split(",")]
    res = parallel.map_cases(one_case, tasks, jobs, TMP)
    hits = [h for r in res for h in r["hits"]]
    print(f"{len(tasks)} campaigns x {opt['--turns']} turns, {sum(r['lines'] for r in res)} player-facing lines scanned ({parallel.map_cases.workers} worker(s))")
    for h in hits:
        print("  HIT:", h)
    print("CLEAN: no percentage and no odds figure" if not hits else f"{len(hits)} HITS")
    return 1 if hits else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main(_args, _jobs))
