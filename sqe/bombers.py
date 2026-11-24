"""Red's bomber wing is a trump card (v0.41.105, XO 2026-10-22): the Tu-22M3s are expensive, so red keeps them back and sends a raid on the carrier
only in numbers and only when it has reason to: a window it judges safe, or desperation. One function, `decide`, answers for the day; the planner (war.py)
and the raid plan (packages.py) both call it, so they always agree.

Sources and judgment calls (the numbers below are JUDGMENT CALLS unless a source is named):
- Soviet naval aviation planned MASSED raids on carrier groups (an air division, up to about 100 bombers, per carrier battle group) and accepted
  expected losses "as high as 50%" (CIMSEC, "Deception and the Backfire Bomber"; Tokarev via CIMSEC "Kamikazes: The Legacy of Soviet Naval Aviation, Pt. 2").
  A raid went in with ECM and decoy groups and with fighter cover: a Su-15TM regiment against the E-2s, "one or two fighter squadrons" as escort
  (Gordon and Rigmant, quoted on forum.dcs.world). That supports "in numbers, with escorts". It does NOT support "only when no losses are expected":
  that rule is XO's game design (a small wing, so the bombers are precious), mirrored by sending everything when desperate.
- Escort ratio (XO 2026-11-03, v0.41.249): ONE escort per TWO bombers, what XO reads public sources to suggest for red doctrine (not checked by Crew Chief; the
  earlier rule was 2 per bomber, after a 4 + 4 raid "didn't last long"). A raid is the FULL size or none (16 bombers + 8 escorts at L3, 8 + 4 at L2), except
  when desperate, which sends what it has. If red cannot field them, it holds.
- Safe / desperate thresholds, cooldowns and the Mozdok weight are judgment calls, tuned on the 100-day background sims.
- B1 (XO 2026-11-21, red-standoff-plan): a pack may name SEVERAL bomber fields (`bomber_bases`, Syria: Damascus and Bassel Al-Assad; S142: each field's Tu-22M3 share is capped at its DCS stand count). The Tu-22M3 squadron and its escort squadron of each field are part of that field's red wing (one wing per
  field, like every other red field), `bomber_wings` lists the ones whose field is up, and the carrier raid and the land strike draw from all of them (the S46 pool: the first field gives what it has, the next the rest). A cut or
  destroyed field is skipped. With one bomber field (the Caucasus) every figure and every draw is what it was."""
from __future__ import annotations

import math
import random

from . import clock
from .loadouts import ENEMY_FIGHTERS, ENEMY_RADIUS_NM
from . import runways

NM = 1852.0
MIN_RAID = 4                  # never fewer bombers than this ("no 2-ship raids, ever", XO)
ESCORT_PER_BOMBER = 0.5       # escorts per bomber (XO 2026-11-03: 1 escort per 2 bombers; was 2 per bomber)
MAX_RAID = {2: 8, 3: 16}      # v0.41.260 (XO 2026-11-03): the full raid by level, L3 16 of the 24 at Mozdok, L2 8 of 14 (judgment calls: public sources give no raid size; the IISS count of about 55 to 57 Tu-22M3 in all of Russia says 24 in one raid is too many); was 12 / 24 (v0.41.249); L1 has no bomber wing
QUIET_DAYS = 1                # days red goes quiet before a staged raid launches (XO: "mysteriously quiet for a day or two"; 0 = no quiet day)
COOLDOWN_SAFE = 8
COOLDOWN_DESPERATE = 5
DESPERATE_AT = 1.0            # desperation score that sends everything
LOSING_HARD = 1.0             # air strength < 45 % or command < 50 % (the old "losing badly" test)
LOSING_SOFT = 0.6             # air strength < 60 % or command < 65 %
MOZDOK_WEIGHT = 0.5           # weight of "the bomber base itself is under attack" (a good weight, never enough alone)
FRONT_WEIGHT = 0.25           # red's air defence is broken (S20 Phase 3, replaces "the front is in its last stage"): judgment call, one step like the old front stage 2
FRONT_IADS_AT = 0.40          # ...when the mean health of red's SAM sites and EWRs (war.totals "iads") is this or less
COVER_FLOOR = 0.3             # share of blue's fighters that is still ready when no patrol is up (alert launch), judgment call
BLUE_FIGHTERS_CAP = 8         # fighters a carrier can put against one raid, as far as red's estimate goes
# v0.41.355 (campaign rules plan Phase 10a, XO 2026-11-10: "spread the risk on something more productive for red"): the Tu-22M3 LAND STRIKE, 2 Tu-22M3 + 2 Mozdok Su-27 on a blue supply site, comes FIRST in the bomber pool.
LAND_TU = 2                   # Tu-22M3 in one land strike (XO plan decision 34: a 2-ship escorted by a 2-ship); B1: a pack's `land_tu` {level: n} replaces it (`land_tu(d)`; Syria L3 4, XO 2026-11-21)
LAND_ESCORTS = 2              # Mozdok Su-27 that ride along (the floor: a bigger strike takes one escort per two Tu-22M3, rounded up, `land_escorts(d)`; the 2-ship stays 2 + 2)
LAND_STRIKES_PER_DAY = {2: 1, 3: 2}   # land strikes a day at most, by level (judgment call: a Tu-22M3 is lost outright and comes back one per 48 h, `refit.SLOW_REPL_MIN`, so the cap is what keeps the wing alive); L1 has no bomber wing


