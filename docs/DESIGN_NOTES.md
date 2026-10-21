# SQE design notes (for Crew Chief)

Where things live and how they behave, written so a fresh Crew Chief can answer "how does X work?" without re-reading
the whole builder. Read from the code on 2026-10-16 (version v0.41.28 plus PR #65). **Nothing here was run in DCS**:
it is what the code says it does. When a note says "check", verify before acting on it. Line numbers drift, so
the notes name functions, variables and comments to search for. Keep this file current: when a PR changes
one of these behaviours, change the note in the same PR.

Procedure (also in CLAUDE.md): read this first, grep the anchor a note names, answer from the doc if it still matches and the stamp is recent; otherwise
read the code, then correct the note and update its stamp. Stamps: `verified v0.41.28 + PR #65, 2026-10-16` unless a section says otherwise.

## 1. Where to look
_verified v0.41.28 + PR #65, 2026-10-16_

| Question | File | Search for |
|---|---|---|
| Which waypoints does a flight get? | `sqe/routes.py` | `plan_route`, `Wpt(` |
| What are a waypoint's names / actions? | `sqe/routes.py`, `sqe/mission_builder.py` | `class Wpt`, `OBJECTIVE_ACTIONS` (routes), `STATION_ACTIONS` (builder) |
| Support CAP waypoints (HAVCAP, BASECAP, CVCAP, TNKCAP) | `sqe/mission_builder.py` | `f.tag`, `Wpt("CAP1"`, `CVCAP_NM`, `tanker_spot` |
| Tasks attached to waypoints / the group | `sqe/mission_builder.py` | `for w in wps[first:]`, `g.points[0].tasks` |
| Fuel (unlimited / real) | `sqe/mission_builder.py` | `SetUnlimitedFuelCommand`, `ai_unlimited_fuel`, `past_push` |
| Engage-zone circles, homeward fight | `sqe/mission_builder.py` | `_limit_engage`, `_cover_circle`, `_clear_zone`, `HOMEWARD_ENGAGE_NM` |
| Hold times (TARCAP, sweep, escort) | `sqe/mission_builder.py` | `_hold_end`, `self._holds`, `_extend_holds`, `_sync_sead` (in `engine.py`). v0.41.38: a TARCAP holds at least `TARCAP_MIN` (15) min after arriving and until the LAST strike / SEAD / CAS flight of its own package (`striker_tots`) and any merged package near the target is off target + `TARCAP_AFTER_TOT_S` (5 min), at most `HOLD_EXTEND_MAX_S` past its own end; escorts +3 min, sweeps +2 min. _verified v0.41.38, 2026-10-20_ |
| Recovery at the boat / field | `sqe/mission_builder.py`, `sqe/debrief.py` | `_recov_net`, `SQE_RECOVER`, `RECOV` |
| Red patrols / sweeps / raids | `sqe/redair.py`, `sqe/raids.py`, `sqe/mission_builder.py` | `RED_DOCTRINE`, `enemy_unlimited_fuel`, `INTERCEPT` |
| Reactive dispatch (extra pairs mid-sortie) | `sqe/reactive.py` | `plan_red`, `blue_sources`, `INTERCEPT_NM` |
| Ground war (zones, strength) | `sqe/ground.py` | `zone_of`, `_advance`, `SKIRMISH` |
| Which job types are player-flyable | `sqe/packages.py` | `AI_ONLY` |
| SAM reach / avoidance numbers | `sqe/routes.py`, `sqe/profiles.py`, `sqe/war.py` | `AVOID_NM`, `STATION_FRAC`, `GATE_REACH_NM` (XO v0.41.37: `STATION_FRAC` 0.85 against a long-range SAM, about 40 nm for an SA-10; `STANDOFF_MARGIN_NM` 5 nm outside medium / short-range rings, both in `profiles.py`). XO v0.41.36: a player flight from a land base no longer gets a SPAWN waypoint (`routes.py`, `elif not is_player`) |
| The Lua hook (landed/dead tables, recovery) | `sqe/debrief.py` | `lua_hook`, `RECOV` |
| The unit cap | `sqe/mission_builder.py` | `max_units`, `_counts` |
| Red air wings and squadrons | `sqe/models.py`, `sqe/scenario.py` | `EnemyAirWing.sqns` (`RedSquadron`: one type each), `red_squadrons`, `Difficulty.red_squadron_max` (L1 6 / L2 12 / L3 14). v0.41.52: a wing is `ceil(jets / max)` typed squadrons. v0.41.53: strength is per SQUADRON (`available`, `reserve`, `rest_days` on `RedSquadron`); the wing's numbers are sums, `wing.available = n` spreads a change, `wing.lose(type, n)` takes typed losses (manifest groups carry `ac`), `types_up` / `fighter_types()` / `available_of()` say what can fly today; rest, return and replenishment run per squadron (`airwings.py`, `war.end_day`). Old saves load via `models.wing_from_dict`. _verified v0.41.53, 2026-10-21_ |

## 2. How a flight is built (outline)
_verified v0.41.28 + PR #65, 2026-10-16_

1. `engine.py` plans the day: objectives, packages, flights (role, aircraft, base, tag).
2. `mission_builder.py` builds each blue flight: waypoints (`plan_route` or the support-CAP branch), times
   (`assign_times`), group, then the tasks. AI flights and the all-AI test (`player_is_ai`) get the full set of tasks.
   The human player's flight skips most of them (the loop `continue`s after the player's ETA/name handling).
