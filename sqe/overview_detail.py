"""The Overview's Situation panel and detail tabs (Campaign Revamp, Stage C2, v0.41.149). Data only: the GUI draws it, the smoke test reads it.
Like posture.py it only READS the state."""
from __future__ import annotations
import re
from . import ground, posture, tempo, narrative, sams, story
from .models import AssetKind

EVENT_RE = re.compile(r"HAS FALLEN|has been retaken|back in our hands|counter-force|VICTORY|DEFEAT|The last objective|takeover", re.I)


def situation(state) -> dict:
    """The Situation panel: the Background (full text), the Intent, and the Now line pinned under them. They come from the level's story (`story.py`);
    a theatre without stories shows its one background, whose last paragraph (when it is the commander's intent) becomes the Intent."""
    st_ = story.get(state)
    if st_.get("background"):
        paras, intent = list(st_["background"]), st_.get("intent", "")
    else:
        paras = [p.strip() for p in narrative.BACKGROUND.split("\n\n") if p.strip()]
        intent = ""
        if len(paras) > 1 and "intent" in paras[-1].lower():
            intent = paras.pop()
    label, now = posture.posture(state)
    return {"background": paras, "intent": intent, "label": label, "now": now}


def _bn(x: float) -> str:
    n = round(x / posture.POINTS_PER_BATTALION)
    return str(n) if n >= 1 else ("<1" if x >= ground.MIN_FORCE else "0")


def ground_rows(state) -> list:
    """One row per sector, from red's end: (name, enemy battalions, Coalition battalions, tag)."""
    if not posture._active(state):
        return []
    g, out = state.ground, []
    for i in range(ground.n_zones(g)):
        r, b = ground.red_strength(state, i), ground.blue_strength(state, i)
        tag = "contested" if (r >= ground.MIN_FORCE and b >= ground.MIN_FORCE) else ("enemy holds" if r >= ground.MIN_FORCE else "Coalition holds" if b >= ground.MIN_FORCE else "empty")
        out.append((g["names"][i], _bn(r), _bn(b), tag))
    return out


def ground_notes(state) -> list:
    """The takeover clock, each base's state, and the front's history (the war log lines that moved the front, newest first, up to 12)."""
    if not posture._active(state):
        return []
    g, out = state.ground, []
    clock = int(g.get("clock", 0))
    if g["taken"] and clock > state.day:
        out.append(f"Takeover clock: our next attack in about {clock - state.day} day{'s' if clock - state.day != 1 else ''} (day {clock})")
    elif g["taken"]:
        out.append("Takeover clock: finished, the next attack is allowed")
    for nm, st_ in posture.bases_status(state):
        out.append(f"{nm}: " + {"ours": "taken", "next": "next objective", "enemy": "held by the enemy"}[st_])
    for rb in g["rbases"]:
        d = g.get("taken_day", {}).get(rb["id"])
        if d is not None:
            out.append(f"{rb['name']} taken on day {d}")
    for bid in g.get("fallen", []):
        if bid in state.bases:
            out.append(f"{state.bases[bid].name}: LOST")
    return out


def history(state, limit: int = 12) -> list:
    """The war log lines that moved the front, newest first."""
    ev = [ln for ln in state.log if EVENT_RE.search(ln)]
    return list(reversed(ev))[:limit]


def supply_rows(state) -> list:
    """(side, site, health %, status) for every fuel farm and depot either side holds. Status: intact, down, struck last (no repair tonight), repairing with the days
    to full at the holder's rate. A site that changed hands says so."""
    if not posture._active(state):
        return []
    g, out = state.ground, []
    prev = g.get("sup_h", {})
    for side, label, pool in (("blue", "Coalition", getattr(state, "blue_assets", {})), ("red", story.enemy(state), state.assets)):
        rate = ground.supply(state, side) / ground.SUPPLY_REPAIR_DAYS
        for a in sorted(pool.values(), key=lambda x: x.name):
            if a.kind not in ground.SUPPLY_KINDS:
                continue
            h = a.health
            days = max(1, round((1.0 - h) / rate)) if rate > 0 else 99
            if h < prev.get(a.id, h) - 1e-6:
                st_ = "struck since last night, no repair tonight"
            elif h <= 0.05:
                st_ = f"destroyed, about {days} day{'s' if days != 1 else ''} to rebuild"
            elif h < 1.0 - 1e-6:
                st_ = f"repairing, about {days} day{'s' if days != 1 else ''} to full"
            else:
                st_ = "intact"
            mine = (a.id.startswith("b") and side == "blue") or (not a.id.startswith("b") and side == "red")
            out.append((label, a.name + ("" if mine else " (captured)"), round(100 * h), st_))
    return out