STAGE_GRACE_DAYS = 0              # S118 (XO 2026-11-19): red stages no carrier raid while `state.day` is at most this (the war's surprise opening: red is not already loading missiles on Day 0). A pack's `raid_grace_days` replaces it (Syria 7); the Caucasus keeps 0


def grace_days() -> int:
    from . import theatres
    v = theatres.hook("raid_grace_days")
    return STAGE_GRACE_DAYS if v is None else int(v)


RAID_BEARING_DEG = (20.0, 40.0)   # the bearing from the carrier a raid arrives on, drawn between these (the old range). S90 J8: a pack's `raid_bearing_deg` [lo, hi] replaces it (Syria: out of the open sea south-west of the task force)


def raid_bearing_range() -> tuple:
    """(lo, hi) degrees of the carrier raid's bearing: the active pack's `raid_bearing_deg` (S90 J8), else RAID_BEARING_DEG (the Caucasus)."""
    from . import theatres
    v = theatres.hook("raid_bearing_deg")
    return RAID_BEARING_DEG if v is None else (float(v[0]), float(v[1]))


def raid_bearing(state, rnd) -> float:
    """The bearing the carrier raid arrives on, drawn with `rnd`: the pack's `raid_from_base` J (S90, XO 2026-11-19: "make them come from a vector over Damascus"): the straight line from the carrier through the bomber
    wing's field, plus or minus J degrees; else a draw inside `raid_bearing_range()` (the Caucasus: 20 to 40, the same one `rnd.uniform` call as before)."""
    from . import theatres
    from .routes import bearing
    j = theatres.hook("raid_from_base")
    cv, bw = _carrier(state), _bomber_wing(state)
    if j and cv is not None and bw is not None:
        ba = state.assets[bw.base_asset_id]
        return round((bearing(cv.x, cv.y, ba.x, ba.y) + rnd.uniform(-float(j), float(j))) % 360.0, 1)
    return round(rnd.uniform(*raid_bearing_range()), 1)


def escorts_for(n: int) -> int:
    """Escorts that go with `n` bombers: one per two, rounded up."""
    return int(math.ceil(n * ESCORT_PER_BOMBER))


def land_tu(d) -> int:
    """B1: Tu-22M3 in one land strike at this level: the active pack's `land_tu` {level: n} (Syria L3 4: a 20-jet wing fields a 16-jet carrier raid and still a 4-ship strike; XO 2026-11-21), else `LAND_TU` (the Caucasus 2)."""
    from . import theatres
    v = (theatres.hook("land_tu") or {}).get(str(int(getattr(d, "level", 3))))
    return LAND_TU if v is None else int(v)


def land_escorts(d) -> int:
    """B1: the land strike's escorts: `LAND_ESCORTS` (2) as before, or one per two Tu-22M3 rounded up (`escorts_for`) when the strike is bigger (the 2-ship keeps 2 + 2: one escort per two would be 1). Judgment call (the 1 : 2 raid ratio, XO 2026-11-03)."""
    return max(LAND_ESCORTS, escorts_for(land_tu(d)))


