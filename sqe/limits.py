"""Hard limits you can tune without touching the code: sqe/data/limits.json (v0.41.104). Read once.

unit_ceiling: the most units any mission may hold in total, merged packages included. The ordinary unit limit (Settings > Mission Build, default 250)
counts only the BASE mission; the units that merged packages bring do not count against it, so this ceiling is the only thing that bounds them
(together with the merge radius and the six-package limit). It is a runaway guard, not a performance setting."""
import json
from pathlib import Path

_DEFAULT = {"unit_ceiling": 500}
_CACHE: dict | None = None


def load() -> dict:
    global _CACHE
    if _CACHE is None:
        d = dict(_DEFAULT)
        try:
            raw = json.loads((Path(__file__).parent / "data" / "limits.json").read_text(encoding="utf-8"))
            d.update({k: raw[k] for k in _DEFAULT if isinstance(raw.get(k), (int, float)) and raw[k] > 0})
        except (OSError, ValueError):
            pass
        _CACHE = d
    return _CACHE


def unit_ceiling() -> int:
    return int(load()["unit_ceiling"])
