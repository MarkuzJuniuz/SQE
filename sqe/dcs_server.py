"""S161a (experimental): run a built sortie on the local DCS dedicated server.

The server is the normal DCS install started as "DCS.exe --server --norender -w DCS_Server". It shares the install's Scripts\\MissionScripting.lua with the
client, so SQE's patch there (io / lfs) covers the server too, and the hook writes its state file into the server's own profile folder
(Saved Games\\DCS_Server\\SQE\\SQE_state.json). The player joins as a client at 127.0.0.1:10308.

Rules this module keeps:
  * Never two servers: start refuses when another server process runs. A normal DCS client running beside it is fine.
  * The user's serverSettings.lua is saved once to serverSettings.lua.sqe-backup before the first change. A backup that already exists is never
    overwritten (it holds the user's own file, even if an earlier run crashed). Every stop, a failed start and `recover` put the backup back and delete it.
  * The server is detached: closing SQE does not stop a running mission. `stop_server` stops it.
  * Files keep their own line ending.
  * No function raises into the UI: each returns (ok, text) and the text says what went wrong.

Plain Python on purpose (the maintainer is learning it): full names, one step per line.
"""
from __future__ import annotations

import re
import shutil
import socket
import subprocess
import time
from pathlib import Path

SERVER_PORT = 10308
SERVER_PROFILE = "DCS_Server"
BACKUP_NAME = "serverSettings.lua.sqe-backup"
SETTINGS_KEYS_FIXED = (
    ("listStartIndex", "1"),
    ("password", '""'),
    ("isPublic", "false"),
    ("pause_on_load", "false"),
    ("pause_without_clients", "false"),
    ("resume_mode", "1"),
)
# S161b: with a person about to join, the mission waits for him: it pauses while no client is connected and runs when one is
# (the server options "pause_without_clients" and "resume_mode" 2 = resume with clients; DCS server settings, from memory, firmness medium:
# the unattended test cycle checks that the mission loads and stays at time 0 until a client joins).
SETTINGS_KEYS_WAIT_FOR_CLIENT = (
    ("pause_without_clients", "true"),
    ("resume_mode", "2"),
)


# ---- paths --------------------------------------------------------------------------------------------------------
def server_saves_dir(dcs_saves: str) -> Path:
    """The server's own profile folder: a sibling of the client's Saved Games folder (...\\Saved Games\\DCS -> ...\\Saved Games\\DCS_Server)."""
    return Path(dcs_saves).parent / SERVER_PROFILE


def server_settings_path(dcs_saves: str) -> Path:
    return server_saves_dir(dcs_saves) / "Config" / "serverSettings.lua"


def server_backup_path(dcs_saves: str) -> Path:
    return server_saves_dir(dcs_saves) / "Config" / BACKUP_NAME


def server_state_path(dcs_saves: str) -> Path:
    """Where the hook writes its state file when the mission runs on the server."""
    return server_saves_dir(dcs_saves) / "SQE" / "SQE_state.json"


def server_mission_path(dcs_saves: str) -> Path:
    return server_saves_dir(dcs_saves) / "Missions" / "SQE_test.miz"


def dcs_exe_path(dcs_install: str) -> Path:
    return Path(dcs_install) / "bin" / "DCS.exe"


# ---- the text edits (pure functions, tested on a temp copy of a real serverSettings.lua) ------------------------------------
def read_text_keep_ending(path: Path) -> tuple:
    """(text, line ending) of a file: the ending it already uses."""
    text = open(path, encoding="utf-8", newline="").read()
    if "\r\n" in text:
        return text, "\r\n"
    return text, "\n"


