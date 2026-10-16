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
| Hold times (TARCAP, sweep, escort) | `sqe/mission_builder.py` | `_hold_end`, `self._holds`, `_sync_sead` (in `engine.py`) |
| Recovery at the boat / field | `sqe/mission_builder.py`, `sqe/debrief.py` | `_recov_net`, `SQE_RECOVER`, `RECOV` |
| Red patrols / sweeps / raids | `sqe/redair.py`, `sqe/raids.py`, `sqe/mission_builder.py` | `RED_DOCTRINE`, `enemy_unlimited_fuel`, `INTERCEPT` |
| Reactive dispatch (extra pairs mid-sortie) | `sqe/reactive.py` | `plan_red`, `blue_sources`, `INTERCEPT_NM` |
| Ground war (zones, strength) | `sqe/ground.py` | `zone_of`, `_advance`, `SKIRMISH` |
| Which job types are player-flyable | `sqe/packages.py` | `AI_ONLY` |
| SAM reach / avoidance numbers | `sqe/routes.py`, `sqe/profiles.py`, `sqe/war.py` | `AVOID_NM`, `STATION_FRAC`, `GATE_REACH_NM` |
| The Lua hook (landed/dead tables, recovery) | `sqe/debrief.py` | `lua_hook`, `RECOV` |
| The unit cap | `sqe/mission_builder.py` | `max_units`, `_counts` |

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
_verified v0.41.28 + PR #65, 2026-10-16_

Roles (`sqe/models.py`): CAS, CAP, SWEEP, ESCORT, SEAD, STRIKE. Names are confusing, so note the mapping in `plan_route`:
- **ESCORT role = TARCAP** (a station short of the target).
- **SWEEP role = package escort** (holds on a station, leaves after the last striker is off target). When the objective
  itself is a sweep (`g.sweep`), the flight is a **Fighter Sweep** (waypoint action `SWEEPSTN`).
- Support CAPs are flights with a `tag`: HAVCAP, BASECAP, CVCAP, TNKCAP (not a separate role).

| Class | Waypoints | Main tasks | EGR? | Fuel |
|---|---|---|---|---|
| Support CAPs (`f.tag`) | SPAWN, CAP1 (`CAPORBIT`), CAP2, then home points that bend round SAMs | engage zone around what it guards; `MaxRange` shots; RTB on out-of-AAM; bingo RTB; TNKCAP: radar continuous search + WeaponFree | **none** | unlimited at start; **real from CAP1 on**; never unlimited again |
| TARCAP (ESCORT role) | SPAWN/DEP, MSHL (`HOLD`), PUSH, TGT (station, `TARCAP`, orbit) | engage zone covering launch points; homeward `EngageTargetsInZone` circles from `hold_end`; `HalfWayRMaxNoEsc` on the way out, `MaxRange` from the station; radar continuous search; RTB on out-of-AAM | **none** (goes home from the station) | real from PUSH; never unlimited again |
| Fighter Sweep | SPAWN, PUSH (ahead of the base), TGT (station, `SWEEPSTN`) | circle round the station (25 nm long-range / 15 nm others, kept off SA-10 reach); homeward circles; RTB on out-of-AAM | **none** | same as TARCAP |
| Package escort (SWEEP role) | SPAWN/DEP, MSHL, PUSH, TGT (station, `ESCORT`) | same as TARCAP; leaves `ESCORT_AFTER_TOT_S` after the last striker | only if the egress leg is clear of SAM cover (`egr_ok_`) | real from PUSH; unlimited again only if it has an EGR |
| Strike (bombs) | SPAWN/DEP, MSHL, PUSH, IP (+LOW), TGT (`BOMB`), EGR | restricted air-to-air, `ReturnFire`, `WeaponFree` at the target; RTB on out-of-A2G; ECM only PUSH to EGR; bomb tasks only until `LATE_ATTACK_S` after TOT | yes | unlimited, real PUSH to EGR, unlimited again at EGR |
| JSOW (Strike with kit) | like Strike but a `JSOW` launch point instead of TGT | stand-off release, never crosses the site | yes (back along its approach) | as Strike |
| SEAD / Standoff DEAD | SPAWN/DEP, MSHL, PUSH, IP, `SEAD` (HARM point), EGR | `ReturnFire` until the HARM point; `AttackGroup` ARM tasks with `stop_after_time`; covering-Tor second pass; radar gate for DEAD | yes (back along the approach) | as Strike |
| CAS | like Strike with `CAS` at the TGT | `WeaponFree` at the target; both columns are driven into contact (see ground notes) | yes | as Strike |
| Player flight | built the same, then skips AI tasks | bingo RTB and a few; no fuel toggles | built | the player's group is not toggled |
| Red patrol / sweep / raid | spawn + `INTERCEPT` waypoint (controlled task, `stop_after_time`) | engage cap (`enemy_cap_engage_nm`) | n/a | `enemy_unlimited_fuel` (default off): unlimited only if set, once at the start |

Common to every blue AI flight: `OptRTBOnBingoFuel(True)` on `points[0]`.

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
The builder turns them into DCS tasks (orbit with `stop_after_time`, `AttackGroup`, `Bombing`, ROE, ECM, fuel).

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
_verified v0.41.28 + PR #66, 2026-10-16 (read from the code, not run)_

Three kinds exist, all built in `mission_builder.py` (`_spawn_enemy`-style block near the red alert code, and `_spawn_reactive`), planned in `sqe/reactive.py`:
- **Red alert pairs** (on the runway or ramp, `_alert_group`): a trigger zone round the field (`_field_zone`, `FIELD_DETECT_NM`) fires when blue is detected inside it; on CAS days a clock replaces the zone (friendly troops sit on the target). Route: the start, one `INTERCEPT` waypoint at the target with an orbit until TOT + 1 h. No SAM-bending, no cover circle; only `_limit_engage(g, enemy_cap_engage_nm)`.
- **Red reinforcements** ("Reinforce k"): the same shape, plus a random delay; `reactive.plan_red` picks fields within the type's `INTERCEPT_NM`, held to a ratio of blue fighters.
- **Blue alert pairs** (`reactive.blue_sources`, carrier or field): trigger zone of 120 nm round the target (fleet / raid objectives) or a clock for other targets; route: one `CAP` waypoint AT the target (or the raid target) with an orbit for `cap_minutes`, engage limit `friendly_cap_engage_nm`, then land or RTB.
- Red patrols (planned picture, `CAP1`/`CAP2`) are different: they have a station and a circle (`A2A_ZONE_NM`) like ours.

**Gap (found 2026-10-16):** none of the three scramble kinds use the SAM rules (`avoid_circles`, `_zone_sams`, `_cover_circle`, `_clear_zone`). They fly a straight line to the target and orbit on it. For blue alert pairs that target can be inside a red SAM's reach. Raids by red bombers are separate (`raids.py` has `shy`, `PATRIOT_NM`, `HAWK_NM`).

## 7. Verify before trusting

- All of the above is from reading the code. No DCS run was used to confirm each behaviour.
- The old DCS behaviour of `SetUnlimitedFuelCommand` on a group with a human is not checked here; the player's own group
  is not toggled by the builder.
- Search the code again when a PR touches `plan_route`, `_limit_engage` or the fuel block, and update this file.
