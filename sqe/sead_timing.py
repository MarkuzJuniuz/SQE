"""How a turn's SEAD / DEAD-stage packages are timed against each other and how the SEAD dice are cast.

A mixin: `Session` inherits these methods (like a C# partial class). They use `self.options`, `self.state`, `self.d`,
`self._sim()` and the other fields `Session` sets up; the callers (`plan_turn`) go through `self`.
"""
from __future__ import annotations

from .aircraft import AIRCRAFT
from .models import ObjectiveType, Role


class SeadTiming:
    def _agm88_leg_s(self, p) -> float | None:
        """Seconds from PUSH to the HARM point for this SEAD package's first HARM flight, from the same marshal, geometry and route the
        mission builder will use (an umbrella keep-out included). Within one mission every package pushes exactly its start difference after
        the others, so this leg is all that separates their HARM times."""
        from .models import BaseKind
        from . import samtier
        from .routes import assign_times, bearing, make_geometry, objective_wp, plan_route
        from . import threatmap as tm
        st = self.state
        fl = [f for f in p.flights if f.role == Role.SEAD and not f.tag and getattr(f, "base_id", None) in st.bases]
        if not fl:
            return None
        f = fl[0]
        base, spec, tgt = st.bases[f.base_id], AIRCRAFT[f.aircraft], st.assets[p.objective.target_id]
        try:
            bx, by = base.x, base.y
            if base.kind == BaseKind.CARRIER:                          # the builder slides the carrier back for the sortie: time it from there
                from .mission_builder import carrier_station
                spot = carrier_station(st, base, tgt.x, tgt.y, self.options.carrier_min_enemy_nm)
                if spot:
                    bx, by = spot[0], spot[1]
            mshl = tm.package_marshal(st, (bx, by), bearing(bx, by, tgt.x, tgt.y), (tgt.x, tgt.y), p.flights)
            g = make_geometry(bx, by, tgt.x, tgt.y, spec.profile, mshl, carrier=base.kind == BaseKind.CARRIER)
            from .strike_tasks import own_target_keep
            um = tm.umbrella_site(st, tgt)
            keep_out = []
            if um:
                keep_out.append((um.x, um.y, samtier.get(um.variant, "harm_nm")))
            own_keep = own_target_keep(tgt)                            # S153: the builder keeps the HARM point off an SA-10 target too
            if own_keep is not None:
                keep_out.append(own_keep)
            wps = plan_route(Role.SEAD, (bx, by), g, spec.profile, is_player=False, tanker_xy=None,
                             keep_out=keep_out or None)
            assign_times(wps, 0.0)
            push, obj = next(w for w in wps if w.name == "PUSH"), objective_wp(wps)
            return obj.eta_s - push.eta_s
        except Exception:
            return None

    def _sead_groups(self, pkgs: list) -> list:
        """The turn's SEAD-stage packages in connected groups: (package, its target asset, its push-to-HARM leg in seconds) lists, a package joining a group when its target is within SEAD_SYNC_KM of ANY target in it."""
        from .engine import SEAD_SYNC_KM  # the session's module imports this one, so it is imported here, when called
        import math
        st = self.state
        sead = []
        for p in pkgs:
            if p.objective.type != ObjectiveType.DEAD or not p.objective.target_id or p.objective.target_id not in st.assets:
                continue
            leg = self._agm88_leg_s(p)
            if leg is None:
                continue
            sead.append((p, st.assets[p.objective.target_id], leg))
        # v0.41.27: connected groups (a package joins if its target is close to ANY target in the group, not only the first one's): with the
        # carrier further out, the greedy version split the Gudauta cluster and its SA-11 package went in 15 minutes ahead of the others
        groups = []
        for item in sead:
            near = [g for g in groups if any(math.hypot(o[1].x - item[1].x, o[1].y - item[1].y) <= SEAD_SYNC_KM * 1000 for o in g)]
            merged = [item]
            for g in near:
                merged = g + merged
                groups.remove(g)
            groups.append(merged)
        return groups

    def _wave_times(self, pkgs: list) -> None:
        """v0.41.367 (S20 Phase 2): the turn's SEAD-stage groups (the same 60 km groups `_sync_sead` builds) get HARM times at least SAM_WAVE_GAP_MIN apart, the group nearest to blue's side first (`wave_factor`: the
        belt is rolled back, Falcon BMS style). A group keeps its own simultaneous arrival. Groups are only ever moved LATER (a group already further apart than the gap stays), so no package goes in before its wave's floor;
        the clock stays inside the day (the turn's safety net clamps the start into the turn)."""
        from .engine import SEAD_SYNC_ON, SAM_WAVE_GAP_MIN  # the session's module imports this one, so it is imported here, when called
        if not SEAD_SYNC_ON:
            return
        from .war import wave_factor
        st = self.state
        groups = self._sead_groups(pkgs)
        if len(groups) < 2:
            return
        groups.sort(key=lambda g: (-max(wave_factor(st, it[1]) for it in g), min(int(it[0].start[:2]) * 60 + int(it[0].start[3:5]) for it in g)))
        arrive = lambda it: int(it[0].start[:2]) * 60 + int(it[0].start[3:5]) + it[2] / 60.0
        last = None
        for g in groups:
            now = max(arrive(it) for it in g)
            tgt = now if last is None else max(now, last + SAM_WAVE_GAP_MIN)
            shift = round(tgt - now)
            if shift:
                for it in g:
                    p = it[0]
                    m = min(23 * 60 + 55, int(p.start[:2]) * 60 + int(p.start[3:5]) + shift)
                    p.start = f"{m // 60:02d}:{m % 60:02d}"
            last = tgt

    def _sync_sead(self, pkgs: list) -> None:
        """SEAD packages whose targets sit within SEAD_SYNC_KM of each other go in together: each one's start is moved so that its HARM time
        lands on the latest of the group (the earlier packages wait; none goes in ahead of the others). The HARM time is the package's start plus
        its real push-to-HARM-point leg (marshal, geometry and route as the builder makes them). v0.39.13-v0.39.20 used a straight line from the
        base at 400 kt, which ignored where each package marshals: the carrier's wave arrived about 3 minutes after the land-based one."""
        from .engine import SEAD_SYNC_ON  # the session's module imports this one, so it is imported here, when called
        if not SEAD_SYNC_ON:
            return
        groups = self._sead_groups(pkgs)
        for g in groups:
            if len(g) < 2:
                continue
            def arrive(item):
                p, _, leg = item
                return int(p.start[:2]) * 60 + int(p.start[3:5]) + leg / 60.0
            latest = max(arrive(it) for it in g)
            for it in g:
                shift = round(latest - arrive(it))
                if shift:
                    p = it[0]
                    m = min(23 * 60 + 55, max(0, int(p.start[:2]) * 60 + int(p.start[3:5]) + shift))
                    p.start = f"{m // 60:02d}:{m % 60:02d}"

    def _drop_orphan_followers(self, pkgs: list) -> list:
        """A follow job (STRIKE / CAS with `after`) stays only if every site it waits on still stands and has its SEAD / standoff package built."""
        from .models import SEAD_AIMS
        from .war import after_sites
        st = self.state
        have = {p.objective.target_id for p in pkgs if p.objective.type == ObjectiveType.DEAD and p.objective.aim in SEAD_AIMS}
        keep = [p for p in pkgs if all(x in have or st.assets.get(x) is None or st.assets[x].destroyed for x in after_sites(p.objective))]
        if len(keep) == len(pkgs):
            return pkgs
        for p in pkgs:
            if p not in keep:
                st.note(f"{p.objective.description}: dropped, the SEAD it was to follow could not be crewed")
        return keep

    def _stage_times(self, pkgs: list) -> None:
        """Keep each DEAD-stage package DEAD_STAGE_GAP_MIN after the SEAD-stage package of the same site (waves would otherwise spread them)."""
        from .models import SEAD_AIMS
        from .war import DEAD_STAGE_GAP_MIN, FOLLOW_GAP_MIN, after_sites
        sead = {p.objective.target_id: p for p in pkgs if p.objective.type == ObjectiveType.DEAD and p.objective.aim == "SEAD"}
        for p in pkgs:
            sp = sead.get(p.objective.target_id)
            if p.objective.type == ObjectiveType.DEAD and p.objective.aim == "DEAD" and sp is not None:
                m = min(23 * 60 + 55, int(sp.start[:2]) * 60 + int(sp.start[3:5]) + DEAD_STAGE_GAP_MIN)
                p.start = f"{m // 60:02d}:{m % 60:02d}"
        # v0.41.158: a follow job (STRIKE / CAS behind the SEAD of the long-reach sites round its target) starts FOLLOW_GAP_MIN after the latest of those packages
        stage = {p.objective.target_id: p for p in pkgs if p.objective.type == ObjectiveType.DEAD and p.objective.aim in SEAD_AIMS}
        hm = lambda q: int(q.start[:2]) * 60 + int(q.start[3:5])
        for p in pkgs:
            sps = [stage[x] for x in after_sites(p.objective) if x in stage]
            if sps:
                m = min(23 * 60 + 55, max(hm(q) for q in sps) + FOLLOW_GAP_MIN)
                p.start = f"{m // 60:02d}:{m % 60:02d}"

    def _late_sead(self, pkgs: list) -> None:
        """Test option --late-sead: every SEAD-stage package starts late_sead_min later. It runs after _stage_times, so the DEAD stage keeps its
        time and now arrives ahead of its SEAD: it reaches the gate with the radars still up and the SEAD flights still alive, which is the case
        the hold is for. Only days planned while the option is on are affected (the plan is saved with the day)."""
        n = int(getattr(self, "late_sead_min", 0) or 0)
        if n <= 0:
            return
        for p in pkgs:
            if p.objective.type == ObjectiveType.DEAD and p.objective.aim == "SEAD":
                m = min(23 * 60 + 55, int(p.start[:2]) * 60 + int(p.start[3:5]) + n)
                p.start = f"{m // 60:02d}:{m % 60:02d}"

    def _cast_sead(self, pkgs: list) -> None:
        """The dice for every SEAD package of the turn are cast now, once (seeded from the campaign, the turn and the site): the war simulation, the
        DEAD stage's briefing and the mission builder all read the same answer. Flying the SEAD package replaces it with what really happened."""
        import random as _r
        from .war import WarSimulator, chance
        st = self.state
        st.raids.setdefault("sead", {})
        sim = self._sim()
        from .models import SEAD_AIMS
        for p in pkgs:
            if p.objective.type == ObjectiveType.DEAD and p.objective.aim in SEAD_AIMS:
                rng = _r.Random(f"{st.campaign_id}:{st.turn}:{p.objective.target_id}:sead")
                st.raids["sead"][p.objective.target_id] = chance(rng, sim.sead_p(st, p), self.d.variance)
