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


# Plain imports the sections share (they used to be borrowed from whichever earlier section imported them first).
import math as _m3j, math as _mm, math as _m                                   # noqa: E401
import random, random as _rnd, random as _rd                                    # noqa: E401
import re as _re, tempfile as _tf, zipfile as _zf                               # noqa: E401
from types import SimpleNamespace as _NS
from dcs import lua, lua as _luaj
from sqe import profiles as _pf, relief as _rl, sams as _sm, threatmap as _tm9
from sqe import ground as _gr, war as _war
import sqe.engine as _eng27
from sqe.aircraft import AIRCRAFT as _AC
from sqe.difficulty import get as _gd
from sqe.models import AssetKind as _AK, Role, Role as _Rl, Role as _Rl2, task_label as _tl
from sqe.packages import Package as _Pkg, is_sweep as _isw
from sqe.routes import bearing as _brg, plan_route as _pr3
from sqe.engine import SWEEP_LEAD_MIN as _slm
from sqe.state import CampaignState, CampaignState as _CS
from sqe.war import WarSimulator, long_range_site as _lrs


mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))     # a new session on the test's temp folder


class Ctx:
    """Shared state between the check sections: a section reads what it borrows from here at the top and leaves what later sections need at the bottom."""


def fresh_session(level=3, seed=7, ac="F-16C"):
    """A new campaign of its own for a section that needs a session (instead of borrowing setup's, which earlier sections have changed)."""
    ses = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    ses.new("Smoke fresh", ac, level, seed=seed)
    return ses


def check_00_setup(c):
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
        _cs = [f.callsign for p in s.packages() for f in p.flights if f.tag not in ("BASECAP", "CVCAP", "HAVCAP", "TNKCAP")]      # v0.41.85: one planned base / carrier CAP sortie is carried by every package it covers
        assert len(_cs) == len(set(_cs)), f"no two flights share a callsign in a day: {sorted(c for c in _cs if _cs.count(c) > 1)}"
        _bc = {}
        for p in s.packages():
            for f in p.flights:
                if f.tag in ("BASECAP", "CVCAP"):
                    assert _bc.setdefault(f.callsign, (f.tag, f.squadron_id, f.base_id, f.guard)) == (f.tag, f.squadron_id, f.base_id, f.guard), "a planned CAP sortie keeps one identity"
        assert not (set(_bc) & set(_cs)), "a CAP callsign is never also a package flight's"
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
        assert out["tempo"] and any(x_.startswith("Tactical Edge") for x_ in out["lines"]), "v0.41.147: the debrief shows the air tempo change"
        assert s.state.pilot["sorties"] == 1 and s.state.pilot["kills_ground"] == 2, s.state.pilot
        print(f"    debrief: {out['story'].splitlines()[0][:100]}...  pilot: {s.state.pilot['sorties']} sortie, {s.state.pilot['kills_air']}A/{s.state.pilot['kills_ground']}G kills")
        r = mk(); r.open(s.path)
        assert r.state.day == 2 and r.state.pilot["sorties"] == 1
        tested += 1
    assert tested >= 3, "too few jets tested"
    c.__dict__.update({k_: v_ for k_, v_ in locals().items() if k_ in ('lua', 'man', 'mk', 'res', 's',)})












def check_06_gui_dialogs_build_scan(c):
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
        assert [_dlg.tabs.tabText(i) for i in range(_dlg.tabs.count())] == ["General", "Campaign", "Mission Build", "DCS integration", "Experimental"]
        assert not hasattr(_dlg, "probe_btn") and not hasattr(_dlg, "tm_status"), "v0.41.206: the terrain scan page is gone"
        _gs.carcass_weight_pct, _gs.weather_mode, _gs.merge_radius_nm = 40, "rain", 35       # every moved control still round-trips
        _d2 = SettingsDialog(_gs)
        assert (_d2.cw.value(), _d2.wxm.currentData(), _d2.mrad.value()) == (40, "rain", 35)
        assert not hasattr(_d2, "react") and not hasattr(_d2, "emerg")      # v0.41.135: both checkboxes are gone
        _dlg._save()
        _nc = NewCampaignDialog(None, "rain")
        assert _nc.values()["weather_mode"] == "rain", "the new-campaign dialog offers the weather, starting from the current setting"
        assert _d2.ecm.isChecked() is False and _d2.splash.isChecked() is True, "ECM script off and splash damage on by default (v0.41.13)"
        print("[gui] settings (5 tabs, no terrain scan page) and new-campaign dialogs build; every control round-trips")
    except ImportError:
        print("[gui] PySide6 not installed here; dialogs not exercised")












































































































































