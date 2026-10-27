"""Air tempo (v0.41.147, XO 2026-10-27): the player's flown results nudge how well the AI flights do the same kind of job in the background.

Four job kinds (CAS, STRIKE, DEAD = SEAD / DEAD / Standoff, AIR = sweeps, patrols, intercepts). Each has a tempo, an additive change to the chance that a
background (AI) package of that kind gets the job done, and to the abstract AI close air support of the ground war. After a flown sortie the debrief rates it
the way the story does (great / good / mixed / bad) and the tempo of that kind moves a small step; it is capped at +-TEMPO_CAP and drifts back toward zero a
little every night (a squadron's edge fades if you stop flying that job). Judgment calls (no source): step sizes, the cap, the decay.
"""
from __future__ import annotations

from .models import ObjectiveType

KINDS = ("CAS", "STRIKE", "DEAD", "AIR")
TEMPO_CAP = 0.20                  # most the chance of a background job moves (+-20 percentage points)
STEP = {"great": 0.05, "good": 0.03, "mixed": 0.0, "bad": -0.04}
DECAY = 0.97                      # per night, toward zero
LABEL = {"CAS": "close air support", "STRIKE": "strike", "DEAD": "SEAD / DEAD", "AIR": "air cover and counter-air"}


def kind_of(objective_type: str) -> str:
    t = getattr(objective_type, "value", objective_type)
    return {"CAS": "CAS", "STRIKE": "STRIKE", "DEAD": "DEAD"}.get(t, "AIR")


def get(state, kind: str) -> float:
    return float((getattr(state, "tempo", None) or {}).get(kind, 0.0))


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


def record(state, objective_type, tone: str) -> list:
    """The flown sortie moves its kind's tempo. -> the debrief lines ([] when nothing moved)."""
    k = kind_of(objective_type)
    step = STEP.get(tone, 0.0)
    if not hasattr(state, "tempo") or state.tempo is None:
        state.tempo = {}
    old = get(state, k)
    new = max(-TEMPO_CAP, min(TEMPO_CAP, old + step))
    state.tempo[k] = round(new, 4)
    if abs(new - old) < 1e-9:
        return [f"Air tempo, {LABEL[k]}: unchanged at {new * 100:+.0f}%" + (" (at the cap)" if abs(new) >= TEMPO_CAP - 1e-9 and step else "")]
    return [f"Air tempo, {LABEL[k]}: {(new - old) * 100:+.0f}% (now {new * 100:+.0f}%): the squadrons' background jobs of this kind {'go' if new > old else 'fare'} {'better' if new > old else 'worse'}"]


def decay(state) -> None:
    t = getattr(state, "tempo", None)
    if not t:
        return
    for k in list(t):
        t[k] = round(t[k] * DECAY, 4)
        if abs(t[k]) < 0.005:
            t[k] = 0.0
