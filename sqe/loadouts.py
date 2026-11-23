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
# S51 (XO 2026-11-12: "F-15E does standoff runway cratering, while DEAD stays the domain of the F-16"): the "PEN" kit, AGM-154C (unitary BROACH) per F-15E on pylons 2 and 18. Its own table, NOT JSOW_PER_JET:
# the F-15E must never fill a Standoff DEAD / standoff counter-air slot (`packages.KIT_JETS["JSOW"]` is JSOW_PER_JET). Only a runway crater (a STRIKE with aim RUNWAY) offers it.
PEN_PER_JET = {"F-15E": 2}
# S51: a PEN F-15E has no 610 gal wing tanks (they sit on the pylons the JSOW-Cs take). pydcs figures: `F_15E.fuel_max` 10,246 kg internal, each 610 gal tank 2,011 kg (tank and fuel): without the two
# tanks the jet carries 10,246 / (10,246 + 2 x 2,011) = 0.72 of the fuel of the plain STRIKE load. Judgment call 0.75 of the combat radius (`_in_range` multiplies it in; the 30 nm stand-off release saves
# flight but is not counted). At 450 nm: 337 nm, 506 with a safe tanker track (x1.5): the F-15E squadrons (Vaziani, Tbilisi) reach every red field but Gelen (353 to 357) and Krymsk (366 to 369) without one.
PEN_REACH = 0.75
# S60 (XO 2026-11-12: "no more GPS guided EWR strikes"): an EWR strike is a stand-off job. Who flies it, in this order: the first airframe with a squadron that has 2+ free jets in range for its kit. The ORDER is
# Opus's pick, XO has not chosen it (judgment call): JSOW-C's unitary warhead suits one radar truck best (the F-15E), then the F-16's JSOW-A, then the Hornet's SLAM-ER. XO may reorder it. The F-16 only fills the
# JSOW slot of an EWR strike (KIT_JETS["JSOW"] also lists the Hornet, which flies its SLAM-ER here). The PEN kit stays off SAM sites and counter-air: only a runway crater and an EWR strike offer it.
EWR_KIT_ORDER = (("F-15E", "PEN"), ("F-16C", "JSOW"), ("FA-18C", "SLAM"))
JSOW_FLIGHT_KITS = ("JSOW", "PEN")            # S51: the kits whose AI flight takes the JSOW route (launch point on its own axis, release, home) and is tasked from it. DEAD-only code tests "JSOW" alone

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
    "F-14B": {
        # S103c (XO 2026-11-18): the plain F-14B. CAP and FLEET are the B(U)'s two kits (every CLSID is on the pydcs `F_14B` pylon tables too, checked 2026-11-18). STRIKE is the B(U)'s kit with the two GBU-31 (4, 7) replaced
        # by the laser-guided GBU-10 (BRU-32, 2,000 lb Paveway II, the same weight as the GBU-31 so the load is the same); the LANTIRN pod stays on 9 (the B had it from 1996). No GPS / JDAM store: F_14B has none. NOT in
        # JDAM_JETS. In weather that rules a laser weapon out `weather.adapt` finds no GPS bomb for the pylon and the flight is scrubbed ("no weapon it can use"): era-true, the B cannot swap to JDAM.
        "CAP": {1: "={LAU-138 wtip - AIM-9M}", 2: "={SHOULDER AIM-7P}", 3: "={F14-300gal}", 4: "={AIM_54C_Mk47}", 5: "={AIM_54C_Mk47}", 6: "={AIM_54C_Mk47}", 7: "={AIM_54C_Mk47}", 8: "={F14-300gal}", 9: "={SHOULDER AIM-7P}", 10: "={LAU-138 wtip - AIM-9M}"},
        "FLEET": {1: "={LAU-138 wtip - AIM-9M}", 2: "={SHOULDER AIM_54C_Mk47 L}", 3: "={F14-300gal}", 4: "={AIM_54C_Mk47}", 5: "={AIM_54C_Mk47}", 6: "={AIM_54C_Mk47}", 7: "={AIM_54C_Mk47}", 8: "={F14-300gal}", 9: "={SHOULDER AIM_54C_Mk47 R}", 10: "={LAU-138 wtip - AIM-9M}"},
        "STRIKE": {1: "={LAU-138 wtip - AIM-9M}", 2: "={SHOULDER AIM_54C_Mk47 L}", 3: "={F14-300gal}", 4: "={BRU-32 GBU-10}", 7: "={BRU-32 GBU-10}", 8: "={F14-300gal}", 9: "={F14-LANTIRN-TP}", 10: "={LAU-138 wtip - AIM-9M}"},
    },
    "F-15C": {
        # stock DCS preset: AIM-9*4,AIM-120*4,Fuel*3; S157 (XO 2026-11-22): AIM-120B -> AIM-120C on 4, 5, 7, 8 (test T1fix3: the B launched at 15 to 27 km, the F-16s' C at 33 to 39;
        # the AIM-120C was first delivered in 1996, designation-systems.net, so it fits Syria 2000; firmness medium)
        "CAP": {1: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 2: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 3: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 4: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 5: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 6: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 7: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 8: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 9: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 10: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 11: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}"},
    },
    "F-15E": {
        # NOT a stock preset (the old AI model has none to copy; judgment call): AIM-9M on 1 and 19, AIM-120C on 3 and 17, 610 gal tanks on 2 and 18, GBU-31(V)1 on the four conformal-tank stations 7, 9, 11, 13
        "STRIKE": {1: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 2: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 3: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 7: "={GBU-31}", 9: "={GBU-31}", 11: "={GBU-31}", 13: "={GBU-31}", 17: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 18: "={E1F29B21-F291-4589-9FD8-3272EEC69506}", 19: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}"},
        # S51 PEN kit (standoff runway crater): the STRIKE preset's pylons 2 and 18 (610 gal tanks) take an AGM-154C JSOW (unitary BROACH, CLSID {9BCC2A2B-...}: the S50 probe fired exactly this on 2 and 18); AIM-9M on 1 and 19, AIM-120C on 3 and 17
        # as STRIKE; the four conformal stations 7, 9, 11, 13 stay EMPTY (judgment call: the kit is a stand-off shot, fewer stores is less drag and the JSOWs are the load).
        "PEN": {1: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}", 2: "={9BCC2A2B-5708-4860-B1F1-053A18442067}", 3: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 17: "={40EF17B7-F508-45de-8566-6FFECC0C1AB8}", 18: "={9BCC2A2B-5708-4860-B1F1-053A18442067}", 19: "={6CEB49FC-DED8-4DED-B053-E1F033FF72D3}"},
    },
    "F-117A": {
        # S104 (XO 2026-11-17 / 18): the two bay stations (pydcs `F_117A` Pylon1 and Pylon2 take only GBU-10 / GBU-12 / GBU-27, all laser-guided) carry a GBU-27 Paveway III penetrator each (2,000 lb, the weapon the F-117 was
        # built around; Desert Storm 1991 and Allied Force 1999 used it and the GBU-10). NOT a stock preset (the old AI model has none): judgment call. No GPS weapon exists for it, so NOT in JDAM_JETS: it releases on the target.
        "STRIKE": {1: "GBU_27", 2: "GBU_27"},
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
    "A-10A": {
        # S103b (XO 2026-11-18): the A-10C's CAS and STRIKE kits above with the targeting pod (pylon 10, A111396E) left off: the Syria 2000 A-10A has no Litening pod and no JDAM (`syria-2000-research.md` section 3), and every other
        # store of those kits (ALQ-184 on 1, LAU-88 2 x AGM-65D on 3 and 9, CBU-97 on 4 and 8, CBU-87 on 5 and 7, 2 x AIM-9M on 11; the supply strike's BRU-42 3 x Mk-82 on 3 and 9 and CBU-87 on 4, 5, 7, 8) is on the pydcs `A_10A`
        # pylon tables with the same CLSIDs (checked 2026-11-18). No "GUIDED" kit (it is GBU-31 / GBU-54 / CBU-103: JDAM and WCMD): an A-10A attacking from a high floor flies this CAS kit, Mavericks and cluster bombs. NOT in JDAM_JETS.
        "CAS": {1: "=ALQ_184", 3: "={E6A6262A-CA08-4B3D-B030-E1A993B98452}", 4: "={5335D97A-35A5-4643-9D9B-026C75961E52}", 5: "={CBU-87}", 7: "={CBU-87}", 8: "={5335D97A-35A5-4643-9D9B-026C75961E52}", 9: "={E6A6262A-CA08-4B3D-B030-E1A993B98453}", 11: "={DB434044-F5D0-4F1F-9BA9-B73027E18DD3}"},
        "STRIKE": {1: "=ALQ_184", 3: "={60CC734F-0AFA-4E2E-82B8-93B941AB11CF}", 4: "={CBU-87}", 5: "={CBU-87}", 7: "={CBU-87}", 8: "={CBU-87}", 9: "={60CC734F-0AFA-4E2E-82B8-93B941AB11CF}", 11: "={DB434044-F5D0-4F1F-9BA9-B73027E18DD3}"},
    },
}
_D["A-10C2"] = _D["A-10C"]          # S103e: the A-10C II (late) choice flies the same pydcs model and the same kits (one table, not a copy of the CLSIDs)
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
ENEMY_FIGHTERS = {"MiG_29A", "MiG_29S", "Su_27", "MiG_31", "MiG_21Bis", "MiG_23MLD", "F_4E", "F_5E_3", "MiG_25PD"}      # S90 P3a: + the MiG-25PD (Syria 2000; no Caucasus roster has it)
# S90 P3a: a fixed air-to-air kit for a type the generic picker below fills badly. MiG_25PD: pydcs gives it four pylons (1 to 4), all R-40 (1 and 4 also take an APU-60 with an R-60M). The picker would
# hang three R-40RD and an R-60M; the usual MiG-25PD / MiG-25P fit is two radar-guided R-40R (RD) on the inner pylons and two infrared R-40T (TD) on the outer ones (Wikipedia "Mikoyan-Gurevich
# MiG-25", the interceptor's armament lines, and the usual photos; from memory, firmness medium). No R-60 / R-73 on it: none was needed for the mix and the 1990s fit carries only R-40s.
ENEMY_CAP_KITS = {"MiG_25PD": {1: "R_40TD", 2: "R_40RD", 3: "R_40RD", 4: "R_40TD"}}


