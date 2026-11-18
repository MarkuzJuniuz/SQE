"""Site geometry and compositions: where an enemy site's centre sits, how a platoon is laid out, what a column or garrison carries, and the runway keep-out helpers.

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.m`, `self.t`, `self.state`, `self.o`, `self.vrng`, `self.site_pos` and the other fields the builder sets up.
The module-level constants (`RUNWAY_HALF_LEN_M`, `SITES`, `SOFT`, ...) and the `_vt` helper stay in `mission_builder.py`: each method imports what it uses at the start of its own body,
so a probe's `mb.NAME = ...` still takes effect.
"""
from __future__ import annotations
import math

from dcs import mapping
from dcs.unit import Skill

from . import seacheck as seac
from .difficulty import ai_skill
from .models import AssetKind, BaseKind
from .routes import bearing, dist, offset


class SiteLayout:
    def _platoon(self, country, name, comp, x, y, heading, formation, scale=1.0, spacing=None, base_def=False):
        from .mission_builder import _vt, F, BLUE_BASE_DEF_SKILL  # the builder's module imports this one
        types = []
        for vname, n in comp:
            vt = _vt(vname)
            if vt is None:
                self.warns.append(f"unknown vehicle {vname}; skipped")
                continue
            types += [vt] * max(1, round(n * scale))
        if not types:
            return None
        g = self.m.vehicle_group_platoon(country, name, types, mapping.Point(x, y, self.t), heading=int(heading) % 360, formation=formation)
        if spacing and formation == F.Star:                  # pydcs lays a star out 20 m apart; a wider one for SAM batteries
            g.formation_star(int(heading) % 360, spacing)
        bs = ai_skill(self.o, "blue", self.d, ground=True) if country is self.usa else None      # v0.41.70: blue base defences follow the Blue skill when it is set
        if base_def:                                         # v0.41.222 (XO 2026-10-31): blue's base SAMs and AAA are always Excellent, whatever the Blue skill setting says
            bs = BLUE_BASE_DEF_SKILL
        if bs:
            g.set_skill(getattr(Skill, bs, Skill.High))
        return g

    def _nearest_airfield(self, x, y):
        return min((b for b in self.state.bases.values() if b.kind == BaseKind.AIRFIELD), key=lambda b: dist(b.x, b.y, x, y))

    def _site_center(self, a):
        from .mission_builder import SITES, SOFT  # the builder's module imports this one
        if a.id in self.site_pos:
            return self.site_pos[a.id]
        r = self.vrng
        if a.kind == AssetKind.AIRFIELD:
            pos = (a.x, a.y)
        elif a.kind == AssetKind.ARMOR and a.variant == "GARRISON":
            pos = offset(a.x, a.y, r.uniform(0, 360), r.uniform(0, 400))
        elif a.kind == AssetKind.ARMOR:       # the column sits somewhere along its axis of advance
            fb = self._nearest_airfield(a.x, a.y)
            pos = offset(a.x, a.y, bearing(a.x, a.y, fb.x, fb.y), r.uniform(-1500, 1500))
        else:
            pos = offset(a.x, a.y, r.uniform(0, 360), r.uniform(0, 900))
        if a.kind != AssetKind.AIRFIELD and not seac.site_ok(pos[0], pos[1], min(600.0, seac.SITE_MARGIN)):
            pos = (a.x, a.y)                  # the random shift would put it in the sea: keep the site where it is (it is on land)
        pos = self._off_runway(pos[0], pos[1], 150.0 + 20.0 * len(SITES.get(a.variant) or SOFT.get(a.kind) or []))      # v0.41.48
        self.site_pos[a.id] = pos
        return pos

    def _guard_spot(self, aim, cx, cy):
        """v0.41.376 (S10): where a supply site's guard group stands: just outside the buildings (`_bld_xy`), on the side of the nearest blue airfield (red's threat
        axis: the front is where blue's fighters come from). The next sides round if that spot is water or too close to a building; (cx, cy) if none works."""
        bl = self._bld_xy.get(aim) or []
        if not bl:
            return cx, cy
        mx, my = sum(p[0] for p in bl) / len(bl), sum(p[1] for p in bl) / len(bl)
        fb = self._nearest_airfield(mx, my)
        t0 = bearing(mx, my, fb.x, fb.y)
        for da in (0, 45, -45, 90, -90, 135, -135, 180):
            t = t0 + da
            ux, uy = offset(0.0, 0.0, t, 1.0)               # unit step of that bearing
            ext = max((p[0] - mx) * ux + (p[1] - my) * uy for p in bl)
            gx, gy = offset(mx, my, t, max(0.0, ext) + self.GUARD_CLEAR_M)
            if seac.site_ok(gx, gy) and min(dist(gx, gy, p[0], p[1]) for p in bl) >= self.GUARD_CLEAR_M * 0.9:
                return gx, gy
        return cx, cy

    def _on_runway(self, x, y, margin):
        """v0.41.48: True when a group centred here (its footprint about `margin` m) would sit on a runway and block the side that uses it.
        pydcs gives each runway only a heading, so the strip is modelled as a corridor through the airfield reference point:
        RUNWAY_HALF_LEN_M each way, RUNWAY_HALF_WIDTH_M either side, plus the group's own margin (a judgment call, not a surveyed runway)."""
        from .mission_builder import RUNWAY_HALF_LEN_M, RUNWAY_HALF_WIDTH_M  # the builder's module imports this one
        for ap in self.t.airports.values():
            ax, ay = ap.position.x, ap.position.y
            if abs(x - ax) > RUNWAY_HALF_LEN_M + margin + 500 or abs(y - ay) > RUNWAY_HALF_LEN_M + margin + 500:
                continue
            for rw in ap.runways:
                h = math.radians(rw.heading)
                dx, dy = x - ax, y - ay
                along = dx * math.cos(h) + dy * math.sin(h)
                across = -dx * math.sin(h) + dy * math.cos(h)
                if abs(along) < RUNWAY_HALF_LEN_M + margin and abs(across) < RUNWAY_HALF_WIDTH_M + margin:
                    return True
        return False

    def _off_runway(self, x, y, margin):
        """Move a site centre sideways, off any runway corridor, to the nearest clear dry spot (unchanged when already clear)."""
        if not self._on_runway(x, y, margin):
            return (x, y)
        for d in range(150, 2401, 150):
            for ang in range(0, 360, 30):
                px, py = offset(x, y, ang, d)
                if not self._on_runway(px, py, margin) and seac.site_ok(px, py, min(600.0, seac.SITE_MARGIN)):
                    return (px, py)
        return (x, y)

    def _vary_comp(self, a, comp):
        r, out = self.vrng, []
        for name, n in comp:
            if a.kind in (AssetKind.SAM, AssetKind.EWR) and n >= 3:
                n = max(2, n + r.choice([-1, 0, 0, 1]))
            elif a.kind in (AssetKind.C2, AssetKind.FUEL, AssetKind.DEPOT, AssetKind.AIRFIELD):
                n = max(1, n + r.randint(-1, 2))
            out.append((name, n))
        if a.kind == AssetKind.SAM and r.random() < 0.45:
            out.append((r.choice(["ZSU_23_4_Shilka", "SA_18_Igla_manpad", "Ural_375_ZU_23"]), r.randint(1, 2)))
        if a.kind == AssetKind.C2 and r.random() < 0.5:
            out.append(("Ural_375", r.randint(1, 3)))
        return out

    def _garrison_comp(self):
        """A dug-in garrison: fewer vehicles than a column, no one is advancing. Bigger at higher difficulty."""
        r, k = self.vrng, self.d.garrison_size
        comp = [(r.choice(["T_72B", "T_80B"]), max(1, round(r.randint(2, 3) * k))), (r.choice(["BMP_2", "BMP_1"]), max(1, round(r.randint(1, 2) * k))),
                ("ZSU_23_4_Shilka", 1), ("Ural_375", r.randint(0, 1))]
        if self.d.level >= 3:
            comp.append(("Strela_10M3", 1))
        return comp

    def _armor_site_comp(self, a):
        """S92b: an armor column's / garrison's composition, rolled once per mission and cached, so the CAS planner (which runs before the group is built) sees the air defence it will really carry."""
        if a.id not in self._armor_comps:
            self._armor_comps[a.id] = self._garrison_comp() if a.variant == "GARRISON" else self._armor_comp()
        return self._armor_comps[a.id]

    def _site_types(self, a):
        """S92b: the DCS type strings an asset's group will carry (profiles.area_ad's `comp_types`); None = unknown (counted as a Shilka)."""
        from .mission_builder import _vt  # the builder's module imports this one
        if a.kind != AssetKind.ARMOR:
            return None
        return [getattr(_vt(n), "id", "") for n, c in self._armor_site_comp(a) if c > 0]

    def _armor_comp(self):
        r = self.vrng
        comp = [(r.choice(["T_72B", "T_72B", "T_80B", "T_80UD"]), r.randint(3, 6)), (r.choice(["BMP_2", "BMP_1", "BMP_3"]), r.randint(2, 5)),
                (r.choice(["BTR_80", "BTR_70", "BTR_60"]), r.randint(1, 3)), ("ZSU_23_4_Shilka", r.randint(0, 2)), ("Ural_375", r.randint(0, 3))]
        if r.random() < 0.4:
            comp.append((r.choice(["Strela_10M3", "Osa_9A33_ln"]), 1))       # mobile air defence travelling with the column
        return [(n, c) for n, c in comp if c > 0]
