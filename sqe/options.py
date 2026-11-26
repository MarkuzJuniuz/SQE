"""The mission options (`MissionOptions`) and the one place the player's settings fill them (`options_from_settings`).

`MissionOptions` is created once per `Session` and read live; `mission_builder` re-exports it
(`sqe.mission_builder.MissionOptions is sqe.options.MissionOptions`)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .radio import RadioLayout
from .settings import f14_turnpoints_installed, f14_turnpoints_state


@dataclass
class MissionOptions:
    takeoff_buffer_s: int = 60          # takeoff buffer: you are on the cat/runway at start; the briefed takeoff is this many SECONDS in (negative = hurry)
    marshal_slack_min: int = 1          # (S77: was 2) slack at MARSHAL before PUSH, minutes. Negative = you must be quicker than the natural pace
    cap_minutes: int = 40               # time on station for CAP flights
    hot_ramp_scrambles: bool = False    # v0.41.80: alert / scramble pairs at land fields start hot on the ramp (see _alert_group)
    hot_runway_starts: bool = False     # v0.41.96: AI package flights from land fields other than yours start on the runway (see _hot_slot)
    hot_runway_own_field: bool = False  # v0.41.99: with hot_runway_starts: also flights at the player's own field (see _hot_slot)
    ai_unlimited_fuel: bool = True      # Retribution-style: ON until the push, OFF for the combat leg, ON again from egress
    enemy_unlimited_fuel: bool = False
    ai_despawn_on_land: bool = True
    ai_skill_red: str = "level"            # v0.41.70: see difficulty.ai_skill
    ai_skill_blue: str = "level"
    base_defenses: bool = True
    carrier_escorts: bool = True
    enemy_cap_engage_nm: int = 50       # enemy patrol fighters chase no further than this (0 = unlimited); v0.41.61: fixed, no settings box
    friendly_cap_engage_nm: int = 50    # HVAACAP / base BARCAP likewise (0 = unlimited); v0.41.61: fixed, no settings box
    fighter_engage_nm: int = 40         # AI escorts and sweeps chase no further than this (0 = unlimited)
    fighter_engage_minutes: int = 5     # AI escorts, sweeps, SEAD stop engaging this many minutes after the TOT and fly on (alert pairs: +5). 0 = no time limit
    player_is_ai: bool = False          # test: your own flight is built as an AI flight (no player / client slot) and gets the AI behaviour too (stand-off, engage window)
    fighter_standoff: bool = True       # AI escorts and sweeps stop short of live SAM cover instead of flying into it
    weather_mode: str = "clear"         # see weather.py: clear | procedural | scattered | broken | overcast | rain | storm
    ils_low_vis: bool = True            # S63: in low ceiling / visibility the ground wind favours each ILS runway (weather.low_visibility, weather._ground_dir)
    reactive: bool = True               # extra enemy fighters / blue alert pairs that launch during the sortie (reactive.py)
    ai_land_carrier: str = "always"     # v0.41.18: AI recovery short of a carrier: always | home (your deck only) | never
    ai_land_field: str = "never"        # v0.41.18: the same for airfields
    splash_damage: bool = True          # blasts on ground units near an air-to-ground weapon's impact (the hook)
    awacs_tuned: bool = True            # v0.41.215: the AWACS calls need a tuned radio (the cockpit-parameter triggers, tune_triggers)
    damage_calls: bool = True           # v0.41.215: damage / mayday calls from the other aircraft
    ecm_status: bool = True             # v0.41.213: the on-screen ECM messages (F-16C lamp, FC3 F10 calls); only with ecm_script
    ecm_script: bool = False            # SQE's own jamming model in the mission hook (ecm.py). Off: DCS's own ECM, the AI decides when it is locked
    f14_turnpoints: bool = False        # the F-14 RIO Navigation export script is installed: the player's F-14B / F-14B(U) gets the F10 entries (`rio_nav`)
    f14_script_old: bool = False        # ...but the installed copy is older than SQE's: it cannot work the waypoints (the build warns)
    dormant_sites: bool = False         # S89: red SAM sites on the route start late-activated and wake by detector (see `_wire_dormant`)
    carcasses: bool = True              # dead wrecks at damaged / destroyed ground sites (see carcass.py)
    wreck_static_weight: float = 0.25   # how much of a live unit one wreck or one live static building counts toward the unit limit (v0.41.221: the buildings too; renamed in S88 R2)
    carcass_range_nm: int = 40          # only sites this close to the route get wrecks
    full_map: bool = False              # stress test: build everything that exists (see _spawn_everything); the unit limit is off
    max_units: int = 250                # the unit limit of the BASE mission (wrecks are trimmed, furthest first, to fit under it); merged packages' units do not count (v0.41.104)
    target_area_radius_nm: int = 15           # v0.41.209 (XO; S139b: was merge_radius_nm): the target area radius, also the radius inside which every supply site (fuel farm, depot, both sides) is built round the target: the performance knob
    enemy_air_sum: int = 100            # folded packages: biggest enemy-air need + this % of the others' (S88 R2: no setting, no UI: 100 for everybody)
    carrier_min_enemy_nm: int = 150     # the carrier group is moved back along the line of retreat until it is at least this far from the fight
    player_is_client: bool = False
    carrier_speed_kts: int = 15
    carrier_tacan: str = "74X"
    carrier_icls: int = 11
    carrier_link4_mhz: int = 336
    carrier_atc_mhz: float = 305.0
    layout: RadioLayout = field(default_factory=RadioLayout)


_REQUIRED = object()     # no default: the setting must exist on the settings object (a missing one raises, as it always did)

# (option field, settings name, cast, default or _REQUIRED); applied in this order by options_from_settings
_PLAIN = (
    ("marshal_slack_min", "marshal_slack_min", int, _REQUIRED),
    ("takeoff_buffer_s", "takeoff_buffer_s", int, _REQUIRED),
    ("ai_unlimited_fuel", "ai_unlimited_fuel", bool, _REQUIRED),
    ("hot_ramp_scrambles", "hot_ramp_scrambles", bool, False),
    ("hot_runway_starts", "hot_runway_starts", bool, False),
    ("ai_skill_red", "ai_skill_red", str, "level"),
    ("ai_skill_blue", "ai_skill_blue", str, "level"),
    ("fighter_engage_nm", "fighter_engage_nm", int, _REQUIRED),
    ("fighter_engage_minutes", "fighter_engage_minutes", int, _REQUIRED),
    ("fighter_standoff", "fighter_standoff", bool, _REQUIRED),
    ("carcasses", "carcasses", bool, True),
    ("dormant_sites", "dormant_sites", bool, False),
    ("player_is_client", "dcs_server_fly", bool, False),         # S161a: the server option gives the flight lead a client slot
    ("reactive", "reactive", bool, True),
    ("ecm_script", "ecm_script", bool, False),
    ("ecm_status", "ecm_status", bool, True),
    ("awacs_tuned", "awacs_tuned", bool, True),
    ("damage_calls", "damage_calls", bool, True),
    ("splash_damage", "splash_damage", bool, True),
    ("ai_land_carrier", "ai_land_carrier", str, "always"),
    ("ai_land_field", "ai_land_field", str, "never"),
    ("max_units", "max_units", int, _REQUIRED),
    ("target_area_radius_nm", "target_area_radius_nm", int, 15),
    ("weather_mode", "weather_mode", str, "clear"),
    ("ils_low_vis", "ils_low_vis", bool, True),
)


def options_from_settings(options: MissionOptions, settings, *, ai_test: bool, full_map: bool) -> MissionOptions:
    """Fill `options` (the same object, it is read live elsewhere) from the settings and return it.
    Fields this does not set (enemy_air_sum, the carrier fields, ...) keep their values."""
    for field_name, name, cast, default in _PLAIN:
        value = getattr(settings, name) if default is _REQUIRED else getattr(settings, name, default)
        setattr(options, field_name, cast(value))
    options.hot_runway_own_field = options.hot_runway_starts and bool(getattr(settings, "hot_runway_own_field", False))
    options.wreck_static_weight = max(5, int(getattr(settings, "wreck_static_weight_pct", 25))) / 100.0
    # not a saved setting: installed or not, on this PC, when the mission is built
    options.f14_turnpoints = f14_turnpoints_installed(getattr(settings, "dcs_saves", ""))
    options.f14_script_old = f14_turnpoints_state(getattr(settings, "dcs_saves", "")) == "old"
    options.player_is_ai = bool(ai_test)
    options.full_map = bool(full_map)
    if full_map:
        options.max_units = 10 ** 6
    return options
