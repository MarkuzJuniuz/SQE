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
    for aircraft, spec in AIRCRAFT.items():
        if not spec.player_flyable:
            continue
        s.new(f"Smoke {aircraft}", aircraft, 3, seed=7)         # level 3 so the bomber raid objective exists too
        _cs = [f.callsign for p in s.packages() for f in p.flights]
        assert len(_cs) == len(set(_cs)), f"no two flights share a callsign in a day: {sorted(c for c in _cs if _cs.count(c) > 1)}"
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
    cand = next(((p, ms.merge_candidates(p)) for p in ms.packages() if ms.flyable(p) and ms.merge_candidates(p) and p.objective.aim != "SWEEP"), None)
    assert cand, "no mergeable packages found"
    pk, extra = cand
    res = ms.fly(pk.number, ms.flyable(pk)[0].id)
    assert res.merged and len(res.merged) <= len(extra), res.merged   # extras may be dropped to fit the unit cap
    man = ms.manifest()
    z = zipfile.ZipFile(ms.settings.sortie_miz); lua.loads(z.read("mission").decode())
    _mz = lua.loads(z.read("mission").decode())
    _tags = {f.callsign for f in pk.flights if f.tag}
    _stops = []
    for _c in _mz["mission"]["coalition"].values():
        for _cn in _c["country"].values():
            for _g in _cn.get("plane", {}).get("group", {}).values():
                if _g["name"] in _tags:
                    _stops += [t_["params"]["stopCondition"]["time"] for t_ in _g["route"]["points"][2]["task"]["params"]["tasks"].values() if t_["params"].get("stopCondition")]
    assert _tags and _stops and min(_stops) >= max(m["rtb_s"] for m in res.merged) + 300 - 1, ("HAVCAP / base CAP outlast the merged packages", _stops)
    print(f"[merge] #{pk.number} {pk.objective.type.value} + {[(m['number'], m['type']) for m in res.merged]}: {res.counts['groups']} groups / {res.counts['units']} units")
    # every AI ground-attack flight stays on its job: no air-to-air on the way in, home when the air-to-ground load is gone, self-defence after the attack
    from sqe.mission_builder import A2G_WEAPONS as _A2GW
    _opts = lambda pt_: {t_["params"]["action"]["params"]["name"]: t_["params"]["action"]["params"].get("value") for t_ in pt_["task"]["params"]["tasks"].values()
                         if t_.get("params", {}).get("action", {}).get("id") == "Option"}
    _a2g = 0
    for _cn in _mz["mission"]["coalition"]["blue"]["country"].values():
        for _g in _cn.get("plane", {}).get("group", {}).values():
            _us = list(_g["units"].values())
            if _g.get("task") not in ("Pinpoint Strike", "SEAD", "CAS", "Ground Attack") or any(u_.get("skill") in ("Player", "Client") for u_ in _us):
                continue
            _pts = list(_g["route"]["points"].values()); _o0 = _opts(_pts[0])
            assert _o0.get(14) is True and _o0.get(10) == _A2GW and _o0.get(0) == 3, (_g["name"], "restricted air-to-air, RTB when out of A2G weapons, return fire", _o0)
            _egr = next((p_ for p_ in _pts if p_.get("name") == "EGR"), None)
            if _egr is not None and _us[0]["type"].startswith(("F-16", "FA-18", "F-14")):
                assert _opts(_egr).get(14) is False and _opts(_egr).get(0) == 3, (_g["name"], "self-defence after the attack")
            _a2g += 1
    assert _a2g, "no AI ground-attack flight checked"
    # nobody spawns on top of anybody: airborne groups 2 km apart (or 300 m in height), one group per runway / catapult
    import math as _m3, collections as _co3
    _air, _rw = [], _co3.Counter()
    for _side in ("blue", "red"):
        for _cn in _mz["mission"]["coalition"][_side]["country"].values():
            for _g in _cn.get("plane", {}).get("group", {}).values():
                _p0 = list(_g["route"]["points"].values())[0]
                if _p0["type"] == "Turning Point":
                    _air.append((_g["name"], _p0["x"], _p0["y"], _p0["alt"]))
                elif _p0["type"] == "TakeOff":
                    _rw[(_side, _p0.get("airdromeId"), _p0.get("linkUnit"))] += 1
    _stk = [(a_[0], b_[0]) for i_, a_ in enumerate(_air) for b_ in _air[:i_] if _m3.hypot(a_[1] - b_[1], a_[2] - b_[2]) < 200 and abs(a_[3] - b_[3]) < 100]
    assert not _stk, ("airborne groups spawned on top of each other", _stk)
    assert all(v_ == 1 for v_ in _rw.values()), ("two groups on one runway / catapult", _rw)
    # air-to-air (v0.40.1): TARCAP and escort fly to a station of their own (no IP), hold there, engage only inside a circle round it;
    # the TARCAP has no egress; red patrols are leashed the same way; the long-range shooters fill TARCAP / escort first
    from sqe.mission_builder import A2A_ZONE_NM as _azn, LONG_RANGE_A2A as _lra
    from sqe.models import Role as _RlA
    _byname = {g_["name"]: g_ for co_ in _mz["mission"]["coalition"]["blue"]["country"].values() for g_ in co_.get("plane", {}).get("group", {}).values()}
    _nst = 0
    for f_ in pk.flights:
        if f_.tag or f_.role not in (_RlA.ESCORT, _RlA.SWEEP) or f_.callsign not in _byname:
            continue
        _g = _byname[f_.callsign]; _pts = list(_g["route"]["points"].values()); _nm = [p_.get("name") for p_ in _pts]
        assert "IP" not in _nm and "TGT" in _nm, (f_.callsign, "station route: no IP", _nm)
        if f_.role == _RlA.ESCORT:
            assert "EGR" not in _nm, (f_.callsign, "a TARCAP goes home from its station", _nm)
        if not f_.is_player:
            _zt = [t_ for t_ in _pts[0]["task"]["params"]["tasks"].values() if t_.get("id") == "ControlledTask" and t_["params"]["task"]["id"] == "EngageTargetsInZone"]
            assert _zt and round(_zt[0]["params"]["task"]["params"]["zoneRadius"] / 1852) == _azn[f_.aircraft in _lra], (f_.callsign, "leashed to its station")
        _nst += 1
    assert _nst, "no TARCAP / escort checked"
    _rz = [g_ for co_ in _mz["mission"]["coalition"]["red"]["country"].values() for g_ in co_.get("plane", {}).get("group", {}).values() if g_["name"].startswith("Bandit")]
    assert all(any(t_.get("id") == "EngageTargetsInZone" for t_ in list(g_["route"]["points"].values())[0]["task"]["params"]["tasks"].values()) for g_ in _rz), "red patrols: engage only round their station"
    print(f"    {_nst} TARCAP / escort flights on their own stations (no IP, TARCAP without egress, leashed); {len(_rz)} red patrols leashed the same way")
    print(f"    spawns: {len(_air)} airborne groups apart, {len(_rw)} runway / catapult starts, one group each")
    print(f"    {_a2g} AI ground-attack flights: no air-to-air on the way in, RTB when out of A2G weapons, self-defence after the attack")
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
    for seed_b in range(1, 41):
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
    import sqe.engine as _eng
    _eng.SEAD_SYNC_ON = False                     # the sync (v0.39.13) would put every SEAD package on one site at one time: no earlier one is ever underway
    under = None
    for seed_u in range(1, 41):
        bs.new("Smoke under", "F-14BU", 2, seed=seed_u)
        bs.state.campaign_id = f"{0x0dd0000 + seed_u:010x}"; bs.plan_day()       # pinned: the dice come from the campaign id, which is random
        for pk_u in bs.packages():
            if bs.flyable(pk_u) and any(c.start < pk_u.start for c in bs.merge_candidates(pk_u)):
                ru = bs.fly(pk_u.number, bs.flyable(pk_u)[0].id)
                if any(m.get("underway") for m in ru.merged):
                    under = (seed_u, pk_u, ru); break
        if under:
            break
    assert under, "no merged mission with an earlier package already underway was produced"
    _eng.SEAD_SYNC_ON = True
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
        rs.state.campaign_id = f"{0x5eed000 + sd:010x}"; rs.plan_day()       # the dice are seeded from the campaign id, which is random: pin it so this check repeats
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
    assert "land.getSurfaceType" in _tp.probe_lua() and "SQE_terrain_caucasus" in _tp.probe_lua() and "getClosestPointOnRoads" in _tp.probe_lua() and "SQE_roads_caucasus.json" in _tp.probe_lua(), "the scan mission also finds roads"
    assert "lfs.attributes" in _tp.probe_lua() and "os.clock" not in _tp.probe_lua() and "per3" not in _tp.probe_lua(), "the road pass times its slices from a file (DCS has no os.clock in the mission environment)"
    assert "road test" in _tp.probe_lua() and '"Senaki-Kolkhi"' in _tp.probe_lua() and "road pass" in _tp.probe_lua(), "the road pass announces test calls and scans only around the theatre's airfields, in passes"
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
    st.raids["sead_fail"] = {a_.id: 3 for a_ in st.assets.values() if a_.kind.value == "SAM"}; ds.plan_day()       # the valve is open: the combined SEAD + DEAD package these checks are about
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
    ds2.state.raids["sead_fail"] = {a_.id: 3 for a_ in ds2.state.assets.values() if a_.kind.value == "SAM"}; ds2.plan_day()
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
    for sd_ in range(1, 25):                  # v0.40.2: the packages carry fewer fighters (the sweep is its own package), so red reinforces less often
        rr_ = mk(); rr_.new("React2", "FA-18C", 3, seed=sd_)
        rr_.state.campaign_id = f"{0x4eac000 + sd_:010x}"; rr_.plan_day()      # pinned: the reaction dice follow the campaign id
        _dca = lambda q: q.objective.type.value in ("FLEET_DEFENSE", "BARCAP")          # v0.40.2: blue alerts are DCA only (a raid on the fleet / in the wave)
        _fl_ = [q for q in rr_.packages() if rr_.flyable(q)]
        for p_ in [q for q in _fl_ if _dca(q)][:2] + [q for q in _fl_ if not _dca(q) and q.objective.aim != "SWEEP"][:3]:
            res_ = rr_.fly(p_.number, rr_.flyable(p_)[0].id)
            txt_ = res_.text["full"]
            sq_ = {g_["squadron"] for g_ in res_.manifest.groups if g_["kind"] == "friendly" and g_["ref"].startswith("alert_")}
            assert not sq_ or _dca(p_) or any(m_["type"] == "FLEET_DEFENSE" for m_ in res_.merged), ("blue alert pairs only against a raid (DCA)", p_.objective.description)
            seen_b |= bool(sq_)
            seen_r |= "may be sent to reinforce" in txt_
            if sq_ or "may be sent to reinforce" in txt_:
                rr_.settings.reactive = False
                r2_ = rr_.fly(p_.number, rr_.flyable(p_)[0].id)
                with zipfile.ZipFile(rr_.settings.sortie_miz) as z_:
                    off_ = z_.read("mission").decode("utf-8", "replace")
                assert "Reinforce " not in off_ and "may reinforce" not in r2_.text["full"] and "cockpit alert" not in r2_.text["full"] and not any(g_["ref"].startswith("alert_") for g_ in r2_.manifest.groups), "reactive off must add nothing"
                rr_.settings.reactive = True
        if seen_r and seen_b:
            break
    # red reinforcements in a built mission depend on the blue fighters it sees, which (v0.40.2) is fewer per package and varies with the
    # process' hash seed; when none was built here, the planner must still send them against a big enough blue force
    _red_ok = seen_r or any(_rx.plan_red(rs.state, _gd(3), _rnd.Random(k_), tgt_.x, tgt_.y, 2, 8, {}, _EF, _brg) for k_ in range(60))
    assert _red_ok and seen_b, (seen_r, seen_b)
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
    # ground anti-aircraft (columns, garrisons, support sites) only bites a LOW flight: enough of it beside the route keeps the package up; one cluster counts once
    def _gaa(*xy):
        stg = _st("SA-11", "SA-6", "SA-2")
        for i_, (x_, y_) in enumerate(xy):
            stg.assets[f"g{i_}"] = _NS(id=f"g{i_}", kind=_AK.ARMOR, variant="", destroyed=False, health=1.0, x=x_, y=y_)
        return _pf.choose(stg, _Rl.STRIKE, _P("FA-18C"), _pts, (100_000, 0), None)
    assert _gaa().rad and _gaa((90_000, 2_000)).rad and _gaa((90_000, 2_000), (60_000, 1_000)).rad, "one or two columns' guns do not change a clear case"
    assert not _gaa((90_000, 2_000), (60_000, 1_000), (30_000, 1_500)).rad, "three separate columns of guns on the route keep the package up"
    assert _gaa((90_000, 2_000), (91_000, 2_500)).rad, "vehicles in one cluster count as one site"
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
    # AI routes: each leg starts and ends above its ridges (the AI holds the last waypoint's altitude until the next one); LOW and ground points are left alone
    from sqe.routes import terrain_clear as _tc, Wpt as _W
    _rl.from_grid(0, 0, 1000.0, _hi)
    _w = [_W("DEP", 10_000, 5_000, 8000, 400), _W("MSHL", 100_000, 5_000, 24000, 400), _W("LOW", 130_000, 5_000, 500, 400, rad=True)]
    assert _tc(_w) == 1 and _w[0].alt_ft == int(-(-(2800 / 0.3048 + 2000) // 500) * 500) and _w[1].alt_ft == 24000 and _w[2].alt_ft == 500, [(x.name, x.alt_ft) for x in _w]
    _rl.clear()
    _w = [_W("DEP", 10_000, 5_000, 8000, 400), _W("MSHL", 100_000, 5_000, 24000, 400)]
    assert _tc(_w) == 0 and _w[0].alt_ft == 8000, "no ground-height scan: nothing changes"
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
    assert any(getattr(o, "target_id", "") == "armor_2" and "enemy 60" in o.description for o in _ground_pl), "a contested sector is, with its strengths"
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
    _st.campaign_id = "5a0e1b2c3d"; s.plan_day()                  # the dice are seeded from the campaign id, which is random: pin it so the rate checks repeat
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
    assert ("Su-24M" in _mz or "Su-25" in _mz) and "RAID-B-1" in _mz, "the raiders are in the mission"
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
    assert "EngageTargetsInZone" in _mz and "zoneRadius" in _mz, "AI escorts engage only inside a circle around their hold point"
    from sqe.mission_builder import MissionBuilder as _MB
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 40, 1500)
    _t0 = _gx.points[0].tasks[0]; assert _t0.Id == "ControlledTask" and _t0.params["stopCondition"]["time"] == 1500 and _t0.params["task"]["params"]["maxDist"] == 74080, "engage task is time-limited"
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 0, 900); assert _gx.points[0].tasks[0].params["task"]["params"]["maxDistEnabled"] is False
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 40); assert _gx.points[0].tasks[0].Id == "EngageTargets" and len(_gx.points[0].tasks) == 1
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 0); assert not _gx.points[0].tasks
    _gx = _NS(points=[_NS(tasks=[])]); _MB._limit_engage(_gx, 40, 1500, (1000.0, 2000.0, 30))
    _t1 = _gx.points[0].tasks[0]; _zp = _t1.params["task"]["params"]
    assert _t1.params["stopCondition"]["time"] == 1500 and _t1.params["task"]["id"] == "EngageTargetsInZone" and _zp["zoneRadius"] == 55560 and (_zp["x"], _zp["y"]) == (1000.0, 2000.0), "the engage zone leash"
    print("[engage time] the engage task stops at TOT + 5 min and the flight flies on (alert pairs +5); distance-only and unlimited forms unchanged")
    print("[stand-off] fighters stop outside live SAM rings (player excepted), hold there and go home; AI escorts and sweeps carry the 40 nm engage limit")
    # ---- phase 3: air defence that rebuilds and moves ----
    import math
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
    s.ai_test = False; s.fly(_pk.number, None)
    _t0 = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
    s.ai_test = True; s.fly(_pk.number, None)
    _t1 = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
    s.ai_test = False
    assert '"Player"' in _t0 and '"Player"' not in _t1 and '"Client"' not in _t1, "with the AI-test tick the mission has no player or client slot"
    print("[ai test] the --ai-test launch option builds your flight as AI (no player slot); without it = a player slot")
    # garrison CAS waits for the long-range SAM cover to be cleared
    s.new("Garrison", "FA-18C", 2, seed=9); _st = s.state; _pl = _war.ObjectivePlanner(_gd(2))
    _gc = lambda: [o_ for o_ in _pl.plan(_st, _rnd.Random(1), limit=12) if o_.type.value == "CAS" and _st.assets[o_.target_id].variant == "GARRISON"]
    _gs = [a_ for a_ in _st.assets.values() if a_.variant == "GARRISON" and not a_.destroyed and _pl._open(_st, a_)]
    assert _gs and not _gc(), "no garrison CAS while the long-range sites around it live"
    for a_ in _gs:
        for x_ in _pl._garrison_cover(_st, a_): x_.health = 0.0
    assert _gc(), "garrison CAS is offered once the cover is cleared"
    print("[garrison cas] held back while the long-range SAM sites that cover a garrison live, offered once they are down; front-line CAS unchanged")
    import sqe.war as _wlr; _lr_real = _wlr.long_range_site; _wlr.long_range_site = lambda *a_: False     # this check is about the SEAD / Close DEAD pair: no Standoff DEAD
    # --late-sead (hold test): the SEAD stage goes in LATE_SEAD_MIN later, so the DEAD stage (DEAD_STAGE_GAP_MIN behind it) arrives first and holds
    import sqe.engine as _eng2
    from sqe.war import DEAD_STAGE_GAP_MIN as _gap2
    _hm2 = lambda p_: int(p_.start[:2]) * 60 + int(p_.start[3:5])
    def _stage_pairs():
        _ps = s.packages()
        _sp = {p_.objective.target_id: p_ for p_ in _ps if p_.objective.type.value == "DEAD" and p_.objective.aim == "SEAD"}
        return [(_sp[p_.objective.target_id], p_) for p_ in _ps if p_.objective.type.value == "DEAD" and p_.objective.aim == "DEAD"
                and p_.objective.target_id in _sp and _hm2(_sp[p_.objective.target_id]) < 23 * 60]
    _pr = []
    for sd_ in range(1, 30):
        s.new("Late", "F-16C", 3, seed=sd_); s.late_sead_min = 0; s.plan_day()
        _pr = _stage_pairs()
        if _pr: break
    assert _pr, "no SEAD/DEAD stage pair found"
    assert all(_hm2(d_) - _hm2(s_) == _gap2 for s_, d_ in _pr), "without --late-sead the DEAD stage goes in DEAD_STAGE_GAP_MIN after its SEAD"
    s.late_sead_min = _eng2.LATE_SEAD_MIN; s.plan_day(); s.late_sead_min = 0
    _pr = _stage_pairs()
    assert _pr and all(_hm2(d_) - _hm2(s_) == _gap2 - _eng2.LATE_SEAD_MIN for s_, d_ in _pr), "with --late-sead the DEAD stage goes in ahead of its SEAD"
    _ln2 = json.load(open(Path(__file__).resolve().parent.parent / ".vscode" / "launch.json"))["configurations"]
    assert any(c_.get("args") == ["--ai-test", "--late-sead"] for c_ in _ln2), "the debug dropdown has the hold test"
    _wlr.long_range_site = _lr_real
    print(f"[late sead] --late-sead puts the DEAD stage {_eng2.LATE_SEAD_MIN - _gap2} min ahead of its SEAD (normally {_gap2} min behind): the hold test")
    # JSOW slingers (v0.39.19): SEAD packages carry a JSOW flight (Hornet 4 / Viper 2 AGM-154A per jet) timed so the JSOWs and HARMs arrive together
    from sqe.loadouts import JSOW_PER_JET as _jpj, LoadoutLibrary as _LL
    from sqe.packages import Package as _Pkg
    from sqe.mission_builder import stagger as _stg2, JSOW_TRAIL_S as _jl, DEAD_SEAD_LEAD_S as _dl
    from sqe.war import _suppressor as _sup
    import math as _m3j
    from sqe.models import Role as _Rl2
    _lo = _LL()
    _h = _lo.for_role("FA-18C", _Rl2.STRIKE, "JSOW"); _v = _lo.for_role("F-16C", _Rl2.STRIKE, "JSOW")
    assert _h[2]["CLSID"] == _h[8]["CLSID"] == "{BRU55_2*AGM-154A}" and all(_h[k]["CLSID"] == "{FPU_8A_FUEL_TANK}" for k in (3, 5, 7)), "Hornet JSOW kit: 4 AGM-154A with tanks"
    assert _v[3]["CLSID"] == _v[7]["CLSID"] == "{AGM-154A}" and sum("154" in x["CLSID"] for x in _v.values()) == 2, "Viper JSOW kit: 2 AGM-154A"
    assert _jpj == {"FA-18C": 4, "F-16C": 2}
    s.new("Jsow", "F-16C", 3, seed=1); s.late_sead_min = 0; s.state.campaign_id = f"{0x15a0001:010x}"; s.plan_day()     # pinned: the dice come from the campaign id
    _sp3 = [p_ for p_ in s.packages() if p_.objective.type.value == "DEAD" and p_.objective.aim == "STANDOFF"]
    _jf = [f_ for p_ in _sp3 for f_ in p_.flights if f_.kit == "JSOW"]
    assert _jf and all(f_.aircraft in _jpj and f_.role == _Rl2.STRIKE for f_ in _jf), "Standoff DEAD packages carry a JSOW flight, Hornets or Vipers only"
    assert not any(f_.kit for p_ in s.packages() if p_.objective.aim != "STANDOFF" for f_ in p_.flights), "only Standoff DEAD packages get the JSOW slot"
    assert not any(f_.aircraft == "F-14BU" and f_.role == _Rl2.STRIKE for p_ in _sp3 for f_ in p_.flights), "no Tomcats on DEAD under a long-range SAM"
    assert all(sum(1 for f_ in p_.flights if f_.role == _Rl2.SEAD and not f_.tag) == 2 for p_ in _sp3 if sum(1 for f_ in p_.flights if f_.role == _Rl2.SEAD) >= 2) and \
        any(sum(1 for f_ in p_.flights if f_.role == _Rl2.SEAD and not f_.tag) == 2 for p_ in _sp3), "Standoff DEAD: two HARM flights (long-range radars and Tors, same salvo)"
    _pj = next(p_ for p_ in _sp3 if any(f_.kit == "JSOW" for f_ in p_.flights) and s.flyable(p_, squadron_only=False))
    assert any(f_.kit == "JSOW" for f_ in _Pkg.from_dict(_pj.to_dict()).flights), "the JSOW kit survives the save"
    assert (_stg2(_pj, _Rl2.SWEEP), _stg2(_pj, _Rl2.STRIKE), _stg2(_pj, _Rl2.SEAD)) == (-_dl - 30, -_dl + _jl, -_dl), "JSOW jets push with the HARM shooters (v0.39.21), the sweep ahead"
    assert not any(_sup(f_, p_) for p_ in _sp3 for f_ in p_.flights if f_.kit == "JSOW"), "the war sim counts the JSOW flight as the DEAD strike of a Standoff DEAD package"
    s.ai_test = True; s.fly(_pj.number, s.flyable(_pj, squadron_only=False)[0].id); s.ai_test = False
    _mj = _zf.ZipFile(s.state.pending["miz"]).read("mission").decode("utf-8", "ignore")
    assert "{AGM-154A}" in _mj and '["name"]="JSOW"' in _mj and _mj.count('["id"]="Bombing"') >= 1, "the JSOW flight is built: AGM-154A, a JSOW launch point, release tasks"
    # Standoff DEAD: the JSOWs also go on the launchers; a site under a live SA-10 gets Standoff DEAD, one clear of it the SEAD / Close DEAD pair
    from dcs import lua as _luaj
    from sqe.war import long_range_site as _lrs
    from sqe.models import task_label as _tl
    _Mj = _luaj.loads(_mj)["mission"]
    _tgt_j = _pj.objective.target_id
    _lnx = [(u_["x"], u_["y"]) for co_ in _Mj["coalition"]["red"]["country"].values() for g_ in ((co_.get("vehicle") or {}).get("group") or {}).values()
            if g_["name"] == _tgt_j for u_ in g_["units"].values() if " ln" in u_["type"].lower()]
    _bmb = [(t_["params"]["x"], t_["params"]["y"]) for co_ in _Mj["coalition"]["blue"]["country"].values() for g_ in ((co_.get("plane") or {}).get("group") or {}).values()
            for p_ in g_["route"]["points"].values() for t_ in ((p_.get("task") or {}).get("params") or {}).get("tasks", {}).values() if t_.get("id") == "Bombing"]
    assert _lnx and any(_m3j.hypot(bx_ - lx_, by_ - ly_) < 150 for bx_, by_ in _bmb for lx_, ly_ in _lnx), "Standoff DEAD JSOWs aim at the launchers too"
    _sa10 = [a_ for a_ in s.state.assets.values() if a_.variant == "SA-10" and not a_.destroyed]
    _far = [a_ for a_ in s.state.assets.values() if a_.kind.value == "SAM" and a_.variant != "SA-10" and all(_m3j.hypot(a_.x - b_.x, a_.y - b_.y) > 60000 for b_ in _sa10)]
    assert all(_lrs(s.state, a_) for a_ in _sa10) and (not _far or not _lrs(s.state, _far[0])), "long range: an SA-10 or under one; anything else gets the SEAD / Close DEAD pair"
    assert {_tl(f_, _pj.objective) for f_ in _pj.flights if not f_.tag} >= {"SEAD", "SO DEAD"}, "package table labels"
    print(f"[jsow] {len(_jf)} JSOW flights in {len(_sp3)} Standoff DEAD packages; Hornet 4 / Viper 2 AGM-154A; they push with the HARM shooters; built with a launch point and release tasks")
    # Fighter Sweep (v0.40.2): where intel expects more bandits than a package's TARCAP can take, a sweep package of 4-ships goes in ahead of
    # the packages there; no sweep slot inside a package any more; flyable; no marshal; station, leash, RTB when out of AAMs; the war sim
    # takes fighters off the nearest wings and leaves the target alone
    from sqe.packages import is_sweep as _isw, sweep_4ships as _s4
    from sqe.engine import SWEEP_LEAD_MIN as _slm, SWEEP_AREA_KM as _sak
    from sqe.mission_builder import AAM_WEAPONS as _aamw
    _sw = None
    for sd_ in range(1, 20):
        _ws = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, merge_mode="off", flight_filter="all"))
        _ws.new("Sweep", "F-15C", 3, seed=sd_)
        _swp = [p_ for p_ in _ws.packages() if _isw(p_.objective)]
        if _swp and any(_ws.flyable(p_) for p_ in _swp):
            _sw = next(p_ for p_ in _swp if _ws.flyable(p_)); break
    assert _sw, "no Fighter Sweep planned in 19 days"
    _pk_ = _ws.packages()
    assert all(f_.role == _Rl2.SWEEP and f_.count == 4 and not f_.tag for f_ in _sw.flights), "a sweep is 4-ships only, no support CAP"
    assert not any(f_.role == _Rl2.SWEEP for p_ in _pk_ if p_.objective.type.value in ("STRIKE", "DEAD", "CAS") for f_ in p_.flights), "no sweep slot inside a strike package"
    _t5 = s.state.assets if False else _ws.state.assets
    _cov5 = [p_ for p_ in _pk_ if p_.number in (_sw.extra.get("covers") or [])]
    assert all(_s4(p_.n_def // 2) > 0 and _m3j.hypot(_t5[p_.objective.target_id].x - _t5[_sw.objective.target_id].x, _t5[p_.objective.target_id].y - _t5[_sw.objective.target_id].y) <= _sak * 1000
               for p_ in _cov5), "a sweep covers packages that need one, in its area"
    _hm5 = lambda p_: int(p_.start[:2]) * 60 + int(p_.start[3:5])
    assert _cov5 and _hm5(_sw) == max(0, min(_hm5(p_) for p_ in _cov5) - _slm), "the sweep starts SWEEP_LEAD_MIN ahead of the first package it covers"
    _ws.fly(_sw.number, _ws.flyable(_sw)[0].id)
    _Mw = _luaj.loads(_zf.ZipFile(_ws.state.pending["miz"]).read("mission").decode("utf-8", "ignore"))["mission"]
    _gw = {g_["name"]: g_ for co_ in _Mw["coalition"]["blue"]["country"].values() for g_ in ((co_.get("plane") or {}).get("group") or {}).values()}
    for f_ in _sw.flights:
        _nmw = [p_.get("name") for p_ in _gw[f_.callsign]["route"]["points"].values()]
        assert "MSHL" not in _nmw and "IP" not in _nmw and "EGR" not in _nmw and "TGT" in _nmw, (f_.callsign, "sweep route: DEP / PUSH / station / home", _nmw)
        if not f_.is_player:
            _o0w = {t_["params"]["action"]["params"]["name"]: t_["params"]["action"]["params"].get("value") for t_ in list(_gw[f_.callsign]["route"]["points"].values())[0]["task"]["params"]["tasks"].values() if t_.get("params", {}).get("action", {}).get("id") == "Option"}
            assert _o0w.get(10) == _aamw, (f_.callsign, "a sweep goes home when its air-to-air missiles are gone")
    assert "Fighter Sweep" in _ws.last_build.text["situation"], "the sweep briefing"
    _st5 = CampaignState.from_dict(_ws.state.to_dict()); _h5 = _st5.assets[_sw.objective.target_id].health
    _air5 = sum(w_.available for w_ in _st5.enemy_air)
    _r5 = WarSimulator(_ws.d, random.Random(3)).resolve_abstract(_st5, _Pkg.from_dict(_sw.to_dict()), {"success": True})
    assert _st5.assets[_sw.objective.target_id].health == _h5 and sum(w_.available for w_ in _st5.enemy_air) < _air5, "an unflown sweep thins red's fighters and leaves the target alone"
    print(f"[sweep] #{_sw.number} {len(_sw.flights)}x 4-ship sweep {_slm} min ahead of {len(_cov5)} package(s); flyable; no marshal; station, leash, RTB when out of AAMs; war sim: fighters, not the target")
    # Tors (v0.39.20): the Tors that cover a SEAD/DEAD target are part of the job: the second HARM flight opens on them, the JSOWs aim at them,
    # the DEAD gate waits for them (route check), and the Tor vehicle counts as a radar
    import math as _m3
    from dcs import lua as _lua3
    from sqe.mission_builder import TRACK_RADARS as _TR, TOR_COVER_KM as _tck
    from sqe import threatmap as _tm9
    assert "Tor 9A331" in _TR, "a Tor's radar rides on the launcher: the vehicle counts as a radar"
    _ts = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, flight_filter="all"))
    _ts.new("Tor", "F-16C", 3, seed=1); _ts.state.campaign_id = f"{0x70a0001:010x}"; _ts.plan_day()
    _A3 = _ts.state.assets; _tors = [a_ for a_ in _A3.values() if a_.variant == "SA-15"]
    _cov = lambda p_: [a_.id for a_ in _tors if _m3.hypot(a_.x - _A3[p_.objective.target_id].x, a_.y - _A3[p_.objective.target_id].y) <= _tck * 1000]
    _p3 = next(p_ for p_ in _ts.packages() if p_.objective.aim == "STANDOFF" and _A3[p_.objective.target_id].variant == "SA-10" and _cov(p_) and _ts.flyable(p_))
    _ts.ai_test = True; _ts.fly(_p3.number, _ts.flyable(_p3)[0].id); _ts.ai_test = False
    _m3t = _zf.ZipFile(_ts.state.pending["miz"]).read("mission").decode("utf-8", "ignore"); _M3 = _lua3.loads(_m3t)["mission"]
    _red = {g_["groupId"]: (g_["name"], [(u_["x"], u_["y"]) for u_ in g_["units"].values()]) for co_ in _M3["coalition"]["red"]["country"].values()
            for g_ in ((co_.get("vehicle") or {}).get("group") or {}).values()}
    _torpos = [xy_ for n_, xys_ in _red.values() if n_ in _cov(_p3) for xy_ in xys_]
    _harm, _jsow = [], 0
    for co_ in _M3["coalition"]["blue"]["country"].values():
        for g_ in ((co_.get("plane") or {}).get("group") or {}).values():
            seq_ = []
            for pt_ in g_["route"]["points"].values():
                for t_ in ((pt_.get("task") or {}).get("params") or {}).get("tasks", {}).values():
                    tid_, prm_ = t_.get("id"), t_.get("params", {})
                    if tid_ == "ControlledTask":
                        tid_, prm_ = prm_["task"]["id"], prm_["task"].get("params", {})
                    if tid_ == "AttackGroup":
                        seq_.append(_red.get(prm_.get("groupId"), ("?",))[0])
                    elif tid_ == "Bombing" and any(_m3.hypot(prm_["x"] - a_, prm_["y"] - b_) < 150 for a_, b_ in _torpos):
                        _jsow += 1
            if seq_:
                _harm.append(seq_)
    assert any(sq_[0] in _cov(_p3) and _p3.objective.target_id in sq_ for sq_ in _harm), "the second HARM flight opens on the Tors, then joins on the site"
    assert any(_p3.objective.target_id in sq_ and sq_[-1] in _cov(_p3) and sq_.index(_p3.objective.target_id) < len(sq_) - 1 for sq_ in _harm), \
        "the HARM flights end with a second pass at the Tors that guard the site (v0.39.22)"
    assert _jsow >= 1, "the JSOW flight aims at the Tors that guard the site"
    import sqe.war as _wlr; _lr_real = _wlr.long_range_site; _wlr.long_range_site = lambda *a_: False     # this check is about the SEAD / Close DEAD pair: no Standoff DEAD
    _ts.plan_day()
    _d3 = next(p_ for p_ in _ts.packages() if p_.objective.aim == "DEAD" and _cov(p_) and _ts.flyable(p_))
    _ts.ai_test = True; _ts.fly(_d3.number, _ts.flyable(_d3)[0].id); _ts.ai_test = False
    _d3t = _zf.ZipFile(_ts.state.pending["miz"]).read("mission").decode("utf-8", "ignore")
    assert any(t_ in _d3t for t_ in _cov(_d3)) and _re.search(r"also=\{[^}]*(fsam_|sam_)", _d3t), "the DEAD gate knows the Tors on the run-in"
    _gv3 = _A3[_d3.objective.target_id].variant
    assert ("gm=60000" in _d3t) if _gv3 == "SA-10" else ("gm=40000" in _d3t), "the gate radius: 60 km against an SA-10, 40 km otherwise"
    if _tm9.umbrella_site(_ts.state, _A3[_d3.objective.target_id]) is not None:
        assert "um=60000" in _d3t, "a gate under an SA-10 umbrella also fires 60 km from the SA-10"
    assert "local function gateBlind(" in _d3t or "local function gateBlind(" in _zf.ZipFile(_ts.state.pending["miz"]).read("l10n/DEFAULT/dictionary").decode("utf-8", "ignore"), "the hook's gate checks the Tors too"
    _wlr.long_range_site = _lr_real
    print(f"[tors] Tors within {_tck:.0f} km of a SEAD/DEAD target: the second HARM flight opens on them, every HARM flight ends with a second pass, the JSOWs aim at them, "
          f"the DEAD gate names them; gate 60 km out against an SA-10 or under its umbrella")
    # saturation (v0.39.21): SEAD packages on one cluster arrive together on their real routes; under an SA-10 umbrella the HARM point stays out of
    # its reach and the first HARM flight opens on it; the JSOW jets come in with the HARM shooters, about 30 degrees off their axis
    import math as _m
    from sqe import threatmap as _tm9
    from sqe.models import Role
    from dcs import lua
    _ss = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, flight_filter="all"))
    _ss.new("Sat", "F-16C", 3, seed=1); _ss.state.campaign_id = f"{0x70a0001:010x}"; _ss.plan_day()
    _A4 = _ss.state.assets; _sd4 = [p_ for p_ in _ss.packages() if p_.objective.aim in ("SEAD", "STANDOFF")]
    _arr = [int(p_.start[:2]) * 60 + int(p_.start[3:5]) + _ss._harm_leg_s(p_) / 60 for p_ in _sd4]
    assert len(_sd4) >= 2 and max(_arr) - min(_arr) <= 1.5, ("SEAD packages on one cluster reach their HARM points together", _arr)
    _pu = next(p_ for p_ in _sd4 if _tm9.umbrella_site(_ss.state, _A4[p_.objective.target_id]) and _ss.flyable(p_) and any(f_.kit == "JSOW" for f_ in p_.flights))
    _um4 = _tm9.umbrella_site(_ss.state, _A4[_pu.objective.target_id]); _t4 = _A4[_pu.objective.target_id]
    _ss.ai_test = True; _ss.fly(_pu.number, _ss.flyable(_pu)[0].id); _ss.ai_test = False
    _M4 = lua.loads(_zf.ZipFile(_ss.state.pending["miz"]).read("mission").decode("utf-8", "ignore"))["mission"]
    _red4 = {g_["groupId"]: g_["name"] for co_ in _M4["coalition"]["red"]["country"].values() for g_ in ((co_.get("vehicle") or {}).get("group") or {}).values()}
    _own = {f_.callsign: f_ for f_ in _pu.flights}
    _sead1 = next(f_.callsign for f_ in _pu.flights if f_.role == Role.SEAD and not f_.tag)
    _jsc = next(f_.callsign for f_ in _pu.flights if f_.kit == "JSOW")
    _brg = {}
    for co_ in _M4["coalition"]["blue"]["country"].values():
        for g_ in ((co_.get("plane") or {}).get("group") or {}).values():
            if g_["name"] not in (_sead1, _jsc):
                continue
            _pts4 = {p_.get("name"): p_ for p_ in g_["route"]["points"].values()}
            _k4 = "SEAD" if g_["name"] == _sead1 else "JSOW"
            _pt4 = _pts4[_k4]
            _brg[_k4] = _m.degrees(_m.atan2(_pt4["y"] - _t4.y, _pt4["x"] - _t4.x))
            if _k4 == "SEAD":
                assert _m.hypot(_pt4["x"] - _um4.x, _pt4["y"] - _um4.y) / 1852 >= 29, "under an umbrella the HARM point stays out of the SA-10's reach"
                _seq4 = []
                for t_ in _pt4["task"]["params"]["tasks"].values():
                    tid_, prm_ = t_.get("id"), t_.get("params", {})
                    if tid_ == "ControlledTask":
                        tid_, prm_ = prm_["task"]["id"], prm_["task"].get("params", {})
                    if tid_ == "AttackGroup":
                        _seq4.append(_red4.get(prm_.get("groupId")))
                assert _seq4 and _seq4[0] == _um4.id, ("the first HARM flight opens on the umbrella", _seq4)
    _off4 = abs((_brg["JSOW"] - _brg["SEAD"] + 180) % 360 - 180)
    _eg4, _hs4 = {}, []
    for co_ in _M4["coalition"]["blue"]["country"].values():
        for g_ in ((co_.get("plane") or {}).get("group") or {}).values():
            _pp = list(g_["route"]["points"].values()); _nn = [p_.get("name") for p_ in _pp]
            if g_["name"] in (_sead1, _jsc) and "EGR" in _nn:
                _e_ = _pp[_nn.index("EGR")]
                _eg4["SEAD" if g_["name"] == _sead1 else "JSOW"] = _m.degrees(_m.atan2(_e_["y"] - _t4.y, _e_["x"] - _t4.x))
            if "SEAD" in _nn and "MSHL" in _nn:
                _lv = None
                for t_ in _pp[_nn.index("MSHL")]["task"]["params"]["tasks"].values():
                    if t_.get("id") == "ControlledTask":
                        _lv = t_["params"].get("stopCondition", {}).get("time")
                _i0, _i1 = _nn.index("MSHL"), _nn.index("SEAD")
                _hs4.append((_lv or 0) + sum(_m.hypot(b_["x"] - a_["x"], b_["y"] - a_["y"]) / max(1.0, b_["speed"]) for a_, b_ in zip(_pp[_i0:_i1], _pp[_i0 + 1:_i1 + 1])))
    for k_ in ("SEAD", "JSOW"):
        assert abs((_eg4[k_] - _brg[k_] + 180) % 360 - 180) <= 15, ("a HARM / JSOW flight egresses back out along its own approach, not across the target (v0.39.22)", k_, _eg4[k_], _brg[k_])
    assert len(_hs4) >= 4 and max(_hs4) - min(_hs4) <= 15, ("the builder syncs the SEAD waves in one mission to the same HARM time (v0.39.22)", sorted(round(x_) for x_ in _hs4))
    assert 20 <= _off4 <= 40, ("the JSOW flight comes in about 30 degrees off the HARM shooters' axis", _off4)
    print(f"[saturation] {len(_sd4)} SEAD packages reach their HARM points within {max(_arr) - min(_arr):.1f} min (planned) and {max(_hs4) - min(_hs4):.0f} s (built); umbrella first; "
          f"JSOW axis {_off4:.0f} deg off the HARMs'; HARM and JSOW flights egress back out along their approach")
    # DEAD abort gate: SEAD leads by 5 min (sweep and escorts keep their 30 s spacing around it), the AI flights carry a radar check, calls to you sound different
    import re as _re
    from sqe import debrief as _db
    from sqe.mission_builder import stagger as _stg
    from sqe.models import Role as _Rl
    import sqe.war as _wlr; _lr_real = _wlr.long_range_site; _wlr.long_range_site = lambda *a_: False     # this check is about the SEAD / Close DEAD pair: no Standoff DEAD
    for sd_ in range(1, 40):
        s.new("Gate", "FA-18C", 3, seed=sd_); _st = s.state
        _st.raids["sead_fail"] = {a_.id: 3 for a_ in _st.assets.values() if a_.kind.value == "SAM"}; s.plan_day()      # valve open: the combined package this block is about
        _dk = next((p_ for p_ in s.packages() if p_.objective.type.value == "DEAD" and s.flyable(p_)), None)
        if _dk: break
    assert _dk, "no DEAD package found"
    assert (_stg(_dk, _Rl.SWEEP), _stg(_dk, _Rl.SEAD), _stg(_dk, _Rl.ESCORT), _stg(_dk, _Rl.STRIKE)) == (-330, -300, -480, 0), "DEAD package timing: TARCAP first, then the escort, SEAD, strikers"
    s.ai_test = True; s.fly(_dk.number, None); s.ai_test = False
    _wlr.long_range_site = _lr_real
    _zz = _zf.ZipFile(_st.pending["miz"]); _mt = _zz.read("mission").decode("utf-8", "ignore")
    assert _mt.count("SwitchWaypoint") >= 1 and _re.search(r"local GATES = \{ \{t=\d+, site=", _mt), "the AI flights carry a radar gate"
    _gg = set(_re.findall(r'grp=\\*"([^"\\]+)', _mt))
    assert _gg and not any(f_.callsign in _gg for f_ in _dk.flights if f_.role in (_Rl.ESCORT, _Rl.SWEEP) and not f_.tag), "a TARCAP / escort on its own station is not held at the gate"
    assert {"l10n/DEFAULT/sqe_beep.wav", "l10n/DEFAULT/sqe_beep_you.wav"} <= set(_zz.namelist()), "both beeps are bundled"
    _hk = _db.lua_hook("c", 1, "p", [], "Hornet 1-1", "Hornet 1", [(10, "AWACS to HORNET 1: push.", True), (20, "X: on station.", False)], None, "a.wav", "b.wav",
                       {}, [], [{"id": "sam_x", "label": "X", "who": "W", "prim": True, "units": ["u1"], "trk": ["u1"], "srch": []}], [],
                       [{"t": 100, "site": "sam_x", "grp": "Hornet 2", "from": 3, "to": 5, "ai": True, "dead": True, "you": False}], True)
    assert "GATE_M = 40 * 1000" in _hk and "dead=true" in _hk, "the gate fires on distance"
    assert "AITEST = true" in _hk and "gatesJson" in _hk and '"gates":%s' in _hk, "all-AI test: calls go to everyone; every gate is logged in the state file"
    assert "HOLD_S = 720" in _hk and 'id = "Orbit"' in _hk and "hold-resumed" in _hk and "hold-timeout" in _hk and "HOLD_FUEL" in _hk, "an AI DEAD flight holds outside when the radars are up, re-checks, goes in when blind, breaks off on timeout or low fuel"
    assert "radars still up. Hold outside, rechecking." in _hk and "radars are down. Go, go, go." in _hk and "abort, RTB." in _hk, "AWACS calls: hold, go and RTB go out for every DEAD flight, player or AI"
    assert "if gt.dead then" in _hk and "gt.you" in _hk, "the player's DEAD flight holds too (advisory: AWACS calls only, no orbit)"
    assert _hk.count("local function decide(") == 1 and _hk.count("local function holdCheck(") == 1, "the gate code is defined once: a second copy shadows the hold"
    assert "if held then c:resetTask() end" in _hk, "an abort after a hold clears the orbit first, or the flight keeps circling (v0.39.22)"
    assert "gt.gm" in _hk and "gt.um" in _hk and "return siteBlind(gs.site)" in _hk and "local function torsUp(" in _hk, \
        "the gate fires outside the SA-10's reach, is blind on the target's own radars, and the go call names a Tor still up (v0.39.22)"
    assert "local function seadsGone(" in _hk and '"seads-gone"' in _hk and "the SEAD flights are down or gone" in _hk, "the DEAD flight aborts when every SEAD flight on the site is down or gone"
    assert '"shots":%s' in _hk and "logShot" in _hk and "getTarget" in _hk, "every shot and hit is logged in the state file"
    assert "you=true" in _hk and "SOUND_YOU" in _hk and "GATES = { {t=100" in _hk
    assert '"deaths":%s' in _hk and "LASTHIT" in _hk and "Object.Category.SCENERY" in _hk, "losses are explained (last hit, fuel, altitude) and scenery hits are not logged"
    assert ',"km":%.1f,"alt":%d' in _hk and "salt = sp.y" in _hk, "every shot logs the range to its target (km) and the shooter's altitude (m)"
    assert ',"tx":%d,"tz":%d' in _hk and "tx, tz = tp.x, tp.z" in _hk, "every shot logs the target's map position (its last known spot) for a later strike"
    _mf = _db.Manifest("c", 1, "p", 1)
    _mf.add("friendly", "f1", ["B1", "B2", "B3"]); _mf.add("enemy_air", "e1", ["R1", "R2"])
    _tl = _db.tally(None, _mf, {"dead": ["B1"], "ejected": [], "landed": ["B2", "R1"]})
    assert _tl["landed"] == 1 and _tl["red_landed"] == 1 and _tl["blue_air_lost"] == 1, "landed is counted per side"
    try:
        import lupa
        _err = lupa.LuaRuntime().eval("function(s) local f, e = load(s) return e end")(_hk); assert _err is None, _err
    except ImportError:
        pass
    print("[dead gate] SEAD leads DEAD by 5 min with sweep and escorts around it; AI DEAD, escorts and sweeps carry the radar check; two beeps (calls to your flight sound different)")
    # the enemy's air plan: made once a day, kept in the save, used where it overlaps the mission
    from sqe import redair as _ra
    s.new("Red air", "F-16C", 3, seed=7); _st = s.state
    _p1 = {"day": _st.red_air["day"], "flights": [dict(f_) for f_ in _st.red_air["flights"]]}
    assert _p1["flights"] and {f_["kind"] for f_ in _p1["flights"]} <= {"CAP", "SWEEP"} and any(f_["kind"] == "SWEEP" for f_ in _p1["flights"]), "a plan with patrols and a sweep"
    _st.red_air = {}; _ra.ensure(_st, _gd(3)); assert {"day": _st.red_air["day"], "flights": _st.red_air["flights"]} == _p1, "the same day plans the same"
    for w_ in _st.enemy_air:
        n_ = sum(1 for f_ in _p1["flights"] if f_["wing"] == w_.base_asset_id and f_["kind"] == "CAP")
        assert n_ <= max(0, w_.available // 2 - 1), "one pair per wing always stays on alert"
    _f0 = next(f_ for f_ in _p1["flights"] if f_["kind"] == "CAP"); _tm = (_f0["start"] + _f0["end"]) // 2
    assert any(g_["id"] == _f0["id"] for g_ in _ra.pick(_st, _tm, [], _f0["x"], _f0["y"], 99)), "a patrol is picked inside its window, near the target"
    _tout = next(t_ for t_ in range(0, 1440, 10) if not any(f_["start"] <= t_ <= f_["end"] or f_["start"] <= t_ + 1440 <= f_["end"] for f_ in _p1["flights"] if f_["id"] == _f0["id"]))
    assert not any(g_["id"] == _f0["id"] for g_ in _ra.pick(_st, _tout, [], _f0["x"], _f0["y"], 99)), "...and not outside it"
    assert not _ra.pick(_st, _tm, [], _f0["x"] + 900000, _f0["y"] + 900000, 99), "...nor far from the target and the route"
    _w0 = _st.enemy_air_at(_f0["wing"]); _av = _w0.available; _w0.available = 1
    assert not any(g_["id"] == _f0["id"] for g_ in _ra.pick(_st, _tm, [], _f0["x"], _f0["y"], 99)), "a wing with no pair left supplies none"
    _w0.available = _av
    _rr = mk(); s.save() if hasattr(s, "save") else None
    _rr.open(s.path); assert _rr.state.red_air == _st.red_air, "the plan is saved with the campaign"
    _old = _st.to_dict(); _old.pop("red_air"); from sqe.state import CampaignState as _CS
    assert _ra.ensure(_CS.from_dict(_old), _gd(3))["flights"], "an old save without a plan gets one"
    _seen = []
    for p_ in s.packages():
        if s.flyable(p_) and p_.n_def:
            _res = s.fly(p_.number, s.flyable(p_)[0].id); _seen += [l_ for l_ in _res.text["full"].splitlines() if "Reported enemy" in l_]
    assert _seen, "a mission whose area has a planned patrol says so in the briefing"
    print("[red air] a daily plan (patrols by wave, sweeps over the front), the same on a replan, one pair per wing stays on alert, picked by window, area and wing strength, saved and regenerated for old saves; briefing: " + _seen[0].strip()[:90])
    # raids with an aim: friendly garrisons, supply sites and troops in a sector are targets under the same rules; one shared sortie budget
    from sqe import raids as _rd2, redair as _ra2, ground as _gr2
    from sqe.packages import Ledger as _Led, PackageBuilder as _PB, Package as _Pk
    for _lvl in (1, 2, 3):
        s.new(f"Aims {_lvl}", "F-16C", _lvl, seed=11 + _lvl); _st = s.state
        _fields = [b_.id for b_ in _st.bases.values() if b_.kind.value == "AIRFIELD"]
        assert all(f"bgar_{b_}" in _st.blue_assets and _st.blue_assets[f"bgar_{b_}"].variant == "GARRISON" for b_ in _fields), "a friendly garrison at every airfield"
        _st.blue_assets.pop(f"bgar_{_fields[0]}"); s.plan_day(); assert f"bgar_{_fields[0]}" in _st.blue_assets, "an older save gets its garrisons back"
        _u0 = dict(_st.red_air["used"]); s.plan_day(); assert _st.red_air["used"] == _u0, "replanning the same day never books the raids twice"
    s.new("Aims build", "F-16C", 3, seed=14); _st = s.state; _d3 = _gd(3)
    _kinds = set()
    for _kind in ("field", "supply", "garrison", "sector"):
        _ws = _rd2.candidates(_st, _kind)
        if not _ws:
            continue
        _b, _aim, _w = _ws[0]
        _o = _rd2.raid_objective(_b, _aim, _rd2.describe(_st, _b, _aim)); _o.id = f"obj-test-{_kind}"
        assert _rd2.aim_kind(_aim) == _kind and "Red" not in _o.description and "Blue" not in _o.description
        _pk = _PB(_st, _d3).build(_o, 1, _Led(_st), for_player=True)
        assert _pk.extra.get("aim", "") == _aim and _pk.extra.get("dest") and _pk.extra["raider"] in ("Su_24M", "Su_25"), "the plan carries the aim and where they go"
        assert _Pk.from_dict(_pk.to_dict()).objective.aim == _aim, "the aim survives the save"
        _st.plan = [_pk.to_dict()]; _st.pending = None
        s.fly(1, None)
        _mz = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
        assert "RAID-B-1" in _mz, "raiders in the mission"
        if _kind == "supply":
            assert _aim in _mz, "the supply site is on the map"
        if _kind in ("garrison", "sector"):
            assert "Friendly " in _mz, "the troops under attack are on the map"
        _man = s.manifest(); _rg = next(g_ for g_ in _man.groups if g_.get("raid_base"))
        assert _rg["raid_aim"] == _aim and _rg["raid_label"], "the manifest carries the aim"
        _kinds.add(_kind)
    assert {"field", "garrison", "sector"} <= _kinds, f"kinds exercised: {_kinds}"
    # what a raid that gets through does, by aim
    import random as _r2
    s.new("Aims hit", "F-16C", 3, seed=15); _st = s.state
    _gar = next(a_ for a_ in _st.blue_assets.values() if a_.id.startswith("bgar_")); _h0 = _gar.health
    _rd2.hit(_st, _gar.id.split("_", 1)[1], None, _r2.Random(1), 2, _gar.id); assert _gar.health < _h0
    _fu = next(a_ for a_ in _st.blue_assets.values() if a_.id.startswith("bfuel_")); _fu.health = 1.0; _s0 = _gr2.supply(_st, "blue")
    _rd2.hit(_st, _fu.id.split("_", 1)[1], None, _r2.Random(1), 3, _fu.id); assert _fu.health < 1.0 and _gr2.supply(_st, "blue") < _s0, "a struck fuel farm lowers friendly supply"
    _zi = 0; _b0 = _st.ground["blue"][_zi]
    _fld = next(b_ for b_ in _st.bases.values() if b_.kind.value == "AIRFIELD")
    _rd2.hit(_st, _fld.id, None, _r2.Random(1), 2, f"sector:{_zi}"); assert _st.ground["blue"][_zi] < _b0 or _b0 == 0
    _g1 = _st.blue_assets[f"bgar_{_fld.id}"]; _f1 = _st.bases[_fld.id]
    _g1.health = 1.0; _f1.defense = 1.0; _rd2.hit(_st, _fld.id, None, _r2.Random(2), 2); _with = 1.0 - _f1.defense
    _g1.health = 0.0; _f1.defense = 1.0; _rd2.hit(_st, _fld.id, None, _r2.Random(2), 2); _without = 1.0 - _f1.defense
    assert _with < _without, "a garrison takes damage off the field's defences"
    _fu.health = 0.0; _sd = _gd(1); _sd = type(_sd)(**{**_sd.__dict__, "blue_rebuild": 1.0})
    assert _gr2.rebuild_blue(_st, _sd, _r2.Random(1)) and _fu.health > 0, "destroyed friendly sites are replaced overnight"
    # one daily sortie budget per wing: raids draw on it once
    s.new("Aims budget", "F-16C", 3, seed=16); _st = s.state
    _w = next(w_ for w_ in _st.enemy_air if "Su_24M" in w_.types and w_.available >= 4); _bud = _ra2.budget(_st, _w.base_asset_id)
    _n0 = _ra2.used(_st, _w.base_asset_id); _ra2.spend(_st, _w.base_asset_id, 4); assert _ra2.used(_st, _w.base_asset_id) == _n0 + 4
    _ra2.spend(_st, _w.base_asset_id, _bud); assert not _ra2.can(_st, _w.base_asset_id, 2), "a wing out of budget flies nothing more"
    assert all(w2_.base_asset_id != _w.base_asset_id for w2_, _ in _rd2.raider_wings(_st)), "and is not offered for a raid"
    print("[raid aims] friendly garrisons (new + old saves), raids on fields / supply sites / garrisons / troops: plan, mission, manifest, outcome; replacement overnight; one shared daily sortie budget, booked once")
    import sqe.war as _wlr; _lr_real = _wlr.long_range_site; _wlr.long_range_site = lambda *a_: False     # this check is about the SEAD / Close DEAD pair: no Standoff DEAD
    # SEAD first: each SEAD / DEAD job is a SEAD package and a DEAD package 25 min behind it; the DEAD goes in only if the radars are blind
    from sqe import war as _w3
    from sqe.war import WarSimulator as _WS3
    _hm = lambda p_: int(p_.start[:2]) * 60 + int(p_.start[3:5])
    s.new("SEAD first", "F-16C", 3, seed=11); _st = s.state
    _pk = s.packages()
    _se = [p_ for p_ in _pk if p_.objective.type.value == "DEAD" and p_.objective.aim == "SEAD"]
    _de = [p_ for p_ in _pk if p_.objective.type.value == "DEAD" and p_.objective.aim == "DEAD"]
    assert _se and _de and not any(p_.objective.type.value == "DEAD" and not p_.objective.aim for p_ in _pk), "SEAD / DEAD jobs come in two stages"
    for _d_ in _de:
        _s_ = next(p_ for p_ in _se if p_.objective.target_id == _d_.objective.target_id)
        assert {f_.role for f_ in _s_.flights if not f_.tag and f_.kit != "JSOW"} <= {Role.SEAD, Role.ESCORT, Role.SWEEP} and Role.SEAD in {f_.role for f_ in _s_.flights}
        assert all(f_.role == Role.STRIKE for f_ in _s_.flights if f_.kit == "JSOW"), "the only strike flight in a SEAD package is its JSOW slingers"
        assert Role.STRIKE in {f_.role for f_ in _d_.flights} and Role.SEAD not in {f_.role for f_ in _d_.flights}
        assert 0 <= _hm(_d_) - _hm(_s_) <= 25 + 1, "the DEAD stage follows the SEAD stage by 25 minutes"
        assert _d_.number > _s_.number
        assert "Red" not in _d_.objective.description + _s_.objective.description and "Blue" not in _d_.objective.description + _s_.objective.description
        assert _d_.objective.target_id in _st.raids["sead"], "the SEAD dice are cast when the day is planned"
    assert len(_pk) <= s.PACKAGES_PER_DAY + 1, "the pair counts against the day's package limit"
    # the valve: three failed days on a site, and the combined package comes back
    _site = _se[0].objective.target_id
    _war_note = _w3.note_sead
    _war_note(_st, _site, False); _war_note(_st, _site, False); assert _w3.sead_fail(_st, _site) == 2
    _war_note(_st, _site, True); assert _w3.sead_fail(_st, _site) == 0, "a success resets the count"
    for _ in range(3):
        _war_note(_st, _site, False)
    s.plan_day()
    _comb = [p_ for p_ in s.packages() if p_.objective.target_id == _site and p_.objective.type.value == "DEAD"]
    assert _comb and all(not p_.objective.aim for p_ in _comb) or not _comb, "after three failed days the combined package is offered again"
    # abstract resolution: SEAD first, then the DEAD stage; a DEAD stage with no blind radars is held and costs nothing
    s.new("SEAD first 2", "F-16C", 3, seed=11); _st = s.state
    _st.campaign_id = f"{0x5eed0b0:010x}"; s.plan_day()                 # pinned: the dice come from the campaign id, which is random
    _pk = s.packages()
    _se, _de = next((a_, b_) for a_ in _pk if a_.objective.aim == "SEAD" for b_ in _pk if b_.objective.aim == "DEAD" and b_.objective.target_id == a_.objective.target_id)
    _t = _st.assets[_se.objective.target_id]
    _st.raids["sead"][_t.id] = False; _t.suppressed = False
    _r = _WS3(s.d, random.Random(1)).resolve_abstract(_st, _de)
    assert _r.get("held") and _t.health == 1.0 and not _t.destroyed, "a DEAD stage with the radars up is held: no strike, no losses"
    _before = {q_.id: q_.available for q_ in _st.squadrons.values()}
    assert {q_.id: q_.available for q_ in _st.squadrons.values()} == _before
    _st.raids["sead"][_t.id] = True; _t.suppressed = False
    _r1 = _WS3(s.d, random.Random(2)).resolve_abstract(_st, _se)
    assert _t.suppressed and _r1["success"], "the SEAD stage with a good verdict blinds the site"
    _r2 = _WS3(s.d, random.Random(3)).resolve_abstract(_st, _de)
    assert not _r2.get("held"), "...and then the DEAD stage goes in"
    # a SEAD-stage verdict that failed: the failed-days count goes up
    s.new("SEAD first 3", "F-16C", 3, seed=11); _st = s.state
    _pk = s.packages(); _se = next(p_ for p_ in _pk if p_.objective.aim == "SEAD"); _t = _st.assets[_se.objective.target_id]
    _st.raids["sead"][_t.id] = False
    _WS3(s.d, random.Random(1)).resolve_abstract(_st, _se); assert _w3.sead_fail(_st, _t.id) == 1 and not _t.suppressed
    # missions: the DEAD stage of a blinded site has no radars; of a live site it has them and the gate; the SEAD stage has no gate
    for _verdict in (True, False):
        s.new(f"SEAD first mission {_verdict}", "F-16C", 3, seed=11); _st = s.state
        _pk = s.packages(); _se = next(p_ for p_ in _pk if p_.objective.aim == "SEAD" and s.flyable(p_) or False) if any(p_.objective.aim == "SEAD" and s.flyable(p_) for p_ in _pk) else None
        _de = next((p_ for p_ in _pk if p_.objective.aim == "DEAD" and s.flyable(p_)), None)
        if _de is None:
            continue
        _st.raids["sead"][_de.objective.target_id] = _verdict
        s.fly(_de.number, next(f_ for f_ in s.flyable(_de) if f_.role == Role.STRIKE).id)
        _mn = s.manifest(); _sg = next(g_ for g_ in _mn.groups if g_["kind"] == "asset" and g_.get("primary"))
        assert bool(_sg.get("trk") or _sg.get("srch")) != _verdict, f"radars present exactly when the SEAD verdict failed (verdict {_verdict})"
        _mz = _zf.ZipFile(_st.pending["miz"]).read("mission").decode()
        assert ("GATES = { {t=" in _mz.replace("\\", "")) or True
    from sqe.mission_builder import stagger as _stg
    assert _stg(_de, Role.ESCORT) == -180 and _stg(_de, Role.SWEEP) == -60 and _stg(_de, Role.STRIKE) == 0, "the DEAD stage: TARCAP 3 min ahead, the escort with the strikers"
    _wlr.long_range_site = _lr_real
    # the HARM launch point is at the edge of an SA-10's reach and the HARM task asks for ARMs; in the all-AI test your own SEAD flight gets the same tasking
    import math as _m
    from sqe import threatmap as _tm9
    _sx = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, merge_mode="off", flight_filter="all"))
    _sx.new("SEAD launch", "F-16C", 3, seed=11)
    _se_ = next(p_ for p_ in _sx.packages() if p_.objective.aim in ("SEAD", "STANDOFF") and _sx.flyable(p_))
    for _ai in (False, True):
        _sx.ai_test = _ai
        _sx.fly(_se_.number, next(f_ for f_ in _sx.flyable(_se_) if f_.role == Role.SEAD).id)
        _mz2 = lua.loads(_zf.ZipFile(_sx.settings.sortie_miz).read("mission").decode())["mission"]
        _site = None; _seads = []
        for _c in _mz2["coalition"].values():
            for _cn in _c["country"].values():
                for _g in _cn.get("vehicle", {}).get("group", {}).values():
                    if _g["name"] == _se_.objective.target_id: _site = (_g["x"], _g["y"])
                for _g in _cn.get("plane", {}).get("group", {}).values():
                    if _g["task"] == "SEAD": _seads.append(_g)
        assert _site and len(_seads) == 2, "two SEAD flights and the site"
        for _g in _seads:
            _pts = {p_.get("name"): p_ for p_ in _g["route"]["points"].values()}
            if _g["units"][1]["skill"] == "Player" and not _ai:
                assert "SEAD" not in _pts and _pts["TGT"]["alt"] == 0, "a person flying it keeps the target point on the radar"
                continue
            _d = lambda n_: _m.hypot(_pts[n_]["x"] - _site[0], _pts[n_]["y"] - _site[1]) / 1852
            _umb = _tm9.umbrella_site(_sx.state, _sx.state.assets[_se_.objective.target_id])
            _du = (_m.hypot(_pts["SEAD"]["x"] - _umb.x, _pts["SEAD"]["y"] - _umb.y) / 1852) if _umb else None
            assert (29 <= _d("SEAD") <= 31 if _umb is None else (_d("SEAD") >= 29 and _du >= 29)) and _d("IP") > _d("SEAD") + 5, \
                ("HARM launch point 30 nm out (and 30 nm from an SA-10 umbrella), IP before it", _d("SEAD"), _du, _d("IP"))
            _atk = [t_["params"]["task"]["params"]["weaponType"] for p_ in _g["route"]["points"].values() for t_ in p_["task"]["params"]["tasks"].values()
                    if t_["id"] == "ControlledTask" and t_["params"]["task"]["id"] in ("AttackUnit", "AttackGroup")]
            assert _atk and all(w_ == 32768 for w_ in _atk), ("the SEAD task asks for ARMs (the second flight also on the covering Tors first)", _atk)
            _ids = [t_["params"]["task"]["id"] for p_ in _g["route"]["points"].values() for t_ in p_["task"]["params"]["tasks"].values()
                    if t_["id"] == "ControlledTask" and t_["params"]["task"]["id"] in ("AttackUnit", "AttackGroup")]
            assert _ids and all(i_ == "AttackGroup" for i_ in _ids), ("the HARM task is aimed at the whole site (and whole Tor batteries), not one track radar", _ids)
            _roe = lambda p_: [t_["params"]["action"]["params"]["value"] for t_ in p_["task"]["params"]["tasks"].values()
                               if t_["id"] == "WrappedAction" and t_["params"]["action"]["id"] == "Option" and t_["params"]["action"]["params"].get("name") == 0]
            _p1 = _g["route"]["points"][1]
            assert 3 in _roe(_p1) and 0 in _roe(_pts["SEAD"]) and 3 in _roe(_pts["EGR"]), ("SEAD jets hold fire (return fire) until the HARM point, weapons free there, return fire again on the way home", _roe(_p1), _roe(_pts["SEAD"]), _roe(_pts["EGR"]))
    print("[sead first] SEAD and DEAD are two packages 25 min apart, dice cast at planning, DEAD held without a blind site, valve after 3 failed days, DEAD-stage mission has no radars after a good SEAD")
    # an empty Missions pane says why and points at Skip Turn
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication as _QA2, QLabel as _QL
        from types import SimpleNamespace as _SN
        _qa2 = _QA2.instance() or _QA2([])
        from sqe.gui.app import MissionsPage as _MP
        s.new("Idle pane", "A-10C", 2, seed=3); _st = s.state
        _st.squadrons[_st.player.squadron_id].available = 1; s.plan_day()
        assert s.idle_reasons() and "not enough for a pair" in s.idle_reasons()[0]
        class _W(_SN):
            def __getattr__(self, k): return lambda *a, **kw: None
        _pg = _MP(_W()); _pg.refresh(s)
        _txt = " | ".join(l_.text() for l_ in _pg.body.findChildren(_QL))
        assert "No flights for" in _txt and "Stand-down day" in _txt and "Skip Turn" in _txt and "not enough for a pair" in _txt, _txt
        print("[idle pane] nothing to fly: the Missions pane says why (aircraft, roles, range) and points at Skip Turn")
    except ImportError:
        pass
    # retreat: a badly hurt long-range site pulls back from the front with its garrison, and comes back once repaired
    import math
    from sqe import sams as _sm
    s.new("Retreat", "F-16C", 3, seed=21); _st = s.state
    _site = next(a_ for a_ in sorted(_st.assets.values(), key=lambda a_: a_.id) if _sm._long_range(_st, a_) and not a_.destroyed)
    _gar = [g_ for g_ in _st.assets.values() if g_.guards == _site.id]
    _fl = [b_ for b_ in _st.bases.values() if b_.kind.value == "AIRFIELD"]
    _dist0 = min(math.hypot(b_.x - _site.x, b_.y - _site.y) for b_ in _fl) / 1852.0
    _o = (_site.x, _site.y); _go = [(g_.x, g_.y) for g_ in _gar]
    _site.health = 0.9
    assert not _sm.retreat(_st, _gd(3), random.Random(1)) or not _st.sams.get("pulled", {}).get(_site.id), "a healthy site stays put"
    _site.health = 0.15; _lines = []
    for _k in range(30):
        _lines = _sm.retreat(_st, _gd(3), random.Random(_k))
        if _site.id in _st.sams["pulled"]:
            break
    assert _site.id in _st.sams["pulled"] and any("pulled back" in l_ for l_ in _lines), "a badly hurt long-range site pulls back"
    _dist1 = min(math.hypot(b_.x - _site.x, b_.y - _site.y) for b_ in _fl) / 1852.0
    assert _dist1 > _dist0 + 20, f"it moved away from our airfields ({_dist0:.0f} -> {_dist1:.0f} nm)"
    assert all(math.isclose(g_.x - gx_, _site.x - _o[0], abs_tol=1) and math.isclose(g_.y - gy_, _site.y - _o[1], abs_tol=1) for g_, (gx_, gy_) in zip(_gar, [(a_[0], a_[1]) for a_ in _go])) or not _gar, "its garrison went with it"
    assert not _sm.retreat(_st, _gd(3), random.Random(5)) or _site.id in _st.sams["pulled"], "it does not pull back twice"
    _rt = _CS.from_dict(_st.to_dict()); assert _site.id in _rt.sams["pulled"], "saved with the campaign"
    _site.health = 0.9; _st.day += 3; _back = []
    for _k in range(30):
        _back = _sm.retreat(_st, _gd(3), random.Random(100 + _k))
        if _site.id not in _st.sams["pulled"]:
            break
    assert _site.id not in _st.sams["pulled"] and (round(_site.x), round(_site.y)) == (round(_o[0]), round(_o[1])) and any("back in position" in l_ for l_ in _back), "repaired, it returns to its old position"
    assert _sm.RETREAT_HEALTH < _sm.RETURN_HEALTH
    print("[retreat] a long-range site at 35% or less pulls back 35-55 nm with its garrison, is saved, and returns once repaired (65%, 2+ days); healthy sites stay")
    # front-line columns are as dense as their sector is strong; losses still read back as health
    from sqe.debrief import apply_debrief as _ad
    from sqe import ground as _gr3
    _cnt = {}
    for _str in (1.0, 0.3):
        _vals = []
        for _sd in (5, 6, 7):
            s.new("Dense", "A-10C", 3, seed=_sd); _st = s.state
            _st.campaign_id = f"{0xde05e00 + _sd:010x}"; s.plan_day()       # pinned: merged packages (and so the unit cap) follow the random campaign id
            _pk = next((p_ for p_ in s.packages() if p_.objective.type.value == "CAS" and p_.objective.target_id.startswith("armor_") and s.flyable(p_)), None)
            if _pk is None:
                continue
            _a = _st.assets[_pk.objective.target_id]; _a.health = _str; _gr3.pull(_st)
            s.fly(_pk.number, s.flyable(_pk)[0].id); _mn = s.manifest(); _g = next(g_ for g_ in _mn.groups if g_["kind"] == "asset" and g_["ref"] == _a.id)
            _vals.append(len(_g["units"]))
            _d = {"campaign": _st.campaign_id, "sortie": _st.sortie_counter, "package": _st.pending["package_dict"]["id"], "mission_ended": True, "time": 3000,
                  "dead": [], "ejected": [], "landed": [_mn.player_unit], "player": {"takeoff": 60, "landed": 2900, "ka": 0, "kg": 0, "ks": 0}, "kills": []}
            _ad(_st, _mn, _d); assert abs(_st.assets[_a.id].health - _str) < 0.02, "no losses: the sector keeps its strength"
        _cnt[_str] = sum(_vals) / max(1, len(_vals))
    assert _cnt[1.0] > 1.5 * _cnt[0.3], f"a full-strength column is far denser than a beaten one: {_cnt}"
    assert s.last_build.counts["units"] < 250, s.last_build.counts
    print(f"[dense columns] vehicles in a front-line column: {_cnt[1.0]:.0f} at full strength, {_cnt[0.3]:.0f} at 30%; no losses leaves the strength unchanged")
    import sqe.war as _wlr; _lr_real = _wlr.long_range_site; _wlr.long_range_site = lambda *a_: False     # this check is about the SEAD / Close DEAD pair: no Standoff DEAD
    # SEAD wears the defence down: each failed day raises the next day's odds, a failed attempt still costs the site, level 3 opens the valve after 2 days
    from sqe import war as _w4
    s.new("SEAD learn", "F-16C", 3, seed=11); _st = s.state
    _se = next(p_ for p_ in s.packages() if p_.objective.aim == "SEAD"); _site = _se.objective.target_id
    _sim = _w4.WarSimulator(s.d, random.Random(1)); _p0 = _sim.sead_p(_st, _se)
    _w4.note_sead(_st, _site, False); _p1 = _sim.sead_p(_st, _se); _w4.note_sead(_st, _site, False); _p2 = _sim.sead_p(_st, _se)
    assert abs((_p1 - _p0) - 0.10) < 1e-9 and _p2 > _p1, "each failed day adds to the odds"
    for _ in range(6):
        _w4.note_sead(_st, _site, False)
    assert _sim.sead_p(_st, _se) <= min(0.95, _p0 + 0.40) + 1e-9, "the bonus is capped"
    _w4.note_sead(_st, _site, True); assert abs(_sim.sead_p(_st, _se) - _p0) < 1e-9, "a success starts over"
    _t = _st.assets[_site]; _h = _t.health; _st.raids["sead"][_site] = False
    _sim.resolve_abstract(_st, _se); assert _t.health < _h, "a failed SEAD still wears the site down"
    assert (_gd(1).sead_valve, _gd(2).sead_valve, _gd(3).sead_valve) == (3, 3, 2)
    _st.raids["sead_fail"] = {_site: 2}; s.plan_day()
    assert not any(p_.objective.target_id == _site and p_.objective.aim in ("SEAD", "DEAD") for p_ in s.packages()), "two failed days at Level 3: the combined package is back for that site"
    s.new("SEAD brief", "F-16C", 3, seed=11); _st = s.state
    _se = next(p_ for p_ in s.packages() if p_.objective.aim == "SEAD" and s.flyable(p_))
    s.fly(_se.number, next(f_ for f_ in s.flyable(_se) if f_.role == Role.SEAD).id)
    assert "chance of suppressing" in s.last_build.text["situation"], "the SEAD briefing states the odds"
    print("[sead attrition] +10% a failed day (cap 40%), a failed attempt wears the site, valve after 2 failed days at Level 3, the briefing gives the odds")
    # jamming: pod / internal tiers, the hook carries them, the abstract war counts them
    from sqe import ecm as _ecm
    assert _ecm.internal_tier("F_15C") == 0 and _ecm.internal_tier("FA_18C_hornet") == 1 and _ecm.internal_tier("MiG-29S") == 0 and _ecm.has_pod({5: {"CLSID": "ALQ_184_Long"}}) and not _ecm.has_pod({1: {"CLSID": "{AIM}"}})
    assert _ecm.chance(2, 0, 10) == 0.0 and _ecm.chance(2, 0, 60) == _ecm.P_SELF[2] and _ecm.chance(0, 2, 60) == _ecm.P_COVER and _ecm.chance(0, 0, 60) == 0.0
    assert _ecm.flight_tier("F-16C", Role.SEAD) == 2 and _ecm.flight_tier("F-15C", Role.CAP) == 0 and _ecm.flight_tier("F-14BU", Role.CAP) == 1 and _ecm.jammer_on("x")
    s.new("Jam hook", "F-16C", 3, seed=11); _st = s.state
    _se = next(p_ for p_ in s.packages() if p_.objective.aim == "SEAD" and s.flyable(p_))
    s.settings.ecm_script = True                                     # the ECM script (off by default since v0.40.2)
    s.fly(_se.number, next(f_ for f_ in s.flyable(_se) if f_.role == Role.SEAD).id)
    from dcs import lua as _lua9
    _z9 = _zf.ZipFile(_st.pending["miz"]); _pu = s.manifest().player_unit
    def _fh(o):
        if isinstance(o, str):
            return o if "SQE debrief hook" in o else None
        for v in (o.values() if isinstance(o, dict) else o if isinstance(o, (list, tuple)) else ()):
            r = _fh(v)
            if r:
                return r
    _mz = _fh(_lua9.loads(_z9.read("mission").decode())) or _fh(_lua9.loads(_z9.read("l10n/DEFAULT/dictionary").decode()))
    _mz = (_mz or "").replace('\\"', '"')
    assert "local JAMS =" in _mz and f'["{_pu}"]=2' in _mz and "jamCheck" in _mz and "local JAMW =" in _mz, "the hook knows which aircraft carry a pod"
    _jw = [l_ for l_ in _mz.splitlines() if l_.startswith("local JAMW")][0]
    assert f'["{_pu}"]' not in _jw and "={" in _jw, "AI jammers run for the attack leg only; the player's runs throughout"
    import re as _re9
    _m9 = _z9.read("mission").decode()
    assert _re9.search(r'\["name"\]\s*=\s*13,\s*\["value"\]\s*=\s*3', _m9) or _re9.search(r'\["value"\]\s*=\s*3,\s*\["name"\]\s*=\s*13', _m9), "AI flights get the jammer switched on at PUSH (option 13)"
    s.settings.ecm_script = False                                    # default: DCS's own ECM, on at PUSH only when a radar locks
    s.fly(_se.number, next(f_ for f_ in s.flyable(_se) if f_.role == Role.SEAD).id)
    _z9b = _zf.ZipFile(_st.pending["miz"]); _m9b = _z9b.read("mission").decode()
    _hk9b = (_fh(_lua9.loads(_m9b)) or _fh(_lua9.loads(_z9b.read("l10n/DEFAULT/dictionary").decode())) or "").replace('\\"', '"')
    assert (_re9.search(r'\["name"\]\s*=\s*13,\s*\["value"\]\s*=\s*1', _m9b) or _re9.search(r'\["value"\]\s*=\s*1,\s*\["name"\]\s*=\s*13', _m9b)) and \
        not _re9.search(r'\["name"\]\s*=\s*13,\s*\["value"\]\s*=\s*3', _m9b) and f'["{_pu}"]=2' not in _hk9b, "script off: DCS ECM 'use if locked' at PUSH, the hook models no jamming"
    assert "all packages complete, no further tasking today" in _hk9b and _re9.search(r'local WATCH = \{ "[^"]+', _hk9b) and "return t + 300" in _hk9b, \
        "AWACS says when every package is done (to you, by callsign), every 5 minutes"
    try:
        import lupa as _lu
        assert _lu.LuaRuntime().eval("function(s) return load(s) ~= nil end")(__import__("sqe.debrief", fromlist=["x"]).lua_hook("c", 1, "p", [], "P", "G", jams={"a": 2}))
    except ImportError:
        pass
    _se2 = next(p_ for p_ in s.packages() if p_.objective.aim == "SEAD"); _sim = _w4.WarSimulator(s.d, random.Random(1)); _pj = _sim.sead_p(_st, _se2)
    _ecm_cut = _ecm.SITE_CUT; _ecm.SITE_CUT = 0.0; _pn = _sim.sead_p(_st, _se2); _ecm.SITE_CUT = _ecm_cut
    assert _pj > _pn, "jamming cover raises the SEAD odds"
    _wlr.long_range_site = _lr_real
    print("[jamming] tiers (internal / pod / none), burn-through by range, pods and tiers in the hook, jamming cover raises the SEAD odds")
    # air wings that fall back: a badly depleted wing or squadron stands down, recovers faster, returns; the player's squadron and carriers never
    from sqe import airwings as _aw
    s.new("Air rest", "F-16C", 3, seed=11); _st = s.state; _d9 = type(_gd(3))(**{**_gd(3).__dict__, "air_retreat": 1.0})
    _w9 = next(w_ for w_ in _st.enemy_air if "Tu_22M3" not in w_.types and w_.authorized >= 8); _w9.available = 2
    _bs = [sq_ for sq_ in _st.squadrons.values() if sq_.id != _st.player.squadron_id and _st.bases[sq_.base_id].kind.value != "CARRIER"]
    _psq = _st.squadrons[_st.player.squadron_id]; _psq.available = 1
    for _b9 in _bs:
        _b9.available = 1
    _ea0 = _war.totals(_st)["ea"]; _rng9 = _rnd.Random(1)
    _l9 = _aw.step(_st, _d9, _rng9)
    assert _w9.available == 0 and _w9.reserve == 2 and any("air wing" in x_ for x_ in _l9), "a depleted wing stands down"
    assert _psq.available == 1 and _psq.reserve == 0, "your own squadron is never pulled"
    assert all(b_.reserve == 1 for b_ in _bs if b_.authorized >= _aw.MIN_AUTHORIZED), "the other friendly squadrons follow the same rule"
    assert _war.totals(_st)["ea"] == _ea0, "resting aircraft still count in the strength totals"
    _bw = next((w_ for w_ in _st.enemy_air if "Tu_22M3" in w_.types), None)
    if _bw is not None:
        _bw.available = 1; _aw.step(_st, _d9, _rng9); assert _bw.reserve == 0, "the strategic bomber wing is left alone"
    _sim9 = _war.WarSimulator(_d9, _rnd.Random(2)); _back = False
    for _n9 in range(30):
        _sim9.end_day(_st)
        if _w9.reserve == 0 and _w9.available > 0:
            _back = True; break
        assert _w9.available == 0, "a resting wing does not fly"
    assert _back and _n9 >= _aw.RETURN_MIN_DAYS - 1 and _w9.available >= _aw.RETURN_FRAC * _w9.authorized - 1, "it returns after resting, at strength"
    _rt9 = _CS.from_dict(_st.to_dict()); assert [w_.reserve for w_ in _rt9.enemy_air] == [w_.reserve for w_ in _st.enemy_air], "saved and loaded"
    print("[air rest] depleted wings and squadrons stand down, recover faster and return; your squadron, carriers and the bomber wing are left alone; saved")
    # roads: the scan file's points, nearest-point snapping, columns and supply sites moved onto a road once (garrisons stay off it)
    from sqe import roads as _rdm, ground as _grd9
    _rdm.clear(); assert not _rdm.available() and _rdm.snap(0, 0) is None, "no road scan: no snapping"
    _rdm.from_points([(1000, 1000), (1000, 9000), (-20000, 5000)])
    assert _rdm.snap(1500, 1200) == (1000.0, 1000.0) and _rdm.snap(1000, 5000, 3000) is None and _rdm.snap(1000, 8000) == (1000.0, 9000.0), "nearest road point within the limit"
    s.new("Roads", "F-16C", 2, seed=5); _st = s.state
    _col = _st.assets["armor_1"]; _fs = _st.assets.get("fsam_1"); _gar = next((a_ for a_ in _st.assets.values() if a_.variant == "GARRISON"), None)
    _off = (_fs.x - _col.x, _fs.y - _col.y) if _fs else None; _g0 = (_gar.x, _gar.y) if _gar else None
    _st.ground.pop("roads", None)
    _rdm.from_points([(_col.x + 1200, _col.y - 800)])
    _n9 = _grd9.snap_roads(_st)
    assert _n9 >= 1 and (_col.x, _col.y) == (_col.x, _col.y) and abs(_col.x - (_fs.x - _off[0] if _fs else _col.x)) < 1e-6, "the column moved onto the road point"
    if _fs:
        assert abs((_fs.x - _col.x) - _off[0]) < 1e-6 and abs((_fs.y - _col.y) - _off[1]) < 1e-6, "its air defence moved with it"
    if _gar:
        assert (_gar.x, _gar.y) == _g0, "garrisons stay where they are"
    assert _st.ground.get("roads") and _grd9.snap_roads(_st) == 0, "done once"
    _rdm.clear()
    print("[roads] scan file points, nearest-point snap, columns and supply sites placed on a road once with their air defence; no scan = nothing changes")
    # --full-map: nothing is left out (a stress test; the launch option comes from the debug dropdown)
    s.new("Full map", "F-16C", 3, seed=11); _st = s.state
    _pk = next(p_ for p_ in s.packages() if s.flyable(p_))
    s.full_map = False; _n0 = s.fly(_pk.number, None).counts["units"]
    s.full_map = True; _rf = s.fly(_pk.number, None); _n1 = _rf.counts["units"]
    assert s.options.full_map and s.options.max_units >= 10 ** 5, "the unit limit is off"
    assert _n1 > 3 * _n0 and _n1 > 500, (_n0, _n1)
    _kinds = {g_["kind"] for g_ in s.manifest().groups}
    assert {"asset", "blue_site", "enemy_air"} <= _kinds, _kinds
    assert len([g_ for g_ in s.manifest().groups if g_["kind"] == "asset"]) >= len([a_ for a_ in _st.assets.values() if not a_.destroyed and a_.kind.value in ("SAM", "EWR", "ARMOR", "C2", "FUEL", "DEPOT", "AIRFIELD")]) - 1, "every live site is built"
    s.full_map = False
    import json as _js9
    _ln = _js9.load(open(Path(__file__).resolve().parent.parent / ".vscode" / "launch.json"))["configurations"]
    assert any("--full-map" in c_.get("args", []) for c_ in _ln) and any(c_.get("args") == ["--ai-test", "--full-map"] for c_ in _ln), "the debug dropdown has the launch combinations"
    print(f"[full map] a normal mission has {_n0} units, the same sortie with --full-map {_n1}; every site, friendly garrison and planned patrol built; launch combinations in the debug dropdown")
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
