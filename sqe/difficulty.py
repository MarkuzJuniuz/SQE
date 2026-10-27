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
    red_squadron_max: int = 12           # v0.41.52: most jets in one red squadron; a wing is cut into ceil(jets / this) typed squadrons (judgment call, no sourced Russian figure)
    bomber_wing: int = 0                 # strategic bombers (Tu-22M3) at Mozdok
    bomber_escort_wing: int = 0          # v0.41.106: the Mozdok escort squadron (Su-27, escort-only), 2 escorts per bomber at the biggest raid (judgment call)
    bomber_policy: str = "none"          # none | desperate | normal (v0.41.105: see bombers.py; "none" = the wing never raids)
    bomber_safe_p: float = 0.0           # v0.41.105: red sends a 4-ship raid only if its estimate of blue stopping it is at most this (0 = only when desperate); judgment calls
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
    raid_rate: float = 0.40              # Red raids on our airfields per day (raids.py); some are announced, the rest are surprises
    raid_arm: float = 0.0                # v0.41.84: chance a Su-24M raid on a field with a live Patriot / HAWK brings a Kh-31P SEAD pair (judgment call: L1 none, L2 rare, L3 normal)
    raid_banzai: bool = False            # v0.41.146 (Campaign Revamp B4): Level 1's insurgents raid targets under live Patriot / HAWK cover without any SEAD (judgment call: they have no SEAD doctrine, and with every one of our fields covered they could never raid at all); the cover shoots them
    arm_cap: int = 8                     # v0.41.125: most Su-24M in red's SEAD group (L2: a pair, judgment call) ...
    arm_cap_free: int = 8                # ... unless the wing has this many spare jets beyond the bombers (then the full sizing)
    raid_surprise: float = 0.35          # share of the raids that are surprises (nobody warned us)
    emerg_chance: float = 0.09           # chance per sortie that something breaks out while you are about to fly (an emergency)
    sam_rebuild: float = 0.04            # nightly chance (x Red supply) that a destroyed SAM site is replaced (sams.py)
    sam_scoot: float = 0.30              # nightly chance that a hurt mobile SAM site moves
    raid_size: tuple = (2, 2)            # Su-24M in a raid: drawn between these (never more than the wing has)
    raid_mix: tuple = (0.0, 0.0, 0.0)    # share of the raids that go for (a supply site, a field's garrison, friendly troops in a contested sector) instead of the airfield itself
    blue_garrison_size: float = 1.0      # scales the vehicle count of a friendly airfield garrison
    sead_valve: int = 3                  # failed SEAD days on one site before the combined SEAD + DEAD package is offered again (war.py)
    sam_retreat: float = 1.0             # scales the nightly chance that a badly hurt long-range SAM site pulls back from the front to recover (sams.retreat)
    air_retreat: float = 1.0             # nightly chance that a badly depleted air wing or squadron stands down to a rear field to recover (airwings.py)
    blue_rebuild: float = 0.15           # nightly chance (x friendly supply) that a destroyed friendly supply site or garrison is replaced

