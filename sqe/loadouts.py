"""Loadouts as raw {pylon: CLSID} dicts. Weapons are looked up by stem so they survive pydcs renames.
Override anything by naming a group in the Mission Editor like  F-14BU:STRIKE  and running tools/capture_loadouts.py."""
from __future__ import annotations
import json
import zipfile
from pathlib import Path
from .aircraft import AIRCRAFT
from .models import Role

# Taken from DCS's own stock presets (the lists you pick from in the Mission Editor). "=<CLSID>" is a raw weapon id; anything else is a
# weapon-name stem looked up on the pylon. The comment above each line names the stock preset it was copied from.
_D: dict = {
    "F-16C": {
        # stock DCS preset: AIM-120C*4, AIM-9X*2, FUEL*2, ECM
        "CAP": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 3: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 8: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}"},
        # stock DCS preset: AIM-120C*2, AIM-9X*2, GBU-31-1B*2, FUEL*2, ECM, TGP
        "STRIKE": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={GBU-31}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={GBU-31}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
        # stock DCS preset: AIM-120C*2, AIM-9X*2, AGM-88C*2, FUEL*2, ECM, TGP, HTS
        "SEAD": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 10: "={AN_ASQ_213}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
        # stock DCS preset: AIM-120C*2, AIM-9X*2, AGM-65D*4, FUEL*2, ECM, TGP
        "CAS": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={E6A6262A-CA08-4B3D-B030-E1A993B98452}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={E6A6262A-CA08-4B3D-B030-E1A993B98453}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
    },
    "FA-18C": {
        # stock DCS preset: AIM-9X*2, AIM-120C-5*6, FUEL*3
        "CAP": {1: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 2: "=LAU-115_2*LAU-127_AIM-120C", 3: "={FPU_8A_FUEL_TANK}", 4: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 5: "={FPU_8A_FUEL_TANK}", 6: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "={FPU_8A_FUEL_TANK}", 8: "=LAU-115_2*LAU-127_AIM-120C", 9: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}"},
        # stock DCS preset: AIM-9X*2, AIM-120C-5*1, GBU-38*4, GBU-12*4, ATFLIR, FUEL
        "STRIKE": {1: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 2: "={BRU55_2*GBU-38}", 3: "={BRU33_2X_GBU-12}", 4: "={AN_ASQ_228}", 5: "={FPU_8A_FUEL_TANK}", 6: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "={BRU33_2X_GBU-12}", 8: "={BRU55_2*GBU-38}", 9: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}"},
        # stock DCS preset: AIM-9X*2, AIM-120C-5*2, AGM-88C*2, FUEL
        "SEAD": {1: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 2: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 3: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 4: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 5: "={FPU_8A_FUEL_TANK}", 6: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 8: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 9: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}"},
        # stock DCS preset: AIM-9X*2, AIM-120C-5*1, AGM-65D*4, ATFLIR, FUEL
        "CAS": {1: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 2: "=LAU_117_AGM_65F", 3: "=LAU_117_AGM_65F", 4: "={AN_ASQ_228}", 5: "={FPU_8A_FUEL_TANK}", 6: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "=LAU_117_AGM_65F", 8: "=LAU_117_AGM_65F", 9: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}"},
    },
    "F-14BU": {
        # stock DCS preset AAW05: (4/2/2) HEAVY CAP, with the LANTIRN pod on station 9 swapped for the second Sparrow (the stock preset only carries one)
        "CAP": {1: "={LAU-138 wtip - AIM-9M}", 2: "={SHOULDER AIM-7P}", 3: "={F14-300gal}", 4: "={AIM_54C_Mk47}", 5: "={AIM_54C_Mk47}", 6: "={AIM_54C_Mk47}", 7: "={AIM_54C_Mk47}", 8: "={F14-300gal}", 9: "={SHOULDER AIM-7P}", 10: "={LAU-138 wtip - AIM-9M}"},
        # stock DCS preset: AG04: (1/0/2) 2*J84 MEDIUM STRIKE
        "STRIKE": {1: "={LAU-138 wtip - AIM-9M}", 2: "={SHOULDER AIM_54C_Mk47 L}", 3: "={F14-300gal}", 4: "={BRU-32 GBU_31_V_2B}", 7: "={BRU-32 GBU_31_V_2B}", 8: "={F14-300gal}", 9: "={F14-LANTIRN-TP}", 10: "={LAU-138 wtip - AIM-9M}"},
    },
    "F-15C": {
        # stock DCS preset: AIM-9*4,AIM-120*4,Fuel*3
        "CAP": {1: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 2: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 3: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 4: "={C8E06185-7CD6-4C90-959F-044679E90751}", 5: "={C8E06185-7CD6-4C90-959F-044679E90751}", 6: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 7: "={C8E06185-7CD6-4C90-959F-044679E90751}", 8: "={C8E06185-7CD6-4C90-959F-044679E90751}", 9: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 10: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 11: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}"},
    },
    "A-10C": {
        # stock DCS preset: AGM-65D*4, CBU-97*2, CBU-87*2, TGP, ECM, AIM-9*2
        "CAS": {1: "=ALQ_184", 3: "={E6A6262A-CA08-4B3D-B030-E1A993B98452}", 4: "={5335D97A-35A5-4643-9D9B-026C75961E52}", 5: "={CBU-87}", 7: "={CBU-87}", 8: "={5335D97A-35A5-4643-9D9B-026C75961E52}", 9: "={E6A6262A-CA08-4B3D-B030-E1A993B98453}", 10: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}", 11: "={DB434044-F5D0-4F1F-9BA9-B73027E18DD3}"},
    },
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
            if want.startswith("="):                       # raw CLSID copied from a stock preset
                out[pylon] = {"CLSID": want[1:]}
                continue
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
