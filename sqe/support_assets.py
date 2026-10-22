"""Tankers and AWACS as assets (v0.41.87): a small number of airframes at a base, an orbit that needs one up and a relief behind it.

Until now a package always got an AWACS and a tanker out of thin air. Now blue has a few airframes of each type (a table below, sources and
judgment calls named), each day plans when each type has an aircraft on orbit (sorties that fly their time on station, then spend a turnaround
on the ground before they can fly again), and a package gets the AWACS / tanker only if it is up while the package flies. A support aircraft
shot down in a flown mission leaves the count; missing airframes come back slowly. Red's A-50 is kept as data only (decoration, XO 2026-10-20).
The guards (HAVCAP, tanker CAP) are still package slots; planning them as chains of their own is the next step.

Saved in `state.support_assets` (older saves get the table on first use) and today's windows in `state.barcap["support_flights"]`.
"""
from __future__ import annotations
import math

from . import barcap
from .models import BaseKind

NM = 1852.0
UP_LEAD_MIN = 0                # a package needs its AWACS / tanker from its start...
UP_WINDOW_MIN = 70             # ...to this long after (the push, the target and the way home; judgment call)
RETURN_P = 0.34                # a missing airframe is back with this chance a day (about three days of repair or replacement; judgment call)

# key -> (side, dcs class, label, home, authorized, minutes on orbit per sortie, turnaround minutes, source)
TABLE = {
    "bl_e3": ("blue", "E_3A", "Overlord", "rear", 6, 480, 720,
              "USAF has about 30 E-3s, 26 of them at Tinker over four squadrons, so six or seven a squadron (Wikipedia, Boeing E-3 Sentry); "
              "more than 8 h aloft without refuelling (same page); the 12 h turnaround is a judgment call"),
    "bl_e2": ("blue", "E_2C", "Magic", "carrier", 4, 240, 360,
              "a carrier airborne early warning squadron has four E-2Cs (globalsecurity.org, VAW-126); the 4 h cycle and 6 h turnaround are judgment calls"),
    "bl_kc135": ("blue", "KC_135", "Arco", "rear", 8, 240, 480,
                 "the 465th Air Refueling Squadron operates eight KC-135Rs (globalsecurity.org); the 4 h on station and 8 h turnaround are judgment calls"),
    "bl_kc135mprs": ("blue", "KC135MPRS", "Texaco", "rear", 8, 240, 480,
                     "probe-and-drogue KC-135MPRS: a squadron of eight is a judgment call (same size as the boom squadron)"),
    "bl_s3": ("blue", "S_3B_Tanker", "Shell", "carrier", 4, 120, 240,
              "the carrier's recovery tanker: four S-3Bs, a 2 h cycle and 4 h turnaround are judgment calls"),
    "rd_a50": ("red", "A_50", "Mainstay", "rear", 16, 480, 720,
               "Russian A-50: 16 aircraft at Ivanovo Severny (Wikipedia, Beriev A-50; the figure is from about 2011, 2006 is not given); data only, "
               "the red AWACS never flies in a mission yet"),
}
BY_CLASS = {v[1]: k for k, v in TABLE.items() if v[0] == "blue"}
HANDOVER_MIN = barcap.HANDOVER_MIN


def _rear_blue_airfield(state):
    """The blue airfield furthest from every red air wing: where the AWACS and tankers are based."""
    reds = [state.assets[w.base_asset_id] for w in state.enemy_air if w.base_asset_id in state.assets]
    fields = [b for b in state.bases.values() if b.kind == BaseKind.AIRFIELD]
    if not fields:
        return None
    if not reds:
        return sorted(fields, key=lambda b: b.id)[0]
    return max(fields, key=lambda b: (min(math.hypot(b.x - r.x, b.y - r.y) for r in reds), b.id))


