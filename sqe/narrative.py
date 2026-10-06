"""All the words: the conflict background, campaign phases, situation reports, briefings and debrief flavor.
Hand-written templates (no runtime AI). Add variants to any list to widen the pool."""
from __future__ import annotations
import random
from .models import ObjectiveType
from .war import totals

TITLE = "Operation IRON TIDE"

BACKGROUND = (
    "After months of border incidents and a collapsed ceasefire, the Northern Federation's Southern Military "
    "District crossed the frontier in force. Its armored columns are pushing south along the Black Sea coast "
    "toward the Georgian airbase at Senaki, supported by air regiments at Sukhumi, Gudauta, Sochi and across the "
    "Kuban, and covered by a layered air-defence network.\n\n"
    "A coalition task force has answered the request for assistance. The USS Stennis carrier air wing operates "
    "from the eastern Black Sea; U.S. Air Force squadrons operate from Senaki, Kutaisi and Kobuleti. You fly with "
    "the Navy's Tomcat community or with the Air Force, as part of a joint air campaign.\n\n"
    "Coalition command's intent is plain: stop the armored advance, win control of the air, take the enemy "
    "air-defence network apart, and then strike the headquarters and logistics that keep the offensive moving. "
    "Every day the war is planned; every day the packages go out. Yours is the one you fly yourself."
)

PHASES = [
    ("Phase 1 - Stop the Advance and Contest the Air",
     "The first priority is to halt the armored columns and keep the Federation's fighters off our airfields and "
     "the fleet. Close air support, counter-air strikes and a standing combat air patrol over the carrier.",
     lambda t: t["enemy_air"] < 0.6 or t["armor"] < 0.45),
    ("Phase 2 - Roll Back the Air Defences",
     "With the advance checked, the task force turns on the SAM and early-warning network. Every site destroyed "
     "makes the next package cheaper. Suppress, destroy, and keep the pressure on.",
     lambda t: t["iads"] < 0.45),
    ("Phase 3 - Break the Machine",
     "The air defences are in tatters. Now hit what the offensive runs on: command posts, fuel and ammunition. "
     "Finish the enemy air arm on the ground and in the air.",
     lambda t: False),
]


def phase(state) -> tuple:
    t = totals(state)
    for i, (name, text, done) in enumerate(PHASES, 1):
        if not done(t):
            return i, name, text
    return len(PHASES), PHASES[-1][0], PHASES[-1][1]


def sitrep(state) -> list:
    t = totals(state)
    lines = [f"Enemy air arm: {t['ea']} of {t['ez']} aircraft serviceable ({t['enemy_air']:.0%}).",
             f"Air-defence network: {t['iads']:.0%} of sites operational.",
             f"Armored advance: columns at {t['armor']:.0%} strength.",
             f"Enemy command posts: {t['c2']:.0%} intact.",
             f"Coalition air component: {t['fa']} of {t['fz']} aircraft serviceable ({t['friendly_air']:.0%})."]
    return lines


_INTENT = {
    ObjectiveType.STRIKE: ["The offensive lives on what this site supplies. Cut it and the front starves.",
                           "Intel puts this target at the heart of the enemy's sustainment. Make it burn."],
    ObjectiveType.DEAD: ["This site is a thorn in every package's side. Take it out and the corridor opens.",
                         "Until this battery is silenced, our strikers pay a toll. Remove it."],
    ObjectiveType.COUNTER_AIR: ["Their fighters are sheltered and rested. Make them fight or make them burn on the ramp.",
                                "Hit the air regiment while it is still on the ground. Air control starts here."],
    ObjectiveType.BARCAP: ["The fleet is the center of gravity. Nothing gets through to the carrier.",
                           "Hold the line over the task force and kill anything that approaches."],
    ObjectiveType.FLEET_DEFENSE: ["Backfires are inbound with anti-ship missiles. The fleet is counting on you to kill them before they launch.",
                                  "Intelligence has the bombers in the air. Stop the raid at long range; the missiles are the real threat."],
    ObjectiveType.CAS: ["Ground forces are under pressure. The column must be stopped before it reaches the airbase.",
                        "Friendly troops are in contact. Your JTAC is waiting. Find the armor and destroy it."],
}
_COMMANDERS = ["Capt. Reyes (Air Wing)", "Col. Hale (Air Component)", "Cdr. Ito (CAG)", "Col. Brandt (Ops)"]
_INTEL = ["Maj. Okafor (Intel)", "Lt. Cdr. Vance (Intel)", "Capt. Lindqvist (Intel)"]


def commander_intent(obj_type, rng: random.Random) -> str:
    return rng.choice(_INTENT[obj_type]) + f"  -- {rng.choice(_COMMANDERS)}"


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
_PLAYER = {"recovered": ["You brought your jet home.", "You recovered safely."],
           "ejected": ["You ejected and are being recovered.", "You punched out. Search-and-rescue is on the way."],
           "lost": ["Your aircraft was lost. The squadron will write to your family if you are not found.",
                    "You did not return."],
           "airborne": ["You were still airborne when the sortie was closed out."]}
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
        parts.append(f"The patrol over the fleet {'splashed ' + str(k) + ' hostile aircraft' if k else 'saw no engagement'}.")
    else:
        parts.append(f"{obj}: damage assessment puts the target at {dmg:.0%} destroyed.")
    if outcome.get("red_air_lost") and outcome.get("objective_type") not in (ObjectiveType.BARCAP.value, ObjectiveType.FLEET_DEFENSE.value):
        parts.append(f"{outcome['red_air_lost']} enemy aircraft were also destroyed.")
    parts.append(rng.choice(_LOSS[min(lost, 2)]) if lost < 3 else f"The package lost {lost} aircraft.")
    parts.append(rng.choice(_PLAYER.get(outcome.get("player", "recovered"), _PLAYER["recovered"])))
    parts.append(rng.choice(_FOLLOW[tone]))
    return "  ".join(parts) + f"\n\n-- {intel_officer(rng)}"