3. Group-level tasks go on `g.points[0].tasks` (they apply from the start). Waypoint-level tasks go on that waypoint.
4. Home leg: AI airfield flights add an `RCV` entry point (staggered by `RCV_SPREAD`), then land or are recovered by
   `SQE_RECOVER`; carrier flights are recovered `CV_RECOVER_NM` out; the player lands for real.

## 3. Flight classes: waypoints and tasks
_verified v0.41.50 (role rename), 2026-10-21_

Roles (`sqe/models.py`), one name per job since v0.41.50: CAS, CAP, TARCAP, ESCORT, SWEEP, SEAD, STRIKE.
- **TARCAP role** = a station short of the target (was `Role.ESCORT` before v0.41.50).
- **ESCORT role** = package escort (holds on a station, leaves after the last striker is off target; was `Role.SWEEP` in a strike / DEAD / CAS package).
- **SWEEP role** = Fighter Sweep (COUNTER_AIR package, `g.sweep`, waypoint action `SWEEPSTN`) and the fleet-defence fighters.
- Still old in the code (rename PR B, not done): waypoint action names (`SWEEPSTN`, the fallback `SWEEP`), class names, GUI labels. `plan_route` still tests `(Role.ESCORT, Role.SWEEP)` together in the places where both fly a station.
- Saved campaigns: format 6; `state._migrate_roles_v6` converts format-5 plan flights (ESCORT -> TARCAP; SWEEP -> ESCORT unless the objective is COUNTER_AIR / FLEET_DEFENSE).
- Support CAPs are flights with a `tag`: HAVCAP, BASECAP, CVCAP, TNKCAP (not a separate role).

