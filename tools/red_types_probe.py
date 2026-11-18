"""S90 P3a probe: red flights of the Syria 2000 types MiG_25PD and Su_17M4 through the normal red-air path (tools only, nothing ships).

    python tools/red_types_probe.py [seed ...] [--jobs N]

No Caucasus roster has these two types yet, so the probe makes a campaign (level 3, level 2) and, before the day is planned, swaps red's jets: every MiG_31 / MiG_29A / MiG_29S squadron becomes MiG_25PD and
every Su_24M / Su_25 squadron becomes Su_17M4 (the squadron objects keep their names, counts and fields). Red's raid code names its attack types in module tables (`raids.RAIDERS`, `loadouts.BOMBER_TYPES`: Su_24M / Su_25
only, the follow-up of this job), so the probe adds the Su_17M4 to those tables IN THE PROBE'S PROCESS ONLY to let a raid pick it: that shows its kit and route through the real raid builder. It then plans the day, walks a few turns and builds
every flyable package as the all-AI test, plus the packages nobody can fly (fleet defence = raid intercepts, BARCAP) with one flight standing in for yours. In every built .miz it lists the red groups of the two types: how many, their kit (pylon -> weapon name from pydcs), the route summary (waypoint types, altitudes, speeds), and any loadout warning. Checks (BAD lines):
  - a MiG_25PD group holds only R-40 / R-60 stores (R-40RD / R-40TD) and at least one of each R-40 kind; no weapon that did not exist for it in 2000;
  - a Su_17M4 group holds bombs / rockets only (no AA missile, no ARM, no weapon younger than 2000) and at most four 500-kg class stores (`STRIKE_PER_JET`);
  - an unarmed MiG-25PD group; a build that raises. An unarmed Su-17M4 raid group is a NOTE, not a failure: a SEAD (Kh-31P) or stand-off (Kh-59M) raid has no store for it, so once the raid code lets the
    Su-17M4 fly (the follow-up) it must keep it off those jobs; the probe only forces the type in to see the kit and the route.
Exit 0 = all clean. One worker process per (level, seed) (--jobs N, default cores minus 2, --jobs 1 = one process); the output is the same either way."""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_redtypes_")
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dcs import lua
from dcs.weapons_data import weapon_ids
from sqe.engine import Session
from sqe.models import ObjectiveType
from sqe.settings import AppSettings

SWAP = {"MiG_31": "MiG_25PD", "MiG_29A": "MiG_25PD", "MiG_29S": "MiG_25PD", "Su_24M": "Su_17M4", "Su_25": "Su_17M4"}
DCS_TYPE = {"MiG-25PD", "Su-17M4"}
BAD_AIR = ("AIM", "R_77", "R-77", "R_27", "R_73", "R_33", "R-33", "Kh_31", "Kh_58", "Kh_59", "Kh-59", "Kh_29")      # none of these on either type in 2000 (the R-73 / R-27 / R-77 never fitted the MiG-25PD)


def groups(M):
    for cname, coal in M["coalition"].items():
        for country in coal["country"].values():
            for g in ((country.get("plane") or {}).get("group") or {}).values():
                yield cname, g


def wname(clsid) -> str:
    return str((weapon_ids.get(clsid) or {}).get("name", clsid))


