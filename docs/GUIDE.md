# Squadron Campaign Engine (SQE): setup and first run

Windows + Visual Studio Code. Everything below is copy-paste. Budget about 20 minutes for first-time setup.
For what changed in each version see `docs/CHANGES.md`; for how the campaign works and its rules see `docs/CAMPAIGN.md`; for adding a map see `docs/THEATRES.md`.

---------------------------------------------------------------------------------------------------

## 1. What you need installed

| Need | Why | Get it |
|---|---|---|
| **Python 3.13 or 3.14, 64-bit** | runs SQE | python.org/downloads. **Tick "Add python.exe to PATH"** in the installer. |
| **Git** | the F-14B(U) lives in a pydcs *fork* that pip downloads from GitHub | git-scm.com/download/win (defaults are fine) |
| **VS Code** + the **Python** extension (Microsoft) | editor/debugger | code.visualstudio.com, then Extensions (Ctrl+Shift+X) -> "Python" |
| DCS World with the module of the jet you want to fly | to fly the missions | F-14B(U) or F-14B, F/A-18C, F-16C, F-15C, A-10C or A-10A |

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
3. **File > New Campaign**: name it, pick the map, your jet, your squadron, a difficulty level (1 Insurgent, 2 Regional power,
   3 Near-peer) and the start month/day (the year goes with the map: Caucasus 2006, Syria 2001), then OK.

---------------------------------------------------------------------------------------------------

## 4. How a turn works

The campaign runs in **4-hour turns**, six a day, starting on Day 1 at 08:00 (Caucasus) or 00:00 (Syria). Each turn the planner lays out that turn's
packages for both sides; whatever you do not fly is settled by the war simulation. The packages launch in four waves, an hour
apart, so the start times on the Missions tab are spread over the turn's four hours (about four clusters).

1. **Missions** tab: pick a tasking, then press **FLY** on the row of the flight you want to fly (green rows). SQE writes
   `SQE_Sortie.miz` and opens the **waiting window**. Base, carrier, tanker and AWACS cover patrols are planned each turn and
   are AI-only. Red raids on your fields, supply sites and troops are listed as "Intercept" jobs with a red border.
   What a raid carries follows its target (runway-piercing bombs on a runway, cluster bombs on troops, anti-radiation missiles
   fired from about 50 nm on a SAM site); the list is in CAMPAIGN.md, section 5.
2. Start DCS, **Mission > Open > Missions > SQE_Sortie.miz**, fly it. The kneeboard carries comms and waypoints numbered the
   way your jet's cockpit numbers them, the timeline, bingo/joker, IFF, laser code, the package who's-who, threats and bullseye.
   Where a leg of your route would cut a live SAM ring, SQE adds turnpoints, **TP1**, **TP2** and so on in flying order (the notes line of page 1 says how many
   nm and minutes they add), moves your egress point out of the rings, and puts a strike or SEAD IP outside the rings that hold the
   target. The plain F-14B holds only three waypoints, so every other point of its route (WP column "-", the turnpoints too) has its
   position on the line under its row on page 1, as degrees and decimal minutes (enter the minutes and tenths). When they do
   not fit, they are on an extra page after page 1, **ROUTE POINTS (enter by hand)**, in route order with altitude.
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

The war behind the turns (what is planned, how red fights, how the campaign is won or lost) is in `docs/CAMPAIGN.md`.

Two features worth knowing: **package merging** (Settings > Mission build) flies every package that starts inside the time
windows (15 minutes before and 30 after yours by default) in the same mission, nearest to your target first, and the **unit
limit** there (250 by default) lets you trade detail for performance: over it, the furthest packages are left out first. The
**Target Area Radius** (15 nm) sets how much of the ground war round your target is built. `--full-map` (alone or with the AI test) builds
every sortie with everything on the map, as a stress test, not for play.

