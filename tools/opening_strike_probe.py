"""S90 J9s probe: the scripted opening strike (pack key `opening_strike`), proved with a dummy pack (tools only, nothing ships).

    python tools/opening_strike_probe.py [seed ...] [--jobs N]

A temp pack `strikepack` (the Caucasus renamed) gets two fixed SA-5 sites (`extra_sams`, levels 2 and 3) and `opening_strike` {"levels": [2, 3], "kill": "sa5"}. For each level and seed the probe makes a
campaign and checks (BAD lines otherwise):
  - L2 / L3: every SA-5 is down (health 0, `destroyed`) and is in the SAM rebuild record with its day (`state.sams["down"]`); no SA-10 or other site was touched; the opening line is in the war log; L1 and the
    Caucasus campaign made after it have no strike line and no SA-5;
  - day 1: the planner (`ObjectivePlanner.plan`, many objectives) offers no job against a downed SA-5, and no package of the planned day names one;
  - the Overview's air-defence rows show them as destroyed;
  - the normal rebuild rule brings them back: `sams.rebuild` is called one day at a time (the war's nightly call) with the level's `sam_rebuild` and the Force Index; the first return is not before the order wait
    (`sams.order_days`, 5 to 7 days), at `sams.REBUILT_HEALTH`, with the replacement line in the log; once back the planner offers jobs against them again (counted; it is a quota, so not every seed shows one);
  - the strike survives a save and reopen.
Exit 0 = all clean. One worker process per (level, seed); the output is the same either way."""
import json
import os
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_strike_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EXTRA = [{"id": "sam_xa5a_0", "site": "SA-5", "x": 480000.0, "y": 260000.0, "levels": [2, 3]},
         {"id": "sam_xa5b_0", "site": "SA-5", "near": "Kutaisi", "bearing": 90, "dist_m": 40000, "levels": [3]}]


def make_pack(root: Path) -> Path:
    pack = root / "packs"
    pack.mkdir(parents=True, exist_ok=True)
    src = ROOT / "sqe" / "data" / "theatres"
    d = json.loads((src / "caucasus.json").read_text(encoding="utf-8"))
    d["id"], d["name"] = "strikepack", "Opening strike pack"
    d["extra_sams"] = EXTRA
    d["opening_strike"] = {"levels": [2, 3], "kill": "sa5"}
    (pack / "strikepack.json").write_text(json.dumps(d), encoding="utf-8")
    for f in src.glob("caucasus_*.json"):
        shutil.copy(f, pack / f.name.replace("caucasus_", "strikepack_"))
    return pack


