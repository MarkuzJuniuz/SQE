# Squadron Campaign Engine (SQE)

Abstracted war in the background; each sortie, one fully generated DCS package (Caucasus) with a BMS-style
marshal/push/TOT timeline, proper briefing, kneeboard, and results fed back into the war.

Start here: **docs/GUIDE.md**   |   Sample briefing: docs/SAMPLE_BRIEFING.txt

    py -m venv .venv && .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python tools/smoke_test.py      # headless self-test
    python -m sqe                   # the app
