# CHANGES.md

## v0.41.429, the tanker and the AWACS always fly with their guard
The pair of fighters that guards the tanker or the AWACS now stays on station for as long as that aircraft is up in the turn, so a package launching in the second half of a turn finds it there. Every package that carries the AWACS or the tanker gets the guard (sweeps and fleet-defence packages included), and the Navy's S-3B tanker, when it is a package's tanker, has a guard too. Before, only about four packages in ten had theirs.
## v0.41.428, AI runway strikers drop their bombs on the runway
The AI flights that crater a runway used to run in to the field and turn for home without releasing. They now bomb with the same plain bomb task as every other AI strike, with their bombs spread along the runway, and a flight held at the gate keeps its full attack window.
## v0.41.427, red sends a fighter sweep ahead of its SEAD raids
At Levels 2 and 3 a red SEAD raid now has a sweep of four fighters (eight when red has the jets) flying about a minute ahead of the SEAD jets and turning back 60 nm short of the SAM site, to draw blue's interceptors before the missile salvo. Level 1 has none, and red sends no sweep if it has fewer than four spare fighters. Level 2's SEAD escorts rise to one fighter for every SEAD jet, as at Level 3, and all of a SEAD raid's escort groups now stay with the bombers.
## v0.41.426, red raid escorts stay with their bombers through the attack
The Su-27 escorts of a red raid used to turn for home as the bombers began their attack run, leaving them to be shot down. They now stay until the bombers reach their egress point.
## v0.41.425, a player's EWR strike is a stand-off job too
A person flying an EWR strike now takes the stand-off kit of their own jet, as the AI does: the F-16C carries AGM-154A JSOWs and the Hornet SLAM-ERs, with the launch point outside the SAM rings. The plain GBU slot is gone; an airframe with no stand-off kit is not offered the EWR strike.
## v0.41.424, AI GBU strikes spread their bombs over a supply site's buildings
An AI strike flight with guided bombs on a fuel farm or depot now gives each bomb its own building instead of dropping every bomb on one point, so more of the site dies per strike. Flights a person flies, and every other kind of strike, are unchanged.
## v0.41.423, the mission hook records where bombs land
The in-mission hook now recognises a bomb in flight (GBU-31, GBU-38, Mk-82 and the rest), so the impact points reach the state file and bombs that land on a runway count toward cratering the field. Before, it only recognised the AGM-154.
## v0.41.422, red's SEAD raids go for a full-strength Patriot more often, and only when it can field the jets
When red picks a blue SAM site to hit, a Patriot at full strength now counts twice as much as a HAWK, so red no longer leaves it for the HAWK beside it. A Patriot is only in the draw while red has the jets for it (two packages, after pooling a second wing); otherwise red goes for the HAWK or another target instead of planning nothing.
## v0.41.421, the sample briefing is a real one from the current build
Docs/SAMPLE_BRIEFING.txt is replaced by a briefing the program wrote itself: a Level 2 F-16C flying the day-1 Standoff DEAD, with the situation, the package table, the timeline, the radio plan and the footer as they read today. The old text still described a counter-air strike and an older package layout. The README link to it is unchanged.
## v0.41.420, the theatre pack guide matches the real pack format
Docs/THEATRES.md now lists the keys a pack really has: `stories` instead of `background`, the `front` chain keys, `red_extra_airports`, `road_blue_airports`, the carrier stand-off, the squadron `role` and the wind keys. The old terrain-scan section is replaced by a note on the data files a pack folder can ship.
## v0.41.419, the setup guide is trimmed to what is current
Docs/GUIDE.md keeps the install, first run, build and troubleshooting steps and adds a short "how a turn works" (4-hour turns, Skip Turn, Auto-Skip). The old sections on tiers, raid popups, dice and the long list of version-by-version features are gone; CHANGES.md has the history.
## v0.41.418, in low cloud or visibility the ground wind keeps each field's ILS runway active
In low cloud, poor visibility or fog, the ground wind is turned to favour each blue field's ILS runway, so the ILS stays lit; the wind aloft follows the season's real direction. In good weather the wind is left as it is. The parked dummy aircraft is gone, and the briefing no longer quotes the wind. Settings > Experimental has a checkbox for it.
## v0.41.417, raids on a field's SAM site or fuel farm read Base Defense, on a depot Depot Defense
The intercept job for a red raid on a blue SAM site or fuel farm is now "Base Defense: Intercept", and one on the forward or rear supply depot is "Depot Defense: Intercept". Nothing reads "Supply Defense" any more.
## v0.41.416, EWR strikes wait for the SAMs to go down, then go out as stand-off jobs
An early-warning radar is no longer a target while a SAM site covers it: the covering sites get their SEAD and DEAD first. Once they are down the radar is struck from stand-off range by AI flights only, never with a GPS-bomb run: F-15Es with JSOW-C, F-16s with JSOW-A, or Hornets with SLAM-ER. A person who picks an EWR strike still flies it as before.
## v0.41.415, a full-strength Patriot draws three SEAD packages, a HAWK two
Red now sends three coordinated anti-radar packages at a Patriot site at full strength (two at a HAWK), and when one squadron cannot field them a second nearby squadron joins. Red will not send a single package at a full-strength Patriot: it waits and raids something softer.
## v0.41.414, debrief: no "you landed" line; a suppressed SAM is a win
The debrief no longer says you brought your jet home. A SEAD or DEAD job that knocks out a site's radars is now reported as a win (the site is "suppressed") instead of 0% destroyed.
## v0.41.413, red's anti-radar raids fire one coordinated salvo
Red's SEAD raids on a blue Patriot or HAWK site now launch their Kh-31P missiles all together, from several directions, instead of one group after another from a single line. The jets also no longer turn aside to attack other SAM sites on the way in: they fly to their launch point and fire at the site they were sent against.
## v0.41.412, the tanker guard reads HAVCAP
The flight that guards the tanker no longer reads TNKCAP in the package tables, radio, kneeboard or briefing; it says HAVCAP, like the AWACS guard. Old campaigns load as before.
## v0.41.411, BARCAP is the only name for base and carrier patrols
The base and carrier patrol flights no longer read BASECAP or CVCAP in the package tables, radio, kneeboard, briefing or guide; they say BARCAP, like the other patrols. HAVCAP and TNKCAP are unchanged. Old campaigns load as before.
## v0.41.410, F-15Es crater runways from stand-off range; JSOW hits now count
A runway strike is now flown by F-15Es when an F-15E squadron is in reach and has jets free: two AGM-154C JSOWs a jet (no wing tanks, so a shorter reach), released on the middle of the runway from about 30 nm out, then straight home; nobody crosses the airfield. With no F-15E free the strike is the plain bombing run it was. Standoff DEAD stays the Vipers' and Hornets'. The mission hook now also counts the AGM-154 JSOW as a runway hit (it saw none before): three JSOWs on the strip close the field like three bombs.
## v0.41.409, the F-14B(U) holds further out, the MiG-31 is a stand-off interceptor
The Tomcat is no longer treated like the F-15C. Its TARCAP and escort stations sit 12 nm further from the fight than before (yours too: only the station and the end of the racetrack move, the rest of your route is the same), and a hunting Tomcat TARCAP engages inside a 35 nm circle, the Phoenix's reach, not the Eagle's 25. A Fighter Sweep goes to an F-15C squadron first and to the Tomcat only when no Eagle squadron can fly it. On the red side the MiG-31 now counts 0.5, not the Su-27's 0.67, when red decides whether to commit to a fight; it engages inside a 40 nm circle and works only from inside its own SAM cover.
## v0.41.408, blue has no road supply sites; Level 1 red's supply follows its inner depots
New campaigns give blue no road supply sites on any level: it keeps only the fuel farms and depots it brought to each field, so every hit on them weighs more. Red keeps its road sites (15 / 30 / 30). On Level 1 red's supply is now 70% its depots near the fields and 30% its road sites, and it falls when you hit them, down to a 45% floor (insurgents supplied by night); it no longer sits on a fixed 70%. Old saves are unchanged.
## v0.41.407, red sends two SEAD packages against a HAWK site too
A HAWK site now draws the same SEAD raid as a full-strength Patriot: two packages in one raid (Level 3: 12 Su-24M / Su-34 with Kh-31P and 12 fighters, was 6 and 6; Levels 1 and 2: 8 and 4, was 4 and 2). A wing with fewer jets free sends what it has, never less than one package. A Patriot below full strength still draws one package.
## v0.41.406, raids folded into one mission no longer share unit and group names
When two or more red raids fly in the same mission their aircraft were both named RAID-B-1, RAID-E-1 and so on, and their groups Raid Bomber 1 and so on. A kill or a "got through" on one raid could be charged to the other raid's squadron, and DCS could drop a group. Each raid now continues the numbering of the one before it, so every name in the mission is unique. A mission with a single raid is named as before.
## v0.41.405, red's Su-34 and Su-24M raids on supply sites and garrisons fire Kh-59M cruise missiles from standoff
At Levels 2 and 3 about a third (Level 2) to a half (Level 3) of red's raids on an uncovered supply site or garrison are now flown by Su-24M or Su-34 carrying Kh-59M missiles, two a jet. They push, fire from about 50 nm out and turn for home instead of bombing over the target, and the site is hit a few minutes later. The briefing says so: "They will fire from about 50 nm out and turn for home; stop them before they launch." The Su-24M carries its APK-9 datalink pod on pylon 4, without which the AI does not fire. Level 1 and raids on fields are unchanged.
## v0.41.404, groundwork for red's Kh-59M standoff strikes (switched off)
Red's Su-34 and Su-24M can now be given Kh-59M missiles and a launch point about 50 nm from the target instead of bombing over it. Nothing changes in play yet: the switch is off until the DCS behaviour has been tested in a test mission.
## v0.41.403, Level 3 red raids on supply sites and garrisons come from two airfields
A raid on a supply site, a garrison or a field whose first airfield cannot field the size red asked for now takes a second airfield's jets too (within 150 nm), and its escorts come from a second wing the same way. The formation can mix types: Su-34s with Su-25s, an Su-27 and a MiG-29 as escorts. Each group flies its own aircraft with its own loadout and goes home to its own field; a raid with Su-25s in it flies low. The briefing lists the types ("2 Su-25 attack aircraft and 4 Su-34 bombers"). These raids were 2 to 4 jets against your 10 to 12; red now has at least your numbers in about 45% of them (was 33%). Levels 1 and 2 are practically unchanged (their raids are small enough for one wing).
## v0.41.402, Level 3 red's SEAD packages are bigger, and raids come from a wing that can fill them
At Level 3 red's SEAD package against a HAWK site is now 6 Su-24M / Su-34 with 6 fighters (was 4 with 2 to 4), and a full-strength Patriot gets twice that. Raids on fields, supply sites and garrisons are now drawn from the nearest wing that has the raid's size free, not just the nearest wing, and the escorts likewise. Red's raids are still outnumbered by blue's intercept package most of the time, but a good deal less often. Levels 1 and 2 are unchanged in size.

## v0.41.401, Level 3 red flies more Su-27 than MiG-29 and only a few Su-25
At Level 3 red's fighters are now 46 Su-27, 20 MiG-29S and 12 MiG-29A beside 8 MiG-31 (was 30 / 28 / 20), and its Su-25 fleet is 18, like your A-10Cs (was 130). With fewer cheap attack jets red raids less (about 4.6 raids a day, was 6.9) and the Su-25 pairs no longer carry most of the supply-site raids. Levels 1 and 2 are unchanged.
## v0.41.400, red keeps a bigger supply net, blue a thin one
New campaigns start with 5 road supply sites for blue on every level, and 15 for red on Level 1 and 30 on Levels 2 and 3 (was 42 / 70 / 70 sites split 65 / 35). Blue's supply is thin, so every hit on it is felt; red plays at home. Airfield fuel farms and depots are unchanged. Old saves keep the sites they have.
## v0.41.399, red's SEAD packages fire all their missiles at the site's radars, then leave
Red's Kh-31P SEAD flights now empty all their anti-radiation missiles at the Patriot or HAWK site they were sent against in one go (Open Fire), then turn for home. Before, each jet fired a single missile at whatever radar the AI picked, sometimes at another field's site.
## v0.41.398, raid intercepts fold into one mission, and the Missions list marks the ones that carry red's raids
Raid intercepts that start inside the time windows now fly in one mission, wherever the raids are going (new setting Merge raids on the Mission Build page, on by default). A raid also counts along its way in, from its airfield to its target: a blue package under that line folds into the raid's mission, and you flying a blue package get the raids that cross your area. Over the unit limit, a raid far from the fight goes first. In the Missions list a mission with only red's packages has a red border and one that mixes yours with red's has an amber border; in the right panel red's packages sit in a red frame.
## v0.41.397, red sends SEAD packages at your SAM sites, no more SEAD and DEAD in front of its bombers
At Levels 2 and 3 red no longer sends SEAD and DEAD groups with its bomber raids, and no longer raids a target that lies under a live Patriot or HAWK. Instead it sends escorted SEAD packages at the Patriot and HAWK sites themselves: four Su-24M or Su-34 with Kh-31P, fired from about 40 nm out, with a pair of fighters for every four (a full-strength Patriot gets two packages in one raid, a HAWK one). The missiles that get through cut the site's health, and once the cover over a field is down red's bombers raid it again; your repairs and rebuilds put the sites back. Level 1 is unchanged.
## v0.41.396, AI strike flights go for their assigned target
Strike flights flown by the AI now attack only their designated target (Open Fire) instead of anything nearby (Weapon Free). Before, they dropped on depots and SAM sites near the approach point and turned for home without reaching the target. CAS is unchanged.

## v0.41.395, the ILS dummy aircraft stands on the grass beside the runway
The small invisible aircraft that keeps each blue ILS runway active (Settings > ILS dummy) no longer sits on a far, covered parking slot. It stands on the grass beside the ILS end of the runway, 100 m off the centreline, past the hold-short line and turned across the runway like a parked aircraft, never on the pavement. Whether DCS lights the ILS for it is still to be checked in the game.

## v0.41.394, raid intercepts on land no longer talk about the fleet
The commander's intent for an intercept of a raid on a field, supply site, garrison or your troops now names what is attacked and talks about bombers and bomb release, not anti-ship missiles and the fleet (it read "Backfires are inbound with anti-ship missiles" for a raid on the Kutaisi refinery). The debrief says "the intercept" instead of "the patrol over the fleet". The carrier raid keeps its fleet text.

## v0.41.393, a Fighter Sweep you fly no longer fails to load in the Mission Editor
A sweep route with no marshal point put the PUSH time-lock straight after the locked takeoff, which the Mission Editor refuses. The PUSH speed is now left free. Waypoints, altitudes, speeds and times are unchanged. The smoke test now checks the waypoint locks on one mission of every kind of package, as your own flight and as the all-AI test.

## v0.41.392, a CAP mission no longer fails to load in the Mission Editor
A CAP or Fighter Sweep flight you fly could be refused by the Mission Editor ("All waypoints (2-2) have locked speed and surrounded by waypoints 1 and 2 with locked time"). The CAP station point is no longer time-locked, like the escort and sweep stations. Your waypoints, altitudes, speeds and times are unchanged.

## v0.41.391, S38: the SEAD stays on station while the strikers go in
In a STRIKE or CAS package the AI SEAD flight now times its HARM point to 90 seconds before the strikers' time over target (it used to arrive about 5 minutes ahead, find every radar switched off, and leave before the SAMs came up). It holds at the HARM point until the last striker's time over target plus 2 minutes, then goes home. Your own flights and DEAD packages are unchanged.

