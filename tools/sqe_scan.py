"""SQE terrain scan tool (command line; lives in tools/, never ships in the exe).

  python tools/sqe_scan.py make OUT.miz              write the DCS scan mission (same one as Settings > Terrain scan)
  python tools/sqe_scan.py condense SCAN_DIR [--out FILE] [--theatre caucasus]
                                                     read the raw scan files (SQE_terrain_*, SQE_relief_*, SQE_roads_*.json
                                                     from <Saved Games>\\SQE) and write the small site list
                                                     sqe/data/theatres/<theatre>_sites.json and the built-in ground-height grid <theatre>_relief.json (2 km cells) that ship with SQE.

v0.41.198 (XO 2026-10-30): players must not have to run scans, and the first flights had SAMs floating in the sea. The raw scan is 2.5 MB and
needs DCS; the condensed file is a few tens of KB and is picked ahead of any live placement by the campaign (a later change).

The sites file also holds, for each airfield (red and blue), SAM and supply spots within 20 km of it (v0.41.199).
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
FIELD_QUOTA = {"sam": 30, "supply": 12}  # per airfield (v0.41.199, judgment call). Dense on purpose: the campaign moves each SAM site to the nearest spot, and the doctrinal layout (a Tor within 12 km of an SA-10, a short-range site 3.5 to 4.5 km out) only survives if that move is small
FIELD_SPACINGS_M = (1500.0, 1200.0, 1000.0)   # spots of one kind round a field may sit this close (the sector spots keep SPACINGS_M)
FIELD_RADIUS_M = 20000.0          # a field's spots lie within this of it (red's long-range SAM sites sit 7 to 19 km out, supply sites up to 15 km)
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


def field_centres() -> list:
    """[(id, x, y)] of every airfield of the pack, red and blue (red_fields, blue_fields; the pydcs airport positions the campaign builder uses). Blue's fuel farms and depots hang off its fields the same way."""
    from sqe import theatres
    th = theatres.active()
    t = theatres.terrain()
    out = []
    for f in list(th.get("red_fields", [])) + list(th.get("blue_fields", [])):
        p = t.airports[f["airport"]].position
        out.append((f["id"], p.x, p.y))
    return out