def check_39_dcs_refuses_mission_whose(c):
    # v0.41.2: DCS refuses a mission whose player route has a run of locked-speed points between two locked times (v0.41.1: the player as an
    # escort, "Viper 3: All waypoints (5-5) have locked speed and surrounded by waypoints 4 and 5 with locked time"). Every fighter role you
    # can fly is built and checked.
    def _dcs_eta_ok(pts_):
        lk = [i for i, p_ in enumerate(pts_) if p_.get("ETA_locked")]
        for a_, b_ in zip(lk, lk[1:]):
            mid = pts_[a_ + 1:b_]
            if mid and all(p_.get("speed_locked") for p_ in mid):
                return False
        if lk and lk[-1] + 1 < len(pts_) and pts_[lk[-1] + 1].get("type") == "Land" and pts_[lk[-1] + 1].get("speed_locked"):
            return False
        return True
    _ps = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, merge_mode="off", flight_filter="all"))
    _seen_r = set()
    for _ac in ("F-16C", "F-15C", "F-14BU"):
        _ps.new("Eta", _ac, 3, seed=3)
        for _pk in _ps.packages():
            for _fl in _ps.flyable(_pk, squadron_only=False):
                _key = (_ac, _fl.role.value, _pk.objective.type.value)
                if _key in _seen_r or _fl.role.value not in ("TARCAP", "ESCORT", "SWEEP", "SEAD", "STRIKE", "CAP"):
                    continue
                _seen_r.add(_key)
                _ps.fly(_pk.number, _fl.id)
                _Me = _luaj.loads(_zf.ZipFile(_ps.state.pending["miz"]).read("mission").decode("utf-8", "ignore"))["mission"]
                _pg = next(g_ for co_ in _Me["coalition"]["blue"]["country"].values() for g_ in ((co_.get("plane") or {}).get("group") or {}).values()
                           if any(u_.get("skill") in ("Player", "Client") for u_ in g_["units"].values()))
                assert _dcs_eta_ok(list(_pg["route"]["points"].values())), (_key, "DCS would refuse this player route (locked speed between locked times)")
                _ps.abort()
    print(f"[eta locks] {len(_seen_r)} player roles built (TARCAP, escort, sweep, SEAD, strike, CAP): no locked-speed run between locked times")
    # Tors (v0.39.20): the Tors that cover a SEAD/DEAD target are part of the job: the second HARM flight opens on them, the JSOWs aim at them,
    # the DEAD gate waits for them (route check), and the Tor vehicle counts as a radar
    import math as _m3
    from dcs import lua as _lua3
    from sqe.strike_tasks import TRACK_RADARS as _TR, TOR_COVER_KM as _tck
    from sqe import threatmap as _tm9
    assert "Tor 9A331" in _TR, "a Tor's radar rides on the launcher: the vehicle counts as a radar"
    _p3 = None
    for _sd3 in range(1, 9):                          # v0.41.199: the layout moves with the site spots; take the first seed whose Tor-covered SA-10 DEAD job passes the checks below
        try:
            _ts = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, flight_filter="all"))
            _ts.new("Tor", "F-16C", 3, seed=_sd3); _ts.state.campaign_id = f"{0x70a0001 + _sd3 - 1:010x}"; _ts.plan_day()
            _A3 = _ts.state.assets; _tors = [a_ for a_ in _A3.values() if a_.variant == "SA-15"]
            _cov = lambda p_, _A3=_A3, _tors=_tors: [a_.id for a_ in _tors if _m3.hypot(a_.x - _A3[p_.objective.target_id].x, a_.y - _A3[p_.objective.target_id].y) <= _tck * 1000]
            _p3 = next((p_ for p_ in _ts.packages() if p_.objective.aim == "STANDOFF" and _A3[p_.objective.target_id].variant == "SA-10" and _cov(p_) and _ts.flyable(p_)), None)
            if _p3 is None:
                continue
            _ts.ai_test = True; _ts.fly(_p3.number, _ts.flyable(_p3)[0].id); _ts.ai_test = False
            _m3t = _zf.ZipFile(_ts.state.pending["miz"]).read("mission").decode("utf-8", "ignore"); _M3 = _lua3.loads(_m3t)["mission"]
            _red = {g_["groupId"]: (g_["name"], [(u_["x"], u_["y"]) for u_ in g_["units"].values()]) for co_ in _M3["coalition"]["red"]["country"].values()
                    for g_ in ((co_.get("vehicle") or {}).get("group") or {}).values()}
            _torpos = [xy_ for n_, xys_ in _red.values() if n_ in _cov(_p3) for xy_ in xys_]
            _agm88, _jsow = [], 0
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
                        _agm88.append(seq_)
            assert any(sq_[0] in _cov(_p3) and _p3.objective.target_id in sq_ for sq_ in _agm88), "the second HARM flight opens on the Tors, then joins on the site"
            assert any(_p3.objective.target_id in sq_ and sq_[-1] in _cov(_p3) and sq_.index(_p3.objective.target_id) < len(sq_) - 1 for sq_ in _agm88), \
                "the HARM flights end with a second pass at the Tors that guard the site (v0.39.22)"
            assert _jsow >= 1, ("the JSOW flight aims at the Tors that guard the site", _sd3, len(_torpos))
        except AssertionError:
            _p3 = None
            continue
        break
    assert _p3 is not None, "a Tor-covered SA-10 standoff job that passes the Tor checks in one of 8 seeds"
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
    _arr = [int(p_.start[:2]) * 60 + int(p_.start[3:5]) + _ss._agm88_leg_s(p_) / 60 for p_ in _sd4]
    assert len(_sd4) >= 2 and max(_arr) - min(_arr) <= 1.5, ("SEAD packages on one cluster reach their HARM points together", _arr)
    _pus = [p_ for p_ in _sd4 if _tm9.umbrella_site(_ss.state, _A4[p_.objective.target_id]) and _ss.flyable(p_) and any(f_.kit == "JSOW" for f_ in p_.flights)]
    _pu = next((p_ for p_ in _pus if any(_ss.state.bases[f_.base_id].kind.value == "CARRIER" for f_ in p_.flights)), _pus[0])       # v0.41.65: prefer a package with carrier flights, the [cv recover] check below needs one (it passed by luck of the layout before)
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
                assert _m.hypot(_pt4["x"] - _um4.x, _pt4["y"] - _um4.y) / 1852 >= 34, "under an umbrella the HARM point stays out of the SA-10's reach"
                _seq4 = []
                for t_ in _pt4["task"]["params"]["tasks"].values():
                    tid_, prm_ = t_.get("id"), t_.get("params", {})
                    if tid_ == "ControlledTask":
                        tid_, prm_ = prm_["task"]["id"], prm_["task"].get("params", {})
                    if tid_ == "AttackGroup":
                        _seq4.append(_red4.get(prm_.get("groupId")))
                assert _seq4 and _seq4[0] == _um4.id, ("the first HARM flight opens on the umbrella", _seq4)
            else:       # v0.41.3: the JSOW launch point stays out of every live SA-10's reach too, and a pushed-out shot goes from high up
                _sa10 = [a_ for a_ in _A4.values() if a_.variant in _tm9.UMBRELLA_VARIANTS and not a_.destroyed]
                _jk = min(_m.hypot(_pt4["x"] - a_.x, _pt4["y"] - a_.y) / 1852 for a_ in _sa10)
                _jt = _m.hypot(_pt4["x"] - _t4.x, _pt4["y"] - _t4.y) / 1852
                assert _jk >= 39 or _jt >= 44, ("the JSOW launch point stays 40 nm from every live SA-10 (up to 45 nm from the target, v0.41.4)", round(_jk, 1), round(_jt, 1))
                if _jt > 21:
                    assert _pts4["IP"]["alt"] / 0.3048 >= 32900, ("a long JSOW shot goes from 33,000 ft", _pts4["IP"]["alt"])
                _jsow_kp = (_jk, _jt)
    _sead2 = [f_.callsign for f_ in _pu.flights if f_.role == Role.SEAD and not f_.tag][1:]
    if _sead2 and _um4.id != _t4.id:          # v0.41.4: the second HARM flight also holds HARMs for the umbrella after its Tor window
        for co_ in _M4["coalition"]["blue"]["country"].values():
            for g_ in ((co_.get("plane") or {}).get("group") or {}).values():
                if g_["name"] == _sead2[0]:
                    _sp2 = next(p_ for p_ in g_["route"]["points"].values() if p_.get("name") == "SEAD")
                    _q2 = [_red4.get((t_["params"]["task"].get("params") or {}).get("groupId")) for t_ in _sp2["task"]["params"]["tasks"].values()
                           if t_.get("id") == "ControlledTask" and t_["params"]["task"]["id"] == "AttackGroup"]
                    assert _um4.id in _q2, ("the second HARM flight waits on the umbrella too", _q2)
        print(f"[umbrella] second HARM flight {_sead2[0]} also tasked on the SA-10 {_um4.id}")
    _hw = 0                                    # v0.41.5: after the hold, TARCAP / escort / sweep still fight what follows them home
    for co_ in _M4["coalition"]["blue"]["country"].values():
        for g_ in ((co_.get("plane") or {}).get("group") or {}).values():
            _t0 = [t_ for t_ in g_["route"]["points"][1]["task"]["params"]["tasks"].values() if t_.get("id") == "ControlledTask"]
            _zn = [t_ for t_ in _t0 if t_["params"]["task"]["id"] == "EngageTargetsInZone" and "stopCondition" in t_["params"]]
            if not _zn or not ({"TGT", "SWEEP"} & {p_.get("name") for p_ in g_["route"]["points"].values()}) or "SEAD" in {p_.get("name") for p_ in g_["route"]["points"].values()}:
                continue        # the stationed fighters only (SEAD flights have their own engage window)
            _st = _zn[0]["params"]["stopCondition"]["time"]
            _hm = [t_ for t_ in _t0 if t_["params"]["task"]["id"] == "EngageTargetsInZone" and t_["params"].get("condition", {}).get("time") == _st]
            assert _hm, ("a held fighter flight engages on the way home after its hold", g_["name"])
            _hw += 1
    assert _hw >= 2, ("TARCAP / escort flights with the homeward engage", _hw)
    print(f"[homeward] {_hw} held fighter flights engage air in a fixed circle over their way home after their hold ends (v0.41.15)")
    c.__dict__.update({k_: v_ for k_, v_ in locals().items() if k_ in ('Role', '_A4', '_M4', '_arr', '_brg', '_jsc', '_jsow_kp', '_m', '_pu', '_sd4', '_sead1', '_ss', '_st', '_t4', '_tm9', 'lua',)})














































































































