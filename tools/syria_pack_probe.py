"""S90 J7 probe: the Syria 2000 theatre pack (tools only, nothing ships).

    python tools/syria_pack_probe.py [--jobs N] [--seeds 5,7]

For levels 1, 2 and 3 (and each seed) it creates a Syria campaign with the pack's own Era Equipment, and reports / checks (BAD lines otherwise; exit 0 = clean):
  blue    - 284 jets (272 + the 12 F-117As of the 8th FS, PR #623), the era airframes (A-10A, F-14B), every squadron on a base that can park it (`placement`), callsigns unique;
  red     - the jets of each level (L1 94, L2 202, L3 238 + the Damascus bomber wing 16 + 8 at L3), each field's jets against its DCS parking (all spots and the heavy spots), types inside the pack's roster;
  sites   - SAMs by variant, the fixed SA-5s (L2 two, L3 three) down on day 1 and in the rebuild record, EWRs, the support targets, every ground asset on land;
  front   - the sectors (L1 5, L2 8, L3 11), stages, the Bassel victory (L1 only), `win_supply` (L2 / L3), defeat after one lost base;
  day 1   - the campaign starts at 00:00, the war log carries the opening strike line once (L2 / L3) and the story's open beat;
  save    - a saved Syria campaign opens in a fresh session;
  missions- the day is planned, every flyable package of the first six builds as the all-AI test, one as the player's own flight; each carries a flight for its first job.
One worker process per case (--jobs N); the output is the same either way."""
import math
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_syria_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ROSTER_TOTAL = {1: 94, 2: 202, 3: 238}
SECTORS = {1: 5, 2: 8, 3: 11}
SA5 = {1: 0, 2: 2, 3: 3}
BOMBERS = {1: (0, 0), 2: (0, 0), 3: (16, 12)}
DAYS = 12


