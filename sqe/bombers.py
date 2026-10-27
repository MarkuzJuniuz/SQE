"""Red's bomber wing is a trump card (v0.41.105, XO 2026-10-22): the Tu-22M3s are expensive, so red keeps them back and sends a raid on the carrier
only in numbers and only when it has reason to: a window it judges safe, or desperation. One function, `decide`, answers for the day; the planner (war.py)
and the raid plan (packages.py) both call it, so they always agree.

Sources and judgment calls (the numbers below are JUDGMENT CALLS unless a source is named):
- Soviet naval aviation planned MASSED raids on carrier groups (an air division, up to about 100 bombers, per carrier battle group) and accepted
  expected losses "as high as 50%" (CIMSEC, "Deception and the Backfire Bomber"; Tokarev via CIMSEC "Kamikazes: The Legacy of Soviet Naval Aviation, Pt. 2").
  A raid went in with ECM and decoy groups and with fighter cover: a Su-15TM regiment against the E-2s, "one or two fighter squadrons" as escort
  (Gordon and Rigmant, quoted on forum.dcs.world). That supports "in numbers, with escorts". It does NOT support "only when no losses are expected":
  that rule is XO's game design (a small wing, so the bombers are precious), mirrored by sending everything when desperate.
- No source gives an escort ratio. XO's rule: 2 escorts per bomber (4 bombers + 4 escorts "didn't last long"). If red cannot field them, it holds.
- Safe / desperate thresholds, cooldowns and the Mozdok weight are judgment calls, tuned on the 100-day background sims."""
from __future__ import annotations

import math

from .loadouts import ENEMY_FIGHTERS, ENEMY_RADIUS_NM

NM = 1852.0
MIN_RAID = 4                  # never fewer bombers than this ("no 2-ship raids, ever", XO)
ESCORT_PER_BOMBER = 2         # escorts per bomber (XO's rule; no source)
MAX_RAID = 12                 # the biggest all-in raid
QUIET_DAYS = 1                # days red goes quiet before a staged raid launches (XO: "mysteriously quiet for a day or two"; 0 = no quiet day)
COOLDOWN_SAFE = 8
COOLDOWN_DESPERATE = 5
DESPERATE_AT = 1.0            # desperation score that sends everything
LOSING_HARD = 1.0             # air strength < 45 % or command < 50 % (the old "losing badly" test)
LOSING_SOFT = 0.6             # air strength < 60 % or command < 65 %
MOZDOK_WEIGHT = 0.5           # weight of "the bomber base itself is under attack" (a good weight, never enough alone)
FRONT_WEIGHT = 0.25           # the front is in its last stage
COVER_FLOOR = 0.3             # share of blue's fighters that is still ready when no patrol is up (alert launch), judgment call
BLUE_FIGHTERS_CAP = 8         # fighters a carrier can put against one raid, as far as red's estimate goes


def _bomber_wing(state):
    return next((w for w in state.enemy_air if "Tu_22M3" in w.types and not state.assets[w.base_asset_id].destroyed), None)


def _carrier(state):
    return next((b for b in state.bases.values() if b.kind.value == "CARRIER"), None)


def escort_options(state, bw, cv):
    """[(jets that can reach the carrier, wing, type)] best first: serviceable jets of one fighter type whose radius (x 0.85) reaches the carrier.
    v0.41.106: Mozdok's own escort squadron (role "escort", the bomber wing's fighters) is counted and goes FIRST when it can cover a minimum raid;
    the other fields are the fallback and the top-up."""
    out = []
    for w in state.enemy_air:
        a = state.assets[w.base_asset_id]
        if a.destroyed:
            continue
        d_nm = math.hypot(a.x - cv.x, a.y - cv.y) / NM
        sq = [q for q in w.sqns if q.role == "escort"] if w is bw else w.sqns
        for t in dict.fromkeys(q.aircraft for q in sq):
            if t in ENEMY_FIGHTERS and ENEMY_RADIUS_NM.get(t, 0) * 0.85 >= d_nm:
                out.append((sum(q.available for q in sq if q.aircraft == t), w, t))
    own = [r for r in out if r[1] is bw and r[0] >= MIN_RAID * ESCORT_PER_BOMBER]
    rest = sorted((r for r in out if r not in own), key=lambda r: (-r[0], r[1].base_asset_id, r[2]))
    return own + rest


def mozdok_pressure(state, bw) -> float:
    """0..1: how hard the bomber base itself has been hit (its field, its SAM cluster and early-warning radar)."""
    a = state.assets[bw.base_asset_id]
    key = a.id.split("_", 1)[1] if "_" in a.id else a.id
    cl = [x.health for x in state.assets.values() if x.kind.value in ("SAM", "EWR") and len(x.id.split("_")) > 1 and x.id.split("_")[1] == key]
    cluster = sum(cl) / len(cl) if cl else 1.0
    return max(0.0, min(1.0, (1.0 - min(a.health, cluster)) / 0.5))


def desperation(state, bw) -> float:
    from .war import totals
    t = totals(state)
    losing = LOSING_HARD if (t["enemy_air"] < 0.45 or t["c2"] < 0.5) else LOSING_SOFT if (t["enemy_air"] < 0.60 or t["c2"] < 0.65) else 0.0
    return losing + MOZDOK_WEIGHT * mozdok_pressure(state, bw) + (FRONT_WEIGHT if state.front >= 2 else 0.0)


