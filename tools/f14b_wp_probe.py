"""F-14B waypoint probe (S90 / S103, XO 2026-11-18; tools only, nothing ships, no change in play).

What does the Heatblur F-14B do with the waypoints of a mission, and what do the names do? SQE names a B(U) player's points "IPXIP", "TGTXST", ...
(`MissionBuilder._f14_special_namer`, "untested in the cockpit") and has no scheme at all for the F-14A / B. This writes ONE small Caucasus mission with
four player slots at Kutaisi, all flying the same 10-point route, named differently:

  B-A   F-14B     names as the B(U) scheme: PUSHX1, IPXIP, TGTXST, a second IPXIP, HAXHA, FPXFP, DPXDP, X8, X9, RTBXHB (HAXHA / FPXFP / DPXDP are guesses)
  B-B   F-14B     bare codes: PUSH, IP, ST, a second IP, HA, FP, DP, X8, X9, HB
  B-C   F-14B     plain numbered points, no names at all
  BU-A  F-14B(U)  the same names as B-A, for comparison (the scheme SQE already uses for the B(U))

Route (the same for all four, 9 points after takeoff and the landing point): 1 = PUSH (marshal / push), 2 = IP, 3 = TGT, 4 = a second IP (duplicate code),
5 = HA, 6 = FP, 7 = DP, 8 and 9 = extra points, then the landing point (home base). Altitude 20,000 ft, 350 kt.

  python tools/f14b_wp_probe.py [OUT.miz] [--runway]  default .private/f14b_probe/SQE_F14B_WP_Probe.miz; --runway starts the jets on the runway instead of parked
The README in .private/f14b_probe/ tells XO what to look at. Nothing here is verified in DCS yet."""
from __future__ import annotations

import argparse
import contextlib
import datetime
import io
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / ".private" / "f14b_probe" / "SQE_F14B_WP_Probe.miz"
ALT_M = 6096                      # 20,000 ft
SPEED_KPH = 350 * 1.852           # pydcs add_waypoint takes km/h
# offsets from Kutaisi in km: (north, east); a loop east / north-east of the field, 15 to 40 km between points. Nothing is placed there: it is only a route.
ROUTE = [(20, 25), (40, 55), (65, 80), (50, 110), (80, 105), (30, 130), (15, 90), (5, 60), (-10, 35)]
NAMES_A = ["PUSHX1", "IPXIP", "TGTXST", "IP2XIP", "HAXHA", "FPXFP", "DPXDP", "X8", "X9"]; LAND_A = "RTBXHB"
NAMES_B = ["PUSH", "IP", "ST", "IP", "HA", "FP", "DP", "X8", "X9"]; LAND_B = "HB"
NAMES_C = [""] * 9; LAND_C = ""
SLOTS = [("B-A", "F_14B", "F-14B", NAMES_A, LAND_A, "B(U) scheme names"),
         ("B-B", "F_14B", "F-14B", NAMES_B, LAND_B, "bare codes"),
         ("B-C", "F_14B", "F-14B", NAMES_C, LAND_C, "numbered, no names"),
         ("BU-A", "F_14BU", "F-14B(U)", NAMES_A, LAND_A, "B(U) scheme names")]


def build(out: Path, air: bool = False) -> Path:
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated livery files
        return _build(out, air)


def _build(out: Path, air: bool) -> Path:
    from dcs import mapping, planes, task
    from dcs.mission import Mission, StartType
    from dcs.terrain import caucasus
    m = Mission(caucasus.Caucasus())
    m.start_time = datetime.datetime(2000, 6, 12, 9, 0)
    blue = m.country("USA")
    ap = m.terrain.airports["Kutaisi"]
    ax, ay = ap.position.x, ap.position.y
    legend = []
    for key, cls, label, names, land, note in SLOTS:
        g = m.flight_group_from_airport(blue, f"Probe {key}", getattr(planes, cls), ap, maintask=task.CAP,
                                        start_type=StartType.Runway if air else StartType.Warm, group_size=1)
        g.units[0].set_client()               # a Client slot: XO picks one of the four in the slot screen
        g.units[0].name = f"Probe {key} 1-1"
        for (dn, de), nm in zip(ROUTE, names):
            g.add_waypoint(mapping.Point(ax + dn * 1000, ay + de * 1000, m.terrain), ALT_M, SPEED_KPH, nm)
        lp = g.land_at(ap)
        lp.name = land
        legend.append(f"Probe {key}: {label}, {note}")
    text = ("SQE F-14B waypoint probe. Four slots, one route of 9 points + landing: 1 PUSH, 2 IP, 3 TGT, 4 second IP, 5 HA, 6 FP, 7 DP, 8, 9, then home base.\n"
            + "\n".join(legend) + "\nSee .private/f14b_probe/README.md for what to look at.")
    m.set_sortie_text("SQE F-14B waypoint probe")
    m.set_description_text(text)
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?", default=str(DEFAULT_OUT))
    ap.add_argument("--runway", dest="air", action="store_true", help="start the jets on the runway (ready to take off) instead of parked, engines running")
    a = ap.parse_args()
    p = build(Path(a.out), a.air)
    print(f"wrote {p}: 4 player slots at Kutaisi ({'on the runway' if a.air else 'parked, engines running'}); copy to <Saved Games>\\DCS\\Missions")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
