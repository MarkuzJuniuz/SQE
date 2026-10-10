"""Theatre packs: everything that is specific to one DCS map lives in a JSON file, not in code.

Bundled packs are in sqe/data/theatres/<id>.json. Your own packs go in %APPDATA%\\SQE\\theatres\\<id>.json (a pack with the same id
replaces the bundled one). A pack names the DCS terrain, the airfields and who holds them, the depth tiers, the squadrons, the carrier
station, the sun position and time zone, the monthly temperatures, the terrain scan area and the scenario text. See docs/THEATRES.md.

`use(id)` makes a pack the active one; the rest of SQE reads it through `active()`. Coordinates in a pack are DCS's: x north, y east, metres.
"""
from __future__ import annotations
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "theatres"
DEFAULT = "caucasus"

REQUIRED = ("id", "name", "dcs_terrain", "lat", "lon", "tz", "temp_c", "geo", "scan", "carrier", "blue_fields", "red_fields",
            "wing_weight", "field_tier", "squadrons", "front", "tier_labels", "front_names", "front_desc", "title", "background")

_ACTIVE: dict | None = None
_CACHE: dict = {}
EXTRA_DIRS: list = []                 # extra pack folders (tests, or a portable install); searched after the bundled ones


def user_dir() -> Path | None:
    try:
        from .settings import config_dir
        return config_dir() / "theatres"
    except Exception:
        return None


def _dirs() -> list:
    out = [DATA]
    u = user_dir()
    if u is not None and u.is_dir():
        out.append(u)
    out.extend(Path(x) for x in EXTRA_DIRS if Path(x).is_dir())
    return out


def _validate(d: dict, src) -> dict:
    miss = [k for k in REQUIRED if k not in d]
    if miss:
        raise ValueError(f"theatre pack {src} is missing: {', '.join(miss)}")
    if len(d["temp_c"]) != 12:
        raise ValueError(f"theatre pack {src}: temp_c needs 12 monthly values")
    from .weather import DEFAULT_CLIMATE
    d.setdefault("climate", dict(DEFAULT_CLIMATE))
    d.setdefault("support_targets", [])
    d.setdefault("red_keep", {})
    d.setdefault("bomber_base", "")
    d["_dir"] = str(Path(src).parent)
    return d


def available() -> dict:
    """{id: name} for every readable pack (bundled, then the user's own)."""
    out = {}
    for folder in _dirs():
        for p in sorted(folder.glob("*.json")):
            if p.stem.endswith("_geo"):
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if "id" in d and "name" in d:
                    out[d["id"]] = d["name"]
            except (OSError, ValueError):
                continue
    return out


def load(tid: str) -> dict:
    tid = (tid or DEFAULT).lower()
    if tid in _CACHE:
        return _CACHE[tid]
    found = None
    for folder in _dirs():                   # a later folder (the user's) overrides the bundled pack
        p = folder / f"{tid}.json"
        if p.is_file():
            found = p
    if found is None:
        raise ValueError(f"unknown theatre {tid!r}; available: {', '.join(available()) or 'none'}")
    d = _validate(json.loads(found.read_text(encoding="utf-8")), found)
    _CACHE[tid] = d
    return d


def use(tid: str) -> dict:
    """Make `tid` the active theatre and re-point the terrain scan at it."""
    global _ACTIVE
    d = load(tid)
    changed = _ACTIVE is None or _ACTIVE["id"] != d["id"]
    _ACTIVE = d
    if changed:
        try:
            from . import relief, seacheck, terrainmask
            seacheck.reset()
            terrainmask.theatre_changed()
            relief.theatre_changed()
        except Exception:
            pass
    return d


def active() -> dict:
    return _ACTIVE if _ACTIVE is not None else use(DEFAULT)


def terrain():
    """A fresh pydcs terrain object for the active theatre."""
    from dcs import terrain as T
    name = active()["dcs_terrain"]
    cls = getattr(T, name, None)
    if cls is None:
        raise ValueError(f"this pydcs has no terrain {name!r}")
    return cls()


def geo() -> dict:
    """Coarse coastline, lakes and borders for the active theatre (map view and the fallback land test)."""
    d = active()
    p = Path(d["_dir"]) / d["geo"]
    if not p.is_file():
        p = DATA / d["geo"]
    return json.loads(p.read_text(encoding="utf-8"))