def _grid(tmask, relief, roads, cx: float, cy: float, radius: float, keep) -> tuple:
    """Candidate SAM / supply cells on a GRID_M grid round (cx, cy): dry land, near a road, and keep(x, y) true.
    -> ({"sam": [(roughness, road distance, x, y)], "supply": [...]}, {"water": n, "road": n})."""
    rej = {"water": 0, "road": 0}
    grid = {"sam": [], "supply": []}
    n = int(radius // GRID_M)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = cx + i * GRID_M, cy + j * GRID_M
            if math.hypot(x - cx, y - cy) > radius or not keep(x, y):
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
    return grid, rej


def _fill(kind: str, grid: dict, quota: int, taken: list, spacings=SPACINGS_M) -> tuple:
    """Fill one kind's quota from the grid, relaxing the flatness limit step by step. -> (spots, (limit used, spacing used))."""
    ch, sp, limit = [], spacings[0], ROUGH_STEPS[kind][0]
    for limit in ROUGH_STEPS[kind]:
        cands = [(rg + dr / 100.0, x, y) for rg, dr, x, y in grid[kind] if rg <= limit]
        ch, sp = _pick(cands, quota, taken, CROSS_M, spacings)
        if len(ch) >= quota:
            break
    return ch, (limit, sp)


def condense(scan_dir, theatre: str = "caucasus") -> tuple:
    """-> (the sites dict, a report [str]). Sectors: ground / SAM / supply spots round the 13 zone centres. Fields: SAM / supply spots round each red airfield
    (v0.41.199: red's SAM clusters, fuel farms and depots sit within 20 km of their field, which the sector spots do not cover; blue's fields get the same for their fuel farms)."""
    from sqe import theatres
    theatres.use(theatre)
    tmask, relief, roads = _load(Path(scan_dir), theatre)
    centres = sector_centres()
    report, sectors = [], []
    short = 0
    for si, (cx, cy) in enumerate(centres):
        spots = {k: [] for k in QUOTA}
        used = {k: None for k in QUOTA}
        taken = []
        # ground spots: scanned road points that belong to this sector and are on dry land
        gnd = []
        for (px, py) in _road_points(roads, cx, cy, SECTOR_RADIUS_M):
            if _owner(centres, px, py) != si:
                continue
            if tmask.land_ok(px, py, SEA_MARGIN_M):
                gnd.append((math.hypot(px - cx, py - cy), px, py))
        grid, _rej = _grid(tmask, relief, roads, cx, cy, SECTOR_RADIUS_M, lambda x, y, si=si: _owner(centres, x, y) == si)
        for k in ("sam", "supply"):
            spots[k], used[k] = _fill(k, grid, QUOTA[k], taken)
            taken += spots[k]
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
    fields = []
    flds = field_centres()
    for fid, fx, fy in flds:
        taken_sam = [(x, y) for s in sectors for x, y in s["sam"] if math.hypot(x - fx, y - fy) <= FIELD_RADIUS_M]
        taken_sup = [(x, y) for s in sectors for x, y in s["supply"] if math.hypot(x - fx, y - fy) <= FIELD_RADIUS_M]
        grid, _rej = _grid(tmask, relief, roads, fx, fy, FIELD_RADIUS_M,
                           lambda x, y, fid=fid: min(flds, key=lambda f: math.hypot(f[1] - x, f[2] - y))[0] == fid)
        spots, used = {}, {}
        for k, tk in (("sam", taken_sam), ("supply", taken_sup)):
            spots[k], used[k] = _fill(k, grid, FIELD_QUOTA[k], list(tk), FIELD_SPACINGS_M)
        fields.append({"id": fid, "x": round(fx), "y": round(fy), **{k: [[round(x), round(y)] for x, y in v] for k, v in spots.items()}})
        row = " ".join(f"{k} {len(spots[k])}/{FIELD_QUOTA[k]}" for k in FIELD_QUOTA)
        relax = [f"{k}: relief <= {used[k][0]:.0f} m, spacing {used[k][1] / 1000:.1f} km" for k in ("sam", "supply") if used[k][0] != ROUGH_STEPS[k][0] or used[k][1] != FIELD_SPACINGS_M[0]]
        flag = ""
        if any(len(spots[k]) < FIELD_QUOTA[k] for k in FIELD_QUOTA):
            flag = "  <-- SHORT"
            short += 1
        report.append(f"field  {fid:11s}              {row}{flag}" + (f"   [relaxed: {'; '.join(relax)}]" if relax else ""))
    report.append(f"{len(sectors)} sectors and {len(fields)} fields, {short} short of quota")
    out = {"terrain": theatre, "version": 2, "quota": QUOTA, "field_quota": FIELD_QUOTA, "sea_margin_m": SEA_MARGIN_M, "sector_radius_m": SECTOR_RADIUS_M,
           "field_radius_m": FIELD_RADIUS_M, "sectors": sectors, "fields": fields}
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


RELIEF_FACTOR = 2                 # the built-in relief grid has cells this many times wider than the scan's (2 km): never lower than the scan, so safe altitudes stay safe


def condense_relief(scan_dir, theatre: str = "caucasus") -> dict:
    """The built-in ground-height grid: the scan's 1 km cells merged RELIEF_FACTOR x RELIEF_FACTOR (highest ground = the highest of the block, so a ridge is never
    lost; average ground = the rounded average), packed as base64 of zlib of int16 differences along each row. Measured on XO's 2026-10-30 scan against the 1 km
    grid over 300 random legs of 30 to 150 km: highest ground never lower, +38 ft on average, +361 ft at the 95th percentile; radar visibility share 0.02 different on average."""
    import base64
    import sys
    import zlib
    from array import array
    from sqe import relief
    from sqe import theatres
    theatres.use(theatre)
    relief.configure(scan_dir)
    if not relief.available():
        sys.exit(f"no usable SQE_relief_{theatre}.json in {scan_dir}")
    R = relief._R
    f = RELIEF_FACTOR
    nx, ny = R["nx"] // f, R["ny"] // f

    def merge(src, how):
        rows = []
        for i in range(nx):
            blk = [src[i * f + a] for a in range(f)]
            row = []
            for j in range(ny):
                v = [r[j * f + b] for r in blk for b in range(f)]
                row.append(max(v) if how == "max" else int(round(sum(v) / len(v))))
            rows.append(row)
        return rows

    def pack(rows):
        a = array("h")
        for row in rows:
            prev = 0
            for v in row:
                a.append(v - prev)
                prev = v
        if sys.byteorder == "big":
            a.byteswap()
        return base64.b64encode(zlib.compress(a.tobytes(), 9)).decode("ascii")
    return {"terrain": theatre, "version": 1, "x0": int(R["x0"]), "y0": int(R["y0"]), "step": int(R["step"] * f), "nx": nx, "ny": ny, "unit": 10,
            "packing": "base64 of zlib of int16 differences along each row, rows in order",
            "max": pack(merge(R["max"], "max")), "mean": pack(merge(R["mean"], "mean"))}


def cmd_condense(a) -> None:
    out, report = condense(a.scan_dir, a.theatre)
    print("\n".join(report))
    dest = Path(a.out) if a.out else ROOT / "sqe" / "data" / "theatres" / f"{a.theatre}_sites.json"
    dest.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size / 1024:.0f} KB)")
    rel = condense_relief(a.scan_dir, a.theatre)
    rdest = dest.with_name(f"{a.theatre}_relief.json")
    rdest.write_text(json.dumps(rel, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {rdest} ({rdest.stat().st_size / 1024:.0f} KB, {rel['nx']} x {rel['ny']} cells of {rel['step']} m)")
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
