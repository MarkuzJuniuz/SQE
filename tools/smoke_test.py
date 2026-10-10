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
    print(f"SQE smoke test, version {sqe.__version__}  (isolated temp data: {TMP})")
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    s = mk()
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    assert not s.settings.problems(), s.settings.problems()
    tested, kinds = 0, set()
    for aircraft, spec in AIRCRAFT.items():
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
    assert [k for k, v in _AC.items() if v.profile.dep_nm != 8.0] == ["A-10C"], "only the A-10C departs at 6 nm"
    assert ks.__class__ and any(r_["name"] == "TAKEOFF" for r_ in ctx_["waypoints"])
    print("[departure] DEP 8 nm land / 10 nm carrier / 6 nm A-10C, capped at 40% of the way to the marshal point")
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
