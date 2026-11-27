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


# S88 R2 (XO 2026-11-17): settings fields renamed to match the dialog labels. old name -> new name; `merge_enemy_pct` is gone (no setting any more: an old file's key is ignored on load).
RENAMED_FIELDS = {"carcass_weight_pct": "wreck_static_weight_pct", "hold_minutes": "marshal_slack_min", "merge_max_units": "max_units",
                  "merge_back_min": "merge_earlier_min", "merge_fwd_min": "merge_later_min", "merge_radius_nm": "target_area_radius_nm",       # S139b: the radius is the target area's now
                  "autoskip_duration_on": "autoskip_crew_rest", "autoskip_hours": "autoskip_crew_rest_hours"}


def _apply_renames(raw: dict) -> None:
    """Move an old key's value to its new name in a loaded settings file (in place). If both exist the new name wins and the old is dropped."""
    for old, new in RENAMED_FIELDS.items():
        if old in raw:
            val = raw.pop(old)
            raw.setdefault(new, val)


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
    hot_ramp_scrambles: bool = False      # v0.41.80: scramble pairs at LAND fields wait hot on the ramp and taxi out (experimental); off = hidden, put on the runway when called
    hot_runway_starts: bool = False       # v0.41.96: AI package flights from LAND fields other than yours start on the runway (queued by the hook) instead of airborne, when the schedule allows (v0.41.97: your own field too, after your takeoff)
    hot_runway_own_field: bool = False    # v0.41.99: sub-setting of hot_runway_starts: also AI flights at YOUR field (after your takeoff); only counts while hot_runway_starts is on
    takeoff_buffer_s: int = 60            # seconds between mission start and the briefed takeoff (negative = you must be quicker than the plan)
    marshal_slack_min: int = 1            # (S77: was 2) slack at the marshal point before PUSH (minutes; negative = hurry)
    flight_filter: str = "squadron"      # who you may fly: "squadron" (only flights of YOUR squadron). "all" is for tests and tools only: a saved file never turns it on (v0.41.93)
    window_geometry: str = ""            # v0.41.151: the main window's size and position (Qt saveGeometry, base64); empty = open at the default size, centered (File > Reset window)
    situation_open: bool = True          # v0.41.149: the Overview's Situation panel is open (day 1 starts open; it remembers the last state)
    list_filter: str = "squadron"        # v0.41.93: the Missions page list: "squadron" (packages with a flight of yours) or "all" (every package, for looking only)
    merge_mode: str = "area"              # "off" | "area" (default): fold packages in the same area, starting within 30 min, into one mission
    shore_margin_m: int = 1500            # ground sites keep this far from the sea and lakes
    river_margin_m: int = 100             # ...and this far from rivers and shallow water (terrain scan only)
    ai_skill_red: str = "level"            # v0.41.70: "level" (the difficulty level decides) or Average / Good / High / Excellent: Red's pilots and ground units
    ai_skill_blue: str = "level"           # ...and Blue's AI flights ("level" = High); see difficulty.ai_skill
    # S88 R3 (XO 2026-11-18): the two Tactical Edge switches are per campaign now (`state.ground`), no longer settings; an old settings file's keys for them are ignored on load (the load filter drops unknown keys)
    weather_mode: str = "clear"            # "clear" | "procedural" | a fixed weather: scattered, broken, overcast, rain, storm
    ils_low_vis: bool = True               # S63 (XO 2026-11-12): in low ceiling or visibility the ground wind is turned to favour each blue field's ILS runway (DCS lights the ILS only on the active runway, picked by the low-level wind); good weather keeps the real wind
    ruins: bool = True                    # earlier packages' targets show as smoking ruins (and struck flights head home)
    target_area_radius_nm: int = 15             # S139b (was merge_radius_nm): the target area round your target (supply sites, CAS sectors, ruins, the Missions list nesting, plan-time grouping); no longer limits what FLY merges (v0.41.131: 15, was 25)
    merge_later_min: int = 30             # v0.41.131: packages that start up to this many minutes AFTER yours fly with you (5 minute steps in Settings, 0 to 240 since S139b)
    merge_v131: bool = False
    merge_raids_all: bool = True          # S39: raid intercepts that start inside the time windows are listed in one mission, at any distance (off: a raid is listed there only when its way in passes the target area); S139b: the Missions list only, FLY takes every raid in the window
    merge_earlier_min: int = 15            # packages that started up to this many minutes BEFORE yours fly with you, already underway (0 = only later ones)
    max_units: int = 250                  # v0.41.131: the unit limit counts the WHOLE mission again, merged packages included (ruins go first, then the latest-starting package); the 500 ceiling in sqe/data/limits.json is dormant
    reactive: bool = True                 # enemy reinforcements and blue alert pairs can launch during a sortie
    ai_land_carrier: str = "always"       # v0.41.18: AI flights going home to a carrier: "always" recovered short of it | "home" only at your deck | "never" land
    ai_land_field: str = "never"          # v0.41.18: the same for airfields
    splash_damage: bool = True            # extra blast damage near bomb / missile impacts (mission hook); v0.41.13: on by default
    awacs_tuned: bool = True              # v0.41.215: AWACS calls reach you only while a radio is on the AWACS frequency (jets that can be read)
    damage_calls: bool = True             # v0.41.215: other blue aircraft, the tanker and the AWACS call their own hits and mayday
    ecm_status: bool = True               # v0.41.213: show the on-screen ECM messages (needs ecm_script)
    ecm_script: bool = False              # SQE's own jamming model in the mission hook; off = DCS's own ECM, used by the AI when locked
    carcasses: bool = True                # burnt-out wrecks at damaged and destroyed ground sites near your route
    dormant_sites: bool = False           # S89 (Experimental): red SAM sites on your route start asleep and wake when a detector sees blue; they count 10% toward the unit limit
    wreck_static_weight_pct: int = 25    # one wreck or one live static building (a fuel farm's tank, a depot's warehouse) counts this % of a live unit toward the unit limit (v0.41.221; renamed in refactor week)
    unit_cap_v2: bool = False             # the old default (150) has been moved to the new one (250) once
    fighter_engage_nm: int = 40           # AI escorts and sweeps chase no further than this (0 = unlimited)
    fighter_engage_minutes: int = 5       # AI escorts, sweeps and SEAD stop engaging this long after the TOT and fly on (0 = no time limit)
    fighter_standoff: bool = True         # AI escorts and sweeps stop short of live SAM cover
    auto_patch_scripting: bool = False    # patch DCS MissionScripting.lua when SQE starts, restore it when SQE exits. Off until the user agrees on first run
    patch_asked: bool = False
    terrain_asked: bool = False           # the one-time 'scan the map?' offer has been shown
    autoskip_stand_down: bool = False     # Phase 11 (XO): AUTOMATICALLY SKIP under Skip Turn: keep skipping turns with nothing to fly
    autoskip_night: bool = False          # ...also night turns, even when a flight is on offer
    autoskip_crew_rest: bool = False      # ...stop after autoskip_crew_rest_hours of campaign time (unticked: no limit, a week at most)
    autoskip_crew_rest_hours: int = 12  # 4 to 24, step 4 (S25: a turn is four hours; `load` rounds an older value to a multiple of 4)
    dcs_server_fly: bool = False          # S161a (Experimental, default OFF): Fly builds the sortie with a client slot for the flight lead and runs it on the local DCS dedicated server (sqe/dcs_server.py)
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
                _apply_renames(raw)       # S88 R2: an older file's field names, before the filter and the migrations below
                s = cls(**{k: v for k, v in raw.items() if k in cls.__dataclass_fields__ and k != "persist"})
                if not raw.get("unit_cap_v2"):
                    if raw.get("max_units") == 150:
                        s.max_units = 250   # still on the old default: move to the new one (an explicit different value is kept)
                    s.unit_cap_v2 = True
                s.reactive = True     # v0.41.135 (XO 2026-10-24): reactive dispatch is always on (the checkbox is gone)
                s.fighter_standoff = True         # v0.41.133 (XO 2026-10-23): TARCAPs, escorts and sweeps always stop short of live SAM cover (the checkbox is gone; off made the AI go banzai)
                if not raw.get("merge_v131"):
                    if raw.get("target_area_radius_nm") == 25:         # `_apply_renames` has moved an old file's merge_radius_nm here already
                        s.target_area_radius_nm = 15    # still on the old default: move to the new one
                    s.merge_v131 = True
                if "patch_asked" not in raw and "auto_patch_scripting" in raw:
                    s.patch_asked = True          # a settings file from before the question existed: the choice stands
            except (OSError, ValueError):
                pass
        if not getattr(s, "hot_runway_starts", False):
            s.hot_runway_own_field = False            # v0.41.99: the sub-setting cannot be on without the main one
        if getattr(s, "flight_filter", "squadron") != "squadron":
            s.list_filter = "all"                     # v0.41.93: an older file's "all" was the list choice; it no longer lets you fly other squadrons' jets
            s.flight_filter = "squadron"
        s.dcs_install = native(s.dcs_install or _detect_install())
        s.dcs_saves = native(s.dcs_saves or _detect_saves())
        s.last_campaign = native(s.last_campaign)
        try:
            s.autoskip_crew_rest_hours = min(24, max(4, int(round(int(s.autoskip_crew_rest_hours) / 4.0)) * 4))      # S25: Crew Rest goes by four-hour turns; an old 2, 6, 10 ... is rounded to the nearest multiple of 4
        except (TypeError, ValueError):
            s.autoskip_crew_rest_hours = 12
        return s

    def save(self) -> None:
        if not self.persist:
            return
        self.dcs_install, self.dcs_saves, self.last_campaign = native(self.dcs_install), native(self.dcs_saves), native(self.last_campaign)
        d = asdict(self); d.pop("persist", None)
        (config_dir() / "settings.json").write_text(json.dumps(d, indent=2))


