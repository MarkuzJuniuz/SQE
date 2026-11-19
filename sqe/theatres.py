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
            "wing_weight", "field_tier", "squadrons", "front", "tier_labels", "front_names", "front_desc", "title", "stories")

# S90 P4: the pack's `sam_tier` block names the long-range SAM systems of the theatre: {"umbrella": ["SA-5", "SA-10"], "gate": ["SA-2", "SA-3", "SA-6", "SA-5", ...]} (samtier.py holds the
# systems' reach and margins). A pack without the block gets the Caucasus tier (the SA-10 as the umbrella).

# S103a: the pack's `era` block = the year shown for the campaign (a fixed label: the month and day stay free) and the Era Equipment defaults of the campaign-create dialog. A pack without
# the block (or with part of it) gets these values, which are Caucasus 2006 (what SQE always flew).
ERA_DEFAULT = {"year": 2006, "a10_variant": "A-10C", "f14_variant": "F-14BU", "link16": True}

# S90 J5 (the theatre hooks): OPTIONAL pack keys. Each is read in ONE place and a pack without it gets today's Caucasus constant, so the Caucasus is byte-identical:
#   red_roster {level: {type: jets}}      -> redroster.allocate(roster=...)           (default redroster.ROSTERS[level])
#   level_overrides {level: {field: v}}   -> difficulty.get(level) for this theatre   (default: the level as it is)
#   front.air_fields [field key, ...]     -> war.mountain_fields()                    (default war.MOUNTAIN_FIELDS)
#   front.defeat_bases N                  -> ground.defeat_bases()                    (default ground.DEFEAT_BASES)
#   nav {airport: kneeboard line}         -> kneeboard.nav_line()                     (default kneeboard.NAV)
#   ils_runway {airport: runway number}   -> runways.ils_runways()                    (default runways.ILS_RUNWAY)
#   mag_var_deg number                    -> runways.mag_var_deg()                    (default runways.MAG_VAR_DEG)
#   extra_sams [{id, site, x/y or near+bearing+dist_m, levels, ...}] -> scenario.new_campaign (fixed extra SAM sites; default none)

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
    d.setdefault("red_fill", {})                                   # v0.41.439: {level: {red field id: jets}}, the most jets the field holds at that level (a theatre without it parks by the DCS count only)
    d.setdefault("bomber_base", "")
    d["era"] = {**ERA_DEFAULT, **(d.get("era") or {})}
    from . import samtier
    samtier.check(d.get("sam_tier"), src)
    _check_hooks(d, src)
    d["_dir"] = str(Path(src).parent)
    return d


def _check_hooks(d: dict, src) -> None:
    """S90 J5: raise a clear ValueError for a bad value in one of the optional hook keys (see the table at the top). A missing key is fine."""
    def bad(msg):
        raise ValueError(f"theatre pack {src}: {msg}")

    def levels_of(name, block):
        if not isinstance(block, dict):
            bad(f"{name} must be a {{level: ...}} object")
        for k in block:
            if str(k) not in ("1", "2", "3"):
                bad(f"{name} has the level {k!r}: levels are \"1\", \"2\" and \"3\"")
    if "red_roster" in d:
        levels_of("red_roster", d["red_roster"])
        for lv, roster in d["red_roster"].items():
            if not isinstance(roster, dict) or not roster:
                bad(f"red_roster level {lv} must be a non-empty {{aircraft type: jets}} object")
            for t, n in roster.items():
                if not isinstance(t, str) or isinstance(n, bool) or not isinstance(n, int) or n < 0:
                    bad(f"red_roster level {lv}: {t!r}: {n!r} must be an aircraft type and a whole number of jets, 0 or more")
    if "level_overrides" in d:
        levels_of("level_overrides", d["level_overrides"])
        import dataclasses
        from .difficulty import Difficulty
        fields = {f.name for f in dataclasses.fields(Difficulty)} - {"level"}
        for lv, ov in d["level_overrides"].items():
            if not isinstance(ov, dict):
                bad(f"level_overrides level {lv} must be a {{difficulty field: value}} object")
            for k in ov:
                if k not in fields:
                    bad(f"level_overrides level {lv}: {k!r} is not a Difficulty field")
    fr = d.get("front") or {}
    if "air_fields" in fr and (not isinstance(fr["air_fields"], list) or not all(isinstance(x, str) for x in fr["air_fields"])):
        bad("front.air_fields must be a list of red field keys (the part of the id after ab_)")
    if "defeat_bases" in fr and (isinstance(fr["defeat_bases"], bool) or not isinstance(fr["defeat_bases"], int) or fr["defeat_bases"] < 1):
        bad("front.defeat_bases must be a whole number, 1 or more")
    if "nav" in d and (not isinstance(d["nav"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in d["nav"].items())):
        bad("nav must be an {airport name: kneeboard line} object")
    if "ils_runway" in d and (not isinstance(d["ils_runway"], dict) or not all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 36 for k, v in d["ils_runway"].items())):
        bad("ils_runway must be an {airport name: runway number 1 to 36} object")
    if "mag_var_deg" in d and (isinstance(d["mag_var_deg"], bool) or not isinstance(d["mag_var_deg"], (int, float)) or abs(d["mag_var_deg"]) > 30):
        bad("mag_var_deg must be a number of degrees (east positive, within 30)")
    if "extra_sams" in d:
        if not isinstance(d["extra_sams"], list):
            bad("extra_sams must be a list")
        from . import scenario
        seen = set()
        for i, e in enumerate(d["extra_sams"]):
            if not isinstance(e, dict):
                bad(f"extra_sams[{i}] must be an object")
            eid = e.get("id")
            if not isinstance(eid, str) or not eid.startswith("sam_") or "_" not in eid[4:] or eid in seen:
                bad(f"extra_sams[{i}]: id must be a unique text of the form sam_<key>_<n> (e.g. sam_sa5h_0), got {eid!r}")
            seen.add(eid)
            if e.get("site") not in scenario.SAM_VALUE:
                bad(f"extra_sams[{i}]: site {e.get('site')!r} is not a SAM variant ({', '.join(scenario.SAM_VALUE)})")
            if not ("x" in e and "y" in e) and not ("near" in e and "bearing" in e and "dist_m" in e):
                bad(f"extra_sams[{i}]: give x and y (DCS metres) or near (an airport name) with bearing (degrees) and dist_m")
            for k in ("x", "y", "bearing", "dist_m", "jitter_m"):
                if k in e and (isinstance(e[k], bool) or not isinstance(e[k], (int, float))):
                    bad(f"extra_sams[{i}]: {k} must be a number")
            if not isinstance(e.get("levels"), list) or not e["levels"] or not all(v in (1, 2, 3) for v in e["levels"]):
                bad(f"extra_sams[{i}]: levels must be a list of 1, 2, 3")


def hook(key: str, default=None):
    """The active pack's optional hook key `key`, or `default` when the pack has none (S90 J5)."""
    v = active().get(key)
    return default if v is None else v


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
    from . import samtier
    samtier.configure(d.get("sam_tier"))               # S90 P4: the long-range tier of this theatre (in place: every module sees it)
    if changed:
        try:
            from . import relief, roads, seacheck, terrainmask
            seacheck.reset()
            terrainmask.theatre_changed()
            relief.theatre_changed()
            roads.theatre_changed()
        except Exception:
            pass
    return d


def era(tid: str | None = None) -> dict:
    """The `era` block of a pack (the active one when no id is given), with the missing keys filled from ERA_DEFAULT."""
    return dict(load(tid)["era"]) if tid else dict(active()["era"])


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
