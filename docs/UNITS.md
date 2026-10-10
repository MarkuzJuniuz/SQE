# Aircraft and unit packs

SQE-Danica can put any aircraft DCS flies in a mission. The table behind it (`sqe/catalog.py`) is built from three sources:

| Source | What it is | Profile and loadouts |
|---|---|---|
| Tuned | F-14B(U), F/A-18C, F-16C, F-15C, A-10C (`sqe/aircraft.py`) | hand-tuned route profiles, bingo/joker and loadouts |
| Mod | unit packs in `sqe/data/units/` and `%APPDATA%\SQE\units\` (e.g. A-4E-C) | from the pack, loadouts from the mod's presets |
| Generic | every other flyable type pydcs knows (warbirds, MiG-21, AJS37, ...) | from its speed class, loadouts from DCS presets |

In **File > New Campaign**, pick any aircraft. If the theatre has no squadron of that type, choose "New ... squadron at <base>".

## Loadouts

SQE looks for a loadout in this order and uses the first one it finds:

1. Captured overrides in `loadouts.json` (`tools/capture_loadouts.py`).
2. The tuned tables (tuned jets only).
3. The unit pack's `loadouts` table.
4. DCS payload presets: the stock ones, the mod's own `UnitPayloads` folder, and the ones you saved in the Mission Editor.
   - A preset named **`SQE CAS`**, **`SQE STRIKE`**, **`SQE SEAD`** or **`SQE CAP`** wins.
   - Otherwise SQE uses a preset whose task matches the role.
5. A generic load built from the pylon tables.

If nothing is found, the jet flies clean and the mission warnings tell you which preset to save.

SQE reads the presets from the **DCS** and **DCS Saves** folders in Settings, so set both.

## Adding a mod aircraft

1. Install the mod as usual in `Saved Games\DCS\Mods\aircraft\<mod>`.
2. Run `python tools/make_unit_pack.py` to list your mods and whether SQE knows them.
3. Run `python tools/make_unit_pack.py --write --id <type>` to write a starter pack to `%APPDATA%\SQE\units\<type>.json`.
4. Open the pack and check `fuel_max` (kg), `max_speed` (km/h), `pylons`, `roles` and `era`. Then set `"verified": true`.
5. In the Mission Editor, save presets named `SQE CAS`, `SQE STRIKE` and so on for the jet.

Missions that use a mod aircraft list it under `requiredModules`. DCS then names the missing mod instead of failing to load.

## Pack keys

See the docstring at the top of `sqe/modunits.py`. Only `id` is required, plus a `type` block when pydcs doesn't know the aircraft.
