"""AWACS tuning probe (XO 2026-10-22): can a mission tell that the player's radio is tuned to the AWACS?

Builds one tiny Caucasus mission per jet (a single Player slot at Kutaisi, cold and dark; an E-3A orbiting on 251.0 MHz AM). The mission holds
Mission Editor "cockpit parameter" triggers for a list of CANDIDATE parameter names (we do not know the real names per module):
  * "PROBE <name> EXISTS"        - the parameter has any value (so the name is real for this jet),
  * "PROBE <name> TUNED MHz/kHz/Hz" - its value is within 0.1 of 251.0 MHz in that unit (so we learn the unit as well).
Each fires once as an on-screen message AND a line in dcs.log (`SQEPROBE ...`). Also a looping radio transmission on 251.0 MHz AM with a subtitle, to
see whether the subtitle shows only when tuned.

How XO runs it: fly the jet for a minute, switch the radio to 251.0 (AM), then away and back; send dcs.log (grep SQEPROBE) or a screenshot of the messages.
Usage:  python tools/awacs_probe.py OUT_DIR            (all jets)     python tools/awacs_probe.py OUT_DIR f16 fa18
Public source for the idea: the ME conditions "Cockpit Parameter is in range / equal to" (pydcs `CockpitParamInRange`). Nothing here is verified in DCS yet."""
from __future__ import annotations

import datetime
import struct
import sys
import wave
from pathlib import Path

from dcs import action, condition, mapping, planes, task, triggers
from dcs.mission import Mission, StartType
from dcs.terrain import caucasus
from dcs.translation import String
from dcs.unit import Skill

FREQ_MHZ = 251.0
JETS = {"f16": ("F-16C", planes.F_16C_50), "fa18": ("FA-18C", planes.FA_18C_hornet), "f14": ("F-14B", planes.F_14B),
        "a10": ("A-10C", planes.A_10C_2), "f15": ("F-15C", planes.F_15C)}
CANDIDATES = [
    "UHF_FREQ", "UHF_RADIO_FREQ", "UHF_FREQUENCY", "UHF_RADIO_FREQUENCY", "ARC164_FREQ", "ARC_164_FREQ", "AN_ARC_164_FREQ", "UHF_ARC164_FREQ",
    "COMM1_FREQ", "COMM2_FREQ", "COMM_1_FREQ", "COMM_2_FREQ", "COMM1", "COMM2", "COMM1_FREQ_MHZ", "VHF_AM_FREQ", "VHF_FM_FREQ", "VHF_FREQ",
    "VHF_RADIO_FREQ", "ARC186_FREQ", "ARC_186_FREQ", "ARC210_FREQ", "ARC_210_FREQ", "ARC_210_1_FREQ", "ARC_210_2_FREQ", "ARC182_FREQ", "ARC_182_FREQ",
    "ARC159_FREQ", "ARC_159_FREQ", "RADIO1_FREQ", "RADIO2_FREQ", "RADIO_FREQ", "CNI_UHF_FREQ", "UFC_UHF_FREQ", "UFC_COMM1_FREQ", "FREQ_UHF"]
SCALES = {"MHz": 1.0, "kHz": 1e3, "Hz": 1e6}


def _wav(path: Path) -> None:
    rate = 22050
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * __import__("math").sin(2 * 3.14159 * 800 * i / rate))) for i in range(int(rate * 0.4))))


def build(key: str, out_dir: Path) -> Path:
    label, cls = JETS[key]
    out_dir.mkdir(parents=True, exist_ok=True)
    m = Mission(caucasus.Caucasus())
    m.start_time = datetime.datetime(2006, 6, 12, 9, 0)
    blue = m.country("USA")
    ap = m.terrain.airports["Kutaisi"]
    g = m.flight_group_from_airport(blue, f"Probe {label}", cls, ap, maintask=task.CAP, start_type=StartType.Cold, group_size=1)
    g.units[0].skill = Skill.Player
    g.units[0].name = f"Probe {label} 1-1"
    aw = m.flight_group(blue, "Probe AWACS", planes.E_3A, None, mapping.Point(ap.position.x + 40000, ap.position.y + 20000, m.terrain), altitude=9000, speed=220, maintask=task.AWACS)
    aw.set_frequency(FREQ_MHZ)
    aw.add_waypoint(mapping.Point(ap.position.x + 90000, ap.position.y + 20000, m.terrain), 9000, 220)
    # candidate parameter triggers
    def say(text, cond):
        t = triggers.TriggerOnce(comment=text)
        t.add_condition(cond)
        t.add_action(action.MessageToAll(String(text), 20))
        t.add_action(action.DoScript(String(f'env.info("SQEPROBE {text}")')))
        m.triggerrules.triggers.append(t)
    for name in CANDIDATES:
        say(f"PROBE {name} EXISTS", condition.CockpitParamInRange(name, "0.000001", "1000000000000"))
        for unit, mul in SCALES.items():
            say(f"PROBE {name} TUNED {unit}", condition.CockpitParamInRange(name, f"{(FREQ_MHZ - 0.1) * mul:.1f}", f"{(FREQ_MHZ + 0.1) * mul:.1f}"))
    # a looping radio transmission with a subtitle: does the text show only to a pilot tuned to 251.0 AM?
    wav = out_dir / "sqe_probe.wav"
    _wav(wav)
    key_ = m.map_resource.add_resource_file(str(wav))
    rt = action.RadioTransmission(file=key_, frequency=int(FREQ_MHZ * 1000), modulation=False, loop=True, power=1000, name="sqeprobe")
    orig = rt.dict
    def with_subtitle():
        d = orig(); d["subtitle"] = "SQEPROBE AWACS: you are tuned to 251.0 AM"; d["subtitleDuration"] = 10; return d
    rt.dict = with_subtitle
    t = triggers.TriggerOnce(comment="PROBE radio transmission")
    t.add_condition(condition.TimeAfter(20))
    t.add_action(rt)
    t.add_action(action.MessageToAll(String("PROBE: radio transmission started on 251.0 AM (subtitle test)"), 15))
    m.triggerrules.triggers.append(t)
    m.set_description_text(f"AWACS tuning probe, {label}. Start up, tune 251.0 (AM), then away and back. Messages named PROBE <param> EXISTS / TUNED <unit> tell which cockpit parameter reports your radio.")
    path = out_dir / f"AWACS_Probe_{label}.miz"
    m.save(str(path))
    return path


def main(argv) -> int:
    if not argv:
        print(__doc__); return 2
    out = Path(argv[0])
    keys = argv[1:] or list(JETS)
    for k in keys:
        print(build(k, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
