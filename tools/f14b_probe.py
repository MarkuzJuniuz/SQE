"""S103c probe: a campaign created with f14_variant="F-14B" flies the plain F-14B (pydcs F_14B), with no JDAM / GPS store in the .miz.

    python tools/f14b_probe.py [seed ...] [--jobs N]

For each seed and level (2 and 3, with and without the red SAM sites: "open skies" brings out the strikes, counter-air, TARCAP and escort flights) it creates a campaign with the F-14B, the player flying the
Tomcat squadron, walks a few turns, and builds EVERY flyable package as your own flight and as the all-AI test, plus the packages nobody can fly (BARCAP, fleet defence, Fighter Sweep) with one of their flights
standing in for yours (the same cases as `tools/miz_identity.py`). In every built .miz it checks, for all blue F-14 groups:
  - the unit type is "F-14B" (never "F-14BU"), and no squadron of the campaign is a F-14BU;
  - no pylon holds a JDAM (GBU-31 / 32 / 38 / 54), GBU-24E, a WCMD or any other GPS-guided store;
  - every pylon is a store of the pydcs F_14B pylon tables.
Prints which job kinds it built (fleet defence, TARCAP, carrier strike ...) and the distinct loadouts. Exit 0 = all clean.
One worker process per (level, open skies, seed) (S109; --jobs N, default cores minus 2, --jobs 1 = one process); the output is the same either way."""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_f14b_")
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dcs import lua, planes
from sqe.engine import Session
from sqe.models import ObjectiveType
from sqe.settings import AppSettings

BAD = ("GBU-31", "GBU_31", "GBU-32", "GBU-38", "GBU_38", "GBU_54", "GBU-54", "GBU-24E", "CBU_103", "CBU_104", "CBU_105", "AGM_154", "AGM-154", "JDAM")


def groups(M):
    for coal in M["coalition"].values():
        for country in coal["country"].values():
            for g in ((country.get("plane") or {}).get("group") or {}).values():
                yield g


def _ok_clsids():
    return {p: {getattr(getattr(planes.F_14B, f"Pylon{p}"), n)[1]["clsid"] for n in dir(getattr(planes.F_14B, f"Pylon{p}")) if not n.startswith("_")
                     and isinstance(getattr(getattr(planes.F_14B, f"Pylon{p}"), n), tuple)} for p in planes.F_14B.pylons}


def one_case(task) -> dict:
    """One (level, open skies, seed): a fresh Session; returns what the serial loop would have added ({bad, seen, kinds, kits, builds})."""
    level, opened, seed = task
    parallel.pin_task(f"f14b:{level}:{opened}:{seed}")
    ok_clsids = _ok_clsids()
    from sqe.models import Role
    bad, seen, kinds, kits, builds = [], 0, {}, set(), 0

    def check(tag, s, p, flight_id, ai):
        nonlocal seen, builds
        s.ai_test = ai
        try:
            s.fly(p.number, flight_id)
        except Exception as e:
            bad.append(f"{tag}: {type(e).__name__}: {e}")
            return
        builds += 1
        kinds[p.objective.type.value + ("-sweep" if p.objective.aim == "SWEEP" else "")] = kinds.get(p.objective.type.value + ("-sweep" if p.objective.aim == "SWEEP" else ""), 0) + 1
        z = zipfile.ZipFile(s.settings.sortie_miz)
        M = lua.loads(z.read("mission").decode("utf-8", "replace"))["mission"]
        for g in groups(M):
            for u in g["units"].values():
                t = str(u.get("type", ""))
                if t.startswith("F-14") and t != "F-14B":
                    bad.append(f"{tag}: blue unit type {t}")
                if t != "F-14B":
                    continue
                seen += 1
                held = {int(k): (v.get("CLSID") if isinstance(v, dict) else v) for k, v in (u.get("payload", {}).get("pylons") or {}).items()}
                kits.add(tuple(sorted(str(c) for c in held.values())))
                for pyl, c in held.items():
                    if any(b_ in str(c) for b_ in BAD):
                        bad.append(f"{tag} {u.get('name')}: pylon {pyl} holds {c}")
                    if c not in ok_clsids.get(pyl, set()):
                        bad.append(f"{tag} {u.get('name')}: pylon {pyl} {c} is not an F_14B store")

    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s.new(f"Probe{level}{seed}", "F-14B", level, seed=seed, f14_variant="F-14B")
    st = s.state
    wrong = sorted({q.aircraft for q in st.squadrons.values() if q.aircraft.startswith("F-14") and q.aircraft != "F-14B"})
    if wrong or not st.squadrons_for("F-14B"):
        bad.append(f"L{level} s{seed}: squadron types {wrong or 'no F-14B squadron'}")
    if opened:
        for a in st.assets.values():
            if a.kind.value == "SAM":
                a.health = 0.0
        s.plan_day()
    done_kinds = set()
    for _turn in range(4):
        for p in [p for p in s.packages() if s.flyable(p)]:
            fl_ = s.flyable(p)
            ids_ = [fl_[0]] + [f for f in fl_[1:] if f.role == Role.STRIKE and fl_[0].role != Role.STRIKE][:1]      # the first flyable flight, and a STRIKE one too (its laser kit)
            for f_ in ids_:
                for ai in (False, True):
                    check(f"L{level} s{seed} open={opened} #{p.number} {p.objective.type.value} {f_.role.value} ai={ai}", s, p, f_.id, ai)
        for p in s.packages():
            kind = (p.objective.type, p.objective.aim if p.objective.aim == "SWEEP" else "")
            if kind in done_kinds or s.flyable(p) or not p.flights:
                continue
            if p.objective.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE) or kind[1] == "SWEEP":
                stand = p.player_options(st.player.aircraft)
                if stand:
                    done_kinds.add(kind)
                    check(f"L{level} s{seed} open={opened} #{p.number} {p.objective.type.value} aionly", s, p, stand[0].id, True)
        s.skip_turn()
    return {"bad": bad, "seen": seen, "kinds": kinds, "kits": kits, "builds": builds}


def main(seeds, jobs=None) -> int:
    ok_clsids = _ok_clsids()
    from sqe.loadouts import LoadoutLibrary
    from sqe.models import Role
    bad, seen, kinds, kits, builds = [], 0, {}, set(), 0
    lib = LoadoutLibrary()
    for role in (Role.CAP, Role.STRIKE):                      # the kits themselves, so the STRIKE kit is checked even when no strike is built
        kit = {p: v["CLSID"] for p, v in lib.for_role("F-14B", role).items()}
        print(f"kit {role.value}: " + ", ".join(f"{p}:{c}" for p, c in sorted(kit.items())))
        for pyl, c in kit.items():
            if any(b_ in str(c) for b_ in BAD) or c not in ok_clsids.get(pyl, set()):
                bad.append(f"kit {role.value}: pylon {pyl} {c}")
    bad += [f"loadout warning: {w}" for w in lib.warnings]
    for r in parallel.map_cases(one_case, [(level, opened, seed) for level, opened in ((2, False), (3, False), (3, True)) for seed in seeds], jobs, TMP):      # S109: one task per (level, open skies, seed), merged in task order
        bad += r["bad"]; seen += r["seen"]; kits |= r["kits"]; builds += r["builds"]
        for k, v in r["kinds"].items():
            kinds[k] = kinds.get(k, 0) + v
    print(f"{builds} missions built ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}); {seen} F-14B units checked, {len(kits)} distinct loadouts")
    for b in bad[:40]:
        print("  BAD:", b)
    print("CLEAN" if not bad else f"{len(bad)} PROBLEMS")
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main([int(a) for a in _args] or [9], _jobs))
