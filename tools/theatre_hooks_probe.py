"""S90 J5 probe: the optional theatre-pack hook keys, proved with a dummy second pack (tools only, nothing ships).

    python tools/theatre_hooks_probe.py [--jobs N]

The probe writes a pack `hookdummy` into a temp folder (the Caucasus pack renamed, its data files copied under the new id) that sets EVERY hook key: `red_roster`, `level_overrides`, `front.air_fields`,
`front.defeat_bases`, `nav`, `ils_runway`, `mag_var_deg`, `extra_sams`. For levels 1, 2 and 3 it creates a campaign in that pack and checks that each key took effect where it is read (BAD lines otherwise):
  roster      - red's squadrons fly only the pack's types, and no more jets than it lists;
  overrides   - the Difficulty of the level (`difficulty.get`) carries the pack's value, and the Tu-22M3 wing has the pack's size (L1 6 + 2 escorts, L2 none, L3 6 + 3) where the Caucasus has none / 14 / 24;
  front keys  - `war.mountain_fields()`, `ground.defeat_bases()`, a field outside the list is on the "SEA" axis;
  nav / ils / mag var - `kneeboard.nav_line`, `runways.ils_runways`, `runways.mag_var_deg`;
  extra SAMs  - the fixed sites of the level exist with the pack's variant at the pack's place (by x / y and by near + bearing + distance), none of the other levels' ones does;
and that a saved campaign of the pack opens in a fresh session with the same hooks (the loader re-activates the pack), that a Caucasus campaign made after it sees none of them (every accessor gives the
Caucasus constant), and that one mission of the dummy pack at L3 builds (the extra SA-5s are counted in it). A last block feeds bad values to the pack loader: each must raise a ValueError naming the key.
Exit 0 = all clean. One worker process per level (--jobs N); the output is the same either way."""
import json
import math
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_hooks_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ROSTER = {"1": {"MiG_21Bis": 40, "MiG_23MLD": 54}, "2": {"MiG_29A": 90, "Su_24M": 70}, "3": {"MiG_31": 20, "Su_27": 90, "Su_24M": 100}}
OVERRIDES = {"1": {"bomber_wing": 6, "bomber_escort_wing": 2}, "2": {"bomber_wing": 0, "bomber_escort_wing": 0}, "3": {"bomber_wing": 6, "bomber_escort_wing": 3}}
EXTRA = [{"id": "sam_xa5a_0", "site": "SA-5", "x": -20000.0, "y": 500000.0, "levels": [2, 3]},
         {"id": "sam_xa5b_0", "site": "SA-5", "near": "Kutaisi", "bearing": 90, "dist_m": 30000, "levels": [3], "name": "Dummy SA-5 near Kutaisi"}]
NAV = {"Batumi": "DUMMY NAV Batumi"}


def make_pack(root: Path) -> Path:
    """A pack folder with `hookdummy` (and its files); returns the folder."""
    pack = root / "packs"
    pack.mkdir(parents=True, exist_ok=True)
    src = ROOT / "sqe" / "data" / "theatres"
    d = json.loads((src / "caucasus.json").read_text(encoding="utf-8"))
    d["id"], d["name"] = "hookdummy", "Hook dummy"
    d["red_roster"], d["level_overrides"] = ROSTER, OVERRIDES
    d["front"] = {**d["front"], "air_fields": ["krymsk"], "defeat_bases": 1}
    d["nav"], d["ils_runway"], d["mag_var_deg"], d["extra_sams"] = NAV, {"Batumi": 31}, 4.0, EXTRA
    (pack / "hookdummy.json").write_text(json.dumps(d), encoding="utf-8")
    for f in src.glob("caucasus_*.json"):
        shutil.copy(f, pack / f.name.replace("caucasus_", "hookdummy_"))
    return pack


