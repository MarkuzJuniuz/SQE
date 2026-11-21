"""Release main: checks, full smoke test, then the version tag that starts the build.

Run it from anywhere inside the repo, with the repo's own Python (the .venv):

    python tools/release.py            # the real release
    python tools/release.py --dry-run  # every check and the smoke test, then stop before the tag

What it does, in order (it stops at the first problem and tags nothing):
  1. The working tree has no uncommitted changes to tracked files.
  2. Checks out main and pulls it (fast-forward only); main must equal origin/main.
  3. Reads __version__ from sqe/__init__.py; the tag vX.Y.Z must not exist yet, here or on origin.
  4. docs/CHANGES.md has a "## vX.Y.Z" entry for that version.
  5. python -m compileall -q sqe tools, then the full tools/smoke_test.py must print SMOKE TEST PASSED (and not exit with an error).
  6. Shows the version and commit and asks for y; then tags that commit and pushes the tag.
     The tag push starts .github/workflows/release.yml (a Windows build, about 2 to 3 minutes).

It never merges, never pushes a branch and never moves or deletes a tag. The PRs stay yours.
"""
import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_URL = "https://github.com/MarkuzJuniuz/SQE"


def die(msg):
    print(f"\nSTOP: {msg}\nNothing was tagged.")
    sys.exit(1)


def git(*args, check=True):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed:\n{(r.stdout + r.stderr).strip()}")
    return r.stdout.strip()


def step(n, text):
    print(f"\n[{n}] {text}")


def version_of(text):
    m = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.M)
    return m.group(1) if m else None


def run_smoke():
    """Run the full smoke test, show its output as it comes, and need its PASSED line."""
    p = subprocess.Popen([sys.executable, os.path.join("tools", "smoke_test.py")], cwd=ROOT,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    passed = False
    for line in p.stdout:
        print("    " + line.rstrip())
        if "SMOKE TEST PASSED" in line:
            passed = True
    code = p.wait()
    # SMOKE TEST PASSED prints only after every check passed. A crash by signal AFTER it (seen once in the cloud
    # sandbox: exit -11 while the interpreter shut down) is a warning, not a failed check; a plain error exit is a fail.
    if code != 0:
        print(f"    (the smoke test process exited with code {code} after its last line)")
    return passed and code <= 0


def main():
    ap = argparse.ArgumentParser(description="Release main: checks, smoke test, tag, push the tag.")
    ap.add_argument("--dry-run", action="store_true", help="run every check and the smoke test, but do not tag or push")
    args = ap.parse_args()

    step(1, "Working tree")
    if git("status", "--porcelain", "--untracked-files=no"):
        die("tracked files have uncommitted changes; commit or stash them first.")
    print("    clean")

    step(2, "main = origin/main")
    git("fetch", "origin", "--tags", "--prune")
    git("checkout", "main")
    git("pull", "--ff-only", "origin", "main")
    head, remote = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if head != remote:
        die(f"local main ({head[:8]}) is not origin/main ({remote[:8]}); push or reset it first.")
    print(f"    main is at {head[:8]}: {git('log', '-1', '--format=%s', 'HEAD')}")

    step(3, "Version and tag")
    version = version_of(open(os.path.join(ROOT, "sqe", "__init__.py"), encoding="utf-8").read())
    if not version:
        die("could not read __version__ from sqe/__init__.py.")
    tag = f"v{version}"
    if git("tag", "-l", tag):
        die(f"tag {tag} already exists here; main is at version {version}, which is already released (merge the next PR first).")
    if git("ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
        die(f"tag {tag} already exists on origin; main is at version {version}, which is already released.")
    latest = git("tag", "--sort=-v:refname", "-l", "v*").splitlines()
    print(f"    sqe/__init__.py says {version}; new tag {tag} (latest tag now: {latest[0] if latest else 'none'})")

    step(4, "docs/CHANGES.md entry")
    changes = open(os.path.join(ROOT, "docs", "CHANGES.md"), encoding="utf-8").read()
    if not re.search(rf"^## {re.escape(tag)}\b", changes, re.M):
        die(f"docs/CHANGES.md has no '## {tag}' entry.")
    print(f"    '## {tag}' found")

    step(5, "Compile check and full smoke test (a few minutes)")
    if subprocess.run([sys.executable, "-m", "compileall", "-q", "sqe", "tools"], cwd=ROOT).returncode != 0:
        die("compileall failed.")
    if not run_smoke():
        die("the smoke test did not pass.")
    # The smoke test must not have left the tree changed or moved HEAD.
    if git("rev-parse", "HEAD") != head or git("status", "--porcelain", "--untracked-files=no"):
        die("the tree or HEAD changed while the smoke test ran.")
    print("\n    smoke test passed")

    step(6, "Tag and push")
    print(f"    version {version}, tag {tag}, commit {head[:8]}")
    if args.dry_run:
        print("\nDRY RUN: all checks passed. Nothing was tagged or pushed.")
        return
    if input(f"    Tag {tag} on {head[:8]} and push it? [y/N] ").strip().lower() != "y":
        die("not confirmed.")
    git("tag", tag, head)
    out = subprocess.run(["git", "push", "origin", tag], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        git("tag", "-d", tag)
        die(f"git push origin {tag} failed (the local tag was removed again):\n{(out.stdout + out.stderr).strip()}")
    print(f"\nPushed {tag}. The release build is running (about 2 to 3 minutes): {REPO_URL}/actions")
    try:
        r = subprocess.run(["gh", "run", "list", "--limit", "1", "--workflow", "release.yml"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            print("    " + r.stdout.strip())
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    main()