# ---- export scripts: copied to Saved Games\DCS\Scripts and hooked into Export.lua (v0.41.219, XO 2026-10-31) ------------------
class _ExportScript:
    """One script SQE installs: its file in `data/`, the mark of our line in Export.lua, and the flag or request file it uses in Logs."""

    def __init__(self, mark: str, file_name: str, log_file: str):
        self.line = mark + "dofile(lfs.writedir() .. [[Scripts\\" + file_name + "]])"
        self.active = re.compile(r"^[ \t]*(?:" + re.escape(mark) + r")?[ \t]*dofile\(.*" + re.escape(file_name), re.M)
        self.bundled = Path(__file__).resolve().parent / "data" / file_name
        self.file_name = file_name
        self.log_file = log_file


_ECM = _ExportScript("--[[SQE ECM EXPORT]]", "sqe_ecm_export.lua", "SQE_ecm.flag")
_F14_TURNPOINTS = _ExportScript("--[[SQE F14 TURNPOINTS EXPORT]]", "sqe_f14_turnpoints_export.lua", "SQE_turnpoints.req")
_F14_RADAR = _ExportScript("--[[SQE F14 RADAR EXPORT]]", "sqe_f14_radar_export.lua", "SQE_radar.req")      # S219: RIO Radar ("Hunt Bandit")
ECM_LINE = _ECM.line