def check_80_incompatible_saves(c):
    """v0.41.162: a save this build cannot open raises SaveIncompatible (older / newer / damaged), never a raw traceback; the open campaign stays open;
    the backup copies the file and leaves the original alone; a good save loads with no fuss and is stamped with the version and era."""
    import json as _j, tempfile as _tf
    from pathlib import Path as _P
    from sqe import __version__, COMPAT_ERA
    from sqe.state import SaveIncompatible
    s = fresh_session(2, 3); s.save()
    d = _j.loads(_P(s.path).read_text(encoding="utf-8"))
    assert d["app_version"] == __version__ and d["compat"] == COMPAT_ERA, "saves carry the version and the era"
    tmp = _P(_tf.mkdtemp())
    def put(name, dd):
        p = tmp / name; p.write_text(dd if isinstance(dd, str) else _j.dumps(dd), encoding="utf-8"); return p
    cur = s.state
    cases = {"old_ground": ({**d, "ground": {**d["ground"], "v": 1}, "app_version": "0.41.150"}, "older"),
             "format3": ({**d, "format": 3}, "older"), "newer_era": ({**d, "compat": COMPAT_ERA + 1, "app_version": "0.99.0"}, "newer"),
             "newer_fmt": ({**d, "format": 99}, "newer"), "broken": ({k: v for k, v in d.items() if k != "assets"}, "older"), "junk": ("not json {{", "damaged")}
    for nm, (dd, kind) in cases.items():
        p = put(nm + ".sqe", dd)
        try:
            s.open(p)
        except SaveIncompatible as e:
            assert e.kind == kind, (nm, e.kind, kind)
            e.info()
        else:
            raise AssertionError(f"{nm}: should not open")
        assert s.state is cur, "a refused save leaves the open campaign open"
    bad = put("bak.sqe", cases["old_ground"][0]); before = bad.read_text(encoding="utf-8")
    dst = s.backup_incompatible(bad)
    assert dst.exists() and dst.read_text(encoding="utf-8") == before and bad.read_text(encoding="utf-8") == before, "the backup is a copy; the original is untouched"
    s.open(s.path)                                                       # a good save opens with no dialog
    print(f"[incompatible saves] {len(cases)} bad saves refused with a friendly error, the open campaign stayed open; backup copied to {dst.name}")






















