"""The frame-time log hook (XO 2026-11-24): a DCS hook that writes frame times to dcs.log, installed only for a run with SQE_DEBUG=1.

SQE_DEBUG=1 is the same switch as the dormant-sites log (mission_builder.S89_LOG). With it on, `sync` copies `data/sqe_frame_log.lua` into
`Scripts\\Hooks` of the client's Saved Games folder and of the dedicated server's profile (when that folder exists). With it unset or not 1, `sync`
takes our copies out again. The hook also checks the variable itself when DCS loads it (a hook cannot be switched by SQE once DCS is running).
A hook is a script DCS runs in its own program, not inside the mission: it can read real time (DCS.getRealTime), which a mission script cannot."""
import os
from pathlib import Path

HOOK_NAME = "SQEFrameLog.lua"
HOOK_MARK = b"SQE FRAME LOG (installed by SQE)"
BUNDLED = Path(__file__).resolve().parent / "data" / "sqe_frame_log.lua"


def debug_is_on() -> bool:
    return os.environ.get("SQE_DEBUG") == "1"


def hook_folders(dcs_saves: str) -> list:
    """The Hooks folders to serve: the client's, and the server profile's (a sibling folder, DCS_Server) when it exists."""
    from .dcs_server import server_saves_dir
    folders = []
    if dcs_saves and Path(dcs_saves).is_dir():
        folders.append(Path(dcs_saves) / "Scripts" / "Hooks")
        server_dir = server_saves_dir(dcs_saves)
        if server_dir.is_dir():
            folders.append(server_dir / "Scripts" / "Hooks")
    return folders


def sync(dcs_saves: str) -> str:
    """Install (SQE_DEBUG=1) or remove (otherwise) the frame hook. Never raises: a locked or missing folder only changes the text. -> a short note."""
    notes = []
    wanted = BUNDLED.read_bytes() if debug_is_on() else b""
    for folder in hook_folders(dcs_saves):
        target = folder / HOOK_NAME
        try:
            if debug_is_on():
                folder.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != wanted:
                    target.write_bytes(wanted)
                    notes.append("frame hook installed in %s" % folder)
            elif target.exists() and HOOK_MARK in target.read_bytes():
                target.unlink()
                notes.append("frame hook removed from %s" % folder)
        except OSError as error:
            notes.append("frame hook: could not update %s (%s)" % (folder, error))
    return "; ".join(notes)
