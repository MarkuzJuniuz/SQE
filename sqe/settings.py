"""App settings: just two paths, like DCC (Digital Crew Chief) and Retribution.

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


def native(p: str) -> str:
    """One slash style everywhere: the OS's own (backslashes on Windows). Qt file dialogs and the registry mix them."""
    p = (p or "").strip()
    return os.path.normpath(p) if p else ""


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
    takeoff_buffer_s: int = 60            # seconds between mission start and the briefed takeoff (negative = you must be quicker than the plan)
    hold_minutes: int = 2                 # slack at the marshal point before PUSH (minutes; negative = hurry)
    flight_filter: str = "squadron"      # Missions page: "squadron" (only flights of YOUR squadron) or "all" (any flight your jet can fly)
    merge_mode: str = "area"              # "off" | "area" (default): fold packages in the same area, starting within 30 min, into one mission
    shore_margin_m: int = 1500            # ground sites keep this far from the sea and lakes
    river_margin_m: int = 100             # ...and this far from rivers and shallow water (terrain scan only)
    weather_mode: str = "clear"            # "clear" | "procedural" | a fixed weather: scattered, broken, overcast, rain, storm
    ruins: bool = True                    # earlier packages' targets show as smoking ruins (and struck flights head home)
    merge_radius_nm: int = 50             # packages whose target is inside this circle (centred on yours, kept inside the target area) can fold in
    merge_back_min: int = 15              # packages that started up to this many minutes BEFORE yours fly with you, already underway (0 = only later ones)
    merge_max_units: int = 250            # a merged mission is trimmed until it holds no more than this many units
    emergencies: bool = True              # an emergency (raid or troops in contact) can come up when you click Fly; announced and surprise raids happen either way
    reactive: bool = True                 # enemy reinforcements and blue alert pairs can launch during a sortie
    carcasses: bool = True                # burnt-out wrecks at damaged and destroyed ground sites near your route
    carcass_weight_pct: int = 25          # one wreck counts this % of a live unit toward the unit limit
    unit_cap_v2: bool = False             # the old default (150) has been moved to the new one (250) once
    merge_enemy_pct: int = 100            # folded packages: enemy fighters = the biggest package's + this % of every other folded package's (100 = full sum)
    enemy_cap_engage_nm: int = 50         # enemy patrol fighters will not chase further than this from where they are (0 = unlimited)
    friendly_cap_engage_nm: int = 50      # same for your HAVCAP / BASECAP (0 = unlimited)
    auto_patch_scripting: bool = False    # patch DCS MissionScripting.lua when SQE starts, restore it when SQE exits. Off until the user agrees on first run
    patch_asked: bool = False
    terrain_asked: bool = False           # the one-time 'scan the map?' offer has been shown
    f14_special_names: bool = True             # F-14B(U): special-point waypoint names (untested in the cockpit)
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
                raw = json.loads(f.read_text())
                s = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__ and k != "persist"})
                if not raw.get("unit_cap_v2"):
                    if raw.get("merge_max_units") == 150:
                        s.merge_max_units = 250   # still on the old default: move to the new one (an explicit different value is kept)
                    s.unit_cap_v2 = True
                if "patch_asked" not in raw and "auto_patch_scripting" in raw:
                    s.patch_asked = True          # a settings file from before the question existed: the choice stands
            except (OSError, ValueError):
                pass
        s.dcs_install = native(s.dcs_install or _detect_install())
        s.dcs_saves = native(s.dcs_saves or _detect_saves())
        s.last_campaign = native(s.last_campaign)
        return s

    def save(self) -> None:
        if not self.persist:
            return
        self.dcs_install, self.dcs_saves, self.last_campaign = native(self.dcs_install), native(self.dcs_saves), native(self.last_campaign)
        d = asdict(self); d.pop("persist", None)
        (config_dir() / "settings.json").write_text(json.dumps(d, indent=2))


# ---- MissionScripting.lua: patched while SQE is open, restored on exit -------------------------------------------------
_PAT = re.compile(r"^(\s*)(sanitizeModule\(\s*['\"](io|lfs)['\"]\s*\))", re.M)
_MARK = "-- patched by SQE"
_DONE = re.compile(r"^(\s*)-- (sanitizeModule\(\s*['\"](?:io|lfs)['\"]\s*\))  " + re.escape(_MARK) + r"\s*$", re.M)
_APPLIED = {"by_us": False}


def mission_scripting_path(install: str) -> Path:
    return Path(install) / "Scripts" / "MissionScripting.lua"


def _backup(p: Path) -> Path:
    return p.with_suffix(".lua.sqe.bak")


def mission_scripting_status(install: str) -> str:
    p = mission_scripting_path(install)
    if not install or not p.exists():
        return "MissionScripting.lua not found. Set the DCS folder first."
    text = p.read_text(encoding="utf-8", errors="replace")
    if _PAT.search(text):
        return "NOT patched (debrief will not work)"
    return "Patched by SQE (restored when SQE closes)" if _DONE.search(text) else "Patched (io/lfs available to missions)"


def patch_mission_scripting(install: str) -> tuple[bool, str]:
    """Comment out sanitizeModule('io') and sanitizeModule('lfs'), after saving a backup next to the file. Safe to call repeatedly.
    A file somebody else already unsanitised is left alone (and never 'restored' by us)."""
    p = mission_scripting_path(install)
    if not install or not p.exists():
        return False, f"{p} not found"
    text = p.read_text(encoding="utf-8", errors="replace")
    if not _PAT.search(text):
        return True, "Already patched."
    try:
        shutil.copy2(p, _backup(p))                           # the file is untouched right now, so it IS the original
        p.write_text(_PAT.sub(r"\1-- \2  " + _MARK, text), encoding="utf-8")
    except OSError as e:
        return False, f"Could not write MissionScripting.lua (run SQE as administrator, or turn the setting off and patch it by hand): {e}"
    _APPLIED["by_us"] = True
    return True, f"Patched. Backup: {_backup(p).name}. It is restored when SQE closes."


def restore_mission_scripting(install: str) -> tuple[bool, str]:
    """Undo OUR patch only (re-enable the sanitize lines). Works line by line, so a DCS update to the rest of the file is never overwritten.
    If a crash left the patch in place, the next start simply finds our marker and restores it at exit."""
    p = mission_scripting_path(install)
    if not install or not p.exists():
        return False, "MissionScripting.lua not found."
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if not _DONE.search(text):
            _APPLIED["by_us"] = False
            return True, "Nothing of ours to restore."
        p.write_text(_DONE.sub(r"\1\2", text), encoding="utf-8")
    except OSError as e:
        return False, f"Could not restore MissionScripting.lua: {e} (a backup is at {_backup(p)})"
    _APPLIED["by_us"] = False
    return True, "MissionScripting.lua restored."


def scripting_patched_by_us(install: str) -> bool:
    p = mission_scripting_path(install)
    try:
        return bool(install) and p.exists() and bool(_DONE.search(p.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return False
