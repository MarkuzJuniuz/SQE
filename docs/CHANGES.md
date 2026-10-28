# CHANGES.md


## v0.41.171, Air tempo: credit for what the whole mission did; a bad sortie takes nothing back

XO 2026-10-28: the tempo only looked at the package's own objective, so air kills and blinded SAM sites in a strike package taught the background AI nothing, and a bad sortie made it unlearn.
- `tempo.credits(outcome)`: DEAD +2 per SAM site blinded or damaged by a quarter or more (+4 destroyed); AIR +2 for one red aircraft shot down, +4 for two or more; STRIKE +2 for another (non-SAM) asset hit by a quarter or more; at most +6 a kind per sortie (judgment calls). A kind takes the larger of its grade step and its credit, not the sum. The debrief lists each credit.
- `STEP["bad"]` 0 (was -4): only the nightly decay lowers the tempo. Cap +40 and decay 3% unchanged.
- `debrief` `red_assets` entries now carry `kind`, `primary`, `destroyed`, `suppressed`.
- `raids.overnight`: half of the AIR tempo (`TEMPO_STOP_SHARE` 0.5, so +20 points at the cap) is added to the chance a surprise raider is stopped (cap 95% as before); the damage of raiders that get through is unchanged.
- Smoke: `check_67_air_tempo` (bad takes nothing back; credits by kind; the raid share).


## v0.41.170, The CAS task force starts closer

XO 2026-10-28: in the flown CAS run the friendly task force stalled 0.7 km out (11 min in) and the red column barely moved, 5.6 km apart, so they never met. `CAS_APPROACH_M` 6000 -> 2500 m: the task force starts at most 2.5 km from the contact point. Cause of the stalls unknown (DCS ground pathing); this hides it for short trips.


## v0.41.169, State file: tracks of the CAS columns

XO 2026-10-28 (CAS columns stop "at kissing distance" then move apart): `tracks` in SQE_state.json now also holds the lead unit of each Friendly Task Force and each red `armor_` group, every 30 s, at most 120 points (same `[t, x, z, alt, -1, kts]` format as the flights). Diagnosis only; no behaviour change.


## v0.41.168, The TARCAP stands further back

XO 2026-10-27: the TARCAP dived into red's BARCAP swarm. `TARCAP_NEAR_NM` 16 -> 26 (judgment call); BARCAP circles unchanged. Smoke bound in check on the TARCAP distance 28 -> 38.


## v0.41.167, A strike's SEAD escort fires HARMs at the SAMs that cover the target

XO 2026-10-27 (L2 F-14 supply-depot strike): the escort flight fired no HARMs, because its ARM task was aimed at the depot group; the SA-2 and SA-3 shot down three jets.

- `strike_tasks._sead_attack_tasks`: the covering SA-2/3/6 (gate) sites get HARM tasks for a STRIKE package as well as a CAS one (same window as CAS).


## v0.41.166, The coalition's supply floor is 30%; air tempo runs 0 to +40%

XO 2026-10-27: idle L3 could not lose, and AI-flown sorties made the air tempo worse.

- `ground.BLUE_SUPPLY_FLOOR` 0.30 on every level (red keeps 0.55, L1 red 0.70): the coalition's stock comes by sea, so once its depots and fuel are hit it recovers slowly (repair is supply / 6 days). Sims (L3 F-16C, 5 seeds, 120 days, red 0.55): idle 3 red wins of 5, flying stand-in 0 red wins (2 coalition wins, 3 still open); L2 unchanged (coalition wins in about a month either way). Judgment call, no public source. Flying L3 now takes longer to finish (about 100+ days).
- `tempo`: the air tempo runs 0 to +40 points (`TEMPO_MIN` 0, `TEMPO_CAP` 0.40; was +-20): a bad sortie only takes back what flying built, so an AI-flown sortie cannot make the background jobs worse. A negative value in an older save reads as zero. Overview and tempo text updated.
- Smoke: `check_61` (coalition floor 0.30) and `check_67_air_tempo` (cap, zero floor, old negative saves) adjusted.

## v0.41.165, Settings: Pilot Influence moved below the whole Weather block

XO 2026-10-27 (screenshot): in Settings > Campaign the Pilot Influence row sat between the Weather combo and the Weather description, so the weather text read as if it described Pilot Influence. The row and its description now come after the Weather block. The New Campaign dialog was already fine (no description paragraphs there). Layout only; smoke not needed beyond the import check.

## v0.41.164, Nothing to fly keeps your Pilot Influence; a box when the war ends

XO 2026-10-27: a day with no flyable package is out of the pilot's hands.

- `Session.skip_day`: on a stand-down day (no package you can fly) with Pilot Influence on, the idle surge clock is held (`flown_day` = today) and tonight's air-tempo fade is skipped (`war.end_day` checks the `stand_down` flag, cleared after the day). Skipping while you could have flown is unchanged.
- The GUI shows one box, titled VICTORY or DEFEAT with the ending's name, with the same story line as the Overview, the moment the war ends (a flown sortie, a skipped day or the dev skip). A finished campaign that is merely loaded shows none. The old VICTORY / DEFEAT line in the "Day resolved" box is gone.
- Smoke: new `check_81_stand_down_keeps_pilot_influence`.

## v0.41.163, Fewer MiG-31s, and they sit deep

XO 2026-10-27: the fringe fields were full of MiG-31s that dogfighters would slaughter. A MiG-31 is a big interceptor that works from rear bases under ground control, so:

- The depth gradient is flipped (`redroster.MIG31_SHARE`): of a field's MiG-31 + Su-27 jets, 15% are MiG-31 at fringe fields (tier 2), 50% in the middle, 75% deep (tier 4). The Su-27 now holds the fringe.
- Smaller MiG-31 fleet (judgment call, no public source): L2 7 down to 4 (3 more MiG-29S, same fighter total of 52), L3 14 down to 8 (6 more Su-27, same total of 86).
- Smoke: `check_62_red_roster` now asserts the share rises with depth.
- Only new campaigns get the new split; running campaigns keep their jets.

## v0.41.162, Friendly errors for saves this version cannot open

XO (2026-10-27, "when I loaded an old save it gave py errors... make that graceful"). Loading a save that this build cannot read no longer shows a traceback.
- Saves now carry `app_version` and `compat` (an era number, `COMPAT_ERA` in `sqe/__init__.py`, bumped when a change breaks older saves). Saves without the stamp are simply tried.
- `CampaignState.load` raises `SaveIncompatible` (kind older / newer / damaged) for a bad file, a newer format or era, an older era, or any error while reading; `Session.open` also catches errors in the steps after loading and leaves the campaign that was open open.
- The GUI dialog says which SQE saved the file (when it is stamped) and offers "Back up and start a new campaign" (a copy goes to the backups folder, the original is not touched, and New Campaign opens with the name, aircraft and level filled in) or "Leave it alone". A save from a newer SQE gets an OK button only. A save that loads fine shows nothing.
- Smoke: new `check_80_incompatible_saves`.


## v0.41.161, Pilot Influence also switches air tempo

XO (2026-10-27, "lump them together"; he wants to test progress with flying off). With Pilot Influence off, `tempo.get` returns 0 and `tempo.record` moves nothing, on top of the red surge: your flying changes nothing in the war sim. The tempo already earned is kept and comes back when the setting is turned on. The setting's text says so. Smoke: `check_79_pilot_influence` also checks tempo.


## v0.41.160, Pilot Influence

XO (2026-10-27: "a setting for the dynamic player flight effects... it's just for giving red a chance to win on L3"). New setting `pilot_influence`, on by default, in New Campaign and Settings > Campaign (like Weather and AI Skill: an app setting, copied into the campaign when it is planned and simulated).
- On: as before, red surges while your squadron stands down (v0.41.155).
- Off: `ground.surge` stays at 1.0, so your flying makes no difference to the red surge. Measured first: with the surge off and no flying at all, L2 still wins and L3 does not lose (6 seeds, 60 days), so the war cannot be lost by standing down. The air tempo (what your flown sorties do to the odds of background jobs) is unchanged.
- Smoke: new `check_79_pilot_influence`.


## v0.41.159, The carrier moves along the campaign

XO (2026-10-27, "100 sounds about right... fully dynamic"). The fleet no longer sits at a fixed point 160 km west of Batumi.
- New `sqe/carrier_pos.py`: once a day (at planning; a replan changes nothing) the fleet takes the spot nearest the front line that is at least 100 nm (`carrier_standoff_nm` in the theatre pack) from every red airfield red still holds and 25 nm off the coast, moving at most 150 km a day. Under 30 km of gain it stays put. As red fields fall the circle shrinks and the fleet closes in. The first day on an older save puts it on its station at once. A log line says when it moves.
- Fiction (XO): red's shore-based anti-ship missiles; the real reason is that nothing red launches near it survives. The numbers are judgment calls (100 nm from XO's run, 150 km/day, 30 km hysteresis).
- Smoke: new `check_78_carrier_moves_with_the_front`.


## v0.41.158, Strikes and CAS go in behind the SEAD

XO (2026-10-27, "strikes first... go high"). On L2 and L3 most jobs for a Viper or Hornet were DEAD, because every strike and CAS target under an SA-11 or SA-10 was blocked until a DEAD cleared it. Sources (SLDinfo on SEAD in an A2AD world, GAO-03-51): SEAD suppresses and degrades, it does not make a site safe for good, so the new rule is conditional and the job is turned back when the SEAD fails (judgment call).
- A STRIKE or CAS whose target is covered by one or two SA-11 / SA-10 sites is now offered when today's list already holds the SEAD / standoff job of each of those sites (`Objective.after`, `war._add_followers`). Under three or more sites it stays DEAD-first. SA-2/3/6 round it still get the HARM escort in the package. The site's DEAD job gets x1.4 priority when something waits behind it.
- It starts 10 minutes after the latest of those packages (`FOLLOW_GAP_MIN`, `engine._stage_times`). If a SEAD package cannot be crewed, the follow job is dropped.
- War sim: held (no losses, no damage) when the day's SEAD verdict failed; otherwise the strike rolls as usual with the blinded sites counted as suppressed defenders.
- Mission: the site(s) spawn in the mission; those the SEAD blinded start without radars (unless the SEAD flies in the same merged mission). The Close DEAD radar gate now also guards these flights: hold outside, turn back on timeout, low fuel or SEAD gone. Briefing and debrief lines added.
- Smoke: new `check_77_strike_behind_sead`.


## v0.41.157, CAS task force stops at the contact point

XO (2026-10-27, "go on cas fix light"). From his 15:38 run: the A-10s killed 11 of 19 red units in 3 minutes, but the friendly task force arrived about 12 minutes later (DCS ran its off-road column about 36% slower than planned) and then drove 2.5 km past the red column.
- The task force now stops 400 m short of the contact point on our side and holds, weapons free (a dug-in garrison target: 2 km short, as before), and drives 1.3 times the planned speed (`CAS_TF_SPEED_MARGIN`, judgment call, one run's measurement; the speed is capped at 8 m/s).
- Smoke: new `check_76_cas_task_force`.


## v0.41.156, Red zerg, part 2: the mass raid in the mission

XO (2026-10-27, "go on next item, high"; "I want to be annoyed by constant scrambles on L3"). The mission side already built big raids in several groups with SEAD and DEAD groups ahead of them (part 1 made L3 raids 6 to 8 bombers, 12 on a wave day); this makes them proper zergs.
- Escorts: one fighter per two bombers (judgment call, XO's 1:2), and a raid of 8 or more bombers (`mass`) gets two more as a sweep that flies ahead of the bombers (`packages._land_raid_plan`, `raid_spawns._spawn_raid`). Never more than the escort wing has serviceable. Before, a raid always had 4.
- L3 scramble chance per sortie 21% to 33% (`emerg_chance`; still never two sorties in a row). L1 and L2 unchanged.
- Measured (L3, SEAD and DEAD groups included): a normal raid is about 210 units, a 12-bomber wave raid about 235 to 250 (the builder trims wrecks and the latest packages to stay at the 250 limit).
- Smoke: new `check_75_mass_raid_build`.
- XO's three runs on v0.41.154 (CAS, a big AI-only scramble, a SAM-heavy L3 sweep) are kept as reference. Watch item from them: on the CAS run the blue tanks killed one red ground unit and the two columns then drove past each other.


## v0.41.155, Red zerg, part 1: red can win (ground and war model)

XO (2026-10-27, "red needs the zerg for a chance ... high effort, go in your order"). This is the war-model half; the mass raids you fly come next (part 2). A NEW CAMPAIGN is needed to see it (the ground state gains `flown_day`; older saves load but start the clock at day 1).
- Idle surge (`ground.surge`): the longer your squadron has not flown, the harder red pushes. After 2 idle days it adds `red_surge` (L1 0, L2 0.03, L3 0.08) per day, up to x3 (`SURGE_CAP` 2.0). It multiplies red's reinforcements, attack chance and raid rate. Any flown sortie resets it (`tempo.record` stamps `flown_day`). Judgment call, tuned on sims.
- Mass raids (L3 raid rate 2.0 a day, was 0.7; size 6 to 8, was 4; L2 rate and size unchanged): a raid of more than 4 is settled aircraft by aircraft (some stopped, the rest bomb), the odds of stopping it fall with its size, and damage counts the first four aircraft in full and the rest at half (`raids.eff`). Small raids are settled exactly as before. Massed-wave days (`raid_wave`: L2 10%, L3 25%) make that day's raids 1.5 times bigger (`raids.wave_mult`).
- Red strikes on our depots and fuel in the background (`red_supply_strikes`: L1 1, L2 2, L3 4 a skip day). Our supply now really drops (sims: 0.57 to 0.85 on L3), which lowers our reinforcements and our blue AI strikes (the AI CAS chance is now multiplied by our supply).
- Rear feed (`red_rear_feed`: L2 0.02, L3 0.05): each night red's rear sectors move that share of their strength one sector forward, scaled by supply, never below 15.
- Fix: a trickle of reinforcements in our last sector kept a field from ever falling. A field now falls (and a red base is taken) when the holder faces a force under 30% of its own (the no-hunt ratio), for both sides.
- Sims (4 seeds, 130 day cap): L3 idle = DEFEAT on days 78 to 103 (all four); flying every 3rd day wins at day 87; flying daily wins at day 72 (before: 66 to 73). L2 idle still wins at about day 31 (the war is too short for the surge to bite; gentle on purpose). L1 unchanged.
- Smoke: new `check_74_red_zerg`.


## v0.41.154, L1 gets museum-piece SAMs; Ctrl+Space only in AI-Test

XO (2026-10-27, "the more SAMs the merrier ... medium"). Story premise: a shadow sponsor keeps the insurgents properly funded and armed, so their old SAMs work at full health.
- Level 1 air defence (`difficulty.py`): SA-2 and SA-3 join the AAA and MANPADS mix, and 4 sites per field instead of fewer. They are old sites, so the rebuild stays slow and there is no EWR (iads 0.15). Judgment call: SA-2/SA-3 are real 1960s-era exports and still fielded by irregulars' sponsors; the numbers are tuned to give SEAD / DEAD work for every airframe without stalling the planner.
- Sims (8 seeds, none and good play): L1 still wins every run, median day 23 (was about 22).
- Story: the L1 Background mentions old but working SAM batteries kept in repair across the border. Russia is not named on L1.
- Ctrl+Space (XO) now works only in AI-Test, not in a normal campaign (`gui/app.py`).


## v0.41.153, Story wording and Ctrl+Space everywhere

XO (2026-10-27). Merged #217 before this landed, so it is its own change.
- Story text (XO): the "In this scenario" opening is gone from the three Backgrounds.
- Ctrl+Space (v0.41.151's developer secret) now works from any page: a focused list or text box used the key itself and swallowed the shortcut, so it is caught by an application-wide key filter instead.


## v0.41.152, Campaign Revamp Stage C4: polish

XO (2026-10-27, "go, medium C4"; nothing else to change from his skip-day runs yet). Display only; the war is untouched.
- Overview: a "Today's tasking" card: the day's packages by kind (CAS, strike, SEAD / DEAD, counter-air, patrol, fleet defence), how many your squadron can fly, or why it has none (`overview_detail.tasking`). There is no "supply is low" stand-down: the planner has no such rule, so the card only reports what the planner gave. After the war it says so.
- Forces page: the aircraft counts of both sides are one quiet detail line at the top ("jets no longer decide the war"); the ground-war, air-wing and asset tabs and columns use the opponent's label (Russia / CRA) and "Coalition" instead of Enemy / Friendly.
- Smoke: new `check_73_tasking_line`.


## v0.41.151, Window size and position, and a developer shortcut

XO (2026-10-27, "fit on a 1080p screen with some margins, centered ... remember size and position, with reset"). Light change in `gui/app.py`.
- The window first opens at 90% of the usable screen (the taskbar is left out), at most 1700 x 960 and never under the 1100 x 700 minimum, centered on the screen it opens on. On a 1080p screen that is about 1700 x 936. (It was 1280 x 820 wherever Windows put it.)
- It remembers its size and position when you close it (new setting `window_geometry`, Qt's own saved geometry, so a monitor that has gone is handled by Qt). File > Reset window size and position goes back to the default and centers it.
- Developer secret (XO): Ctrl+Space skips the day at once with no questions and no result box, so you can watch the Overview and its map move. It does nothing while a sortie is built or once the war is over. Not in any menu.
- Smoke: new `check_72_window_size`.


## v0.41.150, Campaign Revamp Stage C3: the stories, and the ending

XO (2026-10-27, "go C3, medium"). New `sqe/story.py`; the text lives in the theatre pack (`caucasus.json`, `stories`, one entry per level). A theatre without `stories` keeps the old texts.
- THE STORIES: one per level. Levels 2 and 3 are Russia against Georgia and a US-led coalition; level 2 is level 3's story with a smaller Russian force, the victory at Sochi and a smaller counter-attack. Level 1 is the fictional Coastal Republic Army (CRA). Each has the Background, the Intent and a "Now" line for every posture label and ending (Ceasefire on L2 and L3, Insurgency broken on L1, Defeat). No named leaders or parties, no Tomcat line (the carrier air wing or the Air Force, joint campaign), and no foreshadowing: the counter-attack is not mentioned until the last objective falls.
- The opponent's short label is used on the Overview and in the tabs: Russia, or CRA (it was "Enemy").
- WAR LOG BEATS (so the log reads as the story so far): the opening, each base falling (Sukhumi, Gudauta, Sochi, Gelendzhik, Krymsk), a base retaken by the enemy, the counter-force arriving (L2, L3), one of our airfields falling and coming back, the win and the defeat. Hooks in `ground.py` (`_check_red_bases`, `check_falls`, `_counter_arrives`, `_update_win`), `war.update_status` and the campaign start.
- THE ENDING (XO's report: after the victory the flights were listed and the buttons looked clickable): once a campaign is won or lost the Missions page shows the ending instead of the tasking order, the Warnings card and the takeover warnings are gone, and the Ground odds card shows the ending.
- Smoke: new `check_71_story`; the C1 and C2 checks follow the opponent's label.


## v0.41.149, Campaign Revamp Stage C2: Situation panel, detail tabs, scramble fix

XO (2026-10-27, "go C2, high"). New `sqe/overview_detail.py` (data only; the GUI draws it).
- SITUATION PANEL (Overview, top left): the full Background text, scrollable, and the Intent, in a panel with a Hide / Show button; the posture label and one "Now" line (the posture's line; at the end of the campaign the ending text) stay pinned at the bottom open or closed. It starts open and remembers the last state (new setting `situation_open`). The text is still the one per-theatre background (its last paragraph, the commander's intent, is shown as the Intent); the per-level stories are Stage C3.
- DETAIL TABS (Overview, bottom left; they replaced the long sector list): Ground (takeover clock, each base, a row per sector with battalions each side, front history from the war log: falls, retakes, counter-force), Supply (every fuel farm and depot of both sides with health and state: intact / struck since last night, no repair tonight / repairing, days to full / destroyed, days to rebuild; captured sites say so), Air defence (IADS per side, SAM batteries in transit with the days, every SAM site and radar with health and state), Air (the four air-tempo values and the BARCAP cover lines).
- SCRAMBLE NOTE FIX (XO's report): cancelling a sortie that came with a scramble and pressing Fly again no longer forgets the scramble. Building the sortie had used the emergency up (its package was added to the day's plan, the raid record marked, and your own package maybe postponed) and the cancel never gave that back. The pending sortie now keeps a copy of the plan, the raid record and the log length from before; Cancel (and Discard and rebuild) restores them, so the scramble popup comes up again.
- Smoke: new `check_69_scramble_undo` (it fails without the fix) and `check_70_overview_detail`.


## v0.41.148, Campaign Revamp Stage C1: the Overview figures

XO (2026-10-27, "please go C1, high"). New `sqe/posture.py` holds every Overview figure; the Overview and the briefing both read it. The war itself is unchanged.
- POSTURE replaces the three phases (`narrative.PHASES` is gone; `narrative.phase()` now returns the posture). Labels as XO agreed: Offensive, Consolidating, Holding, Under pressure, Last stand, Counter-force, and the endings Ceasefire (L2, L3) / Insurgency broken (L1) / Defeat. Order of the rules: counter-force attacking, then Under pressure (a Coalition field fallen, a fall warning, or a taken base under attack), then Consolidating (takeover clock running or counter-force on its way), then Last stand (the next objective is the last one), then Offensive (our force at the front is at least 1.3 times the enemy's) or Holding. The one-line text under each label is a placeholder; Stage C3 writes the stories.
- THE FRONT card: stage x of y (taken bases + 1), the next objective, each base taken / next / enemy, and any Coalition field lost.
- GROUND ODDS card: our frontmost sector against the enemy's, in battalions (10 strength points = one battalion; a full sector is ten), with a word: holding (ratio 1.3 or more), even, losing (0.77 or less). Judgment calls (the defender factor `ground.DEFENDER` is 1.25).
- WARNINGS card (hidden when empty): "X falls in about N days" (a Coalition field when the sector two in front of it or nearer is held by the enemy with none of ours there; a line moves about a sector a day), "X is under attack" for a base we took, "the enemy counter-force arrives in N days" / "is attacking", "one of our airfields has fallen: a second loses the campaign", "takeover under way: our next attack in about N days".
- SUPPLY card: a percentage (55 to 100) per side plus a word (good 90+, adequate 75+, strained 62+, critical); the bands are judgment calls.
- AIR DEFENCE card: IADS % per side and the SAM batteries in transit with the days to the first.
- REMOVED: Coalition air %, Enemy air %, Armored advance %, "Enemy command posts", the old three-stage front text, the "Phase n" pill (it shows the posture), and the carrier's damaged-deck line on the Overview (the deck still cuts launches; XO wants no carrier line).
- The briefing situation uses the same lines (front, odds, warnings, supply, air defence) instead of the aircraft counts.
- Smoke: new `check_68_overview`.


## v0.41.147, Air tempo

XO (2026-10-27, "the player flying would improve the odds of the background jobs ... incremental and capped ... indicated in the debrief"). New `sqe/tempo.py`.
- Four job kinds: CAS, STRIKE, DEAD (SEAD / DEAD / Standoff) and AIR (sweeps, patrols, intercepts). Each has a tempo, an additive change to the chance that a background (AI) package of that kind gets the job done, and to the ground war's abstract AI close air support.
- A flown sortie is graded the way the story already is (great / good / mixed / bad) and moves its kind's tempo by +5 / +3 / 0 / -4 points; capped at +-20 points; it fades 3% a night, so the edge goes if you stop flying that job. Saved with the campaign (older saves load with none).
- The debrief gets a line, e.g. "Air tempo, close air support: +5% (now +9%)", or "unchanged ... (at the cap)".
- Where it bites: `WarSimulator.odds` (strike, CAS and the other generic jobs, plus the SEAD-escorted supply strike), `sead_p` (SEAD / DEAD), the Fighter Sweep odds, and the ground war's abstract AI strikes (`TEMPO_GROUND_GAIN` 2: the CAS tempo counts twice there). The raid-intercept rolls are not touched.
- All step sizes, the cap, the fade and the gain are judgment calls (no source).
- Sims (8 seeds, L3): idle about day 78, every third day 73, daily CAS play 66. L1 and L2 stay inside their targets (about 22 to 23, and 29 to 30). The sims still show no defeats, so the "idle wins about 50%" goal needs red to be stronger; left for XO's flown tests.
- Smoke: new `check_67_air_tempo`; the debrief path check asserts the tempo line.


## v0.41.146, Campaign Revamp Stage B4: Level 1 raids

XO (2026-10-27, "go, medium"). Which rule blocked L1 raids: every airfield, depot and garrison of ours sits under a live Patriot / HAWK, and red raids a covered target only with a Su-24M wing that can field a SEAD group (v0.41.125). Level 1 has no SEAD (`raid_arm` 0), so the only raids it ever planned were on a contested sector outside the cover: about 5 of 31 drawn raids in a 40-day probe, none on a field, depot or garrison.
- New difficulty setting `raid_banzai` (Level 1 only): the insurgents go in unsuppressed on covered targets. The batteries shoot at them (the existing raid resolution and mission), so most raids cost red jets; judgment call, no source.
- L1 `raid_rate` 0.15 to 0.25 a day (one raid every four days; XO's open item, my default).
- Probe after: 52 of 52 drawn raids find a target on L1 (was 5 of 31). L1 sims still win around day 22 to 23, no defeats.
- Smoke: new `check_66_l1_raids`; `check_31wd` now expects an L1 raid on a covered field to be allowed with no SEAD.
- No other tuning needed: all three levels sit inside the days-to-win targets after B1 to B3.


## v0.41.145, Campaign Revamp Stage B3: detachments and the no-hunt thresholds

XO (2026-10-27, "your defaults. Please go B3 on high."). The detachments along the road already exist as the sectors of the push: each has a red and a blue force and a dug-in forward position (`rfwd_N` / `bfwd_N`, v0.41.102), so the red-side sectors are Sochi to Gelendzhik 4, Gelendzhik to Krymsk 1, Gudauta to Sochi 2, Sukhumi to Gudauta 1 (it was 2; XO asked for a second look and the plan said 1 for the 54 km leg): 8 on L3 and 3 on L1 and L2, the plan's 7 to 8 and 2 to 3. The push now has 8 / 8 / 13 sectors in all. No new unit types. What B3 adds is the rule that nobody hunts the last unit:
- A sector is lost on a threshold: a force under `BREAK_RATIO` (30%) of the force facing it withdraws that night, for both sides, in a shared sector and across a quiet line. Nothing has to be destroyed.
- A sector red has already lost on that rule is not offered as a CAS job (it is beaten; the fight ends tonight). The planner's `engaged` and the new `broken` flag in `ground.info`.
- A depot, fuel farm, command post or SAM site at or under `DOWN_HEALTH` (30%) counts as down: the planner does not offer it, a down SAM no longer gates strikes, and the route map stops drawing its ring. It mends on its own timer.
- Effect on pacing (AI-only sims, 6 seeds, with the 8 / 8 / 13 sectors): L1 about day 23, L2 about 30 to 32, L3 about 72 to 74 (daily play inside the 57 to 77 target). Idle and daily still look alike, which is the air-tempo item.
- Numbers (30%) are a judgment call from the plan ("about 30%").
- Smoke: new `check_65_no_last_unit_hunt`; `check_08` picks a DEAD package whose strike flight the player can fly; `check_31x` sets up a real fight (the start values leave red under 30% of ours on L1/L2, which is now a beaten sector).


## v0.41.144, Campaign Revamp Stage B2: depots and the supply loop

XO (2026-10-27, "go with B2 as planned. High."). Depots and fuel on both sides now matter: they feed the ground war, they can be struck, they mend on a timer, and they change hands with the bases.
- Sites: red gets a fuel farm and a depot at each base of the push (Sukhumi, Gudauta, Sochi, and on L3 Gelendzhik and Krymsk; Level 1 has them at the fields it has) besides Beslan and Nalchik; blue gets a rear depot next to the forward one. Counts and places are judgment calls.
- Supply is stock over the count a side started with, not an average of what is left: a captured site lifts the captor (capped at 100%) and lowers the old owner (floor 55%). L1 red keeps its 70% floor. L1 red now starts at 100% instead of 85%.
- Captured sites change sides with their stock, no fade, when a base falls (red's to us, ours to red) and go back on a retake. Both sides can still raid or strike what the other holds.
- Repair timer: a destroyed site is back in 6 days at 100% supply, about 11 at 55%, none on a night after it was struck, skip days count. (Judgment call: XO's baseline of 6 days.)
- Supply strikes under SA-2/3/6 cover go out with a required HARM escort (as CAS does), at the escort's salvo-size odds; under an SA-11/SA-10 belt they still wait for a DEAD. Escort missing = the job waits.
- Skip days run a background supply-strike round for both sides (blue 2 tries on red, red 1 or 2 on us), with a 50% chance in the open, 20% under escortable cover, none under a long-range belt.
- Ground format v3: v2 saves are refused ("start a new campaign").
- Sims: L1 about day 27, L2 about 32 to 35, L3 about 83 (idle and daily the same, as before: the sim does not model the player). A 120-day trace on L3: red supply falls from 100% to 59% as bases fall, blue stays at 100% from the captures, no spiral.
- Smoke: new `check_64_supply_loop`; `check_35` accepts a 2-ship sweep when the squadron has only two jets free.


## v0.41.143, Campaign Revamp Stage B1: the push

XO (2026-10-27, "go on B, high"). The ground war is now a march across red's airfields, and victory is by ground only.
- The front line is a chain of airfields: Krymsk, Gelendzhik, Sochi-Adler, Gudauta, Sukhumi-Babushara, then our Senaki and Kutaisi. Levels 1 and 2 have 9 sectors (Sukhumi, Gudauta, Sochi), Level 3 has 14 (Gelendzhik and Krymsk too). Theatre data: `front.chain`, `leg_zones`, `stages`, `victory`, `counter` in `caucasus.json`.
- A red base falls when we hold its sector and red is gone from it; red retakes it by the same rule. When one falls: its field, SAM, EWR and garrison are zeroed (depots, fuel and command posts wait for B2), its squadrons move to the nearest standing red wing with 30% lost.
- Takeover clock: after a base falls our next attack waits 9 days and red's own attacks wait 3 (judgment calls).
- Last counter-force: at Krymsk on L3 (60% strength) and Sochi on L2 (35%); L1 has none. It arrives 3 days after the base falls and presses for 6 days. Victory needs the victory bases (Sochi on L1/L2; Sochi AND Krymsk on L3) and the counter-force beaten. No hunting the last unit.
- Blue's own abstract air strikes (the AI flights nobody flies) work the red sector facing us: `AI_CAS` 3 / 2 / 3 a day at 55% for a 15% cut (judgment call, from the toy model).
- Red reinforcement per day: L1 3.5, L2 5.6, L3 7.0; blue 7.0 on all levels. L3 `red_attack` 0.8. Front columns no longer regenerate through the generic nightly repair (it made red a wall).
- Planner: CAS targets a sector that is engaged (in contact, or facing our force across the line).
- Old saves are refused: "start a new campaign" (ground format v2).
- Sims (8 seeds, AI only): L1 about day 26, L2 about day 34, L3 about day 90. L3 is inside the idle target but over the daily-play one: the sim does not model the player enough. The "air tempo" idea (flown results nudging the AI flights' odds, capped) is next.
- Smoke: new `check_63_the_push`; `check_19`, `check_20`, `check_28`, `check_31g`, `check_31wf`, `check_47` updated for the 9/14-sector war and for days whose first package differs.


## v0.41.142, Campaign Revamp Stage A3: red's air roster by type, not by dice

XO (2026-10-24 to 10-27, the Revamp plan). Red now starts each level with a fixed ROSTER of jets per type, placed by rules, instead of a total split over fields with a random type per field. New module `sqe/redroster.py`.
- Numbers (judgment calls, no public source; the plan's zerg sizes): Level 1 44 jets (14 fighters: MiG-21Bis 6, MiG-23MLD 5, MiG-29A 3; Su-25 20; Su-24M 10). Level 2 128 field jets (MiG-31 7, MiG-29S 12, MiG-29A 22, MiG-23MLD 11, Su-25 52, Su-24M 24) plus a Mozdok Tu-22M3 wing of 11 and an Su-27 escort squadron of 8. Level 3 256 field jets (MiG-31 14, Su-27 24, MiG-29S 28, MiG-29A 20, Su-25 110, Su-24M 60) plus 30 Tu-22M3 and 16 Su-27 escorts. The old totals were 20 / 90 / 150.
- Where they go: in proportion to the theatre's `wing_weight`, capped by what each field can park (the DCS parking count) and, for the heavy types (MiG-31, Su-27, Su-24M), by its heavy spots. Su-24M leans to the deeper fields (weight x (tier - 1)). Every field keeps at least four fighters, and nobody gets a lone jet of a type (it joins the biggest block of that type).
- Long-range depth gradient (XO 2026-10-24): of a field's MiG-31 + Su-27 jets, 75% are MiG-31 at fringe fields (tier 2), 50% in the middle (tier 3), about 15% deep (tier 4), so the Su-27 feels prized and a deep MiG-31 pair is the "spice". L3 check: MiG-31 share 0.71 at the fringe, 0.53 in the middle, and a pair at Maykop deep (a lone jet is topped up to a pair from the biggest block).
- MiG-31 is now a proper red type: R-33 / R-40 loadout (the heavy-missile list gained them, it used to carry R-60 only), quality 0.67 and intercept reach 230 nm (judgment calls), and it counts as a long-range red jet in the red air picture.
- Raids on blue airfields: with Su-24M spread thin, the nearest red wing could hold only 2 of them, too few for the SEAD group a covered target needs, and the planner then dropped the raid (the Level 2 raid-rate check saw none in 60 days). `raids.reach_for` now takes the level and passes over a wing that cannot field that group for the nearest one that can.
- Mozdok bomber wing and escorts are bigger on paper; raids are still capped (`MAX_RAID` 12 on L3, 4 on L2), so bigger raids and the 1:2 escorts wait for the mass-raid step. The Tu-22M3 wing of 30 is more than the 14 Tu-22M3 parking slots at Mozdok; accepted (XO: nobody launches them all).
- Level 1 has no MiG-31, Su-27 or MiG-25; MiG-21Bis is Level 1 only.
- Smoke: new `check_62_red_roster` (per-level totals and fighter counts, bomber wing sizes, parking and heavy caps, two or more fighters per field, no lone jets, no MiG-25, MiG-31 only on L2/L3, the gradient falls with depth and is above zero deep, MiG-31 loadout). `check_01` now also counts the standby pair as HAVCAP / base CAP cover (the new roster changed the merged mix and the check had ignored it).
- A 40-day no-player air sim: Level 1 and 2 still end in VICTORY on day 41, Level 3 stays ACTIVE with red's air not bleeding (the same as before: the sim has no player sorties).

## v0.41.141, Campaign Revamp Stage A2: the Level 1 insurgents never drop below 70% supply

XO (2026-10-27): on L1 the opponent is resupplied across the border by night, so killing its depots cannot starve it completely. `ground.supply("red")` on Level 1 now has a floor of 70% (`L1_RED_SUPPLY_FLOOR`; Levels 2 and 3 keep 55%; blue is unchanged on every level). It reaches everything that reads red's supply: the daily ground fight and reinforcements, SAM rebuilds and SAM-order transit time (v0.41.140). Judgment call: a toy-model run (2026-10-27 notes) showed the floor does not change who wins on L1, it only slows the grind. Today L1 has no red depot or fuel site at all (red supply is a flat 85% there), so nothing changes in play until Stage B adds the depots; the rule is in place for them.
- Smoke: new section `check_61_l1_red_supply_floor` (every red depot and fuel site gone: L1 0.70, L2 and L3 0.55; blue 0.55 on all levels).

## v0.41.140, Campaign Revamp Stage A1: SAM orders are a fixed feature

XO (2026-10-27). Both sides' SAM orders (`sams.red_orders`, `sams.blue_orders`) now always run overnight, at every level. They used to sit behind two Experimental-tab checkboxes ("Red SAM borrowing", "Blue SAM borrowing"), both OFF by default, so in a normal campaign no battery ever moved.
- The settings `borrow_red` / `borrow_blue`, the two checkboxes and the war simulator's `borrow` switch are gone (old settings files still load; the two keys are ignored).
- A battery moves by air, so it arrives in `transit_days(supply)` days: 1 at 100% supply, 2 in between (about 66% to 89%), 3 at the 55% floor (was a flat 2). Judgment call: no public figure; the shape is XO's "1 to 3 days by supply". The sender's supply is red's or blue's own `ground.supply`.
- The chance roll is gone for both sides (it was the side's supply as a probability): supply now sets the time, not whether it happens. This also stops the war sim drawing a random number per order.
- Not yet: the planner weighing what the sending site leaves exposed (queued for later).
- A 30-day check without a player: L1 no orders (no destroyed sites), L2 12 to 14 orders, L3 12 to 14, all arrived.
- Smoke: `check_31j_borrow_switches` is now `check_31j_sam_orders_always_on` (settings gone, transit table, both sides run in a skipped day); the red and blue order checks wait for the order's own due day.

## v0.41.139, engagement circles slice 2: the long-range TARCAP stands behind and aside of the short-range escort

XO (2026-10-27, engagement circle diagram): short-range jets forward, long-range jets behind and to one side. Measured first on the identity set: no package has a short- and a long-range TARCAP together (one TARCAP flight per package, and the planner gives it a long-range jet first), so there was nothing to stagger there. The pair that does exist is the TARCAP (long-range first) and the package ESCORT (short-range first): in 34 packages, 24 of them had both on one and the same point (the SAM-free runs), the other 10 (DEAD, JSOW) sat 30 nm apart already.
- New `FighterStations._stagger_stations`, run once after the stations are planned: where a TARCAP and an escort of different range classes (`LONG_RANGE_A2A`: F-15C, F-14B) stand within `LRA_SPLIT_MIN_NM` (12) of each other, the long-range station moves `LRA_BACK_NM` (8) back from the target and `LRA_SIDE_NM` (6) to one side, the side with more room to the SAM rings; smaller moves if a ring is in the way, none if nothing is clear. About 10 nm apart, the long-range one about 8 nm farther from the target (judgment call: the sweep circles are 25 and 15 nm; the side gap is for friendly fire with active missiles in the air, DCS behaviour unverified). Same class, or already apart: nothing moves. The station tuple keeps its other fields. Applies to your own TARCAP or escort route too.
- A first version put the long-range jets "away from red"; where red's nearest patrol sat on our side that landed one 3 nm from the target, so "behind" is measured from the target.
- Left as they are: DEAD and JSOW packages, where the SAM rings already put the two stations 30 nm apart (there the TARCAP is the nearer one to the target by up to 8 nm; no change).
- Smoke: new section `check_60_long_range_tarcap_stands_behind_the_short_range_escort` (24 stations moved, each farther from the target, at most 15 nm). The identity tool shows changed TARCAP stations, routes and circles in those packages (expected).

## v0.41.138, engagement circles slice 1: the TARCAP circle meets the BARCAP circle

XO (2026-10-27, engagement circle diagram). Measured on the identity set first (84 missions, 120 TARCAP circles): matched inside each mission, every TARCAP has a BARCAP circle, and 9 of them left a strip of 0 to 9 nm between the two circles (my first count, 33 gaps up to 37 nm, paired circles from different missions and was wrong).
- A TARCAP's cover circle now takes in a point just inside the nearest BARCAP circle's edge (`TARCAP_BARCAP_OVERLAP_NM = 4`, so the circles overlap by about 2 nm; judgment call). It sits after the shooters' launch points and the station in the list and before the forward reach toward red, so if one circle cannot span everything it is the forward reach that gives way. Result on the same set: 9 gaps down to 4, the largest 4 nm (SAM trim or the 35 nm cap; left alone).
- `SupportCaps._barcap_circles`: works out the BARCAP circles of the mission before any flight is built (same route plan and SAM trim the flights use), so build order does not matter. Nothing it does is kept.
- A TARCAP is wanted at the sweep size for its type: 25 nm for the long-range shooters (F-15C, F-14B), 15 nm for the rest (was 20 nm for all). The launch points still make it bigger, so a short-range jet's circle is rarely 15.
- The player-facing label of the base CAP is now "BARCAP" (briefings, kneeboards). The internal tag `BASECAP` stays.
- Not done (design stays in the notes): short-range jets forward / long-range jets behind and to the side. Both types already share one station per package and the launch points decide the circle, so it needs a station per flight type; only 11 of 59 missions in the set have mixed types. Timings were left alone: the BARCAP is up for the whole package and the TARCAP holds to TOT + 5 min, no gap seen.
- Smoke: new section `check_59_tarcap_circle_meets_the_barcap_circle` (38 TARCAP circles in F-15C, F-14B and Hornet missions: no strip over 1 nm; fails on the old code). The identity tool will show changed circles and the new label (expected).

## v0.41.137, the CAS target column stays at the CAS point

XO (2026-10-27): last night's L1 CAS mission, the A-10s' target was off by some distance and they never touched it. `mission_builder._spawn_cas_support` moved the enemy column up to 10 km back and drove it 13 km at 7 to 8 m/s so it would be at the CAS waypoint at the TOT (the plan put it within 1.4 to 1.9 km on paper), but DCS's real speed (slopes, a long mixed column, stopping to fight on the v0.41.39 weapons-free orders) decides where it is. Now:
- The column is built at the CAS point and only creeps 1.2 km toward your side (at most 3.5 m/s); the friendly task force starts at most 6 km from the contact point (was up to 10 km).
- The support spawn uses the CAS target's OWN group and centre, not "the last armour group spawned" (a CAS package also builds the target's defenders, so a garrison or neighbouring column built after the target could take its place; the A-10s' own attack task already named the right group).
- Dug-in forward garrisons were already on the point (2 to 22 m) and are unchanged.
- Smoke: new section `check_58_cas_column_stays_at_the_cas_point` (12 campaigns, every AI CAS mission: target group is the package's own, within 400 m of the CAS waypoint, creep under 2 km). The identity tool will show CAS missions changed (expected).

## v0.41.136, Bug B: the war sim's red air cover counts fighters only

XO (2026-10-27, Campaign Revamp prep). `war.py` added `0.05 * every serviceable red aircraft` to the defence of a strike or a DEAD (two places), bombers and strikers included. With the planned striker zerg that would have made every strike harder. It now counts red's serviceable FIGHTERS only (`ENEMY_FIGHTERS`), at 0.0765 each (fighters are about 65% of red's jets today, so the term stays about where it was; judgment call). New helper `war._air_cover`. No mission-building change. Smoke: war-sim sections.

## v0.41.135, reactive dispatch and emergencies are always on

XO (2026-10-24): the two Settings checkboxes "Reactive dispatch" and "Emergencies" are gone; both behaviours are always on (the defaults). A settings file that had either off is set back on at load. The settings fields stay internal (the smoke test still switches them). GUI and settings only.

## v0.41.134, the Resume button looks like a button

XO (2026-10-24): the Missions pane's "Resume pending sortie..." button was a red outline that did not look clickable. It is now a solid Fly-blue button, "Resume sortie in progress" (same style as FLY; shown only while a sortie is waiting for results). GUI only.

## v0.41.133, Settings and notice clean-up

XO (2026-10-24):
- Settings > Campaign: the Weather description now sits under the Weather dropdown (it had drifted below the AI Skill text).
- The "AI TARCAPs, escorts and sweeps stop short of live SAM cover" checkbox is gone: the behaviour is always on (switching it off made the AI go banzai). A settings file that had it off is set back to on at load; `fighter_standoff` stays an internal option (the identity tool still uses it).
- The "Built with notes" popup after FLY is gone; the same notes appear on the waiting screen, now below the Launch / Marshal / PUSH / TOT line (last in the box).
- The emergency scramble popups show their game-mechanics paragraph (what happens to your tasking, who settles it) as a small grey "SQE NOTE" label over grey italics in parentheses; the in-universe lines are unchanged. Other text is unchanged.
- Smoke: GUI sections.

## v0.41.132, no RCV point on the player's own carrier flight

XO (2026-10-23): the v0.41.127 RCV point (30 nm from the boat, 10,000 ft) was added to every flight going home to the carrier, the player's too. It is now added to AI flights only (and to the player's flight when the AI flies it, the all-AI test), as the land-field recovery point already was. `mission_builder._home_leg`. Smoke: carrier-return section.

## v0.41.131, the unit limit counts the whole mission again; merge radius 15; "later packages" setting

XO (2026-10-23): "put back the unit limit", radius 15, the +30 minutes adjustable in 5 minute steps, drop the latest-starting package first.
- `merge_max_units` (250) counts the WHOLE mission, merged packages included (v0.41.104 had exempted them). The 500 ceiling in `sqe/data/limits.json` stays in the code but is dormant (250 is lower).
- Over the limit (`Session.fly`): returning (ruin) flights go first; then `Session._drop_one`: the package that starts latest, a tie by the one further from the centre; a Fighter Sweep or a folded raid scramble (FLEET_DEFENSE) last; the mission is rebuilt each time. Wrecks are trimmed by the builder as before (furthest first), now against the whole count. Your own flight is never dropped; a base mission already over the limit just stays over it.
- Default merge radius 15 nm (was 25; a settings file still on 25 moves to 15 once).
- New setting `merge_fwd_min` ("Later packages", default 30, 0 to 60, 5 minute steps) replaces the fixed 30 in `merge_candidates` and the emergency scramble's hidden-package window; "Earlier packages" also steps by 5.
- Smoke: `check_31n` rewritten (drop order, tiny limit, later window, defaults). Untested in DCS.

## v0.41.130, Overview: ground-war text moved left, blue SAM rings, damage-aware rings

XO (2026-10-23): give the map its space back and let the rings show what is changing.
- The ground-war sector lines, BARCAP cover lines and bomber lines moved from above the map to a "GROUND WAR AND PATROLS" card under the conflict text on the left.
- Map: blue Patriot (40 nm) and HAWK (25 nm) rings from `state.blue_sams` in blue (same ranges as the red raid planning, `raids.PATRIOT_NM` / `HAWK_NM`); one checkbox, "SAM rings (red / blue)". A damaged site's ring is fainter (health, floor 25 %); a destroyed site has no ring. Ring sizes are still fixed per site type. A "moved" marker is not built: the state does not keep a site's earlier position.
- GUI only. Smoke: UI sections only.

## v0.41.129, red SEAD covers every battery that covers the target

XO (2026-10-23): close the gap left by v0.41.128 (the neighbour's Patriot still shot the bombers after the gate opened). In Georgia the fields are about 20 nm apart: Kutaisi is covered by Senaki's and Kobuleti's batteries too.
- `raids.covering_fields` (every field whose live Patriot, 40 nm, or HAWK, 25 nm, covers a point, nearest first) and `raids.sead_groups`: one SEAD group per covering field. Each gets a pair (4 Kh-31P to blind its radars; judgment call); the wing's spare jets (`available` less the bombers) top the nearest fields up to their `arm_jets` size, nearest first, at most `ARM_MAX_TOTAL` 12 jets in all (judgment call). A wing that cannot spare a pair for each field does not raid that target. `arm_cap` (L2: a pair) now caps one group; the L2 lift at `arm_cap_free` 8 spare jets is as before. `sead_plan`, `pick_aim`, `pick_target`, `overnight` and `packages._land_raid_plan` use it; the package carries `arm_fields` ([[field id, jets]]).
- `raid_spawns._spawn_raid_arm`: a group (or two flights of four for an eight) per covering field, firing from `ARM_LAUNCH_NM` from that field, 600 m apart, names `Raid SEAD n`. The escort / TARCAP cover and the DEAD flights stay with the raided field. A package without `arm_fields` (an older save) sends all its jets at the raided field.
- The gate (`_raid_gate_new`) now opens when the radars of every covering field are dead.
- 40-day sims, 2 seeds, announced raid packages: L1 0, L2 11, L3 9 (the SEAD force is 12 jets at L3). Red raids a clustered field only when it has the jets for all of it; L2 needs 8 spare, L3 six beyond the bombers.
- Smoke: `check_31wg_sead_every_covering_battery`; `check_31wd_red_sead_first` rewritten for the per-field sizing. Full smoke passed. Untested in DCS.

## v0.41.128, the raid gate sits clear of the neighbouring fields' SAMs too

XO's run (v0.41.126): the gate worked (abort at 1294 s, DEAD flights and the escort turned home), but the bombers were shot at the gate. The raid was on Kutaisi; the gate, 48 nm from Kutaisi, lay 28 nm from Senaki's Patriot, which killed RAID-B-3 at 90 s and RAID-D-2-1 at 354 s. In this theatre the fields are 20 nm apart, so a gate measured from the raided field alone is inside a neighbour's reach.
- `_raid_gate_new`: the gate moves out along the way in (4 nm steps, from 48 nm, at most `DEAD_HOLD_MAX_NM` 110) until it is `DEAD_GATE_CLEAR_NM` (8) outside the reach of every live Patriot (40) and HAWK (25) of any field. The gate distance is `gate["nm"]` for the bombers, sweep, escorts, DEAD flights, their TARCAP and the debrief's arrival delay.
- Not changed, to look at next: the gate still opens on the raided field's radars only, and the SEAD / DEAD flights only hit that field. A neighbour's battery that covers the last 20 nm in still shoots at the bombers after the gate opens. Every field here has a neighbour in reach, so planning the SEAD against all covering batteries (or refusing the raid) is the real fix; not done in this light PR.
- Smoke: `check_31l_red_arm` checks the gate is clear of every battery. Full smoke passed. Untested in DCS.

## v0.41.127, carrier flights keep their height until 30 nm from the boat

XO's F-14 flight (Uzi 3) flew the last 65 nm home at 2,000 ft over the sea: its home waypoint (the boat, 600 m) is the next point after the target, and DCS descends to the next point's height at once. Hornets and Tomcats on every carrier return did the same.
- `mission_builder._home_leg`: a flight going home to a carrier gets an RCV point `CV_RCV_NM` (30, judgment call) from the boat on its way in, at `CV_RCV_FT` (10,000 ft, judgment call), then the Land point as before. Skipped when the last route point is already within 40 nm. Airfield recoveries are unchanged.
- Smoke: `check_31wf_carrier_return_height`. Full smoke passed. Untested in DCS.

## v0.41.126, red bombers wait outside the Patriot's reach until the radars are down

XO (2026-10-23): red plans like blue; a raid with SEAD in front of it does not fly into the Patriot / HAWK until the SEAD (and DEAD) have taken the radars down. Hold the bombers at a gate, abort if the radars stay up.
- One gate per SEAD raid (`raid_spawns._raid_gate_new`): a point `DEAD_HOLD_NM` (48) from the field on the way in, one mission flag set when every `Patriot str` / `Hawk tr` of the field is dead, and an abort time `DEAD_GATE_WAIT_S` (1200 s, judgment call) after the Kh-31P launch. The bomber groups, the raid's sweep and its escorts get a "GATE" waypoint there and orbit (`stop_if_user_flag`) until the flag is set, each 250 m above the one before (`GATE_ALT_STEP_M`); the sweep and escorts engage air in their class's circle meanwhile. A group that would appear inside the gate circle (a late raid) starts at the gate instead. The DEAD flights use the same gate (flag, trigger) as before. Raids on the fleet (Tu-22M3) and raids with no SEAD are unchanged.
- The abort now sends every held group to the first leg home, past the EGR point. (v0.41.117's DEAD abort sent them to the EGR point, which sits 20 nm from the field: they would have flown toward the Patriot first. Fixed for them too.)
- Debrief: the Lua (`SQE_GOTO`, new `SQE_GATE_OPEN`) records per group when the gate opened or the group was sent home (`SQE_RGATE`, written to the state file as `rgate`). `apply_debrief`: bombers sent home, or still held when the mission ended, report "turned back at the gate / still held outside the defences; no bombs fell" and the field takes no hit; a gate that opened late delays the arrival by the leg in (`raid_gate_s`).
- Smoke: `check_31we_red_gate_debrief`; `check_31l_red_arm` also checks the shared flag and the abort for the bombers. Full smoke passed. Untested in DCS (the first thing to look at: do the held groups orbit at the GATE point and does the sweep still fight there; does the abort turn them home).

## v0.41.125, red raids: SEAD first, no dice

XO (2026-10-23): "we minimize dice rolls now and stick to intelligent mission planning"; red should not attempt a target under SAM cover it cannot suppress. Red raids on fields had a 60 % (L3) / 20 % (L2) roll for the SEAD group, so many raids flew straight into the Patriot / HAWK (XO's Senaki raid: 4 of 4 bombers shot down, no SEAD).
- `raids.sead_plan` / `cover_field` / `reach_for`: a target within `PATRIOT_NM` (40) of a live Patriot or `HAWK_NM` (25) of a live HAWK is raided only by a Su-24M wing that can field the SEAD group (`arm_jets`, sized by the field's batteries as before). Covered supply sites, garrisons and sectors are not tried (no SEAD is built for them); Su-25 raids do not go in under cover. Uncovered targets need none.
- No roll: `Difficulty.raid_arm` is now on / off (L1 0, L2 and L3 1.0). `pick_aim` and `pick_target` (announced, surprise and scramble raids) drop what red cannot support; `_land_raid_plan` returns no raid for a covered target it has no SEAD for.
- L2 (`arm_cap` 2, `arm_cap_free` 8, judgment calls): the SEAD group is a pair (a DEAD pair behind it) unless the wing has 8 jets spare beyond the bombers, then the full sizing. L3: as v0.41.116 / .117. L1: never raids a covered target (docile).
- 40-day sims, 2 seeds, raids in the log (before -> after): L1 2 -> 0, L2 23 -> 11, L3 38 -> 25 (announced + surprise). Red raids less often and with SEAD.
- Smoke: `check_31wd_red_sead_first`; two older checks adjusted (the raid-kinds build check bypasses the cover rule). Full smoke passed. Untested in DCS. Not in this PR: holding the bombers until the radars are down (the next step).

## v0.41.124, a scramble you do not take is folded in wherever it is

XO (2026-10-23): the mirror of v0.41.121. The mission is built around the package you picked (its circle and window); every unit of the scramble that started in its window comes along, rooted on that package's time.
- `engine.fly`: the CAS / raid emergency is folded into your mission without the merge-circle test (`_inside_merge`). Not when your own tasking is a fleet defence / raid. Unit cap and six-package limit unchanged (the cap trims the furthest units first).
- Smoke: `check_31wc_scramble_folds_outside_circle`; two older checks adjusted (the unit-cap count pins emergencies off, the red call-in check picks a mission with a red call-in: a folded scramble can carry blue call-ins only). Full smoke passed. Untested in DCS.

## v0.41.123, alert pairs: the clock call is no longer dropped, and they dash to the station

XO (2026-10-23 runs, v0.41.122, Standoff DEAD): 0 air-to-air again. Tracks: red alert pairs came within 19 to 28 nm of the F-14 TARCAP and nobody fired (ROE is the DCS default on both sides; not the cause). The pairs were late: Sochi pairs called at 850 to 890 s (detection circle) and on station about 1530 s; Nalchik pairs (120 nm out) took off at 450 s and needed about 1,000 s at 400 kt, arriving after the JSOW release (1333 s).
- `red_air_picture`: a clock call that fell below `ALERT_CLOCK_MIN_S` (60 s) was dropped, so a pair with an early TOT waited for the detection circle. It is now made at the floor time instead.
- The alert pair's INTERCEPT leg is flown at `ALERT_DASH_KT` 500 (was 400), and the clock lead uses the same speed. Judgment call.
- Smoke: `check_31zd` (existing asserts still hold). Untested in DCS.

## v0.41.122, state file: missiles left on the shooter

XO (2026-10-23): "if there's anything you need to track easier you could add it on the state file". Logging only; no mission behaviour changes.
- `debrief` (Lua): every `shot` record gets `left`, the air-to-air missiles the shooter still carries (`getAmmo`, missile category, summed; inside `pcall`). Read it as about one high: DCS may count the missile just fired. Shows when a pair goes winchester. `km`, `alt`, `tg`, `tx`, `tz` were already logged for shots; "hit" records have no range.
- Smoke: Lua syntax check (lupa) and a string check in the hook section. Untested in DCS.

## v0.41.121, a scramble you take brings along the packages that were hidden in your original

XO (2026-10-23): taking an emergency scramble built the mission around the scramble: its merge circle and time window are centred on the raided field and the scramble's start, so the packages listed inside the package you were tasked with never got built.
- `engine.fly`: when you take the scramble, the packages `merge_candidates` listed for your original package (same circle, same list as the Missions panel) are added to the scramble mission if their start is inside the usual window round the scramble's start (-`merge_back_min` / +30 min). The scramble's own finds come first; six packages at most; the usual unit cap trims the furthest. Your original package still goes to the war sim (the AI flies it; later flights are recomputed in the background). Members keep their own start times.
- Smoke: `check_31wb_scramble_takes_hidden_packages`. Untested in DCS.

## v0.41.120, red alert pairs fight at their station and are called in time; the TARCAP circle reaches toward red

XO (2026-10-23 run, Standoff DEAD, v0.41.119): no air-to-air again. Tracks: two alert pairs (Su-27 Sochi, MiG-29A Gudauta) were called at 1040 / 950 s and airborne at 1248 / 1286 s, 140 to 175 s after the TOT (1111 s); they orbited at 22,000 ft 24 nm from the F-14 TARCAP (Uzi 1, 26,000 ft) for about 12 minutes. No shots on either side.
- ENGAGE CIRCLE (`red_air_picture`): the alert pair's `INTERCEPT` waypoint carried only the orbit, so the "engage air" order of its first point was gone after that waypoint (DCS replaces the order list per waypoint; this reading is from the mission file, not confirmed in DCS). It now carries an `EngageTargetsInZone` round the station, `ALERT_ZONE_NM` 40 (the call-in hotspot's size, capped by the CAP engage limit). Probably the reason for "red's pairs watch the missiles blow up" since v0.41.91.
- CALLED BY THE CLOCK TOO: a pair whose station is within `CALLIN_REACH_NM` (110) of its field is also called at `TOT - ALERT_ON_STATION_S (420) - lag - flight to the station`, lag `ALERT_RAMP_LAG_S` 300 (hot ramp; XO's runs 200 to 340 s) or `ALERT_RWY_LAG_S` 120. The detection-circle trigger stays; whichever fires first sets a "done" flag and the other stays quiet (`FlagIsFalse`). A clock call earlier than `ALERT_CLOCK_MIN_S` (60 s) is not made (it would turn the pair into a patrol). Far fields keep the zone trigger only. All numbers judgment calls.
- BLUE TARCAP CIRCLE (`mission_builder`): the circle round the shooters' launch points now also tries to take in a point `TARCAP_FWD_NM` (20) past the station toward red's nearest patrol station or fighter base, last in the list and never bigger than `TARCAP_COVER_MAX_NM` (35). The old circle (about 15 nm) ended 24 nm short of red's station.
- Smoke: `check_31zd` (station engage circle, clock trigger time and done flag).
- Untested in DCS. Open: no red patrols were planned for that window (14:50, L3): cause not found without the campaign save.

## v0.41.119, contest: TARCAP on the threat axis, red guards fight for their sites, red's stations reach forward

XO (2026-10-22 runs, Standoff DEAD Sukhumi): blue always gets lucky, red hums along while its SAMs are destroyed; the F-14 TARCAP sat on the sea side about 90 degrees off the way red comes; red's short-range pairs park over their base and watch the missiles blow up underneath, and some arrive after the time on target.
- TARCAP AXIS (`fighter_stations.axis_station`, used in `mission_builder`'s TARCAP branch after the v0.41.118 pull-in): the station is `TARCAP_NEAR_NM` (16) from the middle of the shooters' launch points on the bearing toward red's nearest planned patrol station or live fighter base (`_red_approach`), swung off that bearing by the smallest step (15 degrees, up to 180) that is outside the SAM rings (SA-10 at 35 nm, as in v0.41.118) and at least `TARCAP_BEHIND_NM` (8) from the JSOW point. The old station stays when no clear point is nearer the axis. In the probe missions the Sukhumi SA-10 sits right on the axis, so the F-14 TARCAP moved from 159 degrees off to the flank (about 75 degrees off); with an SA-10 all round (seed 3, seed 8) nothing nearer is clear and the station is unchanged. 16 nm, the 15 degree step and "nearest clear point" are judgment calls.
- CONTEST RULE (`RedAirPicture._contested`, `CONTEST_NM` 40): a red CAP patrol that guards a SAM site (it has a site link) is called in whatever the odds when the site is within 40 nm of blue's shooters' launch points or of the target. Before, a patrol that was outgunned and not guarding the target's own cluster stayed on its station (`_red_held` "callin"). Patrols with no site link keep the old outgunned rule. 40 nm is a judgment call (about the HARM launch distance, 36 to 40 nm in the runs). Recorded in `_red_contest`.
- RED FORWARD STATIONS (`scramble.red_station_vs`): the call-in hotspot and the alert pair's INTERCEPT station start from `red_station` as before, then move toward the nearest blue shooter launch point, at most `RED_FWD_MAX_NM` (30), stopping `RED_GAP_NM` (20) short of it, to the furthest point still under a live red SAM. A long-range type (the Su-27) may work `RED_EXTRA_NM` (15 nm) beyond its SAM cover; the MiG-29A not at all. With no cover (a station over the field) or no shooter point nothing changes. Replaces v0.41.115's `_hotspot_fwd` (12 nm, stop 30 nm short). All four numbers are judgment calls. The raid alert pairs in `raid_spawns` (red raids on blue) are unchanged.
- NOT done: the alert pairs from the far east fields still launch late (their scramble is the detection circle of their own field); gating red's bombers on the DEAD gate.
- Smoke: `red_station_vs` (under cover, at most 30 nm forward, 20 nm gap, long-range at least as far, no threat = old station, no cover = field), `axis_station` (clear, blocked, none), `_contested`, the TARCAP no further off the axis than before.
- Untested in DCS.

## v0.41.118, TARCAP in closer to the shooters; red site-guard call-in waits for the strike

XO (2026-10-22 run, Standoff DEAD, Sukhumi SA-10): a red Su-27 pair (Bandit 3, called in) killed two Hornets (SEAD Hornet 1-1 and the JSOW Hornet 3-1) at the HARM point and was unopposed for about 150 s: its first P-27 shot at 1141 s, our first reply at 1289 s, the F-14 TARCAP (Uzi 3, 36 nm from the HARM point) never fired. XO's marks on the map put the TARCAP about 24 nm from the SEAD / DEAD jets.
- TARCAP STATION (`mission_builder._plan_stations`, the TARCAP branch): after the step back it now moves toward the middle of the shooters' launch points, 1 nm at a time, until it is `TARCAP_NEAR_NM` (16) from it, never closer than `TARCAP_BEHIND_NM` (8) to the JSOW point and never into a SAM ring. The blocker was the SA-10: the step test holds fighters 53 nm from it (the 48 nm table ring plus the 5 nm margin) while the HARM point is 36 nm from it. For this move only, an SA-10 counts at `SA10_AVOID_NM` (35 nm, the reach measured in the runs; the friendly orbits use the same figure). The other rings keep their margins. In the test mission the TARCAP went from 13 nm behind the JSOW point and 22 to 34 nm from the shooters' centre to 8 nm and about 15.5 nm. 16 and the 35 are judgment calls.
- RED CALL-IN: the site-guard triggers ("call in Bandit N to the SAM site it guards") were missed by v0.41.115: they still fired at 5 s and 42 s with the old stay (558 to 992 s), so the patrols left again before the strike. They now wait until the pair can reach the hotspot 7 minutes before the time on target and stay until 5 minutes after, like the other call.
- Untested in DCS.

## v0.41.117, red's DEAD package: 4 + 4 Su-24M KAB-500Kr, gated on the battery's radars (step 2 of 2)

XO (2026-10-22): after the SEAD package, a DEAD package of 4 + 4 with its own TARCAP and escort that waits for the gate to open.
- PLAN (`PackageBuilder._land_raid_plan`): behind a SEAD group of 4+ jets, `extra["dead"]` = 8 (behind 8 SEAD jets, if the wing has 8 more Su-24M beyond the bombers and the SEAD group), else 4 (if it has 4), else 0; `dead_cover` = 4 fighters of the raid's escort type.
- FLIGHTS (`RaidSpawns._spawn_raid_dead`): "Raid DEAD 1/2", Su-24M with KAB-500Kr (`loadouts.enemy_dead_loadout`: TV-guided 500 kg bomb, seeker 15 to 17 km; Wikipedia), flights of 4. They fly the SEAD flights' way in to a GATE point `DEAD_HOLD_NM` (48) from the field, 8 nm outside the Patriot's 40 nm reach, in `DEAD_HOLD_LAG_S` (60 s) after the Kh-31P launch, and orbit there. The first flight attacks the Patriot group, the second the HAWK group (or the Patriot again), `AttackGroup` with guided bombs.
- THE GATE: a trigger sets a flag when every Patriot search-and-track radar (`Patriot str`) and HAWK tracking radar (`Hawk tr`) of the field is dead (`UnitDead`); the orbit at the gate ends on that flag and the flights go in. If the flag is not set `DEAD_GATE_WAIT_S` (20 min) after the Kh-31P launch, a second trigger runs the Lua `SQE_GOTO` (a `SwitchWaypoint`, the call-in's mechanism) and the flights go to their egress and home: no banzai. Both are judgment calls (the 20 minutes; blue's own DEAD hold is 12).
- COVER: "Raid DEAD Escort" on the gate point and "Raid DEAD TARCAP" 8 nm back, on station 2 minutes before the flights, until 5 minutes after the abort time (the `_spawn_arm_cover` of v0.41.116, now with its own times and stations).
- Not done: the bomber groups keep their own timing (they do not wait for the gate); the war sim does not model the DEAD package in unflown raids; red stand-off weapons (Kh-58, Kh-29/59, Su-25T, ship radars). Untested in DCS.

## v0.41.116, red's SEAD package: 4 + 4 Kh-31P jets with an escort and a TARCAP (step 1 of 2: the DEAD package and its gate come next)

XO (2026-10-22): red's attack groups should follow blue's shape: SEAD 4 + SEAD 4 + TARCAP + Escort, then a DEAD package that waits for the gate.
- SIZE (`raids.arm_jets`): a full-strength Patriot AND a HAWK live: 8 Su-24M, two four-jet flights (16 Kh-31P); the first on the Patriot, the second on the HAWK. Before: at most 4. A short wing steps down 8, 4, 2, none. The sizing for a lone battery is unchanged (2, or 4 against both / a full Patriot). The background (unflown) raids meet `ARM_AD_FACTOR_8` (0.2) of the battery cover for an 8-jet group (judgment call).
- COVER (`RaidSpawns._spawn_arm_cover`): a SEAD group of four or more brings its own fighters (`arm_cover`, 4 jets of the raid's escort type): a pair on the Kh-31P launch point ("Raid SEAD Escort") and a pair `ARM_TARCAP_BEHIND_NM` (8) back along the way in ("Raid SEAD TARCAP"). Both are on station `ARM_TARCAP_LEAD_S` (120 s) before the missiles go, engage air inside their class's circle, stay `ARM_TARCAP_STAY_S` (600 s) after, and go home when out of air-to-air missiles. The numbers are blue's TARCAP numbers (v0.41.115); judgment calls.
- Not done (next PR): red's DEAD package (4 + 4 bombers with its own TARCAP and escort) that waits for the gate (the radar suppressed). Red stand-off weapons are a later PR. Untested in DCS.

## v0.41.115, red patrols called in at the right time and place; fighters in first and closer

XO (2026-10-22 run, no air-to-air at all): red's three patrols were called at 42 s and flew home at 600-1055 s, before the HARMs flew (1093 s). Their circle (25 nm) did not reach the SEAD shooters 36 nm away. The blue TARCAPs sat 56 nm from red's patrols, the escort 32 nm.
- RED CALL TIMING: the call waits so the pair reaches its hotspot `CALLIN_ARRIVE_BEFORE_S` (7 min) before the package's time on target, and stays until `CALLIN_AFTER_TOT_S` (5 min) after it. The detection / alert flag still has to be set too (both must hold).
- RED HOTSPOT: moved up to `CALLIN_FWD_NM` (12 nm) toward the nearest blue shooter launch point, stopping `CALLIN_SHOOTER_NM` (30 nm) short of it, and only while it is still under a live red SAM. Its engage circle is `CALLIN_ZONE_NM` (40 nm, was 25), capped by the CAP engage limit.
- BLUE: `TARCAP_BEHIND_NM` 16 to 8 (the TARCAP holds closer behind the JSOW launch point; still SAM-clear). `TARCAP_LEAD_S` 0 to 120: the TARCAP is on station 2 minutes ahead of the strikers (sweeps and escorts already led by 90 s). A 5-minute lead let the SA-10 kill six Eagles in v0.41.0, so 2 minutes.
- All numbers are judgment calls. The red fighter stations (TARCAP-equivalents) do not change. Untested in DCS. Smoke check_31zd asserts the call waits.

## v0.41.114, blue defensive missions: stations up the raid's way in, a base CAP for the intercept, and a fix to the call-in script error

XO (Kobuleti run, 2026-10-22): the CAPs sat on top of the bases and nothing was there to call in. Also his mission-load error `attempt to call global 'SQE_CALLIN' (a nil value)`.
- FIX: the call-in triggers (red, red SAM guard, blue) fired at mission time 0 when the target side was already inside the zone, before the trigger that defines `SQE_CALLIN` had run. All three now wait `CALLIN_LUA_DELAY_S` (5 s). Smoke checks 31zd / 31ze assert it.
- STATIONS: the raid scramble's package CAP (CAP1/CAP2, for an airfield target) now sits on `scramble.blue_station` (forward on the raid's line, under our air defence) instead of on the line from the player's base. Alert pairs use the same point.
- COVER: a point counts as covered also when a full-strength Patriot (0.65 air defence) is within `BLUE_COVER_PAT_NM` (30 nm); before, only the 25 nm HAWK-class reach counted.
- CLEARANCE: blue stations use `scramble.clear_for_station` (SA-10 35 nm, other rings +3 nm) instead of the sweep's rule (45 nm, +20 nm), which rejected even the target field and sent the pair 10 nm BEHIND it.
- ATTACH: an airfield raid-intercept package (FLEET_DEFENSE on a field) now gets the field's BASECAP, and a raid scramble made by the emergency path (`_make_emergency`) gets its guards too, if a patrol is planned in that window.
- Judgment calls: 30 nm / 0.65, 35 nm, 3 nm (all mine, no source). Untested in DCS.

## v0.41.113, BARCAP stations pushed forward

XO (2026-10-22 runs): the base CAPs sat too safe, so no air-to-air happened between the bases. The orbit centre moves out toward the threat so the two sides can snipe at long range while the defender is still inside its own SAM cover.
- `STATION_BASE_NM` 12 to 25 (the HAWK ring edge, well inside the Patriot's 40), `STATION_FLEET_NM` 13 to 35 (inside the ships' 70 nm SM-2 ring), `STATION_MAX_NM` (the do-not-exceed distance when a red SAM ring pushes a station out) 30 to 50. Both sides' patrols use the same areas.
- The engage circle of a blue base / carrier CAP is round what it guards, so a forward station sat at or past its edge: it now reaches `CAP_REACH_BEYOND_NM` (25) past the station, but never beyond the fixed 50 nm CAP engage limit in the mission options (the carrier CAP reaches 15 nm past its station).
- All three numbers and the 25 are judgment calls, from the game's SAM rings (HAWK 25, Patriot 40, SM-2 70) and AMRAAM-class reach (25 to 40 nm). Untested in DCS.

## v0.41.112, blue BASECAPs called in with the alert pairs (step 2 of 2, blue side) and a fix to red's stay time

XO: the same call-in for blue, in the missions where the alert pairs are called.
- BLUE CALL-IN (`RaidSpawns._blue_callins`): in a defensive mission (a raid scramble folded into yours, or a package that defends the fleet) every blue base CAP and carrier CAP (relief and standby pairs too) that can answer gets the same extended route as red's: after its home leg, HOTSPOT, BACK, the racetrack leg and a second way home (landing, recovery point or the deck). The hotspot is the station a blue alert pair takes (`scramble.blue_station`: forward of the target, under our own air defence, clear of red's SAM rings). One trigger on red entering the 120 nm circle round the target (the alert pairs' own trigger) runs the same `SQE_CALLIN` Lua. Base CAPs answer from 10 to 110 nm, the carrier CAP from 10 to 60 nm so the boat is not left bare (`BLUE_CALLIN_CV_NM`, judgment call). The tanker and AWACS guards stay with their asset. A relief that is not yet airborne when the call goes out is not called.
- FIX (red, from #172): the time a called pair stays was worked out with the speed in km/h against a distance in metres, so the flight to the hotspot counted a third of its real length and the pair would have left again early. Fixed for both sides.
- Blue alert pairs already fly home on a clock (the time on target plus the sortie time); no change there.
- Judgment calls: the 60 nm limit for the carrier CAP; all other numbers are red's (`CALLIN_REACH_NM` 110, `CALLIN_MIN_NM` 10, `CALLIN_STAY_S` 480). Not done: a call-in in blue's offensive missions (the base CAPs stay home there), a second pair per area. Untested in DCS. Smoke check_31ze.

## v0.41.111, red BASECAPs called in with the scramblers (step 2 of 2, red side)

XO: red's lone 2-ship waited for the strike while the rest of the wing sat on the ramp. The patrols should be called to the hotspot when the scramblers are called, and fly back to their station afterwards. Blue follows in the next part.
- CALL-IN: a red CAP patrol that can answer (hotspot 10 to 110 nm from its station, clear of every carrier's reach, red not outgunned) now has a hotspot leg on its route, placed AFTER its landing point: HOTSPOT (orbit, engages inside its own circle), BACK (orbit on the station to the end of the shift), the racetrack leg and a second landing. The hotspot is the station an alert pair of its own field would take (`scramble.red_station`: over a covering SAM, else the covered point nearest the target, else over the field).
- THE CALL: every alert trigger also sets a flag; one trigger fires when it is set (or, with no alert pair in the mission, when blue enters the detection circle of the nearest red field) and runs `SQE_CALLIN` for each armed patrol. It sends the pair to the hotspot with a Lua `SwitchWaypoint`, and `CALLIN_STAY_S` (8 minutes) plus the flight time later sends it back to the BACK waypoint. A pair already sent home by the hook (lost a jet, winchester, bingo) is left alone. The SAM-guard call-in of v0.41.10 now uses the same leg (the old pushed engage task never came back: probe runs of 2026-10-22).
- Scrambled alert pairs now fly home `ALERT_STAY_AFTER_TOT_S` (20 minutes) after the time on target instead of an hour.
- What the probe runs showed (tools/callin_probe.py, PRs #168 to #171): a flag-released orbit works but a pair whose shift ends would fly it too; a pushed `EngageTargetsInZone` wanders and does not return; `GoToWaypoint` is not supported by DCS ("No state creator"); `SwitchWaypoint` works, at once with from = 1 and only after the current leg with from = the current waypoint. All of it from one run each: judgment calls until XO has flown it.
- Judgment calls: `CALLIN_REACH_NM` 110 (the existing "in the area" radius), `CALLIN_MIN_NM` 10, `CALLIN_STAY_S` 480. Not done: blue's patrols (next part), the fight-over return (it is time-based), a second pair per area.

## Tools only (no version bump): call-in probe, fourth version

XO's third run: a control pair that is never called holds a 20 nm racetrack; a flag-released route (V3) flew to the hotspot, orbited and came home; pushed engage tasks (today's red SAM-guard call-in) did not come back. Problem with the flag route: a pair whose shift ends, or that bugs out, would also fly the hotspot leg. `tools/callin_probe.py` now tests jumping to the hotspot leg only when called: a Lua `SwitchWaypoint` command (V4), the same with a wrong `from` index (V6), and a pushed `GoToWaypoint` task (V5), against the never-called control. Speeds are now km/h like pydcs wants (the old probe flew at 220 km/h).

## Tools only (no version bump): call-in probe, third version

XO's second run: all four pairs, even the control, chased the visible bait tanker on their own, so the call-in could not be told apart. The bait is now AI-invisible. What the run did show: a CAP pair goes about 40 nm out for a visible air target by itself, and the survivors turn back to their station afterwards.

## Tools only (no version bump): call-in probe, second version

XO's first run showed the pairs leaving their stations before the call-in (my probe spawned them exactly on the station point). `tools/callin_probe.py` now spawns each pair 8 nm short of its station like the real patrols, adds a control pair V0 that is never called in, and logs the heading. The first run's hint: V3 (flag-released orbit, hotspot waypoint, waypoint back) did return; the pushed tasks were inconclusive.

## Tools only (no version bump): call-in probe

XO: BASECAPs should be called to the hotspot when the scramblers launch, then go back to station. Step 2a is a test of the DCS mechanics, not the feature.
- New `tools/callin_probe.py`: one AI-only test mission with three red Su-27 pairs on station, each with an immortal blue tanker on a hotspot 40 nm away. At t = 60 s they are called in three ways: V1 a pushed `EngageTargetsInZone` with a 240 s stop, V2 the same pushed task without a stop (what the red SAM-guard call-in does today), V3 a route with a flag-released orbit, a hotspot waypoint, and a waypoint back. Each pair logs its distance to station and hotspot every 20 s as `SQEPROBE2` lines in dcs.log.
- No campaign code touched, no smoke test, no version bump. Whether DCS sends the pairs back is unverified until XO flies it.

## v0.41.110, red patrols first (step 1 of 2)

XO: in the 8-day runs red scrambles outnumbered the basecaps, a lone 2-ship waited for the strike and the rest of the wing sat on the ramp, which made SEAD / DEAD too easy. The wide scramble net is working as intended.
- PATROLS FIRST: `reactive.plan_red` now holds one pair per BARCAP area a wing flies today out of the reinforcement draw. A scramble can no longer take the airframes the day's patrols need. Blue already worked this way (`blue_barcap.plan` is paid before the packages).
- MORE PATROL SORTIES: the red share of a wing's day (`redair.DOCTRINE` frac) goes L2 0.30 -> 0.40 and L3 0.40 -> 0.55 (L1 unchanged). Judgment calls, to be tuned from XO's runs. 5-day sims (4 seeds): L2 about 140 -> 195 patrol pairs, 19 -> 27 pair-hours a day; L3 about 335 -> 465, 70 -> 95.
- Not done yet (step 2, high effort): BASECAPs called in to the hotspot when the scramblers launch and sent back to station afterwards, both sides. A second pair per area at L3 is also left out.

## Tools only (no version bump): AWACS tuning probe

XO: AWACS tactical messages should only show when the player is tuned to the AWACS. Step one is a test, not a feature.
- New `tools/awacs_probe.py`: builds one tiny Caucasus test mission per jet (F-16C, F/A-18C, F-14B, A-10C, F-15C), one Player slot at Kutaisi plus an E-3A on 251.0 AM. Mission Editor "cockpit parameter" triggers try about 36 guessed parameter names in three units (MHz, kHz, Hz); each fires once as an on-screen message and a `SQEPROBE` line in dcs.log. Also a looping radio transmission with a subtitle on 251.0 AM to see whether the text shows only to a tuned pilot.
- No campaign code touched, so no smoke test and no version bump. The probe is a guess list: the real parameter names per jet are unverified until XO flies it.

## v0.41.109, the quiet day, the carrier CAP on the setpiece, and the big hit (part 3 of 3)

XO: red goes "mysteriously quiet" before the raid; the setpiece should have its base CAP, AWACS and tanker guards; not flown at L3 it is "a super duper big deal".
- QUIET DAY: red now STAGES the carrier raid (`bombers.decide` -> `stage`, `QUIET_DAYS` = 1). The day it decides, red flies patrols only: no announced raids, no surprise raids, no emergencies, and the Overview says "Red air is unusually quiet today". The raid launches the next day if it still has its escorts. Judgment call: one quiet day (XO said a day or two).
- L2: the raid is exactly 4 bombers and 8 escorts (never more).
- The carrier raid setpiece gets the carrier CAP and the AWACS / tanker guards that are planned up in its window (`blue_barcap.attach` used to skip every fleet package).
- BIG HIT (new `sqe/carrier_hit.py`): a raid nobody flew that gets through, at Level 3, is the big one with chance 0.8: each carrier squadron loses 15 to 35 % of its serviceable aircraft on deck, the group's air defence drops 25 points, no launches the next day and half the sorties the day after (packages and patrols). Level 2 keeps the old small loss; a flown raid keeps counting what really reached the boat. All numbers are judgment calls.
- 100-day L3 sims (8 seeds): 0 to 5 carrier raids a run, blue air strength 0.80 to 1.0 at the end, two victories (days 95 and 99); L2 unchanged (one raid before victory about day 30).
- DESIGN_NOTES section 12 describes the whole setpiece.
- Smoke: new `check_31zc_raid_quiet_and_hit`; `check_31zb` runs without the quiet day.


## v0.41.108, the carrier raid in the mission: big raids are several groups (part 2 of 3)

XO: the raid is a setpiece with "lotsa planes up and more booms"; pydcs makes one group of at most 4, so a 12-bomber raid used to show as 4.
- A raid of more than 4 bombers (or escorts) is now several groups of nearly equal size (12 = 4+4+4, 6 = 3+3). The bomber groups follow the same route one minute apart (`RAID_GROUP_GAP_S`, judgment call); their TOT and the debrief's "got through" check follow each group. Unit names run on (RAID-B-1 to RAID-B-12), so the debrief and the hook see every aircraft. The old "shown with at most 4 aircraft" warning is gone.
- Escorts: with 3 or more escort groups, half fly a Fighter Sweep on the same route `RAID_SWEEP_LEAD_S` (90 s, judgment call) ahead of the bombers and fight what they meet; the rest escort the bomber groups, spread over them (Escort task tied to that group). A small raid keeps its single escort group.
- Land raids (Su-24M, Su-25) use the same code and are unchanged when small.
- Unit limit: the raid is part of the base mission, never trimmed; wrecks and optional flights are trimmed first (existing rules). Nothing is merged into the setpiece.
- Not changed (open): where the Backfires fire. They still fly to the carrier with the Kh-22 attack task; a launch point outside the escort ships' SM-2 ring needs a doctrine lookup (Kh-22 reach vs SM-2) before it is moved.
- Smoke: `check_31zb_raid_setpiece` now builds the mission and checks every bomber and escort is in it, the group split and the sweep.


## v0.41.107, the carrier raid is a flyable setpiece (part 1 of 3: package, list and right pane)

XO: "a tasking like any other except it's not hidden like scrambles ... a setpiece, no merged packages ... on the right it will contain all of the flights participating ... A-10: greyed out, in-universe text, press Skip".
- The red bomber raid on the carrier (FLEET_DEFENSE aimed at the carrier) is no longer AI-only. `packages.carrier_raid` / `ai_only`: BARCAP and land-raid intercepts stay AI-only. The package carries `extra["setpiece"]`.
- Its flights: CAP flights of 4 from every fighter squadron in radius, nearest first (the boat's squadrons, then land fighters), about one blue fighter per raider (3 flights per 4 bombers, `SETPIECE_RATIO`, judgment call) plus an optional 2-ship sweep. Tasks read in universe ("Intercept: kill the Backfires before they reach launch range...").
- Built FIRST in the day's plan (numbers unchanged) so the carrier squadrons are not used up, and your squadron always gets a flight in it when it can reach the raid. Nothing merges into it or out of it.
- Missions page: the right pane lists every flight; the ones you cannot fly are greyed out ("On alert (AI)"); in-universe text above (raid size, bearing); for an A-10 (or any squadron out of reach) a second paragraph says several fighter groups are on alert and Skip Turn settles it. No threat lines for the setpiece.
- Not yet: the mission side (groups over 4, route, escorts out front) = part 2; the quiet day, big-deal consequences and L2 sizing = part 3. Until part 2 the raid in the mission still shows at most 4 bombers per group.
- Smoke: new `check_31zb_raid_setpiece` (planned, F-14 can fly, A-10 cannot, no merging, the mission builds).


## v0.41.106, Mozdok's own escort squadron (bomber trump card, step 2)

XO: "Mozdok fighters for now" / a dedicated escort squadron that sits "down the queue for taskings".
- Red's Mozdok wing now holds a second squadron: Su-27s flagged `role="escort"` (L1 none, L2 8, L3 16; `Difficulty.bomber_escort_wing`, a judgment call: 2 escorts per bomber for the biggest L2 raid, 8 bombers' worth at L3; no source for the size). A new campaign gets it; old saves keep working without it.
- What it does: escorts the carrier raid (`bombers.escort_options` counts it and picks it FIRST when it can cover a 4-ship raid, the other fields are the fallback), flies Mozdok's own patrols and scrambles like any fighter squadron on its field. What it does NOT do: red reinforcements never take it (`general_types_up`), land-raid escorts skip it, it never stands down overnight (the wing is exempt, as before).
- The bomber count now reads only the Tu-22M3s (`available_of`), so the escort jets are never counted as bombers.
- 100-day L3 sims (8 seeds): 0 to 7 carrier raids a run, bombers stay at 10, the escort squadron ends at 13 to 16 of 16. L2: one raid before victory around day 30.
- Not done: the Mozdok SAM question (second SA-10 or not; fighters first, XO's call) and the mission-side raid.
- Smoke: new `check_31za_mozdok_escorts`.


## v0.41.105, red's bombers are a trump card (step 1: background sim)

XO: "No 2 ships raids, ever. Those bombers are expensive" / "2 escorts per bomber" / "Mozdok under attack ... a good weight, not the main factor".
- New `sqe/bombers.py`: one `decide` for the day. Red launches the Tu-22M3 carrier raid only (a) in a window it judges safe (estimated chance the raid is stopped under `bomber_safe_p`: L3 0.12, L2 0.06, L1 never), cooldown 8 days, or (b) when desperate (air/command losing, Mozdok under attack weighted 0.5, front in its last stage), cooldown 5 days, everything it can escort.
- Never fewer than 4 bombers (max 12), 2 escorts per bomber; if red cannot field the escorts it holds. Wired into the planner (war.py) and the raid plan (packages.py).
- 100-day background sims at L3 (8 seeds): 0 to 5 carrier raids per run (before: 25 to 37). L2: 1 to 2 raids before blue wins around day 30. Frequency is a judgment call; doctrine caveats are in the bombers.py docstring (Soviet doctrine massed raids and accepted heavy losses; "only when safe" is XO's design).
- Not done: the Mozdok escort squadron (step 2) and the mission-side boss fight.
- Smoke: new `check_31z_bomber_trump_card`.


## v0.41.104, the unit limit counts only the base mission; merged packages are bounded by the radius and a fixed ceiling

XO: "for package merging only the radius along with additional units that were merged is used ... the unit cap of default 250 would only be used for setpiece missions" / "the ceiling in the json instead of a user adjustable value" / "the smoother version first".
- Settings > Mission Build "units max" (default 250) now counts the BASE mission only (your package, its support, its sites, the reliefs, standby and alert pairs, reinforcements). The units that merged packages bring (their flights, their own sites, ruins) do not count against it and are never dropped for it. Wrecks and the optional flights above are still trimmed to the base limit, furthest wrecks first.
- The only bound on the whole mission is a ceiling in the new `sqe/data/limits.json` (`unit_ceiling`, 500, a judgment call; edit the file, not a setting). Over the ceiling the existing trim order applies: ruins first, then merged packages, last one first. Full-map mode stays unlimited.
- New `sqe/limits.py` (reads the JSON once), `MissionBuilder._units_room`, `_merged_units` tracked in `_add_merged`; the old per-site checks (wrecks, reliefs, standby, reinforcements, alert pairs) use it. The trim message now says "ceiling".
- Not measured: how this plays in VR with several merged packages (XO reports mostly two packages in the air at once at 25 nm). If it stutters, lower the merge radius or the ceiling.
- Smoke: new `check_31y_unit_cap_merged`.


## v0.41.103, the ground war on the Forces page

XO: "forward garrisons ... along with the GUI changes."
- Forces > new tab "Ground war": one row per sector with the enemy and friendly force as bars and the forward garrison each side holds there (a dash where that side holds nothing in the sector). The garrisons were already in the Enemy assets list as "Garrison".
- Builds on v0.41.102 (forward garrisons); merge that first.


## v0.41.102, forward garrisons (both sides, every sector)

XO: "forward garrisons ... mirroring red ... every sector ... they should have effect in the background sim."
- Every sector now has a dug-in forward garrison for each side: red `rfwd_N` (state.assets) and blue `bfwd_N` (state.blue_assets), 3 km either side of the sector centre. New campaigns get them at build; older saves get them at the next planning (`ground.ensure_forward_garrisons`).
- Background sim: a forward garrison lost since yesterday takes 15% x the health lost off its side's force in that sector (`FWD_SHARE`); a standing one lifts the defender factor from 1.25 up to 1.5 (`FWD_EXTRA`). A destroyed red one is dug in again with a daily chance while red holds the sector (blue's come back through the existing rebuild).
- Blue tasking: red's forward garrison is a CAS job ("dislodge the enemy forward position, Sector N") where both sides hold the sector, weighted by the sector's pressure; under a live long-range SAM umbrella the SEAD / DEAD goes first, as for any garrison. Friendly troops at the JTAC are sized from the sector.
- Red tasking: red raids can aim at a blue forward garrison (counted as a garrison raid) where blue still holds the sector, more often where red presses. A hit lowers its health, which the sim turns into force loss.
- In missions: red's is built when it is the CAS target; blue's when it is a raid target (and in the full-map test). Sector sizes and effects are judgment calls inside the range of open sources (see DESIGN_NOTES section 11); tune on XO's runs.
- Smoke: new `check_31x_forward_garrisons`; the old garrison-CAS check ignores forward positions (they have no SAM site to wait for).
- Not yet: Forces-page rows for the forward garrisons (next PR).


## v0.41.101, in-universe scramble text, and raid scrambles fold into your mission

XO: "an in-universe message like 'our A-10Cs have been dispatched to help' ... if those scrambles happen I suppose they're close to the time I picked to fly so shouldn't they be merged ... on the -15 to 30 minutes merge?"
- An emergency you cannot take no longer says why ("the F-16 doesn't do CAS", "no free pair"). The popup and the campaign note say who answers it: "Our A-10Cs from Kobuleti have been dispatched to help." (troops in contact) or "Our F-14Bs from ... are scrambling to intercept." (raid). New `Session.dispatch_line`.
- A raid scramble you do not fly now folds into your mission as AI, like a troops-in-contact call already did, when the raided field is inside your merge circle (same -15 / +30 minute window, same six-package and unit limits; merge mode "area" only). Scramblers and raiders (RAID-B) both appear. Not folded when your own tasking is itself a raid intercept (the raiders' names would clash). Otherwise the war sim settles it as before.
- `MissionBuilder._add_merged` can now take a raid package (target is a field, not an asset): no ground opfor or egress search for it, and `_spawn_raid` is called with the scramble's station and TOT.
- Smoke: new `check_31w_raid_scramble_merge`.

## v0.41.100, tankers and AWACS on the Forces page, blue air defences per site

XO: "put the awacs and tankers on the GUI ... dunno if the GUI needs adjusting to show that blue has assets too".
- Forces > new tab "Tankers and AWACS": each support asset (E-3A, E-2C, KC-135, KC-135 MPRS, S-3B; the red A-50 dimmed, "not flying yet"), its type, base, serviceable / authorized airframes, cycle (time on orbit and turnaround), hours of cover today (from `state.barcap["support_flights"]`) and a strength bar. Read-only; tankers and AWACS are assets of their own, not squadrons.
- Forces > Coalition bases: the single blended "Air defences" bar is now three bars, Patriot / HAWK / AAA, one per blue site (`state.blue_sams`); a carrier shows its escorts; an older save without sites shows its one figure on the Patriot.


## v0.41.99, hot runway starts at your own field become a sub-setting

XO: "a subsetting ... The main setting is for those not of same base. Then the subsetting is the one where it does it even on same base ... If main setting is off then the subsetting cannot be on."
- New `hot_runway_own_field` (Settings > Experimental, "...also at my own field", off by default), indented under "Hot starts on the runway (AI flights)". The main setting now covers only the other fields; the own-field rules of v0.41.97 (release after your takeoff, none in the last 10 min before your planned landing, hook holds while you are inbound) run only with the sub-setting.
- The sub-setting is greyed out and cleared while the main one is off; the settings loader and `engine` also force it off, so it can never be on alone.
- Not built yet (XO's "dupes"): the runway-plus-airborne copy of each own-field flight so a flight can still air-start when you are about to land; until then a flight caught by the inbound check is delayed.
- Smoke: `check_31v_hot_runway` checks that the main setting alone releases nothing at your field and that the sub-setting is ignored without the main one.


## Docs: audit of stale text (no version change)

XO: "check all docs for fellow CCs if they're updated and nothing is stale."
- `docs/GUIDE.md`: Settings now lists six tabs (Experimental, hot starts at the ramp in General); the Missions "All packages" line says the list is display-only (v0.41.93); the AI-only patrol line names all four support patrols.
- `sqe/gui/dialogs.py`: the SettingsDialog docstring says six tabs. `CLAUDE.md`: the plan-doc list names all five plan docs.
- `docs/DESIGN_NOTES.md` section 10 (AI start types, hot runway starts, v0.41.96 to .98) was pushed directly.


## v0.41.98, hot runway starts move to Experimental

XO: "the same runway hotstarts can be put on experimental for now."
- "Hot starts on the runway (AI flights)" moves from Settings > General to Settings > Experimental. Same setting, still off by default, no behaviour change. (Builds on #151.)


## v0.41.97, hot runway starts at your own field (phase 2)

XO: "OK, let's do 2."
- With "Hot starts on the runway (AI flights)" on, AI flights from YOUR field start on the runway too, but only after you are rolling: the earliest release is your takeoff time + 60 s (the 60 s stagger), and the hook (existing `PRWY` rule) also waits until you have actually taken off.
- "About to land, air start again": no release in the last 10 min (`HOT_HOME_S`, judgment call) before your planned landing; a flight due then keeps the old airborne spawn. In the air the hook adds a second guard: while you are within 10 nm of your field, under 1500 m above the ground, more than 5 min after your takeoff and not yet landed (`playerInbound`), runway releases at your field wait (they go once you are on the ground or leave the area). The hook cannot switch a hidden runway group to an air start on the fly, so a flight caught by the live check is delayed, not air-started; only the planned check air-starts. Say if a twin (runway and airborne copy, the hook picks one) is worth the extra units.
- The hook gets your field's position (`PHOME`, nil off a carrier). Carriers still use the airborne start.
- Smoke: `check_31v_hot_runway` also checks your own field.


## v0.41.96, hot starts on the runway for AI flights (phase 1)

XO: "Can we start the hot on runway starts phase 1?"
- New setting, Settings > General, "Hot starts on the runway (AI flights)", **off by default**. On: AI package flights from LAND fields other than yours no longer appear airborne. They wait hidden on the runway and the mission hook releases them at a set time (`RWYQ` entries with a time `t`; the same queue the alert pairs use, never taxiing).
- Timing: a flight is due at its first route point (the pretend DEP, 4 to 23 nm out) at the old activation time. The release is earlier by the roll (45 s, from the v0.41.0 alert-pair runs) + 15 s + the climb-out to that point at 300 kt (judgment call). The flight's margin before the push (2 min with a hold, 1 min without) still absorbs up to margin minus 30 s of lateness.
- Stagger: releases from one runway are at least 60 s apart (the hook's `RWY_STAGGER_S`). A flight whose release would be later than its margin allows, or whose package is already underway at mission start, keeps the airborne spawn. So L3's early packages stay airborne; later ones go hot.
- Not changed: your own field (phase 2: start hot once you are airborne, back to air start when you are about to land), carriers, support/guard flights.
- Fix: a relief or standby sortie could pick the same callsign as a flight of a merged package (two groups named "Enfield 1"); it now avoids every flight already built. DCS and the hook find groups by name.
- Smoke: `check_31v_hot_runway`.


## v0.41.95, hot-ramp setting moves to General

XO: "move the hot starts on ramp to its actual and appropriate spot on the settings."
- The hot-start checkbox moves from Settings > Experimental to Settings > General (next to the other "how a sortie runs" options) and is retitled "Hot starts at the ramp (scramble pairs)". Same setting (`hot_ramp_scrambles`), same hint text, no behaviour change.

## Docs: CLAUDE.md code map (no version change)

XO: "OK, update docs."
- CLAUDE.md's code map lists `blue_barcap.py`, `support_assets.py`, `barcap.py` and `scramble.py`. `docs/DESIGN_NOTES.md` got section 9 (planned air cover, support assets and scrambles, v0.41.85 to v0.41.94; pushed directly). The Project's `barcap-plan.md`, `red-arm-plan.md` and the design notes copy were refreshed.

## v0.41.94, red's SEAD group is sized like blue's salvo

XO: "Do SEAD pair sizing."
- `raids.arm_jets`: red's Su-24M SEAD group against a field is 2 jets (4 Kh-31P) for a Patriot or a HAWK alone, 4 jets (8 missiles) when both are live or the Patriot is at full strength (`BLUE_PATRIOT_LN` launchers); never more than the Su-24Ms the wing has left beyond its bombers (a short wing falls back to a pair, none left means no SEAD); 0 against a field with neither battery. Thresholds mirror blue's HARM salvo (v0.41.83) and are judgment calls; 2 Kh-31P per Su-24M is from Wikipedia (Kh-31).
- In a flown mission four jets against both batteries fly as two pairs ("Raid SEAD 1" on the Patriot, "Raid SEAD 2" on the HAWK, the second 600 m higher: they share a route); four against a lone full-strength Patriot fly as one group of four on it. Unit names are now `RAID-S-<group>-<jet>`.
- Unflown (background) raids: a four-jet group takes more of the batteries' cover, `ARM_AD_FACTOR_4` 0.3 (a pair keeps 0.5), judgment call.
- Chance of a SEAD group at all (`raid_arm`: L1 none, L2 0.2, L3 0.6) is unchanged.
- Smoke: `check_31u_red_sead_size`; `check_31l_red_arm` also builds a four-jet group.

## v0.41.93, "All packages" is display only; no "are you sure" on a stand-down day

XO: "All squadrons list is just for display ... I shouldn't be able to fly non-squadron planes." / "On stand down days the confirmation ... should not appear anymore."
- The Missions page list choice (My squadron / All packages) now only decides what the list shows. It is saved as the new setting `list_filter`; `flight_filter` (who you may fly) is always "squadron" in the app: an older settings file whose `flight_filter` was "all" becomes `list_filter` "all" on load and no longer lets you fly other squadrons' jets. `flight_filter="all"` stays for the smoke tests and tools.
- Skip Turn on a stand-down day (nothing you may fly and no sortie pending) skips at once, with no confirmation; the question stays when you could fly something or have a sortie built.
- Smoke: `check_31t_all_list_is_display_only`.

## v0.41.92, hot-ramp scramblers launch earlier; fuel lines in the debrief

XO: "Begin 1 & 2." (scramblers get in the air too late; are the MiG-29s going home bingo?)
- Read from XO's 2026-10-21 runs (`alerts` called / airborne times): with hot ramp on, a pair took 324 to 566 s from the call to the air at Gudauta and 283 to 369 s at Nalchik; the hidden runway start is about 2 minutes (`ALERT_TAXI_S`). So the late scramblers are the taxi, not the detection range.
- With the hot-ramp setting on, every alert field's scramble circle is wider by `RAMP_LEAD_NM` 30 nm (what blue covers in about 4 extra minutes at 500 kt; judgment call from those runs), never past 0.85 x the field's distance from the fight + 15 nm (`threatmap.field_detect_nm`, `set_ramp_lead`). The marshal, sweep and carrier CAP keep-outs read the same radius, so planning stays consistent (the lead is set from the setting at `plan_day` and at every build). With the setting off nothing changes.
- The debrief now has a "Fuel:" line for every AI group that was airborne and ended the mission at 35 % fuel or less (from the hook's 30-second tracks; `BINGO_REPORT_PCT`), with the time it reached bingo (20 %, the hook's own `BINGO_FUEL`). No hook change.
- Finding: none of the red pairs in those runs were near bingo (fuel 52 to 81 % at the end). The MiG-29 pairs that went home (Bandit 3 landed at 33 minutes with 52 % fuel) were patrols whose planned window ended with their relief already on station, not fuel.
- Smoke: `check_31s_scramble_timing_fuel`.

## v0.41.91, scramblers take a station and fly a complete route

XO: "I pretty much think scramblers really should mirror fighter sweep tasks ... stick forward towards the attackers but stay over SAM protection ... the waypoints should be complete like the normal TARCAPs, escorts or something."
- Read first (runs of 2026-10-21): red alert / reinforcement pairs had one `INTERCEPT` point ON the target with an orbit and nothing after it; red patrols (Bandit, Relief, Standby) ended at `CAP2`; blue alert pairs had a `CAP` point exactly on the raid's target (inside red SAM reach in the 2026-10-16 test) and then landed. MiG-29s seen going home were probably bingo: no route home was flown.
- New `sqe/scramble.py` (planning only). Red: the station is the target when a live red SAM covers it, else the covered point nearest the target on the line from its field (at most as far as the line goes), else 15 nm out from its own field. Blue: on the line from the target toward where the raid comes from (the bomber wing, else the nearest red fighter wing), as far forward as 30 nm (`STICK_NM`) while it is still under blue's own field air defence (Patriot / HAWK, 25 nm of a field with air defence 0.3 or more) AND clear of red's SAM rings (the sweep's `clear_for_sweep`); else on the target when that is clear, else the nearest clear point back. Doctrine: fighter / missile / joint engagement zones (JP 3-01 terms, definitions from a summary card); the stick distance, the step, the cover margins and the 15 nm field hold are judgment calls.
- Every red patrol and alert route now ends in a landing at its own field (Bandit, Relief, Standby, Alert, Reinforce; `RedAirPicture._land_home`). A pair the hook sends home (jet down, winchester, bingo) now has a landing to fly to.
- Engage limits are unchanged. Not done: scramble launch time (detection range), a bingo / fuel line in the debrief.
- Smoke: `check_31r_scramble_stations`.

## v0.41.90, red's base CAPs are spread through the day

XO: "I think red don't have BaseCAPs." (three days of runs, all starting 06:10 to 06:35)
- Cause: each red patrol area flew its day's sorties back to back from the start of one 6-hour wave (`redair.plan`), so a field's whole day of patrols sat in one to three hours (Sukhumi 00:00 to 00:50, for example) and a morning mission found most areas empty. Same number of sorties, bad spread.
- Now an area's sorties are spread evenly through the 24 hours (the wave and a dice roll pick where in its gap the area starts; many sorties still chain back to back with the 10 minute handover). Same sortie count and budget as before; blue's patrols already worked this way. Level 2 seed 3: patrols up in 20 of 24 hours (was 14 on the old plan), level 3 in 24.
- Expect red patrols in your morning missions more often, and a harder time at level 3.
- Smoke: `check_31q_red_patrols_spread`.

## v0.41.89, BARCAP status line and shorter Experimental settings

XO: "You can go with the BARCAP status line." / "The setting headers don't wrap."
- The Overview's theatre summary now ends with "BARCAP cover today", one line per base or carrier (the share of today's 24 h each blue area, by direction, has a pair up, from the plan in `state.barcap["blue_cover"]`; the patrols fly 06:00 to 22:00, so 67 % is the most) and a line with the planned tanker / AWACS guard sorties (`blue_barcap.status_lines`). Display only.
- Settings, Experimental tab: the checkbox titles are short (they do not wrap) and the explanation moved into the text underneath.
- Smoke: `check_31m_blue_barcap_plan` also builds the status lines.

## v0.41.88, HAVCAP and tanker CAP are planned chains of their own

XO: "Merged and I would love it if you did."
- HAVCAP and TNKCAP are no longer package slots. `blue_barcap._plan_guards` plans them each day, one chain per tanker (KC-135, KC-135MPRS) and AWACS (E-3, E-2C) type, along the hours `support_assets` says that type is on orbit (06:00 to 22:00). Pairs stay two hours (the tanker-guard endurance); the number is the same patrol share by level as the BARCAP (10 / 20 / 40 % of full cover), at least one sortie per asset. Tankers are planned first, since the tanker's guard is not optional.
- Guards come from the asset's base squadron, else the nearest capable one, else any fighter squadron; your squadron is never drafted for them. They are paid from the same daily budget as the patrols, before the packages.
- `blue_barcap.attach` gives a package the guard sortie of its AWACS / tanker that is up while it flies; one sortie keeps one callsign in every package that carries it. Station and route stay per mission (`support_caps`); only existence, timing, squadron and cost are planned.
- Changed behaviour: a tanker can now fly without its guard on a day when no planned guard sortie is up (before, the guard was mandatory).
- Engine order: `support_assets.plan` runs before `blue_barcap.plan`.
- Smoke: `check_31p_guard_chains`; the callsign check excludes shared guards; the raid S-route check always uses the scramble path (a planned raid package resolves overnight).

## v0.41.87, tankers and AWACS as assets (step 1: airframes, windows, losses)

XO: "Take the most educated guess on the numbers of these assets."
- New `sqe/support_assets.py`, saved in `state.support_assets` (older saves get it on first use). Blue: E-3 "Overlord" 6 airframes (USAF has about 30 E-3s, 26 at Tinker over four squadrons; Wikipedia), E-2C "Magic" 4 on the carrier (a VAW squadron has four, globalsecurity.org), KC-135 "Arco" 8 (the 465th ARS operates eight KC-135Rs, globalsecurity.org), KC-135MPRS "Texaco" 8 (judgment call), recovery S-3B "Shell" 4 on the carrier (judgment call). Red: A-50 "Mainstay" 16 (Wikipedia, Ivanovo Severny, about 2011), data only. Time on orbit per sortie and turnaround (E-3 8 h / 12 h; E-2C 4 h / 6 h; tankers 4 h / 8 h; S-3B 2 h / 4 h) are judgment calls (the E-3's "more than 8 hours" is from Wikipedia).
- Each day plans when every blue type has an aircraft on orbit: back-to-back sorties by the airframes that are ready, each handing over 10 minutes early, an airframe flying again after its turnaround (`state.barcap["support_flights"]`). At full strength the whole day is covered, so nothing changes for you until airframes are lost.
- A package gets its AWACS / tanker only if one is on orbit from its start to 70 minutes after (`UP_WINDOW_MIN`, judgment call); the supports are recomputed once the start times are known and again when you pick a flight.
- A support aircraft shot down in a flown mission comes off its asset (the debrief says so); each missing airframe is back overnight with chance 0.34 (about three days; judgment call).
- Not yet: HAVCAP and the tanker CAP as planned chains of their own, red's A-50 flying, the status line.
- Smoke check `check_31o_support_assets`.

## v0.41.86, blue's patrols count in the background raids (BARCAP background sim, step 2)

- A base patrol on station now matters to raids nobody flies. `blue_barcap.patrol_up` draws, once per raid, whether a pair is up over the raided field on the side the raid comes from: the chance is the area's covered minutes of the day over 1440 (`state.barcap["blue_cover"]`; the patrols fly 06:00-22:00, so at most two thirds, and the night is open).
- Surprise raids (`raids.overnight`): a pair up adds PATROL_STOP 0.25 to the chance the raid is stopped; the log line says "the base patrol and alert aircraft got up in time".
- Announced raids the war sim resolves (`war._resolve_raid`, land raids): a pair up adds PATROL_RAID_WEIGHT 2.0 CAP-weighted jets to blue's side of the odds.
- A patrol that fought a stopped raid loses one jet with PATROL_LOSS_P 0.15 (its squadron's serviceable count drops; the log says so).
- All three numbers are judgment calls. Red patrols meeting blue patrols in the background are not simulated. Raids on the carrier are not affected (carrier CAP counts only in flown missions).
- Smoke check `check_31n_blue_patrol_vs_raids`.

## v0.41.85, blue's base CAP and carrier CAP are a daily plan (BARCAP in the background sim, step 1)

XO: "Basecaps and carrier caps are planned separately from packages so I don't think they should be attached to a package", AI only for good, the same budget share by level as red but lower at Levels 1 and 2.
- New `sqe/blue_barcap.py`. Each day plans, per blue field or boat that has a BARCAP area, a few sorties of a fighter pair through 06:00-22:00 (airframe endurance as in barcap.py: 30 min F-16 / Hornet, 2 h F-14 / F-15C). The count is a share of the base's daily sortie budget: Level 1 10 %, Level 2 20 %, Level 3 40 % (red's patrols take 20 / 30 / 40 %; the blue shares are judgment calls). The sorties are paid out of the squadrons' two-sorties-a-day budget BEFORE the packages are built, so patrols and packages compete for jets.
- The base CAP and carrier CAP are no longer slots of a package. Once the start times are known, a package carries the planned sortie of the area that faces its target and is up while it flies (LEAD_MIN 10, PACKAGE_WINDOW_MIN 100, judgment calls); with none up it flies without one. A planned sortie keeps one callsign in every package that carries it (a merged mission builds it once). Tanker CAP and HAVCAP stay package slots until the tanker / AWACS assets step.
- State: `state.barcap["blue_flights"]` (the plan) and `["blue_cover"]` (minutes covered per area, for a later status line). Old saves get the plan the next time the day is planned.
- Not yet: the effect on unflown raids and patrol losses (PR B), the BARCAP status line.
- Smoke check `check_31m_blue_barcap_plan`; check 00's callsign test allows the shared CAP sortie.

## v0.41.84, red anti-radiation missiles, step 1: a Su-24M SEAD pair ahead of a field raid

XO: "Put red anti-rad and standoffs on top" (shooters Su-24M only, Patriot / HAWK first, L1 none / L2 rare / L3 normal).
- A Su-24M raid on one of our airfields that has a live Patriot or HAWK may bring a pair of Su-24M with Kh-31P (`raid_arm`: Level 1 never, Level 2 20 %, Level 3 60 %; judgment calls). The pair needs two jets more than the raid in the wing, so it never takes the bombers' jets. Raids by Su-25 never bring one (the plain Su-25 has no ARM in DCS).
- In the mission "Raid SEAD 1" flies the raid's way in, fires at the field's Patriot (else HAWK) from 40 nm, 150 s before the bombers' TOT, then turns away 20 nm and goes home. 40 nm and 150 s are judgment calls; the Kh-31P's 60 nm is the Wikipedia figure (launch altitude lowers it). It counts as part of the raid's wing in the debrief (`RAID-S-n`).
- Unflown (surprise) raids on a field: the batteries' cover counts half when the raid brings a SEAD pair (`ARM_AD_FACTOR` 0.5, judgment call).
- Not yet: Kh-58 / Kh-25MP, Su-25T, ship radars, stand-off weapons (Kh-29 / Kh-59), raids on supply sites / garrisons. Untested in DCS: whether the Patriot shuts its radar down for an inbound ARM.
- Smoke check `check_31l_red_arm`.

## v0.41.83, SAM borrowing defaults to off

XO: "put the borrowing of sams default off". The Experimental tab's Red / Blue borrowing switches now start unticked; tick them to get SAM orders by need (v0.41.67 / .68). Saved settings keep whatever was stored.

## v0.41.82, HARM salvo scales with the SAM cluster (Standoff DEAD)

XO: "Is it out of doctrine to always have 4 ships for harms and jsows? Maybe it's the reason why the sams aren't saturated enough?"
- The Standoff DEAD package's HARM flights were always 2 + 2 jets whatever surrounded the target. Now the count of live serious SAM sites within 25 nm of the target sets the size: 0-1 neighbours 2 + 2, 2-3 neighbours 4 + 2, 4 or more 4 + 4. The JSOW flight stays at 4.
- All thresholds (25 nm, 2, 4) are judgment calls, no public source. Short of jets in the squadron pool, the flight is built smaller as before.
- Smoke check `check_31k_salvo_size`.

## v0.41.81, Experimental settings tab: borrowing per side

* **XO: "a setting that lets me turn borrowing on and off per side, on its own Experimental tab; the ECM script goes there too."** Settings has a new last tab, **Experimental**: *Red borrowing*, *Blue borrowing* (new, `borrow_red` / `borrow_blue`, both on = today's behaviour), the **ECM script** (moved from Mission Build) and **Hot ramp scrambles** (v0.41.80, moved from General).
* "Borrowing" = the SAM orders by need (`sams.red_orders` / `sams.blue_orders`: a battery is moved from the least-threatened site to a threatened one). Off for a side: its orders do not run overnight (orders already on their way wait until you switch it back on) and only the slow rebuild by supply replaces destroyed sites. The engine builds every war simulator through `Session._sim` which applies the switches.
* Smoke: new `check_31j_borrow_switches`; the Settings tab-list check expects the new tab.

## v0.41.80, hot ramp scrambles at land fields (experimental, off by default)

* **XO's experiment: "hot ramp starts for scramblers, land fields first".** New setting (Settings, "Hot ramp scrambles at land fields", off by default; `hot_ramp_scrambles`). On: scramble pairs at land fields (red alert pairs, red reinforcements, blue alert pairs, the red relief and standby pairs) start hot on the ramp, uncontrolled, and a trigger starts them when called (the v0.40.x path, kept in the callers all along; `_alert_group` now creates it). Off: the hidden runway start of v0.41.0, unchanged.
* **Fallbacks:** the pair stays on the hidden runway start at your own field, at a field with no parking for its type, and on the carrier (hidden deck start until land works, XO).
* **Why it was removed in v0.41.0:** DCS AI taxiing made some pairs take 3 to 11 minutes from the call to the air and two never got airborne. This run is the test: the state file's `alerts` list (called / air / stuck) shows it. Turn it off if pairs get stuck.
* **Not done:** the ruins rule (a field with ruins starts hot on the runway), carriers, the player's own field.
* Smoke: new `check_31i_hot_ramp_scrambles` (13 ramp pairs on with the setting, none off).

## v0.41.79, BARCAP as planned coverage, step 3 (third slice): a CAP pair that loses a jet, goes winchester or hits bingo is replaced

* **XO's rules:** if one jet is shot down, goes winchester (no air-to-air missiles left) or is at bingo fuel, the whole pair bugs out; the nearest field replaces it after a short delay; the cost is whatever the background war computes for the next sortie from the real result (the mission does nothing extra: only the jets that really die or use up count).
* **The hook watches every covered pair** (`COVER` in `sqe/debrief.py`, checked every 10 s): a jet missing, all missiles gone (only once the pair was seen armed), or fuel under `BINGO_FUEL` (20 %, judgment call). It sets the pair's **bug-out flag**: the pair's CAP orbit carries a `stopCondition` user flag (`ControlledTask.stop_if_user_flag`), so the pair leaves along its own route home exactly as it does when its window ends. `COVER_DELAY_S` (150 s, "short delay": a judgment call) later it sets the **replacement flag**. Nothing is called when the sortie has less than 10 min left (`COVER_MIN_LEFT_S`); a pair that lands at the end of its window is not counted as a loss. What happened is saved in SQE_state.json as `cover` ({g, why, t, replaced}).
* **Red patrols** (`_spawn_red_standby`): the standby is the nearest red field within reach that has four fighters (a pair beyond the one it gave); it waits hidden like an alert pair, appears on the runway when called (the same ALERT_TAXI_S queue) and flies to the patrol's station until its window ends (+15 min).
* **Blue base / carrier / HAVCAP / tanker CAPs** (`_spawn_replacement`): one standby per CAP's first sortie, a copy of the flight with a new callsign that appears 12 nm behind the station (as the v0.41.78 reliefs) when its flag is set; it stays until the replaced sortie's end plus the 10 min handover (or the end of the mission cover). Relief sorties of the chain (k >= 1) are not watched yet.
* **Not in this slice:** TARCAP / escort / sweep and in-package flights are not covered; red SWEEP patrols are not covered; the replacement's cost is not charged in advance; the unit cap is respected (no standby when it would exceed it: a warning, the pair is still watched and sent home).
* Smoke: new `check_31h_cap_replacement` (the hook watches the pairs, standbys wait for their flag, each orbit stops on its flag). The watcher's logic was also run against a mock of the DCS API (loss, winchester, late sortie, delay).

## v0.41.78, BARCAP as planned coverage, step 3 (second slice): blue base / carrier / HAVCAP / tanker CAPs rotate

* **XO's plan: "a CAP goes home only after its replacement has arrived", for blue's support CAPs too.** Until now a base CAP, carrier CAP, HAVCAP or tanker CAP sat on station for the whole mission, however short its legs (a jet that could fly 3 hours on one load). Now each sortie flies only its airframe's time on station (`barcap.endurance_min`: 30 min F-16 / Hornet and older, 2 h F-14 / F-15C / Su-27 type, 2 h for a tanker guard) and then goes home. The rest of the mission is covered by **relief sorties**: sortie k starts k x (endurance - 10 min) after mission start, so the relief is on station 10 minutes before the sortie it replaces leaves.
* A relief is a copy of the flight with its own callsign (the same name with a free number, else another name of the type), appears 12 nm behind its station toward its base, is late-activated (a "support relief" trigger) to arrive on time, and stops at its own time; the last one stops when the mission no longer needs cover (the same "last flight of any package is home" rule as before). If the unit limit is reached the reliefs are left out and a warning says so.
* Sources and gaps: endurance figures are XO's judgment calls; the 10 min handover and the 12 nm spawn are mine, also judgment calls (see `barcap.py` header).
* **Not in this slice:** the background war does not track these sorties (a lost or winchester pair is not replaced yet: v0.41.79 design with XO); AWACS and tankers themselves still fly unlimited (assets step later); the player's own flight is never rotated.
* Smoke: new `check_31g_blue_support_relief`.

## v0.41.77, BARCAP as planned coverage, step 3 (first slice): red patrols get their relief in the mission

* **XO's plan, BARCAP relief: "a CAP goes home only after its replacement has arrived".** The planned chain (v0.41.73) has the next sortie of an area start 10 minutes before the one on station leaves. When that relief falls due inside the mission (up to `RELIEF_HORIZON_S` 1 h after the time on target, a judgment call) and the wing has a second pair, the relief pair is now flown: it waits on its field like an alert pair (hidden, put on the runway when called; the v0.41.0 no-taxi rule) and a timed trigger calls it early enough to reach the station when its window opens (flight time + the 2 min runway delay + a minute's slack). The pair on station stays until its own window ends. Not flown when the wing has no second pair, its field is gone, or the unit limit would be passed. The briefing gets a "Relief for that patrol" line.
* **Not in this slice (needs XO's call):** blue's support CAPs (base / carrier CAP) still fly the whole package without relief; hot starts on the ramp (XO's hot-scramble item; today every alert / relief group is the runway start); SPAWN points at the player's base; HAVCAP following its asset under the BARCAP rules; replacing a pair that is lost, winchester or bingo; the background sim.
* Smoke: new `check_31f_red_relief_in_mission`.

## Smoke test step 2 (tools only, no version change): every section passes on its own

* `tools/smoke_test.py`: `--only a,b` now also runs the earlier sections a chosen section borrows state from (it reads `c._name` at the top; the nearest earlier section that leaves that name runs first), so every one of the 58 sections passes by itself (`--only check_NN`). The full run is unchanged and green.
* Campaign ids are random, so seeded checks could pass or fail by luck (`check_47` "no flyable SEAD flight", the HARM point 33.8 vs 35 nm). Each section now gets the same run of ids every time, whatever ran before it.
* Sections that used a borrowed name that a later local import or the module-level `random` shadowed (26, 27, 47) are fixed; sections that only needed a session build their own (`fresh_session`); shared imports are at the top of the file.
* Not done: sections still borrow from one another through `Ctx` instead of building a scenario each (the borrowing is now explicit and automatic). A full per-section scenario would mean cutting `check_47` (450 lines) into smaller pieces; left for the refactor week.
## v0.41.76, red's patrol stations lose the old fixed keep-outs; the ships' reach is a SAM ring

* **XO 2026-10-21: "that old red rule came from the early, almost random stage; use the stay-away-from-SAMs system (and the boat's range) instead."** Red's patrol stations are no longer pushed 45 nm from our marshal point and fields and 130 nm from our carrier (`RED_KEEP_NM`, v0.41.10; the 130 nm push is what put Bandit 1 behind the SA-10 in the v0.41.74 run). Their stations are BARCAP stations (v0.41.73) that stay outside blue's SAM rings, and now outside the carrier group's real reach too: `barcap.FLEET_REACH_NM` 70 nm (measured: CAP pairs were killed 51 to 67 nm out) is a ring in the SAM-clear rule, and `CAP_FLEET_KEEPOUT_NM` (the boat's CURRENT position, it may be slid back for the sortie) is 78 nm (reach + 8 nm margin; was 90, hand-set).
* **Kept on purpose:** the 100 nm bubble round the AWACS anchor / HAVCAP (the AWACS does not check red stations when it picks its spot; revisit when the HAVCAP rules follow BARCAP in PR 3); the behind-the-target test from v0.41.75. **Dropped:** the 60 nm bubble round the tanker: the tanker picks its spot 40 nm from every red station and 25 nm from red's lanes (`threatmap.tanker_spot`), which is the rule that protects it.
* Smoke: `check_31d_barcap_areas` checks the carrier ring.

## v0.41.75, red patrols pushed behind the target by the keep-out are left out

* **XO's v0.41.74 run (Standoff DEAD, Gudauta SA-10):** Bandit 1's station sat 36 nm PAST the SA-10 site (and Bandit 2 27 nm past), although v0.41.74 drops patrols whose BARCAP station is behind the target. Cause: `_plan_cap_stations` then pushes every station away from our marshal point, fields and the carrier (`RED_KEEP_NM`, 130 nm round the boat), and that push moved a station that was fine into the back of the target. The behind-the-target test (`redair.beyond_nm`, 20 nm, `BEHIND_NM`) now also runs AFTER the keep-out push; a patrol that ends up behind the target is left out of the mission (it is not in the fight), and its place goes to the alert aircraft. `pick` uses the same helper.
* Smoke: `check_31e_barcap_mission_side` also checks `beyond_nm`.

## v0.41.74, BARCAP as planned coverage, step 2: the mission side (the checkpoint)

* **XO's same-rules plan, BARCAP, PR 2 of 3.** Blue's carrier CAP and base CAP no longer face "the nearest enemy field": each takes the BARCAP area (v0.41.73) of its asset that faces the mission's target (the area whose direction is closest to the bearing from the asset to the target; with merged targets this is the main target's, a judgment call). The station is 13 nm from the boat (the boat's current position: it may have been slid back for the sortie) or 12 nm from a field, in the area's direction, and still steps back out of every SAM ring and the scramble circles as before. An asset with no area today (no hostile base can reach it) keeps the old placement.
* **Red patrols behind the target are left out.** `redair.pick` drops a planned patrol whose station sits more than 20 nm BEYOND the target along the way in (IP to target): it is guarding its own rear field, not the fight. 20 nm is a judgment call (`BEHIND_NM`). Together with v0.41.73 (stations on the side of the base facing blue) this is the fix for red's CAPs flying around the back of the target (XO's 2026-10-21 run: pairs 35 to 60 nm beyond the SA-11 site).
* **Unit cap:** unchanged. Support CAPs are one per field and boat, red patrols are bounded by the package's threat size, and wrecks are still trimmed first; nothing here adds enough units to need a new trim rule.
* Smoke: new `check_31e_barcap_mission_side`.

## v0.41.73, BARCAP as planned coverage, step 1: planning and state (red's patrols fly it)

* **XO's same-rules plan, BARCAP (claude/barcap-plan.md), PR 1 of 3.** New `sqe/barcap.py` (pure planning). Every defended asset gets BARCAP areas: red's fighter fields and blue's fields and carriers. One area per DIRECTION a hostile base could still send something from (hostile fields and carriers with jets left, within 300 nm; bases within 40 degrees share an area; at most 3). The station sits close to the asset on that side (12 nm for a field, 13 nm for a carrier group, XO's "about 15 mi") and is pushed out of every enemy SAM ring plus 8 nm, never further than 30 nm from the asset. Today's areas for both sides are kept in the campaign (`state.barcap`, saved).
* **Time on station and relief.** A sortie stays 2 h for the long-legged (F-14, F-15C, Su-27, XO), 30 min for the short-legged (F-16, F/A-18, MiG-29 and older, XO), 2 h guarding a tanker. Sorties of one area chain back to back: the relief is on station 10 min before the one it replaces leaves.
* **Red's patrols now fly these areas.** `redair.plan` no longer puts a pair 20 to 25 nm in front of its base in one 6-hour window: each pair takes an area of its own field and a slot in that area's chain. `assign_guards` no longer MOVES the station over a SAM site; it only links the pair to the best-rated site within 40 nm of its station for the call-in. Blue's areas are planned and saved but not flown yet (PR 2 and 3).
* **Patrol share counted in sorties.** A 30-minute stay is one sortie, so a pair can fly several a day: a wing's patrol sorties are the level's share (`DOCTRINE["frac"]`) of its day budget (in pairs), flown over at most pairs - 1 areas (one pair always stays on alert). Without this the first cut left red with almost no patrol up during a mission (the smoke briefing check caught it). Short-legged wings still have gaps in the day; the long-legged cover more. `frac` is the knob.
* **Sources:** only the outline is public (a CAP sits between the threat and the asset, 1 to 2 h without tankers, relief as the last one runs low, the AFIT thesis' 20 / 40 / 60 minute stays). No source gives a station distance, a handover overlap or a sector width; those, and the 300 nm reach, are judgment calls (listed in the module header).
* Smoke: new `check_31d_barcap_areas`.

## v0.41.72, AI boat flights land for real; the hook removes them after the pattern

* **XO 2026-10-21: "pretend they still land, but if the don't-land switch is on they are despawned after a few rounds on their pattern."** With Settings > AI landings set to "always" (or "home" at your deck), an AI flight going home to the carrier used to fly to a fixed RTB point (10 nm from the boat, v0.41.17; v0.41.71 moved it to where the boat would be). Now it gets the real Land waypoint tied to the ship (as when AI landings is off), so DCS homes on the moving boat itself. The hook removes it, counted as landed, once it has been within `CV_PATTERN_NM` (6 nm) of the boat for `CV_PATTERN_S` (90 s, about two laps of the pattern); both are judgment calls. A flight that traps first lands normally. A flight that never gets there is still recovered by the 25-minute stale deadline (v0.41.71). The predicted-boat-position code (`_cv_pos_at`) is gone; the tracks with fuel and speed stay. Airfields are unchanged (recovered at the entry point as before). Risks: a busy deck can stack AI in your pattern (why v0.41.17 recovered short of the boat), and a flight held in a stack farther than 6 nm out waits for the stale deadline. Smoke `[46]`: every AI carrier flight's last point is a Land point tied to the ship, and the hook entry has the 90 s dwell.

## v0.41.71, Navy flights are recovered near the boat that has steamed on

* **XO's 2026-10-21 run (Standoff DEAD, Gudauta SA-10, 20 of 52 blue aircraft lost, 8 landed):** nine Navy flights (Squids, Uzis, Hornets 3 and 5) were still flying at 2520 s, 71 km from the boat, at 20,000 ft. The tracks show them joining the tanker Texaco 1 from about 1800 s and flying its racetrack with it; they never reached their RTB point. Why they chose the tanker is not known from the files (the tracks had no fuel or speed). Three changes:
  * **The recovery point follows the boat.** An AI carrier flight's RTB point (where `SQE_RECOVER` runs) was 10 nm from where the carrier STARTED; the carrier steams away at 15 kn, so a flight that came home 30 minutes later found the point 14 nm or more from the boat, outside the hook's 12 nm net as well. Now it sits 10 nm from where the boat will be when the flight gets there (`_cv_pos_at`: the ship's own route and speed, at the last waypoint's time plus the leg to the boat at 200 m/s, a rough estimate).
  * **Tracks carry fuel and speed.** Each track point is now `[t, x, z, alt, fuel %, kts]` (the lead's, every 30 s; -1 if unknown), so the next state file shows whether the flights were low on fuel when they went to the tanker.
  * **A stale deadline.** A homebound AI flight still out `RECOV_STALE_S` (25 min, a judgment call: the way home is 5 to 10 minutes) after its work is done is recovered where it is and counts as landed, so no flight flies for ever. This is generous (a flight that was going nowhere counts as saved); I judged it better than a flight that never lands.
* Smoke check in `[46]`: the recovery point is 10 nm from the boat at some time in the mission, at least one is more than 10 nm from where the boat started, the net has `t2` and the tracks carry fuel. The section now builds its own session.

## v0.41.70, AI Skill for Red and Blue

* **New "AI Skill, Red" and "AI Skill, Blue" settings** (XO 2026-10-21: "DCS is kinda iffy when the AI is set pretty high, like they cheat"), on the New Campaign page and in Settings > Campaign (the same two settings, like Weather; they apply from the next mission). Values: Level default, Average, Good, High, Excellent. Level default is what the game did before: Red follows the difficulty level (L1 Average, L2 Good, L3 High, `enemy_skill`), Blue's AI aircraft fly at High (they were hard-set to High). A named value sets that side directly: Red's pilots (CAP, raids, reactive spawns, red air picture) and Red's ground units and SAM sites; Blue's AI flights and alert pairs, and Blue's base defences (Patriot, HAWK, AAA; under Level default these stay at DCS's default as before). Skill only: the war sim's numbers (`base_damage`, `loss_rate`) are untouched. `difficulty.ai_skill(opts, side, d, ground)` is the one place that decides. Your own flight keeps "Player". Not done: a "Random" value, per-unit-type skill. Smoke check `[31c]` builds missions at each setting and reads the skill back from the .miz.

## v0.41.69, blue Patriot and HAWK batteries stand apart

* **XO's 2026-10-21 AI run (Standoff DEAD, Sukhumi SA-11):** at 673 s a Senaki Patriot launcher fired at a Su-27 and the launch hit the 11 units around it (launchers, radar, ECS, command post, power plant: `hit` events by the site's own units), and one launcher was lost at 701 s with no enemy near it. Cause: the battery was laid out by pydcs's star formation, 20 m between units. Now a blue Patriot or HAWK battery has `BLUE_SPACING_M` (80 m, a judgment call, no public figure found) between units (`_platoon(..., spacing=)`, then `formation_star`). The ring-2 units of the 12-unit Patriot sit 160 m out, so the battery is about 400 m across. Red's sites are not changed (no such event seen). Smoke check: the unit spacing in `[41]`. The same run: Senaki's Patriot killed three red MiGs and the Stennis SM-2 one; no blue jet was lost to a SAM.

## v0.41.68, red SAM orders by need

* **Red orders SAM batteries by the same rule as blue** (XO 2026-10-21: "SAMs can be ordered by both sides"). Each night, at most one order: the shallowest-tier destroyed SAM site that is in play (tier up to front + 2, its field standing, higher value first among equals) is replaced by a battery of the same kind from a DEEPER tier (a standing site, health 0.6 or more); the chance it goes is red's supply. It arrives 2 days later (a new build needs 3) at the sender's health; the receiver is not rebuilt meanwhile; the sender's site goes down and the usual rebuild takes it when its tier comes into play. No spare, no order: `sams.rebuild` stays the only way. Same judgment calls as blue's (transit days, one order a night, the 0.6 spare level); the "deeper tier sends" rule is the red form of "the least-threatened field sends". Forward mobile sites (`fsam_`) are left out. Orders save in the SAM record (`red_orders`, `red_vacated`). Smoke check `[31b]`.

## v0.41.67, blue SAM orders by need

* **A destroyed blue SAM site is replaced by a battery MOVED from the least-threatened field first, and built only if none is spare** (XO 2026-10-21: "SAMs can be ordered by both sides should the need arise"; "move first, build if nothing to spare"). Each night, at most one order: the most threatened field (nearest to an enemy fighter field) with a destroyed site asks for a battery of that kind; the sender is the field furthest from the front that has a standing one (health 0.6 or more) and sits at least 20 nm further back than the receiver; the chance it goes is blue's supply. The battery arrives 2 days later (a new build needs 3) at the sender's health; the receiving site is not rebuilt meanwhile, and the sender's site goes down and is rebuilt by the usual rule (a site emptied by an order does not itself ask for one, so batteries do not chain backward). No spare, no order: the usual 3-day rebuild stays. The old whole-field "lend a battery" is gone (`LEND_*`). Judgment calls: transit time, the 20 nm gap, one order a night, the 0.6 spare level (JP 3-01 gives the defended-asset-list idea, no figures). New orders save with the SAM record. Blue has no mobile SAMs in the data (Patriot, HAWK, AAA per field), so scoot has nothing to move yet; blue's retreat is the order itself. Red's orders come in the next PR. Smoke check `[31a]`.

## Unreleased (tools only, no version bump), smoke test split into sections

* **`tools/smoke_test.py`: `main()` is now 58 named section functions** (XO 2026-10-21: "prioritize the smoke test refactoring... sometimes it's the only trouble that blocks PRs"). Step 1, no change to what is checked: the 2,300-line function is cut at its version-tagged blocks; what a section borrows from an earlier one is listed at its top (`a, b = c.a, c.b`) and what it leaves for later at its bottom, through a shared `Ctx`. Same 526 asserts and the same sequence of section tags as before; a deliberate break (blue repair 0.10 -> 0.30) failed in `check_29_phase_air_defence_that...`. Runner: `--list` (section names), `--only a,b` (the setup section plus sections whose name contains a or b; a section that borrows from one you left out fails naming what it needed), `--timeout SECONDS` (default 600; a section that runs longer dumps every thread's traceback and stops, so a hang says where: that is how the v0.41.66 pydcs freeze was found), line-buffered output, and the five slowest sections at the end. Next (step 2): the sections that borrow a mission from an earlier one get their own scenario, so a change to a layout cannot break an unrelated check.

## v0.41.66

* **A mission build can no longer freeze in pydcs's scattered formation** (found 2026-10-21 through the smoke test, which stalled about one run in three; XO: "prioritize the smoke test"). pydcs's `VehicleGroup.formation_scattered` retries each vehicle's random point with `while True` and its ring is random and can be too small for the group (a group of 12 with a ring under about 25 m has no clear point): the build never returned. Measured: 4 of 300 groups of 12 vehicles hung; groups of 8 or fewer never did. The smoke test's stall was this, caught by the new section watchdog (a traceback in `formation_scattered`, called from `_platoon` for a red site). `sqe/pydcs_patch.py` swaps in the same algorithm with the same random draws, plus one line: after every 100 failed tries the ring widens by 10 m. Where pydcs finishes the layout is identical (checked for 40 seeds); where it would have hung, the build now finishes. Installed when the mission builder is imported. New smoke check `[scatter]`.

## v0.41.65

* **Red's SAM clusters follow the same placement doctrine as blue's** (PR 4 of the SAM build; XO 2026-10-21: "follow doctrine and adjust as I test"). The old layout put each red site at a random bearing round its field. Now (`sams.place_red_site`): the axis is the bearing to the nearest blue base (airfield or carrier); the medium and long-range sites (SA-2 / 3 / 6 / 10 / 11) are the outer layer, the first on the axis and the next ones fanned out to +40, -40, +80 degrees, at 7 km and 3 km further each (the old distances); the short-range sites (AAA, MANPADS, SA-8 / 15 / 19) sit 3.5 to 4.5 km out either side (+/-100 degrees, then +/-150) to cover the dead zone round the field. The same seeded jitter as blue's (15 degrees, 15%), fixed for the campaign. Source: the US Army air-defence employment guidelines (mutual support, overlapping fires, weighted coverage toward the likely air avenue, defence in depth); the public text gives no distances, so every number is a judgment call. A site that would sit in the sea moves along nearby bearings, so coastal fields (Sochi, Gudauta, Gelendzhik) show some sites far off the axis. New campaigns only (positions are stored); a fresh campaign differs from before only in the SAM sites and their dug-in garrisons (same ids, variants, guards and every other asset unchanged, checked old against new for six campaigns). `tools/red_sam_report.py [level] [seed]` prints each site's bearing from the axis and distance for eyeballing.
* Next: orders by need (both sides), with blue scoot / retreat now that blue positions mean something.

## v0.41.64

* **Blue's air-defence sites sit at their own place, doctrinal with a seeded jitter** (PR 3 of the blue SAM build; XO 2026-10-21: "doctrinal, but randomness on the exact positioning so no two campaigns will be exactly the same"). Each blue site now stores its position (`sams.place_blue_site`): the v0.41.7 layout (Patriot toward the threat axis, the nearest enemy fighter field, at 4.5 km; AAA either side at +/-120 degrees, 3.5 km; HAWK the outer layer at +50 degrees, 6 km) plus a jitter of up to 15 degrees in bearing and 15% in distance, seeded by campaign id + field + site, so a field looks the same every day and different in the next campaign. The layout follows the US Army air-defence employment guidelines (mutual support, overlapping fires, weighted coverage toward the likely air avenue, defence in depth); they give no distances, so the numbers and the jitter are judgment calls. The mission builder places each BASEDEF group at its stored site, falling back to the old search when it lands on a runway or the sea. Older saves give their sites a place on load. With the jitter set to zero the 79 identity missions are IDENTICAL to v0.41.59; with it on, only the BASEDEF positions differ (new identity baseline saved for the next refactor).
* Next: red's placement by the same rule (own PR), then orders by need with blue scoot / retreat.

## v0.41.63

* **Blue's air-defence sites are damaged, repaired and rebuilt one by one, like red's** (PR 2 of the blue SAM build; XO 2026-10-21). Raid damage and the overrun hit now go through `sams.hit_field`: the drop in the field's mean strength is spread over the three sites outside-in (HAWK first, then Patriot, then AAA; outside-in is a judgment call, defence in depth), so a battered field loses its HAWK first, then its Patriot launchers, and the raid report names a site that was destroyed. `Base.defense` is now the mean health of the three sites. Nightly repair (supply-scaled, 0.10 a day) and the lent battery only touch standing sites: a destroyed site (health 0.05 or less) is not repaired but REBUILT, with red's rule (`sams.rebuild_blue_sites`: at least 3 days down, then the level's `blue_rebuild` chance a night times blue's supply, one a night, half health, never at a fallen field; a retaken field's defences rebuild too). `sams.air_defence` / `covering_ad` read the sites. Missions of a fresh campaign are unchanged (identity 79/79); what changes is how a hit field wears down and recovers over days.
* Not in this PR: scoot / retreat for blue (a site's position is not used by the mission builder yet: that comes with doctrinal placement), orders by need.

## v0.41.62

* **Blue's air defence is three sites per airfield, in red's record** (XO 2026-10-21: "I'd rather use red's because I think it's tested and it's not abstract"). Every blue airfield now has `bsam_<field>_pat`, `_hawk` and `_aaa`: the same `EnemyAsset` record as red's SAM sites (variant, health, parent field), kept in their own list `state.blue_sams` so the supply and garrison loops over `blue_assets` never touch them. The site health IS the strength; `Base.defense` is only a cache of the Patriot site's health for the readers not moved (GUI bar, war-sim score). Every writer goes through `sams.shift_field` / `sams.set_field` (raid damage, the overrun hit, a fallen field, nightly repair by supply, the lent battery). The mission builder reads the three sites (`sams.blue_battery(base, state)`; Patriot launchers by its health, HAWK stands at 0.6 or more, AAA 2 sites at 0.6, 1 at 0.15: the v0.41.30 thresholds, judgment calls, now per site). No behaviour change: all three sites move together for now, so missions are identical (identity check 79/79). An older save builds its sites from each field's `defense` number on load (no format bump; an older SQE opening a new save just ignores the list). Smoke test: checks for the sites, a hurt HAWK dropping out alone, round trip and old-save migration.
* Next (not in this PR): per-site damage, blue rebuild / scoot / retreat like red's, orders by need, doctrinal placement.

## v0.41.61

* **The "CAP engage range" boxes are gone from the settings page** (XO 2026-10-21: "Remove and take the defaults first. We'll be tuning CAPs later."). The enemy and friendly 50 nm values are now fixed in the mission options (`enemy_cap_engage_nm`, `friendly_cap_engage_nm`, both 50), so missions are unchanged. The two settings fields are removed; an old `settings.json` that still has them loads fine (unknown keys are ignored). The mission-side BARCAP / patrol rules will replace these limits.

## Unreleased (tools only, no version bump), identity check covers AI-only packages

* **`tools/miz_identity.py` now also builds the packages nobody can fly** (XO 2026-10-21, before the per-job code split): per case, one BARCAP, one fleet-defence (bomber / raid intercept) and one Fighter Sweep package, where the day's plan has them, built as the all-AI test with the package's first flight standing in for yours (key `aionly`). 19 extra missions, 79 in all (about 100 s a run); `selfcheck` repeatable; a change to the sweep station reach shows up as a difference. Baselines saved before this change must be saved again. Production code unchanged.

## Unreleased (tools only, no version bump)

* **Mission identity check, `tools/miz_identity.py`** (XO 2026-10-20: the refactor, the rename and the `_spawn_flight` split must not change a generated mission). `save DIR` builds 60 missions (9 campaigns, level 1-3, five jets, normal and "open skies" days with the red SAMs zeroed so strikes, counter-air, escorts and TARCAPs appear; each as your own flight and as the all-AI test), writes them out as normalised text; `check DIR` rebuilds on the changed code and prints a diff of anything that differs (exit 1); `selfcheck` builds twice on the same code and fails if the result is not repeatable. Runs in a temp folder, nothing of yours is touched, about 40 s a run. It pins campaign id, the builder's Random(), the global `random` and PYTHONHASHSEED inside the tool only. Production code unchanged. Not covered: fighter sweeps, BARCAP, bomber intercepts, and paths no case reaches (see the tool's docstring).
* CLAUDE.md: the code map names the tool.

## v0.41.60

* **PR B: one name per job in the waypoint actions and the settings screen** (XO 2026-10-21; no change to what flies). Waypoint actions now follow the role: the Fighter Sweep station is `SWEEP` (was `SWEEPSTN`); a package escort with no station of its own is `ESCORT` (was `SWEEP`) and a TARCAP with none is `TARCAP` (was `ESCORT`); their kneeboard notes say the same. A station is now recognised by `w.orbit` (or a TARCAP's own point) instead of an action-name list, so the lock rule in `_set_eta` keeps its old result (`STATION_ACTIONS` is gone). Settings: "TARCAP / escort / sweep engage range" and "AI TARCAPs, escorts and sweeps stop short of live SAM cover". There are no per-job flight classes (the job code lives in the mixin files from v0.41.56 to .59), so no class renames.
  * Checked: `tools/miz_identity.py` 79 of 79 identical with the default settings. A first try differed in four COUNTER_AIR missions (a SWEEP point became a "station" by name and lost its time lock); fixed as above. New variant `SQE_IDENT_NO_STANDOFF=1` (stand-off setting off, so the no-station routes are built): `mission` identical in all 79; only the kneeboard comms / times page differs (its waypoint notes were renamed), as expected. Smoke test passed.

## v0.41.59

* **Split step 6: the red air picture and the raid / reactive spawns moved to their own files** (XO 2026-10-21; NO behaviour change). Two more mixins that `MissionBuilder` inherits (like `StrikeTasks`, `FighterStations`, `SupportCaps`):
  * `sqe/red_air_picture.py`, class `RedAirPicture`: `_spawn_air_picture`, `_plan_cap_stations`, `_fleet_keepout`, `_cap_side`, `_fighter_wings` (red's known CAP stations from its daily air plan, the alert aircraft that scramble from enemy fields), with `RED_LONG_RANGE`, `RED_CALLIN_*`, `CAP_FLEET_KEEPOUT_NM`, `ALERT_REACH_NM`, `A2A_ZONE_NM`.
  * `sqe/raid_spawns.py`, class `RaidSpawns`: `_spawn_reactive`, `_spawn_raid`, `_spawn_raid_target`, `_raid_marshal`, `_raid_bend`, `_raid_cap` (red bomber raids and the extra pairs that launch mid-mission), with the `RAID_*` constants and `FLEET_RAID_AVOID_NM`.
  * `mission_builder.py` 2,490 -> 1,995 lines (3,080 before the split began). `ALERT_REACH_NM` no longer needs an import inside a method. The smoke test imports the moved constants from the new files.
  * Checked: `tools/miz_identity.py` 79 of 79 identical against a fresh v0.41.58 baseline; pyflakes finds no undefined name in `sqe/`; smoke test passed.
  * One name (`AAM_WEAPONS`) is still imported inside a raid method (the builder's file imports that one). Next: PR B, the renames (waypoint action names, class names, GUI labels).

## v0.41.58

* **Split step 5: the support-CAP code moved to its own file, `sqe/support_caps.py`** (XO 2026-10-21; NO behaviour change). Four methods left `MissionBuilder` (`_gather_support`, `_place_support`, `_pull_back_carriers`, `_support_cap_route`) and live in the class `SupportCaps` (a mixin, like `StrikeTasks` and `FighterStations`): which tanker CAP / HAVCAP / base CAP / carrier CAP a mission has, where the tanker and AWACS sit, the support CAP's route, and moving the carrier group out of the fight. The constants only they use moved with them (`TANKER_COVER_NM`, `SUPPORT_CAP_ZONE_NM`, `TNKCAP_ZONE_NM`, `CVCAP_ZONE_NM`, `CVCAP_NM`, `CVCAP_DETECT_MARGIN_NM`). `mission_builder.py` 2,650 -> 2,490 lines. Two names are imported inside the methods (`carrier_station`, `ALERT_REACH_NM`) because the builder's file imports this one; `ALERT_REACH_NM` moves with the red air-picture code in the next step. The smoke test imports `CVCAP_NM` and `CVCAP_DETECT_MARGIN_NM` from the new file.
  * Checked: `tools/miz_identity.py` 79 of 79 identical against a fresh v0.41.57 baseline; pyflakes clean; smoke test passed.
  * Next: the red air picture (`_spawn_air_picture`, `_plan_cap_stations`, ...) and the raid / reactive spawns, then PR B (renames).

## v0.41.57

* **Split step 4: the fighter-station rules moved to their own file, `sqe/fighter_stations.py`** (XO 2026-10-21; NO behaviour change). Ten methods left `MissionBuilder` (`_limit_engage`, `_launch_points`, `_sam_clear`, `_zone_sams`, `_clear_zone`, `_cover_circle`, `_hold_end`, `_extend_holds`, `_room`, `_sweep_station`) and live in the class `FighterStations` (a mixin the builder inherits, as `StrikeTasks` since v0.41.56). These are the engage circles, the SAM-clear stations and the hold times that TARCAP, escort and Fighter Sweep share. The constants only they use moved with them (`TARCAP_MIN`, `TARCAP_AFTER_TOT_S`, `ESCORT_AFTER_TOT_S`, `ESCORT_AFTER_EGR_S`, `HOLD_AREA_KM`, `HOLD_EXTEND_MAX_S`). `mission_builder.py` 2,820 -> 2,650 lines. The smoke test imports those constants from the new file.
  * Checked: `tools/miz_identity.py` 79 of 79 identical (the 19 `aionly` BARCAP / intercept / sweep missions included, against a fresh v0.41.56 baseline); pyflakes clean; smoke test passed on the second run (the first run hit the known flaky DEAD-stage check, `_de` None, listed in the queue; it passes on rerun).
  * Not moved on purpose: `_engage_tasks` (117 lines) and `_attach_waypoints` serve every job with role checks inside; they stay stages of the builder. Next: the support-CAP pieces, then PR B (renames).

## v0.41.56

* **Split step 3: the strike / SEAD / DEAD / CAS tasking moved to its own file, `sqe/strike_tasks.py`** (XO 2026-10-21; NO behaviour change). Nine methods left `MissionBuilder` (`_sead_attack_tasks`, `_dead_gate`, `_cas_tasks`, `_harm_time`, `_umbrella_keep`, `_harm_deg`, `_jsow_side`, `_cover_tors`, `_jsow_tasks`) and live in the class `StrikeTasks`, which `MissionBuilder` inherits (a mixin: like a C# partial class, the builder still calls them as `self._jsow_tasks(...)`). The constants only they use moved with them (`JSOW_ATTACK_S`, `JSOW_AIM_ERR_M`, `DEAD_GATE_*`, `SA10_GATE_KM`, `TOR_*`, `TRACK_RADARS`, `SEARCH_RADARS`, `SEAD_WAVE_KM`, `KPH`); the builder imports the ones it still uses. `mission_builder.py` 3,080 -> 2,820 lines. The smoke test imports `TRACK_RADARS` / `TOR_COVER_KM` from the new file.
  * Checked: `tools/miz_identity.py` 60 of 60 identical; pyflakes clean (the three old warnings only); smoke test passed. Not covered by the identity check: sweeps, BARCAP, bomber intercepts (none of the moved code is theirs).
  * Next: TARCAP / escort station code, then sweep and support CAP (with identity cases added first), then PR B (renames).

## v0.41.55

* **Split step 2: the SEAD attack tasks moved out of `_attach_waypoints`** (XO 2026-10-21; NO behaviour change). The ~50-line block that gives a SEAD flight its HARM tasks (own site, neighbouring sites, covering Tors, the umbrella) is now `_sead_attack_tasks(package, f, wp, w, armor)`; `_attach_waypoints` drops from about 115 to about 65 lines. Code moved as written.
  * Checked with `tools/miz_identity.py` against the v0.41.53 baseline: 60 of 60 missions identical; pyflakes clean (only the three old warnings); smoke test passed.
  * Next: the per-job classes, then PR B (renames).

## v0.41.54

* **`_spawn_flight` cut into named stages** (XO 2026-10-21, step 1 of the refactor; NO behaviour change). The 500-line `_spawn_flight` in `mission_builder.py` is now a short list of calls, each a method with a one-line docstring: `_support_cap_route` / `_flight_route` (the route), `_make_group`, `_dress_group` (loadout, names, jammers), `_engage_tasks` (engage circles, hold, homeward fight, ROE and range options), `_crew_setup` (your seat and radio, or an AI flight's frequency and fuel), `_announce` (manifest and radio calls), `_roe_defaults`, `_attach_waypoints` (each point's tasks), `_dead_gate`, `_home_leg`; `_pt` replaces the local lambda. The code inside is moved as written; only the inputs it needs became parameters and what later stages use is returned.
  * Checked with `tools/miz_identity.py` against v0.41.53: 60 of 60 missions identical; pyflakes finds no undefined name; smoke test passed. Not covered by the identity check: fighter sweeps, BARCAP and bomber intercepts (AI-only); their code is moved the same way and pyflakes passes.
  * Not done (later steps): the stages are still methods of the one `MissionBuilder` class, `_attach_waypoints` is still about 115 lines (the SEAD attack tasks inside it are the next piece), and the per-job classes (strike, SEAD, TARCAP, escort, sweep, support CAP) and the waypoint action / class / GUI renames (PR B) come after.

## v0.41.53

* **Red strength is tracked per squadron** (XO 2026-10-21, step 2 of the typed red squadrons). Each `RedSquadron` now has its own `available`, `reserve` and `rest_days`; the wing's `authorized` / `available` / `reserve` / `rest_days` are sums over its squadrons (`EnemyAirWing` properties). Assigning the wing's `available` still works and spreads over the squadrons (a loss comes off the strongest squadron, a gain goes to the one furthest below strength that is not resting), so code that only knows the wing is unchanged.
  * **Losses by type.** Mission groups record the aircraft type (`ac`), and the debrief takes dead jets off the squadron that flew that type (`EnemyAirWing.lose`); abstract raid losses (`raids.hit`, the war sim's raid resolution) take them off the raider's type first.
  * **Rest and return per squadron** (`airwings.py`): a red squadron at 30% or less stands down on its own and returns after resting; the rest of the wing keeps flying. Messages read "the squadron at <field> (<type>)". The wing used to rest as one block.
  * **Replenishment per squadron** (`war.end_day`): the wing's daily amount (unchanged) goes to the squadrons furthest below strength that are not resting. A cratered field scatters each squadron (x0.75).
  * **Types by what is serviceable.** A type counts as available only while a squadron of that type has a pair serviceable (`EnemyAirWing.types_up`). Raids (`raider_wings`), red patrol planning and sweeps (`redair`: pairs are cut from the FIGHTER squadrons' jets, not the wing total), red reactive pairs, escort picks for raids (`packages`) and the expected-defenders estimate (`threat.expected_defenders`: serviceable fighter jets) use it. The day's sortie budget is still the whole wing's.
  * Saves: v0.41.52 and v0.41.51 saves load (the wing's strength is spread over its squadrons in proportion; v0.41.51 saves get one squadron per type). No format bump. The waiting-room table shows each squadron as "MiG-29S 7/9" and marks resting ones.
  * Effect (40-day all-skip simulation, 12 seeds each, v0.41.52 vs this): L2 won in 22.2 vs 23.0 days, red raid packages 5.8 vs 6.8 per campaign; L3 raid packages 38.0 vs 42.5, red air left 0.56 vs 0.52. A red attack squadron that is shot up or resting no longer lets its fighter squadron's jets raid, and the reverse. Not tested in DCS.
* Smoke test: the air-rest check is per squadron; "[red squadrons]" gained checks for typed losses, sums, spreading, replenishment, `types_up` and loading v0.41.52 / v0.41.51 saves.

## v0.41.52

* **Red wings are cut into typed squadrons** (XO 2026-10-20 / 21, step 1 of the same-rules build: data only). Each `EnemyAirWing` now carries `sqns`, a list of `RedSquadron` (id, name, one aircraft type, authorized jets). The rule (XO's, sizes are judgment calls): `ceil(wing jets / max size)` squadrons, split as evenly as possible, never over the cap; max size L1 6, L2 12, L3 14 (`Difficulty.red_squadron_max`). The Tu-22M3 wing stays one squadron (L2 4, L3 10).
  * **Types.** The wing still draws its old mixed type pool (same random draws, so the world is laid out as before); `red_squadrons()` (scenario.py) deals it into squadrons: a wing of 2+ squadrons gets fighter, attack, fighter ... so it keeps one of each; a one-squadron mixed wing flies an attack type with the chance (attack types / pool types) from a Random of its own, otherwise a fighter. A wing whose pool has no fighter gets one. The wing's `types` are now the types its squadrons fly.
  * **Effect on red (XO chose "keep raid strength").** One-squadron wings can no longer hold both a fighter and an attack type, so fewer wings can raid: over 20 test seeds, wings with a Su-24M or Su-25 went from 118 to 79 of 160 (L2) and from 126 to 106 of 160 (L3); about 26 (L2) and 18 (L3) of 160 wings are attack-only and have no fighter squadron (no alert pair from them). Judgment call; if red feels too tame or too soft, the dealing in `red_squadrons` is the one place to change.
  * Not changed in this step: availability, losses, rest and replenishment are still tracked per wing (`available`, `reserve`, `rest_days`); per-squadron tracking is step 2. Saved campaigns from v0.41.51 still load (`sqns` empty; no format bump). The waiting-room GUI table shows each wing's squadrons ("MiG-29S x9, Su-24M x8").
* Smoke test: "[red squadrons]" checks the rule (sizes, cap, even split, mixed wing keeps both kinds), that every wing's squadrons add up to the wing, that the bomber wing is one squadron, and save / load.

## v0.41.51

* **Support-CAP pull-back removed** (XO 2026-10-20 22:39: three runs in a row showed `pulls` empty). The Lua hook no longer re-sends a support CAP its route when it leaves its circle (PR #77, v0.41.34); `PULLBACK_MARGIN_NM`, `PULLBACK_BINGO`, `_pull_entries`, the hook's `__PULL__` block and the `pulls` list in the results file are gone. The engage circle on every support CAP stays, and the tanker CAP keeps the default ROE (v0.41.35); the position tracks (v0.41.43) show whether a CAP ever leaves its circle.
  * Not tested in DCS. Cost of a wrong guess: a support CAP that chases out of its circle is no longer called back (none did in three runs); the tracks would show it.
* Smoke test: the pull-back check is replaced by "[cap circle]" (no pull-back in the hook, support CAPs keep their engage circle).

## v0.41.50

* **Role rename: one name per job** (XO 2026-10-20, PR A of the same-rules build). `Role.ESCORT` (the TARCAP) is now `Role.TARCAP`; `Role.SWEEP` in a strike / DEAD / CAS package (the package escort) is now `Role.ESCORT`; `Role.SWEEP` stays for Fighter Sweeps and the fleet-defence fighters. Every place that tested the old pair now tests the right new roles.
  * Saved campaigns: `FORMAT_VERSION` 5 -> 6. `_migrate_roles_v6` converts plan and pending flights on load (ESCORT -> TARCAP; SWEEP -> ESCORT unless the objective is COUNTER_AIR / FLEET_DEFENSE).
  * Behaviour is unchanged. Checked with `tools/miz_identity.py`: 60 of 60 missions identical to v0.41.49 once the text that shows the role name is mapped back. Expected differences only: the version string and the role name printed on the kneeboard fuel-code images (TARCAP / ESCORT instead of ESCORT / SWEEP).
  * Not done (PR B, with the `_spawn_flight` split): waypoint action names (`SWEEPSTN`, the fallback `SWEEP`), class names, GUI labels.
* Smoke test: aliased `Role` uses updated, "[roles v0.41.50]" checks a format-5 state migrates.
* `tools/miz_identity.py`: the version string is scrubbed, so a baseline from another version compares cleanly.

## v0.41.49

* **AI flights fly home above the ridges** (XO 2026-10-20 22:07 run: Venom 5-2, a lone F-16 TARCAP, went from 26,000 ft to 3,000 ft MSL about 50 nm out and flew level for 100 nm over rising ground, 914 to 1,127 m on its track, then died at 2574 s with 84% fuel and nobody shooting; every other flight went home over water at 2,000 ft). Cause, confirmed by the track: the recovery point (RCV) is added after the terrain check at a fixed 3,000-6,000 ft, and an AI flight drops to the next point's altitude right after the last one.
  * `home_leg_ft` (routes.py): the RCV altitude is raised to what the leg from the last route point needs (ground within 5 nm of the leg + 1,000 ft, or + 2,000 ft over mountains; capped at 20,000 ft). Same rule and margin as `terrain_clear`; without a ground-height scan nothing changes.
  * Support CAPs now run `terrain_clear` too (the support-CAP branch never did).
  * The mission hook's death record carries the last sampled position (`x`, `z`) and the ground height under it (`ground_m`, from `land.getHeight`), so the next run says where a jet died and whether the ground was near its altitude.
  * Not tested in DCS. Cost of a wrong guess: a flight comes home higher and steeper in its last 8 nm (RCV to the runway is not stepped).
* Smoke test: `home_leg_ft` with and without a relief grid.

## v0.41.48

* **Ground groups keep off the runways** (XO 2026-10-20 20:53: a target AAA formation lay diagonally across a runway; it could block the side's own aircraft). Sites and blue base defences are now moved sideways off any runway corridor before they are placed (`_on_runway`, `_off_runway` in `mission_builder.py`; the site centre is moved BEFORE it is stored, so the bomb point and the units agree).
  * pydcs gives only each runway's heading, so the strip is modelled as a corridor through the airfield reference point: `RUNWAY_HALF_LEN_M` 2600 m each way, `RUNWAY_HALF_WIDTH_M` 120 m either side, plus the group's own footprint margin (judgment call; not a surveyed runway). A site that is on it moves to the nearest clear dry spot up to 2.4 km away.
  * Not tested in DCS. Cost of a wrong guess: a strike target sits a few hundred metres from the airfield centre, or a corridor too wide pushes a defence slightly further out.
* Smoke test: "[runway]" checks no vehicle lies on a runway strip.

## v0.41.47

* **The JSOW flight stops hunting after its salvo** (XO 2026-10-20 18:27: the Squids lingered, moved closer after launching; all eight were lost, seven to Sukhumi / Gudauta MiGs, one to the SA-11). From the state file: the 30 nm launch point worked (first releases at 52-66 km, jets at 30 nm of the SAMs), but each Hornet then released a second and third time at 47-50 km (1354-1470 s, Squid 2's flight has ONE planned aim yet its jets fired at four different sites), so the jets crept to 21 and 16 nm of the SAMs and turned late. Cause: the JSOW waypoint sets WEAPON FREE, so a jet with JSOWs left hunts every radar and launcher it can see, closing to range; v0.41.46's stop time only ended the planned Bombing tasks.
  * A timed Option task on the JSOW waypoint: `JSOW_ATTACK_S` (120 s) after the point's ETA the ROE goes to Return Fire, so the flight drops what it is hunting and flies its route home (EGR already sets Return Fire).
  * **The Hornet JSOW kit is XO's own Mission Editor loadout** (captured from his `.miz` 2026-10-20): AGM-154A on stations 2 and 8 (TWO per jet, was four in two BRU-55s), AIM-9X on 1 and 9, AIM-120C-5 on 4 and 6, fuel tanks on 3 and 7, a Litening pod on 5 (was a third tank). `JSOW_PER_JET` FA-18C 4 -> 2 (the Viper kit already has two and a pod). XO: send more jets and lose fewer of them; later packages mop up.
  * **Two aim points a jet**: in a Standoff DEAD the JSOW flight now aims the covering Tor first (it shoots JSOWs and HARMs down), then a launcher, then the radars (the HARM flights go for those). Before: two radars, the Tors, the launchers, up to four.
  * Not tested in DCS. Cost: if a tasked release is still pending when the window ends it is dropped (JSOWs not fired); an open question is whether DCS drops a running attack when the ROE changes.
* Smoke test: "[jsow]" checks for the timed Return Fire and the new Hornet kit.

## v0.41.46

* **JSOWs are flung further out** (XO 2026-10-20: the JSOWers were still massacred; SAMs target them and enemy scrambles jump them). From XO's run (tracks + shots): 5 of 8 Squids lost, two to the Gudauta SA-11 at 14-18 nm, three to its scrambled MiG-29s. The AGM-154As released from 20,000 ft at 45-65 km (24-35 nm), but the JSOW point was 20 nm from the target, on the target's own SA-11 ring (about 19 nm), and the jets flew on to it.
  * `JSOW_LAUNCH_NM` 20 -> 30 (judgment call: inside the release range seen, about 10 nm clear of the SA-11 ring). A launch point pushed past it still goes high (`JSOW_HIGH_ALT_FT`).
  * The JSOW point now also keeps clear of the TARGET SITE's own live SAMs, each by its own ring (`AVOID_NM`: SA-11 20, SA-6 16, SA-2 26, SA-3 15); SA-10s keep the 40 nm they had (the loop used to force it for every entry).
  * The JSOW release tasks are time-limited: `JSOW_ATTACK_S` (120 s) after the launch point's ETA the flight turns for home. Before, Squid 2 flew on to 14 nm of the SA-11 for a second salvo.
  * The TARCAP and escort stations follow the new point automatically.
  * Not tested in DCS. Cost: if the AI will not release from 30 nm the JSOWs stay on the jets and the site survives; the scrambled MiGs are not stopped, only given about 10 nm more to fly.
* Smoke test: "[shepherd]" checks the 30 nm point; "[jsow]" checks the release tasks have a stop time.

## v0.41.45

* **Default merge radius is 25 nm** (XO 2026-10-20; was 50): fewer packages fold into yours, so fewer units, but nearby packages still merge. Only the default changes: a campaign or settings file that already stores a merge radius keeps its value (change it in Settings > Package merging). Smoke test and GUIDE updated.
* XO's own request, in his words: "Default merge radius to 25."

## v0.41.44

* **Station orbits are circles, not race-tracks** (XO 2026-10-20: "very long orbits, north to south"; the new tracks confirm it: Springfield 7 and Hornet 6 flew 57-60 nm from their station to RTB and back). DCS's default Race-Track orbit runs from its waypoint to the NEXT waypoint, which for a station is RTB. TARCAP, escort, sweep and SAM-held fighters now orbit in a Circle at their station. Support-CAP racetracks (CAP1 -> CAP2) are unchanged.
* Smoke test: the TARCAP check also asserts no station orbit is a Race-Track.

## v0.41.43

* **The TARCAP overwatches from behind the JSOW flight** (XO 2026-10-20: after the HARM shooters launch, the TARCAP turned round with them, then was out of position when red's second wave arrived; XO: that turn-round point should be the TARCAP's station). In a package with a JSOW flight the TARCAP station is `TARCAP_BEHIND_NM` (16 nm, judgment call: twice the escort's 8) behind the JSOW launch point on its axis, stepped back 1 nm at a time (at most 14 more) until it is outside every live medium / long-range SAM ring plus the stand-off margin. No 9 nm sideways step for these packages.
* **Position tracks in `SQE_state.json`**: the Lua hook records each group's lead unit every 30 s (`"tracks": {group: [[t, x, z, alt_m], ...]}`, at most 400 points a group) so a run can show where the TARCAP, escort and strikers actually flew.
* Not tested in DCS. Cost: a TARCAP that sits too far back to reach red fighters, or one that still chases (the tracks will show which). Not changed: the engage circle and the support-CAP pull-back.
* Smoke test: "[shepherd]" also checks the TARCAP station.

## v0.41.42

* **The JSOW flight is no longer left alone** (XO 2026-10-20: the run lost all five Standoff DEAD Hornets to Sukhumi / Gudauta MiG-29s after their JSOW release; the TARCAP and escort sat at the HARM point, 17-18 nm from the JSOW launch points, and the TARCAP's circle did not reach them). Two changes:
  * **The package escort shepherds the JSOW flight**: in a Standoff DEAD (a package with a JSOW flight) the escort's station is `ESCORT_BEHIND_NM` (8 nm, judgment call) behind the JSOW launch point, on the JSOW axis, not at the HARM shooters' stand-off station. It is NOT kept out of SAM cover (that is the shepherd's risk); it leaves from its station. Packages without a JSOW flight are unchanged. `routes.jsow_launch_nm` / `jsow_launch_xy` pulled out of `plan_route` so the builder can ask where the JSOW flight will launch.
  * **The TARCAP / escort fight circle takes in every shooter's launch point**: it is now kept out only by SA-10 reach (`_zone_sams(long_only)`), no longer by SA-2/3/6/11 rings, and may be up to `TARCAP_COVER_MAX_NM` (35 nm, judgment call). Before, the SA-11 rings pushed the circle 21 nm west of the JSOW points. The shooters' launch points are known before any flight is built (`_launch_points`), so the order flights are built in no longer matters.
  * Kept: `STATION_OFFSET_NM` (the TARCAP station's 9 nm sideways step toward the nearest red field: it puts the TARCAP on red's approach, not a cover offset) and the STATION_FRAC / STANDOFF_MARGIN_NM SAM stand-off of the TARCAP's own station.
  * Not tested in DCS. Cost: an escort or a TARCAP that chases into a SAM site (XO accepted this).
* Smoke test: new "[shepherd]" check (its own session).

## v0.41.41

* **Divert tower on COMM2 CH3** (XO 2026-10-20): it was COMM1 CH5. Radio presets, kneeboard and briefing follow the layout. An Air Force jet gets the divert field's VHF tower (its COMM2 is VHF only); a Navy jet gets the UHF tower. COMM1 now holds only AWACS, tanker(s) and JTAC.
* **Link 16: the AWACS is no longer a donor or member** (XO): members are your wing; donors are the Link 16 capable flights of the SAME package (their leads), and no other package's or support aircraft. Briefing line reworded. Not tested in DCS (does the HSD/TAD show the package flights?).
* Smoke test: radio layout check covers the divert channel.

## v0.41.40

* **Escorts stick to the last striker until it is out** (XO 2026-10-20: the DEADers were left behind at the mercy of enemy air). The package escort (SWEEP role) used to leave 3 min after the last striker's time over target, about when the strikers only reached their egress point. It now stays until the last striker's egress point + 2 min (`ESCORT_AFTER_EGR_S`, a judgment call), still capped at 30 min past its own hold; the old TOT + 3 min stays as the floor. TARCAP is unchanged (minimum time, leaves last by its own rule). Merged packages count by their TOT as before (their egress is not tracked). Smoke test: new "[escort egress]" check.

## v0.41.39

* **Ground units get explicit orders** (XO 2026-10-20): every red garrison and armour column, every blue site (garrisons, sector forces) and the CAS task force now carry weapons free + alarm state red on their first waypoint (`_ground_orders` in `mission_builder.py`; `_drive` uses it too, so the CAS drive-in is unchanged). SAM sites keep their own orders. Limit: the Mission Editor has no target-priority order for ground units, so "other ground units first, then parked jets" is NOT enforced; DCS picks the target. Untested in DCS whether ground AI fires at parked aircraft at all.
* Smoke test: new "[ground orders]" check.

## v0.41.38

* **TARCAP stays at least 15 minutes, then until the last striker is off target + 5 minutes** (the 15-minute minimum is back: it had been halved to 7.5 min in `_hold_end`) (XO 2026-10-20: TARCAPs left as soon as the SEAD flight headed home). Cause: the hold ended at the TOT of the flight being built for the player plus 5 minutes (at least 7.5 minutes after arriving). When the player flew the TARCAP that TOT was the TARCAP's own station time (Day 4 mission: station 1468 s, stop 1918 s = 7.5 min); when the player flew SEAD it was the HARM time, so the TARCAP left with the SEAD flight. Now `mission_builder.py` also feeds the latest target time of the package's own strike / SEAD / CAS flights into `_extend_holds` (capped as before by `HOLD_EXTEND_MAX_S`).
* The TARCAP task text now says "at least 15 minutes and until the last strike flight is off target plus 5 minutes" (packages.py, models.py comment). Smoke test: new "[tarcap hold]" check.
* Build: docs/GUIDE.md now says "Python 3.12 or 3.13" (was 3.11 or 3.12). The release workflow now builds with Python 3.13 (was 3.12) to match XO's machine and the Crew Chief workspace (smoke test passes on 3.13); `requirements-build.txt` needs PyInstaller 6.10 or newer. Not tested: the Windows release build itself.
* Docs: CLAUDE.md #82 / #83 (always reset origin URL; one queue doc; Sonnet 5.5 build rule), DESIGN_NOTES update for v0.41.36/37. XO's own commits since v0.41.35: v0.41.36 and v0.41.37 below, `.gitignore` removed, version rule in CLAUDE.md.

## v0.41.37

* **Enhanced stationing logic for TARCAP and ESCORT**:
  - Adjusted `STATION_FRAC` to 0.85 to provide better coverage from long-range SAMs.
  - Increased `STANDOFF_MARGIN_NM` to 5 nm to ensure effective cover from medium and short-range SAMs.
  - Improved the stationing logic to be more robust and ensure effective air cover.

## v0.41.36

**(XO) Player SPAWN WP on Kneeboard** Fixed the issue where player flights from land bases show SPAWN WP.

## v0.41.35

**Tanker CAP no longer weapons free.** In all three of XO's runs of 2026-10-16/17 the chasing support CAP was the tanker CAP, the only one with an explicit weapons-free ROE (v0.41.26, to make it shoot first). Weapons free means "engage any enemy group in contact" (Mission Editor docs, quoted on the DCS forum), which overrides the engage circle. In the third run the v0.41.34 pull-back fired twice (35 and 55 nm out) and Viper 1 kept going to 68 nm, firing at an Su-27 101 nm from its station, until the Sukhumi S-300 killed both jets: the ROE option outlives a new route. The base CAP, HAVCAP and carrier CAP use the default ROE and stayed home. Now the tanker CAP uses the default too; it keeps continuous radar search and maximum-range shots. Cost: it may shoot first a little less eagerly. The pull-back stays as a backstop. Smoke test: no support CAP is weapons free. Evidence is three runs pointing the same way, not proof.

## v0.41.34

**Support CAPs are pulled back when they chase out of their circle.** In XO's two runs of 2026-10-16 the tanker CAP left its engage circle (37 nm in one, 25 nm in the other after XO lowered the friendly CAP engage setting) and ran 50 to 78 nm out after red fighters, into the Sukhumi S-300, which killed both jets each time. DCS's engage-in-zone circle chooses targets but does not hold a flight once it is chasing one, so lowering the setting did not help.

* **Backstop in the mission's Lua hook:** every 10 s, a support CAP (tanker CAP, HAVCAP, base CAP, carrier CAP) whose lead is further than its engage circle plus 10 nm (`PULLBACK_MARGIN_NM`) from the circle's centre gets its own route again from its first orbit point, with its engage circle. That drops the chase. It is then left alone for 2 min. Not pulled: a flight out of air-to-air missiles or below 25% fuel (`PULLBACK_BINGO`, it is going home), or past the end of its time on station.
* **The CAP engage settings keep their job:** the friendly setting still sets the circle (the smaller of the setting and each CAP's own figure), and the pull-back line follows it. The enemy setting is not touched. Recommended to XO: both back to the 50 nm default (25 nm only shrank the tanker CAP's circle and did not stop the chase).
* **Logged:** each pull-back is written to the results file (`pulls`: group, time, how far out, the limit).
* The 10 nm margin and the 25% fuel are judgment calls, not sourced. Untested in DCS so far: whether the AI takes the new route in the middle of a fight (it should: a new route replaces the current task).
* **Fixed (v0.41.33's sweep):** the builder's station search from the sweep's PUSH point can find no clear spot; it then backed out toward home like the old sweep (a smoke run put one 108 nm short of its red flight). The planner now stores the station it checked, and the builder uses it in that case.
* **Smoke test:** every support CAP has a pull-back entry centred on its engage circle, at the circle plus the margin, and the route it gets carries the engage circle.

## v0.41.33

**Fighter Sweep: hunts known enemy air out in the open, no more baiting (XO 2026-10-16).** XO's run (Viper 1, AI only) lost two F-15Cs of the sweep Dodge 2 to the Sukhumi S-300 in the first 95 seconds: the sweep was spawned on a station 37 nm from the site (clear by the old 35 nm rule) at 30,000 ft and was shot at from 34 nm. v0.41.13 had put the station inside the nearest red field's scramble circle, at the very edge of SAM reach, to pull red up.

* **Dispatch:** command sends a sweep only against a known red flight from red's own air plan for the day (a patrol pair or a red sweep) within 80 nm of the area, out in the open (12 nm outside every medium / long-range SAM's reach), with a SAM-clear station short of it, and up in the sweep's window (10 min before to 60 min after the first covered package). Otherwise no sweep: the packages' TARCAP and escorts carry the fight. The package names the flight it goes after (`extra["sweep_vs"]`).
* **Station:** 20 nm short of that red flight, on its line toward the sweep's home (or swung up to 60 deg off it), 45 nm from every SA-10 and 20 nm outside every other SAM ring, outside red's scramble circles where it can be. The fight circle takes in both stations as far as it stays clear of SAMs. New module `sqe/sweep.py`.
* **What it does to the campaign:** red's patrols sit over the SAMs they guard and red's sweeps sit at the S-300's edge, so on day one no sweep flies at Normal or Hard. Measured on 10 campaigns: Hard gets 9 sweeps once the SA-10s are down; Normal gets 8 once the SA-10s, SA-11s and SA-2s are down. XO: rare on Hard is fine.
* **Doctrine:** AFDP 3-01 (Counterair) defines the sweep as an offensive mission "to seek out and destroy enemy aircraft" whose need "will depend on the air and missile threat": supports the trigger. Keeping the sweep out of SAM reach is not doctrine: a judgment call from XO's runs (DCS AI fighters do not evade SAMs). The 45 / 20 / 12 / 20 nm figures are judgment calls (the 45 from the 34 nm S-300 shot), tunable in `sqe/sweep.py`.
* **Smoke test:** the sweep check now takes the medium / long-range SAMs down first (as SEAD / DEAD would) and checks that every sweep names a red flight in the open, its station is clear by the sweep margins and within reach of that flight.

## v0.41.32

**Fixed: DCS refused to save a mission ("Viper 2: Waypoint 8 have both unlocked speed and time and not surrounded by waypoints with locked time!").**

* **Cause:** `_spawn_flight` forced the player's landing waypoint speed free ("so it never closes a locked-speed run"), a leftover from a different, already-fixed Mission Editor rule (v0.41.2). `_trailing_steerpoints` then appends the DIVERT/TKR/BULLS reference points after landing, none of them time-locked — so the landing point was never followed by a time-locked waypoint and broke the mirror rule: a point with both speed and time unlocked needs a locked-time point on each side. Reproduced on every player flight that gets the trailing steerpoints (not just raid scrambles).
* **Fix:** stopped forcing the landing point's speed free (`land_at()` already leaves it locked, which is safe). `_free_locked_speeds` now also walks the tail after the last time-locked waypoint and locks the speed of any point that would otherwise be both-unlocked, so the rule holds even if more trailing points are added later.
* **Smoke test:** the raid-scramble build (a real player flight, not the AI test) now checks every player waypoint against both ME rules (`_bad31` check). Caught nothing further.
* XO's quick ME workaround for an already-generated mission (lock the named waypoint's speed or time, then save) still works and is no longer needed on new builds.

## v0.41.31

**Red raids keep clear of the carrier group:** a red raid's ingress and way home now bend round the fleet as well as round blue's Patriot fields, keeping 70 nm from the carrier unless the fleet is what it is raiding. Red's target pick (Normal / Hard doctrine) also shies from targets inside that circle. The 70 nm is measured: in XO's runs the cruiser's SM-2s killed CAP pairs 51 to 67 nm out. Smoke test: a raid leg through the fleet is bent round it.

## v0.41.30

**Blue air defence at doctrinal strength, every field alike (XO: "all bases are important"):**

* **Every blue airfield built in a mission gets the full set:** a Patriot fire unit with 8 launchers (was 3), a HAWK battery with 6 launchers and 2 tracking radars (was 3 launchers and 1 tracker, and only at your home field), and both AAA sites. Sources: FM 44-85 App. B (Patriot fire unit = 1 radar, 1 ECS, 1 power plant, 1 antenna mast group, 8 launching stations) and the Phase III HAWK battery (6 launchers, 2 HIPIR). A damaged field (defense 0.15-0.6) keeps a reduced Patriot (launchers by its defence) and one AAA site, with no HAWK. Below 0.15 nothing stands, as before.
* **The war sim counts the batteries:**
  * An unflown raid on a blue target is fought by the batteries that cover it, worth up to 4 fighters for a full Patriot + HAWK.
  * Surprise raids are stopped more often under a full battery (up to 95%), and lose more jets when they are.
  * A raid that gets through still loses an extra jet to a full battery, and does less damage to the field.
* **Red's raids shy from every full field's HAWK**, not only yours (Normal / Hard doctrine, as before).
* All the numbers live in `sqe/sams.py`. The thresholds and the sim weights are judgment calls; the launcher counts are the doctrine.
* Not tested yet: whether more launchers raise the Patriot's fire rate in DCS, or only the missiles on the rails. Count the shots in the next raid.
* Smoke test: the doctrinal launcher counts, a HAWK at every full-strength field, and the war sim's battery cover.

## v0.41.29

**Red raids fly blue's shape and stop rushing in (red side):** XO wants raids that stop rushing to their deaths like RTS units.

* **Marshal and TOT:** a raid now marshals on red's side and orbits there until it must push. The marshal is in a red SAM's cover along its way in and at least 60 nm from the target, or just off its own field if there's no such site. From there it flies PUSH (10 nm on), its ingress, and the target at its own TOT, which is 1 to 2.5 minutes after our intercept is on station, then on to the target. It shows up at most 10 minutes before it pushes. With no time to hold, it starts on its way in but never closer than 40 nm to the target, and arrives late rather than early.
* **Ingress bends round blue's Patriot fields** (40 nm, every field with standing defences except the one it raids).
* **Egress and home:** off target it turns 40 degrees off its way in, leaves 30 nm, and flies home round the Patriot fields. It goes home on bingo fuel.
* **Escorts stay with the bombers:** a real escort task tied to the bomber group, fighting only what comes within reach (Su-27 25 nm, the rest 15 nm), up to the egress point. Home once out of air-to-air missiles. No chasing.
* **Red long-range class = Su-27 only** (XO; the MiG-31 isn't in rotation). Red patrols engage inside 25 nm of their station for the Su-27, 15 nm for the rest. Every red patrol used 25 nm before.
* The new distances (60 nm marshal, 40 nm minimum, 30 nm egress, 10 min hold) are judgment calls, not sourced.
* Smoke test: the raid reaches its target after our intercept's TOT, has a PUSH and an egress, and its escorts fly an escort task. Red's long-range class is the Su-27.

## v0.41.28

**GUI Changes (XO):**

* Removed the text 'untested in the cockpit' in the F-14B(U) setting. 
* Capitalized the B in Mission Build tab on Settings.

**Updated Readme (XO):**

* Wrote the contents of readme.md in my own words.

**Raid scrambles are back (XO):** `RAID_SCRAMBLES` is on again, so an emergency can scramble you against a raid on a blue field.

**Raid scrambles follow the TARCAP rules (blue side):** from XO's Kobuleti run, where the Eagles went to dogfight range and lost to Fulcrums, the raid hit about 10 minutes before the scramble's TOT, and the raided field had no defences.

* **Station on our side of the SAMs:** the intercept station (40 nm out on the raid's bearing, 85 nm for the fleet) steps back toward the field until it is clear of red SAMs, the same rule as the support CAPs.
* **Route bends round red SAMs** on the way out to the station, like a strike's. The orbit itself is left as it is.
* **Engage circle, no chasing:** AI scramblers fight only inside a circle that takes in their station and the raided field (25 nm round the long-range shooters, 15 nm for the rest, larger where it has to reach both), moved or trimmed clear of red SAMs. They shoot at maximum range with the radar searching, and go home once their air-to-air missiles are gone.
* **Raid timing:** a raid from a nearby field used to be placed at the start of its path and flown at once, so it arrived early. Now it starts late enough to cross the station about 1 to 2.5 minutes after the scramble's TOT.
* **Raided field defended:** the field being raided now gets its base defences in the mission, even when nothing launches from it.
* **Merge circle on the raided field:** packages whose targets are within the merge circle round the raided field (same time window) are folded in. A raid package is still never folded into someone else's mission.
* Smoke test: a raid scramble may be offered while `RAID_SCRAMBLES` is on, and the flag is restored after the raid test (it used to be forced off). The raid build checks the raided field's defences and the intercept's engage circle.

## v0.41.27

Only the job types that have been tuned are offered to you; the rest stay in the war, flown by the AI.

* **AI-only for now:** BARCAP, bomber intercepts and raid intercepts are still planned, still listed under "All squadrons" and still played out by the war sim, but they have no FLY button, you're never put in one, and they're never folded into your mission. Their routes and fight circles don't follow the SAM rules yet (in XO's run six BARCAP jets wandered inland over red without a single scramble). They come back one at a time, the bomber intercept "boss fight" first.
* **Emergencies:** troops in contact (CAS) stay; raid scrambles are off while intercepts are AI-only.
* **Carrier further out to sea (XO):** about 86 nm west of Batumi (was about 54 nm west of Kobuleti), so the escort ships stop swatting every red jet up the coast. New campaigns only.
* **SEAD waves on one SAM cluster go in together again:** the packages are grouped by connected clusters (close to any target in the group, not only the first one's). With the carrier further out, the old grouping split the Gudauta cluster and its SA-11 package went in 15 minutes ahead of the others.
* Smoke test: AI-only jobs are never offered; emergencies are troops in contact only; the land-raid build is still tested with the AI-only list lifted; the ruins check runs on level 2 (on Hard a cluster's SEAD packages now all go in together, so there are no earlier ruins); the in-mission HARM spread allows 20 s (was 15; 18 s with the carrier's longer legs).

## v0.41.26

From XO's Nalchik SA-6 run: the tanker was shot down in the middle of the fight, and the F-16s guarding it were timid.

* **Tanker placement:** the tanker track still sits between the fight and home, where the package can use it, but now keeps a minimum distance from every danger, both ends of the racetrack included: 20 nm outside every SAM ring and every enemy field's scramble circle (was 15), 40 nm from every red patrol station, and 25 nm from the lines red fighters fly in on (each enemy field within reach to each target in the mission). Among the clear spots, one under friendly SAM cover (within 30 nm of a defended friendly field or the carrier group) wins, then the one furthest forward. Scan over 16 campaigns: 4 of 32 tankers used to sit on a red inbound line, now none; the typical tanker sits about 58 nm from the target (was 44).
* **Tanker CAP (F-16s):** it engages anything inside 40 nm of the tanker (was 25), radar searching all the time, weapons free, firing at maximum range, and stays on its leash round the tanker.
* Smoke test: the tanker track stays off a red inbound line.

## v0.41.25

From XO's second Sukhumi run (v0.41.24): 10 friendly jets lost, 4 of them the Gudauta SEAD flight to the Sukhumi S-300 again, and some Hornets never recovered at the boat.

* **HARM points, properly this time:** v0.41.24 kept a HARM point clear of every SAM "not sent against", but counted any SA-10 whose reach covered the target as one the package was sent against. The Sukhumi S-300 covers the Gudauta SA-6, so the Gudauta package still fired from 30 nm of it, and nobody's HARMs were on it. Now only the sites the package's HARMs are tasked on are exempt: the target's cluster and its umbrella SA-10 (and, for a CAS escort, the sites covering the CAS target). The HARM point moves out or turns its axis to clear every other site, and if it can't, the HARMs go for that site first.
* **Recovery net:** a flight sent home early (bingo, out of missiles) flies straight to its deck or field and skips its recovery point, so it never counted as landed and circled the boat. Every homebound AI flight is now also recovered once any of its jets is within 12 nm of the carrier (where the boat is at that moment, not where it started) or of its field, after its work is done.

## v0.41.24

From XO's Sukhumi SA-11 Standoff DEAD run (13 friendly jets lost: 5 to SAMs, 8 in the air).

* **Fighters stay off the target's SAMs too.** Since v0.41.22 every fight circle was trimmed clear of SAMs, except the ones the package was sent against. That exemption is right for the HARM and JSOW shooters but not for fighters: the TARCAP's circle was centred 23 nm from the SA-11 with a 35 nm radius, and Springfield 1-1 and Hornet 3-1 chased bandits into it before the HARMs arrived. TARCAP, sweep, escort, support CAP and homeward circles now stay clear of every SAM, the target's included. In a 12-campaign scan 6% of fighter circles are still at their 8 nm minimum with the edge a few nm inside an SA-2's ring; none reaches over a site.
* **HARM launch points clear of neighbouring SAMs.** A Gudauta SEAD flight's HARM point sat 30 nm from the Sukhumi S-300 (another package's target), and three Hornets died to it. The HARM point now stays outside the reach of every SAM the package isn't sent against, as well as the umbrella SA-10: it moves further out along its axis, and the axis may turn 15 or 30 degrees. When nothing is clear, the HARM flights fire on the neighbouring site first. Scan: 190 HARM points, none inside a neighbour's reach.
* **Enemy air wings panel:** aircraft types show their proper names (Su-27, MiG-29S, Tu-22M3) instead of DCS's internal ones (XO).
* `docs/GITHUB_GUIDE.md` is ignored by git; it stays local (XO).

## v0.41.23

Fight circles moved instead of shrunk, and preloaded flights placed right.

* **TARCAP, sweep and escort circles:** instead of only shrinking round a fixed centre, the circle's centre moves (up to 24 nm, toward our side first, then up to 90 degrees off) to where a full-size circle is clear of every SAM the package isn't sent against. A TARCAP's circle covers the package's launch points and its own station, 20 nm at least. Measured over 12 campaigns: 94% of these circles are now full size (v0.41.22: a typical one lost a quarter of its reach, about 1 in 12 was down to 8 nm); 2% are still at 8 nm.
* **Homeward fight:** when the one circle over the way home would reach a SAM (it did in 136 of 320), it's split into two or three smaller circles along the way home, each clear of SAMs.
* **Preloaded flights:** a flight from an earlier package already airborne at mission start is placed counting its time on station. One still within its hold starts on its station with the rest of its hold, instead of past it on its way home.
* Compiled Python cache files are no longer tracked in the repo.
* Smoke test: a preloaded flight within its hold starts on its station.

## v0.41.22

All blue flights stay away from SAMs they aren't sent against. A scan of about 30 sorties (some 700 AI flights) found fighters chasing bandits over SA-2s and SA-11s, JSOW flights launching 20 nm from a neighbouring SA-2, and support CAPs flying home over one.

* **Fight circles:** every blue air-to-air engage circle (sweeps, TARCAPs, escorts, SEAD, support CAP, the homeward fight) ends outside the reach of every live SA-2/3/6/11/10 that isn't the package's job, never smaller than 8 nm (homeward: 20 nm). A sweep or TARCAP can still fight on its station; it no longer follows a bandit over a SAM. Fight circles reaching into a SAM's reach went from about 300 to about 80 of 700; the rest are 8 nm circles whose edge is within a few nm of an SA-2's ring.
* **JSOW launch points:** the Standoff DEAD's JSOW flight tries approaches 30, 50, 15 and 70 degrees either side of the HARM axis and takes the first whose launch point and IP are outside every other SAM's reach. When none is, it takes the one with the most room and the package's second HARM flight also fires on the sites still in reach.
* **Support CAP home leg** bends round SAM sites like the strike routes.
* Smoke test: no blue AI route inside a SAM it isn't sent against.

## v0.41.21

* **Carrier CAP pulled in:** the F-14s orbit 12 nm from the boat (was 22) on a 10 nm leg, and engage within 30 nm of it (was 50). Their orbit and engage circle stay outside every enemy field's scramble circle (5 nm margin), so they no longer set off red's alert pairs ahead of the package. They're there to guard the boat, not to start fights.
* Smoke test: the carrier CAP's orbit is outside every scramble circle.

## v0.41.20

No needless banzai: nobody flies into defences it can't survive unless the situation calls for it. Blue always; red by its doctrine for the level.

* **CAS gate:** front-line and garrison CAS, and the emergency "troops in contact" event, are gated like strikes. Under a live SA-2, SA-3 or SA-6 the CAS goes out only with a SEAD flight (its HARMs on the covering sites through the CAS window); with no HARM jets free that day it waits. Under a live SA-11 or SA-10 there is no CAS: that site gets its Standoff DEAD first. Short-range SAMs and guns stay the CAS flight's problem, as before.
* **Gate reach:** the SA-10 gates targets within its measured reach (35 nm), not the 48 nm ring table, as the CAP stations have since v0.41.14. Strikes and counter-air follow the same reach.
* **Routes:** AI strike, SEAD and CAS routes bend round every live medium / long-range SAM that isn't their target (SA-2 26, SA-3 15, SA-6 16, SA-11 20, SA-10 35 nm), not only SA-10s.
* **Red doctrine by level:** red fighters commit only with a quality-weighted edge (a MiG-29 or Su-27 counts 0.67 of a blue fighter, older types 0.5): Easy at any odds, Normal at even odds, Hard at 2:1. A patrol called in to a SAM site it guards holds its station instead when outgunned, unless that site is the one blue is attacking (then it fights at any odds). An outgunned red sweep near the fight stays home.
* **Red raids** on Normal and Hard prefer softer targets: aims under a full-strength field's Patriot (40 nm) weigh half on Normal and a quarter on Hard; Hard also shies from your home field's HAWK (25 nm). Easy is unchanged.
* Smoke test: no CAS under an SA-11/10, escorted CAS under an SA-2/3/6 flies with its HARM flight, red commit thresholds, raid weights.

## v0.41.19

Rolling back the SAM belt. From the v0.41.14 Gudauta fuel-farm run: a strike was planned under a live SA-6 (the planner's SAM-belt rule skipped the target's own cluster), flew low because of it and lost all four jets; and Gudauta's alert pairs never got airborne.

* **Strike gate:** a strike or counter-air package is not planned while a live medium / long-range SAM (SA-2, SA-3, SA-6, SA-11, SA-10; partly destroyed sites count while above a quarter strength) covers its target, unless that SAM is suppressed. The covering site goes up the DEAD list instead. As the belt is taken down, the targets behind it open up, and with no SAM left to hide from the strikes fly at height.
* **Standoff DEAD by default:** every DEAD on a medium / long-range site is a Standoff DEAD (HARMs plus JSOWs). No JSOW jets free that day: it is not planned, and the planner offers it again the next day (no Close DEAD fallback).
* **Stuck alert pairs fixed:** the smoke and fire placed at earlier strikes' ruins set off an explosion at 4 s. On an airfield that killed the airbase in DCS, which then started nobody there. Airfield ruins are smoke only now.
* Smoke test: no strike under a live gate SAM; DEADs on such sites are Standoff with their JSOW flight.

## v0.41.18

* **Settings: AI landings,** one for carriers and one for airfields:
  * **Always skip:** AI flights going home there are recovered short of the base (10 nm from the boat, at their 8 nm entry point for a field), count as landed and leave the mission.
  * **Skip at your home deck / field:** only where you land.
  * **Land for real:** DCS landings and ATC.
  
  Defaults: carrier Always skip (as v0.41.17), airfields Land for real. Your wingmen are recovered too, at your home, when its type skips.

## v0.41.17

* **Carrier recovery without the deck queue.** An AI flight going home to the carrier is recovered at a point 10 nm from the boat: every jet still flying counts as landed (debrief and war sim) and the group leaves the mission. DCS's carrier landing queue ran an F-14 dry and stacked AI in your pattern.
* **Your wingmen too:** once you are back within 10 nm of the boat after your TOT, your wingmen are recovered the same way, so you trap alone. Airfields are unchanged (the AI still lands there for real).
* Briefing: a low-level profile now reads "from the LOW point, 30 nm out" (v0.41.16 moved the descent there).

## v0.41.16

From the v0.41.14 Gudauta fuel-farm run: the whole Venom 7 strike flight was lost. The low-level run started at the IP, 70 nm from the target (the IP sits half way out on long routes); three F-16s flamed out (the wingmen queued at the tanker behind the lead until they were dry); the lead refuelled, bombed alone 30 min after its TOT and was shot down by a live SA-6.

* **The low-level leg starts 30 nm from the target:** the flight cruises to the IP at height and descends at a new LOW point. Your kneeboard shows it.
* **Bingo fuel for your own flight too:** your AI wingmen head home on bingo instead of waiting at the tanker until they flame out.
* **No late attacks:** an AI strike flight only drops within 10 min of its TOT; later, it flies on to its egress and home.

## v0.41.15

From the v0.41.14 run: fighter flights chased MiGs north toward Gudauta and Sochi after their hold (the homeward 20 nm circle moved with the jet) and died to Sochi's alert pairs; and F-16s flying Fighter Sweeps had to get close to kill anything, which drags them toward the SAMs.

* **The homeward fight stays over the way home:** after the hold, a TARCAP / escort / sweep engages inside a fixed circle covering its station-to-home leg (plus 20 nm), not a circle that moves with the jet.
* **Fighter Sweeps fly F-15Cs and F-14s only.** No long-range fighter free: no sweep that day (the packages keep their TARCAPs). You are offered a sweep only in an F-15C or F-14.
* **Long-range sweeps stand at the edge of the scramble circle** (2 nm in, was 5), as far back as it allows, and reach in with their missiles.
* Smoke test: sweeps are F-15C / F-14 only; the homeward circle is fixed.

## v0.41.14

From the v0.41.13 run (1 jet lost, 20 red aircraft down, the target at 86%): the F-14 carrier CAP never fired, orbiting 3 nm from the boat while the SM-2s took everything; the sweep chased a MiG to 10 nm of the Sukhumi SA-10 and lost Venom 9-2.

* **Support CAP stations use the measured SA-10 reach.** Orbits keep 35 nm from a live SA-10 (it never fired beyond 31 nm in the runs) and 15 nm outside every other SAM ring. The ring table's 48 nm pushed the carrier CAP back onto the boat; in the test campaign it now orbits 18 nm out.
* **The carrier CAP engages within 50 nm of the boat** (was 35), so the Tomcats shoot ahead of the SM-2s.
* **Support CAP snipes at maximum range and goes home when out of air-to-air missiles** (it had neither setting).
* **The sweep's engagement circle stops short of SA-10 reach,** so it lets red come out to it instead of chasing into the SA-10.
* Settings: the splash damage hint says on by default.

## v0.41.13

From the v0.41.12 runs: the Batumi sweep orbited just short of SAM cover, tripped no scramble circle and met only SAM missiles; the carrier CAP's F-14s were shot at on a station 22 nm toward Sukhumi.

* **The Fighter Sweep pulls red up.** Its station sits inside the nearest enemy field's scramble circle (5 nm in), so the alert pairs launch into the sweep before the strikers arrive, while staying 35 nm from every live SA-10 and 15 nm outside every other SAM ring. It searches round the circle's edge for a clear spot.
* **The sweep holds until the first package it covers is over the target** (plus 2 min), at most 30 min longer than before; bingo fuel or no missiles still send it home. The 10 min lead stays.
* **Support CAP stations stay out of SAM range:** carrier CAP, tanker CAP, base CAP and HAVCAP orbits stay 15 nm outside every SAM ring, stepping back toward what they guard.
* **Defaults:** splash damage on (the ECM script stays off). A default applies to a fresh settings file; your saved settings keep your choice.
* Smoke test: sweep station inside the scramble circle and clear of SA-10s; the new defaults.

## v0.41.12

* **No DEP point from a land base.** After take-off the first point is the marshal point, for you and for AI runway starts. The DEP sat 6 nm out at 8,000 ft with PUSH about a mile on at 26,000 ft: a steep climb and a turn back over the field. The two unexplained crashes 3-5 minutes after take-off were both runway starts out of Batumi. Off the carrier the DEP stays: it is the departure radial.
* **A sweep's PUSH is ahead of its base,** 15 nm toward its station (it was behind the base), so a sweep climbs straight out instead of turning back over its field.
* Smoke test: no DEP from a land base, sweep PUSH ahead of the base.

## v0.41.11

From the v0.41.10 sweep run (73 min; good SEAD on the Sukhumi cluster, both early-warning radars down): the Sukhumi SA-10 got 4 Hornets, it fired from 50-57 km; two JSOW flights bound for Gudauta passed 31 nm from it on the way; two AI jets ran out of fuel; red's patrols guarded rear-area sites.

* **AI strike, SEAD and CAS routes bend around every live SA-10 that is not their target** (or the umbrella their HARMs go for), keeping 35 nm, with a turn point where a leg would pass inside.
* **HARM launch point 35 nm** (was 30): the SA-10 engaged the HARM shooters at 31 nm. The AI already fires from 35-38 nm.
* **JSOW flights push 2 minutes after the HARM shooters** (was together), so they reach SA-10 range once the HARMs have landed, not while they are in the air.
* **Bingo fuel for every AI flight** (was only fighters on station). A Viper and a Tomcat ran dry in that run.
* **The tanker serves the whole mission:** its track starts from the middle of the fields the mission's flights fly home to, not only yours.
* **Red patrols guard front-line SAMs:** a wing can guard any SAM site within 150 nm (was 60), so the big rear wings send their patrols forward.
* **Kill counts count real targets only:** units and static objects, not scenery flattened by the bombs.
* Smoke test: HARM point 35 nm; a route bends around an SA-10.

Investigated, not changed: a single AI jet crashing 3-5 minutes after take-off (Colt 6-4, Venom 3-4, both 4-ships out of Batumi, low, full fuel, no shooter). Needs a look at the departure in DCS.

## v0.41.10

From the v0.41.8 sweep run: the F-15 TARCAPs went home 5 minutes after their own package's TOT while later packages were still coming through; the F-16 sweep never fired (15 nm circle) and one jet flamed out; two F-15 wingmen collided on the way home (the second time); red's patrols sat far north and never came to their SAMs' help.

* **TARCAP and escort hold until the last package over their target area is off target** (targets within 60 km), not only their own; at most 30 minutes longer.
* **Sweeps engage within 25 nm** of their station whatever they fly (F-16s had 15).
* **Bingo fuel:** AI fighters on station go home on bingo instead of running dry.
* **Missiles kept for the fight:** on the way out, TARCAP, escort and sweep shoot from halfway between maximum range and the no-escape zone (fewer, surer shots); from their station on, maximum range (snipe).
* **Red patrols guard their SAMs.** Red has its own "briefing": each patrol pair takes a station 10 nm in front of the SAM site its wing rates likeliest to be attacked (value, closeness to our fields, recent attacks, and, by level, whether red read today's targets right: 25 / 50 / 75%). When we come within 50 nm of that site, the pair is called in to fight over it.
* **Red patrol stations** keep 45 nm from our marshal point and fields (was 120 / 80 nm, which pushed them out of the fight once the marshal moved close to the base).
* **Base CAP over the field red is likeliest to raid** (the raid planner's own weights: nearer and softer fields first), usually the strikers' home field.
* **Deconfliction:** AI flights cross PUSH and EGR on their own lanes (1.5 nm apart, egress 1,000 ft apart by slot) and come home through their own entry point 8 nm from the field on their own bearing and height.
* Smoke test: staged missile ranges and bingo option, red patrols over the sites they guard.

## v0.41.9

From the v0.41.8 Batumi run (you on a Fighter Sweep): no tanker CAP, HAVCAP, base CAP or carrier CAP anywhere in the mission. A sweep plans no support CAP, and the packages folded into the mission had theirs dropped (support is shared), so the tanker, the AWACS and the boat flew unguarded.

* **The mission's support CAP comes from all its packages, one of each kind:** a tanker CAP, a HAVCAP, a base CAP per home field and a carrier CAP per carrier. Yours first; what yours lacks comes from the first folded package that planned it. The war sim already counts those sorties in that package's plan, so no extra jets are used.
* Flight frequencies: when the VHF band's 1 MHz grid is full (a big mission), any free channel 0.5 MHz apart, instead of failing the build.
* Smoke test: a sweep mission takes one of each support CAP from the packages it covers; the campaign plan is not changed.

## v0.41.8

From the v0.41.6 Sukhumi run: not one red alert pair was called. Gudauta's scramble circle was 29 nm round the field. The stand-off wave stayed outside it: HARM shooters about 32 nm out, now firing from their launch point (open fire) instead of drifting in after other radars, and JSOWs released 40 nm from the SA-10 next to the field. So it HARMed and bombed that SA-10 while the field slept.

* **An enemy field next to a live long-range SAM sees as far as that radar.** A field with a live SA-10 within 15 nm scrambles on a 50 nm circle (at least), so a Standoff DEAD on the SA-10 brings its alert pairs up.
* Marshal points and the forward tanker keep clear of the bigger circles too. In the test campaign the marshal points stay 15 nm behind their bases.
* Smoke test: every field next to a live SA-10 has the 50 nm circle.

## v0.41.7

Protecting friendly bases and support aircraft.

* **Airfield air defence**
  * The Patriot faces the nearest enemy fighter field. It used to face a direction picked from the base's name; a Patriot radar covers about 120 degrees, so a raid from the wrong side met none.
  * A second short-range site (Vulcan + 2 Avengers) on the other side of the field.
  * A HAWK battery as the middle layer at your home field.
  * A degraded field (below 0.6) keeps what it had: the Patriot with 1 launcher and one short-range site.
* **Tanker forward, on the way home.**
  * Its track sits between the base and the egress point, as far forward as it can while staying 15 nm outside every SAM ring and outside every enemy field's scramble circle (plus 15 nm). It moves sideways off the line if it has to, or just behind the base when nothing forward is clear.
  * It used to sit up to about 50 nm behind the base, behind the marshal point. A second tanker sits 15 nm nearer home; the carrier recovery tanker stays with the boat.
* **Each support aircraft gets its own guard.**
  * Tanker CAP: required, and it gets the pair when only one is free.
  * HAVCAP: now only the AWACS, which is back at its old distance (no longer tied to the marshal point).
  * Each guard orbits on the side the threat comes from and engages only inside 25 nm of what it guards.
* **Base CAP** orbits on the side the threat comes from and engages only inside 25 nm of the field. It now also flies whenever an enemy fighter field is within 130 nm of the strikers' home field.
* **Carrier CAP:** a package off the carrier brings a 2-ship from the carrier's own squadrons, 22 nm out from the boat toward the nearest enemy field. It engages within 35 nm of the boat, while the deck still has fighters free that day.
* Red patrol stations keep 60 nm from the forward tanker (100 nm from the AWACS's HAVCAP, as before).
* Smoke test: Patriot heading, both short-range sites and the HAWK, tanker placement and its CAP, the HAVCAP on the AWACS, carrier CAP off its own deck.

## v0.41.6

From the v0.41.5 runs: the Senaki Vipers flew about 50 nm south to their marshal point and back north past their own base; and Viper 5-2's HARM killed Squid 1-4 (a JSOW Hornet on its way home).

* **HARM flights fire only at what they are tasked on** (OPEN FIRE, was weapons free): their own site, the Tors that guard it and the SA-10 umbrella. The fratricide: Viper 5-2 (a Sukhumi package) fired at the *Gudauta* SA-6 radar from 89 km, the radar went quiet, and 197 s later the HARM hit Squid 1-4, whose own radar was on, 40 nm short of Gudauta.
* **Marshal points close behind the base.** A marshal point only has to be outside every enemy field's scramble circle (plus 10 nm) and 20 nm outside every SAM ring, not a flat 90 nm from every enemy field (from before the per-field circles of v0.41.1). In the test campaign the Senaki marshal moved from 40 nm to 15 nm behind the base. Early-warning radars still see the stack; they trigger nothing.
* The shot log keeps up to 2,000 entries (was 600; busy runs reached 595).
* Removed an unused scramble-radius function left over from v0.41.0.
* Smoke test: every HARM flight is OPEN FIRE at its HARM point; every marshal point is outside the scramble circles.

## v0.41.5

From the v0.41.4 run: the Gudauta package came through (all four Squid JSOW jets home, the SA-10 killed by JSOW bomblets). But after Springfield's (F-14 TARCAP) hold ended, a lone MiG-29 followed them home and fired four R-27s while they only defended: three F-14s lost with about 35 missiles still on board.

* **TARCAP, escort and sweep fight on the way home.** When the hold ends they still engage any aircraft within 20 nm of themselves, until they are out of air-to-air missiles (then they just go home).
* Smoke test: every stationed fighter flight carries the homeward engage task from the end of its hold.

## v0.41.4

From the v0.41.3 Gudauta Standoff DEAD: the SA-10 next to the target stayed quiet while the first HARM flight was looking for it (one HARM went at it), lit up a minute later and shot down all four Squid JSOW Hornets and Hornet 2-1. The JSOW launch point was 30.6 nm from it, as designed, but the jets were at 33,000 ft and kept closing as they released, and up there an SA-10 reaches farther.

* **JSOW launch points stay 40 nm from a live SA-10** (was 30), up to 45 nm from the target (was 40). In the run, AGM-154As released from 30-40 nm at 33,000 ft reached their targets.
* **The second HARM flight also waits on the SA-10.** After its window on the Tors it holds HARMs for the umbrella until 7 minutes after its HARM time, so an SA-10 that switches on late still meets HARMs. The first HARM flight still opens on it.
* Smoke test: the JSOW launch point distance and the second HARM flight's SA-10 task.

## v0.41.3

From the v0.41.1 runs: whole JSOW flights were lost to the SA-10s. Their launch point sat 20 nm from the target, which put it 13-24 nm from a live SA-10, well inside its reach.

* **JSOW launch points stay out of every live SA-10's reach**, the same 30 nm the HARM shooters keep, counting every live, unsuppressed SA-10 near the target (the target itself included). The point moves out along the JSOW flight's own axis, up to 40 nm from the target.
* **A pushed-out JSOW shot goes from 33,000 ft** (from the IP on), so the AGM-154A glides far enough. Unpushed shots keep the old 20 nm / 20,000 ft profile.
* Smoke test: the built JSOW launch point is 30 nm from every SA-10 and high when it is far out (36 nm from the target, 30 nm from the SA-10 in the test campaign).

## v0.41.2

DCS refused a v0.41.1 player escort mission: "Viper 3: All waypoints (5-5) have locked speed and surrounded by waypoints 4 and 5 with locked time!"

* **Fighter stations (TARCAP, escort, sweep) are no longer time-locked.** Only the PUSH point and strike objectives keep a locked time, so the player's route never has a speed-locked run between two locked times.
* **The player's landing point has no locked speed.**
* Smoke test: every flyable player role (escort, sweep, SEAD, strike, CAP) for the F-16C, F-15C and F-14 is checked against that DCS rule.

## v0.41.1

From the v0.41.0 Batumi run: an earlier package already airborne near the target scrambled all 20 red alert pairs from six fields 10 s into the mission (45 radar missiles fired at us); the SA-10 killed six F-15Cs waiting on the new 62% stations (it engaged from 59-61 km); and no package had an escort (v0.40.2 had dropped the slot).

* **Alert fields scramble on what their own radar sees.** Each field's trigger is a circle round the field itself (up to 60 nm, smaller for fields close to the fight), not one big circle round the target. Red reinforcements use the same circles.
* **Only fields that can reach the fight send alert pairs:** within 130 nm of the target. The far fields (Krymsk, Gelendzhik, Maykop, Beslan for a Sukhumi target) no longer scramble at all.
* **TARCAP arrives with the package:** no head start (was 5 minutes), so the SAM has to split its attention and its exposure ends with the HARM salvo. In DEAD packages it arrives with the HARM shooters.
* **TARCAP and escort stations against a long-range SAM at 75% of its reach** (about 36 nm from an SA-10, was 62% / 30 nm), outside where it actually engaged.
* **Escorts are back:** every defended strike, DEAD or CAS package carries a 2-ship escort beside its TARCAP. Escorts pick F-16s and F/A-18s first (they stay with the package and fight close); an F-15C or F-14 fills in when none is free. TARCAP and sweeps keep the F-15Cs and F-14s first.
* Smoke test: detection circles round their own fields, the escort slot and its pick order, the new timing.

## v0.41.0

From the v0.40.10 run (Standoff DEAD, Sukhumi SA-10): one Su-27 alert pair from Sukhumi killed 7 ground-attack jets from 4-6 nm in two minutes; the F-15C TARCAPs never fired a missile (their stations were about 50 nm from the SA-10, 20 nm behind the HARM shooters); alert pairs took 3 to 11 minutes from the call to the air and two never made it (DCS AI taxiing).

* **TARCAP and escort stations against a long-range SAM** (an SA-10 whose reach covers the target): 62% of its reach from it (about 30 nm), level with the HARM shooters, and 9 nm sideways toward the nearest enemy airfield, between the threat and the package. Against shorter-ranged SAMs the stand-off edge rule is unchanged.
* **They cover the package, not their own station:** a TARCAP or escort engages inside a 20 nm circle round the package's launch points (HARM / JSOW points, or the IP), widened to take in its own station. Sweeps keep the circle round their station.
* **Snipe:** TARCAP, escort and sweep fire at maximum missile range and search with their radar all the time, so red is spiked and forced defensive early. (DCS AI launch behaviour varies by type; the shot log will show the real ranges.)
* **TARCAP on station first and for the whole attack:** it pushes 5 minutes ahead of the first flight it covers (was 3) and holds until 5 minutes after the TOT (was a fixed 15 minutes).
* **Alert pairs no longer taxi.** Every alert pair (red and blue, airfield and carrier) waits hidden and appears on the runway or catapult 2 minutes after it is called, 60 s apart at one runway, and after you have left it at your own field. In the run the queued pairs were airborne in about 45 s from appearing.
* **Abort rewinds the sortie counter.** The counter feeds the mission seed, so flying the same package again after Abort rebuilds the same layout (sites, spawns, patrols): two test runs of one package can be compared.
* Smoke test: TARCAP level with the HARM points against an SA-10, the cover zone, max-range / radar options, alert pairs hidden for the runway, the new timing, Abort keeps the seed.

## v0.40.10

* **ECM script: your jammer follows the AI's window.** With the script on, it used to count your jammer on for the whole mission (it cannot read your switch). It now counts it on from your PUSH to your egress, like the AI's, until the cockpit-switch reading is built. With the script off (the default) nothing changes: your jammer is DCS's own and your switch decides.
* Smoke test: your jammer window is in the hook.

## v0.40.9

* **The ECM script counts the F-15C's jammer.** It treated the F-15C as having none (tier 0); it now has an internal self-protection set (tier 1, like the F-14 and F/A-18), for AI Eagles and for yours. With the script off (the default) nothing changes: AI F-15Cs already used DCS's own ECM when locked (v0.40.2).
* Smoke test: the F-15C's tier.

## v0.40.8

Test data, so runs can be compared.

* **Alert log.** The state file now records each alert and scramble group (red alerts, red reinforcements, blue DCA): when it was called (its scramble trigger fired, or the runway queue released it), when its first jet got airborne, and "stuck" when it was called but still on the ground 5 minutes later (a taxi jam). The debrief says it: "Alert Alert 2 (Su-27, Beslan): called at 22 min, airborne 95 s later" or "... NEVER GOT AIRBORNE (stuck on the ground)".
* **The run's settings in the state file and the debrief:** splash damage on or off (with how many blasts it set off and how many kills it caused), ECM script on or off, and the build version. "Settings: splash damage ON (7 blasts, 2 kills), ECM script off, build v0.40.8".
* Smoke test: the hook carries the alert log and settings; the debrief reports both. The hook was also run in a mock DCS (called / airborne / stuck written correctly).

## v0.40.7

* **Alert and scramble jets wait hot on the ramp and taxi when called** (red alerts, red reinforcements, blue DCA; on the carrier, hot on deck). The runway and catapults stay free for flights scheduled to take off. Replaces v0.40.6's in-air fallback, which looked odd: a pair appearing off a field that could not have parked it.
* **Runway queue.** A field with no ramp spot for the type: the group waits hidden, and when it is called the mission hook puts it on the runway, at least 60 seconds after the last group that went from that runway. At your own field it waits until you have taken off (or 15 minutes in).
* **Dispersal (new campaigns).** No field holds more jets than DCS can park there. A red wing bigger than its field keeps what fits and its overflow goes to the nearest enemy fields with room (it joins their wings); the enemy total is unchanged. A blue squadron that does not fit moves, whole, to the nearest friendly airfield with room for its type; yours never moves. The campaign log says what moved. Fields that were over: Gelendzhik (Su-27, 3 slots), Sukhumi (Su-27, 5), Beslan (Su-24M, 5), Nalchik (15), Maykop (Su-27, 20), Batumi (blue, 10 slots for two squadrons). Existing campaigns keep their basing.
* Smoke test: alert groups on the ramp (or hidden for the runway), the queue in the hook, no field over its parking at levels 2 and 3.

## v0.40.6

* **Alert groups that cannot fit a field start in the air instead of being left out.** Since v0.39.25 a second alert or reinforcement group at a field whose runway was taken and which has no parking for the type (Gelendzhik, Beslan for red's Su-27s) was dropped, so red was thinner than planned. It is now late-activated in the air 4 km off the field, 2,000 ft, heading for the target, and activated by the same trigger that would have started it on the ground (as if it had just scrambled). Blue DCA alerts at a field get the same; carrier groups are unchanged.
* **Weather on the new-campaign dialog.** The same choice as Settings > Campaign > Weather, starting from the current setting; your pick is saved to Settings when the campaign is created.
* Smoke test: no alert group left out for parking in the merged mission; the dialog's weather choice; ECM script and splash damage off by default.

## v0.40.5

* **New radio layout.** COMM1 (UHF): CH1 AWACS, CH2 tanker, CH3 JTAC (when there is one), CH4 second tanker (when there is one), CH5 divert. COMM2: CH1 your flight, CH2 the tower. The flight stays on COMM2 CH1 because DCS writes the group's frequency onto the first channel that can tune it, whatever preset is set there; putting the tower on CH1 would have had it overwritten.
* **The tower on COMM2 is VHF for Air Force jets** at an airfield (the F-16's COMM2 tunes VHF only): the field's own VHF tower frequency. Navy jets keep the UHF tower or carrier control there (their COMM2 tunes both).
* COMM2 presets (flight and tower) are now written to your jet as well as COMM1.
* Kneeboard, briefing and radio calls follow: the comms card lists COMM2 CH2 as TOWER (or CVN), the RTB note and recovery line say "Tower COMM2 CH2", the tanker's on-station call names its channel, the JTAC is COMM1 CH3.
* Not in this build: starting both radios on CH1 (COMM2 starts on the flight frequency DCS gives the group), and showing AWACS and flight calls only when you are tuned to them (needs your cockpit radio state: the dcs-bios / Export.lua research item).
* Smoke test: layout, the F-16's VHF tower, the presets in the mission file, the briefing.

## v0.40.4

* **Splash damage** (Settings: "Splash damage", off by default). DCS often leaves a vehicle a few metres from a bomb untouched. On: when an air-to-ground weapon (bomb, rocket, air-to-ground missile, HARM included) reaches the ground, every ground unit or ship within a blast radius of 9 m x (explosive mass in kg)^(1/3) (a Mk-82 about 40 m, a 2000 lb bomb about 68 m, capped at 120 m) gets a blast of its own of 0.35 x explosive mass x (1 - distance / radius)^2. The direct hit is left to DCS. A weapon that ends in the air (a JSOW opening its dispenser, a missile shot down) does nothing, and a weapon whose DCS data gives no explosive mass is left alone. Kills it causes are credited to the shooter (DCS reports them with no killer), your ground kill count included. The numbers are a first guess, to tune from your test.
* Smoke test: off by default; on, the hook carries it and loads.

## v0.40.3

* **AWACS tells you when the day is done.** Once the last package's TOT has passed (plus 2 minutes) and every AI flight of every package in the mission is landed, shot down or gone, AWACS calls you by callsign: "OVERLORD to SPRINGFIELD 1: all packages complete, no further tasking today. Return to base." Once you have landed: "...all flights accounted for. Good work today. OVERLORD out." It repeats every 5 minutes, for when you have stepped away. It never ends the mission (an End Mission trigger would throw you to the debrief while still flying). Support flights (tanker, AWACS, HAVCAP, base CAP) and enemy aircraft do not hold it up; a late-activated flight that has not launched yet does.
* A Fighter Sweep records the packages it covers (package extra "covers").
* Smoke test: the call is in the hook, addressed to you, with the flights it waits for; the reactive check no longer depends on the process' hash seed.

## v0.40.2

Air-to-air rework, part 2: Fighter Sweep and Defensive Counter Air. And the ECM script becomes a setting, off by default.

* **Fighter Sweep package.** Where intel expects more enemy fighters at a target than its package's 4-ship TARCAP can take, the day gets a Fighter Sweep package for that area (targets within 60 km share one): one 4-ship per 4 fighters beyond the TARCAP, sized to the worst package there. It starts 10 minutes ahead of the first package it covers. You can fly it. Route: departure, push, station, home: no marshal, no IP, no egress. The station is short of the target and outside live SAM cover; the flight engages only inside 25 nm of it (15 nm for F-16 / F/A-18), holds 15 minutes, and goes home sooner when its air-to-air missiles are gone. It gets no HAVCAP or base CAP of its own.
* **No sweep slot inside strike packages any more.** A strike, DEAD or CAS package carries its TARCAP (and SEAD, strikers); the extra fighters it used to get are the sweep now.
* **Aircraft priority:** sweeps are built after the day's other packages, so HAVCAP, TARCAP and escort get the F-15Cs and F-14s first; a sweep takes what is left, long-range shooters first, then F-16s and F/A-18s.
* **Unit limit:** a merged sweep is listed first among the folded-in packages, so the unit limit drops strike packages before it (wrecks, red reinforcements and alert pairs are still trimmed before any package).
* **Unflown sweeps** (war sim): the sweep fights the fighters of the three nearest enemy wings; a win shoots down about 40% of its own number times the odds. The target is left alone. Sweeps start earlier, so they are resolved before the packages they cover, which then face fewer enemy fighters.
* **Defensive Counter Air.** Blue's alert pairs now launch only against a raid on the fleet or a base (zone-triggered, as before). The pairs that used to launch on the clock to reinforce a package's fight when red outnumbered it are gone: that is the sweep's job.
* A sweep leaves no ruins and its debrief line shows losses, not target damage. Its briefing and commander's intent are its own.
* **ECM script off by default** (Settings: "ECM script", experimental). Off: SQE's own jamming model in the hook is not used (the code stays), and jammers use DCS's own ECM: AI jets with a jammer keep it off on the way in and out and, over the attack leg (PUSH to egress), switch it on only when a radar has locked them. The F-15C (which the script counts as having none) gets the same. On: as before, the hook models jamming and burn-through, jammers always on over the attack leg. The war sim's jamming cover for unflown packages is unchanged.
* With fewer fighters per package, red reinforces a little less often (its reinforcements are sized against the blue fighters it sees).
* Smoke test: sweep planning, timing, route, RTB on AAMs, briefing and war sim; no sweep slot in strike packages; blue alert pairs only against raids; both ECM modes. The merge, ruins and reactive checks skip or pin around the new sweep packages.

## v0.40.1

Air-to-air rework, part 1 (from the v0.39.24 remarks): fighters don't chase into danger, for blue and red.

* **TARCAP** (the package's ESCORT flight, renamed): flies to a station of its own, short of the target and outside live SAM cover (12 nm short on the run-in when nothing is in the way). It pushes 3 minutes ahead of the first flight it covers, so it is on station first, holds there 15 minutes, then goes home from the station. No IP, no egress, for the AI and for you.
* **ESCORT** (the package's fighter sweep, renamed): its own station the same way, held until 3 minutes after the TOT (the last ground-attack flight off target), then out with the package by its egress when that leg is clear of SAM cover, or home from the station when it isn't. No IP.
* **No chasing.** An AI TARCAP or escort engages only inside a circle round its station: 25 nm for the long-range shooters (F-15C, F-14), 15 nm for the rest, until its hold ends. Enemy patrols are leashed the same way, 25 nm round their station (they used to chase up to 50 nm from wherever they were).
* **Long-range shooters first.** TARCAP and escort slots go to F-15C and F-14 squadrons; an F-16 or F/A-18 squadron is picked only when no long-range shooter is within 400 nm more of the target.
* A TARCAP or escort on its station is no longer held at a Close DEAD radar gate: it is already outside the threat.
* Labels: TARCAP and ESCORT in package tables and briefings. A COUNTER_AIR package's sweep is still a SWEEP.
* Not in this build: the new Fighter Sweep package (4-ships sent when intel expects heavy enemy air). Still open: how it is planned and whether you can fly it.
* Smoke test: TARCAP and escort routes (no IP, TARCAP without egress), leash radius by type, red patrols leashed, the new timing.

## v0.40.0

Standoff DEAD and Close DEAD. Each DEAD job now gets one kind of DEAD flight, picked by the threat at the site.

* **Standoff DEAD** (a site that is, or sits within 55 km of, a live SA-10): one package, not two. Two HARM flights and a JSOW flight (Hornets or Vipers; no Tomcats on DEAD here) go in together, and nobody flies into the SA-10's reach. The JSOW flight is now the DEAD strike: its AGM-154As go on two radars, the covering Tors and the launchers, as far as one JSOW per aim point goes. The war sim counts it as the DEAD flight (it used to count JSOWs as suppression only), released from stand-off range so it is less exposed than a GBU flight. The JSOW flight is picked before the second HARM flight, so a package short of jets keeps its DEAD flight.
* **Equal weight on the long-range radars and the Tors.** A Standoff DEAD package always has two HARM flights: the first opens on the long-range radars, the second on the Tors, in the same salvo, so the Tors are busy with HARMs when the JSOWs arrive (v0.39.24 run: Tors shot down 10 JSOWs). Every HARM flight still ends with a second pass at the Tors.
* **Close DEAD** (everything else): as before, a SEAD package that suppresses the radars, then a GBU package 10 minutes later behind the radar gate and hold. The SEAD package no longer carries JSOWs.
* A suppressed SA-10 (radars out) does not count as long-range: its site and its neighbours get the SEAD / Close DEAD pair until it is repaired overnight.
* Names: "Standoff DEAD: destroy ...", "SEAD: suppress ...", "Close DEAD: destroy ..., once its radars are down". Package tables label the JSOW flight SO DEAD; the briefing says "tasked as Standoff DEAD" or "Close DEAD". "Blinded" is now "suppressed" in the briefing, the debrief, the radio and the Missions list.
* The war sim ignores a flight with no aircraft in it (it could take the SEAD verdict without any SEAD jets).
* Out of HARMs or JSOWs, a flight goes home (v0.39.24's RTB when empty) and stand-off flights egress back along their approach (v0.39.22).
* Unit counts, 129 builds against 125 before (Viper, Hornet, Tomcat, Hog; levels 1-3): DEAD missions median 221 units (was 228), level 2 median 200 (was 213), missions at the 250 cap 4 (was 6).
* Smoke test: Standoff DEAD packages (JSOW flight, two HARM flights, no Tomcat on DEAD, JSOW counted as the DEAD strike, JSOWs on the launchers), which sites are long-range, labels. The SEAD / Close DEAD checks force the pair. The dense-column check is pinned to fixed campaign ids (it failed once on a random one).

## v0.39.25

Fix from the v0.39.24 run: about 9 of the 21 friendly losses were collisions in the first two minutes.

* **Airborne flights no longer spawn on top of each other.** Two flights on the same route and schedule (the two SEAD flights of a package already underway when the mission starts) appeared at the same point and height: Viper 6 and 7, Viper 1 and 2, Cowboy 1 and Colt 2 flew into each other at 00:00. A flight that would appear within 2 km and 300 m of another, within 90 s of it, is now moved 2 km to the side and 1000 ft up (further if needed). Red CAP pairs and full-map patrols use the same rule.
* **One group per runway or catapult.** Two Tomcat alert pairs were both put on the carrier's catapult (Springfield 8 and 9, three jets destroyed at 00:01). The first group at a base (your own flight first) gets the runway; every other one starts hot on the ramp or deck and taxis. A field with its runway taken and no parking for the type leaves that alert pair out (with a warning) instead of stacking it.
* Who starts in the air and who starts on the ground is unchanged.
* Smoke test: no stacked airborne spawns and one group per runway or catapult in a merged mission. A check over 18 missions (Viper, Hornet, Tomcat, level 3) found none.

## v0.39.24

Fix from the v0.39.23 run: strikers with nothing but guns left turned on fresh MiGs and Su-27s, and most of the coalition's air losses were ground-attack flights that never left after their task.

* **Ground-attack flights stay on their job.** Every AI strike, DEAD, SEAD, JSOW and CAS flight now takes off with "restrict air-to-air attack" on. On the way in it evades when attacked but never turns to fight aircraft. At its attack point it goes weapons free on the ground target only.
* **Self-defence after the attack.** At the egress point, jets carrying radar missiles (F-16, F/A-18, F-14: AIM-120 or AIM-54 on their strike loadouts) switch to return fire: they shoot back at whoever shoots at them, but don't go hunting. The A-10 stays restricted all the way home and relies on the air cover.
* **Home when the air-to-ground load is gone.** "RTB when out of ammo" is set for bombs (guided, iron, cluster), air-to-ground missiles (HARM, JSOW, Maverick) and rockets. Not guns or air-to-air missiles, so an empty bomber with a gun and two Sidewinders still goes home.
* Strikers that had no ROE at all (DCS default, which lets them open fire on anything) now get return fire on the way in and weapons free at the target, like the SEAD flights.
* Your own flight is not changed: your wingmen still follow your commands.
* Smoke test: every AI ground-attack flight in a merged mission is checked for the three options and the switch at egress.

## v0.39.23

* **No two flights share a name in a day.** Callsign numbers used to restart in every package, so the tasking order could list two Viper 1s in different packages. The planner now numbers flights across the whole day (Viper 1 to Viper 9). DCS flight numbers stop at 9, so a squadron flying more than nine flights in a day carries on under a spare callsign of its type that no squadron owns. An emergency package continues the day's numbering.
* Smoke test: every planned day is checked for duplicate callsigns.

## v0.39.22

Fixes from the v0.39.21 run (Sukhumi SA-6 SEAD, Day 1). The run worked (both SA-10s, the SA-11, the SA-6s and both Tors suppressed or dead, the first DEAD hold that resumed), but several of our own bugs drove the losses.

* **HARM and JSOW flights go home the way they came.** They now egress 25 nm (`STANDOFF_EGRESS_NM`) beyond their launch point, straight back out along their own approach. They used to fly to the package egress, which lies beyond the target for the strikers that overfly it: after a clean release the Navy JSOW Hornets crossed the Sukhumi cluster toward it and the Su-27s and MiG-29s killed about 11 jets between minutes 36 and 43.
* **An abort after a hold clears the orbit.** The hold pushes an orbit task on top of the route; "resume" cleared it but "abort" did not, so Springfield 1 timed out at 2250 s and then circled to the end of the mission. The hook now resets the task before sending the flight to its exit.
* **The hold is outside the SA-10's reach.** A DEAD gate now fires 60 km (`SA10_GATE_KM`) from an SA-10 target (was 40 km, inside its 55 km reach), and a gate whose target sits under a live SA-10 umbrella also fires 60 km from the SA-10. Hornet 1 held 40 km from the Sukhumi SA-6, which is 26 km from the SA-10, and lost all four jets in the orbit.
* **The gate waits only for the target's own radars.** A covering Tor still up no longer holds the strike (Springfield 1 held 12 minutes for one surviving column Tor while the SA-10's radars were already down). The go call says "A Tor is still up on the run-in, watch it."
* **Second pass at the Tors.** Every HARM flight now ends its task list with the Tors that cover its site, after its main targets, with whatever HARMs are left.
* **The SEAD waves in one mission arrive together (the Navy delay).** Traced from the mission file: the AI flew the plan to within seconds; the plan itself had the Navy HARMs 220 s after the USAF ones. The planner times a SEAD package from its first SEAD flight's base (Cowboy 1, Kutaisi), but the builder lays out your package from your own base (Senaki, about 20 nm closer). The builder now syncs: each merged SEAD package on the same ground (`SEAD_WAVE_KM` 60) is shifted to reach its HARM point with your package's. In a test build the SEAD waves are within 5 s of each other (they were 30 s apart there, 220 s in your run).
* The planner also times a carrier's SEAD packages from where the builder will put the carrier (it slides it back for the sortie). Not the cause of this delay (the carrier did not move in your runs), but it would have been on another map.
* Smoke test: checks for each fix (egress side, built HARM times, abort reset, gate radius and umbrella, second Tor pass).
* Untested in DCS. Check: HARM and JSOW flights turn back after firing; a held flight that aborts leaves its orbit; holds sit 60 km from an SA-10; the Navy and USAF HARMs go off together.
* Builds on v0.39.21 (#18 and #19 are merged into the catch-up branch).

## v0.39.21

* **HARMs first, JSOWs right behind.** The JSOW flight now pushes with the HARM shooters (`JSOW_TRAIL_S = 0`) instead of 160 s ahead of them. The jets cross into the umbrella's reach together; the HARMs go first and force the radar to die or shut down, and the JSOWs land a few minutes later on a dead or silent site. In the v0.39.19 run the USAF JSOW flight went in alone, 4 minutes before the first HARM, and died without releasing; the Navy JSOWs, which happened to land after the Navy HARMs, hit the S-300. The sweep is back to 30 s ahead of the HARM shooters.
* **Two axes.** The JSOW flight comes in about 30 degrees (`JSOW_AXIS_DEG`) off the HARM shooters' axis, on the side whose launch point stays farther from every other live SAM site, so the site has two directions to watch and the flights don't bunch up.
* **Hit the umbrella first.** A SEAD target under a live SA-10's reach (55 km, `UMBRELLA_KM`) keeps its HARM point 30 nm from the SA-10 as well as from its own target, and the package's first HARM flight opens on the SA-10 (3 minutes) before its own site. In the last run the SA-6 package's flights were inside the S-300's reach before they could fire.
* **SEAD sync on the real routes.** SEAD packages on one cluster are synced on each package's push-to-HARM-point leg, from the same marshal point, geometry and route the builder uses (umbrella keep-out included). The old estimate, a straight line from the base at 400 kt, ignored where each package marshals: the carrier's wave arrived about 3 minutes after the land-based one. In a test campaign the five SEAD packages on Sukhumi and Gudauta now reach their HARM points within 30 s of each other.
* JSOW briefing updated: you push with the HARM shooters, on your own axis.
* Smoke test: new saturation checks (sync within 1.5 min, umbrella first, JSOW axis 20-40 degrees off); the HARM-point check allows the umbrella keep-out; the v0.39.19 JSOW check pins its campaign id and flies a package your aircraft type can fly.
* Untested in DCS. Check: the HARM and JSOW flights cross into the S-300's reach together; the first HARMs go at the SA-10; the JSOWs release after the HARMs are off; the Navy and USAF waves arrive together.
* Stacked on PR #18 (v0.39.20); merge #18 first.

## v0.39.20

* **The Tors are part of the job.** A Tor (SA-15) battery within 12 km (`TOR_COVER_KM`) of a SEAD or DEAD target, or of the strike leg into it, is now targeted with the site. At Sukhumi both Tors cover the SA-10 (7 and 11 km). They shot down HARMs and GBUs aimed at the S-300 and killed Vipers coming in low.
  * **HARMs:** a SEAD package's second HARM flight opens on the covering Tors (3 minutes each), then joins on the site. The first flight goes straight at the site, as before.
  * **JSOWs:** the JSOW flight gets an aim point on each covering Tor, after the site's radars. A Hornet 4-ship (16 JSOWs) covers both; a Viper 4-ship (8) may run out before the Tors at a two-radar site like the SA-10.
  * **Route check:** the DEAD gate now also waits for the covering Tors, not just the target's radars, and holds while one is up. The hold call says so: "<site> blind, but the Tors covering it are still up."
* **A Tor counts as a radar.** Its radar rides on the launcher, so the Tor vehicle is now in `TRACK_RADARS`. Before, a Tor battery always looked blind to the hook. It now reads blind only when its Tors are down, and the call-outs report it.
* Smoke test: new Tor checks on a pinned campaign; the SEAD-task checks now allow the second flight's extra Tor attacks (still ARMs, still whole groups); the SEAD/DEAD resolution check pins its campaign id and finds a matching pair instead of assuming the first SEAD package has one.
* Untested in DCS. Check: the second HARM flight fires at the Tors; JSOWs land on the Tors; the DEAD gate holds while a covering Tor is up.
* Stacked on PR #17 (v0.39.19); merge #16 and #17 first.

## v0.39.19

* **JSOW slingers fly with the SEAD packages.** Every SEAD package now has an optional 4-ship JSOW flight alongside its HARM shooters: Hornets carry 4 AGM-154A JSOW CEB each (BRU-55 doubles on 2 and 8, tanks on 3, 5 and 7), Vipers carry 2 (pylons 3 and 7). Only Hornet and Viper squadrons fill the slot.
* **The overwhelm.** The JSOW flight pushes 160 s (`JSOW_LEAD_S`) ahead of the HARM shooters, because a JSOW's glide from 20 nm takes about three minutes against a HARM's 70 s from 30 nm. Both arrive at the radars together: a radar that keeps tracking is the HARMs' kill, one that shuts down to dodge them is still where it was last seen. The sweep moves ahead of the JSOW flight.
* **Stand-off attack.** The AI JSOW flight flies push, IP, a JSOW launch point 20 nm out (`JSOW_LAUNCH_NM`), then home; it never overflies the site. At the launch point it gets one release per radar of the target site (search and track radars), aimed at the radar's last-known position give or take 100 m (`JSOW_AIM_ERR_M`), with its JSOWs shared between the aim points. Like the SEAD flights it only returns fire until the launch point, so it does not chase fighters.
* **Your flight.** In a SEAD package you may now be given the JSOW slot (strike outranks SEAD in your role preference) if you fly a Hornet or a Viper. Your briefing and task say so; your loadout is the JSOW kit and your target point is the site.
* **War simulation.** Packages you do not fly count their JSOW flight as suppression (it raises the odds of blinding the site), not as a DEAD strike on the launchers.
* A merged SEAD package is still timed on its HARM flight, not its JSOW flight: the HARM salvo is the package's event and the JSOWs are timed to it.
* **Cost:** each SEAD package now takes up to 4 more Hornets or Vipers, so squadrons run out sooner and a day plans fewer other packages. If that turns out too heavy, the slot can drop to a pair.
* Smoke test: two checks that depended on the random campaign id (ruins of earlier packages, an underway package's flights already airborne) now pin it, so they give the same answer every run. Both had failed intermittently since before this version.
* Untested in DCS. Check: the JSOW flight releases at its launch point; JSOWs land on the radars about when the HARMs do; impacts appear as hits in `SQE_state.json`; the aim points are the release tasks in the .miz.
* Stacked on PR #16 (v0.39.18); merge #16 first.

## v0.39.18

* **New test option `--late-sead` (hold test).** SEAD-stage packages go in 15 minutes later (`LATE_SEAD_MIN`), so each DEAD stage, normally 10 minutes behind its SEAD, now arrives about 5 minutes ahead of it. The DEAD flight reaches its gate with the radars still up and its SEAD flights still alive, which is exactly the case the hold is for. In the last AI test every gate found the radars already down, so the hold never ran.
* In VS Code it's in the debug dropdown as "SQE: run app (AI test + late SEAD: hold test)". The window title shows `[LATE SEAD: +15 min, from the next planned day]`.
* It only changes days planned while it is on, and the shifted times are saved with that day. Use it on a test campaign: Skip Turn once after launching with it, or start a new campaign.
* The hook no longer counts a SEAD flight that has not launched yet (late-activated) as gone, so the `seads-gone` abort cannot fire on a SEAD that is still on its way.
* Untested in DCS. Check: the DEAD flight holds at the gate ("radars still up. Hold outside, rechecking."), the late SEAD suppresses the site, and the DEAD flight gets "Go, go, go" and goes in. If the SEAD fails, the hold ends with an RTB.

## v0.39.17

* **Aborting DEAD flights go home, not back over the target.** In the v0.39.16 run, Viper 1 got the `seads-gone` abort at 1255 s but flew on toward the Sukhumi site (39.8 km to 33.8 km in 60 s), dropped two GBU-31s and lost Viper 1-3 to the Tor. The abort pointed at the egress waypoint itself, which lies past the target. It now points at the waypoint after egress, the way home.
* Sweeps and escorts that abort are unaffected (they carry no egress point).
* Untested in DCS. Check: an AI strike that aborts turns onto the return leg, and its distance to the site grows in the 60 s after the abort.
* Stacked on the catch-up branch (v0.39.16 and earlier are merged).

## v0.39.16

* **Briefing matches the current behaviour.** The DEAD briefing now says the DEAD package follows the SEAD by the real gap (10 minutes, read from `DEAD_STAGE_GAP_MIN`; it said a hardcoded 25). The strike briefing now describes the hold, the AWACS hold, go and RTB calls, and the abort conditions (timeout, low fuel, every SEAD flight down or gone).
* Text only. Untested in DCS; check the briefing reads correctly on a DEAD and a SEAD flight.
* Stacked on PR #13 (v0.39.15); merge #13 first.

## v0.39.15

* **Early abort when the SEADs have failed.** If every SEAD flight on a site is down or gone while its radars are still up, the DEAD flight calls "abort, RTB" straight away instead of holding until the timeout. The check runs at the gate and on every hold re-check. AWACS gives the reason: "the SEAD flights are down or gone." The player and AI get the same calls.
* The SEAD flights are every SEAD group on the site in the mission, merged packages included. A SEAD flight counts as gone once it has no airborne unit, so a SEAD that lands and despawns counts too.
* **Fix:** v0.39.12 to v0.39.14 had the gate code defined twice in the hook. The second copy shadowed the hold, so the hold never ran in DCS. There is now one copy, and the smoke test fails if it comes back.
* Untested in DCS. Check: the hold actually orbits and re-checks (the v0.39.12 check was never run); the RTB call comes when the SEADs are down; the hold still goes in when blind.
* Stacked on PR #12 (v0.39.14); merge #12 first.

## v0.39.14

* **Your own DEAD flight holds too, the same way AI does.** When the radars are still up at the gate, the player's DEAD flight gets the hold calls instead of an immediate turn back. AWACS calls the hold point: "Springfield 1, radars still up. Hold outside, rechecking." It re-checks each minute and calls "radars are down. Go, go, go." when the site is blind. If it times out, runs low on fuel or cannot go in, AWACS calls "abort, RTB."
* **The hold is advisory for the player.** The game does not orbit your jet; the calls tell you when to hold, go or come home. AI DEAD flights get the same calls for immersion and still orbit and resume as before.
* **Your call uses your beep**, the same as other player calls. AI calls use the AI beep.
* Untested in DCS. Check: the hold call and beep come on the player's gate; the go call comes once the site is blind; the RTB call comes on timeout or low fuel.
* Stacked on PR #11 (v0.39.13); merge #11 first.

## v0.39.13

* **SEAD packages on the same ground go in together.** SEAD packages whose targets lie within 60 km of each other are synchronised: each push is moved so that its estimated arrival lands on the latest arrival of the group, so the earlier flights wait rather than going in alone. In the v0.39.11 run the USAF SEAD salvo went in at about 14 minutes and the Navy's, on the same ground, at about 30. The estimate is straight-line at 400 kt; the mission builder still builds the real route.
* **The DEAD stage goes in 10 minutes after its SEAD stage** (was 25). The v0.39.12 hold covers the case where the SEAD runs late.
* Untested in DCS. Check: SEAD packages on the same site arrive within about a minute of each other; the DEAD stage goes in 10 minutes after the SEAD; the hold still fires when the radars are up.
* Stacked on PR #10 (v0.39.12); merge #9 and #10 first.

## v0.39.12

* **An AI DEAD flight holds instead of turning back when the radars are still up.** In the v0.39.11 run Viper 1 reached the gate at about 22 minutes, found the Sukhumi radars still up and turned back, but the Navy SEAD finished blinding the site about 15 minutes later. The DEAD flight now orbits outside the threat (6 km radius at its own altitude), re-checks the radars every minute, and goes in as soon as the site is blind. It breaks off after 12 minutes (`HOLD_S = 720`) or at once if fuel falls below 30% (`HOLD_FUEL`), so it can still get home.
* The state file logs the outcome as `hold-resumed`, `hold-timeout` or `hold-fuel`, with `held` (seconds held) on the resumed entries.
* AI flights only. Your own flight still turns back at the gate.
* Untested in DCS. Check: an AI DEAD flight with radars up orbits and rechecks; it goes in when the site is blind; it breaks off after the timeout.
* Stacked on PR #9 (v0.39.11); merge #9 first.

## v0.39.11

* **Every shot in `SQE_state.json` now carries the target's map position (`tx`, `tz`)**: its last known spot at the time of the shot or hit. This is the first step of the JSOW strike plan: a later strike aims at where the emitters were last seen, not where the launchers are.
* Untested in DCS. Check that `shots` entries for `AGM_88` carry `tx` and `tz`, and that the values match the site's position in the mission.
* Stacked on PR #8 (v0.39.10); merge #8 first.

## v0.39.10

* **SEAD jets no longer chase fighters.** In the v0.39.9 run both Hornet SEAD flights (Hornet 1, Squid 1, four HARMs each) fought MiGs on the way in, drifted into Tor and SA-11 range (15-16 km from the site) and died 140 to 180 s before their HARM launch point without firing a HARM. AI SEAD flights (and your own flight in the AI test) now fly with hold-fire "return fire" from the start: they shoot back when shot at, and go weapons free at the HARM point, as before. On the way home they are back on return fire so they do not turn round for a kill. Support SEAD flights in strike and CAS packages get the same treatment.
* **Every shot in `SQE_state.json` now carries `km` and `alt`**: the range to its target (km) and the shooter's altitude (m) at launch. This is the data the standoff work needs: it shows how far out the AI really fires a HARM, and how far out the S-300 really shoots at the launching jet. Before this the file had times only, so every distance was inferred.
* Untested in DCS. Check: do the SEAD flights now arrive at the HARM point alive (Hornet 1, Squid 1 and Viper 1/2), and what are the `km` values of the `AGM_88` shots?

## v0.39.9

* **SEAD flights aim at the whole site.** In the v0.39.7 run (AI test, Sukhumi SA-10) the player package's SEAD pair (Viper 1/2) never fired a HARM: its task was aimed at the site's S-300 track radar, which only radiates while it is tracking, so there was nothing to shoot at. The pair fought MiGs, pressed on past the launch point and a Tor killed both 12 km from the site. The escort SEAD flight of another package (Cowboy 1) was aimed at a ground group instead, fired two HARMs from 31 nm and killed both Osa launchers it radiated against. The HARM task is now `AttackGroup` on the whole site (ARM only), as that one was. HARMs still only kill what radiates; the launchers stay the DEAD flight's job.
* Untested in DCS. Read `shots` for `AGM_88` from the SEAD flight; if it still fires nothing, the next step is a salvo at the search radar, which radiates all the time.

## v0.39.8

* **AI flights climb clear of the mountains.** In the AI run, Viper 3-4 crashed at 596 s with nothing shooting at it. The ground-height scan shows why: the leg from the departure point to the marshal point (59 km, south-east of Senaki, toward the hills) crosses ridges up to 2,650 m (8,700 ft), and the departure point was at 8,000 ft. An AI flight holds the altitude of its last waypoint until it gets to the next one, so it flew the ridges at 2,300 m. Every waypoint of an AI route (and your own flight in the AI test) is now lifted to the minimum safe altitude of the leg it starts and of the leg it ends (highest ground within 5 nm of the leg, plus 1,000 ft, or 2,000 ft over mountains). On that leg the departure point goes from 8,000 to 11,500 ft. The LOW tier (it follows the ground) and ground points are left alone. Without a ground-height scan nothing changes; a person flying the flight still reads the MSA on the kneeboard.
* Untested in DCS. Still open: the marshal point itself sits over high ground (2,100 m); it is now safe at 24,000 ft, but picking one over low ground would be better.

## v0.39.7

* **SEAD flights get to shoot first.** In the AI-only run on the Sukhumi SA-10 the four SEAD F-16s fired no HARM at all and all four died (the site lost nothing). Two causes, both fixed:
  * **The HARM launch point was inside the SA-10's reach.** It was 21 nm (39 km) from the site, and the S-300 opened fire at about 55 km. SEAD flights now launch from 30 nm (55 km), with the IP 6 nm before it; on a short route the distance is pulled in so the IP stays ahead of the base. They egress from there, so the SEAD flight never flies over the site. Both SEAD flights of a package hold the same launch time, so the missiles go off together.
  * **In the all-AI test your own flight had no SEAD tasking at all.** It was routed like a person flying it: a point on the radar itself at 0 m above ground and no attack task, so it flew straight at the site. In the AI test your flight is now routed and tasked like any AI flight (launch point, HARM task, orbit at the marshal, a strike's target point at altitude instead of on the ground). Flying it yourself is unchanged.
  * The HARM task now asks for anti-radiation missiles (`ARM`) instead of "Auto", so the AI can't pick another weapon.
* Untested in DCS. In particular: does the AI actually fire HARMs at the launch point (read `shots` in `SQE_state.json`: AGM_88C), and does it still manoeuvre toward the site while doing it?

## v0.39.6

* **HAVCAP and base CAP stay until the last flight is home.** In the AI run, Viper 4 (the HAVCAP) left 40 minutes after your TOT and landed while the merged DEAD package was still flying, so the tanker and AWACS were unguarded for the last hour. Both support CAPs now stay on station until five minutes after the latest return of any package in the mission (yours or a merged one). Fuel still applies: DCS sends an AI flight home at bingo whatever its task says, so a very long mission can still lose them (a relief pair is a later idea).
* **The waiting window counts landings per side.** "Landed / recovered" showed 31 under Friendly when only 24 of your aircraft had landed: the hook's list also holds red aircraft that landed. It now counts your side in the Friendly column and red in the Enemy column.
* **`SQE_state.json` explains losses.** New `deaths` list: for every unit lost, the event (`dead`, `crash` or `pilot_dead`), the last hit on it (who and with what, and how many seconds before), and the last fuel (fraction), altitude (m) and speed (kts) sampled for it (every 30 s, both sides, all aircraft) and how old that sample was. A loss with no recent hit and low fuel is a fuel or crash loss; with a recent hit it was shot. The three Viper 6 losses in the last run had no shot or kill record and could not be explained from the old file.
* **The shot log skips scenery.** Trees, houses and power poles that bombs and wrecks hit made up about a third of the `hit` entries; they are no longer logged.
* Untested in DCS.

## v0.39.5

* **The road scan only covers the places the war touches.** The v0.39.4 run in DCS showed the real cost: `getClosestPointOnRoads` takes about 90 ms whenever no road is near, so scanning the whole map (97,500 points) would take hours. The scan now covers 25 km around every airfield of the theatre (both sides) and along the front line (Sukhumi to Senaki to Kutaisi), skips water, and runs in three passes (8 km, 4 km, 2 km spacing, about 7,000 points in all). The roads file is written after each pass, so any finished pass is usable and the messages say when you can leave. Slices are 0 to 1 s of wall time per timer tick (the clock comes from a file's modification time). Theatre packs can set `road_radius_m` in the scan block. Untested in DCS.

## v0.39.4

* **The road scan finally gets a clock.** The DCS log of the v0.39.2 run showed `cpu_s=-1`: `os.clock` does not exist in DCS's mission environment, so every timer in the road pass had been silently off, the "0 ms" test results meant nothing, and the scan fell back to 50 calls per tick (hours for the map). The scan now reads wall time from a small file's modification time (`SQE_clock.tmp` in the SQE folder, whole seconds) and works in slices of 1 to 2 seconds per timer tick. A test call that takes 1 s or more still ends the scan without roads. Progress is shown as a percentage and every 5% is written to dcs.log (`SQE road scan:` lines with the mission and wall seconds). Untested in DCS.

## v0.39.3

* Road scan: 0.5 s slices and progress lines in dcs.log. Superseded by v0.39.4: it relied on `os.clock`, which DCS's mission environment does not have, so the slices never applied.

## v0.39.2

* **The road scan announces its first calls and skips the roads instead of freezing.** The first DCS test froze right at the start of the road pass even in time slices, so a single `getClosestPointOnRoads` call is the suspect. The scan now makes three test calls first, each announced on screen before it runs ("road test 1 of 3: calling now ... If this is the last message, DCS is stuck in that call") and logged to dcs.log with the prefix `SQE road scan:`. A call slower than 1 s ends the scan as COMPLETE without roads. The grid is coarsened until the estimate is about 20 minutes. Untested in DCS.

## v0.39.1

* **The road scan no longer freezes DCS.** The road pass ran 40 map columns (about 15,600 `getClosestPointOnRoads` calls) in one tick; that call is a nearest-road search and far slower than the height calls, so DCS stalled. It now works in 20 ms time slices and the progress message shows the percentage and a rough time left. If the scan is still too slow, raise `road_step` in the theatre's scan block (default 2000 m) and fly the scan again.

## v0.39.0
A full-map stress run. Untested in DCS.
* **`--full-map` launch option**: nothing is left out of the mission. Every live enemy site, column, garrison, support site and early-warning radar is built; every friendly airfield gets its defences, garrison and supply sites; every friendly sector with troops gets its column; every planned enemy patrol is airborne at its station. The unit limit and the merge trim are off. Your package and the target are the same as in a normal run. On a Level 3 campaign one sortie went from 144 to 766 units in testing.
* **Debug dropdown** (`.vscode/launch.json`): "SQE: run app (full map)" and "SQE: run app (AI test + full map)" next to the existing AI test entry. The window title shows [FULL MAP: no restrictions].
* Meant to find out what DCS and your VR rig can carry. A mission this size may load slowly or not at all.

## v0.38.2
* New campaigns start in 2006 (June 12 by default, was 2004). The A-10C flew first in 2005, so 2004 never fitted; in this story the F-14 stays in service because the war needs it. The year only changes the date (daylight, kneeboard); nothing in the war reads it. Existing campaigns keep their date.

## v0.38.1
* The FC3 F-15C no longer counts as having an internal jammer: its tier is 0 (no jamming rolls, no cover in the abstract war). Its switch cannot be read later and what the real set does is not clear enough to emulate.

## v0.38.0
Road snapping, needing a new scan. Untested in DCS.
* **The scan mission also finds roads** (`terrainprobe.py`): after the land / water and ground-height passes it asks `land.getClosestPointOnRoads('roads', x, y)` on a 2 km grid (`"road_step"` in the theatre's scan block) and writes the distinct road points (rounded to 50 m) to `SQE_roads_<theatre>.json`. This adds a minute or two to the scan. The Settings > Terrain scan page shows whether roads are loaded. Run the scan mission again to get them; the old files are still valid.
* **Snapping** (`ground.snap_roads`, `sqe/roads.py`): once, as soon as a roads file exists (new campaigns at creation, older ones at the next day plan), front-line columns, fuel farms and depots for both sides move onto the nearest road point within 3 km, if it is still on land. A column's air defence and anything guarding a moved site moves with it. Garrisons stay off the road, dug in. No roads file means nothing changes.
* It is a point cloud, not a road graph: things sit on a road, they do not drive along one.

## v0.37.0
The altitude choice (HIGH / MED / LOW) now counts ground anti-aircraft. Untested in DCS.
* **Ground AA counts**: front-line columns, garrisons, support sites (fuel, depot, C2) and Red airfields carry guns and short-range SAMs (ZSU-23-4, Strela, Osa, MANPADs). Each live one within 5 nm of the route from the PUSH on counts as an AAA site, which only reaches a flight that goes LOW (0 to 10,000 ft). Vehicles and buildings within 6 km of each other count as one site (`profiles.GROUND_AA_MERGE_M`).
* **Effect**: with enough guns beside the route or at the target, a package that would have gone LOW to dodge radar SAMs stays up instead. One or two columns do not change a clear case.
* CAS is unaffected (its choices are 9,000 ft and LOW, both inside gun range).

## v0.36.0
Air wings that fall back to recover, the same rule for both sides. Untested in DCS.
* **Stand-down** (`sqe/airwings.py`): an air wing (Red) or squadron (friendly) down to 30% of its aircraft or less may stand down overnight (`Difficulty.air_retreat`: 60% / 80% / 100% a night at Levels 1 / 2 / 3). Its survivors go to a rear field: they stop flying, so they are out of every patrol, raid, escort, sweep and threat count while they rest.
* **Recovery**: twice the normal replenishment rate; the unit returns after at least 2 nights once it is back to 65% of its aircraft. The overnight log says when a unit stands down and when it returns.
* **Left alone**: your own squadron, carrier squadrons (a ship has no rear field), the strategic bomber wing and units of fewer than 4 aircraft. A rest-base cratered while resting costs a quarter of the aircraft.
* **Totals**: resting aircraft still count in the strength totals (victory / defeat), because they are not lost.
* Smoke test: the raid-rate and emergency-rate checks now pin the campaign id, which is random, so those dice repeat from run to run (they could fail now and then before).

## v0.35.0
Jamming emulation. DCS gives jammers almost no effect of their own, so SQE adds one, the same for both sides and for you. Untested in DCS.
* **Tiers** (`sqe/ecm.py`): 1 = an internal self-protection set (F-15C, F-14, F/A-18C, Red Su-24M and Tu-22M3), 2 = an ECM pod on the loadout (the F-16C presets and the A-10C CAS preset carry the ALQ-184). The numbers are judgement, not sourced.
* **The missile roll** (in the hook): when a radar-guided missile (active or semi-active guidance; never anti-radiation missiles, IR missiles or bombs) is launched at an aircraft, the hook rolls the target's chance (20% internal, 45% pod, 30% when a pod-carrier within 2 nm covers it), scaled by launch range: none inside 12 km (burn-through), full from 40 km. A defeated missile is destroyed partway through its flight. The RWR still warns. Your flight hears "missile defeated". Every roll goes into `SQE_state.json` as `"jams"`.
* **When it runs**: AI flights switch the jammer on at PUSH and off at EGR (the DCS option `ECM_USING` is set on those waypoints, and the hook only rolls inside that window), so the jam strobes appear when they go in. Your own jet is on throughout for now. `ecm.jammer_on` / the hook's `jamOn` is the one place a future cockpit-switch export script plugs in.
* **The abstract war**: a package's jamming cover (pod 1.0, internal 0.4, by aircraft) cuts the site's strength in the SEAD odds by up to 20% and the package's loss chance by up to 15%.
* Not done: a dedicated jammer support flight (no Growler in DCS); the cockpit switch.

## v0.34.0
SEAD wears the defence down, so a campaign against a strong air-defence network moves instead of stalling. Untested in DCS.
* **Each failed SEAD day raises the next day's odds** on that site by 10 points, up to 40 (`war.SEAD_LEARN`, `SEAD_LEARN_MAX`); the failed-days count is the one the valve already kept. A success starts over.
* **A failed SEAD still costs the site** 4% health (`war.SEAD_WEAR`), which also feeds the retreat of v0.32.
* **The valve opens after 2 failed days at Level 3** (3 at Levels 1 and 2; `Difficulty.sead_valve`).
* **The SEAD briefing gives the odds**: "Intelligence puts the chance of blinding this site at about 55%", and says when the site has beaten us before.
* Queued next: a jamming emulation (event-driven missile kills near a jammer); see the notes in the chat. Not started.

## v0.33.0
* **Denser front-line columns.** The number of vehicles in an enemy front-line column now follows its sector's strength: the base mix is multiplied by 0.5 + 1.5 x strength (2x at full strength, 1x at a third, as few as half at nearly nothing). Before, the column was the base mix times strength, so a strong sector looked the same as it always had. At Level 2-3 a full-strength column is about 20-28 vehicles, a third-strength one about 12. Losses still read back as sector strength: nothing lost leaves the sector as it was, and half the column destroyed took a full-strength sector from 100% to 70% (the existing damping). Garrisons and other sites are unchanged. Tune `mission_builder.ARMOR_DENSITY`. A mission with a full-strength column was 114-140 units in the trial builds (limit 250), so VR cost goes up where the front is hot.

## v0.32.0
Retreat for badly hurt long-range SAM sites. Untested in DCS.
* A long-range site (the kind SEAD / DEAD packages are sent to) at **35% health or less** can **pull back from the front to recover**. Each night, with a chance that grows the worse it is hurt and falls with the enemy's supply (`sams.retreat`, scaled by the level: 60% / 80% / 100%), the site and its dug-in garrison move 35-55 nm further from our nearest airfield, onto land. Its ring leaves the contested ground while it is away. It is still on the map and the planner can still send a package against it where it sits. Once it is repaired to **65%** (at least 2 days later) it returns to its old position, with a 50% chance each night. A site destroyed while pulled back is handled by the normal rebuild rule at the position it had reached.
* The overnight log says "<site> (25% left) pulled back about 44 nm from the front to recover" and "<site> is back in position". State: `sams.pulled` in the campaign (old position, day).
* Sites that scoot (mobile ones, up to 10 nm) are unchanged. They do not scoot while pulled back.
* Not done: retreat of depleted air wings to a rear field (it needs a merge rule for wings), and the friendly equivalent.
* Seen in an all-AI simulation of 40 days at Level 3: 8 pulls, 1 return and 33 held DEAD stages (the SEAD stage fails often at Level 3, which is the point of the 3-day valve); at Level 2, none (no long-range site got below 42%).

## v0.31.2
* The empty Missions pane calls it a stand-down day ("Stand-down day for you. Skip Turn takes the day.") instead of talking about the war going on without you.

## v0.31.1
* When the Missions list has nothing you can fly, the right-hand pane now says so: "No flights for <squadron> today." with the reasons that apply (too few serviceable aircraft for a pair, nothing on the tasking order for your aircraft's roles, jobs given to other squadrons or out of reach) and a quiet line: "Stand-down day for you. Skip Turn takes the day."

## v0.31.0
SEAD first. Untested in DCS.
* **A SEAD / DEAD job is now two packages for the same site**: "SEAD: blind <site>" (SEAD flights, escorts, sweeps if the threat calls for them) and, 25 minutes later, "DEAD: destroy <site>, once its radars are blind" (strikers and their escorts). The pair counts against the day's package limit. Before this, one package carried both and the DEAD flight depended on the in-mission gate alone.
* **The DEAD stage only commits if the radars are blind.** The dice for every SEAD package of the day are cast once, when the day is planned (seeded from the campaign, day and site), and every part of the program reads that answer: the war simulation, the built mission and the briefing. If you fly the SEAD package, what really happens replaces it (radars all destroyed = blind). In the war simulation a DEAD stage whose site is not blind is **held**: no strike, no losses ("HELD - the radars were not blinded").
* **In a mission**: when you fly the DEAD stage and the SEAD stage succeeded, the site starts with its search and track radars already gone (launchers intact), so there is nothing to abort. When the SEAD stage failed the radars are up, and the in-mission radar gate from v0.28 still turns the DEAD flight, its escorts and sweeps back. The SEAD package has no gate. The DEAD stage's escorts and sweep now go in 30 and 60 seconds ahead of the strikers instead of the 4.5 minutes they needed when SEAD was in the same package.
* **The valve**: after 3 failed SEAD days on the same site (`war.SEAD_FAIL_VALVE`) the old combined SEAD + DEAD package is offered again for that site. A success resets the count. `SQE_state.json` is unchanged; the count lives in the campaign (`raids.sead_fail`) with today's verdicts (`raids.sead`).
* The debrief says what happened to the SEAD package you flew ("its radars are out; the DEAD package can go in" or "still up; the DEAD package will not commit"). The DEAD-stage briefing says a SEAD package goes in ahead of you.
* Raid briefings now name the real raiders ("Su-25 attack aircraft") and the real target (supply site, garrison, troops).
* Not done: retreat of battered groups, splash damage. A DEAD stage is not postponed to tomorrow when held (it is replanned with its SEAD partner).

## v0.30.0
Both sides play by the same rules a step further. Everything here is untested in DCS.
* **Friendly garrisons.** Every friendly airfield now has a dug-in garrison next to it (`bgar_<field>`), the same kind of record as the enemy's. Older saves get them on the next plan. A garrison takes damage off its field when bombs fall on it (a quarter at full health) and is part of the raid mission when its field or the garrison itself is under attack. Size follows the level (`blue_garrison_size`: 1.0 / 0.8 / 0.7).
* **Enemy raids have targets, not only airfields.** A raid (an "Intercept ..." package in the tasking order, announced or a surprise) can now go for a **supply site** (a friendly fuel farm or the forward depot), a **field's garrison**, or **friendly troops in a contested sector**, with the level's chances (`raid_mix`, supply / garrison / troops: 10-10-20% at Level 1, 20-15-25% at Level 2, 25-20-25% at Level 3; the rest still go for the airfield). The package, the raiders' route and the CAP station are built around the target; the thing under attack is on the map (garrison vehicles, fuel tanks and warehouses, a friendly column). When raiders get through: a supply site loses health (so friendly supply drops, as the enemy's does when you hit its depots), a garrison loses health, troops lose sector strength. Su-25s fly the raids against garrisons and troops, Su-24Ms against fields and supply sites; at Level 1 (no Su-24M) raids are now possible too.
* **Friendly sites are replaced.** A destroyed friendly supply site or garrison comes back overnight with a chance that follows friendly supply (`blue_rebuild`: 20% / 15% / 10%), the mirror of the enemy's SAM rebuild.
* **One daily sortie budget per enemy wing** (`redair.DAILY_SORTIES` = 2 per serviceable airframe, the same rule the friendly packages already follow). Patrols, sweeps and raids all draw on it; a raid books its aircraft once when it is picked (replanning the same day never books it twice) and a wing with nothing left sends no more raids. State: `red_air.budget` / `used`.
* **Shot log** in `SQE_state.json` (`"shots"`): every weapon launched (`ev: "shot"`: shooter, shooter type, weapon, and the target the weapon was guided at) and every hit (`ev: "hit"`: shooter, weapon, who was hit), up to 600 entries. This is the diagnostic for why SEAD blinded nothing: it shows whether the HARMs were fired, at what, and whether they hit.
* Wording: raid lines say "attack aircraft" and "friendly troops".
* Not done: the SEAD-first planning rule, retreat of battered groups, and splash damage are queued. Raids on a field's garrison or supply site do not have escort SEAD; the enemy's planned CAS flights are the raids above (there is no separate enemy CAS plan).

## v0.29.0
* The enemy has an air plan for the day (new `sqe/redair.py`, stored in the campaign as `red_air`, so old saves just get one on first use). Before, the enemy's fighters were invented around your package when the mission was built: the nearest wings, a CAP in front of each of their bases, always there. Now each wing flies **patrol pairs** in time windows (the day is cut into four 6-hour waves; which waves a wing covers differs from wing to wing and day to day, so some hours have no patrol over an area), each on a station in front of its own base toward the nearest friendly airfield; one pair per wing always stays on alert. At Level 2 and 3 a pair also flies a **sweep** over a contested sector of the front for 90 minutes. How much a wing flies follows the level (patrol pairs per wing: 1 / 2 / 3; share of its aircraft: 20% / 30% / 40%) and what the wing has left, so a beaten-up wing flies less tomorrow.
* The mission uses the plan where it overlaps your mission: a patrol is built only if its window contains your time over the target (estimated 20 minutes after the start) and its station is within 110 nm of the target or 45 nm of your route, and a wing never supplies more pairs than it has aircraft for. Those pairs are the briefed enemy patrol, airborne on station from the start and staying until their window ends. How many enemy fighters there are in all is unchanged (the package's threat size, `n_def`); patrols fill the first places and the rest are alert pairs that scramble as before. So a mission can have no patrol at all (the plan has none up in your area and hour), and then everything is alert pairs. Expect fewer briefed patrols than before.
* The briefing says what is known: "Reported enemy patrol: a pair of MiG-29A from Sochi-Adler, 55 nm NW of the target, 0600-1220." (a sweep says "fighter sweep"). Alert pairs and reinforcements are described as before.
* Not in this version: enemy CAS, strikes on friendly facilities, or a plan for the enemy's attack aircraft (only the raids from v0.20 and the ground push). Alert pairs are not part of the plan yet. The plan is made from the wings' strength at the start of the day.

## v0.28.3
From the first real all-AI run of the DEAD gate (two folded DEAD packages at Nalchik: 8 of 24 friendly aircraft lost, no ground unit destroyed).
* The radar check now fires on distance, not on the clock. It runs when the DEAD flight's lead is within 40 km of the site (`DEAD_GATE_KM`). In the test run one DEAD flight was about 3.5 minutes behind its plan, so the old fixed-time check judged it 70 km out, in the middle of the S-300 ring. The clock time (plus 5 minutes) is only a fallback for a flight that is gone. One decision per site: the escorts and sweeps of the package turn back with the DEAD flight, even though they hold far from the site. The state file's `gates` entries gain `"by": "dist"` or `"clock"`.
* The turn-back no longer cuts from cruise altitude straight to the runway. Stand-off escorts and sweeps (which have no egress point) get an "ABORT" return waypoint 20 nm from their base, at 9,000 ft or lower, before the landing. In the test run both F-15s of the player's flight ejected after hitting a hangar about 6.5 minutes after the abort order; the F-16s that took the same switch landed. Not proven to be the cause, but the straight dive is the only difference I found. The return point is also on the normal way home.
* A real engage leash. DCS's engage distance is measured from the aircraft, so a fighter chasing a MiG was never stopped (the escort that died to the SA-11 at Nalchik held 113 km from it and went about 75 km toward it, and the SEAD flights fought MiGs for the same reason). AI escorts, sweeps and SEAD now engage only what is inside a circle: around the stand-off hold point (30 nm) or the SEAD point (30 nm), or around the target (40 nm) for a flight that is not held back. It still stops at TOT + 5 minutes. Setting "chase no further than" to 0 in Settings keeps the old unlimited behaviour. Uses the DCS task `EngageTargetsInZone`; not verified in DCS.
* Not changed: SEAD did not blind any radar in the test run (no kills at all). The state file does not record weapon shots, so I cannot tell whether the HARMs were fired. A shot log is the next diagnostic.

## v0.28.2
* In-world wording: the text you read in the game no longer says "Red" and "Blue". The ground-war lines, the sector list, the "troops in contact" and CAS job text, the SAM-rebuild line, the map legend, the Settings label and the debrief table headers say "enemy" and "friendly" (an attack is "Enemy forces attacked ...", a sector is "enemy 60 | friendly 15 (contested)"). Code, comments, docs and the state file keep their Red / Blue names. The map still draws friendly in blue and enemy in red.

## v0.28.1
* Every DEAD gate is now written to `SQE_state.json` (`"gates"`), so an all-AI run shows what happened without watching: for each flight the site, the scheduled and actual check time, radars left, whether the turn-back command went through (`cmd`), and the flight's distance to the target when the command was issued (`d0`) and 60 s later (`d1`; a smaller number than `d0` means it kept going in, a larger one means it turned). A gate that found the radars dead is logged too, with `abort: false`.
* In the `--ai-test` launch the radio calls (with their beeps) are shown to everyone instead of to your flight's group, which nobody is in. Before this you saw nothing in an all-AI run.
* Time compression: the script runs on mission time, so the checks happen at the same mission second at any speed; at very high compression the check can run a little late (the file records both times).

## v0.28.0
* DEAD packages call themselves off when the radars are still up. Shortly before the strike (75 s before the target time) the mission checks every search and track radar of the target site. If any is still alive, the DEAD flight, and the escorts and sweeps in the package, break off: the AI skips to its egress point (or straight to the landing point for stand-off fighters), a "abort, abort, ... radars still up, DEAD flight break off." call goes out, and the debrief says "DEAD called off on <site>". A human flight gets the call and decides. A site with no radars at all is never aborted. Abstract (unflown) packages are unchanged: they already did badly against an unblinded site.
* SEAD now leads the DEAD flight by 5 minutes (it was 90 s) so the HARMs have time to land before the check. The sweep keeps going in 30 s ahead of SEAD and the escorts 30 s behind it, so the fighters stay with the SEAD flight instead of arriving minutes after it. Other package types are unchanged.
* Calls addressed to your flight ("AWACS to VIPER 1: ...", and the abort call when you are in the DEAD flight) have their own sound, a double high beep, instead of the single low beep every other call uses.
* Not verified in DCS: the AI turn-back uses the SwitchWaypoint command from the debrief script. The smoke test checks that the gate is built and that the script compiles.

## v0.27.1
* The all-AI test is a launch option now, not a setting. Start SQE with `--ai-test` (`run_ai_test.bat` does it from the folder; for the exe, add `--ai-test` to a shortcut's target) and your own flight is built as an AI flight: no player or client slot, the AI stand-off and the engage window. The title bar says "[AI TEST ...]" so you cannot forget. Started normally, nothing changes. The Settings tick from v0.26.1 is gone; an old settings file that still has it is read without trouble.

## v0.27.0
* Garrison CAS waits for the SAM cover to be cleared. "Close air support: dislodge the ... garrison" used to be offered from day 1, and the A-10s flew straight into the whole SAM cluster around it (twelve lost in one all-AI sortie). Now a dug-in garrison is not offered while any long-range SAM site (the kind SEAD / DEAD packages are sent to: value 5 or more, ring 10 nm or more) whose ring covers it is alive and can be tasked. Clear the sites (SEAD and DEAD, or "Finish off" jobs) and the garrison CAS appears. The Tors, Shilkas and other short-range systems are not counted: they are never DEAD targets, so waiting for them would hold the job back for ever.
* The sites that stand between you and a garrison now also count as "blocking" for the planner, so their DEAD packages are ranked higher (the same x1.8 the SAM belt already got).
* Front-line CAS (the armor column in each contested sector) is unchanged: in my test, an A-10C pilot still has a flyable CAS job on day 1 at all three levels. Level 1 has no garrison jobs open on day 1 at all.
* In 20 test campaigns per level: Level 2 offered no garrison CAS on day 1 and offered it for all 61 open garrisons once their cover was cleared; Level 3 offered none on day 1 and 80 of 120 after clearing (the rest did not fit the daily list).

## v0.26.5
* A DEAD package never flies LOW. Its target is a defended cluster (the site's own AAA, Shilka and Strela, a garrison, Tunguskas next door), and LOW only helps against radar missiles, which are exactly what the package is there to destroy. In the last test the four Hornets that bombed a mop-up SA-10 site at 500 ft AGL all died within 40 seconds. A DEAD package now picks between its normal altitude and MED, as before. CAS, STRIKE and the other packages are unchanged.
* The altitude profile now counts SAM sites at 25% health or less, like the stand-off since v0.26.4: a site with a unit left still shoots, so it no longer makes a package look safer than it is.
* Not changed: the garrison's own anti-air units (Strela-10, Shilka) are still not counted as a low-altitude threat near the target. If STRIKE or CAS packages near garrisons keep losing aircraft low, that is the next step.

## v0.26.4
* Stand-off bug: a SAM site that is nearly dead still counted as dead. The stand-off ignored sites at 25% health or less, but a mop-up target ("Finish off Gudauta SA-10 site, 11% left") still has units: its track radar killed an F-14 and an F-15 that the stand-off had parked 23 nm from it. Now every site with a unit left counts as live; only a destroyed site (5% or less) is ignored. Consequence: escorts and sweeps now stay outside the ring of a mop-up site too, so on a "finish it off" mission they stop further out.
* Not changed (found in the same mission): the altitude profile still ignores sites at 25% health or less when it decides whether the package goes LOW, and it only looks at long-range SAMs. The four Hornets that bombed that site at 500 ft AGL all died within 40 seconds to the Tunguskas, a Strela and a Shilka in its cluster. Whether LOW should count the short-range systems around the target is a decision for you.
* Checked, not a bug: the Maykop pair that killed a Viper at 1126 s was not chasing; it is a scramble pair whose waypoint is the target, 97 nm from its base, so it flew to the fight. The Viper 1 SEAD flight stayed within 21 to 40 nm of the target.

## v0.26.3
* The "My flight is flown by the AI" tick (Settings > Mission build) now really does it. In v0.26.1 it only gave your flight the AI stand-off and engage window; the aircraft was still a player slot, so you had to switch it to AI in the editor yourself (and if you did not, you could sit in it and fly). Now the flight is built as an AI flight: no player or client slot at all, so there is nothing to change in the editor, and you cannot take it. It flies like the other AI flights (stand-off short of SAM cover, engage window). Leave the tick off when you fly.

## v0.26.2
* The ground-war map is readable again. The red and blue strength figures (R100, B18 ...) overlapped each other and the airfield names around Sukhumi and Senaki. Each sector is now a number with a small red | blue bar under it (the strengths themselves are in the list above the map). The "front line" label moved clear of the sector numbers.
* Found, not changed: garrison CAS ("dislodge the ... garrison") is still offered from day 1 even though the garrison sits under its site's SAM cluster. The planner's blocker check only looks at SAM rings on the route, not at the target's own cluster, so it never holds the mission back. A rule that offers garrison CAS only after the long-range sites around it are cleared needs your decision first (it also changes what a campaign offers early on).

## v0.26.1
* Red's known CAP no longer sits inside the fleet's missile range. In an all-AI test the cruiser escort shot down both known CAP pairs (Gudauta and Sochi) in the first seven minutes of every sortie: the carrier's home station is only 55 to 66 nm from Sukhumi and Gudauta, the CAP stations were 67 to 71 nm out, and their racetrack legs ran toward the fleet (51 to 56 nm). The old 130 nm keep-out only counted carriers used by a flight of your own package. Now every carrier in the campaign keeps Red's known CAP stations at least 90 nm away (CAP_FLEET_KEEPOUT_NM in mission_builder.py, a hand-set number: the escorts killed pairs 51 nm out, so their reach is at least that), the station is moved inland along the line from the carrier, and the racetrack leg runs the way that stays further from the fleet. Alert and scramble pairs are unchanged (they fly to the target area, not to the fleet).
* New setting for all-AI test runs: Settings > Mission build > "My flight is AI-flown". When you set your slot to AI in the editor, SQE cannot know it, so your own flight kept the "player is never cut short" rule: it flew into SAM cover and had no engage time limit (in the last test Enfield 1 lost two F-15s to the SA-10). With the tick box on, a player ESCORT or SWEEP flight gets the same stand-off and engage window as the AI flights. Leave it off when you fly.
* Not changed: CAS flights against SAM garrisons (they still fly over the site's own short-range SAMs).

## v0.26.0
* Air defence that rebuilds and moves (phase 3 of the ground war; sqe/sams.py). Before, a destroyed SAM site stayed destroyed for ever and Blue's airfield defences repaired by a flat 10% a day.
* Red rebuilds. A SAM site you destroyed can be replaced from its fourth day down, at half strength, at a chance of 2% / 4% / 7% a night (Levels 1 / 2 / 3) times Red's supply (strike the depots and fuel farms and it slows), at most one site a night. Not rebuilt: the column air defence that travels with each sector, a site at a cratered airfield, anything in a tier beyond the ones in play. In my test (every site in the tiers in play destroyed on day 0, nothing else done) Level 2 had 11 of 18 back after 40 days, Level 3 had 19 of 24.
* Red moves. A hurt mobile site (SA-6, SA-11, SA-8, SA-15, SA-19, at 80% health or less) can pack up overnight and move 3 to 6 nm (15% / 30% / 50% a night by level), at most twice and never more than 10 nm from where it started. Its dug-in garrison moves with it. Fixed sites (SA-2, SA-3, SA-10) never move. The tasking order of the next day has the new position, the log says "... was hit and has moved about N nm".
* Blue's airfield air defences now repair by supply: 10% a day at full supply, about half that with every fuel farm and depot gone (the old flat repair ignored supply). A fallen field does not repair until it is retaken. A well-defended field (80% or more) lends 5% to the weakest one (below 50%), shown in the log as "A SAM battery moved from ... to ...".
* Saves: the campaign file gains an optional sams record; older saves load without it. No format change.
* Balance numbers are first guesses; the rebuild and move rates are in Difficulty (sam_rebuild, sam_scoot).
* GUIDE: the file table now points at the theatre pack's geo file instead of the removed geo_data.py. Two stale files can be deleted from the repository: sqe/geo_data.py and sqe/data/caucasus_geo.json (nothing uses them).

## v0.25.1
* AI fighters no longer chase to the far end of the map. In the all-AI test of v0.24 an F-16 and a Hornet flight followed a MiG-29 as far as Mozdok, 40 minutes into the sortie. The cause: DCS's "engage targets within X nm" is measured from the aircraft, so it decides what the AI starts to engage but is no leash; a bandit running home at the same speed stays inside it all the way. v0.25.0's 40 nm limit alone would not have stopped that.
* The engage task of AI escorts, sweeps and SEAD flights is now time-limited: it ends 5 minutes after the strike's TOT (Settings > Mission build, "min after TOT"; 0 = no time limit), and the flight carries on along its route to egress and home. Blue alert pairs get 5 minutes more, since they arrive late. The distance limit (40 nm for escorts and sweeps, 50 nm for the alert pairs) stays as the first filter. Your own flight, enemy CAP and the HAVCAP / BASECAP flights are unchanged.
* Note: SEAD flights had no engage limit at all before; they now get the time limit (not the distance one).
* Not changed: CAS against a SAM site's garrison still flies the A-10s over that site's own short-range SAMs (four A-10s lost to Tors in the same test). That is a target-selection question, not part of this fix.

## v0.25.0
* AI escorts and sweeps no longer fly head-on into live SAM cover. For each AI escort or sweep flight the builder walks the route PUSH > IP > target and finds the last point outside the range (plus 3 nm) of every live SAM site that can engage the flight's altitude (sites at 25% health or less, or destroyed, do not count). The flight flies there, holds (racetrack orbit) for the whole of the strike and goes home from that point; it has no egress leg past the target. Its waypoint note says how far short it stopped and which SAMs stopped it. Nothing changes if the route is clear of live SAMs, if the flight would start inside cover, or if the stop would be less than 4 nm short.
* Your own flight is never cut short. Primary sweeps (the COUNTER_AIR mission) and the fleet-defence / BARCAP missions are not changed either.
* AI escorts and sweeps now have an engage limit (Settings > Mission build, 40 nm by default, 0 = unlimited), like the CAP flights already had: they will not leave their route further than that to chase a fighter.
* Settings: "Escort / sweep engage range" and a tickbox "AI escorts and sweeps stop short of live SAM cover".
* Bug fixed: the altitude profile (HIGH / MED / LOW) was worked out once for the player's role and applied to every flight in the package, so an escort or SEAD flight could inherit a striker's tier. Each kind of flight now gets its own, as the guide says (SEAD and escorts never go LOW).
* Limits: with heavy SAM cover the stop is far from the target (in my test builds at Level 3, 30 to 64 nm short), so those escorts cover the way in and out, not the target area. The 3 nm margin and the 4 nm minimum are hand-set in sqe/profiles.py. The wingmen and escorts still react to threats inside their own radar range.

## v0.24.1
* Our alert pairs now have a dispatch range, like the enemy's reinforcements always had. Before, a squadron could put a pair up for any area within 60% of its combat radius (about 180 nm for a Hornet), so a carrier pair could be sent east to harass a pair of MiG-29s a long way from the fleet. Now an alert pair is sent no further than: F-14B(U) 150 nm, F/A-18C 130 nm, F-16C 120 nm, F-15C 160 nm (110 nm for anything else), and never more than 60% of the combat radius. The numbers are hand-set in sqe/reactive.py (BLUE_DISPATCH_NM) and shorter than the combat radius on purpose: the pair has to reach the area, fight and get home. For the Caucasus: the carrier and the Senaki and Kutaisi fighters cover the Sukhumi, Gudauta and Sochi area and the Nalchik side in part; Mozdok and Beslan are out of reach for alert pairs.
* Fixed a rare crash when building a mission with ruins: a package shown as already struck and heading home could belong to a carrier or airfield that nothing else in the mission uses, and the base had not been placed (KeyError 'cvn74'). The bases of the ruin packages' flights are placed too.
* The smoke test no longer depends on the dice for emergencies outside its own block.

## v0.24.0
* Red raids and emergencies (phase 2 of the ground war). Red now plans raids on our airfields the way we plan strikes: it picks an airfield its Su-24M bombers can reach, favouring the ones nearest its own fields and the least defended, escorted by fighters when any can reach that far. Per day, raids happen at about 0.15 / 0.40 / 0.70 for Levels 1 / 2 / 3 (Difficulty.raid_rate); 25% / 35% / 45% of them are surprises.
* Announced raids are ordinary packages in the tasking order: "Intercept a raid on Kobuleti AB", flown like the fleet-defence mission (your CAP station sits on the bearing the bombers arrive on; the bombers are already en route when you spawn). Bombs that get through cost the airfield defence strength and parked aircraft; stopped raids cost Red its bombers. A raid you do not fly is settled by odds like any other package.
* Surprise raids are never announced. If nobody flies them they are settled overnight: the airfield's alert aircraft and defences against the bombers ("Overnight: Surprise raid on ... the bombers got through"). They replace the old random overnight air strike.
* Emergencies. When you click Fly there is a chance (about 3% / 9% / 21% a sortie by level, at most one per sortie, never two sorties in a row; Settings > Emergencies switches them off) that something breaks out: a surprise raid on one of our airfields, or "troops in contact" in the sector Red is pressing hardest. The answer is fixed by the campaign, the day and the package, so closing and reopening never re-rolls it.
  - Your squadron can take it if the role matches (fighters for a raid, an A-10C for troops in contact), the airfield is within 60% of your combat radius of the event, and a free pair is left once your own tasked flight has taken its aircraft. You get a popup: Scramble, or Stay with my tasking. If you cannot take it, the popup just tells you why.
  - Scramble: you fly the emergency. The package you were tasked with is left to the war simulation (and joins your mission as AI when it is a ground job in the same area). If your squadron cannot cover both, that package is not dice-rolled with missing aircraft: it is postponed and comes back first in tomorrow's tasking order.
  - Stay (or cannot): a "troops in contact" emergency is flown by AI inside your mission when its sector is within the merge circle and the unit limit allows; otherwise, and for raids, the war simulation settles it.
* A raid you were sent to stop is scored from what really happened: bombers still alive when they reach the field hit it (defence strength, parked aircraft). Leave before they arrive and a coin toss decides.
* Limits you should know: a raid is its own mission, it is not folded into another package (the builder only folds ground targets together); the AI does not fly your displaced package visibly, the war simulation settles it. The old overnight "enemy air strike" is gone, so airfield defences now fall to real raids only. Raid and emergency numbers are first guesses.
* Settings: new tickbox Emergencies. Saves: an old campaign loads without raid data and starts fresh.

## v0.23.0
* The ground war (phase 1). The front is no longer a few armor columns that only exist to be shot at: it is five sectors along the Sukhumi to Senaki axis (four plus one deep zone toward Kutaisi), and every sector holds a Red strength and a Blue strength (0 to 100). The Campaign page lists them and the map draws the sector strengths and a dashed amber "front line".
* Each night every contested sector fights. Red attacks with a chance that grows with the difficulty and with its strength ratio; Blue counterattacks where it is clearly stronger. Losses scale with the other side's strength, the defender gets a 25% bonus, and an attack that overwhelms the defender breaks it: the survivors fall back one sector and the winner moves forward. A force too small to hold ground withdraws. A sector nobody holds is occupied by the neighbouring side. Reinforcements arrive at the sector in contact, scaled by supply.
* Supply: each side's supply is 55% plus 45% of the mean health of its fuel farms and depots (Red from the strategic targets, Blue from new Blue facilities that are now part of the campaign file: a fuel farm per friendly airfield and a forward depot). Strike a Red depot and Red's reinforcements and punch weaken; Red can now do the same to us (Phase 3 will let them attack the Blue facilities).
* Air power matters on the ground. Close air support is offered only for contested sectors, with the strengths in its description, and urgency grows with Red pressure. A flown CAS sortie takes its losses off the Red column AND 60% of that off the sector's Red strength. Losing the friendly task force at your JTAC costs Blue 40 strength in that sector. The friendly task force you see at the JTAC is scaled to Blue's strength there.
* Fields can fall: if Red holds the sector next to Senaki (sector 4) or Kutaisi (sector 5) and Blue has nothing there, that field falls: its defence goes to 0 and its squadrons move to the nearest field, losing 30% of their aircraft. Retake the sector and the field is back (empty of defences). Two fallen fields at once is DEFEAT.
* Neglect is punished, effort is rewarded. In my simulation (60 days, not flown, just the nightly resolution): at Level 2, with no air support at all Red takes a field around day 55; about 3 strength points a day of air support holds the line, about 6 pushes it back. Level 3 neglected loses a field around day 36. Level 1 Blue wins slowly even unaided. Difficulty only changes the numbers (starting strengths, Red attack chance, reinforcement rates), never the rules: Red and Blue use the same ones.
* Saves: the campaign file format is now 5. A v0.22 (format 4) campaign loads, gets a ground war for its level and says so in the war log. Older ones are still refused.
* Not done yet: Red raids and emergency scrambles (Phase 2) and SAM relocation and rebuilding for both sides (Phase 3). The balance numbers are first guesses; tell me how a real campaign feels.

## v0.22.0
* The terrain scan now also measures ground height. The same scan mission, after the land and water pass, samples the ground on a 1 km grid (3 x 3 points per cell) and writes SQE_relief_<theatre>.json next to the old file: the highest and the average ground per cell, in units of 10 m (a few MB). The scan takes about one more minute. Existing land and water scans keep working untouched; run the scan mission once more to get heights. Settings > Terrain scan shows a second line, "Ground height: loaded (... highest ground ...)" or amber "not scanned".
* Minimum safe altitude (MSA) on the kneeboard, page 1 notes: "MSA 10,500 ft along the route." It is the highest ground within 5 nm of any leg of the route plus 1,000 ft (2,000 ft over mountains, where the highest ground is above 5,000 ft), rounded up to 500 ft. Without the scan the line is absent.
* Terrain masking for LOW flights: a radar SAM that covers a low route is now judged by what it can really see over the terrain (line of sight over the height grid with the 4/3-earth radar horizon), never counting for less than 0.2 of its weight. Before, every radar SAM counted exactly half against LOW. A SAM behind a ridge no longer forces a LOW profile; one on open ground does.
* A MED profile is never planned below the minimum safe altitude of the IP-to-egress legs. The role altitudes themselves are not raised (a CAS flight is meant to be low).
* Flights already underway at the start of the mission (in-progress merged packages) spawn at least 1,500 ft above the highest ground near their position instead of a flat 6,000 ft.
* The line of sight is an approximation: 1 km cells show ridges but not small hills. It chooses a profile; it does not guarantee a site cannot see you. The probe code could not be run in DCS here; it was run in a Lua interpreter against a mock of the DCS API and its file read back by SQE.
* Without the ground-height file everything behaves as in v0.21.0.

## v0.21.0
* Threat-aware altitude profiles. A package no longer flies one fixed altitude: the planner looks at which live SAM and AAA sites cover the route from the PUSH to the egress and picks HIGH (the role altitude, as before), MED (about 60% of it, at least 10,000 ft) or LOW (500 ft above the ground, 300 ft for the A-10C). PUSH stays at the role altitude; the chosen profile applies from the IP to the egress. When nothing is clearly better, the profile is exactly what it was before.
* How it chooses: each system has a hand-set altitude band in which it engages (AAA and MANPAD below about 10,000 ft, SA-8 16,000, SA-15 20,000, SA-19 11,000, SA-2 above 1,500 ft, the rest from near the ground up) and a weight (SA-10 3.0 down to AAA 1.0). The planner adds up what covers each altitude, adds a small cost for lower profiles (fuel, flying difficulty) and picks the least exposed. Radar SAMs count half against a LOW flight (terrain masking and radar horizon). A lower profile has to be clearly safer to be chosen. All numbers are in sqe/profiles.py.
* LOW is flown as height above the ground (DCS radio altitude), so the flight follows the terrain; the terrain scan does not hold elevation, so this needed no new scan. On the kneeboard a LOW point reads "500AGL" and page 3 says why: "LOW from the IP: SA-11, SA-2 cover the target at HIGH altitude."
* Limits: SEAD flights and escorts never go LOW; CAS chooses only between its usual altitude and LOW; the FC3 F-15C never goes LOW; a cloud base under 2,000 ft closes LOW. The target of a DEAD package does not push the package low (it is the site you are killing). Your own TGT point stays on the ground. Merged packages get their own profile.
* Not done: the weapon is not a factor yet (the loadout library does not say which loads need a low or a high release), speeds do not change with the profile, and fuel is not recomputed for low flight.
* The per-type tables were reviewed; the Hornet and Viper defaults stay as they were. New per-type fields (med_alt_ft, low_agl_ft, no_low) are in RouteProfile.

## v0.20.0
* DEP (the climb-out point after takeoff) is now spaced out the way real departures are flown. It used to sit 4 nm from the runway, which was too close to the takeoff spot.
* From a carrier DEP is 10 nm out, the Case III departure circle, on the radial toward the marshal point. The TAKEOFF line on the kneeboard now reads, for example, "CVN-74, depart radial 045". From a land base DEP is 8 nm out (6 nm for the A-10C) on the straight line to the marshal point. On a short leg it never goes past 40% of the way to the marshal point.
* Straight-out-along-the-runway is not modelled: the FAA only requires 400 ft above the runway end before a turn, and a fighter does that within a mile or two. It would also mean guessing which runway DCS puts you on.
* The timeline follows: the longer climb-out moves DEP, marshal and the whole schedule by about a minute. Nothing else in a built mission changed.

## v0.19.0
* The kneeboard is now three pages laid out like a printed form: shaded section bands, ruled rows and exactly three type sizes (24 px title, 16 px values, 11 px labels). The old pages mixed 11-18 px text; nothing is smaller than 16 px now except the small band labels.
* Page 1: comms and waypoints, then notes (waypoint numbering, tolerances, time zone), one fact per line. Page 2: fuel, codes, weather, the target LAT/LONG in its own block, bullseye, package list. Page 3: other packages in the mission, threats near the target, intelligence, including the new reinforcement and alert hints.
* The header no longer says SQE. The page-3 band reads "OTHER PACKAGES - OWN PUSH / TOT" (it used to say "AI packages").
* Every time on the kneeboard is hh:mm:ss, including takeoff, DEP, IP, EGR, RTB and the "hold to" time (before, only PUSH and TGT had seconds). Other-package lines are laid out as PUSH / TOT / DONE in a row.
* Text wraps only at logical breaks: after a comma or a sentence, so "+/-30 s" and "Dodge 2 4xF-15C" are never split.
* The TGT row's remark now says "TGT LAT/LONG - PG 2" ahead of the jet's own note. The F-14B(U)'s old remark "coords below" was wrong (the coordinates are on page 2) and is gone. The time-zone note uses the theatre's own offset.
* Only the kneeboard changed in the mission: nothing else in a built mission is different from v0.18.0.

## v0.18.0
* Settings is now five tabs instead of one long page: General (takeoff buffer, marshal slack, AI fuel, F-14 waypoint names), Campaign (weather, reactive dispatch, ruins, carcasses), Mission build (package merging, radius, limits, CAP ranges), DCS integration (DCS and Saved Games folders, the MissionScripting.lua patch) and Terrain scan.
* The Terrain scan tab starts with a plain status line: green "Scanned" with the grid size, or amber "Not scanned". The scan mission button and a Re-check button live there. Every tab scrolls, so the long help texts never get squeezed.
* On a first run, with no valid Saved Games folder, Settings opens on the DCS integration tab.
* Nothing else changed: the same settings, the same names, the same saved file, and missions are identical to v0.17.0.

## v0.17.0
* Reactive dispatch. On top of the planned enemy air picture, a sortie can now see extra fighters launch while you fly.
* Red reinforcements: with a chance that depends on difficulty (rare at Level 1, about one sortie in three at Level 2, more than half at Level 3), other enemy wings send extra pairs toward the target. They are real aircraft of that wing: a wing never sends more than it has available, counting what the planned picture already uses, and only types within their intercept radius of the target fly (MiG-21 110 nm, MiG-23 130, MiG-29 170, Su-27 220, F-4 150, F-5 100; hand-set and shorter than published combat radii because a scramble must reach the area, fight and get home). They launch after the package is detected, with a short random delay, so far fields arrive late, often during your egress. Losses come out of the wing at the debrief like any other.
* The total enemy fighter count is held to a ratio of your fighters in the mission, drawn per sortie: about 0.2-0.5 at Level 1, 0.6-1.1 at Level 2, 1.0-1.6 at Level 3, and now and then 2.0 at Level 3. Never more than three extra pairs. A package that is already outnumbered gets nothing extra.
* Blue alert pairs: when the enemy response outnumbers your fighters, for fleet defence and BARCAP, or when a fleet raid is part of the same wave, up to two alert pairs launch from the carrier or a nearby base. They come from squadrons with fighter jets that the mission is not already using (the base must be within 60% of the type's combat radius of the fight), and they come out of that squadron's available aircraft: their losses count at the debrief.
* The briefing gets an Intelligence line naming the field and the direction of possible reinforcement, or the squadron on alert. No numbers.
* Reinforcements are the first thing skipped when a mission is near the unit limit; no flight is dropped for them. Settings > Reactive dispatch turns the whole thing off. Planned campaigns are unchanged (12 fixed-seed campaigns match v0.13.0).
* Untested in DCS itself: the scramble and launch timing, and whether carrier alert groups launch cleanly when triggered.

## v0.16.0
* Carcasses. Ground sites the war has damaged or destroyed now show burnt-out wrecks (SAM launchers, trucks, tanks) near your route, next to the smoking ruins. A site that is half gone shows about half its vehicles as wrecks; a destroyed site shows all of them (at most six per site).
* The layout is fixed per site: it is seeded by the campaign and the site, not by the day or the sortie, so a wreck stays where it was and a site that gets worse only ADDS wrecks. A damaged site that still has live vehicles puts its wrecks with them; a destroyed site uses a fixed spot.
* Cheap by design: wrecks are dead static objects (no AI, no weapons, no radar), and each counts 25% of a unit toward the unit limit (Settings > Wreck weight). They are placed last, so when a mission is over the limit the wrecks furthest from your route are dropped first and no flight is touched. Only sites within 40 nm of the route get wrecks. Switch them off with Settings > Carcasses.
* Untested in DCS itself: SQE writes the wrecks as dead statics using the vehicle's own type. If DCS shows nothing, or shows a live-looking vehicle, tell me which. With nothing damaged (a fresh campaign) nothing changes.

## v0.15.0
* Weather (Settings > Weather). **Clear** is still the default and is exactly what SQE always built. **Procedural** follows the theatre's climate: each month has its own odds of clear, scattered, broken, overcast, rain and storm, and the weather changes slowly from day to day (a day is always the same as yesterday or one step different, never clear to storm overnight). Inside a day it drifts from morning to the next morning, so each sortie sees the weather at its own start time. You can also pin one weather for the whole campaign (scattered, broken, overcast, rain, storms).
* Everything is seeded from the campaign and the day, so the plan, the mission and the briefing agree and a saved campaign shows the same weather every time you open it.
* Real DCS cloud presets, cloud base, visibility, rain, dawn fog, wind (at the ground, 2,000 m and 8,000 m), turbulence, pressure and temperature are written to the mission. The briefing and kneeboard show the weather; the Missions page shows each package's weather.
* Loadouts follow the weather. Laser-guided weapons need a cloud-free line of sight (the USAF's Desert Storm report puts the threshold at ceilings of 10,000 ft and up); imaging Mavericks and similar need a lower ceiling and visibility; unguided weapons need you to see the target. When the weather rules a weapon out, SQE swaps it for the closest-weight GPS bomb that fits the same pylon (JDAM) and tells you on the Missions page and in the briefing. GPS weapons, anti-radiation missiles and air-to-air weapons ignore the weather.
* A package is scrubbed when it cannot attack at all: a storm, fog or a ceiling under 600 ft stops every offensive package, and a flight left with no usable weapon stops its package. A scrubbed package cannot be flown and the war simulation leaves its target alone. Combat air patrols over the fleet and bases always fly.
* A pack's `climate` block holds the numbers (see docs/THEATRES.md). The Caucasus numbers come from Sochi's published sunshine hours and rain days; wind and fog are hand-tuned.
* Untested in DCS itself: how the cloud presets look and sit against the terrain, and the wind direction convention. In clear mode nothing changed: 12 fixed-seed campaigns and missions are still identical to v0.13.0.

## v0.14.0
* Theatre packs: everything that is specific to the Caucasus (airfields, squadrons, depth tiers, carrier station, sun position and time zone, monthly temperatures, terrain scan area and file, operation text) now lives in `sqe/data/theatres/caucasus.json` instead of being spread through the code. Behaviour is unchanged: 12 campaigns generated with fixed seeds, across all difficulty levels and jets, and their built missions are identical to v0.13.0.
* You can add a theatre without touching code: put a pack in `%APPDATA%\SQE\theatres\`. The New Campaign window shows a Theatre picker once there is more than one. See docs/THEATRES.md.
* A campaign remembers its theatre; opening one switches the map, coastline, sun times and terrain scan to it. The terrain scan mission and file follow the theatre.
* A pack whose bomber base is not one of its enemy airfields no longer crashes the war planner.
* Internal: `geo_data.py` is gone (the coastline is a data file in the pack).

## v0.13.0
* Merging by radius: packages whose target lies inside a circle (Settings > Merge radius, default 50 nm) around YOUR target fly in the same mission, within the same time windows as before (up to 30 min after yours, up to "Earlier packages" before). The old "same area" test is replaced. At most six packages fold in; the unit limit (default 250) is applied by dropping the package furthest from the circle's centre first.
* The circle is kept inside the box that holds every possible target (destroyed sites included): near an edge its centre slides inward so it is not half empty, and your own target always stays inside it.
* The daily plan now launches packages whose targets are within the radius of each other in the same wave, so they can actually fold together.
* Ruins use the same circle. BARCAP and fleet defence are still never folded by area.
* The debrief no longer says anything when the sortie ended with you still airborne.

## v0.12.8
* The default merged-mission unit limit is now 250 (was 150). A settings file that still holds the old default of 150 is moved to 250 once; any other value you set is kept. Change it any time in Settings.

## v0.12.7
* Fix: vehicles in the water. A final pass now checks every ground group (armour columns, the friendly task force and its JTAC, base defences, sites) against the terrain scan and moves any group with a unit or driving destination in the water, as a whole and as little as possible. In 74 test builds against a real scan, no ground unit started in the water. Without the scan the rough coastline is used for the same check.
* DCS reports rivers and ponds as water too, so only the sea and big lakes keep the full shore margin; rivers and small lakes use the river margin (100 m).
* Settings lists which theatres have a terrain scan and when it was made.

## v0.12.6
* Every sortie build now says in its warnings whether ground sites were placed with the DCS terrain scan or only with the rough built-in coastline, so it is clear which one produced a given mission.

## v0.12.5
* Creating the terrain scan mission no longer prints pydcs's harmless 'Failed to parse Lua code ... description.lua' lines (a livery file in your DCS install that pydcs cannot read; it is skipped either way).

## v0.12.4
* Fix: Settings crashed on opening (wrong import for the terrain scan status line). The smoke test now builds the Settings and New Campaign dialogs so this kind of slip is caught.

## v0.12.3
* River margin is now a setting (Settings > Shore margin, second box) and defaults to 100 m instead of 400 m: sites only keep out of the water and off the very bank, so batteries can sit near streams. Needs the terrain scan; the sea margin is unchanged (1500 m).

## v0.12.2
* First campaign: if the terrain scan has not been done, SQE offers it once (create the scan mission now, or skip and do it later in Settings). Choosing the scan means no campaign is created until you have run it, so the first campaign already gets exact placement.

## v0.12.1
* The terrain scan mission now uses the free Su-25T slot instead of the F-15C (part of the paid Flaming Cliffs 3 pack), so it runs on a DCS install with only the free aircraft and the free Caucasus map.

## v0.12.0
* Terrain scan: Settings > "Create terrain scan mission" writes SQE_TerrainScan.miz into your DCS Missions folder. Fly it once; a script reads DCS's own surface type over the whole theatre (four samples per 250 m cell, so narrow rivers are not stepped over) and saves SQE_terrain_caucasus.json in Saved Games\\SQE. From then on every ground site (SAMs, garrisons, radars, depots, armour columns) is placed on real dry land, at least the "Shore margin" from the sea (default 1500 m) and 400 m from rivers. Airfield base defences are placed on dry ground the same way. Without the scan the coarse built-in coastline is used, as in v0.11.1.
* Campaigns you open are re-checked against the scan; sites that are in water or on a riverbank are moved once.
* Nothing from DCS is bundled: the scan is made on your own install.

## v0.11.1
* Fix: enemy sites generated in the sea. SAM sites, garrisons, radars, depots and armour columns are now placed on land, at least 1.5 km from the coast, and garrisons and column air defence stay close to what they guard. Campaigns you open from older versions are corrected once (a note goes in the war log). A site's random shift in the mission can no longer push it into the water either.

## v0.11.0
* Ruins: an earlier package of the same day and area that has already struck by the time your mission starts leaves its target burning: up to three sites, a few smoke plumes each (a destroyed site gets three big fires, a failed attack one small fire). Capped to protect VR frame rates. Settings > Package merging > Ruins switches it off.
* If that package has struck but is still airborne, its flights spawn on the way home along their egress route, land on their own, and the ruins are already there. If it has landed, only the ruins remain.
* The result is rolled when the mission is built and stored: what you saw burning is what the war applies at the debrief. Those packages are not credited to you.

## v0.10.0
* Package merging now works in both directions: packages that started up to 15 minutes BEFORE yours (Settings > Earlier packages, 0-30) also fly, already airborne and underway when the mission starts (spawned along their route, or holding at the marshal point). A package that has already struck and gone home by then is left out with a note.
* Missions screen: a package that another one folds in is shown inside that package's panel instead of as its own row. Each package in the panel has its own table and FLY button, and a line says what FLY there gives you (start time and which packages fly with it).
* Commander's intent: 6-8 lines per objective type, each naming the actual site. Packages of the same type in one day's tasking order never share a line, and the signing officer rotates too. The briefing uses the same line.

## v0.9.12
* The player's TGT waypoint now sits on the ground target at 0 AGL (kneeboard shows "AGL 0"), so pods, weapons and Jester / the WSO can slave to it. Applies to strike, DEAD, SEAD and CAS.
* A player SEAD route is now IP, TGT, EGR like the others: the standoff "SEAD" launch point is gone for the player and the standoff range is your call. AI SEAD flights keep their launch point.
* AI flights are unchanged: TGT stays at cruise altitude for them, so no AI-only flight gets a ground-level waypoint.

## v0.9.11
* Carrier starts: the carrier and escort ships now get warehouse entries like the Mission Editor writes on save. Without them the carrier had no warehouse to spawn the player's aircraft from, which dropped you into the F10 map until you resaved the mission in the editor.

## v0.9.9
* Flying from the carrier no longer lists the "LSO" and "Air Boss" stations as slots (the carrier is saved with allowLso / allowAirboss false).

## v0.9.8
* F-14B(U) kneeboard: the start point is now 0 and DEP is 1, matching Jester.

## v0.9.7
* Packaging only: release zips no longer contain `.gitignore` or the GitHub guide, so copying a zip over your repo folder keeps your own.

## v0.9.6
* The sidebar no longer shows the file name or a second copy of the campaign title (the title is in the page header and the window title).

## v0.9.4
* The Missions screen and the briefing now show the enemy fighter count for the whole mission, counting folded packages, the same number the mission is built with.

## v0.9.3
* App icon (stencil SQE roundel): window and taskbar icon, and the built SQE.exe.

## v0.9.2
* F-14B(U) CAP: 4 AIM-54C, 2 AIM-7P, 2 AIM-9M, 2 tanks (stock AAW05 with the LANTIRN pod on station 9 swapped for the second Sparrow).

## v0.9.1
* **Loadouts corrected from DCS's own stock presets** (`loadouts.py`): the F-16C SEAD flight now carries 2 HARM + 2 AMRAAM + 2 AIM-9X + 2 tanks + ECM + Litening + HTS instead of 4 HARMs. F/A-18C, F-14B(U), F-15C and A-10C loads were taken from their stock presets too.
* Docs: "DCC" is now "Digital Crew Chief" in THIRD_PARTY_NOTICES.

## v0.9.0
* **Enemy air with folded packages:** enemy fighters = the biggest package's need + a share (Settings, default 100%) of every other folded package's need. Still trimmed to the unit cap.
* **Engage cap:** enemy patrol fighters and your HAVCAP/BASECAP no longer chase past a set range (default 50 nm each, 0 = unlimited). Scrambled alert fighters are untouched.
* **Carrier placement:** the pull-back only uses open water (25 nm off the coast), picks a heading with 120 nm of clear sea, and otherwise stays on its home station. Smoke test checks carrier/escort routes for land.
* **Start numbering:** F-15C and A-10C now start at 0 (F-14B still 1 until checked in the cockpit).
* **FC3 (F-15C):** no COMM1 presets popup; briefing and kneeboard list plain frequencies, no channels.
* **F-14B(U) special waypoint names (untested in the cockpit, Settings toggle, default ON):** IPXIP, TGTXST, RTBXHB, BULLSXB, DEPX1, MSHLX2, PUSHX3. Kneeboard keeps plain names.
* **Debrief kill log:** who killed what, with weapon and time, recorded by the hook and shown in the debrief.
* Removed "seed" from the waiting window.
* Mission Editor lock rule now enforced for every group (fixes an AI CAP edge case in fleet defence).
* **GitHub prep:** MIT LICENSE (MarkuzJuniuz), author set, MissionScripting patch is now opt-in (asked on first run, default off).

# Changes in v0.8.8

- Kneeboard (F/A-18C): the start point is waypoint 0 and DEP is 1 (ED: "Waypoint 0 is your starting position" in the Hornet). F-14B and A-10C still number the takeoff point 1 until checked in the cockpit.

# Changes in v0.8.7

- Kneeboard (F-16C): the base / takeoff point is steerpoint 0 and DEP is 1, then 2, 3... (F-15C is unchanged: B, then 1, 2...). The note under the table says so. Other jets still number the takeoff point 1.

# Changes in v0.8.6

- Fixed: opening a v0.8.5 sortie in the Mission Editor gave "All waypoints (2-4) have locked speed and surrounded by waypoints 1 and 4 with locked time" and it could not be saved. The point just before PUSH now has a free speed on your flight, so the takeoff-to-PUSH leg is valid. v0.8.5's fix for "Flight is delayed to start" (takeoff locked at mission start) is kept.

# Changes in v0.8.5

- **Fixed: "Flight is delayed to start" and no cockpit.** Your takeoff waypoint was time-unlocked while PUSH and the target were time-locked, so DCS worked out your start time backwards from those and held you at the F10 map until then (several minutes). The takeoff waypoint is now locked at mission start, as the Mission Editor does for a normal runway start. Kneeboard times and the plan are unchanged. AI flights keep their staggered starts.

# Changes in v0.8.4

- Package merging ("Same area") is now the default for new installs. If you already have a settings file, your saved choice stays; change it under Settings.

# Changes in v0.8.3

- The takeoff waypoint in the mission file no longer carries a time (it was the Takeoff buffer, 60 s by default). DCS can show "flight delayed to start" and hold a player at the start when the takeoff waypoint's time is later than the mission start; your flight now starts the moment the mission loads. The kneeboard still shows the buffered takeoff time and every other time is unchanged.

# Changes in v0.8.2

- Folder paths in Settings (and the saved settings file) now use one slash style, the OS's own (backslashes on Windows). Before, the DCS install path (from the registry) and the Saves path (from the folder picker) could show different slashes.

# Changes in v0.8.1

- Settings: the fuel option is now called "AI fuel management" and the MissionScripting note no longer names other tools. README and THIRD_PARTY_NOTICES credit Liberation, Retribution, Falcon BMS and Strike Fighters as inspiration (no code from them). GitHub guide: corrected the licence of Retribution (LGPL-3.0, not GPL).

# Changes in v0.8.0

**Old campaigns will not load** (the enemy order of battle changed; the save format is now 4). Start a new campaign.

**Depth tiers replace the flat 87 nm minimum**
- Every enemy asset belongs to a tier: 1 the front line (armour columns and the SAMs that travel with them), 2 Abkhazia (Sukhumi, Gudauta), 3 the coast and north Caucasus (Sochi, Nalchik, Beslan, Mozdok), 4 deep (Maykop, Krymsk, Gelendzhik). Tiers up to **front + 2** are open for tasking, so a new campaign is fought over Abkhazia and Nalchik is a late-campaign strike, not a day-one target.
- The **front** advances (stage 1 to 3) when the SAMs and ground forces of the open tiers average 30% or less (after at least 4 days at the stage), or after 14 days of stalemate ("the enemy line buckles"). Destroyed assets stay destroyed, so progress always sticks. The Overview shows the stage; the Forces page shows each asset's depth and whether it is still locked.
- The old route rule stays: a target whose route crosses an intact SAM belt in front of it is not offered, and the blocking site becomes a DEAD objective instead.

**SEAD and DEAD are different jobs**
- A DEAD objective is now a package with a dedicated **SEAD flight** (HARM) and a **DEAD flight** (the strikers) behind it. In the mission the SEAD flight pushes 90 seconds ahead and its HARMs are tasked against the site's radars, not the whole site.
- Killing the radars **blinds** the site; it does not kill it. If all the radars of a site die and the launchers survive, the debrief says SUPPRESSED, not dead, and the site is flagged "radars blinded" until the day ends. A site that is hurt but alive is offered again as a mop-up ("Finish off ..."), with a priority bonus.
- AI-resolved packages follow the same rule: a SEAD roll blinds the site, then the DEAD roll is far better against a blinded site (and the DEAD flight is more likely to take losses against an active one). A blinded site also weakens the SAM defence of other packages launched later the same day.
- Kneeboard and briefing label the flights "SEAD" and "DEAD". Short-range SAMs (SA-8/15/19, AAA) are no longer SEAD/DEAD targets; CAS deals with them.

**More SAMs, and ground troops to fight**
- SAM sites per airfield cluster: Level 1 one, Level 2 three (was two), Level 3 four (was three). Level 2 and 3 also put short-range SAMs (SA-8, SA-15, SA-19) with the front-line armour columns (new SA-8 site).
- **Garrisons**: long-range SAM sites may have a dug-in ground garrison (about 60% of sites at Level 2, all at Level 3; none at Level 1). Garrisons are CAS targets ("Close air support: dislodge the ... garrison"). In the mission the garrison stays put and your troops advance on it with a JTAC; it is spawned with the SAM site it guards.
- To keep the frame rate sane the mission spawns the target's cluster (target, its two nearest SAM defenders, its garrison) plus at most two other SAM sites whose rings touch the route. Typical unit counts: about 60 to 80 at Level 2 and 70 to 100 at Level 3 for a single package.

**Other**
- No single job type may fill more than 40% of the day's packages (DEAD packages are big).
- A wing whose airfield has been destroyed no longer replenishes and loses a quarter of its aircraft every day; before, a campaign could be stuck with an enemy air arm that never fell below the victory threshold.
- The Forces page asset table has Type, Depth and Condition columns.

# Changes in v0.7.3

- Shorter transit to the marshal point. DEP is now a short climb-out / turning point about 4 nm from the field (was 8 nm), on the line toward the marshal. The marshal search starts at 15 nm behind the base (was 25 nm) and only moves farther back when the safety rules need it (at least 20 nm outside SAM rings, 90 nm from enemy fighter bases).

# Changes in v0.7.2

- New setting **Takeoff buffer** (Settings): seconds between mission start and the takeoff time on your kneeboard. It replaces the fixed 3 minutes; default 60 s, can be negative, granular to the second (-600 to +900 s). Negative means the plan expects you to be rolling before the clock starts, so you make the time up in the air; waypoint times in the jet are never written before mission start. Marshal slack is unchanged (default 2 min).

# Changes in v0.7.1

- **MissionScripting.lua is automatic.** Settings has a checkbox (on by default) replacing the old patch button: SQE patches DCS's MissionScripting.lua when it starts and restores it when it exits. It only comments out the io/lfs sanitize lines (the rest of the file is never overwritten, so DCS updates are safe) and keeps a backup next to the file. If SQE crashed and left the patch in place, the next start recognises it and restores it at exit. Closing SQE with a sortie pending asks first, because DCS can no longer write results once the file is restored.
- **Call-outs rewritten.** The waypoint "NAV:" messages are gone. The sound is now a short 1 kHz beep (not a squelch). Messages name the speaker in capitals:
  - the AWACS and tanker keep their scheduled calls ("OVERLORD to VIPER 1: package, push, push, push.");
  - every other flight announces "pushing", "off target, egressing", or "on station" (HAVCAP, base CAP, CAP) at its own times; extra packages of a merged mission are prefixed "P2 ...";
  - AI aircraft, including your own wingmen (never you), call their weapons: "Magnum" (anti-radiation missile), "Fox 1/2/3", "Rifle" (guided air-to-ground missile), "Bombs away", then "direct hit" when one of their weapons hits the target's site, and "splash one" for aircraft kills;
  - radar results: "track radar destroyed", "<site> blinded, all radars destroyed" (a radar that is only shut down is not detected), and "target destroyed" when the last unit of an objective goes. These come from the flight that last hit that site, or the package's lead flight.
  The AWACS makes no splash or target calls.

# Changes in v0.7.0

**Old campaigns will not load** (the squadron structure changed; the save format is now 3). Start a new campaign.

**Realistic squadrons**
- The coalition now has 11 squadrons, about 175 jets at Level 2: Navy 2x F-14B(U) and 2x F/A-18C (12 each), USAF 3x F-16C, 2x F-15C and 2x A-10C (18 each; Level 1 is scaled up, Level 3 down). Every squadron has its own callsign (Springfield/Uzi, Hornet/Squid, Viper/Cowboy/Venom, Enfield/Dodge, Hawg/Boar).
- The enemy air force is about 20 aircraft at Level 1, 90 at Level 2 and 150 at Level 3, spread over several squadrons per airfield (Forces page shows it). Expected fighter opposition per target was recalibrated so a bigger air force does not swamp every mission.
- New Campaign has a squadron picker for the jet you chose.
- The daily tasking order is bigger (up to ~14 packages, usually 6-12 depending on level). Packages are launched in waves, same-area packages together, and are numbered in time order.

**Missions filter**
- A drop-down above the list: "My squadron" (default; only packages with a flight from your own squadron) or "All packages". Your choice is remembered. In My squadron mode FLY buttons appear only on your squadron's flights; in All mode on any flight your jet type can fly.

**Package merging** (Settings > Package merging: Off / Same area)
- With it on, packages in the same area (targets within ~45 km, or covered by the same SAM cluster) that start at or after yours and within 30 minutes are folded into your mission (at most 2 extra, 3 packages in all). The tasking list shows "+N packages".
- The extra packages are AI-flown but fully live: their own marshal, push, TOT and stagger, each pushing at its own time. They share ONE ground world (a site needed by two packages is spawned once), ONE set of support (tanker, AWACS, HAVCAP, base CAP) and ONE enemy air picture sized by the biggest need, not the sum. Callsigns are renumbered so nothing collides. Kneeboard page 2 lists the other packages with their push/TOT/done times.
- A merged mission is trimmed (last package dropped) until it fits the unit limit (Settings, default 150), so you can compare performance: the waiting window already prints groups and units.
- Debrief reads what really happened, per package (target damage and losses). If you landed and ended the mission before a merged package reached its target, that package is resolved by the war simulation instead, so staying in the mission longer is rewarded but never required.

# Changes in v0.6.3

- PUSH is now about 10 nm from the marshal point, toward the target (BMS style). DEP, MSHL and PUSH cluster near home; the ingress to the IP is one long straight run.
- Every player waypoint now carries its planned time, so the F-16 CRUS/TOS page matches the kneeboard. Only PUSH and the objective (TGT/SEAD) point are time-locked; speed is left free between them. Kneeboard page 1 notes that Caucasus local = Zulu + 4 h (jets show Zulu).
- AWACS and tanker racetracks run sideways (parallel to the front), shorter (AWACS 40 nm, tanker 30 nm), behind the marshal point; the HAVCAP sits in the rear as well.
- Kneeboard REMARKS show your base name on the TAKEOFF and RTB lines ("Kobuleti: Land. Tower COMM1 CH1", "Stennis: Case I TACAN 74X ICLS 11").
- Enemy CAP stations sit 20-25 nm in front of their OWN base (toward the target), inside their SAM cover, and stay up from the start.
- EGR also avoids CAP stations (35 nm) and enemy fighter bases (40 nm) where possible, as well as SAM rings.
- Alert fighters now scramble when the package comes within a ring around the TARGET (sized so they arrive ~1-2 min before TOT; smaller with no EWR cover; never trips at start). Far-off SAMs and armour are protected. CAS packages scramble on a clock because friendly troops sit on the target.
- Intercept missions (fleet defence / BARCAP) now keep the enemy SAM sites (and nearest EWRs) whose rings touch your route or station.
- Fixed: the player's takeoff/DEP times were offset from the kneeboard times in the mission file.

# Changes in v0.6.2

- EGR is now the FIRST safe point after the target: the closest point (8 nm or more from the target) that is clear of every live SAM ring plus a margin, turning for home and away from enemy fighter bases where it can. It used to sit a fixed 25-30 nm out. A DEAD target itself is ignored (you are killing it); its surviving neighbours are not.

# Changes in v0.6.1

- Your wingmen (and every aircraft in your flight) are now members of each other's Link 16 / SADL network, with the first jet as flight lead: they show blue instead of only the AWACS.
- Enemy CAP is airborne from the first second again (no hidden/late-activated CAP). Alert fighters still scramble from their fields.
- PUSH now sits just ahead of the base (about 12 nm out) and the marshal stays behind it, so both are far from the IP and target; the ingress is one long straight cruise. IP is 20-25 nm from the target, the SEAD launch point is just before it.
- Cruise speeds raised (F-16: 500-510 kts ground speed in the push; F-14/F-18/F-15 similar or faster); climb-out and marshal speeds up as well. Kneeboard times follow the new speeds.
- AI fuel trick (Settings, on by default, switchable): unlimited fuel from spawn until PUSH, real fuel for the combat leg, unlimited again from EGR (same logic as Retribution).
- AI SEAD flights get an explicit attack order on the briefed site's group at their SEAD waypoint (they no longer rely on whatever radar they notice first).
- Minimum target distance raised to 87 nm (about 100 statute miles) from the nearest friendly base; CAS is exempt. If fewer than four targets qualify, closer ones are allowed so the tasking order is never empty.

# Changes in v0.6

**Safe departures, believable timing**
- DEP and MARSHAL are now BEHIND your base (away from the enemy), at least 20 nm outside every SAM ring and ~90 nm from enemy fighter bases. Tanker, AWACS and HAVCAP sit around that marshal point, as close to home as it gets. The route runs marshal -> PUSH -> IP -> TGT.
- The carrier group slides back along the line of retreat (up to 60 nm, that sortie only) until it is at least 150 nm from the target and from enemy fighter bases, so it no longer shoots at the fight.
- Other friendly flights "depart" a few minutes after start from points behind their own base (carrier jets and land jets start differently, same-service flights are spaced a few miles apart) and arrive at the marshal about 2 minutes before their push. Nobody is waiting 10 minutes up there any more.
- Enemy CAP is activated about 4.5 minutes before the strikers' TOT, on stations between the target and THEIR bases (kept away from our marshal, tanker, fields and carrier). Alert fighters still scramble from their own fields.
- Marshal slack is a setting (Settings > Marshal slack). Default 2 min; negative values are allowed (you must beat the natural pace).
- The kneeboard times now count the TAKEOFF -> DEP leg (previously every time was a couple of minutes optimistic).
- Waypoint ESC/SWP/CAS is now TGT, with the task in the remarks. "WINDOW" column is now REMARKS. Divert tower is COMM1 CH6.

**CAS actually fights**
- Enemy column and friendly task force (with the JTAC) start 8-10 km apart and drive into contact so the firefight is under way at the CAS TOT (within about 30 s). Both are weapons-free, alarm red.
- AI A-10s now carry AGM-65D Mavericks, rockets and Mk-82 (before, they had only laser bombs and nothing they could use on their own), start with weapons free, attack the column group, then keep working the zone for several minutes.

**Other**
- Unlimited fuel is off for everyone (AI included). The cheat option is gone.
- Level 1 (insurgent): only two enemy airfields (Sukhumi, Sochi); every other field is neutral.
- Skip Turn button on the Missions page: resolves the whole day (including packages you could fly) and advances the date; any unfinished sortie is discarded.
- On-screen messages are attributed: AWACS calls the push and the 5-minute-to-TOT warning, "NAV:" announces your waypoints.
- File menu shortcut text no longer overlaps the labels. Waiting-window table header says "This sortie".

# Changes in v0.5

**The war is logical now**
- FLOT/gatekeeper rule: a target is only offered if the route to it does not cross an intact SAM belt in front of it; blocking sites become DEAD objectives, so the war advances belt by belt. Minimum target distance is 50 nm.
- Everything the intelligence picture says is there exists from the first second: all SAM sites on the route, CAP flights airborne on stations, alert fighters that scramble from real airfields when the package is detected. No mid-air pop-ups, no surprise pairs, no hidden mobile SAMs.
- Egress is steered away from SAM rings; tanker tracks sit behind the FLOT, away from enemy fighter bases and rings; a HAVCAP is mandatory; aircraft reach counts tanker support (x1.5) only when a safe tanker track exists.
- Staggered push/TOT (sweep 90 s, SEAD 60 s, escorts 30 s ahead of the strikers); your kneeboard shows YOUR times; briefing has a per-flight table.
- Radio call-outs (text + squelch): tanker on station, package push, waypoint announcements, five minutes to TOT.

**Missions**
- Per-mission variety (seeded; every FLY re-rolls layouts, unit mixes and column positions).
- CAS has friendly troops in contact with a JTAC among them; A-10s get an explicit attack order; debrief reports friendly losses.
- Level 3: Tu-22M3 raid on the fleet with range-limited escorts (regional powers use bombers only when losing badly; insurgents never).
- Later packages stay flyable (aircraft can fly more than one sortie per day).
- Kneeboard page 1 = comms + times (no coordinates); page 2 = codes, package, threats, target coordinates for strike roles.
- Briefings rewritten in-universe (no game-mechanics talk).

**App / tools**
- Smoke test is fully isolated (temp folder, no writes to your real settings) and parses every mission as Lua. v0.4 testing overwrote your real settings: delete `%APPDATA%\\SQE\\settings.json` once.
- Map data embedded in code (fixes the missing map in built exes). Options menu: unlimited-fuel cheat for your flight.

# Earlier: v0.3

**Bug fixes**
- Results hook was stored as a translation key, so DCS tried to run its name as code (the `DictKey_Translation_5` error) and nothing was tracked or despawned. Fixed.
- SAM sites and armor columns were built as one-unit groups, so SAM launchers had no radar and never worked. They are now single groups.
- A-10 CAS now gets an explicit attack-group order on the armor column.
- Quieted pydcs's harmless "Failed to parse Lua code" log lines.

**Mission generation**
- DCS-native callsigns (Springfield 1-2). Flights are pairs/fours only.
- Escorts/sweeps sized to the expected enemy defenders; enemy fighters are late-activated and arrive at TOT +/- 1-2 min from the enemy side.
- Targets at least 100 nm from our bases (CAS excepted; relaxed only if too few targets remain).
- Tanker/AWACS placed well back from enemy bases with a HAVCAP; base CAP on CAS missions.
- Patriot + AAA at coalition bases (the enemy can degrade them in the war layer; they repair), carrier escorts always.
- Link 16 / SADL networks, STNs and voice callsigns per package.
- Campaign dates (2004), time of day spread through the day (optional night), clear weather.
- F/A-18C, F-15C, A-10C II are now flyable.
- Tanker, divert and bullseye are the last steerpoints; waypoint numbers follow each jet's cockpit (F-15C: B, 1, 2...).
- Kneeboard is two pages. Briefing shows bingo/joker, IFF Mode 3, laser code, bullseye.

**App**
- FLY button on each flight row, themed theatre map with real coastline and SAM rings, Pilot page (sorties, hours, kills, rescues), bases tab, dated header, build size shown in the waiting window.