def _export_paths(script: _ExportScript, saves: str):
    d = Path(saves) / "Scripts"
    return d, d / script.file_name, d / "Export.lua"


def _read_export(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="surrogateescape") if p.exists() else ""


def _script_state(script: _ExportScript, saves: str) -> str:
    """'nofolder' | 'none' | 'partial' (line or file missing) | 'old' (script differs from the bundled one) | 'ok'."""
    if not saves or not Path(saves).is_dir():
        return "nofolder"
    _, sc, ex = _export_paths(script, saves)
    has_line = bool(script.active.search(_read_export(ex)))
    has_file = sc.exists()
    if not has_line and not has_file:
        return "none"
    if not (has_line and has_file):
        return "partial"
    try:
        return "ok" if sc.read_bytes() == script.bundled.read_bytes() else "old"
    except OSError:
        return "old"


def _script_status(state: str) -> str:
    return {"nofolder": "Set the DCS Saves folder first.", "none": "Not installed",
            "partial": "Half installed (click Install to finish)", "old": "Installed, an older copy (click Install to update)",
            "ok": "Installed"}[state]


def _install_script(script: _ExportScript, saves: str) -> tuple[bool, str]:
    """Copy the script to Saved Games\\DCS\\Scripts and add ONE marked line to the END of Export.lua (created if missing). Export.lua is saved once to
    Export.lua.sqe.bak first. Safe to call again: a line already there (ours or a hand-made one) is not added twice."""
    if not saves or not Path(saves).is_dir():
        return False, "Set the DCS Saves folder first."
    d, sc, ex = _export_paths(script, saves)
    try:
        d.mkdir(parents=True, exist_ok=True)
        sc.write_bytes(script.bundled.read_bytes())
        raw = ex.read_bytes() if ex.exists() else b""
        if script.active.search(raw.decode("utf-8", errors="surrogateescape")):
            return True, "Installed (the Export.lua line was already there)."
        bak = ex.with_name("Export.lua.sqe.bak")
        if ex.exists() and not bak.exists():
            shutil.copy2(ex, bak)
        nl = b"\r\n" if b"\r\n" in raw else b"\n"
        if raw and not raw.endswith((b"\n", b"\r")):
            raw += nl
        ex.write_bytes(raw + script.line.encode("utf-8") + nl)
    except OSError as e:
        return False, f"Could not write to {d}: {e}"
    return True, "Installed. Restart DCS (or start a new flight) to load it." + (" Export.lua backup: Export.lua.sqe.bak." if (ex.with_name("Export.lua.sqe.bak")).exists() else "")


