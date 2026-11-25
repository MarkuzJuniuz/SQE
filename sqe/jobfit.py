"""What this turn can crew, for the planner (`war.ObjectivePlanner.plan`).

A stand-off job needs jets that carry its weapon: SLAM-ER Hornets, JSOW Vipers and Hornets, or (for an early-warning radar) one of the `EWR_KIT_ORDER` kits.
The planner used to name such a job whenever ANY such squadron had two jets, so one squadron got several jobs and the builder dropped all but one.
`TurnFit` counts the free pairs and takes them away as jobs are named: a job whose kit has no pair left is passed over and the slot goes to the next candidate.

It is an estimate, not a booking: the builder still decides who flies. A fit object is made for one planner call and thrown away.
"""
from __future__ import annotations

from .aircraft import AIRCRAFT
from .loadouts import EWR_KIT_ORDER
from .models import AssetKind, ObjectiveType, Role
from .packages import KIT_JETS, SALVO_4_NEIGHBOURS, SALVO_8_NEIGHBOURS, PackageBuilder
from .timeofday import NWAVES
from .war import long_range_site

# A stand-off strike slot is four jets. With one pair left the package still goes, two jets short.
PAIRS_PER_KIT_JOB = 2
# The name for "any of the early-warning-radar kits" (`EWR_KIT_ORDER`).
EWR_KIT = "EWR"


def kit_count(aircraft: str) -> int:
    """How many different kits this airframe can carry. An airframe with fewer is drawn from first, to keep the versatile ones free."""
    count = 0
    for jets in KIT_JETS.values():
        if aircraft in jets:
            count += 1
    return count


def carriers(kit: str) -> list:
    """The airframes that can fly a job of this kit, the least versatile first."""
    if kit == EWR_KIT:
        aircraft = []
        for entry in EWR_KIT_ORDER:
            aircraft.append(entry[0])
    else:
        aircraft = list(KIT_JETS[kit])
    aircraft.sort(key=kit_count)
    return aircraft


class TurnFit:
    def __init__(self, state, ledger):
        """`ledger`: the turn's jets after the reaction reserve and the standing patrols came off (`packages.Ledger`)."""
        self.state = state
        self.pairs = {}
        for squadron_id, squadron in state.squadrons.items():
            if Role.STRIKE in AIRCRAFT[squadron.aircraft].roles:
                self.pairs[squadron_id] = ledger.room(squadron_id, NWAVES) // 2

    def kit_of(self, objective) -> str:
        """The kit this job needs, "" for a job any strike pair can try."""
        if objective.type == ObjectiveType.DEAD:
            if objective.aim == "STANDOFF":
                return "JSOW"
            # A plain DEAD job on a long-range site becomes a Standoff DEAD (`ObjectivePlanner._stage_dead`).
            if not objective.aim and long_range_site(self.state, self.state.assets[objective.target_id]):
                return "JSOW"
            return ""
        if objective.type == ObjectiveType.STRIKE and objective.aim == "STANDOFF":
            asset = self.state.assets.get(objective.target_id)
            if asset is not None and asset.kind == AssetKind.EWR:
                return EWR_KIT
            return "SLAM"
        return ""

    def squadrons_with(self, kit: str) -> list:
        """The squadrons that can fly this kit and still have a pair, the least versatile airframe first."""
        found = []
        for aircraft in carriers(kit):
            for squadron_id, pairs in self.pairs.items():
                if pairs > 0 and self.state.squadrons[squadron_id].aircraft == aircraft:
                    found.append(squadron_id)
        return found

    def harm_pairs(self, objective) -> tuple:
        """The pairs of the two HARM flights of a Standoff DEAD, sized as `PackageBuilder._slots` sizes them. They are flown by the same Vipers
        and Hornets that carry the JSOW, and the first one is picked before the JSOW flight."""
        neighbours = PackageBuilder(self.state)._cluster_sites(objective)
        first = 1
        if neighbours >= SALVO_4_NEIGHBOURS:
            first = 2
        second = 1
        if neighbours >= SALVO_8_NEIGHBOURS:
            second = 2
        return first, second

    def fits(self, objective) -> bool:
        """Can this job still be crewed, counting the jobs already named?"""
        kit = self.kit_of(objective)
        if not kit:
            return True
        free = 0
        for squadron_id in self.squadrons_with(kit):
            free += self.pairs[squadron_id]
        needed = 1
        if kit == "JSOW":
            first_harm, _second_harm = self.harm_pairs(objective)
            needed += first_harm
        return free >= needed

    def spend(self, objective) -> None:
        """The job was named: take its pairs off the count."""
        kit = self.kit_of(objective)
        if not kit:
            return
        wanted = PAIRS_PER_KIT_JOB
        if kit == "JSOW":
            first_harm, second_harm = self.harm_pairs(objective)
            wanted += first_harm + second_harm
        for squadron_id in self.squadrons_with(kit):
            used = min(wanted, self.pairs[squadron_id])
            self.pairs[squadron_id] -= used
            wanted -= used
            if wanted <= 0:
                return
