"""Briefing text (SMEAC) and threat summary."""
from __future__ import annotations
import random
from . import narrative, credit_line
from .aircraft import AIRCRAFT
from .models import AssetKind
from .routes import dist, NM
from .war import totals

_SAM_NAME = {"SA-8": "SA-8 Gecko", "AAA": "AAA", "MANPAD": "MANPADS", "SA-2": "SA-2 Guideline", "SA-3": "SA-3 Goa", "SA-6": "SA-6 Gainful",
             "SA-11": "SA-11 Gadfly", "SA-10": "SA-10 Grumble", "SA-15": "SA-15 Gauntlet", "SA-19": "SA-19 Grison"}
RANGE_NM = {"SA-8": 7, "AAA": 3, "MANPAD": 3, "SA-2": 25, "SA-3": 13, "SA-6": 13, "SA-11": 18, "SA-10": 48, "SA-15": 8, "SA-19": 5}


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
           f"Commander's intent: {narrative.intent_for(state, pkg)}"]
    if threats:
        sit += ["", "Threats near the target:"] + [f"  - {s}" for s in threats]
    if obj.type.value == "FLEET_DEFENSE" and pkg.extra:
        e = pkg.extra
        tb = state.bases.get(obj.target_id)
        rtype = {"Su_24M": "Su-24M bombers", "Su_25": "Su-25 attack aircraft"}.get(e.get("raider", "Su_24M"), "attack aircraft")
        what = obj.description.replace("Intercept a raid on ", "").replace("Intercept an air attack on ", "") if e.get("aim") else (tb.name if tb else "our airfield")
        sit += ["", (f"Intelligence reports {e['bombers']} {rtype} with free-fall bombs inbound toward {what}, "
                     f"approaching from a bearing of about {e['brg']:.0f} degrees." if e.get("land") else
                     f"Intelligence reports {e['bombers']} Tu-22M3 bombers armed with anti-ship missiles inbound toward the fleet, "
                     f"approaching on a bearing of about {e['brg']:.0f} degrees from the carrier.")
                    + (f" They are escorted by {e['escorts']} fighters." if e.get("escorts") else
                       (" They have no escort." if e.get("land") else " They have no escort: the enemy cannot reach this far with fighters. It is a last throw of the dice."))]
    n_def = x.get("n_def", pkg.n_def)
    inc = (" (counting the packages flown with this one: " + ", ".join(f"#{n}" for n in x["merged_nums"]) + ")") if x.get("merged_nums") else ""
    sit += ["", (f"Expect about {n_def} hostile fighters to contest the target{inc}; command is committing enough fighters to answer them."
                 if n_def and obj.type.value != "FLEET_DEFENSE" else
                 ("" if obj.type.value == "FLEET_DEFENSE" else "No organised fighter defence is expected at the target.")),
            f"Weather: {x['weather']}." + ((" Loadouts changed for the weather: " + " ".join(x["wx_notes"])) if x.get("wx_notes") else "")]
    if obj.type.value == "DEAD" and obj.aim == "DEAD":
        sit += ["", "A SEAD package goes in ahead of you to blind this site's radars. If any search or track radar is still up when you reach the gate, "
                    "you hold outside the threat and re-check. AWACS calls hold, go, or RTB. You break off and RTB on a timeout, on low fuel, "
                    "or when every SEAD flight on the site is down or gone."]
    elif obj.type.value == "DEAD" and obj.aim == "SEAD":
        from .difficulty import get as _gd2
        from .war import WarSimulator as _WS, sead_fail as _sf
        _p = _WS(_gd2(state.level)).sead_p(state, pkg)
        from .war import DEAD_STAGE_GAP_MIN as _gap
        if getattr(pf, "kit", "") == "JSOW":
            sit += ["", "You are the JSOW slingers. You push with the HARM shooters and come in on your own axis, about 30 degrees off theirs, so the "
                        "site has two directions to watch. The HARMs go first; release your AGM-154As on the radars' last-known positions from stand-off "
                        "range. A radar that keeps tracking is the HARMs' kill; one that shuts down to dodge them is still where it was last seen, and "
                        "that is where your JSOWs land."]
        sit += ["", f"Your job is only to blind the radars. A DEAD package follows about {_gap} minutes behind you and goes in only if the radars are out. "
                    f"Intelligence puts the chance of blinding this site at about {round(_p * 100 / 5) * 5:.0f}%" + (f", better than it was: this site has beaten us {_sf(state, obj.target_id)} time{'s' if _sf(state, obj.target_id) != 1 else ''} running and its crews and positions are known." if _sf(state, obj.target_id) else ".")]
    if x.get("intel"):
        sit += ["", "Intelligence: " + " ".join(x["intel"])]
    mis = [f"{obj.description}.", f"You are {pf.callsign}-1, lead of {pf.count}x {spec.display}, tasked as {'JSOW' if getattr(pf, 'kit', '') == 'JSOW' else ('DEAD' if (pf.role.value == 'STRIKE' and obj.type.value == 'DEAD') else pf.role.value)}.", f"Your task: {pf.task}."]
    exe = ["Package (push / TOT are staggered: sweep first, then SEAD, escorts, strikers):"]
    for r in x["pkg_table"]:
        f = next(ff for ff in pkg.flights if ff.callsign == r["callsign"])
        exe.append(f"  {f.callsign:<14} {f.count}x {AIRCRAFT[f.aircraft].display:<16} {r['role']:<8} push {r['push']}   TOT {r['tot']}" + ("   <- YOU" if f.is_player else ""))
    exe += ["", "Your timeline (local):", f"  Launch    {tl['launch']}", f"  Marshal   {tl['marshal']}   hold at MSHL, flights stacked 1,000 ft apart",
            f"  PUSH      {tl['push']}   +/- 30 s", f"  TOT       {tl['tot']}   +/- 1 min", f"  Egress    {tl['egress']}", f"  RTB       {tl['rtb']}", "",
            "The rest of the package is airborne and holding at MSHL. Each flight pushes on its own time; be there."]
    if pkg.joint:
        exe += ["", "Joint package. Navy flights recover aboard the carrier; Air Force flights recover at their own fields."]
    if spec.fc3:           # FC3 radios have no channels: say the frequency
        tower, jtac_at = f"ATC {plan.freq('ATC'):.3f}", None
    else:
        tower, jtac_at = "ATC COMM1 CH1", "COMM1 CH4"
    adm = [f"BINGO {x['bingo']} lb   JOKER {x['joker']} lb",
           "Recovery: " + (f"carrier Case I, TACAN 74X, ICLS 11, {tower}" if spec.home.value == "CARRIER" else f"home field, tower {tower.replace('ATC ', 'on ')}"),
           f"Divert: {x['divert']}", "Tanker track is steerpoint TKR. Bullseye is the last steerpoint."]
    if spec.fc3:
        com = ["Frequencies: " + " | ".join(f"{e.label} {e.mhz:.3f}" for e in list(plan.comm1.values()) + list(plan.comm2.values()))]
    else:
        com = ["COMM1 (UHF): " + " | ".join(f"CH{c} {e.label} {e.mhz:.3f}" for c, e in plan.comm1.items()),
               "COMM2 (VHF): " + " | ".join(f"CH{c} {e.label} {e.mhz:.3f}" for c, e in plan.comm2.items())]
    com += [f"IFF Mode 3: {x['mode3']}    Laser code: {x['laser']}", f"Bullseye: {x['bullseye']}"]
    if x.get("link16"):
        com.append("Package aircraft share a datalink; the AWACS feeds it. Station numbers (STN) are on your kneeboard.")
    if pkg.jtac:
        if jtac_at is None:
            jtac_at = f"{plan.freq('JTAC'):.3f}" if any(e.label == "JTAC" for e in plan.comm1.values()) else "its briefed frequency"
        com.append(f"JTAC (Axeman) is with our troops in contact, on {jtac_at}. Laser code {pkg.jtac_laser_code}.")
    text = {"situation": "\n".join(sit), "mission": "\n".join(mis), "execution": "\n".join(exe),
            "admin": "\n".join(adm), "comms": "\n".join(com), "threats": threats}
    text["full"] = (f"1. SITUATION\n{text['situation']}\n\n2. MISSION\n{text['mission']}\n\n3. EXECUTION\n{text['execution']}"
                    f"\n\n4. ADMINISTRATION AND LOGISTICS\n{text['admin']}\n\n5. COMMAND AND SIGNAL\n{text['comms']}\n\n{credit_line()}")
    text["blue_task"] = f"{text['mission']}\n\nPUSH {tl['push']}   TOT {tl['tot']}"
    return text
