"""Headless core-function test (no DCS). Run:  python tools/smoke_test.py   (options: --list, --only a,b, --timeout SECONDS)
Isolated: a temporary folder for everything, APPDATA redirected, your real settings and campaigns are never touched; the temp data is deleted at the end.
Parallel (S124, XO 2026-11-20): the default run splits the checks over worker processes (one TMP / APPDATA each; the output is printed in the usual order); `--jobs N` sets the workers, `--jobs 1` is the old serial run. A single check runs in this process.
Scope (XO 2026-11-06, see .claude/smoke test plan.md): (1) loads, saves, campaigns, compatibility; (2) the dialogs and the main window build; (3) missions are generated;
(4) every package carries its required flight; (5) the .miz structure loads in DCS without errors. Assert STRUCTURE, never values: no constant, no state.day value, no waypoint, job, role or kit name, no
game or hook text. An assert that ends with us changing this file instead of fixing SQE is invalid: remove it, do not relax it.
The soak (skip to the end of the war, three campaigns, no assert but "no exception") is part of the default run (XO 2026-11-11); `--only soak` runs it alone, `--seeds N` adds seeds.
Five jets are built once (`builds()`, lazy) and read by the missions and .miz checks. 'SMOKE TEST PASSED' + exit code 0 = everything worked."""
import json
import os
import shutil
import sys
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="sqe_test_"))
os.environ["APPDATA"] = str(TMP / "appdata")                 # belt and braces: even a stray settings save stays in TMP
_FONTS = Path(os.environ.get("WINDIR", "")) / "Fonts"
if os.environ.get("WINDIR") and _FONTS.is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", str(_FONTS))      # S99: Qt's offscreen platform finds no font folder and prints a warning per GUI worker; the workers re-import this module, so it covers them
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parent))      # hook_lua_sim sits beside this file
import sqe
from dcs import lua
from sqe.engine import Session
from sqe.packages import NoPlayerSlot
from sqe.settings import AppSettings

mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))     # a new session on the test's temp folder
LUA_SKIPPED = []                                              # set when lupa is missing: the last line says so


def fresh_session(level=3, seed=7, ac="F-16C", theatre="caucasus"):
    """A new campaign of its own for a check that needs a session (S126: the soak also runs on Syria; the caller puts the Caucasus back with `theatres.use("caucasus")`)."""
    ses = mk()
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    ses.new("Smoke fresh", ac, level, seed=seed, a10_variant=ac if ac in ("A-10A", "A-10C2") else None, f14_variant=ac if ac == "F-14B" else None, theatre=theatre)      # S103b / S103c: the A-10A and the F-14B need a campaign created with them (Era Equipment)
    return ses


def clock(s):                                                 # survives the turn system
    return (s.state.day, getattr(s.state, "turn", 0))


def advance(s):
    (getattr(s, "skip_turn", None) or s.skip_day)()


def first_flyable(s, steps=24):
    """The first package this jet can fly, walking forward through turns. None if there is none. `steps` is a loop bound, not a game rule."""
    for _ in range(steps):
        p = next((p for p in s.packages() if s.flyable(p)), None)
        if p or s.state.status != "ACTIVE":
            return p
        advance(s)
    return None


def _fixed_ids(name: str) -> None:
    """Campaign ids are random (they seed the day plan and the site layouts), so a seeded check could pass or fail by luck. Each check gets
    the same run of ids every time, whatever ran before it."""
    import random as _r
    import uuid as _u
    rng = _r.Random(name)
    _u.uuid4 = lambda: _u.UUID(int=rng.getrandbits(128), version=4)


BUILD_CASES = [("F-16C", 3, 7), ("F-15C", 3, 3), ("FA-18C", 2, 11), ("A-10C", 1, 5), ("F-14BU", 2, 9), ("A-10A", 1, 5), ("F-14B", 2, 9), ("A-10C2", 1, 5)]
_built = None


def builds():
    """Lazy, runs once: [(aircraft, session, packages, miz_bytes)]. Every session writes the same SQE_Sortie.miz, so the bytes are read straight after each fly."""
    global _built
    if _built is None:
        _fixed_ids("build-set")
        _built = []
        for ac, lv, seed in BUILD_CASES:
            s = fresh_session(lv, seed, ac)
            pk = first_flyable(s)
            pkgs, miz = s.packages(), None
            if pk:
                s.fly(pk.number, s.flyable(pk)[0].id)
                miz = Path(s.state.pending["miz"]).read_bytes()
            else:
                print(f"[{ac}] nothing to fly in the first turns (not a failure)")
            _built.append((ac, s, pkgs, miz))
    return _built


def _mission(miz):
    z = zipfile.ZipFile(BytesIO(miz))
    return z, lua.loads(z.read("mission").decode("utf-8"))["mission"]


def _air_groups(M):
    """[(group, is_player_group)] for every plane and helicopter group of both coalitions."""
    out = []
    for coal in M["coalition"].values():
        for country in coal["country"].values():
            for kind in ("plane", "helicopter"):
                for g in ((country.get(kind) or {}).get("group") or {}).values():
                    out.append((g, any(u.get("skill") in ("Player", "Client") for u in g["units"].values())))
    return out