## v0.41.390, S37: red raids with a share of its free bombers each turn, not on a dice roll
Red no longer rolls one chance of a raid a turn. Each turn it earns raid credit equal to a share of its free attack jets (Su-24M, Su-25, Tu-22M3; half as much at night, more while you stand down) and builds raids while the credit lasts, up to four a turn, carrying the rest to the next turn. A strong red now raids turn after turn and a worn-down one less. At Level 3 red builds about 3.9 raids a day (before: 2.2), most of them on supply sites and fields; Level 1 stays at about 0.1 a day and Level 2 goes to about 0.5 (before: 0.35).

## v0.41.389, S35: red's bombers now raid your fields at Levels 2 and 3
A red bomber wing is now sent against an airfield when it can field a smaller raid and its SEAD groups together, instead of only when it could field the largest raid. The raid shrinks by pairs to fit the wing's free jets (never under the level's minimum). At Level 3 red now builds about 0.7 to 1.0 field raids a day (before: 0.3 to 0.4), with 6 to 8 bombers instead of 8. Level 1, Tu-22M3 strikes and raids on covered supply sites are unchanged.

## v0.41.388, S31a2: AI A-10 CAS flights carry guided bombs under the high floor
An AI A-10C CAS flight that now attacks from 24,000 or 12,000 ft (short-range air defence near the target) loads two GBU-31 JDAM, two GBU-54 laser JDAM and two CBU-103 wind-corrected cluster bombs instead of Mavericks and unguided cluster bombs. With no air defence near, the loadout is unchanged. Your own flight keeps its loadout.

## v0.41.387, S31a: AI CAS flights fly above short-range air defence
An AI CAS flight whose target or run-in lies within reach (plus 3 nm) of a live Tor, Osa or Tunguska now attacks from 24,000 ft, and from 12,000 ft when only guns or shoulder-fired missiles are near, instead of 9,000 ft or LOW. The attack order is given that height too. The kneeboard says why. Your own flight's route is unchanged.

## v0.41.386, S30: stand-off strike missiles go only at their target
The AI F/A-18C SLAM-ER flight of a Standoff Strike now fires with rules of engagement "Open Fire" (designated target only) instead of "Weapon Free", so its missiles stop picking radiating radars of opportunity on the way and go at the package's target.

## v0.41.385, S33: AI fighters fly home high over short-range air defence
An AI TARCAP, escort, sweep or fleet-defence flight whose way home passes a live Tor, Osa, Tunguska, gun or MANPAD site now stays above that system's ceiling (plus 4,000 ft) until it has passed it, and only then descends to its recovery point. Your own flight's route is unchanged.

## v0.41.384, S29: the blue CAS task force starts on land
The friendly task force and its JTAC, and the red column a CAS package moves, no longer start or stop in the sea. Their start, stop and patrol points now move onto land (150 m from the coast), and a garrison's task force picks another approach bearing if its straight leg would cross water.

## v0.41.383, S32: the ILS dummy is a small aircraft on the ramp
The aircraft that keeps each blue field's ILS runway active is now a small Christen Eagle parked on the ramp, far from the runway, instead of an F-16 beside the threshold. The ILS dummy setting is just On or Off (Beside and On are gone; an old Beside reads as On).

## v0.41.382, S28: low-level strikers descend late
AI low-level strikers whose approach point is close to the target used to drop to treetop height right after the push and fly the whole long leg at 150 m, burning most of their fuel before the target. They now cruise high and start the descent 30 nm before the approach point.

## v0.41.381, S27: runway strikers start their attack on the way in
AI runway-cratering flights now begin the runway bombing task on the approach point before the field, as other AI strikes do, instead of on the field itself, where they used to turn away short of it without dropping.

## v0.41.380, S26: red raid groups no longer collide at spawn
Red raid groups that waited together on one marshal point used to share one altitude and collided in the first seconds, taking out most of a raid before it flew. Each group now holds its own level, and the SEAD flights sit above the bombers.

## v0.41.379, S25: four-hour turns
A turn is now four hours (six a day, a night is three turns; it was two hours and twelve). Each turn offers about twice the packages and patrols, so the flights per day stay about nine tenths of before; refit is 2 hours for the standard jets (8 for the Tu-22M3 and E-3). Crew Rest goes in steps of four hours. Campaigns saved with two-hour turns will NOT open (a new campaign is needed).

## v0.41.378, S24: supply sites at 70%
New campaigns lay about 30% fewer supply sites (road_sites 42 / 70 / 70, was 60 / 100 / 100), so each supply strike moves the Force Index more; the war sim's own strikes bite harder too. Old saves keep their stored count.

## Tools, 2026-11-11 (no version change): the soak is part of the smoke test
The soak (three campaigns skipped to the end of the war, with fake sorties and save/reopen) now runs in the default smoke test instead of only on request. Tools only. XO runs the smoke test (about 70 s in all).

## v0.41.377, S23: Auto-Skip in the sidebar, Crew Rest after a sortie
The Auto-Skip options (Stand-Down Turns, Night Turns, Crew Rest) now sit in a box in the sidebar, seen on every page; Skip Turn stands alone again. Crew Rest replaces Duration: after a flown sortie the run skips until the hours are up, flights on offer or not, and the three options add up. One report per run, the night after a sortie included. Skip Turn itself never starts a crew rest.

## v0.41.376, S10: supply sites laid out in rows, the guard outside
A depot's warehouses now stand in a row with the ammunition bunkers dispersed 170 to 280 m out; a fuel farm is a row of tanks with the store at one end; refineries and factories are one row. The red guard group stands just outside the buildings, on the side of the nearest blue airfield.

## Docs, 2026-11-11 (no version change): CHANGES.md slimmed (S11)
This file now holds one short entry per version (what changed for the player or the war, flown or not). The full detail (constants, probes, file and line notes) moved to a file outside Git. Docs only.

## Tools, 2026-11-11 (no version change): smoke test soak (S12), skip to the end of the war
New opt-in smoke group `--only soak`: campaigns at all three levels are skipped to the end of the war with fake sorties and save/reopen along the way; the only check is no exception. Tools only, not in the default run. XO runs it (about 3 to 5 minutes).

## Tools, 2026-11-11 (no version change): smoke test Phase 3, the two missing checks
Two missing checks added to the smoke test: the main window builds and shows every page, and every stored package carries its required flight. Tools only. XO runs the smoke test.

## v0.41.375, S20 Phase 5: the belt that guards a northern runway ranks first in the mountain wave
A SAM belt that guards a northern runway now ranks first in the mountain wave of SAM jobs. It only reorders the wave; quotas and jets are unchanged.

## v0.41.374, S22: the air wings tables show the number of jets
The air wings tables show the jets on hand (including those refitting) against the authorized number, for your coalition and for red. Display only.

## v0.41.373, S21 follow-up: the after-action report is a plain list
The after-action report is a plain list shown all at once from the top: no animation, no blank gaps.

## v0.41.372, S21: Skip Turn layout and the after-action report
Skip Turn no longer shows a ticker; every skip ends in one after-action report that lists each turn in order.

## v0.41.371, S20 Phase 3: the depth tiers are gone
Depth tiers are gone: every job type is offered from day 1, gated only by the SAM belt rule, and the front no longer advances.

## v0.41.370, S13: the theatre-level background is gone
The theatre-level background text is removed (it was never shown); each level keeps its own story.

## v0.41.369, S19: one fixed safe AWACS station and its guard every turn
The AWACS sits at one fixed safe station behind the support field every turn, with its guard flight, instead of following the player.

## v0.41.368, S17: storms no longer scrub every package
Storms no longer scrub every package. Fog and low minimums still do; otherwise flights swap to GPS weapons and only a flight with nothing it can use scrubs.

## v0.41.367, S20 Phase 2: two-front SAM / EWR / runway waves
The planner adds a wave of SAM, EWR and runway-crater jobs on top of each turn's jobs, split between the sea front and the mountain front by level, ranked by nearness to blue's fields.

## v0.41.366, S18: drop the "Allow night sorties" field
The "Allow night sorties" checkbox is removed from New Campaign; night turns always plan and the Autoskip "Nighttime Sorties" box is the way past them.

## v0.41.365, campaign rules Phase 11: Autoskip UI
Autoskip under Skip Turn: stand-down days, nighttime sorties and a duration (2 to 24 hours) can be set; the skip steps turn by turn and stops on an available flight or the war's end.

## v0.41.364, attack fix Stage C: AI CAS attack tasks on the IP
AI CAS flights carry their attack tasks on the IP before the target point, so they engage a column they pass instead of only when overhead. Player flights unchanged.

## v0.41.363, attack fix Stage B1: pop the hold, stretch the attack stops
A held AI strike or CAS flight is released cleanly and its attack tasks run longer, so a long gate hold cannot expire them. A dev switch forces a 60 s hold for testing.

## v0.41.362, attack fix Stage A: wider SLAM-ER and JSOW launch windows
Wider SLAM-ER and JSOW launch windows (90 and 120 s up to 240 s), so a stand-off jet that leaves the marshal late still launches.

## v0.41.361, campaign rules Phase 10d: Level 3 red flies the Su-34
New Level 3 campaigns give red the Su-34 in place of the Su-24M for raids and SEAD / DEAD groups. Levels 1 and 2 and old saves unchanged.

## v0.41.360, campaign rules Phase 10c part 2: the A-10C flies clean supply strikes
The A-10C gets a clean STRIKE load, used only on plain supply strikes no live SAM ring or red fighter covers. Common at Level 1, rare at Levels 2 and 3.

## v0.41.359, campaign rules Phase 10c part 1: more Su-25s, Su-25 supply raids, L1 sponsor fighters
More red Su-25s (60 at L2, 130 at L3), Su-25 supply raids, and a Level 1 red with 24 relic fighters. New campaigns only.

## v0.41.358, the F-15E phase: two AI-only strike squadrons
Two AI-only F-15E strike squadrons (Vaziani and Tbilisi) replace two F-15C squadrons in new campaigns. Old saves unchanged.

## v0.41.357, campaign rules Phase 10b part 2: the flown carrier raid reads the prep's result
A flown carrier raid reads the prep's result: destroyed SAM sites are gone, suppressed ones blind, the rest live. Saves with no prep record keep the old behaviour.

## v0.41.356, campaign rules Phase 10b part 1: the carrier raid's SEAD prep goes in the turn before
The carrier raid's SEAD prep is planned in the turn before the raid, so you can fly both; the war sim reads the prep's sites.

## v0.41.355, campaign rules Phase 10a: the Mozdok wing gets work
The Mozdok Su-27 wing flies red's normal jobs, and a new Tu-22M3 land strike hits blue supply sites.

## v0.41.354, campaign rules Phase 9b part 2: Mineralnye Vody is a red field
Mineralnye Vody becomes a red airfield with an air wing, SAMs and an EWR at L2 and L3. Old saves untouched.

## v0.41.353, campaign rules Phase 9b part 1: the blue laydown
New campaigns start with 272 blue jets in 17 squadrons at every level; Vaziani and Tbilisi base squadrons and Batumi holds a HAVCAP F-15C squadron. Old saves keep their squadrons.

## v0.41.352, campaign rules Phase 9a: Kobuleti zone, divert fields, three-base defeat
Vaziani, Tbilisi and Soganlug become blue divert fields, Kobuleti a third fall point, and defeat is three fallen airfields (a sunk carrier no longer counts).

## v0.41.351, raids fold into flown missions (queue S8)
A land raid's intercept package now merges into a flown mission whose area holds its target; an unseen raid is built in but never named. The mission settles it.

## v0.41.350, support CAP legs (queue S9)
Longer race-track legs for the support CAPs where the ground is clear, and a forward tanker's CAP runs along the tanker's track.

## v0.41.349, campaign rules Phase 8: CAP1 and CAP2 on the TARCAP, escort and sweep station
The blue TARCAP, escort and sweep station is flown as a CAP1 / CAP2 race-track.

## v0.41.348, campaign rules Phase 7b: blue detection by AWACS and the AWACS loss
Blue detects red raids through its AWACS; a raid with no AWACS up may go unseen and is then not listed. An optional switch lets AWACS be lost (off by default).

## v0.41.347, EWR Strike priority
An EWR Strike now scores by how much of red's picture the radar covers, so key EWRs are hit sooner.

## v0.41.346, campaign rules Phase 7a: red detection by EWR and the EWR Strike job
Red detection by EWR: a target outside EWR cover may be answered by barcap only (no alert or reactive pairs), and a new EWR Strike job hunts live radars.

## v0.41.345, scaled tasking Phases B and C: packages from free pairs, front spread, raids from red's free attack pairs
Blue's packages per turn come from its free pairs and spread across the front sectors; red's raid rate follows its free attack pairs.

## v0.41.344, campaign rules Phase 6b: the war sim spends the reaction hold
The war sim draws a red pair from the reaction hold against each package it resolves and may shoot down some of it; blue raid intercepts are crewed from blue's hold.

## v0.41.343, campaign rules Phase 6a: scrambles draw from the reaction hold
Red's alert, relief, standby and reactive pairs come out of its reaction hold, and a scramble that got airborne goes to refit.

## v0.41.342, fix: sams.transfer_days NameError
Fix: `sams.transfer_days` could crash at the end of a day (a missing import). No other change.

## v0.41.341, campaign rules Phase 5b: red's raids per turn
Red's raids are drawn every turn and booked from the turn's free red jets, which then go to refit. Fixes a raid-intercept crash. Expect fewer raids at L3.

## v0.41.340, campaign rules Phase 5a: red plans per turn, the reaction reserve
Red plans its patrols and sweeps every turn from its ready fighters, both sides hold a 25 percent reaction reserve, and every red pair planned goes to refit.

## v0.41.339, campaign rules Phase 4b: standing cover per turn
Support assets, standing patrols and guards are planned per turn, AWACS and tankers have airframe clocks, and every planned patrol is committed to refit.

## v0.41.338, campaign rules Phase 4a: blue plans per turn, two launch waves
Blue plans every turn with two launch waves, package counts per turn, re-tasking holds and a three-turn SAM suppression. The daily planning is split into a day start and a turn plan.

## v0.41.337, campaign rules Phase 3: the 2-hour clock (Skip and Fly take one turn)
Every campaign flow goes through here.

## v0.41.336, campaign rules Phase 2b: ILS dummy aircraft, runway crater blasts, real regional wind
NOT TESTED IN DCS (the dummy, the blasts and the wind are all things only a DCS run can judge).

## v0.41.335, campaign rules Phase 2: Supplies is now Force Index (display only), and the land tankers are 8 KC-135 boom
Player-facing text where "Supply" meant a side's percentage now reads "Force Index": the Overview tab, its table header and note, the side cards (`FORCE INDEX | AIR DEFENSE`), and the briefing lines (`posture.supply_lines`).

## v0.41.334, campaign rules Phase 1: the refit clock, replacements, the runway queue, a new save format
The first step toward 2-hour turns: the clock itself arrives in Phase 3, so planning, Skip and the UI do not change yet.

## Tools, 2026-11-09 (no version change): smoke test Phase 2, rewritten to the fresh structure
Asserts check structure only (no constants, no `state.day` value, no waypoint, job or kit names, no game or hook text).

## Tools, 2026-11-09 (no version change): smoke test Phase 1, the doomed checks are deleted
Whole functions only; the survivors are unchanged.

