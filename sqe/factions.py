"""Faction packs: who fights, with what, and in which era. Data, not code.

A pack is one JSON file:
  * bundled:   sqe/data/factions/<id>.json
  * your own:  %APPDATA%\\SQE\\factions\\<id>.json   (same id as a bundled pack replaces it)

A campaign has two: blue and red (CampaignState.factions; a new campaign takes them from its theatre pack's "factions" key). Every pack may
hold every section; what a side actually uses today:
  * blue: countries, support (AWACS, tankers, recovery tanker), navy (carrier and escorts), base_defence, ground.task_force / ground.jtac;
  * red:  countries, air (fighters, ranges, types per level, striker, bomber), air_defence (site types and which appear per level),
          ground (support sites, armour columns, garrisons, wrecks).
When red gets real squadrons and bases (next step) both sides read the same sections.

Air-defence site types ("variants": "SA-6", "AAA", later "FLAK88" ...) are global: every pack's variants are merged into one table, so
code that asks "how far does an SA-6 reach" works whichever side owns it. Variant ids must be unique across packs.

The module-level views (RANGE_NM, ENVELOPE, ...) and the Live* containers keep old call sites working unchanged: `x in ENEMY_FIGHTERS`
or `RANGE_NM["SA-6"]` read from the packs in use at that moment.

Pack keys: see docs/FACTIONS.md.
"""
from __future__ import annotations
import json
from collections.abc import Mapping, Set
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "factions"
DEFAULT = {"blue": "modern_usa", "red": "modern_russia"}
ERAS = ("ww2", "early_jet", "modern")

_PACKS: dict | None = None
_ACTIVE: dict = {}
_VARIANTS: dict | None = None


# ---- loading ------------------------------------------------------------------------------------------------------------------------
def user_dir() -> Path | None:
    try:
        from .settings import config_dir
        return config_dir() / "factions"
    except Exception:
        return None


def _dirs() -> list:
    out = [DATA]
    u = user_dir()
    if u is not None and u.is_dir():
        out.append(u)
    return out


def packs() -> dict:
    """{id: pack}; a user pack replaces a bundled one with the same id."""
    global _PACKS
    if _PACKS is None:
        out = {}
        for folder in _dirs():
            for p in sorted(folder.glob("*.json")):
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    raise ValueError(f"faction pack {p.name} is not valid JSON: {e}") from None
                if not isinstance(d, dict) or not d.get("id"):
                    raise ValueError(f"faction pack {p.name} has no id")
                if d.get("era", "modern") not in ERAS:
                    raise ValueError(f"faction pack {p.name}: era must be one of {', '.join(ERAS)}")
                d.setdefault("countries", ["USA"])
                d["_file"] = str(p)
                out[d["id"]] = d
        _PACKS = out
    return _PACKS


def reload() -> None:
    global _PACKS, _VARIANTS
    _PACKS = _VARIANTS = None
    _ACTIVE.clear()


def get(fid: str) -> dict:
    p = packs().get(fid)
    if p is None:
        raise ValueError(f"unknown faction {fid!r}; available: {', '.join(sorted(packs()))}")
    return p


def available(era: str | None = None, side: str | None = None) -> dict:
    return {k: v["name"] for k, v in packs().items() if (era is None or v.get("era") == era) and (side is None or v.get("side") in (side, None))}


# ---- the factions in use ------------------------------------------------------------------------------------------------------------
def use(blue: str | None = None, red: str | None = None) -> dict:
    """Make these the active factions (a campaign calls this when it is created or opened)."""
    _ACTIVE["blue"] = get(blue or DEFAULT["blue"])
    _ACTIVE["red"] = get(red or DEFAULT["red"])
    return {"blue": _ACTIVE["blue"]["id"], "red": _ACTIVE["red"]["id"]}


def for_theatre(th: dict) -> dict:
    """The theatre pack's factions, or the modern pair."""
    f = th.get("factions") or {}
    return {"blue": f.get("blue", DEFAULT["blue"]), "red": f.get("red", DEFAULT["red"])}


def blue() -> dict:
    if "blue" not in _ACTIVE:
        _use_theatre_default()
    return _ACTIVE["blue"]


def red() -> dict:
    if "red" not in _ACTIVE:
        _use_theatre_default()
    return _ACTIVE["red"]


def _use_theatre_default() -> None:
    try:
        from . import theatres
        use(**for_theatre(theatres.active()))
    except Exception:
        use(**DEFAULT)


def side(name: str) -> dict:
    return blue() if name == "blue" else red()


def country(name: str) -> str:
    """The main DCS country of a side (the first in its pack)."""
    return side(name)["countries"][0]


def _sec(p: dict, *path, default=None):
    for k in path:
        if not isinstance(p, dict) or k not in p:
            return default
        p = p[k]
    return p


# ---- red: air ----------------------------------------------------------------------------------------------------------------------
def enemy_types(level: int, fallback=None) -> list:
    t = _sec(red(), "air", "types_by_level", str(level))
    return list(t) if t else list(fallback or [])