def check_104_tuned_and_damage_calls(c):
    """v0.41.215: AWACS calls need a tuned radio (cockpit-parameter triggers for the jets whose radios can be read), and the other aircraft call their own damage."""
    import re as _re, zipfile as _zf
    from dcs import lua as _lua
    from sqe import debrief as _db
    h = _db.lua_hook("c", 1, "p", [], "P1", "G", tune_flags=[9101, 9102], tune_mhz=262.5, awacs_unit="Magic 1-1", dmg={"Viper 2-2": "VIPER 2-2", "Texaco 1-1": "*TEXACO"}, dmg_on=True)
    assert "local TUNEF = { 9101, 9102 }" in h and 'local TUNEMHZ = "262.500"' in h and 'local AWUNIT = "Magic 1-1"' in h and "local DMG_ON = true" in h, "the hook carries the tuning flags and the damage table"
    assert '["Texaco 1-1"]="*TEXACO"' in h and "function tryCall" in h and "function sayAw" in h and "awdown = true" in h and "Mayday, mayday, ejecting." in h
    h0 = _db.lua_hook("c", 1, "p", [], "P1", "G")
    assert "local TUNEF = {  }" in h0 and "local DMG_ON = false" in h0, "nothing set: always tuned, no damage calls"
    try:                                                    # the hook still compiles as Lua (lupa is optional)
        import lupa as _lupa
        _chk = _lupa.LuaRuntime().eval("function(src) local fn, err = load(src); return err end")
        assert _chk(h) is None and _chk(h0) is None, "the hook is valid Lua"
    except ImportError:
        pass
    try:                                                    # v0.41.217: run the hook with a stubbed DCS API and fire hit / eject / dead events at it (tools/hook_lua_sim.py)
        import lupa  # noqa
        sys_path = str(__import__("pathlib").Path(__file__).resolve().parent)
        if sys_path not in __import__("sys").path:
            __import__("sys").path.insert(0, sys_path)
        import hook_lua_sim as _hs
        _r = _hs.run(_db.lua_hook("c", 1, "p", [], "Viper 1-1", "Viper 1", flights={"Viper 1-2": "VIPER 1-2"}, tune_flags=[9101], tune_mhz=262.5, awacs_unit="Magic 1-1",
                                  dmg={"Viper 1-2": "VIPER 1-2", "Magic 1-1": "*MAGIC"}, dmg_on=True, awacs="Magic"))
        assert _r.startswith("ok | undefined globals read:  |") and "MAGIC: Mayday" in _r and "VIPER 1-2: " in _r, ("the hook survives hit / eject / dead events", _r)
    except ImportError:
        pass
    def hook_of(ac, **opt):
        s = mk(); s.new("Tune " + ac, ac, 3, seed=11)
        for k, v in opt.items():
            setattr(s.settings, k, v)
        s.plan_day()
        for p_ in s.packages():
            fl = s.flyable(p_)
            if fl:
                s.fly(p_.number, fl[0].id); break
        z = _zf.ZipFile(s.state.pending["miz"]); m = z.read("mission").decode()
        def fh(o):
            if isinstance(o, str):
                return o if "SQE debrief hook" in o else None
            for v in (o.values() if isinstance(o, dict) else o if isinstance(o, (list, tuple)) else ()):
                r = fh(v)
                if r:
                    return r
        hk = (fh(_lua.loads(m)) or fh(_lua.loads(z.read("l10n/DEFAULT/dictionary").decode())) or "").replace('\\"', '"')
        return m, hk, s
    m, hk, s = hook_of("F-16C")
    n_ = m.count("COMM1_FREQ")
    assert n_ >= 3 and "COMM2_FREQ" not in m and _re.search(r"local TUNEF = \{ \d+ \}", hk), ("F-16C: one radio, three triggers", n_)
    assert "local DMG_ON = true" in hk and '="*' in hk, "damage calls on by default, the AWACS (and any tanker) is in the table with a * marker"
    m2, hk2, _ = hook_of("A-10C")
    assert "UHF_FREQ" in m2 and "COMM1_FREQ" not in m2 and "VHF_AM_FREQ" not in m2, "A-10C: UHF only"
    m3, hk3, _ = hook_of("F-15C")
    assert "COMM1_FREQ" not in m3 and "local TUNEF = {  }" in hk3, "F-15C (FC3): nothing readable, always tuned"
    m4, hk4, _ = hook_of("F-16C", awacs_tuned=False, damage_calls=False)
    assert "COMM1_FREQ" not in m4 and "local TUNEF = {  }" in hk4 and "local DMG_ON = false" in hk4, "both switches off"
    print("[tuned + damage calls] F-16C COMM1 triggers, A-10C UHF only, F-15C none, both switches off, AWACS in the damage table")




