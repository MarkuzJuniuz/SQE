"""Capture custom loadouts from a Mission Editor .miz.
In the ME, name each aircraft GROUP '<aircraft key>:<ROLE>', e.g.  F-14BU:STRIKE   F-14BU:CAP   FA-18C:SEAD   A-10C:CAS
Save the mission, then:   python tools/capture_loadouts.py my_loadouts.miz
Output goes to <Saved Games>\\SQE\\loadouts.json (pass a second argument to choose another file).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqe.loadouts import capture_from_miz
from sqe.settings import AppSettings

if len(sys.argv) < 2:
    sys.exit(__doc__)
s = AppSettings.load()
out = sys.argv[2] if len(sys.argv) > 2 else str(Path(s.sqe_dir) / "loadouts.json")
found = capture_from_miz(sys.argv[1], out)
print("\n".join(f"captured {k} ({n} pylons)" for k, n in found.items()) or "No groups named like 'F-14BU:STRIKE' found.")
print("->", out)