# ---- 1. loads, saves, campaigns, compatibility ---------------------------------------------------------------------------------------------------
def check_saves_round_trip():
    for level, seed in ((1, 1), (2, 2), (3, 3)):
        s = fresh_session(level, seed)
        s.save()
        r = mk()
        r.open(s.path)
        assert (r.state.campaign_id, r.state.level, clock(r)) == (s.state.campaign_id, s.state.level, clock(s)), "campaign id, level and clock survive a reload"
        assert sorted(r.state.squadrons) == sorted(s.state.squadrons), "squadrons survive a reload"
        assert [p.number for p in r.packages()] == [p.number for p in s.packages()], "packages survive a reload"
    s = fresh_session(2, 2)                                                  # S88 R3: Tactical Edge is per campaign; a save from before holds the two switches under their old names
    for k in ("tactical_edge", "tactical_edge_decay"):
        s.state.ground.pop(k, None)
    s.state.ground.update({"pilot_influence": False, "tempo_decay": True})
    s.save()
    r = mk()
    r.open(s.path)
    assert (r.state.ground.get("tactical_edge"), r.state.ground.get("tactical_edge_decay")) == (False, True), "an old save's two Tactical Edge switches load under their new names"
    assert "pilot_influence" not in r.state.ground and "tempo_decay" not in r.state.ground, "...and the old names are gone"
    s = fresh_session(2, 2)                                                  # S103a: Era Equipment is saved with the campaign; a save from before holds none of the three and loads as A-10C / F-14B(U) / Link 16 on
    assert (s.state.a10_variant, s.state.f14_variant, s.state.link16) == ("A-10C", "F-14BU", True), "a new Caucasus campaign has the 2006 era equipment"
    s.state.link16 = False
    s.save()
    r = mk()
    r.open(s.path)
    assert r.state.link16 is False, "the Link 16 switch survives a reload"
    d_ = json.loads(Path(s.path).read_text(encoding="utf-8"))
    for k in ("a10_variant", "f14_variant", "link16"):
        d_.pop(k)
    Path(s.path).write_text(json.dumps(d_), encoding="utf-8")
    r = mk()
    r.open(s.path)
    assert (r.state.a10_variant, r.state.f14_variant, r.state.link16) == ("A-10C", "F-14BU", True), "an old save without the era keys loads with today's equipment"
    s = fresh_session(3, 3)                                                  # S192: HAVCAP became HVAACAP; an old save holds the guard flights' tags, their task text and the guard squadrons' role under the old name
    s.skip_turn()
    s.save()
    saved_text = Path(s.path).read_text(encoding="utf-8")
    assert "HVAACAP" in saved_text, "a new save names the guard flights HVAACAP (the check needs a campaign that has guards planned)"
    old_text = saved_text.replace("TKR_HVAACAP", "TKR_HAVCAP").replace("HVAACAP", "HAVCAP").replace('"role": "hvaacap"', '"role": "havcap"')
    assert '"role": "havcap"' in old_text and "HVAACAP" not in old_text, "the test rewrote the save to the old names"
    Path(s.path).write_text(old_text, encoding="utf-8")
    r = mk()
    r.open(s.path)
    reopened_text = json.dumps(r.state.to_dict())
    assert "HAVCAP" not in reopened_text and "havcap" not in reopened_text, "an old save's HAVCAP tags, task text and squadron role are renamed on load"
    assert any(q.role == "hvaacap" for q in r.state.squadrons.values()), "...and the guard squadron keeps its role under the new name"
    (TMP / "appdata" / "SQE").mkdir(parents=True, exist_ok=True)           # an old settings.json with the two keys loads, and they are not kept
    (TMP / "appdata" / "SQE" / "settings.json").write_text('{"pilot_influence": false, "tempo_decay": true}')
    from sqe.settings import AppSettings as _AS
    assert not hasattr(_AS.load(), "pilot_influence"), "an old settings file's Tactical Edge keys are ignored"
    (TMP / "appdata" / "SQE" / "settings.json").unlink()
    print("[saves] levels 1 to 3: new campaign, save, reopen in a new session: the same campaign; an old save's Tactical Edge keys are renamed on load; Era Equipment saved, an old save gets the 2006 defaults")