def one_case(task) -> dict:
    level, = task
    parallel.pin_task(f"hooks:{level}")
    bad, lines = [], []
    from sqe import theatres, difficulty, war, ground, kneeboard, runways, redroster
    from sqe.engine import Session
    from sqe.models import AssetKind
    from sqe.settings import AppSettings
    theatres.EXTRA_DIRS.append(str(make_pack(TMP)))
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    mk = lambda: Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
    tag = f"L{level}"
    s = mk()
    s.new(f"Hk{level}", "F-16C", level, seed=5, theatre="hookdummy")
    st = s.state

    def hooks_ok(st_, where):
        d = difficulty.get(level)
        ov = OVERRIDES[str(level)]
        if (d.bomber_wing, d.bomber_escort_wing) != (ov["bomber_wing"], ov["bomber_escort_wing"]):
            bad.append(f"{tag} {where}: difficulty.get has bomber_wing {d.bomber_wing} / escort {d.bomber_escort_wing}, the pack says {ov}")
        if war.mountain_fields() != ("krymsk",):
            bad.append(f"{tag} {where}: mountain_fields {war.mountain_fields()}")
        if ground.defeat_bases() != 1:
            bad.append(f"{tag} {where}: defeat_bases {ground.defeat_bases()}")
        if kneeboard.nav_line("Batumi") != NAV["Batumi"] or kneeboard.nav_line("Kutaisi") != "":
            bad.append(f"{tag} {where}: nav_line Batumi {kneeboard.nav_line('Batumi')!r}, Kutaisi {kneeboard.nav_line('Kutaisi')!r} (the pack's table replaces the Caucasus one)")
        if runways.ils_runways() != {"Batumi": 31}:
            bad.append(f"{tag} {where}: ils_runways {runways.ils_runways()}")
        if runways.mag_var_deg() != 4.0:
            bad.append(f"{tag} {where}: mag_var_deg {runways.mag_var_deg()}")
        if any((war.axis_of(a) == "MOUNTAIN") != (war.field_of(a) == "krymsk") for a in st_.assets.values() if war.field_of(a)):
            bad.append(f"{tag} {where}: the MOUNTAIN axis is not just Krymsk")
    hooks_ok(st, "new")

    types = {q.aircraft for w in st.enemy_air for q in w.sqns if q.role != "escort" and q.aircraft != "Tu_22M3"}
    jets = sum(q.authorized for w in st.enemy_air for q in w.sqns if q.aircraft not in ("Tu_22M3",) and q.role != "escort")
    ros = ROSTER[str(level)]
    if not types <= set(ros) or jets > sum(ros.values()):
        bad.append(f"{tag}: red flies {sorted(types)} with {jets} jets, the pack's roster is {ros}")
    tu = [q for w in st.enemy_air for q in w.sqns if q.aircraft == "Tu_22M3"]
    esc = [q for w in st.enemy_air for q in w.sqns if q.role == "escort"]
    want = OVERRIDES[str(level)]
    if "ab_mozdok" in st.assets and (sum(q.authorized for q in tu) != want["bomber_wing"] or sum(q.authorized for q in esc) != want["bomber_escort_wing"]):          # (Mozdok is not a field at L1)
        bad.append(f"{tag}: Tu-22M3 {sum(q.authorized for q in tu)} + escorts {sum(q.authorized for q in esc)}, the pack says {want}")
    lines.append(f"{tag}: red types {sorted(types)}, {jets} jets (roster {sum(ros.values())}), Tu-22M3 {sum(q.authorized for q in tu)} + {sum(q.authorized for q in esc)} escorts")

    ex = {a.id: a for a in st.assets.values() if a.id.startswith("sam_xa5")}
    must = {e["id"] for e in EXTRA if level in e["levels"]}
    if set(ex) != must:
        bad.append(f"{tag}: extra SAM sites {sorted(ex)}, expected {sorted(must)}")
    for e in EXTRA:
        a = ex.get(e["id"])
        if a is None:
            continue
        if a.kind != AssetKind.SAM or a.variant != "SA-5":
            bad.append(f"{tag}: {a.id} is {a.kind} / {a.variant}")
        if "x" in e and (a.x, a.y) != (e["x"], e["y"]):
            bad.append(f"{tag}: {a.id} at {a.x:.0f}, {a.y:.0f}, the pack says {e['x']}, {e['y']}")
        if "near" in e:
            from sqe import theatres as T
            p = T.terrain().airports[e["near"]].position
            if abs(math.hypot(a.x - p.x, a.y - p.y) - e["dist_m"]) > 5.0:
                bad.append(f"{tag}: {a.id} is {math.hypot(a.x - p.x, a.y - p.y):.0f} m from {e['near']}, the pack says {e['dist_m']}")
    lines.append(f"{tag}: extra SAM sites {sorted(ex)}")

    path = str(TMP / "saves" / f"hk{level}.sqe")                                     # a saved campaign opens in a fresh session with the hooks again
    s.save(path)
    theatres.use("caucasus")
    s2 = mk()
    s2.open(path)
    hooks_ok(s2.state, "reopened")
    if {a.id for a in s2.state.assets.values() if a.id.startswith("sam_xa5")} != must:
        bad.append(f"{tag}: the reopened campaign lost its extra SAM sites")

    if level == 3:                                                                    # one mission builds with the extra SA-5s in the world
        from sqe.models import ObjectiveType
        s2.plan_day()
        tgt = [p.number for p in s2.packages() if p.objective.target_id in must]
        lines.append(f"{tag}: packages planned against the extra SAM sites after plan_day: {tgt}")
        built = 0
        for p in [p for p in s2.packages() if s2.flyable(p)][:3]:
            s2.ai_test = True
            try:
                s2.fly(p.number, s2.flyable(p)[0].id)
                built += 1
            except Exception as e:
                bad.append(f"{tag}: mission #{p.number} {p.objective.type.value} failed: {type(e).__name__}: {e}")
                continue
            from dcs import lua
            M = lua.loads(zipfile.ZipFile(s2.settings.sortie_miz).read("mission").decode("utf-8", "replace"))["mission"]
            n200 = sum(1 for coal in M["coalition"].values() for c in coal["country"].values() for g in ((c.get("vehicle") or {}).get("group") or {}).values()
                       for u in g["units"].values() if str(u.get("type")) == "S_200_Launcher")
            lines.append(f"{tag}: mission #{p.number} {p.objective.type.value} built, S-200 launchers in it: {n200}")
        if not built:
            bad.append(f"{tag}: no mission could be built")

    theatres.use("caucasus")                                                          # a Caucasus campaign made now sees none of the hooks
    s3 = mk()
    s3.new(f"Cc{level}", "F-16C", level, seed=5)
    dd = difficulty.get(level)
    if (dd is not difficulty.LEVELS[level] or war.mountain_fields() != war.MOUNTAIN_FIELDS or ground.defeat_bases() != ground.DEFEAT_BASES or kneeboard.nav_line("Batumi") != kneeboard.NAV["Batumi"]
            or runways.ils_runways() is not runways.ILS_RUNWAY or runways.mag_var_deg() != runways.MAG_VAR_DEG
            or any(a.id.startswith("sam_xa5") for a in s3.state.assets.values())):
        bad.append(f"{tag}: the Caucasus campaign after the dummy pack still sees a hook")
    return {"tag": tag, "bad": bad, "lines": lines}


