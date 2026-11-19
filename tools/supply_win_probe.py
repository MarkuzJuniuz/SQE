"""S90 probe: the Force Index win (pack key `win_supply`), measured and proved with a dummy pack (tools only, nothing ships).

    python tools/supply_win_probe.py [--days N] [--below X] [--need N] [seed ...] [--jobs N]

A temp pack `supplypack` (the Caucasus renamed) gets `win_supply` for levels 2 and 3. For each level (2, 3) and seed the probe plays the campaign with the player idle (every turn is a Skip Turn: the war
simulation plays both sides' packages, the blue side strikes red's depots and fuel with the packages the planner gives it) for --days days (default 40) and prints red's Force Index (`ground.supply`) at each
night, the day it first falls to or below 0.50 / 0.45 / 0.40 / 0.35, and the day the pack's rule (below --below, default 0.40, for --need days, default 3) ended the war. That is the sim the values are picked
from; with the rule ON the campaign stops at the win (the `VICTORY` status).
Checks (BAD lines otherwise): the counter `ground["supply_low"]` counts consecutive nights at or below the line and resets on a night above it; the win sets `supply_won`, the status VICTORY and the pack's `win`
story beat in the log; the counter and the win survive save and reopen; the Overview line reads one of distant / approaching / close / under way and nothing else; the old air / command win still works
at these levels (red's command posts and air arm broken by hand: VICTORY); the Caucasus (no key) has no collapse word, no counter and the same status as before. A last block feeds bad `win_supply` values to the loader.
Exit 0 = all clean. One worker process per (level, seed); the output is the same either way."""
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_supplywin_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OPT = {"days": 40, "below": 0.40, "need": 3}


def make_pack(root: Path, below: float, need: int) -> Path:
    pack = root / "packs"
    pack.mkdir(parents=True, exist_ok=True)
    src = ROOT / "sqe" / "data" / "theatres"
    d = json.loads((src / "caucasus.json").read_text(encoding="utf-8"))
    d["id"], d["name"] = "supplypack", "Supply win pack"
    d["win_supply"] = {"2": {"below": below, "days": need}, "3": {"below": below, "days": need}}
    d["front"] = {**d["front"], "victory": {k: v for k, v in (d["front"].get("victory") or {}).items() if k == "1"}}      # like Syria: only L1 is won on the ground (L2 / L3: no victory bases, `by_ground` False)
    d["stories"] = json.loads(json.dumps(d["stories"]))
    for lv in d["stories"].values():                                              # a win beat the probe can find in the log
        lv.setdefault("beats", {})["win"] = "PROBE-WIN-BEAT"
    (pack / "supplypack.json").write_text(json.dumps(d), encoding="utf-8")
    for f in src.glob("caucasus_*.json"):
        shutil.copy(f, pack / f.name.replace("caucasus_", "supplypack_"))
    return pack


