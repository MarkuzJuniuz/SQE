"""Session: the single API the GUI (and the smoke test) talk to. No Qt in here."""
from __future__ import annotations
import copy
import json
import math
import re
import random
import time
from pathlib import Path

from . import CAMPAIGN_EXT, narrative
from .aircraft import AIRCRAFT
from .debrief import Manifest, apply_debrief, read_state_file, tally
from .difficulty import get as get_difficulty
from .loadouts import LoadoutLibrary
from .models import BaseKind, Objective, ObjectiveType, Role
from . import airwings, barcap as barcap_, clock, raids, redair, refit, sams, ground, support_assets, tempo
from .mission_builder import MissionBuilder, MissionOptions
from .packages import AI_ONLY, ai_only, carrier_raid, Ledger, NoPlayerSlot, Package, PackageBuilder

from .scenario import new_campaign
from . import theatres
from .settings import AppSettings
from .state import CampaignState, SaveIncompatible
from .war import ObjectivePlanner, SUPPRESS_TURNS, WarSimulator, update_status



SEAD_SYNC_KM = 60            # SEAD packages whose targets are this close together are synchronised (the same ground, the same defence)
SEAD_SYNC_ON = True          # off only in tests that need an unsynchronised day (the merge-underway case)
SWEEP_AREA_KM = 60           # packages whose targets are this close together share one Fighter Sweep
RAID_PREP_LEAD_MIN = 20      # v0.41.305 (XO 2026-11-05): the SEAD / Standoff DEAD packages that open the fleet-defence lane start this long before the raid package (the plan doc measured about 20 min from launch to homebound HARMs; judgment call, tune)
SWEEP_LEAD_MIN = 10          # the sweep starts this much ahead of the first package it covers
PACKAGES_PER_TURN = {1: (1.0, 0.25), 2: (1.5, 0.5), 3: (1.5, 0.5)}      # v0.41.338 (campaign rules plan Phase 4; it replaces PACKAGES_PER_DAY 14): packages planned per TURN by level, (day turn, night turn). A fraction is a seeded
                             # chance of one more. Judgment calls: the plan's section 6 starting points (toy-model tempo, L3 about 50:50); L1 is demand-limited anyway; tune in Phase 13
DAY1_EXTRA = 1               # every day turn of Day 1 plans this many more packages ("day 1 is brutal", XO's notes; the plan's value, judgment call)
RETASK_TURNS = 2             # a target hit in the last this-many turns is not planned again unless its health has dropped since (the plan's value, judgment call)
PLAYER_EXTRA_JOBS = 4        # a day turn with no job for your squadron (while it has a ready pair) may add up to this many of the planner's next-best jobs, one at a time, until one fits (judgment call)
RETASK_KEEP_TURNS = 8        # ...and the hit record is kept this long (bookkeeping only)
MAX_NIGHT_TURNS = 12         # a loop bound for the night auto-resolution (a night is six turns), never a game rule
LATE_SEAD_MIN = 15           # launch option --late-sead: SEAD-stage packages go in this much later, so the DEAD stage (10 min behind) arrives
                             # about 5 min ahead of them and reaches its gate with the radars still up: it holds (HOLD_S = 12 min) and goes in once
                             # the late SEAD blinds the site. A test of the hold; it changes that day's plan in the save.

def _hm(start: str) -> int:
    """A package's "HH:MM" start as minutes since midnight."""
    return int(start[:2]) * 60 + int(start[3:5])


def _fmt_hm(m: int) -> str:
    """Minutes since midnight as "HH:MM" (clamped to the day)."""
    m = max(0, min(23 * 60 + 59, int(m)))
    return f"{m // 60:02d}:{m % 60:02d}"


