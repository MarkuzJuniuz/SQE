"""The unit catalog: every aircraft SQE can put in a mission, in one dict-like table (`aircraft.AIRCRAFT`).

Where the entries come from, in order (a later source never replaces an earlier key):
  1. hand-tuned specs in aircraft.py (_TUNED): flown and tuned, they keep their route profiles, bingo/joker and loadouts;
  2. mod aircraft from unit packs (modunits.py): sqe/data/units/*.json and %APPDATA%\\SQE\\units\\*.json, e.g. the A-4E-C;
  3. every flyable plane and helicopter pydcs knows, generated from pydcs's own data.

A generated spec takes its roles from the DCS tasks the type can do, its route profile from its speed class (warbird, subsonic jet,
supersonic jet) and its loadouts from DCS's payload presets (loadouts.py). Generation is lazy: nothing is built until the first lookup,
and `AIRCRAFT.refresh()` rebuilds after the payload folders or unit packs change.

`configure(install, saves)` points pydcs's payload reader at YOUR DCS install and Saved Games folder (the stock presets, every mod's own
UnitPayloads folder and the presets you saved in the Mission Editor), so loadouts work without the Windows registry.
"""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

# ---- type lookup ---------------------------------------------------------------------------------------------------------------
def resolve_type(name: str):
    """A pydcs unit type from a class attribute name (F_16C_50) or a DCS type id (F-16C_50, A-4E-C)."""
    from dcs import planes, helicopters
    from . import modunits
    modunits.ensure_registered()
    for mod in (planes, helicopters):
        t = getattr(mod, name, None)
        if isinstance(t, type):
            return t
    t = planes.plane_map.get(name) or helicopters.helicopter_map.get(name)
    if t is None:
        raise KeyError(f"no aircraft type {name!r} (not in pydcs and no unit pack defines it)")
    return t


# ---- payload folders -------------------------------------------------------------------------------------------------------------
_CONFIGURED: dict = {}


def configure(install: str | None, saves: str | None) -> None:
    """Tell pydcs where the payload presets are. Safe to call repeatedly; only re-scans when a path changed."""
    key = (install or "", saves or "")
    if _CONFIGURED.get("key") == key:
        return
    _CONFIGURED["key"] = key
    try:
        from dcs.payloads import PayloadDirectories as P
        from dcs.unittype import FlyingType
    except ImportError:
        return
    dcs_dirs, mod_dirs = [], []
    if install and Path(install).is_dir():
        root = Path(install)
        dcs_dirs.append(root / "MissionEditor" / "data" / "scripts" / "UnitPayloads")
        core = root / "CoreMods" / "aircraft"
        if core.is_dir():
            dcs_dirs += [e / "UnitPayloads" for e in core.iterdir() if (e / "UnitPayloads").is_dir()]
    user = None
    if saves and Path(saves).is_dir():
        user = Path(saves) / "MissionEditor" / "UnitPayloads"
        for folder in mod_aircraft_dirs(saves):
            if (folder / "UnitPayloads").is_dir():
                mod_dirs.append(folder / "UnitPayloads")
    P._dcs, P._mod = dcs_dirs, mod_dirs
    P._user = user or Path(__file__).resolve().parent / "data" / "no_user_payloads"   # never None: pydcs would crash off Windows
    FlyingType._payload_cache = None                       # empty = pydcs re-scans the folders on the next payload lookup
    _reset_type_payloads()
    from . import aircraft
    aircraft.AIRCRAFT.refresh()


def _reset_type_payloads() -> None:
    from dcs import planes, helicopters
    for t in list(planes.plane_map.values()) + list(helicopters.helicopter_map.values()):
        if "payloads" in t.__dict__:
            t.payloads = None


def mod_aircraft_dirs(saves: str | None) -> list:
    """Every aircraft mod folder in Saved Games (Mods\\aircraft\\<mod>)."""
    if not saves:
        return []
    for sub in ("aircraft", "Aircraft"):
        p = Path(saves) / "Mods" / sub
        if p.is_dir():
            return [e for e in sorted(p.iterdir()) if e.is_dir()]
    return []