def check_106_ecm_install(c):
    """v0.41.219 (XO 2026-10-31): the ECM export script installs itself (copy + one marked line at the end of Export.lua), removes cleanly, never touches
    other lines or line endings, backs Export.lua up once, and polls four times a second; plus the renamed support-CAP labels."""
    import tempfile
    from pathlib import Path as _Pa
    from sqe import settings as S
    from sqe import packages as _pk
    with tempfile.TemporaryDirectory() as td:
        sv = str(_Pa(td) / "DCS"); _Pa(sv).mkdir()
        assert S.ecm_script_state(sv) == "none" and S.ecm_script_state("") == "nofolder"
        ok, _m = S.install_ecm_script(sv); assert ok
        ex = _Pa(sv, "Scripts", "Export.lua"); sc = _Pa(sv, "Scripts", "sqe_ecm_export.lua")
        assert ex.read_text() == S.ECM_LINE + "\n" and sc.exists() and S.ecm_script_state(sv) == "ok", ex.read_text()
        S.install_ecm_script(sv); assert ex.read_text().count("sqe_ecm_export") == 1          # twice = still one line
        assert S.remove_ecm_script(sv)[0] and not sc.exists() and S.ecm_script_state(sv) == "none"
        assert ex.read_text().strip() == "", repr(ex.read_text())
        orig = b"-- tacview\r\ndofile(lfs.writedir()..[[Scripts\\TacviewGameExport.lua]])"      # CRLF, no trailing newline
        ex.write_bytes(orig); S.install_ecm_script(sv)
        got = ex.read_bytes()
        assert got == orig + b"\r\n" + S.ECM_LINE.encode() + b"\r\n", got
        assert _Pa(sv, "Scripts", "Export.lua.sqe.bak").read_bytes() == orig
        sc.write_text("-- old copy"); assert S.ecm_script_state(sv) == "old"
        S.install_ecm_script(sv); assert S.ecm_script_state(sv) == "ok"
        S.remove_ecm_script(sv); assert ex.read_bytes() == orig + b"\r\n", ex.read_bytes()    # our line gone, theirs untouched
        ex.write_bytes(orig + b"\r\ndofile(lfs.writedir() .. [[Scripts\\sqe_ecm_export.lua]])\r\n")     # a hand-made line counts as installed
        S.install_ecm_script(sv); assert ex.read_bytes().count(b"sqe_ecm_export") == 1
    lua = (_Pa(__file__).resolve().parent.parent / "sqe" / "data" / "sqe_ecm_export.lua").read_text()
    assert "POLL_S, BEAT_S = 0.25, 1.0" in lua and "--[[SQE ECM EXPORT]]dofile" in lua
    assert _pk._TAG_TASK["TNKCAP"] == "HAVCAP (guards the tanker)" and _pk._TAG_TASK["CVCAP"] == "BARCAP (guards the carrier group)"
    print("[ecm install] install / twice / remove / CRLF / backup / old copy / hand line; 0.25 s polling; support-CAP labels")















































