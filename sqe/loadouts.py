"""Loadouts as raw {pylon: CLSID} dicts. Weapons are looked up by stem so they survive pydcs renames.
Override anything by naming a group in the Mission Editor like  F-14BU:STRIKE  and running tools/capture_loadouts.py."""
from __future__ import annotations
import json
import zipfile
from pathlib import Path
from .aircraft import AIRCRAFT
from .models import Role

_D: dict = {
    "F-14BU": {
        "CAP": {1: "LAU_138_AIM_9M", 10: "LAU_138_AIM_9M", 2: "AIM_7MH", 9: "AIM_7MH", 4: "AIM_54C_Mk60",
                5: "AIM_54C_Mk60", 6: "AIM_54C_Mk60", 7: "AIM_54C_Mk60", 3: "Fuel_tank_300_gal_", 8: "Fuel_tank_300_gal_"},
        "STRIKE": {1: "LAU_138_AIM_9M", 10: "LAU_138_AIM_9M", 2: "AIM_7MH", 9: "LANTIRN_Targeting_Pod",
                   4: "GBU_31_V_2", 7: "GBU_31_V_2", 5: "AIM_7MH_", 6: "AIM_7MH_", 3: "Fuel_tank_300_gal_", 8: "Fuel_tank_300_gal_"},
    },
    "FA-18C": {
        "CAP": {1: "AIM_9X", 9: "AIM_9X", 2: "AIM_120C", 8: "AIM_120C", 4: "AIM_120C", 6: "AIM_120C", 5: "FPU_8A"},
        "STRIKE": {1: "AIM_9X", 9: "AIM_9X", 4: "AIM_120C", 6: "AIM_120C", 2: "GBU_31_V_1", 8: "GBU_31_V_1",
                   3: "FPU_8A", 7: "FPU_8A", 5: "AN_AAQ_28"},
        "SEAD": {1: "AIM_9X", 9: "AIM_9X", 4: "AIM_120C", 6: "AIM_120C", 2: "AGM_88C", 8: "AGM_88C", 3: "AGM_88C",
                 7: "AGM_88C", 5: "FPU_8A"},
    },
    "F-16C": {
        "CAP": {1: "AIM_9X", 9: "AIM_9X", 2: "AIM_120C", 8: "AIM_120C", 3: "AIM_120C", 7: "AIM_120C",
                4: "Fuel_tank_370", 6: "Fuel_tank_370"},
        "STRIKE": {1: "AIM_9X", 9: "AIM_9X", 2: "AIM_120C", 8: "AIM_120C", 3: "GBU_31_V_1", 7: "GBU_31_V_1",
                   4: "Fuel_tank_370", 6: "Fuel_tank_370", 11: "AN_AAQ_28"},
        "SEAD": {1: "AIM_9X", 9: "AIM_9X", 2: "AIM_120C", 8: "AIM_120C", 3: "AGM_88C", 7: "AGM_88C",
                 4: "AGM_88C", 6: "AGM_88C"},
    },
    "F-15C": {"CAP": {1: "AIM_120C", 3: "AIM_9M", 4: "AIM_120C", 5: "AIM_120C", 7: "AIM_120C", 8: "AIM_120C",
                      9: "AIM_9M", 11: "AIM_120C"}},
    "A-10C": {"CAS": {1: "GBU_12", 11: "GBU_12", 2: "LAU_68___7_x_UnGd_Rkts__70_mm_Hydra_70_M151_HE",
                      10: "LAU_68___7_x_UnGd_Rkts__70_mm_Hydra_70_M151_HE", 5: "BRU_42___1_x_Mk_82___500lb_GP_Bomb_LD",
                      7: "BRU_42___1_x_Mk_82___500lb_GP_Bomb_LD", 6: "Mk_82___500lb_GP_Bomb_LD"}},
}
_ALIAS = {Role.ESCORT: "CAP", Role.SWEEP: "CAP", Role.CAP: "CAP"}


def _find(P, want):
    if hasattr(P, want):
        return getattr(P, want)
    c = sorted((a for a in dir(P) if not a.startswith("_") and want in a), key=len)
    return getattr(P, c[0]) if c else None


