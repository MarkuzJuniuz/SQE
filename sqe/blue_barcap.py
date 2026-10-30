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
from .models import BaseKind, ObjectiveType, Role

NM = 1852.0
DAILY_SORTIES = 2              # per serviceable airframe per day: the rule the packages follow (engine.plan_day)
SHARE = {1: 0.10, 2: 0.20, 3: 0.40}   # judgment call: red's patrol share is 0.20 / 0.30 / 0.40 (redair.DOCTRINE); blue's is lower at L1 / L2 (XO plays the sorties himself)
DAY_START, DAY_END = 6 * 60, 22 * 60   # the patrols are spread through these hours (minutes of the day)
PACKAGE_WINDOW_MIN = 100       # a package is out about this long after its start (judgment call)
PATROL_STOP = 0.25             # an unflown raid that meets a pair on station is stopped this much more often (judgment call)
PATROL_RAID_WEIGHT = 2.0       # ...and in an announced raid's odds the pair on station counts as this many CAP-weighted jets (a pair; judgment call)
PATROL_LOSS_P = 0.15           # a patrol that fights a raid loses a jet this often (judgment call)
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
    from . import carrier_hit
    _df = carrier_hit.deck_factor(state)                                    # v0.41.109: a damaged flight deck launches fewer patrols too
    free = {sid: int(DAILY_SORTIES * sq.available * (_df if state.bases[sq.base_id].kind == BaseKind.CARRIER else 1.0)) for sid, sq in state.squadrons.items()}
    used = {}
    flights, cover = [], {}
    _plan_guards(state, level, free, used, flights)                      # v0.41.88: the AWACS and tanker guards first (the tanker's is not optional)
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


# the guard of each support asset: key -> (tag, whether the guard sortie is the tanker's long stay)
GUARDS = {"bl_kc135": "TNKCAP", "bl_kc135mprs": "TNKCAP", "bl_e3": "HAVCAP", "bl_e2": "HAVCAP"}      # tankers first: their guard is not optional


def _guard_squadrons(state, base) -> list:
    """The fighters that guard an asset based at `base`: the base's own; else the nearest within reach; else any capable squadron (the tanker's
    guard is not optional). The player's squadron is left to the packages."""
    pl = state.player.squadron_id if getattr(state, "player", None) else None
    sqs = [q for q in _cap_squadrons(state, base) if q.id != pl]
    if sqs:
        return sqs
    cands = [sq for sq in state.squadrons.values() if sq.id != pl and Role.CAP in AIRCRAFT[sq.aircraft].roles and sq.available >= 2]
    return sorted(cands, key=lambda q: (-q.available, q.id))[:1]


