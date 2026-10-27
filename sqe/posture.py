"""The campaign posture and the Overview figures (Campaign Revamp, Stage C1, v0.41.148).

One place for what the Overview and the briefing say about the war: the posture label (it replaced the three old phases), the front, the odds at the
base we are fighting for, warnings, supply and air defence. It only READS the state; nothing here changes the war.

Every word threshold and unit below is a judgment call (no public figure exists for a game's abstract force points); the numbers are named constants so
they can be tuned from XO's flown tests.
"""
from __future__ import annotations
from . import ground, story
from .models import AssetKind

POINTS_PER_BATTALION = 10.0       # judgment call: a sector's strength runs 0..100, so a full sector is ten battalions (XO 2026-10-24 gave "scale 10 for L3")
ODDS_AHEAD = 1.3                  # our force at the front sector against the enemy's: at or above this we are "holding" the odds (judgment call; the
ODDS_BEHIND = 0.77                # defender factor in ground.DEFENDER is 1.25, so a 30% edge is roughly an even fight for the attacker); at or under 1/1.3 "losing"
WARN_ZONES = 2                    # a Coalition field is warned about when the sector this many sectors in front of it (or nearer) is held by the enemy with none of ours there (a line moves about one sector a day; judgment call)
SUPPLY_WORDS = ((0.90, "good"), (0.75, "adequate"), (0.62, "strained"), (0.0, "critical"))     # of the displayed percentage (55..100); judgment call

LABELS = ("Offensive", "Consolidating", "Holding", "Under pressure", "Last stand", "Counter-force")
ENDINGS = {1: "Insurgency broken", 2: "Ceasefire", 3: "Ceasefire"}

# One short line under each label. Stage C3 replaces these with the per-level story text; they only say what the label means.
LINES = {
    "Offensive": "The advance is moving: our ground force at the front outweighs the enemy's, and the air campaign is keeping it that way.",
    "Consolidating": "We hold the ground we took. The next push waits for the takeover to finish; use the time to break the enemy's supply and air defence.",
    "Holding": "The front is not moving. Our ground force at the contested sector is not yet strong enough to attack, so CAS and supply strikes decide the next move.",
    "Under pressure": "The enemy is gaining ground on our side of the line. Hold the sector in front of our airfields.",
    "Last stand": "The final objective is next. Take it and the war is decided.",
    "Counter-force": "The enemy's last reserve has arrived and is counter-attacking. Beat it and the war is won.",
    "Ceasefire": "The last objective is ours and the enemy has asked for talks. The campaign is won.",
    "Insurgency broken": "The coastal cities are back under government control and the insurgency has lost the field. The campaign is won.",
    "Defeat": "The front has collapsed and our airfields are being lost. The campaign is lost.",
}


def _active(state) -> bool:
    return ground.active(state) and bool(state.ground.get("rbases"))


def supply_word(frac: float) -> str:
    return next(w for lim, w in SUPPLY_WORDS if frac >= lim)


def supply_pct(state, side: str) -> int:
    return int(round(100 * ground.supply(state, side)))


def objective(state):
    """The red base we are fighting for now: the first one in the order we take them that is not ours yet. None when all are taken."""
    g = state.ground
    return next((rb for rb in g["rbases"] if rb["id"] not in g["taken"]), None)


def stage(state) -> tuple:
    """(bases taken so far + 1 capped at the total, total): 'stage x of y' of the push."""
    g = state.ground
    n = len(g["rbases"])
    return min(n, len(g["taken"]) + 1), n


def front_sector(state):
    """Our frontmost sector on the way to the objective: the lowest-numbered sector (the chain runs from red's end) in which we have a force. -> index or None."""
    g = state.ground
    return next((i for i in range(ground.n_zones(g)) if g["blue"][i] >= ground.MIN_FORCE), None)


