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
JDAM_JETS = {"F-16C", "FA-18C", "F-14BU", "F-15E"}       # v0.41.299: the jets whose STRIKE loadout is JDAMs (GBU-31 / GBU-38): their AI strikes release short of the target (routes.JDAM_RELEASE_NM)
CBU_JETS = {"F-16C"}                          # v0.41.313 (XO 2026-11-06): the jets that carry CBU-103 on a plain counter-air strike (parked aircraft, little air cover); the others keep their JDAMs
SLAM_PER_JET = {"FA-18C": 2}                  # v0.41.298: AGM-84H SLAM-ER per jet in the Standoff Strike kit (a Hornet job: no F-16 SLAM-ER in DCS)
JSOW_PER_JET = {"FA-18C": 2, "F-16C": 2}      # AGM-154A JSOW CEB per jet in the JSOW kit; only these jets fly the JSOW slot of a SEAD package

_D: dict = {
    "F-16C": {
        # JSOW slinger (SEAD package): the SEAD preset with an AGM-154A JSOW CEB on 3 and 7 in place of the HARMs (2 per jet)
        "JSOW": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={AGM-154A}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={AGM-154A}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
        # stock DCS preset: AIM-120C*4, AIM-9X*2, FUEL*2, ECM
        "CAP": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 3: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 8: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}"},
        # stock DCS preset: AIM-120C*2, AIM-9X*2, GBU-31-1B*2, FUEL*2, ECM, TGP
        "STRIKE": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={GBU-31}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={GBU-31}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
        # CBU kit (counter-air strike on parked aircraft, v0.41.313): the STRIKE preset with a CBU-103 (202 CEM bomblets, WCMD wind-corrected tail kit) on 3 and 7 in place of the GBU-31s
        "CBU": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={CBU_103}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={CBU_103}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
        # stock DCS preset: AIM-120C*2, AIM-9X*2, AGM-88C*2, FUEL*2, ECM, TGP, HTS
        "SEAD": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={B06DD79A-F21E-4EB9-BD9D-AB3844618C93}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 10: "={AN_ASQ_213}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
        # stock DCS preset: AIM-120C*2, AIM-9X*2, AGM-65D*4, FUEL*2, ECM, TGP
        "CAS": {1: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 2: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 3: "={E6A6262A-CA08-4B3D-B030-E1A993B98452}", 4: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 5: "=ALQ_184_Long", 6: "={F376DBEE-4CAE-41BA-ADD9-B2910AC95DEC}", 7: "={E6A6262A-CA08-4B3D-B030-E1A993B98453}", 8: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 9: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 11: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}"},
    },
    "FA-18C": {
        # JSOW slinger (SEAD package), XO's own Mission Editor loadout (2026-10-20): AIM-9X*2, AIM-120C-5*2, AGM-154A on 2 and 8 (2 per jet), FUEL*2 (on 3 and 7), Litening pod on 5
        "JSOW": {1: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 2: "={AGM-154A}", 3: "={FPU_8A_FUEL_TANK}", 4: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 5: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}", 6: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "={FPU_8A_FUEL_TANK}", 8: "={AGM-154A}", 9: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}"},
        # SLAM-ER kit (Standoff Strike), v0.41.298: the JSOW layout with an AGM-84H SLAM-ER on 2 and 8 (2 per jet); a starting point, not XO's Mission Editor capture
        "SLAM": {1: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}", 2: "={AGM_84H}", 3: "={FPU_8A_FUEL_TANK}", 4: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 5: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}", 6: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "={FPU_8A_FUEL_TANK}", 8: "={AGM_84H}", 9: "={5CE2FF2A-645A-4197-B48D-8720AC69394F}"},
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
        # v0.41.271 (XO 2026-11-04): the fleet-defence Tomcats carry 6 Phoenix + 2 Sidewinders (the 4 belly Phoenix of the heavy CAP preset and a Phoenix on each shoulder in place of the two Sparrows)
        "FLEET": {1: "={LAU-138 wtip - AIM-9M}", 2: "={SHOULDER AIM_54C_Mk47 L}", 3: "={F14-300gal}", 4: "={AIM_54C_Mk47}", 5: "={AIM_54C_Mk47}", 6: "={AIM_54C_Mk47}", 7: "={AIM_54C_Mk47}", 8: "={F14-300gal}", 9: "={SHOULDER AIM_54C_Mk47 R}", 10: "={LAU-138 wtip - AIM-9M}"},
        # stock DCS preset: AG04: (1/0/2) 2*J84 MEDIUM STRIKE
        "STRIKE": {1: "={LAU-138 wtip - AIM-9M}", 2: "={SHOULDER AIM_54C_Mk47 L}", 3: "={F14-300gal}", 4: "={BRU-32 GBU_31_V_2B}", 7: "={BRU-32 GBU_31_V_2B}", 8: "={F14-300gal}", 9: "={F14-LANTIRN-TP}", 10: "={LAU-138 wtip - AIM-9M}"},
    },
    "F-15C": {
        # stock DCS preset: AIM-9*4,AIM-120*4,Fuel*3
        "CAP": {1: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 2: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 3: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 4: "={C8E06185-7CD6-4C90-959F-044679E90751}", 5: "={C8E06185-7CD6-4C90-959F-044679E90751}", 6: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 7: "={C8E06185-7CD6-4C90-959F-044679E90751}", 8: "={C8E06185-7CD6-4C90-959F-044679E90751}", 9: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 10: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 11: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}"},
    },
    "F-15E": {
        # NOT a stock preset (the old AI model has none to copy; judgment call): AIM-9M on 1 and 19, AIM-120C on 3 and 17, 610 gal tanks on 2 and 18, GBU-31(V)1 on the four conformal-tank stations 7, 9, 11, 13
        "STRIKE": {1: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 2: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 3: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "={GBU-31}", 9: "={GBU-31}", 11: "={GBU-31}", 13: "={GBU-31}", 17: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 18: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 19: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}"},
    },
    "A-10C": {
        # stock DCS preset: AGM-65D*4, CBU-97*2, CBU-87*2, TGP, ECM, AIM-9*2
        "CAS": {1: "=ALQ_184", 3: "={E6A6262A-CA08-4B3D-B030-E1A993B98452}", 4: "={5335D97A-35A5-4643-9D9B-026C75961E52}", 5: "={CBU-87}", 7: "={CBU-87}", 8: "={5335D97A-35A5-4643-9D9B-026C75961E52}", 9: "={E6A6262A-CA08-4B3D-B030-E1A993B98453}", 10: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}", 11: "={DB434044-F5D0-4F1F-9BA9-B73027E18DD3}"},
        # v0.41.360 (Phase 10c part 2): the supply strike. NOT a stock preset (judgment call): the stock CAS preset above with its two AGM-65D replaced by BRU-42 3 x Mk-82 (pylons 3 and 9) and its two CBU-97
        # by CBU-87 (pylons 4 and 8): 6 Mk-82 + 4 CBU-87 (area and blast weapons for fuel and depot sites), TGP, ECM, AIM-9 as before. Dumb bombs: not in JDAM_JETS.
        # S31a part A2 (v0.41.388): the guided kit for an AI A-10C CAS flight that attacks from a high floor (24,000 ft near a radar short-range SAM, 12,000 ft near guns / MANPADS). NOT a stock DCS preset
        # (judgment call; XO flew GBU-31 / GBU-54 from his own captured loadouts.json): the stock CAS preset above with the Mavericks (3, 9) -> GBU-31(V)1 JDAM 2,000 lb, the CBU-97 (4, 8) -> GBU-54(V)1/B laser JDAM 500 lb,
        # the CBU-87 (5, 7) -> CBU-103 CEM with the WCMD wind-corrected tail kit. GPS / wind-corrected weapons only, no Maverick, rocket or gun reliance. ALQ-184, TGP, AIM-9 as before. About 3,230 kg of stores.
        "GUIDED": {1: "=ALQ_184", 3: "={GBU-31}", 4: "={GBU_54_V_1B}", 5: "={CBU_103}", 7: "={CBU_103}", 8: "={GBU_54_V_1B}", 9: "={GBU-31}", 10: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}", 11: "={DB434044-F5D0-4F1F-9BA9-B73027E18DD3}"},
        "STRIKE": {1: "=ALQ_184", 3: "={60CC734F-0AFA-4E2E-82B8-93B941AB11CF}", 4: "={CBU-87}", 5: "={CBU-87}", 7: "={CBU-87}", 8: "={CBU-87}", 9: "={60CC734F-0AFA-4E2E-82B8-93B941AB11CF}", 10: "={A111396E-D3E8-4b9c-8AC9-2432489304D5}", 11: "={DB434044-F5D0-4F1F-9BA9-B73027E18DD3}"},
    },
}
_ALIAS = {Role.TARCAP: "CAP", Role.ESCORT: "CAP", Role.SWEEP: "CAP", Role.CAP: "CAP"}


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

    def for_role(self, key: str, role: Role, kit: str = "") -> dict:
        name = kit or _ALIAS.get(role, role.value)
        c = self.custom.get(key, {})
        if name in c:
            return {int(p): {"CLSID": v} for p, v in c[name].items()}
        if name == "CBU" and "STRIKE" in c:                # v0.41.313 (XO 2026-11-06): the CBU kit starts from his own captured STRIKE loadout, only the bomb pylons change
            out = {int(p): {"CLSID": v} for p, v in c["STRIKE"].items()}
            tc, ts = _D.get(key, {}).get("CBU", {}), _D.get(key, {}).get("STRIKE", {})
            for pylon, want in tc.items():
                if ts.get(pylon) != want and want.startswith("="):
                    out[pylon] = {"CLSID": want[1:]}
            return out
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
_HEAVY = ["R_27ER", "R_24R", "R_77", "AIM_7", "R_33", "R_40RD"]      # v0.41.142: + the MiG-31's R-33 and R-40RD
_SHORT = ["R_73", "R_60", "R_3S", "AIM_9"]
ENEMY_FIGHTERS = {"MiG_29A", "MiG_29S", "Su_27", "MiG_31", "MiG_21Bis", "MiG_23MLD", "F_4E", "F_5E_3"}


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
                   "F_4E": 300, "F_5E_3": 200, "Su_24M": 300, "Su_25": 160,
                   # v0.41.361 (Phase 10d): the Su-34 flies the Su-24M's raids at L3. Judgment call: 330 nm, a little over the Su-24M's 300 (public figures: about 1,100 km combat radius for the Su-34, 1,050 km for the Su-24M,
                   # both "from memory", medium firmness; the table is the game's scale, not the books': the Caucasus targets lie 70 to 250 nm from red's fields, so the figure rarely limits a raid).
                   "Su_34": 330,
                   # v0.41.355 (Phase 10a): the Tu-22M3 on a land strike. 1200 nm is the one public figure for an OFAB-250 load (cmo-db.com, Tu-22M3 loadout table: unverified method, low firmness); other
                   # sources give 2,200 to 2,500 km (about 1,200 to 1,350 nm) unrefuelled (airrecognition.com, armyrecognition.com, medium firmness). Judgment call: the Caucasus targets lie 70 to 200 nm from Mozdok, so the figure never limits a strike.
                   "Tu_22M3": 1200}