## Build, 2026-11-09 (no version change): the release builds on Python 3.14
The `requirements-build.txt` comment and `docs/GUIDE.md` ("Python 3.13 or 3.14", was "3.12 or 3.13") follow.

## v0.41.333, no Counter-Air strike and no Standoff Counter-Air any more
The Fighter Sweep, also a COUNTER_AIR objective, is untouched.

## Rules, 2026-11-06 (CLAUDE.md only, no version change)
Crew Chief edits but does not run the smoke test; XO runs it before a release.

## v0.41.332, the hook logs where every bomb ended
The Lua hook now follows every bomb (category BOMB) to its last position plus a quarter second of its velocity and writes `imp` in `SQE_state.json`: `{t, w (type), by (shooter), x, y (height), z, g (ground height)}`, at most 80.

## v0.41.331, the ramp strike aims at the parked jet nearest the middle; the job text loses the count
After v0.41.329 the aim was exactly the middle of the nine parked jets, an empty spot between them; the run showed no jet destroyed (cause unknown: the hook does not follow CBU impacts).

## v0.41.330, the counter-air job text says "serviceable", not a parked count
The job text read "(N aircraft at the field)" with N the red wing's serviceable total (`w.available`), which is not what stands on the ramp (at most `PARKED_MAX` 8 in the mission).

