"""Build a theatre pack's map file (`<id>_geo.json`: land, lakes, borders) from Natural Earth shapefiles (public domain), projected to DCS x / y with pydcs.

    python tools/geo_from_ne.py --pack syria --ne-dir .private/syria/ne [--tol 1500] [--out sqe/data/theatres/syria_geo.json]

`--ne-dir` holds the unzipped Natural Earth 1:10m folders `ne_10m_land`, `ne_10m_lakes` and `ne_10m_admin_0_boundary_lines_land` (naturalearthdata.com; the zips are
public domain, credited in the About box). The pack names the terrain (`dcs_terrain`) and the scan box (`scan.x0 / x1 / y0 / y1`): everything is clipped to the box (plus
`--margin`, 30 km) and simplified with Douglas-Peucker (`--tol`, metres). Output format = `caucasus_geo.json`: {"land": [[[x, y], ...], ...], "lakes": [...], "borders": [...]},
DCS metres, x north, y east, land and lake rings closed. A reader of shapefiles of its own (polygon and polyline records only), so no extra library is needed.
This tool only reads the Natural Earth folder and writes the one output file; it changes nothing else."""
from __future__ import annotations
import argparse
import json
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_shp(path: Path, bbox):
    """-> [[ring or line as [(lon, lat), ...], ...]] for every polygon / polyline record whose bounding box meets `bbox` = (lon0, lat0, lon1, lat1)."""
    data = path.read_bytes()
    stype = struct.unpack_from("<i", data, 32)[0]
    if stype not in (3, 5):
        raise ValueError(f"{path.name}: shape type {stype} (only polyline 3 and polygon 5 are read)")
    out, pos = [], 100
    while pos + 8 <= len(data):
        _num, clen = struct.unpack_from(">ii", data, pos)
        rec = pos + 8
        pos = rec + clen * 2
        if struct.unpack_from("<i", data, rec)[0] == 0:
            continue
        x0, y0, x1, y1 = struct.unpack_from("<4d", data, rec + 4)
        if x1 < bbox[0] or x0 > bbox[2] or y1 < bbox[1] or y0 > bbox[3]:
            continue
        nparts, npts = struct.unpack_from("<2i", data, rec + 36)
        parts = list(struct.unpack_from(f"<{nparts}i", data, rec + 44)) + [npts]
        base = rec + 44 + 4 * nparts
        pts = struct.unpack_from(f"<{2 * npts}d", data, base)
        for a, b in zip(parts, parts[1:]):
            out.append([(pts[2 * i], pts[2 * i + 1]) for i in range(a, b)])
    return out


def clip_ring(ring, x0, x1, y0, y1):
    """Sutherland-Hodgman against the box (x0..x1 north, y0..y1 east)."""
    def side(pt, k, lim, keep_ge):
        return pt[k] >= lim if keep_ge else pt[k] <= lim

    def cut(a, b, k, lim):
        t = (lim - a[k]) / (b[k] - a[k])
        return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
    pts = list(ring[:-1]) if ring and ring[0] == ring[-1] else list(ring)
    for k, lim, ge in ((0, x0, True), (0, x1, False), (1, y0, True), (1, y1, False)):
        if not pts:
            break
        nxt = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if side(cur, k, lim, ge):
                if not side(prev, k, lim, ge):
                    nxt.append(cut(prev, cur, k, lim))
                nxt.append(cur)
            elif side(prev, k, lim, ge):
                nxt.append(cut(prev, cur, k, lim))
        pts = nxt
    return pts


def clip_line(line, x0, x1, y0, y1):
    """Runs of the polyline that lie inside the box (a run is cut at the first point outside; the cut is not interpolated: the margin hides it)."""
    runs, cur = [], []
    for p in line:
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            cur.append(p)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


def dp(pts, tol):
    """Douglas-Peucker (iterative)."""
    n = len(pts)
    if n < 3:
        return list(pts)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = math.hypot(px - ax, py - ay) if L == 0 else abs(dx * (py - ay) - dy * (px - ax)) / L
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack.append((a, bi))
            stack.append((bi, b))
    return [p for p, k in zip(pts, keep) if k]


def project(terr, lonlat):
    from dcs import mapping
    return [(p.x, p.y) for p in (mapping.Point.from_latlng(mapping.LatLng(lat, lon), terr) for lon, lat in lonlat)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pack", required=True)
    ap.add_argument("--ne-dir", required=True)
    ap.add_argument("--tol", type=float, default=1500.0, help="simplify tolerance, metres")
    ap.add_argument("--margin", type=float, default=30000.0, help="clip box margin round the scan box, metres")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    from sqe import theatres
    th = theatres.load(a.pack) if not Path(a.pack).is_file() else json.loads(Path(a.pack).read_text(encoding="utf-8"))
    from dcs import terrain as T
    terr = getattr(T, th["dcs_terrain"])()
    sc = th["scan"]
    box = (sc["x0"] - a.margin, sc["x1"] + a.margin, sc["y0"] - a.margin, sc["y1"] + a.margin)
    # lon / lat window that surely holds the box: project the corners back is not needed, a wide window is only a speed filter
    lat_c, lon_c = th["lat"], th["lon"]
    bbox = (lon_c - 14.0, lat_c - 9.0, lon_c + 14.0, lat_c + 9.0)
    ne = Path(a.ne_dir)
    out = {"land": [], "lakes": [], "borders": []}
    for key, folder, shp, closed in (("land", "ne_10m_land", "ne_10m_land.shp", True), ("lakes", "ne_10m_lakes", "ne_10m_lakes.shp", True),
                                     ("borders", "ne_10m_admin_0_boundary_lines_land", "ne_10m_admin_0_boundary_lines_land.shp", False)):
        recs = read_shp(ne / folder / shp, bbox)
        for r in recs:
            # cut to the lon / lat window FIRST: a continent-sized ring holds points far from the map's central meridian, where the projection folds back
            if closed:
                r = clip_ring(r, bbox[0], bbox[2], bbox[1], bbox[3])
                if len(r) < 3:
                    continue
                pr = project(terr, r)
                ring = clip_ring(pr, *box)
                if len(ring) < 3:
                    continue
                ring = dp(ring + [ring[0]], a.tol)
                if len(ring) < 4:
                    continue
                out[key].append([[round(x), round(y)] for x, y in ring])
            else:
                for wrun in clip_line(r, bbox[0], bbox[2], bbox[1], bbox[3]):
                    pr = project(terr, wrun)
                    for run in clip_line(pr, *box):
                        run = dp(run, a.tol)
                        if len(run) >= 2:
                            out[key].append([[round(x), round(y)] for x, y in run])
        print(f"{key}: {len(recs)} records in the window, {len(out[key])} kept, {sum(len(r) for r in out[key])} points")
    dst = Path(a.out) if a.out else theatres.DATA / f"{th['id']}_geo.json"
    dst.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