BOMBER_TYPES = ("Su_24M", "Su_34")       # v0.41.361 (Phase 10d): the red raid bombers: the types that fly field raids, the SEAD (Kh-31P) group and the DEAD (KAB-500Kr) group. Every test that used to say "Su_24M" reads this
ARM_PER_JET = {"Su_24M": 2, "Su_34": 4}   # Kh-31P per jet in a SEAD group (Su-24M: pylons 2 and 7, all it takes; Su-34: four of the six pylons that take one, judgment call: group sizes stay the same in jets, so a Su-34 group fires twice the missiles)
STRIKE_PER_JET = {"Su_34": 6}             # FAB-500 per jet on a plain raid (Su-24M: every pylon that takes one; Su-34: six of eight, about 3 t: judgment call)


# S48 (XO musing 2026-11-12): the Kh-59M (AS-18 Kazoo) standoff strike missile for red's raid bombers. SOURCES (open, checked 2026-11-12; the sources are thin and disagree on range, so every figure here is a lead, not a fact):
#  - Wikipedia "Kh-59" and the aggregator sites (redstar.gr, globalmilitary.net, armyrecognition.com): Kh-59M about 930 kg launch weight, warhead about 320 kg (penetrator or cluster), turbojet, about Mach 0.9 to 1.1 (900 to 1,080 km/h),
#    TV (day) / inertial + datalink guidance (the Kingbolt family), cruise 100 to 1,000 m above ground by radar altimeter. Medium firmness for the warhead (several sources agree on 320 kg; the 280 to 290 kg some recall is not the figure printed).
#  - RANGE: Wikipedia gives 115 km for the Kh-59M (the figure the game and the job use: about 62 nm); the 285 km some sites print is for the later Kh-59MK / anti-ship case against large ships, not the land missile. Low-to-medium firmness.
#  - Launch envelope (redstar.gr, Kh-59M page): carrier at 600 to 1,100 km/h and 0.2 to 5 km (anti-ship page: up to 11 km): a launch from 20,000 ft at 450 km/h is inside it only at the speed's low end (the raid flies 450 KPH, the table below it: judgment call, the probe shows what the AI does).
#  - Jets and count: pydcs gives the Su-24M the Kh-59M on pylons 2 and 7 and the Su-34 on pylons 4 and 9: two missiles a jet each, a symmetric pair. The "up to three on a Su-34" in the musing is not possible in the game (the only count found in public text, "up to 5", is for the Kh-59MK).
#  - The DCS AI's use of it from a Bombing / AttackGroup task is NOT known: that is what the probe mission from `.private/probes/s48` is for.
# PROBE (XO flew `.private/probes/s48`, 2026-11-12): the AI fires the Kh-59M (X_59M) from a Bombing or AttackMapObject task on a point, 2 a jet, both jets; AttackGroup and AttackUnit never fired. The Su-34 fires AT the launch waypoint, the Su-24M about 3 nm
#  before it, and ONLY with the APK-9 datalink pod on pylon 4 (without it the Su-24M kept its ammo and flew home): KH59_POD. Missiles flew 55 to 58.6 nm and hit about 335 to 355 s later; the jets turned for home within about 25 s of the second missile.
KH59_PER_JET = {"Su_24M": 2, "Su_34": 2}   # Kh-59M per jet: every pylon that takes one (pydcs: 2 and 7 / 4 and 9, a balanced pair); the rest stay empty (judgment call: 930 kg each, the pair is the load)
KH59_POD = {"Su_24M": 4}   # the APK-9 pod (pydcs `APK_9_Datalink_Pod`, clsid {APK_9}) a type needs on this pylon before the AI fires its Kh-59M (the Su-34 needs none). It is not a weapon: `_limit` and the "unarmed" warning count only the missiles


