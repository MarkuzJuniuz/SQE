"""Campaign state and the .sqe save format (human-readable JSON, versioned)."""
from __future__ import annotations
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from . import FORMAT_VERSION
from .models import (Base, BaseKind, Squadron, EnemyAsset, AssetKind, EnemyAirWing, PlayerProfile)


@dataclass
class CampaignState:
    name: str
    theatre: str = "caucasus"
    level: int = 2
    campaign_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    day: int = 1
    sortie_counter: int = 0
    player: PlayerProfile | None = None
    bases: dict = field(default_factory=dict)
    squadrons: dict = field(default_factory=dict)
    assets: dict = field(default_factory=dict)
    enemy_air: list = field(default_factory=list)
    plan: list = field(default_factory=list)       # today's packages as dicts
    pending: dict | None = None                    # the sortie that has been built but not yet debriefed
    history: list = field(default_factory=list)    # one dict per debriefed sortie
    log: list = field(default_factory=list)
    status: str = "ACTIVE"                         # ACTIVE | VICTORY | DEFEAT
    start_date: str = "2004-06-12"                 # campaign day 1 (year 2004: F-14B(U) era)
    night_ops: bool = False                        # allow night sorties in the daily cycle
    pilot: dict = field(default_factory=dict)      # your pilot log

    # ---- helpers ------------------------------------------------------------------------
    def campaign_date(self):
        from datetime import date, timedelta
        return date.fromisoformat(self.start_date) + timedelta(days=self.day - 1)

    def note(self, text: str) -> None:
        self.log.append(f"[day {self.day}] {text}")

    def enemy_air_at(self, asset_id: str):
        return next((w for w in self.enemy_air if w.base_asset_id == asset_id), None)

    def squadrons_for(self, aircraft_key: str) -> list:
        return [s for s in self.squadrons.values() if s.aircraft == aircraft_key]

    # ---- serialisation ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": FORMAT_VERSION, "saved": datetime.now().isoformat(timespec="seconds"),
            "name": self.name, "theatre": self.theatre, "level": self.level, "campaign_id": self.campaign_id,
            "day": self.day, "sortie_counter": self.sortie_counter, "status": self.status,
            "start_date": self.start_date, "night_ops": self.night_ops, "pilot": self.pilot,
            "player": asdict(self.player) if self.player else None,
            "bases": {k: {**asdict(v), "kind": v.kind.value} for k, v in self.bases.items()},
            "squadrons": {k: asdict(v) for k, v in self.squadrons.items()},
            "assets": {k: {**asdict(v), "kind": v.kind.value} for k, v in self.assets.items()},
            "enemy_air": [asdict(w) for w in self.enemy_air],
            "plan": self.plan, "pending": self.pending, "history": self.history[-300:], "log": self.log[-400:],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CampaignState":
        if d.get("format", 1) > FORMAT_VERSION:
            raise ValueError("This campaign was saved by a newer version of SQE.")
        s = cls(name=d["name"], theatre=d.get("theatre", "caucasus"), level=d.get("level", 2),
                campaign_id=d.get("campaign_id", uuid.uuid4().hex[:10]), day=d.get("day", 1),
                sortie_counter=d.get("sortie_counter", 0), status=d.get("status", "ACTIVE"),
                start_date=d.get("start_date", "2004-06-12"), night_ops=d.get("night_ops", False), pilot=d.get("pilot", {}))
        s.player = PlayerProfile(**d["player"]) if d.get("player") else None
        s.bases = {k: Base(**{**v, "kind": BaseKind(v["kind"])}) for k, v in d["bases"].items()}
        s.squadrons = {k: Squadron(**v) for k, v in d["squadrons"].items()}
        s.assets = {k: EnemyAsset(**{**v, "kind": AssetKind(v["kind"])}) for k, v in d["assets"].items()}
        s.enemy_air = [EnemyAirWing(**w) for w in d["enemy_air"]]
        s.plan, s.pending = d.get("plan", []), d.get("pending")
        s.history, s.log = d.get("history", []), d.get("log", [])
        return s

    def save(self, path: str | Path, backups_dir: str | Path | None = None, keep: int = 6) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        tmp.replace(path)
        if backups_dir:
            b = Path(backups_dir)
            b.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9_-]+", "_", self.name)
            shutil.copy2(path, b / f"{safe}_{time.strftime('%Y%m%d_%H%M%S')}.sqe")
            old = sorted(b.glob(f"{safe}_*.sqe"))
            for f in old[:-keep]:
                f.unlink(missing_ok=True)

    @classmethod
    def load(cls, path: str | Path) -> "CampaignState":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
