"""Unit packs: mod aircraft (and overrides for stock ones) described as data, so a new mod never needs code.

A pack is one JSON file per aircraft:
  * bundled:   sqe/data/units/<id>.json
  * your own:  %APPDATA%\\SQE\\units\\<id>.json      (same id as a bundled pack replaces it)

When pydcs does not know the type (most mods), the pack's "type" block becomes a real pydcs unit type at runtime, so SQE can put it in a
mission like any stock jet. When pydcs does know it, the pack only changes how SQE uses it (roles, era, profile, basing, loadouts).
Loadouts come from the mod's own payload presets (Saved Games\\DCS\\Mods\\aircraft\\<mod>\\UnitPayloads) or the ones you save in the
Mission Editor; a pack can also carry its own "loadouts" table.

`discover(saves)` reads every mod's entry.lua for the aircraft it declares, and `missing(saves)` lists mods with no pack yet;
tools/make_unit_pack.py writes a starter pack for one of those.

Pack keys (only "id" and, for a type pydcs lacks, "type" are required):
  id, display, required_module, era ("ww2" | "early_jet" | "modern"), home ("AIRFIELD" | "CARRIER"), carrier_capable,
  refuel ("BOOM" | "BASKET" | "NONE"), roles (["CAP","ESCORT","SWEEP","CAS","STRIKE","SEAD"]), combat_radius_nm, cruise_kts,
  bingo_lbs, joker_lbs, crew, profile ("ww2" | "subsonic" | "supersonic"), loadouts ({ROLE: {pylon: CLSID}}), verified, notes,
  type: {class_name, height, width, length, fuel_max, max_speed, chaff, flare, charge_total, chaff_charge_size, flare_charge_size,
         radio_frequency, pylons [..], tasks ["CAS", "Ground Attack", ...], livery_name, helicopter}
"""
from __future__ import annotations
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "units"
_PACKS: dict | None = None
_REGISTERED: set = set()


# ---- loading ----------------------------------------------------------------------------------------------------------------------
def user_dir() -> Path | None:
    try:
        from .settings import config_dir
        return config_dir() / "units"
    except Exception:
        return None


def _dirs() -> list:
    out = [DATA]
    u = user_dir()
    if u is not None and u.is_dir():
        out.append(u)
    return out


def packs() -> dict:
    """{type id: pack dict}; a user pack replaces a bundled one with the same id. A broken file is skipped, never fatal."""
    global _PACKS
    if _PACKS is None:
        out = {}
        for folder in _dirs():
            for p in sorted(folder.glob("*.json")):
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(d, dict) and d.get("id"):
                    d["_file"] = str(p)
                    out[d["id"]] = d
        _PACKS = out
    return _PACKS


def reload() -> None:
    global _PACKS
    _PACKS = None
    _REGISTERED.clear()
    from . import aircraft
    aircraft.AIRCRAFT.refresh()


# ---- runtime pydcs types ------------------------------------------------------------------------------------------------------------
def _task_classes(names) -> list:
    from dcs import task
    by_name = {getattr(c, "name", ""): c for c in task.MainTask.map.values()}
    return [by_name[n] for n in names if n in by_name]


def _make_type(pack: dict):
    from dcs.planes import PlaneType
    from dcs.helicopters import HelicopterType
    t = pack["type"]
    heli = bool(t.get("helicopter", False))
    tasks = _task_classes(t.get("tasks", ["CAP"])) or _task_classes(["CAP"])
    attrs = dict(
        id=pack["id"], flyable=True, height=float(t.get("height", 4.0)), width=float(t.get("width", 10.0)),
        length=float(t.get("length", 14.0)), fuel_max=float(t["fuel_max"]), max_speed=float(t.get("max_speed", 1000)),
        chaff=int(t.get("chaff", 0)), flare=int(t.get("flare", 0)), charge_total=int(t.get("charge_total", 0)),
        chaff_charge_size=int(t.get("chaff_charge_size", 1)), flare_charge_size=int(t.get("flare_charge_size", 1)),
        category=t.get("category", "Air"), radio_frequency=float(t.get("radio_frequency", 251)),
        pylons=set(int(p) for p in t.get("pylons", [])), tasks=tasks, task_default=tasks[0],
        livery_name=t.get("livery_name", pack["id"]), property_defaults={}, properties={}, payloads=None, panel_radio=None,
        helicopter=heli,
    )
    cls_name = t.get("class_name") or re.sub(r"\W", "_", pack["id"])
    return type(cls_name, (HelicopterType if heli else PlaneType,), attrs)


def ensure_registered() -> None:
    """Make every pack's type known to pydcs (idempotent). Types pydcs already has are left alone."""
    from dcs import planes, helicopters
    for tid, pack in packs().items():
        if tid in _REGISTERED:
            continue
        _REGISTERED.add(tid)
        if tid in planes.plane_map or tid in helicopters.helicopter_map or "type" not in pack:
            continue
        try:
            t = _make_type(pack)
        except (KeyError, TypeError, ValueError):
            continue                                              # a pack with a broken type block is ignored, not fatal
        (helicopters.helicopter_map if t.helicopter else planes.plane_map)[tid] = t