def one_case(task) -> dict:
    level, seed = task
    parallel.pin_task(f"strike:{level}:{seed}")
    from sqe import theatres, sams, difficulty, overview_detail
    from sqe.engine import Session
    from sqe.models import AssetKind
    from sqe.settings import AppSettings
    from sqe.war import ObjectivePlanner
    theatres.EXTRA_DIRS.append(str(make_pack(TMP)))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    tag = f"L{level} s{seed}"
    bad, lines = [], []
    s = mk()
    s.new(f"St{level}{seed}", "F-16C", level, seed=seed, theatre="strikepack")
    st = s.state
    d = difficulty.get(level)
    sa5 = sorted(a.id for a in st.assets.values() if a.kind == AssetKind.SAM and a.variant == "SA-5")
    must = [e["id"] for e in EXTRA if level in e["levels"]]
    if sa5 != sorted(must):
        bad.append(f"{tag}: SA-5 sites {sa5}, expected {sorted(must)}")
    struck_line = [x for x in st.log if "F-117A Nighthawks" in x]
    if level == 1:
        if struck_line or sa5:
            bad.append(f"{tag}: L1 has a strike line or an SA-5: {struck_line} {sa5}")
        return {"tag": tag, "bad": bad, "lines": [f"{tag}: no strike at L1 (as the pack says)"]}
    if len(struck_line) != 1 or "SA-5" not in struck_line[0]:
        bad.append(f"{tag}: the opening line is missing or doubled: {struck_line}")
    for i in sa5:
        a = st.assets[i]
        if not a.destroyed or a.health != 0.0:
            bad.append(f"{tag}: {i} is not down (health {a.health})")
        if i not in st.sams.get("down", {}):
            bad.append(f"{tag}: {i} is not in the rebuild record")
    others = [a for a in st.assets.values() if a.kind == AssetKind.SAM and a.id not in sa5 and a.destroyed]
    if others:
        bad.append(f"{tag}: other SAM sites are down at the start: {[a.id for a in others]}")
    n_sa10 = sum(1 for a in st.assets.values() if a.kind == AssetKind.SAM and a.variant == "SA-10" and not a.destroyed)
    lines.append(f"{tag}: SA-5 down {sa5}; SA-10 sites alive {n_sa10}; day {st.day}; opening line: {struck_line[0] if struck_line else None}")
    jobs = [o for o in ObjectivePlanner(d).plan(st, random.Random(seed), limit=80) if o.target_id in sa5]
    pk = [p.number for p in s.packages() if p.objective.target_id in sa5]
    if jobs or pk:
        bad.append(f"{tag}: day 1 offers jobs against downed SA-5s: objectives {[o.target_id for o in jobs]}, packages {pk}")
    rows = [r for r in overview_detail.air_defence_rows(st) if any(st.assets[i].name in r[1] for i in sa5)]
    if len(rows) < len(sa5) or not all("destroyed" in str(r[-1]) for r in rows):
        bad.append(f"{tag}: the Overview rows do not show the SA-5s as destroyed: {rows}")
    path = str(TMP / "saves" / f"st{level}{seed}.sqe")
    s.save(path)
    theatres.use("caucasus")
    s2 = mk()
    s2.open(path)
    if not all(s2.state.assets[i].destroyed and i in s2.state.sams.get("down", {}) for i in sa5):
        bad.append(f"{tag}: the strike did not survive save and reopen")
    st = s2.state
    d = difficulty.get(level)
    rng = random.Random(seed)
    first = {}
    for k in range(1, 61):
        st.day += 1
        for ln in sams.rebuild(st, d, rng):
            if "SA-5" in ln:
                lines.append(f"{tag} day +{k}: {ln}")
        for i in sa5:
            if i not in first and not st.assets[i].destroyed:
                first[i] = k
        if len(first) == len(sa5):
            break
    wait = sams.order_days(0.35)
    for i in sa5:
        if i not in first:
            bad.append(f"{tag}: {i} was not rebuilt in 60 days")
        elif first[i] < 5:
            bad.append(f"{tag}: {i} was back after {first[i]} days, before the order wait ({wait} days at the floor)")
        elif st.assets[i].health != sams.REBUILT_HEALTH:
            bad.append(f"{tag}: {i} came back at {st.assets[i].health}, not {sams.REBUILT_HEALTH}")
    back = [o for o in ObjectivePlanner(d).plan(st, random.Random(seed), limit=80) if o.target_id in sa5]
    lines.append(f"{tag}: back after {first} days (half strength {sams.REBUILT_HEALTH}); the planner then offers {len(back)} job(s) against them")
    theatres.use("caucasus")
    s3 = mk()
    s3.new(f"Cc{level}{seed}", "F-16C", level, seed=seed)
    if any("Nighthawk" in x for x in s3.state.log) or any(a.variant == "SA-5" for a in s3.state.assets.values()):
        bad.append(f"{tag}: the Caucasus campaign made after the dummy pack shows a strike or an SA-5")
    return {"tag": tag, "bad": bad, "lines": lines, "back": len(back)}


def bad_values() -> tuple:
    from sqe import theatres
    base = json.loads((ROOT / "sqe" / "data" / "theatres" / "caucasus.json").read_text(encoding="utf-8"))
    cases = [{"levels": [4], "kill": "sa5"}, {"levels": [], "kill": "sa5"}, {"levels": [3], "kill": "sa99"}, {"levels": [3]}, {"levels": [3], "kill": "sa5", "extra": 1}, {"levels": [3], "kill": "sa5", "text": "{nope}"}]
    bad = []
    for v in cases:
        d = json.loads(json.dumps(base))
        d["opening_strike"] = v
        try:
            theatres._validate(d, "probe")
        except ValueError as e:
            if "opening_strike" not in str(e):
                bad.append(f"bad {v}: the error does not name the key: {e}")
        else:
            bad.append(f"bad {v}: accepted")
    ok = json.loads(json.dumps(base))
    ok["opening_strike"] = {"levels": [2, 3], "kill": "SA-5", "text": "Done: {kill}."}
    try:
        theatres._validate(ok, "probe")
    except ValueError as e:
        bad.append(f"a good opening_strike was refused: {e}")
    return bad, len(cases)


def main(seeds, jobs=None) -> int:
    res = parallel.map_cases(one_case, [(lv, sd) for lv in (1, 2, 3) for sd in seeds], jobs, TMP)
    bad = []
    for r in res:
        print("\n".join(r["lines"]))
        bad += r["bad"]
    b, n = bad_values()
    bad += b
    print(f"{n} bad-value cases fed to the pack loader")
    jobs_back = sum(r.get("back", 0) for r in res)
    print(f"{len(res)} campaigns ({parallel.map_cases.workers} worker(s)); jobs offered against rebuilt SA-5s: {jobs_back}")
    for x in bad:
        print("BAD", x)
    print("CLEAN" if not bad else f"{len(bad)} BAD")
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main([int(a) for a in _args] or [3, 7], _jobs))
