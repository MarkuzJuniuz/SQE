"""All the words: campaign phases, situation reports, briefings and debrief flavor.
Hand-written templates (no runtime AI). Add variants to any list to widen the pool."""
from __future__ import annotations
import random
from .models import ObjectiveType
from . import theatres

def __getattr__(name):
    """TITLE comes from the active theatre pack (so `narrative.TITLE` keeps working)."""
    if name == "TITLE":
        from . import theatres
        return theatres.active()[name.lower()]
    raise AttributeError(name)


def phase(state) -> tuple:
    """v0.41.148: the campaign posture (it replaced the three phases, which were driven by jet counts and the old tiers). -> (number, label, text)."""
    from . import posture
    lab, text = posture.posture(state)
    order = list(posture.LABELS) + [posture.ENDINGS[1], posture.ENDINGS[2], "Defeat"]
    return (order.index(lab) + 1 if lab in order else 0), lab, text


def sitrep(state) -> list:
    """The situation lines of the briefing: the front, warnings, supply and air defence (no aircraft counts since v0.41.148)."""
    from . import posture
    return posture.sitrep(state)


_INTENT = {
    ObjectiveType.STRIKE: [
        "The offensive lives on what {site} supplies. Cut it and the front starves.",
        "Intel puts {site} at the heart of the enemy's sustainment. Make it burn.",
        "{site} keeps their columns moving. Every hour it stands costs us on the ground.",
        "Strike {site} hard and fast. Command wants it out of the war before the next wave.",
        "Reconnaissance shows {site} fully operational. Today is the day that changes.",
        "{site} is on the list because it matters. Put your weapons on it and bring everyone home.",
        "Their logistics run through {site}. Break it and the offensive stutters.",
        "Priority target: {site}. Command is counting on a clean hit.",
    ],
    ObjectiveType.DEAD: [
        "{site} is a thorn in every package's side. SEAD blinds it; the DEAD flight right behind must finish it.",
        "Until {site} is dead our strikers pay a toll. Blinding it is not enough: the launchers have to burn.",
        "{site} has been swatting at everything we send north. Take it off the board.",
        "Intel has {site} on alert and ready. SEAD goes in first; DEAD follows through the hole they open.",
        "The air-defence network leans on {site}. Kill it and the corridor opens for every package behind you.",
        "Expect {site} to track you early. Use your standoff and your timing; the launchers are the prize.",
        "{site} anchors the local air defences. Make it quiet, then make it permanent.",
        "Command wants {site} gone today. SEAD blinds, DEAD destroys, nobody lingers.",
    ],
    ObjectiveType.COUNTER_AIR: [
        "Their fighters at {site} are sheltered and rested. Make them fight or make them burn on the ramp.",
        "Hit the air regiment at {site} while it is still on the ground. Air control starts here.",
        "{site} is where their fighter wing lives. Crater the ramp and the sorties stop.",
        "Every jet destroyed at {site} is one we will not meet over the fleet tomorrow.",
        "Intel shows {site} loaded and fuelled. Hit it before it launches.",
        "Take {site} out of the fight. What cannot launch cannot kill us.",
    ],
    ObjectiveType.BARCAP: [
        "The fleet is the center of gravity. Nothing gets through to the carrier.",
        "Hold the line over the task force and kill anything that approaches.",
        "{site} is what everything else depends on. Keep the picture clean and the airspace ours.",
        "Stay sharp on station. The enemy wants {site} and will probe for a gap.",
        "Patrol the approaches to {site}. Anything unidentified is hostile until proven otherwise.",
        "A quiet patrol is a good patrol, but be ready. They only need one gap at {site}.",
    ],
    ObjectiveType.FLEET_DEFENSE: [
        "Backfires are inbound with anti-ship missiles. The fleet is counting on you to kill them before they launch.",
        "Intelligence has the bombers in the air. Stop the raid at long range; the missiles are the real threat.",
        "A raid is heading for {site}. Intercept early and keep the shooters outside missile range.",
        "Radar has the Backfires tracking toward {site}. Every bomber that reaches launch range is a missile in the air.",
        "Kill the shooters, not the missiles. Hit the raid before it turns on {site}.",
        "The low threats are the fleet's blind spot, so the intercept is on you. Hold the raid away from {site}.",
    ],
    "RAID_DEFENSE": [                   # v0.41.394: a red bomber raid on a field, supply site, garrison or our troops (`extra["land"]`): free-fall bombs, no ships in it
        "Red bombers are inbound for {site}. Stop them before they reach their bomb release.",
        "Intelligence has a raid in the air against {site}. Intercept early: every bomber that gets through drops on us.",
        "Radar has bombers tracking toward {site}. Kill them on the way in, before they roll in on the target.",
        "A raid is heading for {site}. Hold it away from the target: the bombers first, any escort second.",
        "They want {site} hit today. Meet the raid short of the target and do not let it through.",
        "The bombers are committed against {site}. Every one you stop is a bomb that does not fall.",
    ],
    ObjectiveType.CAS: [
        "Ground forces are under pressure from {site}. Break it before it breaks us.",
        "Friendly troops are in contact. Your JTAC is waiting. Find {site} and destroy it.",
        "Our troops cannot take {site} without you. Check in with the JTAC and clear the way.",
        "{site} is the only thing between our line and the next objective. Hit it hard and early.",
        "Our task force needs air now. Your JTAC will talk you onto {site}.",
        "Hold the line on the ground by breaking {site}. Call the JTAC and work the target.",
    ],
}
_COMMANDERS = ["Capt. Reyes (Air Wing)", "Col. Hale (Air Component)", "Cdr. Ito (CAG)", "Col. Brandt (Ops)",
               "Maj. Gen. Whitlow (Air Component)", "Capt. Duarte (Strike Ops)", "Cdr. Nakamura (Air Boss)", "Lt. Col. Sorensen (Ops)"]
