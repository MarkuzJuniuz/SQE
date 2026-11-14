"""Red's starting air order of battle (Campaign Revamp Stage A3, v0.41.142).

Until v0.41.141 a level had a total (`enemy_air_total`) and a pool of types, and each field's types were drawn at random. Now each level has a ROSTER:
how many jets of each type red starts with, and where they go follows rules, not dice:

- Jets go to the fields in proportion to the theatre's `wing_weight`, within what each field can park (the DCS parking count, as before).
- The long-range fighters ("snipers": MiG-31 and Su-27) follow a depth gradient (flipped 2026-10-27, XO): at the fringe fields (field tier 2) 15% of a
  field's long-range jets are MiG-31, in the middle (tier 3) 50%, deep (tier 4) 75%. The MiG-31 is a big interceptor that works from rear bases under
  ground control and is poor in a turning fight, so it sits deep and the Su-27 holds the fringe. The numbers are judgment calls (no public source); the
  MiG-31 is a small, specialised fleet in reality, so L2 has 4 and L3 has 8.
- The heavy types (MiG-31, Su-27, Su-24M) need the bigger parking spots, so a field takes only as many as its heavy count allows.
- Nobody gets a lone jet: a type with a single jet at a field moves to the field that has most of that type.

The Mozdok bomber wing and its escort squadron are not part of this (scenario.py, `bomber_wing` / `bomber_escort_wing`).
"""
from __future__ import annotations
import math

HEAVY = {"MiG_31", "Su_27", "Su_24M", "Su_34"}
LONG_RANGE = ("MiG_31", "Su_27")
MIG31_SHARE = {2: 0.15, 3: 0.50, 4: 0.75}             # share of a field's long-range jets that are MiG-31, by the field's tier (v0.41.163, XO 2026-10-27: flipped, the interceptor sits deep under ground control, the Su-27 holds the fringe)
ORDER = ("MiG_31", "Su_27", "MiG_29S", "MiG_29A", "MiG_23MLD", "MiG_21Bis", "Su_24M", "Su_34", "Su_25")      # allocation order: the fighters first (every field gets some), then the strikers fill what parking is left
FIGHTERS = ("MiG_31", "Su_27", "MiG_29S", "MiG_29A", "MiG_23MLD", "MiG_21Bis")
LIGHT_FIGHTERS = ("MiG_29S", "MiG_29A", "MiG_23MLD", "MiG_21Bis")                # the fighter types `consolidate` may swap (not heavy: parking caps; not MiG-31: depth gradient)
STRIKERS = ("Su_25", "Su_24M", "Su_34")                                           # `consolidate` swaps these among themselves too (v0.41.438)
FIGHTER_FLOOR = 4                                       # every field keeps at least this many fighters (a pair of pairs): the old rule "every wing keeps a fighter squadron"

# Jets per level, bombers excluded (judgment calls: the red numbers of the 2026-10-25 plan; fighters about 85% of the old count with the MiG-31s inside,
# the extra jets are cheap strikers). L1: an old museum-piece air force that is quietly supplied (XO 2026-10-25): 20 Su-25, 10 Su-24M and, since v0.41.359 (campaign rules plan Phase 10c, the sponsor air arm,
# judgment call: no public figure), 24 relic fighters (MiG-21Bis and MiG-23MLD only; it was 14 with 3 MiG-29A, which is no museum piece). v0.41.359: Su-25 L2 52 to 60, L3 110 to 130 (the cheap attack fleet raids supply sites, `raids.SU25_SUPPLY`). v0.41.401 (S42, XO): L3 Su-25 130 to 18 (a few, like blue's 18 A-10C; judgment call, no public figure), fighters keep about the same total (86): Su-27 30 to 46, MiG-29S 28 to 20, MiG-29A 20 to 12 (Su-27 the main air-superiority fighter, MiG-29 the older short-legged one: public order-of-battle knowledge; the counts are judgment calls). All 46 Su-27 fit the heavy parking (checked, seeds 1-3).
ROSTERS = {
    1: {"MiG_21Bis": 18, "MiG_23MLD": 18, "Su_25": 28, "Su_24M": 12},                       # v0.41.438 (S84, XO 2026-11-14): 54 to 76, the sponsor keeps the insurgents supplied (judgment call, no public figure); still no MiG-29A
    2: {"MiG_31": 4, "MiG_29S": 15, "MiG_29A": 22, "MiG_23MLD": 11, "Su_25": 60, "Su_24M": 24},
    3: {"MiG_31": 8, "Su_27": 46, "MiG_29S": 20, "MiG_29A": 12, "Su_25": 18, "Su_34": 60},       # v0.41.361 (Phase 10d): L3 flies the Su-34 where it flew the Su-24M (same 60: judgment call, no public figure; L1 and L2 keep the Su-24M)
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


def consolidate(plan: dict, fields: list, cap_heavy: dict | None = None) -> None:
    """v0.41.437 (S83, XO 2026-11-14): fewer, fuller squadrons. The allocator above hands every field a little of every light fighter type (2 MiG-29S, 3 MiG-29A,
    2 MiG-23 ...), a shape no air force flies: a Soviet / Russian squadron is about 10 to 12 jets and a regiment keeps one or two types (from memory, medium
    firmness; the 12 cap itself is a judgment call). This swaps jets between two fields so one type grows into the bigger block and the other type
    follows the opposite way: each field keeps its jet count in the group (so the fighter floor and the parking caps hold) and the roster totals do not change. A swap needs
    the sum of squares of the blocks to rise (it always terminates), and never leaves a lone jet. v0.41.438 (S84): the strikers (Su-25 / Su-24M / Su-34) are swapped the
    same way, and a swap that would put a field over its heavy-parking cap is skipped. Groups: the light fighters, the strikers; the long-range fighters
    (Su-27, MiG-31 depth gradient) are left as they are."""
    big = 10 ** 6
    hv = lambda f: sum(n for k, n in plan[f].items() if k in HEAVY)
    for group in (LIGHT_FIGHTERS, STRIKERS):
        for _ in range(400):
            best = None
            for f in fields:
                for a, n in list(plan[f].items()):
                    if a not in group or n <= 0:
                        continue
                    for g in fields:
                        if g == f or plan[g].get(a, 0) < n:
                            continue
                        for b in group:
                            if b == a or plan[g].get(b, 0) < n or plan[f].get(b, 0) <= 0 or plan[g][b] - n == 1:
                                continue
                            d_hv = n * ((a in HEAVY) - (b in HEAVY))                       # heavy jets g gains (f loses the same)
                            if cap_heavy and ((d_hv > 0 and hv(g) + d_hv > (cap_heavy.get(g) or big)) or (d_hv < 0 and hv(f) - d_hv > (cap_heavy.get(f) or big))):
                                continue
                            gain = 2 * n * plan[g][a] + 2 * n * (plan[f][b] - plan[g][b] + n)
                            key = (gain, -fields.index(f), -fields.index(g), a, b)
                            if gain > 0 and (best is None or key > best[0]):
                                best = (key, f, g, a, b, n)
            if best is None:
                break
            _, f, g, a, b, n = best
            del plan[f][a]; plan[f][b] += n
            plan[g][a] += n; plan[g][b] -= n
            if plan[g][b] == 0:
                del plan[g][b]


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
        elif t in ("Su_24M", "Su_34"):                                             # the SEAD / DEAD / strike supply sits deeper, away from blue's reach: weight x (tier - 1)
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
    consolidate(plan, fields, cap_heavy)
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