def enemy_cap_loadout(cls_name: str) -> dict:
    from dcs import planes
    cls = getattr(planes, cls_name)
    out = {}
    fixed = ENEMY_CAP_KITS.get(cls_name)
    if fixed:                                                          # S90 P3a: a table kit (a pylon the type lacks is skipped, as the picker does)
        for i, stem in sorted(fixed.items()):
            P = getattr(cls, f"Pylon{i}", None)
            w = _find(P, stem) if P is not None else None
            if w is not None:
                out[i] = {"CLSID": w[1]["clsid"]}
        return out
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
                   # S90 P3a (Syria 2000, no Caucasus roster has them; judgment calls, firmness low, from memory of the public data sheets): MiG_25PD 300 nm: the published combat radius is about 1,100 km subsonic
                   # but an interceptor's dash at Mach 2+ burns its fuel (about 300 km at high speed); the table runs about 0.5 to 0.7 of the sheet figure, so 300 sits between the MiG-31 (450) and the MiG-29A (250).
                   # Su_17M4 220 nm: Su-17M4 combat radius about 360 km at low level with 2,000 kg and about 650 km hi-lo-hi (Wikipedia "Sukhoi Su-17"): 220 nm lies between the two and above the Su-25 (160).
                   "MiG_25PD": 300, "Su_17M4": 220,
                   # v0.41.355 (Phase 10a): the Tu-22M3 on a land strike. 1200 nm is the one public figure for an OFAB-250 load (cmo-db.com, Tu-22M3 loadout table: unverified method, low firmness); other
                   # sources give 2,200 to 2,500 km (about 1,200 to 1,350 nm) unrefuelled (airrecognition.com, armyrecognition.com, medium firmness). Judgment call: the Caucasus targets lie 70 to 200 nm from Mozdok, so the figure never limits a strike.
                   "Tu_22M3": 1200}