_INTEL = ["Maj. Okafor (Intel)", "Lt. Cdr. Vance (Intel)", "Capt. Lindqvist (Intel)", "Lt. Hargrove (Intel)", "Maj. Delacroix (Intel)", "Capt. Mbeki (Intel)"]


def commander_intent(obj_type, rng: random.Random | None = None, n: int | None = None, site: str = "", pkg_no: int = 0, day: int = 0) -> str:
    """One line of commander's intent plus a signature.
    n = how many packages of the same objective type come before this one in the day's tasking order: consecutive packages walk through the pool,
    so two on the same screen never get the same line (the day rotates where the walk starts). With no n it falls back to a random pick."""
    pool = _INTENT[obj_type]
    site = site or "the target"
    if n is None:
        line, who = (rng or random).choice(pool), (rng or random).choice(_COMMANDERS)
    else:
        line, who = pool[(day * 3 + n) % len(pool)], _COMMANDERS[(day * 5 + pkg_no) % len(_COMMANDERS)]
    return line.format(site=site) + f"  -- {who}"


def site_name(state, obj) -> str:
    try:
        a = state.assets.get(obj.target_id) or state.bases.get(obj.target_id)
        return a.name if a is not None else ""
    except Exception:
        return ""


def setpiece_text(state, pkg, yours: bool, aircraft: str = "") -> list:
    """v0.41.107: the carrier raid setpiece, in universe. -> paragraphs for the right-hand pane. `yours`: a flight in the list is one you can fly."""
    ex = pkg.extra
    bomb, esc = ex.get("bombers", 0), ex.get("escorts", 0)
    cv = state.bases.get(pkg.objective.target_id)
    site = cv.name if cv is not None else "the task force"
    first = (f"Radar and the E-2 have a raid forming up out of Mozdok: {bomb} Backfires with {esc} Flankers on their wing, bearing {ex.get('brg', 0):.0f} degrees onto {site}. "
             f"Every fighter that can reach the task force is being launched to meet it.")
    if yours:
        return [first, "Kill the bombers before they reach launch range, then the escorts. One of these flights is yours; the others fly with you."]
    return [first, f"Several fighter groups from the carrier and the land bases are on high alert to defend {site}. There is no job on this order for {aircraft or 'your aircraft'}.",
            "Press Skip Turn and the war simulation settles the raid and the day moves on."]


def intent_for(state, pkg) -> str:
    """The intent line for a package, stable for the day and varied across the tasking order (see commander_intent)."""
    typ = pkg.objective.type
    if typ == ObjectiveType.COUNTER_AIR and pkg.objective.aim == "SWEEP":         # a Fighter Sweep: its own lines
        n = sum(1 for d in state.plan if d["number"] < pkg.number and d["objective"].get("aim") == "SWEEP")
        line = _SWEEP_INTENT[(state.day * 3 + n) % len(_SWEEP_INTENT)]
        return line.format(site=site_name(state, pkg.objective) or "the target") + f"  -- {_COMMANDERS[(state.day * 5 + pkg.number) % len(_COMMANDERS)]}"
    n = sum(1 for d in state.plan if d["number"] < pkg.number and d["objective"]["type"] == typ.value)
    if typ == ObjectiveType.FLEET_DEFENSE and (pkg.extra or {}).get("land"):         # v0.41.394: a land raid has its own lines, naming what is attacked (the title's text), not the fleet
        what = pkg.objective.description.replace("Intercept a raid on ", "").replace("Intercept an air attack on ", "").replace("friendly troops: ", "our troops at ")
        return commander_intent("RAID_DEFENSE", None, n, what or site_name(state, pkg.objective), pkg.number, state.day)
    return commander_intent(typ, None, n, site_name(state, pkg.objective), pkg.number, state.day)