def set_value(text: str, key: str, value_lua: str) -> str:
    """Replace ["key"] = <value>, in the settings text. The key must be there exactly once, else ValueError."""
    pattern = re.compile(r'(\["' + re.escape(key) + r'"\]\s*=\s*)([^,\r\n]+)(,)')
    found = pattern.findall(text)
    if len(found) != 1:
        raise ValueError("serverSettings.lua: expected one %s, found %d" % (key, len(found)))
    # Keep the text before and after the value, swap in the new value.
    def swap_value(match):
        return match.group(1) + value_lua + match.group(3)

    return pattern.sub(swap_value, text)


def set_mission_list(text: str, newline: str, miz_path) -> str:
    """Replace the whole missionList table with one mission."""
    pattern = re.compile(r'\["missionList"\]\s*=\s*\{.*?\}, -- end of \["missionList"\]', re.S)
    if len(pattern.findall(text)) != 1:
        raise ValueError("serverSettings.lua: missionList block not found exactly once")
    escaped = str(miz_path).replace("\\", "\\\\")
    block = ('["missionList"] = ' + newline + "\t{" + newline + '\t\t[1] = "' + escaped + '",' + newline + '\t}, -- end of ["missionList"]')
    # The whole match becomes the new block.
    def new_block(match):
        return block

    return pattern.sub(new_block, text)


def edit_settings_text(text: str, newline: str, miz_path, wait_for_client: bool = False) -> str:
    """The settings text with one mission, no password, private, run on load without pausing; with `wait_for_client` the mission pauses until a client is connected."""
    text = set_mission_list(text, newline, miz_path)
    for key, value_lua in SETTINGS_KEYS_FIXED:
        text = set_value(text, key, value_lua)
    if wait_for_client:
        for key, value_lua in SETTINGS_KEYS_WAIT_FOR_CLIENT:
            text = set_value(text, key, value_lua)
    return text


# ---- processes ----------------------------------------------------------------------------------------------------------
_PROCESS_QUERY = ("Get-CimInstance Win32_Process -Filter \"Name='DCS.exe'\" | ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }")


def parse_server_processes(query_output: str) -> list:
    """[(pid, command line)] of the DCS.exe lines that were started with --server (a normal client has no such flag)."""
    found = []
    for line in query_output.splitlines():
        if "|" not in line:
            continue
        pid_text, command = line.split("|", 1)
        if "--server" not in command:
            continue
        try:
            found.append((int(pid_text), command))
        except ValueError:
            continue
    return found


def server_processes() -> list:
    """[(pid, command line)] of running DCS servers. An empty list when the query fails (the caller then cannot tell, and the port check still runs)."""
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-Command", _PROCESS_QUERY], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return []
    return parse_server_processes(result.stdout)


def port_is_free(port: int = SERVER_PORT) -> bool:
    """True when nothing listens on the server port (TCP) and nothing holds its UDP port."""
    for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
        probe = socket.socket(socket.AF_INET, kind)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            return False
        finally:
            probe.close()
    return True


# ---- checks -------------------------------------------------------------------------------------------------------------
def scripting_is_patched(dcs_install: str) -> bool:
    """MissionScripting.lua has io and lfs un-sanitized (SQE's patch, or somebody's)."""
    path = Path(dcs_install) / "Scripts" / "MissionScripting.lua"
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    return "-- sanitizeModule('io')" in text and "-- sanitizeModule('lfs')" in text


def check_ready(dcs_install: str, dcs_saves: str) -> list:
    """The reasons a server cannot start now, as plain sentences. An empty list = ready."""
    problems = []
    if not dcs_install or not dcs_exe_path(dcs_install).exists():
        problems.append("DCS.exe was not found: set the DCS install folder in Settings.")
    if not dcs_saves or not server_settings_path(dcs_saves).exists():
        problems.append("The server profile was not found (Saved Games\\DCS_Server\\Config\\serverSettings.lua): start the DCS dedicated server once by hand so DCS creates it.")
    if dcs_install and not scripting_is_patched(dcs_install):
        problems.append("MissionScripting.lua is not patched (Settings > DCS Integration): the hook could not write the results.")
    running = server_processes()
    if running:
        problems.append("A DCS server is already running (pid %d). Stop it first." % running[0][0])
    elif not port_is_free():
        problems.append("Port %d is in use by another program." % SERVER_PORT)
    return problems


