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
from .models import ObjectiveType
from .mission_builder import MissionBuilder, MissionOptions
from .packages import Ledger, NoPlayerSlot, Package, PackageBuilder
from .scenario import new_campaign
from . import theatres
from .settings import AppSettings
from .state import CampaignState
from .war import ObjectivePlanner, WarSimulator, update_status


class Session:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.state: CampaignState | None = None
        self.path: Path | None = None
        self.last_build = None
        self.options = MissionOptions()
        self.loadouts = LoadoutLibrary(Path(settings.sqe_dir) / "loadouts.json" if settings.dcs_saves else None)
        self.sync_terrain()

    def sync_terrain(self) -> None:
        """Point the land / water checks at the terrain scan DCS measured (if it has been run) and at the shore margin from Settings."""
        from . import seacheck, terrainmask
        seacheck.SITE_MARGIN = float(getattr(self.settings, "shore_margin_m", 1500))
        terrainmask.RIVER_MARGIN = float(getattr(self.settings, "river_margin_m", 100))
        terrainmask.configure(self.settings.sqe_dir if self.settings.dcs_saves else None)

    # ---- persistence ---------------------------------------------------------------------------
    @property
    def d(self):
        return get_difficulty(self.state.level)

    def campaigns_dir(self) -> Path:
        return self.settings.sqe_dir

    def list_campaigns(self) -> list:
        d = self.campaigns_dir()
        return sorted(d.glob(f"*{CAMPAIGN_EXT}"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []

    def new(self, name: str, aircraft: str, level: int, seed: int | None = None, start_date: str = "2004-06-12", night_ops: bool = False,
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
        objs = ObjectivePlanner(self.d).plan(st, self._rng(), limit=self.PACKAGES_PER_DAY)
        pb = PackageBuilder(st, self.d)
        psq = st.player.squadron_id if st.player else None

        def build_all(forced: set) -> list:
            # Packages launch at different times of day, so an aircraft can fly more than one sortie: each package sees every
            # serviceable airframe, but no squadron is asked for more than two sorties per airframe per day.
            daily = {sid: 2 * q.available for sid, q in st.squadrons.items()}
            out = []
            for i, o in enumerate(objs, 1):
                ledger = Ledger(st)
                for sid in ledger.free:
                    ledger.free[sid] = min(ledger.free[sid], daily[sid])
                pkg = None
                for fp in ((True, False) if (i - 1) in forced else (False,)):
                    try:
                        pkg = pb.build(o, i, ledger, for_player=fp)
                        break
                    except NoPlayerSlot:
                        continue
                if pkg is None:
                    continue
                for f in pkg.flights:
                    daily[f.squadron_id] -= f.count
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
        pkgs.sort(key=lambda p: p.start)
        for n, p in enumerate(pkgs, 1):                              # numbers follow the clock
            p.number, p.id = n, f"pkg{n}"
            for k, f in enumerate(p.flights, 1):
                f.id = f"{p.id}-f{k}"
        st.plan = [p.to_dict() for p in pkgs]
        self.refresh_weather()
        return self.packages()

    def packages(self) -> list:
        return [Package.from_dict(d) for d in self.state.plan]

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
        opts = pkg.player_options(self.state.player.aircraft)
        return [f for f in opts if f.squadron_id == self.state.player.squadron_id] if squadron_only else opts

    # ---- merge area: a circle around the package's target, kept inside the area where targets exist ---------------------
    def merge_radius_m(self) -> float:
        return max(5.0, float(getattr(self.settings, "merge_radius_nm", 50))) * 1852.0

    def _pkg_xy(self, p: Package):
        """The ground target of a package, or None for fleet packages (BARCAP, fleet defence), which are never folded by area."""
        if p.objective.type in (ObjectiveType.BARCAP, ObjectiveType.FLEET_DEFENSE):
            return None
        a = self.state.assets.get(p.objective.target_id)
        return (a.x, a.y) if a is not None else None

    def _near(self, a: Package, b: Package, R: float) -> bool:
        pa, pb = self._pkg_xy(a), self._pkg_xy(b)
        return pa is not None and pb is not None and math.hypot(pa[0] - pb[0], pa[1] - pb[1]) <= R

    def merge_center(self, pkg: Package, R: float | None = None):
        """The centre of the merge circle: your target, slid inward so the whole circle stays inside the box that holds every possible target
        (destroyed sites included, so it does not shrink as the war goes on). Your own target always stays inside the circle."""
        R = self.merge_radius_m() if R is None else R
        t = self._pkg_xy(pkg)
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
        out.sort(key=lambda r: r[:3])
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
               and any(not f.tag for f in p.flights) and not p.extra.get("scrub") and inside(p)]
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

    # ---- fly ---------------------------------------------------------------------------------------
    def fly(self, package_number: int, flight_id: str | None):
        st = self.state
        pkg = next(p for p in self.packages() if p.number == package_number)
        PackageBuilder(st, self.d).assign_player(pkg, flight_id)
        problems = self.settings.problems()
        if problems:
            raise RuntimeError("; ".join(problems))
        self.options.hold_minutes = int(self.settings.hold_minutes)
        self.options.launch_offset_s = int(self.settings.takeoff_buffer_s)
        self.options.ai_unlimited_fuel = bool(self.settings.ai_unlimited_fuel)
        self.options.enemy_cap_engage_nm = int(self.settings.enemy_cap_engage_nm)
        self.options.friendly_cap_engage_nm = int(self.settings.friendly_cap_engage_nm)
        self.options.f14_special_names = bool(getattr(self.settings, 'f14_special_names', True)); self.options.merge_enemy_pct = int(self.settings.merge_enemy_pct); self.options.weather_mode = str(getattr(self.settings, 'weather_mode', 'clear'))
        import contextlib, io, logging
        logging.getLogger("pydcs").setLevel(logging.CRITICAL)
        extras = self.merge_candidates(pkg)
        ruins = self.ruin_candidates(pkg, extras)
        pre = self._preroll(list(extras) + ruins) if (ruins or extras) and getattr(self.settings, "ruins", True) else {}
        cap = int(self.settings.merge_max_units)
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
