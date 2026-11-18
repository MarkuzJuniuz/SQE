"""F-14B waypoint probe (S90 / S103, XO 2026-11-18; tools only, nothing ships, no change in play).

What does the Heatblur F-14B do with a mission's waypoints and special points? Researched first (2026-11-18):
  * Heatblur manual, Mission Editor page (f14.manuals.heatblur.se/dcs/mission_editor.html), "Waypoints Types (F-14A/B Only)": the A/B has only three
    numbered waypoints, so "Waypoints 1-3: set directly in the mission editor. Home Base: set to the landing waypoint. All others: set by naming
    Navigation Target Points": Fix Point `FP`, Initial Point `IP`, Surface Target `ST`, Defended Point `DP`, Hostile Area `HA`, Datalink Waypoint 1-3
    `DLWP1` / `DLWP2` / `DLWP3`, Datalink Surface Target `DLST`, Datalink Fixed Point `DLFP`.
  * pydcs (`dcs/nav_target_point.py`) writes these as the group's `NavTargetPoints` (x, y, index, text_comment = the code); it names the F-14B (and JF-17) as the
    users. SQE writes none of them: `MissionBuilder._f14_special_namer` renames ordinary WAYPOINTS "IPXIP" / "TGTXST" (an "X" scheme for the F-14B(U)); no source
    for that scheme was found in the manual pages that could be read (forum threads returned 403): treat it as unverified.
  * F-14B(U), manual page "Mission Data Loader", "Designation of Special Points, Bullseye, LANTIRN, and Priority Waypoints" (read): a waypoint NAME ending in
    "X" + a designator sets the point: XFP, XIP, XHB, XDP, XHA, XST (e.g. OCEANA -> OCEANAXHB), then optionally D destination, 1 to 3 priority, 4 to 7 generic priority,
    B bullseye (one only), L LANTIRN (up to 20); the label is 5 characters and the suffix is not shown. "If more than one waypoint is designated as the same Special Point ...
    the navigation system will ignore all of the waypoints so designated." So SQE's B(U) names (IPXIP, TGTXST, RTBXHB, BULLSXB, DEPX1, MSHLX2, PUSHX3, one of each code) FOLLOW the
    manual; the B(U) page does not mention Navigation Target Points. (An earlier session wrote the scheme; I could not find its source, the manual page above is it.)
  * The A/B pages say nothing about a duplicate code, waypoints 4 and up, or the ENTER key; the probe asks the jet.

One small Caucasus mission, seven Client slots at Kutaisi (an F-14B / F-14B(U) each), all on the same area; the NAMING differs:
  B-A   F-14B     the manual's scheme: waypoints 1 MSHL, 2 PUSH, 3 EGR (+ plain 4 and 5 to see what 4+ does), nav target points IP, ST, FP, DP, HA and a SECOND IP; landing = home base
  B-B   F-14B     the manual's scheme, clean: waypoints 1 to 3, nav target points IP, ST, FP, DP, HA, DLWP1, DLST, DLFP (one each); landing = home base
  B-C   F-14B     the old guess: 9 ordinary waypoints named with the bare codes (PUSH, IP, ST, IP, HA, FP, DP, PT8, PT9): do names on waypoints do anything?
  B-D   F-14B     9 ordinary waypoints, no names: what happens to 4 to 9
  BU-A  F-14B(U)  the B(U) manual scheme as SQE writes it, clean: PUSHX1, IPXIP, TGTXST, HAXHA, FPXFP, DPXDP, PT7, BULLSXB, MSHLX2, landing RTBXHB (each code once)
  BU-B  F-14B(U)  as BU-A but a SECOND IP (IP2XIP in point 4): per the manual the jet ignores every point with a duplicated code
  BU-C  F-14B(U)  the A/B scheme (waypoints 1 to 3 + nav target points) as B-B: does the B(U) take nav target points at all?

  python tools/f14b_wp_probe.py [OUT.miz] [--runway]   default .private/f14b_probe/SQE_F14B_WP_Probe.miz; --runway starts the jets on the runway instead of parked
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
# offsets from Kutaisi in km: (north, east); a loop east / north-east of the field. Nothing is placed there: it is only a route.
ROUTE = [(20, 25), (40, 55), (65, 80), (50, 110), (80, 105), (30, 130), (15, 90), (5, 60), (-10, 35)]
NAMES_X = ["PUSHX1", "IPXIP", "TGTXST", "HAXHA", "FPXFP", "DPXDP", "PT7", "BULLSXB", "MSHLX2"]; LAND_X = "RTBXHB"
NAMES_XDUP = ["PUSHX1", "IPXIP", "TGTXST", "IP2XIP", "HAXHA", "FPXFP", "DPXDP", "PT8", "PT9"]
NAMES_BARE = ["PUSH", "IP", "ST", "IP", "HA", "FP", "DP", "PT8", "PT9"]
NAMES_MANUAL = ["MSHL", "PUSH", "EGR", "", ""]
# nav target points (north, east km from Kutaisi): where each coded point sits; a second IP sits elsewhere
NTP = {"IP": (45, 70), "ST": (70, 95), "FP": (30, 125), "DP": (10, 45), "HA": (85, 110), "IP#2": (55, 100), "DLWP1": (35, 35), "DLST": (75, 60), "DLFP": (55, 130)}
NTP_A = ["IP", "ST", "FP", "DP", "HA", "IP#2"]
NTP_B = ["IP", "ST", "FP", "DP", "HA", "DLWP1", "DLST", "DLFP"]
# (key, pydcs class, label, route points used, waypoint names, landing name, nav target codes, note)
SLOTS = [("B-A", "F_14B", "F-14B", 5, NAMES_MANUAL, "", NTP_A, "manual scheme, a second IP, plain points 4 and 5"),
         ("B-B", "F_14B", "F-14B", 3, NAMES_MANUAL[:3], "", NTP_B, "manual scheme, clean, with the datalink codes"),
         ("B-C", "F_14B", "F-14B", 9, NAMES_BARE, "HB", [], "bare codes as ordinary waypoint names"),
         ("B-D", "F_14B", "F-14B", 9, [""] * 9, "", [], "9 numbered waypoints, no names"),
         ("BU-A", "F_14BU", "F-14B(U)", 9, NAMES_X, LAND_X, [], "B(U) manual X names as SQE writes them, each code once"),
         ("BU-B", "F_14BU", "F-14B(U)", 9, NAMES_XDUP, LAND_X, [], "as BU-A with a second IP (duplicate code)"),
         ("BU-C", "F_14BU", "F-14B(U)", 3, NAMES_MANUAL[:3], "", NTP_B, "A/B scheme (nav target points) on the B(U)")]


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

    def pt(dn, de):
        return mapping.Point(ax + dn * 1000, ay + de * 1000, m.terrain)

    legend = []
    for key, cls, label, n, names, land, codes, note in SLOTS:
        g = m.flight_group_from_airport(blue, f"Probe {key}", getattr(planes, cls), ap, maintask=task.CAP,
                                        start_type=StartType.Runway if air else StartType.Warm, group_size=1)
        g.units[0].set_client()               # a Client slot: XO picks one of the slots in the slot screen
        g.units[0].name = f"Probe {key} 1-1"
        for (dn, de), nm in zip(ROUTE[:n], names):
            g.add_waypoint(pt(dn, de), ALT_M, SPEED_KPH, nm)
        lp = g.land_at(ap)
        lp.name = land
        for c in codes:
            g.add_nav_target_point(pt(*NTP[c]), c.split("#")[0])          # the Editor's "Navigation Target Point": its text comment is the code
        legend.append(f"Probe {key}: {label}, {note}")
    text = ("SQE F-14B waypoint probe. Seven slots, the same area, different naming (Heatblur: waypoints 1-3, home base = the landing point, the rest as named Navigation "
            "Target Points FP IP ST DP HA DLWP1-3 DLST DLFP).\n" + "\n".join(legend) + "\nSee .private/f14b_probe/README.md for what to look at.")
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
    print(f"wrote {p}: {len(SLOTS)} player slots at Kutaisi ({'on the runway' if a.air else 'parked, engines running'}); copy to <Saved Games>\\DCS\\Missions")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
