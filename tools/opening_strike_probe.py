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
  - the strike survives a save and reopen;
  - S104d, the jets: the squadron flies six pairs (one per target: the SA-5s, then the pack's `fill` kinds in turn, deepest / farthest first), is 0 / 12 ready and 12 in refit at `land_min` + 960, "returning" until it lands,
    back in `available` for the 20:00 turn; one log line per struck site; the record and the cooldown clock survive the day's planning and a save; no squadron / 5 ready jets (`short_cases`); the real Syria pack (`syria_case`).
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


def kind_rank(st, kind, base):
    """All live-at-the-start sites of a fill kind, in the order the rule picks them (tier high to low, farthest from the squadron's base, id): computed here independently of f117.opening_picks."""
    import math
    from sqe.models import AssetKind
    want = kind.replace("-", "").lower()
    c = [a for a in st.assets.values() if not a.id.startswith("fsam_") and ((a.kind == AssetKind.EWR) if want == "ewr" else (a.kind == AssetKind.SAM and a.variant.replace("-", "").lower() == want))]
    return sorted(c, key=lambda a: (-a.tier, -math.hypot(a.x - base.x, a.y - base.y), a.id))


def check_jets(st, tag, level, bad, lines, expect_pairs=None):
    """S104d: the squadron state and the picks of the opening strike (the Caucasus dummy pack has the F-117A squadron at Kutaisi, the Syria pack at Incirlik)."""
    from sqe import clock, f117, refit
    from sqe.models import AssetKind
    q = f117.squadrons(st)[0]
    rec = (st.raids or {}).get("opening_strike")
    sa5 = [a for a in st.assets.values() if a.kind == AssetKind.SAM and a.variant == "SA-5"]
    if not rec or rec["squadron"] != q.id:
        bad.append(f"{tag}: no opening_strike record")
        return
    pairs = rec["pairs"]
    if len(pairs) != 6 or q.available != 0 or len(q.refit) != 12 or q.on_hand != q.authorized:
        bad.append(f"{tag}: {len(pairs)} pairs, available {q.available}, refit {len(q.refit)}, on hand {q.on_hand} / {q.authorized} (expected 6 pairs, 0 ready, 12 in refit, 12 / 12)")
    base = st.bases[q.base_id]
    want_refit = sorted(int(round(p["land_min"] + refit.refit_minutes("F-117A", False, 1.0))) for p in pairs for _ in range(2))
    if sorted(q.refit) != want_refit:
        bad.append(f"{tag}: refit minutes {sorted(q.refit)} are not land_min + 960 {want_refit}")
    killed = [st.assets[p["target"]] for p in pairs]
    if not all(a.destroyed and a.id in st.sams.get("down", {}) for a in killed):
        bad.append(f"{tag}: a pair's target is not down and in the rebuild record")
    down = {a.id for a in st.assets.values() if a.kind in (AssetKind.SAM, AssetKind.EWR) and a.destroyed}
    if down != {a.id for a in killed}:
        bad.append(f"{tag}: sites down {sorted(down)} differ from the pairs' targets {[a.id for a in killed]}")
    if not all(a.id in {k.id for k in killed} for a in sa5):
        bad.append(f"{tag}: an SA-5 has no pair")
    fill = [a for a in killed if a.variant != "SA-5"]
    have = {"SA-10": len(kind_rank(st, "SA-10", base)), "EWR": len(kind_rank(st, "EWR", base))}
    take = {"SA-10": 0, "EWR": 0}
    left = len(fill)
    while left and any(take[k] < have[k] for k in take):          # the kinds in turn, a kind with nothing left skipped
        for kind in take:
            if left and take[kind] < have[kind]:
                take[kind] += 1
                left -= 1
    for kind, n in take.items():
        got = [a.id for a in fill if (a.kind == AssetKind.EWR) == (kind == "EWR")]
        top = [a.id for a in kind_rank(st, kind, base)[:n]]
        if sorted(got) != sorted(top):
            bad.append(f"{tag}: {kind} picks {got} are not the top {n} by tier / distance / id {top}")
    for p in pairs:
        a = st.assets[p["target"]]
        d_nm = ((a.x - base.x) ** 2 + (a.y - base.y) ** 2) ** 0.5 / 1852.0
        exp = clock.minute(0) + int(-(-d_nm * f117.OPENING_ROUTE_FACTOR / 480 * 60 // 1)) + f117.OPENING_RECOVERY_MIN
        if abs(p["land_min"] - exp) > 1:
            bad.append(f"{tag}: {a.id} lands at {p['land_min']}, expected {exp}")
    if st.raids.get("f117_last") is None or any(st.raids["f117_last"].get(a.id) != 1 for a in killed):
        bad.append(f"{tag}: the cooldown clock is not day 1 for every struck site")
    site_lines = [x for x in st.log if "destroyed (" in x and "F-117A" in x]
    if len(site_lines) != 6 or any(sum(1 for x in site_lines if a.name in x) != 1 for a in killed):
        bad.append(f"{tag}: the log has {len(site_lines)} site lines, expected one per struck site: {site_lines}")
    note = [x for x in st.log if "on their way home" in x]
    if len(note) != 1 or "all 12" not in note[0]:
        bad.append(f"{tag}: the squadron note is missing or doubled: {note}")
    if f117.returning(st, q) != 12:
        bad.append(f"{tag}: {f117.returning(st, q)} returning at turn 0, expected 12")
    from sqe.gui.app import ForcesPage
    if ForcesPage._refit_note(st, q) != " (12 returning)":
        bad.append(f"{tag}: Overview note {ForcesPage._refit_note(st, q)!r} at turn 0")
    t_save = st.turn
    st.turn = 1
    ret1, objs1, note1 = f117.returning(st, q), f117.objectives(st), ForcesPage._refit_note(st, q)
    st.turn = 5
    if ret1 != 0 or objs1 or note1 != " (12 refitting)":
        bad.append(f"{tag}: turn 1: returning {ret1}, F-117A jobs {len(objs1)}, note {note1!r} (expected 0, none, ' (12 refitting)')")
    refit.step(st, clock.minute(4))
    still = q.available
    refit.step(st, clock.minute(5))
    st.turn = t_save
    if still != 0 or q.available != 12 or q.refit:
        bad.append(f"{tag}: the squadron is back too early or not at all: ready at 16:00 {still}, at 20:00 {q.available}, still in refit {len(q.refit)}")
    # the planner state is not left changed for the later checks: put the jets back into refit
    q.available = 0
    q.refit = want_refit
    lines.append(f"{tag}: pairs {[(p['target'], p['land_min']) for p in pairs]}; ready again {sorted(set(want_refit))}")


def short_cases(st0, th, d, bad, lines, tag):
    """No squadron: only the SA-5 lines; a squadron with 5 ready jets: two pairs, the third SA-5 has no pair and nothing is filled."""
    import copy
    from sqe import scenario, f117
    from sqe.models import AssetKind
    for label, ready in (("no squadron", None), ("5 ready", 5)):
        st = copy.deepcopy(st0)
        for a in st.assets.values():
            if a.kind in (AssetKind.SAM, AssetKind.EWR):
                a.health = 1.0
        st.raids = {}
        st.sams = {}
        if ready is None:
            for k in [k for k, v in st.squadrons.items() if v.aircraft == "F-117A"]:
                del st.squadrons[k]
        else:
            q = f117.squadrons(st)[0]
            q.available, q.refit = ready, []
        out = scenario._opening_strike(st, th, d)
        sa5 = [a for a in st.assets.values() if a.kind == AssetKind.SAM and a.variant == "SA-5"]
        down = [a for a in st.assets.values() if a.kind in (AssetKind.SAM, AssetKind.EWR) and a.destroyed]
        paired = [x for x in out if "(" in x and "destroyed" in x]
        want_down = len(sa5) if ready is None else max(len(sa5), ready // 2)             # no squadron: only the SA-5s; 5 ready = 2 pairs: the SA-5s, then fill up to 2 targets
        if len(down) != want_down or any(not a.destroyed for a in sa5):
            bad.append(f"{tag} {label}: {len(down)} sites down, expected {want_down} ({len(sa5)} SA-5s)")
        if len(out) < 1 + len(sa5):
            bad.append(f"{tag} {label}: the log lines are {out}")
        if ready is None and (paired or (st.raids or {}).get("opening_strike")):
            bad.append(f"{tag} {label}: a pair or a record appeared without a squadron")
        if ready == 5 and (len(paired) != 2 or len((st.raids["opening_strike"])["pairs"]) != 2 or f117.squadrons(st)[0].available != 1):
            bad.append(f"{tag} {label}: expected 2 pairs and 1 ready jet left: {paired}")
        lines.append(f"{tag} {label}: {len(out)} log line(s), {len(down)} down")


def make_pack(root: Path) -> Path:
    pack = root / "packs"
    pack.mkdir(parents=True, exist_ok=True)
    src = ROOT / "sqe" / "data" / "theatres"
    d = json.loads((src / "caucasus.json").read_text(encoding="utf-8"))
    d["id"], d["name"] = "strikepack", "Opening strike pack"
    d["extra_sams"] = EXTRA
    d["opening_strike"] = {"levels": [2, 3], "kill": "sa5", "fill": ["SA-10", "EWR"]}
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
    check_jets(st, tag, level, bad, lines)
    short_cases(st, theatres.use("strikepack"), d, bad, lines, tag)
    n_sa10 = sum(1 for a in st.assets.values() if a.kind == AssetKind.SAM and a.variant == "SA-10" and not a.destroyed)
    lines.append(f"{tag}: SA-5 down {sa5}; SA-10 sites alive {n_sa10}; day {st.day}; opening line: {struck_line[0] if struck_line else None}")
    jobs = [o for o in ObjectivePlanner(d).plan(st, random.Random(seed), limit=80) if o.target_id in sa5]
    pk = [p.number for p in s.packages() if p.objective.target_id in sa5]
    if [p for p in s.packages() if p.objective.aim == "F117" or p.objective.type.name == "STRIKE" and p.objective.aim == "RUNWAY" and p.objective.id.rsplit("-", 1)[-1].startswith("f")]:
        bad.append(f"{tag}: an F-117A package is planned on turn 0 with no jets ready")
    if (st.raids or {}).get("opening_strike") is None:
        bad.append(f"{tag}: the day's planning dropped the opening_strike record")
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
    if (s2.state.raids or {}).get("opening_strike") != st.raids.get("opening_strike") or (s2.state.raids or {}).get("f117_last") != st.raids.get("f117_last"):
        bad.append(f"{tag}: the opening_strike record or the cooldown clock did not survive save and reopen")
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


def syria_case(task) -> dict:
    """S104d, the real pack: Syria L2 and L3 (8th FS at Incirlik, 12 jets): six pairs, the SA-5s then SA-10 / EWR in turn; L2 = 2 SA-5 + 4 EWR, L3 = 3 SA-5 + 2 SA-10 + 1 EWR; the squadron is 0 / 12 ready
    at the start; turn 0 plans no F-117A package; the log names every struck site."""
    _k, level, seed = task
    parallel.pin_task(f"syria:{level}:{seed}")
    from sqe import theatres, f117
    from sqe.engine import Session
    from sqe.models import AssetKind
    from sqe.settings import AppSettings
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    tag = f"Syria L{level} s{seed}"
    s.new(f"Sy{level}{seed}", "F-16C", level, seed=seed, theatre="syria")
    st = s.state
    bad, lines = [], []
    check_jets(st, tag, level, bad, lines)
    rec = st.raids["opening_strike"]["pairs"]
    kinds = [("SA-5" if st.assets[p["target"]].variant == "SA-5" else "EWR" if st.assets[p["target"]].kind == AssetKind.EWR else st.assets[p["target"]].variant) for p in rec]
    want = {2: ["SA-5", "SA-5", "EWR", "EWR", "EWR", "EWR"], 3: ["SA-5", "SA-5", "SA-5", "SA-10", "EWR", "SA-10"]}[level]
    if kinds != want:
        bad.append(f"{tag}: target kinds in order {kinds}, expected {want}")
    if [p for p in s.packages() if f117.is_job(p.objective)]:
        bad.append(f"{tag}: an F-117A package is planned on turn 0")
    q = f117.squadrons(st)[0]
    lines.append(f"{tag}: {q.name} {q.available} / {q.authorized} ready, on hand {q.on_hand}; picks {[(st.assets[p['target']].name, p['land_min']) for p in rec]}")
    lines += [x for x in st.log if "F-117A" in x or "on their way" in x]
    return {"tag": tag, "bad": bad, "lines": lines}


def run_case(task) -> dict:
    return syria_case(task) if task[0] == "syria" else one_case(task)


def bad_values() -> tuple:
    from sqe import theatres
    base = json.loads((ROOT / "sqe" / "data" / "theatres" / "caucasus.json").read_text(encoding="utf-8"))
    cases = [{"levels": [4], "kill": "sa5"}, {"levels": [], "kill": "sa5"}, {"levels": [3], "kill": "sa99"}, {"levels": [3]}, {"levels": [3], "kill": "sa5", "extra": 1}, {"levels": [3], "kill": "sa5", "text": "{nope}"},
             {"levels": [3], "kill": "sa5", "fill": "SA-10"}, {"levels": [3], "kill": "sa5", "fill": ["SA-99"]}, {"levels": [3], "kill": "sa5", "fill": [1]}]
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
    ok["opening_strike"] = {"levels": [2, 3], "kill": "SA-5", "text": "Done: {kill}.", "fill": ["sa10", "EWR", "SA-5"]}
    try:
        theatres._validate(ok, "probe")
    except ValueError as e:
        bad.append(f"a good opening_strike was refused: {e}")
    return bad, len(cases)


def main(seeds, jobs=None) -> int:
    res = parallel.map_cases(run_case, [(lv, sd) for lv in (1, 2, 3) for sd in seeds] + [("syria", lv, sd) for lv in (2, 3) for sd in seeds], jobs, TMP)
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
