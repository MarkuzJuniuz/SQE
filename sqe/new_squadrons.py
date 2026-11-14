"""New squadrons for a field we took (v0.41.247, XO 2026-11-03, queue item h part 1, PR 3).

When a taken field's defences are complete and TAKEN_NEW_DAY has passed (`ground.taken_fields_step`), a NEW squadron is formed at it: F-16C by default ("they could do
almost anything", XO), or the airframe the planner is short of near that field. "Short" = slots the day's packages could not fill (`PackageBuilder.short`, kept for a week
in `ground["short"]` by `ground.note_shortfall`): CAS slots point to the A-10C, TARCAP / SWEEP slots (the long-range air-to-air jobs) to the F-15C, anything else to the F-16C.
All the numbers are judgment calls: the radius, the minimum count, one new squadron per field, full strength on arrival. Squadron names are real USAF designations and
nicknames written from memory, used as labels only (not checked against a source). Pure state, no pydcs except the parking count in `ground._parking`."""
from __future__ import annotations

import math

NM = 1852.0
NEED_RADIUS_NM = 150.0          # shortfalls whose target lies within this of the field count as its need (judgment call)
NEW_MIN_SIZE = 8                # a new squadron is cut down to the free parking, and not formed at all below this many jets (judgment call)
NEED_MIN = 6                    # unfilled slots in the week before the need beats the F-16C default (judgment call)
ROLE_TYPE = {"CAS": "A-10C", "TARCAP": "F-15C", "SWEEP": "F-15C"}
POOL = {"F-16C": [("fs_480", "480th FS 'Warhawks'"), ("fs_13", "13th FS 'Panthers'"), ("fs_14", "14th FS 'Samurais'"), ("fs_35", "35th FS 'Pantons'"),
                  ("fs_36", "36th FS 'Flying Fiends'"), ("fs_80", "80th FS 'Juvats'"), ("fs_555", "555th FS 'Triple Nickel'"), ("fs_510", "510th FS 'Buzzards'")],
        "F-15C": [("fs_44", "44th FS 'Vampire Bats'"), ("fs_67", "67th FS 'Fighting Cocks'"), ("fs_12", "12th FS 'Dirty Dozen'"), ("fs_71", "71st FS 'Ironmen'")],
        "A-10C": [("as_81", "81st FS 'Panthers'"), ("as_190", "190th FS 'Skullbangers'"), ("as_357", "357th FS 'Dragons'"), ("as_103", "103rd FS 'Eagles'")]}


def need(state, b) -> tuple:
    """(aircraft, unfilled slots counted) for a new squadron at base `b`: the type with the most unfilled slots near it over the last week, F-16C below NEED_MIN."""
    counts = {}
    for rec in (state.ground or {}).get("short", []):
        role, x, y = rec[1], rec[2], rec[3]                    # [day, role, x, y] before v0.41.338, [day, role, x, y, turn] since
        t = ROLE_TYPE.get(role)
        if t and math.hypot(x - b.x, y - b.y) / NM <= NEED_RADIUS_NM:
            counts[t] = counts.get(t, 0) + 1
    if counts:
        t = max(sorted(counts), key=lambda k: counts[k])
        if counts[t] >= NEED_MIN:
            return t, counts[t]
    return "F-16C", counts.get("F-16C", 0)


def callsign_for(state, aircraft: str) -> str | None:
    """A callsign of the type's table that no squadron owns (the group names of the whole coalition must stay unique): the type's own names first, then the shared ones."""
    from .callsigns import EXTRA, table
    owned = {q.callsign for q in state.squadrons.values()}
    for nm in list(EXTRA.get(aircraft, {})) + list(table(aircraft)):
        if nm not in owned:
            return nm
    return None


def form(state, b, parking) -> tuple:
    """Form ONE new squadron at taken base `b` if there is room for it (`parking(airport, aircraft)` = free spots or None). Returns (log lines, squadron or None).
    v0.41.353 (Phase 9b): the F-15C has only the eight generic callsigns and the 9b laydown owns them all; a field that needs an F-15C squadron then forms an F-16C one (callsign table of its own)."""
    from .models import Squadron
    aircraft, short = need(state, b)
    cs = callsign_for(state, aircraft)
    if cs is None and aircraft != "F-16C":
        aircraft, short = "F-16C", 0
        cs = callsign_for(state, aircraft)
    size = max([q.authorized for q in state.squadrons.values() if q.aircraft == aircraft and q.role != "havcap"] or [12])
    here = sum(q.authorized for q in state.squadrons.values() if q.base_id == b.id)
    cap = parking(b.airport, aircraft) if b.airport else None
    if cap is not None:
        size = min(size, cap - here)                                  # (a small field takes a smaller squadron; ground.py's first mover already took its spots)
        size -= size % 2
        if size < NEW_MIN_SIZE:
            return [], None
    free = [p for p in POOL[aircraft] if p[0] not in state.squadrons]
    if cs is None or not free:
        return [], None
    sid, name = free[0]
    sq = Squadron(sid, name, aircraft, b.id, size, size, cs)
    state.squadrons[sid] = sq
    why = f" (short of {aircraft} slots near it: {short})" if short >= NEED_MIN else ""
    return [f"   {name} ({aircraft}, {size} aircraft, callsign {cs}) is formed at {b.name}{why}"], sq
