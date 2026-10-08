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
        assert len([n for n in z.namelist() if "KNEEBOARD" in n]) == 2, "expected 2 kneeboard pages"
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
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
