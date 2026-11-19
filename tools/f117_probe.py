"""S104 probe: the F-117A (tools only, nothing ships).

    python tools/f117_probe.py [--jobs N] [--days D]

Part 1, the war: Level 3 campaigns (Caucasus, and Syria with the F-117A squadron injected at Incirlik: its pack has none yet) with night ops on, the player idle, D days (default 30). Each night turn
it reports how many EWRs / SAM sites qualify (no red air within `f117.COVER_NM`, in the F-117A's radius, no SAM belt of another cluster in front), at the real constant and at 40 / 30 / 20 nm, the F-117A
packages planned, hit / loss lines, and the squadron's ready jets turn by turn (a few at most: refit 960 min, replacement one per 5,760 min).
Part 2, the package: one night turn of a Caucasus campaign with red air wiped by hand (so targets qualify), the F-117A package built as the all-AI test, and its .miz read: group, aircraft, payload,
every waypoint (name, altitude, speed, tasks) and what the planner passed in. Checks: the flight is F-117A only, no TARCAP / SEAD / escort flight in the package, GBU-27 on both bay stations, a bombing task on
the target, the lock rules A / B of the Mission Editor hold. Exit 0 = clean. One worker process per case (--jobs N); the output is the same either way."""
import math
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_f117_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _inject(theatre: str) -> None:
    """Syria's pack has no F-117A squadron yet: add one at Incirlik (in memory only) so the probe can see what it would do there."""
    from sqe import theatres
    th = theatres.load(theatre)
    if not any(q["aircraft"] == "F-117A" for q in th["squadrons"]):
        th["squadrons"] = list(th["squadrons"]) + [{"id": "fs_8", "name": "8th FS 'Black Sheep'", "aircraft": "F-117A", "base": "incirlik", "count": 12, "callsign": "Pontiac"}]


def war_case(task) -> dict:
    theatre, seed, days = task
    parallel.pin_task(f"f117:{theatre}:{seed}")
    from sqe import clock, f117, theatres
    from sqe.engine import Session
    from sqe.settings import AppSettings
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    _inject(theatre)
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new(f"F{seed}", "F-16C", 3, seed=seed, theatre=theatre)
    st = s.state
    tag = f"{theatre} s{seed}"
    bad, lines = [], []
    night = 0
    ready, planned, hits, lost, flights = [], 0, 0, 0, 0
    cov = {c: 0 for c in (60.0, 40.0, 30.0, 20.0)}
    seen = set()
    orig = f117.COVER_NM
    rwy = 0
    for _ in range(days * 6):
        if st.status != "ACTIVE":
            break
        s.skip_turn()
        ready.append(f117.ready_jets(st))
        if clock.is_night_turn(st.turn):
            night += 1
            for c in cov:
                f117.COVER_NM = c
                cov[c] += len(f117.targets(st))
            f117.COVER_NM = orig
            rwy += len(f117.runway_targets(st))
        for p in s.packages():
            if f117.is_job(p.objective) and p.objective.id + (":RUNWAY" if p.objective.aim == "RUNWAY" else "") not in seen:
                seen.add(p.objective.id + (":RUNWAY" if p.objective.aim == "RUNWAY" else ""))
                planned += 1
                flights += sum(f.count for f in p.flights if f.aircraft == "F-117A")
                if any(f.aircraft != "F-117A" and not f.tag for f in p.flights):
                    bad.append(f"{tag}: package #{p.number} carries a non-F-117A flight: {[(f.role.value, f.aircraft) for f in p.flights]}")
                if p.objective.aim == "F117" or len(seen) <= 6:
                    lines.append(f"{tag}: day {st.day} turn {st.turn}: {p.objective.description}; {[(f.count, f.aircraft) for f in p.flights if not f.tag]}")
    notes = [n for n in st.log if "F-117A" in str(n) or "Night strike" in str(n) or "Night OCA" in str(n)]
    hits = sum(1 for n in notes if ("Night strike" in str(n) or "Night OCA" in str(n)) and "objective achieved" in str(n))
    lost = sum(1 for n in st.log if "lost" in str(n) and "Pontiac" in str(n))
    lines.append(f"{tag}: runway targets (no OTHER red patrol within reach, own patrol ignored) summed over the night turns: {rwy}")
    lines.append(f"{tag}: {night} night turns; qualifying targets summed over them at 60 / 40 / 30 / 20 nm: {cov[60.0]} / {cov[40.0]} / {cov[30.0]} / {cov[20.0]}; {planned} F-117A packages incl. {sum(1 for x in seen if 'RUNWAY' in x)} runway ({flights} jets), {hits} hits, lost ({lost} log lines)")
    lines.append(f"{tag}: ready F-117As turn by turn: max {max(ready) if ready else 0}, min {min(ready) if ready else 0}, at the end {ready[-1] if ready else 0}; squadron {[(q.available, q.authorized, len(q.refit)) for q in f117.squadrons(st)]}")
    theatres.use("caucasus")
    return {"tag": tag, "bad": bad, "lines": lines}