def check_incompatible_saves():
    """A save this build cannot open raises SaveIncompatible (older / newer / damaged), never a raw traceback; the open campaign stays open;
    the backup copies the file and leaves the original alone; a good save loads with no fuss."""
    from sqe import COMPAT_ERA
    from sqe.state import SaveIncompatible
    s = fresh_session(2, 3)
    s.save()
    d = json.loads(Path(s.path).read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(dir=TMP))

    def put(name, dd):
        p = tmp / name
        p.write_text(dd if isinstance(dd, str) else json.dumps(dd), encoding="utf-8")
        return p
    cur = s.state
    cases = {"old_ground": ({**d, "ground": {**d["ground"], "v": 1}, "app_version": "0.41.150"}, "older"),
             "format3": ({**d, "format": 3}, "older"), "format6": ({**d, "format": 6, "compat": 1}, "older"),       # v0.41.334: the refit clock (format 7) refuses older saves
             "format6_unstamped": ({k: v for k, v in {**d, "format": 6}.items() if k != "compat"}, "older"), "newer_era": ({**d, "compat": COMPAT_ERA + 1, "app_version": "0.99.0"}, "newer"),
             "newer_fmt": ({**d, "format": 99}, "newer"), "broken": ({k: v for k, v in d.items() if k != "assets"}, "older"), "junk": ("not json {{", "damaged")}
    for nm, (dd, kind) in cases.items():
        try:
            s.open(put(nm + ".sqe", dd))
        except SaveIncompatible as e:
            assert e.kind == kind, (nm, e.kind, kind)
            e.info()
        else:
            raise AssertionError(f"{nm}: should not open")
        assert s.state is cur, "a refused save leaves the open campaign open"
    bad = put("bak.sqe", cases["old_ground"][0])
    before = bad.read_text(encoding="utf-8")
    dst = s.backup_incompatible(bad)
    assert dst.exists() and dst.read_text(encoding="utf-8") == before and bad.read_text(encoding="utf-8") == before, "the backup is a copy; the original is untouched"
    s.open(s.path)                                                       # a good save opens with no dialog
    print(f"[incompatible saves] {len(cases)} bad saves refused, the open campaign stayed open; backup copied")


def check_syria_theatre():
    """S90 J7: the Syria pack is a second theatre. A Syria campaign is created, saved and reopened at levels 1 to 3 (the reopened one is Syria again), one mission builds at each level and its package carries the
    flight of its first job, and the new-campaign dialog lists both theatres and follows the picked one (era defaults). The Caucasus is active again afterwards."""
    from sqe import theatres
    from sqe.packages import PackageBuilder
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from sqe.gui.dialogs import NewCampaignDialog
    _fixed_ids("syria-theatre")
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    try:
        assert "syria" in theatres.available() and "caucasus" in theatres.available(), "both theatre packs are listed"
        for level, seed in ((1, 5), (2, 5), (3, 7)):
            s = mk()
            s.new(f"Smoke Syria {level}", "F-16C", level, seed=seed, theatre="syria")
            s.save()
            theatres.use("caucasus")
            r = mk()
            r.open(s.path)
            assert theatres.active()["id"] == "syria" and r.state.theatre == "syria", "a reopened Syria campaign activates its theatre"
            assert r.state.campaign_id == s.state.campaign_id, "the same campaign after a reload"
            pk = first_flyable(r)
            assert pk is not None, f"level {level}: nothing to fly"
            r.fly(pk.number, r.flyable(pk)[0].id)
            assert Path(r.state.pending["miz"]).read_bytes()[:2] == b"PK", f"level {level}: the .miz is not a zip"
            job = PackageBuilder(r.state)._slots(pk.objective, False, 0, pk.extra)[0].role
            assert any(f.role == job and not f.tag for f in pk.flights), f"level {level}: the package has no flight for its first job"
        from PySide6.QtWidgets import QMessageBox
        from sqe.gui import theme
        from sqe.gui.app import MainWindow
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.warning = staticmethod(lambda *a, **k: None)
        QApplication.instance().setStyleSheet(theme.QSS)
        ses = mk()
        ses.new("Smoke Syria window", "F-16C", 3, seed=7, theatre="syria")
        w = MainWindow(ses)                                                      # the main window (map included) builds on a Syria campaign
        w.refresh_all()
        w.show()
        for i in range(w.stack.count()):
            w.stack.setCurrentIndex(i)
            QApplication.instance().processEvents()
        w.hide()
        theatres.use("caucasus")
        dlg = NewCampaignDialog(None, "rain")
        ids = [dlg.th.itemData(i) for i in range(dlg.th.count())]
        assert "syria" in ids and "caucasus" in ids, "the dialog lists both theatres"
        dlg.th.setCurrentIndex(ids.index("syria"))
        v = dlg.values()
        assert v["theatre"] == "syria" and v["start_date"].startswith(str(theatres.era("syria")["year"])), "the dialog follows the picked theatre"
    finally:
        theatres.use("caucasus")
    print("[syria] a Syria campaign is created, saved and reopened at levels 1 to 3; one mission builds at each; the main window shows on a Syria campaign; the dialog lists both theatres")


