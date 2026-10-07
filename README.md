# Squadron Campaign Engine (SQE)

Abstracted war in the background; each sortie, one fully generated DCS package (Caucasus) with a BMS-style
marshal/push/TOT timeline, proper briefing, kneeboard, and results fed back into the war.

Start here: **docs/GUIDE.md**   |   Sample briefing: docs/SAMPLE_BRIEFING.txt

    py -m venv .venv && .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python tools/smoke_test.py      # headless self-test
    python -m sqe                   # the app


## Legal

* SQE is free software released under the licence in `LICENSE`. It is **free of charge and non-commercial**, as DCS World's EULA requires of anything built on it.
* It is **not made or supported by Eagle Dynamics SA**. It contains no DCS files; see `THIRD_PARTY_NOTICES.md` for the libraries it uses and their licences.
* **What the MissionScripting.lua option does**: DCS blocks `io` and `lfs` in mission scripts, which SQE needs to read your sortie results. With the setting on, SQE comments out
  those sanitizing lines in your own `MissionScripting.lua` when it starts (a backup is saved beside it) and restores the file when it closes. It changes nothing else. DCS updates and repairs can
  overwrite the file, which is why SQE re-applies the change at every start. If you play multiplayer, close SQE first so the file is unmodified.
* Use at your own risk; there is no warranty.
