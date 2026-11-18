"""S89 dormant sites: the sleep / wake wiring of the mission builder (late-activated red SAM / EWR sites and blue airfield defences, the detector triggers that wake them, the sleep triggers that put them back to AI OFF, the dcs.log lines).

A mixin: `MissionBuilder` inherits these methods (like a C# partial class). They use `self.state`, `self.o`, `self.groups_by_asset`, `self.mission`
and the dormant fields the builder sets up in `__init__` (`_dormant`, `_dormant_sites`, `_dormant_blue`, `_dormant_red_added`, `_dormant_fields`);
`_late` / `_late_flag` and the unit budget (`_counts`, `_units_room`, `_fits`) stay in the builder. The constants (`S89_LOG`, `DORMANT_SLEEP`, `WAKE_MARGIN_NM`, ...) stay in `mission_builder.py`:
each method imports what it uses at the start of its own body, so a probe's `mb.DORMANT_SLEEP = False` still takes effect.
"""
from __future__ import annotations
from dcs import action, condition, triggers
from dcs.translation import String

from . import detection
from . import threatmap as tm
from .models import AssetKind, BaseKind
from .routes import NM, dist


def _covered(det, a) -> bool:
    """(x, y, radius nm) round a detector holds the group's asset."""
    return dist(det[0], det[1], a.x, a.y) <= det[2] * NM


def _route_dist(poly, x, y) -> float:
    """Distance from (x, y) to the route polyline; 0.0 when the route has fewer than two points."""
    return tm.poly_dist(x, y, poly) if len(poly) >= 2 else 0.0


