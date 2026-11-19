"""S90 J8 probe: the Syria setpieces, the Tu-22M3 carrier raid and land strike from Damascus (tools only, nothing ships).

    python tools/syria_raid_probe.py [--jobs N] [--days D] [--theatre syria|caucasus]
    python tools/syria_raid_probe.py --make-test FILE.sqe     (a Syria L3 campaign sitting at a staged carrier raid, for XO to fly)

Level 3 campaigns (seeds 3, 7, 11), the player idle, D days (default 30): every turn the plan is read. For every carrier raid (a FLEET_DEFENSE package of the bomber wing) and every Tu-22M3 land strike it reports the
day and turn, the bomber field, the bearing, the jets, and the geometry: the field to the carrier or to the target in nm against the table reach (`ENEMY_RADIUS_NM` x 0.85), the raid's spawn point at the edge of the map
(distance from the carrier, land or sea) and how many live red SAM sites threaten its inbound line. The first carrier raid and the first land strike of each campaign are saved, reopened in a new session and BUILT as the
all-AI test: the build must work, and the setpiece text must name the bomber field. A geometry table at the top lists the bearings of the pack's range. Exit 0 = nothing out of reach, nothing failed to build.
One worker process per campaign; the output is the same either way."""
import math
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_raid_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NM = 1852.0


def one_case(task) -> dict:
    theatre, seed, days = task
    parallel.pin_task(f"raid:{theatre}:{seed}")
    from sqe import theatres, bombers, fleet, threatmap as tm, seacheck
    from sqe.engine import Session
    from sqe.loadouts import ENEMY_RADIUS_NM
    from sqe.packages import carrier_raid
    from sqe.routes import offset, dist
    from sqe.settings import AppSettings
    from sqe.mission_builder import MissionBuilder
    bad, lines, saved = [], [], {}
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s = mk()
    s.new(f"Rd{seed}", "F-16C", 3, seed=seed, theatre=theatre)
    st = s.state
    tag = f"{theatre} s{seed}"
    reach = ENEMY_RADIUS_NM["Tu_22M3"] * 0.85
    seen = set()
    n_car = n_land = 0
    for _ in range(days * 6):
        if st.status != "ACTIVE":
            break
        s.skip_turn()
        for p in s.packages():
            ex = p.extra or {}
            if not ex.get("bomber_wing") or p.objective.id in seen:
                continue
            land = bool(ex.get("land"))
            if land and not ex.get("tu_strike"):
                continue                                             # an ordinary red raid (Su-17 / Su-24M), not the bomber wing's
            if not land and not carrier_raid(st, p.objective):
                continue
            seen.add(p.objective.id)
            bw = st.assets[ex["bomber_wing"]]
            if land:
                n_land += 1
                dest = ex.get("dest") or (bw.x, bw.y)
                d_nm = dist(bw.x, bw.y, dest[0], dest[1]) / NM
                what = f"land strike on {p.objective.target_id} {p.objective.description[:48]!r}"
                geo = f"{d_nm:.0f} nm from {bw.name} (reach {reach:.0f})"
                if d_nm > reach:
                    bad.append(f"{tag}: day {st.day} land strike {d_nm:.0f} nm from {bw.name}, past the reach {reach:.0f}")
                key = "land"
            else:
                n_car += 1
                cv = fleet.carrier(st)
                d_nm = dist(bw.x, bw.y, cv.x, cv.y) / NM
                brg = float(ex["brg"])
                inb = tm.raid_inbound_sites(st, (cv.x, cv.y), brg, ex["bomber_wing"])
                top, bottom = (theatres.hook("map_box") or {}).get("x1"), (theatres.hook("map_box") or {}).get("x0")
                mbx = MissionBuilder.__new__(MissionBuilder)
                mbx.t = theatres.terrain()
                edge = mbx._raid_edge(cv.x, cv.y, brg)
                e_nm = dist(edge[0], edge[1], cv.x, cv.y) / NM
                what = f"carrier raid {ex.get('bombers')} + {ex.get('escorts')} ({ex.get('mode')})"
                geo = (f"{d_nm:.0f} nm {bw.name} to the carrier (reach {reach:.0f}), bearing {brg:.0f}, spawn {e_nm:.0f} nm out ({'land' if seacheck.is_land(*edge) else 'sea'}), "
                       f"{len(inb)} live SAM sites threaten the inbound line {sorted({a.variant for a, _ in inb})}")
                if d_nm > reach:
                    bad.append(f"{tag}: day {st.day} carrier {d_nm:.0f} nm from {bw.name}, past the reach")
                key = "carrier"
            lines.append(f"{tag}: day {st.day} turn {st.turn}: {what}; {geo}")
            if key not in saved:
                path = str(TMP / "saves" / f"raid_{theatre}_{seed}_{key}.sqe")
                s.save(path)
                import shutil
                shutil.copy(path, path + ".snap")                    # the session keeps autosaving to `path` as the war goes on: keep this turn's file apart
                saved[key] = (path + ".snap", p.objective.id, p.number)
    lines.append(f"{tag}: {n_car} carrier raids and {n_land} land strikes planned in {st.day} days, status {st.status}")
    # build the first of each in a reopened session
    for key, (path, oid, num) in sorted(saved.items()):
        r = mk()
        r.open(path)
        pk = next((p for p in r.packages() if p.number == num), None)
        if pk is None:
            bad.append(f"{tag}: the saved {key} package #{num} ({oid}) is not in the reopened plan")
            continue
        from sqe import narrative
        if key == "carrier":
            txt = narrative.setpiece_text(r.state, pk, False, "F-16C")[0]
            bwn = r.state.assets[pk.extra["bomber_wing"]].name
            lines.append(f"{tag}: setpiece text: {txt[:96]}")
            if f"out of {bwn}" not in txt:
                bad.append(f"{tag}: the setpiece text does not name {bwn}: {txt[:80]!r}")
        r.ai_test = True
        old = r.state.player.aircraft
        fid = None
        for f in pk.flights:
            if not f.tag and f.role.value != "SEAD":
                r.state.player.aircraft = f.aircraft
                opts = pk.player_options(f.aircraft)
                if opts:
                    fid = opts[0].id
                    break
        try:
            r.fly(pk.number, fid)
            z = zipfile.ZipFile(r.settings.sortie_miz)
            ok = z.testzip() is None
            lines.append(f"{tag}: the {key} raid builds ({len(pk.flights)} flights), .miz {'sound' if ok else 'DAMAGED'}")
            if not ok:
                bad.append(f"{tag}: the {key} raid .miz is damaged")
        except Exception as e:
            import traceback
            bad.append(f"{tag}: the {key} raid failed to build: {type(e).__name__}: {e} {traceback.format_exc().splitlines()[-3:]}")
        finally:
            r.state.player.aircraft = old
    theatres.use("caucasus")
    return {"tag": tag, "bad": bad, "lines": lines}


