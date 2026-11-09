"""Tankers and AWACS as assets (v0.41.87): a small number of airframes at a base, an orbit that needs one up and a relief behind it.

Until now a package always got an AWACS and a tanker out of thin air. Now blue has a few airframes of each type (a table below, sources and
judgment calls named), each day plans when each type has an aircraft on orbit (sorties that fly their time on station, then spend a turnaround
on the ground before they can fly again), and a package gets the AWACS / tanker only if it is up while the package flies. A support aircraft
shot down in a flown mission leaves the count; missing airframes come back slowly. Red has no AWACS asset any more (the A-50 was deleted, XO 2026-11-08).
The guards (HAVCAP, tanker CAP) are planned chains from v0.41.88 (blue_barcap._plan_guards).

Saved in `state.support_assets` (older saves get the table on first use) and today's windows in `state.barcap["support_flights"]`.
"""
from __future__ import annotations
import math

from . import barcap
from .models import BaseKind

NM = 1852.0
UP_LEAD_MIN = 0                # a package needs its AWACS / tanker from its start...
UP_WINDOW_MIN = 70             # ...to this long after (the push, the target and the way home; judgment call)
RETURN_P = 0.34                # a missing airframe is back with this chance a day (about three days of repair or replacement; judgment call). The E-3 is the exception: E3_REPLACEMENT_MIN
E3_REPLACEMENT_MIN = 2880      # a lost E-3 is replaced one airframe per 48 hours (XO 2026-11-08, game rule; the same slow rule as the Tu-22M3, refit.SLOW_REPL_MIN)

# key -> (side, dcs class, label, home, authorized, minutes on orbit per sortie, turnaround (refit) minutes, source)
# v0.41.334 (campaign rules plan, Phase 1; XO 2026-11-08 / 11-09): E-3 four airframes on 12 h shifts with a 6 h refit; the land tankers eight in all (the split below is Crew
# Chief's reading, 4 boom + 4 drogue, plan open item 2), 3 h standard refit; the carrier's S-3B a separate squadron of eight; red's A-50 is gone (XO: none).
TABLE = {
    "bl_e3": ("blue", "E_3A", "Overlord", "rear", 4, 720, 360,
              "XO 2026-11-08: four airframes in 12 hour shifts, a 6 hour refit (high maintenance). USAF has about 30 E-3s, 26 of them at Tinker over four squadrons (Wikipedia, "
              "Boeing E-3 Sentry); E-3s refuel about every 4 to 6 hours on long surveillance (list25.com, low firmness); the shift length is a judgment call"),
    "bl_e2": ("blue", "E_2C", "Magic", "carrier", 4, 240, 360,
              "a carrier airborne early warning squadron has four E-2Cs (globalsecurity.org, VAW-126); the 4 h cycle and 6 h turnaround are judgment calls"),
    "bl_kc135": ("blue", "KC_135", "Arco", "rear", 4, 240, 180,
                 "XO 2026-11-08: eight land tankers, normal 3 h refit; the split into 4 boom KC-135R here and 4 probe-and-drogue below is Crew Chief's reading "
                 "(plan item 2). The 465th Air Refueling Squadron operates eight KC-135Rs (globalsecurity.org); the 4 h on station is a judgment call"),
    "bl_kc135mprs": ("blue", "KC135MPRS", "Texaco", "rear", 4, 240, 180,
                     "probe-and-drogue KC-135MPRS, the other half of the eight land tankers (judgment call, same refit as the boom tankers)"),
    "bl_s3": ("blue", "S_3B_Tanker", "Shell", "carrier", 8, 120, 180,
              "the carrier's recovery tanker, its own squadron of eight S-3Bs (XO 2026-11-09; almost every carrier air wing had an eight-plane S-3 squadron, USNI Naval History, "
              "July 2012); same rules as the land tankers: 3 h refit; the 2 h on station is a judgment call"),
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
    sa = {}
    for key, (side, cls, label, home, n, on, turn, src) in TABLE.items():
        base = carrier if home == "carrier" else rear
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
    from . import fleet
    out = {k: ([] if fleet.is_sunk_base(state, a.get("base_id", "")) else windows(a)) for k, a in sa.items() if a["side"] == "blue"}          # v0.41.257: the boat's E-2C and S-3 are gone with it
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
    """Overnight: each missing blue airframe is back with RETURN_P; a missing E-3 is replaced one at a time every 48 hours (E3_REPLACEMENT_MIN, on the campaign
    clock, `state.turn`). -> log lines."""
    from . import clock
    out = []
    now = clock.minute(state.turn)
    for a in ensure(state).values():
        if a["side"] != "blue" or a["available"] >= a["authorized"]:
            a.pop("repl_due", None)
            continue
        if a["dcs_class"] == "E_3A":
            if "repl_due" not in a:
                a["repl_due"] = now + E3_REPLACEMENT_MIN             # the timer starts when the first airframe is missing
            if now >= a["repl_due"]:
                a["available"] += 1
                a["repl_due"] = now + E3_REPLACEMENT_MIN
                out.append(f"{a['label']}: a replacement airframe arrived ({a['available']}/{a['authorized']})")
            continue
        back = sum(1 for _ in range(a["authorized"] - a["available"]) if rng.random() < RETURN_P)
        if back:
            a["available"] += back
            out.append(f"{a['label']}: {back} airframe(s) back in service ({a['available']}/{a['authorized']})")
    return out
