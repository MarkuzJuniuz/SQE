"""Mission identity check: build the same missions before and after a change and compare them.

Use it for refactors that must NOT change behaviour (renames, splitting a long function):

    python tools/miz_identity.py save  BASE_DIR     # on the code BEFORE the change
    python tools/miz_identity.py check BASE_DIR     # on the code AFTER the change: exit 0 = identical, 1 = differences (a diff is printed)
    add --jobs N to either: N worker processes, one case each (default: cores minus 2, at most one per case, S109); --jobs 1 = one process, the old serial path

Each case is a new campaign (aircraft, level, seed). For every objective type that has a flyable package the mission is built
twice: as your own flight and as the all-AI test (`ai_test`), which gives your flight the full AI task set. The `mission` and
`dictionary` files are parsed, normalised (temp paths, campaign ids) and written out as text; the other files in the .miz are
compared by hash. Everything runs in a temp folder (like tools/smoke_test.py): your settings and campaigns are never touched.
`python tools/miz_identity.py selfcheck` builds twice on the same code and fails if the result is not repeatable
(if it is not, the check is useless and the noise has to be removed first).
Coverage (about 60 missions plus the AI-only extras, about 100 s a run): CAS, DEAD, strike and counter-air packages with their SEAD / JSOW / TARCAP / escort / support-CAP / red patrol and
alert flights; and, one BARCAP, one fleet-defence (bomber / raid intercept) and one Fighter Sweep package per case where the plan has them (key `aionly`: built as the
all-AI test with the package's first flight standing in for yours). NOT covered: code paths no case reaches (for example `STATION_FRAC`
changed from 0.85 to 0.80 shows no difference). If a refactor touches such a path, add a case here first. The check pins what is random
per run (campaign id, the builder's Random(), the global `random`, PYTHONHASHSEED) only inside this tool."""
import os
import sys

if os.environ.get("PYTHONHASHSEED") != "0":       # string hashing is random per process, which changes set / dict-of-set order (onboard numbers, ...): pin it by restarting once
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import difflib
import hashlib
import json
import random
import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
TMP = parallel.make_tmp("sqe_ident_")      # S109: in a worker process of the parallel run this is a subfolder of the parent's (APPDATA, saves and the sortie .miz never collide; the parent removes the lot)
os.environ["APPDATA"] = str(TMP / "appdata")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sqe
from sqe import raids as _raids
from sqe.engine import Session
from sqe.models import ObjectiveType
from sqe.settings import AppSettings

# (campaign name, aircraft, level, seed, open skies): a spread of jets and levels so every flight class turns up. On day 1 every strike target
# sits under a SAM, so only CAS and DEAD packages exist; "open skies" cases zero the red SAM sites before the day is planned, which brings
# out strikes, counter-air with its escort / TARCAP flights and more CAS. BARCAP, fleet-defence intercepts and sweeps are added as `aionly` extras below.
CASES = [("IdA", "F-16C", 3, 7, False), ("IdB", "FA-18C", 2, 11, False), ("IdC", "F-15C", 3, 3, False), ("IdD", "A-10C", 1, 5, False), ("IdE", "F-14BU", 2, 9, False),
         ("IdF", "F-16C", 3, 7, True), ("IdG", "F-15C", 3, 3, True), ("IdH", "FA-18C", 2, 11, True), ("IdI", "F-14BU", 3, 9, True)]
MAX_PER_CASE = 7                       # packages built per case and mode (distinct objective types first)
CASE_TURNS = 6                         # v0.41.338: turns walked per case (a plan is one turn: the case skips on and builds from each turn's tasking order)


# Two things are random per run and would make every comparison noisy; both are pinned HERE, in the tool only (production code is untouched):
# the campaign id (a uuid4: it seeds the day's plan and the site layouts) and the builder's own unseeded Random().
_CUR, _N = ["", 0], [0]


def _fake_uuid4():
    _CUR[1] += 1
    return uuid.UUID(int=int(hashlib.md5(f"{_CUR[0]}:{_CUR[1]}".encode()).hexdigest(), 16))


uuid.uuid4 = _fake_uuid4
from sqe import mission_builder as _mb
_orig_init = _mb.MissionBuilder.__init__


def _init(self, state, d, opts=None, loadouts=None, rng=None):
    _orig_init(self, state, d, opts, loadouts, rng or random.Random("sqe-identity"))


_mb.MissionBuilder.__init__ = _init


def _canon(o, ind=0):
    """Deterministic text for a parsed Lua value (dicts sorted by key)."""
    pad = "  " * ind
    if isinstance(o, dict):
        return "\n".join(f"{pad}{k}:" + ("\n" + _canon(v, ind + 1) if isinstance(v, (dict, list, tuple)) else f" {v!r}") for k, v in sorted(o.items(), key=lambda kv: str(kv[0])))
    if isinstance(o, (list, tuple)):
        return "\n".join(f"{pad}[{i}]" + ("\n" + _canon(v, ind + 1) if isinstance(v, (dict, list, tuple)) else f" {v!r}") for i, v in enumerate(o))
    return f"{pad}{o!r}"


