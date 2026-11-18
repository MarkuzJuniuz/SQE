"""Ground-site, base-defence, supply and wreck spawners: the groups of every enemy site (target, route SAM belt, supply sites, armour and garrisons), the blue field defences and carrier fleet, the full-map stress test and the wrecks.

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.m`, `self.t`, `self.state`, `self.o`, `self.d`, `self.vrng`, `self.groups_by_asset`, `self.warns`
and the other fields the builder sets up. The unit budget (`_counts`, `_units_room`, `_fits`) stays in `mission_builder.py` and is called through `self`.
The module-level constants (`SITES`, `SOFT`, `TRACK_RADARS`, `BLUE_AAA_NM`, ...) and the `_vt` helper stay in `mission_builder.py`: each method imports what it uses at the start of its own body,
so a probe's `mb.NAME = ...` still takes effect.
"""
from __future__ import annotations
import copy
import math

from dcs import mapping, planes, ships, task
from dcs.unit import Skill

from . import carcass, ground, road_sites, sams
from . import seacheck as seac
from . import threatmap as tm
from .difficulty import ai_skill
from .loadouts import enemy_cap_loadout
from .models import SEAD_AIMS, AssetKind, BaseKind, ObjectiveType
from .raid_spawns import supply_parts
from .routes import FT, NM, bearing, dist, offset
from .strike_tasks import KPH


