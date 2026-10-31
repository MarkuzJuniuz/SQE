"""SQE terrain scan tool (command line; lives in tools/, never ships in the exe).

  python tools/sqe_scan.py make OUT.miz              write the DCS scan mission (same one as Settings > Terrain scan)
  python tools/sqe_scan.py condense SCAN_DIR [--out FILE] [--theatre caucasus] [--scan-relief]
                                                     read the raw scan files (SQE_terrain_*, SQE_relief_*, SQE_roads_*.json
                                                     from <Saved Games>\\SQE) and write the small site list sqe/data/theatres/<theatre>_sites.json
                                                     (--scan-relief: also the ground-height grid from the scan)
  python tools/sqe_scan.py srtm TILE_DIR [--compare SCAN_DIR] [--no-download] [--keep]
                                                     build the built-in ground-height grid <theatre>_relief.json (2 km cells) from open SRTM tiles
                                                     (downloads the ones TILE_DIR lacks from the AWS open terrain tiles; needs numpy: pip install numpy);
                                                     --compare prints how it differs from a DCS scan. v0.41.201.

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


RELIEF_FACTOR = 2                 # the scan-built relief grid has cells this many times wider than the scan's (2 km)
SRTM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/skadi/{ns}{lat:02d}/{ns}{lat:02d}{ew}{lng:03d}.hgt.gz"      # AWS open terrain tiles (SRTM, 1 arc-second, 3601 x 3601 per degree)
SRTM_BLOCK = 8                    # each tile is cut down 8 x 8 (about 250 m) before use: block maximum + block average, then the 2 km cells are read from that
GRIDS = {"caucasus": (-430000.0, 190000.0, 2000.0, 250, 390)}      # theatre -> (x0, y0, cell size m, nx, ny): the shipped relief grid; same frame as the scan files
SRTM_CREDIT = "SRTM (NASA / USGS Shuttle Radar Topography Mission) via the AWS open terrain tiles, registry.opendata.aws/terrain-tiles"


def _pack_rows(rows) -> str:
    """int16 differences along each row, zlib 9, base64 (relief._parse_packed reads it)."""
    import base64
    import zlib
    from array import array
    a = array("h")
    for row in rows:
        prev = 0
        for v in row:
            a.append(int(v) - prev)
            prev = int(v)
    if sys.byteorder == "big":
        a.byteswap()
    return base64.b64encode(zlib.compress(a.tobytes(), 9)).decode("ascii")


def _relief_json(theatre, x0, y0, step, nx, ny, mx, mean, source) -> dict:
    return {"terrain": theatre, "version": 1, "x0": int(x0), "y0": int(y0), "step": int(step), "nx": nx, "ny": ny, "unit": 10, "source": source,
            "packing": "base64 of zlib of int16 differences along each row, rows in order", "max": _pack_rows(mx), "mean": _pack_rows(mean)}


def condense_relief(scan_dir, theatre: str = "caucasus") -> dict:
    """The built-in ground-height grid from a DCS scan: the scan's 1 km cells merged RELIEF_FACTOR x RELIEF_FACTOR (highest ground = the highest of the block, average
    ground = the rounded average). (v0.41.200; since v0.41.201 the shipped grid comes from SRTM, see condense_srtm; this stays as the fallback and for other theatres.)"""
    from sqe import relief
    from sqe import theatres
    theatres.use(theatre)
    relief.configure(scan_dir)
    if not relief.available():
        sys.exit(f"no usable SQE_relief_{theatre}.json in {scan_dir}")
    R = relief._R
    f = RELIEF_FACTOR
    nx, ny = R["nx"] // f, R["ny"] // f
    mx = [[max(R["max"][i * f + a][j * f + b] for a in range(f) for b in range(f)) for j in range(ny)] for i in range(nx)]
    mean = [[int(round(sum(R["mean"][i * f + a][j * f + b] for a in range(f) for b in range(f)) / (f * f))) for j in range(ny)] for i in range(nx)]
    return _relief_json(theatre, R["x0"], R["y0"], R["step"] * f, nx, ny, mx, mean, "DCS scan")


def srtm_tile_name(lat: int, lng: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lng >= 0 else 'W'}{abs(lng):03d}"


def _srtm_reduced(tile_dir: Path, lat: int, lng: int, fetch: bool, keep: bool, log: list):
    """(max, mean) of one tile cut down SRTM_BLOCK x SRTM_BLOCK, in metres, row 0 = north; None when the tile does not exist (open sea). Cached as reduced/<tile>.npz."""
    import gzip
    import numpy as np
    name = srtm_tile_name(lat, lng)
    cache = tile_dir / "reduced" / f"{name}.npz"
    if cache.exists():
        z = np.load(cache)
        return z["max"], z["mean"]
    src = tile_dir / f"{name}.hgt.gz"
    downloaded = False
    if not src.exists() and fetch:
        import urllib.error
        import urllib.request
        url = SRTM_URL.format(ns="N" if lat >= 0 else "S", lat=abs(lat), ew="E" if lng >= 0 else "W", lng=abs(lng))
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                src.write_bytes(r.read())
            downloaded = True
            log.append(f"downloaded {name}")
        except urllib.error.HTTPError as e:
            log.append(f"{name}: not available ({e.code}), treated as sea level")
            return None
    if not src.exists():
        log.append(f"{name}: missing, treated as sea level")
        return None
    raw = gzip.open(src).read()
    n = int((len(raw) / 2) ** 0.5)
    a = np.frombuffer(raw, ">i2").reshape(n, n).astype(np.float32)
    void = int((a <= -32000).sum())
    if void:
        log.append(f"{name}: {void} void samples set to sea level")
    a = np.clip(a, 0, None)[: n - 1, : n - 1]                  # sea-floor depths and voids to 0; the last row / column is the next tile's first
    k = (n - 1) // SRTM_BLOCK
    b = a[: k * SRTM_BLOCK, : k * SRTM_BLOCK].reshape(k, SRTM_BLOCK, k, SRTM_BLOCK)
    mx, mean = b.max(axis=(1, 3)).astype(np.float32), b.mean(axis=(1, 3)).astype(np.float32)
    cache.parent.mkdir(exist_ok=True)
    np.savez_compressed(cache, max=mx, mean=mean)
    if downloaded and not keep:
        src.unlink()
    return mx, mean


def condense_srtm(tile_dir, theatre: str = "caucasus", grid=None, fetch: bool = True, keep: bool = False) -> tuple:
    """The built-in ground-height grid from open SRTM tiles (v0.41.201). Each cell of the shipped grid (GRIDS) is read from the SRTM samples inside its box: the highest
    ground is the highest sample, rounded UP to 10 m; the average ground is the average. The box is the corners' lat/long bounding box, which is a little bigger than the
    cell (DCS's grid is turned up to about 7 degrees against north / east on the Caucasus map), so the highest ground can only come out a touch high, never low.
    Returns (json dict, report lines, mask) with mask[i][j] False for cells that needed a missing tile."""
    import numpy as np
    import dcs.terrain
    from dcs import mapping
    tile_dir = Path(tile_dir)
    tile_dir.mkdir(parents=True, exist_ok=True)
    x0, y0, step, nx, ny = grid or GRIDS[theatre]
    T = getattr(dcs.terrain, theatre.capitalize())()
    lat = np.zeros((nx + 1, ny + 1)); lng = np.zeros((nx + 1, ny + 1))
    for i in range(nx + 1):
        for j in range(ny + 1):
            p = mapping.Point(x0 + i * step, y0 + j * step, T).latlng()
            lat[i, j], lng[i, j] = p.lat, p.lng
    la0, la1, lo0, lo1 = int(math.floor(lat.min())), int(math.floor(lat.max())), int(math.floor(lng.min())), int(math.floor(lng.max()))
    log: list = []
    k = 3600 // SRTM_BLOCK
    nla, nlo = la1 - la0 + 1, lo1 - lo0 + 1
    Mx = np.zeros((nla * k, nlo * k), np.float32); Mn = np.zeros_like(Mx); have = np.zeros((nla, nlo), bool)
    for la in range(la0, la1 + 1):
        for lo in range(lo0, lo1 + 1):
            t = _srtm_reduced(tile_dir, la, lo, fetch, keep, log)
            if t is not None:
                r = (la1 - la) * k                              # mosaic row 0 = the north edge of the northernmost tile
                Mx[r:r + k, (lo - lo0) * k:(lo - lo0 + 1) * k], Mn[r:r + k, (lo - lo0) * k:(lo - lo0 + 1) * k] = t
                have[la - la0, lo - lo0] = True
    d = 1.0 / (k)                                                # degrees per reduced sample
    mx_rows, mean_rows, mask = [], [], []
    for i in range(nx):
        rm, rn, rk = [], [], []
        for j in range(ny):
            cl = (lat[i, j], lat[i + 1, j], lat[i, j + 1], lat[i + 1, j + 1]); cg = (lng[i, j], lng[i + 1, j], lng[i, j + 1], lng[i + 1, j + 1])
            r0 = int(math.floor((la1 + 1 - max(cl)) / d)); r1 = max(r0 + 1, int(math.ceil((la1 + 1 - min(cl)) / d)))
            c0 = int(math.floor((min(cg) - lo0) / d)); c1 = max(c0 + 1, int(math.ceil((max(cg) - lo0) / d)))
            r0, c0 = max(r0, 0), max(c0, 0)
            ok = all(have[la - la0, lo - lo0] for la in range(int(math.floor(min(cl))), int(math.floor(max(cl))) + 1) for lo in range(int(math.floor(min(cg))), int(math.floor(max(cg))) + 1))
            rk.append(ok)
            rm.append(int(math.ceil(float(Mx[r0:r1, c0:c1].max()) / 10.0)))
            rn.append(int(round(float(Mn[r0:r1, c0:c1].mean()) / 10.0)))
        mx_rows.append(rm); mean_rows.append(rn); mask.append(rk)
    miss = sum(1 for row in mask for v in row if not v)
    rep = log + [f"tiles N{la0}..{la1} x E{lo0}..{lo1}: {int(have.sum())} found of {nla * nlo}; {miss} of {nx * ny} cells need a missing tile (they read as sea level)",
                 f"highest ground {max(max(r) for r in mx_rows) * 10} m"]
    return _relief_json(theatre, x0, y0, step, nx, ny, mx_rows, mean_rows, SRTM_CREDIT), rep, mask


def compare_relief(new: dict, mask, scan_dir, theatre: str) -> list:
    """New grid against the DCS scan (the 1 km cells inside each new cell): how far apart the average ground is, and the highest ground."""
    import numpy as np
    from sqe import relief, theatres
    theatres.use(theatre)
    relief.configure(scan_dir)
    if not relief.available():
        return ["(no scan to compare with)"]
    g = relief._parse_packed(new)
    R = relief._R
    f = int(round(new["step"] / R["step"]))
    dm, dx, where = [], [], []
    for i in range(new["nx"]):
        for j in range(new["ny"]):
            if not mask[i][j] or i * f + f > R["nx"] or j * f + f > R["ny"]:
                continue
            sm = sum(R["mean"][i * f + a][j * f + b] for a in range(f) for b in range(f)) / (f * f) * 10
            sx = max(R["max"][i * f + a][j * f + b] for a in range(f) for b in range(f)) * 10
            dm.append(g["mean"][i][j] * 10 - sm); dx.append(g["max"][i][j] * 10 - sx); where.append((i, j))
    dm, dx = np.array(dm), np.array(dx)
    if not len(dm):
        return ["(no cells to compare)"]
    worst = np.argsort(-abs(dm))[:5]
    out = [f"compared {len(dm)} cells with the DCS scan",
           f"average ground, SRTM minus scan (m): mean {dm.mean():+.1f}, median {np.median(dm):+.1f}, mean absolute {abs(dm).mean():.1f}, 95th percentile of the absolute {np.percentile(abs(dm), 95):.0f}; {100 * (abs(dm) > 100).mean():.1f}% of cells differ by more than 100 m",
           f"highest ground, SRTM minus scan (m): mean {dx.mean():+.1f}, median {np.median(dx):+.1f}, 5th percentile {np.percentile(dx, 5):+.0f}, 95th {np.percentile(dx, 95):+.0f}"]
    for w in worst:
        i, j = where[w]
        out.append(f"  worst average-ground cell ({i},{j}) at x {new['x0'] + i * new['step']:.0f} y {new['y0'] + j * new['step']:.0f}: SRTM {g['mean'][i][j] * 10} m, scan {g['mean'][i][j] * 10 - dm[w]:.0f} m")
    return out


def cmd_condense(a) -> None:
    out, report = condense(a.scan_dir, a.theatre)
    print("\n".join(report))
    dest = Path(a.out) if a.out else ROOT / "sqe" / "data" / "theatres" / f"{a.theatre}_sites.json"
    dest.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size / 1024:.0f} KB)")
    if a.scan_relief:
        rel = condense_relief(a.scan_dir, a.theatre)
        rdest = dest.with_name(f"{a.theatre}_relief.json")
        rdest.write_text(json.dumps(rel, separators=(",", ":")), encoding="utf-8")
        print(f"wrote {rdest} ({rdest.stat().st_size / 1024:.0f} KB, {rel['nx']} x {rel['ny']} cells of {rel['step']} m, from the DCS scan)")
    print(JUDGMENT)


def cmd_srtm(a) -> None:
    out, rep, mask = condense_srtm(a.tile_dir, a.theatre, fetch=not a.no_download, keep=a.keep)
    print("\n".join(rep))
    if a.compare:
        print("\n".join(compare_relief(out, mask, a.compare, a.theatre)))
    dest = Path(a.out) if a.out else ROOT / "sqe" / "data" / "theatres" / f"{a.theatre}_relief.json"
    dest.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size / 1024:.0f} KB, {out['nx']} x {out['ny']} cells of {out['step']} m, from SRTM)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make"); m.add_argument("out"); m.add_argument("--theatre", default="caucasus"); m.set_defaults(fn=cmd_make)
    c = sub.add_parser("condense"); c.add_argument("scan_dir"); c.add_argument("--out"); c.add_argument("--theatre", default="caucasus"); c.add_argument("--scan-relief", action="store_true", help="also write the relief grid from the DCS scan (the shipped one comes from SRTM, see `srtm`)"); c.set_defaults(fn=cmd_condense)
    r = sub.add_parser("srtm"); r.add_argument("tile_dir"); r.add_argument("--out"); r.add_argument("--theatre", default="caucasus"); r.add_argument("--compare", metavar="SCAN_DIR")
    r.add_argument("--no-download", action="store_true"); r.add_argument("--keep", action="store_true", help="keep downloaded .hgt.gz files (they are 15 MB each; the reduced copy in tile_dir/reduced is enough)"); r.set_defaults(fn=cmd_srtm)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