BOMBER_TYPES = ("Su_24M",)       # v0.41.361 (Phase 10d) made this a tuple of two; S106 (XO 2026-11-18) removed the Su-34, so it is the Su-24M again: the red raid bombers: the types that fly field raids, the SEAD (Kh-31P) group and the DEAD (KAB-500Kr) group. Every test that used to say "Su_24M" reads this
ARM_PER_JET = {"Su_24M": 2}   # Kh-31P per jet in a SEAD group (Su-24M: pylons 2 and 7, all it takes)
ARM58_PER_JET = {"Su_24M": 2, "Su_17M4": 2}   # B2 (XO 2026-11-21): Kh-58U per jet in a long-range SEAD package. Sources: the Kh-58U is the Su-24M's anti-radiation missile from 1991 (Wikipedia "Kh-58": 36 km low, 120 km from 10,000 m, 160 km from 15,000 m; the Kh-58E fits the Su-22M4), so it is era-true for 2001 and 2006; pydcs takes it on the Su-24M's pylons 2 and 7 and on the Su-17M4's pylons 3 and 6 (the Su-17M4 takes no Kh-31P), two a jet (all each type's pylons take). Not flown in DCS: whether the AI fires it at 65 nm and whether the Su-17M4 carries it is checked in XO's flown sorties
STRIKE_PER_JET = {"Su_17M4": 4}             # FAB-500 (B3: or the kit's bomb, `STRIKE_KITS`) per jet on a plain raid: the Su-24M is not capped (it takes every pylon that takes one; the Su-34 was capped at six, S106 removed it). S90 P3a: the Su-17M4 takes six 500-kg bombs in pydcs (pylons 1, 3, 4, 5, 6, 8): four (outer pairs, 2,000 kg) is the usual combat load (Wikipedia "Sukhoi Su-17": 2,000 kg combat load at low level, firmness medium; judgment call)


