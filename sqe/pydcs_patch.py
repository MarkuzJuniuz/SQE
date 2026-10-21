"""A fix for a pydcs bug that can freeze a mission build (v0.41.66).

pydcs's `VehicleGroup.formation_scattered` places each vehicle at a random point in a ring round the first one and retries with `while True` until
the point is clear of the others. The ring's outer radius is random too (`randrange(15, units * 20)`, at least 15 m), and a vehicle blocks a 14 m square.
When the radius comes out small for the number of vehicles (a group of 12 with a radius under about 25 m), no clear point exists and the loop never ends:
the build hangs (found 2026-10-21 through the smoke test, which stalled about one run in three; measured: 4 of 300 groups of 12 vehicles never finish).

`install()` swaps in the same algorithm, drawing the same random numbers in the same order, with one addition: after every 100 failed tries for a vehicle
the ring is widened by 10 m. A group that pydcs places within 100 tries comes out exactly as before; one that would have hung now finishes.
"""
from __future__ import annotations

import copy
import random

from dcs import mapping
from dcs.unitgroup import VehicleGroup

ORIGINAL = VehicleGroup.formation_scattered       # pydcs's own, kept for the smoke test (same result wherever it finishes)
TRIES_BEFORE_WIDENING = 100
WIDEN_M = 10


def formation_scattered(self, heading=0, max_radius=None):
    unit_count = len(self.units)
    max_r = max_radius if max_radius else random.randrange(15, unit_count * 20)
    max_r = 15 if max_r < 15 else max_r
    start_pos = self.units[0].position

    for i in range(1, unit_count):
        tries = 0
        while True:
            tries += 1
            if tries % TRIES_BEFORE_WIDENING == 0:
                max_r += WIDEN_M                    # (pydcs has no such line: its loop never ends when the ring is too small)
            pos = start_pos.point_from_heading(random.randrange(0, 360), random.randrange(14, max_r))
            if not any(mapping.Rectangle.from_point(self.units[j].position, 14).point_in_rect(pos) for j in range(0, i)):
                u = self.units[i]
                u.position = copy.copy(pos)
                u.heading = heading
                break


def install() -> None:
    VehicleGroup.formation_scattered = formation_scattered
