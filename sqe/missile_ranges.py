"""S231b: each fighter type's missile launch ranges as DCS's AI flew them (server probe S231, `data/missile_ranges.json`), and the
station distance a cover flight takes from them. XO's rule (2026-11-27): an AI flight's station uses the OPTIMAL shooting range (DCS's
NEZ_RANGE launch), the player's flight the MAX firing range (a person can shoot at max range: the one intended route difference
between AI and player). A type with no figure gives None: the caller keeps its old constant."""
import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "missile_ranges.json"

# The loaded file, read once (like a static field filled on first use in Java / C#)
_cache = {}


def _table() -> dict:
    if "types" not in _cache:
        with open(DATA_FILE, encoding="utf-8") as handle:
            loaded = json.load(handle)
        _cache["types"] = loaded.get("types", {})
        _cache["heights_ft"] = loaded.get("heights_ft", {"low": 1500, "med": 20000, "high": 35000})
    return _cache


def range_nm(aircraft: str, alt_ft: float, kind: str):
    """The launch range in nm of `aircraft`'s main missile at `alt_ft`, kind "max_nm" or "optimal_nm": straight-line between the probe's three
    heights, the end figure below the lowest and above the highest. None when the type has no row or no figure of that kind."""
    table = _table()
    row = table["types"].get(aircraft)
    if row is None:
        return None
    figures = row.get(kind)
    if not figures:
        return None
    heights = table["heights_ft"]
    # the three (height, range) points, lowest first
    points = []
    for band in ("low", "med", "high"):
        value = figures.get(band)
        if value is None:
            return None
        points.append((float(heights[band]), float(value)))
    if alt_ft <= points[0][0]:
        return points[0][1]
    if alt_ft >= points[-1][0]:
        return points[-1][1]
    for index in range(len(points) - 1):
        low_ft, low_nm = points[index]
        high_ft, high_nm = points[index + 1]
        if low_ft <= alt_ft <= high_ft:
            share = (alt_ft - low_ft) / (high_ft - low_ft)
            return low_nm + (high_nm - low_nm) * share
    return points[-1][1]


def station_nm(aircraft: str, alt_ft: float, player: bool):
    """The station distance for a cover flight of `aircraft` at `alt_ft`: the max firing range for the player's own flight (a person flies it),
    the optimal shooting range for AI. None when the type has no figure (the caller's old constant stays)."""
    if player:
        return range_nm(aircraft, alt_ft, "max_nm")
    return range_nm(aircraft, alt_ft, "optimal_nm")