CHECKS = [
    check_00_setup,
    check_06_gui_dialogs_build_scan,
    check_39_dcs_refuses_mission_whose,
    check_80_incompatible_saves,
    check_104_tuned_and_damage_calls,
    check_106_ecm_install,
]

def _borrows(fn) -> set:
    """The Ctx attributes a section reads (`c._M4` ...): the names it borrows from earlier sections."""
    import inspect
    import re
    return set(re.findall(r"\bc\.(_?\w+)", inspect.getsource(fn)))


def _provides(fn) -> set:
    """The Ctx attributes a section leaves for later ones (its `c.__dict__.update(... in (names))` line)."""
    import inspect
    import re
    out = set()
    for m in re.finditer(r"c\.__dict__\.update\(\{[^}]*\bin \(([^)]*)\)", inspect.getsource(fn)):
        out |= set(re.findall(r"'(\w+)'", m.group(1)))
    return out


def _with_prerequisites(run: list) -> list:
    """`--only`: add, ahead of each chosen section, the earlier sections it borrows state from (the nearest earlier one that leaves each name),
    so a section passes on its own. Sections still run in their normal order."""
    keep, todo = {fn.__name__ for fn in run}, list(run)
    while todo:
        fn = todo.pop()
        k = CHECKS.index(fn)
        for attr in _borrows(fn):
            src = next((p for p in reversed(CHECKS[:k]) if attr in _provides(p)), None)
            if src is not None and src.__name__ not in keep:
                keep.add(src.__name__)
                todo.append(src)
    return [fn for fn in CHECKS if fn.__name__ in keep]


