"""Print where red's SAM sites sit round their fields (v0.41.65): for each site, its class, its bearing from the threat axis (the nearest blue base)
and its distance from the field. For eyeballing the doctrinal placement (sqe/sams.py place_red_site). Usage: python tools/red_sam_report.py [level] [seed]"""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ["APPDATA"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqe import sams
from sqe.engine import Session
from sqe.scenario import LONG_RANGE
from sqe.settings import AppSettings


def main(level: int = 3, seed: int = 3) -> None:
    s = Session(AppSettings(dcs_saves=tempfile.mkdtemp(), persist=False))
    s.new("Report", "F-16C", level, seed=seed)
    st = s.state
    for fid in sorted(a.id for a in st.assets.values() if a.kind.value == "AIRFIELD"):
        f = st.assets[fid]
        axis = sams.red_threat_axis(st, f.x, f.y)
        print(f"{f.name}: threat axis {axis:.0f} deg")
        for a in sorted((x for x in st.assets.values() if x.id.startswith("sam_" + fid[3:] + "_")), key=lambda x: x.id):
            brg = math.degrees(math.atan2(a.y - f.y, a.x - f.x)) % 360
            off = (brg - axis + 180) % 360 - 180
            print(f"   {a.id:<18} {a.variant:<6} {'long ' if a.variant in LONG_RANGE else 'short'}  {off:+4.0f} deg from the axis  {math.hypot(a.x - f.x, a.y - f.y) / 1000:5.1f} km")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 3, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
