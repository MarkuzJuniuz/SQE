"""Run independent cases of a tool in worker processes (S109, XO 2026-11-18: use all the cores).

Python threads share one interpreter lock, so CPU work (building missions) only speeds up with processes. A tool that loops over independent cases
(level x seed, one campaign per case ...) makes a module-level function `one_case(task) -> result`, then:

    jobs, argv = parallel.pop_jobs(sys.argv[1:])           # --jobs N (default: cores minus 2; 1 = one process, the old serial path)
    results = parallel.map_cases(one_case, tasks, jobs, TMP)   # a list in TASK order, so the merged output is the same as the serial run

Rules for the case function: it is a top-level function of the tool (spawn re-imports the tool in each worker, so the module-level pins and imports run again
there), it builds its own Session (no state shared between cases), and everything it returns can be pickled. Each worker has its own temp folder inside the
parent's: the tool makes its TMP with `make_tmp(prefix)` and the workers' APPDATA / saves never collide.

The probes were never repeatable run to run (a campaign id is a random uuid4 that seeds the plan, the builder has its own unseeded Random): a serial and a parallel
run could not be compared. `ensure_hashseed()` (at the top of the tool) and `pin_task(key)` (first line of the case function) pin them the way `miz_identity`
does, per case, so a probe's output is the same serial or parallel and the same on every run."""
import concurrent.futures
import hashlib
import multiprocessing
import os
import random
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PARENT_ENV = "SQE_TOOLS_PARENT_TMP"


def make_tmp(prefix: str) -> Path:
    """A temp folder: a fresh one in the parent process, a subfolder of the parent's in a worker."""
    parent = os.environ.get(PARENT_ENV)
    if parent:
        p = Path(parent) / f"w{os.getpid()}"
        p.mkdir(parents=True, exist_ok=True)
        return p
    return Path(tempfile.mkdtemp(prefix=prefix))


def ensure_hashseed() -> None:
    """String hashing is random per process (set order changes); pin it by running this script once more with PYTHONHASHSEED=0 (os.execv does not work on Windows)."""
    if os.environ.get("PYTHONHASHSEED") != "0":
        sys.exit(subprocess.call([sys.executable] + sys.argv, env=dict(os.environ, PYTHONHASHSEED="0")))


_PIN = ["", 0, False]


def pin_task(key: str) -> None:
    """Pin what is random per run for one case (call it first in the case function): the campaign id (uuid4), the mission builder's own Random(), the global `random`."""
    _PIN[0], _PIN[1] = key, 0
    random.seed(key)
    if not _PIN[2]:
        _PIN[2] = True

        def _fake_uuid4():
            _PIN[1] += 1
            return uuid.UUID(int=int(hashlib.md5(f"{_PIN[0]}:{_PIN[1]}".encode()).hexdigest(), 16))

        uuid.uuid4 = _fake_uuid4
        from sqe import mission_builder as mb
        orig = mb.MissionBuilder.__init__

        def _init(self, state, d, opts=None, loadouts=None, rng=None):
            orig(self, state, d, opts, loadouts, rng or random.Random("sqe-probe"))

        mb.MissionBuilder.__init__ = _init


def default_jobs() -> int:
    """One worker per core, two left free."""
    return max(1, (os.cpu_count() or 2) - 2)


def pop_jobs(argv):
    """(jobs or None, argv without `--jobs N`)."""
    argv = list(argv)
    if "--jobs" not in argv:
        return None, argv
    i = argv.index("--jobs")
    jobs = int(argv[i + 1])
    del argv[i:i + 2]
    return jobs, argv


def map_cases(fn, tasks, jobs, tmp) -> list:
    """[fn(t) for t in tasks], in task order, over up to `jobs` worker processes (never more than tasks). jobs=1 or one task: in this process.
    The number of workers used is left in `map_cases.workers`."""
    tasks = list(tasks)
    jobs = max(1, min(default_jobs() if jobs is None else jobs, len(tasks) or 1))
    map_cases.workers = jobs
    if jobs == 1:
        return [fn(t) for t in tasks]
    os.environ[PARENT_ENV] = str(tmp)                  # the spawned workers put their own folder inside ours
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs, mp_context=multiprocessing.get_context("spawn")) as ex:
            return list(ex.map(fn, tasks))
    finally:
        os.environ.pop(PARENT_ENV, None)


map_cases.workers = 1