def bomber_base_ids(th=None) -> list:
    """B1: the field ids of the bomber wing, in the order the wings are drawn on (the first is the lead): the pack's `bomber_bases` list, else its one `bomber_base` (the Caucasus: Mozdok)."""
    from . import theatres
    th = th if th is not None else theatres.active()
    ids = th.get("bomber_bases") or ([th["bomber_base"]] if th.get("bomber_base") else [])
    return list(ids)


def max_raid(d) -> int:
    from . import theatres
    lv = int(getattr(d, "level", 3))
    ov = (theatres.hook("max_raid") or {}).get(str(lv))                  # S90: a pack's `max_raid` {level: n} (Syria L3 12 of a wing of 16: the 16-jet wing could never field the Caucasus's 16 after the day's land strikes)
    if ov is not None:
        return int(ov)
    return MAX_RAID.get(lv, MAX_RAID[3] if lv >= 3 else 4)


def escorts_held(state) -> bool:
    """v0.41.355 (Phase 10a): is the Mozdok escort squadron (role "escort") held for the carrier raid? True while a raid is staged or launching (`bomber_stage` launches today or later); the other days the
    squadron flies red's normal jobs (reactions, reinforcements, land-raid escorts). THE one place that rule lives: `EnemyAirWing.general_types_up` and `raids.plan_raid` read it."""
    stage = (state.raids or {}).get("bomber_stage") or {}
    return QUIET_DAYS > 0 and stage.get("launch", -1) >= state.day


def land_cap(d) -> int:
    """Land strikes a day this level may fly (0 when the wing never raids)."""
    return 0 if getattr(d, "bomber_policy", "none") == "none" else LAND_STRIKES_PER_DAY.get(int(getattr(d, "level", 3)), 0)


def land_done(state, turn: int | None = None) -> int:
    """Land strikes booked today in other turns than `turn` (`state.raids["tu_land"]`: turn -> count, rebuilt each day; a replan of one turn replaces its own entry)."""
    return sum(int(v) for k, v in ((state.raids or {}).get("tu_land") or {}).items() if turn is None or str(k) != str(turn))


def carrier_claim(state, d, turn: int) -> tuple:
    """(Tu-22M3, escorts) the carrier raid still needs from the wing: the raid launches today in this turn or a later one (`raids["bomber_turn"]`). The land strikes leave these alone, so a staged raid
    keeps the bombers it was staged with; (0, 0) when no raid is due."""
    bt = (state.raids or {}).get("bomber_turn")
    if bt is None or bt < turn:
        return 0, 0
    dec = decide(state, d)
    return (int(dec["n"]), int(dec["escorts"])) if dec["mode"] != "hold" else (0, 0)


def bomber_wings(state) -> list:
    """B1: every Tu-22M3 wing whose field is up (not destroyed, runway not cut), in the pack's `bomber_bases` order (`bomber_base_ids`): the lead first. One entry in the Caucasus. A closed field is skipped."""
    order = {a: i for i, a in enumerate(bomber_base_ids())}
    ws = [w for w in state.enemy_air if "Tu_22M3" in w.types and not state.assets[w.base_asset_id].destroyed and not runways.is_closed(state, w.base_asset_id)]
    # The pack's bomber_bases order; a field not in it goes last.
    def field_order(wing):
        return order.get(wing.base_asset_id, len(order))

    return sorted(ws, key=field_order)


def _bomber_wing(state):
    """The LEAD bomber wing (the first field that is up), else None: the bearing and the facing patrol area are taken from it (B1: `bomber_wings` has them all)."""
    ws = bomber_wings(state)
    return ws[0] if ws else None


def _is_in(w, ws) -> bool:
    return w is not None and any(w is x for x in ws)


def _fill(parts, n: int) -> list:
    """[(wing, jets free)] -> [(wing, jets)]: `n` jets taken in order, each wing as many as it has (the S46 pool: the lead gives what it has, the next the rest); a wing that gives none is left out."""
    out = []
    for w, free in parts:
        k = min(int(n), max(0, int(free)))
        if k > 0:
            out.append((w, k))
            n -= k
        if n <= 0:
            break
    return out