# S48 (XO musing 2026-11-12): the Kh-59M (AS-18 Kazoo) standoff strike missile for red's raid bombers. SOURCES (open, checked 2026-11-12; the sources are thin and disagree on range, so every figure here is a lead, not a fact):
#  - Wikipedia "Kh-59" and the aggregator sites (redstar.gr, globalmilitary.net, armyrecognition.com): Kh-59M about 930 kg launch weight, warhead about 320 kg (penetrator or cluster), turbojet, about Mach 0.9 to 1.1 (900 to 1,080 km/h),
#    TV (day) / inertial + datalink guidance (the Kingbolt family), cruise 100 to 1,000 m above ground by radar altimeter. Medium firmness for the warhead (several sources agree on 320 kg; the 280 to 290 kg some recall is not the figure printed).
#  - RANGE: Wikipedia gives 115 km for the Kh-59M (the figure the game and the job use: about 62 nm); the 285 km some sites print is for the later Kh-59MK / anti-ship case against large ships, not the land missile. Low-to-medium firmness.
#  - Launch envelope (redstar.gr, Kh-59M page): carrier at 600 to 1,100 km/h and 0.2 to 5 km (anti-ship page: up to 11 km): a launch from 20,000 ft at 450 km/h is inside it only at the speed's low end (the raid flies 450 KPH, the table below it: judgment call, the probe shows what the AI does).
#  - Jets and count: pydcs gives the Su-24M the Kh-59M on pylons 2 and 7 and the Su-34 on pylons 4 and 9: two missiles a jet each, a symmetric pair. The "up to three on a Su-34" in the musing is not possible in the game (the only count found in public text, "up to 5", is for the Kh-59MK).
#  - The DCS AI's use of it from a Bombing / AttackGroup task is NOT known: that is what the probe mission from `.private/probes/s48` is for.
# PROBE (XO flew `.private/probes/s48`, 2026-11-12): the AI fires the Kh-59M (X_59M) from a Bombing or AttackMapObject task on a point, 2 a jet, both jets; AttackGroup and AttackUnit never fired. The Su-34 fires AT the launch waypoint, the Su-24M about 3 nm
#  before it, and ONLY with the APK-9 datalink pod on pylon 4 (without it the Su-24M kept its ammo and flew home): KH59_POD. Missiles flew 55 to 58.6 nm and hit about 335 to 355 s later; the jets turned for home within about 25 s of the second missile.
KH59_PER_JET = {"Su_24M": 2}   # Kh-59M per jet: every pylon that takes one (pydcs: 2 and 7 / 4 and 9, a balanced pair); the rest stay empty (judgment call: 930 kg each, the pair is the load)
KH59_POD = {"Su_24M": 4}   # the APK-9 pod (pydcs `APK_9_Datalink_Pod`, clsid {APK_9}) a type needs on this pylon before the AI fires its Kh-59M (the Su-34 needs none). It is not a weapon: `_limit` and the "unarmed" warning count only the missiles
ARM_POD = {"Su_24M": 5}   # T3b (XO 2026-11-22, server run: Su-24M and Su-17M4 with Kh-31P / Kh-58U flew to the launch point and turned home without firing; XO saw no Fantasmagoria pod on the jet): the L-081 Fantasmagoria ELINT pod (pydcs `L_081_Fantasmagoria_ELINT_pod`, pylon 5) the Su-24M carries with its anti-radiation missiles. Precedent: the Kh-59M fired only with its APK-9 pod (`KH59_POD`, XO's s48 probe). A HYPOTHESIS, not proven for the ARMs: the rerun shows it. The Su-17M4 has no such pod in pydcs