def geometry(theatre) -> list:
    """The bearings of the pack's range: spawn point, land or sea there, inbound SAM sites, on a fresh level 3 campaign (day 1)."""
    from sqe import theatres, bombers, fleet, threatmap as tm, seacheck
    from sqe.engine import Session
    from sqe.routes import offset, dist
    from sqe.settings import AppSettings
    from sqe.mission_builder import MissionBuilder
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new("Geo", "F-16C", 3, seed=5, theatre=theatre)
    st = s.state
    cv = fleet.carrier(st)
    bw = next(w for w in st.enemy_air if "Tu_22M3" in w.types)
    mbx = MissionBuilder.__new__(MissionBuilder)
    mbx.t = theatres.terrain()
    lo, hi = bombers.raid_bearing_range()
    out = [f"geometry ({theatre}, L3 day 1): carrier at {cv.x:.0f}, {cv.y:.0f}; bomber base {st.assets[bw.base_asset_id].name} {dist(cv.x, cv.y, st.assets[bw.base_asset_id].x, st.assets[bw.base_asset_id].y) / NM:.0f} nm away; bearing range {lo:.0f} to {hi:.0f}"]
    for brg in sorted({lo, (lo + hi) / 2, hi}):
        edge = mbx._raid_edge(cv.x, cv.y, brg)
        inb = tm.raid_inbound_sites(st, (cv.x, cv.y), brg, bw.base_asset_id)
        land_pts = sum(1 for k in range(1, 22) if seacheck.is_land(*offset(cv.x, cv.y, brg, k * 10 * NM)))
        out.append(f"  bearing {brg:.0f}: spawn {dist(edge[0], edge[1], cv.x, cv.y) / NM:.0f} nm out ({'land' if seacheck.is_land(*edge) else 'sea'}), {land_pts} of 21 sample points on land, {len(inb)} live SAM sites on the inbound line")
    theatres.use("caucasus")
    return out


def make_test(path: str) -> None:
    """A Syria level 3 campaign (F-14B, seed 5) walked to the first turn of a carrier raid that was STAGED by hand on day 2 (the idle war rarely raids the carrier before day 20), saved to `path`: open it in SQE and fly the raid intercept."""
    from sqe import bombers
    from sqe.engine import Session
    from sqe.packages import carrier_raid
    from sqe.settings import AppSettings
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    parallel.pin_task("raid:maketest")
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s.new("Syria L3 raid test", "F-14B", 3, seed=5, theatre="syria")
    st = s.state
    forced = False
    for _ in range(400):
        if st.day == 1 and st.turn >= 2 and not forced:
            bombers.decide(st, s.d)
            st.raids["bomber_stage"] = {"launch": 2, "mode": "safe", "n": bombers.max_raid(s.d), **bombers.stage_extras(st, 2)}
            forced = True
        s.skip_turn()
        raid = [p for p in s.packages() if carrier_raid(st, p.objective)]
        if raid:
            p = raid[0]
            ex = p.extra
            s.save(path)
            print(f"saved {path}: day {st.day} turn {st.turn}, package #{p.number}: {ex.get('bombers')} Tu-22M3 + {ex.get('escorts')} escorts ({ex.get('mode')}), bearing {ex.get('brg')}; flights: "
                  + ", ".join(f"{f.role.value} {f.count}x{f.aircraft}" for f in p.flights))
            return
    print("no carrier raid package came up in 400 turns")


def main(argv):
    jobs, argv = parallel.pop_jobs(argv)
    if "--make-test" in argv:
        make_test(argv[argv.index("--make-test") + 1])
        return 0
    days = int(argv[argv.index("--days") + 1]) if "--days" in argv else 30
    theatre = argv[argv.index("--theatre") + 1] if "--theatre" in argv else "syria"
    import time
    t0 = time.time()
    for ln in geometry(theatre):
        print(ln)
    res = parallel.map_cases(one_case, [(theatre, sd, days) for sd in (3, 7, 11)], jobs, TMP)
    bad = 0
    for r in res:
        for ln in r["lines"]:
            print(ln)
        for b in r["bad"]:
            print("BAD", b)
            bad += 1
    print(f"{len(res)} campaigns, {days} days, {bad} problems ({time.time() - t0:.0f} s, {parallel.map_cases.workers} workers)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
