"""The campaign story (Campaign Revamp, Stage C3, v0.41.150): the text of each level, read from the theatre pack (`stories`, one entry per level).
Each entry has: enemy (the short label the Overview uses), enemy_long, background (paragraphs), intent, now (a line for each posture label and each ending),
beats (lines the war log gets as the war moves: open, fall_<red base id>, retake, counter, fallen_blue, back_blue, win, lose).
A theatre pack without `stories` falls back to the plain texts in posture.py and its one `background`."""
from __future__ import annotations
from . import theatres


def get(state) -> dict:
    return (theatres.active().get("stories") or {}).get(str(int(getattr(state, "level", 2)))) or {}


def enemy(state) -> str:
    """The opponent's short label for the Overview ('Russia', 'CRA'): 'Enemy' when the theatre has no story."""
    return get(state).get("enemy") or "Enemy"


def now_line(state, label: str, default: str) -> str:
    return (get(state).get("now") or {}).get(label) or default


def beat(state, key: str, **fmt) -> list:
    """The war-log line for a story beat, as a one-item list ([] when the story has none)."""
    t = (get(state).get("beats") or {}).get(key)
    return [t.format(**fmt)] if t else []
