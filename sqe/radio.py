"""Radio plan: your fixed preset layout, filled with unique frequencies per mission.

    COMM1 (radio 1, UHF):  CH1 ATC | CH2 AWACS | CH3 TANKER | CH4 JTAC (if any) | CH5 2nd tanker (if any)
    COMM2 (radio 2, VHF):  CH1 FLIGHT

Why it is built this way
- COMM1 entities are all UHF 225-399.975 so the F-14B(U) ARC-159 and the F-16C UHF radio can both tune them.
- The flight frequency is VHF so DCS (which puts a group's frequency on the first radio able to tune it)
  puts it on COMM2 and never overwrites a COMM1 preset.
- Only the player's own jet gets presets; AI aircraft ignore them.
"""
from __future__ import annotations
import random
from dataclasses import dataclass, field
from dataclasses import dataclass as _dc
from .aircraft import AIRCRAFT
from .models import BaseKind


@dataclass
@_dc
class RadioLayout:
    """Your fixed preset layout. CH4 (JTAC) and CH5 (second tanker) appear only when the mission has them."""
    comm1: dict = field(default_factory=lambda: {1: "ATC", 2: "AWACS", 3: "TANKER1", 4: "JTAC", 5: "TANKER2"})
    comm2: dict = field(default_factory=lambda: {1: "FLIGHT"})
    optional: frozenset = frozenset({"JTAC", "TANKER2"})
    comm1_radio_id: int = 1
    comm2_radio_id: int = 2


@_dc
class RadioCfg:
    carrier_tacan: str = "74X"
    carrier_link4_mhz: int = 336


@dataclass
class RadioEntry:
    label: str          # "ATC", "AWACS", "TANKER1", ...
    mhz: float
    callsign: str = ""  # e.g. "Texaco 1-1"
    note: str = ""      # e.g. "TACAN 51X"


@dataclass
class RadioPlan:
    comm1: dict[int, RadioEntry] = field(default_factory=dict)
    comm2: dict[int, RadioEntry] = field(default_factory=dict)
    tacan: dict[str, str] = field(default_factory=dict)       # label -> "51X"
    package_flights: list[RadioEntry] = field(default_factory=list)  # info only (kneeboard)

    def freq(self, label: str) -> float:
        for tbl in (self.comm1, self.comm2):
            for e in tbl.values():
                if e.label == label:
                    return e.mhz
        raise KeyError(label)


class FrequencyAllocator:
    """Unique, tidy (0.5 MHz grid) frequencies. Deterministic for a given rng."""
    UHF = (225.0, 399.5)

    def __init__(self, rng: random.Random):
        self.rng = rng
        self.used: set[float] = set()

    def reserve(self, mhz: float) -> None:
        self.used.add(round(mhz, 3))

    def pick(self, lo: float, hi: float, step: float = 0.5) -> float:
        n = int(round((hi - lo) / step))
        for _ in range(500):
            f = round(lo + self.rng.randint(0, n) * step, 3)
            if f not in self.used and not any(abs(f - u) < 1.0 for u in self.used):
                self.used.add(f)
                return f
        raise RuntimeError("frequency pool exhausted")


def build_radio_plan(package, state, atc_mhz: float, rng: random.Random,
                     layout: RadioLayout, mcfg: RadioCfg) -> RadioPlan:
    alloc = FrequencyAllocator(rng)
    alloc.reserve(atc_mhz)
    alloc.reserve(mcfg.carrier_link4_mhz)
    plan = RadioPlan()
    plan.comm1[1] = RadioEntry(layout.comm1[1], atc_mhz, note="Tower / carrier control")

    sup = {s.slot: s for s in package.support}
    tacans_used = {mcfg.carrier_tacan}
    for ch, label in layout.comm1.items():
        if ch == 1:
            continue
        if label in layout.optional and not (package.jtac if label == "JTAC" else label in sup):
            continue
        f = alloc.pick(*FrequencyAllocator.UHF)
        s = sup.get(label)
        callsign = f"{s.label} {package.number}-1" if s else ""
        note = ""
        if label.startswith("TANKER") and s:
            tac = _free_tacan(tacans_used, rng)
            plan.tacan[label] = tac
            note = f"TACAN {tac} {s.refuel.title() if s.refuel else ''}".strip()
        if label == "AWACS" and s:
            note = "Picture / bogey dope"
        if label == "JTAC":
            callsign = f"Axeman {package.number}-1"
            note = f"Laser {package.jtac_laser_code}"
            plan.tacan.pop("JTAC", None)
        plan.comm1[ch] = RadioEntry(label, f, callsign, note)

    player = package.player_flight
    spec = AIRCRAFT[player.aircraft]
    flt = alloc.pick(*spec.comm2_band_mhz, step=0.5)
    plan.comm2[1] = RadioEntry(layout.comm2[1], flt, player.callsign, "Intra-flight")
    for f in package.flights:
        if f is player:
            continue
        plan.package_flights.append(RadioEntry("PKG", alloc.pick(*spec.comm2_band_mhz, step=0.5),
                                               f.callsign, f"{f.count}x {f.aircraft} {f.role.value}"))
    return plan


def _free_tacan(used: set, rng: random.Random) -> str:
    for _ in range(100):
        t = f"{rng.randint(30, 99)}X"
        if t not in used:
            used.add(t)
            return t
    raise RuntimeError("no free TACAN")


def apply_player_presets(unit, plan, layout) -> bool:
    """Write COMM1 presets onto one human aircraft. COMM2 CH1 is set via group.set_frequency().
    Returns False when pydcs has no preset table for the jet (e.g. F-15C): set those by hand from the kneeboard."""
    try:
        if unit.radio is None:
            unit.set_radio_preset()
        for ch, e in plan.comm1.items():
            unit.set_radio_channel_preset(layout.comm1_radio_id, ch, e.mhz)
        return True
    except Exception:
        return False
