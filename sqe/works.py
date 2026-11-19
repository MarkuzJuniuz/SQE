"""Lutorin's works (S111, XO 2026-11-19): the special blue targets of a pack with a `works` block (Syria Level 2 and 3), and the second way the war ends there.

The story: a handful of plants that make Lutorin's wares can only exist in Syria (the stabilizer that gives old Soviet arsenals new life is made from a crystal that only forms there and
cannot be shipped). Damascus hosts them in return for his money and his arms, and that backs its claim on Hatay. The coalition's way to win without conquering anything is to destroy
every works; red's is the one it already has, taking Hatay (a blue defeat, `ground.defeat_bases`).

How it works (everything numeric lives in the pack's `works` block, so a theatre tunes it with no code):
* The works are `DEPOT` assets with the id prefix `wks_` and the variant FACTORY (the road-net plants' look and double guard), registered at campaign start for the levels the pack names. The planner,
  the SEAD gating and the abstract resolution treat them as supply strikes with a priority bonus (`PLAN_BONUS`); a strike removes only `damage` of what it removes from a depot, so a works takes
  several good strikes. They are not supply sites: they stay out of the Force Index and its nightly repair, and a works is hunted until it is destroyed (no "down for planning" at 0.3 health).
* One rebuild team: a destroyed works is rebuilt one at a time, each taking about `rebuild_days` (a level's value; the draw is 60 to 140 percent of it), back at full health. A damaged works does not mend.
* Red's push: the works feed the war on the Hatay front. `edge` = 1 + the level's `push` x (works standing / works built) multiplies red's surge factor in `ground.resolve_day` (reinforcements, attack
  chance) and the raid rate (`raids`), so every works lost takes strength from the push, and none left leaves red at its plain strength.
* Win: every works destroyed at once is a VICTORY (`war.update_status`); the pack's `works_win` story beat tells it. Judgment calls, no public figure: every number in the block (tuned on the
  real sim, tools probe `works_probe.py`).
"""
from __future__ import annotations
import random
from .models import AssetKind, EnemyAsset

PREFIX = "wks_"
PLAN_BONUS = 30.0          # added to a works' strike score (war.ObjectivePlanner) on top of SUPPLY_FIRST_BONUS: the works come before ordinary supply strikes (judgment call; tuned by the probe)
STANDOFF_SAM = 0.3          # a Standoff Strike on a works counts only this share of the SAM sites around it in its odds (`war.WarSimulator.odds`): the weapon is released outside their rings (judgment call; tuned by the probe)
DEFAULT_DAMAGE = 0.67      # the share of a depot's damage a strike does to a works (the pack's `damage` overrides)


def is_works(a) -> bool:
    return str(getattr(a, "id", "")).startswith(PREFIX)


def _block():
    from . import theatres
    return theatres.active().get("works") or None


def params(state):
    """The pack's `works` block merged with this level's values, or None (no works here: the Caucasus, Syria Level 1, a campaign made before S111)."""
    b = _block()
    g = getattr(state, "ground", None) or {}
    if not b or not g.get("works"):
        return None
    lv = (b.get("levels") or {}).get(str(int(getattr(state, "level", 2))))
    if not lv:
        return None
    return {"label": b.get("label", "The works"), "damage": float(lv.get("damage", b.get("damage", DEFAULT_DAMAGE))), "push": float(lv.get("push", 0.0)),
            "rebuild_days": float(lv.get("rebuild_days", 60.0))}


def ids(state) -> list:
    return [i for i in ((getattr(state, "ground", None) or {}).get("works") or {}).get("ids", []) if i in state.assets]


def standing(state) -> int:
    return sum(1 for i in ids(state) if not state.assets[i].destroyed)


def build(st, th: dict, d, ap=None) -> list:
    """Register the pack's works for this level (scenario.new_campaign, after the sites are placed and the sea check ran; own sites, no random draw). -> the asset ids."""
    b = th.get("works")
    g = getattr(st, "ground", None)
    if not b or g is None or str((d.level)) not in (b.get("levels") or {}):
        return []
    from . import seacheck
    out = []
    for s in b["sites"]:
        x, y = float(s["x"]), float(s["y"])
        if not seacheck.site_ok(x, y):
            x, y = seacheck.snap_to_land(x, y)
        a = EnemyAsset(s["id"], s["name"], AssetKind.DEPOT, x, y, 1.0, int(s.get("value", 10)), [], None, "FACTORY", int(s.get("tier", 4)), "")
        st.assets[a.id] = a
        out.append(a.id)
    g["works"] = {"ids": out, "team": None, "left": 0.0, "built": 0}
    return out


def edge(state, d=None) -> float:
    """Red's push multiplier from the works (1.0 with none standing, or where the pack has none)."""
    p = params(state)
    n = len(ids(state))
    if not p or not n:
        return 1.0
    return 1.0 + p["push"] * standing(state) / n


def damage_factor(state, a) -> float:
    """What a strike on this asset does compared with the same strike on a depot (1.0 for everything but a works)."""
    if not is_works(a):
        return 1.0
    p = params(state)
    return p["damage"] if p else DEFAULT_DAMAGE


def gone(state) -> bool:
    """Every works the campaign started with is destroyed (the coalition's win where the pack has them)."""
    n = ids(state)
    return bool(n) and params(state) is not None and standing(state) == 0


def rebuild(state, rng: random.Random) -> list:
    """Overnight: the one rebuild team works on one destroyed works at a time. -> war-log lines."""
    from . import story
    p = params(state)
    if not p:
        return []
    w = state.ground["works"]
    dead = [i for i in ids(state) if state.assets[i].destroyed]
    out = []
    for i in dead:                                                           # a works that fell since last night: one log line (the story beat tells the first)
        if i not in (w.get("seen") or []):
            out.append(f"{state.assets[i].name} is destroyed")
            if not w.get("lost"):
                out += story.beat(state, "works_down")
            w["lost"] = int(w.get("lost", 0)) + 1
    w["seen"] = list(dead)
    if not dead:
        w["team"], w["left"] = None, 0.0
        return out
    if w.get("team") not in dead:
        w["team"] = dead[0]
        w["left"] = max(3.0, p["rebuild_days"] * rng.uniform(0.6, 1.4))
    w["left"] = float(w["left"]) - 1.0
    if w["left"] > 0:
        return out
    a = state.assets[w["team"]]
    a.health = 1.0
    w["team"], w["left"] = None, 0.0
    w["built"] = int(w.get("built", 0)) + 1
    w["seen"] = [i for i in dead if i != a.id]
    return out + [f"{a.name} is back in production"] + story.beat(state, "works_back")


def line(state):
    """The Overview line in words (S80: no figures), or None where there are no works."""
    p = params(state)
    n = len(ids(state))
    if not p or not n:
        return None
    s = standing(state)
    word = ("all in production" if s == n else "most of them still in production" if s * 2 > n else "only a few still in production" if s > 0 else "all destroyed")
    team = (state.ground.get("works") or {}).get("team")
    return f"{p['label']}: {word}" + (", one being rebuilt" if team and s < n else "")
