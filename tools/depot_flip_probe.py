"""S108 part 2: PROBE of the road depots' rule at `road_sites.flip` (the front moves, a depot that would break the new rules falls). Changes no file of the game; dev tool, not shipped.

    python tools/depot_flip_probe.py [--levels 2,3] [--seeds 3,7,11] [--blue 5] [--jobs N]

For each campaign (Caucasus, `road_sites_blue` forced to --blue, the game has 0) it prints the depots the build placed (`ground["road"]["skipped"]`: the spots each new rule kept out), then moves the
front BY HAND: `ground["line_km"]` is shifted by each delta (km, both ways) on a deep copy of the state and `road_sites.flip(state)` runs on it (the nightly war step does the same call after it
moves the line). Per delta: how many depots changed hands, how many fell, the log lines of the falls, and a check of the state after: no road of the two sides interleaved among the live depots, no
red-blue pair of live depots closer than CROSS_SEP_M unless it was already so before the move. One worker per campaign (--jobs, default cores minus 2); the output is the same either way."""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_depotflip_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DELTAS = (-120, -80, -50, -30, -15, 15, 30, 50, 80, 120)


def _live(state, road_sites, ground):
    """{id: (x, y, side)} of the road depots still in play (a fallen one is out)."""
    lost = set((state.ground or {}).get("road_fell") or [])
    out = {}
    for side, pool in (("red", state.assets), ("blue", state.blue_assets)):
        for a in pool.values():
            if road_sites.is_road(a) and a.kind in ground.SUPPLY_KINDS and a.id not in lost:
                out[a.id] = (a.x, a.y, side)
    return out


def _bad(live, rts, road_front, road_sites):
    """(interleaved routes, closest red-blue pair km)."""
    per: dict = {}
    for i, (x, y, s) in live.items():
        for ri, km in road_front.along(rts, x, y):
            per.setdefault(ri, []).append((km, s))
    inter = sum(1 for lst in per.values() if road_sites._changes([s for _k, s in sorted(lst)]) >= 2)
    gap = min((math.hypot(a[0] - b[0], a[1] - b[1]) for a in live.values() for b in live.values() if a[2] == "red" and b[2] == "blue"), default=None)
    return inter, (gap / 1000.0 if gap is not None else None)


def one_case(task) -> dict:
    import copy
    level, seed, blue_n = task
    parallel.pin_task(f"depotflip:{level}:{seed}:{blue_n}")
    from dataclasses import replace
    from sqe import difficulty, theatres, road_front, road_sites, ground
    from sqe.engine import Session
    from sqe.settings import AppSettings
    if blue_n:
        difficulty.LEVELS[level] = replace(difficulty.LEVELS[level], road_sites_blue=blue_n)
    tag = f"L{level} s{seed} +{blue_n} blue"
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new(f"Df{level}{seed}", "F-16C", level, seed=seed)
    st, th = s.state, theatres.active()
    rts = road_front.routes(th) or []
    g = st.ground
    lines = [f"== {tag}: road record {g.get('road')}; line at {g.get('line_km', ground.line_km(g)):.0f} km"]
    line0 = float(g.get("line_km", ground.line_km(g)))
    res = {"tag": tag, "lines": lines, "moved": 0, "fell": 0, "bad": 0}
    for dk in DELTAS:
        c = copy.deepcopy(st)
        c.ground["line_km"] = line0 + dk
        b_inter, b_gap = _bad(_live(c, road_sites, ground), rts, road_front, road_sites)
        log = road_sites.flip(c)
        a_inter, a_gap = _bad(_live(c, road_sites, ground), rts, road_front, road_sites)
        fell = [x for x in log if "it is lost" in x]
        moved = [x for x in log if "it is lost" not in x]
        ok = a_inter <= b_inter and (a_gap is None or a_gap >= road_sites.CROSS_SEP_M / 1000.0 or (b_gap is not None and a_gap >= b_gap - 1e-6))
        res["moved"] += len(moved); res["fell"] += len(fell); res["bad"] += 0 if ok else 1
        lines.append(f"  front {dk:+4d} km: changed hands {len(moved)}, fell {len(fell)}; interleaved routes {b_inter} -> {a_inter}; closest red-blue pair "
                     + ("-" if a_gap is None else f"{a_gap:.1f} km") + ("" if ok else "  RULE BROKEN"))
        for x in fell:
            lines.append(f"      {x}")
    return res


def main(argv, jobs=None) -> int:
    opt = {"--levels": "2,3", "--seeds": "3,7,11", "--blue": "5"}
    for i, x in enumerate(argv):
        if x in opt and i + 1 < len(argv):
            opt[x] = argv[i + 1]
    tasks = [(int(lv), int(sd), int(opt["--blue"])) for lv in opt["--levels"].split(",") for sd in opt["--seeds"].split(",")]
    res = parallel.map_cases(one_case, tasks, jobs, TMP)
    for r in res:
        print("\n".join(r["lines"]))
    print(f"\n{len(res)} campaigns ({parallel.map_cases.workers} worker(s)); changed hands {sum(r['moved'] for r in res)}, fell {sum(r['fell'] for r in res)}, rule broken in {sum(r['bad'] for r in res)} cases")
    return 1 if any(r["bad"] for r in res) else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main(_args, _jobs))
