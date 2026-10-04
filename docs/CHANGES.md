# Changes in v0.3

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