def check_ecm_install():
    """The ECM export script installs itself (copy + one marked line at the end of Export.lua), removes cleanly, never touches other lines or line
    endings, backs Export.lua up once. It writes to a file outside SQE, so XO keeps it as critical."""
    from sqe import settings as S
    with tempfile.TemporaryDirectory() as td:
        sv = str(Path(td) / "DCS")
        Path(sv).mkdir()
        assert S.ecm_script_state(sv) == "none" and S.ecm_script_state("") == "nofolder"
        ok, _m = S.install_ecm_script(sv)
        assert ok
        ex, sc = Path(sv, "Scripts", "Export.lua"), Path(sv, "Scripts", "sqe_ecm_export.lua")
        assert ex.read_text() == S.ECM_LINE + "\n" and sc.exists() and S.ecm_script_state(sv) == "ok", ex.read_text()
        S.install_ecm_script(sv)
        assert ex.read_text().count("sqe_ecm_export") == 1                   # twice = still one line
        assert S.remove_ecm_script(sv)[0] and not sc.exists() and S.ecm_script_state(sv) == "none"
        assert ex.read_text().strip() == "", repr(ex.read_text())
        orig = b"-- tacview\r\ndofile(lfs.writedir()..[[Scripts\\TacviewGameExport.lua]])"      # CRLF, no trailing newline
        ex.write_bytes(orig)
        S.install_ecm_script(sv)
        assert ex.read_bytes() == orig + b"\r\n" + S.ECM_LINE.encode() + b"\r\n", ex.read_bytes()
        assert Path(sv, "Scripts", "Export.lua.sqe.bak").read_bytes() == orig
        sc.write_text("-- old copy")
        assert S.ecm_script_state(sv) == "old"
        S.install_ecm_script(sv)
        assert S.ecm_script_state(sv) == "ok"
        S.remove_ecm_script(sv)
        assert ex.read_bytes() == orig + b"\r\n", ex.read_bytes()            # our line gone, theirs untouched
        ex.write_bytes(orig + b"\r\ndofile(lfs.writedir() .. [[Scripts\\sqe_ecm_export.lua]])\r\n")     # a hand-made line counts as installed
        S.install_ecm_script(sv)
        assert ex.read_bytes().count(b"sqe_ecm_export") == 1
    print("[ecm install] install / twice / remove / CRLF / backup / old copy / hand line")


def fake_debrief(s):
    """Write a fake state file for the pending sortie (a few dead, one kill) and poll it. -> (status, data) as `s.poll()` gives them; the caller applies."""
    man = s.manifest()
    prim = next((g for g in man.groups if g["kind"] == "asset" and g.get("primary")), None)
    dead = prim["units"][: int(len(prim["units"]) * 0.6)] if prim else []
    data = {"campaign": man.campaign_id, "sortie": man.sortie, "package": man.package_id, "mission_ended": True, "time": 2400, "dead": dead, "ejected": [],
            "landed": [man.player_unit], "player": {"takeoff": 300, "landed": 2300, "ka": 1, "kg": 2, "ks": 0},
            "kills": [{"k": man.player_unit, "kt": "Test", "v": (dead or ["x"])[0], "vt": "TargetType", "w": "AIM-120C", "t": 725}]}
    s.settings.state_file.write_text(json.dumps(data))
    status, got, _tl = s.poll()
    return status, got


def check_fly_debrief_advance():
    """The core loop on the first built jet: fake state file -> poll ok -> apply (clock moves, the pilot log counts the sortie) -> reload -> skip (clock moves)."""
    s = next((b[1] for b in builds() if b[3]), None)
    assert s is not None, "no jet built a mission"
    t0, sorties0 = clock(s), (s.state.pilot or {}).get("sorties", 0)
    status, got = fake_debrief(s)
    assert status == "ok", status
    s.apply(got)
    assert clock(s) != t0, "the campaign did not advance after the debrief"
    assert s.state.pilot["sorties"] > sorties0, "the pilot log did not count the sortie"
    r = mk()
    r.open(s.path)
    assert clock(r) == clock(s) and r.state.pilot["sorties"] == s.state.pilot["sorties"], "the reload differs from the saved campaign"
    t1 = clock(r)
    advance(r)
    assert clock(r) != t1, "skipping did not advance the campaign"
    print("[fly] fake sortie -> poll -> debrief -> reload -> skip: the clock moved each time")


# ---- 2. the dialogs build -----------------------------------------------------------------------------------------------------------------------
def check_dialogs():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    from sqe.gui.dialogs import NewCampaignDialog, SettingsDialog
    (TMP / "gsv").mkdir(exist_ok=True)
    QMessageBox.information = staticmethod(lambda *a, **k: None)         # a message box would wait for a click
    dlg = SettingsDialog(AppSettings(dcs_saves=str(TMP / "gsv"), persist=False))
    dlg._save()
    assert NewCampaignDialog(None, "rain").values(), "the new-campaign dialog gives its values"
    print("[gui] settings and new-campaign dialogs build; save and values run")