def front_odds(state) -> dict:
    """The fight at the front: our force in the frontmost sector against the enemy's there (or in the sector beyond, when ours stands alone).
    -> {"sector", "blue", "red", "bn_blue", "bn_red", "word", "ratio"} or {} when no front exists."""
    g = state.ground
    i = front_sector(state)
    if i is None:
        return {}
    b = g["blue"][i]
    r = ground.red_strength(state, i)
    if r < ground.MIN_FORCE and i > 0:
        r = ground.red_strength(state, i - 1)
    ratio = b / r if r >= ground.MIN_FORCE else 99.0
    word = "holding" if ratio >= ODDS_AHEAD else "losing" if ratio <= ODDS_BEHIND else "even"
    return {"sector": g["names"][i], "blue": b, "red": r, "bn_blue": round(b / POINTS_PER_BATTALION), "bn_red": round(r / POINTS_PER_BATTALION),
            "word": word, "ratio": ratio}


def bases_status(state) -> list:
    """One entry per red base in the order we take them: (name, 'ours' | 'next' | 'enemy'), plus our own fields that have fallen."""
    g = state.ground
    nxt = objective(state)
    out = []
    for rb in g["rbases"]:
        out.append((rb["name"], "ours" if rb["id"] in g["taken"] else "next" if nxt is not None and rb["id"] == nxt["id"] else "enemy"))
    return out


def _days(n: int) -> str:
    return f"{n} day{'s' if n != 1 else ''}"


def _warnings(state) -> list:
    """(kind, text) pairs. Kinds: fall, retake, counter_due, counter_on, lost, clock."""
    g, out = state.ground, []
    n = ground.n_zones(g)
    for k, bid in sorted(g.get("fall", {}).items(), key=lambda kv: int(kv[0])):
        if bid in g["fallen"] or bid not in state.bases:
            continue
        i = int(k)
        if i >= n:
            continue
        # a field falls when the enemy holds its sector and we have nothing there (ground.check_falls); a line moves about one sector a day
        held = [j for j in range(0, i + 1) if ground.red_strength(state, j) >= ground.MIN_FORCE and g["blue"][j] < ground.MIN_FORCE]
        d = i - max(held) if held else 99
        if ground.red_strength(state, i) >= ground.MIN_FORCE and g["blue"][i] >= ground.MIN_FORCE:
            d = min(d, 1)                                               # the enemy is already in the field's own sector
        if d <= WARN_ZONES:
            out.append(("fall", f"{state.bases[bid].name} falls in about {_days(max(1, d))} if the enemy keeps advancing"))
    for rb in g["rbases"]:
        i = rb["zone"]
        if rb["id"] in g["taken"] and ground.red_strength(state, i) >= ground.MIN_FORCE and g["blue"][i] >= ground.MIN_FORCE:
            out.append(("retake", f"{rb['name']} is under attack: the enemy is back in its sector and may retake it"))
    c = g.get("counter")
    if c and not c.get("arrived") and not c.get("used"):
        d = max(0, int(c["arrive"]) - state.day)
        out.append(("counter_due", f"The enemy counter-force arrives in {_days(d)}" if d else "The enemy counter-force arrives today"))
    elif c and c.get("arrived") and not c.get("resolved") and not c.get("used") and state.day <= c.get("until", -1):
        d = int(c["until"]) - state.day
        out.append(("counter_on", "The enemy counter-force is attacking" + (f" for {_days(d)} more" if d else " today")))
    if len(g["fallen"]) == 1:
        out.append(("lost", "One of our airfields has fallen: if a second one is lost the campaign is lost"))
    clock = int(g.get("clock", 0))
    if g["taken"] and clock > state.day:
        out.append(("clock", f"Takeover under way: our next attack in about {_days(clock - state.day)}"))
    return out


def fall_warnings(state) -> list:
    return [t for _, t in _warnings(state)] if _active(state) and state.status == "ACTIVE" else []          # v0.41.150: none once the war is over


