"""List the aircraft mods SQE cannot use yet, and write a starter unit pack for them.

    python tools/make_unit_pack.py                    # list mods in Saved Games\\DCS\\Mods\\aircraft and whether SQE knows them
    python tools/make_unit_pack.py --write            # write a starter pack for every unknown mod aircraft
    python tools/make_unit_pack.py --write --id F-104 # only that one

Packs go to %APPDATA%\\SQE\\units\\<id>.json. They are read from the mod's own Lua files and marked "verified": false:
open the file and check fuel_max (kg), max_speed (km/h), pylons and roles before you fly it.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from sqe import modunits
    from sqe.settings import AppSettings, config_dir
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saves", help="DCS Saved Games folder (default: from SQE Settings)")
    ap.add_argument("--write", action="store_true", help="write starter packs for unknown mod aircraft")
    ap.add_argument("--id", help="only this aircraft type id")
    a = ap.parse_args()
    saves = a.saves or AppSettings.load().dcs_saves
    found = modunits.discover(saves)
    if not found:
        print(f"No aircraft mods found under {saves}\\Mods\\aircraft")
        return 0
    unknown = {tid for _f, tid in modunits.missing(saves)}
    for folder, plug, ids in found:
        for tid in ids or ["(no make_flyable found)"]:
            state = "needs a pack" if tid in unknown else "known"
            print(f"{plug:<28} {tid:<24} {state}")
    if not a.write:
        return 0
    out_dir = config_dir() / "units"
    out_dir.mkdir(parents=True, exist_ok=True)
    for folder, plug, ids in found:
        for tid in ids:
            if tid not in unknown or (a.id and tid != a.id):
                continue
            p = out_dir / f"{tid}.json"
            p.write_text(json.dumps(modunits.starter_pack(folder, tid, plug), indent=2), encoding="utf-8")
            print(f"wrote {p}  (check the numbers, then set \"verified\": true)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