def gbu_count(load: dict) -> int:
    """S67: how many GBU bombs a loadout carries ({pylon: {"CLSID": id}}). Reads each pylon's weapon name from pydcs's table: a name with "GBU" counts once, or N for a
    rack named "... with N x GBU-..." (F/A-18C: BRU-55 with 2 x GBU-38, BRU-33 with 2 x GBU-12). F-16C 2, F-14B 2, F-15E 4, F/A-18C 8 (stock presets)."""
    import re
    from dcs.weapons_data import weapon_ids
    n = 0
    for v in (load or {}).values():
        name = str((weapon_ids.get(v.get("CLSID")) or {}).get("name", ""))
        if "GBU" not in name.upper():
            continue
        m = re.search(r"with\s+(\d+)\s*x", name, re.I)
        n += int(m.group(1)) if m else 1
    return n


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


def enemy_arm_loadout(cls_name: str, weapon: str = "Kh_31P") -> dict:
    """v0.41.84: Kh-31P anti-radiation missiles on every pylon that takes one (Su-24M: pylons 2 and 7); v0.41.361: at most ARM_PER_JET of them (S106: the Su-34 is gone). B2: `weapon` "Kh_58U" gives the long-range kit
    (Su-24M pylons 2 and 7, Su-17M4 pylons 3 and 6), at most ARM58_PER_JET a jet. Empty for a type that cannot carry the weapon (the Su-17M4 has no Kh-31P)."""
    from dcs import planes
    cls = getattr(planes, cls_name)
    per = ARM58_PER_JET if weapon == "Kh_58U" else ARM_PER_JET
    out = {}
    for i in sorted(cls.pylons):
        P = getattr(cls, f"Pylon{i}", None)
        w = _find(P, weapon) if P is not None else None
        if w is not None:
            out[i] = {"CLSID": w[1]["clsid"]}
    out = _limit(out, per.get(cls_name))
    pod = ARM_POD.get(cls_name)
    if out and pod:                                                              # T3b: the Su-24M's ELINT pod rides with its missiles; a pod the pydcs table lacks leaves the kit as it was
        P = getattr(cls, f"Pylon{pod}", None)
        w = _find(P, "L_081") if P is not None else None
        if w is not None:
            out[pod] = {"CLSID": w[1]["clsid"]}
    return out