def _limit(out: dict, n) -> dict:
    """At most n pylons of a loadout, outermost pairs first (the lowest and highest pylon numbers alternately), so the load stays symmetric. None or n >= len: unchanged."""
    if not n or len(out) <= n:
        return out
    keys = sorted(out)
    pick, lo, hi = [], 0, len(keys) - 1
    while len(pick) < n and lo <= hi:
        pick.append(keys[lo]); lo += 1
        if len(pick) < n and lo <= hi:
            pick.append(keys[hi]); hi -= 1
    return {k: out[k] for k in sorted(pick)}


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


def enemy_land_bomber_loadout(cls_name: str) -> dict:
    """v0.41.355 (Phase 10a): the Tu-22M3 on a land strike: an MBD3-U9M rack of nine OFAB-250-270 on every pylon that takes one (pydcs: pylons 1, 2, 4 and 5; pylon 3 only carries the Kh-22). No missile."""
    from dcs import planes
    cls = getattr(planes, cls_name)
    out = {}
    for i in sorted(cls.pylons):
        P = getattr(cls, f"Pylon{i}", None)
        w = _find(P, "MBD3_U9M") if P is not None else None
        if w is not None:
            out[i] = {"CLSID": w[1]["clsid"]}
    return out


def enemy_arm_loadout(cls_name: str) -> dict:
    """v0.41.84: Kh-31P anti-radiation missiles on every pylon that takes one (Su-24M: pylons 2 and 7); v0.41.361: at most ARM_PER_JET of them (Su-34: four)."""
    from dcs import planes
    cls = getattr(planes, cls_name)
    out = {}
    for i in sorted(cls.pylons):
        P = getattr(cls, f"Pylon{i}", None)
        w = _find(P, "Kh_31P") if P is not None else None
        if w is not None:
            out[i] = {"CLSID": w[1]["clsid"]}
    return _limit(out, ARM_PER_JET.get(cls_name))


