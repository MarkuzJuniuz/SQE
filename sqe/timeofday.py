"""Sun times and the daily tasking timeline, so sorties are spread through the day (not always 09:00)."""
from __future__ import annotations
import math
import random
from datetime import date

from . import clock

def _loc() -> tuple:
    """(lat, lon, utc offset) of the active theatre pack (the Caucasus pack: Georgian Black Sea coast, UTC+4)."""
    from . import theatres
    t = theatres.active()
    return t["lat"], t["lon"], t["tz"]


def sun_times(d: date) -> tuple:
    """(sunrise, sunset) in local decimal hours. NOAA approximation."""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    LAT, LON, TZ = _loc()
    lat = math.radians(LAT)
    ha = math.degrees(math.acos(max(-1, min(1, math.cos(math.radians(90.833)) / (math.cos(lat) * math.cos(decl)) - math.tan(lat) * math.tan(decl)))))
    rise = (720 - 4 * (LON + ha) - eq) / 60 + TZ
    sets = (720 - 4 * (LON - ha) - eq) / 60 + TZ
    return rise, sets


def hhmm(h: float) -> str:
    h = h % 24
    m = int(round((h - int(h)) * 60 / 5.0)) * 5
    hh = int(h) + (m // 60)
    return f"{hh % 24:02d}:{m % 60:02d}"


def is_night(d: date, hhmm_str: str) -> bool:
    rise, sets = sun_times(d)
    h = int(hhmm_str[:2]) + int(hhmm_str[3:5]) / 60
    return h < rise - 0.4 or h > sets + 0.4


def ato_times(n: int, d: date, night_ops: bool, rng: random.Random) -> list:
    """n start times spread through the campaign day, ascending."""
    rise, sets = sun_times(d)
    if night_ops:
        lo, hi = rise + 0.5, rise + 0.5 + 22.0
    else:
        lo, hi = rise + 1.0, sets - 2.0
    if n <= 1:
        return [hhmm((lo + hi) / 2)]
    step = (hi - lo) / (n - 1)
    return [hhmm(lo + i * step + rng.uniform(-0.2, 0.2) * (0 if i in (0, n - 1) else 1)) for i in range(n)]


WAVE_GAP_MIN = 60            # S110 (XO 2026-11-19): a launch wave an hour, XO's cadence (the campaign rules plan gave a 2-hour turn two waves an hour apart; S25 made the turn 4 hours and left two waves, two hours apart)
WAVE_OFFSETS_MIN = tuple(range(0, clock.TURN_MIN, WAVE_GAP_MIN))      # S110: the minutes after a turn opens at which its launch waves open: (0, 60, 120, 180). A longer or shorter turn keeps the hourly waves
NWAVES = len(WAVE_OFFSETS_MIN)                                       # waves are numbered 1 to NWAVES
WAVE_SPREAD_MIN = 25         # ...and the packages of a wave start within this many minutes of its opening, as the old 0 to 25 minute "wave" of `wave_times` (judgment call, the value of the code it replaces; it fits inside the hour)


def wave_open(w: int) -> int:
    """Minutes after the turn opens at which wave w (1 to NWAVES) opens."""
    return WAVE_OFFSETS_MIN[max(1, min(NWAVES, int(w))) - 1]


def split_waves(n: int) -> list:
    """The default wave of each of n packages: spread over the NWAVES waves as evenly as they go, the earlier waves taking the extra one when it is uneven (5 packages: 2, 1, 1, 1)."""
    base, extra = divmod(n, NWAVES)
    out = []
    for w in range(1, NWAVES + 1):
        out += [w] * (base + (1 if w <= extra else 0))
    return out


def turn_times(n: int, t0: int, rng: random.Random, waves: list | None = None) -> list:
    """Start times of the n packages of ONE turn (campaign rules plan Phase 4; it replaces the day-long `wave_times`). `t0` = the turn's first minute of the day (minutes since 00:00).
    `waves[i]` is the wave of package i (1 to NWAVES; default `split_waves(n)`): a wave starts its packages `WAVE_OFFSETS_MIN[w - 1]` minutes after the turn opens plus 0 to WAVE_SPREAD_MIN more.
    Inside a wave the packages take the times in the order they come, ascending, so the caller can give packages of one area consecutive times (they fold into one mission).
    -> [(minute of the day, wave)] in the order of the packages, minutes rounded to 5."""
    waves = list(waves) if waves is not None else split_waves(n)
    out = [None] * n
    for w, base in enumerate(WAVE_OFFSETS_MIN, 1):
        idx = [i for i in range(n) if waves[i] == w]
        offs = sorted(int(round(rng.uniform(0, WAVE_SPREAD_MIN) / 5.0)) * 5 for _ in idx)
        if offs:
            offs[0] = 0                                       # the wave opens with its first package
        for i, o in zip(idx, offs):
            out[i] = (int(t0) + base + o, w)
    return out
