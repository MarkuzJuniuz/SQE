"""Syria probe kit (S90, tools only, nothing ships): the airfield list and the probe-only pack stub.

  python tools/syria_fields.py list [--out FILE]      read pydcs' Syria terrain and write .private/syria/airfields.md: every airport with an id, name,
                                                      region (by position), DCS x / y, lat / lon, runway headings, parking slots (planes / helicopters),
                                                      radio and beacon data pydcs has. Sorted by region, then north to south. XO picks the fields from it.
  python tools/syria_fields.py stub [--fields FILE] [--out FILE]
                                                      write the probe-only pack stub .private/syria/syria.json from the chosen fields (fields.txt):
                                                      the scan area (the whole DCS Syria map) and discs round those airfields. Not in sqe/data/theatres,
                                                      so the campaign dialog never lists it (theatres.available() reads only the bundled and user pack folders).

fields.txt: one pydcs airport name per line with a prefix (blank lines and # comments are ignored):
  blue: Incirlik        blue field of the pack (scan discs, site list)
  red: Damascus         red field of the pack
  front: Hatay          the front chain, in order from the red end to the blue end (sector centres of the site list lie along it)
A name may appear under more than one prefix. If fields.txt is missing, `list` writes a PROVISIONAL one next to airfields.md; edit it, then run `stub`.

The region column comes from coarse border polygons written from memory (judgment, no survey): good to a few km, wrong for a field that sits on a border.
No runway length: pydcs has none (the Mission Editor shows it; XO's screenshots fill it).
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / ".private" / "syria"
FIELDS_TXT = OUT_DIR / "fields.txt"
AIRFIELDS_MD = OUT_DIR / "airfields.md"
STUB_JSON = OUT_DIR / "syria.json"

# The whole DCS Syria map in DCS coordinates (x north, y east, metres). pydcs: Syria.bounds = Rectangle(top -320000, left -579986, bottom 300000, right 579998).
# Rounded out to whole kilometres so the 250 m scan grid and the 1 km height grid divide it.
MAP_X0, MAP_X1, MAP_Y0, MAP_Y1 = -320000, 300000, -580000, 580000
MAP_LAT, MAP_LON = 34.93, 35.90           # the middle of the map (pydcs: x -10000, y 0), 2026-11-18
MAP_TZ = 2.0                              # Syria, Lebanon, Israel, Jordan, Cyprus all run UTC+2 as standard time (2000: EET)
PROBE_AIRPORT = "Damascus"                # where the scan mission parks its Su-25T (71 slots, planes)
FRONT_ZONES_PER_LEG = 3                   # sector centres per leg of the front chain in the stub (the real pack decides its own)
REGIONS = ("Syria", "Lebanon", "Israel / Golan", "Jordan", "Iraq", "Turkey", "Cyprus")

# A provisional pick so the first stub can be made: the main fields of Syria and its neighbours. XO's choice replaces it.
PROVISIONAL = {
    "blue": ["Incirlik", "Adana Sakirpasa", "Hatay", "Akrotiri", "Paphos", "Larnaca"],
    "red": ["Bassel Al-Assad", "Abu al-Duhur", "Aleppo", "Hama", "Tiyas", "Shayrat", "Damascus", "Mezzeh", "Tabqa", "Deir ez-Zor", "Palmyra", "Al-Dumayr", "Sayqal", "Marj Ruhayyil"],
    "front": ["Damascus", "Hama", "Aleppo", "Hatay", "Incirlik"],
}


def _terrain():
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):      # pydcs prints noisy 'Failed to parse Lua' lines for unrelated livery files
        from dcs import terrain as T
        return T.Syria()


# ---- region by position (judgment: coarse borders from memory) ----

# the Turkish border with Syria and Iraq, (lon, lat) from west to east; a point north of it (or at the Mediterranean end, north of lat 35.85) is Turkey
_TURKEY_BORDER = [(29.0, 35.85), (35.92, 35.85), (36.05, 36.00), (36.35, 36.20), (36.65, 36.25), (36.70, 36.62), (37.0, 36.68), (37.5, 36.68),
                  (38.0, 36.65), (38.2, 36.84), (39.0, 36.70), (40.0, 36.83), (41.0, 37.10), (42.4, 37.30)]
_LEBANON = [(33.05, 35.0), (33.09, 35.5), (33.28, 35.58), (33.30, 35.78), (33.4, 35.9), (33.85, 36.45), (34.3, 36.6), (34.65, 36.4), (34.7, 35.7), (34.7, 35.0)]       # (lat, lon) polygon; the notch at (33.28, 35.58) is the Galilee panhandle (Kiryat Shmona is Israeli)


def _in_poly(lat: float, lon: float, poly: list) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if (a[1] > lon) != (b[1] > lon):
            if lat < a[0] + (lon - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
                inside = not inside
    return inside


def region(lat: float, lon: float) -> str:
    if 34.4 <= lat <= 35.75 and 32.1 <= lon <= 34.7:
        return "Cyprus"
    for (l0, a0), (l1, a1) in zip(_TURKEY_BORDER, _TURKEY_BORDER[1:]):
        if l0 <= lon <= l1:
            if lat >= a0 + (a1 - a0) * (lon - l0) / (l1 - l0):
                return "Turkey"
            break
    if _in_poly(lat, lon, _LEBANON):
        return "Lebanon"
    if lon >= 39.15 and lat <= 33.4:
        return "Iraq"
    if lon >= 41.0 and lat <= 37.1:
        return "Iraq"
    if lat <= 33.3 and lon <= 35.55:
        return "Israel / Golan"
    if 32.65 <= lat <= 33.3 and lon <= 35.95:
        return "Israel / Golan"
    if lat < 32.65 and lon >= 35.55:
        return "Jordan"
    return "Syria"


# ---- reading pydcs ----

def read_airports(T) -> list:
    rows = []
    for name, a in T.airports.items():
        ll = a.position.latlng()
        slots = list(a.parking_slots)
        rwys = []
        for r in a.runways:
            rwys.append(f"{r.main.name}/{r.opposite.name}")
        rwy_beacons = sum(len(r.main.beacons) + len(r.opposite.beacons) for r in a.runways)
        atc = a.atc_radio
        rows.append({
            "id": a.id, "name": name, "region": region(ll.lat, ll.lng),
            "x": round(a.position.x), "y": round(a.position.y), "lat": ll.lat, "lon": ll.lng,
            "runways": rwys, "headings": [r.main.heading for r in a.runways],
            "planes": sum(1 for s in slots if s.airplanes), "helis": sum(1 for s in slots if s.helicopter), "slots": len(slots),
            "shelters": sum(1 for s in slots if s.shelter),
            "tacan": getattr(a, "tacan", None), "rwy_beacons": rwy_beacons, "beacons": len(a.beacons or []),
            "vhf": (f"{atc.vhf_high_hz / 1e6:.3f}" if atc and getattr(atc, "vhf_high_hz", None) else ""),
            "uhf": (f"{atc.uhf_hz / 1e6:.3f}" if atc and getattr(atc, "uhf_hz", None) else ""),
        })
    return rows


def _ordered(rows: list) -> list:
    return sorted(rows, key=lambda r: (REGIONS.index(r["region"]), -r["lat"]))


def _table(rows: list, cols: list) -> list:
    out = ["| " + " | ".join(c for c, _ in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(f(r)) for _, f in cols) + " |")
    return out


def write_list(path: Path, T) -> None:
    rows = _ordered(read_airports(T))
    runway = [r for r in rows if r["runways"]]
    pads = [r for r in rows if not r["runways"]]
    have_tacan = sum(1 for r in rows if r["tacan"])
    have_vhf = sum(1 for r in rows if r["vhf"])
    L = ["# DCS Syria airfields (made by `python tools/syria_fields.py list`)", "",
         f"{len(rows)} airports in pydcs' Syria terrain: {len(runway)} with a runway, {len(pads)} helipads / FARPs (no runway in pydcs).",
         "Sorted by region, then north to south. Region is by position from coarse hand-written borders (approximate: a field on a border can be wrong).", "",
         "## What pydcs gives and what it does not",
         f"- TACAN: pydcs has it for {have_tacan} of {len(rows)} airports: the column is {'empty' if not have_tacan else 'partly empty'}.",
         "- ILS: pydcs has no ILS frequency or course. `rwy bcn` is the number of beacon ids pydcs lists on the runway ends (a hint that the runway has nav aids, not the frequency).",
         f"- Tower radio: VHF / UHF as pydcs lists them ({have_vhf} of {len(rows)} airports have a VHF value).",
         "- Runway length and width: NOT in pydcs (column absent). Runway headings are the runway numbers as DCS names them.",
         "- XO's Mission Editor airfield-panel screenshots fill ILS / TACAN / tower / length for the fields he picks.", "",
         "Columns: x / y are DCS coordinates in metres (x north, y east). Slots = parking slots; planes / helis = slots that take that kind (a slot can take both); shelters = hardened slots.", ""]
    cols = [("id", lambda r: r["id"]), ("name", lambda r: r["name"]), ("region", lambda r: r["region"]), ("x", lambda r: r["x"]), ("y", lambda r: r["y"]),
            ("lat", lambda r: f"{r['lat']:.3f}"), ("lon", lambda r: f"{r['lon']:.3f}"), ("runways", lambda r: ", ".join(r["runways"])),
            ("slots", lambda r: r["slots"]), ("planes", lambda r: r["planes"]), ("helis", lambda r: r["helis"]), ("shelters", lambda r: r["shelters"]),
            ("TACAN", lambda r: r["tacan"] or ""), ("rwy bcn", lambda r: r["rwy_beacons"]), ("VHF", lambda r: r["vhf"]), ("UHF", lambda r: r["uhf"])]
    L += ["## Airfields with a runway", ""] + _table(runway, cols) + [""]
    pcols = [("id", lambda r: r["id"]), ("name", lambda r: r["name"]), ("region", lambda r: r["region"]), ("x", lambda r: r["x"]), ("y", lambda r: r["y"]),
             ("lat", lambda r: f"{r['lat']:.3f}"), ("lon", lambda r: f"{r['lon']:.3f}"), ("slots", lambda r: r["slots"]), ("helis", lambda r: r["helis"])]
    L += ["## Helipads and FARPs (no runway)", ""] + _table(pads, pcols) + [""]
    by = {}
    for r in runway:
        by.setdefault(r["region"], []).append(r)
    L += ["## Count by region (runway fields / helipads)", ""]
    for g in REGIONS:
        L.append(f"- {g}: {len(by.get(g, []))} / {sum(1 for r in pads if r['region'] == g)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


def write_provisional_fields(path: Path) -> None:
    L = ["# Fields for the Syria probe stub. PROVISIONAL (written by syria_fields.py): replace with XO's choice, then run `python tools/syria_fields.py stub`.",
         "# One pydcs airport name per line, with a prefix: blue: / red: / front: (the front chain in order, red end to blue end).", ""]
    for k in ("blue", "red", "front"):
        L += [f"{k}: {n}" for n in PROVISIONAL[k]] + [""]
    path.write_text("\n".join(L), encoding="utf-8")


# ---- the pack stub ----

def read_fields(path: Path, T) -> dict:
    out = {"blue": [], "red": [], "front": []}
    for ln, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = raw.split("#", 1)[0].strip()
        if not s:
            continue
        m = re.match(r"(blue|red|front)\s*:\s*(.+)$", s, re.I)
        if not m:
            sys.exit(f"{path}:{ln}: expected 'blue: NAME', 'red: NAME' or 'front: NAME', got {raw!r}")
        name = m.group(2).strip()
        if name not in T.airports:
            near = [n for n in T.airports if name.lower() in n.lower() or n.lower() in name.lower()][:5]
            sys.exit(f"{path}:{ln}: no airport {name!r} in pydcs' Syria terrain" + (f" (did you mean: {', '.join(near)}?)" if near else ""))
        if name in out[m.group(1).lower()]:
            sys.exit(f"{path}:{ln}: {name!r} listed twice under {m.group(1).lower()}")
        out[m.group(1).lower()].append(name)
    if len(out["front"]) < 2:
        sys.exit(f"{path}: the front chain needs at least two 'front:' airfields")
    if not out["blue"] or not out["red"]:
        sys.exit(f"{path}: needs at least one 'blue:' and one 'red:' field")
    return out


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def build_stub(fields: dict) -> dict:
    """The probe-only pack. It carries every key theatres._validate wants (placeholders where the scan does not look) and `_stub: true`."""
    blue = [{"id": _slug(n), "name": n, "airport": n} for n in fields["blue"]]
    red = [{"id": "ab_" + _slug(n), "name": n, "airport": n, "value": 5} for n in fields["red"]]
    bid, rid = {f["airport"]: f["id"] for f in blue}, {f["airport"]: f["id"] for f in red}
    chain = []
    for n in fields["front"]:
        node = {"airport": n, "name": n}
        if n in rid:
            node["red"] = rid[n]
        elif n in bid:
            node["blue"] = bid[n]
        chain.append(node)
    return {
        "_stub": True, "_note": "Syria PROBE stub (tools/syria_fields.py stub). Not a campaign pack: placeholders everywhere the terrain scan does not look.",
        "id": "syria", "name": "Syria (probe stub)", "dcs_terrain": "Syria", "lat": MAP_LAT, "lon": MAP_LON, "tz": MAP_TZ,
        "temp_c": [10, 11, 14, 18, 23, 27, 29, 30, 27, 22, 16, 11], "geo": "caucasus_geo.json",
        "scan": {"file": "SQE_terrain_syria.json", "x0": MAP_X0, "x1": MAP_X1, "y0": MAP_Y0, "y1": MAP_Y1, "step": 250, "probe_airport": PROBE_AIRPORT},
        "carrier": {}, "blue_fields": blue, "red_fields": red, "red_extra_airports": [], "road_blue_airports": fields["blue"],
        "wing_weight": {}, "field_tier": {}, "squadrons": {}, "front": {"chain": chain, "leg_zones": [FRONT_ZONES_PER_LEG] * (len(chain) - 1), "rear_zones": 1,
                                                                        "stages": {}, "victory": {}, "counter": {}},
        "tier_labels": {}, "front_names": {}, "front_desc": "", "title": "Syria (probe stub)", "stories": [],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("list"); a.add_argument("--out", default=str(AIRFIELDS_MD))
    b = sub.add_parser("stub"); b.add_argument("--fields", default=str(FIELDS_TXT)); b.add_argument("--out", default=str(STUB_JSON))
    args = ap.parse_args()
    T = _terrain()
    if args.cmd == "list":
        write_list(Path(args.out), T)
        print(f"wrote {args.out}")
        if not FIELDS_TXT.exists():
            write_provisional_fields(FIELDS_TXT)
            print(f"wrote a PROVISIONAL {FIELDS_TXT}: edit it to your choice before `stub`")
    else:
        fp = Path(args.fields)
        if not fp.exists():
            sys.exit(f"{fp} not found: run `python tools/syria_fields.py list` first (it writes a provisional one), edit it, then run `stub`")
        stub = build_stub(read_fields(fp, T))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(stub, indent=1), encoding="utf-8")
        print(f"wrote {out}: {len(stub['blue_fields'])} blue, {len(stub['red_fields'])} red fields, front chain of {len(stub['front']['chain'])} "
              f"({sum(stub['front']['leg_zones'])} sectors)")


if __name__ == "__main__":
    main()
