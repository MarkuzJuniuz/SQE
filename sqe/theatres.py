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
#   win_supply {level: {below, days}}     -> ground.update_supply_win / war.update_status (default none: red's Force Index at or below `below` on `days` consecutive days wins the level)
#   works {label, damage, levels {level: {push, rebuild_days, supply_total?, teams?, hold_days?}}, sites [{id wks_.., name, x, y}]} -> works.build / war / ground.push_factor (S111: Lutorin's works, special blue targets; the win when all are destroyed. Default none: the Caucasus)
#   start_hour 0|4|8|12|16|20             -> CampaignState.start_hour, clock.use()    (default 8: Day 1 / turn 0 starts at 08:00; Syria 0)
#   opening_strike {levels, kill, text?, fill?}  -> scenario._opening_strike          (default none: every red site of the variant `kill` starts the campaign destroyed, rebuilt by the normal rule; `fill`: what the F-117A pairs left over hit, S104d)
#   raid_attack_types [type, ...]         -> raids.attack_types()                     (default ("Su_25",): leads raids on troops, garrisons, supply sites)
#   raid_bomber_types [type, ...]         -> raids.bomber_types()                     (default loadouts.BOMBER_TYPES = ("Su_24M",): field raids, SEAD and Kh-59M raids only)
#   extra_sams [{id, site, x/y or near+bearing+dist_m, levels, ...}] -> scenario.new_campaign (fixed extra SAM sites; default none)
#   raid_bearing_deg [lo, hi]             -> bombers.raid_bearing_range()             (default (20, 40): the bearing from the carrier the Tu-22M3 raid arrives on; Syria 200 to 220, out of the open sea)
#   max_raid {level: n}                   -> bombers.max_raid()                       (default bombers.MAX_RAID {2: 8, 3: 16}: the full Tu-22M3 carrier raid; Syria has none since B1: its 20-jet wing fields the 16)
#   blue_fields[].patriot bool             -> sams.site_keys()                          (S143: a divert field still gets its Patriot; Syria: Hatay)
#   bomber_bases [red field id, ...]      -> scenario.new_campaign / bombers.bomber_base_ids()   (B1: the Tu-22M3 wing's fields, the first is the lead: the level's `bomber_wing` and `bomber_escort_wing` are split between them; default [bomber_base] (the Caucasus: Mozdok). Syria: Damascus and Bassel Al-Assad; each field's Tu-22M3 share is capped at its DCS stand count, the overflow goes to the next field)
#   land_tu {level: n}                    -> bombers.land_tu()                        (B1: Tu-22M3 in one land strike; default bombers.LAND_TU 2; Syria L3 4)
#   raid_from_base J                      -> bombers.raid_bearing()                   (default none: the raid's bearing is drawn in raid_bearing_deg; J degrees = it comes along the line from the carrier through the bomber field, plus or minus J: Syria 4)
#   raid_grace_days N                     -> bombers.grace_days()                     (default 0: red stages no carrier raid while the day is at most N, the surprise opening; Syria 7)
#   map_box {x0, x1, y0, y1}              -> raid_spawns._map_edges()                 (default the terrain's own bounds: the edge of the map the raid spawns on; Syria: pydcs's bounds are wrong)

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
    d.setdefault("painted_airports", {})                           # v0.41.539: {"blue": [airport names], "red": [...]}, mission-only paint for fields that are not SQE bases (no neutral field for a jet to land on)
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
    for k in ("raid_attack_types", "raid_bomber_types"):
        if k in d:
            if not isinstance(d[k], list) or not d[k] or not all(isinstance(t, str) for t in d[k]):
                bad(f"{k} must be a non-empty list of red aircraft types (pydcs class names)")
            from dcs import planes
            for t in d[k]:
                if not hasattr(planes, t):
                    bad(f"{k}: {t!r} is not a pydcs aircraft")
    if set(d.get("raid_attack_types") or ()) & set(d.get("raid_bomber_types") or ()):
        bad("raid_attack_types and raid_bomber_types must not share a type (the bomber list alone flies the SEAD and Kh-59M raids)")
    if "win_supply" in d:
        levels_of("win_supply", d["win_supply"])
        for lv, r in d["win_supply"].items():
            if (not isinstance(r, dict) or set(r) != {"below", "days"} or isinstance(r["below"], bool) or not isinstance(r["below"], (int, float)) or not 0.0 < r["below"] <= 1.0
                    or isinstance(r["days"], bool) or not isinstance(r["days"], int) or r["days"] < 1):
                bad(f"win_supply level {lv} must be {{\"below\": a number above 0 and up to 1, \"days\": a whole number of days, 1 or more}}")
    if "works" in d:                                                  # S111: Lutorin's works (works.py)
        w = d["works"]
        num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
        if not isinstance(w, dict) or set(w) - {"label", "damage", "levels", "sites"}:
            bad("works takes only label, damage, levels and sites")
        if "label" in w and not isinstance(w["label"], str):
            bad("works.label must be a string")
        if "damage" in w and (not num(w["damage"]) or not 0.0 < w["damage"] <= 1.0):
            bad("works.damage must be a number above 0 and up to 1 (the share of a depot's strike damage a works takes)")
        levels_of("works.levels", w.get("levels"))
        for lv, r in w["levels"].items():
            if (not isinstance(r, dict) or not {"push", "rebuild_days"} <= set(r) or set(r) - {"push", "rebuild_days", "damage", "supply_total", "teams", "hold_days"} or not num(r["push"]) or r["push"] < 0
                    or not num(r["rebuild_days"]) or r["rebuild_days"] <= 0 or ("damage" in r and (not num(r["damage"]) or not 0.0 < r["damage"] <= 1.0)) or ("supply_total" in r and (not isinstance(r["supply_total"], int) or isinstance(r["supply_total"], bool) or r["supply_total"] < 1)) or ("teams" in r and (not isinstance(r["teams"], int) or isinstance(r["teams"], bool) or r["teams"] < 1)) or ("hold_days" in r and (not isinstance(r["hold_days"], int) or isinstance(r["hold_days"], bool) or r["hold_days"] < 0))):
                bad(f"works.levels {lv} must be {{\"push\": a number, 0 or more, \"rebuild_days\": a number above 0, \"damage\": optional, a number above 0 and up to 1, \"supply_total\": optional, a whole number, red's supply sites counted for the Force Index with the works, \"teams\": optional, a whole number, 1 or more: how many destroyed works are rebuilt at once, default 1, \"hold_days\": optional, a whole number, 0 or more: days every works must STAY destroyed before the win, default 0}}")
            if "works_win" not in (((d.get("stories") or {}).get(lv) or {}).get("beats") or {}):
                bad(f"works.levels {lv}: the level's story needs the beat works_win (the text of the win)")
        sites = w.get("sites")
        if not isinstance(sites, list) or not sites:
            bad("works.sites must be a non-empty list of {id, name, x, y, value?, tier?}")
        for s_ in sites:
            if (not isinstance(s_, dict) or set(s_) - {"id", "name", "x", "y", "value", "tier"} or not {"id", "name", "x", "y"} <= set(s_)
                    or not isinstance(s_["id"], str) or not s_["id"].startswith("wks_") or not isinstance(s_["name"], str) or not num(s_["x"]) or not num(s_["y"])):
                bad("every works site needs an id starting wks_, a name, and numbers x and y (DCS metres)")
    if "start_hour" in d and (isinstance(d["start_hour"], bool) or d["start_hour"] not in (0, 4, 8, 12, 16, 20)):
        bad("start_hour must be 0, 4, 8, 12, 16 or 20 (a campaign turn is four hours: the start lies on that grid)")
    if "opening_strike" in d:
        o = d["opening_strike"]
        if not isinstance(o, dict) or set(o) - {"levels", "kill", "text", "fill"}:
            bad("opening_strike takes only levels, kill, text and fill")
        if not isinstance(o.get("levels"), list) or not o["levels"] or not all(v in (1, 2, 3) for v in o["levels"]):
            bad("opening_strike.levels must be a list of 1, 2, 3")
        from . import scenario
        if not isinstance(o.get("kill"), str) or o["kill"].replace("-", "").lower() not in {v.replace("-", "").lower() for v in scenario.SAM_VALUE}:
            bad(f"opening_strike.kill must name a SAM variant ({', '.join(scenario.SAM_VALUE)}; \"sa5\" and \"SA-5\" both work)")
        if "text" in o and (not isinstance(o["text"], str) or o["text"].count("{") != o["text"].count("{kill}")):
            bad("opening_strike.text is plain text; the only placeholder is {kill}")
        known_ = {v.replace("-", "").lower() for v in scenario.SAM_VALUE} | {"ewr"}
        if "fill" in o and (not isinstance(o["fill"], list) or not all(isinstance(k_, str) and k_.replace("-", "").lower() in known_ for k_ in o["fill"])):
            bad(f"opening_strike.fill is a list of SAM variants ({', '.join(scenario.SAM_VALUE)}) or \"EWR\", in the order the F-117A pairs take them")
    if "raid_bearing_deg" in d:
        v = d["raid_bearing_deg"]
        if (not isinstance(v, list) or len(v) != 2 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v) or not 0 <= v[0] <= v[1] <= 360):
            bad("raid_bearing_deg must be [lo, hi] in degrees, 0 <= lo <= hi <= 360")
    if "raid_from_base" in d and (isinstance(d["raid_from_base"], bool) or not isinstance(d["raid_from_base"], (int, float)) or not 0 <= d["raid_from_base"] <= 45):
        bad("raid_from_base must be a number of degrees, 0 to 45 (the jitter either side of the line from the carrier through the bomber field)")
    if "raid_grace_days" in d and (isinstance(d["raid_grace_days"], bool) or not isinstance(d["raid_grace_days"], int) or not 0 <= d["raid_grace_days"] <= 60):
        bad("raid_grace_days must be a whole number of days, 0 to 60 (no carrier raid is staged while the day is at most this)")
    if "max_raid" in d:
        levels_of("max_raid", d["max_raid"])
        if not all(isinstance(n_, int) and not isinstance(n_, bool) and 4 <= n_ <= 40 for n_ in d["max_raid"].values()):
            bad("max_raid values must be whole numbers of bombers, 4 to 40")
    for f_ in d.get("blue_fields", []):
        if "patriot" in f_ and not isinstance(f_["patriot"], bool):
            bad(f"blue field {f_.get('id')!r}: patriot must be true or false (a divert field that still gets its Patriot)")
    if "bomber_bases" in d:
        ids_ = [f["id"] for f in d.get("red_fields", [])]
        if (not isinstance(d["bomber_bases"], list) or not d["bomber_bases"] or len(set(d["bomber_bases"])) != len(d["bomber_bases"])
                or not all(isinstance(b_, str) and b_ in ids_ for b_ in d["bomber_bases"])):
            bad("bomber_bases must be a list of different red field ids (an id from red_fields, e.g. ab_damascus), the lead first")
    if "land_tu" in d:
        levels_of("land_tu", d["land_tu"])
        if not all(isinstance(n_, int) and not isinstance(n_, bool) and 2 <= n_ <= 8 for n_ in d["land_tu"].values()):
            bad("land_tu values must be whole numbers of Tu-22M3, 2 to 8")
    if "map_box" in d:
        v = d["map_box"]
        if (not isinstance(v, dict) or set(v) != {"x0", "x1", "y0", "y1"} or not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values()) or v["x0"] >= v["x1"] or v["y0"] >= v["y1"]):
            bad("map_box must be {x0, x1, y0, y1} in DCS metres with x0 < x1 (south, north) and y0 < y1 (west, east)")
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
