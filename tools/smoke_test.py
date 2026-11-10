"""Headless core-function test (no DCS). Run:  python tools/smoke_test.py   (options: --list, --only a,b, --timeout SECONDS)
Isolated: a temporary folder for everything, APPDATA redirected, your real settings and campaigns are never touched; the temp data is deleted at the end.
Scope (XO 2026-11-06, see .claude/smoke test plan.md): (1) loads, saves, campaigns, compatibility; (2) the dialogs build; (3) missions are generated;
(5) the .miz structure loads in DCS without errors. Assert STRUCTURE, never values: no constant, no state.day value, no waypoint, job, role or kit name, no
game or hook text. An assert that ends with us changing this file instead of fixing SQE is invalid: remove it, do not relax it.
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(1, str(Path(__file__).resolve().parent))      # hook_lua_sim sits beside this file
import sqe
from dcs import lua
from sqe.engine import Session
from sqe.settings import AppSettings

mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))     # a new session on the test's temp folder
LUA_SKIPPED = []                                              # set when lupa is missing: the last line says so


def fresh_session(level=3, seed=7, ac="F-16C"):
    """A new campaign of its own for a check that needs a session."""
    ses = mk()
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    ses.new("Smoke fresh", ac, level, seed=seed)
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


BUILD_CASES = [("F-16C", 3, 7), ("F-15C", 3, 3), ("FA-18C", 2, 11), ("A-10C", 1, 5), ("F-14BU", 2, 9)]
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
    print("[saves] levels 1 to 3: new campaign, save, reopen in a new session: the same campaign")


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


def check_fly_debrief_advance():
    """The core loop on the first built jet: fake state file -> poll ok -> apply (clock moves, the pilot log counts the sortie) -> reload -> skip (clock moves)."""
    s = next((b[1] for b in builds() if b[3]), None)
    assert s is not None, "no jet built a mission"
    man, t0, sorties0 = s.manifest(), clock(s), (s.state.pilot or {}).get("sorties", 0)
    prim = next((g for g in man.groups if g["kind"] == "asset" and g.get("primary")), None)
    dead = prim["units"][: int(len(prim["units"]) * 0.6)] if prim else []
    data = {"campaign": man.campaign_id, "sortie": man.sortie, "package": man.package_id, "mission_ended": True, "time": 2400, "dead": dead, "ejected": [],
            "landed": [man.player_unit], "player": {"takeoff": 300, "landed": 2300, "ka": 1, "kg": 2, "ks": 0},
            "kills": [{"k": man.player_unit, "kt": "Test", "v": (dead or ["x"])[0], "vt": "TargetType", "w": "AIM-120C", "t": 725}]}
    s.settings.state_file.write_text(json.dumps(data))
    status, got, _tl = s.poll()
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


# ---- 3. missions are generated ----------------------------------------------------------------------------------------------------------------
def check_missions_build():
    got = [(ac, miz) for ac, _s, _p, miz in builds() if miz]
    assert got, "no jet built a mission"
    for ac, miz in got:
        assert miz[:2] == b"PK", (ac, "the .miz is not a zip")
    print(f"[missions] built a .miz for {len(got)} of {len(BUILD_CASES)} jets: " + ", ".join(ac for ac, _ in got))


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
        for g, _player in _air_groups(M):                                # the ILS dummy (if the setting builds one) is a never-started ground aircraft, not a flight
            if str(g.get("name", "")).startswith("ILS dummy"):
                assert g.get("uncontrolled") and g["route"]["points"][1]["type"] == "TakeOffGround", (ac, g["name"], "dummy is not an uncontrolled ground start")
    print("[miz] zip sound, members present, Lua parses, a player slot exists, any ILS dummy is an uncontrolled ground start")


def check_waypoint_locks():
    """DESIGN_NOTES section 8: the Mission Editor refuses a route that breaks a lock rule. A: no run of speed-locked points between two time-locked
    ones. B: every point after the last time-locked one is time- or speed-locked. C (player group only): a point with both free needs a time-locked
    point on each side."""
    n = 0
    for ac, _s, _p, miz in builds():
        if not miz:
            continue
        for g, player in _air_groups(_mission(miz)[1]):
            pts = ((g.get("route") or {}).get("points")) or {}
            seq = [pts[k] for k in sorted(pts)]
            L = [i for i, p in enumerate(seq) if p.get("ETA_locked")]
            for a, b in zip(L, L[1:]):
                mid = seq[a + 1:b]
                assert not (mid and all(p.get("speed_locked") for p in mid)), (ac, g["name"], "A: locked speeds between locked times", a, b)
            for i in range(L[-1] + 1 if L else 1, len(seq)):
                assert seq[i].get("ETA_locked") or seq[i].get("speed_locked"), (ac, g["name"], "B: free speed and time after the last locked time", i)
            if player:
                for i, p in enumerate(seq):
                    if not p.get("ETA_locked") and not p.get("speed_locked"):
                        assert any(j < i for j in L) and any(j > i for j in L), (ac, g["name"], "C: free speed and time, not between locked times", i)
            n += 1
    print(f"[locks] rules A and B on {n} plane and helicopter groups, rule C on the player's groups")


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


CHECKS = [
    check_saves_round_trip,
    check_incompatible_saves,
    check_ecm_install,
    check_fly_debrief_advance,
    check_dialogs,
    check_missions_build,
    check_miz_parses,
    check_waypoint_locks,
    check_hook_lua,
]


def main(argv=None):
    """Run the checks in order. Options: `--list` (names only), `--only a,b` (the checks whose name contains a or b), `--timeout SECONDS` (a check that
    runs longer dumps every thread's traceback and stops the run; default 120, 0 = off)."""
    import argparse
    import faulthandler
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args(argv)
    if args.list:
        print("\n".join(fn.__name__ for fn in CHECKS))
        return
    sys.stdout.reconfigure(line_buffering=True)                  # output reaches a log file at once, so a stall shows where it is
    print(f"SQE smoke test, version {sqe.__version__}  (isolated temp data: {TMP})")
    want = [w for w in args.only.split(",") if w]
    run = [fn for fn in CHECKS if not want or any(w in fn.__name__ for w in want)]
    times = []
    for fn in run:
        if args.timeout:
            faulthandler.dump_traceback_later(args.timeout, exit=True)
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
