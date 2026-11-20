"""S108 part 1: REPORT-ONLY look at the road depots (the supply sites along the roads) of a new campaign, both sides. Tools only: nothing in `sqe/` changes, nothing ships.

    python tools/depot_report.py [--pack caucasus] [--levels 1,2,3] [--seeds 3,7,11] [--blue N] [--brief] [--jobs N]

Why: XO 2026-11-18 asked that no road depot lies unrealistically far from its owner and that the two sides' depots do not interleave along a road (B ---- R-depot ---- B-depot ---- R: if each side can
drive past the other's depot, why does it not shoot it). Today (`road_sites.build`): the spots come from the pack's sites file, a site's side is where its road connects (`road_front.site_side`), each
side then picks its own count with only its own 9 km separation (`SEP_M`), 5 km clear of airfields, plants 90 km from the front. There is NO distance cap from the owner and NO rule between the two
sides' sites. This tool measures what that gives. It changes no rule and flags nothing as wrong: the flags are only markers on raw numbers, the judgment is XO's.

For every (level, seed) it creates the campaign through `Session.new` (temp APPDATA, pinned randomness) and takes the road sites of BOTH sides (`state.assets` red / `state.blue_assets` blue with
`road_sites.is_road`). Per campaign it prints:
  1. per site: owner, and straight-line km to the owner's nearest airfield, nearest own sector centre (the centres on the owner's side of the front: `ground.path_pos` against `line_km`, the same
     rule as `road_front.cut_side`) and nearest own other site;
  2. the same three to the ENEMY's side; flags: F1 = nearer to an enemy field than to any own field; F2 = nearer to an enemy site than to any own site (needs two sites on the owner's side or
     one on the enemy's); F3 = farther than 150 km from every own field (the thresholds are report markers only);
  3. INTERLEAVING: for every route of `road_front.routes(th)` the sites of both sides within 3 km of the route (`road_front.SNAP_M`) are ordered by distance along the route; a route whose
     order is not "all of one side, then all of the other" (two or more side changes: B R B R) is listed with the ordered site ids and the along-route gaps (km) between neighbours of different sides;
  4. the smallest straight-line gap between any red site and any blue site.
Then a summary per level (sites per side, flags, interleaved routes, minimum cross-side gap). The Caucasus gives blue NO road sites (`road_sites_blue` 0 since S49), so its interleaving is empty by
construction; `--blue N` builds the same campaigns with N blue road sites (what the game had before S49 was 5) to show what the rule would face. `--pack syria` uses the stub under `.claude/crew-chief-internal/syria/` when the
campaign builds, else prints why not. One worker process per campaign (--jobs N, default cores minus 2, --jobs 1 = one process); the output is the same either way."""
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parallel
parallel.ensure_hashseed()
TMP = parallel.make_tmp("sqe_depots_")
os.environ["APPDATA"] = str(TMP / "appdata")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAR_KM = 150.0
SYRIA_DIR = ROOT / ".claude" / "crew-chief-internal" / "syria"


def _d(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1]) / 1000.0


def _near(p, pts):
    """(km, name) of the nearest of [(name, (x, y))], or (None, '-')."""
    best = min(((_d(p, q), n) for n, q in pts), default=(None, "-"))
    return best


def _along(rts, site, snap_m):
    """[(route index, km along that route)] for every route that passes within snap_m of the site."""
    out = []
    for ri, r in enumerate(rts):
        cum, best = 0.0, None
        for i in range(len(r) - 1):
            ax, ay = r[i]; bx, by = r[i + 1]
            dx, dy = bx - ax, by - ay
            L = math.hypot(dx, dy)
            t = max(0.0, min(1.0, ((site[0] - ax) * dx + (site[1] - ay) * dy) / max(1.0, dx * dx + dy * dy)))
            d = math.hypot(site[0] - (ax + t * dx), site[1] - (ay + t * dy))
            if d <= snap_m and (best is None or d < best[0]):
                best = (d, (cum + t * L) / 1000.0)
            cum += L
        if best is not None:
            out.append((ri, best[1]))
    return out