def package_case(task) -> dict:
    seed, = task
    from sqe import clock, f117, theatres
    from sqe.engine import Session
    from sqe.settings import AppSettings
    from dcs import lua
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    pk = None
    for sd in (seed, 7, 11, 3, 13, 17):                      # the first campaign whose night turn offers a reachable target with no intact belt in front
        parallel.pin_task(f"f117pkg:{sd}")
        s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
        s.new(f"P{sd}", "F-16C", 3, seed=sd, theatre="caucasus")
        st = s.state
        for _ in range(40):
            if clock.is_night_turn(st.turn):
                break
            s.skip_turn()
        for w in st.enemy_air:                               # no red air anywhere: every reachable EWR / SAM site qualifies
            w.available = 0
            for q in w.sqns:
                q.available = 0
        st.barcap = None
        s.plan_turn()
        pk = next((p for p in s.packages() if p.objective.aim == "F117"), None)
        if pk is not None:
            break
    tag = f"caucasus s{sd} package"
    bad, lines = [], []
    if pk is None:
        return {"tag": tag, "bad": [f"{tag}: no F-117A package planned on a night turn in any of six campaigns"], "lines": []}
    t = st.assets[pk.objective.target_id]
    lines.append(f"{tag}: day {st.day} turn {st.turn} (night): #{pk.number} {pk.objective.description}; flights {[(f.role.value, f.count, f.aircraft, f.kit or '-', bool(f.tag)) for f in pk.flights]}")
    if [f for f in pk.flights if not f.tag and (f.role.value != "STRIKE" or f.aircraft != "F-117A")]:
        bad.append(f"{tag}: the package carries a flight other than the F-117A strike")
    s.ai_test = True
    old = st.player.aircraft
    fid = None
    for f in pk.flights:
        if f.aircraft == "F-117A" and not f.tag:
            st.player.aircraft = f.aircraft
            opts = pk.player_options(f.aircraft)
            if opts:
                fid = opts[0].id
            break
    try:
        s.fly(pk.number, fid)
    except Exception as e:
        import traceback
        return {"tag": tag, "bad": [f"{tag}: the build failed: {type(e).__name__}: {e} {traceback.format_exc().splitlines()[-3:]}"], "lines": lines}
    finally:
        st.player.aircraft = old
    z = zipfile.ZipFile(s.settings.sortie_miz)
    M = lua.loads(z.read("mission").decode("utf-8"))["mission"]
    dic = lua.loads(z.read("l10n/DEFAULT/dictionary").decode("utf-8")).get("dictionary", {})
    found = 0
    for coal in M["coalition"].values():
        for country in coal["country"].values():
            for g in ((country.get("plane") or {}).get("group") or {}).values():
                u0 = g["units"][1]
                if u0.get("type") != "F-117A":
                    continue
                found += 1
                nm = dic.get(g.get("name", ""), g.get("name", ""))
                pyl = {k: v["CLSID"] for k, v in (u0.get("payload", {}).get("pylons", {}) or {}).items()}
                lines.append(f"{tag}: group {nm}: {len(g['units'])} x F-117A, skill {u0.get('skill')}, payload {pyl}, fuel {u0.get('payload', {}).get('fuel')} kg, start {g.get('start_time', 0)} s, ETA at the target {t.name}")
                if len(pyl) != 2 or any("EF0A9419" not in v for v in pyl.values()):
                    bad.append(f"{tag}: payload is not GBU-27 on both bay stations: {pyl}")
                pts = (g.get("route") or {}).get("points") or {}
                seq = [pts[k] for k in sorted(pts)]
                bombing = 0
                for i, p in enumerate(seq, 1):
                    tasks = []
                    for tk in ((p.get("task") or {}).get("params") or {}).get("tasks", {}).values():
                        tasks.append(tk.get("id") if tk.get("id") != "ControlledTask" else "controlled:" + str(((tk.get("params") or {}).get("task") or {}).get("id")))
                        if "Bombing" in str(tasks[-1]):
                            bombing += 1
                    lines.append(f"{tag}:   wp {i:2d} {dic.get(p.get('name', ''), p.get('name', ''))!s:12.12} {p.get('type')}/{p.get('action')} alt {p.get('alt', 0) * 3.28084:6.0f} ft speed {p.get('speed', 0) * 1.94384:4.0f} kt ETA {int(p.get('ETA', 0)):5d}{' locked' if p.get('ETA_locked') else ''}{' spd-locked' if p.get('speed_locked') else ''} tasks {tasks}")
                if bombing < 1:
                    bad.append(f"{tag}: no bombing task on the route")
                L = [i for i, p in enumerate(seq) if p.get("ETA_locked")]
                for a, b in zip(L, L[1:]):
                    mid = seq[a + 1:b + 1]
                    if mid and all(p.get("speed_locked") for p in mid):
                        bad.append(f"{tag}: lock rule A broken between points {a + 1} and {b + 1}")
                for i in range(L[-1] + 1 if L else 1, len(seq)):
                    if not seq[i].get("ETA_locked") and not seq[i].get("speed_locked"):
                        bad.append(f"{tag}: lock rule B broken at point {i + 1}")
    if not found:
        bad.append(f"{tag}: no F-117A group in the mission")
    theatres.use("caucasus")
    return {"tag": tag, "bad": bad, "lines": lines}