def check_main_window():
    """The main window builds on a fresh campaign, refreshes and shows every page of its stack without an exception. No labels, tabs or row counts."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    from sqe.gui import theme
    from sqe.gui.app import MainWindow
    QMessageBox.information = staticmethod(lambda *a, **k: None)         # a message box would wait for a click
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    app.setStyleSheet(theme.QSS)
    w = MainWindow(fresh_session(2, 3))
    w.refresh_all()
    w.show()
    for i in range(w.stack.count()):
        w.stack.setCurrentIndex(i)
        app.processEvents()
    w.hide()                                                  # not close(): a save prompt would wait for a click
    print(f"[gui] the main window refreshes and shows its {w.stack.count()} pages")


# ---- 3. missions are generated ----------------------------------------------------------------------------------------------------------------
def check_missions_build():
    got = [(ac, miz) for ac, _s, _p, miz in builds() if miz]
    assert got, "no jet built a mission"
    for ac, miz in got:
        assert miz[:2] == b"PK", (ac, "the .miz is not a zip")
    print(f"[missions] built a .miz for {len(got)} of {len(BUILD_CASES)} jets: " + ", ".join(ac for ac, _ in got))


def check_required_flights():
    """Every stored package carries a flight for the job the planner lists first for its objective (a package with only support flights is broken)."""
    from sqe.packages import PackageBuilder
    n = 0
    for ac, s, pkgs, _miz in builds():
        for p in pkgs:
            job = PackageBuilder(s.state)._slots(p.objective, False, 0, p.extra)[0].role
            assert any(f.role == job and not f.tag for f in p.flights), (ac, p.number, p.objective.description, job)
            n += 1
    print(f"[packages] {n} stored packages each carry their first job's flight")


# ---- 5. the .miz structure loads in DCS without errors ------------------------------------------------------------------------------------------
def check_miz_parses():
    for ac, _s, _p, miz in builds():
        if not miz:
            continue
        z, M = _mission(miz)
        assert z.testzip() is None, (ac, "damaged zip")
        need = ["mission", "options", "warehouses", "theatre", "l10n/DEFAULT/dictionary", "l10n/DEFAULT/mapResource"]
        assert all(n in z.namelist() for n in need), (ac, [n for n in need if n not in z.namelist()])
        for n in need:
            if n == "theatre":
                assert z.read(n).strip(), (ac, "empty theatre")
            else:
                lua.loads(z.read(n).decode("utf-8"))                     # DCS reads these as Lua
        assert any(player for _g, player in _air_groups(M)), (ac, "no player slot")
    print("[miz] zip sound, members present, Lua parses, a player slot exists")


def _lock_problems(M, label):
    """DESIGN_NOTES section 8: the Mission Editor refuses a route that breaks a lock rule. A: no run of speed-locked points between two time-locked ones, the
    second time-locked point INCLUDED (the Editor counts it: "(2-2) ... surrounded by 1 and 2"). B: every point after the last time-locked one is time- or
    speed-locked. C (player group only): a point with both free needs a time-locked point on each side. Returns [message] and the group count."""
    bad, n = [], 0
    for g, player in _air_groups(M):
        pts = ((g.get("route") or {}).get("points")) or {}
        seq = [pts[k] for k in sorted(pts)]
        names = [str(p.get("name", "")) for p in seq]
        L = [i for i, p in enumerate(seq) if p.get("ETA_locked")]
        for a, b in zip(L, L[1:]):
            mid = seq[a + 1:b + 1]                               # the second locked-time point is part of the run
            if mid and all(p.get("speed_locked") for p in mid):
                bad.append(f"{label} {g['name']}: A, locked speeds between locked times, points {a + 1}-{b + 1} of {names}")
        for i in range(L[-1] + 1 if L else 1, len(seq)):
            if not seq[i].get("ETA_locked") and not seq[i].get("speed_locked"):
                bad.append(f"{label} {g['name']}: B, free speed and time after the last locked time, point {i + 1} of {names}")
        if player:
            for i, p in enumerate(seq):
                if not p.get("ETA_locked") and not p.get("speed_locked"):
                    if not (any(j < i for j in L) and any(j > i for j in L)):
                        bad.append(f"{label} {g['name']}: C, free speed and time, not between locked times, point {i + 1} of {names}")
        n += 1
    return bad, n


LOCK_CASES = [("F-16C", 3, 7, False), ("F-16C", 3, 7, True), ("F-15C", 3, 3, True), ("FA-18C", 2, 11, False), ("F-14BU", 3, 9, True)]   # (jet, level, seed, SAMs zeroed): open skies brings out strikes, counter-air, escorts and sweeps
LOCK_TURNS = 6                                                # a plan is one turn's tasking: walk a few turns so every kind of package turns up


def lock_builds(cases=None):
    """Lazy, runs once: [(label, miz_bytes)] for one package of every kind the plan offers (objective type and aim), built as the player's own flight and as the
    all-AI test (your flight gets the full AI task set), plus the BARCAP / fleet-defence / sweep packages nobody can fly (the first flight stands in for yours).
    With `cases` (a subset of LOCK_CASES, S124: one case per worker) it builds just those, uncached."""
    global _lock_built
    if cases is not None or _lock_built is None:
        _fixed_ids("lock-sweep")
        import random
        keep = _lock_built
        _lock_built = []
        for ac, lv, seed, opened in (LOCK_CASES if cases is None else cases):
            s = fresh_session(lv, seed, ac)
            if opened:
                for a in s.state.assets.values():
                    if a.kind.value == "SAM":
                        a.health = 0.0
                s.plan_day()
            seen = set()
            for _t in range(LOCK_TURNS):
                if s.state.status != "ACTIVE":
                    break
                for p in s.packages():
                    kind = (p.objective.type, p.objective.aim)
                    fly = bool(s.flyable(p))
                    modes = (False, True) if fly else ((True,) if p.flights else ())
                    for ai in modes:
                        if (kind, ai, fly) in seen:
                            continue
                        seen.add((kind, ai, fly))
                        s.ai_test = ai
                        s.state.turn = s._turn_of(p)                  # the builder works from the package's own turn
                        random.seed(f"{ac}:{p.number}:{ai}")
                        try:
                            s.fly(p.number, (s.flyable(p)[0] if fly else p.flights[0]).id)
                            miz = Path(s.state.pending["miz"]).read_bytes()
                        except NoPlayerSlot:                             # a package no flight of which your jet can stand in for: nothing to build
                            continue
                        except Exception as e:                           # any other build that raises is a failure of its own, reported by the check
                            _lock_built.append((f"{ac} L{lv} {p.objective.type.value}/{p.objective.aim} {'all-AI' if ai else 'player'}", e))
                            continue
                        _lock_built.append((f"{ac} L{lv} {p.objective.type.value}/{p.objective.aim} {'all-AI' if ai else 'player'}", miz))
                advance(s)
        if cases is not None:                                     # a subset is not cached
            part, _lock_built = _lock_built, keep
            return part
    return _lock_built


_lock_built = None


def lock_part(part):
    """The lock rules on one part of the sweep: part None = the jets' own missions (`builds()`), an int = that LOCK_CASES entry (S124: one part per worker). -> (problems, groups checked, package builds)."""
    bad, n, m = [], 0, 0
    if part is None:
        for ac, _s, _p, miz in builds():
            if miz:
                b, k = _lock_problems(_mission(miz)[1], ac)
                bad += b; n += k
        return bad, n, m
    for label, miz in lock_builds([LOCK_CASES[part]]):
        assert not isinstance(miz, Exception), (label, "the build raised", repr(miz))
        b, k = _lock_problems(_mission(miz)[1], label)
        bad += b; n += k; m += 1
    return bad, n, m