# ---- generated specs ----------------------------------------------------------------------------------------------------------------
WW2 = {"Bf-109K-4", "FW-190A8", "FW-190D9", "I-16", "La-7", "MosquitoFBMkVI", "P-47D-30", "P-47D-30bl1", "P-47D-40", "P-51D",
       "P-51D-30-NA", "SpitfireLFMkIX", "SpitfireLFMkIXCW", "F4U-1D", "TF-51D", "Ju-88A4", "A-20G", "B-17G", "Ju-52", "C-47", "Ju-87"}
EARLY_JET = {"F-86F Sabre", "F-86F_FC", "MiG-15bis", "MiG-15bis_FC", "MiG-19P", "F-100D", "A-4E-C"}
BOOM = {"F-15ESE", "F-4E-45MC", "F-4E"}
BASKET = {"F-14A-135-GR", "F-14A-135-GR-Early", "F-14A-95-GR", "F-14B", "AV8BNA", "M-2000C", "JF-17", "Su-33", "A-4E-C"}
CARRIER_HOME = {"F-14A-135-GR", "F-14A-135-GR-Early", "F-14A-95-GR", "F-14B"}
CARRIER_OK = {"AV8BNA", "Su-33", "F4U-1D", "A-4E-C"}
TWO_SEAT = {"F-14A-135-GR", "F-14A-135-GR-Early", "F-14A-95-GR", "F-14B", "F-15ESE", "F-4E-45MC", "MosquitoFBMkVI", "Mi-24P", "AH-64D_BLK_II",
            "CH-47Fbl1", "OH58D", "Mi-8MT", "UH-1H"}

# DCS task name -> SQE role
TASK_ROLES = {"CAP": "CAP", "Intercept": "CAP", "Escort": "ESCORT", "Fighter Sweep": "SWEEP", "CAS": "CAS",
              "Ground Attack": "STRIKE", "Pinpoint Strike": "STRIKE", "SEAD": "SEAD"}


def era_of(type_id: str, max_speed: float) -> str:
    if type_id in WW2:
        return "ww2"
    if type_id in EARLY_JET:
        return "early_jet"
    return "modern"


def profile_for(era: str, max_speed_kmh: float):
    """A route profile from the speed class. Tuned jets have their own; these are sensible starting points."""
    from .aircraft import RouteProfile
    from .models import Role as R
    if era == "ww2":
        return RouteProfile(depart_alt_ft=3000, depart_kts=200, dep_nm=5, aar_alt_ft=8000, aar_kts=220, marshal_alt_ft=10000, marshal_kts=230,
                            cap_alt_ft=15000, cap_kts=250, cap_leg_nm=15,
                            alt_ft={R.STRIKE: 8000, R.SEAD: 6000, R.ESCORT: 12000, R.SWEEP: 15000, R.CAS: 4000},
                            push_kts=260, ip_kts=270, attack_kts=280, egress_kts=280, push_nm=30, ip_nm=10, egress_nm=12,
                            med_alt_ft=5000, low_agl_ft=300, tgt_note="Release")
    if max_speed_kmh < 1300:
        return RouteProfile(depart_alt_ft=5000, depart_kts=300, aar_alt_ft=16000, aar_kts=300, marshal_alt_ft=16000, marshal_kts=330,
                            cap_alt_ft=20000, cap_kts=360, cap_leg_nm=20,
                            alt_ft={R.STRIKE: 15000, R.SEAD: 15000, R.ESCORT: 20000, R.SWEEP: 22000, R.CAS: 8000},
                            push_kts=420, ip_kts=450, attack_kts=450, egress_kts=480, push_nm=45, ip_nm=18, egress_nm=20,
                            low_agl_ft=400)
    return RouteProfile()


def _fuel_marks(fuel_kg: float) -> tuple:
    lbs = fuel_kg * 2.2046
    r = lambda v: max(300, int(round(v / 100.0)) * 100)
    return r(lbs * 0.16), r(lbs * 0.24)