def _remove_script(script: _ExportScript, saves: str) -> tuple[bool, str]:
    """Take our line out of Export.lua, delete the copied script and a leftover flag or request file. Other lines in Export.lua stay as they are."""
    if not saves or not Path(saves).is_dir():
        return False, "Set the DCS Saves folder first."
    d, sc, ex = _export_paths(script, saves)
    try:
        if ex.exists():
            raw = ex.read_bytes().decode("utf-8", errors="surrogateescape")
            keep = [ln for ln in raw.splitlines(True) if not script.active.match(ln)]
            if len(keep) != len(raw.splitlines(True)):
                ex.write_bytes("".join(keep).encode("utf-8", errors="surrogateescape"))
        for f in (sc, Path(saves) / "Logs" / script.log_file):
            if f.exists():
                f.unlink()
    except OSError as e:
        return False, f"Could not remove it: {e}"
    return True, "Removed."


def ecm_script_state(saves: str) -> str:
    return _script_state(_ECM, saves)


def ecm_script_status(saves: str) -> str:
    return _script_status(ecm_script_state(saves))


def install_ecm_script(saves: str) -> tuple[bool, str]:
    return _install_script(_ECM, saves)


def remove_ecm_script(saves: str) -> tuple[bool, str]:
    return _remove_script(_ECM, saves)


def f14_turnpoints_state(saves: str) -> str:
    return _script_state(_F14_TURNPOINTS, saves)


def f14_turnpoints_status(saves: str) -> str:
    return _script_status(f14_turnpoints_state(saves))


def f14_turnpoints_installed(saves: str) -> bool:
    """An older copy still counts: the mission only has to know that something on this PC will read its request."""
    return f14_turnpoints_state(saves) in ("ok", "old")


def install_f14_turnpoints(saves: str) -> tuple[bool, str]:
    return _install_script(_F14_TURNPOINTS, saves)


def remove_f14_turnpoints(saves: str) -> tuple[bool, str]:
    return _remove_script(_F14_TURNPOINTS, saves)


def f14_radar_state(saves: str) -> str:
    return _script_state(_F14_RADAR, saves)


def f14_radar_status(saves: str) -> str:
    return _script_status(f14_radar_state(saves))


def f14_radar_installed(saves: str) -> bool:
    """An older copy still counts: the mission only has to know that something on this PC will read its request."""
    return f14_radar_state(saves) in ("ok", "old")


def install_f14_radar(saves: str) -> tuple[bool, str]:
    return _install_script(_F14_RADAR, saves)


def remove_f14_radar(saves: str) -> tuple[bool, str]:
    return _remove_script(_F14_RADAR, saves)


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