class SiteSpawns:
    def _spawn_supply_in_radius(self, package, tx, ty, manifest, only_raid: bool = False, max_units: int | None = None) -> None:
        """v0.41.209 (XO 2026-10-30): every live supply site (fuel farm, depot) of BOTH sides inside the merge radius round the target is in the mission, so a
        pilot who flies past a depot sees it. The radius is the Settings > Mission Build merge radius (the performance knob). Built last (after every flight and
        patrol), nearest first, while the unit limit has room: the rest are left out with a warning, and nothing else is pushed out for them (wrecks fit after).
        v0.41.220 (XO 2026-10-31): a raid scramble's target gets the same circle (`self._raid_xy`; the CAP station that centres the mission is up to 40 nm out from
        it). `only_raid` measures from the raid targets only and `max_units` caps what that call builds: the first call runs BEFORE the raiders and the alert pairs,
        because the raid's own load had already used the whole unit limit and the sites round its target were the first thing left out."""
        from .mission_builder import SUPPLY_BUILDINGS, SOFT, SOFT_WAKE_NM  # the builder's module imports this one
        st, o = self.state, self.o
        if o.full_map:
            return
        R = max(5.0, float(o.merge_radius_nm)) * NM
        centres = list(getattr(self, "_raid_xy", [])) + ([] if only_raid else [(tx, ty)])
        if not centres:
            return
        cands = []
        for a in st.assets.values():
            if a.kind in SUPPLY_BUILDINGS and not a.destroyed and a.id not in self.groups_by_asset:
                cands.append((min(dist(a.x, a.y, cx, cy) for cx, cy in centres), a.id, "red", a))
        for aid, a in st.blue_assets.items():
            if a.kind in SUPPLY_BUILDINGS and not a.destroyed and aid not in self._supply_built:
                cands.append((min(dist(a.x, a.y, cx, cy) for cx, cy in centres), aid, "blue", a))
        cands = sorted((c for c in cands if c[0] <= R), key=lambda c: (c[0], c[1]))
        if not cands:
            return
        home = min((b for b in st.bases.values() if b.kind == BaseKind.AIRFIELD), key=lambda b: dist(b.x, b.y, tx, ty), default=None)
        built = used = 0
        dorm_on = bool(o.dormant_sites) and not only_raid                  # S89 B2: red's guards sleep (never what a raid is about)
        for d_, aid, side, a in cands:
            bld_ = math.ceil(len(supply_parts(a.kind, a.variant)) * o.wreck_static_weight)
            guard_ = ((road_sites.guard_units(a, self.d.level) if road_sites.is_road(a) else 1) if side == "red" else 0)
            need = bld_ + guard_         # v0.41.221: the buildings count like wrecks (wreck_static_weight), and red's Shilka guard is a whole unit
            dorm_ = dorm_on and side == "red"
            if self._units_room() < need or (max_units is not None and used + need > max_units):       # S89 B2: a sleeping guard counts whole, as with the setting off
                break
            if side == "red":
                self._spawn_site(a, SOFT.get(a.kind), manifest, primary=False)
                if dorm_:
                    self._make_dormant(a, SOFT_WAKE_NM)
            elif home is not None:
                self._spawn_raid_target(package, home, aid, a.x, a.y, manifest)
            built += 1
            used += need
        if built < len(cands) and max_units is None:
            self.warns.append(f"{len(cands) - built} supply sites inside the {o.merge_radius_nm} nm merge radius left out to stay under the {o.max_units}-unit limit (furthest first)")

    def _place_carcasses(self) -> None:
        """Wrecks for every damaged or destroyed ground site near the route. Trimmed to what fits under the unit limit: the furthest
        from the route go first, and this runs after everything live is placed, so wrecks never push a flight out."""
        from .mission_builder import SITES, SOFT, _vt  # the builder's module imports this one
        o, st = self.o, self.state
        if not o.carcasses:
            return
        w = max(0.05, float(o.wreck_static_weight))
        budget = int(max(0, self._units_room()) / w)
        if budget <= 0:
            return
        ok = lambda x, y: seac.site_ok(x, y, 60.0)
        cands = []
        for a in st.assets.values():
            if a.kind == AssetKind.AIRFIELD or a.health >= 0.999:
                continue
            dnm = tm.poly_dist(a.x, a.y, self._poly) / NM
            if dnm > o.carcass_range_nm:
                continue
            centre = self.site_pos.get(a.id) or carcass.stable_center(a, st.campaign_id, ok)
            for k, wr in enumerate(carcass.wrecks_for(a, st.campaign_id, centre, SITES, SOFT, ok)):
                cands.append((dnm, a.id, k, wr))
        cands.sort(key=lambda c: (c[0], c[1], c[2]))
        placed = 0
        for dnm, aid, k, wr in cands[:budget]:
            vt = _vt(wr["type"])
            if vt is None:
                continue
            self.m.static_group(self.red, f"WRECK {aid} {k + 1}", vt, mapping.Point(wr["x"], wr["y"], self.t), heading=wr["hdg"], dead=True)
            placed += 1
        if len(cands) > placed:
            self.warns.append(f"{len(cands) - placed} wrecks left out to stay under the {o.max_units}-unit limit (furthest from your route first)")

    def _place_base(self, base, tx, ty, near=None, dormant: bool = False):
        """v0.41.220: `near` = (x, y) of a raid target this field is built to cover (a neighbour of the raided field): it then gets only what reaches that point, the
        Patriot inside PATRIOT_NM, the HAWK inside HAWK_NM, the AAA inside COVER_AAA_NM (a full field is about 30 units).
        S89 C: `dormant=True` puts every group it builds to sleep (late-activated, tagged, listed in `_dormant_blue` with its ring). Returns the groups built."""
        from .mission_builder import F, BLUE_AAA_NM  # the builder's module imports this one
        o = self.o
        built = []
        from .raids import HAWK_NM as _HN, PATRIOT_NM as _PN

        def keep(g, x, y, ring):
            if g is not None:
                built.append(g)
                if dormant:
                    g.late_activation = True
                    self._tag_dormant(g)
                    self._dormant_blue.append((x, y, ring, g))
            return g
        from . import fleet as _fleet
        if base.kind == BaseKind.CARRIER and _fleet.sunk(self.state):      # v0.41.257: the ship is on the bottom: no carrier group in the mission
            return built
        if base.kind == BaseKind.AIRFIELD:
            self.apt[base.id] = self.t.airports[base.airport]
            bt = dict(sams.blue_battery(base, self.state))      # v0.41.30: doctrinal batteries, every field alike; v0.41.62: read from the field's three sites (sams.py)
            if near is not None:                                 # v0.41.220: a covering neighbour builds only what reaches the raid's target
                from .raids import HAWK_NM, PATRIOT_NM
                from .raid_spawns import COVER_AAA_NM
                dn_ = dist(base.x, base.y, near[0], near[1]) / NM
                if dn_ > PATRIOT_NM:
                    bt["patriot_ln"] = 0
                if dn_ > HAWK_NM:
                    bt["hawk"] = False
                if dn_ > COVER_AAA_NM:
                    bt["aaa"] = 0
            if o.base_defenses and (bt["patriot_ln"] or bt["aaa"] or bt["hawk"]):
                p = self.apt[base.id].position
                # v0.41.7: the Patriot faces the threat (the nearest enemy fighter field; was a direction picked from the base's name: a Patriot
                # radar covers about 120 degrees, so a raid from the wrong side met none). Short-range sites on both sides of the field, and a
                # HAWK battery as the middle layer at your home field. A degraded field (below 0.6) keeps the Patriot with 1 launcher and one site.
                ang = tm.nearest_threat_bearing(self.state, p.x, p.y, bearing(p.x, p.y, tx, ty))
                dry = lambda a0, d0: next(((px, py) for k in range(12) for px, py in [offset(p.x, p.y, a0 + (30 * ((k + 1) // 2)) * (1 if k % 2 else -1), d0)]
                                           if seac.site_ok(px, py, 300.0) and not self._on_runway(px, py, 150.0)), offset(p.x, p.y, a0, d0))           # the nearest bearing that is dry land
                sites_ = sams.blue_sites(self.state, base)
                def site_at(key, a0, d0):               # v0.41.64: the site's own position (doctrinal bearing + seeded jitter, sams.place_blue_site); the old search if it falls on a runway
                    a_ = sites_.get(key)
                    px, py = (a_.x, a_.y) if a_ is not None else sams.place_blue_site(self.state, base, key)
                    return (px, py) if seac.site_ok(px, py, 300.0) and not self._on_runway(px, py, 150.0) else dry(a0, d0)
                x, y = site_at("pat", ang, 4500)
                if bt["patriot_ln"]:
                    self.base_ad.setdefault(base.id, {})["pat"] = keep(self._platoon(self.usa, f"BASEDEF {base.name} Patriot", [("Patriot_str", 1), ("Patriot_ECS", 1), ("Patriot_cp", 1),
                                  ("Patriot_EPP", 1), ("Patriot_ln", bt["patriot_ln"])], x, y, ang, F.Star, spacing=sams.BLUE_SPACING_M, base_def=True), x, y, _PN)
                x, y = site_at("aaa", ang + 120, 3500)
                if bt["aaa"]:
                    keep(self._platoon(self.usa, f"BASEDEF {base.name} AAA", [("Vulcan", 2), ("M1097_Avenger", 2 if bt["aaa"] >= 2 else 1)], x, y, ang, F.Line, base_def=True), x, y, BLUE_AAA_NM)
                if bt["aaa"] >= 2:
                    x, y = site_at("aaa2", ang - 120, 3500)
                    keep(self._platoon(self.usa, f"BASEDEF {base.name} AAA 2", [("Vulcan", 1), ("M1097_Avenger", 2)], x, y, ang, F.Line, base_def=True), x, y, BLUE_AAA_NM)
                if bt["hawk"]:
                    x, y = site_at("hawk", ang + 50, 6000)
                    self.base_ad.setdefault(base.id, {})["hawk"] = keep(self._platoon(self.usa, f"BASEDEF {base.name} HAWK", [("Hawk_sr", 1), ("Hawk_tr", sams.BLUE_HAWK_TR), ("Hawk_pcp", 1), ("Hawk_cwar", 1),
                                  ("Hawk_ln", sams.BLUE_HAWK_LN)], x, y, ang, F.Star, spacing=sams.BLUE_SPACING_M, base_def=True), x, y, _HN)
            return built
        hdg = getattr(self, '_cv_hdg', {}).get(base.id)
        if hdg is None:
            hdg = (bearing(base.x, base.y, tx, ty) + 180) % 360
        pos = mapping.Point(base.x, base.y, self.t)
        cv = self.m.ship_group(self.usa, base.name, ships.Stennis, pos, heading=hdg)      # legacy free CVN-74: no deck crew
        cv.add_waypoint(pos.point_from_heading(hdg, 120 * NM), speed=o.carrier_speed_kts * KPH)
        uid = cv.units[0].id
        p0 = cv.points[0]
        p0.add_task(task.ActivateBeaconCommand(channel=int(o.carrier_tacan[:-1]), modechannel=o.carrier_tacan[-1], callsign="STN", unit_id=uid, aa=False))
        p0.add_task(task.ActivateICLSCommand(channel=o.carrier_icls, unit_id=uid))
        p0.add_task(task.ActivateLink4Command(frequency=o.carrier_link4_mhz, unit_id=uid))
        p0.add_task(task.ActivateACLSCommand(unit_id=uid))
        cv.set_frequency(int(o.carrier_atc_mhz * 1e6))
        self.ship[base.id] = cv
        if o.carrier_escorts:      # the fleet is never alone: a cruiser and two escorts station-keeping on the carrier
            for k, (cls, ang, nm) in enumerate(((ships.TICONDEROG, 40, 3.0), (ships.USS_Arleigh_Burke_IIa, -40, 3.0), (ships.PERRY, 180, 3.5))):
                if _fleet.escort_out(self.state, k):               # v0.41.257: a sunk escort is missing until it is replaced
                    continue
                ex, ey = offset(base.x, base.y, hdg + ang, nm * NM)
                ep = mapping.Point(ex, ey, self.t)
                eg = self.m.ship_group(self.usa, f"{base.name} escort {k + 1}", cls, ep, heading=hdg)
                eg.add_waypoint(ep.point_from_heading(hdg, 120 * NM), speed=o.carrier_speed_kts * KPH)

    def _spawn_everything(self, package, manifest, tx, ty) -> None:
        """Full-map stress test: no restrictions. Every live enemy site, column, garrison, support site and early-warning radar is built; every friendly
        airfield gets its defences, garrison and supply sites; every friendly sector with troops gets its column; every planned enemy patrol is
        airborne at its station. The target and your package are unchanged. A mission this size may not load well in VR: that is the point."""
        from .mission_builder import SITES, SOFT, ENEMY_FIGHTERS  # the builder's module imports this one
        st, d = self.state, self.d
        for a in sorted(st.assets.values(), key=lambda a: a.id):
            if a.destroyed or a.id in self.groups_by_asset:
                continue
            comp = SITES.get(a.variant) if a.kind in (AssetKind.SAM, AssetKind.EWR) else SOFT.get(a.kind)
            if comp:
                self._spawn_site(a, comp, manifest, primary=False)
        for b in st.bases.values():
            if b.kind == BaseKind.AIRFIELD and b.id not in self.apt:
                self._place_base(b, tx, ty)
        home = min((b for b in st.bases.values() if b.kind == BaseKind.AIRFIELD), key=lambda b: dist(b.x, b.y, tx, ty), default=None)
        if home is not None:
            for aim, ba in sorted(st.blue_assets.items()):
                if ba.destroyed:
                    continue
                if (ground.sector_of(st, aim) is not None) and ground.blue_strength(st, ground.sector_of(st, aim)) < ground.MIN_FORCE:
                    continue                                # full map: no blue forward position in a sector Blue no longer holds
                base = st.bases.get(ba.guards) or home
                self._spawn_raid_target(package, base, aim, ba.x, ba.y, manifest)
            g = st.ground or {}
            for i, v in enumerate(g.get("blue", [])):
                if v >= ground.MIN_FORCE and i < len(g.get("centers", [])):
                    c = g["centers"][i]
                    self._spawn_raid_target(package, home, f"sector:{i}", float(c[0]), float(c[1]), manifest)
        skill = getattr(Skill, ai_skill(self.o, "red", d), Skill.High)
        pt = lambda x, y: mapping.Point(x, y, self.t)
        for n, pf in enumerate((st.red_air or {}).get("flights", [])):
            a = st.assets.get(pf["wing"])
            if a is None or a.destroyed or pf["type"] not in ENEMY_FIGHTERS:
                continue
            fx_, fy_, fa_ = self._sep(pf["x"], pf["y"], 22000 * FT, 0.0)
            g = self.m.flight_group(self.red, f"FM Bandit {n + 1}", getattr(planes, pf["type"]), None, pt(fx_, fy_), altitude=fa_, speed=400 * KPH,
                                    maintask=task.CAP, group_size=2)
            g.set_skill(skill)
            load = enemy_cap_loadout(pf["type"])
            names = []
            for j, u in enumerate(g.units, 1):
                u.name = f"ENM-FM-{pf['wing']}-{n}-{j}"; u.pylons = copy.deepcopy(load); names.append(u.name); self._note_jam(u)
            manifest.add("enemy_air", pf["wing"], names, ac=pf["type"])

    def _spawn_opfor_ground(self, package, tx, ty, manifest, polyline=None, route_sites=None, route_near=None, all_sams=False):
        from .mission_builder import SITES, SOFT, SUPPLY_BUILDINGS, RAID_SAM_RESERVE, SOFT_WAKE_NM  # the builder's module imports this one
        st, obj = self.state, package.objective
        from .war import blinded_today
        # the DEAD stage of a SEAD-first pair: if the SEAD package blinded the site (the day's verdict), its radars are already gone when the mission starts
        self._blind_site = {obj.target_id} if (obj.type == ObjectiveType.DEAD and obj.aim == "DEAD" and blinded_today(st, obj.target_id)) else set()
        fol_ = []
        if obj.type in (ObjectiveType.STRIKE, ObjectiveType.CAS) and obj.after:      # v0.41.158: behind a SEAD: the sites it waits on are live in this mission, those the SEAD blinded without their radars
            from .war import after_sites, site_blind_today
            fol_ = [st.assets[x] for x in after_sites(obj) if x in st.assets and not st.assets[x].destroyed]
            staged_ = {x.objective.target_id for x in getattr(self, "_extras", []) if x.objective.type == ObjectiveType.DEAD and x.objective.aim in SEAD_AIMS}
            self._blind_site |= {a.id for a in fol_ if site_blind_today(st, a.id) and a.id not in staged_}      # a SEAD flown in this mission blinds it for real
        if obj.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            tgt, relevant = None, []            # no ground target, but enemy SAMs whose rings touch the route / station stay live
        else:
            tgt = st.assets[obj.target_id]
            dfn = sorted((st.assets[i] for i in tgt.defended_by if not st.assets[i].destroyed), key=lambda x: dist(x.x, x.y, tgt.x, tgt.y))
            relevant = [tgt] + dfn[:2]                                                   # the two nearest defenders; more only costs VR frame rate
            relevant += [g for g in st.assets.values() if g.guards == tgt.id]            # a SAM site's dug-in garrison is part of its cluster
            relevant += fol_
        route_ids = set()
        extra_ids_ = set()                   # v0.41.291: the SAM sites `all_sams` adds beyond the route's own (they leave RAID_SAM_RESERVE units free for the flights built after)
        if polyline:                         # every SAM site whose ring touches the route is live from the start
            cs_ = tm.corridor_sam_sites(st, polyline, tgt, **({"max_route": route_sites} if route_sites else {}))
            if all_sams:                     # v0.41.291 (XO 2026-11-04: "spawn all red SAMs", the carrier-defence setpiece only): every live SAM site, not just the ones whose ring touches the route
                have_ = {a_.id for a_ in cs_}
                extra_ = [a_ for a_ in st.assets.values() if a_.kind == AssetKind.SAM and not a_.destroyed and a_.id not in have_]
                cs_ = cs_ + extra_
                extra_ids_ = {a_.id for a_ in extra_}
            if route_near is not None:                                  # v0.41.285: nearest to this point first, so the unit limit trims the furthest (see `_spawn_raid`)
                cs_.sort(key=lambda a_: (a_.id in extra_ids_, dist(a_.x, a_.y, route_near[0], route_near[1])))      # (v0.41.291: the route's own sites first, then the extras `all_sams` adds)
            route_ids = {a_.id for a_ in cs_}
            relevant += cs_
        ewrs = sorted((a for a in st.assets.values() if a.kind == AssetKind.EWR and not a.destroyed),
                      key=lambda a: tm.poly_dist(a.x, a.y, polyline) if polyline else dist(a.x, a.y, tx, ty))
        relevant += [a for a in ewrs[:2] if (tm.poly_dist(a.x, a.y, polyline) if polyline else 0) < 80 * NM]
        keep_live_ = ({tgt.id} | set(tgt.defended_by) | {g_.id for g_ in st.assets.values() if g_.guards == tgt.id} | {a_.id for a_ in fol_}) if tgt is not None else set()
        dormant_on_ = bool(self.o.dormant_sites) and bool(polyline)      # S89 B1: the route's SAM sites sleep (never the target, its defenders, its garrison or a `fol_` site)
        seen = set()
        cut_ = False                                                    # v0.41.285: once a route site does not fit, the rest of them (further out) are left out too
        cut_names_ = []
        for a in relevant:
            if a.id in seen or a.destroyed:
                continue
            seen.add(a.id)
            is_tgt = tgt is not None and a.id == tgt.id
            if a.id in self.groups_by_asset:           # already live for another package of this mission: shared world, never twice
                if is_tgt:
                    manifest.mark_primary(a.id, manifest.cur_pkg or package.id)
                continue
            comp = SITES.get(a.variant) if a.kind in (AssetKind.SAM, AssetKind.EWR) else SOFT.get(a.kind)
            sz_ = sum(n_ for _, n_ in (comp or []))
            soft_ = a.kind in (AssetKind.C2, AssetKind.AIRFIELD) or a.kind in SUPPLY_BUILDINGS or (a.kind == AssetKind.ARMOR and a.variant == "GARRISON")       # S89 B2: soft sites and garrisons (never an armour column, never an EWR)
            dorm_ = dormant_on_ and a.id not in keep_live_ and ((a.kind == AssetKind.SAM and a.id in route_ids) or soft_)
            if route_near is not None and a.id in route_ids and a.id not in self.groups_by_asset and (cut_ or not self._fits(sz_, (RAID_SAM_RESERVE if a.id in extra_ids_ else 0))):
                cut_ = True
                if all_sams:
                    cut_names_.append(a.name)                            # one warning for the whole tail (v0.41.291: up to every SAM site is a candidate)
                else:
                    self.warns.append(f"{a.name}: left out to stay under the unit limit (furthest from the intercept point first)")
                continue
            if comp and route_sites and not self._fits(sz_):
                self.warns.append(f"{a.name}: left out to stay under the unit limit")        # v0.41.256: the raid's extra route sites never push the mission over it
                continue
            if comp:
                self._spawn_site(a, comp, manifest, primary=is_tgt)
                g_ = self.groups_by_asset.get(a.id)
                if dorm_ and g_ is not None:                         # S89 B1: asleep until `_wire_dormant` hands it to a detector (or its own ring)
                    self._make_dormant(a, SOFT_WAKE_NM if soft_ else tm.RANGE_NM.get(a.variant, 0))
        if cut_names_:
            self.warns.append(f"{len(cut_names_)} SAM sites left out to stay under the {self.o.max_units}-unit limit (furthest from the intercept point first): " + ", ".join(cut_names_[:6]) + (", ..." if len(cut_names_) > 6 else ""))

    def _spawn_site(self, a, comp, manifest, primary):
        """ONE group per site: a SAM battery needs its search/track radars, launchers and command post together."""
        from .mission_builder import F, _vt, ARMOR_DENSITY, SUPPLY_BUILDINGS, TRACK_RADARS, SEARCH_RADARS  # the builder's module imports this one
        r = self.vrng
        skill = getattr(Skill, ai_skill(self.o, "red", self.d), Skill.High)
        garrison = a.kind == AssetKind.ARMOR and a.variant == "GARRISON"
        comp = self._armor_site_comp(a) if a.kind == AssetKind.ARMOR else (
            road_sites.guard_comp(a, self.d.level) if road_sites.is_road(a) else self._vary_comp(a, comp))        # v0.41.241: a road site's guard follows its level and variant
        cx, cy = self._site_center(a)
        base_count = sum(n for vname, n in comp if _vt(vname) is not None)
        bld = []
        if a.kind in SUPPLY_BUILDINGS:                  # v0.41.192: fuel farm / depot = real buildings, guarded by the Shilka group
            bld = self._place_buildings(self.red, a.id, a.kind, cx, cy, r.randint(0, 359), scale=a.health, variant=a.variant)
            base_count += len(supply_parts(a.kind, a.variant))
            gx, gy = self._guard_spot(a.id, cx, cy)         # v0.41.376 (S10): the guard stands at the edge of the layout facing blue, not inside it
            cx, cy = gx, gy
        if garrison:
            fb = self._nearest_airfield(cx, cy)
            heading, form = int(bearing(cx, cy, fb.x, fb.y)), r.choice([F.Rectangle, F.Scattered, F.Star])
        elif a.kind == AssetKind.ARMOR:
            fb = self._nearest_airfield(cx, cy)
            heading, form = int(bearing(cx, cy, fb.x, fb.y)), r.choice([F.Line, F.Rectangle, F.Line])
        else:
            heading, form = r.randint(0, 359), r.choice([F.Star, F.Scattered, F.Rectangle])
        column = a.kind == AssetKind.ARMOR and not garrison and ground.zone_of(self.state, a.id) is not None
        scale = (ARMOR_DENSITY[0] + ARMOR_DENSITY[1] * a.health) if column else a.health         # a front-line column is as dense as its sector is strong
        if bld:
            scale = 1.0                                 # the guard is always there; the damage shows in the buildings
        g = self._platoon(self.red, a.id, comp, cx, cy, heading, form, scale=scale)
        if g is None:
            return
        if column:
            base_count = max(1, round(len(g.units) / max(0.05, a.health)))                      # the count at full health, so losses read back as health
        if a.kind == AssetKind.SAM and (a.suppressed or a.id in self._blind_site):
            gone = [u for u in g.units if str(getattr(u, "type", "")) in TRACK_RADARS | SEARCH_RADARS]
            for u in gone:
                g.units.remove(u)
            base_count = max(1, base_count - len(gone))      # the radars were already destroyed: not damage this mission caused
        if a.kind != AssetKind.SAM:
            self._ground_orders(g)                      # v0.41.39: armour columns and garrisons fight on explicit orders
        names = []
        for k, u in enumerate(g.units, 1):
            u.name = f"{a.id}|{k}"
            try:
                u.skill = skill
            except Exception:
                pass
            names.append(u.name)
        names += bld
        self.groups_by_asset[a.id] = g
        if a.kind == AssetKind.ARMOR:
            self.armor_id, self.armor_center = a.id, (cx, cy)
        mine = bool(primary) and (not manifest.cur_pkg or manifest.cur_pkg == self._anchor_id)
        trk = [u.name for u in g.units if str(getattr(u, "type", "")) in TRACK_RADARS]
        srch = [u.name for u in g.units if str(getattr(u, "type", "")) in SEARCH_RADARS]
        manifest.add("asset", a.id, names, base_count=base_count, health_before=a.health, primary=mine, label=a.name, trk=trk, srch=srch,
                     primary_pkgs=[manifest.cur_pkg] if (primary and manifest.cur_pkg) else [])