class Session:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.state: CampaignState | None = None
        self.path: Path | None = None
        self.last_build = None
        self.options = MissionOptions()
        self.full_map = False                                 # launch option --full-map: no restrictions, every site, garrison, column and planned patrol is built (a stress test)
        self.ai_test = False                                  # launch option --ai-test: your own flight is built as an AI flight (see run() in gui/app.py)
        self.late_sead_min = 0                                # launch option --late-sead: SEAD-stage packages go in LATE_SEAD_MIN later (forces the DEAD hold; a test)
        self.loadouts = LoadoutLibrary(Path(settings.sqe_dir) / "loadouts.json" if settings.dcs_saves else None)
        self.sync_terrain()

    def sync_terrain(self) -> None:
        """Point the land / water checks at the terrain scan DCS measured (if it has been run) and at the shore margin from Settings."""
        from . import relief, roads, seacheck, terrainmask
        seacheck.SITE_MARGIN = float(getattr(self.settings, "shore_margin_m", 1500))
        terrainmask.RIVER_MARGIN = float(getattr(self.settings, "river_margin_m", 100))
        terrainmask.configure(self.settings.sqe_dir if self.settings.dcs_saves else None)
        relief.configure(self.settings.sqe_dir if self.settings.dcs_saves else None, builtin=True)
        roads.configure(self.settings.sqe_dir if self.settings.dcs_saves else None)

    # ---- persistence ---------------------------------------------------------------------------
    @property
    def d(self):
        return get_difficulty(self.state.level)

    def campaigns_dir(self) -> Path:
        return self.settings.sqe_dir

    def list_campaigns(self) -> list:
        d = self.campaigns_dir()
        return sorted(d.glob(f"*{CAMPAIGN_EXT}"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []

    def new(self, name: str, aircraft: str, level: int, seed: int | None = None, start_date: str = "2006-06-12", night_ops: bool = False,
            squadron: str | None = None, theatre: str = "caucasus") -> None:
        theatres.use(theatre)
        self.sync_terrain()
        self.state = new_campaign(name, aircraft, level, theatre=theatre, seed=seed, start_date=start_date, night_ops=night_ops, player_squadron=squadron)
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip() or "campaign"
        self.path = self.campaigns_dir() / f"{safe}{CAMPAIGN_EXT}"
        self.plan_day()
        self.save()

    def open(self, path) -> None:
        """Open a campaign. Raises SaveIncompatible (never a raw traceback) when it cannot be read; the campaign that was open stays open."""
        prev = (self.state, getattr(self, "path", None))
        loaded = CampaignState.load(path)
        try:
            self._open_loaded(loaded, path)
        except SaveIncompatible:
            self.state, self.path = prev
            raise
        except Exception as e:
            self.state, self.path = prev
            raise SaveIncompatible(loaded.to_dict() if loaded is not None else {}, "older", f"{type(e).__name__}: {e}") from e

    def backup_incompatible(self, path) -> Path:
        """Copy a save this build cannot open into the backups folder (the original is not touched). -> the copy's path."""
        import re as _re, shutil as _sh, time as _t
        src = Path(path)
        b = self.settings.backups_dir
        b.mkdir(parents=True, exist_ok=True)
        dst = b / f"{_re.sub(r'[^A-Za-z0-9_-]+', '_', src.stem)}_old_{_t.strftime('%Y%m%d_%H%M')}{CAMPAIGN_EXT}"
        _sh.copy2(src, dst)
        return dst

    def _open_loaded(self, loaded, path) -> None:
        self.state = loaded
        theatres.use(self.state.theatre)
        self.sync_terrain()
        self.path = Path(path)
        self.settings.last_campaign = str(path)
        self.settings.save()
        from .scenario import snap_assets_to_land
        moved = snap_assets_to_land(self.state)          # older campaigns generated some sites in the sea
        if moved:
            self.state.note(f"{moved} enemy sites that were placed in the water have been moved onto land.")
        st_ = self.state
        if st_.status == "ACTIVE" and (st_.raids or {}).get("day") != st_.day:                 # the day was never begun (a new save, or one from before the day counter): begin it and plan this turn
            self.plan_day()
        elif st_.status == "ACTIVE" and (st_.raids or {}).get("planned_turn") != st_.turn:      # v0.41.338: a save from before per-turn planning holds a whole-day plan: this turn is planned again (it is the only one that is kept)
            self.plan_turn()
        else:
            self.refresh_weather()                       # old saves, or the weather setting changed since
        if moved:
            self.save()

    def save(self, path=None) -> None:
        if path:
            self.path = Path(path)
        self.state.save(self.path, backups_dir=self.settings.backups_dir)
        self.settings.last_campaign = str(self.path)
        try:
            self.settings.save()
        except OSError:
            pass

    # ---- planning --------------------------------------------------------------------------------
    def _rng(self, salt: int = 0) -> random.Random:
        return random.Random(int(self.state.campaign_id, 16) % 10_000_019 + self.state.turn * 101 + salt)      # v0.41.338 (Phase 4): by the turn, a day plans 12 times

    def plan_day(self) -> list:
        """Plan from scratch: the day's start (`_begin_day`) and this turn's tasking (`plan_turn`). A new campaign and tools call this; `Session._tick` calls the two halves itself."""
        self._begin_day()
        return self.plan_turn()

    def _day_turns(self) -> list:
        """The turns of today from now on in which something can be planned: every turn with night ops on, the day turns with them off (a night turn is resolved without you, `advance_turn`)."""
        st = self.state
        return [t for t in range(st.turn, clock.first_turn(st.day + 1)) if st.night_ops or not clock.is_night_turn(t)]

    def _begin_day(self) -> None:
        """What is decided once a day (v0.41.338, Phase 4; it was the first half of `plan_day`): the garrisons and sites a day needs, the fleet and carrier, red's air tasking, the day's
        announced raids and the carrier raid (each gets a turn of its own here: `plan_turn` offers it then). Blue's standing patrols, the guards and the AWACS / tanker windows start the day empty and are planned turn by turn (`plan_turn`, Phase 4b)."""
        st = self.state
        from . import threatmap as _tm
        _tm.set_ramp_lead(bool(getattr(self.settings, "hot_ramp_scrambles", False)))      # v0.41.92: planning keep-outs use the same scramble circles as the build
        from . import ground
        ground.ensure_blue_garrisons(st)                # older saves: a friendly garrison at every airfield
        ground.ensure_forward_garrisons(st)             # v0.41.102: a forward garrison for each side in every sector (older saves too)
        sams.ensure_blue_sams(st)                       # v0.41.62: blue's three air-defence sites at every airfield (older saves: from the field's `defense`)
        ground.snap_roads(st)                           # once, as soon as a road scan exists: columns and supply sites sit on a road
        if st.ground is not None:
            st.ground["pilot_influence"] = bool(getattr(self.settings, "pilot_influence", True))
            st.ground["tempo_decay"] = bool(getattr(self.settings, "tempo_decay", False))      # v0.41.208
        from . import carrier_pos, fleet as _fleet
        for _ln in _fleet.step(st):                     # v0.41.257: a sunk carrier comes back as new on its day; sunk escorts are replaced
            st.note(_ln)
        _cv = None if _fleet.sunk(st) else carrier_pos.update(st)      # v0.41.159: the fleet repositions once a day, along the front and clear of the red airfields
        if _cv:
            st.note(_cv)
        redair.begin_day(st)                            # the enemy's air tasking: the day's shell (v0.41.340, Phase 5a: its patrols and sweeps are planned per turn, `plan_turn`)
        turns = self._day_turns()
        pick = self._rng(72)                            # which turn each of the day's raids goes in (seeded: the same campaign gives the same day)
        # the carrier raid (bombers.decide is pure, so the planner and the raid plan agree): a staged raid is noted the day red decides it (and makes today the quiet day
        # `raids.todays_raids` reads); a raid that launches today gets one turn of the day, the only turn `ObjectivePlanner.plan` looks at it
        bomber_turn = None
        fleet_ = _fleet.carrier(st)
        if fleet_ and self.d.bomber_policy != "none":
            from . import bombers
            dec = bombers.decide(st, self.d)
            if dec["mode"] == "hold":
                bombers.note_stage(st, dec)
            else:
                bomber_turn = pick.choice(turns) if turns else st.turn
        keep = {k: v for k, v in (st.raids or {}).items() if k in ("carry", "sead_fail", "bomber_days", "bomber_stage", "deck_out_to", "retask")}
        warned, n_surprise = raids.todays_raids(st, self.d, self._rng(71))      # still one draw a day (the plan: Phase 5 moves it); each raid is offered in a turn of its own
        st.raids = {**keep, "day": st.day, "surprise": n_surprise, "carry": [], "bomber_turn": bomber_turn,
                    "day_raids": [{"turn": pick.choice(turns) if turns else st.turn, "o": o.to_dict()} for o in warned]}
        bc = barcap_.ensure(st)                          # the day's BARCAP areas (made once a day); the standing patrols, guards and the AWACS / tanker windows are planned turn by turn (`plan_turn`, Phase 4b)
        bc["blue_flights"], bc["blue_cover"], bc["support_flights"], bc["blue_committed"] = [], {}, {}, []

    def _turn_rate(self, turn: int) -> float:
        """How many packages this turn plans (a fraction is a seeded chance of one more): PACKAGES_PER_TURN by level and day / night, DAY1_EXTRA more on every day turn of Day 1."""
        st = self.state
        day_r, night_r = PACKAGES_PER_TURN[max(1, min(3, int(st.level)))]
        if clock.is_night_turn(turn):
            return night_r
        return day_r + (DAY1_EXTRA if st.day == 1 else 0)

    def _retask_skip(self) -> set:
        """The re-tasking rule: a target hit within the last RETASK_TURNS turns is not planned again unless its health has dropped below what it was after that hit
        (`st.raids["retask"]`: target id -> [turn, health after], written by `_retire`)."""
        st = self.state
        out = set()
        for tid, (t, h) in ((st.raids or {}).get("retask") or {}).items():
            a = st.assets.get(tid)
            if a is not None and st.turn - t <= RETASK_TURNS and a.health >= h - 1e-6:
                out.add(tid)
        return out

    def _day_names(self) -> dict:
        """The day's callsign counter, seeded from every flight of the packages already resolved today, so a later turn never reuses 'Viper 1' (a returning flight shown as a ruin keeps its name)."""
        names = {}
        for d in self.state.plan_done or []:
            for f in d.get("flights", []):
                nm, _, no = (f.get("callsign") or "").rpartition(" ")
                if no.isdigit():
                    names[nm] = max(names.get(nm, 0), int(no))
        return names

    def _build_wave(self, pb, o, i: int, ledger, fps: tuple, names: dict, waves: tuple = (1, 2)) -> tuple:
        """Build one objective's package in the first wave that crews it (Phase 4): wave 1 draws on the jets that are ready now, wave 2 on those plus the jets whose refit ends by
        the second wave. A package with a required slot short in wave 1 is tried in wave 2 and goes there when that is better; ties keep wave 1.
        -> (package, wave) or (None, 0). The ledger, the shortfall list and the callsign counter are touched only by the attempt that is kept."""
        tries = []
        if not any(ledger.late.values()):
            waves = tuple(w for w in waves if w == 1) or waves[:1]          # nothing comes ready for the second wave: one attempt is all there is
        n0, names0 = len(pb.short), dict(names)
        for w in waves:
            view = ledger.view(w)
            pkg = None
            for fp in fps:
                try:
                    pkg = pb.build(o, i, view, for_player=fp, names=names)
                    break
                except NoPlayerSlot:
                    continue
            sh = pb.short[n0:]
            del pb.short[n0:]
            after = dict(names)
            names.clear()
            names.update(names0)
            if pkg is None:
                continue
            tries.append((pb.missing, w, pkg, view, sh, after))
            if pb.missing == 0:
                break
        if not tries:
            return None, 0
        miss, w, pkg, view, sh, after = min(tries, key=lambda t: (t[0], t[1]))
        ledger.settle(view, w)
        pb.short.extend(sh)
        names.clear()
        names.update(after)
        pkg.extra["wave"] = w
        return pkg, w

    def plan_turn(self) -> list:
        """The tasking order of THIS TURN (v0.41.338, Phase 4; the second half of the old `plan_day`): a few jobs from `ObjectivePlanner` (PACKAGES_PER_TURN), the day's raids that
        belong to this turn, crewed from the squadrons' ready jets in two launch waves (`Ledger`, `turn_times`). `state.plan` holds only this turn's packages. -> the packages."""
        st = self.state
        from . import timeofday as _tod
        turn = st.turn
        t0 = clock.minute(turn) - clock.day_start_minute(st.day)             # the turn's first minute of today
        st.raids["planned_turn"] = turn
        st.raids["sead"] = {}                                                # the SEAD dice are cast per turn (`_cast_sead`)
        st.plan = []
        if st.barcap is not None:
            st.barcap["blue_committed"] = []                                 # per turn (Phase 4b): the standing patrols already sent to refit this turn, by `squadron:callsign`
        if clock.is_night_turn(turn) and not st.night_ops:                   # a night turn with night ops off is resolved without you: nothing is planned in it
            self.refresh_weather()
            return []
        from . import threatmap as _tm
        _tm.set_ramp_lead(bool(getattr(self.settings, "hot_ramp_scrambles", False)))
        redair.plan_turn(st, self.d, turn, t0, self._rng(91))            # v0.41.340 (Phase 5a): red plans this turn's patrols and sweeps FIRST, from its own ready fighters (blue's sweeps and the mission read its flights)
        rate = self._turn_rate(turn)
        rr = self._rng(2)
        n = int(rate) + (1 if rr.random() < rate - int(rate) else 0)
        is_bomber = st.raids.get("bomber_turn") == turn
        objs = ObjectivePlanner(self.d).plan(st, self._rng(), limit=n + (1 if is_bomber else 0), bomber=is_bomber, skip=self._retask_skip()) if (n > 0 or is_bomber) else []
        redair.assign_guards(st, self.d, objs)          # v0.41.10: red's patrols take stations over the SAM sites it expects to be attacked
        warned = [Objective(r["o"]["id"], ObjectiveType(r["o"]["type"]), r["o"]["target_id"], r["o"]["priority"], r["o"].get("description", ""), r["o"].get("aim", ""))
                  for r in st.raids.get("day_raids", []) if r["turn"] == turn]
        carry = self._carried(objs)
        # v0.41.241: the supply strikes and road-battalion CAS are the day's filler (with the road sites there are always some): they are built AFTER the announced raids, so a full job list
        # does not use up the fighters a raid intercept needs (it did: on a fresh L3 campaign no raid intercept was offered for ten days running)
        _late = [o for o in objs if (o.type == ObjectiveType.STRIKE and getattr(st.assets.get(o.target_id), "kind", None) in ground.SUPPLY_KINDS)
                 or (o.type == ObjectiveType.CAS and o.target_id.startswith("rgar_sup_"))]          # ...and the CAS jobs on a road site's battalion
        objs = carry + [o for o in objs if o not in _late] + warned + _late        # postponed from yesterday first, then the turn's job list, then the announced raids, then the supply strikes and road battalions
        pb = PackageBuilder(st, self.d)
        prep_ids = self._raid_prep_objectives(pb, objs)          # v0.41.305: the carrier raid's blocking SAM sites get their own SEAD / Standoff DEAD packages, appended AFTER the turn's jobs (the raid keeps its index, so its bearing is the one planned here)
        objs = objs + prep_ids[0]
        prep_obj_ids = {o.id for o in prep_ids[0]}                # built right after the raid itself, before the turn's other jobs take the squadrons' jets
        psq = st.player.squadron_id if st.player else None
        from . import blue_barcap
        t_abs = clock.minute(turn)

        from . import carrier_hit
        base_L = Ledger(st, ready_min=t_abs + _tod.WAVE2_OFFSET_MIN)       # the turn's jets: wave 1 = ready now, wave 2 adds what finishes its refit by the second wave
        from . import reserve as _res                                       # v0.41.340 (Phase 5a): the reaction reserve comes off the fighter / multirole squadrons BEFORE the patrols and packages draw on the ledger
        if st.barcap is not None:
            st.barcap["react_hold"] = _res.apply(base_L, [q for q in st.squadrons.values() if Role.CAP in AIRCRAFT[q.aircraft].roles], int(st.level))
        _df = carrier_hit.deck_factor(st)                                   # v0.41.109: a carrier deck torn up by a raid launches less (0 the day after, half the day after that)
        if _df < 1.0:
            base_L.scale([sid for sid, q in st.squadrons.items() if st.bases[q.base_id].kind == BaseKind.CARRIER], _df)
        # v0.41.339 (Phase 4b): the AWACS / tanker windows of this turn, then the standing patrols and guards, planned from the same ledger BEFORE the packages: their jets come off it
        # (the packages are built from what is left, so nothing is booked twice and the 4a `hold` is gone)
        wins = support_assets.plan(st, turn)
        blue_barcap.plan_turn(st, self.d, turn, t0, base_L, self._rng(81), wins)

        def make_ledger():
            return base_L.copy()

        sweeps = {}                                     # id(sweep package) -> the packages it goes in ahead of

        def preferred_waves() -> dict:
            """Which wave each job is meant for: up to half of them (whole areas together, so packages that fold into one mission stay in one wave) in wave 1, the rest in wave 2. The carrier raid
            and its prep go in wave 1. A job meant for wave 1 moves to wave 2 only when its jets are not ready (`_build_wave`)."""
            from types import SimpleNamespace
            from .packages import packages_linked
            fake = [SimpleNamespace(objective=o) for o in objs]
            comp = list(range(len(objs)))
            def root(i):
                while comp[i] != i:
                    comp[i] = comp[comp[i]]; i = comp[i]
                return i
            for i in range(len(objs)):
                for j in range(i + 1, len(objs)):
                    if packages_linked(st, fake[i], fake[j]):
                        comp[root(j)] = root(i)
            groups: dict = {}
            for i in range(len(objs)):
                groups.setdefault(root(i), []).append(i)
            half, seen, out = (len(objs) + 1) // 2, 0, {}
            for g in sorted(groups.values(), key=lambda g: (-len(g), g[0])):
                for i in g:
                    out[i] = 1 if (seen < half or carrier_raid(st, objs[i]) or objs[i].id in prep_obj_ids) else 2
                seen += len(g)
            return out

        def build_all(forced: set) -> list:
            sweeps.clear()
            pb.short = []
            ledger = make_ledger()
            pref = preferred_waves()
            out, names = [], self._day_names()          # callsign counter for the whole day: Enfield 1, Enfield 2 ... never two Enfield 1s
            for i, o in sorted(enumerate(objs, 1), key=lambda t: (0 if carrier_raid(st, t[1]) else (1 if t[1].id in prep_obj_ids else 2))):      # v0.41.107: the setpiece is built FIRST (it is rare and needs the carrier squadrons), numbers unchanged
                fps = (True, False) if (((i - 1) in forced or carrier_raid(st, o) or o.type == ObjectiveType.FLEET_DEFENSE) and not ai_only(st, o)) else (False,)
                pkg, _w = self._build_wave(pb, o, i, ledger, fps, names, waves=(1, 2) if pref[i - 1] == 1 else (2,))
                if pkg is not None:
                    out.append(pkg)
            out.sort(key=lambda p: p.number)
            # Fighter Sweep (v0.40.2): where intel expects more enemy fighters there than the packages' own TARCAP and escort can take, a sweep
            # package of 4-ships goes in ahead of them. One per area (targets within SWEEP_AREA_KM), sized to the worst package there.
            from .packages import is_sweep, sweep_4ships
            need = [(p, sweep_4ships(p.n_def // 2)) for p in out if p.objective.type in (ObjectiveType.STRIKE, ObjectiveType.DEAD, ObjectiveType.CAS)
                    and p.objective.target_id in st.assets]
            areas = []
            for p, n4 in sorted(need, key=lambda x: -x[1]):
                if n4 <= 0:
                    continue
                t = st.assets[p.objective.target_id]
                a = next((a for a in areas if math.hypot(a[0].x - t.x, a[0].y - t.y) <= SWEEP_AREA_KM * 1000), None)
                if a is None:
                    areas.append((t, [p]))
                else:
                    a[1].append(p)
            sp_spec = AIRCRAFT[st.squadrons[psq].aircraft] if psq else None
            from . import sweep as sweep_
            # v0.41.33 (XO 2026-10-16): no sweep to bait red. Only where red's own plan has a flight near the area OUT IN THE OPEN (not under
            # SAM cover) with a SAM-clear station short of it; otherwise the packages' TARCAP and escorts carry the fight
            areas = [a for a in areas if sweep_.candidates(st, a[0].x, a[0].y)]
            for k, (t, covered) in enumerate(areas):
                o = Objective(f"obj-t{turn}-sw{k + 1}", ObjectiveType.COUNTER_AIR, t.id, max(p.objective.priority for p in covered),
                              f"Fighter Sweep: clear the air over {t.name} ahead of the strikes", "SWEEP")
                w_ = min(p.extra.get("wave", 1) for p in covered)       # the sweep flies in the wave of the first package it covers
                fps = (True, False) if (sp_spec and Role.SWEEP in sp_spec.roles) else (False,)
                pkg, _w = self._build_wave(pb, o, len(objs) + k + 1, ledger, fps, names, waves=(w_,))
                if pkg is None or not pkg.flights:
                    continue
                sweeps[id(pkg)] = covered
                out.append(pkg)
            return out

        mine = lambda pk: sum(1 for p in pk if any(f.squadron_id == psq and not f.tag for f in p.flights))
        rng = self._rng(3)
        pkgs = build_all(set(rng.sample(range(len(objs)), min(len(objs), max(1, (len(objs) + 1) // 2)))))     # your squadron is tasked on about half of them
        _L0 = make_ledger()
        if psq and not clock.is_night_turn(turn) and mine(pkgs) < 1 and _L0.free[psq] + _L0.late[psq] >= 2:      # a day turn offers your squadron a slot when it has a ready pair
            pkgs = build_all(set(range(len(objs))))
            if mine(pkgs) < 1:                                  # still none (a short list is often one AI-only job, a fleet patrol): the planner's next-best jobs are offered until one fits your squadron
                have = {(o.type, o.target_id, o.aim) for o in objs}
                more = ObjectivePlanner(self.d).plan(st, self._rng(), limit=n + PLAYER_EXTRA_JOBS, bomber=False, skip=self._retask_skip())
                tried = 0
                for k, c in enumerate(more):
                    if (c.type, c.target_id, c.aim) in have or c.after or c.aim == "DEAD" or ai_only(st, c) or tried >= PLAYER_EXTRA_JOBS:
                        continue                                # (a Close DEAD or a follow job needs its partner package in the same list)
                    tried += 1
                    c.id = f"obj-t{turn}-x{k + 1}"
                    objs.append(c)
                    pkgs = build_all(set(range(len(objs))))
                    if mine(pkgs) >= 1:
                        break
                    objs.pop()
                if mine(pkgs) < 1:
                    pkgs = build_all(set(range(len(objs))))
        ground.note_shortfall(st, pb.short)                  # v0.41.247: the slots nobody could fill (a taken field's new squadron follows the need)
        pkgs = self._drop_orphan_followers(pkgs)             # v0.41.158: a strike behind a SEAD whose package could not be crewed has nothing to go in behind
        # same-area packages are launched in the same wave (so they can be folded together): they take consecutive times
        from .packages import packages_linked
        comp = list(range(len(pkgs)))
        def root(i):
            while comp[i] != i:
                comp[i] = comp[comp[i]]; i = comp[i]
            return i
        use_radius = self.settings.merge_mode == "area"
        R = self.merge_radius_m()
        for i in range(len(pkgs)):
            for j in range(i + 1, len(pkgs)):
                if packages_linked(st, pkgs[i], pkgs[j]) or (use_radius and self._near(pkgs[i], pkgs[j], R)):
                    comp[root(j)] = root(i)
        groups: dict = {}
        for i in range(len(pkgs)):
            groups.setdefault(root(i), []).append(i)
        order = [i for g in sorted(groups.values(), key=lambda g: (-len(g), g[0])) for i in g]
        for i, (m, _w) in zip(order, _tod.turn_times(len(pkgs), t0, self._rng(5), [pkgs[i].extra.get("wave", 1) for i in order])):
            pkgs[i].start = _fmt_hm(m)
        self._sync_sead(pkgs)                                        # SEAD flights on the same ground (within SEAD_SYNC_KM) arrive together, not one after another
        self._stage_times(pkgs)                                      # a DEAD stage goes in DEAD_STAGE_GAP_MIN after the SEAD stage of the same site
        self._late_sead(pkgs)                                        # test option --late-sead: the SEAD stage goes in late, so the DEAD stage holds
        floor = lambda p: t0 + (_tod.WAVE2_OFFSET_MIN if p.extra.get("wave", 1) == 2 else 0)      # no package starts before its wave opens (its jets are not ready earlier)
        self._time_raid_prep(pkgs, prep_ids, floor)                  # v0.41.305: the carrier raid's SEAD / Standoff DEAD packages go in RAID_PREP_LEAD_MIN ahead of it (before the sweeps are timed from their packages)
        from . import sweep as sweep_
        dropped = set()
        for p in pkgs:                                               # a Fighter Sweep starts SWEEP_LEAD_MIN ahead of the first package it covers (after every other timing step)
            cov = sweeps.get(id(p))
            if cov:
                first_ = min(_hm(c.start) for c in cov)
                m = max(floor(p), first_ - SWEEP_LEAD_MIN)
                p.start = _fmt_hm(m)
                # v0.41.33: the red flight it goes after must be up in its window; none: no sweep (TARCAP and escorts carry the fight)
                t_ = st.assets.get(p.objective.target_id)
                vs_ = sweep_.pick(st, t_.x, t_.y, first_) if t_ is not None else None
                if vs_ is None:
                    dropped.add(id(p))
                else:
                    p.extra["sweep_vs"] = {"id": vs_["id"], "x": float(vs_["x"]), "y": float(vs_["y"]), "kind": vs_["kind"]}
                    # v0.41.34: the station the planner checked (toward the nearest friendly field); the builder falls back to it when its own
                    # search from the flight's PUSH point finds none (the v0.41.33 smoke run: a sweep fell back to backing out, 108 nm short)
                    sst_ = sweep_.station_for(st, (vs_["x"], vs_["y"]), sweep_._home_guess(st, vs_["x"], vs_["y"]), t_.x, t_.y)
                    if sst_ is not None:
                        p.extra["sweep_vs"].update(sx=float(sst_[0]), sy=float(sst_[1]))
        if dropped:
            pkgs = [p for p in pkgs if id(p) not in dropped]
        for p in pkgs:                                               # the safety net: every package starts inside its wave of this turn (and nothing before the campaign does: Day 1 turn 0 opens at 08:00)
            p.start = _fmt_hm(max(floor(p), min(t0 + clock.TURN_MIN - 5, _hm(p.start))))
        for p in pkgs:
            p.support = pb._support(p)                                   # v0.41.87: with the start times known, only the AWACS / tankers that are on orbit while it flies
        blue_barcap.attach(st, pkgs, until=t0 + clock.TURN_MIN, since=t0)      # v0.41.85: the planned base CAP / carrier CAP sortie that faces each package and is up while it flies (those that start in this turn)
        pkgs.sort(key=lambda p: p.start)
        base = 1 + max([d["number"] for d in st.plan_done] + [0])    # the day's packages are numbered on: turn 2 carries on after turn 1 (the resolved ones are in `plan_done`)
        for n_, p in enumerate(pkgs, base):                          # numbers follow the clock
            p.number, p.id = n_, f"pkg{n_}"
            for k, f in enumerate(p.flights, 1):
                f.id = f"{p.id}-f{k}"
        for p in pkgs:
            if sweeps.get(id(p)):
                p.extra["covers"] = sorted(c.number for c in sweeps[id(p)])           # the packages this Fighter Sweep goes in ahead of
        # v0.41.304 (XO 2026-11-05: no dice, "only what red actually tries", no hidden ones): every raid red plans is a listed, flyable package; an unwarned one says so, and the
        # contested sector under the hardest pressure marks its planned CAS as troops in contact. An unwarned raid that could not be built is still settled overnight.
        _unw = lambda o: bool(re.search(r"-s\d+$", o.id or ""))
        built_ = {p.objective.id for p in pkgs}
        st.raids["surprise"] = int(st.raids.get("surprise", 0)) + sum(1 for o in objs if _unw(o) and o.id not in built_)
        _hot = raids.hot_sector(st)
        for p in pkgs:
            if p.objective.type == ObjectiveType.FLEET_DEFENSE and _unw(p.objective):
                p.extra["unwarned"] = True
            if _hot is not None and p.objective.type == ObjectiveType.CAS and p.objective.target_id == f"armor_{_hot + 1}":
                p.extra["tic"] = True
        st.plan = [p.to_dict() for p in pkgs]
        self._cast_sead(pkgs)
        refit.step(st, t_abs + _tod.WAVE2_OFFSET_MIN)       # the jets the second wave counted on are ready by its opening: they join `available` now, so the turn's losses and its commit come out of the same pool
        self.refresh_weather()
        return self.packages()

    def _agm88_leg_s(self, p) -> float | None:
        """Seconds from PUSH to the HARM point for this SEAD package's first HARM flight, from the same marshal, geometry and route the
        mission builder will use (an umbrella keep-out included). Within one mission every package pushes exactly its start difference after
        the others, so this leg is all that separates their HARM times."""
        from .models import BaseKind
        from .routes import AGM88_LAUNCH_NM, assign_times, bearing, make_geometry, objective_wp, plan_route
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
            mshl = tm.safe_marshal(st, (bx, by), bearing(bx, by, tgt.x, tgt.y), (tgt.x, tgt.y))
            g = make_geometry(bx, by, tgt.x, tgt.y, spec.profile, mshl, carrier=base.kind == BaseKind.CARRIER)
            um = tm.umbrella_site(st, tgt)
            wps = plan_route(Role.SEAD, (bx, by), g, spec.profile, is_player=False, tanker_xy=None,
                             keep_out=(um.x, um.y, AGM88_LAUNCH_NM) if um else None)
            assign_times(wps, 0.0)
            push, obj = next(w for w in wps if w.name == "PUSH"), objective_wp(wps)
            return obj.eta_s - push.eta_s
        except Exception:
            return None

    def _sync_sead(self, pkgs: list) -> None:
        """SEAD packages whose targets sit within SEAD_SYNC_KM of each other go in together: each one's start is moved so that its HARM time
        lands on the latest of the group (the earlier packages wait; none goes in ahead of the others). The HARM time is the package's start plus
        its real push-to-HARM-point leg (marshal, geometry and route as the builder makes them). v0.39.13-v0.39.20 used a straight line from the
        base at 400 kt, which ignored where each package marshals: the carrier's wave arrived about 3 minutes after the land-based one."""
        import math
        if not SEAD_SYNC_ON:
            return
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

    def idle_reasons(self) -> list:
        """Why your squadron has nothing to fly this turn, from the facts at hand (shown when the Missions list has no flight for you)."""
        st = self.state
        sq = st.squadrons[st.player.squadron_id]
        spec = AIRCRAFT[sq.aircraft]
        pk = self.packages()
        out = []
        if sq.available < 2:
            out.append(f"{sq.name} has {sq.available} of {sq.authorized} aircraft serviceable, not enough for a pair.")
        if not pk:
            out.append("No jobs are open on this turn's tasking order.")
        elif not any(f.role in spec.roles for p in pk for f in p.flights if not f.tag):
            out.append(f"Nothing on this turn's tasking order is a job for {spec.display} ({', '.join(sorted(r.value for r in spec.roles))}).")
        elif sq.available >= 2:
            out.append("This turn's jobs were given to other squadrons, or are out of reach of your base.")
        return out

    def _turn_of(self, pd) -> int:
        """The turn a package's start time falls in, on the day it is planned in (tools; the plan holds only this turn's packages since v0.41.338, so nothing in the engine filters by it)."""
        st = self.state
        start = pd["start"] if isinstance(pd, dict) else pd.start
        t = (clock.day_start_minute(st.day) + _hm(start) - clock.START_MIN) // clock.TURN_MIN
        return max(clock.first_turn(st.day), min(clock.first_turn(st.day + 1) - 1, t))

    def turn_label(self, turn: int | None = None) -> str:
        """"Day 2, 08:00": the clock's day and the hour the turn starts."""
        t = self.state.turn if turn is None else turn
        m = clock.minute(t) % clock.DAY_MIN
        return f"Day {clock.day_of(t)}, {m // 60:02d}:{m % 60:02d}"

    def packages(self) -> list:
        """The tasking order of THIS TURN (v0.41.338: `state.plan` holds this turn's packages only). Emergency packages (flown, folded in or settled by odds) are in the plan but are not listed."""
        return [p for p in (Package.from_dict(d) for d in self.state.plan) if not p.extra.get("past")]

    def day_packages(self) -> list:
        """Kept for tools and tests (v0.41.337 had the whole day here): the same as `packages()` now, since the plan is this turn's."""
        return self.packages()

    def _raid_prep_objectives(self, pb, objs: list) -> tuple:
        """v0.41.305 (XO 2026-11-05: "just offer them as SEAD / SO DEAD packages that go before the fleet defense ... they're tuned already"): for the carrier raid, one SEAD or
        Standoff DEAD job per live SAM site that threatens its intercept line (`tm.raid_inbound_sites`, the same list the raid's own scripted SEAD uses), skipping a site that
        already has a DEAD job in the day's list. -> (new objectives, {site id: objective id of the raid's own job it serves}, the raid's objective id). Appended after the day's
        jobs so the raid's index (and so its planned bearing) does not move. The raid package keeps its own SEAD seats: they are the scripted result for a Tomcat / Eagle seat."""
        from . import threatmap as tm
        from .war import long_range_site
        st = self.state
        i = next((n for n, o in enumerate(objs, 1) if carrier_raid(st, o)), None)
        if i is None:
            return [], {}, ""
        o_r = objs[i - 1]
        ex = pb._raid_plan(i, o_r) or {}
        b = st.bases.get(o_r.target_id)
        if b is None or ex.get("bomber_wing") not in st.assets or ex.get("brg") is None:
            return [], {}, o_r.id
        dest = ex.get("dest") or (b.x, b.y)
        have = {o.target_id for o in objs if o.type == ObjectiveType.DEAD}
        new, sites = [], {}
        for a, _r in tm.raid_inbound_sites(st, (dest[0], dest[1]), ex["brg"], ex["bomber_wing"]):
            sites[a.id] = o_r.id
            if a.id in have:
                continue
            tail = f" ({a.health:.0%} left)" if a.health < 0.85 else ""
            if long_range_site(st, a):
                o = Objective(f"obj-d{st.day}-p{len(new) + 1}", ObjectiveType.DEAD, a.id, o_r.priority, f"Standoff DEAD: destroy {a.name}{tail}", "STANDOFF")
            else:
                o = Objective(f"obj-d{st.day}-p{len(new) + 1}", ObjectiveType.DEAD, a.id, o_r.priority, f"SEAD: suppress {a.name}{tail}", "SEAD")
            new.append(o)
        return new, sites, o_r.id

    def _time_raid_prep(self, pkgs: list, prep, floor=None) -> None:
        """Start the raid prep packages RAID_PREP_LEAD_MIN before the carrier raid (and pull a Standoff DEAD of the day that would fall after it ahead of it); the raid package remembers its sites (`prep_sites`) for the war sim.
        `floor(package)` (v0.41.338): the earliest minute of the package's wave; the prep never goes in before its own, and the raid then moves back so the lead stays."""
        new, sites, raid_oid = prep
        if not sites:
            return
        raid = next((p for p in pkgs if p.objective.id == raid_oid), None)
        if raid is None:
            return
        raid.extra["prep_sites"] = sorted(sites)
        hm = int(raid.start[:2]) * 60 + int(raid.start[3:5])
        m = max(0, hm - RAID_PREP_LEAD_MIN)
        ids = {o.id for o in new}
        if floor is not None:
            m = max([m] + [floor(p) for p in pkgs if p.objective.id in ids])
            raid.start = _fmt_hm(max(hm, m + RAID_PREP_LEAD_MIN))
        for p in pkgs:
            if p.objective.id in ids:                                      # a package made for the raid: named for it, and ahead of it
                p.extra["raid_prep"] = raid_oid
                p.start = f"{m // 60:02d}:{m % 60:02d}"
            elif (p.objective.type == ObjectiveType.DEAD and p.objective.target_id in sites and p.objective.aim == "STANDOFF"
                  and int(p.start[:2]) * 60 + int(p.start[3:5]) > m):          # the day's own Standoff DEAD on a blocking site that would go in after the raid: it goes in ahead of it (a SEAD / Close DEAD pair keeps its own staging)
                p.start = f"{m // 60:02d}:{m % 60:02d}"

    def _carried(self, objs: list) -> list:
        """Objectives postponed yesterday (no aircraft left for them after an emergency scramble), if they are still worth flying and not already in the list."""
        st, out = self.state, []
        for od in (st.raids or {}).get("carry", []):
            if (od["type"] == "DEAD" and od.get("aim")) or od.get("after"):
                continue                                        # a SEAD / DEAD stage, or a strike behind a SEAD, is planned fresh with its partner, never carried alone
            o = Objective(od["id"], ObjectiveType(od["type"]), od["target_id"], od["priority"] + 2.0, od.get("description", ""), od.get("aim", ""))
            tgt = st.assets.get(o.target_id) or st.bases.get(o.target_id)
            if tgt is None or getattr(tgt, "destroyed", False) or any(x.type == o.type and x.target_id == o.target_id for x in objs + out):
                continue
            out.append(o)
        return out

    # ---- weather: what the sky does to each package of the day ------------------------------------------------------
    def weather_mode(self) -> str:
        return str(getattr(self.settings, "weather_mode", "clear") or "clear")

    def ils_dummy_mode(self) -> str:
        """v0.41.336: the ILS dummy setting, "off", "beside" or "on" (anything else reads as "off")."""
        m = str(getattr(self.settings, "ils_dummy", "beside") or "off")
        return m if m in ("off", "beside", "on") else "off"

    def refresh_weather(self) -> None:
        """Work out the weather at every package's start time, which packages it scrubs and which loadouts it changes. Stored in the plan so
        the Missions page, the war simulation and the mission builder all see the same thing. Safe to call any time (mode changes, old saves)."""
        from . import weather as W, theatres
        st, mode, pack = self.state, self.weather_mode(), theatres.active()
        for pd in st.plan:
            ex = pd.setdefault("extra", {})
            for k in ("wx", "wx_notes", "scrub"):
                ex.pop(k, None)
            if mode == "clear":
                continue
            pkg = Package.from_dict(pd)
            wx = W.for_package(st, mode, pack, pkg.start, self.ils_dummy_mode() != "off")
            res = W.assess(wx, pkg.objective.type.value, pkg.flights, self.loadouts, AIRCRAFT)
            ex["wx"] = wx.to_dict()
            if res["notes"]:
                ex["wx_notes"] = res["notes"]
            if res["scrub"]:
                ex["scrub"] = res["scrub"]

    def wx_of(self, pkg: Package):
        """The Wx stored for a package (None in clear mode)."""
        from . import weather as W
        return W.Wx.from_dict(pkg.extra.get("wx"))

    def flyable(self, pkg: Package, squadron_only: bool | None = None) -> list:
        """Flights you could fly. 'My squadron' (the default filter) = flights of YOUR squadron; 'all' = any flight of your aircraft type."""
        if squadron_only is None:
            squadron_only = self.settings.flight_filter != "all"
        if pkg.extra.get("scrub"):                                       # scrubbed for weather: nobody flies it, the war sim ignores it
            return []
        if pkg.objective.type == ObjectiveType.BARCAP:                       # v0.41.27: BARCAP is AI-only; v0.41.107: the carrier raid is a flyable setpiece; v0.41.303 (XO 2026-11-05): so are the land raids
            return []
        opts = pkg.player_options(self.state.player.aircraft)
        if pkg.extra.get("setpiece"):                    # v0.41.293 (XO 2026-11-04: "make the SEAD/DEAD seats not flyable by the player", for now, until the SEAD teams are their own packages): the carrier raid's SEAD is AI-only (v0.41.284: only offered while a SAM was alive)
            opts = [f for f in opts if f.role != Role.SEAD]
        return [f for f in opts if f.squadron_id == self.state.player.squadron_id] if squadron_only else opts

    def _raid_sam_live(self) -> bool:
        """Is any red SAM site alive that a raid SEAD flight could be sent against (the builder's own filter: a long-range type, not nearly dead)?"""
        from . import threatmap as tm
        from .models import AssetKind
        return any(a.kind == AssetKind.SAM and not a.destroyed and a.health > 0.25 and tm.RANGE_NM.get(a.variant, 0) >= 12 for a in self.state.assets.values())

    # ---- merge area: a circle around the package's target, kept inside the area where targets exist ---------------------
    def merge_radius_m(self) -> float:
        return max(5.0, float(getattr(self.settings, "merge_radius_nm", 15))) * 1852.0

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
        R = self.merge_radius_m() if R is None else R
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
        return c is not None and t is not None and math.hypot(t[0] - c[0], t[1] - c[1]) <= self.merge_radius_m()

    def merge_candidates(self, pkg: Package) -> list:
        """Packages folded into a mission built around `pkg`: every package whose target lies inside the merge circle (Settings: radius, default
        50 nm, centred by merge_center), starting up to `merge_fwd_min` minutes AFTER it or up to `merge_back_min` minutes BEFORE it (those are already underway
        when the mission starts). At most six, closest to the centre first, so the unit limit drops the furthest first. Empty when merging is off."""
        if self.settings.merge_mode != "area":
            return []
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        back = max(0, int(getattr(self.settings, "merge_back_min", 15)))
        fwd = max(0, int(getattr(self.settings, "merge_fwd_min", 30)))
        R = self.merge_radius_m()
        c = self.merge_center(pkg, R)
        if c is None:
            return []
        out = []
        for p in self.packages():
            t = self._pkg_xy(p)
            if p.number == pkg.number or t is None or not (-back <= hm(p) - hm(pkg) <= fwd) or not any(not f.tag for f in p.flights) or p.extra.get("scrub"):
                continue
            d = math.hypot(t[0] - c[0], t[1] - c[1])
            if d <= R:
                out.append((d, hm(p), p.number, p))
        out.sort(key=lambda r: (not (r[3].objective.type == ObjectiveType.COUNTER_AIR and r[3].objective.aim == "SWEEP"),) + r[:3])     # a Fighter Sweep first: the unit limit drops the strike packages before it
        picked = [r[3] for r in out[:6]]
        # v0.41.270 (XO 2026-11-04): the carrier raid folds into no mission: it is red aiming for the king, a setpiece of its own (v0.41.250 folded it into any mission at its time)
        return picked

    @staticmethod
    def _drop_one(extras: list) -> list:
        """v0.41.131 (XO 2026-10-23): the package to give up first when the mission is over the unit limit: the one that starts LATEST; of two with the same start the
        one later in the list (further from the centre). A Fighter Sweep (the escorts' reason to be there) and an emergency raid scramble (the in-universe \"help has been dispatched\") go last."""
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        sweep = lambda p: (p.objective.type == ObjectiveType.COUNTER_AIR and p.objective.aim == "SWEEP") or p.objective.type == ObjectiveType.FLEET_DEFENSE
        k = max(range(len(extras)), key=lambda i: (not sweep(extras[i]), hm(extras[i]), i))
        return extras[:k] + extras[k + 1:]

    def ruin_candidates(self, pkg: Package, extras: list) -> list:
        """Earlier packages of the same day, same area, that may already have struck when your mission starts: their targets are shown as ruins.
        Packages of this turn that start earlier, and (v0.41.337) the day's packages of earlier turns, kept in `state.plan_done` with their verdict. The closest in time first,
        at most four looked at (the builder shows at most three)."""
        if not getattr(self.settings, "ruins", True) or self.settings.merge_mode != "area":
            return []
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        have = {x.number for x in extras}
        R = self.merge_radius_m()
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

    def _preroll(self, pkgs: list) -> dict:
        """The war sim's verdict on these packages, rolled NOW on a throwaway copy of the state. The mission shows it as ruins, and the same
        verdict is applied for real at the debrief, so what you saw burning is what happened."""
        import copy
        out = {}
        for p in pkgs:
            sim = self._sim(self._rng(55 + p.number))
            try:
                out[p.id] = sim.resolve_abstract(copy.deepcopy(self.state), Package.from_dict(p.to_dict()))["roll"]
            except Exception:
                continue
        return out

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

    # ---- fly ---------------------------------------------------------------------------------------
    def fly(self, package_number: int, flight_id: str | None):
        """Build the sortie for the package (and the packages the merge rules fold into it)."""
        st = self.state
        problems = self.settings.problems()
        if problems:
            raise RuntimeError("; ".join(problems))
        pkg = next(p for p in self.packages() if p.number == package_number)
        PackageBuilder(st, self.d).assign_player(pkg, flight_id)
        self.options.hold_minutes = int(self.settings.hold_minutes)
        self.options.launch_offset_s = int(self.settings.takeoff_buffer_s)
        self.options.ai_unlimited_fuel = bool(self.settings.ai_unlimited_fuel)
        self.options.hot_ramp_scrambles = bool(getattr(self.settings, "hot_ramp_scrambles", False))
        self.options.hot_runway_starts = bool(getattr(self.settings, "hot_runway_starts", False))
        self.options.hot_runway_own_field = self.options.hot_runway_starts and bool(getattr(self.settings, "hot_runway_own_field", False))
        self.options.ai_skill_red = str(getattr(self.settings, "ai_skill_red", "level"))
        self.options.ai_skill_blue = str(getattr(self.settings, "ai_skill_blue", "level"))
        self.options.fighter_engage_nm = int(self.settings.fighter_engage_nm)
        self.options.fighter_engage_minutes = int(self.settings.fighter_engage_minutes)
        self.options.player_is_ai = bool(self.ai_test)
        self.options.fighter_standoff = bool(self.settings.fighter_standoff)
        self.options.carcasses = bool(getattr(self.settings, 'carcasses', True)); self.options.carcass_weight = max(5, int(getattr(self.settings, 'carcass_weight_pct', 25))) / 100.0
        self.options.reactive = bool(getattr(self.settings, 'reactive', True))
        self.options.ecm_script = bool(getattr(self.settings, 'ecm_script', False))
        self.options.ecm_status = bool(getattr(self.settings, 'ecm_status', True))
        self.options.awacs_tuned = bool(getattr(self.settings, 'awacs_tuned', True))
        self.options.damage_calls = bool(getattr(self.settings, 'damage_calls', True))
        self.options.splash_damage = bool(getattr(self.settings, 'splash_damage', True))
        self.options.ai_land_carrier = str(getattr(self.settings, 'ai_land_carrier', "always"))
        self.options.ai_land_field = str(getattr(self.settings, 'ai_land_field', "never"))
        self.options.max_units = int(self.settings.merge_max_units)
        self.options.merge_radius_nm = int(getattr(self.settings, 'merge_radius_nm', 15))
        self.options.full_map = bool(self.full_map)
        if self.full_map:
            self.options.max_units = 10 ** 6
        self.options.f14_special_names = bool(getattr(self.settings, 'f14_special_names', True)); self.options.merge_enemy_pct = int(self.settings.merge_enemy_pct); self.options.weather_mode = str(getattr(self.settings, 'weather_mode', 'clear')); self.options.ils_dummy = self.ils_dummy_mode()
        import contextlib, io, logging
        logging.getLogger("pydcs").setLevel(logging.CRITICAL)
        extras = list(self.merge_candidates(pkg))
        ruins = self.ruin_candidates(pkg, extras)
        pre = {}
        if (ruins or extras) and getattr(self.settings, "ruins", True):
            pre = self._preroll([p for p in list(extras) + ruins if not p.extra.get("done_roll")])
            pre.update({p.id: p.extra["done_roll"] for p in ruins if p.extra.get("done_roll")})          # v0.41.337: an earlier turn's package was resolved already: its verdict is what burns
        from . import limits
        cap = 10 ** 6 if self.full_map else min(int(self.settings.merge_max_units), limits.unit_ceiling())          # v0.41.131: the unit limit counts the whole mission, merged packages included
        while True:
            with contextlib.redirect_stdout(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated DCS files
                res = MissionBuilder(st, self.d, self.options, self.loadouts, self._rng(9)).build(pkg, self.settings.sortie_miz, extras, ruins, pre)
            if (not extras and not ruins) or res.counts["units"] <= cap:
                break
            if ruins:
                ruins = ruins[:-1]                               # returning flights first
            else:
                extras = self._drop_one(extras)                  # too heavy: drop the latest-starting package (a Fighter Sweep last) and rebuild
            res.warnings.append(f"merged mission trimmed to fit the {cap}-unit limit")
        st.sortie_counter += 1
        st.pending = {"package": package_number, "flight": pkg.player_flight.id, "manifest": res.manifest.to_dict(),
                      "built_at": time.time(), "miz": str(res.miz), "timeline": res.timeline,
                      "objective": pkg.objective.description, "objective_type": pkg.objective.type.value, "counts": res.counts, "warnings": res.warnings, "seed": res.seed,
                      "package_dict": pkg.to_dict(), "merged": res.manifest.merged,
                      "ruins": {str(r["number"]): pre[r["id"]] for r in res.manifest.ruins if r["id"] in pre}}
        self.last_build = res
        # a stale results file from a previous sortie must never be mistaken for this one
        try:
            self.settings.state_file.unlink(missing_ok=True)
        except OSError:
            pass
        self.save()
        return res

    # ---- skip the day ---------------------------------------------------------------------------------
    def _sim(self, rng=None):
        """The war simulator."""
        from .war import WarSimulator
        if self.state is not None and self.state.ground is not None:
            self.state.ground["pilot_influence"] = bool(getattr(self.settings, "pilot_influence", True))      # v0.41.160: the app setting rides in the campaign for the sim
            self.state.ground["tempo_decay"] = bool(getattr(self.settings, "tempo_decay", False))             # v0.41.208
        return WarSimulator(self.d, rng)

    # ---- the clock: Skip and Fly take one turn (v0.41.337, campaign rules plan Phase 3) --------------------------------------
    def skip_turn(self) -> dict:
        """Skip Turn: any pending sortie is discarded and every package of THIS TURN (even ones you could fly) is resolved by the war simulation; then the clock moves on two hours
        (`advance_turn`), and with night ops off the night that follows is resolved too. -> {"results": this turn's results, "turns": [{"label", "turn", "results"}] for this turn and
        any night turns, "status", "text"}."""
        st = self.state
        stand_down = not any(self.flyable(p) for p in self.packages())      # XO 2026-10-27: nothing to fly is out of the pilot's hands
        st.pending = None
        if st.ground and not stand_down:
            st.ground["idle_turns"] = int(st.ground.get("idle_turns", 0)) + 1      # a flyable turn skipped: red's idle surge clock (ground.surge); a stand-down turn does not count (XO 2026-11-09)
            st.ground["flyable_today"] = True                                       # ...and the day is not a stand-down day (the Tactical Edge decay at midnight, `_midnight`)
        sim = self._sim(self._rng(44 + 1000 * st.turn))
        label, turn0 = self.turn_label(), st.turn
        results, book = self._resolve_turn(sim)
        if results:
            scr = sum(1 for r in results if r.get("scrubbed"))
            st.note(f"You stood down this turn. The war went on without you ({sum(1 for r in results if r['success'])} of {len(results) - scr} packages succeeded"
                    f"{'; ' + str(scr) + ' scrubbed for weather' if scr else ''}).")
        turns = [{"label": label, "turn": turn0, "results": results}] + self.advance_turn(book, sim)
        self.save()
        return {"results": results, "turns": turns, "status": st.status, "text": st.status}

    def skip_day(self) -> dict:
        """A helper for tools and tests: skip turns until the day changes (Skip Turn is one turn now). Same keys as `skip_turn`, results and turns of every turn skipped."""
        st = self.state
        day0, res, turns = st.day, [], []
        for _ in range(13):                                                  # a day is 12 turns; the bound is a safety net
            if st.status != "ACTIVE" or st.day != day0:
                break
            r = self.skip_turn()
            res += r["results"]
            turns += r["turns"]
        return {"results": res, "turns": turns, "status": st.status, "text": st.status}

    def advance_turn(self, book: dict | None = None, sim=None) -> list:
        """Close the turn and move the clock on: the turn's sorties (`book`, from `_resolve_turn` / `_flown_book`) go into refit, the turn counter moves, the refit step and the
        replacements run, and when the clock crosses midnight the day's end block runs and tomorrow is planned (`_tick`). With night ops OFF the night turns that follow (20:00 to 08:00) are
        resolved by the war simulation without you, until the clock reaches 08:00. -> the night turns resolved: [{"label", "turn", "results"}] (empty by day)."""
        st = self.state
        sim = sim or self._sim(self._rng(46 + 1000 * st.turn))
        self._tick(self._sorties(book or {}), sim)
        nights = []
        for _ in range(MAX_NIGHT_TURNS):
            if st.status != "ACTIVE" or st.night_ops or not clock.is_night_turn(st.turn):
                break
            label, turn0 = self.turn_label(), st.turn
            results, nbook = self._resolve_turn(sim)
            nights.append({"label": label, "turn": turn0, "results": results})
            self._tick(self._sorties(nbook), sim)
        return nights

    def _tick(self, sorties: list, sim) -> None:
        """One turn forward. The commit comes FIRST (the losses are already off `available`), then the clock, then what the new turn's start brings: jets whose refit is over, replacements,
        squadrons that finished a move. At midnight the day's end block runs (`_midnight`)."""
        st = self.state
        for a in st.assets.values():                                         # the turn a blinded radar was first seen blind (it stays blind SUPPRESS_TURNS turns, then it comes back)
            if a.suppressed and a.suppressed_turn < 0:
                a.suppressed_turn = st.turn
            elif not a.suppressed:
                a.suppressed_turn = -1
        self.last_commit = refit.commit_turn(st, sorties, sim.rng) if sorties else []       # kept for tools: [(unit, survivors, limped, short)]
        st.turn += 1
        for a in st.assets.values():
            if a.suppressed and st.turn - a.suppressed_turn >= SUPPRESS_TURNS:
                a.suppressed, a.suppressed_turn = False, -1
        now = clock.minute(st.turn)
        for ln in refit.step(st, now):
            st.note(ln)
        for ln in refit.replacements(st, now):
            st.note(ln)
        for ln in airwings.step_moves(st):
            st.note(ln)
        for ln in support_assets.replace_e3(st):                             # the E-3's 48 h replacement clock runs by the turn
            st.note(ln)
        if clock.day_of(st.turn) != st.day:
            self._midnight(sim)
        else:
            update_status(st)
        if st.status == "ACTIVE":
            self.plan_turn()                                                  # the new turn's tasking (v0.41.338: every turn plans on its own)

    def _midnight(self, sim) -> None:
        """The clock crossed 24:00: yesterday's end block (it used to be the end of every Skip or Fly), then tomorrow's plan."""
        st = self.state
        g = st.ground
        if not (g or {}).get("flew_today"):                                  # a day you did not fly at all: both sides still bomb each other's depots and fuel in the background (v0.41.144)
            for ln in ground.supply_round(st, self.d, sim.rng):
                st.note("Overnight: " + ln)
        if g:
            g["stand_down"] = not g.get("flyable_today")                     # nothing to fly all day: the Tactical Edge does not decay tonight (war.end_day, v0.41.164)
        sim.end_day(st)
        if st.ground:
            st.ground.pop("stand_down", None)
            st.ground["flew_today"] = st.ground["flyable_today"] = False
        st.plan_done = []
        if st.status == "ACTIVE":
            self._begin_day()                                                 # tomorrow's day-level plan; the turn's own tasking follows in `_tick`

    def _book(self, book: dict, pkg, lost_by: dict, limped_by: dict | None = None, flew_by: dict | None = None, only: set | None = None) -> None:
        """Add a package's flights to the turn's sortie book. A planned CAP sortie (`f.tag`) appears in every package it covers, so it is keyed by squadron and callsign and counted
        once; any other flight is its own sortie. `lost_by` / `limped_by` / `flew_by`: flight id -> jets; `only`: just these flight ids (a flown mission built only some)."""
        st = self.state
        launch = clock.day_start_minute(st.day) + _hm(pkg.start)
        for f in pkg.flights:
            if f.squadron_id not in st.squadrons or (only is not None and f.id not in only):
                continue
            key = f"{f.squadron_id}:{f.callsign}" if f.tag else f.id
            e = book.setdefault(key, {"unit": st.squadrons[f.squadron_id], "side": "blue", "launch_min": launch, "flew": 0, "lost": 0, "limped": None, "tag": bool(f.tag), "key": key})
            n = int(flew_by.get(f.id, f.count)) if flew_by is not None else f.count
            e["flew"] = max(e["flew"], n) if f.tag else e["flew"] + n
            e["lost"] += int(lost_by.get(f.id, 0))
            if limped_by is not None:
                e["limped"] = (e["limped"] or 0) + int(limped_by.get(f.id, 0))
            e["launch_min"] = min(e["launch_min"], launch)

    def _sorties(self, book: dict) -> list:
        """The book as `refit.commit_turn` wants it, plus the standing patrols (Phase 4b). A planned CAP sortie (`f.tag`) that rode in several packages is committed once (`barcap["blue_committed"]`, by
        `squadron:callsign`, reset every turn); it is committed with the launch time and stay of its own plan, not the package's. Every pair the turn planned that no package booked (it covered none, or the
        package that carried it was scrubbed or not flown) is committed here by its callsign or, with none, its flight id: a planned patrol takes its jets out of the ready pool whether or not a package met it."""
        st = self.state
        bc = st.barcap if st.barcap is not None else {}
        done = set(bc.get("blue_committed", []))
        day0 = clock.day_start_minute(st.day)
        planned = {}                                                                 # this turn's planned flights, by the key a package books them under
        for f in bc.get("blue_flights") or []:
            if f.get("turn") == st.turn and f["squadron"] in st.squadrons:
                planned[f"{f['squadron']}:{f['callsign']}" if f.get("callsign") else f["id"]] = f
        out = []
        for key, e in book.items():
            if e["tag"]:
                if key in done:
                    continue
                done.add(key)
                pf = planned.get(key)
                if pf is not None:
                    e["launch_min"], e["sortie_min"] = day0 + pf["start"], max(refit.SORTIE_MIN, pf["end"] - pf["start"])
                    e["lost"] = max(e["lost"], int(pf.get("lost", 0)))
            out.append(e)
        for key, f in planned.items():
            if key in done:
                continue
            done.add(key)
            out.append({"unit": st.squadrons[f["squadron"]], "side": "blue", "launch_min": day0 + f["start"], "flew": int(f["size"]), "lost": int(f.get("lost", 0)), "limped": None, "tag": True, "key": key,
                        "sortie_min": max(refit.SORTIE_MIN, f["end"] - f["start"])})
        if st.barcap is not None:
            st.barcap["blue_committed"] = sorted(done)
        return out + self._red_sorties()

    def _red_sorties(self) -> list:
        """The red patrol and sweep pairs this turn planned (v0.41.340, Phase 5a), as `refit.commit_turn` wants them: one sortie per pair, unit = the RedSquadron it was crewed from, its own launch
        time and stay (`sortie_min` = max(`refit.SORTIE_MIN`, end - start)). Red has no per-flight record of what the war sim or a flown mission took from a pair, so `lost` is 0 here: the jets
        that were shot down are already off `available` (`commit_flight` never moves more than `available`, so a lost jet is not put into refit). One commit per pair, flown or not."""
        st = self.state
        day0 = clock.day_start_minute(st.day)
        owner = {q.id: q for w in st.enemy_air for q in w.sqns}
        return [{"unit": owner[f["squadron"]], "side": "red", "launch_min": day0 + f["start"], "flew": int(f["size"]), "lost": 0, "limped": None, "tag": True, "key": f["id"],
                 "sortie_min": max(refit.SORTIE_MIN, f["end"] - f["start"])}
                for f in (st.red_air or {}).get("flights", []) if f.get("turn") == st.turn and f.get("squadron") in owner]

    def _retire(self, done: list) -> None:
        """Packages that were resolved (flown or by the war simulation) leave the plan and join `state.plan_done` with their verdict, so a later turn's mission can show them as ruins."""
        st = self.state
        nums = {pd["number"] for pd, _roll in done}
        for pd, roll in done:
            d = copy.deepcopy(pd)
            d.setdefault("extra", {})["done_roll"] = roll
            st.plan_done.append(d)
        st.plan = [d for d in st.plan if d["number"] not in nums]
        rt = {k: v for k, v in ((st.raids or {}).get("retask") or {}).items() if st.turn - v[0] <= RETASK_KEEP_TURNS}
        for pd, _roll in done:                                       # the re-tasking rule (`_retask_skip`): a target that was attacked is left alone for RETASK_TURNS turns
            o_ = pd.get("objective") or {}
            a_ = st.assets.get(o_.get("target_id", ""))
            if a_ is not None and o_.get("type") in ("STRIKE", "DEAD", "CAS") and not (pd.get("extra") or {}).get("scrub"):
                rt[a_.id] = [st.turn, a_.health]
        if st.raids is not None:
            st.raids["retask"] = rt

    def _resolve_turn(self, sim, skip=(), forces: dict | None = None, book: dict | None = None) -> tuple:
        """Resolve this turn's packages by the war simulation, except the numbers in `skip` (the ones flown). `forces`: package number (as text) -> the verdict the player saw as ruins.
        -> (results, the sortie book); a scrubbed package flew nothing and books nothing."""
        st = self.state
        book = {} if book is None else book
        results, done = [], []
        for pd in [d for d in st.plan if d["number"] not in skip]:
            pkg = Package.from_dict(pd)
            r = sim.resolve_abstract(st, pkg, force=(forces or {}).get(str(pd["number"])))
            results.append(r)
            done.append((pd, r["roll"]))
            if not r.get("scrubbed"):
                self._book(book, pkg, r.get("lost_by") or {})
        self._retire(done)
        return results, book

    def _flown_book(self, out: dict, flown: set, book: dict) -> None:
        """The sorties of a flown mission: the flights the manifest really built (`out["flights"]`, from apply_debrief) of the package that was flown and the merged ones really flown."""
        info = out.get("flights") or {}
        for pd in self.state.plan:
            if pd["number"] not in flown:
                continue
            pkg = Package.from_dict(pd)
            mine = {f.id for f in pkg.flights if f.id in info}
            self._book(book, pkg, {i: info[i]["lost"] for i in mine}, {i: info[i]["limped"] for i in mine}, {i: info[i]["flew"] for i in mine}, mine)

    # ---- results -------------------------------------------------------------------------------------
    def manifest(self) -> Manifest | None:
        return Manifest.from_dict(self.state.pending["manifest"]) if self.state and self.state.pending else None

    def poll(self, path=None):
        """-> (status, data, tally). status in none|stale|mismatch|busy|ok."""
        man = self.manifest()
        if man is None:
            return "none", None, None
        status, data = read_state_file(Path(path) if path else self.settings.state_file, man,
                                       None if path else self.state.pending["built_at"] - 2)
        return status, data, (tally(self.state, man, data) if status == "ok" else None)

    def load_manual(self, path):
        """Manually Submit: any file the user picks, checked against the pending sortie."""
        return self.poll(path)

    def abort(self) -> None:
        """Throw the built sortie away. The sortie counter goes back too (v0.41.0): it feeds the mission seed, so flying the same package again
        rebuilds the same layout (sites, spawns, patrols), and two test runs of one package can be compared."""
        if self.state.pending is not None and self.state.sortie_counter > 0:
            self.state.sortie_counter -= 1
        self.state.pending = None
        self.save()

    def apply(self, data: dict) -> dict:
        """Accept results: apply the flown sortie, resolve the turn's other packages, send the turn's jets to refit, move the clock one turn (and through the night, night ops off), autosave."""
        st = self.state
        man = self.manifest()
        pend = st.pending
        out = apply_debrief(st, man, data)
        if out["player"] == "lost":                 # you can't die: a lost jet means you bailed out and were rescued
            out["player"] = "ejected"
        pl = st.pilot or {"name": st.player.callsign, "sorties": 0, "flight_s": 0, "kills_air": 0, "kills_ground": 0,
                          "kills_ship": 0, "landings": 0, "rescues": 0, "airframes_lost": 0, "first_date": str(st.campaign_date())}
        pi = out["pilot"]
        pl["sorties"] += 1; pl["flight_s"] += pi["flight_s"]
        pl["kills_air"] += pi["ka"]; pl["kills_ground"] += pi["kg"]; pl["kills_ship"] += pi["ks"]
        pl["landings"] += 1 if out["player"] == "recovered" else 0
        if out["player"] == "ejected":
            pl["rescues"] += 1; pl["airframes_lost"] += 1
        pl["last_date"] = str(st.campaign_date())
        st.pilot = pl
        out["objective"], out["objective_type"] = pend["objective"], pend["objective_type"]
        rng = self._rng(33 + 1000 * st.turn)
        out["story"] = narrative.debrief_story(out, st, rng)
        out["tempo"] = tempo.record(st, pend["objective_type"], tempo.tone_of(out), tempo.credits(out))      # v0.41.147: the flown result nudges the background jobs of its kind (and resets the idle clock)
        out.setdefault("lines", []).extend(out["tempo"])
        sim = self._sim(rng)
        t_end = float(data.get("time", 0) or 0)
        real = {m["number"] for m in pend.get("merged", []) if t_end >= m["tot_s"] + 90}    # their strike was really flown; the rest are dice
        out["merged_real"] = sorted(real)
        flown = {pend["package"]} | real
        book = {}
        self._flown_book(out, flown, book)                                  # the mission's own sorties first: losses are already off `available` (apply_debrief)
        meanwhile, book = self._resolve_turn(sim, skip=flown, forces=pend.get("ruins"), book=book)      # ruins you saw = what happened
        out["meanwhile"] = meanwhile
        st.history.append({"day": st.day, "turn": st.turn, "date": str(st.campaign_date()), "sortie": man.sortie, "objective": pend["objective"], "player": out["player"],
                           "kills": out["pilot"]["ka"] + out["pilot"]["kg"] + out["pilot"]["ks"], "flight_min": out["pilot"]["flight_s"] // 60,
                           "blue_air_lost": out["blue_air_lost"], "red_air_lost": out["red_air_lost"],
                           "target_damage": out["target_damage"]})
        self._retire([(pd, {"success": bool(out.get("target_damage", 0.0) >= 0.3) if pd["number"] == pend["package"] else True}) for pd in st.plan if pd["number"] in flown])
        st.pending = None
        out["turn_label"] = self.turn_label()
        out["night"] = self.advance_turn(book, sim)                         # the turn ends; the night after it is resolved for you when night ops are off
        out["status"] = st.status
        self.save()
        return out