def names_of(state, ws) -> str:
    """B1: the field names of these wings for a text: "Mozdok", "Damascus and Bassel Al-Assad"."""
    ns = [state.assets[w.base_asset_id].name for w in ws]
    return " and ".join(ns) if len(ns) < 3 else ", ".join(ns[:-1]) + " and " + ns[-1]


def _carrier(state):
    from . import fleet
    return fleet.carrier(state)                                    # v0.41.257: None while the carrier is sunk: no raid on a ship that is not there


def escort_options(state, bw, cv):
    """[(jets that can reach the carrier, wing, type)] best first: serviceable jets of one fighter type whose radius (x 0.85) reaches the carrier.
    v0.41.106: Mozdok's own escort squadron (role "escort", the bomber wing's fighters) is counted and goes FIRST when it can cover a minimum raid;
    the other fields are the fallback and the top-up. B1: `bw` is a bomber wing or a list of them (every bomber field's own escort squadron goes first, in the list's order)."""
    bws = list(bw) if isinstance(bw, (list, tuple)) else [bw]
    out = []
    for w in state.enemy_air:
        a = state.assets[w.base_asset_id]
        if a.destroyed:
            continue
        d_nm = math.hypot(a.x - cv.x, a.y - cv.y) / NM
        sq = [q for q in w.sqns if q.role == "escort"] if _is_in(w, bws) else w.sqns
        for t in dict.fromkeys(q.aircraft for q in sq):
            if t in ENEMY_FIGHTERS and ENEMY_RADIUS_NM.get(t, 0) * 0.85 >= d_nm:
                out.append((sum(q.available for q in sq if q.aircraft == t), w, t))
    own = [r for r in out if _is_in(r[1], bws) and r[0] >= escorts_for(MIN_RAID)]
    def bomber_field_index(row):
        return next((i for i, b in enumerate(bws) if b is row[1]), 0)

    def most_escorts_then_field(row):
        return (-row[0], row[1].base_asset_id, row[2])

    own.sort(key=bomber_field_index)                 # B1: the lead field's escorts first (one field: the order it had)
    rest = sorted((r for r in out if r not in own), key=most_escorts_then_field)
    return own + rest


def mozdok_pressure(state, bw) -> float:
    """0..1: how hard the bomber base itself has been hit (its field, its SAM cluster and early-warning radar)."""
    a = state.assets[bw.base_asset_id]
    key = a.id.split("_", 1)[1] if "_" in a.id else a.id
    cl = [x.health for x in state.assets.values() if x.kind.value in ("SAM", "EWR") and len(x.id.split("_")) > 1 and x.id.split("_")[1] == key]
    cluster = sum(cl) / len(cl) if cl else 1.0
    return max(0.0, min(1.0, (1.0 - min(a.health, cluster)) / 0.5))


def desperation(state, bw) -> float:
    """`bw`: the bomber wing, or a list of them (B1: the base under attack is the hardest-hit of the fields that are up: judgment call)."""
    from .war import totals
    t = totals(state)
    ws = list(bw) if isinstance(bw, (list, tuple)) else [bw]
    losing = LOSING_HARD if (t["enemy_air"] < 0.45 or t["c2"] < 0.5) else LOSING_SOFT if (t["enemy_air"] < 0.60 or t["c2"] < 0.65) else 0.0
    return losing + MOZDOK_WEIGHT * max(mozdok_pressure(state, w) for w in ws) + (FRONT_WEIGHT if t["iads"] <= FRONT_IADS_AT else 0.0)


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
    return s / (s + 2.5 + 2.0 * d.iads + 0.4 * escorts_for(n))


