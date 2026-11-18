"""S103b probe: a campaign created with a10_variant="A-10A" flies the A-10A, with no JDAM and no targeting pod in the .miz.

    python tools/a10a_probe.py [seed ...]

For each seed it creates an Era Equipment campaign with the A-10A (level 1 and level 3, the player flying the A-10A squadron), walks a few turns, and builds EVERY flyable package as your own flight and
as the all-AI test. In every built .miz it checks, for all blue A-10 groups:
  - the unit type is "A-10A" (never an A-10C), and so is every squadron of the campaign that was an A-10C slot;
  - no pylon holds the targeting pod, a JDAM (GBU-31 / 32 / 38 / 54), a WCMD (CBU-103 / 104 / 105) or any other GPS-guided store;
  - the pylons are all on the pydcs A_10A pylon tables.
Prints how many A-10A groups and which kits (CAS / STRIKE stores) it saw. Exit 0 = all clean."""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="sqe_a10a_"))
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


def main(seeds) -> int:
    ok_clsids = {p: {w[1]["clsid"] for n in dir(getattr(planes.A_10A, f"Pylon{p}")) if not n.startswith("_") for w in [getattr(getattr(planes.A_10A, f"Pylon{p}"), n)]} for p in planes.A_10A.pylons}
    bad, seen, kits, builds = [], 0, set(), 0
    from sqe.loadouts import LoadoutLibrary                  # the kits themselves, so the STRIKE kit (offered only on a clean supply strike, rare in a short run) is checked too
    from sqe.models import Role
    lib = LoadoutLibrary()
    for role in (Role.CAS, Role.STRIKE):
        kit = {p: v["CLSID"] for p, v in lib.for_role("A-10A", role).items()}
        print(f"kit {role.value}: {len(kit)} pylons, " + ", ".join(f"{p}:{c}" for p, c in sorted(kit.items())))
        for pyl, c in kit.items():
            if any(b_ in str(c) for b_ in BAD) or c not in ok_clsids.get(pyl, set()):
                bad.append(f"kit {role.value}: pylon {pyl} {c}")
    bad += [f"loadout warning: {w}" for w in lib.warnings]
    for level in (1, 3):
        for seed in seeds:
            s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
            (TMP / "saves").mkdir(parents=True, exist_ok=True)
            s.new(f"Probe{level}{seed}", "A-10A", level, seed=seed, a10_variant="A-10A")
            st = s.state
            wrong = sorted({q.aircraft for q in st.squadrons.values() if q.aircraft.startswith("A-10") and q.aircraft != "A-10A"})
            if wrong or not st.squadrons_for("A-10A"):
                bad.append(f"L{level} s{seed}: squadron types {wrong or 'no A-10A squadron'}")
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
                                if str(u.get("type", "")).startswith("A-10") and u["type"] != "A-10A":
                                    bad.append(f"L{level} s{seed} #{p.number}: blue unit type {u['type']}")
                                if u.get("type") != "A-10A":
                                    continue
                                seen += 1
                                held = {int(k): (v.get("CLSID") if isinstance(v, dict) else v) for k, v in (u.get("payload", {}).get("pylons") or {}).items()}
                                kits.add(tuple(sorted(str(c) for c in held.values())))
                                for pyl, c in held.items():
                                    if any(b_ in str(c) for b_ in BAD):
                                        bad.append(f"L{level} s{seed} #{p.number} {u.get('name')}: pylon {pyl} holds {c}")
                                    if c not in ok_clsids.get(pyl, set()):
                                        bad.append(f"L{level} s{seed} #{p.number} {u.get('name')}: pylon {pyl} {c} is not an A_10A store")
                s.skip_turn()
    print(f"{builds} missions built, {seen} A-10A units checked, {len(kits)} distinct loadouts")
    for k in sorted(kits):
        print("   ", ", ".join(k))
    for b in bad[:40]:
        print("  BAD:", b)
    print("CLEAN" if not bad else f"{len(bad)} PROBLEMS")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main([int(a) for a in sys.argv[1:]] or [5, 7]))