def one_case(task) -> dict:
    """One campaign: returns {lines, stat, error}."""
    pack, level, seed, blue_n, brief = task
    parallel.pin_task(f"depots:{pack}:{level}:{seed}:{blue_n}")
    from dataclasses import replace
    from sqe import difficulty, theatres
    from sqe import road_front, road_sites, ground
    from sqe.engine import Session
    from sqe.settings import AppSettings
    if pack != "caucasus" and SYRIA_DIR.is_dir() and SYRIA_DIR not in map(Path, theatres.EXTRA_DIRS):
        theatres.EXTRA_DIRS.append(str(SYRIA_DIR))
    if blue_n:
        difficulty.LEVELS[level] = replace(difficulty.LEVELS[level], road_sites_blue=blue_n)
    tag = f"{pack} L{level} s{seed}" + (f" +{blue_n} blue" if blue_n else "")
    try:
        (TMP / "saves").mkdir(parents=True, exist_ok=True)
        s = Session(AppSettings(dcs_saves=str(TMP / "saves"), persist=False))
        s.new(f"Dp{level}{seed}", "F-16C", level, seed=seed, theatre=pack)
    except Exception as e:                                        # a stub pack may not build a campaign yet
        return {"tag": tag, "lines": [f"{tag}: cannot build a campaign: {type(e).__name__}: {e}"], "stat": None, "error": f"{type(e).__name__}: {e}"}
    st, th = s.state, theatres.active()
    ap = road_front.airports(th)
    red_ap = [(n, ap[n]) for n in ([f["airport"] for f in th.get("red_fields", [])] + list(th.get("red_extra_airports") or [])) if n in ap]
    blue_ap = [(n, ap[n]) for n in (th.get("road_blue_airports") or []) if n in ap]
    g = st.ground or {}
    line = float(g.get("line_km", ground.line_km(g))) if g.get("centers") else 0.0
    centres = {"red": [], "blue": []}
    for i, c in enumerate(g.get("centers") or []):
        k, _lat = ground.path_pos(g, c[0], c[1])
        centres["red" if k < line else "blue"].append((f"c{i}", (c[0], c[1])))
    sites = {"red": [], "blue": []}
    for side, pool in (("red", st.assets), ("blue", st.blue_assets)):
        for a in sorted((x for x in pool.values() if road_sites.is_road(x) and x.kind in ground.SUPPLY_KINDS), key=lambda x: x.id):
            sites[side].append((a.id, (a.x, a.y), a.name, a.variant))
    fields = {"red": red_ap, "blue": blue_ap}
    lines = [f"== {tag}: road sites red {len(sites['red'])}, blue {len(sites['blue'])}; red fields {len(red_ap)}, blue fields {len(blue_ap)}; line at {line:.0f} km; "
             f"sector centres red {len(centres['red'])}, blue {len(centres['blue'])}"]
    flags = {"F1": 0, "F2": 0, "F3": 0}
    far_own = {"red": 0.0, "blue": 0.0}                           # the farthest site of each side from its own nearest field (km)
    rows = []
    for own, enemy in (("red", "blue"), ("blue", "red")):
        for sid, p, nm, var in sites[own]:
            f_own, fo = _near(p, fields[own]); f_en, fe = _near(p, fields[enemy])
            c_own, co = _near(p, centres[own]); c_en, ce = _near(p, centres[enemy])
            s_own, so = _near(p, [(i, q) for i, q, _n, _v in sites[own] if i != sid]); s_en, se = _near(p, [(i, q) for i, q, _n, _v in sites[enemy]])
            fl = []
            if f_own is not None:
                far_own[own] = max(far_own[own], f_own)
            if f_own is not None and f_en is not None and f_en < f_own:
                fl.append("F1"); flags["F1"] += 1
            if s_en is not None and (s_own is None or s_en < s_own):
                fl.append("F2"); flags["F2"] += 1
            if f_own is None or f_own > FAR_KM:
                fl.append("F3"); flags["F3"] += 1
            f = lambda v: "-" if v is None else f"{v:6.1f}"
            rows.append(f"  {sid} {own:4} {var:8} own: field {f(f_own)} ({fo}) centre {f(c_own)} site {f(s_own)} ({so}) | enemy: field {f(f_en)} ({fe}) centre {f(c_en)} site {f(s_en)} ({se})  {' '.join(fl)}")
    if not brief:
        lines += rows
    rts = road_front.routes(th) or []
    owner = {sid: side for side in ("red", "blue") for sid, _p, _n, _v in sites[side]}
    pos = {sid: p for side in ("red", "blue") for sid, p, _n, _v in sites[side]}
    per_route: dict = {}
    for sid, p in pos.items():
        for ri, km in _along(rts, p, road_front.SNAP_M):
            per_route.setdefault(ri, []).append((km, sid))
    inter = []
    for ri, lst in sorted(per_route.items()):
        lst.sort()
        seq = [owner[i] for _k, i in lst]
        changes = sum(1 for a, b in zip(seq, seq[1:]) if a != b)
        if changes >= 2:
            gaps = [f"{lst[j][1]}({owner[lst[j][1]][0]})-{lst[j + 1][1]}({owner[lst[j + 1][1]][0]}) {lst[j + 1][0] - lst[j][0]:.1f} km" for j in range(len(lst) - 1) if owner[lst[j][1]] != owner[lst[j + 1][1]]]
            inter.append((ri, [f"{i}({owner[i][0]})" for _k, i in lst], gaps))
    for ri, order, gaps in inter:
        lines.append(f"  INTERLEAVED route {ri}: " + " > ".join(order) + " | cross-side gaps: " + "; ".join(gaps))
    on_route = len({sid for lst in per_route.values() for _k, sid in lst})
    cross = [(_d(p, q), a, b) for a, p, _n, _v in sites["red"] for b, q, _m, _w in sites["blue"]
             for p, q in [(p, q)]]
    cross.sort()
    min_gap = cross[0][0] if cross else None
    lines.append(f"  farthest site from its own nearest field: red {far_own['red']:.0f} km, blue {far_own['blue']:.0f} km")
    lines.append(f"  flags: F1 {flags['F1']}, F2 {flags['F2']}, F3 {flags['F3']}; interleaved routes {len(inter)} of {len(rts)} (sites on a route: {on_route} of {len(pos)}); min red-blue gap "
                 + (f"{min_gap:.1f} km ({cross[0][1]} - {cross[0][2]})" if min_gap is not None else "- (one side has no sites)"))
    return {"tag": tag, "lines": lines, "error": None,
            "stat": {"level": level, "red": len(sites["red"]), "blue": len(sites["blue"]), "F1": flags["F1"], "F2": flags["F2"], "F3": flags["F3"], "inter": len(inter), "routes": len(rts), "gap": min_gap, "far_red": far_own["red"], "far_blue": far_own["blue"]}}