# ---- specs ----------------------------------------------------------------------------------------------------------------------------
def specs() -> list:
    """An AircraftSpec for every pack whose type resolves."""
    from dcs import planes, helicopters
    from .catalog import spec_from_type, profile_for
    from .models import BaseKind, RefuelMethod, Role
    ensure_registered()
    out = []
    for tid, pack in packs().items():
        t = planes.plane_map.get(tid) or helicopters.helicopter_map.get(tid)
        if t is None:
            continue
        over = {"display": pack.get("display"), "era": pack.get("era"), "combat_radius_nm": pack.get("combat_radius_nm"),
                "cruise_kts": pack.get("cruise_kts"), "bingo_lbs": pack.get("bingo_lbs"), "joker_lbs": pack.get("joker_lbs"),
                "crew": pack.get("crew"), "carrier_capable": pack.get("carrier_capable"), "source": "mod"}
        if pack.get("home"):
            over["home"] = BaseKind(pack["home"])
        if pack.get("refuel"):
            over["refuel"] = RefuelMethod(pack["refuel"])
        if pack.get("roles"):
            over["roles"] = frozenset(Role(r) for r in pack["roles"])
        prof = pack.get("profile")
        if prof:
            era = "ww2" if prof == "ww2" else "modern"
            over["profile"] = profile_for(era, 2000 if prof == "supersonic" else 1000)
        try:
            spec = spec_from_type(t, key=tid, **over)
        except (TypeError, ValueError):
            continue
        if not spec.player_flyable and spec.roles and not spec.helicopter:
            from dataclasses import replace
            spec = replace(spec, player_flyable=True)
        out.append(spec)
    return out


def pack_loadout(type_id: str, role_name: str) -> dict | None:
    """{pylon: CLSID} from the pack's own loadouts table, if it has one for the role."""
    lo = (packs().get(type_id) or {}).get("loadouts") or {}
    return lo.get(role_name) or None


def required_modules(type_ids) -> dict:
    """requiredModules entries for a mission that uses these types (DCS then tells a player which mod is missing)."""
    out = {}
    for tid in type_ids:
        p = packs().get(tid)
        if p and p.get("required_module"):
            out[p["required_module"]] = p["required_module"]
    return out


# ---- discovery in Saved Games -----------------------------------------------------------------------------------------------------
_FLYABLE = re.compile(r"make_flyable\s*\(\s*['\"]([^'\"]+)['\"]")
_PLUGIN = re.compile(r"declare_plugin\s*\(\s*['\"]([^'\"]+)['\"]")


def discover(saves: str | None) -> list:
    """[(mod folder, plugin id, [aircraft type ids])] for every aircraft mod in Saved Games\\DCS\\Mods\\aircraft."""
    from .catalog import mod_aircraft_dirs
    out = []
    for folder in mod_aircraft_dirs(saves):
        entry = folder / "entry.lua"
        if not entry.is_file():
            continue
        try:
            text = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        plug = _PLUGIN.search(text)
        out.append((folder, plug.group(1) if plug else folder.name, sorted(set(_FLYABLE.findall(text)))))
    return out


def missing(saves: str | None) -> list:
    """[(mod folder, type id)] for mod aircraft that neither pydcs nor a unit pack knows: these cannot be used until they get a pack."""
    from dcs import planes, helicopters
    have = set(packs()) | set(planes.plane_map) | set(helicopters.helicopter_map)
    return [(folder, tid) for folder, _plug, ids in discover(saves) for tid in ids if tid not in have]


_NUM = {"fuel_max": r"M_fuel_max\s*=\s*([\d.]+)", "max_speed": r"V_max_h\s*=\s*([\d.]+)", "length": r"length\s*=\s*([\d.]+)",
        "height": r"height\s*=\s*([\d.]+)", "width": r"wing_span\s*=\s*([\d.]+)", "chaff": r"chaff\s*=\s*\{[^}]*default\s*=\s*(\d+)",
        "flare": r"flare\s*=\s*\{[^}]*default\s*=\s*(\d+)"}


def starter_pack(folder: Path, type_id: str, plugin_id: str = "") -> dict:
    """A best-effort pack for a mod aircraft, read from the mod's Lua files. Check the numbers before you trust it ("verified": false)."""
    text = ""
    for p in list(folder.rglob("*.lua"))[:200]:
        try:
            s = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if type_id in s:
            text += s + "\n"
    t: dict = {"class_name": re.sub(r"\W", "_", type_id), "tasks": ["CAP", "CAS", "Ground Attack"], "pylons": []}
    for k, pat in _NUM.items():
        m = re.search(pat, text)
        if m:
            v = float(m.group(1))
            t[k] = v * 3.6 if k == "max_speed" else v               # V_max_h is m/s in an aircraft definition
    stations = sorted({int(n) for n in re.findall(r"pylon\s*\(\s*(\d+)", text)})
    t["pylons"] = stations
    t.setdefault("fuel_max", 2000.0)
    t["charge_total"] = int(t.get("chaff", 0) + t.get("flare", 0))
    return {"id": type_id, "display": type_id, "required_module": plugin_id or type_id, "era": "modern", "home": "AIRFIELD",
            "refuel": "NONE", "verified": False,
            "notes": "Generated from the mod's Lua by tools/make_unit_pack.py. Check fuel_max, max_speed, pylons and roles.", "type": t}