def striker() -> str:
    return _sec(red(), "air", "striker", default="Su_24M")


def bomber() -> str:
    return _sec(red(), "air", "bomber", default="")


# ---- red: air defence ---------------------------------------------------------------------------------------------------------------
def sam_variants(level: int, fallback=None) -> list:
    v = _sec(red(), "air_defence", "sam_variants_by_level", str(level))
    return list(v) if v is not None else list(fallback or [])


def forward_sams(level: int, fallback=()) -> tuple:
    v = _sec(red(), "air_defence", "forward_sams_by_level", str(level))
    return tuple(v) if v is not None else tuple(fallback)


def ewr_variant(advanced: bool) -> str:
    ad = _sec(red(), "air_defence", default={}) or {}
    return ad.get("ewr_advanced" if advanced else "ewr") or ("EWR55" if advanced else "EWR")


def variants() -> dict:
    """Every air-defence site type of every pack: {variant: {label, name, value, range_nm, envelope_ft, weight, radar, long_range, mobile, units}}."""
    global _VARIANTS
    if _VARIANTS is None:
        out = {}
        for p in packs().values():
            for k, v in (_sec(p, "air_defence", "variants") or {}).items():
                out.setdefault(k, v)
        _VARIANTS = out
    return _VARIANTS


def sites() -> dict:
    """{variant: [(unit, count)]} — the vehicles of each site type."""
    return {k: [tuple(u) for u in v.get("units", [])] for k, v in variants().items()}


def radar_types(kind: str) -> set:
    """Unit type names (as DCS stores them) of track ("track") or search ("search") radars, across all packs."""
    key = "track_radars" if kind == "track" else "search_radars"
    out = set()
    for p in packs().values():
        out.update(_sec(p, "air_defence", key) or [])
    return out


# ---- red: ground ------------------------------------------------------------------------------------------------------------------
def soft(side_name: str = "red") -> dict:
    """{AssetKind: [(unit, count)]} for headquarters, fuel, depots, airfield guards and columns."""
    from .models import AssetKind
    raw = _sec(side(side_name), "ground", "soft") or {}
    return {AssetKind(k): [tuple(u) for u in v] for k, v in raw.items()}


def armor(side_name: str = "red") -> dict:
    return _sec(side(side_name), "ground", "armor") or {}


def garrison(side_name: str = "red") -> dict:
    return _sec(side(side_name), "ground", "garrison") or {}


def wreck_mix(side_name: str = "red") -> tuple:
    g = _sec(side(side_name), "ground", default={}) or {}
    return tuple(g.get("wreck_mix") or ()), g.get("wreck_aaa", "")


# ---- blue ---------------------------------------------------------------------------------------------------------------------------
def support(slot: str, key: str | None = None):
    """A SupportSpec for awacs[CARRIER|AIRFIELD], tankers[BASKET|BOOM] or recovery_tanker, or None if the faction has none."""
    from .aircraft import SupportSpec
    d = _sec(blue(), "support", slot)
    if d is not None and key is not None:
        d = d.get(key)
    if not d:
        return None
    return SupportSpec(d["type"], d["label"], int(d["altitude_ft"]), int(d["speed_kts"]))


def navy(side_name: str = "blue") -> dict:
    return _sec(side(side_name), "navy") or {}


def base_defence(side_name: str = "blue") -> list:
    return _sec(side(side_name), "base_defence") or []


def task_force(side_name: str = "blue") -> list:
    return [tuple(u) for u in (_sec(side(side_name), "ground", "task_force") or [])]


def jtac_vehicle(side_name: str = "blue") -> str:
    return _sec(side(side_name), "ground", "jtac", default="Hummer")


# ---- live views for old call sites -----------------------------------------------------------------------------------------------
class VariantView(Mapping):
    """RANGE_NM-style dict: {variant: attribute} over every pack's site types (variants without the attribute are left out)."""
    def __init__(self, attr: str, conv=None):
        self._attr, self._conv = attr, conv or (lambda v: v)

    def _d(self) -> dict:
        return {k: self._conv(v[self._attr]) for k, v in variants().items() if self._attr in v}

    def __getitem__(self, k):
        return self._d()[k]

    def __iter__(self):
        return iter(self._d())

    def __len__(self):
        return len(self._d())


class VariantFlag(Set):
    """RADAR-style set: the variants whose attribute is true."""
    def __init__(self, attr: str):
        self._attr = attr

    def _s(self) -> set:
        return {k for k, v in variants().items() if v.get(self._attr)}

    def __contains__(self, k):
        return k in self._s()

    def __iter__(self):
        return iter(self._s())

    def __len__(self):
        return len(self._s())


