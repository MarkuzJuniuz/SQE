"""The campaign clock (campaign rules plan, section 3.1; Phase 1, v0.41.334).

A turn is four hours (S25, v0.41.379; it was two). The campaign starts on Day 1 at 08:00, so Day 1 has 4 turns (08:00 to 20:00) and every later day has 6. The day rolls over at midnight
(`WarSimulator.end_day` runs when the clock crosses 24:00), so `state.day` stays stored and equal to `day_of(turn)`.

`state.turn` is the only stored clock. Since Phase 3 (v0.41.337) `Session._tick` moves it one turn at a time: a Skip or a flown sortie is one turn, and `end_day` runs when the clock crosses midnight.
Pure arithmetic, no state, no pydcs: like a static utility class in Java or C#.
"""
from __future__ import annotations

TURN_MIN = 240                       # four hours a turn (S25, XO 2026-11-11; was 120)
START_MIN = 480                      # 08:00 on Day 1 (XO 2026-11-06)
NIGHT_START_HOURS = (20, 0, 4)   # a turn that starts at one of these hours is a night turn: 20:00 to 08:00, three turns (S25; was six two-hour turns)
DAY_MIN = 1440


def minute(turn: int) -> int:
    """Absolute minutes since 00:00 of Day 1 at the start of this turn."""
    return START_MIN + TURN_MIN * int(turn)


def hour(turn: int) -> int:
    return (minute(turn) // 60) % 24


def day_of(turn: int) -> int:
    return 1 + minute(turn) // DAY_MIN


def is_night_turn(turn: int) -> bool:
    return hour(turn) in NIGHT_START_HOURS


def first_turn(day: int) -> int:
    """The first turn of a campaign day (Day 1: turn 0 at 08:00; Day 2: turn 4 at 00:00; Day 3: turn 10 ...)."""
    return 0 if day <= 1 else (DAY_MIN * (int(day) - 1) - START_MIN) // TURN_MIN


def day_start_minute(day: int) -> int:
    """Absolute minute of 00:00 on this campaign day."""
    return DAY_MIN * (int(day) - 1)
