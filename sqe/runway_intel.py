"""S181 P4 (XO 2026-11-24): the red intelligence banner for runway raids, in the same strip as the carrier-raid banner (`bombers.intel`).

It shows (a) when a SEEN red raid in this turn's plan goes for the runway of the player's field or of the E-3's field ("imminent"), and (b) while such a runway is cut,
with what that costs in plain words: your field closed (the reason you cannot fly from it), or no AWACS (and whether one is still up). An unseen raid shows nothing.
Same shape as `bombers.intel`: {"head", "text", "sub", "pills", "log"} or None.
"""
from __future__ import annotations

from . import detection, runways, support_assets
from .packages import Package


def _player_field_id(state) -> str:
    squadron = state.squadrons.get(state.player.squadron_id)
    if squadron is None:
        return ""
    return squadron.base_id


def _field_name(state, field_id: str) -> str:
    base = state.bases.get(field_id)
    if base is None:
        return "The field"
    return base.name


def _hours_text(state, field_id: str) -> str:
    hours = runways.hours_left(state, field_id)
    if hours <= 0:
        return "until it is repaired"
    if hours == 1:
        return "for about 1 more hour"
    return "for about %d more hours" % hours


def _e3_up_now(state) -> bool:
    """Is an E-3 on orbit at some time in this turn (one that took off before the runway was cut finishes its shift)?"""
    return detection._on_orbit(state, "bl_e3", state.turn)


def _raids_on(state, field_ids: set) -> list:
    """This turn's seen red raids on the runway of one of these fields -> [field id], in plan order."""
    out = []
    for data in state.plan or []:
        package = Package.from_dict(data)
        if package.extra.get("past") or package.extra.get("unseen_raid"):
            continue
        if not detection.is_raid(state, package):
            continue
        if package.objective.aim:
            continue
        if package.objective.target_id in field_ids and package.objective.target_id not in out:
            out.append(package.objective.target_id)
    return out


def intel(state) -> dict | None:
    if state.status != "ACTIVE":
        return None
    home_id = _player_field_id(state)
    e3 = support_assets.ensure(state).get("bl_e3")
    e3_field_id = ""
    if e3 is not None and int(e3.get("available", 0)) > 0:
        e3_field_id = e3.get("base_id", "")
    # (b) a cut runway that is still closed comes first: it is what stops the player now
    if home_id and runways.is_closed(state, home_id):
        name = _field_name(state, home_id)
        text = "%s's runway is cut. That is why we cannot fly from it: it stays closed %s." % (name, _hours_text(state, home_id))
        sub = "Missions are flown from other fields until it is repaired."
        if home_id == e3_field_id:
            sub = "The E-3 flies from here too: no AWACS can take off, and raids beyond the carrier's E-2C may come unseen. " + sub
        return {"head": "INTELLIGENCE · YOUR FIELD IS CLOSED", "text": text, "sub": sub, "pills": ["Runway cut", name], "log": "INTELLIGENCE: " + text + " " + sub}
    if e3_field_id and runways.is_closed(state, e3_field_id):
        name = _field_name(state, e3_field_id)
        text = "%s's runway is cut: no E-3 can take off %s." % (name, _hours_text(state, e3_field_id))
        if _e3_up_now(state):
            sub = "The E-3 already on station finishes its shift. After that, raids beyond the carrier's E-2C may come unseen."
            pill = "E-3 finishing its shift"
        else:
            sub = "No E-3 is up: raids beyond the carrier's E-2C may come unseen, and you will not be sent to meet them."
            pill = "No AWACS"
        return {"head": "INTELLIGENCE · NO AWACS", "text": text, "sub": sub, "pills": ["Runway cut", pill], "log": "INTELLIGENCE: " + text + " " + sub}
    # (a) a seen raid on one of those runways in this turn's plan
    wanted = set()
    if home_id:
        wanted.add(home_id)
    if e3_field_id:
        wanted.add(e3_field_id)
    targets = _raids_on(state, wanted)
    if not targets:
        return None
    field_id = targets[0]
    name = _field_name(state, field_id)
    if field_id == home_id:
        text = "A red raid is expected on %s's runway, your own field, this turn." % name
        sub = "If it is cut, nobody flies from %s until it is repaired." % name
        if field_id == e3_field_id:
            sub = "The E-3 flies from here too. " + sub
        pills = ["Raid expected", "Your field"]
    else:
        text = "A red raid is expected on %s's runway, where the E-3 flies from, this turn." % name
        sub = "If it is cut, no E-3 can take off until it is repaired, and raids beyond the carrier's E-2C may come unseen."
        pills = ["Raid expected", "AWACS field"]
    return {"head": "INTELLIGENCE · RUNWAY RAID EXPECTED", "text": text, "sub": sub, "pills": pills, "log": "INTELLIGENCE: " + text + " " + sub}
