"""Session: the single API the GUI (and the smoke test) talk to. No Qt in here."""
from __future__ import annotations
import json
import random
import time
from pathlib import Path

from . import CAMPAIGN_EXT, narrative
from .aircraft import AIRCRAFT
from .debrief import Manifest, apply_debrief, read_state_file, tally
from .difficulty import get as get_difficulty
from .loadouts import LoadoutLibrary
from .mission_builder import MissionBuilder, MissionOptions
from .packages import Ledger, NoPlayerSlot, Package, PackageBuilder
from .scenario import new_campaign
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
            squadron: str | None = None) -> None:
        self.state = new_campaign(name, aircraft, level, seed=seed, start_date=start_date, night_ops=night_ops, player_squadron=squadron)
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip() or "campaign"
        self.path = self.campaigns_dir() / f"{safe}{CAMPAIGN_EXT}"
        self.plan_day()
        self.save()

    def open(self, path) -> None:
        self.state = CampaignState.load(path)
        self.path = Path(path)
        self.settings.last_campaign = str(path)
        self.settings.save()
        if not self.state.plan:
            self.plan_day()

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
        for i in range(len(pkgs)):
            for j in range(i + 1, len(pkgs)):
                if packages_linked(st, pkgs[i], pkgs[j]):
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
        return pkgs

    def packages(self) -> list:
        return [Package.from_dict(d) for d in self.state.plan]

    def flyable(self, pkg: Package, squadron_only: bool | None = None) -> list:
        """Flights you could fly. 'My squadron' (the default filter) = flights of YOUR squadron; 'all' = any flight of your aircraft type."""
        if squadron_only is None:
            squadron_only = self.settings.flight_filter != "all"
        opts = pkg.player_options(self.state.player.aircraft)
        return [f for f in opts if f.squadron_id == self.state.player.squadron_id] if squadron_only else opts

    def merge_candidates(self, pkg: Package) -> list:
        """Packages that would be folded into a mission built around `pkg`: same area, starting up to 30 minutes AFTER it, or up to
        `merge_back_min` minutes BEFORE it (those are already underway when the mission starts), at most two extra (three packages in all),
        the ones closest in time first. Empty when merging is off."""
        if self.settings.merge_mode != "area":
            return []
        from .packages import packages_linked
        hm = lambda p: int(p.start[:2]) * 60 + int(p.start[3:5])
        back = max(0, int(getattr(self.settings, "merge_back_min", 15)))
        out = [p for p in self.packages() if p.number != pkg.number and -back <= hm(p) - hm(pkg) <= 30
               and any(not f.tag for f in p.flights) and packages_linked(self.state, pkg, p)]
        out.sort(key=lambda p: (abs(hm(p) - hm(pkg)), hm(p), p.number))
        out = out[:2]
        out.sort(key=lambda p: (hm(p), p.number))
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
        self.options.f14_special_names = bool(getattr(self.settings, 'f14_special_names', True)); self.options.merge_enemy_pct = int(self.settings.merge_enemy_pct)
        import contextlib, io, logging
        logging.getLogger("pydcs").setLevel(logging.CRITICAL)
        extras = self.merge_candidates(pkg)
        cap = int(self.settings.merge_max_units)
        while True:
            with contextlib.redirect_stdout(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated DCS files
                res = MissionBuilder(st, self.d, self.options, self.loadouts, self._rng(9)).build(pkg, self.settings.sortie_miz, extras)
            if not extras or res.counts["units"] <= cap:
                break
            extras = extras[:-1]                                 # too heavy for VR: drop the last package and rebuild
            res.warnings.append(f"merged mission trimmed to fit the {cap}-unit limit")
        st.sortie_counter += 1
        st.pending = {"package": package_number, "flight": pkg.player_flight.id, "manifest": res.manifest.to_dict(),
                      "built_at": time.time(), "miz": str(res.miz), "timeline": res.timeline,
                      "objective": pkg.objective.description, "objective_type": pkg.objective.type.value, "counts": res.counts, "warnings": res.warnings, "seed": res.seed,
                      "package_dict": pkg.to_dict(), "merged": res.manifest.merged}
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
        st.note(f"Day {st.day}: you stood down. The war went on without you ({sum(1 for r in results if r['success'])} of {len(results)} packages succeeded).")
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
            r = sim.resolve_abstract(st, Package.from_dict(pd))
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
