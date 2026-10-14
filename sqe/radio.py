"""Radio plan: your fixed preset layout, filled with unique frequencies per mission.

    COMM1 (radio 1, UHF):  CH1 AWACS | CH2 TANKER | CH3 JTAC (if any) | CH4 2nd tanker (if any) | CH5 DIVERT
    COMM2 (radio 2, VHF):  CH1 FLIGHT | CH2 TOWER (VHF tower for Air Force jets at an airfield; UHF otherwise: Navy COMM2 tunes both)

Why it is built this way
- COMM1 entities are all UHF 225-399.975 so the F-14B(U) ARC-159 and the F-16C UHF radio can both tune them.
- The flight frequency is VHF so DCS (which puts a group's frequency on the first radio able to tune it)
  puts it on COMM2 CH1 and never overwrites a COMM1 preset. That is also why the tower is COMM2 CH2, not CH1 (v0.40.5).
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
    """Your fixed preset layout. COMM1 CH3 (JTAC) and CH4 (second tanker) appear only when the mission has them."""
    comm1: dict = field(default_factory=lambda: {1: "AWACS", 2: "TANKER1", 3: "JTAC", 4: "TANKER2", 5: "DIVERT"})
    comm2: dict = field(default_factory=lambda: {1: "FLIGHT", 2: "ATC"})
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

    def where(self, label: str) -> str:
        """'COMM1 CH2' for a label, '' when the plan has no such entry."""
        for n, tbl in (("COMM1", self.comm1), ("COMM2", self.comm2)):
            for ch, e in tbl.items():
                if e.label == label:
                    return f"{n} CH{ch}"
        return ""

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
        for k in range(n + 1):           # v0.41.9: a busy band (support CAP from folded packages): any free channel on the grid, 0.5 MHz apart
            f = round(lo + k * step, 3)
            if f not in self.used:
                self.used.add(f)
                return f
        raise RuntimeError("frequency pool exhausted")


def build_radio_plan(package, state, atc_mhz: float, rng: random.Random,
                     layout: RadioLayout, mcfg: RadioCfg, divert_mhz: float | None = None, divert_name: str = "", atc_vhf_mhz: float | None = None) -> RadioPlan:
    alloc = FrequencyAllocator(rng)
    alloc.reserve(atc_mhz)
    if divert_mhz:
        alloc.reserve(divert_mhz)
    alloc.reserve(mcfg.carrier_link4_mhz)
    plan = RadioPlan()

    sup = {s.slot: s for s in package.support}
    tacans_used = {mcfg.carrier_tacan}
    for ch, label in layout.comm1.items():
        if label == "DIVERT":
            if divert_mhz:
                plan.comm1[ch] = RadioEntry("DIVERT", divert_mhz, divert_name[:14], "Divert tower")
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
    for ch, label in layout.comm2.items():
        if label == "FLIGHT":
            plan.comm2[ch] = RadioEntry(label, flt, player.callsign, "Intra-flight")
        elif label == "ATC":         # an Air Force jet's COMM2 is VHF only: the field's VHF tower. Navy COMM2 tunes UHF too (and the carrier is UHF)
            vhf = atc_vhf_mhz if (atc_vhf_mhz and spec.service != "Navy") else None
            cv = state.bases[player.base_id].kind == BaseKind.CARRIER
            plan.comm2[ch] = RadioEntry(label, vhf or atc_mhz, note="Carrier control" if cv else "Tower")
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
    """Write COMM1 and COMM2 presets onto one human aircraft (COMM2 CH1, the flight, is also set by group.set_frequency(); DCS writes the
    group frequency there whatever the preset says). Returns False when pydcs has no preset table for the jet (e.g. F-15C): set those by
    hand from the kneeboard."""
    try:
        if unit.radio is None:
            unit.set_radio_preset()
        for ch, e in plan.comm1.items():
            unit.set_radio_channel_preset(layout.comm1_radio_id, ch, e.mhz)
        for ch, e in plan.comm2.items():
            try:
                unit.set_radio_channel_preset(layout.comm2_radio_id, ch, e.mhz)
            except Exception:
                pass                                                  # a COMM2 without presets: the kneeboard has the frequency
        return True
    except Exception:
        return False
