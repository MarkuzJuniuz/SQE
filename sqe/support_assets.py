"""Tankers and AWACS as assets (v0.41.87): a small number of airframes at a base, an orbit that needs one up and a relief behind it.

Until now a package always got an AWACS and a tanker out of thin air. Now blue has a few airframes of each type (a table below, sources and
judgment calls named), and a package gets the AWACS / tanker only if one is on orbit while the package flies. A support aircraft
shot down in a flown mission leaves the count; missing airframes come back slowly. Red has no AWACS asset any more (the A-50 was deleted, XO 2026-11-08).
The guards (HAVCAP, tanker CAP) are planned per turn (blue_barcap._plan_guards).

Since v0.41.339 (campaign rules plan, Phase 4b) every airframe has its own clock and the orbit is planned PER TURN (`plan(state, turn)`, called by `Session.plan_turn`): an airframe flies its
time on orbit (`sortie_min`: the E-3 720 = six turns), then spends the turnaround in refit (`turnaround_min`); a relief goes up HANDOVER_MIN before the airframe it replaces leaves, if one is
ready. The clock is two lists on the asset dict, absolute campaign minutes (like `Squadron.refit`): `orbit` (when each airframe on orbit leaves) and `refit` (when each airframe in refit
is ready); an airframe in neither is ready on the ground. They live in `a["clk"]` with the start of the turn they belong to (and the start of the next, so planning the same turn twice does not
advance the clocks twice). No format change: an asset with no `clk` starts with every airframe ready.

Saved in `state.support_assets` (older saves get the table on first use) and the day's windows so far in `state.barcap["support_flights"]` (minutes of the day, reset by `Session._begin_day`).
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
# v0.41.334 (campaign rules plan, Phase 1; XO 2026-11-08 / 11-09): E-3 four airframes on 12 h shifts with a 6 h refit; 3 h standard refit; the carrier's S-3B a separate
# squadron of eight; red's A-50 is gone (XO: none). v0.41.335 (decision 11): the land tankers are the USAF's, eight KC-135 with the boom and no drogue (v0.41.334 split them
# 4 + 4 with an MPRS half on a misreading); the probe-equipped Navy jets (F-14, F/A-18C) are served by the S-3B only.
TABLE = {
    "bl_e3": ("blue", "E_3A", "Overlord", "rear", 4, 720, 360,
              "XO 2026-11-08: four airframes in 12 hour shifts, a 6 hour refit (high maintenance). USAF has about 30 E-3s, 26 of them at Tinker over four squadrons (Wikipedia, "
              "Boeing E-3 Sentry); E-3s refuel about every 4 to 6 hours on long surveillance (list25.com, low firmness); the shift length is a judgment call"),
    "bl_e2": ("blue", "E_2C", "Magic", "carrier", 4, 240, 360,
              "a carrier airborne early warning squadron has four E-2Cs (globalsecurity.org, VAW-126); the 4 h cycle and 6 h turnaround are judgment calls"),
    "bl_kc135": ("blue", "KC_135", "Arco", "rear", 8, 240, 180,
                 "XO 2026-11-08 / 11-09: eight land tankers, boom only (USAF tankers; the Navy's tanker is the S-3B), normal 3 h refit. The 465th Air Refueling Squadron "
                 "operates eight KC-135Rs (globalsecurity.org); the 4 h on station is a judgment call"),
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
        if sa.pop("bl_kc135mprs", None) is not None or sa.get("bl_kc135", {}).get("authorized", 8) < TABLE["bl_kc135"][4]:      # v0.41.335: a v0.41.334 campaign had 4 boom + 4 MPRS: the drogue half goes, the boom fleet is 8 (no format change)
            k = sa.get("bl_kc135")
            if k is not None and k["authorized"] < TABLE["bl_kc135"][4]:
                add = TABLE["bl_kc135"][4] - k["authorized"]
                k["authorized"] += add
                k["available"] = min(k["authorized"], k["available"] + add)
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


CATCHUP_TURNS = 24             # a clock not planned for longer than this (turns with night ops off are not planned: the airframes fly on through them) starts again from a ready fleet; a rule of thumb: two days


def _trim(orbit: list, refit: list, n: int) -> None:
    """A lost airframe leaves the lists: never more airframes in them than there are in service (`available`)."""
    while len(orbit) + len(refit) > max(0, n):
        if refit:
            refit.remove(max(refit))
        else:
            orbit.remove(min(orbit))


def _run(a: dict, orbit: list, refit: list, t0: int, t1: int) -> tuple:
    """One turn [t0, t1) (absolute minutes) of an asset's airframes. `orbit` / `refit`: the clock at t0. Each airframe flies `sortie_min` on orbit, then `turnaround_min` in refit; when the
    one on orbit has HANDOVER_MIN left a ready airframe goes up (it covers from then on, so a change of aircraft has no gap); with nobody on orbit the first ready airframe goes up now.
    -> ([(start, end)] windows of the airframes on orbit in this turn (the end is the airframe's own, it may be past t1), the orbit list at t1, the refit list at t1)."""
    e, rest = int(a["sortie_min"]), int(a["turnaround_min"])
    n = max(0, int(a["available"]))
    orbit, refit = sorted(orbit), sorted(refit)
    win = [(t0, o) for o in orbit if o > t0]
    t = t0
    while True:
        for o in [o for o in orbit if o <= t]:                           # time on orbit is over: the airframe goes to refit
            orbit.remove(o)
            refit.append(o + rest)
        launch = t if not orbit else max(t, max(orbit) - HANDOVER_MIN)
        if launch >= t1:
            break
        ready = n - len(orbit) - len(refit) + sum(1 for r in refit if r <= launch)
        if ready <= 0:                                                    # nobody is ready: wait for the first airframe out of refit, if it is in this turn
            nxt = min((r for r in refit if r > launch), default=None)
            if nxt is None or nxt >= t1:
                break
            t = nxt
            continue
        due = [r for r in refit if r <= launch]
        if due:
            refit.remove(min(due))
        orbit.append(launch + e)
        win.append((launch, launch + e))
        t = launch
    for o in [o for o in orbit if o <= t1]:
        orbit.remove(o)
        refit.append(o + rest)
    return win, sorted(orbit), sorted(r for r in refit if r > t1)


def _start(a: dict, turn: int) -> tuple:
    """The (orbit, refit) lists of an asset at the start of `turn`: from its saved clock (this turn's, or the next turn's from the turn before, carried over any turns that were not planned),
    else a fleet that is all ready. Trimmed to the airframes in service."""
    from . import clock
    clk = a.get("clk")
    orbit, refit = [], []
    if clk and 0 <= turn - int(clk["turn"]) <= CATCHUP_TURNS:
        if turn == clk["turn"]:
            orbit, refit = list(clk["orbit"]), list(clk["refit"])
        else:
            orbit, refit = list(clk["next"][0]), list(clk["next"][1])
            for t in range(int(clk["turn"]) + 1, turn):                     # turns nobody planned (a night with night ops off): the airframes fly on
                _trim(orbit, refit, int(a["available"]))
                _, orbit, refit = _run(a, orbit, refit, clock.minute(t), clock.minute(t) + clock.TURN_MIN)
    _trim(orbit, refit, int(a["available"]))
    return orbit, refit


def _merge(spans: list) -> list:
    out = []
    for s0, e0 in sorted(spans):
        if out and s0 <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e0))
        else:
            out.append((s0, e0))
    return out


