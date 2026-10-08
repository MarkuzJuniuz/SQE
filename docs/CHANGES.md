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
