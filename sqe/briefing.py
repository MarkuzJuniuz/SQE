"""Briefing text (SMEAC) and threat summary."""
from __future__ import annotations
import random
from . import narrative
from .aircraft import AIRCRAFT
from .models import AssetKind
from .routes import dist, NM
from .war import totals

_SAM_NAME = {"AAA": "AAA", "MANPAD": "MANPADS", "SA-2": "SA-2 Guideline", "SA-3": "SA-3 Goa", "SA-6": "SA-6 Gainful",
             "SA-11": "SA-11 Gadfly", "SA-10": "SA-10 Grumble", "SA-15": "SA-15 Gauntlet", "SA-19": "SA-19 Grison"}
RANGE_NM = {"AAA": 3, "MANPAD": 3, "SA-2": 25, "SA-3": 13, "SA-6": 13, "SA-11": 18, "SA-10": 48, "SA-15": 8, "SA-19": 5}


def threat_lines(state, tx, ty) -> list:
    out = []
    for a in state.assets.values():
        if a.kind not in (AssetKind.SAM, AssetKind.EWR) or a.destroyed:
            continue
        d = dist(a.x, a.y, tx, ty) / NM
        if d <= 60:
            nm = _SAM_NAME.get(a.variant, "Early-warning radar")
            rng = RANGE_NM.get(a.variant)
            out.append((d, f"{nm}{f' (~{rng} nm)' if rng else ''}, {d:.0f} nm from target"))
    out.sort()
    return [t for _, t in out[:8]]


def build_text(state, pkg, tl: dict, plan, rng: random.Random, tgt_xy, x: dict) -> dict:
    """x: date, whois, mode3, laser, bingo, joker, bullseye, divert, weather, link16(bool)."""
    pf = pkg.player_flight
    spec = AIRCRAFT[pf.aircraft]
    n, pname, ptext = narrative.phase(state)
    obj = pkg.objective
    threats = threat_lines(state, *tgt_xy)
    t = totals(state)
    sit = [f"{x['date']}. {narrative.TITLE}, day {state.day}. {pname}.", "", ptext, "", *narrative.sitrep(state), "",
           f"Commander's intent: {narrative.commander_intent(obj.type, rng)}"]
    if threats:
        sit += ["", "Threats near the target:"] + [f"  - {s}" for s in threats]
    sit += ["", (f"Expect about {pkg.n_def} hostile fighters to contest the target; the package is sized to answer them."
                 if pkg.n_def else "No organised fighter defence is expected at the target."),
            f"Weather: {x['weather']}."]
    mis = [f"{obj.description}.", f"You are {pf.callsign}-1, lead of {pf.count}x {spec.display}, tasked as {pf.role.value}."]
    exe = ["Package:"]
    for f in pkg.flights:
        exe.append(f"  {f.callsign}: {f.count}x {AIRCRAFT[f.aircraft].display}, {f.task}" + ("   <- YOU" if f.is_player else ""))
    exe += ["", "Timeline (local):", f"  Launch    {tl['launch']}", f"  Marshal   {tl['marshal']}   hold at MSHL, flights stacked 1,000 ft apart",
            f"  PUSH      {tl['push']}   other flights leave MSHL on this time whether or not you are there", f"  TOT       {tl['tot']}",
            f"  Egress    {tl['egress']}", f"  RTB       {tl['rtb']}", "",
            "Other flights are already airborne and holding at MSHL. There is no radio signal to push: the clock is the signal."]
    if pkg.joint:
        exe += ["", "Joint package. Navy flights recover aboard the carrier; Air Force flights recover at their own fields."]
    adm = [f"BINGO {x['bingo']} lb   JOKER {x['joker']} lb  (starting estimates, tune in aircraft.py)",
           "Recovery: " + ("carrier Case I, TACAN 74X, ICLS 11, ATC COMM1 CH1" if spec.home.value == "CARRIER" else "home field, tower on COMM1 CH1"),
           f"Divert: {x['divert']}", "AI flights have unlimited fuel; you do not. Tanker is steerpoint TKR."]
    com = ["COMM1 (UHF): " + " | ".join(f"CH{c} {e.label} {e.mhz:.3f}" for c, e in plan.comm1.items()),
           "COMM2 (VHF): " + " | ".join(f"CH{c} {e.label} {e.mhz:.3f}" for c, e in plan.comm2.items()),
           f"IFF Mode 3: {x['mode3']}    Laser code: {x['laser']}", f"Bullseye: {x['bullseye']}"]
    if x.get("link16"):
        com.append("Package flights are networked (Link 16 / SADL); the AWACS is a donor where the jet supports it. STNs are on the kneeboard.")
    if pkg.jtac:
        com.append(f"JTAC on COMM1 CH4. Laser code {pkg.jtac_laser_code}.")
    text = {"situation": "\n".join(sit), "mission": "\n".join(mis), "execution": "\n".join(exe),
            "admin": "\n".join(adm), "comms": "\n".join(com), "threats": threats}
    text["full"] = (f"1. SITUATION\n{text['situation']}\n\n2. MISSION\n{text['mission']}\n\n3. EXECUTION\n{text['execution']}"
                    f"\n\n4. ADMINISTRATION AND LOGISTICS\n{text['admin']}\n\n5. COMMAND AND SIGNAL\n{text['comms']}")
    text["blue_task"] = f"{text['mission']}\n\nPUSH {tl['push']}   TOT {tl['tot']}"
    return text