def decide(state, d) -> dict:
    """Today's call on the carrier raid: {"mode": "hold" | "safe" | "desperate", "n": bombers, "escorts", "wing", "type", "why"}. Pure: the same state gives
    the same answer, so the planner and the raid plan agree. v0.41.109: a raid is STAGED the day before (QUIET_DAYS): the day red decides to go it only
    holds ("quiet": True, "stage": {...}; the planner records it with `note_stage`), and the raid launches on the staged day."""
    # The "no raid today" answer, with the reason.
    def hold(why):
        return {"mode": "hold", "n": 0, "escorts": 0, "wing": "", "type": "", "why": why}

    bws, cv = bomber_wings(state), _carrier(state)                # B1: every bomber field that is up; a cut or destroyed one is skipped
    bw = bws[0] if bws else None
    if getattr(d, "bomber_policy", "none") == "none" or bw is None or cv is None:
        return hold("no bomber wing or no carrier")
    tu_by = [(w, w.available_of({"Tu_22M3"})) for w in bws]       # the wings also hold the escort squadrons (v0.41.106)
    avail = sum(a for _w, a in tu_by)
    opts = escort_options(state, bws, cv)
    jets, ew, et = opts[0] if opts else (0, None, "")
    esc_by = [(w, j) for j, w, t_ in opts if _is_in(w, bws) and t_ == et] if _is_in(ew, bws) else []        # B1: the bomber fields' own escort squadrons of that type fly together
    if len(esc_by) > 1:
        jets = sum(j for _w, j in esc_by)
    full = max_raid(d)
    n_max = min(avail, int(jets / ESCORT_PER_BOMBER), full)
    n_max -= n_max % 2
    left_ = max(0, land_cap(d) - land_done(state))                # v0.41.355 (Phase 10a, cadence (c)): the land strikes of today are crewed FIRST; a "safe" raid needs a FULL raid of Tu-22M3 and escorts still left after them (a "desperate" one takes everything)
    n_safe = min(avail - land_tu(d) * left_, int((jets - (land_escorts(d) * left_ if _is_in(ew, bws) else 0)) / ESCORT_PER_BOMBER), full)
    n_safe -= n_safe % 2
    def go(mode, n, desp):
        out = {"mode": mode, "n": n, "escorts": escorts_for(n), "wing": ew.base_asset_id, "type": et, "tu_wing": bw.base_asset_id,
               "why": f"{mode}: {n} bombers, {escorts_for(n)} escorts (desperation {desp:.2f})"}
        tu_ = _fill(tu_by, n)                                    # B1: the bombers come from the fields in order; `pool` (the raid plan's S46 key) names the partners only when there are some
        if tu_:
            out["tu_wing"] = tu_[0][0].base_asset_id
        if len(tu_) > 1:
            out["pool"] = [{"wing": w.base_asset_id, "raider": "Tu_22M3", "n": k} for w, k in tu_[1:]]
        es_ = _fill(esc_by, escorts_for(n)) if len(esc_by) > 1 else []
        if len(es_) > 1:
            out["wing"] = es_[0][0].base_asset_id
            out["esc_pool"] = [{"wing": w.base_asset_id, "type": et, "n": k} for w, k in es_[1:]]
        return out
    stage = (state.raids or {}).get("bomber_stage") or {}
    if QUIET_DAYS > 0 and stage.get("launch") == state.day:      # the staged day: the raid goes if it still has its escorts
        n = min(int(stage.get("n", 0)), n_max)
        n -= n % 2
        if n < MIN_RAID:
            return hold(f"the staged raid is off: only {avail} bombers and {jets} escorts left")
        return go(stage.get("mode", "safe"), n, 0.0)
    if QUIET_DAYS > 0 and stage.get("launch", -1) > state.day:
        return {**hold("quiet day before the raid"), "quiet": True}
    if state.day <= grace_days():                                # S118: the surprise opening: nothing is staged yet (a stage that already exists, an old save, was handled above)
        return hold("surprise opening: red is not ready")
    if n_max < MIN_RAID:
        return hold(f"only {avail} bombers and {jets} escorts: not enough for a {MIN_RAID}-ship raid with {escorts_for(MIN_RAID)} escorts")
    days = [x for x in ((state.raids or {}).get("bomber_days") or [])]
    cd_safe = max([x for x in days if x != state.day] or [-99])
    desp = desperation(state, bws)
    mode, n = "hold", 0
    if desp >= DESPERATE_AT:
        if state.day - cd_safe >= COOLDOWN_DESPERATE or state.day in days:
            mode, n = "desperate", n_max
    elif getattr(d, "bomber_safe_p", 0.0) > 0 and n_safe >= full:                   # v0.41.249: a safe raid is the full raid or nothing; v0.41.355 (Phase 10a): after the day's land strikes are crewed
        if state.day - cd_safe >= COOLDOWN_SAFE or state.day in days:
            p = estimated_stop(state, d, full, cv)
            if p <= d.bomber_safe_p:
                mode, n = "safe", full
    if mode == "hold":
        return hold(f"holding the wing (desperation {desp:.2f})")
    if QUIET_DAYS > 0 and state.day not in days:                 # decided today: red goes quiet, the raid launches QUIET_DAYS from now
        return {**hold(f"quiet day: the raid ({mode}, {n} bombers) is staged"), "quiet": True, "stage": {"launch": state.day + QUIET_DAYS, "mode": mode, "n": n}}
    return go(mode, n, desp)


