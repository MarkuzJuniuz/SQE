"""App settings: just two paths, like DCC/Retribution.

    DCS        the DCS World install folder (only needed by the optional MissionScripting.lua patch helper)
    DCS Saves  the Saved Games profile, e.g. C:\\Users\\You\\Saved Games\\DCS  or  ...\\DCS_Server

Everything else hangs off DCS Saves:
    <saves>\\Missions\\SQE_Sortie.miz      written by FLY
    <saves>\\SQE\\SQE_state.json           written by the mission, read by the waiting window
    <saves>\\SQE\\*.sqe                    campaign saves (+ backups\\)
"""
from __future__ import annotations
import json
import os
import re
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("APPDATA")
    p = Path(base) / "SQE" if base else Path.home() / ".config" / "SQE"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _detect_install() -> str:
    try:                                   # Windows registry, same place pydcs looks
        import winreg
        for sub in ("DCS World", "DCS World OpenBeta", "DCS World Server"):
            for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                try:
                    with winreg.OpenKey(hive, rf"Software\\Eagle Dynamics\\{sub}") as k:
                        return winreg.QueryValueEx(k, "Path")[0]
                except OSError:
                    continue
    except ImportError:
        pass
    return ""


def _detect_saves() -> str:
    for n in ("DCS", "DCS.openbeta", "DCS_Server"):
        p = Path.home() / "Saved Games" / n
        if p.exists():
            return str(p)
    return ""


@dataclass
class AppSettings:
    dcs_install: str = ""
    dcs_saves: str = ""
    last_campaign: str = ""
    ai_unlimited_fuel: bool = True        # AI flights: unlimited fuel until the push, real fuel for the combat leg, unlimited again from egress
    hold_minutes: int = 2                 # slack at the marshal point before PUSH (minutes; negative = hurry)
    persist: bool = True          # False in tests: never write %APPDATA%\\SQE\\settings.json

    # ---- derived paths ------------------------------------------------------------------
    @property
    def missions_dir(self) -> Path:
        return Path(self.dcs_saves) / "Missions"

    @property
    def sortie_miz(self) -> Path:
        return self.missions_dir / "SQE_Sortie.miz"

    @property
    def sqe_dir(self) -> Path:
        return Path(self.dcs_saves) / "SQE"

    @property
    def state_file(self) -> Path:
        return self.sqe_dir / "SQE_state.json"

    @property
    def backups_dir(self) -> Path:
        return self.sqe_dir / "backups"

    def problems(self) -> list[str]:
        out = []
        if not self.dcs_saves or not Path(self.dcs_saves).exists():
            out.append("DCS Saves folder does not exist (e.g. C:\\Users\\<you>\\Saved Games\\DCS).")
        else:
            try:
                self.missions_dir.mkdir(parents=True, exist_ok=True)
                self.sqe_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                out.append(f"Cannot write inside DCS Saves: {e}")
        return out

    # ---- persistence --------------------------------------------------------------------
    @classmethod
    def load(cls) -> "AppSettings":
        f = config_dir() / "settings.json"
        s = cls()
        if f.exists():
            try:
                s = cls(**{k: v for k, v in json.loads(f.read_text()).items() if k in cls.__dataclass_fields__ and k != "persist"})
            except (OSError, ValueError):
                pass
        s.dcs_install = s.dcs_install or _detect_install()
        s.dcs_saves = s.dcs_saves or _detect_saves()
        return s

    def save(self) -> None:
        if not self.persist:
            return
        d = asdict(self); d.pop("persist", None)
        (config_dir() / "settings.json").write_text(json.dumps(d, indent=2))


# ---- optional MissionScripting.lua helper ------------------------------------------------------
_PAT = re.compile(r"^(\s*)(sanitizeModule\(\s*['\"](io|lfs)['\"]\s*\))", re.M)


def mission_scripting_path(install: str) -> Path:
    return Path(install) / "Scripts" / "MissionScripting.lua"


def mission_scripting_status(install: str) -> str:
    p = mission_scripting_path(install)
    if not install or not p.exists():
        return "MissionScripting.lua not found. Set the DCS folder first."
    text = p.read_text(encoding="utf-8", errors="replace")
    return "NOT patched (debrief will not work)" if _PAT.search(text) else "Patched (io/lfs available to missions)"


def patch_mission_scripting(install: str) -> tuple[bool, str]:
    """Comment out sanitizeModule('io') and sanitizeModule('lfs'). Makes a .sqe.bak first."""
    p = mission_scripting_path(install)
    if not p.exists():
        return False, f"{p} not found"
    text = p.read_text(encoding="utf-8", errors="replace")
    if not _PAT.search(text):
        return True, "Already patched."
    try:
        bak = p.with_suffix(".lua.sqe.bak")
        if not bak.exists():
            shutil.copy2(p, bak)
        p.write_text(_PAT.sub(r"\1-- \2  -- patched by SQE", text), encoding="utf-8")
    except OSError as e:
        return False, f"Could not write (run as administrator?): {e}"
    return True, f"Patched. Backup: {bak.name}. Re-apply after DCS updates."