def one_case(task) -> dict:
    """One (level, seed): a fresh Session with the swapped red roster; returns the lines and BAD entries of the serial loop."""
    level, seed = task
    parallel.pin_task(f"redtypes:{level}:{seed}")
    bad, lines, kits, n_groups, builds, unarmed = [], [], {}, {"MiG-25PD": 0, "Su-17M4": 0}, 0, [0]
    from sqe import raids, raid_spawns                                 # the probe's own process: let a raid pick the Su-17M4 (see the module text)
    raids.BOMBER_TYPES = raid_spawns.BOMBER_TYPES = ("Su_24M", "Su_17M4")
    raids.RAIDERS = raids.BOMBER_TYPES + ("Su_25",)
    s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    s.new(f"Rt{level}{seed}", "F-16C", level, seed=seed)
    st = s.state
    swapped = 0
    for w in st.enemy_air:
        for q in w.sqns:
            if q.aircraft in SWAP:
                q.aircraft = SWAP[q.aircraft]; swapped += 1
        w.types = list(dict.fromkeys(q.aircraft for q in w.sqns))
    lines.append(f"L{level} s{seed}: {swapped} red squadrons swapped to MiG_25PD / Su_17M4")
    s.plan_day()
    def scan(tag):
        nonlocal builds
        builds += 1
        z = zipfile.ZipFile(s.settings.sortie_miz)
        M = lua.loads(z.read("mission").decode("utf-8", "replace"))["mission"]
        for cname, g in groups(M):
            for u in g["units"].values():
                t = str(u.get("type"))
                if t not in DCS_TYPE or cname != "red":
                    continue
                n_groups[t] += 1
                held = {int(k): (v.get("CLSID") if isinstance(v, dict) else v) for k, v in (u.get("payload", {}).get("pylons") or {}).items()}
                kit = tuple(f"{k}:{wname(c)}" for k, c in sorted(held.items()))
                kits[(t, kit)] = kits.get((t, kit), 0) + 1
                names = " ".join(wname(c) for c in held.values())
                if not held:
                    if t == "MiG-25PD":
                        bad.append(f"{tag} {g.get('name')}: {t} unarmed")
                    else:
                        unarmed[0] += 1
                    continue
                if any(b_ in names or b_ in " ".join(map(str, held.values())) for b_ in BAD_AIR):
                    bad.append(f"{tag} {g.get('name')}: {t} holds a store it did not have in 2000: {names}")
                if t == "MiG-25PD":
                    if any(not (("R-40" in wname(c)) or ("R-60" in wname(c))) for c in held.values()):
                        bad.append(f"{tag} {g.get('name')}: MiG-25PD holds a store that is not an R-40 / R-60: {names}")
                    if held and not (any("R-40RD" in wname(c) for c in held.values()) and any("R-40TD" in wname(c) for c in held.values())):
                        bad.append(f"{tag} {g.get('name')}: MiG-25PD kit is not the mixed R-40RD + R-40TD fit: {names}")
                else:
                    if any(("AA" in wname(c) and "(AA" in wname(c)) or "R-60" in wname(c) or "R-73" in wname(c) for c in held.values()):
                        bad.append(f"{tag} {g.get('name')}: Su-17M4 strike group holds an air-to-air missile: {names}")
                    if sum(1 for c in held.values() if "FAB-500" in wname(c)) > 4:
                        bad.append(f"{tag} {g.get('name')}: Su-17M4 holds more than four FAB-500: {names}")
        for cname, g in groups(M):
            us = [u for u in g["units"].values() if str(u.get("type")) in DCS_TYPE and cname == "red"]
            if not us:
                continue
            pts = [g["route"]["points"][k] for k in sorted(g["route"]["points"])]
            lines.append(f"  {tag} {g.get('name')} x{len(us)} {us[0]['type']} route: " + " > ".join(f"{q.get('type')}/{q.get('alt', 0) * 3.28084:.0f}ft/{q.get('speed', 0) * 1.94384:.0f}kt" for q in pts[:7]) + (" ..." if len(pts) > 7 else ""))

    for _turn in range(4):
        for p in [p for p in s.packages() if s.flyable(p)]:
            s.ai_test = True
            tag = f"L{level} s{seed} #{p.number} {p.objective.type.value}"
            try:
                s.fly(p.number, s.flyable(p)[0].id)
            except Exception as e:
                bad.append(f"{tag}: {type(e).__name__}: {e}")
                continue
            scan(tag)
        done = 0
        for p in s.packages():                                              # packages nobody can fly: raid intercepts and BARCAP, one flight standing in for yours
            if s.flyable(p) or not p.flights or done >= 6 or p.objective.type not in (ObjectiveType.FLEET_DEFENSE, ObjectiveType.BARCAP):
                continue
            stand = p.player_options(st.player.aircraft)
            if not stand:
                continue
            done += 1
            s.ai_test = True
            tag = f"L{level} s{seed} #{p.number} {p.objective.type.value} aionly"
            try:
                s.fly(p.number, stand[0].id)
            except Exception as e:
                bad.append(f"{tag}: {type(e).__name__}: {e}")
                continue
            scan(tag)
        s.skip_turn()
    return {"bad": bad, "lines": lines, "kits": kits, "groups": n_groups, "builds": builds, "unarmed": unarmed[0]}


def main(seeds, jobs=None) -> int:
    from sqe.loadouts import ENEMY_CAP_KITS, enemy_cap_loadout, enemy_strike_loadout
    bad, kits, groups_n, builds, unarmed = [], {}, {"MiG-25PD": 0, "Su-17M4": 0}, 0, 0
    print("kit MiG_25PD (air-to-air): " + ", ".join(f"{p}:{wname(v['CLSID'])}" for p, v in sorted(enemy_cap_loadout("MiG_25PD").items())))
    print("kit Su_17M4 (strike):      " + ", ".join(f"{p}:{wname(v['CLSID'])}" for p, v in sorted(enemy_strike_loadout("Su_17M4").items())))
    for r in parallel.map_cases(one_case, [(level, seed) for level in (3, 2) for seed in seeds], jobs, TMP):      # one task per (level, seed), merged in task order
        for ln in r["lines"]:
            print(ln)
        bad += r["bad"]; builds += r["builds"]; unarmed += r["unarmed"]
        for k, v in r["kits"].items():
            kits[k] = kits.get(k, 0) + v
        for k, v in r["groups"].items():
            groups_n[k] += v
    print(f"{builds} missions built; red units of the new types in them: MiG-25PD {groups_n['MiG-25PD']}, Su-17M4 {groups_n['Su-17M4']} ({unarmed} of those with no store: a SEAD / Kh-59M raid, see the module text)")
    for (t, kit), n in sorted(kits.items()):
        print(f"  {t} x{n}: " + ", ".join(kit))
    for b in bad[:40]:
        print("  BAD:", b)
    print("CLEAN" if not bad else f"{len(bad)} PROBLEMS")
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main([int(a) for a in _args] or [3, 7], _jobs))
