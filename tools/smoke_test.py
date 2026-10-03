"""Headless end-to-end test (no DCS, no GUI): new campaign -> plan -> FLY (build .miz) -> fake sortie results
-> Accept -> debrief -> next day. Run:  python tools/smoke_test.py
Exit code 0 = everything worked. A temp folder stands in for Saved Games\\DCS.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqe.engine import Session
from sqe.settings import AppSettings


def main():
    tmp = Path(tempfile.mkdtemp(prefix="sqe_test_"))
    s = Session(AppSettings(dcs_saves=str(tmp)))
    assert not s.settings.problems(), s.settings.problems()
    for aircraft in ("F-14BU", "F-16C"):
        s.new(f"Smoke {aircraft}", aircraft, 2, seed=7)
        pk = next(p for p in s.packages() if s.flyable(p))
        fl = s.flyable(pk)[0]
        res = s.fly(pk.number, fl.id)
        assert s.settings.sortie_miz.exists(), "SQE_Sortie.miz was not written"
        print(f"[{aircraft}] built {s.settings.sortie_miz.name}: {pk.objective.description} | you: {fl.callsign} {fl.role.value}"
              f" | push {res.timeline['push']} TOT {res.timeline['tot']} | warnings: {res.warnings or 'none'}")
        man = s.manifest()
        assert s.poll()[0] in ("none", "stale"), "state file should not exist yet"
        # pretend DCS wrote a result: kill 60% of the primary target's units and one escort
        prim = next(g for g in man.groups if g["kind"] == "asset" and g.get("primary"))
        fr = next(g for g in man.groups if g["kind"] == "friendly" and not g.get("player"))
        data = {"campaign": man.campaign_id, "sortie": man.sortie, "package": man.package_id, "mission_ended": True,
                "time": 1800, "dead": prim["units"][: int(len(prim["units"]) * 0.6)] + fr["units"][:1], "ejected": [],
                "landed": [man.player_unit]}
        s.settings.state_file.write_text(json.dumps(data))
        status, got, tl = s.poll()
        assert status == "ok", status
        print(f"    tally: {tl}")
        out = s.apply(got)
        print("    debrief:", out["story"].split("\n")[0][:160])
        print("    meanwhile:", [m["lines"][0][:70] for m in out["meanwhile"]][:2])
        assert s.state.day == 2 and s.state.plan, "campaign did not advance"
        reopened = Session(AppSettings(dcs_saves=str(tmp)))
        reopened.open(s.path)
        assert reopened.state.day == 2
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
