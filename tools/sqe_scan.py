"""SQE terrain scan tool (command line; lives in tools/, never ships in the exe).

  python tools/sqe_scan.py make OUT.miz              write the DCS scan mission (same one as Settings > Terrain scan)
  python tools/sqe_scan.py condense SCAN_DIR [--out FILE] [--theatre caucasus]
                                                     read the raw scan files (SQE_terrain_*, SQE_relief_*, SQE_roads_*.json
                                                     from <Saved Games>\\SQE) and write the small site list
                                                     sqe/data/theatres/<theatre>_sites.json that ships with SQE.

v0.41.198 (XO 2026-10-30): players must not have to run scans, and the first flights had SAMs floating in the sea. The raw scan is 2.5 MB and
needs DCS; the condensed file is a few tens of KB and is picked ahead of any live placement by the campaign (a later change).

The sites file holds, for each ground-war sector (the 13 zone centres of the front chain, `ground.zone_centers`), spots for three kinds:
  ground  front-line columns, garrisons, ground units: on a scanned road point
  sam     SAM sites: off the road, flat ground
  supply  fuel farms and depots: near a road, flat ground
Every spot is on land, clear of the sea by SEA_MARGIN_M and of rivers / ponds by terrainmask.RIVER_MARGIN. Quotas per sector (XO agreed 2026-10-29,
judgment call, no measurement): 20 ground, 12 SAM, 8 supply. The tool prints every sector that falls short.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

QUOTA = {"ground": 20, "sam": 12, "supply": 8}
SEA_MARGIN_M = 500.0              # a spot keeps this far from the sea or a big lake (XO 2026-10-29; the live default is 1,500 m)
SECTOR_RADIUS_M = 30000.0         # candidates lie within this of a sector centre (and nearer to it than to any other centre)
GRID_M = 500.0                    # candidate grid for SAM and supply spots
SPACINGS_M = (3000.0, 2200.0, 1500.0)   # minimum distance between two spots of one kind; tried in order until the quota is met
CROSS_M = 1000.0                  # a spot of one kind stays this far from the spots of the others
ROAD_NEAR_M = {"sam": (200.0, 2500.0), "supply": (100.0, 1500.0)}     # distance to the nearest scanned road point: (min, max). The roads file is a 2 km sample.
FLAT_M = {"sam": 40.0, "supply": 60.0}      # ground relief (highest minus average, 10 m units) round the spot must stay under this
ROUGH_STEPS = {"sam": (40.0, 70.0, 110.0), "supply": (60.0, 100.0, 150.0)}   # relaxed in turn if a sector cannot fill its quota
JUDGMENT = ("all numbers here are judgment calls: no public figure exists for where a battery or a depot may sit, they were chosen so that "
            "every sector can fill its quota while staying near roads and on flat, dry ground")


def sector_centres() -> list:
    """The 13 sector centres of the longest chain, as the campaign builder places them (even steps along the axis between the chain's airfields)."""
    from sqe import theatres, ground
    th = theatres.active()
    fr = th["front"]
    t = theatres.terrain()
    axis = []
    for n in fr["chain"]:
        a = t.airports[n["airport"]].position
        axis.append([a.x, a.y])
    return [tuple(c) for c in ground.zone_centers(axis, list(fr["leg_zones"]))]


def _load(scan_dir: Path, theatre: str):
    from sqe import terrainmask, relief, roads
    for mod in (terrainmask, relief, roads):
        mod.configure(scan_dir)
    for mod, what in ((terrainmask, "terrain"), (relief, "relief"), (roads, "roads")):
        if not mod.available():
            sys.exit(f"no usable SQE_{what}_{theatre}.json in {scan_dir}")
    return terrainmask, relief, roads


def _rough(relief, x: float, y: float) -> float:
    """Ground relief round (x, y) in metres: the largest (highest - average) over the 3 x 3 relief cells (1 km each) round the point."""
    best = 0.0
    st = 1000.0
    for dx in (-st, 0.0, st):
        for dy in (-st, 0.0, st):
            hi = relief.ground_m(x + dx, y + dy, "max")
            mean = relief.ground_m(x + dx, y + dy, "mean")
            if hi is None or mean is None:
                return 1e9
            best = max(best, hi - mean)
    return best


def _nearest_road(roads, x: float, y: float, limit: float):
    p = roads.snap(x, y, limit)
    return None if p is None else math.hypot(p[0] - x, p[1] - y)


def _owner(centres: list, x: float, y: float) -> int:
    return min(range(len(centres)), key=lambda i: math.hypot(centres[i][0] - x, centres[i][1] - y))


def _pick(cands: list, quota: int, taken: list, cross: float, spacings=SPACINGS_M) -> tuple:
    """Farthest-point sampling over the candidates [(score, x, y)] (lower score is better): start at the best one, then keep taking the candidate
    furthest from those chosen, never closer than the spacing to one of its kind or CROSS_M to another kind. Spacing relaxes until the quota fills.
    -> (chosen [(x, y)], spacing used)."""
    for sp in spacings:
        chosen = []
        pool = [c for c in sorted(cands) if all(math.hypot(c[1] - tx, c[2] - ty) >= cross for tx, ty in taken)]
        while pool and len(chosen) < quota:
            if not chosen:
                best = pool[0]
            else:
                best = max(pool, key=lambda c: (min(math.hypot(c[1] - cx, c[2] - cy) for cx, cy in chosen), -c[0]))
            chosen.append((best[1], best[2]))
            pool = [c for c in pool if math.hypot(c[1] - best[1], c[2] - best[2]) >= sp]
        if len(chosen) >= quota:
            return chosen, sp
    return chosen, spacings[-1]


def condense(scan_dir, theatre: str = "caucasus") -> tuple:
    """-> (the sites dict, a report [str])."""
    from sqe import theatres
    theatres.use(theatre)
    tmask, relief, roads = _load(Path(scan_dir), theatre)
    centres = sector_centres()
    report, sectors = [], []
    short = 0
    for si, (cx, cy) in enumerate(centres):
        rej = {"water": 0, "road": 0, "rough": 0}
        spots = {k: [] for k in QUOTA}
        used = {k: None for k in QUOTA}
        taken = []
        # ground spots: scanned road points that belong to this sector and are on dry land
        gnd = []
        for (px, py) in _road_points(roads, cx, cy, SECTOR_RADIUS_M):
            if _owner(centres, px, py) != si:
                continue
            if not tmask.land_ok(px, py, SEA_MARGIN_M):
                rej["water"] += 1
                continue
            gnd.append((math.hypot(px - cx, py - cy), px, py))
        # sam / supply: a grid, scored by roughness then by distance to a road
        grid = {"sam": [], "supply": []}
        n = int(SECTOR_RADIUS_M // GRID_M)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                x, y = cx + i * GRID_M, cy + j * GRID_M
                if math.hypot(x - cx, y - cy) > SECTOR_RADIUS_M or _owner(centres, x, y) != si:
                    continue
                if not tmask.land_ok(x, y, SEA_MARGIN_M):
                    rej["water"] += 1
                    continue
                dr = _nearest_road(roads, x, y, 2500.0)
                rg = _rough(relief, x, y)
                for k in ("sam", "supply"):
                    lo, hi = ROAD_NEAR_M[k]
                    if dr is None or not lo <= dr <= hi:
                        rej["road"] += 1
                        continue
                    grid[k].append((rg, dr, x, y))
        for k in ("sam", "supply"):
            for limit in ROUGH_STEPS[k]:
                cands = [(rg + dr / 100.0, x, y) for rg, dr, x, y in grid[k] if rg <= limit]
                ch, sp = _pick(cands, QUOTA[k], taken, CROSS_M)
                if len(ch) >= QUOTA[k]:
                    break
            used[k] = (limit, sp)
            spots[k] = ch
            taken += ch
        ch, sp = _pick(gnd, QUOTA["ground"], taken, CROSS_M)
        spots["ground"], used["ground"] = ch, (None, sp)
        sectors.append({"i": si, "x": round(cx), "y": round(cy), **{k: [[round(x), round(y)] for x, y in v] for k, v in spots.items()}})
        row = " ".join(f"{k} {len(spots[k])}/{QUOTA[k]}" for k in QUOTA)
        relax = [f"{k}: relief <= {used[k][0]:.0f} m, spacing {used[k][1] / 1000:.1f} km" for k in ("sam", "supply") if used[k][0] != ROUGH_STEPS[k][0] or used[k][1] != SPACINGS_M[0]]
        flag = ""
        if any(len(spots[k]) < QUOTA[k] for k in QUOTA):
            flag = "  <-- SHORT"
            short += 1
        report.append(f"sector {si:2d} ({cx / 1000:7.0f}, {cy / 1000:6.0f} km)  {row}{flag}" + (f"   [relaxed: {'; '.join(relax)}]" if relax else ""))
    report.append(f"{len(sectors)} sectors, {short} short of quota")
    out = {"terrain": theatre, "version": 1, "quota": QUOTA, "sea_margin_m": SEA_MARGIN_M, "sector_radius_m": SECTOR_RADIUS_M, "sectors": sectors}
    return out, report


def _road_points(roads, cx: float, cy: float, radius: float):
    r = roads
    b = r.BUCKET_M
    r._refresh()
    P = r._P or {}
    k = int(radius // b) + 1
    bx, by = int(cx // b), int(cy // b)
    for i in range(bx - k, bx + k + 1):
        for j in range(by - k, by + k + 1):
            for px, py in P.get((i, j), ()):
                if math.hypot(px - cx, py - cy) <= radius:
                    yield px, py


def cmd_make(a) -> None:
    from sqe import terrainprobe
    p = terrainprobe.make_probe(a.out)
    print(f"wrote {p}: start it in DCS (Fly), wait for COMPLETE, then copy the three SQE_*_{a.theatre}.json files from <Saved Games>\\SQE")


def cmd_condense(a) -> None:
    out, report = condense(a.scan_dir, a.theatre)
    print("\n".join(report))
    dest = Path(a.out) if a.out else ROOT / "sqe" / "data" / "theatres" / f"{a.theatre}_sites.json"
    dest.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size / 1024:.0f} KB)")
    print(JUDGMENT)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("out"); m.add_argument("--theatre", default="caucasus"); m.set_defaults(fn=cmd_make)
    c = sub.add_parser("condense"); c.add_argument("scan_dir"); c.add_argument("--out"); c.add_argument("--theatre", default="caucasus"); c.set_defaults(fn=cmd_condense)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
