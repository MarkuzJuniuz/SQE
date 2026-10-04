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
   * **DCS Saves**: `C:\Users\Mark\Saved Games\DCS` (or `...\DCS_Server`). Everything hangs off this folder:
     missions go to `Missions\SQE_Sortie.miz`, results are read from `SQE\SQE_state.json`, campaigns are saved as `SQE\*.sqe`.
   * **DCS**: your DCS World install folder. Only used by the patch button below.
2. Click **Patch MissionScripting.lua**. This is required for results to come back from DCS (same as Liberation/Retribution).
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

## 4. Test checklist inside DCS (please report what fails)

I cannot run DCS where I build this. Tick these off, newest fixes first:

**Fixed in v0.3. Confirm they are really fixed**
- [ ] No `DictKey_Translation` Lua error when the mission loads, and `Saved Games\DCS\SQE\SQE_state.json` appears while you fly (the waiting window shows numbers).
- [ ] Enemy SAM sites fire and show threat rings in the F10 map (they are now single working groups). F10 > enemy-units view if your server allows it.
- [ ] The A-10s on a CAS mission find and attack the armor column (they get an explicit attack-group order plus a zone search). If they still just fly waypoints, send `dcs.log`.
- [ ] Aircraft names read like `Springfield 1-2` in the F10 map, radio and Tacview.
- [ ] Flights are 2 or 4 ships. Tanker + AWACS are well away from enemy airfields and a HAVCAP orbits with them.
- [ ] Enemy fighters are not up when you launch; they appear near the target around TOT (+/- 1-2 min), coming from the enemy side.
- [ ] Patriot + AAA sit beside every airfield used by the package, and the carrier has a cruiser and two escorts.
- [ ] CAS missions have a base-CAP flight over the A-10s' field.
- [ ] Kneeboard waypoint numbers match your cockpit (F-15C: `B`, then 1, 2...). Tanker and bullseye are the last steerpoints.
- [ ] Link 16: F-16C and F/A-18C show their package flights as team members/donors (STNs are on page 2 of the kneeboard). A-10C II uses SADL. F-14B(U) and F-15C have no datalink in DCS data. **If you fly a dedicated server, re-save the mission in the Mission Editor first (Retribution warns F-16C datalink data can crash servers otherwise).**

**Still unverified**
- [ ] `SQE_Sortie.miz` loads in the Missions list; your flight is hot on the cat/runway (INS aligned on the F-14B(U)).
- [ ] Other flights spawn airborne, orbit at MSHL, and leave on the PUSH time (the hold is a timed orbit stop; I am not 100% sure DCS counts that time from mission start).
- [ ] Radios: COMM1 CH1 ATC, CH2 AWACS, CH3 tanker, CH4 JTAC (CAS only), CH5 second tanker; COMM2 CH1 your flight. **F-15C presets cannot be written by pydcs**: set them by hand from the kneeboard (SQE tells you).
- [ ] AI flights never run low on fuel and disappear shortly after landing; no Supercarrier deck crew.
- [ ] Accept -> debrief -> next day; your pilot log (Pilot tab) counts sorties, flight time and kills credited to you.

Build size: after FLY the waiting window shows how many groups/units the mission has, so you can watch performance.

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
| `sqe/data/caucasus_geo.json` | the map's coastline and borders (Natural Earth, public domain) converted to DCS coordinates |

**Custom loadouts**: in the Mission Editor name an aircraft group like `F-14BU:STRIKE`, `F-14BU:CAP`, `FA-18C:SEAD`, `A-10C:CAS`,
build the loadout, save, then `python tools/capture_loadouts.py that.miz`. They override the defaults.

**Campaign files**: `*.sqe` are readable JSON (versioned). Backups rotate in `SQE\backups`. Copy a `.sqe` to move a campaign between
`DCS` and `DCS_Server`.

---------------------------------------------------------------------------------------------------

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
* Allied bombers (B-52H / B-1B) are not tasked yet.
* JDAM target data (DTC) and LANTIRN waypoint designation are not generated by pydcs; enter TGT coordinates from the kneeboard.
* Weather is always clear for now (seasonal temperature only). Procedural/static weather options come later.
* Special points (IP, ST) are added for the F-14BU as per the F-14 manual; confirm in-game that the BU shows them.
* The campaign has one story (Operation IRON TIDE). New stories mean new text in `narrative.py` and a new scenario.