class LiveSet(Set):
    """A set computed from the active packs on every use (e.g. ENEMY_FIGHTERS)."""
    def __init__(self, fn):
        self._fn = fn

    def __contains__(self, k):
        return k in self._fn()

    def __iter__(self):
        return iter(self._fn())

    def __len__(self):
        return len(self._fn())

    def __or__(self, other):
        return set(self._fn()) | set(other)


class LiveMap(Mapping):
    """A dict computed from the active packs on every use. Keys may be str enums (BaseKind.CARRIER) or plain strings."""
    def __init__(self, fn):
        self._fn = fn

    @staticmethod
    def _k(k):
        return getattr(k, "value", k)

    def __getitem__(self, k):
        return self._fn()[self._k(k)]

    def __contains__(self, k):
        return self._k(k) in self._fn()

    def __iter__(self):
        return iter(self._fn())

    def __len__(self):
        return len(self._fn())


class LiveObject:
    """An object whose attributes come from whatever fn() returns now (e.g. RECOVERY_TANKER)."""
    def __init__(self, fn):
        object.__setattr__(self, "_fn", fn)

    def __getattr__(self, name):
        return getattr(self._fn(), name)

    def __bool__(self):
        return self._fn() is not None


def _set_of(*path):
    return lambda: set(_sec(red(), *path) or [])


def _map_of(*path):
    return lambda: dict(_sec(red(), *path) or {})


ENEMY_FIGHTERS_LIVE = LiveSet(_set_of("air", "fighters"))
ENEMY_RADIUS_LIVE = LiveMap(_map_of("air", "radius_nm"))
INTERCEPT_LIVE = LiveMap(_map_of("air", "intercept_nm"))


def _support_map(slot: str):
    def fn():
        d = _sec(blue(), "support", slot) or {}
        return {k: support(slot, k) for k in d}
    return fn


AWACS_LIVE = LiveMap(_support_map("awacs"))
TANKER_LIVE = LiveMap(_support_map("tankers"))
RECOVERY_LIVE = LiveObject(lambda: support("recovery_tanker"))


# ---- checking packs ------------------------------------------------------------------------------------------------------------------
def check_pair(blue_id: str, red_id: str) -> None:
    """Refuse a blue/red pair that cannot make a war: different eras, a pack marked incomplete, or a red side with no air force."""
    b, r = get(blue_id), get(red_id)
    if b.get("era") != r.get("era"):
        raise ValueError(f"{b['name']} ({b.get('era')}) and {r['name']} ({r.get('era')}) are from different eras")
    for p in (b, r):
        if p.get("incomplete"):
            raise ValueError(f"faction {p['name']} is marked incomplete: {p.get('notes', '')}")
    if not any((_sec(r, "air", "types_by_level") or {}).values()):
        raise ValueError(f"red faction {r['name']} has no aircraft (air.types_by_level)")


def problems(fid: str) -> list:
    """Unit names in a pack that this pydcs does not know (empty list = the pack is good). Aircraft may also come from unit packs."""
    from dcs import planes, helicopters, ships, countries
    from .catalog import resolve_type
    p = get(fid)
    bad = []

    def veh(n):
        from .mission_builder import _vt
        if _vt(n) is None:
            bad.append(f"vehicle {n}")

    def air(n):
        try:
            resolve_type(n)
        except KeyError:
            bad.append(f"aircraft {n}")

    for c in p.get("countries", []):
        if not any(getattr(cls, "name", None) == c for cls in vars(countries).values() if isinstance(cls, type)):
            bad.append(f"country {c}")
    for t in set(_sec(p, "air", "fighters") or []) | set(sum((_sec(p, "air", "types_by_level") or {}).values(), [])):
        air(t)
    for k in ("striker", "bomber"):
        if _sec(p, "air", k):
            air(_sec(p, "air", k))
    for slot in ("awacs", "tankers"):
        for d in (_sec(p, "support", slot) or {}).values():
            air(d["type"])
    if _sec(p, "support", "recovery_tanker"):
        air(_sec(p, "support", "recovery_tanker")["type"])
    for v in (_sec(p, "air_defence", "variants") or {}).values():
        for u in v.get("units", []):
            veh(u[0])
    for lst in (_sec(p, "ground", "soft") or {}).values():
        for u in lst:
            veh(u[0])
    for key in ("armor", "garrison"):
        for val in (_sec(p, "ground", key) or {}).values():
            for n in (val if isinstance(val, list) else [val]):
                veh(n)
    for mix in _sec(p, "ground", "wreck_mix") or []:
        for n in mix:
            veh(n)
    for u in _sec(p, "ground", "task_force") or []:
        veh(u[0])
    if _sec(p, "ground", "jtac"):
        veh(_sec(p, "ground", "jtac"))
    for bd in _sec(p, "base_defence") or []:
        for u in bd["units"]:
            veh(u[0])
    nv = _sec(p, "navy") or {}
    for n in [nv.get("carrier")] + [e[0] for e in nv.get("escorts", [])]:
        if n and not isinstance(getattr(ships, n, None), type):
            bad.append(f"ship {n}")
    return bad