class LoadoutLibrary:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.custom = json.loads(self.path.read_text()) if self.path and self.path.exists() else {}
        self.warnings: list = []

    def for_role(self, key: str, role: Role) -> dict:
        name = _ALIAS.get(role, role.value)
        c = self.custom.get(key, {})
        if name in c:
            return {int(p): {"CLSID": v} for p, v in c[name].items()}
        table = _D.get(key, {}).get(name) or _D.get(key, {}).get("CAP") or next(iter(_D.get(key, {}).values()), {})
        cls, out = AIRCRAFT[key].dcs_type, {}
        for pylon, want in table.items():
            P = getattr(cls, f"Pylon{pylon}", None)
            w = _find(P, want) if P is not None else None
            if w is None:
                self.warnings.append(f"{key}: no weapon matching {want!r} on pylon {pylon}; skipped")
                continue
            out[pylon] = {"CLSID": w[1]["clsid"]}
        return out


# ---- enemy fighter air-to-air loads, built generically from pydcs's own tables -----------------------
_HEAVY = ["R_27ER", "R_24R", "R_77", "AIM_7"]
_SHORT = ["R_73", "R_60", "R_3S", "AIM_9"]
ENEMY_FIGHTERS = {"MiG_29A", "MiG_29S", "Su_27", "MiG_21Bis", "MiG_23MLD", "F_4E", "F_5E_3"}


def enemy_cap_loadout(cls_name: str) -> dict:
    from dcs import planes
    cls = getattr(planes, cls_name)
    out = {}
    for i in sorted(cls.pylons):
        P = getattr(cls, f"Pylon{i}", None)
        if P is None:
            continue
        for stems in ((_HEAVY, _SHORT) if i % 2 else (_SHORT, _HEAVY)):
            hit = next((a for s in stems for a in sorted(dir(P), key=len) if not a.startswith("_") and s in a), None)
            if hit:
                out[i] = {"CLSID": getattr(P, hit)[1]["clsid"]}
                break
    return out


def capture_from_miz(miz_path: str, out_path: str = "loadouts.json") -> dict:
    """Read groups named '<aircraft key>:<ROLE>' from a .miz and store their pylons (overrides the defaults)."""
    from dcs import lua
    with zipfile.ZipFile(miz_path) as z:
        mission = lua.loads(z.read("mission").decode("utf-8"))["mission"]
        dic = lua.loads(z.read("l10n/DEFAULT/dictionary").decode("utf-8")).get("dictionary", {})
    p = Path(out_path)
    lib = json.loads(p.read_text()) if p.exists() else {}
    found = {}
    for side in mission["coalition"].values():
        for country in side["country"].values():
            for grp in country.get("plane", {}).get("group", {}).values():
                nm = dic.get(grp.get("name", ""), grp.get("name", ""))
                if ":" not in nm:
                    continue
                key, role = (s.strip() for s in nm.split(":", 1))
                if key in AIRCRAFT and grp.get("units"):
                    pyl = grp["units"][1].get("payload", {}).get("pylons", {})
                    lib.setdefault(key, {})[role] = {str(n): v["CLSID"] for n, v in pyl.items()}
                    found[f"{key}:{role}"] = len(pyl)
    p.write_text(json.dumps(lib, indent=2))
    return found


# approximate combat radius (nm) of enemy types: used to decide who can escort a raid
ENEMY_RADIUS_NM = {"MiG_29A": 250, "MiG_29S": 270, "Su_27": 400, "MiG_31": 450, "MiG_23MLD": 200, "MiG_21Bis": 170,
                   "F_4E": 300, "F_5E_3": 200}


def enemy_bomber_loadout(cls_name: str) -> dict:
    """Anti-ship Kh-22 on every pylon that can take one (Tu-22M3)."""
    from dcs import planes
    cls = getattr(planes, cls_name)
    out = {}
    for i in sorted(cls.pylons):
        P = getattr(cls, f"Pylon{i}", None)
        w = _find(P, "Kh_22") if P is not None else None
        if w is not None:
            out[i] = {"CLSID": w[1]["clsid"]}
    return out
