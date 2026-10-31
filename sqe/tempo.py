"""Air tempo (v0.41.147, XO 2026-10-27): the player's flown results nudge how well the AI flights do the same kind of job in the background.

Four job kinds (CAS, STRIKE, DEAD = SEAD / DEAD / Standoff, AIR = sweeps, patrols, intercepts). Each has a tempo, an additive change to the chance that a
background (AI) package of that kind gets the job done, and to the abstract AI close air support of the ground war. After a flown sortie the debrief rates it
the way the story does (great / good / mixed / bad) and the tempo of that kind moves a small step; it is kept between TEMPO_MIN and TEMPO_CAP (0 to +40 points) and drifts back toward zero a
little every night (a squadron's edge fades if you stop flying that job). Judgment calls (no source): step sizes, the cap, the decay.
"""
from __future__ import annotations

from .models import ObjectiveType

KINDS = ("CAS", "STRIKE", "DEAD", "AIR")
TEMPO_CAP = 0.40                  # v0.41.166 (XO 2026-10-27): the most the chance of a background job moves up (+40 percentage points; was +-20)
TEMPO_MIN = 0.0                   # ...and it never goes below zero: a bad sortie only takes back what flying built (an AI-flown sortie often grades bad, which made the numbers worse)
STEP = {"great": 0.05, "good": 0.03, "mixed": 0.0, "bad": 0.0}      # v0.41.171 (XO 2026-10-28): a bad sortie takes nothing back; only the nightly decay lowers it (lessons learned are not unlearned)
CREDIT_PART, CREDIT_FULL, CREDIT_MAX = 0.02, 0.04, 0.06      # v0.41.171: credit for what the sortie did to each kind (judgment calls): a partial result, a full one, and the most one kind earns in one sortie
DECAY = 0.97                      # per night, toward zero
LABEL = {"CAS": "close air support", "STRIKE": "strike", "DEAD": "SEAD / DEAD", "AIR": "air cover and counter-air"}


def kind_of(objective_type: str) -> str:
    t = getattr(objective_type, "value", objective_type)
    return {"CAS": "CAS", "STRIKE": "STRIKE", "DEAD": "DEAD"}.get(t, "AIR")


def influence_on(state) -> bool:
    """v0.41.160: the Pilot Influence setting (copied into the campaign by the engine). Off: your flying changes nothing in the war."""
    return bool((getattr(state, "ground", None) or {}).get("pilot_influence", True))


def decay_on(state) -> bool:
    """v0.41.208 (XO): the nightly fade of the edge is a per-campaign switch (Enable Tactical Edge Decay), default OFF."""
    return bool((getattr(state, "ground", None) or {}).get("tempo_decay", False))


def get(state, kind: str) -> float:
    if not influence_on(state):
        return 0.0
    return max(TEMPO_MIN, min(TEMPO_CAP, float((getattr(state, "tempo", None) or {}).get(kind, 0.0))))      # older saves may hold a negative value: read as zero


def tone_of(outcome: dict) -> str:
    """The debrief's own grading (narrative.debrief_story): great / good / mixed / bad."""
    lost = outcome.get("blue_air_lost", 0)
    dmg = outcome.get("target_damage", 0.0)
    if outcome.get("objective_type") in (ObjectiveType.BARCAP.value, ObjectiveType.FLEET_DEFENSE.value):
        score = 2 if outcome.get("red_air_lost", 0) >= 1 else 1
    else:
        score = 2 if dmg >= 0.6 else 1 if dmg >= 0.25 else 0
    score -= 1 if lost >= 2 else 0
    return "great" if score >= 2 and lost == 0 else "good" if score >= 1 and lost <= 1 else "mixed" if score >= 1 or lost == 0 else "bad"


def credits(outcome: dict) -> dict:
    """v0.41.171 (XO 2026-10-28): what the whole mission did, by kind, whatever the package's own objective was. -> {kind: step}.
    DEAD: each red SAM site blinded or damaged by a quarter or more (+2), or destroyed (+4). AIR: one red aircraft shot down (+2), two or more (+4).
    STRIKE: another (non-SAM) red asset hit by a quarter or more (+2). The kind keeps the biggest single credit, never more than CREDIT_MAX."""
    c = {k: 0.0 for k in KINDS}
    for a in outcome.get("red_assets") or []:
        before, after = float(a.get("before") or 0.0), float(a.get("after") or 0.0)
        frac = (before - after) / before if before > 0 else 0.0
        if a.get("kind") == "SAM":
            v = CREDIT_FULL if a.get("destroyed") else CREDIT_PART if (a.get("suppressed") or frac >= 0.25) else 0.0
            c["DEAD"] = max(c["DEAD"], v)
        elif not a.get("primary") and frac >= 0.25:
            c["STRIKE"] = max(c["STRIKE"], CREDIT_PART)
    n = int(outcome.get("red_air_lost", 0) or 0)
    c["AIR"] = CREDIT_FULL if n >= 2 else CREDIT_PART if n == 1 else 0.0
    return {k: min(CREDIT_MAX, v) for k, v in c.items()}


def record(state, objective_type, tone: str, extra: dict | None = None) -> list:
    """The flown sortie moves the tempo of its own kind by its grade, and of every kind by what the mission did (`credits`; a kind takes the larger of
    the two, not the sum). -> the debrief lines ([] when nothing moved)."""
    pk = kind_of(objective_type)
    if getattr(state, "ground", None):
        state.ground["flown_day"] = state.day                       # v0.41.155: the squadron flew today: red's idle surge starts over (ground.surge)
    if not influence_on(state):
        return []                                                    # Pilot Influence off: nothing moves
    if not hasattr(state, "tempo") or state.tempo is None:
        state.tempo = {}
    out = []
    for k in KINDS:
        step = max(STEP.get(tone, 0.0) if k == pk else 0.0, (extra or {}).get(k, 0.0))
        if k != pk and step <= 0:
            continue
        old = get(state, k)
        new = max(TEMPO_MIN, min(TEMPO_CAP, old + step))
        state.tempo[k] = round(new, 4)
        if abs(new - old) < 1e-9:
            out.append(f"Tactical Edge, {LABEL[k]}: unchanged at {new * 100:+.0f}%" + (" (at the cap)" if abs(new) >= TEMPO_CAP - 1e-9 and step else ""))
        else:
            out.append(f"Tactical Edge, {LABEL[k]}: {(new - old) * 100:+.0f}% (now {new * 100:+.0f}%): the squadrons' background jobs of this kind go better"
                       + ("" if k == pk else " (credit for what the mission did)"))
    return out


def decay(state) -> None:
    t = getattr(state, "tempo", None)
    if not t:
        return
    for k in list(t):
        t[k] = round(t[k] * DECAY, 4)
        if abs(t[k]) < 0.005:
            t[k] = 0.0
