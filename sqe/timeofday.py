"""Sun times and the daily tasking timeline, so sorties are spread through the day (not always 09:00)."""
from __future__ import annotations
import math
import random
from datetime import date

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


def wave_times(n: int, d: date, night_ops: bool, rng: random.Random, wave: int = 3) -> list:
    """n start times in 'waves' of up to `wave` packages 0-25 minutes apart, the waves spread through the day (like a real ATO).
    Returned ascending; the caller gives consecutive packages (same area) consecutive times."""
    rise, sets = sun_times(d)
    lo, hi = (rise + 0.5, rise + 0.5 + 22.0) if night_ops else (rise + 1.0, sets - 2.5)
    n_w = max(1, math.ceil(n / wave))
    centers = [(lo + hi) / 2] if n_w == 1 else [lo + i * (hi - lo) / (n_w - 1) for i in range(n_w)]
    out = []
    for w in range(n_w):
        k = min(wave, n - w * wave)
        offs = sorted(rng.uniform(0, 0.42) for _ in range(k))
        if k:
            offs[0] = 0.0
        out += [hhmm(centers[w] + o) for o in offs]
    return sorted(out)
