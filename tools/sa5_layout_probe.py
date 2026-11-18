"""SA-5 layout probe (S90 P3b / P4, 2026-11-18; tools only, changes nothing, nothing ships).

Question (XO's decision input, not a fix): with ONE SA-5 site on the Syrian map and the planner's own rules keyed to its reach (samtier.SYSTEMS["SA-5"], measured about 65.9 nm
against a high flyer), where do the TARCAP / escort stations and the SEAD / DEAD stand-off points land, and does the ring block the coast?

    python tools/sa5_layout_probe.py [--alt FT]        (default 25000 ft: the F-16C / F/A-18C TARCAP altitude; the SA-5 reaches it, the planner's LOW tier is under its floor)

It builds no mission and no campaign: it feeds the planner's functions (`profiles.station`, `profiles.standoff`, `threatmap.umbrella_site`, `samtier`) a small hand-made state: the
three planned SA-5 sites (syria-pack-plan decision 10: Homs / Shayrat, Damascus / Al-Dumayr, Tiyas, each placed on the field's DCS position, a judgment call) and the Syria
airfields from pydcs, one site at a time. Targets are the red fields of the Hatay coast front; the blue side comes in from the carrier start spot (Larnaca, heading 140, 107 nm: plan
section 7) and from Hatay. Numbers are nm. The same code runs for the SA-10 (`--system SA-10`) as the Caucasus reference.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dcs.terrain import Syria                      # noqa: E402

from sqe import profiles, samtier, threatmap as tm   # noqa: E402
from sqe.models import AssetKind, EnemyAsset        # noqa: E402
from sqe.routes import NM, bearing, dist, offset    # noqa: E402

SITES = {"SA-5": ["Shayrat", "Damascus", "Tiyas"], "SA-10": ["Shayrat"]}      # where the site stands (the field's own position)
TARGETS = ["Bassel Al-Assad", "Rene Mouawad", "Shayrat", "Hama", "Abu al-Duhur", "Tiyas"]    # red fields of the coast front and the interior
REFS = ["Bassel Al-Assad", "Hatay", "Incirlik", "Larnaca"]      # the coast and the blue side, for "does it block"


def pos(T, name):
    a = T.airports[name]
    return a.position.x, a.position.y


def nm(a, b):
    return dist(a[0], a[1], b[0], b[1]) / NM


def fake_state(site_xy, variant, fields):
    assets = {"sam": EnemyAsset("sam", f"{variant} site", AssetKind.SAM, site_xy[0], site_xy[1], variant=variant)}
    for n, (x, y) in fields.items():
        assets["af_" + n] = EnemyAsset("af_" + n, n, AssetKind.AIRFIELD, x, y)
    return SimpleNamespace(assets=assets)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--alt", type=int, default=25000)
    ap.add_argument("--system", default="SA-5", choices=sorted(samtier.SYSTEMS))
    args = ap.parse_args(argv)
    T = Syria()
    var, alt = args.system, args.alt
    S = samtier.SYSTEMS[var]
    names = sorted(set(TARGETS + REFS + [n for v in SITES.values() for n in v]))
    P = {n: pos(T, n) for n in names + ["Larnaca"]}
    carrier = offset(*P["Larnaca"], 140.0, 107 * NM)
    P["Carrier start"] = carrier
    print(f"{var}: reach {S['reach_km'] / 1.852:.1f} nm (ring table {samtier.RANGE_NM[var]}), route avoid {S['avoid_nm']}, fighter station {S['station_nm']}, defender {S['scramble_nm']}, "
          f"sweep {S['sweep_nm']}, HARM point {S['harm_nm']}, JSOW point {S['jsow_keep_nm']}, DEAD gate {S['gate_km']} km, station rule {profiles.STATION_FRAC} x ring = "
          f"{profiles.STATION_FRAC * samtier.RANGE_NM[var]:.1f} nm; envelope {profiles.ENVELOPE[var]} ft; test altitude {alt} ft (hit: {profiles.hits(var, alt)})\n")
    for site_name in SITES[var]:
        sxy = P[site_name]
        st = fake_state(sxy, var, {n: P[n] for n in TARGETS if n != site_name})
        print(f"=== {var} at {site_name} ({sxy[0]:.0f}, {sxy[1]:.0f}) ===")
        print("  distance from the site, and which of its rules reach it:")
        for n in REFS + ["Carrier start"] + [t for t in TARGETS if t not in REFS]:
            d = nm(sxy, P[n])
            rules = [k for k, v in (("reach", S["reach_km"] / 1.852), ("avoid", S["avoid_nm"]), ("defender", S["scramble_nm"]), ("station", S["station_nm"]), ("sweep", S["sweep_nm"])) if d < v]
            print(f"    {n:18s} {d:6.1f} nm   inside: {', '.join(rules) or '-'}")
        print("  TARCAP / escort station (profiles.station) for a package from the carrier start spot, then from Hatay:")
        for tgt in TARGETS:
            if tgt == site_name:
                continue
            for origin in ("Carrier start", "Hatay"):
                ip = offset(*P[tgt], bearing(*P[tgt], *P[origin]), 20 * NM)
                pts = [P[origin], ip, P[tgt]]
                x, y, who, short, _ok = profiles.station(st, pts, alt)
                so = profiles.standoff(st, pts, alt)
                ref = {n: nm((x, y), P[n]) for n in ("Bassel Al-Assad", "Hatay")}
                print(f"    {tgt:16s} from {origin:13s} station {nm((x, y), sxy):5.1f} nm from the site, {short:5.1f} nm short of the target, by {','.join(who) or 'none'};"
                      f" {ref['Bassel Al-Assad']:5.1f} nm from Bassel, {ref['Hatay']:5.1f} from Hatay; stand-off stop "
                      f"{('%.1f nm short' % so[3]) if so else 'none'}")
        print("  SEAD / DEAD points against THIS site (analytic, on the carrier -> site line):")
        brg = bearing(*sxy, *carrier)
        for label, key in (("HARM point (samtier harm_nm)", "harm_nm"), ("JSOW launch point (jsow_keep_nm)", "jsow_keep_nm"), ("fighter station", "station_nm")):
            p = offset(sxy[0], sxy[1], brg, S[key] * NM)
            print(f"    {label:34s} {S[key]:5.1f} nm out: {nm(p, P['Bassel Al-Assad']):5.1f} nm from Bassel, {nm(p, carrier):5.1f} from the carrier start spot, {nm(p, P['Hatay']):5.1f} from Hatay")
        um = tm.umbrella_site(st, st.assets["af_" + TARGETS[0]]) if var in tm.UMBRELLA_VARIANTS else None
        print(f"  umbrella over {TARGETS[0]}: {'yes (' + var + ' covers it, practical reach)' if um else 'no'}\n")
    print(f"(umbrella variants active in this run: {list(tm.UMBRELLA_VARIANTS)}: the Syria tier, set below the way a pack's sam_tier block will set it)")

if __name__ == "__main__":
    samtier.configure({"umbrella": ["SA-5", "SA-10"], "gate": ["SA-2", "SA-3", "SA-6", "SA-11", "SA-10", "SA-5"]})      # the Syria tier, as the pack will name it
    main(sys.argv[1:])