def estimated_stop(state, d, n, cv) -> float:
    """Red's estimate of the chance blue stops the raid: the same shape as war._resolve_raid, with what red can see (blue's fighters on the carrier, how
    much of the day a patrol covers the side the raid would come from, blue's air defence)."""
    from .war import ROLE_WEIGHT
    from .models import Role
    from . import barcap
    fighters = sum(s.available for s in state.squadrons.values() if s.base_id == cv.id)
    cover = 0.0
    bw = _bomber_wing(state)
    if bw is not None:
        a = state.assets[bw.base_asset_id]
        ar = barcap.facing_area(state, "blue", cv.id, (a.x, a.y))
        if ar is not None:
            cover = min(1.0, ((getattr(state, "barcap", None) or {}).get("blue_cover") or {}).get(ar["id"], 0) / 1440.0)
    up = min(fighters, BLUE_FIGHTERS_CAP) * (COVER_FLOOR + (1.0 - COVER_FLOOR) * cover)
    s = up * ROLE_WEIGHT[Role.CAP]
    return s / (s + 2.5 + 2.0 * d.iads + 0.4 * ESCORT_PER_BOMBER * n)


def decide(state, d) -> dict:
    """Today's call on the carrier raid: {"mode": "hold" | "safe" | "desperate", "n": bombers, "escorts", "wing", "type", "why"}. Pure: the same state gives
    the same answer, so the planner and the raid plan agree. v0.41.109: a raid is STAGED the day before (QUIET_DAYS): the day red decides to go it only
    holds ("quiet": True, "stage": {...}; the planner records it with `note_stage`), and the raid launches on the staged day."""
    hold = lambda why: {"mode": "hold", "n": 0, "escorts": 0, "wing": "", "type": "", "why": why}
    bw, cv = _bomber_wing(state), _carrier(state)
    if getattr(d, "bomber_policy", "none") == "none" or bw is None or cv is None:
        return hold("no bomber wing or no carrier")
    avail = bw.available_of({"Tu_22M3"})                         # the wing also holds the escort squadron (v0.41.106)
    opts = escort_options(state, bw, cv)
    jets, ew, et = opts[0] if opts else (0, None, "")
    n_max = min(avail, jets // ESCORT_PER_BOMBER, MAX_RAID if getattr(d, "level", 3) >= 3 else 4)      # L2: the raid is 4 bombers and 8 escorts, always
    n_max -= n_max % 2
    go = lambda mode, n, desp: {"mode": mode, "n": n, "escorts": ESCORT_PER_BOMBER * n, "wing": ew.base_asset_id, "type": et,
                                "why": f"{mode}: {n} bombers, {ESCORT_PER_BOMBER * n} escorts (desperation {desp:.2f})"}
    stage = (state.raids or {}).get("bomber_stage") or {}
    if QUIET_DAYS > 0 and stage.get("launch") == state.day:      # the staged day: the raid goes if it still has its escorts
        n = min(int(stage.get("n", 0)), n_max)
        n -= n % 2
        if n < MIN_RAID:
            return hold(f"the staged raid is off: only {avail} bombers and {jets} escorts left")
        return go(stage.get("mode", "safe"), n, 0.0)
    if QUIET_DAYS > 0 and stage.get("launch", -1) > state.day:
        return {**hold("quiet day before the raid"), "quiet": True}
    if n_max < MIN_RAID:
        return hold(f"only {avail} bombers and {jets} escorts: not enough for a {MIN_RAID}-ship raid with {ESCORT_PER_BOMBER} escorts each")
    days = [x for x in ((state.raids or {}).get("bomber_days") or [])]
    cd_safe = max([x for x in days if x != state.day] or [-99])
    desp = desperation(state, bw)
    mode, n = "hold", 0
    if desp >= DESPERATE_AT:
        if state.day - cd_safe >= COOLDOWN_DESPERATE or state.day in days:
            mode, n = "desperate", n_max
    elif getattr(d, "bomber_safe_p", 0.0) > 0 and n_max >= MIN_RAID:
        if state.day - cd_safe >= COOLDOWN_SAFE or state.day in days:
            p = estimated_stop(state, d, MIN_RAID, cv)
            if p <= d.bomber_safe_p:
                mode, n = "safe", MIN_RAID
    if mode == "hold":
        return hold(f"holding the wing (desperation {desp:.2f})")
    if QUIET_DAYS > 0 and state.day not in days:                 # decided today: red goes quiet, the raid launches QUIET_DAYS from now
        return {**hold(f"quiet day: the raid ({mode}, {n} bombers) is staged"), "quiet": True, "stage": {"launch": state.day + QUIET_DAYS, "mode": mode, "n": n}}
    return go(mode, n, desp)


def note_stage(state, dec) -> None:
    """The planner records a staged raid once (a replan the same day finds it and keeps it)."""
    if not dec.get("stage"):
        return
    if state.raids is None:
        state.raids = {}
    cur = state.raids.get("bomber_stage") or {}
    if cur.get("launch", -1) < state.day:
        state.raids["bomber_stage"] = dict(dec["stage"])


def is_quiet(state) -> bool:
    """Is today the quiet day before a staged raid? Red flies its patrols only: no strikes, raids or surprise raids."""
    return QUIET_DAYS > 0 and ((state.raids or {}).get("bomber_stage") or {}).get("launch", -1) > state.day


def status_lines(state) -> list:
    """Overview lines: the quiet day (v0.41.148: the damaged-deck line is gone, XO wants no carrier line on the Overview)."""
    out = []
    if is_quiet(state):
        out.append("Red air is unusually quiet today: no strikes or raids, only patrols. Something is being prepared.")
    return out                                                           # v0.41.148 (XO 2026-10-25): the carrier gets no line on the Overview


def note_launch(state) -> None:
    """Remember that the raid is on today (planner calls this once it adds the objective)."""
    days = list((state.raids or {}).get("bomber_days") or [])
    if state.day not in days:
        days.append(state.day)
    if state.raids is None:
        state.raids = {}
    state.raids["bomber_days"] = days[-8:]