# ---- settings backup and restore -----------------------------------------------------------------------------------------
def backup_settings_once(dcs_saves: str) -> str:
    """Save the user's serverSettings.lua before the first change. A backup that already exists is kept as it is."""
    settings_path = server_settings_path(dcs_saves)
    backup_path = server_backup_path(dcs_saves)
    if backup_path.exists():
        return "kept the earlier backup"
    shutil.copy2(settings_path, backup_path)
    return "backed up"


def restore_settings(dcs_saves: str) -> tuple:
    """Put the user's serverSettings.lua back from the backup and delete the backup. Refuses while a server runs."""
    if server_processes():
        return False, "Stop the server first."
    backup_path = server_backup_path(dcs_saves)
    if not backup_path.exists():
        return True, "Nothing to restore."
    try:
        shutil.copy2(backup_path, server_settings_path(dcs_saves))
        backup_path.unlink()
    except OSError as error:
        return False, "Could not restore serverSettings.lua: %s (the backup is %s)" % (error, backup_path)
    return True, "Your serverSettings.lua is back."


def recover(dcs_saves: str) -> tuple:
    """After a crash or a closed SQE: no server runs but our backup is still there = the user's file was never put back. Do it now."""
    if not dcs_saves or not server_backup_path(dcs_saves).exists():
        return True, "Nothing to recover."
    return restore_settings(dcs_saves)


# ---- start and stop -----------------------------------------------------------------------------------------------------
def start_server(dcs_install: str, dcs_saves: str, miz_path, wait_for_client: bool = False) -> tuple:
    """Put the mission into the server's settings and start the server, detached. -> (ok, text). `wait_for_client`: the mission stays paused until a client joins."""
    miz_path = Path(miz_path)
    if not miz_path.exists():
        return False, "The mission file is missing: %s" % miz_path
    problems = check_ready(dcs_install, dcs_saves)
    if problems:
        return False, " ".join(problems)
    from . import frame_hook
    frame_hook.sync(dcs_saves)                       # SQE_DEBUG=1: the frame-time hook goes in before the server starts (otherwise it is taken out)
    settings_path = server_settings_path(dcs_saves)
    try:
        backup_note = backup_settings_once(dcs_saves)
        shutil.copyfile(miz_path, server_mission_path(dcs_saves))
        text, newline = read_text_keep_ending(settings_path)
        text = edit_settings_text(text, newline, server_mission_path(dcs_saves), wait_for_client)
        open(settings_path, "w", encoding="utf-8", newline="").write(text)
        state_path = server_state_path(dcs_saves)
        if state_path.exists():
            state_path.unlink()
    except (OSError, ValueError) as error:
        restore_settings(dcs_saves)
        return False, "Could not prepare the server: %s" % error
    try:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([str(dcs_exe_path(dcs_install)), "--server", "--norender", "-w", SERVER_PROFILE],
                         cwd=str(dcs_exe_path(dcs_install).parent), creationflags=flags)
    except (OSError, AttributeError) as error:
        restore_settings(dcs_saves)
        return False, "Could not start DCS.exe: %s" % error
    return True, "Server started (%s). Join: Multiplayer, 127.0.0.1:%d, no password." % (backup_note, SERVER_PORT)


def stop_server(dcs_saves: str) -> tuple:
    """Stop every DCS server process, then put the user's serverSettings.lua back. -> (ok, text)."""
    stopped = []
    for pid, _command in server_processes():
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
            stopped.append(pid)
        except (OSError, subprocess.SubprocessError):
            pass
    waited = 0
    while server_processes() and waited < 15:
        time.sleep(1)
        waited += 1
    ok, restore_text = restore_settings(dcs_saves)
    return ok, "Stopped %d server process(es). %s" % (len(stopped), restore_text)