def lock_report(parts):
    """Assert and print for the merged results of `lock_part`."""
    bad = [x for p in parts for x in p[0]]
    n, m = sum(p[1] for p in parts), sum(p[2] for p in parts)
    assert not bad, "; ".join(bad[:12]) + (f"; ... {len(bad) - 12} more" if len(bad) > 12 else "")
    print(f"[locks] rules A, B (and C on the player's groups) on {n} plane and helicopter groups, {m} package builds (one per kind of package, player and all-AI)")


def check_waypoint_locks():
    """The lock rules (see `_lock_problems`) on every plane and helicopter group of the five jets' missions and of one mission per kind of package, player and all-AI."""
    lock_report([lock_part(p) for p in [None] + list(range(len(LOCK_CASES)))])


def check_hook_lua():
    """The real built hook compiles and survives hit / eject / dead events under the stub DCS (tools/hook_lua_sim.py). Catches a local declared after the
    code that reads it ("attempt to index global 'DMGL'"). Needs lupa (dev only)."""
    try:
        import lupa  # noqa: F401
    except ImportError:
        print("[hook] SKIPPED: lupa is not installed")
        LUA_SKIPPED.append(True)
        return
    import hook_lua_sim

    def find(o):
        if isinstance(o, dict):
            if o.get("predicate") == "a_do_script" and "SQE debrief hook" in str(o.get("text", "")):
                return o["text"]
            o = list(o.values())
        for v in (o if isinstance(o, list) else ()):
            r = find(v)
            if r:
                return r
    n = 0
    for ac, _s, _p, miz in builds():
        if not miz:
            continue
        hook = find(_mission(miz)[1]["trigrules"])
        assert hook, (ac, "hook script not found in the mission's triggers")
        assert not hook.startswith("DictKey_"), (ac, "the hook is embedded as a dictionary key, not as code")
        r = hook_lua_sim.run(hook)
        assert not r.startswith(("COMPILE:", "RUN:")), (ac, r[:300])
        first = r.split(" | ")[0]
        assert not (first.startswith("EVENT ERRORS") and "global '" in first), (ac, first[:300])
        n += 1
    print(f"[hook] {n} real hooks compile and run under the stub DCS")


def _mission_scripts(node, found):
    """Every script text in a mission table: a trigger's "do script" action and a waypoint's "Script" command."""
    if isinstance(node, dict):
        if node.get("predicate") == "a_do_script":
            found.append(str(node.get("text", "")))
        if node.get("id") == "Script":
            command = (node.get("params") or {}).get("command")
            if command:
                found.append(str(command))
        for value in node.values():
            _mission_scripts(value, found)
    elif isinstance(node, list):
        for value in node:
            _mission_scripts(value, found)
    return found


def check_mission_lua():
    """Every script in every built mission compiles in Lua 5.1, the version DCS runs: a syntax error is an error popup in the game. Compile only,
    nothing is run. Needs lupa (dev only)."""
    try:
        from lupa import lua51
    except ImportError:
        print("[mission lua] SKIPPED: lupa (with Lua 5.1) is not installed")
        LUA_SKIPPED.append(True)
        return
    runtime = lua51.LuaRuntime()
    compile_error = runtime.eval("function(code) local chunk, problem = loadstring(code) if chunk then return '' end return problem end")
    total = 0
    for ac, _s, _p, miz in builds():
        if not miz:
            continue
        z, M = _mission(miz)
        dictionary_text = z.read("l10n/DEFAULT/dictionary").decode("utf-8")
        dictionary = lua.loads(dictionary_text)["dictionary"]
        scripts = _mission_scripts(M, [])
        assert scripts, (ac, "no scripts found in the mission")
        for script in scripts:
            if script.startswith("DictKey_"):                          # the text is kept in the dictionary
                script = dictionary[script]
            problem = compile_error(script)
            assert not problem, (ac, problem, script[:300])
            total += 1
    print(f"[mission lua] {total} mission scripts compile")


