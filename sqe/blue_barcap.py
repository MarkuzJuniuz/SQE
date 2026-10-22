"""Blue's standing BARCAP as a daily plan (v0.41.85), the mirror of red's patrol plan in redair.py.

Until v0.41.84 a base CAP or a carrier CAP existed only as a support slot of a package you (or the war sim) flew. Now each day plans them on
their own from the BARCAP areas (barcap.py): per defended field or boat, a few sorties through the day, paid out of the squadrons' daily sortie
budget BEFORE the packages are built, so patrols compete with packages for jets. The plan is saved in `state.barcap["blue_flights"]`; once the
packages' start times are known, `attach` gives each package the planned sortie of the area that faces its target and is up while it flies.
Always AI only (XO 2026-10-21).

Judgment calls (no public source): SHARE (the part of a base's daily sortie budget spent on standing patrols), DAY_START / DAY_END (when the
patrols fly), PACKAGE_WINDOW_MIN (how long a package is out), LEAD_MIN.
"""
from __future__ import annotations
import math

from . import barcap
from .aircraft import AIRCRAFT
from .models import BaseKind, Role

NM = 1852.0
DAILY_SORTIES = 2              # per serviceable airframe per day: the rule the packages follow (engine.plan_day)
SHARE = {1: 0.10, 2: 0.20, 3: 0.40}   # judgment call: red's patrol share is 0.20 / 0.30 / 0.40 (redair.DOCTRINE); blue's is lower at L1 / L2 (XO plays the sorties himself)
DAY_START, DAY_END = 6 * 60, 22 * 60   # the patrols are spread through these hours (minutes of the day)
PACKAGE_WINDOW_MIN = 100       # a package is out about this long after its start (judgment call)
LEAD_MIN = 10                  # a sortie that comes on station this soon after the package's start still covers it


def _cap_squadrons(state, base) -> list:
    """The fighter squadrons that fly a base's patrol: its own; a field with none borrows the nearest capable squadron within its combat radius."""
    own = [sq for sq in state.squadrons.values() if sq.base_id == base.id and Role.CAP in AIRCRAFT[sq.aircraft].roles and sq.available >= 2]
    if own or base.kind == BaseKind.CARRIER:
        return own
    best, best_d = None, 1e9
    for sq in state.squadrons.values():
        spec = AIRCRAFT[sq.aircraft]
        if Role.CAP not in spec.roles or sq.available < 2:
            continue
        b = state.bases[sq.base_id]
        d = math.hypot(b.x - base.x, b.y - base.y) / NM
        if d <= spec.combat_radius_nm and d < best_d:
            best, best_d = sq, d
    return [best] if best is not None else []