def one_case(task) -> dict:
    level, seed = task
    parallel.pin_task(f"syria:{level}:{seed}")
    bad, lines = [], []
    from sqe import theatres, difficulty, ground, redroster, seacheck
    from sqe.engine import Session
    from sqe.models import AssetKind
    from sqe.settings import AppSettings
    from sqe.aircraft import AIRCRAFT
    from dcs import terrain as T
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    tag = f"L{level} s{seed}"
    s = mk()
    s.new(f"Sy{level}{seed}", "F-16C", level, seed=seed, theatre="syria")
    st = s.state
    th = theatres.active()
    t = theatres.terrain()

    # ---- blue
    sq = list(st.squadrons.values())
    jets = sum(q.authorized for q in sq)
    if jets != 284:
        bad.append(f"{tag}: blue has {jets} jets, expected 284")
    types = sorted({q.aircraft for q in sq})
    if "A-10A" not in types or "F-14B" not in types or "A-10C" in types or "F-14BU" in types:
        bad.append(f"{tag}: blue airframes {types} (the pack's era says A-10A and F-14B)")
    if len({q.callsign for q in sq}) != len(sq):
        bad.append(f"{tag}: blue callsigns are not unique")
    from sqe import callsigns
    for q in sq:                                                                      # DCS knows a callsign per airframe: a name outside the airframe's table breaks the mission build (Lobo is an F-16C name, not an F-15E one)
        if q.callsign not in callsigns.table(q.aircraft):
            bad.append(f"{tag}: {q.name}: callsign {q.callsign!r} is not in the {q.aircraft} table")
    per_base = {}
    for q in sq:
        per_base[q.base_id] = per_base.get(q.base_id, 0) + q.authorized
    lines.append(f"{tag}: blue {jets} jets {sorted(set(types))}; by base " + ", ".join(f"{k} {v}" for k, v in sorted(per_base.items())))

    # ---- red
    fields = {a.id: a for a in st.assets.values() if a.kind == AssetKind.AIRFIELD}
    jets_at = {}
    heavy_at = {}
    by_type = {}
    for w in st.enemy_air:
        for q in w.sqns:
            if w.base_asset_id == th["bomber_base"] and (q.aircraft == "Tu_22M3" or q.role == "escort"):
                continue
            jets_at[w.base_asset_id] = jets_at.get(w.base_asset_id, 0) + q.authorized
            if q.aircraft in redroster.HEAVY:
                heavy_at[w.base_asset_id] = heavy_at.get(w.base_asset_id, 0) + q.authorized
            by_type[q.aircraft] = by_type.get(q.aircraft, 0) + q.authorized
    total = sum(jets_at.values())
    ros = th["red_roster"][str(level)]
    if not set(by_type) <= set(ros):
        bad.append(f"{tag}: red flies {sorted(by_type)} but the roster is {sorted(ros)}")
    if total != ROSTER_TOTAL[level]:
        bad.append(f"{tag}: red has {total} jets, the roster says {ROSTER_TOTAL[level]} (short: {ROSTER_TOTAL[level] - total}; per type {dict(sorted(by_type.items()))} against {ros})")
    rows = []
    for fid, a in sorted(fields.items()):
        if fid not in th["wing_weight"] and fid not in jets_at:
            continue
        slots = len(t.airports[a.airport].parking_slots) if a.airport else 0
        rows.append(f"{fid[3:]} {jets_at.get(fid, 0)}j/{heavy_at.get(fid, 0)}h of {slots}")
        if slots and jets_at.get(fid, 0) > slots:
            bad.append(f"{tag}: {fid} holds {jets_at.get(fid, 0)} jets on {slots} parking spots")
    lines.append(f"{tag}: red {total} jets {dict(sorted(by_type.items()))}; " + ", ".join(rows))
    tu = sum(q.authorized for w in st.enemy_air for q in w.sqns if q.aircraft == "Tu_22M3")
    esc = sum(q.authorized for w in st.enemy_air for q in w.sqns if q.role == "escort")
    if (tu, esc) != BOMBERS[level]:
        bad.append(f"{tag}: Tu-22M3 {tu} + escorts {esc}, expected {BOMBERS[level]}")
    d = difficulty.get(level)
    lines.append(f"{tag}: bombers {tu} + {esc} escorts at {th['bomber_base']} (difficulty bomber_wing {d.bomber_wing})")

    # ---- sites
    sams = [a for a in st.assets.values() if a.kind == AssetKind.SAM]
    by_var = {}
    for a in sams:
        by_var[a.variant] = by_var.get(a.variant, 0) + 1
    sa5 = [a for a in sams if a.variant == "SA-5"]
    if len(sa5) != SA5[level]:
        bad.append(f"{tag}: {len(sa5)} SA-5 sites, expected {SA5[level]}")
    for a in sa5:
        if not a.destroyed or a.id not in (getattr(st, "sams", {}) or {}).get("down", {}):
            bad.append(f"{tag}: {a.id} is not down / not in the rebuild record on day 1")
    ewr = [a for a in st.assets.values() if a.kind == AssetKind.EWR]
    lines.append(f"{tag}: SAM sites {dict(sorted(by_var.items()))}, SA-5 down {sum(1 for a in sa5 if a.destroyed)}/{len(sa5)}, EWR {len(ewr)}, assets {len(st.assets)}")
    sea = [a.id for a in st.assets.values() if a.kind != AssetKind.AIRFIELD and not seacheck.is_land(a.x, a.y)]
    if sea:
        bad.append(f"{tag}: {len(sea)} red assets lie in the sea: {sea[:8]}")
    from sqe import relief
    for x in sa5:                                                                     # the fixed SA-5s: where, and how high the ground
        lines.append(f"{tag}: {x.id} at {x.x:.0f}, {x.y:.0f}, ground {relief.ground_m(x.x, x.y)} m, land {seacheck.is_land(x.x, x.y)}")

    # ---- front, day 1
    g = st.ground
    nz = len(g["centers"])
    if nz != SECTORS[level]:
        bad.append(f"{tag}: {nz} sectors, expected {SECTORS[level]}")
    if ground.defeat_bases() != 1:
        bad.append(f"{tag}: defeat_bases {ground.defeat_bases()}")
    if (level == 1) != bool(g.get("victory_ids")):
        bad.append(f"{tag}: victory ids {g.get('victory_ids')}")
    if (level > 1) != bool(ground.supply_win_rule(st)):
        bad.append(f"{tag}: win_supply rule {ground.supply_win_rule(st)}")
    lines.append(f"{tag}: {nz} sectors, stages {g['stages']}, victory {g.get('victory_ids')}, supply rule {ground.supply_win_rule(st)}, start hour {st.start_hour}")
    if st.start_hour != 0:
        bad.append(f"{tag}: start hour {st.start_hour}")
    notes = [n for n in st.log] if hasattr(st, "log") else []
    strike = [n for n in notes if "Nighthawks" in str(n)]
    if (level > 1) != (len(strike) == 1):
        bad.append(f"{tag}: the opening strike line appears {len(strike)} times")
    opens = [n for n in notes if "LEVANT HORIZON" in str(n)]
    if not opens:
        bad.append(f"{tag}: no 'LEVANT HORIZON' open beat in the log")
    lines.append(f"{tag}: log: " + " | ".join(str(n) for n in notes[:4]))

    # ---- save / reopen
    path = str(TMP / "saves" / f"sy{level}{seed}.sqe")
    s.save(path)
    theatres.use("caucasus")
    s2 = mk()
    s2.open(path)
    if theatres.active()["id"] != "syria" or len([a for a in s2.state.assets.values() if a.variant == "SA-5"]) != SA5[level]:
        bad.append(f"{tag}: the reopened campaign lost the Syria pack or its SA-5s")

    # ---- missions
    s2.plan_day()
    pk = s2.packages()
    kinds = {}
    for p in pk:
        kinds[p.objective.type.value] = kinds.get(p.objective.type.value, 0) + 1
    lines.append(f"{tag}: day plan {len(pk)} packages {dict(sorted(kinds.items()))}")
    from sqe.packages import PackageBuilder
    built = 0
    for p in [p for p in pk if s2.flyable(p)][:6]:
        job = PackageBuilder(s2.state)._slots(p.objective, False, 0, p.extra)[0].role
        if not any(f.role == job and not f.tag for f in p.flights):
            bad.append(f"{tag}: package #{p.number} {p.objective.type.value} has no {job} flight")
        s2.ai_test = True
        try:
            s2.fly(p.number, s2.flyable(p)[0].id)
            built += 1
        except Exception as e:
            bad.append(f"{tag}: mission #{p.number} {p.objective.type.value} failed: {type(e).__name__}: {e}")
            continue
        if zipfile.ZipFile(s2.settings.sortie_miz).testzip() is not None:
            bad.append(f"{tag}: mission #{p.number} .miz is damaged")
    own = [p for p in pk if s2.flyable(p)]
    if own:
        s2.ai_test = False
        try:
            s2.fly(own[0].number, s2.flyable(own[0])[0].id)
            built += 1
        except Exception as e:
            bad.append(f"{tag}: the player's own mission #{own[0].number} failed: {type(e).__name__}: {e}")
    if not built:
        bad.append(f"{tag}: no mission built")
    lines.append(f"{tag}: {built} missions built")

    # ---- the war runs: the player idle, DAYS days (no exception; where the front, the SA-5s and red's supply stand)
    s2.ai_test = False
    try:
        for _ in range(DAYS):
            if s2.state.status != "ACTIVE":
                break
            s2.skip_day()
        st2 = s2.state
        g2 = st2.ground
        back = [a.id for a in st2.assets.values() if a.variant == "SA-5" and not a.destroyed]
        lines.append(f"{tag}: after {DAYS} idle days: day {st2.day}, status {st2.status}, taken {g2['taken']}, fallen {g2['fallen']}, SA-5 back {back}, red Force Index {ground.supply(st2, 'red'):.2f}")
        if hasattr(s2, "save"):
            s2.save()
    except Exception as e:
        import traceback
        bad.append(f"{tag}: the war sim failed on day {s2.state.day}: {type(e).__name__}: {e} {traceback.format_exc().splitlines()[-3:]}")
    theatres.use("caucasus")
    return {"tag": tag, "bad": bad, "lines": lines}


def main(argv):
    jobs, argv = parallel.pop_jobs(argv)
    seeds = (5, 7)
    if "--seeds" in argv:
        seeds = tuple(int(x) for x in argv[argv.index("--seeds") + 1].split(","))
    import time
    t0 = time.time()
    tasks = [(lv, sd) for lv in (1, 2, 3) for sd in seeds]
    res = parallel.map_cases(one_case, tasks, jobs, TMP)
    bad = 0
    for r in sorted(res, key=lambda r: r["tag"]):
        for ln in r["lines"]:
            print(ln)
        for b in r["bad"]:
            print("BAD", b)
            bad += 1
    print(f"{len(tasks)} cases, {bad} problems ({time.time() - t0:.0f} s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
