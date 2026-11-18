"""The long-range SAM tier, as data (S90 P3b / P4, 2026-11-18).

Until now the planner treated the SA-10 as THE long-range system: the umbrella whose reach covers its neighbours, the gate site that gets a Standoff DEAD, and a
dozen margins named SA10_*. This module is the one table behind all of it:

* `SYSTEMS`: per long-range system, how far it reaches in practice and every margin the planner keeps from it (route, station, sweep, defender, gate, JSOW, HARM).
  The SA-10 row holds the numbers the code always had (v0.41.14 to v0.41.194, measured in XO's runs); the SA-5 row is the Syria 2000 system (see below).
* `RANGE_NM`: the ring table (reach by variant), the one copy the threat map, the profiles and the briefing read.
* `UMBRELLA_VARIANTS`, `GATE_VARIANTS`, `GATE_REACH_NM`: which variants play the long-range roles. A theatre pack names them in its `sam_tier` block
  (`{"umbrella": ["SA-5", "SA-10"], "gate": [...]}`); a pack without the block gets the Caucasus tier (the SA-10 as the umbrella), so nothing changes for it.
  The lists are changed IN PLACE (`configure`), so every module that imported them sees the pack's tier.

A leaf module: it imports nothing from SQE, so routes / threatmap / war and the rest can all use it.

SA-5 (S-200, "Gammon"): the public figure for the S-200VE is about 250 km (135 nm) and DCS's own weapon table says 255 km (pydcs), but XO's probe flights
(`tools/sa5_probe.py`, 2026-11-18, one site, flat desert, F-16s at 450 kt, no ECM) measured what the AI site really does: first shots at 65.6 to 66.1 nm
against jets at 20,000 and 35,000 ft, at about 20 nm against a jet at 5,000 ft, and no engagement of a jet at 500 ft (one late shot missed). So the planner
reach is 122 km (65.9 nm) for a high flyer. The margins are the SA-10's own offsets from ITS measured reach (avoid +5.3 nm, a fighter station +15.3 nm, a defender
+5.3 nm, the gate +5 km, the HARM point +5.3 nm, the JSOW point +10.3 nm) laid on the SA-5's: judgment calls, not measurements. Altitude is NOT modelled
here (the SA-5 is much weaker against low flyers; see profiles.ENVELOPE for the floor): that is the open design question, reported by the stand-off probe.
"""
from __future__ import annotations

# reach_km: the practical reach (it opens fire this far out) | avoid_nm: an AI route keeps this far | station_nm: a fighter station (TARCAP / escort) keeps this far
# sweep_nm: a sweep station | scramble_nm: a defender (alert pair) station | gate_km: the DEAD gate / hold orbit keeps this far | gate_reach_nm: the strike gate's
# cover radius (war.covering_sams) | jsow_keep_nm: a JSOW launch point stays this far | harm_nm: a HARM point of another package stays this far | fighter_nm: a sweep's fight circle stops this far short
SYSTEMS = {
    "SA-10": dict(reach_km=55.0, avoid_nm=35.0, station_nm=45.0, sweep_nm=45.0, scramble_nm=35.0, gate_km=60, gate_reach_nm=35, jsow_keep_nm=40.0, harm_nm=35.0, fighter_nm=31),
    "SA-5":  dict(reach_km=122.0, avoid_nm=71.0, station_nm=81.0, sweep_nm=81.0, scramble_nm=71.0, gate_km=127, gate_reach_nm=71, jsow_keep_nm=76.0, harm_nm=71.0, fighter_nm=67),
}

# The ring table: how far a live site of this variant threatens (nm). The SA-10's 48 nm is the old table value (its measured reach is the SYSTEMS row);
# the SA-5's 70 is the measured high-altitude reach rounded up. SA-9: Strela-1 reach 4.2 km (public, firm) = 2.3 nm, rounded to the MANPAD's 3.
RANGE_NM = {"SA-8": 7, "AAA": 3, "MANPAD": 3, "SA-2": 25, "SA-3": 13, "SA-6": 13, "SA-11": 18, "SA-10": 48, "SA-15": 8, "SA-19": 5, "SA-5": 70, "SA-9": 3}

LONG_RANGE_NM = 30.0       # a SAM whose ring reaches this far counts as long-range for the station rule (profiles._long_range_threat): the SA-5 and SA-10 pass, the SA-2 / 3 / 6 / 11 do not

DEFAULT_TIER = {"umbrella": ["SA-10"], "gate": ["SA-2", "SA-3", "SA-6", "SA-11", "SA-10"]}      # the Caucasus tier: exactly what the planner had before this module

UMBRELLA_VARIANTS = list(DEFAULT_TIER["umbrella"])    # long-range sites whose reach covers their neighbours: in a cluster they are the first thing a SEAD wave has to beat
GATE_VARIANTS = list(DEFAULT_TIER["gate"])            # medium / long-range SAMs: they get a Standoff DEAD, and they gate strikes (also where scenario.py places the deep sites)
GATE_REACH_NM = {v: s["gate_reach_nm"] for v, s in SYSTEMS.items()}     # the strike gate's cover radius where it differs from RANGE_NM (the umbrella systems' measured reach)


def get(variant: str, key: str):
    """One margin of an umbrella system (`SYSTEMS[variant][key]`); only umbrella variants have a row."""
    return SYSTEMS[variant][key]


def check(tier, src="the pack") -> None:
    """Raise ValueError for a `sam_tier` block with an unknown key or a variant the tables do not know. None / {} is fine (the default tier)."""
    if not tier:
        return
    if not isinstance(tier, dict) or set(tier) - {"umbrella", "gate"}:
        raise ValueError(f"{src}: sam_tier takes only 'umbrella' and 'gate' lists, got {tier!r}")
    for v in tier.get("umbrella", []):
        if v not in SYSTEMS:
            raise ValueError(f"{src}: sam_tier umbrella {v!r} has no margins in samtier.SYSTEMS (have {', '.join(SYSTEMS)})")
    for v in tier.get("gate", []):
        if v not in RANGE_NM:
            raise ValueError(f"{src}: sam_tier gate {v!r} is not in samtier.RANGE_NM")


def configure(tier=None) -> None:
    """Make a theatre's tier the active one (a pack's `sam_tier` block; None = the Caucasus default). Changes the lists in place."""
    check(tier)
    t = {**DEFAULT_TIER, **(tier or {})}
    UMBRELLA_VARIANTS[:] = list(t["umbrella"])
    GATE_VARIANTS[:] = list(t["gate"])