## v0.41.329, the ramp strike is re-aimed at the real jets once they spawn
The strike flights are built before `_spawn_parked_jets`, so their counter-air Bombing tasks were made on an estimate (v0.41.328: the ramp slots' middle).

## v0.41.328, the ramp strike aims at the real ramp (the aim fell back to the airfield point)
The .miz showed the Bombing task 1.2 km short of the parked jets.

## v0.41.327, the Standoff Counter-Air JSOWs use Open Fire too
Same reasoning and same risk as v0.41.325: if DCS does not treat the Bombing points as designated, nothing is released; revert that one ROE line.

## v0.41.326, the ramp pass runs along the line of parked jets
The counter-air bomb task keeps its aim point (the ramp centre) and now also carries an attack heading: the bearing between the two parked jets furthest apart, when that line is longer than `RAMP_AXIS_MIN_M` 150 m (judgment call).

## v0.41.325, ramp strikers attack the designated point only (no hunting)
In his run one CBU jet dropped on the ramp, the other on the ammo depot, then both spent the rest on the depot.

## v0.41.324, the parked jets are real, untasked aircraft (v0.41.318's static watch is removed)
The ramp strike's result showed 0 parked jets counted (the debrief had only the 4 scrambled jets), and a destroyed static gives the hook no name to count.

## v0.41.323, the counter-air strikers bomb the ramp centre with the plain bomb task
Read: the carpet task (v0.41.316) was on the IP with the right aim point (the ramp, 800 m long), but the CBU-103 jets never crossed the ramp: they looped 6 to 20 km west and north of the field for about 3 minutes and dropped on the Shilka guards of `depot_nalchik`, about 13 km from the aim point ...

## v0.41.322, the AI striker's bomb task moves from the target to the IP
Read from his runs: the F-16s with GBU-31 / CBU-103 flew the whole route and crossed the target 2 km off at 6,100 m and about 530 kt, with the state's bomb count unchanged.

## v0.41.321, the bomb-push and ammo-log attempts are taken out
The JDAM no-release is still OPEN, cause unknown (queue item 18).

## v0.41.318, the debrief sees the parked jets die
Every 5 s from t=20 s the hook asks `StaticObject.getByName` for each: gone means dead, written to the `dead` table (and a `static_dead` entry in `deaths`) under its own name.

## v0.41.317, guided-bomb strikers are left alone; the AWACS watch includes the all-AI flight
Public sources: JDAM is released by the aircraft inside its own launch acceptable region ("up to approximately 15 miles", launch "from very low to very high altitude", GlobalSecurity); the CBU-103 is a CBU-87 with an INS/GPS wind-correction kit, no wings, medium to high altitude delivery (Wikipedia ...

## v0.41.316, counter-air strikers carpet-bomb the ramp
Cluster bombs are not aimed at single things, and the CBU-103 is a wind-corrected dispenser that the AI may treat like a JDAM (the release behaviour in DCS is unverified).

## v0.41.315, cover stays while the strikers sit at a gate
Cost of a wrong guess: cover flights in gated packages stay up to 12 to 15 min longer even when the strikers never hold (fuel).

## v0.41.314, sweep and escort: the hunt starts near the station, not at takeoff
Cause, from the run's mission and state file: the sweep flight's engage task (air targets within 40 nm of the target) was live from the spawn point, so Venom 1 ran down the Su-27s at about 880 kt from 250 km out (plan: 540 kt), killed all four by t=1000, and went home (most likely bingo fuel; the ...

## v0.41.313, counter-air strikes: the strike pair is required, CBU-103s on a quiet ramp, JSOW-As under air cover
The pure Fighter Sweep job has its own slots (`is_sweep`).

## v0.41.312, the AI JDAM strikers break to the side after the release point
The jet flew a U-turn about 10 km short of the release point and went home (first run to fly that shape; the SLAM-ER Hornet in the earlier run cut the same corner 7.5 km short and still fired, its reach is 130 nm).

## v0.41.311, the Missions list keeps your pick when you press FLY
Not seen in the real UI; the smoke test cannot see layout, compile check only.

## Housekeeping, the 72 tracked `.pyc` files are untracked (no version bump)
No `.gitignore` is added (XO keeps his own); XO's local ignore will keep them out.

## v0.41.310, the wind blows down the ILS runways
DCS picks the active runway by wind, so a wind from the wrong side puts the ILS on the departure end.

## v0.41.309, the Standoff Strike's SLAM-ERs aim at the site's buildings, one each
From his 12:31 run: the SLAM waypoint had weapons free and ONE Bombing task on the site's centre point; of four AGM-84H one hit the guard vehicles (Shilka, Strela) at the target and the other three went at the Sukhumi and Gudauta EWRs and an S-300 search radar (t=746 to 757), so the depot stood.

## v0.41.308, the counter-air text names the ramp (PR 2 of the parked jets)
The job reads "Counter-air at <field>: strike the jets on the ramp (N aircraft at the field)" (it said only "N aircraft"), and the briefing's target line of a counter-air strike (not the sweep) ends with the jets parked in THIS mission ("N aircraft stand parked on the ramp." or "No aircraft are ...

## v0.41.307, the dead dice code is gone (cleanup S3)
Since v0.41.304 red's planned raids are listed packages and nothing rolls an emergency any more; this removes the machinery that was left.

## v0.41.306, uniform Title Case job names
The raid jobs keep "<What> Defense: Intercept" and "Fleet Defense: SEAD / Standoff DEAD".

## v0.41.305, the fleet raid's SEAD / Standoff DEAD are their own packages ahead of it
Needs a NEW campaign day (a stored plan keeps its packages).

## v0.41.304, no more dice: red's planned raids are listed (red border), with plain names
PR B of the planned-scramble work; needs a NEW campaign (a stored day plan keeps its old packages).

## v0.41.303, raids on fields, supply sites and garrisons are player-flyable
PR A of the planned-scramble work (his decisions: red's planned raids become scrambles, no more dice; plan in `claude/sqe-queue.md` item S).

## v0.41.302, the Standoff Strike's SLAM-ER launch point asks for a cruise missile
Hornet 1 (the AI flew the player's seat) had full fuel and both AGM-84H, climbed to 30,000 ft at 500 kt as planned, passed 5.9 nm from the SLAM launch point at t=750 and fired nothing (no shot in the state file), then dropped to 5,000 ft and flew home.

## v0.41.301, the fleet-defence fight moves 25 nm further out
The fight sat 190 to 193 nm from the carrier (Tomcats fired from about 118 nm).

## v0.41.300, the scramble choice offers only the flight you clicked in your own package
No flight clicked (`flight_id` None): all you could fly, as before.

## v0.41.299, AI JDAM strikers release short of the target; the Standoff Strike builder (PR 2 of 2)
One commit: the two parts share the release-point code.

## v0.41.298, Standoff Strike: a supply strike under heavy fighter cover goes out as SLAM-ER Hornets (PR 1 of 2, the planner)
His point: "it's mostly jets that trouble our strikes" at L3.

## v0.41.297, a counter-air strike finds the field's jets parked on the ramp (PR 1 of 2)
His run: a counter-air strike on Sukhumi had nothing to hit (the target point was the garrison at the field's reference point; red jets exist in a mission only as flights that launch).

## v0.41.296, the fleet raid flies a formation: escorts ahead, bomber groups in a loose echelon
Fleet raid (edge-spawn setpiece) only; land raids and staged raids unchanged.

## v0.41.295, the buildings of a supply site no longer overlap
In his miz the three buildings stood 30 to 38 m apart, each on a ring of 18 to 30 m round the block's centre (`ROAD_BLOCK_M` 40 cap).

## v0.41.294, the scramble choice is a tall page like the Missions pane, with a FLY button on every flight of both packages
The scramble block is in a red frame, titled "SCRAMBLE:", with the emergency text; when your squadron cannot take it the reason shows and its buttons are greyed out.

## v0.41.293, the carrier raid's battle moves in another 50 nm; the raid SEAD seats are AI-only
In XO's v0.41.291 run the bombers died at 227 to 246 nm from the carrier, not at the 170 nm point: the F-14s fired their first Phoenixes at t=789 s from about 158 nm (still dashing) at Tu-22s 79 nm beyond, so the fight sits about 62 nm past the point.

## v0.41.292, the scramble has its own time and is offered on one package
Engine only; the scramble dialog redesign is the next PR.

## v0.41.291, the carrier-defence setpiece spawns every live red SAM site
It adds every live SAM site in the campaign (`AssetKind.SAM`, not destroyed, including the short-range SA-15/19/8 and field SAMs) to the sites whose ring touches the bombers' route.

## v0.41.290, the interceptors' dash no longer waits on a SEAD job
The intercept point worked out a few lines earlier was thrown away with it, so no interceptor got the dash and all of them held the carrier station 56 to 80 nm out, over the water, while the Tu-22M3s flew past 140 nm away.

## v0.41.289, the carrier raid's battle moves in to about 170 nm
Before, they picked the furthest point out from the route's outer point `w1` (220 nm).

## v0.41.288, the emergency/scramble choice is now its own dialog, not a QMessageBox
New `gui/dialogs.ScrambleChoiceDialog`, replacing `MainWindow._emergency_popup`.

## v0.41.287, every SAM threatening the carrier raid's intercept line gets its own SEAD/DEAD flight
New `threatmap.raid_inbound_sites`: every live, unsuppressed red SAM whose reach (`raid_avoid_nm`, the same `AVOID_NM` figures the lane-avoidance already uses, SA-11 bumped) touches the bombers' straight way in (target out to `w1`, 220 nm on the raid's bearing).

## Docs only: any Sonnet or any Opus version OK for builds (XO 2026-11-04)
Any Opus version is also fine.

## Docs only: builds allowed on any Opus version
The model rule in `CLAUDE.md` now reads "Sonnet 5.5 or higher, or any Opus version", in the standing rules and in the session-start model check.

## v0.41.286, more fields red in every mission; the raid CAP dashes at 500 kt
New theatre key `red_extra_airports` (Caucasus: Mineralnye Vody, Krasnodar-Center, Krasnodar-Pashkovsky, Anapa-Vityazevo, Novorossiysk): set red in every mission, no campaign asset, no new campaign needed.

## v0.41.285, every red SAM along the carrier raid's way in is live; the unit limit trims the furthest from the intercept point
The sites the raid SEAD goes for are built before and are never trimmed.

## v0.41.284, you can fly the raid SEAD: your route goes to a raid site; red's timer is 5 minutes
Before this the SEAD slot of the carrier raid could be picked, but a player SEAD flight flew a route to the package's own point, not a site.

## v0.41.283, the raid SEAD is already done when you fly the Tomcat (or any non-SEAD jet)
In the carrier raid setpiece, when the player does not fly the raid SEAD flight (`MissionBuilder._raid_scripted`): the SEAD flights are placed already past their HARM time (`RAID_SEAD_DONE_S` 150 s before the start), so they are homebound at second 0; the blocking sites' tracking radars and half of ...

## v0.41.282, the carrier raid is a scripted setpiece; red fields are red in every mission
The fleet raid's bombers and escorts no longer taxi, queue, assemble or gate.

## v0.41.281, a raid on a field is "raid defense", not "fleet defense"
New `Package.kind`: a raid intercept on a field, supply site or garrison (`extra["land"]`) reads RAID_DEFENSE; only the carrier raid keeps FLEET_DEFENSE.

## v0.41.280, the interceptors are timed to the raid
The raid's push time is now worked out BEFORE the interceptors are built (`raid_spawns._raid_clock_prep`: marshal, lane, launch point and assembly plan, no build; it draws the arrival jitter, and `_spawn_raid` uses that same number).

## v0.41.279, the fleet raid's bearing is random again (v0.41.275 undone)
Mozdok is about 213 nm from the carrier and the X-22 reaches 208 nm, so on that straight line only 30 to 50 nm of way in lay outside the missile ring, the SAM circles covered it, and no intercept point existed: the F-14s fell back to the old station shape and the F-15s and F-18s got no lane.

## v0.41.278, the interceptors launch before the mission starts; red takes longer to assemble
A player's flight is not moved (the player still leaves at the planned departure; an earlier takeoff is fine). 0 puts them back at their field.

## v0.41.277, the fleet raid starts hot on the ramp and waits for everybody
The plan adds `RAID_TAXI_S = 300` to the time it takes a batch to reach the marshal (judgment call; v0.40.10 measured 3 to 11 minutes for alert pairs).

## v0.41.276, the fleet-defence interceptors have no hold
They leave at the start, fly the SAM-bending lane (direct or bent over a blue field) at the dash speed and wait on the intercept point; their engage circle round it is on from the start (it was swapped in by the DASH flag).

## v0.41.275, the fleet raid arrives on the bearing of its own field
The bearing is now the one from the carrier to the bombers' field, plus or minus 10 degrees (the jitter is a judgment call).

## v0.41.274, the fleet raid starts with one bomber pair and four escorts airborne
Everything else takes off from the field: the remaining bomber pairs first, the rest of the escorts and sweeps last.

## v0.41.273, supply strikes outrank ordinary DEAD jobs in the daily plan
Side effect: strikes on other targets (runway strikes among them) drop (L3 10.3 to 3.9) because the strike type has a cap of 3 a day.

## v0.41.272, the one-scramble-per-sortie cap is off (a test)
A raid scramble can now be offered on every Fly click, not only when the last sortie had none (the quiet day before the carrier raid still blocks them).

## v0.41.271, the fleet-defence Tomcats carry 6 Phoenix
New `FLEET` loadout for the F-14BU in `loadouts.py`: the 4 belly AIM-54C of the heavy CAP preset, a shoulder AIM-54C on each side (stations 2 and 9, the `SHOULDER AIM_54C_Mk47 L` / `R` CLSIDs, both in pydcs) in place of the two Sparrows, 2 AIM-9M, 2 tanks.

## v0.41.270, the carrier raid folds into no mission
The fold-in block of v0.41.250 is out of `engine.merge_candidates`; the small bomber raids and every other package merge as before.

## v0.41.269, red no longer borrows SAM batteries from its rear
A destroyed red site is rebuilt in place by `sams.rebuild` after `ORDER_DAYS` 14 (unchanged).

## v0.41.268, fleet defence: when no lane is clear, the interceptors go by way of a blue field
Bent lane (`raid_spawns._raid_bent`): where neither a straight lane nor the SEAD on the blockers gives the interceptors a SAM-free dash (`_raid_blockers`), the dash goes hold point -> a blue airfield (not inside a SAM circle) -> the intercept point, each leg bent round the SAM circles.

## v0.41.267, fleet defence: the dash limit was too short; the raid SEAD goes for the sites that block the lane
Tracing XO's run found the real reason the interceptors held: at Level 3 the bombers' way in starts 160 to 165 nm from the hold point and `RAID_IP_MAX_NM` was 160, so no dash point was ever in range (not SAMs).

## v0.41.266, fleet defence: the interceptors dash to a point on the bombers' way in; anti-radiation-missile names renamed
In XO's run the Tomcats' dash went to the point they already held (HOLD, PUSH and TGT on one coordinate), and the Hornets and Eagles had no dash at all.

## v0.41.265, the build-time trim of v0.41.264 is taken out again
A new campaign plans raids at the cap already, so it did nothing there.

## v0.41.264, a fleet raid planned before the size cap is trimmed when the mission is built
The raid's size is stored in the saved day plan (`state.plan`), so a plan made before #329 kept its 24.

## v0.41.263, staged raid: every group keeps its own altitude the whole way (two bombers collided)
The run's tracks: the groups orbited the marshal stacked one above the other (0.1 to 0.4 km apart sideways, 150 to 300 m apart in height), then each climbed to one common cruise level at its own push, so group 4 climbed up into group 2 in the same column.

## v0.41.262, squadron tables show "(refitting, N)" for both sides
"Reconstitution" is the doctrinal word, "refit" the plain one.

## v0.41.261, staged fleet raid: half the bombers already on the marshal, the rest take off in batches, no "shoot at ships" order at the start
All figures are judgment calls; XO: "We'll tune on the way." Doctrine point (CIMSEC, "Kamikazes: The Legacy of Soviet Naval Aviation, Pt. 2", medium firmness): a regiment took about 30 minutes to get airborne and assemble, then went in together.

## v0.41.260, smaller bomber raids: Level 3 raid of 16 from a wing of 24, Level 2 raid of 8
Raid size (`bombers.MAX_RAID`): Level 3 24 to 16, Level 2 12 to 8.

## v0.41.259, a supply site's buildings stand beside the road
Cosmetic: placement only, nothing in the saved campaign changes, so no new campaign is needed.

## Docs only: CLAUDE.md, the go word and "untuned"
The go word for a code change is "fox 3" (with an optional effort).

## v0.41.258, road supply sites belong to the side their road connects to
The front is a cut across the roads at the line of sectors.

## v0.41.257, the fleet can be sunk
All numbers are judgment calls (no public figure applies to a game carrier); tune on XO's runs.

## v0.41.256, carrier raid, round 2: USAF share, SAMs along the bomber route, SEAD rush, the interceptors' gate
USAF share: half of the fleet raid's optional CAP flights are land-based (`Slot.land`, `packages.SETPIECE_LAND_SHARE` 0.5): a land squadron fills them, long-range fighters (F-15C) first, whatever the lead's service.

## v0.41.255, carrier raid: the CAP leash, SEAD on the launch-point SAMs, escorts on the bombers' clock
No source for any figure below: all judgment calls.

## v0.41.254, runway cratering: a field with 3 bomb hits on its runway is closed for 2-5 days
The whole field closes (one runway closes it all; XO).

## v0.41.253, runway probe: raiders immortal, victims on hold-fire (tool only)
Compile check; the .miz was rebuilt and its groups read back.

## v0.41.252, approach aids for the five fields we can take (kneeboard data only)
A taken field's mission now prints its recovery row like the four home fields.

## v0.41.251, runway probe (queue idea: disable runways; tool only, no campaign change)
A start script logs `SQERWY` lines to dcs.log (events of the RWY- aircraft, and every 20 s their position, speed, in-air flag and distance from the field), so the log shows whether a cratered runway grounds AI, whether AI can land on it, and when it reopens (forum threads say about 60 minutes ...

## v0.41.250, the carrier raid folds into missions at its time; blue CAP sized to the raiders (queue item o, part 3)
Nothing folds into the raid itself; merging off folds nothing.

## v0.41.249, the carrier raid is the full raid: 24 bombers at L3, 12 at L2, one escort per two bombers (queue item o, part 2)
A SAFE raid is the full raid or none (it needs `full` bombers and their escorts; the stop estimate uses the full raid); a DESPERATE one still sends whatever it can field (at least 4).

## v0.41.248, the carrier raid launches from stand-off and turns home (queue item o, part 1)
Its last waypoint ("LAUNCH") is on the raid's bearing, `RAID_LAUNCH_OUT_NM` 20 beyond the blue CAP station and never closer than `RAID_LAUNCH_MIN_NM` 100 to the carrier; the bombers reach it when the scramble's CAP is on station, carry the attack task there (the whole group, expend ALL: XO wants ...

## v0.41.247, a taken field gets a NEW squadron, F-16C by default or the airframe the planner is short of (queue item h part 1, PR 3 of 3)
Type: F-16C by default; A-10C when at least `NEED_MIN` 6 CAS slots, or F-15C when 6 TARCAP / SWEEP slots, went unfilled within `NEED_RADIUS_NM` 150 nm of the field over the last week.

## v0.41.246, the first squadron moves into a taken field; the player's squadron rests like any other (queue item h part 1, PR 2 of 3)
It keeps its name, counts as the field's squadron, remembers its home (`home_id`), sits out its move nights, and needs parking for its jets at the new field (tried again every night if not).

## v0.41.245, the map draws blue's supply sites and garrisons
The map window drew red assets only, so blue's depots, fuel points, road sites, refineries, factories and garrisons (58 on a fresh L3 campaign) never showed.

## v0.41.244, a field we take becomes a blue base with staged air defences (queue item h part 1, PR 1 of 3)
Before: a red field we took stayed a dead red asset and nothing ever filled it.

## v0.41.243, squadrons rest after a base-fall withdrawal and fly home on a retake (queue items h and h2)
Before: a squadron driven off a fallen field was flying again the next morning, and on a retake nobody went back.

## v0.41.242, L3 bomber raid can fire (queue item o, step 1)
A 30-day L3 sim on seeds 7, 8 and 9 held the wing all 90 days: red's estimate of blue stopping the raid sits at 0.25 to 0.28 (blue's carrier fighters always saturate the 8-jet cap), the safe window needed 0.12 or less, and the desperate test (score 1.0) never came.

## v0.41.241, supply sites along the roads, both sides (queue item i)
A NEW campaign now draws road supply sites from the 447 spots of the road net (v0.41.239): 60 at Level 1, 100 at Levels 2 and 3 (`Difficulty.road_sites`, one number per level), 65% red and 35% blue (judgment call).

## Docs only: CLAUDE.md smoke checkpoints
Adds when to run the smoke test (checkpoints only; targeted section plus a compile check for small changes; the compile check for any `.py` change, after the #297 tooltip slip).

## v0.41.240, red raids: bombers, sweep and escorts fly the clock instead of waiting at the gate (queue item n)
Now only the DEAD package (KAB-500Kr jets, `ex["dead"]`) waits at the gate; `_raid_gate_new` is built only for a raid with a DEAD package, and the bombers, `Raid Sweep` and `Raid Escort` groups are no longer gated (`build_group(gated=...)` unused by them; no `raid_gate_s` in their manifest, so the ...

## v0.41.239, the Caucasus road net: 69 routes and 447 road supply spots (queue item m, step 2 data)
Nothing in a campaign reads the new key yet: item i (quotas, defenders, which side owns a spot, ammo near bases, the #280 rule) is next.

## v0.41.238, road-net scan and road supply spots (queue item m, step 2)
Data side only: no campaign reads the new spots yet (that is item i).

## v0.41.237, road-path probe (queue item m, step 1)
A start script calls `land.findPathOnRoads` ('roads' and 'railroads') for 20 airfield pairs (short, medium, long, both coasts, the north side, the mountain gap, plus XO's Senaki-Vaziani / Tbilisi / Mineralnye Vody roads) and logs one `SQEROAD` line per call to dcs.log: point count, path length ...

## v0.41.236, a pulled-back SAM spends a travel day and cannot regenerate on it
Regen itself is rule-based (`sam_repair` 3 / 6 / 8% a night by level), unchanged.

## v0.41.235, strikers and CAS wait 15 minutes at the fighters-clear gate
Why: XO's runs showed packages barely waiting (6 and 4 min) while the air fight takes longer on every level, L1 included; he also overrides the old rule that CAS waits less because the troops are waiting.

## v0.41.234, smoke check_103: the F-15C hook no longer mentions the engine shutdown event
It now asserts the opposite (the text must NOT contain it).

## v0.41.233, fix: unescaped quotes in the ECM tooltip stopped the app starting
Cause on my side: the smoke run was skipped for #297 and nothing compiled the GUI.

## Docs only: CLAUDE.md smoke convention and learnings
Adds the smoke convention (tactical tunables are not smoked, strategic structure is) and a short learnings list to `CLAUDE.md`.

## v0.41.232, FC3 ECM: "Cockpit: ECM On / Off" messages; engine events unwired
The Settings tooltip is updated; the F-16C lamp message is unchanged.

## v0.41.231, ECM export script: the probe is removed
His F-15C flight with the v0.41.230 probe showed that `LoGetTWSInfo` (the RWR table) holds only `Mode` (0 all flight) and the other radars as `Emitters`; nothing in it followed six ECM presses (the probe rounded Power and Azimuth to whole numbers, but `Mode` is an integer and stayed 0).

## v0.41.230, ECM probes cleaned up; the Export probe now watches only the RWR table (LoGetTWSInfo)
His F-15C logs closed every route: `ECM_on`, the MCP flags, `LoGetActivityLevel` (missing), `list_indication(0)` (no ECM text), `GetDevice(0)` (nil), the external arguments and `list_cockpit_params` (212 flight-sensor names, no ECM or power entry; the watcher also merged the 134 ...

## v0.41.229, ECM probe: drop the ruled-out checks, dump and watch the F-15C's list_cockpit_params
His F-15C log of v0.41.228 answered the checks: `LoGetActivityLevel` is missing (the web snippet was wrong), `list_indication(0)` has no ECM text (315 characters of empty display slots), `GetDevice(0)` is nil.

## v0.41.228, ECM probe: does LoGetActivityLevel / list_indication / GetDevice(0) exist for the F-15C?
A web search gave XO a snippet that reads the F-15C's ECM from `LoGetActivityLevel()[104]` or from the text of `list_indication(0)`.

## v0.41.227, FC3 jets: "SQE ECM Switch" plus a "SQE ECM OFF" re-sync command
His F-15C probe log (v0.41.226) found no readable ECM or power state: LoGetSightingSystemInfo.ECM_on never moved, the failure flags never changed, no draw argument followed power.

## v0.41.226, FC3 ECM Switch: the item stays after a shutdown; the probe logs every event and samples the jet's external arguments
His dcs.log of the v0.41.225 test showed `S_EVENT_ENGINE_SHUTDOWN` firing for the F-15C but no startup line (the mission ended 57 s after the shutdown, so that proves little), and the build removed the menu item on shutdown and relied on a startup event to bring it back: if that event never comes ...

## v0.41.225, FC3 jets: one "ECM Switch" toggle; engine shutdown clears it; the player's events go to dcs.log
The F10 > Other ECM ON / ECM OFF pair is replaced by ONE "ECM Switch" that flips the jammer flag (starts off, the on-screen message still follows Settings > Experimental).

## v0.41.224, number boxes with their minus and plus buttons outside the field
At a display scale above 100% the up arrow of a Settings number box (the "60 s" Takeoff buffer) turned into a text cursor when clicked: Qt's own arrows sit inside the field and their click area drifts with scaling.

## v0.41.223, package scrub: the AI package goes home when it can no longer do its job; the AWACS calls ABORT
His run (Remarks): a 2-ship striker lost its leader, DCS sent the survivor home, but its escorts and TARCAPs went on to their stations.

## v0.41.222, blue's base air defences are always Excellent
Cause found in the code: under the default "level" Blue skill, blue's base Patriot / HAWK / AAA got no skill set, so pydcs left them at Average, while red's sites run at the level's skill (Good on L2, High on L3).

## v0.41.221, supply buildings count like wrecks toward the unit limit
A live static now counts `carcass_weight` of a unit, the same variable as a wreck (25% by default), so a 4-building site costs 1 unit; red's Shilka guard is still a whole unit.

## v0.41.220, a raid scramble builds the fields that cover the raid's target, and the sites round it
Cause, read from the code: a raid scramble built only the raided field plus the fields with flights in the package, though the war sim and the raid gate already count every field whose Patriot (40 nm) or HAWK (25 nm) covers the target (`raids.covering_fields`); and the supply circle (merge radius ...

## Docs, 2026-10-31: CLAUDE.md branch rule
CLAUDE.md now says to recreate it from `main` without asking.

## v0.41.219, the ECM script installs itself; quarter-second lamp reads; support-CAP names; About tidy-up
The script moved from `tools/` to `sqe/data/` so the exe ships it.

## v0.41.218, no CAS against a garrison north of the mountains
A CAS mission at the Nalchik SA-6 site garrison put a friendly task force and its JTAC deep behind red's lines ("Tom Cruise at Nalchik").

## v0.41.217, fix: the hook's event handler could not see DMGL ("attempt to index global 'DMGL'")
My bug: the damage-call tables (`DMGL`, `DMG_ON`, `AWUNIT`, `awdown`, `dmgCall`) were declared as locals far below the event handler that reads them, so the handler saw them as nil globals.

## v0.41.216, bold box headings on the Overview
SITUATION, THE FRONT, GROUND ODDS, COALITION, RUSSIA, TODAY'S TASKING, WARNINGS and THEATRE are bold (new `QLabel#head` style, same grey).

## v0.41.215, AWACS calls need a tuned radio; damage and mayday calls from the other aircraft
Two new top-level checkboxes in Settings > Experimental, both default ON, SQE-wide for now (refactor-day list).

## v0.41.214, the A-10C is CAS master again; strike / CAS flights hold 100 km out for the fighters-clear gate
AI-only sim (30 days x 3 seeds, player in an F-15C, AI's choice): L1 A-10C 28; L2 A-10C 162 / F/A-18C 23; L3 A-10C 175 (before, v0.41.189: L1 29/0/0, L2 60/67/19, L3 38/63/0 for A-10C / F-16C / F/A-18C).

## v0.41.213, "Show ECM status" setting
New checkbox Settings > Experimental > "Show ECM status", indented under the ECM script switch (greyed out while ECM script is off), default ON.

## v0.41.212, ECM: an on-screen message from the F-16C lamp
With the ECM script on and an F-16C player, the hook now shows "SQE sees your ECM lamp: on / off" the first time it reads the Export.lua flag file, then "ECM on" / "ECM off" whenever the lamp changes (checked every 2 s, message 6 s).

## v0.41.211, Overview readability: bar numbers outlined at the left edge, side cards top-aligned
Files: `sqe/gui/overview_view.py`, `sqe/gui/widgets.py`, `sqe/__init__.py`.

## v0.41.210, ECM hookup: your own jammer is read from the F-16C lamp, FC3 jets get F10 ECM ON / OFF
The F/A-18C (24), F-14B (2203) and A-10C (361) arguments are in the script but OFF until XO has flown them.

## v0.41.209, persistent objects: the carrier group is always in the mission, supply sites inside the merge radius are built
The carrier's scheduled CVCAP comes along whenever its window overlaps the sortie (`blue_barcap.attach` used to add it only when the package used the boat); a package that already brought its own carrier CAP gets no second one, and a day with no scheduled CVCAP in that window gets none (XO: the ...

## v0.41.208, UI pass 3: Tactical Edge Decay switch, plainer Tactical Edge text, scramble names, Russia's wings per airframe, a full skip result
Default OFF: the edge you build is kept; ON: it fades 3% a night as before (nothing fades on a stand-down night either way).

## v0.41.207, UI pass 2: the Overview restyle (coloured figures, bars, title case, notes fold away)
Colour cut-offs: supply red at 65% or less, amber 66 to 90, green above 90; every other 0 to 100 figure red under 40, amber 40 to 70, green above 70 (judgment call; the middle band is amber #E0A800).

## v0.41.206, UI pass 1: Help menu with About, Tactical Edge in its own tab, the terrain-scan UI is gone
The shore and river margins keep their saved values (no control).

## v0.41.205, the fighters-clear gate: no spend at spawn, watched on the way in, goes home instead of pushing
The distance trigger now waits until the lead is in the air and within `ARM_S` (240 s) of the gate's clock time, and after a clean check the flight is WATCHED until it is `WATCH_COMMIT_M` (25 km) from the target: red fighters that come up meanwhile hold it, once (`gs.watch`, `gs.rewatched`).

## v0.41.204, a dug-in garrison under one or two SA-11 / SA-10 sites goes in behind their SEAD (A-10s back earlier)
A garrison (a red SAM site's or field's ground guard) was never offered as CAS while any long-range site covered it (`ObjectivePlanner._garrison_cover`), so the A-10s waited for the site to be dead.

## v0.41.203, strikers wait for the air to clear (the fighters-clear gate); the bombing task drops the whole load
Radars down but fighters about: the AI flight holds outside (the same orbit hold as for radars), rechecks every 30 s (was 60), and goes in all the same after `acap` seconds, `AIR_HOLD_STRIKE_S` 240 for a strike, `AIR_HOLD_CAS_S` 150 for CAS (judgment calls: 240 is about what the Day-2 fight lasted ...

## v0.41.202, the shipped ground-height grid now comes from SRTM
Checked against XO's DCS scan, 97,500 cells: from E36 to E45.4 the average ground agrees to about 15 m on average (under 1% of cells in E36 to E44 are more than 150 m off); east of about E45.5 the DCS scan is empty (a flat 10 m, the edge of the DCS map) while SRTM has the real mountains, which is ...

## v0.41.201, the ground-height grid can be built from open SRTM data (tool); the Settings line names its source
Instead of shipping a grid made from DCS's own scan, the shipped grid can now be built from NASA / USGS SRTM (public domain) via the AWS open terrain tiles.

## v0.41.200, SQE ships its own ground-height grid
Measured against the 1 km grid on 300 random legs of 30 to 150 km (5 nm corridor): highest ground never lower, +38 ft on average, +361 ft at the 95th percentile (a leg over a narrow ridge gets flown a little higher, never lower), +1,083 ft worst; radar visibility share 0.02 different on average ...

## v0.41.199, the campaign draws its sites from the condensed site list; a transferred SAM needs a setup day
Step 2 of the terrain data condenser (step 1 is v0.41.198).

## v0.41.198, the terrain data condenser (step 1: the tool and the site list)
For each of the 13 sectors of the front chain it holds spots for ground units (on a scanned road point), SAM sites (off the road, flat ground) and supply (near a road, flat): 20 / 12 / 8 per sector (XO 2026-10-29, judgment call).

## v0.41.197, SAM transfers take 1 to 3 days again; an order from home takes two weeks; the SAM code names say what they do
The two weeks belong to the other path, the plain rebuild of a dead site, which is the order from home (the US for blue, the motherland for red).

## v0.41.196, SAM orders take two weeks; the replacement cost is built but priced at zero; "Pilot Influence" and "Air Tempo" become "Tactical Edge"
With a 1-week order and 1x debt red had a SAM on 53% of days. 2x and 3x debt were no better and pulled red's supply to 0.34-0.48.

## v0.41.195, JSOWs launch with the HARMs
His run: HARMs launched 545-682 s, JSOWs 752-904 s.

## v0.41.194, fighter stations keep 45 nm from a live SA-10
The station point was kept 35 nm out, but the racetrack's near end swings 5-9 nm closer.

## v0.41.193, CAS columns start out of gun range
Risk: a stall short of the meeting (6 km stalled on 10-28).

## v0.41.192, fuel farms and depots are buildings (both sides)
Fuel farm = three tanks and a store; depot = two warehouses and two ammo bunkers (pydcs `Warehouse` statics, the models blue's raid targets already used).

## v0.41.191, defensive pairs stay closer to their cover (both sides)
This shortens the chase, it does not end the long-range duel: the BARCAP circle (the leash) is still the cause of chases beyond cover, which is a bigger change not made here.

## v0.41.190, the CAS columns patrol first so they meet at the CAS TOT
In the F-16C CAS run (13:21) the T-80Bs fired at 362 s, the six Abrams were dead by 741 s and the Mavericks started at 841 s: both columns reached gun range about 8 minutes before the CAS flight (the red column crept from 30 s, the task force arrived at its stop point at about 5 minutes).

## v0.41.189, A-10Cs keep the quieter CAS jobs
Sim of #250 (30 days, 3 seeds a level): A-10Cs flew no CAS on L1 or L2 and only the overflow on L3, because "red fighters reach the target" (`n_fl` above 0) was true for almost every job.

## v0.41.188, Vipers and Hornets fly CAS (Mavericks), player-flyable
Planner (`packages._pick_squadron`): CAS goes to A-10C squadrons when no red fighter can reach the target (`n_fl` 0) and to jets when red fighters can (`CAS_JET_SWAY_NM` 400 is a soft preference, the other kind is still used when none is free).

## v0.41.187, road scan covers the ground-war sectors; supply sites reach roads as far as columns
Measured on nine new campaigns (L1 to L3, three seeds) against XO's road scan: after the snap 93% of columns and 100% of fuel farms were within 1.5 km of a road, but depots 91% (the 3 km limit left 9% out), and the columns and garrisons of the Gelendzhik - Sochi sectors were 45 to 54 km from the ...

## v0.41.186, front-line columns move onto roads up to 6 km away (older saves too)
Measured with XO's road scan (4101 points, 2 km grid) against the five CAS runs of that day: three had every column within 1.2 km of a scanned road, two (the kissing-distance runs) had them 3.4 to 5.2 km away, beyond the campaign's 3 km snap and the mission's 1.5 km snap, so the columns stayed in ...

## v0.41.185, TARCAP pull-back: it protects the package, it does not hunt
Risk: more bandits reach the package through the gap between the two circles.

## v0.41.184, ECM probe v2: air start, RWR / warning-panel / display logging, parser fix
Exercised against a stubbed DCS API (lupa); not in DCS.

## v0.41.183, ECM switch probe tools (tools only, no gameplay change)
NOT verified in DCS: these are the tools to find out.

## v0.41.182, Kneeboard page 1: the RECOVERY block moves to the bottom
At the top, with the task line under it in grey, the recovery data read as if the target belonged to it.

## v0.41.181, TARCAP holds back and chases less (CAS and strike)
All judgment calls; the cost may be a few more A-10s lost to bandits that reach them before the Eagles shoot.

## v0.41.180, CAS columns drive on roads
Both CAS columns were driven `OffRoad` in a straight line, so the blue task force cut cross-country through the forest and met red's column among trees (kissing distance, no fire).

## v0.41.179, The CAS task force stops 1.5 km short of the contact point
The 15:30 and 15:44 runs again ended with the blue task force and red's lead vehicles a few hundred metres apart in dense forest, neither side firing (the earlier run closed to 187 m).

## v0.41.178, Kneeboard RECOVERY block (ILS / TACAN / ICLS) and the BASECAP circle follows its orbit
The ILS is for the runway named; the other end has none.

## v0.41.177, CAS fighter cover stands within reach of the A-10s
A CAS TARCAP / escort under a covering SA-10 stood 35-40 nm from the A-10s (`profiles.station()` anchors to 0.85 x the SA-10's reach), out of engage range: Enfield 1 (4 F-15C) fired 3 AIM-9 and no AIM-120 in run 1 while red Su-27s killed the A-10s after TOT.

## v0.41.176, New Campaign: the Pilot Influence checkbox says only what it does
The checkbox still read "Pilot Influence: your sorties affect the war (you can lose it if you don't fly)": #238 fixed the Settings text and the tooltip but missed this label.

## v0.41.175, A fixed Tor site over a CAS target gets the HARM escort; the "behind the SEAD" wording and a briefing target line
Not counted: a Tor that travels with a column (`fsam_`, the A-10s' own job), strikes and the strike gate (`covering_sams` without `short` is unchanged).

## v0.41.174, The coalition's supply floor is 35%
With red CAS in (v0.41.172), L3 sims (6 seeds, 120 days, optimistic pilot, influence on): 0.30 made flying every 3rd day a coin flip (3 wins, 1 defeat, 2 open); 0.35 wins it 6 of 6 (78-110 days), flying daily wins in 58-85, idle skipping still loses 4 of 6; 0.40 barely punishes idle (1 loss in 6).

## v0.41.173, Pilot Influence text: off does not mean the war cannot be lost
With Pilot Influence off the war plays on its own and, since red CAS (v0.41.172), L3 is lost in about two runs in three (6 seeds, 120 days; the corrected sims never won).

## v0.41.172, Red close air support in the ground war
Each day red flies `RED_AI_CAS` strikes (L1 0, L2 1, L3 1) at the front-most blue sector facing it; one succeeds with chance `RED_CAS_P` 0.30 x red's surge, less half of blue's AIR tempo, less `RED_CAS_BARE` 0.15 when it has neither cover nor an escort; a success takes `RED_CAS_CUT` (10%) off that ...

## v0.41.171, Air tempo: credit for what the whole mission did; a bad sortie takes nothing back
A kind takes the larger of its grade step and its credit, not the sum.

## v0.41.170, The CAS task force starts closer
Cause of the stalls unknown (DCS ground pathing); this hides it for short trips.

## v0.41.169, State file: tracks of the CAS columns
Diagnosis only; no behaviour change.

## v0.41.168, The TARCAP stands further back
Smoke bound in check on the TARCAP distance 28 -> 38.

## v0.41.167, A strike's SEAD escort fires HARMs at the SAMs that cover the target
`strike_tasks._sead_attack_tasks`: the covering SA-2/3/6 (gate) sites get HARM tasks for a STRIKE package as well as a CAS one (same window as CAS).

## v0.41.166, The coalition's supply floor is 30%; air tempo runs 0 to +40%
Sims (L3 F-16C, 5 seeds, 120 days, red 0.55): idle 3 red wins of 5, flying stand-in 0 red wins (2 coalition wins, 3 still open); L2 unchanged (coalition wins in about a month either way).

## v0.41.165, Settings: Pilot Influence moved below the whole Weather block
The row and its description now come after the Weather block.

## v0.41.164, Nothing to fly keeps your Pilot Influence; a box when the war ends
The GUI shows one box, titled VICTORY or DEFEAT with the ending's name, with the same story line as the Overview, the moment the war ends (a flown sortie, a skipped day or the dev skip).

## v0.41.163, Fewer MiG-31s, and they sit deep
A MiG-31 is a big interceptor that works from rear bases under ground control, so:

## v0.41.162, Friendly errors for saves this version cannot open
Loading a save that this build cannot read no longer shows a traceback.

## v0.41.161, Pilot Influence also switches air tempo
With Pilot Influence off, `tempo.get` returns 0 and `tempo.record` moves nothing, on top of the red surge: your flying changes nothing in the war sim.

## v0.41.160, Pilot Influence
New setting `pilot_influence`, on by default, in New Campaign and Settings > Campaign (like Weather and AI Skill: an app setting, copied into the campaign when it is planned and simulated).

## v0.41.159, The carrier moves along the campaign
The fleet no longer sits at a fixed point 160 km west of Batumi.

## v0.41.158, Strikes and CAS go in behind the SEAD
On L2 and L3 most jobs for a Viper or Hornet were DEAD, because every strike and CAS target under an SA-11 or SA-10 was blocked until a DEAD cleared it.

## v0.41.157, CAS task force stops at the contact point
From his 15:38 run: the A-10s killed 11 of 19 red units in 3 minutes, but the friendly task force arrived about 12 minutes later (DCS ran its off-road column about 36% slower than planned) and then drove 2.5 km past the red column.

## v0.41.156, Red zerg, part 2: the mass raid in the mission
The mission side already built big raids in several groups with SEAD and DEAD groups ahead of them (part 1 made L3 raids 6 to 8 bombers, 12 on a wave day); this makes them proper zergs.

## v0.41.155, Red zerg, part 1: red can win (ground and war model)
This is the war-model half; the mass raids you fly come next (part 2).

## v0.41.154, L1 gets museum-piece SAMs; Ctrl+Space only in AI-Test
Story premise: a shadow sponsor keeps the insurgents properly funded and armed, so their old SAMs work at full health.

## v0.41.153, Story wording and Ctrl+Space everywhere
Merged #217 before this landed, so it is its own change.

## v0.41.152, Campaign Revamp Stage C4: polish
Overview: a "Today's tasking" card: the day's packages by kind (CAS, strike, SEAD / DEAD, counter-air, patrol, fleet defence), how many your squadron can fly, or why it has none (`overview_detail.tasking`).

## v0.41.151, Window size and position, and a developer shortcut
The window first opens at 90% of the usable screen (the taskbar is left out), at most 1700 x 960 and never under the 1100 x 700 minimum, centered on the screen it opens on.

## v0.41.150, Campaign Revamp Stage C3: the stories, and the ending
Levels 2 and 3 are Russia against Georgia and a US-led coalition; level 2 is level 3's story with a smaller Russian force, the victory at Sochi and a smaller counter-attack.

## v0.41.149, Campaign Revamp Stage C2: Situation panel, detail tabs, scramble fix
SITUATION PANEL (Overview, top left): the full Background text, scrollable, and the Intent, in a panel with a Hide / Show button; the posture label and one "Now" line (the posture's line; at the end of the campaign the ending text) stay pinned at the bottom open or closed.

## v0.41.148, Campaign Revamp Stage C1: the Overview figures
POSTURE replaces the three phases (`narrative.PHASES` is gone; `narrative.phase()` now returns the posture).

## v0.41.147, Air tempo
Four job kinds: CAS, STRIKE, DEAD (SEAD / DEAD / Standoff) and AIR (sweeps, patrols, intercepts).

## v0.41.146, Campaign Revamp Stage B4: Level 1 raids
Which rule blocked L1 raids: every airfield, depot and garrison of ours sits under a live Patriot / HAWK, and red raids a covered target only with a Su-24M wing that can field a SEAD group (v0.41.125).

## v0.41.145, Campaign Revamp Stage B3: detachments and the no-hunt thresholds
The detachments along the road already exist as the sectors of the push: each has a red and a blue force and a dug-in forward position (`rfwd_N` / `bfwd_N`, v0.41.102), so the red-side sectors are Sochi to Gelendzhik 4, Gelendzhik to Krymsk 1, Gudauta to Sochi 2, Sukhumi to Gudauta 1 (it was 2; XO ...

## v0.41.144, Campaign Revamp Stage B2: depots and the supply loop
Depots and fuel on both sides now matter: they feed the ground war, they can be struck, they mend on a timer, and they change hands with the bases.

## v0.41.143, Campaign Revamp Stage B1: the push
The ground war is now a march across red's airfields, and victory is by ground only.

## v0.41.142, Campaign Revamp Stage A3: red's air roster by type, not by dice
Red now starts each level with a fixed ROSTER of jets per type, placed by rules, instead of a total split over fields with a random type per field.

## v0.41.141, Campaign Revamp Stage A2: the Level 1 insurgents never drop below 70% supply
It reaches everything that reads red's supply: the daily ground fight and reinforcements, SAM rebuilds and SAM-order transit time (v0.41.140).

## v0.41.140, Campaign Revamp Stage A1: SAM orders are a fixed feature
Both sides' SAM orders (`sams.red_orders`, `sams.blue_orders`) now always run overnight, at every level.

## v0.41.139, engagement circles slice 2: the long-range TARCAP stands behind and aside of the short-range escort
Measured first on the identity set: no package has a short- and a long-range TARCAP together (one TARCAP flight per package, and the planner gives it a long-range jet first), so there was nothing to stagger there.

## v0.41.138, engagement circles slice 1: the TARCAP circle meets the BARCAP circle
Measured on the identity set first (84 missions, 120 TARCAP circles): matched inside each mission, every TARCAP has a BARCAP circle, and 9 of them left a strip of 0 to 9 nm between the two circles (my first count, 33 gaps up to 37 nm, paired circles from different missions and was wrong).

## v0.41.137, the CAS target column stays at the CAS point
The column is built at the CAS point and only creeps 1.2 km toward your side (at most 3.5 m/s); the friendly task force starts at most 6 km from the contact point (was up to 10 km).

## v0.41.136, Bug B: the war sim's red air cover counts fighters only
With the planned striker zerg that would have made every strike harder.

## v0.41.135, reactive dispatch and emergencies are always on
A settings file that had either off is set back on at load.

## v0.41.134, the Resume button looks like a button
It is now a solid Fly-blue button, "Resume sortie in progress" (same style as FLY; shown only while a sortie is waiting for results).

## v0.41.133, Settings and notice clean-up
Settings > Campaign: the Weather description now sits under the Weather dropdown (it had drifted below the AI Skill text).

## v0.41.132, no RCV point on the player's own carrier flight
It is now added to AI flights only (and to the player's flight when the AI flies it, the all-AI test), as the land-field recovery point already was.

## v0.41.131, the unit limit counts the whole mission again; merge radius 15; "later packages" setting
The 500 ceiling in `sqe/data/limits.json` stays in the code but is dormant (250 is lower).

## v0.41.130, Overview: ground-war text moved left, blue SAM rings, damage-aware rings
The ground-war sector lines, BARCAP cover lines and bomber lines moved from above the map to a "GROUND WAR AND PATROLS" card under the conflict text on the left.

## v0.41.129, red SEAD covers every battery that covers the target
In Georgia the fields are about 20 nm apart: Kutaisi is covered by Senaki's and Kobuleti's batteries too.

## v0.41.128, the raid gate sits clear of the neighbouring fields' SAMs too
The raid was on Kutaisi; the gate, 48 nm from Kutaisi, lay 28 nm from Senaki's Patriot, which killed RAID-B-3 at 90 s and RAID-D-2-1 at 354 s.

## v0.41.127, carrier flights keep their height until 30 nm from the boat
Hornets and Tomcats on every carrier return did the same.

## v0.41.126, red bombers wait outside the Patriot's reach until the radars are down
Hold the bombers at a gate, abort if the radars stay up.

## v0.41.125, red raids: SEAD first, no dice
Red raids on fields had a 60 % (L3) / 20 % (L2) roll for the SEAD group, so many raids flew straight into the Patriot / HAWK (XO's Senaki raid: 4 of 4 bombers shot down, no SEAD).

## v0.41.124, a scramble you do not take is folded in wherever it is
The mission is built around the package you picked (its circle and window); every unit of the scramble that started in its window comes along, rooted on that package's time.

## v0.41.123, alert pairs: the clock call is no longer dropped, and they dash to the station
Tracks: red alert pairs came within 19 to 28 nm of the F-14 TARCAP and nobody fired (ROE is the DCS default on both sides; not the cause).

## v0.41.122, state file: missiles left on the shooter
Read it as about one high: DCS may count the missile just fired.

## v0.41.121, a scramble you take brings along the packages that were hidden in your original
The scramble's own finds come first; six packages at most; the usual unit cap trims the furthest.

## v0.41.120, red alert pairs fight at their station and are called in time; the TARCAP circle reaches toward red
Tracks: two alert pairs (Su-27 Sochi, MiG-29A Gudauta) were called at 1040 / 950 s and airborne at 1248 / 1286 s, 140 to 175 s after the TOT (1111 s); they orbited at 22,000 ft 24 nm from the F-14 TARCAP (Uzi 1, 26,000 ft) for about 12 minutes.

## v0.41.119, contest: TARCAP on the threat axis, red guards fight for their sites, red's stations reach forward
TARCAP AXIS (`fighter_stations.axis_station`, used in `mission_builder`'s TARCAP branch after the v0.41.118 pull-in): the station is `TARCAP_NEAR_NM` (16) from the middle of the shooters' launch points on the bearing toward red's nearest planned patrol station or live fighter base ...

## v0.41.118, TARCAP in closer to the shooters; red site-guard call-in waits for the strike
TARCAP STATION (`mission_builder._plan_stations`, the TARCAP branch): after the step back it now moves toward the middle of the shooters' launch points, 1 nm at a time, until it is `TARCAP_NEAR_NM` (16) from it, never closer than `TARCAP_BEHIND_NM` (8) to the JSOW point and never into a SAM ring.

## v0.41.117, red's DEAD package: 4 + 4 Su-24M KAB-500Kr, gated on the battery's radars (step 2 of 2)
PLAN (`PackageBuilder._land_raid_plan`): behind a SEAD group of 4+ jets, `extra["dead"]` = 8 (behind 8 SEAD jets, if the wing has 8 more Su-24M beyond the bombers and the SEAD group), else 4 (if it has 4), else 0; `dead_cover` = 4 fighters of the raid's escort type.

## v0.41.116, red's SEAD package: 4 + 4 Kh-31P jets with an escort and a TARCAP (step 1 of 2: the DEAD package and its gate come next)
SIZE (`raids.arm_jets`): a full-strength Patriot AND a HAWK live: 8 Su-24M, two four-jet flights (16 Kh-31P); the first on the Patriot, the second on the HAWK.

## v0.41.115, red patrols called in at the right time and place; fighters in first and closer
Their circle (25 nm) did not reach the SEAD shooters 36 nm away.

## v0.41.114, blue defensive missions: stations up the raid's way in, a base CAP for the intercept, and a fix to the call-in script error
Also his mission-load error `attempt to call global 'SQE_CALLIN' (a nil value)`.

## v0.41.113, BARCAP stations pushed forward
The orbit centre moves out toward the threat so the two sides can snipe at long range while the defender is still inside its own SAM cover.

## v0.41.112, blue BASECAPs called in with the alert pairs (step 2 of 2, blue side) and a fix to red's stay time
BLUE CALL-IN (`RaidSpawns._blue_callins`): in a defensive mission (a raid scramble folded into yours, or a package that defends the fleet) every blue base CAP and carrier CAP (relief and standby pairs too) that can answer gets the same extended route as red's: after its home leg, HOTSPOT, BACK, the ...

## v0.41.111, red BASECAPs called in with the scramblers (step 2 of 2, red side)
The patrols should be called to the hotspot when the scramblers are called, and fly back to their station afterwards.

## Tools only (no version bump): call-in probe, fourth version
Problem with the flag route: a pair whose shift ends, or that bugs out, would also fly the hotspot leg.

## Tools only (no version bump): call-in probe, third version
What the run did show: a CAP pair goes about 40 nm out for a visible air target by itself, and the survivors turn back to their station afterwards.

## Tools only (no version bump): call-in probe, second version
The first run's hint: V3 (flag-released orbit, hotspot waypoint, waypoint back) did return; the pushed tasks were inconclusive.

## Tools only (no version bump): call-in probe
Step 2a is a test of the DCS mechanics, not the feature.

## v0.41.110, red patrols first (step 1 of 2)
PATROLS FIRST: `reactive.plan_red` now holds one pair per BARCAP area a wing flies today out of the reinforcement draw.

## Tools only (no version bump): AWACS tuning probe
Mission Editor "cockpit parameter" triggers try about 36 guessed parameter names in three units (MHz, kHz, Hz); each fires once as an on-screen message and a `SQEPROBE` line in dcs.log.

## v0.41.109, the quiet day, the carrier CAP on the setpiece, and the big hit (part 3 of 3)
QUIET DAY: red now STAGES the carrier raid (`bombers.decide` -> `stage`, `QUIET_DAYS` = 1).

## v0.41.108, the carrier raid in the mission: big raids are several groups (part 2 of 3)
A raid of more than 4 bombers (or escorts) is now several groups of nearly equal size (12 = 4+4+4, 6 = 3+3).

## v0.41.107, the carrier raid is a flyable setpiece (part 1 of 3: package, list and right pane)
The red bomber raid on the carrier (FLEET_DEFENSE aimed at the carrier) is no longer AI-only.

## v0.41.106, Mozdok's own escort squadron (bomber trump card, step 2)
Red's Mozdok wing now holds a second squadron: Su-27s flagged `role="escort"` (L1 none, L2 8, L3 16; `Difficulty.bomber_escort_wing`, a judgment call: 2 escorts per bomber for the biggest L2 raid, 8 bombers' worth at L3; no source for the size).

## v0.41.105, red's bombers are a trump card (step 1: background sim)
Red launches the Tu-22M3 carrier raid only (a) in a window it judges safe (estimated chance the raid is stopped under `bomber_safe_p`: L3 0.12, L2 0.06, L1 never), cooldown 8 days, or (b) when desperate (air/command losing, Mozdok under attack weighted 0.5, front in its last stage), cooldown 5 ...

## v0.41.104, the unit limit counts only the base mission; merged packages are bounded by the radius and a fixed ceiling
Settings > Mission Build "units max" (default 250) now counts the BASE mission only (your package, its support, its sites, the reliefs, standby and alert pairs, reinforcements).

## v0.41.103, the ground war on the Forces page
Forces > new tab "Ground war": one row per sector with the enemy and friendly force as bars and the forward garrison each side holds there (a dash where that side holds nothing in the sector).

## v0.41.102, forward garrisons (both sides, every sector)
Every sector now has a dug-in forward garrison for each side: red `rfwd_N` (state.assets) and blue `bfwd_N` (state.blue_assets), 3 km either side of the sector centre.

## v0.41.101, in-universe scramble text, and raid scrambles fold into your mission
An emergency you cannot take no longer says why ("the F-16 doesn't do CAS", "no free pair").

## v0.41.100, tankers and AWACS on the Forces page, blue air defences per site
Forces > new tab "Tankers and AWACS": each support asset (E-3A, E-2C, KC-135, KC-135 MPRS, S-3B; the red A-50 dimmed, "not flying yet"), its type, base, serviceable / authorized airframes, cycle (time on orbit and turnaround), hours of cover today (from `state.barcap["support_flights"]`) and a ...

## v0.41.99, hot runway starts at your own field become a sub-setting
Then the subsetting is the one where it does it even on same base ...

## Docs: audit of stale text (no version change)
`docs/GUIDE.md`: Settings now lists six tabs (Experimental, hot starts at the ramp in General); the Missions "All packages" line says the list is display-only (v0.41.93); the AI-only patrol line names all four support patrols.

## v0.41.98, hot runway starts move to Experimental
"Hot starts on the runway (AI flights)" moves from Settings > General to Settings > Experimental.

## v0.41.97, hot runway starts at your own field (phase 2)
With "Hot starts on the runway (AI flights)" on, AI flights from YOUR field start on the runway too, but only after you are rolling: the earliest release is your takeoff time + 60 s (the 60 s stagger), and the hook (existing `PRWY` rule) also waits until you have actually taken off.

## v0.41.96, hot starts on the runway for AI flights (phase 1)
New setting, Settings > General, "Hot starts on the runway (AI flights)", off by default.

## v0.41.95, hot-ramp setting moves to General
The hot-start checkbox moves from Settings > Experimental to Settings > General (next to the other "how a sortie runs" options) and is retitled "Hot starts at the ramp (scramble pairs)".

## Docs: CLAUDE.md code map (no version change)
The Project's `barcap-plan.md`, `red-arm-plan.md` and the design notes copy were refreshed.

## v0.41.94, red's SEAD group is sized like blue's salvo
Thresholds mirror blue's HARM salvo (v0.41.83) and are judgment calls; 2 Kh-31P per Su-24M is from Wikipedia (Kh-31).

## v0.41.93, "All packages" is display only; no "are you sure" on a stand-down day
The Missions page list choice (My squadron / All packages) now only decides what the list shows.

## v0.41.92, hot-ramp scramblers launch earlier; fuel lines in the debrief
Read from XO's 2026-10-21 runs (`alerts` called / airborne times): with hot ramp on, a pair took 324 to 566 s from the call to the air at Gudauta and 283 to 369 s at Nalchik; the hidden runway start is about 2 minutes (`ALERT_TAXI_S`).

## v0.41.91, scramblers take a station and fly a complete route
Read first (runs of 2026-10-21): red alert / reinforcement pairs had one `INTERCEPT` point ON the target with an orbit and nothing after it; red patrols (Bandit, Relief, Standby) ended at `CAP2`; blue alert pairs had a `CAP` point exactly on the raid's target (inside red SAM reach in the 2026-10-16 ...

## v0.41.90, red's base CAPs are spread through the day
Cause: each red patrol area flew its day's sorties back to back from the start of one 6-hour wave (`redair.plan`), so a field's whole day of patrols sat in one to three hours (Sukhumi 00:00 to 00:50, for example) and a morning mission found most areas empty.

## v0.41.89, BARCAP status line and shorter Experimental settings
The Overview's theatre summary now ends with "BARCAP cover today", one line per base or carrier (the share of today's 24 h each blue area, by direction, has a pair up, from the plan in `state.barcap["blue_cover"]`; the patrols fly 06:00 to 22:00, so 67 % is the most) and a line with the planned ...

## v0.41.88, HAVCAP and tanker CAP are planned chains of their own
Pairs stay two hours (the tanker-guard endurance); the number is the same patrol share by level as the BARCAP (10 / 20 / 40 % of full cover), at least one sortie per asset.

## v0.41.87, tankers and AWACS as assets (step 1: airframes, windows, losses)
Blue: E-3 "Overlord" 6 airframes (USAF has about 30 E-3s, 26 at Tinker over four squadrons; Wikipedia), E-2C "Magic" 4 on the carrier (a VAW squadron has four, globalsecurity.org), KC-135 "Arco" 8 (the 465th ARS operates eight KC-135Rs, globalsecurity.org), KC-135MPRS "Texaco" 8 (judgment call) ...

## v0.41.86, blue's patrols count in the background raids (BARCAP background sim, step 2)
A base patrol on station now matters to raids nobody flies.

## v0.41.85, blue's base CAP and carrier CAP are a daily plan (BARCAP in the background sim, step 1)
Each day plans, per blue field or boat that has a BARCAP area, a few sorties of a fighter pair through 06:00-22:00 (airframe endurance as in barcap.py: 30 min F-16 / Hornet, 2 h F-14 / F-15C).

## v0.41.84, red anti-radiation missiles, step 1: a Su-24M SEAD pair ahead of a field raid
A Su-24M raid on one of our airfields that has a live Patriot or HAWK may bring a pair of Su-24M with Kh-31P (`raid_arm`: Level 1 never, Level 2 20 %, Level 3 60 %; judgment calls).

## v0.41.83, SAM borrowing defaults to off
The Experimental tab's Red / Blue borrowing switches now start unticked; tick them to get SAM orders by need (v0.41.67 / .68).

## v0.41.82, HARM salvo scales with the SAM cluster (Standoff DEAD)
The Standoff DEAD package's HARM flights were always 2 + 2 jets whatever surrounded the target.

## v0.41.81, Experimental settings tab: borrowing per side
"Borrowing" = the SAM orders by need (`sams.red_orders` / `sams.blue_orders`: a battery is moved from the least-threatened site to a threatened one).

## v0.41.80, hot ramp scrambles at land fields (experimental, off by default)
New setting (Settings, "Hot ramp scrambles at land fields", off by default; `hot_ramp_scrambles`).

## v0.41.79, BARCAP as planned coverage, step 3 (third slice): a CAP pair that loses a jet, goes winchester or hits bingo is replaced
The hook watches every covered pair (`COVER` in `sqe/debrief.py`, checked every 10 s): a jet missing, all missiles gone (only once the pair was seen armed), or fuel under `BINGO_FUEL` (20 %, judgment call).

## v0.41.78, BARCAP as planned coverage, step 3 (second slice): blue base / carrier / HAVCAP / tanker CAPs rotate
Until now a base CAP, carrier CAP, HAVCAP or tanker CAP sat on station for the whole mission, however short its legs (a jet that could fly 3 hours on one load).

## v0.41.77, BARCAP as planned coverage, step 3 (first slice): red patrols get their relief in the mission
The planned chain (v0.41.73) has the next sortie of an area start 10 minutes before the one on station leaves.

## Smoke test step 2 (tools only, no version change): every section passes on its own
Campaign ids are random, so seeded checks could pass or fail by luck (`check_47` "no flyable SEAD flight", the HARM point 33.8 vs 35 nm).

## v0.41.76, red's patrol stations lose the old fixed keep-outs; the ships' reach is a SAM ring
Their stations are BARCAP stations (v0.41.73) that stay outside blue's SAM rings, and now outside the carrier group's real reach too: `barcap.FLEET_REACH_NM` 70 nm (measured: CAP pairs were killed 51 to 67 nm out) is a ring in the SAM-clear rule, and `CAP_FLEET_KEEPOUT_NM` (the boat's CURRENT ...

## v0.41.75, red patrols pushed behind the target by the keep-out are left out
Cause: `_plan_cap_stations` then pushes every station away from our marshal point, fields and the carrier (`RED_KEEP_NM`, 130 nm round the boat), and that push moved a station that was fine into the back of the target.

## v0.41.74, BARCAP as planned coverage, step 2: the mission side (the checkpoint)
Blue's carrier CAP and base CAP no longer face "the nearest enemy field": each takes the BARCAP area (v0.41.73) of its asset that faces the mission's target (the area whose direction is closest to the bearing from the asset to the target; with merged targets this is the main target's, a judgment ...

## v0.41.73, BARCAP as planned coverage, step 1: planning and state (red's patrols fly it)
Every defended asset gets BARCAP areas: red's fighter fields and blue's fields and carriers.

## v0.41.72, AI boat flights land for real; the hook removes them after the pattern
Now it gets the real Land waypoint tied to the ship (as when AI landings is off), so DCS homes on the moving boat itself.

## v0.41.71, Navy flights are recovered near the boat that has steamed on
The tracks show them joining the tanker Texaco 1 from about 1800 s and flying its racetrack with it; they never reached their RTB point.

## v0.41.70, AI Skill for Red and Blue
New "AI Skill, Red" and "AI Skill, Blue" settings (XO 2026-10-21: "DCS is kinda iffy when the AI is set pretty high, like they cheat"), on the New Campaign page and in Settings > Campaign (the same two settings, like Weather; they apply from the next mission).

## v0.41.69, blue Patriot and HAWK batteries stand apart
Cause: the battery was laid out by pydcs's star formation, 20 m between units.

## v0.41.68, red SAM orders by need
Red orders SAM batteries by the same rule as blue (XO 2026-10-21: "SAMs can be ordered by both sides").

## v0.41.67, blue SAM orders by need
Each night, at most one order: the most threatened field (nearest to an enemy fighter field) with a destroyed site asks for a battery of that kind; the sender is the field furthest from the front that has a standing one (health 0.6 or more) and sits at least 20 nm further back than the receiver ...

## Unreleased (tools only, no version bump), smoke test split into sections
Step 1, no change to what is checked: the 2,300-line function is cut at its version-tagged blocks; what a section borrows from an earlier one is listed at its top (`a, b = c.a, c.b`) and what it leaves for later at its bottom, through a shared `Ctx`.

## v0.41.66
A mission build can no longer freeze in pydcs's scattered formation (found 2026-10-21 through the smoke test, which stalled about one run in three; XO: "prioritize the smoke test"). pydcs's `VehicleGroup.formation_scattered` retries each vehicle's random point with `while True` and its ring is ...

## v0.41.65
Red's SAM clusters follow the same placement doctrine as blue's (PR 4 of the SAM build; XO 2026-10-21: "follow doctrine and adjust as I test").

## v0.41.64
Blue's air-defence sites sit at their own place, doctrinal with a seeded jitter (PR 3 of the blue SAM build; XO 2026-10-21: "doctrinal, but randomness on the exact positioning so no two campaigns will be exactly the same").

## v0.41.63
Blue's air-defence sites are damaged, repaired and rebuilt one by one, like red's (PR 2 of the blue SAM build; XO 2026-10-21).

## v0.41.62
Blue's air defence is three sites per airfield, in red's record (XO 2026-10-21: "I'd rather use red's because I think it's tested and it's not abstract").

## v0.41.61
The enemy and friendly 50 nm values are now fixed in the mission options (`enemy_cap_engage_nm`, `friendly_cap_engage_nm`, both 50), so missions are unchanged.

## Unreleased (tools only, no version bump), identity check covers AI-only packages
Baselines saved before this change must be saved again.

## Unreleased (tools only, no version bump)
Runs in a temp folder, nothing of yours is touched, about 40 s a run.

## v0.41.60
PR B: one name per job in the waypoint actions and the settings screen (XO 2026-10-21; no change to what flies).

## v0.41.59
Split step 6: the red air picture and the raid / reactive spawns moved to their own files (XO 2026-10-21; NO behaviour change).

## v0.41.58
Split step 5: the support-CAP code moved to its own file, `sqe/support_caps.py` (XO 2026-10-21; NO behaviour change).

## v0.41.57
Split step 4: the fighter-station rules moved to their own file, `sqe/fighter_stations.py` (XO 2026-10-21; NO behaviour change).

## v0.41.56
Split step 3: the strike / SEAD / DEAD / CAS tasking moved to its own file, `sqe/strike_tasks.py` (XO 2026-10-21; NO behaviour change).

## v0.41.55
Split step 2: the SEAD attack tasks moved out of `_attach_waypoints` (XO 2026-10-21; NO behaviour change).

## v0.41.54
The code inside is moved as written; only the inputs it needs became parameters and what later stages use is returned.

## v0.41.53
Red strength is tracked per squadron (XO 2026-10-21, step 2 of the typed red squadrons).

## v0.41.52
Red wings are cut into typed squadrons (XO 2026-10-20 / 21, step 1 of the same-rules build: data only).

## v0.41.51
Support-CAP pull-back removed (XO 2026-10-20 22:39: three runs in a row showed `pulls` empty).

## v0.41.50
Role rename: one name per job (XO 2026-10-20, PR A of the same-rules build).

## v0.41.49
AI flights fly home above the ridges (XO 2026-10-20 22:07 run: Venom 5-2, a lone F-16 TARCAP, went from 26,000 ft to 3,000 ft MSL about 50 nm out and flew level for 100 nm over rising ground, 914 to 1,127 m on its track, then died at 2574 s with 84% fuel and nobody shooting; every other flight went ...

## v0.41.48
Ground groups keep off the runways (XO 2026-10-20 20:53: a target AAA formation lay diagonally across a runway; it could block the side's own aircraft).

## v0.41.47
The JSOW flight stops hunting after its salvo (XO 2026-10-20 18:27: the Squids lingered, moved closer after launching; all eight were lost, seven to Sukhumi / Gudauta MiGs, one to the SA-11).

## v0.41.46
JSOWs are flung further out (XO 2026-10-20: the JSOWers were still massacred; SAMs target them and enemy scrambles jump them).

## v0.41.45
Default merge radius is 25 nm (XO 2026-10-20; was 50): fewer packages fold into yours, so fewer units, but nearby packages still merge.

## v0.41.44
DCS's default Race-Track orbit runs from its waypoint to the NEXT waypoint, which for a station is RTB.

## v0.41.43
The TARCAP overwatches from behind the JSOW flight (XO 2026-10-20: after the HARM shooters launch, the TARCAP turned round with them, then was out of position when red's second wave arrived; XO: that turn-round point should be the TARCAP's station).

## v0.41.42
The JSOW flight is no longer left alone (XO 2026-10-20: the run lost all five Standoff DEAD Hornets to Sukhumi / Gudauta MiG-29s after their JSOW release; the TARCAP and escort sat at the HARM point, 17-18 nm from the JSOW launch points, and the TARCAP's circle did not reach them).

## v0.41.41
Divert tower on COMM2 CH3 (XO 2026-10-20): it was COMM1 CH5.

## v0.41.40
Escorts stick to the last striker until it is out (XO 2026-10-20: the DEADers were left behind at the mercy of enemy air).

## v0.41.39
Ground units get explicit orders (XO 2026-10-20): every red garrison and armour column, every blue site (garrisons, sector forces) and the CAS task force now carry weapons free + alarm state red on their first waypoint (`_ground_orders` in `mission_builder.py`; `_drive` uses it too, so the CAS ...

## v0.41.38
TARCAP stays at least 15 minutes, then until the last striker is off target + 5 minutes (the 15-minute minimum is back: it had been halved to 7.5 min in `_hold_end`) (XO 2026-10-20: TARCAPs left as soon as the SEAD flight headed home).

## v0.41.37
Adjusted `STATION_FRAC` to 0.85 to provide better coverage from long-range SAMs.

## v0.41.36
(XO) Player SPAWN WP on Kneeboard Fixed the issue where player flights from land bases show SPAWN WP.

## v0.41.35
In all three of XO's runs of 2026-10-16/17 the chasing support CAP was the tanker CAP, the only one with an explicit weapons-free ROE (v0.41.26, to make it shoot first).

## v0.41.34
Support CAPs are pulled back when they chase out of their circle.

## v0.41.33
Fighter Sweep: hunts known enemy air out in the open, no more baiting (XO 2026-10-16).

## v0.41.32
Fixed: DCS refused to save a mission ("Viper 2: Waypoint 8 have both unlocked speed and time and not surrounded by waypoints with locked time!").

## v0.41.31
Red raids keep clear of the carrier group: a red raid's ingress and way home now bend round the fleet as well as round blue's Patriot fields, keeping 70 nm from the carrier unless the fleet is what it is raiding.

## v0.41.30
Blue air defence at doctrinal strength, every field alike (XO: "all bases are important"):

## v0.41.29
Red raids fly blue's shape and stop rushing in (red side): XO wants raids that stop rushing to their deaths like RTS units.

## v0.41.28
Removed the text 'untested in the cockpit' in the F-14B(U) setting.

## v0.41.27
Only the job types that have been tuned are offered to you; the rest stay in the war, flown by the AI.

## v0.41.26
From XO's Nalchik SA-6 run: the tanker was shot down in the middle of the fight, and the F-16s guarding it were timid.

## v0.41.25
From XO's second Sukhumi run (v0.41.24): 10 friendly jets lost, 4 of them the Gudauta SEAD flight to the Sukhumi S-300 again, and some Hornets never recovered at the boat.

## v0.41.24
From XO's Sukhumi SA-11 Standoff DEAD run (13 friendly jets lost: 5 to SAMs, 8 in the air).

## v0.41.23
Fight circles moved instead of shrunk, and preloaded flights placed right.

## v0.41.22
All blue flights stay away from SAMs they aren't sent against.

## v0.41.21
Carrier CAP pulled in: the F-14s orbit 12 nm from the boat (was 22) on a 10 nm leg, and engage within 30 nm of it (was 50).

## v0.41.20
No needless banzai: nobody flies into defences it can't survive unless the situation calls for it.

## v0.41.19
Strike gate: a strike or counter-air package is not planned while a live medium / long-range SAM (SA-2, SA-3, SA-6, SA-11, SA-10; partly destroyed sites count while above a quarter strength) covers its target, unless that SAM is suppressed.

## v0.41.18
Settings: AI landings, one for carriers and one for airfields:

## v0.41.17
An AI flight going home to the carrier is recovered at a point 10 nm from the boat: every jet still flying counts as landed (debrief and war sim) and the group leaves the mission.

## v0.41.16
The low-level run started at the IP, 70 nm from the target (the IP sits half way out on long routes); three F-16s flamed out (the wingmen queued at the tanker behind the lead until they were dry); the lead refuelled, bombed alone 30 min after its TOT and was shot down by a live SA-6.

## v0.41.15
The homeward fight stays over the way home: after the hold, a TARCAP / escort / sweep engages inside a fixed circle covering its station-to-home leg (plus 20 nm), not a circle that moves with the jet.

## v0.41.14
Support CAP stations use the measured SA-10 reach.

## v0.41.13
Its station sits inside the nearest enemy field's scramble circle (5 nm in), so the alert pairs launch into the sweep before the strikers arrive, while staying 35 nm from every live SA-10 and 15 nm outside every other SAM ring.

## v0.41.12
After take-off the first point is the marshal point, for you and for AI runway starts.

## v0.41.11
AI strike, SEAD and CAS routes bend around every live SA-10 that is not their target (or the umbrella their HARMs go for), keeping 35 nm, with a turn point where a leg would pass inside.

## v0.41.10
TARCAP and escort hold until the last package over their target area is off target (targets within 60 km), not only their own; at most 30 minutes longer.

## v0.41.9
A sweep plans no support CAP, and the packages folded into the mission had theirs dropped (support is shared), so the tanker, the AWACS and the boat flew unguarded.

## v0.41.8
Gudauta's scramble circle was 29 nm round the field.

## v0.41.7
The Patriot faces the nearest enemy fighter field.

## v0.41.6
HARM flights fire only at what they are tasked on (OPEN FIRE, was weapons free): their own site, the Tors that guard it and the SA-10 umbrella.

## v0.41.5
But after Springfield's (F-14 TARCAP) hold ended, a lone MiG-29 followed them home and fired four R-27s while they only defended: three F-14s lost with about 35 missiles still on board.

## v0.41.4
From the v0.41.3 Gudauta Standoff DEAD: the SA-10 next to the target stayed quiet while the first HARM flight was looking for it (one HARM went at it), lit up a minute later and shot down all four Squid JSOW Hornets and Hornet 2-1.

## v0.41.3
Their launch point sat 20 nm from the target, which put it 13-24 nm from a live SA-10, well inside its reach.

## v0.41.2
DCS refused a v0.41.1 player escort mission: "Viper 3: All waypoints (5-5) have locked speed and surrounded by waypoints 4 and 5 with locked time!"

## v0.41.1
Alert fields scramble on what their own radar sees.

## v0.41.0
TARCAP and escort stations against a long-range SAM (an SA-10 whose reach covers the target): 62% of its reach from it (about 30 nm), level with the HARM shooters, and 9 nm sideways toward the nearest enemy airfield, between the threat and the package.

## v0.40.10
With the script on, it used to count your jammer on for the whole mission (it cannot read your switch).

## v0.40.9
It treated the F-15C as having none (tier 0); it now has an internal self-protection set (tier 1, like the F-14 and F/A-18), for AI Eagles and for yours.

## v0.40.8
The state file now records each alert and scramble group (red alerts, red reinforcements, blue DCA): when it was called (its scramble trigger fired, or the runway queue released it), when its first jet got airborne, and "stuck" when it was called but still on the ground 5 minutes later (a taxi jam).

## v0.40.7
Alert and scramble jets wait hot on the ramp and taxi when called (red alerts, red reinforcements, blue DCA; on the carrier, hot on deck).

## v0.40.6
Alert groups that cannot fit a field start in the air instead of being left out.

## v0.40.5
COMM1 (UHF): CH1 AWACS, CH2 tanker, CH3 JTAC (when there is one), CH4 second tanker (when there is one), CH5 divert.

## v0.40.4
Splash damage (Settings: "Splash damage", off by default).

## v0.40.3
Return to base." Once you have landed: "...all flights accounted for.

## v0.40.2
Air-to-air rework, part 2: Fighter Sweep and Defensive Counter Air.

## v0.40.1
Air-to-air rework, part 1 (from the v0.39.24 remarks): fighters don't chase into danger, for blue and red.

## v0.40.0
Each DEAD job now gets one kind of DEAD flight, picked by the threat at the site.

## v0.39.25
Airborne flights no longer spawn on top of each other.

## v0.39.24
Every AI strike, DEAD, SEAD, JSOW and CAS flight now takes off with "restrict air-to-air attack" on.

## v0.39.23
Callsign numbers used to restart in every package, so the tasking order could list two Viper 1s in different packages.

## v0.39.22
Fixes from the v0.39.21 run (Sukhumi SA-6 SEAD, Day 1).

## v0.39.21
The JSOW flight now pushes with the HARM shooters (`JSOW_TRAIL_S = 0`) instead of 160 s ahead of them.

## v0.39.20
A Tor (SA-15) battery within 12 km (`TOR_COVER_KM`) of a SEAD or DEAD target, or of the strike leg into it, is now targeted with the site.

## v0.39.19
Every SEAD package now has an optional 4-ship JSOW flight alongside its HARM shooters: Hornets carry 4 AGM-154A JSOW CEB each (BRU-55 doubles on 2 and 8, tanks on 3, 5 and 7), Vipers carry 2 (pylons 3 and 7).

## v0.39.18
SEAD-stage packages go in 15 minutes later (`LATE_SEAD_MIN`), so each DEAD stage, normally 10 minutes behind its SEAD, now arrives about 5 minutes ahead of it.

## v0.39.17
Aborting DEAD flights go home, not back over the target.

## v0.39.16
The DEAD briefing now says the DEAD package follows the SEAD by the real gap (10 minutes, read from `DEAD_STAGE_GAP_MIN`; it said a hardcoded 25).

## v0.39.15
If every SEAD flight on a site is down or gone while its radars are still up, the DEAD flight calls "abort, RTB" straight away instead of holding until the timeout.

## v0.39.14
Your own DEAD flight holds too, the same way AI does.

## v0.39.13
SEAD packages whose targets lie within 60 km of each other are synchronised: each push is moved so that its estimated arrival lands on the latest arrival of the group, so the earlier flights wait rather than going in alone.

## v0.39.12
An AI DEAD flight holds instead of turning back when the radars are still up.

## v0.39.11
Every shot in `SQE_state.json` now carries the target's map position (`tx`, `tz`): its last known spot at the time of the shot or hit.

## v0.39.10
In the v0.39.9 run both Hornet SEAD flights (Hornet 1, Squid 1, four HARMs each) fought MiGs on the way in, drifted into Tor and SA-11 range (15-16 km from the site) and died 140 to 180 s before their HARM launch point without firing a HARM.

## v0.39.9
In the v0.39.7 run (AI test, Sukhumi SA-10) the player package's SEAD pair (Viper 1/2) never fired a HARM: its task was aimed at the site's S-300 track radar, which only radiates while it is tracking, so there was nothing to shoot at.

## v0.39.8
In the AI run, Viper 3-4 crashed at 596 s with nothing shooting at it.

## v0.39.7
In the AI-only run on the Sukhumi SA-10 the four SEAD F-16s fired no HARM at all and all four died (the site lost nothing).

## v0.39.6
HAVCAP and base CAP stay until the last flight is home.

## v0.39.5
The road scan only covers the places the war touches.

## v0.39.4
The DCS log of the v0.39.2 run showed `cpu_s=-1`: `os.clock` does not exist in DCS's mission environment, so every timer in the road pass had been silently off, the "0 ms" test results meant nothing, and the scan fell back to 50 calls per tick (hours for the map).

## v0.39.3
Road scan: 0.5 s slices and progress lines in dcs.log.

## v0.39.2
The road scan announces its first calls and skips the roads instead of freezing.

## v0.39.1
The road pass ran 40 map columns (about 15,600 `getClosestPointOnRoads` calls) in one tick; that call is a nearest-road search and far slower than the height calls, so DCS stalled.

## v0.39.0
Every live enemy site, column, garrison, support site and early-warning radar is built; every friendly airfield gets its defences, garrison and supply sites; every friendly sector with troops gets its column; every planned enemy patrol is airborne at its station.

## v0.38.2
New campaigns start in 2006 (June 12 by default, was 2004).

## v0.38.1
The FC3 F-15C no longer counts as having an internal jammer: its tier is 0 (no jamming rolls, no cover in the abstract war).

## v0.38.0
The Settings > Terrain scan page shows whether roads are loaded.

## v0.37.0
The altitude choice (HIGH / MED / LOW) now counts ground anti-aircraft.

## v0.36.0
Air wings that fall back to recover, the same rule for both sides.

## v0.35.0
DCS gives jammers almost no effect of their own, so SQE adds one, the same for both sides and for you.

## v0.34.0
SEAD wears the defence down, so a campaign against a strong air-defence network moves instead of stalling.

## v0.33.0
The number of vehicles in an enemy front-line column now follows its sector's strength: the base mix is multiplied by 0.5 + 1.5 x strength (2x at full strength, 1x at a third, as few as half at nearly nothing).

## v0.32.0
A long-range site (the kind SEAD / DEAD packages are sent to) at 35% health or less can pull back from the front to recover.

## v0.31.2
The empty Missions pane calls it a stand-down day ("Stand-down day for you.

## v0.31.1
When the Missions list has nothing you can fly, the right-hand pane now says so: "No flights for <squadron> today." with the reasons that apply (too few serviceable aircraft for a pair, nothing on the tasking order for your aircraft's roles, jobs given to other squadrons or out of reach) and a ...

## v0.31.0
A SEAD / DEAD job is now two packages for the same site: "SEAD: blind <site>" (SEAD flights, escorts, sweeps if the threat calls for them) and, 25 minutes later, "DEAD: destroy <site>, once its radars are blind" (strikers and their escorts).

## v0.30.0
Every friendly airfield now has a dug-in garrison next to it (`bgar_<field>`), the same kind of record as the enemy's.

## v0.29.0
Before, the enemy's fighters were invented around your package when the mission was built: the nearest wings, a CAP in front of each of their bases, always there.

## v0.28.3
The radar check now fires on distance, not on the clock.

## v0.28.2
In-world wording: the text you read in the game no longer says "Red" and "Blue".

## v0.28.1
Every DEAD gate is now written to `SQE_state.json` (`"gates"`), so an all-AI run shows what happened without watching: for each flight the site, the scheduled and actual check time, radars left, whether the turn-back command went through (`cmd`), and the flight's distance to the target when the ...

## v0.28.0
DEAD packages call themselves off when the radars are still up.

## v0.27.1
The all-AI test is a launch option now, not a setting.

## v0.27.0
Garrison CAS waits for the SAM cover to be cleared.

## v0.26.5
Its target is a defended cluster (the site's own AAA, Shilka and Strela, a garrison, Tunguskas next door), and LOW only helps against radar missiles, which are exactly what the package is there to destroy.

## v0.26.4
Stand-off bug: a SAM site that is nearly dead still counted as dead.

## v0.26.3
The "My flight is flown by the AI" tick (Settings > Mission build) now really does it.

## v0.26.2
The red and blue strength figures (R100, B18 ...) overlapped each other and the airfield names around Sukhumi and Senaki.

## v0.26.1
Red's known CAP no longer sits inside the fleet's missile range.

## v0.26.0
Air defence that rebuilds and moves (phase 3 of the ground war; sqe/sams.py).

## v0.25.1
AI fighters no longer chase to the far end of the map.

## v0.25.0
AI escorts and sweeps no longer fly head-on into live SAM cover.

## v0.24.1
Our alert pairs now have a dispatch range, like the enemy's reinforcements always had.

## v0.24.0
Red raids and emergencies (phase 2 of the ground war).

## v0.23.0
The front is no longer a few armor columns that only exist to be shot at: it is five sectors along the Sukhumi to Senaki axis (four plus one deep zone toward Kutaisi), and every sector holds a Red strength and a Blue strength (0 to 100).

## v0.22.0
The same scan mission, after the land and water pass, samples the ground on a 1 km grid (3 x 3 points per cell) and writes SQE_relief_<theatre>.json next to the old file: the highest and the average ground per cell, in units of 10 m (a few MB).

## v0.21.0
A package no longer flies one fixed altitude: the planner looks at which live SAM and AAA sites cover the route from the PUSH to the egress and picks HIGH (the role altitude, as before), MED (about 60% of it, at least 10,000 ft) or LOW (500 ft above the ground, 300 ft for the A-10C).

## v0.20.0
DEP (the climb-out point after takeoff) is now spaced out the way real departures are flown.

## v0.19.0
The kneeboard is now three pages laid out like a printed form: shaded section bands, ruled rows and exactly three type sizes (24 px title, 16 px values, 11 px labels).

## v0.18.0
Settings is now five tabs instead of one long page: General (takeoff buffer, marshal slack, AI fuel, F-14 waypoint names), Campaign (weather, reactive dispatch, ruins, carcasses), Mission build (package merging, radius, limits, CAP ranges), DCS integration (DCS and Saved Games folders, the ...

## v0.17.0
On top of the planned enemy air picture, a sortie can now see extra fighters launch while you fly.

## v0.16.0
Ground sites the war has damaged or destroyed now show burnt-out wrecks (SAM launchers, trucks, tanks) near your route, next to the smoking ruins.

## v0.15.0
Clear is still the default and is exactly what SQE always built.

## v0.14.0
Theatre packs: everything that is specific to the Caucasus (airfields, squadrons, depth tiers, carrier station, sun position and time zone, monthly temperatures, terrain scan area and file, operation text) now lives in `sqe/data/theatres/caucasus.json` instead of being spread through the code.

## v0.13.0
Merging by radius: packages whose target lies inside a circle (Settings > Merge radius, default 50 nm) around YOUR target fly in the same mission, within the same time windows as before (up to 30 min after yours, up to "Earlier packages" before).

## v0.12.8
The default merged-mission unit limit is now 250 (was 150).

## v0.12.7
A final pass now checks every ground group (armour columns, the friendly task force and its JTAC, base defences, sites) against the terrain scan and moves any group with a unit or driving destination in the water, as a whole and as little as possible.

## v0.12.6
Every sortie build now says in its warnings whether ground sites were placed with the DCS terrain scan or only with the rough built-in coastline, so it is clear which one produced a given mission.

## v0.12.5
Creating the terrain scan mission no longer prints pydcs's harmless 'Failed to parse Lua code ... description.lua' lines (a livery file in your DCS install that pydcs cannot read; it is skipped either way).

## v0.12.4
Fix: Settings crashed on opening (wrong import for the terrain scan status line).

## v0.12.3
River margin is now a setting (Settings > Shore margin, second box) and defaults to 100 m instead of 400 m: sites only keep out of the water and off the very bank, so batteries can sit near streams.

## v0.12.2
First campaign: if the terrain scan has not been done, SQE offers it once (create the scan mission now, or skip and do it later in Settings).

## v0.12.1
The terrain scan mission now uses the free Su-25T slot instead of the F-15C (part of the paid Flaming Cliffs 3 pack), so it runs on a DCS install with only the free aircraft and the free Caucasus map.

## v0.12.0
Terrain scan: Settings > "Create terrain scan mission" writes SQE_TerrainScan.miz into your DCS Missions folder.

## v0.11.1
SAM sites, garrisons, radars, depots and armour columns are now placed on land, at least 1.5 km from the coast, and garrisons and column air defence stay close to what they guard.

## v0.11.0
Ruins: an earlier package of the same day and area that has already struck by the time your mission starts leaves its target burning: up to three sites, a few smoke plumes each (a destroyed site gets three big fires, a failed attack one small fire).

## v0.10.0
Package merging now works in both directions: packages that started up to 15 minutes BEFORE yours (Settings > Earlier packages, 0-30) also fly, already airborne and underway when the mission starts (spawned along their route, or holding at the marshal point).

## v0.9.12
The player's TGT waypoint now sits on the ground target at 0 AGL (kneeboard shows "AGL 0"), so pods, weapons and Jester / the WSO can slave to it.

## v0.9.11
Carrier starts: the carrier and escort ships now get warehouse entries like the Mission Editor writes on save.

## v0.9.9
Flying from the carrier no longer lists the "LSO" and "Air Boss" stations as slots (the carrier is saved with allowLso / allowAirboss false).

## v0.9.8
F-14B(U) kneeboard: the start point is now 0 and DEP is 1, matching Jester.

## v0.9.7
Packaging only: release zips no longer contain `.gitignore` or the GitHub guide, so copying a zip over your repo folder keeps your own.

## v0.9.6
The sidebar no longer shows the file name or a second copy of the campaign title (the title is in the page header and the window title).

## v0.9.4
The Missions screen and the briefing now show the enemy fighter count for the whole mission, counting folded packages, the same number the mission is built with.

## v0.9.3
App icon (stencil SQE roundel): window and taskbar icon, and the built SQE.exe.

## v0.9.2
F-14B(U) CAP: 4 AIM-54C, 2 AIM-7P, 2 AIM-9M, 2 tanks (stock AAW05 with the LANTIRN pod on station 9 swapped for the second Sparrow).

## v0.9.1
Loadouts corrected from DCS's own stock presets (`loadouts.py`): the F-16C SEAD flight now carries 2 HARM + 2 AMRAAM + 2 AIM-9X + 2 tanks + ECM + Litening + HTS instead of 4 HARMs.

## v0.9.0
Enemy air with folded packages: enemy fighters = the biggest package's need + a share (Settings, default 100%) of every other folded package's need.