def spec_from_type(t, key: str | None = None, **over):
    """An AircraftSpec for a pydcs type, optionally with overrides (from a unit pack)."""
    from .aircraft import AircraftSpec
    from .models import BaseKind, RefuelMethod, Role
    tid = t.id
    heli = bool(getattr(t, "helicopter", False))
    names = {getattr(x, "name", "") for x in (getattr(t, "tasks", None) or [])}
    roles = frozenset(Role(TASK_ROLES[n]) for n in names if n in TASK_ROLES) if not heli else frozenset()
    era = over.pop("era", None) or era_of(tid, getattr(t, "max_speed", 1000) or 1000)
    vmax = float(getattr(t, "max_speed", 1000) or 1000)
    refuel = RefuelMethod.BOOM if tid in BOOM else RefuelMethod.BASKET if tid in BASKET else RefuelMethod.NONE
    home = BaseKind.CARRIER if tid in CARRIER_HOME else BaseKind.AIRFIELD
    bingo, joker = _fuel_marks(float(getattr(t, "fuel_max", 3000) or 3000))
    radius = 300 if era == "ww2" else 250 if vmax < 1300 else 300
    cruise = 220 if era == "ww2" else 380 if vmax < 1300 else 450
    base = dict(key=key or tid, display=tid, dcs_class=tid, home=home, roles=roles, refuel=refuel,
                crew=2 if tid in TWO_SEAT else 1, combat_radius_nm=radius, cruise_kts=cruise,
                player_flyable=bool(getattr(t, "flyable", False)) and not heli and bool(roles),
                profile=profile_for(era, vmax), fc3=not getattr(t, "panel_radio", None), first_wp_label="",
                bingo_lbs=bingo, joker_lbs=joker, carrier_capable=tid in CARRIER_OK, helicopter=heli, era=era, source="pydcs")
    base.update({k: v for k, v in over.items() if v is not None})
    return AircraftSpec(**base)


class Catalog(Mapping):
    """Dict-like: AIRCRAFT[key] -> AircraftSpec. Iterates tuned specs first, then mods, then pydcs types alphabetically."""

    def __init__(self, tuned: dict):
        self._tuned = dict(tuned)
        self._all: dict | None = None

    # -- building ---------------------------------------------------------------------------------------------
    def _build(self) -> dict:
        from dcs import planes, helicopters
        from . import modunits
        out = dict(self._tuned)
        covered = {s.dcs_class for s in self._tuned.values()}
        covered |= {getattr(getattr(planes, s.dcs_class, None), "id", s.dcs_class) for s in self._tuned.values()}
        for spec in modunits.specs():                              # mod aircraft from unit packs
            if spec.key not in out:
                out[spec.key] = spec
                covered.add(spec.dcs_class)
        gen = []
        for t in list(planes.plane_map.values()) + list(helicopters.helicopter_map.values()):
            if not getattr(t, "flyable", False) or t.id in covered or t.id in out:
                continue
            try:
                gen.append(spec_from_type(t))
            except Exception:                                      # one odd type must never break the catalog
                continue
        for s in sorted(gen, key=lambda s: s.display.lower()):
            out.setdefault(s.key, s)
        return out

    @property
    def _d(self) -> dict:
        if self._all is None:
            self._all = self._build()
        return self._all

    def refresh(self) -> None:
        self._all = None

    # -- Mapping ------------------------------------------------------------------------------------------------
    def __getitem__(self, key):
        if key in self._tuned:                                    # fast path: never builds the catalog for the five tuned jets
            return self._tuned[key]
        return self._d[key]

    def __iter__(self):
        return iter(self._d)

    def __len__(self):
        return len(self._d)

    def __contains__(self, key):
        return key in self._tuned or key in self._d

    # -- views ----------------------------------------------------------------------------------------------------
    def tuned(self) -> dict:
        return dict(self._tuned)

    def by_source(self, source: str) -> dict:
        return {k: v for k, v in self._d.items() if v.source == source}

    def player_types(self, era: str | None = None) -> dict:
        return {k: v for k, v in self._d.items() if v.player_flyable and (era is None or v.era == era)}

    def with_overrides(self, key: str, **over):
        """A copy of a spec with some fields changed (used by tests and future faction packs)."""
        return replace(self[key], **over)
