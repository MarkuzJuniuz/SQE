"""Difficulty presets. Each is a plain dataclass; edit the numbers to taste.

Level 1  insurgent-grade enemy: a few old aircraft, AAA/MANPADS, a handful of old SAMs.
Level 2  regional power: sizeable mixed air force, layered SAMs, partial integration.
Level 3  near-peer: modern fighters, long-range SAMs, a fully integrated air-defence network.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Difficulty:
    level: int
    name: str
    blurb: str
    enemy_air_total: int                 # aircraft spread across enemy air wings
    enemy_types: list
    sam_variants: list                   # one site per entry per defended cluster (cycled)
    sam_sites_per_cluster: int
    iads: float                          # 0..1: how well the enemy network shares data (hurts you in the odds)
    enemy_skill: str                     # DCS AI skill name
    loss_rate: float                     # fraction of a flight lost at even odds (AI-resolved packages)
    base_damage: float                   # asset health removed by a fully successful strike
    variance: float                      # 0 = expected values only, 1 = full dice
    friendly_replenish: float            # fraction of authorized airframes restored per day
    enemy_replenish: float
    asset_repair: float
    sam_repair: float
    friendly_scale: float                # scales squadron sizes
    enemy_cap_per_air: float             # enemy CAP flights ~ this * airframes (1..4)
    armor_columns: int = 3
    bomber_wing: int = 0                 # strategic bombers (Tu-22M3) at Mozdok
    bomber_policy: str = "none"          # none | desperate (only when losing badly) | normal
    counterstrike: float = 0.3           # daily chance (x enemy air strength) that the enemy hits a coalition base's defences
    forward_sams: tuple = ()             # short-range SAMs that travel with the front-line columns (one per entry)
    garrison_chance: float = 0.0         # chance that a long-range SAM site has a dug-in ground garrison
    garrison_size: float = 1.0           # scales the garrison's vehicle count
    react_chance: float = 0.0            # chance per sortie that other wings send reinforcements (see reactive.py)
    react_ratio: tuple = (1.0, 1.0)      # total enemy fighters vs your fighters in the mission, drawn between these
    ground_red: tuple = (70, 55, 15, 0, 0)    # ground war (ground.py): Red strength per sector at the start of the campaign (0-100)
    ground_blue: tuple = (0, 15, 60, 70, 50)  # Blue strength per sector at the start
    red_attack: float = 0.30             # daily chance that Red attacks a contested sector it is not clearly losing (x its strength ratio)
    red_reinf: float = 5.0               # strength points Red adds a day at the zone in contact (x supply)
    blue_reinf: float = 5.0              # the same for Blue

LEVELS: dict[int, Difficulty] = {
    1: Difficulty(1, "Level 1 - Insurgent", "Irregular forces. A few old aircraft, AAA and MANPADS, scattered older SAMs. "
                  "Expect to be shot at, not hunted.",
                  enemy_air_total=20, enemy_types=["MiG_21Bis", "Su_25", "MiG_23MLD"],
                  sam_variants=["AAA", "MANPAD", "SA-3"], sam_sites_per_cluster=1, iads=0.15,
                  enemy_skill="Average", loss_rate=0.035, base_damage=0.45, variance=0.8,
                  friendly_replenish=0.14, enemy_replenish=0.03, asset_repair=0.03, sam_repair=0.03,
                  friendly_scale=1.2, enemy_cap_per_air=0.10, counterstrike=0.10, bomber_wing=0, bomber_policy="none", react_chance=0.08, react_ratio=(0.2, 0.5),
                  ground_red=(55, 35, 8, 0, 0), ground_blue=(0, 20, 55, 70, 50), red_attack=0.15, red_reinf=3.5, blue_reinf=6.0),
    2: Difficulty(2, "Level 2 - Regional Power", "A real air force and layered SAMs, but not a peer. "
                  "A competent campaign wins; a careless one bleeds.",
                  enemy_air_total=90, enemy_types=["MiG_29A", "MiG_29S", "MiG_23MLD", "Su_24M", "Su_25"],
                  sam_variants=["SA-2", "SA-3", "SA-6", "SA-11", "AAA"], sam_sites_per_cluster=3, iads=0.55,
                  enemy_skill="Good", loss_rate=0.06, base_damage=0.35, variance=0.8,
                  friendly_replenish=0.08, enemy_replenish=0.05, asset_repair=0.04, sam_repair=0.06,
                  friendly_scale=1.0, enemy_cap_per_air=0.15, counterstrike=0.30, bomber_wing=4, bomber_policy="desperate",
                  forward_sams=("SA-8", "SA-8"), garrison_chance=0.6, garrison_size=0.8, react_chance=0.35, react_ratio=(0.6, 1.1),
                  ground_red=(70, 55, 15, 0, 0), ground_blue=(0, 15, 60, 70, 50), red_attack=0.45, red_reinf=7.5, blue_reinf=4.0),
    3: Difficulty(3, "Level 3 - Near-Peer", "Modern fighters, long-range SAMs and an integrated air-defence network. "
                  "Every sortie is contested and attrition bites.",
                  enemy_air_total=150, enemy_types=["MiG_29S", "Su_27", "Su_24M", "Su_25", "MiG_29A"],
                  sam_variants=["SA-10", "SA-11", "SA-6", "SA-15", "SA-19"], sam_sites_per_cluster=4, iads=0.9,
                  enemy_skill="High", loss_rate=0.085, base_damage=0.28, variance=0.7,
                  friendly_replenish=0.06, enemy_replenish=0.07, asset_repair=0.05, sam_repair=0.08,
                  friendly_scale=0.85, enemy_cap_per_air=0.20, counterstrike=0.55, bomber_wing=10, bomber_policy="normal",
                  forward_sams=("SA-15", "SA-8", "SA-19"), garrison_chance=1.0, garrison_size=1.0, react_chance=0.55, react_ratio=(1.0, 1.6),
                  ground_red=(90, 80, 35, 0, 0), ground_blue=(0, 10, 45, 55, 40), red_attack=0.55, red_reinf=7.0, blue_reinf=4.0),
}


def get(level: int) -> Difficulty:
    return LEVELS[max(1, min(3, int(level)))]