def _scrub(text: str, camp_ids: set) -> str:
    text = text.replace(str(TMP), "<TMP>").replace(sqe.__version__, "<VERSION>")
    for c in camp_ids:
        if c:
            text = text.replace(c, "<CAMPAIGN>")
    return text


def _build(session, st, pkg, ai: bool, flight_id=None):
    session.ai_test = ai
    session.state.turn = session._turn_of(pkg)          # v0.41.337: the tasking list is per turn; the tool builds from the whole day plan, so the clock stands at the package's own turn
    if flight_id is None:
        fl = session.flyable(pkg)
        if not fl:                                             # S57: nothing flyable at the package's own turn: a skip, not an ERROR entry
            return None
        flight_id = fl[0].id
    fl_id = flight_id
    session.fly(pkg.number, fl_id)
    z = zipfile.ZipFile(session.settings.sortie_miz)
    from dcs import lua
    out = {}
    ids = {getattr(st, "campaign_id", "") or "", getattr(st, "id", "") or ""}
    for n in sorted(z.namelist()):
        data = z.read(n)
        key = n.replace("/", "__")
        if n in ("mission", "dictionary", "l10n/DEFAULT/dictionary"):
            txt = _scrub(data.decode("utf-8", "replace"), ids)
            try:
                txt = _scrub(_canon(lua.loads(data.decode("utf-8", "replace"))), ids)
            except Exception:                                  # keep the raw text if it will not parse
                pass
            out[key] = txt
        elif n.endswith((".lua", ".txt", ".json")):
            out[key] = _scrub(data.decode("utf-8", "replace"), ids)
        else:
            out[key] = "sha256:" + hashlib.sha256(data).hexdigest()
    return out


def _session(no_standoff: bool):
    (TMP / "saves").mkdir(parents=True, exist_ok=True)
    # SQE_IDENT_NO_STANDOFF=1 builds everything with "AI TARCAPs, escorts and sweeps stop short of live SAM cover" OFF: their no-station routes (a second baseline)
    return Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False, fighter_standoff=not no_standoff))


def run_case(case, s, no_link16: bool) -> dict:
    """{ "case/mode/package-key": {member: text-or-hash} } for one case, built on the session `s` (S109: one case = one independent task)."""
    res = {}
    if os.environ.get("SQE_IDENT_NO_F117"):                    # S104: the Caucasus pack carries the F-117A squadron; =1 drops it from the loaded pack, so the check compares the campaigns WITHOUT it with a baseline made before the squadron existed
        from sqe import theatres
        th_ = theatres.load("caucasus")
        th_["squadrons"] = [q for q in th_["squadrons"] if q["aircraft"] != "F-117A"]
    for name, aircraft, level, seed, opened in [case]:
        _CUR[0], _CUR[1] = name, 0
        random.seed(f"{name}:new")                             # module-level random.* calls inside SQE would otherwise differ per run
        s.new(name, aircraft, level, seed=seed, link16=False if no_link16 else None)      # S103a: =1 builds every campaign with the Link 16 switch OFF (check it against the normal baseline: only the Link 16 parts may differ)
        st = s.state
        if opened:
            for a in st.assets.values():
                if a.kind.value == "SAM":
                    a.health = 0.0
            s.plan_day()
        seen, built, kinds = set(), 0, set()
        for _turn in range(CASE_TURNS):                        # v0.41.338: a plan is one turn's now, so each case walks a few turns (skipping) and builds from each turn's tasking order
            opts = [p for p in s.packages() if s.flyable(p)]
            pick = [p for p in opts if p.objective.type not in seen]          # one package per objective type first, then fill up
            seen |= {p.objective.type for p in pick}
            pick += [p for p in opts if p not in pick]
            for p in pick:
                if built >= MAX_PER_CASE:
                    break
                built += 1
                got = False
                for ai in (False, True):
                    key = f"{name}/{aircraft}/L{level}/s{seed}/{'ai' if ai else 'player'}/{p.number}-{p.objective.type.value}"
                    random.seed(key)
                    try:
                        r = _build(s, st, p, ai)
                        if r is None:
                            continue                               # S57: skipped, no key
                        res[key] = r
                        got = True
                    except Exception as e:                         # a build that raises is part of the result, not a crash
                        res[key] = {"ERROR": f"{type(e).__name__}: {e}"}
                        got = True
                if not got:
                    built -= 1                                     # a skipped package does not use up MAX_PER_CASE
            # AI-only packages (BARCAP, fleet defence = bomber / raid intercepts) and Fighter Sweeps nobody can fly: built as the all-AI test with
            # the package's first flight standing in for yours, so their route, station and task code is covered too.
            for p in s.packages():
                kind = (p.objective.type, p.objective.aim if p.objective.aim == "SWEEP" else "")
                if kind in kinds or s.flyable(p) or not p.flights:
                    continue
                if p.objective.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE) or kind[1] == "SWEEP":
                    stand = p.player_options(st.player.aircraft)           # S57b: the stand-in must be a flight your aircraft can fly (assign_player raises NoPlayerSlot otherwise)
                    if not stand:
                        continue                                           # none in this package: skip it, and leave the kind open for a later package
                    kinds.add(kind)
                    key = f"{name}/{aircraft}/L{level}/s{seed}/aionly/{p.number}-{p.objective.type.value}{'-sweep' if p.objective.aim == 'SWEEP' else ''}"
                    random.seed(key)
                    try:
                        r = _build(s, st, p, True, stand[0].id)
                        if r is not None:
                            res[key] = r
                    except Exception as e:
                        res[key] = {"ERROR": f"{type(e).__name__}: {e}"}
            s.skip_turn()
    return res