def enemy_standoff_loadout(cls_name: str) -> dict:
    """S48: Kh-59M (AS-18 Kazoo) standoff missiles for a raid on a fixed target (Su-24M, Su-34): every pylon that takes one, at most KH59_PER_JET, plus the APK-9 datalink pod where the type needs it (`KH59_POD`). Empty for a type that cannot carry one (the Su-25): the caller keeps the free-fall kit there."""
    from dcs import planes
    cls = getattr(planes, cls_name, None)
    out = {}
    for i in sorted(getattr(cls, "pylons", ()) or ()):
        P = getattr(cls, f"Pylon{i}", None)
        w = _find(P, "Kh_59M") if P is not None else None
        if w is not None:
            out[i] = {"CLSID": w[1]["clsid"]}
    out = _limit(out, KH59_PER_JET.get(cls_name))
    pod = KH59_POD.get(cls_name)
    if out and pod:                                                              # the Su-24M fires only with its datalink pod (probe): no pod found = an EMPTY kit, so the raid is not flagged and the unarmed warning is not hidden
        P = getattr(cls, f"Pylon{pod}", None)
        w = _find(P, "APK_9") if P is not None else None
        if w is None:
            return {}
        out[pod] = {"CLSID": w[1]["clsid"]}
    return out


def enemy_strike_loadout(cls_name: str) -> dict:
    """Free-fall bombs for a raid on an airfield (Su-24M): FAB-500 where a pylon takes one, else FAB-250."""
    from dcs import planes
    cls = getattr(planes, cls_name)
    out = {}
    for i in sorted(cls.pylons):
        P = getattr(cls, f"Pylon{i}", None)
        w = (_find(P, "FAB_500M") or _find(P, "FAB_250M")) if P is not None else None
        if w is not None:
            out[i] = {"CLSID": w[1]["clsid"]}
    return _limit(out, STRIKE_PER_JET.get(cls_name))