# ---- 6. soak (in the default run; `--only soak` alone) ------------------------------------------------------------------------------------------------------------
SOAK_CASES = [("caucasus", 1, 5), ("caucasus", 2, 3), ("caucasus", 3, 7), ("syria", 1, 2), ("syria", 2, 4), ("syria", 3, 6)]      # (theatre, level, seed); S126: Syria has paths the Caucasus never runs (works rebuild, grace week, opening strike, carrier evade)
SOAK_MAX_SKIPS = 300                                          # a loop bound, not a game rule
SOAK_FLY_EVERY = 20                                           # every N skips the player flies a fake sortie, if anything is flyable
SOAK_RELOAD_EVERY = 25                                        # every N skips: save, reopen, carry on with the reopened session
SOAK_SEEDS = 1                                                # `--seeds N`: each level runs N seeds (seed, seed+1, ...)


def soak_case(theatre, level, seed):
    """One soak campaign: skip to the end of the war."""
    from sqe import theatres
    s, n = fresh_session(level, seed, theatre=theatre), 0
    try:
        while n < SOAK_MAX_SKIPS and s.state.status == "ACTIVE":
            s.skip_turn()
            n += 1
            if n % SOAK_FLY_EVERY == 0:
                pk = first_flyable(s)
                if pk is not None:
                    s.fly(pk.number, s.flyable(pk)[0].id)
                    _status, got = fake_debrief(s)
                    s.apply(got)
            if n % SOAK_RELOAD_EVERY == 0 and s.state.status == "ACTIVE":
                s.save()
                r = mk()
                r.open(s.path)
                s = r
    except BaseException:
        print(f"[soak] FAILED: {theatre} level {level}, seed {seed}, skip {n + 1}  (replay: --only soak, {theatre} level {level} seed {seed})")
        raise
    finally:
        theatres.use("caucasus")
    print(f"[soak] {theatre} level {level} seed {seed}: {n} skips, final status {s.state.status}")


def check_soak():
    """Skip to the end of the war on five campaigns (three Caucasus, two Syria). The ONLY assert is "no exception": a failure prints theatre, level, seed and skip number, then re-raises."""
    for theatre, level, seed0 in SOAK_CASES:
        for seed in range(seed0, seed0 + SOAK_SEEDS):
            soak_case(theatre, level, seed)


OPT_IN = []                                                   # checks that run only when `--only` names them (none now)


CHECKS = [
    check_saves_round_trip,
    check_incompatible_saves,
    check_syria_theatre,
    check_ecm_install,
    check_fly_debrief_advance,
    check_dialogs,
    check_main_window,
    check_missions_build,
    check_required_flights,
    check_miz_parses,
    check_waypoint_locks,
    check_hook_lua,
    check_mission_lua,
    check_soak,
]


# ---- parallel run (S124) ----------------------------------------------------------------------------------------------------------------------------
# Checks that share the five-jet build (`builds()`) stay together in one process (it is built once there); the rest run on their own, and the soak is one task per campaign.
GROUPS = [["check_saves_round_trip"], ["check_incompatible_saves"], ["check_syria_theatre"], ["check_ecm_install"], ["check_dialogs", "check_main_window"],
          ["check_fly_debrief_advance", "check_missions_build", "check_required_flights", "check_miz_parses", "check_hook_lua", "check_mission_lua"]]
LOCK_PARTS = [None] + list(range(len(LOCK_CASES)))              # check_waypoint_locks: one task per part


def _timeout_for(name, override):
    return override if override is not None else (900 if name == "check_soak" else 120)


def _run_task(task):
    """In a worker (or the parent): run one task, print into a buffer, return {name: [text, seconds, error or None]} for each check (the soak: key "check_soak|theatre|level|seed"). A watchdog
    per check as in the serial run; a failed check stops its task and its traceback is returned."""
    import contextlib
    import faulthandler
    import io
    import time
    import traceback
    kind, names, args, timeout = task
    out = {}
    jobs = [(n, None) for n in names] if kind == "checks" else [("check_soak" if kind == "soak" else "check_waypoint_locks", args)]
    for name, soak in jobs:
        buf = io.StringIO()
        t0, err = time.time(), None
        to = _timeout_for(name, timeout)
        if to:
            faulthandler.dump_traceback_later(to, exit=True)
        payload = None
        key = name if soak is None else (f"{name}|{soak[0]}|{soak[1]}|{soak[2]}" if kind == "soak" else f"{name}|{-1 if soak[0] is None else soak[0]}")
        try:
            with contextlib.redirect_stdout(buf):
                _fixed_ids(key)
                if soak is None:
                    globals()[name]()
                elif kind == "soak":
                    soak_case(*soak)
                else:
                    payload = lock_part(soak[0])
        except BaseException:
            err = traceback.format_exc()
        faulthandler.cancel_dump_traceback_later()
        out[key] = [buf.getvalue(), time.time() - t0, err, payload]
        if err:
            break
    out["_lua_skipped"] = [bool(LUA_SKIPPED), 0.0, None, None]
    return out