def posture(state) -> tuple:
    """-> (label, text). The label is one of LABELS, or an ending (Ceasefire / Insurgency broken / Defeat)."""
    if state.status == "VICTORY":
        lab = ENDINGS.get(int(state.level), "Ceasefire")
        return lab, story.now_line(state, lab, LINES[lab])
    if state.status == "DEFEAT":
        return "Defeat", story.now_line(state, "Defeat", LINES["Defeat"])
    if not _active(state):
        return "Holding", story.now_line(state, "Holding", LINES["Holding"])
    g = state.ground
    kinds = {k for k, _ in _warnings(state)}
    nxt = objective(state)
    if "counter_on" in kinds:
        lab = "Counter-force"
    elif g["fallen"] or kinds & {"fall", "retake"}:
        lab = "Under pressure"
    elif "clock" in kinds or "counter_due" in kinds:
        lab = "Consolidating"
    elif nxt is not None and nxt["id"] == g["stages"][-1]:
        lab = "Last stand"
    elif (front_odds(state) or {}).get("word") == "holding":
        lab = "Offensive"
    else:
        lab = "Holding"
    return lab, story.now_line(state, lab, LINES[lab])


def supply_lines(state) -> list:
    e, f = ground.supply(state, "red"), ground.supply(state, "blue")
    return [f"Coalition supply: {round(100 * f)}% ({supply_word(f)})", f"{story.enemy(state)} supply: {round(100 * e)}% ({supply_word(e)})"]


def _orders(state, key: str) -> list:
    return [o for o in ((getattr(state, "sams", None) or {}).get(key) or [])]


def iads_pct(state, side: str) -> float:
    if side == "red":
        ad = [a for a in state.assets.values() if a.kind in (AssetKind.SAM, AssetKind.EWR)]
    else:
        ad = list((getattr(state, "blue_sams", None) or {}).values())
    return sum(a.health for a in ad) / len(ad) if ad else 0.0


def transit_text(state, side: str) -> str:
    """'2 SAM batteries in transit, the first in 1 day' or ''."""
    o = _orders(state, "orders" if side == "blue" else "red_orders")
    if not o:
        return ""
    d = max(0, min(int(x["due"]) for x in o) - state.day)
    return f"{len(o)} SAM {'battery' if len(o) == 1 else 'batteries'} in transit, the first " + ("arrives today" if d == 0 else f"in {_days(d)}")


def air_defence_lines(state) -> list:
    out = []
    for side, label in (("blue", "Coalition"), ("red", story.enemy(state))):
        s = f"{label} air defence: {round(100 * iads_pct(state, side))}% of sites operational"
        t = transit_text(state, side)
        out.append(s + (f"; {t}" if t else ""))
    return out


def odds_line(state) -> str:
    o = front_odds(state)
    if not o:
        return "No Coalition ground force is in contact."
    def bn(n):
        return f"{n} battalion{'s' if n != 1 else ''}" if n >= 1 else "under a battalion"
    en = story.enemy(state)
    return f"{o['sector']}: Coalition {bn(o['bn_blue'])} against {'the enemy' if en == 'Enemy' else en}'s {bn(o['bn_red'])} ({o['word']})"


def front_lines(state) -> list:
    """The front for the Overview and the briefing: the objective, the stage, each base, the odds."""
    if not _active(state):
        return []
    nxt = objective(state)
    n, total = stage(state)
    out = [(f"The front: stage {n} of {total}, next objective {nxt['name']}" if nxt is not None else f"The front: all {total} objectives taken")]
    out.append("Bases: " + ", ".join(f"{nm} ({'taken' if st == 'ours' else 'next' if st == 'next' else 'enemy'})" for nm, st in bases_status(state)))
    g = state.ground
    if g["fallen"]:
        out.append("Lost: " + ", ".join(state.bases[x].name for x in g["fallen"] if x in state.bases))
    out.append(odds_line(state))
    return out


def sitrep(state) -> list:
    """The situation lines of the briefing: no aircraft counts (jets no longer decide the war)."""
    return front_lines(state) + fall_warnings(state) + supply_lines(state) + air_defence_lines(state)