def air_defence_rows(state) -> list:
    """(side, site, kind, health %, status) for every SAM site and radar; the Coalition's sites are listed by field."""
    out = []
    for a in sorted(state.assets.values(), key=lambda x: x.name):
        if a.kind in (AssetKind.SAM, AssetKind.EWR):
            st_ = "destroyed" if a.destroyed else ("radars blinded today" if getattr(a, "suppressed", False) else "operational")
            out.append((story.enemy(state), a.name, a.variant or a.kind.value, round(100 * a.health), st_))
    for a in sorted((getattr(state, "blue_sams", None) or {}).values(), key=lambda x: x.name):
        out.append(("Coalition", a.name, a.variant or "SAM", round(100 * a.health), "destroyed" if a.destroyed else "operational"))
    return out


def asks_rows(state) -> list:
    """SAM batteries in transit: (side, text)."""
    rec = getattr(state, "sams", None) or {}
    out = []
    for o in rec.get("blue_asks", []):
        b = state.bases.get(o.get("to"))
        kind = sams.BLUE_SITES.get(o.get("key"), ("", "battery"))[0]
        out.append(("Coalition", f"{kind} battery from {o.get('from_name', '?')} to {b.name if b else o.get('to')}, due day {o['due']} ({_when(state, o)})"))
    for o in rec.get("red_asks", []):
        to, fr = state.assets.get(o.get("to")), state.assets.get(o.get("from"))
        out.append((story.enemy(state), f"battery from {fr.name if fr else o.get('from')} to {to.name if to else o.get('to')}, due day {o['due']} ({_when(state, o)})"))
    return out


def _when(state, o) -> str:
    d = int(o["due"]) - state.day
    return "arrives today" if d <= 0 else f"in {d} day{'s' if d != 1 else ''}"


def tempo_lines(state) -> list:
    """The air tempo of each job kind: the nudge to the background jobs' odds (0 to +40 points, fades 3% a night)."""
    out = []
    for k in tempo.KINDS:
        v = tempo.get(state, k) * 100
        out.append(f"{tempo.LABEL[k][:1].upper() + tempo.LABEL[k][1:]}: {v:+.0f}%" + ("  (at the cap)" if abs(v) >= tempo.TEMPO_CAP * 100 - 0.5 else ""))
    return out


TYPE_WORDS = (("CAS", "CAS"), ("STRIKE", "strike"), ("DEAD", "SEAD / DEAD"), ("COUNTER_AIR", "counter-air"), ("BARCAP", "patrol"), ("FLEET_DEFENSE", "fleet defence"))


def tasking(sess) -> tuple:
    """Today's tasking for the Overview: (headline, detail). The packages on the order by kind, how many your squadron can fly, or why it has none."""
    st = sess.state
    pk = sess.packages()
    if st.status != "ACTIVE":
        return "War over", "There is nothing left to fly."
    n_you = sum(1 for p in pk if sess.flyable(p))
    kinds = {}
    for p in pk:
        kinds[p.objective.type.value] = kinds.get(p.objective.type.value, 0) + 1
    parts = [f"{kinds[k]} {w}" for k, w in TYPE_WORDS if kinds.get(k)]
    head = f"{len(pk)} package{'s' if len(pk) != 1 else ''}"
    if not pk:
        return "No jobs today", " ".join(sess.idle_reasons()) or "Nothing is open on today's tasking order."
    if n_you:
        return head, ", ".join(parts) + f". You can fly {n_you}."
    return head, ", ".join(parts) + ". Stand-down day for you: " + " ".join(sess.idle_reasons())
