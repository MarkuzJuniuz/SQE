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

    def new(self, name: str, aircraft: str, level: int, seed: int | None = None, start_date: str = "2004-06-12", night_ops: bool = False) -> None:
        self.state = new_campaign(name, aircraft, level, seed=seed, start_date=start_date, night_ops=night_ops)
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

    def plan_day(self) -> list:
        st = self.state
        objs = ObjectivePlanner(self.d).plan(st, self._rng(), limit=6)
        pb, pkgs = PackageBuilder(st, self.d), []
        # Packages launch at different times of day, so an aircraft can fly more than one sortie: each package sees every
        # serviceable airframe, but no squadron is asked for more than two sorties per airframe per day.
        daily = {sid: 2 * s.available for sid, s in st.squadrons.items()}
        for i, o in enumerate(objs, 1):
            ledger = Ledger(st)
            for sid in ledger.free:
                ledger.free[sid] = min(ledger.free[sid], daily[sid])
            try:
                pkg = pb.build(o, i, ledger, for_player=True)
            except NoPlayerSlot:
                try:
                    pkg = pb.build(o, i, ledger, for_player=False)
                except NoPlayerSlot:
                    continue
            for f in pkg.flights:
                daily[f.squadron_id] -= f.count
            pkgs.append(pkg)
        from .timeofday import ato_times
        for p, t in zip(pkgs, ato_times(len(pkgs), st.campaign_date(), st.night_ops, self._rng(5))):
            p.start = t
        st.plan = [p.to_dict() for p in pkgs]
        return pkgs

    def packages(self) -> list:
        return [Package.from_dict(d) for d in self.state.plan]

    def flyable(self, pkg: Package) -> list:
        return pkg.player_options(self.state.player.aircraft)

    # ---- fly ---------------------------------------------------------------------------------------
    def fly(self, package_number: int, flight_id: str | None):
        st = self.state
        pkg = next(p for p in self.packages() if p.number == package_number)
        PackageBuilder(st, self.d).assign_player(pkg, flight_id)
        problems = self.settings.problems()
        if problems:
            raise RuntimeError("; ".join(problems))
        self.options.hold_minutes = int(self.settings.hold_minutes)
        self.options.ai_unlimited_fuel = bool(self.settings.ai_unlimited_fuel)
        import contextlib, io, logging
        logging.getLogger("pydcs").setLevel(logging.CRITICAL)
        with contextlib.redirect_stdout(io.StringIO()):          # pydcs prints noisy 'Failed to parse Lua' lines for unrelated DCS files
            res = MissionBuilder(st, self.d, self.options, self.loadouts, self._rng(9)).build(pkg, self.settings.sortie_miz)
        st.sortie_counter += 1
        st.pending = {"package": package_number, "flight": pkg.player_flight.id, "manifest": res.manifest.to_dict(),
                      "built_at": time.time(), "miz": str(res.miz), "timeline": res.timeline,
                      "objective": pkg.objective.description, "objective_type": pkg.objective.type.value, "counts": res.counts, "warnings": res.warnings, "seed": res.seed,
                      "package_dict": pkg.to_dict()}
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
        for pd in st.plan:
            if pd["number"] == pend["package"]:
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