class DormantSites:
    def _make_dormant(self, a, ring_nm, free: bool = False):
        """S89: put the group just built for asset `a` to sleep (late-activated, tagged, handed to `_wire_dormant` with its ring radius in nm). One recipe for the
        route SAM sites (B1) and the soft sites / garrisons (B2)."""
        g = self.groups_by_asset.get(a.id)
        if g is None:
            return None
        g.late_activation = True
        if free:                                  # an added group (S89 F): the unit limits ignore it
            self._tag_dormant(g)
        self._dormant_sites.append((a, g, ring_nm))
        return g

    def _tag_dormant(self, g):
        """S89: tag a group as dormant (late-activated until a detector wakes it) so `_counts` weighs it DORMANT_WEIGHT. Tag the group, never test `late_activation`
        alone: flights, alert pairs and reliefs are late-activated for timing and must keep counting whole. Called by `_make_dormant` and `_dormant_red_extras`."""
        if g is not None:
            self._dormant.add(g.id)
        return g

    def _dormant_red_extras(self, tx, ty, manifest, kinds=(AssetKind.EWR, AssetKind.SAM)) -> None:
        """S89 F (setting `dormant_sites`, XO 2026-11-17): the mission is built as before; then every red EWR and SAM site still alive in the war that is not in it yet is added,
        with NO unit-limit check (the added groups are tagged, `_counts` ignores them). Detectors never sleep: the EWRs are live (their zones wake the sleeping sites,
        `_wire_dormant`), every SAM site is dormant (ring = its `RANGE_NM` + WAKE_MARGIN_NM as backstop). Nearest the route first (the order only matters for the wake lists)."""
        from .mission_builder import SITES  # the builder's module imports this one
        if not self.o.dormant_sites:
            return
        st = self.state
        poly = self._poly
        key = (lambda a: tm.poly_dist(a.x, a.y, poly)) if poly else (lambda a: dist(a.x, a.y, tx, ty))
        for kind in (AssetKind.EWR, AssetKind.SAM):
            if kind not in kinds:
                continue
            cands = sorted((a for a in st.assets.values() if a.kind == kind and not a.destroyed and a.id not in self.groups_by_asset and SITES.get(a.variant)), key=lambda a: (key(a), a.id))
            for a in cands:
                self._spawn_site(a, SITES[a.variant], manifest, primary=False)
                if kind == AssetKind.SAM:
                    self._make_dormant(a, tm.RANGE_NM.get(a.variant, 0), free=True)
                else:
                    self._tag_dormant(self.groups_by_asset.get(a.id))      # a live detector, but an added one: the unit limits ignore it
                self._dormant_red_added.append(a.id)

    def _dormant_blue_fields(self, tx, ty) -> None:
        """S89 C (setting `dormant_sites`): the defences of every blue airfield not built yet, as dormant groups (they wake on any red unit in their ring + WAKE_MARGIN_NM,
        `_wire_dormant`). One pass at the very end of the build, nearest to the target first, with NO unit-limit check (the added groups are tagged and `_counts` ignores them).
        Fields with flights, the raided field and the covering neighbours were built live before."""
        if not (self.o.dormant_sites and self.o.base_defenses):
            return
        st = self.state
        fields = sorted((b for b in st.bases.values() if b.kind == BaseKind.AIRFIELD and b.id not in self.apt and b.airport in self.t.airports),
                        key=lambda b: dist(b.x, b.y, tx, ty))
        for b in fields:
            self._place_base(b, tx, ty, dormant=True)
            self._dormant_fields.append(b.id)
            self.apt.pop(b.id, None)          # `apt` stays "the fields the mission flies from", as before

    @staticmethod
    def _s89_log(kind: str, text: str) -> list:
        """S89 (XO 2026-11-17): a trigger action that writes `S89 <kind> t=<mission seconds> <text>` to dcs.log (env.info), so a frame hitch in `S89FrameLog.lua` (`model t=`) can be matched to the wake / sleep that caused it."""
        from .mission_builder import S89_LOG  # the builder's module imports this one
        if not S89_LOG:
            return []
        return [action.DoScript(String('env.info(string.format("S89 %s t=%%.1f %%s", timer.getTime(), [==[%s]==]))' % (kind, text.replace("]==]", "]=]"))))]

    @staticmethod
    def _s89_names(grps, cap=10) -> str:
        """S89: the group names for a log line, the first `cap` and a "+N more" tail."""
        n = [g.name for g in grps]
        return ", ".join(n[:cap]) + (f" +{len(n) - cap} more" if len(n) > cap else "")

    @staticmethod
    def _s89_tick_lua(names, flags) -> str:
        """S89: the mission-time tick script (every 10 s: how many dormant groups exist, i.e. were woken once, and how many are asleep again)."""
        q = lambda n: "[==[" + n.replace("]==]", "]=]") + "]==]"
        lines = ["local N={" + ",".join(q(n) for n in names) + "}",
                 "local FS={" + ",".join("[ " + q(n) + " ]=%d" % f for n, f in flags.items()) + "}",
                 "local function tick(_, t)",
                 "  local ex, sl = 0, 0",
                 "  for _, n in ipairs(N) do",
                 "    local ok, g = pcall(Group.getByName, n)",
                 "    if ok and g then ex = ex + 1 end",
                 "    local f = FS[n]",
                 "    if f and trigger.misc.getUserFlag(f) > 0 then sl = sl + 1 end",
                 "  end",
                 "  env.info(string.format('S89 tick t=%.0f dormant=%d existing=%d asleep_again=%d', t, #N, ex, sl))",
                 "  return t + 10",
                 "end",
                 "timer.scheduleFunction(tick, nil, timer.getTime() + 10)",
                 "env.info('S89 start dormant=' .. #N)"]
        return "\n".join(lines)

    def _wire_dormant(self):
        """S89 B1: the ONE final pass that wakes the dormant route SAM sites (setting `dormant_sites`; plan `.claude/s89-late-activation-plan.md` 7.2, XO 2026-11-16).
        Detectors in order: (1) every live red EWR (zone `detection.EWR_COVER_NM`); where no EWR covers a group, (2) the longest-range SAM site built in this mission
        (zone `RANGE_NM` + WAKE_MARGIN_NM) or (3) the red BARCAP stations (zone BARCAP_DETECT_NM), whichever has the LONGER zone radius. One zone and one TriggerOnce per
        detector with an ActivateGroup per covered group; any blue unit wakes them (no `human` guard: the mission is the same for a person and the AI). Backstop: each
        dormant group also has its own ring zone (`RANGE_NM` + WAKE_MARGIN_NM) and trigger, so a belt whose detectors are dead or absent still wakes. Waking a live
        group twice is harmless. Sets `self.dormant_info` (what was wired) for probes."""
        from .mission_builder import DORMANT_SLEEP  # the builder's module imports this one
        self.dormant_info = None
        if not (self.o.dormant_sites and (self._dormant_sites or self._dormant_blue)):
            return
        info = {"detectors": [], "rings": 0, "dormant_before": len(self._dormant_sites), "sam_unslept": None}
        covers, wakers = {}, {}                                         # S89 E: group id -> the zone ids that cover it / the TriggerOnce objects that wake it
        ewr_dets = [(a.x, a.y, detection.EWR_COVER_NM, a) for a in self._dormant_assets(AssetKind.EWR)]
        klass, extra_dets = self._pick_fallback_detector(ewr_dets, info)
        self._wire_detectors(ewr_dets, klass, extra_dets, covers, wakers, info)
        self._wire_site_rings(covers, wakers, info)
        info["dormant_after"] = len(self._dormant_sites)
        info["red_extras"] = list(self._dormant_red_added)
        info["blue"] = {"fields": list(self._dormant_fields), "groups": len(self._dormant_blue), "units": sum(len(t[3].units) for t in self._dormant_blue)}
        self._wire_blue_rings(covers, wakers)
        if DORMANT_SLEEP:
            info["sleep"] = self._wire_sleep([(g, a.x, a.y, "blue") for a, g, _r in self._dormant_sites] + [(g_, x_, y_, "red") for x_, y_, _r2, g_ in self._dormant_blue], covers, wakers)
        self._wire_tick_script()
        self.dormant_info = info

    def _dormant_assets(self, kind) -> list:
        """The assets of this kind that have a group in the mission."""
        st = self.state
        return [st.assets[i] for i in self.groups_by_asset if i in st.assets and st.assets[i].kind == kind]

    def _add_wake_trigger(self, label, x, y, r_m, grps, coalition, covers, wakers, log_text) -> None:
        """One zone (radius in metres) and one TriggerOnce: any unit of `coalition` in it activates every group of `grps`. Records the zone in `covers` and the trigger in `wakers`
        (group id -> list) for the sleep wiring, and adds the dcs.log line `log_text`. The one recipe of the detector, backstop and blue-ring wake triggers."""
        zone = self.m.triggers.add_triggerzone(self._pt(x, y), r_m, True, label)
        trig = triggers.TriggerOnce(comment=label)
        trig.add_condition(condition.PartOfCoalitionInZone(coalition, zone.id))
        for g in grps:
            trig.add_action(action.ActivateGroup(g.id))
            covers.setdefault(g.id, []).append(zone.id)
            wakers.setdefault(g.id, []).append(trig)
        for a_ in self._s89_log("wake", log_text):
            trig.add_action(a_)
        self.m.triggerrules.triggers.append(trig)

    def _pick_fallback_detector(self, ewr_dets, info):
        """Where no EWR covers a dormant group: the longest-range SAM site built in this mission, or the red BARCAP stations, whichever has the longer zone radius.
        Returns `(klass, extra_dets)` (`(None, [])` when every group is covered or nothing can detect). A SAM detector that is itself dormant is woken for good
        (the detector must be live) and recorded in `info["sam_unslept"]`."""
        from .mission_builder import BARCAP_DETECT_NM, WAKE_MARGIN_NM  # the builder's module imports this one
        left = [t for t in self._dormant_sites if not any(_covered(d, t[0]) for d in ewr_dets)]     # no EWR covers these
        extra_dets, klass = [], None
        if left:
            sams = [a for a in self._dormant_assets(AssetKind.SAM) if tm.RANGE_NM.get(a.variant, 0) > 0]
            best = max(sams, key=lambda a: tm.RANGE_NM[a.variant]) if sams else None
            sam_r = (tm.RANGE_NM[best.variant] + WAKE_MARGIN_NM) if best is not None else 0
            if sam_r > 0 and sam_r > (BARCAP_DETECT_NM if self._bandit_stations else 0):
                klass = "SAM"
                if best.id in {t[0].id for t in self._dormant_sites}:   # the detector must be live: it wakes first (accepted: this overshoots the unit room by up to one site, 8 units)
                    t_ = next(t for t in self._dormant_sites if t[0].id == best.id)
                    t_[1].late_activation = False
                    self._dormant.discard(t_[1].id)
                    self._dormant_sites.remove(t_)
                    info["sam_unslept"] = best.id
                extra_dets = [(best.x, best.y, sam_r, best)]
            elif self._bandit_stations:
                klass = "BARCAP"
                extra_dets = [(sx, sy, BARCAP_DETECT_NM, None) for sx, sy in self._bandit_stations]
        return klass, extra_dets

    def _wire_detectors(self, ewr_dets, klass, extra_dets, covers, wakers, info) -> None:
        """One wake trigger per detector (the live EWRs, then the fallback detector) over the dormant groups it covers; appends each to `info["detectors"]`."""
        order = [("EWR", d) for d in ewr_dets] + [(klass, d) for d in extra_dets]
        for kl, d in order:
            if kl == "EWR":
                grps = [t for t in self._dormant_sites if _covered(d, t[0])]
            else:                                                       # the fallback detector wakes only the groups no EWR covers
                grps = [t for t in self._dormant_sites if _covered(d, t[0]) and not any(_covered(e, t[0]) for e in ewr_dets)]
            if not grps:
                continue
            nm_ = d[3].id if d[3] is not None else f"({d[0] / 1000:.0f},{d[1] / 1000:.0f})"
            label = f"S89 detector {kl} {nm_}"
            self._add_wake_trigger(label, d[0], d[1], d[2] * NM, [t[1] for t in grps], "blue", covers, wakers, f"{label}: {len(grps)} groups: {self._s89_names([t[1] for t in grps])}")
            info["detectors"].append({"class": kl, "at": nm_, "radius_nm": d[2], "groups": [t[0].id for t in grps]})

    def _wire_site_rings(self, covers, wakers, info) -> None:
        """Backstop: each dormant group's own ring (`RANGE_NM` + WAKE_MARGIN_NM, 10 nm when it has no range); counted in `info["rings"]`."""
        from .mission_builder import WAKE_MARGIN_NM  # the builder's module imports this one
        for a, g, ring in self._dormant_sites:
            label = f"S89 ring {a.id}"
            self._add_wake_trigger(label, a.x, a.y, ((ring + WAKE_MARGIN_NM) if ring else 10) * NM, [g], "blue", covers, wakers, f"{label}: 1 groups: {self._s89_names([g])}")
            info["rings"] += 1

    def _wire_blue_rings(self, covers, wakers) -> None:
        """S89 C: blue field defences, the backstop form only (no blue EWR model): any red unit in the ring wakes the group."""
        from .mission_builder import WAKE_MARGIN_NM  # the builder's module imports this one
        for x_, y_, ring_, g_ in self._dormant_blue:
            self._add_wake_trigger(f"S89 blue ring {g_.name}", x_, y_, (ring_ + WAKE_MARGIN_NM) * NM, [g_], "red", covers, wakers, f"blue ring: {g_.name}")

    def _wire_tick_script(self) -> None:
        """The `S89 log tick` start trigger (only with S89_LOG on and at least one dormant group)."""
        from .mission_builder import DORMANT_SLEEP, S89_LOG  # the builder's module imports this one
        names_ = [t[1].name for t in self._dormant_sites] + [t[3].name for t in self._dormant_blue]
        if names_ and S89_LOG:
            ts_ = triggers.TriggerStart(comment="S89 log tick")
            ts_.add_action(action.DoScript(String(self._s89_tick_lua(names_, getattr(self, "_s89_sleep_flags", {}) if DORMANT_SLEEP else {}))))
            self.m.triggerrules.triggers.append(ts_)

    def _wire_sleep(self, groups, covers, wakers) -> dict:
        """S89 E (plan 7.3, the rule flown in the probe `zone`): every dormant group `(group, x, y, enemy coalition)` goes back to AI OFF when no enemy unit has been inside ANY zone
        that covers it (its ring and the detector zones that wake it; `covers`) for 30 s, and wakes again (AI ON) when one enters any of them. Flags per group: fa activated (set by
        the group's first-wake triggers, `wakers`), fo outside-timer running, fs asleep. AllOfCoalitionOutsideZone = every enemy unit is outside (PartOf... = at least one is, wrong
        here). Cost 2 + 2 per covering zone continuous triggers per group; groups beyond DORMANT_SLEEP_MAX_TRIGGERS (furthest from the route first) just stay awake once woken.
        Returns what was wired, for probes."""
        from .mission_builder import DORMANT_SLEEP_MAX_TRIGGERS  # the builder's module imports this one
        poly = list(self._poly)

        def cont(comment, conds, acts):
            t = triggers.TriggerContinious(comment=comment)
            for c in conds:
                t.add_condition(c)
            for a in acts:
                t.add_action(a)
            self.m.triggerrules.triggers.append(t)

        used = n_sl = capped = 0
        sleep_flags = self._s89_sleep_flags = {}                         # group name -> its "asleep" flag, for the tick script
        for g, x, y, en in sorted(groups, key=lambda t: _route_dist(poly, t[1], t[2])):
            zs = covers.get(g.id, [])
            if not zs:
                continue
            cost = 2 + 2 * len(zs)
            if used + cost > DORMANT_SLEEP_MAX_TRIGGERS:
                capped += 1
                continue
            used += cost
            n_sl += 1
            self._flag_n += 3
            fa, fo, fs = self._flag_n - 2, self._flag_n - 1, self._flag_n
            for tg in wakers.get(g.id, []):
                tg.add_action(action.SetFlag(fa))
            out_all = lambda: [condition.AllOfCoalitionOutsideZone(en, z) for z in zs]
            cont(f"S89 outside timer start {g.name}", [condition.FlagIsTrue(fa), condition.FlagIsFalse(fs), condition.FlagIsFalse(fo)] + out_all(), [action.SetFlag(fo)])
            cont(f"S89 sleep {g.name}", [condition.FlagIsTrue(fa), condition.FlagIsTrue(fo), condition.FlagIsFalse(fs), condition.TimeSinceFlag(fo, 30)] + out_all(),
                 [action.GroupAIOff(g.id), action.SetFlag(fs), action.ClearFlag(fo)] + self._s89_log("sleep", g.name))
            sleep_flags[g.name] = fs
            for k, z in enumerate(zs, 1):
                cont(f"S89 timer reset {k} {g.name}", [condition.FlagIsTrue(fo), condition.FlagIsFalse(fs), condition.PartOfCoalitionInZone(en, z)], [action.ClearFlag(fo)])
                cont(f"S89 wake again {k} {g.name}", [condition.FlagIsTrue(fa), condition.FlagIsTrue(fs), condition.PartOfCoalitionInZone(en, z)],
                     [action.GroupAIOn(g.id), action.ClearFlag(fs)] + self._s89_log("wake again", g.name))
        return {"groups": n_sl, "capped": capped, "continuous": used}
