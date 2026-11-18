"""Words instead of figures (S80, XO 2026-11-13 / 2026-11-18): nobody should have an accurate percentage for how much was destroyed, how strong a site is, or the odds of a job.
Everything the player READS (war log, debrief, briefing, Overview, tables) says these words; the numbers stay in the data, the war maths, dcs.log and the state file. Pure functions, no state.

Bands (judgment calls, the thresholds are the only numbers here):
  strength (a site's health 0..1):  intact >= 0.85, reduced >= 0.50, heavily damaged > 0, destroyed 0     (0.85 is the old "show the health" cut-off of the objective texts)
  BDA (the damage a job did, 0..1): achieved >= 0.60, partly achieved >= 0.25, not achieved below        (the same cuts `narrative.debrief_story` uses to score a mission)
  chance (a probability 0..1):      good >= 0.65, fair >= 0.40, poor below
  cover (the share of a day 0..1):  continuous >= 0.90, most of the day >= 0.60, part of the day >= 0.25, brief > 0, none
  edge (Tactical Edge 0..0.40):     none <= 0, slight < 0.10, useful < 0.25, strong below the cap, at the cap
A supply level keeps `posture.supply_word` (good / adequate / strained / critical)."""
from __future__ import annotations

STRENGTH = ((0.85, "intact"), (0.50, "reduced"), (1e-9, "heavily damaged"), (-1.0, "destroyed"))
CHANCE = ((0.65, "good"), (0.40, "fair"), (-1.0, "poor"))
COVER = ((0.90, "continuous"), (0.60, "most of the day"), (0.25, "part of the day"), (1e-9, "brief"), (-1.0, "none"))


def _band(table, v: float) -> str:
    return next(w for lim, w in table if v >= lim)


def strength_word(health: float) -> str:
    """intact / reduced / heavily damaged / destroyed."""
    return _band(STRENGTH, float(health))


def chance_word(p: float) -> str:
    """good / fair / poor."""
    return _band(CHANCE, float(p))


def cover_word(frac: float) -> str:
    """continuous / most of the day / part of the day / brief / none."""
    return _band(COVER, float(frac))


def bda_outcome(damage: float) -> str:
    """The three BDA outcomes: 'achieved', 'partly achieved', 'not achieved'."""
    d = float(damage)
    return "achieved" if d >= 0.60 else "partly achieved" if d >= 0.25 else "not achieved"


def bda_text(damage: float) -> str:
    """The BDA sentence tail for a damage figure: what the player reads instead of 'N% destroyed'."""
    return {"achieved": "objective achieved, the target is destroyed or out of action",
            "partly achieved": "objective partly achieved, the target is damaged but not neutralised",
            "not achieved": "objective not achieved, no effect observed"}[bda_outcome(damage)]


def edge_word(v: float, cap: float = 0.40) -> str:
    """The Tactical Edge level (0..cap) as a word."""
    v = float(v)
    return "none" if v <= 1e-9 else "at the cap" if v >= cap - 1e-9 else "slight" if v < 0.10 else "useful" if v < 0.25 else "strong"
