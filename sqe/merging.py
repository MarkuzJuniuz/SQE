"""The package-merging rules: which packages fold into one mission, around which circle.

A mixin: `Session` inherits these methods (like a C# partial class). They use `self.state`, `self.settings`
and the other fields `Session` sets up; the callers (`plan_turn`, `fly`, `gui/app.py`) go through `self`.
"""
from __future__ import annotations
import math

from .models import ObjectiveType
from .packages import Package


class Merging:
    # ---- target area: a circle around the package's target, kept inside the area where targets exist (S139b: the Target Area Radius, was the merge radius) ------
    def area_radius_m(self) -> float:
        return max(5.0, float(getattr(self.settings, "target_area_radius_nm", 15))) * 1852.0

    def _pkg_xy(self, p: Package):
        """The ground target of a package, or None for fleet packages (BARCAP, fleet defence), which are never folded by area."""
        if p.objective.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            return None
        a = self.state.assets.get(p.objective.target_id)
        return (a.x, a.y) if a is not None else None

    def _raid_xy(self, p: Package):
        """v0.41.28: where a land raid is going (the raided field, or the supply site / garrison it is after). Only the centre of the merge circle
        when you fly the intercept; a raid package itself is still never folded into anyone else's mission."""
        if p.objective.type != ObjectiveType.FLEET_DEFENSE or not p.extra.get("land"):
            return None
        b = self.state.bases.get(p.objective.target_id)
        if b is None:
            return None
        return tuple(p.extra.get("dest") or (b.x, b.y))

    def _near(self, a: Package, b: Package, R: float) -> bool:
        pa, pb = self._pkg_xy(a), self._pkg_xy(b)
        return pa is not None and pb is not None and math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= R

    def merge_center(self, pkg: Package, R: float | None = None):
        """The centre of the merge circle: your target, slid inward so the whole circle stays inside the box that holds every possible target
        (destroyed sites included, so it does not shrink as the war goes on). Your own target always stays inside the circle."""
        R = self.area_radius_m() if R is None else R
        t = self._pkg_xy(pkg) or self._raid_xy(pkg)
        if t is None:
            return None
        A = list(self.state.assets.values())
        x0, x1 = min(a.x for a in A), max(a.x for a in A)
        y0, y1 = min(a.y for a in A), max(a.y for a in A)
        cx = min(max(t[0], x0 + R), x1 - R) if (x1 - x0) >= 2 * R else (x0 + x1) / 2
        cy = min(max(t[1], y0 + R), y1 - R) if (y1 - y0) >= 2 * R else (y0 + y1) / 2
        d = math.hypot(t[0] - cx, t[1] - cy)
        if d > R:                                     # never push your own target out of the circle
            cx, cy = t[0] + (cx - t[0]) * R / d, t[1] + (cy - t[1]) * R / d
        return cx, cy

    def _inside_merge(self, anchor: Package, other: Package) -> bool:
        """Is `other`'s target inside the merge circle around `anchor`'s?"""
        if self.settings.merge_mode != "area":
            return False
        c, t = self.merge_center(anchor), self._pkg_xy(other) or self._raid_xy(other)
        return c is not None and t is not None and math.hypot(t[0] - c[0], t[1] - c[1]) <= self.area_radius_m()

    def _raid_way(self, p: Package):
        """S39: a land raid's way in, ((x0, y0), (x1, y1)): from the bomber wing's field to the point it is going for. None for any other package (the carrier raid stays out)."""
        t = self._raid_xy(p)
        if t is None:
            return None
        w = self.state.assets.get(p.extra.get("bomber_wing"))
        return ((w.x, w.y), t) if w is not None else (t, t)

    @staticmethod
    def _seg_dist(pt, a, b) -> float:
        """Distance (m) from the point `pt` to the segment a-b."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 <= 0 else max(0.0, min(1.0, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L2))
        return math.hypot(pt[0] - (a[0] + u * dx), pt[1] - (a[1] + u * dy))

    def merge_candidates(self, pkg: Package, unseen: bool = False) -> list:
        """The target-area rule (S139b: FLY no longer uses it, see `fly_candidates`; the Missions list does, `collapse`, `gui/app.py`): the packages whose target lies inside the target-area circle
        (Settings: Target Area Radius, centred by merge_center), starting up to `merge_later_min` minutes AFTER `pkg` or up to `merge_earlier_min` minutes BEFORE it (those are already underway
        when the mission starts). No count cap (S139b: the unit limit is the only cap), closest to the centre first, a Fighter Sweep first. Empty when merging is off.
        v0.41.351 (XO 2026-11-10, S8): a land raid (the intercept package; its point is the raided field, supply site or garrison, `_raid_xy`) folds in like any package.
        v0.41.398 (S39): a raid also counts along its way in (`_raid_way`, its wing's field to its target). When `pkg` is a land raid, a package folds in when its point is
        inside the circle OR within the radius of the raid's way in; and with `merge_raids_all` (default) every other land raid in the time window folds in, at any distance.
        When `pkg` is anything else, a land raid folds in when its target is inside the circle OR its way in passes within the radius of the merge centre.
        `unseen=True` (`fly` only) also takes the raids blue did not detect (`extra["unseen_raid"]`, not listed): they are built but never named to the player; the list and the GUI never pass it."""
        if self.settings.merge_mode != "area":
            return []
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        back = max(0, int(getattr(self.settings, "merge_earlier_min", 15)))
        fwd = max(0, int(getattr(self.settings, "merge_later_min", 30)))
        R = self.area_radius_m()
        c = self.merge_center(pkg, R)
        if c is None:
            return []
        anchor_way = self._raid_way(pkg)
        raids_all = bool(getattr(self.settings, "merge_raids_all", True))
        out = []
        pool = self.packages()
        if unseen:
            pool = pool + [u for u in (Package.from_dict(d) for d in self.state.plan) if u.extra.get("unseen_raid") and not u.extra.get("past")]
        for p in pool:
            t = self._pkg_xy(p) or self._raid_xy(p)
            if p.number == pkg.number or t is None or not (-back <= hm(p) - hm(pkg) <= fwd) or not any(not f.tag for f in p.flights) or p.extra.get("scrub"):
                continue
            d = math.hypot(t[0] - c[0], t[1] - c[1])
            way = self._raid_way(p)
            if d <= R:
                ok = True
            elif anchor_way is not None:
                ok = self._seg_dist(t, *anchor_way) <= R or (raids_all and way is not None)
            else:
                ok = way is not None and self._seg_dist(c, *way) <= R
            if ok:
                out.append((d, hm(p), p.number, p))
        out.sort(key=lambda r: (not (r[3].objective.type == ObjectiveType.COUNTER_AIR and r[3].objective.aim == "SWEEP"),) + r[:3])     # a Fighter Sweep first: the unit limit drops the strike packages before it
        picked = [r[3] for r in out]
        # v0.41.270 (XO 2026-11-04): the carrier raid folds into no mission: it is red aiming for the king, a setpiece of its own (v0.41.250 folded it into any mission at its time)
        return picked

    def fly_candidates(self, pkg: Package, unseen: bool = False) -> list:
        """S139a (XO 2026-11-20): the packages `fly` folds into a mission built around `pkg`: EVERY package that starts inside the time window (Settings: `merge_earlier_min` before,
        `merge_later_min` after), at any distance and with no count limit; the unit limit is the only cap (`Session.fly` budgets and drops). The same filters as `merge_candidates`
        (not `pkg` itself, has a point, at least one flight that is not a support tag, not scrubbed; `unseen=True` adds the raids blue did not detect). Empty when merging is off.
        Nearest first, by distance from YOUR target point (not the slid merge centre): a land raid's distance is the smaller of its target's and its way in's (`_raid_way`); when YOU fly
        a raid intercept it is also the smaller of the candidate's point to your way in. Ties: start time, then number. A Fighter Sweep sorts right after the furthest of the packages it
        covers (`extra["covers"]`) that is in the list or is `pkg` (covering `pkg` is distance 0); covering none of them, it sorts by its own distance."""
        if self.settings.merge_mode != "area":
            return []
        here = self._pkg_xy(pkg) or self._raid_xy(pkg)
        if here is None:
            return []
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        back = max(0, int(getattr(self.settings, "merge_earlier_min", 15)))
        fwd = max(0, int(getattr(self.settings, "merge_later_min", 30)))
        my_way = self._raid_way(pkg)
        pool = self.packages()
        if unseen:
            pool = pool + [u for u in (Package.from_dict(d) for d in self.state.plan) if u.extra.get("unseen_raid") and not u.extra.get("past")]
        rows = []
        for p in pool:
            t = self._pkg_xy(p) or self._raid_xy(p)
            if p.number == pkg.number or t is None or not (-back <= hm(p) - hm(pkg) <= fwd) or not any(not f.tag for f in p.flights) or p.extra.get("scrub"):
                continue
            d = math.hypot(t[0] - here[0], t[1] - here[1])
            way = self._raid_way(p)
            if way is not None:
                d = min(d, self._seg_dist(here, *way))
            if my_way is not None:
                d = min(d, self._seg_dist(t, *my_way))
            rows.append([d, hm(p), p.number, p])
        is_sweep = lambda p: p.objective.type == ObjectiveType.COUNTER_AIR and p.objective.aim == "SWEEP"
        dist_of = {r[2]: r[0] for r in rows}
        dist_of[pkg.number] = 0.0
        for r in rows:
            if is_sweep(r[3]):
                cov = [dist_of[n] for n in (r[3].extra.get("covers") or []) if n in dist_of]
                if cov:
                    r[0] = max(cov)
        rows.sort(key=lambda r: (r[0], is_sweep(r[3]), r[1], r[2]))
        return [r[3] for r in rows]

    @staticmethod
    def drop_furthest(extras: list, anchor: Package | None = None) -> list:
        """S139a: `extras` (nearest first, `fly_candidates`) without the package to give up first when the mission is over the unit limit: the last one, the furthest. A Fighter Sweep
        stays while a package it covers (`extra["covers"]`) is still in the list or is `anchor`: the furthest package that is not such a sweep goes first. Replaces `_drop_one` (v0.41.131,
        latest start first; v0.41.398, S39, far raids first): the distance order covers both."""
        if not extras:
            return extras
        have = {x.number for x in extras} | ({anchor.number} if anchor is not None else set())
        def kept(x):
            return x.objective.type == ObjectiveType.COUNTER_AIR and x.objective.aim == "SWEEP" and any(n in have and n != x.number for n in (x.extra.get("covers") or []))
        k = next((i for i in range(len(extras) - 1, -1, -1) if not kept(extras[i])), len(extras) - 1)
        return extras[:k] + extras[k + 1:]

    def ruin_candidates(self, pkg: Package, extras: list) -> list:
        """Earlier packages of the same day, same area, that may already have struck when your mission starts: their targets are shown as ruins.
        Packages of this turn that start earlier, and (v0.41.337) the day's packages of earlier turns, kept in `state.plan_done` with their verdict. The closest in time first,
        at most four looked at (the builder shows at most three)."""
        if not getattr(self.settings, "ruins", True) or self.settings.merge_mode != "area":
            return []
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        have = {x.number for x in extras}
        R = self.area_radius_m()
        c = self.merge_center(pkg, R)
        if c is None:
            return []
        def inside(p):
            t = self._pkg_xy(p)
            return t is not None and math.hypot(t[0] - c[0], t[1] - c[1]) <= R
        cands = self.packages() + [Package.from_dict(d) for d in (self.state.plan_done or [])]
        out = [p for p in cands if p.number != pkg.number and p.number not in have and hm(p) < hm(pkg)
               and any(not f.tag for f in p.flights) and not p.extra.get("scrub") and inside(p)
               and not (p.objective.type == ObjectiveType.COUNTER_AIR and p.objective.aim == "SWEEP")]      # a sweep leaves nothing burning on the ground
        out.sort(key=lambda p: (-hm(p), p.number))
        return out[:4]

    def collapse(self, pkgs: list) -> list:
        """The Missions list: [(package, [packages shown inside it])]. A package that an earlier shown package folds in (it starts after it, same area)
        is listed inside that package's panel instead of as a row of its own, each with its own FLY button."""
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        absorbed, out = set(), []
        for p in sorted(pkgs, key=lambda p: (hm(p), p.number)):
            if p.number in absorbed:
                continue
            mem = [x for x in self.merge_candidates(p) if (hm(x), x.number) > (hm(p), p.number)] if self.flyable(p) else []
            absorbed |= {x.number for x in mem}
            out.append((p, mem))
        return out