def stage_extras(state, launch: int) -> dict:
    """v0.41.356 (Phase 10b part 1): what is fixed the day a raid is staged, so the turn BEFORE the raid can plan its SEAD / Standoff DEAD prep: the bearing the raid arrives on ("brg", 20 to 40 degrees, the old
    range; the pack's `raid_bearing_deg` where it has one, S90 J8) and the turn it launches in ("turn", seeded, among the launch day's planned turns that have a planned turn right before them on the same day; absent when none has). Seeded by campaign and launch day only."""
    rnd = random.Random(f"{state.campaign_id}:{launch}:stage")
    out = {"brg": raid_bearing(state, rnd)}
    # A turn the raid may use: any turn with night ops on, else a day turn.
    def ok(turn):
        return bool(getattr(state, "night_ops", False)) or not clock.is_night_turn(turn)

    cands = [t for t in range(clock.first_turn(launch) + 1, clock.first_turn(launch + 1)) if ok(t) and ok(t - 1)]
    if cands:
        out["turn"] = rnd.choice(cands)
    return out


def note_stage(state, dec) -> None:
    """The planner records a staged raid once (a replan the same day finds it and keeps it). v0.41.356 (Phase 10b part 1): with its bearing and launch turn (`stage_extras`)."""
    if not dec.get("stage"):
        return
    if state.raids is None:
        state.raids = {}
    cur = state.raids.get("bomber_stage") or {}
    if cur.get("launch", -1) < state.day:
        state.raids["bomber_stage"] = {**dec["stage"], **stage_extras(state, int(dec["stage"]["launch"]))}


def intel(state) -> dict | None:
    """S115 (XO 2026-11-20): the intelligence pickup of a staged carrier raid, from the day red stages it until the day it launches: {"head", "text", "sub", "pills", "log"} for the banner and the war log, else None.
    The fiction: Tu-22M3s loaded with Kh-22 missiles on a ramp the coalition can see a day out; the fleet sails out of their reach (`carrier_pos.evade`) until it is over."""
    off = (state.raids or {}).get("bomber_off") or {}
    if QUIET_DAYS > 0 and int(off.get("day", -1)) == state.day:                       # S116: the staged raid was called off today (its field is cut or destroyed)
        text = f"{off.get('where', 'The bomber base')} {off.get('why', 'is out of action')}: the Tu-22M3 raid on the carrier is called off."
        sub = "The fleet is returning to its station."
        return {"head": "INTELLIGENCE \u00b7 CARRIER RAID CALLED OFF", "text": text, "sub": sub, "pills": ["Raid called off", "Carrier returning"], "log": f"INTELLIGENCE: {text} {sub}"}
    stage = (state.raids or {}).get("bomber_stage") or {}
    if QUIET_DAYS <= 0 or int(stage.get("launch", -1)) < state.day or _carrier(state) is None:
        return None
    bws = bomber_wings(state)
    if not bws:                                                                       # S116: cut or destroyed after it was staged: called off now, the day's start cancels the stage (B1: every bomber field)
        wh, why = _bomber_field(state)
        return {"head": "INTELLIGENCE \u00b7 CARRIER RAID CALLED OFF", "text": f"{wh} {why}: the Tu-22M3 raid on the carrier is called off.", "sub": "The fleet will return to its station.",
                "pills": ["Raid called off", "Carrier returning"], "log": f"INTELLIGENCE: {wh} {why}: the Tu-22M3 raid on the carrier is called off."}
    where = names_of(state, bws)
    quiet = int(stage.get("launch", -1)) > state.day
    head = "INTELLIGENCE \u00b7 CARRIER RAID EXPECTED"
    text = f"Tu-22M3s are loading Kh-22 missiles at {where}. The raid on the carrier is expected " + ("within a day." if quiet else "today.")
    sub = ("Fighters from other fields cover the base while its own escorts are held for the raid. " if quiet else "") + "The fleet is sailing out of range, until the raid is over."
    return {"head": head, "text": text, "sub": sub, "pills": ["Carrier sailing", "Bomber base guarded" if quiet else "Raid expected today"], "log": f"INTELLIGENCE: {text} {sub}"}


