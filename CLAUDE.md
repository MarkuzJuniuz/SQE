# SQE – Squadron Campaign Engine

Lightweight DCS campaign generator: Python 3.12, a pydcs fork (pinned in `requirements.txt`), PySide6 on Windows.
An abstract war produces a daily tasking order. The player picks ONE flight and SQE builds `SQE_Sortie.miz` with only
that package, its support and the relevant OpFor. Results come back through `SQE_state.json` (written by a Lua hook).
Free, non-commercial, MIT. Bundles NO Eagle Dynamics files.

## Who does what
- **Crew Chief (Claude):** writes code on feature branches, opens PRs. Never pushes to `main`, never tags.
- **Mark:** reviews and merges every PR. Plays and tests in DCS.
- **Ops O (releases):** cuts releases and tags from `main` (`.github/workflows/release.yml`, `tools/mkzip.sh`).
- PR title starts with `[Crew Chief]`, body starts with "Authored by Claude (Crew Chief).", label `crew-chief`.
- `gh pr create` is blocked in cloud sessions (GraphQL): open PRs with `gh api repos/{owner}/{repo}/pulls`.
- One feature per PR. Every feature PR bumps `sqe/__init__.py` `__version__` and adds entries to `docs/CHANGES.md`
  (newest first, `## vX.Y.Z` header) and, for player-visible features, `docs/GUIDE.md`.
- Commit messages: `vX.Y.Z: short title`.

## Ground rules
- Say plainly what is NOT verified in DCS. Nothing counts as working in DCS until Mark has flown it.
- Keep missions tiny: low unit counts, only the chosen package, its support and the relevant OpFor.
  (`--full-map` is a stress option only, never a default.)
- Both sides play by the same rules as far as the setup allows. Red obeying its own doctrine is a feature.
- Never commit ED files (no `MissionScripting.lua`, textures, models, sounds, game screenshots). No donation links.
- Never commit user data: `.sqe` saves, `.miz`, `SQE_state.json`, settings.
- Ask before big or hard-to-undo changes. Parked ideas stay parked until Mark asks.

## Commands
- Smoke test (headless, about a minute): `python tools/smoke_test.py`. CI runs it on every PR (`.github/workflows/smoke.yml`).
  Locally the pydcs fork must be importable (pip-installed from `requirements.txt`, or on `PYTHONPATH`).
- Run the app: `python run_sqe.py` (`--ai-test`, `--full-map` are launch options; see `.vscode/launch.json`).
- Release zip without GitHub-facing files: `tools/mkzip.sh <version>`.

## Where things live (`sqe/`)
- `engine.py` Session: the one API the GUI and the smoke test use (no Qt inside). `state.py` the `.sqe` save. `models.py` plain data.
- War: `war.py` (objectives, AI-resolved packages), `ground.py` (sector front), `sams.py` (rebuild/move), `raids.py`, `reactive.py`,
  `threat.py`, `threatmap.py`, `redair.py` (Red air plan), `airwings.py` (fall-back rule), `ecm.py` (jamming), `roads.py`.
- Sortie: `packages.py`, `routes.py`, `profiles.py` (HIGH/MED/LOW), `loadouts.py`, `radio.py`, `mission_builder.py`
  (package -> miz), `briefing.py`, `kneeboard.py`, `debrief.py` (Lua hook + feedback loop).
- Maps: `theatres.py` + `sqe/data/theatres/<id>.json`; `terrainprobe.py` writes the one-off scan mission that DCS flies to measure the map.
- GUI: `sqe/gui/`. Aircraft registry: `aircraft.py` (add a jet = one `AircraftSpec` + loadouts).

## Standing design decisions (do not revisit without asking)
- **Jamming** (`sqe/ecm.py`; DCS has no area jamming, so SQE rolls it): tier 1 = internal set (F-14, FA-18C, Red Su-24M/Tu-22M3),
  tier 2 = ECM pod on the loadout (ALQ-184). FC3 F-15C is tier 0. Radar-guided missiles only (not ARMs, IR missiles, bombs).
  `P_SELF {1: 0.20, 2: 0.45}`, `P_COVER 0.30` within 2 nm, no effect inside 12 km, full from 40 km. AI jams only PUSH to EGR
  (`OptECMUsing`); player and Red jets are always on. `ecm.jammer_on` / Lua `jamOn` is the single hook for a future cockpit-switch reader.
- **Air-wing retreat** (`airwings.py`): wings/squadrons at or below 30% stand down to `reserve`, recover at 2x replenishment, return after
  at least 2 nights at 65%. Exempt: the player's squadron, carrier squadrons, the Tu-22M3 wing, units under 4 aircraft.
- **LOW decision**: live ARMOR/C2/FUEL/DEPOT/AIRFIELD assets within 5 nm of the route count as AAA sites (merged within 6 km) and
  only affect LOW flights (`profiles._ground_aa`).
- **Roads**: the terrain scan writes `SQE_roads_<theatre>.json`; `ground.snap_roads` moves columns, fuel farms and depots within 3 km
  onto the nearest road once per campaign. Garrisons stay off the road.
- **Start date** defaults to 2006-06-12 (A-10C in service; the Tomcat stays because the war needs it). The date only drives daylight and the kneeboard.
- **AI tasking per role**: Strike = point `Bombing` on the TGT. SEAD = `AttackUnit` on the first radar or `AttackGroup` on the site, boxed to
  10 min. CAS = `AttackGroup` on the column 7 min, then `EngageTargetsInZone` (9 km, vehicles) 18 min. The player's flight and wingmen get
  only the bomb task at the target.
- **Cockpit switches** (future): DCS-BIOS is the reference. SQE would ship its own small export script that writes switch state to a file in
  the SQE folder and the mission hook polls it. The mission scripting environment cannot read cockpit switches. FC3 jets are not exposed.

## Parked (do not build unprompted)
JSOW "Standoff strike" tasking (needs a DCS AI test first) · cockpit-switch jammer reader · comm-menu check-in gate · scripts drop-in folder ·
theatre packs · flight log · runway cratering · carrier-sunk handling · strategic bombers · ingress detours · DCS-version stamp ·
ownership filter.

## Waiting on Mark (DCS checks)
Wreck rendering, weather, carrier alert launches, LOW profile, raid/emergency popups, AI mountain test, no-seat scan, relief scan,
jamming rolls (`jams` list in the state file), road scan message, air-wing retreat, full-map load. Balance retune needs clean all-AI runs.
