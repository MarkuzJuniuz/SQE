# Squadron Campaign Engine (SQE): setup, testing and building guide

Windows + Visual Studio Code. Everything below is copy-paste. Budget about 20 minutes for first-time setup.

---------------------------------------------------------------------------------------------------

## 1. What you need installed

| Need | Why | Get it |
|---|---|---|
| **Python 3.11 or 3.12, 64-bit** | runs SQE | python.org/downloads. **Tick "Add python.exe to PATH"** in the installer. |
| **Git** | the F-14B(U) lives in a pydcs *fork* that pip downloads from GitHub | git-scm.com/download/win (defaults are fine) |
| **VS Code** + the **Python** extension (Microsoft) | editor/debugger | code.visualstudio.com, then Extensions (Ctrl+Shift+X) -> "Python" |
| DCS World with the **F-14B(U)** (and F-16C if you want to fly Air Force) | to fly the missions | you have these |

Close and reopen VS Code after installing Python/Git so they are on PATH.

Check in a terminal (`Ctrl+` ` in VS Code):
```
py --version
git --version
```
Both must print a version.

---------------------------------------------------------------------------------------------------

## 2. Open the project and install the packages

1. Unzip `SQE.zip` somewhere simple, e.g. `C:\Dev\SQE` (avoid OneDrive and Program Files).
2. VS Code -> **File > Open Folder...** -> pick the `SQE` folder (the one containing `sqe`, `tools`, `docs`).
3. Open a terminal (**Terminal > New Terminal**, PowerShell) and run:

```
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

* If PowerShell says *"running scripts is disabled"*, run this once, then activate again:
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
* The `pydcs` line downloads from GitHub, so it needs internet and Git. It takes a minute.
* When VS Code asks *"We noticed a new environment"*, click **Yes**. Otherwise press `Ctrl+Shift+P`
  -> **Python: Select Interpreter** -> choose `.venv`.

Verify the right pydcs got installed (it must know the F-14BU):
```
python -c "from dcs import planes; print(planes.F_14BU.id)"
```
It must print `F-14BU`. If it errors, see Troubleshooting.

---------------------------------------------------------------------------------------------------

## 3. First run

**A. Headless self-test (no DCS, no window)**
```
python tools/smoke_test.py
```
It creates a campaign for the F-14BU and the F-16C, builds a real `SQE_Sortie.miz`, fakes a set of sortie results, applies
them, and advances the day. It must end with `SMOKE TEST PASSED`. (Messages like *"Couldn't detect DCS install"* are harmless.)

**B. The app**
```
python -m sqe
```
or press **F5** in VS Code and pick **"SQE: run app"** (debugger attached, breakpoints work), or double-click `run.bat`.

First launch:
1. It tells you to open **Settings**. Two fields:
   * **DCS Saves**: `C:\Users\<you>\Saved Games\DCS` (or `...\DCS_Server`). Everything hangs off this folder:
     missions go to `Missions\SQE_Sortie.miz`, results are read from `SQE\SQE_state.json`, campaigns are saved as `SQE\*.sqe`.
   * **DCS**: your DCS World install folder. Only used by the patch button below.
2. Tick **Enable DCS scripting access while SQE is open** (SQE asks on first run; it is off until you agree). SQE patches MissionScripting.lua when it starts and restores it when it closes, like Liberation/Retribution (a backup is saved next to the file). This is required for results to come back from DCS. Keep SQE open until the mission is over.
   It makes a backup (`MissionScripting.lua.sqe.bak`) and comments out the `io` and `lfs` sanitize lines.
   If your install is under *Program Files* and it says it cannot write, run VS Code (or SQE.exe) **as administrator** once,
   or edit the file by hand. **DCS updates revert it**: patch again after an update.
3. **File > New Campaign**: name it, pick your jet (**F-14B(U), F/A-18C, F-16C, F-15C or A-10C**), a difficulty, the start month/day (year is 2004) and whether to allow night sorties, OK.

**Playing a day**
1. **Missions** tab: pick a tasking, then press **FLY** on the row of the flight you want to fly (green rows). SQE writes `SQE_Sortie.miz` and opens the **waiting window**. HAVCAP and base-CAP flights are AI-only.
2. Start DCS, **Mission > Open > Missions > SQE_Sortie.miz**, fly it. The kneeboard has two pages: (1) comms + waypoints numbered the way your jet's cockpit numbers them, (2) timeline, bingo/joker, IFF Mode 3, laser code, package who's-who with Link 16 STNs, threats, bullseye. Last steerpoints: RTB, DIVERT, TKR (tanker), BULLS (bullseye).
3. The waiting window updates live (aircraft lost, ground units destroyed, landings). When DCS reports the mission ended it turns green.
   * **Accept results** applies exactly what you see.
   * **Manually Submit...** lets you point at an `SQE_state.json` yourself.
   * **Abort mission** discards the sortie.
   * Closing the window keeps the sortie pending; press **Resume pending sortie** on the Missions tab.
4. After Accept you get the **Debrief** (with the story of how it went and what happened elsewhere), then the next day's tasking order.

---------------------------------------------------------------------------------------------------

## Raids and emergencies (v0.24)
Red raids our airfields. Announced raids are in the tasking order as "Intercept a raid on <airfield>". Surprise raids are settled overnight unless an emergency puts one in front of you: now and then, when you click Fly, a popup tells you a raid has broken out or troops are in contact. If your squadron can take it you can scramble; if not, the war handles it and the popup says why. Details and numbers: docs/CHANGES.md v0.24.0.

## The ground war (v0.23)
The front is five sectors along the Sukhumi to Senaki axis, each with a Red and a Blue strength. Every night contested sectors fight; the line moves; Red takes a field if it holds the sector beside it, and two fallen fields lose the war. Your CAS sorties (and anything that hurts Red supply, such as its fuel farms and depots) are what keeps the line where it is. Blue has the same kind of facilities and supply as Red. The Campaign page shows the sectors and the map draws the front line. See docs/CHANGES.md v0.23.0 for the rules.

## Air defence that rebuilds and moves (v0.26)
A destroyed Red SAM site can be replaced from its fourth day down (half strength, slower when Red's depots and fuel farms are hit); a hurt SA-6 / SA-11 / SA-8 / SA-15 / SA-19 can move a few nm overnight with its garrison. Fixed sites (SA-2, SA-3, SA-10) and the column air defence never move. Blue's airfield defences repair by supply and a strong field lends a battery to the weakest. See CHANGES v0.26.0 for the numbers; the rates are Difficulty.sam_rebuild and sam_scoot.

## Settings (v0.18)
Five tabs. General: takeoff buffer, marshal slack, AI fuel, F-14 names. Campaign: weather, reactive dispatch, ruins, carcasses. Mission build: merging, radius, unit limit, CAP ranges. DCS integration: folders and the scripting patch. Terrain scan: the green / amber status, margins, the scan mission and Re-check.

## Reactive dispatch (v0.17)
Random enemy reinforcements (other wings, only within the type's intercept radius, only aircraft the wing really has) and blue alert pairs (carrier or nearby bases, only aircraft the mission is not using). Scaled by difficulty, capped at 2:1 against your fighters, and skipped first when a mission is near the unit limit. The briefing's Intelligence line hints at them. Settings: Reactive dispatch on/off.

## Carcasses (v0.16)
Damaged and destroyed ground sites within 40 nm of your route show wrecks. They are fixed per site (the same wreck in the same spot every sortie) and a worse site only adds wrecks. Each counts 25% of a unit toward the unit limit and the furthest are dropped first when a mission is too heavy. Settings: Carcasses on/off and Wreck weight.

## 4. Test checklist inside DCS (please report what fails)

I cannot run DCS where I build this. Always run `python tools/smoke_test.py` first (it is isolated and cleans up after itself).

**Newest (v0.5). Confirm these**
- [ ] The target area and your route are *live from the first second*: every SAM site on the route exists and is active; no enemy appears out of nowhere.
- [ ] Enemy CAPs are airborne at mission start on the stations the briefing/kneeboard intelligence line implies; alert fighters sit on a real enemy runway and take off only when your package enters their airfield's detection zone.
- [ ] Day-1 targets are the front belt (Sukhumi / Gudauta / Sochi area) and CAS; deep targets only appear after the belts in front of them are broken.
- [ ] Tanker and AWACS orbit well back from enemy bases, with a HAVCAP flight (Springfield 3 / Viper 3 etc.).
- [ ] After a few nights: a site you destroyed shows up again at half strength in the tasking order (Overnight log: "put up a replacement"); a hurt SA-6 / SA-11 has a new position (log: "has moved about N nm") and its garrison is next to it.
- [ ] Flights push staggered (sweep first, then SEAD, then escorts, then strikers). Your kneeboard times are for YOUR flight only: MSHL arrival, "hold to" time, PUSH (+/-30 s), your TOT (+/-1 min).
- [ ] Heavy SAM cover near the target: AI escorts and sweeps stop and orbit outside the SAM rings (waypoint note "hold here, N nm short of the target") and chase no further than the engage range (Settings > Mission build). Your own flight is not cut short.
- [ ] Text call-outs with a beep: tanker on station, AWACS push and five minutes to TOT, each other flight "pushing" / "off target" / "on station", weapon calls (Magnum, Fox 1/2/3, Rifle, Bombs away), "direct hit", "splash one", "track radar destroyed", "SA-11 site blinded", "target destroyed". (If the beep is silent but text appears, tell me; the sound path is the part I could not verify.)
- [ ] CAS: friendly tanks and a JTAC are in contact with the enemy column; the A-10s attack it. Debrief reports friendly losses.
- [ ] Level 3 only: a bomber raid on the fleet (4x Tu-22M3 with escorts) already en route from their base at mission start.
- [ ] Kneeboard (3 pages, form layout, all times hh:mm:ss): page 1 = comms + waypoints + notes; page 2 = bingo/joker, IFF Mode 3, laser code, weather, target LAT/LONG (strike/SEAD/CAS roles), bullseye, package who's-who with STNs; page 3 = other packages in the mission, threats near the target, intelligence.
- [ ] Wingmen follow you on your route. Nobody has unlimited fuel (AI included). Marshal slack is in Settings (negative values allowed).

**Fixed earlier, still worth a look**
- [ ] No `DictKey_Translation` Lua error; `Saved Games\DCS\SQE\SQE_state.json` appears while you fly.
- [ ] SAM sites fire and show threat rings; callsigns read like `Springfield 1-2`.
- [ ] Link 16: F-16C and F/A-18C list package flights as team members/donors. A-10C II uses SADL. F-14B(U) and F-15C have no datalink in DCS data. **On a dedicated server re-save the mission in the Mission Editor first.**
- [ ] Waypoint numbers match your cockpit (F-15C: `B`, then 1, 2...). Tanker and bullseye are the last steerpoints.

**Still unverified**
- [ ] Other flights spawn airborne, orbit at MSHL and cross PUSH on time (timed orbit stop).
- [ ] Your flight is hot on the cat/runway (INS aligned on the F-14B(U)); F-15C presets must be set by hand (SQE tells you).
- [ ] AI flights disappear after landing; no Supercarrier deck crew.

Build size: the waiting window shows how many groups/units each mission has, and the mission seed.

---------------------------------------------------------------------------------------------------

## 5. Compile to an executable (SQE.exe)

With the venv active (step 2):
```
.\build_exe.bat
```
Result: `dist\SQE\SQE.exe`. Copy the **whole `dist\SQE` folder** wherever you like. Notes:

* The build takes a few minutes and the folder is a few hundred MB (PySide6 is large).
* First launch of an unsigned exe may trigger Windows SmartScreen or antivirus: choose *More info > Run anyway*.
* The exe keeps its settings in `%APPDATA%\SQE\settings.json` (same as running from source).
* If the exe starts and closes instantly, run it from a terminal (`dist\SQE\SQE.exe`) to see the error, or rebuild without `--windowed`.
* I could not build the exe myself (PyInstaller builds for the OS it runs on), so this step is untested. If it fails, send me the last lines of output.

Manual command, if you prefer it to the .bat:
```
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name SQE --collect-all dcs --collect-submodules sqe run_sqe.py
```
(The map data is embedded in the code now, so no extra `--add-data` is needed.)
```
```

---------------------------------------------------------------------------------------------------

## 6. Where things live (and what to tweak)

| File | What it controls |
|---|---|
| `sqe/difficulty.py` | the three difficulty presets: enemy aircraft count/types, SAM mix, air-defence integration, AI skill, loss rate, damage, replenishment, variance (0 = no dice, 1 = full dice) |
| `sqe/scenario.py` | the Caucasus scenario: bases, carrier position, squadrons, enemy airfields, SAM clusters, armor columns, HQs |
| `sqe/narrative.py` | the conflict background, phases, intel lines, debrief story templates (add variants to any list) |
| `sqe/aircraft.py` | every jet: service (derived from carrier/runway), roles, refuel type, speeds/altitudes, radio band |
| `sqe/loadouts.py` | default loadouts per role; enemy air-to-air loads |
| `sqe/mission_builder.py` -> `MissionOptions` | hold minutes, launch offset, AI unlimited fuel, AI despawn on landing, carrier TACAN/ICLS/Link-4, client slot |
| `sqe/packages.py` | how packages are built and when Navy and USAF mix |
| `sqe/war.py` | objective planning, AI-resolved packages (percentile roll with shown odds), victory/defeat |
| `sqe/briefing.py`, `sqe/kneeboard.py` | briefing text and kneeboard pages |
| `sqe/settings.py` | the two settings and the MissionScripting patch helper |
| `sqe/threat.py` | how many enemy fighters defend a target and how many friendly fighters answer them |
| `sqe/callsigns.py` | DCS-native callsign names/ids per aircraft type |
| `sqe/timeofday.py` | sunrise/sunset and the daily tasking timeline (day only, or night too) |
| `sqe/threatmap.py` | SAM rings, the FLOT/gatekeeper rule, tanker stations, egress steering, corridor sites |
| `sqe/data/theatres/<theatre>_geo.json` | the map's coastline and borders (Natural Earth, public domain) in DCS coordinates, one file per theatre pack |

**Custom loadouts**: in the Mission Editor name an aircraft group like `F-14BU:STRIKE`, `F-14BU:CAP`, `FA-18C:SEAD`, `A-10C:CAS`,
build the loadout, save, then `python tools/capture_loadouts.py that.miz`. They override the defaults.

**Campaign files**: `*.sqe` are readable JSON (versioned). Backups rotate in `SQE\backups`. Copy a `.sqe` to move a campaign between
`DCS` and `DCS_Server`.

---------------------------------------------------------------------------------------------------

### Squadrons, the Missions filter and package merging (v0.7)
- New Campaign lets you pick your squadron. Missions shows "My squadron" packages by default; switch to "All packages" to fly any flight of your jet type.
- Settings > Package merging > "Same area" folds packages whose target is inside the Merge radius (default 50 nm, centred on your target and slid inward at the edge of the target area) into one mission: ones that start up to 30 minutes after yours, and ones that started up to "Earlier packages" minutes (default 15) before yours. An earlier package is already airborne and underway when the mission starts (it spawns along its route, or holding at its marshal point); one that has already struck and gone home by then is not flown, but its target is shown as smoking ruins (Settings > Ruins). One that has struck but is still airborne spawns on its way home, with the ruins already in place; the outcome is rolled when the mission is built and applied at the debrief. Compare the unit counts on the waiting window with merging Off to see the performance cost. Lower the unit limit if your VR system struggles.
- On the Missions screen, a package that another one folds in is shown inside that package's panel, each with its own flights and FLY button. The line above each table says what FLY gives you: the start time, and which other packages fly with it. Pressing FLY on a later package starts the mission at its time instead.

### Depth tiers, SEAD vs DEAD, garrisons (v0.8)
- The war opens over Abkhazia (tiers 1 and 2: the armour columns and the Sukhumi/Gudauta belts). The coast and north Caucasus (Sochi, Nalchik, Beslan, Mozdok) open when the front advances, and the deep rear after that. Overview shows "front: stage N of 3"; Forces > Enemy assets shows each asset's depth and whether it is still locked.
- A DEAD objective is a SEAD flight (HARM, pushes about 90 s ahead) plus a DEAD flight (the strikers). HARMs go for the radars. Radars dead and launchers alive = the site is SUPPRESSED, not destroyed; it is offered again as a mop-up ("Finish off ..."). Fly either flight; the kneeboard labels them SEAD and DEAD.
- Long-range SAM sites may have a dug-in garrison (CAS target: your troops with a JTAC advance on it). Level 2 and 3 also put short-range SAMs (SA-8/15/19) with the front-line columns.
- Things to check in DCS: do the AI HARMs actually target the radars (AttackUnit on the first radar of the site)? Does the SEAD flight arrive about 90 s ahead of the DEAD flight? Do the numbers feel right (tier boundaries, 30% advance threshold, 14 stall days: `war.py`, `FRONT_*`; garrison odds and SAM counts: `difficulty.py`; spawn caps: `threatmap.MAX_ROUTE_SITES` and the "two nearest defenders" line in `mission_builder._spawn_opfor_ground`)?

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` fails on the pydcs line | Git is missing or not on PATH. Install Git, reopen VS Code, retry. |
| `AttributeError: ... F_14BU` | the wrong pydcs is installed. `pip uninstall pydcs`, then `pip install -r requirements.txt` again. |
| `ModuleNotFoundError: sqe` | run from the project root (the folder that contains `sqe`). In VS Code open that folder, not its parent. |
| Settings says folders are invalid | DCS Saves must already exist (start DCS once). The `Missions` and `SQE` subfolders are created for you. |
| Waiting window stays on "Waiting for DCS results" | MissionScripting not patched; or you flew a different mission than `SQE_Sortie.miz`; or you rebuilt with FLY after starting (stale results are ignored). |
| "Found a results file, but it belongs to a different sortie" | an old file or another campaign. Press FLY again for a fresh one, or use Manually Submit. |
| A flight is missing from a package | not enough serviceable aircraft or out of range today; replenishment runs each day. |
| Everything flies but the debrief says nothing changed | results were from the first 30 s checkpoint only; fly longer, or check the mission end event fired (exit via the DCS "Mission > Quit" menu). |

---------------------------------------------------------------------------------------------------

## 8. Known gaps (honest list)

* Not yet flown in DCS by me. Items in section 4 are the unknowns.
* Caucasus only. Syria would be a new scenario function in `scenario.py` plus a theatre switch in `mission_builder.py`.
* Allied bombers (B-52H / B-1B) and strategic missions on bomber bases are not tasked yet.
* Not built yet: the war *tempo* model (day-1 surge, reinforcement waves, per-difficulty pacing), runway-cratering/base-repair windows, and what happens if the carrier is sunk.
* Radio call-outs are text plus a beep, not spoken voice.
* JDAM target data (DTC) and LANTIRN waypoint designation are not generated by pydcs; enter TGT coordinates from the kneeboard.
* Weather is always clear for now (seasonal temperature only). Procedural/static weather options come later.
* Special points (IP, ST) are added for the F-14BU as per the F-14 manual; confirm in-game that the BU shows them.
* The campaign has one story (Operation IRON TIDE). New stories mean new text in `narrative.py` and a new scenario.


### Weather (v0.15)

Settings > Weather. **Clear** (default) builds what SQE always built. **Procedural** uses the theatre's climate and changes slowly day to day; the fixed options hold one weather for the whole campaign.

* What you see: the Missions page shows each package's weather at its start time; the briefing and the kneeboard carry it; DCS gets a real cloud preset, base, visibility, rain, dawn fog, wind and turbulence.
* Weapons: laser-guided weapons are unusable under a broken or overcast sky below 10,000 ft or in rain or low visibility; imaging Mavericks need a ceiling above about 3,000 ft and 6 km; unguided weapons need 1,500 ft and 5 km. Whatever the weather rules out is swapped for a JDAM on the same pylon, and the change is shown. JDAMs, HARMs and air-to-air weapons don't care.
* Scrubs: storms, fog or a very low ceiling stop every attacking package; so does a flight with nothing it can use (for example an A-10 with only Mavericks and cluster bombs under a 1,000 ft ceiling). Defensive air patrols still fly. A scrubbed package is not flown and its target is left alone by the war simulation.
* The thresholds are in `sqe/weather.py` (`LASER_BASE_FT`, `EO_BASE_FT`, `VISUAL_BASE_FT` and so on) if you want to change them.

### Theatres (v0.14)

SQE builds the Caucasus out of the box. Maps are data: each theatre is a JSON "pack" (airfields, squadrons, tiers, carrier station, sun position, temperatures, scan area, operation text). To add one, see docs/THEATRES.md and put the file in `%APPDATA%\SQE\theatres\`. The New Campaign window shows a Theatre picker once more than one pack is installed.

### Terrain scan (v0.12)
Ground sites are placed with a coastline that is only roughly right, and it knows nothing about rivers. For exact placement run the scan once:
1. Open SQE, then Settings. Set the Saved Games folder, press "Create terrain scan mission".
2. Keep SQE open (it enables DCS scripting while open; the scan needs the same access as debriefs).
3. In DCS: Fly > Missions > My Missions > SQE_TerrainScan, then Fly (you start in a parked Su-25T, which is free with DCS World, so no paid aircraft is needed). Messages show the percentage; wait for "SQE terrain scan COMPLETE" (about two minutes, DCS may stutter), then leave the mission.
4. Open or start a campaign in SQE. Settings > Terrain scan reads "loaded" and, from v0.22, a second line "Ground height: loaded ...". An older scan has no ground height: run the scan mission once more (it measures both).
Sites then keep the Shore margin from the sea and lakes (default 1500 m) and the river margin from rivers and shallow water (default 100 m); both are in Settings. Re-running is only needed after a DCS terrain update.
