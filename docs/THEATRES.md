# Theatre packs

Everything that belongs to one DCS map is data in a JSON file, not code. The bundled Caucasus pack is `sqe/data/theatres/caucasus.json`.
To add a theatre, write a pack and put it in `%APPDATA%\SQE\theatres\<id>.json` (a pack with the same id as a bundled one replaces it).
The New Campaign window shows a Theatre picker as soon as there is more than one pack. A campaign remembers its theatre.

SQE does not ship maps or ED data: a pack only names things DCS already has (airfield names from pydcs's terrain table) and holds your own numbers.
You still need the map installed in DCS to fly it, and pydcs must know the terrain (the `dcs_terrain` value is a class name in `dcs.terrain`).

## What a pack holds

| Key | Meaning |
|---|---|
| `id`, `name` | file name stem and the label in the picker |
| `dcs_terrain` | pydcs terrain class, e.g. `Caucasus` |
| `lat`, `lon`, `tz` | sun times and local time (`tz` = hours from UTC) |
| `temp_c` | 12 monthly mean temperatures for the mission weather |
| `geo` | coarse coastline / lakes / borders file for the map view (file in the same folder; `land`, `lakes`, `borders` as lists of [x, y] points, x north, y east, metres) |
| `scan` | required. The terrain-scan settings: `file` (the scan's file name in `Saved Games\SQE`), the area `x0 x1 y0 y1` in metres, `step`, and `probe_airport`. Optional: `height_step` and `relief_file`. A scan is not needed to play: the pack folder can ship the results (see "Data files" below) |
| `carrier` | `id`, `name`, optional `short` (the label), and the station: `from_airport`, `heading` and `distance_m` out to sea. Optional `carrier_standoff_nm`: how far the fleet stays from every enemy airfield |
| `blue_fields` | friendly airfields: `id`, `name`, `airport` (the pydcs airport name); optional `"divert": true` = a landing and recovery field with no squadron |
| `support_base` | optional. Blue field id that hosts the AWACS and tankers |
| `red_fields` | enemy airfields: `id` (must start with `ab_`), `name`, `airport`, `value` |
| `red_extra_airports` | optional. Airport names that are set red in every mission although they are not campaign fields |
| `red_keep` | for a campaign level, the only enemy airfields that exist (`{"1": ["ab_a", "ab_b"]}`) |
| `wing_weight` | which enemy fields get an air wing, and how big a share |
| `field_tier` | depth of each enemy airfield, 1 front to 4 deep. Depth is data only: it no longer gates what can be tasked |
| `bomber_base` | enemy airfield for the strategic bomber wing (or empty) |
| `squadrons` | `id`, `name`, `aircraft`, `base` (the carrier or a blue field id), `count`, `callsign` (unique across the coalition). Optional `role`: `"havcap"` = an AI-only squadron that guards the AWACS and tankers. SQE moves a squadron to a field that can park it |
| `support_targets` | headquarters, fuel and ammunition: `parent` field, `id`, `name`, `kind` (C2, FUEL, DEPOT), `airport`, `dx`, `dy` offset in metres, `value` |
| `road_blue_airports` | airports on the blue side of the road net: they decide which side a road supply site belongs to |
| `front` | the ground war, see "The front" below |
| `tier_labels` | the depth labels shown for enemy assets (index 1 to 4). Required |
| `front_names`, `front_desc` | required by the loader, no longer shown anywhere |
| `climate` | optional. `sun_frac` and `rain_frac` (12 monthly values each: share of possible sunshine, share of days with precipitation), `wind_ms` (mean ground wind, 12 values), `fog` (chance of dawn fog, 12 values), `wind_from_deg` (12 values, the usual wind direction) with `wind_scatter_deg`, and `source` / `wind_from_source` (free text). Without it a mild generic climate is used. Drives Procedural weather |
| `title` | the operation name, shown in the app header and on the briefing's first line |
| `stories` | required. One story per level (`"1"`, `"2"`, `"3"`): `enemy`, `enemy_long`, `background` (a list of paragraphs), `intent`, `now` (a line per posture: Offensive, Holding, Under pressure ...) and `beats` (war-log lines for events such as a base falling or retaken) |

### The front

`front.chain` is the line of airfields from the red end to the blue end. Each node has `airport`, `name` and either `red` (an enemy field id) or `blue` (a friendly field id, the one that falls when the line reaches it). `front.leg_zones` is the number of sectors between each pair of neighbouring nodes (one number per leg). `front.rear_zones` adds quiet sectors behind the blue end. `front.stages`, `front.victory` and `front.counter` are keyed by level: the enemy fields that exist for the war, the fields that win it when taken, and the field whose fall brings the enemy counter-force. A level's chain is cut at its last stage field.

## Data files

Next to `<id>.json` in the pack folder SQE reads, when they exist: `<id>_geo.json` (the `geo` file), `<id>_relief.json` (ground height, 2 km cells), `<id>_sites.json` (the condensed ground, SAM and supply spots) and `<id>_roads_net.json` (the road net). They are built from a DCS terrain scan by `tools/sqe_scan.py`. A pack without them still loads: SQE falls back to a coarse coastline, a flat height estimate for low flights, and its own site placement.

Order matters in `wing_weight` and `red_fields` (they decide the order random choices are made in, so the same seed gives the same campaign).
SQE refuses a pack with a missing key and says which one.