def enemy_standoff_loadout(cls_name: str) -> dict:
    """S48: Kh-59M (AS-18 Kazoo) standoff missiles for a raid on a fixed target (Su-24M): every pylon that takes one, at most KH59_PER_JET, plus the APK-9 datalink pod where the type needs it (`KH59_POD`). Empty for a type that cannot carry one (the Su-25): the caller keeps the free-fall kit there."""
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


# B3 (XO 2026-11-21): the kit of a red raid by what it attacks, for the types that have one here. Weapon names are pydcs's (`_find` takes the first pylon attribute that contains the name); every pylon that takes the weapon carries it (the
# Su-24M: pylons 2, 3, 6 and 7, the rest empty: JUDGMENT CALL, the plan left "FAB-250 as before or empty" open), at most STRIKE_PER_JET a jet. A type / kind with no entry, or whose pylons take none of the weapon, keeps the FAB kit below.
#  - "runway": BetAB-500ShP, the rocket-boosted concrete-piercing bomb made for low-level runway attack (weaponsystems.net "BetAB-500ShP": low drop from 170 m, 10-nozzle booster; Fenix Insight METIS: "normally used for the attack of runways"); late Cold War, so era-true for 2001 and 2006.
#  - "troops" (raids on troops in contact and garrisons, and red's front-line strike): the RBK-500 cluster bomb. Su-24M: RBK-500U with 126 OAB-2.5RT fragmentation submunitions, the area kit (the RBK-500U was introduced in the late 1980s, TWZ; armyrecognition.com
#    "RBK-500U"). Su-17M4: pydcs gives it only the PTAB RBK-500s, so the RBK-500 with 268 PTAB-1M (the classic light-armour cluster bomb; globalsecurity.org "RBK cluster bombs"): JUDGMENT CALL on the variant.
#  - "supply" (raids on supply sites): Su-24M KAB-500S, the satellite-guided bomb. LUTORIN PULL-FORWARD (XO decision 6, 2026-11-21): the KAB-500S(-E) first flew in trials in 2000 and was shown in 2003 and the Su-24M is one of its listed carriers (Wikipedia "KAB-500S-E", deagel.com),
#    but it is only in service from about 2019, later than the campaign's 2001 / 2006: red gets it early for these raids. NOT AVAILABLE IN THE PINNED pydcs for the Su-24M (it lists the KAB-500S on the Su-30 and Su-34 only), so today `enemy_strike_loadout("Su_24M", "supply")` finds no pylon and returns the FAB kit as before;
#    the day pydcs lists it on the Su-24M the kit changes by itself. The Su-17M4 has no KAB-500S: its supply raid is the FAB-500 kit.
STRIKE_KITS = {"Su_24M": {"runway": "BetAB_500ShP", "troops": "RBK_500U", "supply": "KAB_500S"},
               "Su_17M4": {"runway": "BetAB_500ShP", "troops": "RBK_500___268"}}


def enemy_strike_loadout(cls_name: str, kind: str | None = None) -> dict:
    """Free-fall bombs for a raid (Su-24M, Su-17M4, Su-25): FAB-500 where a pylon takes one, else FAB-250. B3: `kind` ("runway" | "troops" | "supply", `STRIKE_KITS`) gives the kit for what the raid attacks; None, a type or a kind with no entry,
    or a weapon no pylon takes, gives the FAB kit."""
    from dcs import planes
    cls = getattr(planes, cls_name)
    want = (STRIKE_KITS.get(cls_name) or {}).get(kind or "")
    if want:
        kit = {}
        for i in sorted(cls.pylons):
            P = getattr(cls, f"Pylon{i}", None)
            w = _find(P, want) if P is not None else None
            if w is not None:
                kit[i] = {"CLSID": w[1]["clsid"]}
        if kit:
            return _limit(kit, STRIKE_PER_JET.get(cls_name))
    out = {}
    for i in sorted(cls.pylons):
        P = getattr(cls, f"Pylon{i}", None)
        w = (_find(P, "FAB_500M") or _find(P, "FAB_250M")) if P is not None else None
        if w is not None:
            out[i] = {"CLSID": w[1]["clsid"]}
    return _limit(out, STRIKE_PER_JET.get(cls_name))
