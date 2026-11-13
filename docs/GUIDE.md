# Squadron Campaign Engine (SQE): setup and first run

Windows + Visual Studio Code. Everything below is copy-paste. Budget about 20 minutes for first-time setup.
For what changed in each version see `docs/CHANGES.md`; for adding a map see `docs/THEATRES.md`.

---------------------------------------------------------------------------------------------------

## 1. What you need installed

| Need | Why | Get it |
|---|---|---|
| **Python 3.13 or 3.14, 64-bit** | runs SQE | python.org/downloads. **Tick "Add python.exe to PATH"** in the installer. |
| **Git** | the F-14B(U) lives in a pydcs *fork* that pip downloads from GitHub | git-scm.com/download/win (defaults are fine) |
| **VS Code** + the **Python** extension (Microsoft) | editor/debugger | code.visualstudio.com, then Extensions (Ctrl+Shift+X) -> "Python" |
| DCS World with the module of the jet you want to fly | to fly the missions | F-14B(U), F/A-18C, F-16C, F-15C or A-10C |

Close and reopen VS Code after installing Python/Git so they are on PATH.

Check in a terminal (`Ctrl+` ` in VS Code):
```
py --version
git --version
```
Both must print a version.

---------------------------------------------------------------------------------------------------

## 2. Open the project and install the packages

1. Put the `SQE` folder somewhere simple, e.g. `C:\Dev\SQE` (avoid OneDrive and Program Files).
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
It checks the core functions (campaigns load and save, missions are generated, the required flights are in a package, the
`.miz` structure is sound) and must end with `SMOKE TEST PASSED`. `--list` shows the checks and `--only <name>` runs one.
(Messages like *"Couldn't detect DCS install"* are harmless.)

**B. The app**
```
python -m sqe
```
or press **F5** in VS Code and pick **"SQE: run app"**, or double-click `run.bat`.

First launch:
1. It tells you to open **Settings**. Two fields:
   * **DCS Saves**: `C:\Users\<you>\Saved Games\DCS` (or `...\DCS_Server`). Everything hangs off this folder:
     missions go to `Missions\SQE_Sortie.miz`, results are read from `SQE\SQE_state.json`, campaigns are saved as `SQE\*.sqe`.
   * **DCS**: your DCS World install folder. Only used by the patch button.
2. Tick **Enable DCS scripting access while SQE is open** (SQE asks on first run; it is off until you agree). SQE patches
   `MissionScripting.lua` when it starts and restores it when it closes (a backup, `MissionScripting.lua.sqe.bak`, is saved next
   to the file). This is required for results to come back from DCS. Keep SQE open until the mission is over.
   If your install is under *Program Files* and it says it cannot write, run VS Code (or SQE.exe) **as administrator** once,
   or edit the file by hand. **DCS updates revert it**: patch again after an update.
3. **File > New Campaign**: name it, pick your jet, your squadron, a difficulty level (1 Insurgent, 2 Regional power,
   3 Near-peer) and the start month/day (the year is 2006), then OK.

---------------------------------------------------------------------------------------------------

## 4. How a turn works

The campaign runs in **4-hour turns**, six a day, starting at 08:00 on Day 1. Each turn the planner lays out that turn's
packages for both sides; whatever you do not fly is settled by the war simulation.

1. **Missions** tab: pick a tasking, then press **FLY** on the row of the flight you want to fly (green rows). SQE writes
   `SQE_Sortie.miz` and opens the **waiting window**. Base, carrier, tanker and AWACS cover patrols are planned each turn and
   are AI-only. Red raids on your fields, supply sites and troops are listed as "Intercept" jobs with a red border.
2. Start DCS, **Mission > Open > Missions > SQE_Sortie.miz**, fly it. The kneeboard carries comms and waypoints numbered the
   way your jet's cockpit numbers them, the timeline, bingo/joker, IFF, laser code, the package who's-who, threats and bullseye.
3. The waiting window updates live (aircraft lost, ground units destroyed, landings). When DCS reports the mission ended it
   turns green.
   * **Accept results** applies exactly what you see.
   * **Manually Submit...** lets you point at an `SQE_state.json` yourself.
   * **Abort mission** discards the sortie.
   * Closing the window keeps the sortie pending; press **Resume pending sortie** on the Missions tab.
4. After Accept you get the **Debrief**, then the clock moves on and the next turn is planned.

**Skip Turn** stands down for the turn: its packages are resolved by the war simulation. The **Auto-Skip** box in the sidebar
keeps skipping for you: *Stand-Down Turns* (turns with nothing you can fly), *Night Turns*, and *Crew Rest* (after a flown
sortie, skip until the chosen number of hours has passed). The options add up, and one after-action report lists everything
that was skipped.

Two features worth knowing: **package merging** (Settings > Mission build) folds packages whose targets are close into one
mission, and the **unit limit** there lets you trade detail for performance. `--full-map` (alone or with the AI test) builds
every sortie with everything on the map, as a stress test, not for play.

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
* If the exe starts and closes instantly, run it from a terminal (`dist\SQE\SQE.exe`) to see the error.

Manual command, if you prefer it to the .bat:
```
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name SQE --collect-all dcs --collect-submodules sqe run_sqe.py
```
Releases are built by `.github/workflows/release.yml` (Python 3.14).

---------------------------------------------------------------------------------------------------

## 6. Terrain data

SQE ships relief data and site lists for the Caucasus, so no terrain scan is needed to play. `tools/sqe_scan.py` rebuilds them
after a DCS terrain update (for developers).

---------------------------------------------------------------------------------------------------

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` fails on the pydcs line | Git is missing or not on PATH. Install Git, reopen VS Code, retry. |
| `AttributeError: ... F_14BU` | the wrong pydcs is installed. `pip uninstall pydcs`, then `pip install -r requirements.txt` again. |
| `ModuleNotFoundError: sqe` | run from the project root (the folder that contains `sqe`). In VS Code open that folder, not its parent. |
| Settings says folders are invalid | DCS Saves must already exist (start DCS once). The `Missions` and `SQE` subfolders are created for you. |
| Waiting window stays on "Waiting for DCS results" | MissionScripting not patched (DCS updates revert it); or you flew a different mission than `SQE_Sortie.miz`; or you rebuilt with FLY after starting (stale results are ignored). |
| "Found a results file, but it belongs to a different sortie" | an old file or another campaign. Press FLY again for a fresh one, or use Manually Submit. |
| A flight is missing from a package | not enough serviceable aircraft or out of range this turn; jets that flew are in refit for a few hours. |
| Everything flies but the debrief says nothing changed | results were from the first 30 s checkpoint only; fly longer, or check the mission end event fired (exit via the DCS "Mission > Quit" menu). |
| "Saved campaign is from an older version" | campaign formats change between versions; SQE offers to back it up and start a new campaign. |

---------------------------------------------------------------------------------------------------

## 8. Where to look next

* `docs/CHANGES.md`: what changed in every version, newest first.
* `docs/THEATRES.md`: how a map pack is built.
* `tools/`: `smoke_test.py` and the other test and probe scripts.