LEVELS: dict[int, Difficulty] = {
    1: Difficulty(1, "Level 1 - Insurgent", "Irregular forces. A few old aircraft, AAA and MANPADS, and a few old but working SAMs. "
                  "Expect to be shot at, not hunted.",
                  enemy_air_total=44, red_squadron_max=6, enemy_types=["MiG_21Bis", "MiG_23MLD", "MiG_29A", "Su_25", "Su_24M"],
                  sam_variants=["SA-2", "SA-3", "AAA", "MANPAD"], sam_sites_per_cluster=4, iads=0.15,         # v0.41.154 (XO 2026-10-27): the insurgents are armed with working museum pieces by a sponsor: each field gets an SA-2, an SA-3, AAA and MANPADS (it was one site of AAA or MANPADS)
                  enemy_skill="Average", loss_rate=0.035, base_damage=0.45, variance=0.8,
                  friendly_replenish=0.14, enemy_replenish=0.03, asset_repair=0.03, sam_repair=0.03,
                  friendly_scale=1.2, enemy_cap_per_air=0.10, counterstrike=0.10, bomber_wing=0, bomber_policy="none", react_chance=0.08, react_ratio=(0.2, 0.5),
                  ground_red=(55, 35, 8, 0, 0), ground_blue=(0, 20, 55, 70, 50), red_attack=0.15, red_reinf=3.5, blue_reinf=7.0, raid_rate=0.25, raid_banzai=True, raid_surprise=0.25, emerg_chance=0.03, raid_size=(2, 2), sam_rebuild=0.02, sam_scoot=0.15,
                  raid_mix=(0.10, 0.10, 0.20), blue_garrison_size=1.0, blue_rebuild=0.20, sam_retreat=0.6, air_retreat=0.6),
    2: Difficulty(2, "Level 2 - Regional Power", "A real air force and layered SAMs, but not a peer. "
                  "A competent campaign wins; a careless one bleeds.",
                  enemy_air_total=128, enemy_types=["MiG_31", "MiG_29A", "MiG_29S", "MiG_23MLD", "Su_24M", "Su_25"],
                  sam_variants=["SA-2", "SA-3", "SA-6", "SA-11", "AAA"], sam_sites_per_cluster=3, iads=0.55,
                  enemy_skill="Good", loss_rate=0.06, base_damage=0.35, variance=0.8,
                  friendly_replenish=0.08, enemy_replenish=0.05, asset_repair=0.04, sam_repair=0.06,
                  friendly_scale=1.0, enemy_cap_per_air=0.15, counterstrike=0.30, bomber_wing=11, bomber_escort_wing=8, bomber_policy="desperate", bomber_safe_p=0.06,
                  forward_sams=("SA-8", "SA-8"), garrison_chance=0.6, garrison_size=0.8, react_chance=0.35, react_ratio=(0.6, 1.1),
                  ground_red=(70, 55, 15, 0, 0), ground_blue=(0, 15, 60, 70, 50), red_attack=0.45, red_reinf=5.6, blue_reinf=7.0, raid_rate=0.4, raid_arm=1.0, arm_cap=2, arm_cap_free=8, raid_surprise=0.35, emerg_chance=0.09, raid_size=(2, 4), sam_rebuild=0.04, sam_scoot=0.30,
                  raid_mix=(0.20, 0.15, 0.25), blue_garrison_size=0.8, blue_rebuild=0.15, sam_retreat=0.8, sead_valve=3, air_retreat=0.8),
    3: Difficulty(3, "Level 3 - Near-Peer", "Modern fighters, long-range SAMs and an integrated air-defence network. "
                  "Every sortie is contested and attrition bites.",
                  enemy_air_total=256, red_squadron_max=14, enemy_types=["MiG_31", "MiG_29S", "Su_27", "Su_24M", "Su_25", "MiG_29A"],
                  sam_variants=["SA-10", "SA-11", "SA-6", "SA-15", "SA-19"], sam_sites_per_cluster=4, iads=0.9,
                  enemy_skill="High", loss_rate=0.085, base_damage=0.28, variance=0.7,
                  friendly_replenish=0.06, enemy_replenish=0.07, asset_repair=0.05, sam_repair=0.08,
                  friendly_scale=0.85, enemy_cap_per_air=0.20, counterstrike=0.55, bomber_wing=30, bomber_escort_wing=16, bomber_policy="normal", bomber_safe_p=0.12,
                  forward_sams=("SA-15", "SA-8", "SA-19"), garrison_chance=1.0, garrison_size=1.0, react_chance=0.55, react_ratio=(1.0, 1.6),
                  ground_red=(90, 80, 35, 0, 0), ground_blue=(0, 10, 45, 55, 40), red_attack=0.8, red_reinf=7.0, blue_reinf=7.0, raid_rate=0.7, raid_arm=1.0, raid_surprise=0.45, emerg_chance=0.21, raid_size=(4, 4), sam_rebuild=0.07, sam_scoot=0.50,
                  raid_mix=(0.25, 0.20, 0.25), blue_garrison_size=0.7, blue_rebuild=0.10, sam_retreat=1.0, sead_valve=2, air_retreat=1.0),
}


def get(level: int) -> Difficulty:
    return LEVELS[max(1, min(3, int(level)))]


# v0.41.70: "AI Skill", one for Red and one for Blue (XO 2026-10-21: DCS AI at the top skill cheats, so he wants a say on both sides). Set on the New Campaign
# page and in Settings > Campaign (the same two settings, like the weather). "level" = what the game did before: red follows the difficulty level
# (`enemy_skill`: Average / Good / High), blue's AI aircraft fly at High; the four named values set that side's AI directly. Skill only: the war
# sim's numbers (`base_damage`, `loss_rate`) are not touched. Blue's ground units (base defences) are left at DCS's default under "level".
SKILL_CHOICES = {"level": "Level default", "Average": "Average", "Good": "Good", "High": "High", "Excellent": "Excellent"}
SKILL_NAMES = ("Average", "Good", "High", "Excellent")


def ai_skill(opts, side: str, d, ground: bool = False):
    """The DCS skill name for a side's AI: the setting (`ai_skill_red` / `ai_skill_blue` on the options) when it names one, else the level's.
    None means "leave DCS's default" (blue ground units under "level")."""
    v = getattr(opts, "ai_skill_" + side, "level")
    if v in SKILL_NAMES:
        return v
    if side == "red":
        return d.enemy_skill
    return None if ground else "High"
