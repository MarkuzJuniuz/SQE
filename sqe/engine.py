"""Session: the single API the GUI (and the smoke test) talk to. No Qt in here."""
from __future__ import annotations
import json
import math
import random
import time
from pathlib import Path

from . import CAMPAIGN_EXT, narrative
from .aircraft import AIRCRAFT
from .debrief import Manifest, apply_debrief, read_state_file, tally
from .difficulty import get as get_difficulty
from .loadouts import LoadoutLibrary
from .models import Objective, ObjectiveType, Role
from . import raids, redair, sams
from .mission_builder import MissionBuilder, MissionOptions
from .packages import AI_ONLY, Ledger, NoPlayerSlot, Package, PackageBuilder

RAID_SCRAMBLES = True      # v0.41.27: emergency raid scrambles are off while intercepts are AI-only (troops in contact stay)
from .scenario import new_campaign
from . import theatres
from .settings import AppSettings
from .state import CampaignState
from .war import ObjectivePlanner, WarSimulator, update_status



SEAD_SYNC_KM = 60            # SEAD packages whose targets are this close together are synchronised (the same ground, the same defence)
SEAD_SYNC_ON = True          # off only in tests that need an unsynchronised day (the merge-underway case)
SWEEP_AREA_KM = 60           # packages whose targets are this close together share one Fighter Sweep
SWEEP_LEAD_MIN = 10          # the sweep starts this much ahead of the first package it covers
LATE_SEAD_MIN = 15           # launch option --late-sead: SEAD-stage packages go in this much later, so the DEAD stage (10 min behind) arrives
                             # about 5 min ahead of them and reaches its gate with the radars still up: it holds (HOLD_S = 12 min) and goes in once
                             # the late SEAD blinds the site. A test of the hold; it changes that day's plan in the save.

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
        relief.configure(self.settings.sqe_dir if self.settings.dcs_saves else None)
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
        self.state = CampaignState.load(path)
        theatres.use(self.state.theatre)
        self.sync_terrain()
        self.path = Path(path)
        self.settings.last_campaign = str(path)
        self.settings.save()
        from .scenario import snap_assets_to_land
        moved = snap_assets_to_land(self.state)          # older campaigns generated some sites in the sea
        if moved:
            self.state.note(f"{moved} enemy sites that were placed in the water have been moved onto land.")
        if not self.state.plan:
            self.plan_day()
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
        return random.Random(int(self.state.campaign_id, 16) % 10_000_019 + self.state.day * 101 + salt)

    PACKAGES_PER_DAY = 14

    def plan_day(self) -> list:
        st = self.state
        from . import ground
        ground.ensure_blue_garrisons(st)                # older saves: a friendly garrison at every airfield
        sams.ensure_blue_sams(st)                       # v0.41.62: blue's three air-defence sites at every airfield (older saves: from the field's `defense`)
        ground.snap_roads(st)                           # once, as soon as a road scan exists: columns and supply sites sit on a road
        redair.ensure(st, self.d)                       # the enemy's air tasking for the day
        objs = ObjectivePlanner(self.d).plan(st, self._rng(), limit=self.PACKAGES_PER_DAY)
        redair.assign_guards(st, self.d, objs)          # v0.41.10: red's patrols take stations over the SAM sites it expects to be attacked
        keep = {k: v for k, v in (st.raids or {}).items() if k in ("last_emerg", "carry", "sead_fail")}
        if st.red_air.get("patrol_used") is not None:                 # replanning the same day never books the raids twice
            st.red_air["used"] = dict(st.red_air["patrol_used"])
        warned, n_surprise = raids.todays_raids(st, self.d, self._rng(71))
        carry = self._carried(objs)
        objs = carry + objs + warned                    # postponed from yesterday first, then the day's job list, then the announced raids
        st.raids = {**keep, "day": st.day, "surprise": n_surprise, "carry": []}
        pb = PackageBuilder(st, self.d)
        psq = st.player.squadron_id if st.player else None

        sweeps = {}                                     # id(sweep package) -> the packages it goes in ahead of

        def build_all(forced: set) -> list:
            sweeps.clear()
            # Packages launch at different times of day, so an aircraft can fly more than one sortie: each package sees every
            # serviceable airframe, but no squadron is asked for more than two sorties per airframe per day.
            daily = {sid: 2 * q.available for sid, q in st.squadrons.items()}
            out, names = [], {}          # callsign counter for the whole day: Enfield 1, Enfield 2 ... never two Enfield 1s
            for i, o in enumerate(objs, 1):
                ledger = Ledger(st)
                for sid in ledger.free:
                    ledger.free[sid] = min(ledger.free[sid], daily[sid])
                pkg = None
                for fp in ((True, False) if ((i - 1) in forced and o.type not in AI_ONLY) else (False,)):
                    try:
                        pkg = pb.build(o, i, ledger, for_player=fp, names=names)
                        break
                    except NoPlayerSlot:
                        continue
                if pkg is None:
                    continue
                for f in pkg.flights:
                    daily[f.squadron_id] -= f.count
                out.append(pkg)
            # Fighter Sweep (v0.40.2): where intel expects more enemy fighters than the packages' own TARCAP and escort can take, a sweep
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
                o = Objective(f"obj-d{st.day}-sw{k + 1}", ObjectiveType.COUNTER_AIR, t.id, max(p.objective.priority for p in covered),
                              f"Fighter Sweep: clear the air over {t.name} ahead of the strikes", "SWEEP")
                ledger = Ledger(st)
                for sid in ledger.free:
                    ledger.free[sid] = min(ledger.free[sid], daily[sid])
                pkg = None
                for fp in ((True, False) if (sp_spec and Role.SWEEP in sp_spec.roles) else (False,)):
                    try:
                        pkg = pb.build(o, len(objs) + k + 1, ledger, for_player=fp, names=names)
                        break
                    except NoPlayerSlot:
                        continue
                if pkg is None or not pkg.flights:
                    continue
                for f in pkg.flights:
                    daily[f.squadron_id] -= f.count
                sweeps[id(pkg)] = covered
                out.append(pkg)
            return out

        mine = lambda pk: sum(1 for p in pk if any(f.squadron_id == psq and not f.tag for f in p.flights))
        rng = self._rng(3)
        pkgs = build_all(set(rng.sample(range(len(objs)), min(len(objs), 5))))     # your squadron is tasked on a handful of them
        if mine(pkgs) < 3:
            pkgs = build_all(set(range(len(objs))))
        # same-area packages are launched in the same wave (so they can be folded together), waves spread through the day
        from .packages import packages_linked
        from .timeofday import wave_times
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
        times = wave_times(len(pkgs), st.campaign_date(), st.night_ops, self._rng(5))
        for i, t in zip(order, times):
            pkgs[i].start = t
        self._sync_sead(pkgs)                                        # SEAD flights on the same ground (within SEAD_SYNC_KM) arrive together, not one after another
        self._stage_times(pkgs)                                      # a DEAD stage goes in DEAD_STAGE_GAP_MIN after the SEAD stage of the same site
        self._late_sead(pkgs)                                        # test option --late-sead: the SEAD stage goes in late, so the DEAD stage holds
        from . import sweep as sweep_
        dropped = set()
        for p in pkgs:                                               # a Fighter Sweep starts SWEEP_LEAD_MIN ahead of the first package it covers (after every other timing step)
            cov = sweeps.get(id(p))
            if cov:
                first_ = min(int(c.start[:2]) * 60 + int(c.start[3:5]) for c in cov)
                m = max(0, first_ - SWEEP_LEAD_MIN)
                p.start = f"{m // 60:02d}:{m % 60:02d}"
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
        pkgs.sort(key=lambda p: p.start)
        for n, p in enumerate(pkgs, 1):                              # numbers follow the clock
            p.number, p.id = n, f"pkg{n}"
            for k, f in enumerate(p.flights, 1):
                f.id = f"{p.id}-f{k}"
        for p in pkgs:
            if sweeps.get(id(p)):
                p.extra["covers"] = sorted(c.number for c in sweeps[id(p)])           # the packages this Fighter Sweep goes in ahead of
        st.plan = [p.to_dict() for p in pkgs]
        self._cast_sead(pkgs)
        self.refresh_weather()
        return self.packages()

    def _harm_leg_s(self, p) -> float | None:
        """Seconds from PUSH to the HARM point for this SEAD package's first HARM flight, from the same marshal, geometry and route the
        mission builder will use (an umbrella keep-out included). Within one mission every package pushes exactly its start difference after
        the others, so this leg is all that separates their HARM times."""
        from .models import BaseKind
        from .routes import HARM_LAUNCH_NM, assign_times, bearing, make_geometry, objective_wp, plan_route
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
                             keep_out=(um.x, um.y, HARM_LAUNCH_NM) if um else None)
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
            leg = self._harm_leg_s(p)
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

    def _stage_times(self, pkgs: list) -> None:
        """Keep each DEAD-stage package DEAD_STAGE_GAP_MIN after the SEAD-stage package of the same site (waves would otherwise spread them)."""
        from .war import DEAD_STAGE_GAP_MIN
        sead = {p.objective.target_id: p for p in pkgs if p.objective.type == ObjectiveType.DEAD and p.objective.aim == "SEAD"}
        for p in pkgs:
            sp = sead.get(p.objective.target_id)
            if p.objective.type == ObjectiveType.DEAD and p.objective.aim == "DEAD" and sp is not None:
                m = min(23 * 60 + 55, int(sp.start[:2]) * 60 + int(sp.start[3:5]) + DEAD_STAGE_GAP_MIN)
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
        """The dice for every SEAD package of the day are cast now, once (seeded from the campaign, the day and the site): the war simulation, the
        DEAD stage's briefing and the mission builder all read the same answer. Flying the SEAD package replaces it with what really happened."""
        import random as _r
        from .war import WarSimulator, chance
        st = self.state
        st.raids.setdefault("sead", {})
        sim = WarSimulator(self.d)
        from .models import SEAD_AIMS
        for p in pkgs:
            if p.objective.type == ObjectiveType.DEAD and p.objective.aim in SEAD_AIMS:
                rng = _r.Random(f"{st.campaign_id}:{st.day}:{p.objective.target_id}:sead")
                st.raids["sead"][p.objective.target_id] = chance(rng, sim.sead_p(st, p), self.d.variance)

    def idle_reasons(self) -> list:
        """Why your squadron has nothing to fly today, from the facts at hand (shown when the Missions list has no flight for you)."""
        st = self.state
        sq = st.squadrons[st.player.squadron_id]
        spec = AIRCRAFT[sq.aircraft]
        pk = self.packages()
        out = []
        if sq.available < 2:
            out.append(f"{sq.name} has {sq.available} of {sq.authorized} aircraft serviceable, not enough for a pair.")
        if not pk:
            out.append("No jobs are open on today's tasking order.")
        elif not any(f.role in spec.roles for p in pk for f in p.flights if not f.tag):
            out.append(f"Nothing on today's tasking order is a job for {spec.display} ({', '.join(sorted(r.value for r in spec.roles))}).")
        elif sq.available >= 2:
            out.append("Today's jobs were given to other squadrons, or are out of reach of your base.")
        return out

    def packages(self) -> list:
        """The tasking order. Emergency packages (flown, folded in or settled by odds) are in the plan but are not listed."""
        return [p for p in (Package.from_dict(d) for d in self.state.plan) if not p.extra.get("past")]

    def _carried(self, objs: list) -> list:
        """Objectives postponed yesterday (no aircraft left for them after an emergency scramble), if they are still worth flying and not already in the list."""
        st, out = self.state, []
        for od in (st.raids or {}).get("carry", []):
            if od["type"] == "DEAD" and od.get("aim"):
                continue                                        # a SEAD / DEAD stage is planned fresh with its partner, never carried alone
            o = Objective(od["id"], ObjectiveType(od["type"]), od["target_id"], od["priority"] + 2.0, od.get("description", ""), od.get("aim", ""))
            tgt = st.assets.get(o.target_id) or st.bases.get(o.target_id)
            if tgt is None or getattr(tgt, "destroyed", False) or any(x.type == o.type and x.target_id == o.target_id for x in objs + out):
                continue
            out.append(o)
        return out

    # ---- weather: what the sky does to each package of the day ------------------------------------------------------
    def weather_mode(self) -> str:
        return str(getattr(self.settings, "weather_mode", "clear") or "clear")

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
            wx = W.for_package(st, mode, pack, pkg.start)
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
        if pkg.objective.type in AI_ONLY:                                 # v0.41.27: AI-only for now (BARCAP, bomber and raid intercepts)
            return []
        opts = pkg.player_options(self.state.player.aircraft)
        return [f for f in opts if f.squadron_id == self.state.player.squadron_id] if squadron_only else opts

    # ---- merge area: a circle around the package's target, kept inside the area where targets exist ---------------------
    def merge_radius_m(self) -> float:
        return max(5.0, float(getattr(self.settings, "merge_radius_nm", 25))) * 1852.0

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
        c, t = self.merge_center(anchor), self._pkg_xy(other)
        return c is not None and t is not None and math.hypot(t[0] - c[0], t[1] - c[1]) <= self.merge_radius_m()

    def _postpone_if_short(self, orig: Package, emerg: Package) -> None:
        """You took the emergency, so your squadron's aircraft are spent on it first. If it cannot also cover the package you were tasked with, that
        package is not dice-rolled with missing aircraft: it is postponed to tomorrow's tasking order."""
        st = self.state
        sid = st.player.squadron_id
        need = sum(f.count for f in emerg.flights if f.squadron_id == sid) + sum(f.count for f in orig.flights if f.squadron_id == sid)
        if st.squadrons[sid].available >= need:
            return
        st.plan = [d for d in st.plan if d["number"] != orig.number]
        st.raids.setdefault("carry", []).append(orig.objective.to_dict())
        st.note(f"Package #{orig.number} ({orig.objective.description}) is postponed to tomorrow: {st.squadrons[sid].name} cannot cover both.")

    def merge_candidates(self, pkg: Package) -> list:
        """Packages folded into a mission built around `pkg`: every package whose target lies inside the merge circle (Settings: radius, default
        50 nm, centred by merge_center), starting up to 30 minutes AFTER it or up to `merge_back_min` minutes BEFORE it (those are already underway
        when the mission starts). At most six, closest to the centre first, so the unit limit drops the furthest first. Empty when merging is off."""
        if self.settings.merge_mode != "area":
            return []
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        back = max(0, int(getattr(self.settings, "merge_back_min", 15)))
        R = self.merge_radius_m()
        c = self.merge_center(pkg, R)
        if c is None:
            return []
        out = []
        for p in self.packages():
            t = self._pkg_xy(p)
            if p.number == pkg.number or t is None or not (-back <= hm(p) - hm(pkg) <= 30) or not any(not f.tag for f in p.flights) or p.extra.get("scrub"):
                continue
            d = math.hypot(t[0] - c[0], t[1] - c[1])
            if d <= R:
                out.append((d, hm(p), p.number, p))
        out.sort(key=lambda r: (not (r[3].objective.type == ObjectiveType.COUNTER_AIR and r[3].objective.aim == "SWEEP"),) + r[:3])     # a Fighter Sweep first: the unit limit drops the strike packages before it
        return [r[3] for r in out[:6]]

    def ruin_candidates(self, pkg: Package, extras: list) -> list:
        """Earlier packages of the same day, same area, that may already have struck when your mission starts: their targets are shown as ruins.
        The closest in time first, at most four looked at (the builder shows at most three)."""
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
        out = [p for p in self.packages() if p.number != pkg.number and p.number not in have and hm(p) < hm(pkg)
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
            sim = WarSimulator(self.d, self._rng(55 + p.number))
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

    # ---- emergencies: something breaks out while you are about to fly (raids.py) ----------------------------------------
    def emergency_for(self, package_number: int, flight_id: str | None = None) -> dict | None:
        """The emergency, if any, that comes with flying this package right now. The answer is fixed by the campaign, the day and the package: asking
        twice (or reopening the dialog) never re-rolls it. Returns None, or a dict:
          kind 'RAID' | 'CAS', package (the emergency, ready to fly), eligible (your squadron can take it), reason (why not), title, text."""
        st, d = self.state, self.d
        if not getattr(self.settings, "emergencies", True):
            return None
        key = f"{st.day}:{package_number}:{flight_id}:{st.sortie_counter}"
        cache = (st.raids or {}).get("emerg")
        if cache and cache.get("key") == key:
            return None if cache.get("none") else self._emerg_view(cache)
        pkg = next((p for p in self.packages() if p.number == package_number), None)
        if pkg is None or not self.flyable(pkg):
            return None
        rng = raids.emergency_seed(st, package_number, flight_id)
        ev = self._make_emergency(pkg, rng) if raids.emergency_happens(st, d, rng) else None
        if st.raids is None:
            st.raids = {}
        st.raids["emerg"] = {"key": key, "none": True} if ev is None else {"key": key, **ev}
        return None if ev is None else self._emerg_view(st.raids["emerg"])

    def _emerg_view(self, c: dict) -> dict:
        return {**c, "package": Package.from_dict(c["pkg"])}

    def _make_emergency(self, pkg: Package, rng) -> dict | None:
        st, d = self.state, self.d
        psq = st.squadrons[st.player.squadron_id]
        spec = AIRCRAFT[psq.aircraft]
        committed = sum(f.count for f in pkg.flights if f.squadron_id == psq.id)
        kinds = []
        base = raids.pick_target(st, random.Random(rng.random()))       # (still drawn: the same seed gives the same day)
        # v0.41.27: no raid scrambles for you for now (an intercept is AI-only until its routes follow the SAM rules); troops in contact stay
        if base is not None and RAID_SCRAMBLES:
            kinds.append("RAID")
        sec = raids.hot_sector(st)
        cas_aim = ""
        if sec is not None:
            # v0.41.20: troops in contact under a live SA-11 / SA-10: no CAS (a DEAD comes first); under an SA-2/3/6 only with a SEAD escort
            from types import SimpleNamespace
            from .war import cas_cover
            c_ = st.assets.get(f"armor_{sec + 1}") or SimpleNamespace(x=float(st.ground["centers"][sec][0]), y=float(st.ground["centers"][sec][1]))
            cov_, hard_ = cas_cover(st, c_)
            if not hard_:
                kinds.append("CAS")
                cas_aim = "SEAD" if cov_ else ""
        if not kinds:
            return None
        fighter = bool({r.value for r in spec.roles} & {"CAP", "SWEEP"})
        kind = kinds[0] if len(kinds) == 1 else ("RAID" if rng.random() < (0.55 if fighter else 0.3) else "CAS")      # an A-10 gets mostly "troops in contact"
        number = max([p["number"] for p in st.plan] + [pkg.number]) + 1
        if kind == "RAID":
            obj = raids.raid_objective(base)
            obj.id = f"obj-d{st.day}-e{number}"
            if PackageBuilder(st, d)._land_raid_plan(number, obj) is None:
                return None
            role_needed, where = "fighter", f"{base.name}"
        else:
            from . import ground
            zi = ground.info(st, sec)
            obj = Objective(f"obj-d{st.day}-e{number}", ObjectiveType.CAS, f"armor_{sec + 1}", 12.0,
                            f"EMERGENCY - troops in contact: {zi['name']} (enemy {zi['red']:.0f}, friendly {zi['blue']:.0f})", aim=cas_aim)
            role_needed, where = "cas", zi["name"]
        pb = PackageBuilder(st, d)
        xy = pb.target_xy(obj)
        ok, why = raids.eligible(st, spec, role_needed, xy, psq, committed)
        names = {}                           # carry on the day's callsign numbering so the emergency flight never repeats a name
        for cs in [ff["callsign"] for pd in st.plan for ff in pd["flights"]] + [ff.callsign for ff in pkg.flights]:
            nm, _, no = cs.rpartition(" ")
            if no.isdigit():
                names[nm] = max(names.get(nm, 0), int(no))
        epkg = None
        for want in ((True, False) if ok else (False,)):
            ledger = Ledger(st)
            ledger.free[psq.id] = max(0, ledger.free[psq.id] - committed)         # the tasked flight keeps its own aircraft
            try:
                epkg = pb.build(obj, number, ledger, for_player=want, names=dict(names))
                ok = ok and want
                break
            except NoPlayerSlot:
                continue
        if epkg is None:
            return None
        if ok is False and not why:
            why = f"{psq.name} cannot reach it or has no free pair"
        epkg.start = pkg.start
        epkg.extra = {**epkg.extra, "emergency": kind, "past": True}
        for f in epkg.flights:
            f.is_player = False
        if kind == "RAID":
            text = (f"Bombers are inbound on {where} and nobody was warned. Alert aircraft are not enough: the fighters nearest to it are being scrambled.")
            title = "EMERGENCY SCRAMBLE"
        else:
            text = (f"Troops in contact in {where}: the position is being overrun and the JTAC is calling for anything that can reach it.")
            title = "TROOPS IN CONTACT"
        return {"kind": kind, "eligible": bool(ok), "reason": "" if ok else why, "title": title, "text": text, "pkg": epkg.to_dict(),
                "where": where, "number": number}

    # ---- fly ---------------------------------------------------------------------------------------
    def fly(self, package_number: int, flight_id: str | None, scramble: bool = False):
        """Build the sortie. If an emergency came up for this package (emergency_for) and `scramble` is True and your squadron can take it, you fly the
        emergency and the package you were tasked with goes to the war simulation (or is postponed a day if the squadron cannot cover both). Otherwise the
        emergency is folded into your mission if it is a ground job inside the merge circle, and settled by odds if it is not."""
        st = self.state
        problems = self.settings.problems()
        if problems:
            raise RuntimeError("; ".join(problems))
        pkg = next(p for p in self.packages() if p.number == package_number)
        ev = self.emergency_for(package_number, flight_id)
        lead_extras = []
        if ev:
            epkg = ev["package"]
            st.plan.append(epkg.to_dict())
            st.raids["last_emerg"] = st.sortie_counter + 1
            st.raids["emerg"] = {"key": st.raids["emerg"]["key"], "none": True}              # used: asking again gives nothing new
            self.refresh_weather()
            epkg = next(Package.from_dict(d) for d in st.plan if d["number"] == epkg.number)
            if epkg.extra.get("scrub"):
                scramble = False                                                              # weather scrubs it: nothing flies
            if scramble and ev["eligible"]:
                orig, pkg, flight_id = pkg, epkg, None
                self._postpone_if_short(orig, epkg)
                st.note(f"EMERGENCY: you were scrambled to {ev['where']} ({ev['kind'].lower()}); package #{orig.number} is left to the other squadrons.")
            else:
                st.note(f"EMERGENCY at {ev['where']}: " + ("you stayed with your tasking." if ev["eligible"] else ev["reason"] + ".") + " The war handles it.")
                if epkg.objective.type == ObjectiveType.CAS and self._inside_merge(pkg, epkg):
                    lead_extras = [epkg]
        PackageBuilder(st, self.d).assign_player(pkg, flight_id)
        self.options.hold_minutes = int(self.settings.hold_minutes)
        self.options.launch_offset_s = int(self.settings.takeoff_buffer_s)
        self.options.ai_unlimited_fuel = bool(self.settings.ai_unlimited_fuel)
        self.options.ai_skill_red = str(getattr(self.settings, "ai_skill_red", "level"))
        self.options.ai_skill_blue = str(getattr(self.settings, "ai_skill_blue", "level"))
        self.options.fighter_engage_nm = int(self.settings.fighter_engage_nm)
        self.options.fighter_engage_minutes = int(self.settings.fighter_engage_minutes)
        self.options.player_is_ai = bool(self.ai_test)
        self.options.fighter_standoff = bool(self.settings.fighter_standoff)
        self.options.carcasses = bool(getattr(self.settings, 'carcasses', True)); self.options.carcass_weight = max(5, int(getattr(self.settings, 'carcass_weight_pct', 25))) / 100.0
        self.options.reactive = bool(getattr(self.settings, 'reactive', True))
        self.options.ecm_script = bool(getattr(self.settings, 'ecm_script', False))
        self.options.splash_damage = bool(getattr(self.settings, 'splash_damage', True))
        self.options.ai_land_carrier = str(getattr(self.settings, 'ai_land_carrier', "always"))
        self.options.ai_land_field = str(getattr(self.settings, 'ai_land_field', "never"))
        self.options.max_units = int(self.settings.merge_max_units)
        self.options.full_map = bool(self.full_map)
        if self.full_map:
            self.options.max_units = 10 ** 6
        self.options.f14_special_names = bool(getattr(self.settings, 'f14_special_names', True)); self.options.merge_enemy_pct = int(self.settings.merge_enemy_pct); self.options.weather_mode = str(getattr(self.settings, 'weather_mode', 'clear'))
        import contextlib, io, logging
        logging.getLogger("pydcs").setLevel(logging.CRITICAL)
        extras = lead_extras + [x for x in self.merge_candidates(pkg) if all(x.number != y.number for y in lead_extras)]
        ruins = self.ruin_candidates(pkg, extras)
        pre = self._preroll(list(extras) + ruins) if (ruins or extras) and getattr(self.settings, "ruins", True) else {}
        cap = 10 ** 6 if self.full_map else int(self.settings.merge_max_units)
        while True:
            with contextlib.redirect_stdout(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated DCS files
                res = MissionBuilder(st, self.d, self.options, self.loadouts, self._rng(9)).build(pkg, self.settings.sortie_miz, extras, ruins, pre)
            if (not extras and not ruins) or res.counts["units"] <= cap:
                break
            if ruins:
                ruins = ruins[:-1]                               # returning flights first
            else:
                extras = extras[:-1]                             # too heavy for VR: drop the last package and rebuild
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
    def skip_day(self) -> dict:
        """Skip Turn: any pending sortie is discarded and EVERY package of the day (even ones you could have flown) is resolved
        by the war simulation. The date advances, the war replans."""
        st = self.state
        st.pending = None
        sim = WarSimulator(self.d, self._rng(44))
        results = [sim.resolve_abstract(st, Package.from_dict(pd)) for pd in st.plan]
        st.note(f"Day {st.day}: you stood down. The war went on without you ({sum(1 for r in results if r['success'])} of {sum(1 for r in results if not r.get('scrubbed'))} packages succeeded"
                f"{'; ' + str(sum(1 for r in results if r.get('scrubbed'))) + ' scrubbed for weather' if any(r.get('scrubbed') for r in results) else ''}).")
        sim.end_day(st)
        status = update_status(st)
        if st.status == "ACTIVE":
            self.plan_day()
        self.save()
        return {"results": results, "status": st.status, "text": status}

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
        """Accept results: apply the flown sortie, resolve the day's other packages, advance, replan, autosave."""
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
        rng = self._rng(33)
        out["story"] = narrative.debrief_story(out, st, rng)
        sim = WarSimulator(self.d, rng)
        meanwhile = []
        t_end = float(data.get("time", 0) or 0)
        real = {m["number"] for m in pend.get("merged", []) if t_end >= m["tot_s"] + 90}    # their strike was really flown; the rest are dice
        out["merged_real"] = sorted(real)
        for pd in st.plan:
            if pd["number"] == pend["package"] or pd["number"] in real:
                continue
            r = sim.resolve_abstract(st, Package.from_dict(pd), force=(pend.get("ruins") or {}).get(str(pd["number"])))    # ruins you saw = what happened
            meanwhile.append(r)
        out["meanwhile"] = meanwhile
        st.history.append({"day": st.day, "date": str(st.campaign_date()), "sortie": man.sortie, "objective": pend["objective"], "player": out["player"],
                           "kills": out["pilot"]["ka"] + out["pilot"]["kg"] + out["pilot"]["ks"], "flight_min": out["pilot"]["flight_s"] // 60,
                           "blue_air_lost": out["blue_air_lost"], "red_air_lost": out["red_air_lost"],
                           "target_damage": out["target_damage"]})
        sim.end_day(st)
        st.pending = None
        out["status"] = update_status(st)
        if st.status == "ACTIVE":
            self.plan_day()
        self.save()
        return out