def plan(state, turn: int | None = None) -> dict:
    """This turn's windows per asset (blue ones; red's are data only) -> {key: [(start, end)]}, minutes of the day (an end may be past the turn's, or past midnight: it is the airframe's own).
    They are added to the day's windows in state.barcap["support_flights"] (planning a turn again replaces that turn's windows). Advances each asset's airframe clock one turn (module docstring)."""
    from . import clock, fleet
    turn = state.turn if turn is None else int(turn)
    sa = ensure(state)
    bc = barcap.ensure(state)
    t0, t1 = clock.minute(turn), clock.minute(turn) + clock.TURN_MIN
    base = clock.day_start_minute(clock.day_of(turn))
    out = {}
    for k, a in sa.items():
        if a["side"] != "blue":
            continue
        if fleet.is_sunk_base(state, a.get("base_id", "")):                # v0.41.257: the boat's E-2C and S-3 are gone with it
            a.pop("clk", None)
            out[k] = []
            continue
        orbit, refit = _start(a, turn)
        win, o2, r2 = _run(a, orbit, refit, t0, t1)
        a["clk"] = {"turn": turn, "orbit": orbit, "refit": refit, "next": [o2, r2]}
        out[k] = [(s - base, e - base) for s, e in _merge(win)]
    fl = bc.setdefault("support_flights", {})
    for k, w in out.items():
        fl[k] = [list(x) for x in fl.get(k, []) if x[0] < t0 - base] + [list(x) for x in w]      # this turn's windows replace an earlier plan of the same turn
    return out


def covers(state, key: str, lo: int, hi: int) -> bool:
    """Is there an aircraft of this asset on orbit for the whole of [lo, hi] (minutes of the day)? Reads the day's windows planned so far: a package asks about [its start, 70 minutes after], and an
    airframe's window runs to its own end, so the relief of the next turn is not needed. A day with no plan yet (an old save) says yes."""
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
            clk = a.get("clk")
            for _ in range(n if clk else 0):                              # the airframe that was shot down was on orbit: it leaves the clock too (this turn's start and the next turn's)
                for lst in (clk["orbit"], clk["next"][0]):
                    if lst:
                        lst.pop(0)
            return f"{a['label']} (support aircraft) shot down: {a['available']}/{a['authorized']} airframes left"
    return ""


def replace_e3(state) -> list:
    """Every TURN (v0.41.337, Phase 3; it was inside the nightly `step`, so a 48 h replacement took 64 to 72 h): a missing E-3 is replaced one at a time every 48 hours
    (E3_REPLACEMENT_MIN, on the campaign clock, `state.turn`); the timer starts when the first airframe is seen missing. -> log lines."""
    from . import clock
    out = []
    now = clock.minute(state.turn)
    for a in ensure(state).values():
        if a["side"] != "blue" or a["dcs_class"] != "E_3A":
            continue
        if a["available"] >= a["authorized"]:
            a.pop("repl_due", None)
            continue
        if "repl_due" not in a:
            a["repl_due"] = now + E3_REPLACEMENT_MIN             # the timer starts when the first airframe is missing
        if now >= a["repl_due"]:
            a["available"] += 1
            a["repl_due"] = now + E3_REPLACEMENT_MIN
            out.append(f"{a['label']}: a replacement airframe arrived ({a['available']}/{a['authorized']})")
    return out


def step(state, rng) -> list:
    """Overnight: each missing blue airframe is back with RETURN_P. (The E-3 is replaced on its own 48 h clock, every turn: `replace_e3`.) -> log lines."""
    out = []
    for a in ensure(state).values():
        if a["side"] != "blue" or a["available"] >= a["authorized"]:
            continue
        if a["dcs_class"] == "E_3A":
            continue
        back = sum(1 for _ in range(a["authorized"] - a["available"]) if rng.random() < RETURN_P)
        if back:
            a["available"] += back
            out.append(f"{a['label']}: {back} airframe(s) back in service ({a['available']}/{a['authorized']})")
    return out