def _bomber_field(state) -> tuple:
    """(name, why) of the Tu-22M3 wing's field when it cannot fly: "is destroyed" or "has its runway cut"; ("The bomber base", "is out of action") when there is no such wing. B1: with several bomber fields the names are
    joined ("Damascus and Bassel Al-Assad") and the verb follows them ("are destroyed", "have their runways cut", else "are out of action")."""
    ws = [w for w in state.enemy_air if "Tu_22M3" in w.types and w.base_asset_id in state.assets]
    if not ws:
        return "The bomber base", "is out of action"
    if len(ws) == 1:
        a = state.assets[ws[0].base_asset_id]
        return a.name, ("is destroyed" if a.destroyed else "has its runway cut")
    gone = [state.assets[w.base_asset_id].destroyed for w in ws]
    return names_of(state, ws), ("are destroyed" if all(gone) else "have their runways cut" if not any(gone) else "are out of action")


def cancel_if_cut(state) -> str | None:
    """S116 (XO 2026-11-20): a staged raid whose bomber field is cut or destroyed before it launches is called off: no Tu-22M3 could take off. The stage goes, the escorts are free again, the fleet may sail back (`cv_evade`
    cleared) and today's banner says so (`raids["bomber_off"]`). -> the war-log line, else None."""
    stage = (state.raids or {}).get("bomber_stage") or {}
    if QUIET_DAYS <= 0 or int(stage.get("launch", -1)) < state.day or bomber_wings(state):
        return None
    wh, why = _bomber_field(state)
    state.raids.pop("bomber_stage", None)
    state.raids["bomber_off"] = {"day": state.day, "where": wh, "why": why}
    if state.ground is not None:
        state.ground["cv_evade"] = -1
    return f"INTELLIGENCE: {wh} {why}: the staged Tu-22M3 raid on the carrier is called off. The fleet is returning to its station."


GUARD_PAIRS = {1: 0, 2: 1, 3: 2}      # S116: pairs a turn that cover the bomber base on the quiet day, from OTHER fields (the base's own escorts are held for the raid)
GUARD_FROM_NM = 300                   # ...from fields within this of the bomber base


def guard_base(state, level: int):
    """S116: [(bomber base asset id, pairs a turn)] while the quiet day before a staged raid is on, one entry per bomber field that can still fly (B1: Syria has two; the Caucasus one), else []. Red flies no ordinary patrol from
    those fields; fighters from nearby fields cover each by day and by night (so a night F-117A strike meets them), a tell the player can read. `redair.plan_turn` reads it."""
    if not is_quiet(state):
        return []
    n = GUARD_PAIRS.get(max(1, min(3, int(level))), 0)
    return [(w.base_asset_id, n) for w in bomber_wings(state)] if n > 0 else []


def is_quiet(state) -> bool:
    """Is today the quiet day before a staged raid? Red flies its patrols only: no strikes, raids or surprise raids."""
    return QUIET_DAYS > 0 and ((state.raids or {}).get("bomber_stage") or {}).get("launch", -1) > state.day


def status_lines(state) -> list:
    """Overview lines: the quiet day (v0.41.148: the damaged-deck line is gone, XO wants no carrier line on the Overview)."""
    out = []
    if is_quiet(state):
        bws = bomber_wings(state)
        out.append("Red air is unusually quiet today: no strikes or raids, only patrols"
                   + (f", and fighters from other fields are on station over {names_of(state, bws)}" if bws else "") + ". Something is being prepared.")
    return out                                                           # v0.41.148 (XO 2026-10-25): the carrier gets no line on the Overview


def note_launch(state) -> None:
    """Remember that the raid is on today (planner calls this once it adds the objective)."""
    days = list((state.raids or {}).get("bomber_days") or [])
    if state.day not in days:
        days.append(state.day)
    if state.raids is None:
        state.raids = {}
    state.raids["bomber_days"] = days[-8:]
