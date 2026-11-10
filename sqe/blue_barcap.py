"""Blue's standing BARCAP as a per-turn plan (v0.41.85; per turn since v0.41.339, campaign rules plan Phase 4b), the mirror of red's patrol plan in redair.py.

A base CAP or a carrier CAP is planned on its own from the BARCAP areas (barcap.py): each TURN `plan_turn` puts a pair up over a share of the areas that can be up (CAP_SHARE, by level, day or
night) and one guard pair for each AWACS / tanker that is on orbit in the turn, drawing the jets from the turn's ledger (`packages.Ledger`) BEFORE the packages are built, so patrols compete with
packages for jets and nothing is double-booked. A pair whose airframe stays 30 minutes (a short-legged type) costs two pairs: one in the first wave and a relief in the second. The plan of the
day so far is kept in `state.barcap["blue_flights"]` (every flight has its `turn`); once the packages' start times are known, `attach` gives each package the planned sortie of the area that
faces its target and is up while it flies. Every planned pair is committed to refit at the end of its turn (`Session._sorties`): through the package it covers, else by its own flight id.
Always AI only (XO 2026-10-21).

Judgment calls (no public source): CAP_SHARE (the part of the areas up in a turn), KEEP_BACK, PACKAGE_WINDOW_MIN (how long a package is out), LEAD_MIN.
"""
from __future__ import annotations
import math

from . import barcap, clock
from .aircraft import AIRCRAFT
from .models import BaseKind, ObjectiveType, Role

NM = 1852.0
# the share of the areas that can be up in a turn that have a pair on station, (day turn, night turn) by level, seeded: judgment call, a starting point for the balance pass (campaign rules plan
# section 6, Phase 13). Red's patrol share is higher (redair.RED_CAP_SHARE); blue's is lower at L1 / L2 because XO plays the sorties himself. It also sets how often an AWACS guard is up
# (the tanker's guard is planned every turn the tanker is on orbit).
CAP_SHARE = {1: (0.10, 0.05), 2: (0.20, 0.08), 3: (0.30, 0.10)}
KEEP_BACK = 2                  # an area patrol never takes a squadron's last pair of ready jets (they stay for the packages; as the day plan's "one pair stays back"; judgment call)
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


def _crew(ledger, sqs, wave: int, keep: int):
    """The squadron with the most jets for a pair in this wave (`keep` jets stay behind), or None."""
    return max((q for q in sqs if ledger.room(q.id, wave) >= 2 + keep), key=lambda q: (ledger.room(q.id, wave), q.id), default=None)


def _pairs(ledger, sqs, t0: int, t1: int, keep: int, tanker: bool = False) -> list:
    """The pairs one station needs in a turn [t0, t1), minutes of the day, drawn from the ledger: [(squadron, wave, start, end)]. One pair in the first wave, from the turn's start, stays as long
    as its airframe does (a long-legged pair, 120 minutes, holds the whole turn). A short-legged pair (30 minutes) is relieved by a second pair that goes up in the second wave. A pair that can only be
    crewed from the jets that are ready by the second wave goes up then."""
    from .timeofday import WAVE2_OFFSET_MIN
    out = []
    sq = _crew(ledger, sqs, 1, keep)
    if sq is not None:
        e = barcap.endurance_min(sq.aircraft, tanker)
        ledger.take(sq.id, 2, 1)
        out.append((sq, 1, t0, min(t1, t0 + e)))
        if t0 + e < t1 - barcap.HANDOVER_MIN:                             # a short leg: the second wave relieves it
            sq2 = _crew(ledger, sqs, 2, keep)
            if sq2 is not None:
                e2 = barcap.endurance_min(sq2.aircraft, tanker)
                ledger.take(sq2.id, 2, 2)
                out.append((sq2, 2, t0 + WAVE2_OFFSET_MIN, min(t1, t0 + WAVE2_OFFSET_MIN + e2)))
    else:
        sq = _crew(ledger, sqs, 2, keep)
        if sq is not None:
            e = barcap.endurance_min(sq.aircraft, tanker)
            ledger.take(sq.id, 2, 2)
            out.append((sq, 2, t0 + WAVE2_OFFSET_MIN, min(t1, t0 + WAVE2_OFFSET_MIN + e)))
    return out