def _worker(args) -> dict:
    """One case in a worker process: a fresh Session, this process's own temp folder. The module top level (uuid / builder / random pins) ran again in the worker on import."""
    case, no_link16, no_standoff = args
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise RuntimeError("worker started without PYTHONHASHSEED=0")
    return run_case(case, _session(no_standoff), no_link16)


def run(jobs=None) -> dict:
    """{ "case/mode/package-key": {member: text-or-hash} } for every case, sorted by key. jobs=1: one process, one shared Session (the old serial path);
    jobs=N (default one per core minus two, at most one per case): one worker process per case, the same result.
    SQE_IDENT_NO_LINK16=1 builds every campaign with Link 16 disabled (S103a); SQE_IDENT_NO_STANDOFF=1 see _session; SQE_IDENT_NO_F117=1 drops the F-117A squadron (S104)."""
    no_link16, no_standoff = bool(os.environ.get("SQE_IDENT_NO_LINK16")), bool(os.environ.get("SQE_IDENT_NO_STANDOFF"))
    res = {}
    if jobs == 1:
        s = _session(no_standoff)
        for case in CASES:
            res.update(run_case(case, s, no_link16))
        run.workers = 1
    else:
        for part in parallel.map_cases(_worker, [(case, no_link16, no_standoff) for case in CASES], jobs, TMP):
            res.update(part)
        run.workers = parallel.map_cases.workers
    return dict(sorted(res.items()))


def save(res: dict, base: Path):
    if base.exists():
        shutil.rmtree(base)
    for key, members in res.items():
        for m, txt in members.items():
            p = base / key / (m + ".txt")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding="utf-8")
    (base / "VERSION").write_text(sqe.__version__)


def load(base: Path) -> dict:
    res = {}
    for f in sorted(base.rglob("*.txt")):
        rel = f.relative_to(base)
        key, member = str(rel.parent).replace(os.sep, "/"), rel.name[:-4]
        res.setdefault(key, {})[member] = f.read_text(encoding="utf-8")
    return res


def diff(a: dict, b: dict, label_a="before", label_b="after", limit=60) -> int:
    n = 0
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b:
            print(f"  {key}: only in {label_a if key in a else label_b}"); n += 1; continue
        for m in sorted(set(a[key]) | set(b[key])):
            ma, mb = a[key].get(m), b[key].get(m)
            if ma == mb:
                continue
            n += 1
            print(f"  {key} :: {m}")
            if ma is None or mb is None:
                print(f"    only in {label_a if mb is None else label_b}")
                continue
            lines = list(difflib.unified_diff(ma.splitlines(), mb.splitlines(), label_a, label_b, lineterm="", n=1))
            for ln in lines[:limit]:
                print("    " + ln)
            if len(lines) > limit:
                print(f"    ... {len(lines) - limit} more diff lines")
    return n


def main(argv):
    if len(argv) < 2 or argv[1] not in ("save", "check", "selfcheck"):
        print(__doc__); return 2
    jobs, argv = parallel.pop_jobs(argv)                           # S109: --jobs N (1 = the old serial path)
    print(f"SQE mission identity check, version {sqe.__version__} (isolated temp data: {TMP})")
    mode = argv[1]
    t0 = time.time()
    try:
        if mode == "selfcheck":
            first = run(jobs)
            shutil.rmtree(TMP / "saves", ignore_errors=True)
            second = run(jobs)
            n = diff(first, second, "run 1", "run 2")
            print(f"{len(first)} missions built twice: " + ("IDENTICAL, the check is repeatable" if not n else f"{n} DIFFERENCES: the check is noisy"))
            print(f"{run.workers} worker(s), {time.time() - t0:.0f} s")
            return 1 if n else 0
        if len(argv) < 3:
            print("need a directory"); return 2
        base = Path(argv[2])
        res = run(jobs)
        print(f"built with {run.workers} worker(s) in {time.time() - t0:.0f} s")
        if mode == "save":
            save(res, base)
            print(f"saved {len(res)} missions to {base} (version {sqe.__version__})")
            return 0
        old = load(base)
        old_v = (base / "VERSION").read_text() if (base / "VERSION").exists() else "?"
        if old_v not in ("?", sqe.__version__):                  # a baseline from another version: its text still carries that version string
            old = {k: {m: t.replace(old_v, "<VERSION>") for m, t in v.items()} for k, v in old.items()}
        n = diff(old, res, f"v{old_v}", f"v{sqe.__version__}")
        print(f"{len(res)} missions compared with the saved baseline: " + ("IDENTICAL" if not n else f"{n} DIFFERENCES"))
        return 1 if n else 0
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