def _worker_init():
    import atexit
    atexit.register(shutil.rmtree, TMP, True)                 # a worker's own temp data goes with it


def _key_order(k):
    """Print order of a check's task keys: the soak's by SOAK_CASES order (theatre, then level, seed), the lock sweep's by part number."""
    parts = k.split("|")[1:]
    if parts and not parts[0].lstrip("-").isdigit():
        order = [c[0] for c in SOAK_CASES]
        return [order.index(parts[0]) if parts[0] in order else len(order)] + [int(x) for x in parts[1:]]
    return [int(x) for x in parts]


def run_parallel(selected, jobs, timeout):
    """Run the selected checks over worker processes and print their output in CHECKS order. -> True when every check passed."""
    import concurrent.futures
    import multiprocessing
    import time
    names = [fn.__name__ for fn in selected]
    tasks = [("checks", [n for n in g if n in names], None, timeout) for g in GROUPS if any(n in names for n in g)]
    if "check_soak" in names:
        tasks += [("soak", [], (theatre, level, seed), timeout) for theatre, level, seed0 in SOAK_CASES for seed in range(seed0, seed0 + SOAK_SEEDS)]
    if "check_waypoint_locks" in names:
        tasks = [("lock", [], (p,), timeout) for p in LOCK_PARTS] + tasks              # the longest check first, so its parts start at once
    workers = max(1, min(jobs, len(tasks)))
    print(f"running {len(tasks)} tasks on {workers} worker(s)")
    t0 = time.time()
    results = {}
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"), initializer=_worker_init) as ex:
            for res in ex.map(_run_task, tasks):
                results.update(res)
    except concurrent.futures.process.BrokenProcessPool:
        print("a worker process died (a check hit its timeout or crashed the interpreter): run that check alone with --only to see the traceback")
        return False
    ok, times = True, []
    for n in names:
        keys = [k for k in results if k == n or k.startswith(n + "|")]
        parts = []
        for k in sorted(keys, key=_key_order):
            text, secs, err, payload = results[k]
            print(text, end="")
            times.append((secs, k))
            if err:
                print(err)
                ok = False
            if payload is not None:
                parts.append(payload)
        if n == "check_waypoint_locks" and parts and len(parts) == len(LOCK_PARTS):      # merge the parts and report as the serial check does
            import contextlib
            import io
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    lock_report(parts)
            except AssertionError:
                import traceback
                print(traceback.format_exc())
                ok = False
            print(buf.getvalue(), end="")
        if not keys:
            print(f"[{n}] not run: an earlier check of its group failed")
    if results.get("_lua_skipped", [False])[0]:
        LUA_SKIPPED.append(True)
    print(f"{len(tasks)} tasks on {workers} worker(s), {time.time() - t0:.0f} s wall time; " + "slowest checks: " + ", ".join(f"{n} {t:.0f} s" for t, n in sorted(times, reverse=True)[:5]))
    return ok


def main(argv=None):
    """Run the checks in order. Options: `--list` (names only), `--only a,b` (the checks whose name contains a or b), `--timeout SECONDS` (a check that
    runs longer dumps every thread's traceback and stops the run; default 120, 900 for the soak, 0 = off), `--seeds N` (soak: N seeds per level),
    `--jobs N` (worker processes, default the cores minus two; 1 = everything in this process, the old serial run)."""
    import argparse
    import faulthandler
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=None)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=None)
    args = ap.parse_args(argv)
    global SOAK_SEEDS
    SOAK_SEEDS = max(1, args.seeds)
    if args.list:
        print("\n".join([fn.__name__ for fn in CHECKS] + [fn.__name__ + " (opt-in)" for fn in OPT_IN]))
        return
    sys.stdout.reconfigure(line_buffering=True)                  # output reaches a log file at once, so a stall shows where it is
    print(f"SQE smoke test, version {sqe.__version__}  (isolated temp data: {TMP})")
    want = [w for w in args.only.split(",") if w]
    run = [fn for fn in CHECKS + OPT_IN if (want and any(w in fn.__name__ for w in want)) or (not want and fn in CHECKS)]
    jobs = args.jobs if args.jobs is not None else max(1, (os.cpu_count() or 2) - 2)
    if jobs > 1 and len(run) > 1:                                # S124: the default run goes over the cores
        ok = run_parallel(run, jobs, args.timeout)
        if not ok:
            sys.exit(1)
        if not want:
            print("SMOKE TEST PASSED" + (" (Lua hook not run: lupa is not installed)" if LUA_SKIPPED else ""))
        return
    times = []
    for fn in run:
        timeout = args.timeout if args.timeout is not None else (900 if fn is check_soak else 120)      # the soak needs its own, longer watchdog
        if timeout:
            faulthandler.dump_traceback_later(timeout, exit=True)
        t0 = time.time()
        _fixed_ids(fn.__name__)
        fn()
        times.append((time.time() - t0, fn.__name__))
    faulthandler.cancel_dump_traceback_later()
    print("slowest checks: " + ", ".join(f"{n} {t:.0f} s" for t, n in sorted(times, reverse=True)[:5]))
    if not want:
        print("SMOKE TEST PASSED" + (" (Lua hook not run: lupa is not installed)" if LUA_SKIPPED else ""))


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