def _plan_guards(state, level, free, used, flights) -> None:
    """Chains of guard sorties along the windows the AWACS / tanker types are on orbit (support_assets.plan). A share of the full cover
    (SHARE by level, the patrols' share), at least one sortie when the asset is up at all."""
    from . import support_assets as sa
    wins = (getattr(state, "barcap", None) or {}).get("support_flights") or {}
    for key, tag in GUARDS.items():
        a = (getattr(state, "support_assets", None) or {}).get(key)
        if a is None or not wins.get(key) or a["base_id"] not in state.bases:
            continue
        sqs = _guard_squadrons(state, state.bases[a["base_id"]])
        if not sqs:
            continue
        tanker = True                                                     # both guards stay long (a pair on a tanker / AWACS track flies 2 h, like red's tanker guard)
        e = barcap.endurance_min(sqs[0].aircraft, tanker)
        up = _union_minutes([(max(a_, DAY_START), min(b_, DAY_END)) for a_, b_ in wins[key] if min(b_, DAY_END) > max(a_, DAY_START)])
        step = max(1, e - barcap.HANDOVER_MIN)
        full = max(1, math.ceil(up / step))
        n = max(1, round(SHARE[level] * full))
        spans = sorted((tuple(w) for w in wins[key]))
        span_lo, span_hi = max(spans[0][0], DAY_START), min(spans[-1][1], DAY_END)
        gap = max(step, (span_hi - span_lo) // n)
        for j in range(n):
            sq = max((q for q in sqs if free[q.id] >= 2), key=lambda q: (free[q.id], q.id), default=None)
            if sq is None:
                break
            lo = span_lo + j * gap
            if lo >= 1440:
                break
            free[sq.id] -= 2
            used[sq.id] = used.get(sq.id, 0) + 2
            flights.append({"id": f"bg{state.day}-{key}.{j}", "kind": tag, "asset": key, "area": "", "squadron": sq.id, "aircraft": sq.aircraft,
                            "size": 2, "start": lo, "end": min(1440, lo + barcap.endurance_min(sq.aircraft, tanker)), "callsign": ""})


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


def _support_keys(p) -> list:
    """The support assets a package has that get a guard: its AWACS and its first tanker."""
    from .support_assets import BY_CLASS
    out = []
    for x in p.support:
        k = BY_CLASS.get(x.dcs_class)
        if k in GUARDS and (x.slot == "AWACS" or x.slot == "TANKER1") and k not in out:
            out.append(k)
    return out


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
        setp = bool(p.extra.get("setpiece"))                              # v0.41.109: the carrier raid setpiece gets the carrier CAP and the guards too
        tb_ = state.bases.get(obj.target_id)
        land_raid = (obj.type == ObjectiveType.FLEET_DEFENSE and tb_ is not None and tb_.kind == BaseKind.AIRFIELD and not setp)    # v0.41.114: a land-raid intercept
        if land_raid:
            pass
        elif (obj.type in _FLEET and not setp) or is_sweep(obj) or (obj.target_id not in state.assets and not setp):
            continue
        s0 = _minute(p.start)
        lo, hi = s0 - LEAD_MIN, s0 + PACKAGE_WINDOW_MIN
        if land_raid:
            txy = (tb_.x, tb_.y)                                           # the raided field is what the base CAP faces and guards
        elif setp:
            ba_ = state.assets.get(p.extra.get("bomber_wing", ""))
            txy = (ba_.x, ba_.y) if ba_ is not None else (state.bases[obj.target_id].x, state.bases[obj.target_id].y)
        else:
            txy = target_point(state, obj)
        assets = []
        if land_raid:
            assets.append(tb_)
        elif base_cap is not None and not setp:
            assets.append(base_cap)
        cv = next((state.bases[state.squadrons[f.squadron_id].base_id] for f in p.flights if not f.tag and f.squadron_id in state.squadrons
                   and state.bases[state.squadrons[f.squadron_id].base_id].kind == BaseKind.CARRIER), None)
        if cv is None and setp:
            cv = state.bases[obj.target_id]
        if cv is None:                                                    # v0.41.209 (XO 2026-10-30): the carrier group is in every mission now, so its scheduled CVCAP comes along when its window overlaps the sortie
            cv = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
        if cv is not None:
            assets.append(cv)
        have = {f.tag for f in p.flights if f.tag in ("BASECAP", "CVCAP")}
        for key in _support_keys(p):                                      # v0.41.88: the guard of each AWACS / tanker the package has
            tag = GUARDS[key]
            if tag in have:
                continue
            hit = [f for f in planned if f["kind"] == tag and f["asset"] == key and f["start"] <= hi and f["end"] >= lo]
            if not hit:
                continue
            pf = max(hit, key=lambda f: (min(f["end"], hi) - max(f["start"], lo), -f["start"]))
            sq = state.squadrons[pf["squadron"]]
            if not pf["callsign"]:
                pf["callsign"] = _next_callsign(state, sq, used)
            p.flights.append(FlightPlan(f"{p.id}-f{len(p.flights) + 1}", pf["callsign"], Role.CAP, sq.id, sq.aircraft, pf["size"], sq.base_id,
                                        _TAG_TASK[tag], False, tag, "", ""))
            have.add(tag)
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


def status_lines(state) -> list:
    """The campaign status lines for blue's patrols: the share of today's 24 h each area has a pair up (planned, `blue_cover`; the patrols fly
    06:00-22:00 only, so 67 % is the most), plus how many guard sorties watch the tankers and AWACS. [] when there is no plan yet."""
    bc = getattr(state, "barcap", None) or {}
    cover = bc.get("blue_cover") or {}
    if not bc.get("blue_flights"):
        return []
    dirs = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    parts = []
    for ar in barcap.plan_areas(state, "blue"):
        if ar["id"] in cover:
            parts.append((ar["name"], dirs[int(((ar.get("bearing", 0) % 360) + 22.5) // 45) % 8], round(100 * cover[ar["id"]] / 1440)))
    parts.sort(key=lambda t: (t[0], t[1]))
    by = {}
    for n, d, pc in parts:
        by.setdefault(n, []).append(f"{d} {pc}%")
    g = [f for f in bc["blue_flights"] if f["kind"] in ("HAVCAP", "TNKCAP")]
    out = ["BARCAP cover today (share of 24 h with a pair up):"] + [f"   {n}: " + ", ".join(v) for n, v in by.items()]
    if not by:
        out[0] = "BARCAP cover today: none planned"
    if g:
        out.append(f"Tanker / AWACS guards: {sum(1 for f in g if f['kind'] == 'TNKCAP')} tanker, {sum(1 for f in g if f['kind'] == 'HAVCAP')} AWACS sorties planned")
    return out


def patrol_up(state, rng, base, from_xy) -> tuple:
    """-> (is a pair on station over `base` on the side the raid comes from right now?, the squadron that flies it). The draw is the share of the day
    the area is covered (`state.barcap["blue_cover"]`, minutes of 1440: the patrols fly 06:00-22:00 only, so the night is open)."""
    ar = barcap.facing_area(state, "blue", base.id, from_xy)
    if ar is None:
        return False, None
    mins = ((getattr(state, "barcap", None) or {}).get("blue_cover") or {}).get(ar["id"], 0)
    if mins <= 0 or rng.random() >= min(1.0, mins / 1440.0):
        return False, None
    sq = next((f["squadron"] for f in (state.barcap.get("blue_flights") or []) if f["area"] == ar["id"]), None)
    return True, sq


def patrol_fight(state, rng, sq_id) -> str:
    """A patrol that fought a raid may lose a jet. -> a log line or ''."""
    sq = state.squadrons.get(sq_id) if sq_id else None
    if sq is None or sq.available <= 0 or rng.random() >= PATROL_LOSS_P:
        return ""
    sq.available -= 1
    return f"   the base patrol lost a jet in the fight ({sq.name}: {sq.available}/{sq.authorized} left)"