def rules_case(task) -> dict:
    """The F-117A's own rules: refit 960 min (Tu-22M3 / E-3A still 480, a Viper 180), replacement one airframe per 5,760 min with no Force Index scaling (red's Tu-22M3 wing still 2,880), a lost jet comes off the
    squadron through the war sim's roll, the roll is hit-or-miss with the pair rule, and an ordinary STRIKE slot never takes the F-117A."""
    parallel.pin_task("f117:rules")
    from sqe import clock, f117, refit, theatres
    from sqe.engine import Session
    from sqe.settings import AppSettings
    from sqe.war import WarSimulator
    bad, lines = [], []
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    if (refit.refit_minutes("F-117A", False, 1.0), refit.refit_minutes("Tu_22M3", False, 1.0), refit.refit_minutes("E_3A", False, 1.0), refit.refit_minutes("F-16C", False, 1.0)) != (960, 480, 480, 180):
        bad.append("rules: refit minutes are not 960 / 480 / 480 / 180")
    if (refit.slow_repl_min("F-117A"), refit.slow_repl_min("Tu_22M3"), refit.slow_repl_min("E_3A")) != (5760, 2880, 2880):
        bad.append("rules: replacement minutes are not 5760 / 2880 / 2880")
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new("R", "F-16C", 3, seed=5, theatre="caucasus")
    st = s.state
    sq = f117.squadrons(st)[0]
    sq.available, sq.refit, sq.repl_due = 8, [], 0                        # four jets lost
    now = 100000
    refit.replacements(st, now)
    due0 = sq.repl_due
    if due0 != now + 5760:
        bad.append(f"rules: the first replacement is due at +{due0 - now} min, expected +5760")
    refit.replacements(st, due0 - 1)
    if sq.available != 8:
        bad.append("rules: a replacement arrived early")
    refit.replacements(st, due0)
    if sq.available != 9 or sq.repl_due != due0 + 5760:
        bad.append(f"rules: at the due minute the squadron has {sq.available} (expected 9, one airframe, not a pair) and the next is due +{sq.repl_due - due0} min (expected 5760)")
    lines.append(f"rules: refit 960 / 480 / 480 / 180 min, replacements 5760 / 2880 / 2880 min; the squadron went 8 -> {sq.available} at the due minute, the next one is {sq.repl_due - due0} min later")
    # the war sim's roll, forced: a hit, and a loss at the maximum chance
    for k in range(40):
        if clock.is_night_turn(st.turn):
            break
        s.skip_turn()
    for w in st.enemy_air:
        w.available = 0
        for q in w.sqns:
            q.available = 0
    st.barcap = None
    sq.available, sq.refit = 12, []
    s.plan_turn()
    pk = next((p for p in s.packages() if p.objective.aim == "F117"), None)
    if pk is None:
        bad.append("rules: no F-117A package on the night turn to roll")
    else:
        t = st.assets[pk.objective.target_id]
        f117.LOSS_BASE, f117.LOSS_MAX = 1.0, 1.0
        sim = WarSimulator(s.d, __import__("random").Random(1))
        r = sim.resolve_abstract(st, pk, {"success": True})
        f117.LOSS_BASE, f117.LOSS_MAX = 0.01, 0.15
        n_f = sum(f.count for f in pk.flights if f.aircraft == "F-117A" and not f.tag)
        lines.append(f"rules: a forced hit on {t.name}: destroyed {t.destroyed}; every jet lost at the maximum chance: {sum(r['lost_by'].values())} of {n_f}; the squadron holds {sq.available} of 12")
        if not t.destroyed or sum(r["lost_by"].values()) != n_f or sq.available != 12 - n_f:
            bad.append("rules: the forced roll did not destroy the target / lose the jets / take them off the squadron")
    # the night runway strike: every red wing wiped but one (it has jets, its own patrol is ignored): that field is the target, a forced hit cuts its runway
    for w in st.enemy_air:
        w.available = 0
        for q in w.sqns:
            q.available = 0
    from sqe import runways
    keep = next(w for w in st.enemy_air if st.assets[w.base_asset_id].kind.value == "AIRFIELD" and not runways.is_closed(st, w.base_asset_id))
    for q in keep.sqns:
        q.available = q.authorized
    st.barcap = None
    for a_ in st.assets.values():                            # no EWR / SAM job either (two of those would take both package places of the turn ahead of the runway)
        if a_.kind.value in ("SAM", "EWR"):
            a_.health = 0.0
    sq.available, sq.refit = 12, []
    rt = f117.runway_targets(st)
    pkgs = [p for p in (s.plan_turn() or s.packages()) if f117.is_job(p.objective) and p.objective.aim == "RUNWAY"]
    pkgs = [p for p in s.packages() if f117.is_job(p.objective) and p.objective.aim == "RUNWAY"]
    if not rt or not pkgs:
        bad.append(f"rules: no night runway strike planned for the one field with jets ({len(rt)} targets, {len(pkgs)} packages)")
    else:
        r2 = WarSimulator(s.d, __import__("random").Random(2)).resolve_abstract(st, pkgs[0], {"success": True})
        fid = pkgs[0].objective.target_id
        lines.append(f"rules: night runway strike on {st.assets[fid].name}: closed after a forced hit {runways.is_closed(st, fid)}; flights {[(f.role.value, f.count, f.aircraft) for f in pkgs[0].flights if not f.tag]}")
        if not runways.is_closed(st, fid):
            bad.append("rules: the forced runway hit did not close the field")
        runways._craters(st).pop(fid, None)                      # open it again, then build the job as the all-AI test
        s.ai_test = True
        pa = st.player.aircraft
        st.player.aircraft = "F-117A"
        try:
            s.fly(pkgs[0].number, pkgs[0].player_options("F-117A")[0].id)
            import zipfile as _z
            lines.append(f"rules: the night runway strike builds as a mission (.miz {'sound' if _z.ZipFile(s.settings.sortie_miz).testzip() is None else 'DAMAGED'})")
        except Exception as e:
            bad.append(f"rules: the night runway strike failed to build: {type(e).__name__}: {e}")
        finally:
            st.player.aircraft = pa
    # an ordinary strike never takes the F-117A
    from sqe.packages import PackageBuilder
    pb = PackageBuilder(st, s.d)
    from sqe.packages import Slot
    from sqe.models import Role
    if pb._slot_ok("F-117A", Slot(Role.STRIKE, 4)) or not pb._slot_ok("F-117A", Slot(Role.STRIKE, 4, only="F-117A")):
        bad.append("rules: _slot_ok lets the F-117A into an ordinary strike slot, or refuses its own")
    theatres.use("caucasus")
    return {"tag": "rules", "bad": bad, "lines": lines}


def run_case(task):
    if task[0] == "rules":
        return rules_case(task)
    return package_case(task[1:]) if task[0] == "pkg" else war_case(task[1:])


def main(argv):
    jobs, argv = parallel.pop_jobs(argv)
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 30
    import time
    t0 = time.time()
    tasks = [("war", th, sd, days) for th in ("caucasus", "syria") for sd in (3, 7)] + [("pkg", 5), ("rules",)]
    res = parallel.map_cases(run_case, tasks, jobs, TMP)
    bad = 0
    for r in res:
        for ln in r["lines"]:
            print(ln)
        for b in r["bad"]:
            print("BAD", b)
            bad += 1
    print(f"{len(tasks)} cases, {days} days, {bad} problems ({time.time() - t0:.0f} s, {parallel.map_cases.workers} workers)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