def bad_values() -> list:
    """Each bad hook value must raise a ValueError that names the key."""
    from sqe import theatres
    base = json.loads((ROOT / "sqe" / "data" / "theatres" / "caucasus.json").read_text(encoding="utf-8"))
    cases = [("red_roster", {"4": {"MiG_21Bis": 1}}), ("red_roster", {"1": {}}), ("red_roster", {"1": {"MiG_21Bis": -3}}), ("level_overrides", {"1": {"no_such_field": 1}}),
             ("level_overrides", {"9": {"bomber_wing": 1}}), ("front", {**base["front"], "air_fields": "krymsk"}), ("front", {**base["front"], "defeat_bases": 0}),
             ("nav", {"Batumi": 5}), ("ils_runway", {"Batumi": 40}), ("mag_var_deg", "east"), ("raid_attack_types", []), ("raid_attack_types", ["Not_A_Plane"]), ("raid_bomber_types", "Su_24M"),
             ("extra_sams", [{"id": "x", "site": "SA-5", "x": 1, "y": 2, "levels": [3]}]), ("extra_sams", [{"id": "sam_a_0", "site": "SA-99", "x": 1, "y": 2, "levels": [3]}]),
             ("extra_sams", [{"id": "sam_a_0", "site": "SA-5", "levels": [3]}]), ("extra_sams", [{"id": "sam_a_0", "site": "SA-5", "x": 1, "y": 2, "levels": [4]}]),
             ("extra_sams", [{"id": "sam_a_0", "site": "SA-5", "x": 1, "y": 2, "levels": [3]}, {"id": "sam_a_0", "site": "SA-5", "x": 1, "y": 2, "levels": [3]}]),
             ("raid_bearing_deg", [40, 20]), ("raid_bearing_deg", "20-40"), ("raid_bearing_deg", [20]), ("map_box", {"x0": 1}), ("map_box", {"x0": 5, "x1": 1, "y0": 0, "y1": 1})]
    bad = []
    for key, val in cases:
        d = json.loads(json.dumps(base))
        d[key] = val
        try:
            theatres._validate(d, "probe")
        except ValueError as e:
            if key not in str(e):
                bad.append(f"bad {key}={val!r}: the error does not name the key: {e}")
        except Exception as e:
            bad.append(f"bad {key}={val!r}: raised {type(e).__name__}, not ValueError: {e}")
        else:
            bad.append(f"bad {key}={val!r}: accepted")
    good = json.loads(json.dumps(base))
    try:
        theatres._validate(good, "probe")
    except Exception as e:
        bad.append(f"the unchanged Caucasus pack no longer validates: {e}")
    return bad, len(cases)


def main(jobs=None) -> int:
    res = parallel.map_cases(one_case, [(1,), (2,), (3,)], jobs, TMP)
    bad = []
    for r in res:
        print("\n".join(r["lines"]))
        bad += r["bad"]
    b, n = bad_values()
    bad += b
    print(f"{n} bad-value cases fed to the pack loader")
    for x in bad:
        print("BAD", x)
    print(f"{len(res)} levels ({parallel.map_cases.workers} worker(s)): " + ("CLEAN" if not bad else f"{len(bad)} BAD"))
    return 1 if bad else 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main(_jobs))