| Class | Waypoints | Main tasks | EGR? | Fuel |
|---|---|---|---|---|
| Support CAPs (`f.tag`) | SPAWN, CAP1 (`CAPORBIT`), CAP2, then home points that bend round SAMs | engage zone around what it guards; `MaxRange` shots; RTB on out-of-AAM; bingo RTB; TNKCAP: radar continuous search (default ROE: v0.41.35 dropped WeaponFree, it chased out of the circle); the v0.41.34 pull-back was removed in v0.41.51 (no pulls in three runs; the tracks show a CAP leaving its circle) | **none** | unlimited at start; **real from CAP1 on**; never unlimited again |
| TARCAP (TARCAP role) | SPAWN/DEP, MSHL (`HOLD`), PUSH, TGT (station, `TARCAP`, orbit; v0.41.43: in a package with a JSOW flight the station is `TARCAP_BEHIND_NM` (16) behind the JSOW launch point, stepped back until outside SAM rings) | engage zone covering launch points; homeward `EngageTargetsInZone` circles from `hold_end`; `HalfWayRMaxNoEsc` on the way out, `MaxRange` from the station; radar continuous search; RTB on out-of-AAM | **none** (goes home from the station) | real from PUSH; never unlimited again |
| Fighter Sweep | SPAWN, PUSH (ahead of the base), TGT (station, `SWEEPSTN`) | circle taking in the station and the red flight it hunts (`package.extra["sweep_vs"]`), clear of SAMs; homeward circles; RTB on out-of-AAM. Dispatch and station: see the note under this table | **none** | same as TARCAP |
| Package escort (ESCORT role) | SPAWN/DEP, MSHL, PUSH, TGT (station, `ESCORT`; v0.41.42: in a package with a JSOW flight the station is `ESCORT_BEHIND_NM` behind the JSOW launch point, not SAM-clear) | same as TARCAP (v0.41.42: its circle covers every shooter's launch point and only SA-10 reach keeps it out: `_cover_circle(long_only=True, max_nm=TARCAP_COVER_MAX_NM)`); leaves `ESCORT_AFTER_TOT_S` after the last striker, or `ESCORT_AFTER_EGR_S` (2 min) after the last striker's egress point if later (v0.41.40, `_striker_egr`) | only if the egress leg is clear of SAM cover (`egr_ok_`) | real from PUSH; unlimited again only if it has an EGR |
| Strike (bombs) | SPAWN/DEP, MSHL, PUSH, IP (+LOW), TGT (`BOMB`), EGR | restricted air-to-air, `ReturnFire`, `WeaponFree` at the target; RTB on out-of-A2G; ECM only PUSH to EGR; bomb tasks only until `LATE_ATTACK_S` after TOT | yes | unlimited, real PUSH to EGR, unlimited again at EGR |
| JSOW (Strike with kit) | like Strike but a `JSOW` launch point instead of TGT (v0.41.46: `JSOW_LAUNCH_NM` 30 nm out, kept outside every ring in `g.jsow_keep`: SA-10 at `JSOW_KEEP_HIGH_NM`, the target cluster's own SAMs at their `AVOID_NM`) | stand-off release, never crosses the site; bombing tasks end `JSOW_ATTACK_S` (120 s) after the point's ETA, then a timed Return Fire (v0.41.47) stops the weapons-free hunt; two JSOWs a jet (`JSOW_PER_JET`, Hornet kit = XO's ME loadout with Litening), aim order covering Tor, a launcher, radars | yes (back along its approach) | as Strike |

**Fighter Sweep dispatch (v0.41.33, XO 2026-10-16; _verified v0.41.33, 2026-10-16_).** A sweep is its own package (`ObjectiveType.COUNTER_AIR`, aim `SWEEP`), planned in `engine.plan_day` (`build_all`) for an area whose packages need more fighters than their TARCAP. It hunts; it does not bait. The rules are in `sqe/sweep.py`: `candidates` (a red flight from `state.red_air` within `AREA_NM` of the area, `in_open` = `OPEN_MARGIN_NM` outside every SAM's `AVOID_NM`, with a station from `station_for`), then after the day's timing `pick` (that flight up from `WINDOW_BEFORE_MIN` before to `WINDOW_AFTER_MIN` after the first covered package) or the sweep is dropped. The station (`MissionBuilder._sweep_station` -> `sweep.station_for`): `REACH_NM` short of the red flight toward home, clear by `clear_for_sweep` (`SWEEP_SA10_NM` from an SA-10, `SWEEP_RING_MARGIN_NM` outside other rings), outside red's scramble circles where it can be. Effect: red's patrols sit over the SAMs they guard (`redair.assign_guards`), so no sweep flies on Normal / Hard until SEAD / DEAD opens the air. Margins are judgment calls (CHANGES v0.41.33).
| SEAD / Standoff DEAD | SPAWN/DEP, MSHL, PUSH, IP, `SEAD` (HARM point), EGR | `ReturnFire` until the HARM point; `AttackGroup` ARM tasks with `stop_after_time`; covering-Tor second pass; radar gate for DEAD | yes (back along the approach) | as Strike |
| CAS | like Strike with `CAS` at the TGT | `WeaponFree` at the target; both columns are driven into contact (see ground notes) | yes | as Strike |
| Player flight | built the same, then skips AI tasks | bingo RTB and a few; no fuel toggles | built | the player's group is not toggled |
| Red patrol / sweep / raid | spawn + `INTERCEPT` waypoint (controlled task, `stop_after_time`) | engage cap (`enemy_cap_engage_nm`) | n/a | `enemy_unlimited_fuel` (default off): unlimited only if set, once at the start |

Common to every blue AI flight: `OptRTBOnBingoFuel(True)` on `points[0]`.

**Ground units (v0.41.39, 2026-10-20).** `_ground_orders(g)` in `mission_builder.py` sets `OptROE` weapons free + `OptAlarmState(2)` on point 0 of red garrisons/columns (`_spawn_site`, non-SAM), blue sites (`_spawn_blue_site` area, ~line 2822) and the CAS task force (via `_drive`). No target-priority order exists for ground units in the ME, so ground-before-parked-jets is not enforced. Untested: whether DCS ground AI shoots parked aircraft.

## 4. The fuel model
_verified v0.41.28 + PR #65, 2026-10-16_

- Setting `ai_unlimited_fuel` (default True): "Retribution-style", unlimited until the push, real over the combat leg,
  unlimited again from egress.
- Implementation: `SetUnlimitedFuelCommand(not past_push)` on `points[0]` (blue AI flights only);
  `SetUnlimitedFuelCommand(False)` inserted at the waypoint named **PUSH** or **CAP1**;
  `SetUnlimitedFuelCommand(True)` inserted at the waypoint named **EGR**.
- Consequence: the "free again" step hangs on the **EGR waypoint existing**. Classes with no EGR never get it back.
- `past_push`: for a flight already underway (an earlier package folded in; `in_progress`), the start is real fuel.

## 5. Questions answered so far
_verified v0.41.28 + PR #65, 2026-10-16_

**Which classes set their waypoint actions?** See section 3. Actions come from `plan_route` (`routes.py`): `HOLD` (MSHL),
`CAPORBIT` (CAP1), `TARCAP` / `ESCORT` / `SWEEPSTN` / `SWEEP` (stations), `BOMB`, `SEAD`, `JSOW`, `CAS` (attack points).
The builder turns them into DCS tasks (orbit with `stop_after_time`; v0.41.44: station orbits are `Circle`, because DCS's default Race-Track runs from its waypoint to the NEXT waypoint, which for a station is RTB (2026-10-20 tracks); only the support-CAP CAP1 -> CAP2 racetrack is a real race-track; `AttackGroup`, `Bombing`, ROE, ECM, fuel).

**Would the CAPs still have unlimited fuel on the way home, now that they lost the egress waypoint?** No.
Support CAPs, TARCAPs and Fighter Sweeps have no EGR (stand-off fighters were given none in v0.40.1: they go home from
their station). The fuel switch to real happens at PUSH or CAP1, and only EGR switches it back, so those jets fly
home on real fuel. Escorts keep it only when the egress leg was clear of SAM cover. What saves them today is the
bingo RTB (`OptRTBOnBingoFuel`) and the hold times. A jet that leaves its station low could still run dry on the way home.
Flame-outs happened in earlier runs (v0.41.8, v0.41.14); the fix then was the bingo RTB, and whether the no-EGR fuel state
contributed has not been checked. Possible fix, not built: a
`SetUnlimitedFuelCommand(True)` on the first waypoint after the station (or the RCV point) for classes with no EGR.
Whether that is wanted is XO's call (a CAP that stays on real fuel at the end of its time is also "more honest").

## 6. Scrambles and reactive spawns
_verified v0.41.28 + PR #66, 2026-10-16 (read from the code, not run; the emergency-scramble paragraph also read from a test .miz)_

Three kinds exist, all built in `mission_builder.py` (`_spawn_enemy`-style block near the red alert code, and `_spawn_reactive`), planned in `sqe/reactive.py`:
- **Red alert pairs** (on the runway or ramp, `_alert_group`): a trigger zone round the field (`_field_zone`, `FIELD_DETECT_NM`) fires when blue is detected inside it; on CAS days a clock replaces the zone (friendly troops sit on the target). Route: the start, one `INTERCEPT` waypoint at the target with an orbit until TOT + 1 h. No SAM-bending, no cover circle; only `_limit_engage(g, enemy_cap_engage_nm)`.
- **Red reinforcements** ("Reinforce k"): the same shape, plus a random delay; `reactive.plan_red` picks fields within the type's `INTERCEPT_NM`, held to a ratio of blue fighters.
- **Blue alert pairs** (`reactive.blue_sources`, carrier or field): trigger zone of 120 nm round the target (fleet / raid objectives) or a clock for other targets; route: one `CAP` waypoint AT the target (or the raid target) with an orbit for `cap_minutes`, engage limit `friendly_cap_engage_nm`, then land or RTB.
- Red patrols (planned picture, `CAP1`/`CAP2`) are different: they have a station and a circle (`A2A_ZONE_NM`) like ours.

**Gap (found 2026-10-16):** none of the three scramble kinds use the SAM rules (`avoid_circles`, `_zone_sams`, `_cover_circle`, `_clear_zone`). They fly a straight line to the target and orbit on it. For blue alert pairs that target can be inside a red SAM's reach. Raids by red bombers are separate (`raids.py` has `shy`, `PATRIOT_NM`, `HAWK_NM`).

**Emergency raid scramble and merging (read 2026-10-16 from the code and XO's Kobuleti test .miz; the test ran with `RAID_SCRAMBLES = True` only):**
- The emergency package is built directly in `_make_emergency` (engine.py) and never goes through `flyable()`, so `FLEET_DEFENSE` can stay in `AI_ONLY`; the one switch is `RAID_SCRAMBLES` (engine.py top).
- Blue scramble flights have `CAP1` exactly on the raid's target, so they orbit over the base (inside SA-10 reach in the test; 6 of 7 blue losses went to the Sukhumi S-300).
- Red raid groups (bombers and escorts) are placed in the AIR at t=0, about 93 km (50 nm) from the target, at 12,000 ft, 232 m/s, with waypoints start, STN, STN, BASE: no field spawn, no marshal, no TOT. Colt 3 / Dodge 3 are clock-activated (`c_time_after` 161 / 196 s); Viper alert pairs launch from the runway when the zone trigger fires (10 s in the test).
- Nothing folds into a raid scramble: `_pkg_xy` returns None for `BARCAP` / `FLEET_DEFENSE`, so `merge_center` is None and `merge_candidates` returns []. Only a CAS emergency folds packages in (`lead_extras`). Taking the scramble sends the package you were tasked with to the war sim (`fly`, "left to the other squadrons"), or postpones it a day (`_postpone_if_short`).
- Merge window for packages that do fold: from `merge_back_min` (default 15) minutes before to 30 minutes after the anchor's start, inside the 50 nm merge circle, at most six.

## 7b. How red picks targets (raids and the carrier)
_verified v0.41.28 + PR #66, 2026-10-16 (read from the code, not run)_

- **Red does not "see an opening".** Two separate systems, both score-based:
  1. **Daily raids on our bases and assets** (`raids.py`: `candidates`, `target_weights`, `pick_aim`, `shy`): weight = nearer to a raider wing, softer defence (`base.defense`), supply/garrison value; the level's `raid_mix` picks the kind (field / supply / garrison / sector). `shy` lowers the weight of targets under Patriot (`PATRIOT_NM` 40) or HAWK (`HAWK_NM` 25). **The carrier is skipped as a "field" target** (`b.kind == BaseKind.CARRIER`).
  2. **The carrier raid** is not chosen by red: `war.py` (search `bomber_policy`) adds a `FLEET_DEFENSE` objective "Intercept a bomber raid on <carrier>" to blue's daily pool with priority `6.0 + 0.3 * bombers available`, when a Tu-22M3 wing has 2+ jets and the level allows it: L3 `normal` (any day), L2 `desperate` (only when red `enemy_air` < 0.45 or `c2` < 0.5), L1 `none`. It then competes with the other objectives (one of each type first, 40% cap per type). Wing size: `bomber_wing` in `difficulty.py` (L2 4, L3 10).
- A carrier-opening trigger (e.g. weak carrier CAP, recent red losses) does not exist yet.

## 7. Verify before trusting

- All of the above is from reading the code. No DCS run was used to confirm each behaviour.
- The old DCS behaviour of `SetUnlimitedFuelCommand` on a group with a human is not checked here; the player's own group
  is not toggled by the builder.
- Search the code again when a PR touches `plan_route`, `_limit_engage` or the fuel block, and update this file.

## 8. Mission Editor refuses the mission: waypoint lock errors
_verified v0.41.32 + PR #74, 2026-10-16 (read from the code; FIXED, confirmed by script, not yet reopened in the Mission Editor by XO)_

The Mission Editor (ME) validates every route on load/save. Messages seen so far, all about the speed and time padlocks on a waypoint:
- "All waypoints (5-5) have locked speed and surrounded by waypoints 4 and 5 with locked time" (v0.41.2; fixed by not time-locking fighter stations). Same family: v0.8.5 "(2-4) ... waypoints 1 and 4".
- **"Waypoint 8 have both unlocked speed and time and not surrounded by waypoints with locked time!"** (XO, 2026-10-16, "Viper 2"). The mirror rule: a point whose speed AND time are both free needs a time-locked point on each side. **Fixed in v0.41.32 (PR #74).**

How SQE sets the locks (search `_set_eta`, `_free_locked_speeds`, `speed_locked`, `ETA_locked`, `_trailing_steerpoints` in `mission_builder.py`):
- Time-locked: the first point (takeoff, `ETA = 0`), PUSH, and the objective point (not stations). Speed is locked everywhere except between PUSH and the objective, and on the point just before PUSH.
- `_free_locked_speeds` frees the first speed in any run of speed-locked points between two time-locked ones, and (v0.41.32) also locks the speed of any point past the LAST time-locked waypoint that would otherwise be both-unlocked.
- `land_at()` (pydcs) leaves a flight's landing point `speed_locked = True` by default; that is safe on its own.
- **Confirmed cause of the "Viper 2" error (not a hypothesis any more):** `_spawn_flight` used to force the player's own landing point `speed_locked = False` ("your landing point: speed free, so it never closes a locked-speed run" — a leftover from the v0.41.2 fix above, which only applies when a locked-time point actually follows). `_trailing_steerpoints` (package-level, runs after every flight is built) then appends DIVERT/TKR/BULLS reference points on the player's own route — none of them time-locked (`add_waypoint` always sets `ETA_locked = False`). So the landing point was never followed by a locked-time point, and the override broke the mirror rule. Reproduced on every player flight with trailing steerpoints (not just raid scrambles): the override line is gone, and `_free_locked_speeds` now covers the tail generically instead.

Quick workaround for XO in the ME on a mission generated before v0.41.32 (no rebuild): open the flight's waypoint named in the error and lock its speed (padlock beside speed), or lock its time (padlock beside ETA), then save. Not needed on builds from v0.41.32 on.

How to check a mission without the ME: unzip the `.miz`, parse `mission` with `dcs.lua.loads`, and for each point in a group's route check `not ETA_locked and not speed_locked` with a locked-time point bracketing it on both sides (not just "both false" — a bracketed point like MSHL, between TakeOff and PUSH, is fine). `tools/smoke_test.py`'s raid-build check (`_bad31`, builds a real player flight, not the AI test) does exactly this now. Ask XO for the `.miz` if the ME still refuses a mission after v0.41.32; it would mean a new code path adds points after the last time-locked waypoint.

**JSOW stand-off (v0.41.46-47, XO 2026-10-20; _verified v0.41.47, 2026-10-20_).** Runs showed JSOWers lost to SAMs and scrambles, and jets creeping from 30 to 16 nm of the SAMs after release because the JSOW waypoint sets WeaponFree (they hunted radars and launchers with weapons left). Fix: launch point 30 nm out (judgment call; AGM-154A released at 20,000 ft reached about 24-35 nm in XO's runs, SA-11 reach about 19-20 nm), `jsow_launch_nm` checks every `g.jsow_keep` ring at its own radius, bombing `stop_after_time` at `eta_s + JSOW_ATTACK_S`, then `OptROE ReturnFire` via `ControlledTask.start_after_time`. Open: whether DCS drops an attack in progress when the ROE changes (read the next state file).

**Ground groups and runways (v0.41.48, XO 2026-10-20; _verified v0.41.49, 2026-10-20_).** `MissionBuilder._site_center` moves every site centre off runway corridors before it stores the position (`_on_runway`, `_off_runway`; the bomb point and the units agree); the blue base-defence `dry()` placement uses `_on_runway` too. pydcs gives each runway only a heading, so the strip is a corridor through the airfield reference point: `RUNWAY_HALF_LEN_M` 2600 m each way, `RUNWAY_HALF_WIDTH_M` 120 m, plus the group's footprint (judgment calls). Site formations are still random pydcs presets (Star / Scattered / Rectangle; armour Line / Rectangle); no road or terrain layout yet.

**AI home legs and terrain (v0.41.49, 2026-10-20; _verified v0.41.49_).** `plan_route` waypoints get `terrain_clear`, but the RCV point is added later in `_spawn_flight` (airfield flights) at 3,000-6,000 ft; an AI flight drops to the next point's altitude right after the last one, so a lone F-16 flew 100 nm level at 3,000 ft MSL over rising ground and died. `routes.home_leg_ft` now sets the RCV altitude from the leg's ground (+1,000 ft, +2,000 ft over mountains, cap 20,000 ft); the support-CAP branch runs `terrain_clear` too. Carrier recovery points (RTB 2,000 ft) are over water and unchecked. The Lua death record carries `x`, `z` and `ground_m` (`land.getHeight`; 0 over sea).

