"""Red's starting air order of battle (Campaign Revamp Stage A3, v0.41.142).

Until v0.41.141 a level had a total (`enemy_air_total`) and a pool of types, and each field's types were drawn at random. Now each level has a ROSTER:
how many jets of each type red starts with, and where they go follows rules, not dice:

- Jets go to the fields in proportion to the theatre's `wing_weight`, within what each field can park (the DCS parking count, as before).
- The long-range fighters ("snipers": MiG-31 and Su-27) follow a depth gradient (XO 2026-10-24): at the fringe fields (field tier 2) 75% of a field's
  long-range jets are MiG-31, in the middle (tier 3) 50%, deep (tier 4) 15%, so the Su-27 feels prized and the deep MiG-31 is "spice". The numbers are
  judgment calls (no public source); the MiG-31 itself is a small, specialised fleet in reality and made numerous here as a game liberty.
- The heavy types (MiG-31, Su-27, Su-24M) need the bigger parking spots, so a field takes only as many as its heavy count allows.
- Nobody gets a lone jet: a type with a single jet at a field moves to the field that has most of that type.

The Mozdok bomber wing and its escort squadron are not part of this (scenario.py, `bomber_wing` / `bomber_escort_wing`).
"""
from __future__ import annotations
import math

HEAVY = {"MiG_31", "Su_27", "Su_24M"}
LONG_RANGE = ("MiG_31", "Su_27")
MIG31_SHARE = {2: 0.75, 3: 0.50, 4: 0.15}             # share of a field's long-range jets that are MiG-31, by the field's tier (XO 2026-10-24)
ORDER = ("MiG_31", "Su_27", "MiG_29S", "MiG_29A", "MiG_23MLD", "MiG_21Bis", "Su_24M", "Su_25")      # allocation order: the fighters first (every field gets some), then the strikers fill what parking is left
FIGHTERS = ("MiG_31", "Su_27", "MiG_29S", "MiG_29A", "MiG_23MLD", "MiG_21Bis")
FIGHTER_FLOOR = 4                                       # every field keeps at least this many fighters (a pair of pairs): the old rule "every wing keeps a fighter squadron"

# Jets per level, bombers excluded (judgment calls: the red numbers of the 2026-10-25 plan; fighters about 85% of the old count with the MiG-31s inside,
# the extra jets are cheap strikers). L1: an old museum-piece air force that is quietly supplied (XO 2026-10-25): about 14 fighters, 20 Su-25, 10 Su-24M.
ROSTERS = {
    1: {"MiG_21Bis": 6, "MiG_23MLD": 5, "MiG_29A": 3, "Su_25": 20, "Su_24M": 10},
    2: {"MiG_31": 7, "MiG_29S": 12, "MiG_29A": 22, "MiG_23MLD": 11, "Su_25": 52, "Su_24M": 24},
    3: {"MiG_31": 14, "Su_27": 24, "MiG_29S": 28, "MiG_29A": 20, "Su_25": 110, "Su_24M": 60},
}


def _share(total: int, desire: dict, cap: dict) -> dict:
    """Split `total` over the keys in proportion to `desire`, never more than `cap[key]` each (largest remainder, ties by key). Less than `total`
    only when the caps run out."""
    out = {k: 0 for k in desire}
    live = {k: v for k, v in desire.items() if v > 0 and cap.get(k, 0) > 0}
    left = total
    while left > 0 and live:
        s = sum(live.values())
        quota = {k: left * v / s for k, v in live.items()}
        gave = 0
        for k in sorted(live):
            g = min(int(math.floor(quota[k])), cap[k] - out[k])
            out[k] += g; gave += g
        left -= gave
        if left > 0 and gave == 0:                                  # all quotas below 1: the biggest remainders get one each
            for k in sorted(live, key=lambda k: (-(quota[k] - math.floor(quota[k])), k)):
                if left <= 0:
                    break
                if out[k] < cap[k]:
                    out[k] += 1; left -= 1
        live = {k: v for k, v in live.items() if out[k] < cap[k]}
    return out