def plan_turn(state, d, turn: int, t0: int, ledger, rng, wins: dict) -> list:
    """This turn's standing patrols and guards (v0.41.339, Phase 4b; it was a plan for the whole day, `plan`). `t0`: the turn's first minute of the day; `ledger`: the turn's jets (the pairs are taken
    off it, so the packages are built from what is left); `rng`: seeded by the turn; `wins`: this turn's AWACS / tanker windows (`support_assets.plan`). The turn's flights are added to
    `state.barcap["blue_flights"]` (those of earlier turns of the day stay; a plan of this turn made before is replaced) and `blue_cover` (minutes of the day each area has a pair up) is made
    again from them. -> this turn's flights [{id, kind BASECAP|CVCAP|HAVCAP|TNKCAP, asset, area, squadron, aircraft, size, start, end (minutes of the day), callsign "", turn, wave}]."""
    bc = barcap.ensure(state)
    level = max(1, min(3, int(getattr(d, "level", 1))))
    t1 = t0 + clock.TURN_MIN
    share = CAP_SHARE[level][1 if clock.is_night_turn(turn) else 0]
    flights = []
    _plan_guards(state, ledger, flights, turn, t0, t1, share, rng, wins)    # the AWACS and tanker guards first (the tanker's is not optional)
    cands = []
    for b in sorted((b for b in state.bases.values() if b.kind in (BaseKind.AIRFIELD, BaseKind.CARRIER)), key=lambda b: b.id):
        sqs = _cap_squadrons(state, b)
        if sqs:
            cands += [(b, ar, sqs) for ar in bc["blue"] if ar["asset"] == b.id]
    want = share * len(cands)
    want = int(want) + (1 if rng.random() < want - int(want) else 0)        # a share of the areas that can be up, a fraction is a seeded chance of one more
    order = list(range(len(cands)))
    rng.shuffle(order)
    up = 0
    for i in order:
        if up >= want:
            break
        b, ar, sqs = cands[i]
        kind = "CVCAP" if b.kind == BaseKind.CARRIER else "BASECAP"
        got = _pairs(ledger, sqs, t0, t1, KEEP_BACK)
        for j, (sq, wave, lo, hi) in enumerate(got):
            flights.append({"id": f"bf{turn}-{b.id}-{ar['id'].rsplit('-', 1)[-1]}.{j}", "kind": kind, "asset": b.id, "area": ar["id"], "squadron": sq.id, "aircraft": sq.aircraft,
                            "size": 2, "start": lo, "end": hi, "callsign": "", "turn": turn, "wave": wave})
        up += 1 if got else 0
    keep = [f for f in (bc.get("blue_flights") or []) if f.get("turn") is not None and f["turn"] < turn]     # earlier turns of the day stay; a whole-day plan from before v0.41.339 (no `turn`) goes
    bc["blue_flights"] = keep + flights
    cover = {ar["id"]: 0 for _b, ar, _s in cands}
    for ar_id in cover:
        cover[ar_id] = _union_minutes([(f["start"], f["end"]) for f in bc["blue_flights"] if f["area"] == ar_id])
    bc["blue_cover"] = cover
    return flights


# the guard of each support asset: key -> (tag, whether the guard sortie is the tanker's long stay)
GUARDS = {"bl_kc135": "TNKCAP", "bl_e3": "HAVCAP", "bl_e2": "HAVCAP"}      # tankers first: their guard is not optional


def _guard_squadrons(state, base) -> list:
    """The fighters that guard an asset based at `base`: the base's own; else the nearest within reach; else any capable squadron (the tanker's
    guard is not optional). The player's squadron is left to the packages."""
    pl = state.player.squadron_id if getattr(state, "player", None) else None
    sqs = [q for q in _cap_squadrons(state, base) if q.id != pl]
    if sqs:
        return sqs
    cands = [sq for sq in state.squadrons.values() if sq.id != pl and Role.CAP in AIRCRAFT[sq.aircraft].roles and sq.available >= 2]
    return sorted(cands, key=lambda q: (-q.available, q.id))[:1]


def _plan_guards(state, ledger, flights, turn, t0, t1, share, rng, wins) -> None:
    """One guard pair for each AWACS / tanker type that is on orbit in this turn (`wins`, from support_assets.plan). The tanker's guard is planned every turn it is up and takes any capable
    squadron's last pair; an AWACS guard is up with the turn's CAP share (seeded). A guard stays 120 minutes whatever the airframe (a pair on a tanker / AWACS track can refuel, like red's)."""
    from .timeofday import WAVE2_OFFSET_MIN
    for key, tag in GUARDS.items():
        a = (getattr(state, "support_assets", None) or {}).get(key)
        spans = [(max(s, t0), min(e, t1)) for s, e in (wins.get(key) or []) if e > t0 and s < t1]
        if a is None or not spans or a["base_id"] not in state.bases:
            continue
        if tag != "TNKCAP" and rng.random() >= share:
            continue
        sqs = _guard_squadrons(state, state.bases[a["base_id"]])
        if not sqs:
            continue
        lo, hi = min(s for s, _ in spans), max(e for _, e in spans)
        w = 1 if lo < t0 + WAVE2_OFFSET_MIN else 2
        sq = _crew(ledger, sqs, w, 0)
        if sq is None and w == 1:                                         # not ready at the turn's start: the second wave's jets go up when they are ready
            sq, w, lo = _crew(ledger, sqs, 2, 0), 2, max(lo, t0 + WAVE2_OFFSET_MIN)
        if sq is None or lo >= hi:
            continue
        ledger.take(sq.id, 2, w)
        flights.append({"id": f"bg{turn}-{key}", "kind": tag, "asset": key, "area": "", "squadron": sq.id, "aircraft": sq.aircraft, "size": 2, "start": lo,
                        "end": min(hi, lo + barcap.endurance_min(sq.aircraft, True)), "callsign": "", "turn": turn, "wave": w})


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


