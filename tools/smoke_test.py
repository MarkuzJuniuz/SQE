"""Headless end-to-end test (no DCS, no GUI). Run:  python tools/smoke_test.py
For each flyable jet: new campaign -> plan -> FLY (build SQE_Sortie.miz) -> fake sortie results (with your kills) ->
Accept -> debrief -> next day -> save/reload. Exit code 0 and 'SMOKE TEST PASSED' = everything worked."""
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqe.aircraft import AIRCRAFT
from sqe.engine import Session
from sqe.settings import AppSettings


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sqe_test_"))
    s = Session(AppSettings(dcs_saves=str(tmp)))
    assert not s.settings.problems(), s.settings.problems()
    tested = 0
    for aircraft, spec in AIRCRAFT.items():
        if not spec.player_flyable:
            continue
        s.new(f"Smoke {aircraft}", aircraft, 2, seed=7)
        opts = [p for p in s.packages() if s.flyable(p)]
        if not opts:
            print(f"[{aircraft}] no flyable package today (fine for niche jets like the A-10)"); continue
        pk = opts[0]; fl = s.flyable(pk)[0]
        res = s.fly(pk.number, fl.id)
        assert s.settings.sortie_miz.exists(), "SQE_Sortie.miz was not written"
        z = zipfile.ZipFile(s.settings.sortie_miz)
        mission = z.read("mission").decode()
        assert "world.addEventHandler" in mission and "DictKey_Translation" not in mission.split("a_do_script")[1][:120], "hook not embedded as code"
        assert len([n for n in z.namelist() if "KNEEBOARD" in n]) == 2, "expected 2 kneeboard pages"
        print(f"[{aircraft}] {pk.objective.description} | {fl.callsign}-1 {fl.role.value} | start {pk.start} | push {res.timeline['push']} TOT {res.timeline['tot']}"
              f" | {res.counts['groups']} groups / {res.counts['units']} units | warnings: {res.warnings or 'none'}")
        man = s.manifest()
        prim = next(g for g in man.groups if g["kind"] == "asset" and g.get("primary"))
        fr = next((g for g in man.groups if g["kind"] == "friendly" and not g.get("player")), None)
        data = {"campaign": man.campaign_id, "sortie": man.sortie, "package": man.package_id, "mission_ended": True, "time": 2400,
                "dead": prim["units"][: int(len(prim["units"]) * 0.6)] + (fr["units"][:1] if fr else []), "ejected": [], "landed": [man.player_unit],
                "player": {"takeoff": 300, "landed": 2300, "ka": 1, "kg": 2, "ks": 0}}
        s.settings.state_file.write_text(json.dumps(data))
        status, got, tl = s.poll()
        assert status == "ok", status
        out = s.apply(got)
        assert s.state.day == 2 and s.state.plan, "campaign did not advance"
        assert s.state.pilot["sorties"] == 1 and s.state.pilot["kills_ground"] == 2, s.state.pilot
        print(f"    debrief: {out['story'].splitlines()[0][:110]}...  pilot: {s.state.pilot['sorties']} sortie, {s.state.pilot['kills_air']}A/{s.state.pilot['kills_ground']}G kills")
        r = Session(AppSettings(dcs_saves=str(tmp))); r.open(s.path)
        assert r.state.day == 2 and r.state.pilot["sorties"] == 1
        tested += 1
    assert tested >= 3, "too few jets tested"
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