def allocate(level: int, fields: list, weight: dict, tier: dict, cap_all: dict, cap_heavy: dict, roster: dict | None = None) -> dict:
    """{field id: {aircraft type: jets}} for the level's roster. `cap_all[f]` is the most jets of any kind the field parks, `cap_heavy[f]` the most heavy
    ones (None = unknown = no limit)."""
    roster = ROSTERS[level] if roster is None else roster
    big = 10 ** 6
    plan = {f: {} for f in fields}
    used = lambda f: sum(plan[f].values())
    used_hv = lambda f: sum(n for k, n in plan[f].items() if k in HEAVY)

    def room(f, t):                                                   # can field f take one more jet of type t?
        return used(f) < (cap_all.get(f) or big) and (t not in HEAVY or used_hv(f) < (cap_heavy.get(f) or big))

    def no_lone_jets(t):                                              # a single jet of a type at a field joins the biggest block of that type (or tops its field up to two)
        for f in [f for f in fields if plan[f].get(t) == 1]:
            blocks = sorted((g for g in fields if g != f and plan[g].get(t, 0) >= 2), key=lambda g: (-plan[g][t], fields.index(g)))
            if not blocks:
                continue
            if t in LONG_RANGE and plan[blocks[0]][t] >= 4 and room(f, t):      # a long-range jet at a deep field is the "spice": its field gets a second one from the biggest block
                plan[blocks[0]][t] -= 1; plan[f][t] += 1
                continue
            for g in blocks:
                if room(g, t):
                    del plan[f][t]; plan[g][t] += 1
                    break
    for t in ORDER:
        total = roster.get(t, 0)
        if total <= 0:
            continue
        if t == "MiG_31":
            desire = {f: weight[f] * MIG31_SHARE.get(tier.get(f, 3), 0.5) for f in fields}
        elif t == "Su_27":
            desire = {f: weight[f] * (1.0 - MIG31_SHARE.get(tier.get(f, 3), 0.5)) for f in fields}
        elif t == "Su_24M":                                             # the SEAD / DEAD / strike supply sits deeper, away from blue's reach: weight x (tier - 1)
            desire = {f: weight[f] * max(1, tier.get(f, 3) - 1) for f in fields}
        else:
            desire = {f: float(weight[f]) for f in fields}
        cap = {}
        for f in fields:
            r_ = (cap_all.get(f) or big) - used(f)
            if t in HEAVY:
                r_ = min(r_, (cap_heavy.get(f) or big) - used_hv(f))
            cap[f] = max(0, r_)
        got = _share(total, desire, cap)
        for f, n in got.items():
            if n:
                plan[f][t] = n
        if t in LONG_RANGE:
            no_lone_jets(t)                                           # before the strikers crowd the heavy parking spots out
    for f in fields:                                                  # fighter floor: a field with fewer than FIGHTER_FLOOR fighters takes pairs from the biggest light block elsewhere
        while sum(plan[f].get(t, 0) for t in FIGHTERS) < FIGHTER_FLOOR:
            donors = [(plan[g].get(t, 0), g, t) for g in fields for t in FIGHTERS if g != f and t not in HEAVY and plan[g].get(t, 0) >= 4]
            if not donors or not (room(f, "MiG_29A") and sum(plan[f].values()) + 2 <= (cap_all.get(f) or big)):
                break
            n, g, t = max(donors, key=lambda x: (x[0], x[1], x[2]))
            plan[g][t] -= 2; plan[f][t] = plan[f].get(t, 0) + 2
    for t in ORDER:
        no_lone_jets(t)
    for f in fields:                                                  # fighter floor, once more after the lone jets moved: a field with fewer than FIGHTER_FLOOR fighters takes pairs from the biggest light block elsewhere
        while sum(plan[f].get(t, 0) for t in FIGHTERS) < FIGHTER_FLOOR:
            donors = [(plan[g].get(t, 0), g, t) for g in fields for t in FIGHTERS if g != f and t not in HEAVY and plan[g].get(t, 0) >= 4]
            if not donors or not (room(f, "MiG_29A") and sum(plan[f].values()) + 2 <= (cap_all.get(f) or big)):
                break
            n, g, t = max(donors, key=lambda x: (x[0], x[1], x[2]))
            plan[g][t] -= 2; plan[f][t] = plan[f].get(t, 0) + 2
    return {f: p for f, p in plan.items() if p}


def cut(aid: str, wing_name: str, types: dict, max_size: int) -> list:
    """The squadrons of one field: each type is cut into ceil(jets / max_size) squadrons of even size (never over max_size). -> [(id, name, type, jets)]."""
    out, i = [], 0
    for t in ORDER:
        n = types.get(t, 0)
        if n <= 0:
            continue
        k = max(1, -(-n // max(1, max_size)))
        base, extra = divmod(n, k)
        for j in range(k):
            i += 1
            out.append((f"{aid}_{i}", f"{wing_name} {i}", t, base + (1 if j < extra else 0)))
    return out
