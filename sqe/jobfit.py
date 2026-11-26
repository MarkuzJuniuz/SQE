"""What this turn can crew, for the planner (`war.ObjectivePlanner.plan`).

A stand-off job needs jets that carry its weapon: SLAM-ER Hornets, JSOW Vipers and Hornets, or (for an early-warning radar) one of the `EWR_KIT_ORDER` kits.
The planner used to name such a job whenever ANY such squadron had two jets, so one squadron got several jobs and the builder dropped all but one.
`TurnFit` counts the free pairs and takes them away as jobs are named: a job whose kit has no pair left is passed over and the slot goes to the next candidate.

The planner also used to name targets no squadron could get to: its own gate is the SAM belt in front of a target, the builder's is the length of
the route round the rings (`PackageBuilder._in_range`). With a `builder`, `TurnFit` asks the builder's own test, so both agree.

It is an estimate, not a booking: the builder still decides who flies. A fit object is made for one planner call and thrown away.
"""
from __future__ import annotations

from . import threat
from .aircraft import AIRCRAFT, STRIKE_CONDITIONAL
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


def reach_kit(aircraft: str, kit: str) -> str:
    """The kit name the builder measures reach with: the radar kits differ by airframe (the F-15E's heavy one reaches less far)."""
    if kit != EWR_KIT:
        return kit
    for entry in EWR_KIT_ORDER:
        if entry[0] == aircraft:
            return entry[1]
    return ""


class TurnFit:
    def __init__(self, state, ledger, builder=None):
        """`ledger`: the turn's jets after the reaction reserve and the standing patrols came off (`packages.Ledger`). `builder`: the turn's
        `PackageBuilder`, for the reach test (None: reach is not tested)."""
        self.state = state
        self.ledger = ledger
        self.builder = builder
        self.reach_cache = {}
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

    def main_role(self, objective):
        """The role of the flight that has to get there, None for a job that is not tested (fleet patrols and intercepts)."""
        if objective.type == ObjectiveType.CAS:
            return Role.CAS
        if objective.type == ObjectiveType.STRIKE:
            return Role.STRIKE
        if objective.type == ObjectiveType.DEAD:
            if self.kit_of(objective) or objective.aim == "DEAD":
                return Role.STRIKE
            return Role.SEAD
        return None

    def reaches(self, squadron_id: str, objective, kit: str) -> bool:
        """The builder's own reach test for one squadron and one job."""
        if self.builder is None:
            return True
        asset = self.state.assets.get(objective.target_id)
        if asset is None:
            return True
        key = (squadron_id, objective.type, objective.target_id, objective.aim, kit)
        if key not in self.reach_cache:
            aircraft = self.state.squadrons[squadron_id].aircraft
            # `_in_range` reads the job it is working on from here (the stand-off launch distance and the SAM belt rule depend on it).
            self.builder._ctx = (objective, asset)
            self.reach_cache[key] = self.builder._in_range(squadron_id, asset.x, asset.y, reach_kit(aircraft, kit))
        return self.reach_cache[key]

    def anyone_reaches(self, objective) -> bool:
        """A job without a kit: is there a squadron of the right role, with a pair free, that can get there?"""
        role = self.main_role(objective)
        if self.builder is None or role is None:
            return True
        for squadron_id, squadron in self.state.squadrons.items():
            if squadron.aircraft == "F-117A" or role not in AIRCRAFT[squadron.aircraft].roles:
                continue
            if self.ledger.room(squadron_id, NWAVES) < 2:
                continue
            if role == Role.STRIKE and squadron.aircraft in STRIKE_CONDITIONAL and not self.clean_supply_strike(objective):
                continue                                   # the A-10C strikes only a supply site nothing defends
            if self.reaches(squadron_id, objective, ""):
                return True
        return False

    def clean_supply_strike(self, objective) -> bool:
        """Is this a job an A-10C may take a strike slot on (`PackageBuilder._a10_supply_strike`)?"""
        asset = self.state.assets.get(objective.target_id)
        if asset is None:
            return False
        iads = 0.5
        if self.builder.d is not None:
            iads = self.builder.d.iads
        defenders = threat.defender_flights(threat.expected_defenders(self.state, asset.x, asset.y, iads))
        return self.builder._a10_supply_strike(objective, defenders)

    def squadrons_for(self, objective, kit: str) -> list:
        """The squadrons with a pair left that can fly this kit and reach this job."""
        found = []
        for squadron_id in self.squadrons_with(kit):
            if self.reaches(squadron_id, objective, kit):
                found.append(squadron_id)
        return found

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
            return self.anyone_reaches(objective)
        free = 0
        for squadron_id in self.squadrons_for(objective, kit):
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
        for squadron_id in self.squadrons_for(objective, kit):
            used = min(wanted, self.pairs[squadron_id])
            self.pairs[squadron_id] -= used
            wanted -= used
            if wanted <= 0:
                return