**Blast Wave** (Settings > General, on by default; it was called Splash Damage before v0.41.655). DCS often leaves a vehicle a few metres from a bomb untouched. With Blast Wave on, when a bomb, rocket or air-to-ground missile (a HARM included) reaches the ground, every ground unit or ship inside a blast radius around the impact takes a blast of its own: the radius is 9 m times the cube root of the warhead's explosive mass in kilograms (capped at 120 m), and the blast is weaker the further the unit is from the impact. The direct hit is left to DCS, and a weapon that ends in the air (a JSOW opening its dispenser, a missile shot down) does nothing. The kills it causes count for the shooter. The numbers are SQE's own judgment. The idea of adding blast damage to DCS explosions is not SQE's: it comes from the community Splash Damage scripts (wheelyjoe's original, then Spencer Shepard's "GRIMM" Splash Damage 2.0 and Stevey666's 3.x). SQE uses no code from them; its script was written for SQE.

**F-14 RIO Radar** (Settings > DCS Integration, experimental, not installed by default). For the F-14B or F-14B(U) you fly. **F10 > Other > RIO Radar** has three calls: **Hunt Bandit** has Jester lock an enemy aircraft for you, **Hunt Next** drops it and locks another, **Hunt Off** lets go. SQE picks the nearest enemy ahead that the radar should be able to see (within 65 degrees of your nose, 60 nm) and tells Jester to lock exactly that one, so he cannot lock a friendly; if nothing comes up in a few seconds it tries the next, up to four, then says there is nothing he can lock. The message names what he got: "RIO: Got one. Su-27, 020 for 28, angels 24." (magnetic bearing from you, range in nm, height in thousands of feet). The lock is single-target track: the radar leaves TWS, so no multiple Phoenix shots at once, and the bandit's warning receiver will normally show it. "Lost him" means the lock is gone and Jester will not take it up again on his own. The three names were picked not to clash with common voice-command phrases. In a mission with the feature on, red aircraft are named AirTarget01 and up (only the first 99 can be locked). Install copies a script to `Saved Games\DCS\Scripts` and adds one line to `Export.lua`; install it before you generate the mission. It needs mission scripting access (SQE open), and works in single player and with the dedicated server on your own PC. What it sends is logged in `Saved Games\DCS\Logs\SQE_rio_radar.log`. Not yet proven in a flown mission.

**F-14 RIO Navigation** (Settings > DCS Integration, experimental, not installed by default; it was the F-14B Turnpoints Script). For the F-14B or F-14B(U) you fly. **F10 > Other > RIO Navigation** holds your two calls: **Your Nav** hands Jester the waypoints, **My Nav** takes them back. He has the nav from the start of the mission and answers "I have the nav" or "Your nav". He sets your steerpoint to MSHL, moves to PUSH at your departure time (the "hold to" time on the kneeboard), stays on PUSH until push time wherever you are (the marshal is close to it), and then moves on from point to point as you reach each one. In the F-14B(U) the jet does that stepping itself, in auto sequencing; where Jester waits (MSHL until your departure time, PUSH until push time, a station until your exit time, TGT on a strike, home base) he puts it in manual sequencing, so it does not step on early. On a station the F-14B(U) alternates between its two ends until your exit time; the F-14B holds the first end (its destination knob cannot reach the second). A station with no exit time stays until you change it. On a strike (a DEAD run included) he hands the nav back as he selects TGT; say Your Nav after your run and he starts at the point after TGT. Home base (RTB) ends his work: he goes direct to it, in the F-14B(U) in manual sequencing, and the nav is yours. Called on mid-flight, he picks the point you should be flying to by the clock and keeps up; Your Nav said while he already has it orders the current steerpoint again, so it also puts things right if the jet is not where he thinks. Every message starts with "RIO:". He also hands the nav back when you take it over: on the F-14B, turning the destination knob yourself or asking Jester for another one; on the F-14B(U), asking Jester for another waypoint, steering mode or sequencing, or pressing a TACAN or steering button (front or back), and he tells you if the jet would not take an order. When he takes the nav in the F-14B(U) he takes you out of Destination steering, so your HUD follows. When he hands it back the jet stays in whichever sequencing it was in. In the F-14B(U) a direct to the tanker or another point far down the list deletes everything in between, home base included. When the jet refuses a point he wants, he loads the mission's flight plan again on the CDNU, which brings every waypoint back with its number, and goes direct to it: about half a minute. He reads the CDNU screen before each key and stops if the page is not the one he expects; he tries once. Points you added to the plan yourself may be lost in the reload. What it sends and sees is logged in `Saved Games\DCS\Logs\SQE_rio_navigation.log`. On the F-14B only (the F-14B(U) has every point on Jester's own wheel), **F10 > Other > Turnpoints** lists the route's turnpoints as **Turnpoint 1**, **Turnpoint 2** and so on (TP1, TP2 on the kneeboard; the same words in every mission, so a voice command can be bound to them) and gives you the nav. Jester types its coordinates into the fix point (FP): he types slowly, so wait until the range stops changing and pick the next one early; any route point the jet's three waypoints and IP / ST cannot hold is typed into FP the same way, which leaves FP no longer free for a position fix. The Install button copies a small script to your `Saved Games\DCS\Scripts` and adds one line to `Export.lua` (backed up first); Remove undoes both. If you installed the Turnpoints script before, click Update. Install it before you generate the mission: without it the mission has neither menu. It works in single player and with the dedicated server on your own PC; it cannot work on another computer's server. With a human RIO there is no Jester to do it.

