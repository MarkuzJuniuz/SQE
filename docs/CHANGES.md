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
