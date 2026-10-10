# Faction packs

A faction pack says who fights and with what: countries, aircraft, air defences, ground forces, ships and support aircraft. Each campaign has a **blue** and a **red** pack.

- A new campaign takes its pair from the theatre pack's `factions` key.
- The campaign then saves the pair, so opening it again always restores the same factions.
- If a theatre pack has no `factions` key, it gets the modern pair.

| Pack | Era | Use |
|---|---|---|
| `modern_usa` | modern | Blue on modern theatres (today's Caucasus campaign) |
| `modern_russia` | modern | Red on modern theatres |
| `ww2_allies_europe` | ww2 | Blue on Normandy and The Channel (US and UK) |
| `ww2_axis_germany` | ww2 | Red on Normandy and The Channel |
| `ww2_allies_pacific` | ww2 | Blue on the Marianas (Essex carrier) |
| `ww2_axis_japan` | ww2 | Red on the Marianas. **Incomplete**: ground forces only, because pydcs has no Japanese aircraft and no Marianas WWII map yet |

Bundled packs live in `sqe/data/factions/`. Your own go in `%APPDATA%\SQE\factions\`, and a pack with the same id replaces the bundled one.

SQE refuses a pair from different eras, a pack marked `"incomplete": true`, and a red pack with no aircraft.

## What each side uses today

- **Blue:** `countries`, `support` (AWACS, tankers, recovery tanker), `navy` (carrier and escorts), `base_defence`, `ground.task_force` and `ground.jtac`.
- **Red:** `countries`, `air`, `air_defence`, and `ground` (`soft`, `armor`, `garrison`, `wreck_mix`).

Every pack may hold every section. When red gets real squadrons and bases (the next drop), both sides read the same sections.

## Keys

| Key | Meaning |
|---|---|
| `id`, `name`, `era` | file stem, display name, and era: `ww2`, `early_jet` or `modern`. Only same-era packs can be paired |
| `side`, `notes`, `incomplete` | intended side (a hint), free text, and true to block use |
| `countries` | DCS country names; the first is the side's main country (e.g. `"Third Reich"`, `"USA"`) |
| `air.fighters` | pydcs class names of the fighters (`Bf_109K_4`) |
| `air.radius_nm`, `air.intercept_nm` | combat radius and scramble range per type |
| `air.types_by_level` | `{"1": [...], "2": [...], "3": [...]}`: the types in the air wings at each difficulty |
| `air.striker`, `air.bomber` | the airfield-raid type and the anti-ship bomber; empty means none |
| `air_defence.variants` | site types: `{id: {label, name, value, range_nm, envelope_ft, weight, radar, long_range, mobile, units}}`. Ids are global across packs, so they must be unique |
| `air_defence.track_radars`, `search_radars` | unit type names as DCS stores them, e.g. `"FuSe-65"` |
| `air_defence.sam_variants_by_level`, `forward_sams_by_level` | which site types guard the airfields and travel with the columns, per difficulty |
| `air_defence.ewr`, `ewr_advanced` | the early-warning radar site type (`ewr_advanced` is used at Level 3) |
| `ground.soft` | `{C2/FUEL/DEPOT/AIRFIELD/ARMOR: [[unit, count]]}` |
| `ground.armor`, `ground.garrison` | choices for the moving columns and dug-in garrisons |
| `ground.wreck_mix`, `wreck_aaa` | what burnt-out wrecks are made of |
| `ground.task_force`, `ground.jtac` | the friendly force at a CAS contact, `[[unit, min, max]]`, and the JTAC vehicle |
| `base_defence` | `[{name, units: [[unit, full, reduced]], formation, bearing, distance_m}]`: one platoon per entry around each airfield |
| `navy.carrier`, `carrier_tacan_callsign`, `escorts` | pydcs ship class names; escorts are `[ship, bearing, nm]` |
| `support.awacs`, `support.tankers`, `support.recovery_tanker` | `{type, label, altitude_ft, speed_kts}`; leave a key out for none |

`python -c "from sqe import factions; print(factions.problems('<id>'))"` lists any unit name in a pack that this pydcs doesn't know.
