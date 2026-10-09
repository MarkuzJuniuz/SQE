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
| `scan` | terrain scan: `file` (the name written to `Saved Games\SQE`), the area `x0 x1 y0 y1` in metres, `step`, and `probe_airport` (where the free Su-25T starts) |
| `carrier` | `id`, `name`, and the station: `from_airport`, `heading` and `distance_m` out to sea |
| `blue_fields` | friendly airfields: `id`, `name`, `airport` (the pydcs airport name) |
| `red_fields` | enemy airfields: `id` (must start with `ab_`), `name`, `airport`, `value` |
| `red_keep` | for a campaign level, the only enemy airfields that exist (`{"1": ["ab_a", "ab_b"]}`) |
| `wing_weight` | which enemy fields get an air wing, and how big a share |
| `field_tier` | depth tier of each enemy airfield, 1 front to 4 deep |
| `bomber_base` | enemy airfield for the strategic bomber wing (or empty) |
| `squadrons` | `id`, `name`, `aircraft`, `base` (the carrier or a blue field id), `count`, `callsign` (unique across the coalition) |
| `support_targets` | headquarters, fuel and ammunition: `parent` field, `id`, `name`, `kind` (C2, FUEL, DEPOT), `airport`, `dx`, `dy` offset in metres, `value` |
| `front` | `from_airport` and `to_airport`: where the ground push runs |
| `tier_labels`, `front_names`, `front_desc` | text for the tiers and the three front stages |
| `title`, `background` | the operation name and the conflict background shown in the app and on the briefing |

Order matters in `wing_weight` and `red_fields` (they decide the order random choices are made in, so the same seed gives the same campaign).
SQE refuses a pack with a missing key and says which one.

## Making a scan for a new theatre

Create a campaign on the theatre, then Settings > Create terrain scan mission. The scan area and file name come from the pack,
so each theatre gets its own `SQE_terrain_<name>.json`. Without a scan SQE falls back to the coarse coastline.
