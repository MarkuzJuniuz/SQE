"""S103b / S103e probe: a campaign created with a10_variant="A-10A" flies the A-10A, with no JDAM and no targeting pod in the .miz.

    python tools/a10a_probe.py [seed ...] [--variant A-10A|A-10C2] [--jobs N]

`--variant A-10C2` (S103e, the "A-10C II (late)" choice): the same campaign walk with a10_variant="A-10C2"; every A-10 unit must be type "A-10C_2" (the pydcs `A_10C_2` model, the same as the A-10C) with the A-10C kits
(targeting pod and the GUIDED JDAM / WCMD kit ALLOWED, as for the A-10C), every squadron "A-10C2", every pylon a store of the `A_10C_2` tables. The checks below are the A-10A's (default).

For each seed it creates an Era Equipment campaign with the A-10A (level 1 and level 3, the player flying the A-10A squadron), walks a few turns, and builds EVERY flyable package as your own flight and
as the all-AI test. In every built .miz it checks, for all blue A-10 groups:
  - the unit type is "A-10A" (never an A-10C), and so is every squadron of the campaign that was an A-10C slot;
  - no pylon holds the targeting pod, a JDAM (GBU-31 / 32 / 38 / 54), a WCMD (CBU-103 / 104 / 105) or any other GPS-guided store;
  - the pylons are all on the pydcs A_10A pylon tables.
Prints how many A-10A groups and which kits (CAS / STRIKE stores) it saw. Exit 0 = all clean.
One worker process per (level, seed) (S109; --jobs N, default cores minus 2, --jobs 1 = one process); the output is the same either way."""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_a10a_")
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dcs import lua, planes
from sqe.engine import Session
from sqe.settings import AppSettings

BAD = ("A111396E-D3E8-4b9c-8AC9-2432489304D5", "GBU-31", "GBU-32", "GBU-38", "GBU_54", "GBU-54", "CBU_103", "CBU_104", "CBU_105", "GBU-12", "GBU_12", "GBU-10", "GBU-16", "AGM_154", "AGM-154")


def groups(M):
    for coal in M["coalition"].values():
        for country in coal["country"].values():
            for g in ((country.get("plane") or {}).get("group") or {}).values():
                yield g


VARIANTS = {"A-10A": ("A_10A", "A-10A", True), "A-10C2": ("A_10C_2", "A-10C_2", False)}      # key: (pydcs class, DCS unit type, strict = no pod / JDAM / GPS store)


def _ok_clsids(variant="A-10A"):
    cls = getattr(planes, VARIANTS[variant][0])
    return {p: {w[1]["clsid"] for n in dir(getattr(cls, f"Pylon{p}")) if not n.startswith("_") for w in [getattr(getattr(cls, f"Pylon{p}"), n)]} for p in cls.pylons}


def one_case(task) -> dict:
    """One (level, seed): a fresh Session; returns what the serial loop would have added ({bad, seen, kits, builds})."""
    level, seed, variant = task
    parallel.pin_task(f"a10a:{level}:{seed}" if variant == "A-10A" else f"a10a:{variant}:{level}:{seed}")
    _cls, dcs, strict = VARIANTS[variant]
    ok_clsids = _ok_clsids(variant)
    bad, seen, kits, builds = [], 0, set(), 0
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s.new(f"Probe{level}{seed}", variant, level, seed=seed, a10_variant=variant)
    st = s.state
    wrong = sorted({q.aircraft for q in st.squadrons.values() if q.aircraft.startswith("A-10") and q.aircraft != variant})
    if wrong or not st.squadrons_for(variant):
        bad.append(f"L{level} s{seed}: squadron types {wrong or 'no ' + variant + ' squadron'}")
    for _turn in range(4):
        for p in [p for p in s.packages() if s.flyable(p)]:
            for ai in (False, True):
                s.ai_test = ai
                try:
                    s.fly(p.number, s.flyable(p)[0].id)
                except Exception as e:
                    bad.append(f"L{level} s{seed} #{p.number} ai={ai}: {type(e).__name__}: {e}")
                    continue
                builds += 1
                z = zipfile.ZipFile(s.settings.sortie_miz)
                M = lua.loads(z.read("mission").decode("utf-8", "replace"))["mission"]
                for g in groups(M):
                    for u in g["units"].values():
                        if str(u.get("type", "")).startswith("A-10") and u["type"] != dcs:
                            bad.append(f"L{level} s{seed} #{p.number}: blue unit type {u['type']}")
                        if u.get("type") != dcs:
                            continue
                        seen += 1
                        held = {int(k): (v.get("CLSID") if isinstance(v, dict) else v) for k, v in (u.get("payload", {}).get("pylons") or {}).items()}
                        kits.add(tuple(sorted(str(c) for c in held.values())))
                        for pyl, c in held.items():
                            if strict and any(b_ in str(c) for b_ in BAD):
                                bad.append(f"L{level} s{seed} #{p.number} {u.get('name')}: pylon {pyl} holds {c}")
                            if c not in ok_clsids.get(pyl, set()):
                                bad.append(f"L{level} s{seed} #{p.number} {u.get('name')}: pylon {pyl} {c} is not an A_10A store")
        s.skip_turn()
    return {"bad": bad, "seen": seen, "kits": kits, "builds": builds}


def main(seeds, jobs=None, variant="A-10A") -> int:
    _cls, _dcs, strict = VARIANTS[variant]
    ok_clsids = _ok_clsids(variant)
    bad, seen, kits, builds = [], 0, set(), 0
    from sqe.loadouts import LoadoutLibrary                  # the kits themselves, so the STRIKE kit (offered only on a clean supply strike, rare in a short run) is checked too
    from sqe.models import Role
    lib = LoadoutLibrary()
    for role, kname in ((Role.CAS, ""), (Role.STRIKE, "")) + (() if strict else ((Role.CAS, "GUIDED"),)):
        kit = {p: v["CLSID"] for p, v in lib.for_role(variant, role, kname).items()}
        print(f"kit {role.value}{' ' + kname if kname else ''}: {len(kit)} pylons, " + ", ".join(f"{p}:{c}" for p, c in sorted(kit.items())))
        for pyl, c in kit.items():
            if (strict and any(b_ in str(c) for b_ in BAD)) or c not in ok_clsids.get(pyl, set()):
                bad.append(f"kit {role.value} {kname}: pylon {pyl} {c}")
    bad += [f"loadout warning: {w}" for w in lib.warnings]
    for r in parallel.map_cases(one_case, [(level, seed, variant) for level in (1, 3) for seed in seeds], jobs, TMP):      # S109: one task per (level, seed), merged in task order
        bad += r["bad"]; seen += r["seen"]; kits |= r["kits"]; builds += r["builds"]
    print(f"{builds} missions built, {seen} {variant} units checked, {len(kits)} distinct loadouts")
    for k in sorted(kits):
        print("   ", ", ".join(k))
    for b in bad[:40]:
        print("  BAD:", b)
    print("CLEAN" if not bad else f"{len(bad)} PROBLEMS")
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    _variant = "A-10A"
    if "--variant" in _args:
        _i = _args.index("--variant")
        _variant = _args[_i + 1]
        del _args[_i:_i + 2]
    sys.exit(main([int(a) for a in _args] or [5, 7], _jobs, _variant))