def plan(state, d) -> dict:
    """-> {"flights": [{id, kind BASECAP|CVCAP, asset, area, squadron, aircraft, size, start, end (minutes of the day), callsign ""}],
    "used": {squadron id: jet-sorties}, "cover": {area id: minutes covered}}."""
    bc = barcap.ensure(state)
    level = max(1, min(3, int(getattr(d, "level", 1))))
    free = {sid: DAILY_SORTIES * sq.available for sid, sq in state.squadrons.items()}
    used = {}
    flights, cover = [], {}
    for b in sorted((b for b in state.bases.values() if b.kind in (BaseKind.AIRFIELD, BaseKind.CARRIER)), key=lambda b: b.id):
        areas = [a for a in bc["blue"] if a["asset"] == b.id]
        sqs = _cap_squadrons(state, b)
        if not areas or not sqs:
            continue
        fav = sum(sq.available for sq in sqs)
        areas = areas[:max(1, fav // 2 - 1)]                              # one pair per area up at a time, one pair stays back (as red's)
        n = max(1, round(SHARE[level] * DAILY_SORTIES * fav / 2))         # the share of the base's day budget, in sorties of a pair
        per = [0] * len(areas)
        for k in range(n):
            per[k % len(areas)] += 1
        kind = "CVCAP" if b.kind == BaseKind.CARRIER else "BASECAP"
        for ai, ar in enumerate(areas):
            t, m = DAY_START + 45 * ai, per[ai]
            for j in range(m):
                sq = max((s for s in sqs if free[s.id] >= 2), key=lambda s: (free[s.id], s.id), default=None)
                if sq is None:
                    break
                e = barcap.endurance_min(sq.aircraft)
                step = max(e - barcap.HANDOVER_MIN, (DAY_END - DAY_START) // max(1, m))
                lo = t + j * step
                if lo >= 1440:
                    break
                free[sq.id] -= 2
                used[sq.id] = used.get(sq.id, 0) + 2
                flights.append({"id": f"bf{state.day}-{b.id}-{ai}.{j}", "kind": kind, "asset": b.id, "area": ar["id"], "squadron": sq.id,
                                "aircraft": sq.aircraft, "size": 2, "start": lo, "end": min(1440, lo + e), "callsign": ""})
            cover[ar["id"]] = _union_minutes([(f["start"], f["end"]) for f in flights if f["area"] == ar["id"]])
    return {"flights": flights, "used": used, "cover": cover}


def _union_minutes(spans: list) -> int:
    tot, cur_lo, cur_hi = 0, None, None
    for lo, hi in sorted(spans):
        if cur_hi is None or lo > cur_hi:
            if cur_hi is not None:
                tot += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
        else:
            cur_hi = max(cur_hi, hi)
    return tot + (cur_hi - cur_lo if cur_hi is not None else 0)


def _minute(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def attach(state, pkgs: list) -> None:
    """Give each ground-attack / counter-air package the planned base CAP and carrier CAP sortie that faces its target and is up while it flies.
    The same planned sortie keeps one callsign in every package that carries it (a merged mission builds it once, support_caps._gather_support)."""
    from . import raids
    from .packages import FlightPlan, _TAG_TASK, _next_callsign, is_sweep, target_point, _FLEET
    bc = (getattr(state, "barcap", None) or {})
    planned = bc.get("blue_flights") or []
    if not planned:
        return
    used = {}                                                             # the day's callsign counter, seeded from every flight already named
    for p in pkgs:
        for f in p.flights:
            nm, _, no = f.callsign.rpartition(" ")
            if no.isdigit():
                used[nm] = max(used.get(nm, 0), int(no))
    tw = [(b, w) for b, w in raids.target_weights(state) if b.kind != BaseKind.CARRIER]
    base_cap = max(tw, key=lambda bw: (bw[1], bw[0].id))[0] if tw else None
    for p in pkgs:
        obj = p.objective
        if obj.type in _FLEET or is_sweep(obj) or obj.target_id not in state.assets:
            continue
        s0 = _minute(p.start)
        lo, hi = s0 - LEAD_MIN, s0 + PACKAGE_WINDOW_MIN
        txy = target_point(state, obj)
        assets = []
        if base_cap is not None:
            assets.append(base_cap)
        cv = next((state.bases[state.squadrons[f.squadron_id].base_id] for f in p.flights if not f.tag and f.squadron_id in state.squadrons
                   and state.bases[state.squadrons[f.squadron_id].base_id].kind == BaseKind.CARRIER), None)
        if cv is not None:
            assets.append(cv)
        have = {f.tag for f in p.flights if f.tag in ("BASECAP", "CVCAP")}
        for b in assets:
            kind = "CVCAP" if b.kind == BaseKind.CARRIER else "BASECAP"
            ar = barcap.facing_area(state, "blue", b.id, txy)
            if ar is None or kind in have:
                continue
            hit = [f for f in planned if f["area"] == ar["id"] and f["start"] <= hi and f["end"] >= lo]
            if not hit:
                continue
            pf = max(hit, key=lambda f: (min(f["end"], hi) - max(f["start"], lo), -f["start"]))
            sq = state.squadrons[pf["squadron"]]
            if not pf["callsign"]:
                pf["callsign"] = _next_callsign(state, sq, used)
            p.flights.append(FlightPlan(f"{p.id}-f{len(p.flights) + 1}", pf["callsign"], Role.CAP, sq.id, sq.aircraft, pf["size"], sq.base_id,
                                        _TAG_TASK[kind], False, kind, "", b.id if b.id != sq.base_id else ""))
            have.add(kind)
