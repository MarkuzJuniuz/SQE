"""S103d probe: the plain F-14B player's waypoint scheme in a built .miz.

    python tools/f14b_player_probe.py [seed ...] [--show] [--jobs N]

Creates campaigns with f14_variant="F-14B" (level 2 and 3, 3 with the red SAMs gone so strikes and more fighter jobs appear), walks a few turns and builds every flyable package with a person in the
F-14B (every flyable flight of the package, so strike, SEAD, CAS, TARCAP, escort and sweep flights all turn up). For each player group in the .miz it checks:
  - at most 3 numbered waypoints between the takeoff point and the landing point, and the landing point is a Land point (the Home Base);
  - NavTargetPoints present, each code (IP, ST, DP, HA) at most once, no code outside that set;
  - a ground job has an ST; a fighter job has a DP;
  - no point after the landing point (DIVERT / TKR / BULLS are not waypoints);
and runs the Mission Editor's lock rules (A: every point between two time-locked points having a locked speed; B: a point past the last time-locked point must not have both free) on the group.
--show prints every checked group's points. Exit 0 = all clean.
One worker process per (level, seed) (S109; --jobs N, default cores minus 2, --jobs 1 = one process); the output is the same either way."""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_f14p_")
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dcs import lua
from sqe.engine import Session
from sqe.models import Role
from sqe.settings import AppSettings

CODES = {"IP", "ST", "DP", "HA"}
GROUND = {"STRIKE", "SEAD", "CAS"}


def player_groups(M):
    for coal in M["coalition"].values():
        for country in coal["country"].values():
            for g in ((country.get("plane") or {}).get("group") or {}).values():
                if any(u.get("skill") in ("Player", "Client") for u in g["units"].values()):
                    yield g


def one_case(task) -> dict:
    """One (level, opened, seed): a fresh Session; returns what the serial loop would have added ({bad, kinds, n, lines})."""
    level, opened, seed, show = task
    parallel.pin_task(f"f14p:{level}:{opened}:{seed}")
    bad, kinds, n, lines = [], {}, 0, []
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s.new(f"P{level}{seed}", "F-14B", level, seed=seed, f14_variant="F-14B")
    st = s.state
    if opened:
        for a in st.assets.values():
            if a.kind.value == "SAM":
                a.health = 0.0
        s.plan_day()
    for _turn in range(4):
        for p in [p for p in s.packages() if s.flyable(p)]:
            for fl in s.flyable(p):
                tag = f"L{level} s{seed} open={opened} #{p.number} {p.objective.type.value} {fl.role.value}"
                s.ai_test = False
                try:
                    s.fly(p.number, fl.id)
                except Exception as e:
                    bad.append(f"{tag}: {type(e).__name__}: {e}")
                    continue
                n += 1
                z = zipfile.ZipFile(s.settings.sortie_miz)
                M = lua.loads(z.read("mission").decode("utf-8", "replace"))["mission"]
                gs = [g for g in player_groups(M) if any(u.get("type") == "F-14B" for u in g["units"].values())]
                if not gs:
                    bad.append(f"{tag}: no F-14B player group")
                    continue
                for g in gs:
                    pts = [g["route"]["points"][k] for k in sorted(g["route"]["points"])]
                    ntp = [g["NavTargetPoints"][k] for k in sorted(g.get("NavTargetPoints") or {})] if g.get("NavTargetPoints") else []
                    codes = [str(t.get("text_comment")) for t in ntp]
                    kinds[(fl.role.value, tuple(sorted(codes)))] = kinds.get((fl.role.value, tuple(sorted(codes))), 0) + 1
                    if show:
                        lines.append((tag, "points:", [(q.get("name"), q.get("type")) for q in pts], "ntp:", codes))
                    if len(pts) > 5 or len(pts) < 2:
                        bad.append(f"{tag}: {len(pts)} points (takeoff + at most 3 + landing)")
                    if pts[-1].get("type") != "Land":
                        bad.append(f"{tag}: the last point is {pts[-1].get('type')} {pts[-1].get('name')}, not the landing")
                    if len(set(codes)) != len(codes) or set(codes) - CODES:
                        bad.append(f"{tag}: nav target codes {codes}")
                    if fl.role.value in GROUND and "ST" not in codes and any(q.get("name") == "TGT" for q in pts) is False and "ST" not in codes:
                        bad.append(f"{tag}: a ground job without an ST point")
                    if fl.role.value not in GROUND and "DP" not in codes:
                        bad.append(f"{tag}: a fighter job without a DP point")
                    # the Editor's lock rules (the same two as `MissionBuilder._free_locked_speeds` frees)
                    L = [i for i, q in enumerate(pts) if q.get("ETA_locked")]
                    for a, b in zip(L, L[1:]):
                        mid = pts[a + 1:b]
                        if mid and all(q.get("speed_locked") for q in mid):
                            bad.append(f"{tag}: rule A: every point between {a} and {b} has a locked speed")
                        if not mid and pts[b].get("speed_locked"):
                            bad.append(f"{tag}: rule A: the second of two side-by-side time-locked points {b} has a locked speed")
                    tail = pts[(L[-1] + 1):] if L else pts[1:]
                    for q in tail:
                        if not q.get("ETA_locked") and not q.get("speed_locked"):
                            bad.append(f"{tag}: rule B: {q.get('name')} past the last time-locked point has both free")
        s.skip_turn()
    return {"bad": bad, "kinds": kinds, "n": n, "lines": lines}


def main(seeds, show, jobs=None) -> int:
    bad, kinds, n = [], {}, 0
    for r in parallel.map_cases(one_case, [(level, opened, seed, show) for level, opened in ((2, False), (3, False), (3, True)) for seed in seeds], jobs, TMP):      # S109: one task per (level, seed), merged in task order
        for ln in r["lines"]:
            print(*ln)
        bad += r["bad"]; n += r["n"]
        for k, v in r["kinds"].items():
            kinds[k] = kinds.get(k, 0) + v
    print(f"{n} player missions built; (role, nav target codes): " + "; ".join(f"{k[0]} {list(k[1])} x{v}" for k, v in sorted(kinds.items())))
    for b in bad[:40]:
        print("  BAD:", b)
    print("CLEAN" if not bad else f"{len(bad)} PROBLEMS")
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _argv = parallel.pop_jobs(sys.argv[1:])
    a = [x for x in _argv if not x.startswith("--")]
    sys.exit(main([int(x) for x in a] or [9], "--show" in _argv, _jobs))
