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
3. **File > New Campaign**: name it, pick **F-14B(U)** or **F-16C**, pick a difficulty, OK.

**Playing a day**
1. **Missions** tab: pick a tasking, pick your flight, press **FLY**. SQE writes `SQE_Sortie.miz` and opens the **waiting window**.
2. Start DCS, **Mission > Open > Missions > SQE_Sortie.miz**, fly it. Kneeboard has comms, waypoints with times, and a timeline/threat page.
3. The waiting window updates live (aircraft lost, ground units destroyed, landings). When DCS reports the mission ended it turns green.
   * **Accept results** applies exactly what you see.
   * **Manually Submit...** lets you point at an `SQE_state.json` yourself.
   * **Abort mission** discards the sortie.
   * Closing the window keeps the sortie pending; press **Resume pending sortie** on the Missions tab.
4. After Accept you get the **Debrief** (with the story of how it went and what happened elsewhere), then the next day's tasking order.

---------------------------------------------------------------------------------------------------

## 4. Test checklist inside DCS (please report what fails)

I could not run DCS where I built this, so these are the things to verify. Tick them off:

- [ ] `SQE_Sortie.miz` appears directly in the Missions list and loads without errors.
- [ ] Your flight is on the catapult (F-14BU) / runway (F-16C), engines running, **INS aligned** on the F-14BU.
- [ ] Your wingman is next to you (carrier flights are capped at 2 on purpose: catapult spots).
- [ ] **Radios**: COMM1 CH1 ATC, CH2 AWACS, CH3 tanker, CH4 JTAC (only on CAS missions), CH5 second tanker; COMM2 CH1 your flight.
- [ ] Kneeboard shows 3 pages (comms, waypoints with times, timeline and threats).
- [ ] Other flights **spawn in the air** and fly to **MSHL**, then **orbit**. *Important:* do they leave the orbit at the PUSH time?
      (The hold is a timed orbit stop; I am not 100% sure DCS counts that time from mission start. If the AI leave early or never,
      tell me what happened.)
- [ ] Tankers on station with the TACAN shown on the kneeboard; basket tanker works for the Tomcat.
- [ ] AI flights never run low on fuel; AI flights **disappear shortly after landing**.
- [ ] No Supercarrier deck crew (uses the free Stennis).
- [ ] While flying, `Saved Games\DCS\SQE\SQE_state.json` appears and the waiting window shows numbers.
- [ ] Accept -> debrief -> new day; Save, close the app, re-open: the campaign and the day are there.

If the waiting window never shows numbers: the MissionScripting patch is missing, or DCS cannot write to the folder. In DCS press
`F10`... a message "SQE: results cannot be saved" at mission start means the patch is not applied.

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
* Bombers (B-52H / B-1B) are not tasked yet. A-10C, F-15C, F/A-18C are.
* JDAM target data (DTC) and LANTIRN waypoint designation are not generated by pydcs; enter TGT coordinates from the kneeboard.
* Weather is whatever pydcs defaults to; no weather in the briefing yet.
* Special points (IP, ST) are added for the F-14BU as per the F-14 manual; confirm in-game that the BU shows them.
* The campaign has one story (Operation IRON TIDE). New stories mean new text in `narrative.py` and a new scenario.
