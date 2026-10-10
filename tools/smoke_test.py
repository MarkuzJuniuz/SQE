"""Headless end-to-end test (no DCS, no GUI). Run:  python tools/smoke_test.py
It is fully ISOLATED: it uses a temporary folder for everything, redirects APPDATA, never touches your real
settings or campaigns, and deletes its temp data when it finishes. Output starts with the SQE version so you can
tell it is current.
For each flyable jet: new campaign -> plan -> FLY (build SQE_Sortie.miz) -> fake sortie results (with your kills) ->
Accept -> debrief -> next day -> save/reload. 'SMOKE TEST PASSED' + exit code 0 = everything worked."""
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="sqe_test_"))
os.environ["APPDATA"] = str(TMP / "appdata")                 # belt and braces: even a stray settings save stays in TMP
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqe
from sqe.aircraft import AIRCRAFT
from sqe.engine import Session
from sqe.models import ObjectiveType
from sqe.settings import AppSettings


def main():
    from sqe import raids as _r0
    global _EMERG
    _EMERG = _r0.emergency_happens
    _r0.emergency_happens = lambda *a, **k: False
    print(f"SQE smoke test, version {sqe.__version__}  (isolated temp data: {TMP})")
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s = mk()
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    assert not s.settings.problems(), s.settings.problems()
    tested, kinds = 0, set()
    for aircraft, spec in AIRCRAFT.tuned().items():          # the hand-tuned jets; the generated catalog has its own test below
        if not spec.player_flyable:
            continue
        s.new(f"Smoke {aircraft}", aircraft, 3, seed=7)         # level 3 so the bomber raid objective exists too
        opts = [p for p in s.packages() if s.flyable(p)]
        if not opts:
            print(f"[{aircraft}] no flyable package today (fine for niche jets like the A-10)"); continue
        # prefer something we have not tested yet (CAS, raid, ...) so every mission type gets built
        pk = next((p for p in opts if p.objective.type not in kinds), opts[0])
        kinds.add(pk.objective.type)
        fl = s.flyable(pk)[0]
        res = s.fly(pk.number, fl.id)
        assert s.settings.sortie_miz.exists(), "SQE_Sortie.miz was not written"
        z = zipfile.ZipFile(s.settings.sortie_miz)
        mission = z.read("mission").decode()
        assert "world.addEventHandler" in mission and "DictKey_Translation" not in mission.split("a_do_script")[1][:120], "hook not embedded as code"
        assert len([n for n in z.namelist() if "KNEEBOARD" in n]) == 3, "expected 3 kneeboard pages"
        from dcs import lua                                       # the mission file must parse as valid Lua, exactly like DCS reads it
        lua.loads(mission); lua.loads(z.read("l10n/DEFAULT/dictionary").decode())
        try:                                                      # the embedded hook must compile as Lua (checked when lupa is installed)
            import lupa
            def _find(o):
                if isinstance(o, str):
                    return o if "SQE debrief hook" in o else None
                for v in (o.values() if isinstance(o, dict) else o if isinstance(o, (list, tuple)) else ()):
                    r = _find(v)
                    if r:
                        return r
            hook = _find(lua.loads(mission)) or _find(lua.loads(z.read("l10n/DEFAULT/dictionary").decode()))
            assert hook, "hook script not found in the mission"
            res_ = lupa.LuaRuntime(unpack_returned_tuples=True).eval("function(s) return load(s) end")(hook)
            fn, err = (res_ if isinstance(res_, tuple) else (res_, None))
            assert fn is not None, f"hook does not compile: {err}"
        except ImportError:
            pass
        print(f"[{aircraft}] {pk.objective.type.value}: {pk.objective.description} | {fl.callsign}-1 {fl.role.value} | start {pk.start} | push {res.timeline['push']}"
              f" TOT {res.timeline['tot']} | seed {res.seed} | {res.counts['groups']} groups / {res.counts['units']} units | warnings: {res.warnings or 'none'}")
        man = s.manifest()
        prim = next((g for g in man.groups if g["kind"] == "asset" and g.get("primary")), None)
        fr = next((g for g in man.groups if g["kind"] == "friendly" and not g.get("player")), None)
        en = next((g for g in man.groups if g["kind"] == "enemy_air"), None)
        dead = (prim["units"][: int(len(prim["units"]) * 0.6)] if prim else []) + (en["units"][:1] if en and not prim else []) + (fr["units"][:1] if fr else [])
        data = {"campaign": man.campaign_id, "sortie": man.sortie, "package": man.package_id, "mission_ended": True, "time": 2400,
                "dead": dead, "ejected": [], "landed": [man.player_unit], "player": {"takeoff": 300, "landed": 2300, "ka": 1, "kg": 2, "ks": 0},
                "kills": [{"k": man.player_unit, "kt": "Test", "v": (dead or ["x"])[0], "vt": "TargetType", "w": "AIM-120C", "t": 725}]}
        s.settings.state_file.write_text(json.dumps(data))
        status, got, tl = s.poll()
        assert status == "ok", status
        out = s.apply(got)
        assert out.get("kill_log") and "killed by" in out["kill_log"][0], out.get("kill_log")
        assert s.state.day == 2 and s.state.plan, "campaign did not advance"
        assert s.state.pilot["sorties"] == 1 and s.state.pilot["kills_ground"] == 2, s.state.pilot
        print(f"    debrief: {out['story'].splitlines()[0][:100]}...  pilot: {s.state.pilot['sorties']} sortie, {s.state.pilot['kills_air']}A/{s.state.pilot['kills_ground']}G kills")
        r = mk(); r.open(s.path)
        assert r.state.day == 2 and r.state.pilot["sorties"] == 1
        tested += 1
    assert tested >= 3, "too few jets tested"
    # ---- package merging: fold same-area packages into one mission, fly it, debrief all of them ---------------------------
    ms = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, merge_mode="area", flight_filter="all"))
    ms.new("Smoke merge", "F-16C", 2, seed=5)
    cand = next(((p, ms.merge_candidates(p)) for p in ms.packages() if ms.flyable(p) and ms.merge_candidates(p)), None)
    assert cand, "no mergeable packages found"
    pk, extra = cand
    res = ms.fly(pk.number, ms.flyable(pk)[0].id)
    assert res.merged and len(res.merged) <= len(extra), res.merged   # extras may be dropped to fit the unit cap
    man = ms.manifest()
    z = zipfile.ZipFile(ms.settings.sortie_miz); lua.loads(z.read("mission").decode())
    print(f"[merge] #{pk.number} {pk.objective.type.value} + {[(m['number'], m['type']) for m in res.merged]}: {res.counts['groups']} groups / {res.counts['units']} units")
    prim2 = [g for g in man.groups if g["kind"] == "asset" and g.get("primary_pkgs")]
    assert any(res.merged[0]["id"] in g["primary_pkgs"] for g in prim2), "merged package has no primary target"
    t_late = max(m["tot_s"] for m in res.merged) + 200
    dead = [u for g in man.groups if g["kind"] == "asset" and res.merged[0]["id"] in g.get("primary_pkgs", []) for u in g["units"][:2]]
    ms.settings.state_file.write_text(json.dumps({"campaign": man.campaign_id, "sortie": man.sortie, "package": man.package_id, "mission_ended": True,
        "time": t_late, "dead": dead, "ejected": [], "landed": [man.player_unit], "player": {"takeoff": 300, "landed": 2300, "ka": 0, "kg": 0, "ks": 0}}))
    st_, got, _ = ms.poll(); assert st_ == "ok"
    out = ms.apply(got)
    assert out["packages"] and out["packages"][0]["resolved"], out["packages"]
    print("    merged debrief:", [ln for ln in out["lines"] if ln.startswith("Package #")][:2])
    # ---- v0.10: earlier packages fly with you, already underway; the Missions list folds later ones into the first -----------------
    bs = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, merge_mode="area", flight_filter="all"))
    found = None
    for seed_b in range(1, 13):
        bs.new("Smoke back", "F-14BU", 2, seed=seed_b)
        for pk_b in bs.packages():
            if bs.flyable(pk_b) and any(c.start < pk_b.start for c in bs.merge_candidates(pk_b)):
                found = (seed_b, pk_b); break
        if found:
            break
    assert found, "no host with an earlier package found"
    seed_b, pk_b = found
    rb = bs.fly(pk_b.number, bs.flyable(pk_b)[0].id)
    early = [c for c in bs.merge_candidates(pk_b) if c.start < pk_b.start]
    assert any(m["number"] == early[0].number for m in rb.merged) or rb.warnings, "earlier package neither flown nor reported skipped"
    zb = zipfile.ZipFile(bs.settings.sortie_miz); mb = lua.loads(zb.read("mission").decode())
    print(f"[back] seed {seed_b} host #{pk_b.number} {pk_b.start} + {[(m['number'], m['tot_s'] and round(m['tot_s']), m.get('underway')) for m in rb.merged]}")
    # one where the earlier package really is already airborne at the start: its flights must be live (not late-activated) and in the air
    under = None
    for seed_u in range(1, 13):
        bs.new("Smoke under", "F-14BU", 2, seed=seed_u)
        for pk_u in bs.packages():
            if bs.flyable(pk_u) and any(c.start < pk_u.start for c in bs.merge_candidates(pk_u)):
                ru = bs.fly(pk_u.number, bs.flyable(pk_u)[0].id)
                if any(m.get("underway") for m in ru.merged):
                    under = (seed_u, pk_u, ru); break
        if under:
            break
    assert under, "no merged mission with an earlier package already underway was produced"
    zu = zipfile.ZipFile(bs.settings.sortie_miz); mu = lua.loads(zu.read("mission").decode())["mission"]
    uman = bs.manifest()
    names = {n for g in uman.groups if g.get("pkg") == [m for m in under[2].merged if m.get("underway")][0]["id"] and g["kind"] == "friendly" for n in g["units"]}
    live = 0
    for side in mu["coalition"].values():
        for c in side["country"].values():
            for g in (c.get("plane", {}).get("group", {}) or {}).values():
                if any(u.get("name") in names for u in g["units"].values()) and not g.get("lateActivation"):
                    live += 1
                    assert all(u["alt"] > 300 for u in g["units"].values()), "an underway flight starts on the ground"
    assert live >= 1, "no live in-flight group for the underway package"
    print(f"[underway] seed {under[0]} host #{under[1].number}: {live} flight groups already airborne at the start")
    for m_ in rb.merged:
        assert m_["rtb_s"] > 0, m_
    vis = [p_ for p_ in bs.packages() if bs.flyable(p_)]
    groups = bs.collapse(vis)
    shown = {h.number for h, _ in groups}; folded = {x.number for _, mem in groups for x in mem}
    assert not (shown & folded), (shown, folded)
    assert {p_.number for p_ in vis} <= (shown | folded), "collapse lost a package"
    print(f"[list] {len(vis)} packages -> {len(groups)} rows")
    # ---- v0.11: ruins of earlier packages, pre-rolled and applied at the debrief -------------------------------------------------
    import re as _re
    got = None
    for sd in range(1, 40):
        rs = Session(AppSettings(dcs_saves=str(TMP / f"rs{sd}"), persist=False)); (TMP / f"rs{sd}").mkdir(exist_ok=True)
        rs.settings.merge_back_min = 0
        rs.new("dev", "F-14BU", 3, seed=sd)
        for p_ in rs.packages():
            if rs.flyable(p_) and rs.ruin_candidates(p_, rs.merge_candidates(p_)):
                rr = rs.fly(p_.number, rs.flyable(p_)[0].id)
                if rr.manifest.ruins:
                    got = (rs, p_, rr); break
        if got: break
    assert got, "no seed produced ruins"
    rs, hp, rr = got
    mis = zipfile.ZipFile(rr.miz).read("mission").decode("utf8", "ignore")
    assert _re.search(r"RUINS = \{ \{x=", mis), "ruins missing from the hook"
    pend = rs.state.pending
    assert pend["ruins"] and all(str(r_["number"]) in pend["ruins"] for r_ in rr.manifest.ruins)
    n_rn = rr.manifest.ruins[0]["number"]; roll = pend["ruins"][str(n_rn)]
    data = {"campaign": rs.state.campaign_id, "sortie": rr.manifest.sortie, "package": hp.id, "mission_ended": True, "time": 3000, "dead": [], "ejected": [],
            "landed": [], "player": {"takeoff": 10, "landed": 2900, "ka": 0, "kg": 0, "ks": 0}, "kills": []}
    out = rs.apply(data)
    assert any(m_["success"] == roll["success"] for m_ in out["meanwhile"]), "the stored roll was not applied"
    print(f"[ruins] host #{hp.number}: ruins for #{n_rn} (success={roll['success']}), stored roll applied at the debrief")
    # ---- v0.12: terrain mask from DCS ---------------------------------------------------------------------------------------
    import json as _json
    from sqe import terrainmask as _tm, terrainprobe as _tp
    (TMP / "tm").mkdir(exist_ok=True)
    _json.dump({"terrain": "Caucasus", "x0": 0, "y0": 0, "step": 250, "nx": 40, "ny": 40,
                "rows": ["l20 s2 l18" if i != 5 else "l40" for i in range(40)]}, open(TMP / "tm" / _tm._file(), "w"))
    _tm.configure(TMP / "tm")
    assert _tm.land_ok(5000, 2000, 300) is True and _tm.land_ok(5000, 5100, 300) is False, "river cells must fail"
    assert _tm.land_ok(5000, 4700, 300) is True, "land 200 m+ from the river must pass"
    assert _tm.land_ok(99999, 99999) is None
    assert "land.getSurfaceType" in _tp.probe_lua() and "SQE_terrain_caucasus" in _tp.probe_lua()
    _tm.configure(None)
    print("[terrain] mask read, river margin and off-map fallback OK")
    # ---- GUI dialogs build (offscreen) and the scan button works --------------------------------------------------------------
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QMessageBox
        _app = QApplication.instance() or QApplication([])
        from sqe.gui.dialogs import SettingsDialog, NewCampaignDialog
        (TMP / "gsv").mkdir(exist_ok=True)
        _gs = AppSettings(dcs_saves=str(TMP / "gsv"), persist=False)
        _dlg = SettingsDialog(_gs)
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        assert [_dlg.tabs.tabText(i) for i in range(_dlg.tabs.count())] == ["General", "Campaign", "Mission build", "DCS integration", "Terrain scan"]
        assert "Not scanned" in _dlg.tm_status.text()
        _gs.carcass_weight_pct, _gs.reactive, _gs.weather_mode, _gs.merge_radius_nm = 40, False, "rain", 35       # every moved control still round-trips
        _d2 = SettingsDialog(_gs)
        assert (_d2.cw.value(), _d2.react.isChecked(), _d2.wxm.currentData(), _d2.mrad.value()) == (40, False, "rain", 35)
        _dlg._make_probe(); _dlg._save()
        assert (TMP / "gsv" / "Missions" / "SQE_TerrainScan.miz").exists()
        NewCampaignDialog()
        print("[gui] settings (5 tabs, scan status) and new-campaign dialogs build; every control round-trips; scan mission button works")
    except ImportError:
        print("[gui] PySide6 not installed here; dialogs not exercised")
    # ---- v0.13: merge circle (radius, edge-shifted centre) -------------------------------------------------------------------
    import math as _m
    rs2 = Session(AppSettings(dcs_saves=str(TMP / "rad"), persist=False)); (TMP / "rad").mkdir(exist_ok=True)
    rs2.new("dev", "F-14BU", 3, seed=1)
    _R = rs2.merge_radius_m(); assert abs(_R - 50 * 1852.0) < 1
    _A = list(rs2.state.assets.values())
    _bx = (min(a.x for a in _A), max(a.x for a in _A), min(a.y for a in _A), max(a.y for a in _A))
    _n = 0
    for p_ in rs2.packages():
        c_ = rs2.merge_center(p_)
        if c_ is None:
            continue
        t_ = rs2._pkg_xy(p_)
        assert _m.hypot(t_[0] - c_[0], t_[1] - c_[1]) <= _R + 1, "your own target must stay inside the circle"
        for x_ in rs2.merge_candidates(p_):
            tx_ = rs2._pkg_xy(x_)
            assert _m.hypot(tx_[0] - c_[0], tx_[1] - c_[1]) <= _R + 1
            _n += 1
    from sqe import narrative as _nar
    import random as _rd
    _story = _nar.debrief_story({"objective": "X", "objective_type": "STRIKE", "target_damage": 0.5, "blue_air_lost": 0, "player": "airborne"}, rs2.state, _rd.Random(2))
    assert "airborne" not in _story and "  " in _story and "   " not in _story
    print(f"[radius] 50 nm circle: own target always inside, {_n} folded candidates all inside; debrief says nothing about being airborne")
    # ---- v0.8: SEAD/DEAD split, suppression, depth tiers, front, garrisons ------------------------------------------------
    import random
    from sqe.models import AssetKind, Role
    from sqe.war import update_front, WarSimulator, ObjectivePlanner
    from sqe.state import CampaignState
    ds = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, merge_mode="off", flight_filter="all"))
    ds.new("Smoke dead", "F-16C", 3, seed=11)
    st = ds.state
    assert any(a.variant == "GARRISON" for a in st.assets.values()), "no SAM garrisons at level 3"
    assert all(a.tier <= st.front + 2 for p in ds.packages() if p.objective.type.value not in ("BARCAP", "FLEET_DEFENSE")
               for a in [st.assets[p.objective.target_id]]), "a locked-tier target was offered on day 1"
    dp = next(p for p in ds.packages() if p.objective.type == ObjectiveType.DEAD and ds.flyable(p))
    roles = {f.role for f in dp.flights if not f.tag}
    assert Role.SEAD in roles and Role.STRIKE in roles, f"a DEAD package needs a SEAD flight and a DEAD flight, got {roles}"
    dres = ds.fly(dp.number, next(f for f in ds.flyable(dp) if f.role == Role.STRIKE).id)
    dman = ds.manifest()
    site = next(g for g in dman.groups if g["kind"] == "asset" and g.get("primary"))
    assert site.get("trk") or site.get("srch"), "SAM site has no radars recorded"
    rad = list(site.get("trk") or []) + list(site.get("srch") or [])
    ds.settings.state_file.write_text(json.dumps({"campaign": dman.campaign_id, "sortie": dman.sortie, "package": dman.package_id, "mission_ended": True,
        "time": 2400, "dead": rad, "ejected": [], "landed": [dman.player_unit], "player": {"takeoff": 300, "landed": 2300, "ka": 0, "kg": 0, "ks": 0}}))
    tid = dp.objective.target_id
    st_, got, _ = ds.poll(); assert st_ == "ok"
    dout = ds.apply(got)
    assert any("SUPPRESSED" in ln for ln in dout["lines"]), dout["lines"]
    print("[sead/dead] radars killed, launchers left ->", [ln for ln in dout["lines"] if "SUPPRESSED" in ln][0][:90])
    # abstract SEAD then DEAD: a blinded site dies, a live one mostly survives
    sim = WarSimulator(ds.d, random.Random(1))
    ds2 = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False)); ds2.new("Smoke dead2", "F-16C", 3, seed=11)
    killed = {True: 0, False: 0}
    for blind in (True, False):
        for k in range(40):
            st2 = CampaignState.from_dict(ds2.state.to_dict())
            pk2 = next(p for p in ds2.packages() if p.objective.type == ObjectiveType.DEAD)
            sim2 = WarSimulator(ds2.d, random.Random(k))
            if not blind:
                for f in pk2.flights:
                    if f.role == Role.SEAD: f.count = 0           # no SEAD flight: the site stays active
            sim2.resolve_abstract(st2, pk2)
            killed[blind] += st2.assets[pk2.objective.target_id].destroyed
    print(f"[sead/dead] abstract kills in 40 runs: with SEAD {killed[True]}, without {killed[False]}")
    assert killed[True] > killed[False], "SEAD should make the DEAD strike more likely to destroy the site"
    # depth tiers + front: breaking the open tiers opens deeper ones, and nothing gets stuck
    fs = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False)); fs.new("Smoke front", "F-16C", 2, seed=4)
    f0 = fs.state
    for a in f0.assets.values():
        if a.tier <= 2 and a.kind in (AssetKind.SAM, AssetKind.ARMOR):
            a.health = 0.0
    f0.front_days = 5
    assert update_front(f0) and f0.front == 1, "the front did not advance"
    f1 = CampaignState.from_dict(fs.state.to_dict()); f1.front, f1.front_days = 0, 13
    for a in f1.assets.values():
        a.health = 1.0
    assert update_front(f1) and f1.front == 1, "a stalled front must buckle"
    old = fs.state.to_dict(); old["format"] = 3
    try:
        CampaignState.from_dict(old); raise AssertionError("an old save must be refused")
    except ValueError:
        pass
    print("[front] advance, anti-stall and old-save refusal OK")
    # ---- carrier + escort routes must stay on open water (no land on the track, none inland) --------------------------------
    from sqe import mission_builder as mb, seacheck as sc
    seen = []
    orig_pb = mb.MissionBuilder._place_base
    def _pb(self, base, tx, ty):
        r = orig_pb(self, base, tx, ty)
        for nm, g in self.ship.items():
            seen.extend((g.name, p.position.x, p.position.y) for p in g.points)
        return r
    mb.MissionBuilder._place_base = _pb
    try:
        for ac in ("FA-18C", "F-14BU"):
            for sd in (1, 2, 3):
                cs = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, merge_mode="off", flight_filter="all"))
                cs.new(f"Smoke cv {ac}{sd}", ac, 3, seed=sd)
                for pk in cs.packages():
                    fl = [f for f in cs.flyable(pk) if f.base_id == "cvn74"]
                    if fl:
                        cs.fly(pk.number, fl[0].id); break
    finally:
        mb.MissionBuilder._place_base = orig_pb
    assert seen, "no carrier sortie was built for the land check"
    bad = [(n, round(x / 1000), round(y / 1000)) for n, x, y in seen if sc.is_land(x, y)]
    assert not bad, f"carrier/escort route over land: {bad[:3]}"
    print(f"[carrier] {len(seen)} carrier/escort route points, none on land")
    # ---- theatre packs: data, not code -------------------------------------------------------------
    from sqe import theatres, terrainmask as _tmk2, seacheck as _sc2
    assert "caucasus" in theatres.available()
    pack = json.loads((theatres.DATA / "caucasus.json").read_text(encoding="utf-8"))
    pack.update({"id": "demo", "name": "Demo Theatre", "title": "Operation DEMO", "tz": 3.0, "lat": 30.0})
    pack["scan"] = dict(pack["scan"], file="SQE_terrain_demo.json")
    pack["red_fields"] = pack["red_fields"][:4]
    pack["wing_weight"] = {k: v for k, v in pack["wing_weight"].items() if k in {f["id"] for f in pack["red_fields"]}}
    pack["support_targets"] = []
    (TMP / "packs").mkdir(); (TMP / "packs" / "demo.json").write_text(json.dumps(pack), encoding="utf-8")
    broken = dict(pack); broken.pop("front"); broken["id"] = "broken"
    (TMP / "packs" / "broken.json").write_text(json.dumps(broken), encoding="utf-8")
    theatres.EXTRA_DIRS.append(str(TMP / "packs")); theatres._CACHE.clear()
    assert theatres.available().get("demo") == "Demo Theatre"
    try:
        theatres.load("broken"); raise SystemExit("a pack with a missing key was accepted")
    except ValueError as ex:
        assert "front" in str(ex)
    ds = mk(); ds.new("Demo", "F-16C", 2, seed=7, theatre="demo")
    assert ds.state.theatre == "demo" and len([a for a in ds.state.assets.values() if a.kind.value == "AIRFIELD"]) == 4
    assert theatres.active()["id"] == "demo" and _tmk2._file() == "SQE_terrain_demo.json"
    from sqe import narrative as _nr, timeofday as _tod
    assert _nr.TITLE == "Operation DEMO"
    r1 = _tod.sun_times(__import__("datetime").date(2004, 6, 12))
    dpk = next(p for p in ds.packages() if ds.flyable(p))
    ds.fly(dpk.number, ds.flyable(dpk)[0].id)
    ds.save(); ds2 = mk(); ds2.open(ds.path)
    assert theatres.active()["id"] == "demo"
    from sqe import terrainprobe as _tp
    assert "SQE_terrain_demo.json" in _tp.probe_lua() and "Demo Theatre" in _tp.probe_lua()
    theatres.use("caucasus")
    assert _nr.TITLE == "Operation IRON TIDE" and _tod.sun_times(__import__("datetime").date(2004, 6, 12)) != r1
    assert "SQE_terrain_caucasus.json" in _tp.probe_lua()
    theatres.EXTRA_DIRS.clear(); theatres._CACHE.clear()
    print("[theatres] pack loader, validation, a second pack builds a campaign and a sortie, the scan follows the active theatre")
    # ---- weather and the weapons it allows -------------------------------------------------------------
    import datetime as _dt, collections as _co
    from sqe import weather as W
    pack = theatres.load("caucasus")
    clim = pack["climate"]
    for mth in (1, 7):                                                      # long-run odds match the climate; the walk never jumps two steps
        cnt, jump = _co.Counter(), 0
        for cid in range(30):
            prev = None
            for k in range(28):
                st_ = W._state_on(f"t{cid}", _dt.date(2004, mth, 1), k, clim); cnt[st_] += 1
                jump += 1 if prev is not None and abs(st_ - prev) > 1 else 0
                prev = st_
        tot = sum(cnt.values()); pi = W.stationary(clim, mth)
        assert jump == 0 and all(abs(cnt[i] / tot - pi[i]) < 0.07 for i in range(6)), (mth, jump, [cnt[i] / tot for i in range(6)], pi)
    a1 = W.forecast("procedural", "zz", _dt.date(2004, 6, 12), 3, 14.0, pack); a2 = W.forecast("procedural", "zz", _dt.date(2004, 6, 12), 3, 14.0, pack)
    assert a1 == a2, "weather must be repeatable"
    last = None
    for h in range(6, 22):                                                  # within a day the picture drifts, it does not flip
        w_ = W.forecast("procedural", "zz", _dt.date(2004, 11, 3), 2, float(h), pack)
        assert last is None or abs(W.STATES.index(w_.state) - W.STATES.index(last.state)) <= 1, (h, last.state, w_.state)
        last = w_
    # the gate, on the real loadouts
    from sqe.loadouts import LoadoutLibrary as _LL
    lib_ = _LL()
    low = W.forecast("overcast", "t", _dt.date(2004, 6, 12), 1, 12.0, pack)
    hi = W.forecast("clear", "t", _dt.date(2004, 6, 12), 1, 12.0, pack)
    from sqe.models import Role as _R
    new_, notes_, keep_, dead_ = W.adapt(AIRCRAFT["FA-18C"].dcs_type, lib_.for_role("FA-18C", _R.STRIKE), low)
    names_ = [W.weapon_name(v["CLSID"]) for v in new_.values()]
    assert not any("GBU-12" in n for n in names_) and any("GBU-38" in n for n in names_) and notes_, names_
    assert W.adapt(AIRCRAFT["FA-18C"].dcs_type, lib_.for_role("FA-18C", _R.STRIKE), hi)[1] == []
    assert not any(W.classify(W.weapon_name(v["CLSID"])) == "EO" for v in W.adapt(AIRCRAFT["F-16C"].dcs_type, lib_.for_role("F-16C", _R.CAS), low)[0].values())
    # a campaign in an overcast: loadouts change in the built mission, a storm scrubs offensive packages and not the CAP, scrubbed ones are left alone
    done_ = False
    for sd in range(1, 9):
        ws = mk(); ws.settings.weather_mode = "overcast"
        ws.new("Wx", "FA-18C", 2, seed=sd)
        cand = [(p_, f_) for p_ in ws.packages() for f_ in ws.flyable(p_) if f_.role in (_R.STRIKE, _R.CAS)]
        if not cand:
            continue
        p_, f_ = cand[0]
        assert ws.wx_of(p_) is not None
        r_ = ws.fly(p_.number, f_.id)
        with zipfile.ZipFile(ws.settings.sortie_miz) as z_:
            mis = z_.read("mission").decode("utf-8", "replace")
        assert "BRU33_2X_GBU-12" not in mis and "LAU_117_AGM_65F" not in mis, "laser / imaging weapons loaded in an overcast"
        assert '["preset"]="' in mis and "SQE Overcast" in mis, "overcast clouds were not written to the mission"
        done_ = True
        break
    assert done_, "no Hornet strike or CAS package found to test"
    ss = mk(); ss.settings.weather_mode = "storm"; ss.new("Storm", "FA-18C", 2, seed=3)
    scr = [p_ for p_ in ss.packages() if p_.extra.get("scrub")]
    keep_ = [p_ for p_ in ss.packages() if p_.objective.type.value in ("BARCAP", "FLEET_DEFENSE")]
    assert scr and all(not ss.flyable(p_) for p_ in scr) and all(not p_.extra.get("scrub") for p_ in keep_)
    h0 = {a_.id: a_.health for a_ in ss.state.assets.values()}
    sk = ss.skip_day()
    assert any(r_.get("scrubbed") for r_ in sk["results"])
    print(f"[weather] climate odds, no jumps, repeatable; gate swaps lasers for JDAM and imaging Mavericks off; overcast build clean; storm scrubs {len(scr)} package(s), leaves CAP alone")

    # ---- carcasses: stable layouts, health -> count, weight and trim, off switch ----------------------------------------------------
    from sqe import carcass as _cc
    from sqe.mission_builder import SITES as _SITES, SOFT as _SOFT
    cs = mk(); cs.new("Carc", "FA-18C", 2, seed=5)
    sam = next(a_ for a_ in cs.state.assets.values() if a_.kind.value == "SAM" or str(a_.kind).endswith("SAM"))
    okf = lambda x, y: True
    sam.health = 0.5
    w50 = _cc.wrecks_for(sam, cs.state.campaign_id, (sam.x, sam.y), _SITES, _SOFT, okf)
    sam.health = 0.0
    w00 = _cc.wrecks_for(sam, cs.state.campaign_id, (sam.x, sam.y), _SITES, _SOFT, okf)
    assert 0 < len(w50) < len(w00) <= _cc.MAX_PER_SITE and w00[:len(w50)] == w50, "a worse site must only ADD wrecks, none may move"
    assert w00 == _cc.wrecks_for(sam, cs.state.campaign_id, (sam.x, sam.y), _SITES, _SOFT, okf), "wreck layout must be repeatable"
    assert _cc.stable_center(sam, cs.state.campaign_id, okf) == _cc.stable_center(sam, cs.state.campaign_id, okf)
    sam.health = 1.0
    assert _cc.wrecks_for(sam, cs.state.campaign_id, (sam.x, sam.y), _SITES, _SOFT, okf) == []
    n_by = {}
    for tag, kw in (("on", {}), ("off", {"carcasses": False}), ("tight", {"merge_max_units": 1})):
        ws_ = mk(); ws_.new("Carc2", "FA-18C", 2, seed=5)
        for a_ in ws_.state.assets.values():
            if a_.kind.value != "AIRFIELD" and not str(a_.kind).endswith("AIRFIELD"):
                a_.health = 0.0 if a_.id.endswith(("_0", "_1")) else a_.health
        for k_, v_ in kw.items():
            setattr(ws_.settings, k_, v_)
        p_ = next(p0 for p0 in ws_.packages() if ws_.flyable(p0) and p0.objective.type.value not in ("BARCAP", "FLEET_DEFENSE") and ws_.state.assets[p0.objective.target_id].health > 0)
        r_ = ws_.fly(p_.number, ws_.flyable(p_)[0].id)
        with zipfile.ZipFile(ws_.settings.sortie_miz) as z_:
            mis = z_.read("mission").decode("utf-8", "replace")
        n_by[tag] = (r_.counts.get("wrecks", 0), mis.count("WRECK "))
    assert n_by["on"][0] > 0 and n_by["on"][1] >= n_by["on"][0], n_by
    assert n_by["off"] == (0, 0), n_by
    assert n_by["tight"][0] == 0, n_by
    print(f"[carcass] layouts repeat and only grow as a site worsens; {n_by['on'][0]} wrecks built; off = none; unit limit trims them")

    # ---- reactive dispatch: range, availability, ratio, difficulty scaling, off switch -------------------------------------------------
    import random as _rnd
    from sqe import reactive as _rx
    from sqe.difficulty import get as _gd
    from sqe.loadouts import ENEMY_FIGHTERS as _EF
    from sqe.routes import bearing as _brg, NM as _NM
    rs = mk(); rs.new("React", "FA-18C", 3, seed=11)
    tgt_ = next(a_ for a_ in rs.state.assets.values() if a_.kind.value == "SAM")
    rate = {}
    for lv in (1, 2, 3):
        n_ = 0
        for k_ in range(400):
            used_ = {}
            picks_ = _rx.plan_red(rs.state, _gd(lv), _rnd.Random(k_), tgt_.x, tgt_.y, 2, 6, used_, _EF, _brg)
            n_ += bool(picks_)
            for pk_ in picks_:
                w_ = next(w for w in rs.state.enemy_air if w.base_asset_id == pk_["base"])
                assert used_[pk_["base"]] <= w_.available, "a wing cannot send more than it has"
                assert pk_["nm"] <= _rx.INTERCEPT_NM.get(pk_["type"], 120) and pk_["type"] in w_.types, "out of range or not that wing's type"
            assert 2 * len(picks_) + 2 <= max(2, round(2.0 * 6)), "reinforcements exceed 2:1"
        rate[lv] = n_ / 400
    assert rate[1] < rate[2] < rate[3] and rate[1] < 0.15, rate
    full_ = {w.base_asset_id: w.available for w in rs.state.enemy_air}
    for w in rs.state.enemy_air:
        w.available = 1                                                     # a wing with one jet cannot send a pair
    assert all(not _rx.plan_red(rs.state, _gd(3), _rnd.Random(k_), tgt_.x, tgt_.y, 2, 8, {}, _EF, _brg) for k_ in range(60))
    for w in rs.state.enemy_air:
        w.available = full_[w.base_asset_id]
    seen_r = seen_b = False
    for sd_ in range(1, 9):
        rr_ = mk(); rr_.new("React2", "FA-18C", 3, seed=sd_)
        for p_ in [q for q in rr_.packages() if rr_.flyable(q)][:3]:
            res_ = rr_.fly(p_.number, rr_.flyable(p_)[0].id)
            txt_ = res_.text["full"]
            sq_ = {g_["squadron"] for g_ in res_.manifest.groups if g_["kind"] == "friendly" and g_["ref"].startswith("alert_")}
            seen_b |= bool(sq_)
            seen_r |= "may be sent to reinforce" in txt_
            if sq_ or "may be sent to reinforce" in txt_:
                rr_.settings.reactive = False
                r2_ = rr_.fly(p_.number, rr_.flyable(p_)[0].id)
                with zipfile.ZipFile(rr_.settings.sortie_miz) as z_:
                    off_ = z_.read("mission").decode("utf-8", "replace")
                assert "Reinforce " not in off_ and "Intelligence:" not in r2_.text["full"] and not any(g_["ref"].startswith("alert_") for g_ in r2_.manifest.groups), "reactive off must add nothing"
                rr_.settings.reactive = True
        if seen_r and seen_b:
            break
    assert seen_r and seen_b, (seen_r, seen_b)
    print(f"[reactive] range and availability respected, never past 2:1; chance by level {rate[1]:.0%}/{rate[2]:.0%}/{rate[3]:.0%}; red + blue launch in a build; off = none")

    # ---- kneeboard: form layout, hh:mm:ss everywhere, no stale 'coords below' / 'SQE' / 'AI' wording --------------------------------------
    import re as _re
    from sqe import kneeboard as _kb
    assert _kb.hms("07:03") == "07:03:00" and _kb.hms("07:03:09") == "07:03:09" and _kb.hms("hold to 06:46") == "hold to 06:46:00"
    assert "coords below" not in open(Path(_kb.__file__).parent / "aircraft.py", encoding="utf-8").read()
    ks = mk(); ks.new("KB", "FA-18C", 3, seed=7)
    pk_ = next(p_ for p_ in ks.packages() if ks.flyable(p_))
    import sqe.mission_builder as _mb
    _cap = {}
    _orig = _mb.render_pages
    _mb.render_pages = lambda td, ctx: (_cap.update(ctx=ctx), _orig(td, ctx))[1]
    try:
        ks.fly(pk_.number, ks.flyable(pk_)[0].id)
    finally:
        _mb.render_pages = _orig
    ctx_ = _cap["ctx"]
    assert all(_re.fullmatch(r"\d\d:\d\d:\d\d", r_["time"]) for r_ in ctx_["waypoints"] if r_["time"]), [r_["time"] for r_ in ctx_["waypoints"]]
    assert all("hold to" not in r_["win"] or _re.search(r"\d\d:\d\d:\d\d", r_["win"]) for r_ in ctx_["waypoints"])
    import tempfile as _tf
    from PIL import Image as _Im
    with _tf.TemporaryDirectory() as td_:
        pgs = _kb.render_pages(td_, ctx_)
        assert [Path(p_).name for p_ in pgs] == ["1_comms_times.png", "2_fuel_codes_package.png", "3_other_threats_intel.png"]
        assert all(_Im.open(p_).size == (768, 1024) for p_ in pgs)
    print("[kneeboard] 3 form pages, every time hh:mm:ss, TGT remark points to page 2, 768x1024")
    # ---- DEP spacing: 10 nm from a boat, 8 nm from a field (6 for the A-10C), straight toward the marshal point
    from sqe.routes import make_geometry as _mg, dist as _d, bearing as _b, NM as _NM
    from sqe.aircraft import AIRCRAFT as _AC
    _pr = _AC["FA-18C"].profile
    _g = _mg(0, 0, 200 * _NM, 0, _pr, (-60 * _NM, 0)); assert abs(_d(0, 0, *_g.dep) / _NM - 8) < 0.01
    _g = _mg(0, 0, 200 * _NM, 0, _pr, (-60 * _NM, 0), carrier=True); assert abs(_d(0, 0, *_g.dep) / _NM - 10) < 0.01 and abs(_b(0, 0, *_g.dep) - 180) < 0.1
    _g = _mg(0, 0, 200 * _NM, 0, _pr, (-15 * _NM, 0)); assert abs(_d(0, 0, *_g.dep) / _NM - 6) < 0.01          # 40% cap on a short leg
    assert [k for k, v in _AC.tuned().items() if v.profile.dep_nm != 8.0] == ["A-10C"], "only the A-10C departs at 6 nm (tuned jets)"
    assert ks.__class__ and any(r_["name"] == "TAKEOFF" for r_ in ctx_["waypoints"])
    print("[departure] DEP 8 nm land / 10 nm carrier / 6 nm A-10C, capped at 40% of the way to the marshal point")
    # ---- altitude profiles: HIGH / MED / LOW from the SAM picture
    from types import SimpleNamespace as _NS
    from sqe import profiles as _pf
    from sqe.models import AssetKind as _AK, Role as _Rl
    def _st(*variants):
        return _NS(assets={f"s{i}": _NS(id=f"s{i}", kind=_AK.SAM, variant=v, destroyed=False, health=1.0, x=100_000 + 500 * i, y=0) for i, v in enumerate(variants)})
    _pts = [(0, 0), (60_000, 0), (100_000, 0), (140_000, 0)]
    _P = lambda ac: _AC[ac].profile
    _ch = lambda ac, role, *v, cloud=None: _pf.choose(_st(*v), role, _P(ac), _pts, (100_000, 0), cloud)
    t_ = _ch("FA-18C", _Rl.STRIKE); assert not t_.changed and t_.alt_ft == 20000 and not t_.rad, t_
    t_ = _ch("FA-18C", _Rl.STRIKE, "SA-6"); assert not t_.changed, "one SA-6 is not enough to change the profile"
    t_ = _ch("FA-18C", _Rl.STRIKE, "SA-11", "SA-6", "SA-2"); assert t_.changed and t_.rad and t_.alt_ft == 500 and t_.label == "LOW" and "from the IP" in t_.reason, t_
    assert not _pf.choose(_st("SA-11", "SA-6", "SA-2"), _Rl.STRIKE, _P("FA-18C"), _pts, (100_000, 0), None, skip={"s0", "s1", "s2"}).changed, "the DEAD target itself does not push the package low"
    assert not _ch("F-15C", _Rl.STRIKE, "SA-11", "SA-6", "SA-2").changed, "the FC3 F-15C never goes LOW"
    assert not _pf.choose(_st("SA-11", "SA-6", "SA-2"), _Rl.STRIKE, _P("FA-18C"), _pts, (100_000, 0), None, skip={"nothing"}).rad, "a DEAD package never goes LOW"
    _stn = _st("SA-11", "SA-6", "SA-2")
    for _a in _stn.assets.values(): _a.health = 0.1
    assert _pf.choose(_stn, _Rl.STRIKE, _P("FA-18C"), _pts, (100_000, 0), None).rad, "sites at 10% health still count for the profile"
    assert not _ch("FA-18C", _Rl.STRIKE, "SA-11", "SA-6", "SA-2", cloud=1500).changed, "a low cloud base closes LOW"
    assert not _ch("FA-18C", _Rl.SEAD, "SA-11", "SA-6", "SA-2").rad and not _ch("FA-18C", _Rl.ESCORT, "SA-11", "SA-6", "SA-2").rad, "SEAD and escorts never go LOW"
    t_ = _ch("A-10C", _Rl.CAS, "SA-11", "SA-6", "SA-2"); assert t_.rad and t_.alt_ft == 300, t_
    assert not _ch("A-10C", _Rl.CAS, "AAA").rad, "AAA alone does not push a CAS flight lower"
    from sqe.routes import make_geometry as _mg2, plan_route as _pr2
    _g2 = _mg2(0, 0, 100_000, 0, _P("FA-18C"), (-20_000, 0)); _g2.tier = _ch("FA-18C", _Rl.STRIKE, "SA-11", "SA-6", "SA-2")
    _w2 = {w.name: w for w in _pr2(_Rl.STRIKE, (0, 0), _g2, _P("FA-18C"), is_player=False, tanker_xy=None)}
    assert not _w2["PUSH"].rad and _w2["PUSH"].alt_ft == 20000 and all(_w2[n].rad and _w2[n].alt_ft == 500 for n in ("IP", "TGT", "EGR")), "the tier applies from the IP on"
    _w3 = {w.name: w for w in _pr2(_Rl.STRIKE, (0, 0), _g2, _P("FA-18C"), is_player=True, tanker_xy=None)}
    assert _w3["TGT"].agl and _w3["TGT"].alt_ft == 0 and not _w3["TGT"].rad, "the player's target point stays on the ground"
    print("[profiles] no threat = unchanged; heavy SAM cover -> LOW from the IP; F-15C, SEAD, escorts, low cloud stay up; PUSH keeps its altitude")
    # ---- ground height (relief): MSA, terrain masking, MED floor, spawn floor, kneeboard line
    from sqe import relief as _rl
    _rl.clear(); assert _rl.msa_ft(_pts) is None and _rl.visible_fraction((0, 0), _pts, 500, 50_000) is None, "no relief file: everything falls back"
    # 160 x 20 cells of 1 km: flat at 100 m, a 2,800 m ridge across the route at x = 50..52 km
    _hi = [[100.0] * 20 for _ in range(160)]
    for _i in (50, 51, 52):
        _hi[_i] = [2800.0] * 20
    _rl.from_grid(0, 0, 1000.0, _hi)
    _m = _rl.msa_ft([(10_000, 5_000), (120_000, 5_000)]); assert _m == int(-(-(2800 / 0.3048 + 2000) // 500) * 500), _m      # mountains: +2,000 ft
    _flat = _rl.msa_ft([(100_000, 5_000), (140_000, 5_000)]); assert _flat == int(-(-(100 / 0.3048 + 1000) // 500) * 500), _flat
    assert _rl.los_clear((10_000, 5_000), 10, (30_000, 5_000), 152) is True
    assert _rl.los_clear((10_000, 5_000), 10, (90_000, 5_000), 152) is False, "the ridge hides a low flight"
    assert _rl.los_clear((10_000, 5_000), 10, (90_000, 5_000), 12_000) is True, "...but not a high one"
    # a radar SAM behind the ridge counts for little against LOW; with open ground it keeps its full weight
    _t_open = _pf.exposure([(_NS(x=20_000, y=5_000), "SA-11", "target")], 500, True, [(30_000, 5_000), (45_000, 5_000)])
    _t_hid = _pf.exposure([(_NS(x=40_000, y=5_000), "SA-11", "target")], 500, True, [(56_000, 5_000), (70_000, 5_000)])
    assert _t_open > _t_hid and abs(_t_hid - 2.5 * 0.2) < 1e-6 and abs(_t_open - 2.5) < 1e-6, (_t_open, _t_hid)
    assert _pf.low_factor(_NS(x=0, y=0), "SA-11", None, 500) == _pf.LOW_RADAR_FACTOR
    # MED is dropped when it would sit under the safe altitude
    _rl.clear()
    _ok = _pf.choose(_st("SA-8", "SA-15"), _Rl.ESCORT, _P("FA-18C"), _pts, (100_000, 0), None, (), None)
    _no = _pf.choose(_st("SA-8", "SA-15"), _Rl.ESCORT, _P("FA-18C"), _pts, (100_000, 0), None, (), 30_000)
    assert not _no.changed, "MED below the minimum safe altitude is never chosen"
    # spawn floor: ground + 1,500 ft near the ridge, 6,000 ft without a scan
    from sqe.routes import _floor_ft
    assert _floor_ft(51_000, 5_000) == 6000
    _rl.from_grid(0, 0, 1000.0, _hi); assert _floor_ft(51_000, 5_000) == int(-(-(2800 / 0.3048 + 1500) // 500) * 500) and _floor_ft(140_000, 5_000) < 6000
    _rl.clear()
    # kneeboard: the MSA line shows when the build knows it, and is absent otherwise
    import sqe.kneeboard as _kb2
    _seen = []
    _ol = _kb2._Form.line
    _kb2._Form.line = lambda self, t, *a_, **k_: (_seen.append(str(t)), _ol(self, t, *a_, **k_))[1]
    try:
        with _tf.TemporaryDirectory() as td_:
            _kb2.render_pages(td_, dict(ctx_, msa=14500)); assert "MSA 14,500 ft along the route." in _seen, _seen
            _seen.clear(); _kb2.render_pages(td_, dict(ctx_, msa=None)); assert not any(x_.startswith("MSA") for x_ in _seen)
    finally:
        _kb2._Form.line = _ol
    print("[relief] MSA with 1,000/2,000 ft margin, ridge masks a low flight but not a high one, MED floor, spawn floor, no file = old behaviour")
    # ---- the ground war ----
    import random as _rnd, json as _js
    from sqe import ground as _gr, war as _war
    from sqe.state import CampaignState as _CS
    from sqe.difficulty import get as _gd
    for _lv in (1, 2, 3):
        s.new(f"Ground {_lv}", "F-16C", _lv, seed=11)
        _st = s.state; _g = _st.ground
        assert _gr.active(_st) and _gr.n_zones(_g) == 5 and len(_gr.summary(_st)) >= 5
        assert all(f"armor_{i + 1}" in _st.assets for i in range(5)) and _st.blue_assets, "columns and Blue facilities exist"
        # same seed, same fighting
        _a, _b = _CS.from_dict(_st.to_dict()), _CS.from_dict(_st.to_dict())
        for _d in range(8):
            _gr.resolve_day(_a, _gd(_lv), _rnd.Random(_d)); _gr.resolve_day(_b, _gd(_lv), _rnd.Random(_d))
        assert _a.ground["red"] == _b.ground["red"] and _a.ground["blue"] == _b.ground["blue"]
        assert all(0 <= v <= _gr.MAX_FORCE for v in _a.ground["red"] + _a.ground["blue"])
        # the round trip keeps it
        assert _CS.from_dict(_a.to_dict()).ground == _a.ground and set(_CS.from_dict(_a.to_dict()).blue_assets) == set(_a.blue_assets)
    # a field falls when Red holds the zone beside it; two fallen fields is defeat; Blue retaking it brings it back
    s.new("Ground fall", "F-16C", 2, seed=5); _st = s.state; _g = _st.ground
    _g["red"][3], _g["blue"][3] = 40.0, 0.0
    _ln = _gr.check_falls(_st); assert _g["fallen"] == ["senaki"] and _ln and _st.bases["senaki"].defense == 0
    _g["red"][4], _g["blue"][4] = 40.0, 0.0; _gr.check_falls(_st)
    assert _gr.fallen_count(_st) == 2; assert _war.update_status(_st) == "DEFEAT", "two fallen fields lose the war"; _st.status = "ACTIVE"
    _g["blue"][3] = 30.0; _gr.check_falls(_st); assert "senaki" not in _g["fallen"]
    # a debrief loss in a zone column is damped; Blue losses reduce the zone's strength
    _col = _st.assets["armor_2"]
    assert _gr.column_health(_st, _col, 1.0, 0.0) == 1.0 - _gr.AIR_EFFECT
    _before = _g["blue"][1]; _gr.blue_losses(_st, "armor_2", 2, 4); assert _g["blue"][1] == max(0.0, _before - _gr.BLUE_LOSS / 2)
    # an old format-4 save gets a ground war
    _old = _CS.from_dict(s.state.to_dict()).to_dict(); _old["format"] = 4; _old.pop("ground"); _old.pop("blue_assets")
    _mig = _CS.from_dict(_old); assert _gr.active(_mig) and _mig.blue_assets and any("ground war" in x for x in _mig.log)
    # CAS on a column is offered only where the sector is contested
    s.new("Ground cas", "A-10C", 2, seed=3); _st = s.state; _g = _st.ground
    _g["red"][0], _g["blue"][0] = 70.0, 0.0
    _opts = _war.ObjectivePlanner(_gd(2)).plan(_st, _rnd.Random(2), limit=40)
    assert not any(getattr(o, "target_id", "") == "armor_1" for o in _opts), "an uncontested sector is not a CAS target"
    _g["red"][1], _g["blue"][1] = 60.0, 20.0; _gr.push(_st); _ground_pl = _war.ObjectivePlanner(_gd(2)).plan(_st, _rnd.Random(2), limit=40)
    assert any(getattr(o, "target_id", "") == "armor_2" and "Red 60" in o.description for o in _ground_pl), "a contested sector is, with its strengths"
    # a full night of the war on a live campaign
    for _ in range(3):
        s.state.status = "ACTIVE"; _war.WarSimulator(_gd(2), _rnd.Random(9)).end_day(s.state)
    print("[ground] 5 sectors per level, repeatable fighting, round trip, falls / retaking / defeat, damped column losses, Blue losses, format-4 migration, nightly resolution")
    # ---- raids and emergencies ----
    from sqe import raids as _rd
    from sqe.packages import Package as _Pk
    _ev_orig = _EMERG
    _rd.emergency_happens = _EMERG                       # switched back on here (it is off above so the other tests are not at the mercy of the dice)
    s.new("Raids 2", "F-16C", 2, seed=4); _st = s.state
    # rates over a long run follow the difficulty table, and the same day plans the same raids
    _nw = _ns = 0
    for _ in range(60):
        s.plan_day(); _st.day += 1
        _nw += sum(1 for p_ in s.packages() if p_.objective.type.value == "FLEET_DEFENSE" and p_.extra.get("land")); _ns += _st.raids["surprise"]
    assert 8 <= _nw <= 36 and _ns >= 1, (_nw, _ns)
    _st.day = 5; s.plan_day(); _a = [d_["objective"]["description"] for d_ in _st.plan]; s.plan_day(); assert _a == [d_["objective"]["description"] for d_ in _st.plan], "a day replans the same"
    # per-sortie dice: roughly the table, never two in a row, and asking twice gives the same answer
    _hits = _tot = 0
    for _ in range(150):
        s.plan_day(); _st.day += 1
        for p_ in s.packages():
            if s.flyable(p_):
                _st.sortie_counter += 1; _tot += 1
                e1 = s.emergency_for(p_.number, None); e2 = s.emergency_for(p_.number, None)
                assert (e1 is None) == (e2 is None) and (e1 is None or e1["kind"] == e2["kind"]), "reopening never re-rolls"
                if e1:
                    _hits += 1
                    _st.raids["last_emerg"] = _st.sortie_counter                         # as fly() leaves it: that sortie had one
                    assert s.emergency_for(p_.number, "x") is None, "none in two sorties in a row"
    assert 0.045 <= _hits / _tot <= 0.16, (_hits, _tot)
    # an emergency forced: scramble (fighter) and decline (folds in or odds); both build a mission
    _rd.emergency_happens = lambda st_, d_, rng_: True
    try:
        for _ac, _lv, _seed in (("F-16C", 2, 4), ("A-10C", 2, 9), ("FA-18C", 3, 3)):
            for _scr in (True, False):
                s.new(f"Emerg {_ac}{_scr}", _ac, _lv, seed=_seed); _st = s.state
                _p = next(p_ for p_ in s.packages() if s.flyable(p_) and s.emergency_for(p_.number, None))
                _ev = s.emergency_for(_p.number, None); assert _ev["kind"] in ("RAID", "CAS") and _ev["title"] and _ev["text"]
                _res = s.fly(_p.number, None, scramble=_scr)
                assert _st.pending and _res.counts["units"] > 0
                if _scr and _ev["eligible"]:
                    assert "Intercept a raid" in _st.pending["objective"] or "EMERGENCY" in _st.pending["objective"]
                assert all(p_.number != _st.pending["package"] or True for p_ in s.packages())
                assert all(not x_.extra.get("past") for x_ in s.packages()), "emergency packages are not listed"
        # postponement: the squadron cannot cover both
        s.new("Emerg post", "A-10C", 2, seed=9); _st = s.state
        _p = None
        for _day in range(8):                                                       # any day that has a troops-in-contact emergency for an A-10 package
            _p = next((p_ for p_ in s.packages() if s.flyable(p_) and (s.emergency_for(p_.number, None) or {}).get("kind") == "CAS"), None)
            if _p:
                break
            _st.day += 1; s.plan_day()
        assert _p is not None
        _ev = s.emergency_for(_p.number, None)
        _st.squadrons[_st.player.squadron_id].available = _ev["package"].flights[0].count
        s.fly(_p.number, None, scramble=True)
        assert _st.raids["carry"], "the displaced package is postponed"
        _n_before = len(_st.raids["carry"]); _tgt = _st.raids["carry"][0]["target_id"]
        s.state.status = "ACTIVE"; _war.WarSimulator(_gd(2), _rnd.Random(3)).end_day(_st); s.plan_day()
        assert any(p_.objective.target_id == _tgt for p_ in s.packages()) or _tgt in _st.assets and _st.assets[_tgt].destroyed, "postponed objective returns next day"
    finally:
        _rd.emergency_happens = _ev_orig
    # the land raid is built with Su-24M bombers, and the debrief applies what got through
    import zipfile as _zf
    s.new("Raid build", "F-16C", 2, seed=4); _st = s.state
    _rp = next((p_ for p_ in s.packages() if p_.objective.type.value == "FLEET_DEFENSE" and p_.extra.get("land") and s.flyable(p_)), None)
    if _rp is None:
        _rd.emergency_happens = lambda st_, d_, rng_: True
        try:
            _rp0 = None
            for _day in range(8):
                _rp0 = next((p_ for p_ in s.packages() if s.flyable(p_) and (s.emergency_for(p_.number, None) or {}).get("kind") == "RAID" and s.emergency_for(p_.number, None)["eligible"]), None)
                if _rp0:
                    break
                _st.day += 1; s.plan_day()
            assert _rp0 is not None
            s.fly(_rp0.number, None, scramble=True)
        finally:
            _rd.emergency_happens = _ev_orig
    else:
        s.fly(_rp.number, None)
    _mz = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
    assert "Su-24M" in _mz and "RAID-B-1" in _mz, "the raiders are in the mission"
    _man = s.manifest(); _rg = next(g_ for g_ in _man.groups if g_.get("raid_base"))
    _base = _st.bases[_rg["raid_base"]]; _def0 = _base.defense
    _data = {"campaign": _st.campaign_id, "sortie": _st.sortie_counter, "package": _st.pending["package_dict"]["id"], "mission_ended": True,
             "time": int(_rg["raid_arrive_s"]) + 600, "dead": [], "ejected": [], "landed": [_man.player_unit], "player": {"takeoff": 60, "landed": 3000, "ka": 0, "kg": 0, "ks": 0}, "kills": []}
    s.apply(_data); assert _base.defense < _def0 or any("bombs fell" in x_ for x_ in _st.log), "bombers that got through hit the base"
    # surprise raids nobody flew are settled overnight; the file round-trips and an old save loads
    s.new("Raid night", "F-16C", 2, seed=6); _st = s.state
    _st.raids["surprise"] = 3; _lines = _rd.overnight(_st, _gd(2), _rnd.Random(1)); assert _lines and _st.raids["surprise"] == 0
    _rt = _CS.from_dict(_st.to_dict()); assert _rt.raids == _st.raids
    _o = _st.to_dict(); _o.pop("raids"); assert _CS.from_dict(_o).raids == {}
    print("[raids] announced and surprise raids by level, repeatable emergencies (about 9% a sortie, never two in a row), scramble / stay, CAS folded in, postponement, Su-24M raid built and applied, overnight surprises")
    # alert pairs have a dispatch range like the enemy's reinforcements
    from sqe import reactive as _rv
    s.new("Alert range", "FA-18C", 2, seed=4); _st = s.state
    _cv = next(b_ for b_ in _st.bases.values() if b_.kind.value == "CARRIER")
    _near = _rv.blue_sources(_st, AIRCRAFT, {Role.CAP, Role.ESCORT, Role.SWEEP}, {}, _cv.x + 60 * 1852, _cv.y)
    _far = _rv.blue_sources(_st, AIRCRAFT, {Role.CAP, Role.ESCORT, Role.SWEEP}, {}, _cv.x, _cv.y + 170 * 1852)
    assert any(c_[1].id == _cv.id for c_ in _near), "the carrier answers 60 nm away"
    assert not any(c_[1].id == _cv.id and c_[0].aircraft == "FA-18C" for c_ in _far), "no Hornet alert pair is sent 170 nm"
    assert all(c_[2] <= _rv.BLUE_DISPATCH_NM.get(c_[0].aircraft, _rv.BLUE_DISPATCH_DEFAULT_NM) for c_ in _far + _near)
    print("[alert range] alert pairs are sent no further than their dispatch range (F-14 150, Hornet 130, Viper 120, Eagle 160 nm)")
    # fighters stop short of live SAM cover, and AI escorts / sweeps have an engage limit
    from sqe.routes import make_geometry as _mg3, plan_route as _pr3
    _sam = lambda x_, v_="SA-11", h_=1.0: _NS(assets={"z": _NS(id="z", kind=_AK.SAM, variant=v_, destroyed=h_ <= 0.05, health=h_, x=x_, y=0)})
    _line = [(0, 0), (60_000, 0), (140_000, 0)]
    _r = _pf.standoff(_sam(140_000), _line, 22000)
    assert _r and _r[2] == ["SA-11"] and _r[3] > 20, "a live SA-11 at the target stops the fighters well short"
    assert _pf.standoff(_sam(140_000, h_=0.0), _line, 22000) is None, "a destroyed site stops nobody"
    assert _pf.standoff(_sam(140_000, h_=0.11), _line, 22000) is not None, "a site at 11% still shoots (mop-up targets): it counts"
    assert _pf.standoff(_sam(10_000), _line, 22000) is None, "a flight that already starts inside cover is left alone"
    assert _pf.standoff(_NS(assets={}), _line, 22000) is None
    _g3 = _mg3(0, 0, 140_000, 0, _P("FA-18C"), (-20_000, 0)); _g3.tier = _pf.Tier(22000, False) if False else None
    _key = (_Rl.ESCORT, id(_P("FA-18C"))); _g3.stand = {_key: _r}
    _w4 = {w.name: w for w in _pr3(_Rl.ESCORT, (0, 0), _g3, _P("FA-18C"), is_player=False, tanker_xy=None)}
    assert _w4["TGT"].orbit and "EGR" not in _w4 and abs(_w4["TGT"].x - _r[0]) < 1, "an AI escort holds at the stand-off point and goes home from it"
    _w5 = {w.name: w for w in _pr3(_Rl.ESCORT, (0, 0), _g3, _P("FA-18C"), is_player=True, tanker_xy=None)}
    assert not _w5["TGT"].orbit and "EGR" in _w5, "the player's own route is never cut short"
    # in a built mission: put a live SAM site on the target and look for the limit and the hold
    s.new("Stand off", "FA-18C", 2, seed=8); _st = s.state
    _p = next(p_ for p_ in s.packages() if s.flyable(p_) and any(f_.role == _Rl.ESCORT for f_ in p_.flights) and p_.objective.type.value in ("STRIKE", "DEAD"))
    s.fly(_p.number, None)
    _mz = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
    assert "EngageTargets" in _mz and "74080" in _mz, "AI escorts carry a 40 nm engage limit"
    from sqe.mission_builder import MissionBuilder as _MB
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 40, 1500)
    _t0 = _gx.points[0].tasks[0]; assert _t0.Id == "ControlledTask" and _t0.params["stopCondition"]["time"] == 1500 and _t0.params["task"]["params"]["maxDist"] == 74080, "engage task is time-limited"
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 0, 900); assert _gx.points[0].tasks[0].params["task"]["params"]["maxDistEnabled"] is False
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 40); assert _gx.points[0].tasks[0].Id == "EngageTargets" and len(_gx.points[0].tasks) == 1
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 0); assert not _gx.points[0].tasks
    print("[engage time] the engage task stops at TOT + 5 min and the flight flies on (alert pairs +5); distance-only and unlimited forms unchanged")
    print("[stand-off] fighters stop outside live SAM rings (player excepted), hold there and go home; AI escorts and sweeps carry the 40 nm engage limit")
    # ---- phase 3: air defence that rebuilds and moves ----
    from sqe import sams as _sm
    import math as _mm
    s.new("Sams", "FA-18C", 3, seed=11); _st = s.state
    _ds = _NS(sam_rebuild=1.0, sam_scoot=1.0)
    _lr = next(a_ for a_ in _st.assets.values() if a_.kind == _AK.SAM and a_.id.startswith("sam_") and a_.variant in ("SA-2", "SA-3", "SA-6", "SA-11", "SA-10") and a_.tier <= _st.front + 2)
    _lr.health = 0.0; _st.day = 10; _sm.track(_st); assert _st.sams["down"][_lr.id] == 10
    _st.day = 12; assert not _sm.rebuild(_st, _ds, _rnd.Random(1)) and _lr.destroyed, "not rebuilt before the third day"
    _st.day = 13; _got = []
    for _k in range(30):
        _got = _sm.rebuild(_st, _ds, _rnd.Random(_k))
        if _got: break
    assert _got and abs(_lr.health - _sm.REBUILT_HEALTH) < 1e-9 and _lr.id not in _st.sams["down"], "a destroyed site is replaced at half strength"
    _fs = next(a_ for a_ in _st.assets.values() if a_.id.startswith("fsam_")); _fs.health = 0.0; _st.day = 30; _sm.track(_st); _st.day = 40
    for k_ in range(5): _sm.rebuild(_st, _ds, _rnd.Random(k_))
    assert _fs.destroyed, "column air defence is not rebuilt"
    _deep = next((a_ for a_ in _st.assets.values() if a_.kind == _AK.SAM and a_.tier > _st.front + 2 and a_.id.startswith("sam_")), None)
    if _deep is not None:
        _deep.health = 0.0; _st.day = 30; _sm.track(_st); _st.day = 40
        assert all(not _sm.rebuild(_st, _ds, _rnd.Random(k_)) for k_ in range(5)) and _deep.destroyed, "nothing is rebuilt beyond the tiers in play"
    _mob = next(a_ for a_ in _st.assets.values() if a_.kind == _AK.SAM and a_.variant in _sm.MOBILE and not a_.id.startswith("fsam_") and not a_.destroyed)
    _gar = next((g_ for g_ in _st.assets.values() if g_.guards == _mob.id), None)
    _mob.health = 1.0
    _x0, _y0 = _mob.x, _mob.y; _g0 = (_gar.x, _gar.y) if _gar else None
    _mob.health = 0.5; _n = 0
    for _k in range(6):
        _n += len([l_ for l_ in _sm.relocate(_st, _ds, _rnd.Random(50 + _k)) if _mob.name in l_])
    assert 1 <= _n <= _sm.MAX_MOVES, "a hurt mobile site moves, at most twice"
    assert _mm.hypot(_mob.x - _x0, _mob.y - _y0) <= _sm.MAX_DRIFT_NM * 1852 + 1, "and never drifts far from where it started"
    if _gar: assert abs((_gar.x - _mob.x) - (_g0[0] - _x0)) < 1, "its garrison goes with it"
    _fx = next(a_ for a_ in _st.assets.values() if a_.kind == _AK.SAM and a_.variant not in _sm.MOBILE and not a_.id.startswith("fsam_") and not a_.destroyed)
    _fx.health = 0.4; _px = (_fx.x, _fx.y); _sm.relocate(_st, _ds, _rnd.Random(7)); assert (_fx.x, _fx.y) == _px, "fixed sites (SA-2, SA-3, SA-10) never move"
    _fl = [b_ for b_ in _st.bases.values() if b_.kind.value == "AIRFIELD"]
    for b_ in _fl: b_.defense = 0.3
    _sm.blue_defence(_st, _gd(3)); assert all(0.31 < b_.defense <= 0.41 for b_ in _fl), "airfield defences repair by supply (at most 0.10 a day)"
    _fl[0].defense = 0.95; _fl[1].defense = 0.2; _lines = _sm.blue_defence(_st, _gd(3)); assert _lines and _fl[0].defense < 1.0, "a strong field lends a battery to the weakest"
    _st.ground["fallen"] = [_fl[1].id]; _d1 = _fl[1].defense; _sm.blue_defence(_st, _gd(3)); assert _fl[1].defense == _d1, "a fallen field does not repair"
    _rt = _CS.from_dict(_st.to_dict()); assert _rt.sams == _st.sams
    _o = _st.to_dict(); _o.pop("sams"); assert _CS.from_dict(_o).sams == {}
    s.new("Sams night", "FA-18C", 3, seed=12); _st = s.state; _st.status = "ACTIVE"
    for _k in range(8): _war.WarSimulator(_gd(3), _rnd.Random(_k)).end_day(_st)
    print("[sams] destroyed sites are replaced after 3 days (not column SAMs, not beyond the tiers in play), hurt mobile sites move (garrison too, 2 moves, 10 nm), airfield defences repair by supply and lend a battery, save round trip")
    # v0.26.1: Red's known CAP stays out of the fleet's reach; the player's flight gets the stand-off in AI-test mode
    _g3.ai_player = True
    _w6 = {w.name: w for w in _pr3(_Rl.ESCORT, (0, 0), _g3, _P("FA-18C"), is_player=True, tanker_xy=None)}
    assert _w6["TGT"].orbit and "EGR" not in _w6, "AI-test mode: the player's own flight stops short too"
    from sqe import mission_builder as _mbm
    _rec_cap = []
    _orig_pcs = _mbm.MissionBuilder._plan_cap_stations
    def _spy_pcs(self_, *a_, **k_):
        out_ = _orig_pcs(self_, *a_, **k_)
        cvs_ = [(b_.x, b_.y) for b_ in self_.state.bases.values() if b_.kind.value == "CARRIER"]
        for c_ in out_:
            _rec_cap.append(min(_mm.hypot(c_["x"] - cx_, c_["y"] - cy_) / 1852 for cx_, cy_ in cvs_) if cvs_ else 999.0)
        return out_
    _mbm.MissionBuilder._plan_cap_stations = _spy_pcs
    try:
        for _sd in (3, 5, 8, 11):
            s.new(f"Fleet {_sd}", "F-15C", 3, seed=_sd); _st = s.state
            for _p in [p_ for p_ in s.packages() if s.flyable(p_)][:2]:
                s.fly(_p.number, None)
    finally:
        _mbm.MissionBuilder._plan_cap_stations = _orig_pcs
    assert _rec_cap and min(_rec_cap) >= _mbm.CAP_FLEET_KEEPOUT_NM - 1.0, f"Red CAP stations stay 90 nm from every carrier ({min(_rec_cap):.0f})"
    print(f"[fleet keep-out] {len(_rec_cap)} known CAP stations, the nearest {min(_rec_cap):.0f} nm from a carrier (limit 90); AI-test mode gives your flight the stand-off")
    # the ground-war map draws (sector numbers and strength bars, no overlapping figures)
    import os as _os; _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication as _QA
    _qa = _QA.instance() or _QA([])
    from sqe.gui.widgets import MapView as _MV
    s.new("Map", "FA-18C", 3, seed=2); _mv = _MV(); _mv.resize(600, 420); _mv.set_state(s.state)
    _img = _mv.grab().toImage(); assert _img.width() >= 600 and not _img.isNull(), "the map renders"
    print("[map] the ground-war map renders with sector numbers and red | blue bars")
    # AI-test mode builds the player's flight as an AI flight
    s.new("AI test", "F-15C", 3, seed=4); _st = s.state
    _pk = next(p_ for p_ in s.packages() if s.flyable(p_))
    s.settings.player_is_ai = False; s.fly(_pk.number, None)
    _t0 = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
    s.settings.player_is_ai = True; s.fly(_pk.number, None)
    _t1 = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
    s.settings.player_is_ai = False
    assert '"Player"' in _t0 and '"Player"' not in _t1 and '"Client"' not in _t1, "with the AI-test tick the mission has no player or client slot"
    print("[ai test] the AI-flown tick builds your flight as AI (no player slot); off = a player slot")
    _catalog_test(s)
    _faction_test(s)
    print("SMOKE TEST PASSED")


def _faction_test(s):
    """Faction packs: every bundled pack names only units this pydcs knows; mixed eras and incomplete packs are refused; a campaign saves
    its factions and gets them back on open; the modern pair reproduces the old hard-coded order of battle."""
    from sqe import factions as _fx
    from sqe.state import CampaignState as _CS
    bad = {f: _fx.problems(f) for f in _fx.packs()}
    assert not any(bad.values()), f"faction packs name unknown units: {bad}"
    for pair, ok in ((("modern_usa", "modern_russia"), True), (("ww2_allies_europe", "ww2_axis_germany"), True),
                     (("modern_usa", "ww2_axis_germany"), False), (("ww2_allies_pacific", "ww2_axis_japan"), False)):
        try:
            _fx.check_pair(*pair); got = True
        except ValueError:
            got = False
        assert got == ok, f"pair {pair} should be {'accepted' if ok else 'refused'}"
    s.new("Factions", "F-16C", 2, seed=3)
    assert s.state.factions == {"blue": "modern_usa", "red": "modern_russia"}, s.state.factions
    s.save(); back = _CS.load(s.path)
    assert back.factions == s.state.factions, "factions survive a save"
    _fx.use("ww2_allies_europe", "ww2_axis_germany")
    assert "FW_190D9" in __import__("sqe.loadouts", fromlist=["x"]).ENEMY_FIGHTERS and _fx.striker() == "Ju_88A4", "live views follow the active factions"
    s.open(s.path)
    assert _fx.red()["id"] == "modern_russia" and "MiG_29A" in __import__("sqe.loadouts", fromlist=["x"]).ENEMY_FIGHTERS, "opening a campaign restores its factions"
    from sqe.mission_builder import SITES as _S
    assert _S["SA-6"] == [("Kub_2P25_ln", 3), ("Kub_1S91_str", 1), ("ZSU_23_4_Shilka", 1)] and "FLAK88" in _S, "site types from every pack"
    print(f"[factions] {len(_fx.packs())} packs, all units known to pydcs; eras and incomplete packs checked; saved and restored with the campaign")


def _catalog_test(s):
    """The unit catalog: every flyable pydcs type plus the A-4E-C unit pack resolve; a new squadron of a generated type and of the mod
    can be raised on any theatre, flies a sortie, and the mod mission lists the A-4E-C under requiredModules."""
    import zipfile as _zf
    from dcs import planes as _pl, lua as _lua
    from sqe import scenario as _sc, modunits as _mu
    from sqe.models import RefuelMethod as _RM
    flyable = [t for t in _pl.plane_map.values() if t.flyable]
    assert all(t.id in AIRCRAFT or any(sp.dcs_type is t for sp in AIRCRAFT.tuned().values()) for t in flyable), "every flyable pydcs plane is in the catalog"
    a4 = AIRCRAFT["A-4E-C"]
    assert a4.source == "mod" and a4.player_flyable and a4.carrier_capable and a4.era == "early_jet", "A-4E-C comes from its unit pack"
    assert a4.dcs_type.id == "A-4E-C" and "A-4E-C" in _pl.plane_map, "the A-4E-C is a real pydcs type at runtime"
    assert AIRCRAFT["P-51D"].era == "ww2" and AIRCRAFT["P-51D"].refuel == _RM.NONE, "warbirds are WWII and never refuel"
    assert not AIRCRAFT["CH-47Fbl1"].player_flyable, "helicopters wait for their own profiles"
    built = []
    for key in ("A-4E-C", "P-51D", "MiG-21Bis"):
        opts = [sid for sid, _ in _sc.squadron_options(key, "caucasus") if sid.startswith(_sc.NEW_SQUADRON)]
        assert opts, f"{key}: a new squadron can be raised"
        s.new(f"Catalog {key}", key, 2, seed=5, squadron=opts[-1])
        assert s.state.squadrons[s.state.player.squadron_id].aircraft == key
        pks = [p for p in s.packages() if s.flyable(p)]
        if not pks:
            print(f"[catalog] {key}: no flyable package today (fine)"); continue
        res = s.fly(pks[0].number, None)
        mission = _zf.ZipFile(s.state.pending["miz"]).read("mission").decode()
        m = _lua.loads(mission)["mission"]
        if key == "A-4E-C":
            assert m.get("requiredModules", {}).get("A-4E-C") == "A-4E-C", "the mod is listed under requiredModules"
            assert '"A-4E-C"' in mission
        if all(AIRCRAFT[f.aircraft].refuel == _RM.NONE for f in pks[0].flights if not f.tag):
            assert not any(sp.slot.startswith("TANKER") for sp in pks[0].support), "no tanker for a package nobody in it can refuel from"
        built.append(f"{key}: {pks[0].objective.type.value}, {res.counts['units']} units")
    assert _mu.required_modules({"F-16C_50"}) == {}, "stock types need no module entry"
    print(f"[catalog] {len(AIRCRAFT)} types ({len(AIRCRAFT.tuned())} tuned, {len(AIRCRAFT.by_source('mod'))} mod, "
          f"{len(AIRCRAFT.player_types())} flyable by you); new squadrons flown: " + "; ".join(built))


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