_SWEEP_INTENT = [
    "Intel expects more fighters over {site} than the strike packages can carry. Get there first and make the sky ours.",
    "Clear the air over {site} before the bombers arrive. Shoot from range; nobody chases into their SAMs.",
    "Their fighters will be waiting near {site}. Be waiting for them.",
    "Every bandit you take off the board over {site} is one the strikers never see.",
]


def intel_officer(rng) -> str:
    return rng.choice(_INTEL)


# ---------------- debrief flavor ---------------------------------------------------------------------------------
_OPEN = {
    "great": ["A textbook mission.", "Clean work from start to finish.", "That is how it is supposed to go."],
    "good": ["The package got the job done.", "Not pretty everywhere, but effective.", "A solid result."],
    "mixed": ["A mixed day.", "Some of it worked, some of it did not.", "Progress, but at a price."],
    "bad": ["That did not go to plan.", "A hard day for the task force.", "The enemy had a say today."],
}
_LOSS = {0: ["Everyone came home.", "No losses to report.", "All aircraft recovered."],
         1: ["We lost one aircraft.", "One airframe did not make it back.", "A single loss, and it will be felt."],
         2: ["Two aircraft were lost.", "The wing is down two airframes tonight."]}
_PLAYER = {"recovered": [""],                         # v0.41.414 (XO): nothing is said when you landed
           "ejected": ["You ejected and are being recovered.", "You punched out. Search-and-rescue is on the way."],
           "lost": ["Your aircraft was lost. The squadron will write to your family if you are not found.",
                    "You did not return."],
           "airborne": [""]}
_FOLLOW = {"great": ["Command wants more of the same tomorrow.", "The enemy will feel this for days."],
           "good": ["The picture is improving.", "It was enough. Rest, and get ready for tomorrow."],
           "mixed": ["Intel will reassess before the next tasking.", "We take the gain and plan around the cost."],
           "bad": ["Command will rethink the approach.", "Get some rest. We will try again."]}


def debrief_story(outcome: dict, state, rng: random.Random) -> str:
    """outcome: success(bool/None), target_pct (0..1 damage), blue_air_lost, red_air_lost, player ('recovered'|...)."""
    lost = outcome.get("blue_air_lost", 0)
    dmg = outcome.get("target_damage", 0.0)
    if outcome.get("objective_type") in (ObjectiveType.BARCAP.value, ObjectiveType.FLEET_DEFENSE.value):
        score = 2 if outcome.get("red_air_lost", 0) >= 1 else 1
    else:
        score = 2 if dmg >= 0.6 else 1 if dmg >= 0.25 else 0
    score = score - (1 if lost >= 2 else 0)
    tone = "great" if score >= 2 and lost == 0 else "good" if score >= 1 and lost <= 1 else "mixed" if score >= 1 or lost == 0 else "bad"
    parts = [rng.choice(_OPEN[tone])]
    obj = outcome.get("objective", "the objective")
    if outcome.get("objective_type") in (ObjectiveType.BARCAP.value, ObjectiveType.FLEET_DEFENSE.value):
        k = outcome.get("red_air_lost", 0)
        parts.append(f"The {'intercept' if outcome.get('land_raid') else 'patrol over the fleet'} {'splashed ' + str(k) + ' hostile aircraft' if k else 'saw no engagement'}.")
    elif outcome.get("runway"):                          # S75: a runway job is told by the crater, not by a damage percent
        rw = outcome["runway"]
        if rw.get("closed"):
            parts.append(f"{obj}: the runway is cratered and the field is shut for some time.")
        elif rw.get("hits"):
            parts.append(f"{obj}: the runway was hit, but not enough to close the field; the crews will have it repaired overnight.")
        else:
            parts.append(f"{obj}: the runway was not hit.")
    elif any(a.get("primary") and a.get("suppressed") and not a.get("destroyed") for a in outcome.get("red_assets") or []):
        parts.append(f"{obj}: the site's radars are out; it is suppressed.")
    else:
        parts.append(f"{obj}: damage assessment puts the target at {dmg:.0%} destroyed.")
    if outcome.get("red_air_lost") and outcome.get("objective_type") not in (ObjectiveType.BARCAP.value, ObjectiveType.FLEET_DEFENSE.value):
        parts.append(f"{outcome['red_air_lost']} enemy aircraft were also destroyed.")
    parts.append(rng.choice(_LOSS[min(lost, 2)]) if lost < 3 else f"The package lost {lost} aircraft.")
    pl = rng.choice(_PLAYER.get(outcome.get("player", "recovered"), _PLAYER["recovered"]))
    if pl:                                              # nothing is said when you landed or were still airborne
        parts.append(pl)
    parts.append(rng.choice(_FOLLOW[tone]))
    return "  ".join(parts) + f"\n\n-- {intel_officer(rng)}"