def main(argv, jobs=None) -> int:
    opt = {"--pack": "caucasus", "--levels": "1,2,3", "--seeds": "3,7,11", "--blue": "0"}
    brief = "--brief" in argv
    a = [x for x in argv if x != "--brief"]
    for i, x in enumerate(a):
        if x in opt and i + 1 < len(a):
            opt[x] = a[i + 1]
    levels = [int(v) for v in opt["--levels"].split(",")]
    seeds = [int(v) for v in opt["--seeds"].split(",")]
    tasks = [(opt["--pack"], lv, sd, int(opt["--blue"]), brief) for lv in levels for sd in seeds]
    res = parallel.map_cases(one_case, tasks, jobs, TMP)
    for r in res:
        for ln in r["lines"]:
            print(ln)
    ok = [r for r in res if r["stat"]]
    print(f"\n{len(res)} campaigns, {len(ok)} built ({parallel.map_cases.workers} worker(s))")
    if not ok:
        return 1
    print(f"\nSUMMARY {opt['--pack']}, blue road sites {opt['--blue']} (per level, over seeds {opt['--seeds']}; sites = per campaign, flags and interleaved routes = summed, gap = minimum)")
    print("level | red sites | blue sites | F1 nearer enemy field | F2 nearer enemy site | F3 >150 km | farthest from own field red/blue km | interleaved routes (of) | min red-blue gap km")
    for lv in levels:
        st = [r["stat"] for r in ok if r["stat"]["level"] == lv]
        if not st:
            continue
        gaps = [x["gap"] for x in st if x["gap"] is not None]
        print(f"  L{lv}  | {'/'.join(str(x['red']) for x in st):9} | {'/'.join(str(x['blue']) for x in st):10} | {sum(x['F1'] for x in st):21} | {sum(x['F2'] for x in st):20} | "
              f"{sum(x['F3'] for x in st):10} | {max(x['far_red'] for x in st):4.0f} / {max(x['far_blue'] for x in st):4.0f}{'':17}| {sum(x['inter'] for x in st):4} ({st[0]['routes']} routes x {len(st)}) | " + (f"{min(gaps):.1f}" if gaps else "-"))
    return 0


if __name__ == "__main__":
    _jobs, _args = parallel.pop_jobs(sys.argv[1:])
    sys.exit(main(_args, _jobs))
