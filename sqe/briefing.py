"""Briefing text (SMEAC-style) and the threat summary used by the briefing and the kneeboard."""
from __future__ import annotations
import random
from . import narrative
from .aircraft import AIRCRAFT
from .models import AssetKind, ObjectiveType
from .routes import dist, NM
from .war import totals

_SAM_NAME = {"AAA": "AAA", "MANPAD": "MANPADS", "SA-2": "SA-2 Guideline", "SA-3": "SA-3 Goa", "SA-6": "SA-6 Gainful",
             "SA-11": "SA-11 Gadfly", "SA-10": "SA-10 Grumble", "SA-15": "SA-15 Gauntlet", "SA-19": "SA-19 Grison"}
_RANGE_NM = {"AAA": 3, "MANPAD": 3, "SA-2": 25, "SA-3": 13, "SA-6": 13, "SA-11": 18, "SA-10": 48, "SA-15": 8, "SA-19": 5}


def threat_lines(state, pkg, tx, ty) -> list:
    """SAMs/EWR within ~60 nm of the target, nearest first: 'SA-6 Gainful  Gudauta SA-6 site  12 nm from target'."""
    out = []
    for a in state.assets.values():
        if a.kind not in (AssetKind.SAM, AssetKind.EWR) or a.destroyed:
            continue
        d = dist(a.x, a.y, tx, ty) / NM
        if d <= 60:
            nm = _SAM_NAME.get(a.variant, "Early-warning radar")
            rng = _RANGE_NM.get(a.variant)
            out.append((d, f"{nm}{f' (~{rng} nm)' if rng else ''} - {d:.0f} nm from target"))
    out.sort()
    return [t for _, t in out[:8]]


def fighter_threat(state) -> str:
    t = totals(state)
    return f"{t['ea']} enemy aircraft serviceable (about {t['enemy_air']:.0%} of strength)"


def build_text(state, pkg, tl: dict, plan, wps, rng: random.Random, tgt_xy) -> dict:
    """Returns {'situation','mission','execution','admin','comms','full','blue_task'} strings."""
    pf = pkg.player_flight
    spec = AIRCRAFT[pf.aircraft]
    n, pname, ptext = narrative.phase(state)
    obj = pkg.objective
    threats = threat_lines(state, pkg, *tgt_xy)
    sit = [f"{narrative.TITLE} - Day {state.day}. {pname}.", "", ptext, "", *narrative.sitrep(state), "",
           f"Commander's intent: {narrative.commander_intent(obj.type, rng)}"]
    if threats:
        sit += ["", "Threats near the target:"] + [f"  - {t}" for t in threats]
    sit += ["", f"Enemy air: {fighter_threat(state)}."]
    mis = [f"{obj.description}.", f"You are {pf.callsign}, {pf.count}x {spec.display}, tasked as {pf.role.value}."]
    exe = ["Package:"] + [f"  {f.callsign}: {f.count}x {AIRCRAFT[f.aircraft].display} ({f.role.value})"
                          + (" <- YOU" if f.is_player else "") for f in pkg.flights]
    exe += ["", "Timeline (local):", f"  Launch        {tl['launch']}", f"  Marshal       {tl['marshal']}  (hold at MSHL, stack altitudes +1,000 ft per flight)",
            f"  PUSH          {tl['push']}  (leave MSHL on this time, +/- 30 s)", f"  TOT           {tl['tot']}  (+/- 1 min)",
            f"  Egress        {tl['egress']}",
            "", "Join the package at MSHL. Other flights are already airborne and holding. Push on time, expect no formation forming."]
    if pkg.joint:
        exe += ["", "This is a joint Navy / Air Force package. Navy flights recover aboard the carrier; Air Force flights recover at their own fields."]
    adm = ["Fuel: take what you need from the tanker (TKR). AI flights have unlimited fuel; you do not.",
           "Recovery: " + ("carrier Case I, TACAN 74X, ICLS 11" if spec.home.value == "CARRIER" else "your home field, tower on COMM1 CH1"),
           f"Divert: {'Kobuleti / Batumi (land)' if spec.home.value == 'CARRIER' else 'Kutaisi / Senaki'}"]
    com = ["COMM1 (UHF): " + " | ".join(f"CH{c} {e.label} {e.mhz:.3f}" for c, e in plan.comm1.items()),
           "COMM2 (VHF): " + " | ".join(f"CH{c} {e.label} {e.mhz:.3f}" for c, e in plan.comm2.items())]
    if pkg.jtac:
        com.append(f"JTAC on COMM1 CH4. Laser code {pkg.jtac_laser_code}.")
    text = {"situation": "\n".join(sit), "mission": "\n".join(mis), "execution": "\n".join(exe),
            "admin": "\n".join(adm), "comms": "\n".join(com), "threats": threats}
    text["full"] = (f"1. SITUATION\n{text['situation']}\n\n2. MISSION\n{text['mission']}\n\n3. EXECUTION\n{text['execution']}"
                    f"\n\n4. ADMINISTRATION AND LOGISTICS\n{text['admin']}\n\n5. COMMAND AND SIGNAL\n{text['comms']}")
    text["blue_task"] = f"{text['mission']}\n\nPUSH {tl['push']}   TOT {tl['tot']}"
    return text
