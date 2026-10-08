# Squadron Campaign Engine (SQE)

Abstracted war in the background; each sortie, one fully generated DCS package (Caucasus) with a BMS-style
marshal/push/TOT timeline, proper briefing, kneeboard, and results fed back into the war.

## Download

1. Get **`SQE_vX.Y.Z.zip`** from the [latest release](https://github.com/MarkuzJuniuz/SQE/releases/latest).
2. Extract the whole `SQE` folder anywhere (not inside DCS's own folders) and run **`SQE.exe`**. Keep the folder together; the .exe needs the files beside it.
3. Windows may show **"Windows protected your PC"** because SQE isn't code-signed. Click **More info → Run anyway**.
4. On first run, set the two folders in Settings (your DCS install and `Saved Games\DCS`) and answer the scripting-access question (see Legal below).

Needs Windows and DCS World with the Caucasus map. To update, extract the new zip over the old folder; campaigns are kept in `Saved Games\DCS\SQE`.

## Running from source

Start here: **docs/GUIDE.md**   |   Sample briefing: docs/SAMPLE_BRIEFING.txt

    py -m venv .venv && .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python tools/smoke_test.py      # headless self-test
    python -m sqe                   # the app


## Legal

* SQE is released under the **MIT licence** (`LICENSE`, copyright MarkuzJuniuz). It is **free of charge and non-commercial**, as DCS World's EULA requires of anything built on it. Debrief results need DCS's `MissionScripting.lua` opened up; SQE asks you on first run and does this **only if you agree** (default off, change it in Settings).
* It is **not made or supported by Eagle Dynamics SA**. It contains no DCS files; see `THIRD_PARTY_NOTICES.md` for the libraries it uses and their licences.
* **What the MissionScripting.lua option does**: DCS blocks `io` and `lfs` in mission scripts, which SQE needs to read your sortie results. With the setting on, SQE comments out
  those sanitizing lines in your own `MissionScripting.lua` when it starts (a backup is saved beside it) and restores the file when it closes. It changes nothing else. DCS updates and repairs can
  overwrite the file, which is why SQE re-applies the change at every start. If you play multiplayer, close SQE first so the file is unmodified.
* Use at your own risk; there is no warranty.

## Inspiration

Many of SQE's ideas are inspired by community campaign tools, especially DCS Liberation and DCS Retribution (a front line that moves as targets fall, packages with escorts and SEAD,
the MissionScripting approach for results, AI fuel management), and by the feel of Falcon BMS and the Strike Fighters series. SQE contains no code from them and is not affiliated with them.
