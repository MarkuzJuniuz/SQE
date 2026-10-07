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