def one_case(task) -> dict:
    level, seed, days, below, need = task
    parallel.pin_task(f"supplywin:{level}:{seed}")
    from sqe import theatres, ground, posture
    from sqe.engine import Session
    from sqe.settings import AppSettings
    theatres.EXTRA_DIRS.append(str(make_pack(TMP, below, need)))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    tag = f"L{level} s{seed}"
    bad, lines = [], []
    s = mk()
    s.new(f"Sw{level}{seed}", "F-16C", level, seed=seed, theatre="supplypack")
    st = s.state
    series, first, won_day = [], {}, None
    words = set()
    for _day in range(1, days + 1):
        d0 = st.day
        while st.day == d0 and st.status == "ACTIVE":                                   # one campaign day: until the clock crosses midnight (the nightly checks ran)
            s.skip_turn()
        v = ground.supply(st, "red")
        series.append(round(v, 2))
        for lim in (0.50, 0.45, 0.40, 0.35):
            if v <= lim and lim not in first:
                first[lim] = st.day
        w = ground.supply_collapse_word(st)
        if st.status == "ACTIVE" and w not in ("distant", "approaching", "close", "under way"):
            bad.append(f"{tag}: day {st.day}: the collapse word is {w!r}")
        words.add(w)
        if st.status == "ACTIVE" and any("supply collapse" in x for x in posture.supply_lines(st)) is False:
            bad.append(f"{tag}: the Overview shows no collapse line")
        if st.status != "ACTIVE":
            won_day = st.day
            break
    lines.append(f"{tag}: red Force Index by night: {series}")
    lines.append(f"{tag}: first night at or below 0.50 / 0.45 / 0.40 / 0.35: " + " / ".join(str(first.get(k, "never")) for k in (0.50, 0.45, 0.40, 0.35))
                 + f"; status {st.status}" + (f" on day {won_day}" if won_day else f" after {days} days") + f"; words seen {sorted(map(str, words))}")
    if st.status == "VICTORY":
        if not st.ground.get("supply_won") or not any("PROBE-WIN-BEAT" in x for x in st.log):
            bad.append(f"{tag}: VICTORY without supply_won or the win beat in the log")
        path = str(TMP / "saves" / f"sw{level}{seed}.sqe")
        s.save(path)
        s2 = mk()
        s2.open(path)
        if s2.state.status != "VICTORY" or not s2.state.ground.get("supply_won"):
            bad.append(f"{tag}: the win did not survive save and reopen")
    else:                                                                              # the counter survives a save too
        path = str(TMP / "saves" / f"sw{level}{seed}.sqe")
        st.ground["supply_low"] = 2
        s.save(path)
        s2 = mk()
        s2.open(path)
        if int(s2.state.ground.get("supply_low", 0)) != 2:
            bad.append(f"{tag}: the collapse counter did not survive save and reopen")
    # unit checks on a fresh campaign: the rule, the reset, the old win
    s3 = mk()
    s3.new(f"Sx{level}{seed}", "F-16C", level, seed=seed, theatre="supplypack")
    st3 = s3.state
    from sqe.models import AssetKind
    real = ground.supply
    try:
        ground.supply = lambda state, side: below - 0.01 if side == "red" else real(state, side)
        for k in range(1, need):
            ground.update_supply_win(st3)
            if st3.ground.get("supply_low") != k or st3.ground.get("supply_won"):
                bad.append(f"{tag}: after {k} low nights: supply_low {st3.ground.get('supply_low')}, won {st3.ground.get('supply_won')}")
        ground.supply = lambda state, side: below + 0.05 if side == "red" else real(state, side)
        ground.update_supply_win(st3)
        if st3.ground.get("supply_low") != 0:
            bad.append(f"{tag}: a night above the line did not reset the count ({st3.ground.get('supply_low')})")
        ground.supply = lambda state, side: below if side == "red" else real(state, side)
        for _ in range(need):
            ln = ground.update_supply_win(st3)
        if not st3.ground.get("supply_won") or not any("PROBE-WIN-BEAT" in x for x in ln):
            bad.append(f"{tag}: {need} nights at exactly the line did not win ({st3.ground.get('supply_low')}, {ln})")
    finally:
        ground.supply = real
    s5 = mk()
    s5.new(f"Sy{level}{seed}", "F-16C", level, seed=seed, theatre="supplypack")
    st5 = s5.state
    for a in st5.assets.values():
        if a.kind == AssetKind.C2:
            a.health = 0.0
    for w_ in st5.enemy_air:
        for q in w_.sqns:
            q.available = q.reserve = 0
    from sqe import war
    war.update_status(st5)
    if st5.status != "VICTORY" or "command structure" not in st5.log[-1]:
        bad.append(f"{tag}: the old air / command win no longer works with a win_supply rule: {st5.status}")
    theatres.use("caucasus")
    s6 = mk()
    s6.new(f"Cc{level}{seed}", "F-16C", level, seed=seed)
    if ground.supply_collapse_word(s6.state) is not None or any("collapse" in x for x in posture.supply_lines(s6.state)) or s6.state.ground.get("supply_low"):
        bad.append(f"{tag}: the Caucasus shows a collapse word / counter")
    return {"tag": tag, "bad": bad, "lines": lines}


def bad_values() -> tuple:
    from sqe import theatres
    base = json.loads((ROOT / "sqe" / "data" / "theatres" / "caucasus.json").read_text(encoding="utf-8"))
    cases = [{"4": {"below": 0.4, "days": 3}}, {"2": {"below": 0, "days": 3}}, {"2": {"below": 1.5, "days": 3}}, {"2": {"below": 0.4, "days": 0}}, {"2": {"below": 0.4}},
             {"2": {"below": 0.4, "days": 3, "x": 1}}, {"2": {"below": "low", "days": 3}}, [1]]
    bad = []
    for v in cases:
        d = json.loads(json.dumps(base))
        d["win_supply"] = v
        try:
            theatres._validate(d, "probe")
        except ValueError as e:
            if "win_supply" not in str(e):
                bad.append(f"bad {v}: the error does not name the key")
        else:
            bad.append(f"bad {v}: accepted")
    ok = json.loads(json.dumps(base))
    ok["win_supply"] = {"2": {"below": 0.4, "days": 3}, "3": {"below": 0.4, "days": 2}}
    try:
        theatres._validate(ok, "probe")
    except ValueError as e:
        bad.append(f"a good win_supply was refused: {e}")
    return bad, len(cases)


def main(argv, jobs=None) -> int:
    args = list(argv)
    for k in ("--days", "--below", "--need"):
        if k in args:
            i = args.index(k)
            OPT[k[2:]] = type(OPT[k[2:]])(args[i + 1])
            del args[i:i + 2]
    seeds = [int(a) for a in args] or [3, 7, 11]
    res = parallel.map_cases(one_case, [(lv, sd, OPT["days"], OPT["below"], OPT["need"]) for lv in (2, 3) for sd in seeds], jobs, TMP)
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
    sys.exit(main(_args, _jobs))