**Jammer Model** (Settings, off by default; it was called ECM Script before v0.41.655). With the option off, jammers work as DCS models them. With it on, SQE adds an effect of its own: a radar-guided missile fired at a jet that
has a jammer may be fooled: SQE rolls a chance and, when it comes up, removes the missile partway through its flight. The chance is 20% for a jet with an internal jammer, 45% for
a jet carrying an ECM pod and 30% for a jet without a pod flying within 2 nm of one that has it. The full chance applies to a missile launched from 40 km or more; it shrinks in a
straight line to nothing at 12 km, and inside 12 km the missile "burns through" and jamming does nothing. The same rule serves both sides, your own jet included. A jammer cannot
really destroy a missile: this is the closest a mission script can get to a missile that loses its target, and the numbers are SQE's own judgment, not measured figures. The idea
of scripted jamming in DCS missions is not SQE's: it goes back to the "Complete Electronic War" jamming script that ESAc_matador published on the Eagle Dynamics forum in 2016,
and the campaign tool DCS Retribution offers an electronic warfare script as a plugin. SQE uses no code from either; its script was written for SQE from a description of the
effect. For your own jet, SQE knows the jammer is on by reading the F-16C's ECM lamp or the A-10C II's countermeasure display (OPR) once the jammer script is installed (Settings > DCS Integration);
in an FC3 jet you call it from F10 > Other > SQE ECM Switch. Otherwise your jammer counts as on over the attack leg.

**Experimental: Fly on the local DCS dedicated server** (Settings > DCS Integration, off by default). The idea: the server runs the same mission with the AI at real time and without
a screen, so it may carry bigger missions than the game on its own, and you join it as a client at 127.0.0.1:10308 (no password). It needs the MissionScripting patch, the
`DCS_Server` profile folder (start the dedicated server once by hand so DCS creates it), a free port 10308 and real time only: no time acceleration. SQE keeps your own
`serverSettings.lua` in a backup, and puts it back when the server stops. With the option on, your flight lead gets a client slot (a mission built that way can be flown on a
server only, not in single player), and **Fly starts the server with the sortie**. The mission waits, paused, until you join: start DCS, Multiplayer, connect to
127.0.0.1:10308 and take the only client slot. The waiting window reads the results from the server; Accept or Abort stops the server. If the server cannot start, SQE says why
and the sortie stays built: fix the cause, Abort, and Fly again (or turn the option off). Still to be proven by a flown sortie: the radio calls and menus for a client, and the
debrief after a full flight.

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

SQE ships relief data and site lists for the Caucasus and for Syria (a Syria campaign needs the DCS Syria map), so no terrain scan is needed to play. `tools/sqe_scan.py` rebuilds them
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

* `docs/CAMPAIGN.md`: how the campaign works and what its rules are.
* `docs/CHANGES.md`: what changed in every version, newest first.
* `docs/THEATRES.md`: how a map pack is built.
* `tools/`: `smoke_test.py` (the self-test), `hook_lua_sim.py` (its Lua check), `sqe_scan.py` (the terrain scan) and `capture_loadouts.py` (the loadout capture). Crew Chief's other test and probe scripts are not in Git.