def ensure(state) -> dict:
    """The support assets of both sides, made once (an older save gets them here)."""
    sa = getattr(state, "support_assets", None)
    if sa:
        return sa
    carrier = next((b for b in state.bases.values() if b.kind == BaseKind.CARRIER), None)
    rear = _rear_blue_airfield(state)
    red_rear = max((state.assets[w.base_asset_id] for w in state.enemy_air if w.base_asset_id in state.assets),
                   key=lambda a: min((math.hypot(a.x - b.x, a.y - b.y) for b in state.bases.values()), default=0), default=None)
    sa = {}
    for key, (side, cls, label, home, n, on, turn, src) in TABLE.items():
        base = (carrier if home == "carrier" else rear) if side == "blue" else red_rear
        if base is None:
            continue
        sa[key] = {"id": key, "side": side, "dcs_class": cls, "label": label, "base_id": base.id, "authorized": n, "available": n,
                   "sortie_min": on, "turnaround_min": turn, "source": src}
    state.support_assets = sa
    return sa


def windows(a: dict, start: int = 0, end: int = 1440) -> list:
    """When this asset has an aircraft on orbit today: back-to-back sorties by the airframes that are ready, [(start, end)] in minutes of the day.
    Each sortie hands over HANDOVER_MIN before the last one leaves; an airframe that flew is ready again after its turnaround."""
    n = int(a["available"])
    e, turn = int(a["sortie_min"]), int(a["turnaround_min"])
    ready = [0] * n
    out, t = [], int(start)
    while n and t < end:
        k = min(range(n), key=lambda i: ready[i])
        if ready[k] > t:                                                  # nobody is ready: the orbit is empty until one is
            t = ready[k]
            if t >= end:
                break
        out.append((t, min(end, t + e)))
        ready[k] = t + e + turn
        t = t + e - HANDOVER_MIN
    return out


def plan(state) -> dict:
    """Today's windows per asset (blue ones; red's are data only) -> {key: [(start, end)]}, kept in state.barcap["support_flights"]."""
    sa = ensure(state)
    out = {k: windows(a) for k, a in sa.items() if a["side"] == "blue"}
    state.barcap["support_flights"] = {k: [list(w) for w in v] for k, v in out.items()}
    return out


def covers(state, key: str, lo: int, hi: int) -> bool:
    """Is there an aircraft of this asset on orbit for the whole of [lo, hi] (minutes of the day)? A day with no plan yet (an old save) says yes."""
    fl = (getattr(state, "barcap", None) or {}).get("support_flights")
    if not fl or key not in fl:
        return True
    t = lo
    for s, e in sorted(fl[key]):
        if s <= t < e:
            t = e
        if t >= hi:
            return True
    return t >= hi


def up_for(state, dcs_class: str, start_hhmm: str) -> bool:
    """Is the blue asset of this airframe class on orbit while a package that starts at `start_hhmm` flies? An empty start (planning) says yes."""
    key = BY_CLASS.get(dcs_class)
    if key is None or not start_hhmm:
        return True
    s0 = int(start_hhmm[:2]) * 60 + int(start_hhmm[3:5])
    return covers(state, key, s0 - UP_LEAD_MIN, s0 + UP_WINDOW_MIN)


def lose(state, label: str, n: int = 1) -> str:
    """A support aircraft shot down in a flown mission (found by its callsign label). -> a log line or ''."""
    for a in ensure(state).values():
        if a["side"] == "blue" and a["label"] == label and a["available"] > 0 and n > 0:
            a["available"] = max(0, a["available"] - n)
            return f"{a['label']} (support aircraft) shot down: {a['available']}/{a['authorized']} airframes left"
    return ""


def step(state, rng) -> list:
    """Overnight: each missing blue airframe is back with RETURN_P. -> log lines."""
    out = []
    for a in ensure(state).values():
        if a["side"] != "blue" or a["available"] >= a["authorized"]:
            continue
        back = sum(1 for _ in range(a["authorized"] - a["available"]) if rng.random() < RETURN_P)
        if back:
            a["available"] += back
            out.append(f"{a['label']}: {back} airframe(s) back in service ({a['available']}/{a['authorized']})")
    return out