def attach(state, pkgs: list, until: int | None = None, since: int | None = None) -> None:
    """Give each ground-attack / counter-air package the planned base CAP and carrier CAP sortie that faces its target and is up while it flies.
    The same planned sortie keeps one callsign in every package that carries it (a merged mission builds it once, support_caps._gather_support).
    `until` / `since` (v0.41.338, Phase 4): only the planned sorties that START before `until` and END after `since` (minutes of the day: the turn's bounds) are attached: a sortie of the
    next turn is crewed and committed in that turn, one that ended before this turn began has been committed already."""
    from . import raids
    from .packages import FlightPlan, _TAG_TASK, _next_callsign, is_sweep, target_point, _FLEET
    bc = (getattr(state, "barcap", None) or {})
    planned = [f for f in (bc.get("blue_flights") or []) if (until is None or f["start"] < until) and (since is None or f["end"] > since)]
    if not planned:
        return
    used = {}                                                             # the day's callsign counter, seeded from every flight already named
    for p in pkgs:
        for f in p.flights:
            nm, _, no = f.callsign.rpartition(" ")
            if no.isdigit():
                used[nm] = max(used.get(nm, 0), int(no))
    for d_ in getattr(state, "plan_done", None) or []:                    # v0.41.338: the packages of the day's earlier turns (resolved, `plan_done`) have named flights too
        for f in d_.get("flights", []):
            nm, _, no = (f.get("callsign") or "").rpartition(" ")
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
            from . import fleet as _fleet
            cv = _fleet.carrier(state)                                    # v0.41.257: none while the carrier is sunk
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
    """The campaign status lines for blue's patrols: the share of 24 h each area has had a pair up so far today (`blue_cover` adds up the day's turns), plus how many guard sorties have watched
    the tankers and AWACS so far. [] when nothing is planned yet today."""
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
    out = ["BARCAP cover so far today (share of 24 h with a pair up):"] + [f"   {n}: " + ", ".join(v) for n, v in by.items()]
    if not by:
        out[0] = "BARCAP cover so far today: none planned"
    if g:
        out.append(f"Tanker / AWACS guards so far today: {sum(1 for f in g if f['kind'] == 'TNKCAP')} tanker, {sum(1 for f in g if f['kind'] == 'HAVCAP')} AWACS sorties")
    return out + detection_lines(state)


def detection_lines(state) -> list:
    """v0.41.348 (Phase 7b): what blue did not see today (raids the war sim settled without an Intercept package) and the AWACS airframes the war sim lost."""
    out = []
    ra = getattr(state, "raids", None) or {}
    n = int(ra.get("unseen_n", 0))
    if n:
        out.append(f"Raids not detected so far (no AWACS up): {n}")
    for a in (getattr(state, "support_assets", None) or {}).values():
        if a.get("side") == "blue" and a.get("war_lost"):
            out.append(f"{a['label']} airframes lost in the war sim: {a['war_lost']} ({a['available']}/{a['authorized']} left)")
    return out


def patrol_up(state, rng, base, from_xy, window: tuple | None = None) -> tuple:
    """-> (is a pair on station over `base` on the side the raid comes from?, the squadron that flies it).
    `window` = (lo, hi) minutes of the day (a raid package's start and the time it is out): the answer is whether a pair planned for the area is up in it (a turn's war-sim raid, v0.41.339:
    the planned pairs are known by turn). No window (the overnight raids, `raids.overnight`): a draw by the share of the day the area was covered (`state.barcap["blue_cover"]`, minutes of 1440 added up over the
    day's turns, so the night counts open when no pair flew in it)."""
    ar = barcap.facing_area(state, "blue", base.id, from_xy)
    if ar is None:
        return False, None
    bc = getattr(state, "barcap", None) or {}
    if window is not None:
        lo, hi = window
        f = next((f for f in (bc.get("blue_flights") or []) if f["area"] == ar["id"] and f["start"] <= hi and f["end"] >= lo), None)
        return (True, f["squadron"]) if f else (False, None)
    mins = (bc.get("blue_cover") or {}).get(ar["id"], 0)
    if mins <= 0 or rng.random() >= min(1.0, mins / 1440.0):
        return False, None
    sq = next((f["squadron"] for f in (bc.get("blue_flights") or []) if f["area"] == ar["id"]), None)
    return True, sq


def patrol_fight(state, rng, sq_id) -> str:
    """A patrol that fought a raid may lose a jet. -> a log line or ''."""
    sq = state.squadrons.get(sq_id) if sq_id else None
    if sq is None or sq.available <= 0 or rng.random() >= PATROL_LOSS_P:
        return ""
    sq.available -= 1
    pf = next((f for f in ((getattr(state, "barcap", None) or {}).get("blue_flights") or []) if f["squadron"] == sq_id and f.get("turn") == state.turn), None)
    if pf is not None:                                                    # the jet is the planned pair's loss: its commit to refit counts it (`Session._sorties`)
        pf["lost"] = pf.get("lost", 0) + 1
    return f"   the base patrol lost a jet in the fight ({sq.name}: {sq.available}/{sq.authorized} left)"