def _fixed_ids(name: str) -> None:
    """Campaign ids are random (they seed the day plan and the site layouts), so a seeded check could pass or fail by luck. Each section gets
    the same run of ids every time, whatever ran before it."""
    import random as _r
    import uuid as _u
    rng = _r.Random(name)
    _u.uuid4 = lambda: _u.UUID(int=rng.getrandbits(128), version=4)


def main(argv=None):
    """Run the check sections in order. Options: `--list` (names only), `--only a,b` (the setup section plus the sections whose name contains a or b,
    each with the earlier sections it borrows state from), `--timeout SECONDS` (a section that runs longer
    dumps every thread's traceback and stops the run; default 600, 0 = off)."""
    import argparse
    import faulthandler
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args(argv)
    if args.list:
        print("\n".join(fn.__name__ for fn in CHECKS))
        return
    sys.stdout.reconfigure(line_buffering=True)                  # output reaches a log file at once, so a stall shows where it is
    want = [w for w in args.only.split(",") if w]
    run = [fn for k, fn in enumerate(CHECKS) if not want or k == 0 or any(w in fn.__name__ for w in want)]
    if want:
        run = _with_prerequisites(run)
    c, times = Ctx(), []
    for fn in run:
        if args.timeout:
            faulthandler.dump_traceback_later(args.timeout, exit=True)
        t0 = time.time()
        _fixed_ids(fn.__name__)
        fn(c)
        times.append((time.time() - t0, fn.__name__))
    faulthandler.cancel_dump_traceback_later()
    print("slowest sections: " + ", ".join(f"{n} {t:.0f} s" for t, n in sorted(times, reverse=True)[:5]))
    if not want:
        print("SMOKE TEST PASSED")



if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
