# Third-party notices

SQE itself is MIT licensed (see `LICENSE`, copyright MarkuzJuniuz).

SQE is not affiliated with, endorsed by, or supported by Eagle Dynamics SA. "DCS World" and "Digital Combat Simulator" belong to
their owners and are used here only to say what SQE works with. THIS MATERIAL IS NOT MADE OR SUPPORTED BY EAGLE DYNAMICS SA.

SQE does not contain, copy or redistribute any DCS World file, texture, model, sound or script. It writes new mission files
(.miz) that reference DCS's own content by name, and (only while it is running, only if you said yes on first run or switched it on in Settings; it is off by default) comments
out the `io` / `lfs` sanitizing lines of your own local `MissionScripting.lua`, then restores it when SQE closes.

SQE is not affiliated with DCS Liberation, DCS Retribution, DCC (Digital Crew Chief), Falcon BMS or Strike Fighters.
Many of its ideas take inspiration from them (see the README), but it contains none of their code. Their names appear only to credit that inspiration.

Unit names in the sample squadrons (for example VF-31, 77th FS) are real unit designations used as flavour. No insignia or
artwork is included, and no endorsement by any air force or navy is implied. Pilots, call signs and events are fictional.

## Libraries SQE uses (installed by pip, not copied into this repository)

| Component | Licence | Notes |
|---|---|---|
| pydcs (the dcs-retribution fork, pinned in requirements.txt) | LGPL-3.0 | https://github.com/dcs-retribution/pydcs . Used as an unmodified, separately installed package. In the Windows build it is bundled as a normal folder of files (not a single packed exe), so you can replace it. |
| PySide6 / Qt for Python | LGPL-3.0 (also GPL and commercial) | https://doc.qt.io/qtforpython-6/ . Dynamically linked; replaceable in the Windows build folder. |
| Pillow | HPND (MIT-CMU style) | https://python-pillow.org |
| PyInstaller (build time only) | GPL-2.0 with the bootloader exception | The executables it builds may be shipped under any licence. |
| lupa (tests only) | MIT | Used only by tools/smoke_test.py to check the embedded Lua compiles. |

## Data

* Coastlines, lakes and borders on the map (sqe/geo_data.py): Natural Earth, public domain, https://www.naturalearthdata.com .
  Borders are shown as the data provides them and make no political statement.
* Weapon and vehicle identifiers come from pydcs's own tables.
