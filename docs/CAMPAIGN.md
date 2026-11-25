# How the SQE campaign works

What the war is, what happens each turn, and the rules behind it. For installing and running SQE see `docs/GUIDE.md`
(section 4 there is the short "how a turn works"); for adding a map see `docs/THEATRES.md`.

Checked against the code as of v0.41.529, for both maps (the Caucasus, and Syria in section 10). The mod is still evolving, so things may change (see the last section). Numbers are
tuning values in the code and change between versions: where one matters it is named, so you can find it. Several are the author's judgment calls with no public source, and
where that is the case the code says so next to the number.

---------------------------------------------------------------------------------------------------

## 1. The idea

SQE runs a small background war and gives you short missions out of it. The war tracks both sides' airfields, jets,
SAM sites, supply sites and ground forces. Every turn it plans a handful of **packages** (a job with the flights that
fly it) for both sides. You fly one flight of one package; everything you do not fly is settled by the war simulation
from the odds. Your results change the war, and the war changes what the next turn offers.

It is built to give light missions: few units, only the flights your squadron's jets can actually fill, and nothing
that needs a hundred aircraft in the air. The war underneath is not scaled down: red and blue lose and replace real jets
and sites.

There are two maps: the Caucasus (this page's numbers, unless it says otherwise) and Syria 2001 (section 10, which lists what differs). On the Caucasus the coalition (blue) holds the south-east (Senaki, Kutaisi, Kobuleti, a carrier group at sea and
the rear support base at Kutaisi); red holds the north and the Black Sea coast (Sukhumi, Gudauta, Sochi, Gelendzhik,
Krymsk, Anapa-Vityazevo and Krasnodar-Center behind it, and the northern fields such as Mozdok, Beslan, Nalchik, Maykop and Mineralnye Vody). On Syria blue holds Incirlik and the Cyprus fields and fights down the Hatay coast road.

---------------------------------------------------------------------------------------------------

## 2. The three levels

You pick the level when you start a campaign. It sets how strong red is and how it fights (`sqe/difficulty.py`). The table is the Caucasus; Syria's is in section 10.

| | Level 1, Insurgent | Level 2, Regional power | Level 3, Near-peer |
|---|---|---|---|
| Red airfields | 4: Sukhumi, Gudauta, Sochi, Gelendzhik | 10, the whole red coast and the north | 10, the whole red coast and the north |
| Red aircraft at the start | 94, old types kept supplied by a sponsor (MiG-21, MiG-23, Su-25, Su-24M) | 240, mixed (MiG-31, MiG-29, MiG-23, Su-24M, Su-25), plus the Mozdok bombers and escorts | 284, modern (MiG-29S, Su-27, Su-24M, Su-25; on the Caucasus no MiG-31 or MiG-29A), plus the Mozdok bombers and escorts |
| Red SAMs | SA-2, SA-3, AAA, MANPADS | SA-2, SA-3, SA-6, SA-11, AAA | SA-10, SA-11, SA-6, SA-15, SA-19 |
| Air defence integration (`iads`) | 0.15 | 0.55 | 0.90 |
| Red AI skill | Average | Good | High |
| Bomber wing (Tu-22M3 at Mozdok) | none | 14, raids the carrier only when red is desperate | 24, raids the carrier as a normal part of its plan |
| Red counter-attacks on blue bases (`counterstrike`) | low (0.10) | 0.30 | 0.55 |
| Ground war pressure (`red_attack`) | 0.15 | 0.45 | 0.80 |

Blue is the same at every level: 18 squadrons with 284 jets in total across the coalition fields and the carrier (F-14B(U), F/A-18C, F-16C, F-15C
and A-10C squadrons, plus F-15E and HVAACAP squadrons and the F-117A squadron that the AI flies). A person can fly the F-14B(U),
F/A-18C, F-16C, F-15C and A-10C; the F-15E and F-117A are AI only. You can change the AI skill of each side in Settings.

---------------------------------------------------------------------------------------------------

## 3. The clock

* A **turn is 4 hours**. Six turns a day. On the Caucasus Day 1 starts at 08:00, so it has four turns (08, 12, 16, 20); on Syria it starts at 00:00 and has all six.
* Turns that start at 20:00, 00:00 and 04:00 are **night turns**. They are planned like any other turn; the Auto-Skip option for night
  turns passes them for you.
* One thing moves the clock: **Skip Turn** or a flown sortie. Either one is exactly one turn forward (a flown mission
  does not skip ahead to the end of the day).
* The war resolves a turn's unflown packages when the clock moves. At midnight the daily steps run: supply-site repair and the Force Index,
  the ground war's night, squadrons moving after a fallen field, red's rebuilding.

**Auto-Skip** (sidebar) only repeats Skip Turn for you: Stand-Down Turns (nothing you can fly), Night Turns, and Crew Rest
(after a flown sortie, skip until a chosen number of hours has passed). It stops when a flight is available, the war ends,
or after a week.

---------------------------------------------------------------------------------------------------

## 4. What a turn plans

At the start of each (day) turn the planner builds the turn's tasking list, in this order:

1. **Red moves first.** Red plans its standing patrols (CAP pairs over its fighter fields, a Fighter Sweep now and then
   where the ground is contested) and draws its raids on you.
2. **Blue's standing cover** is planned (section 8): BARCAP pairs over a share of the BARCAP areas and a guard pair for the
   AWACS and each tanker.
3. **The planner picks the jobs.** It scores every target red has that can be hit (a SAM site, an EWR, a runway, a supply
   site, a garrison, a troop column), skips ones that cannot be attacked yet or that no squadron can reach, and takes a few. How many jobs a turn
   gets follows the jets: the free strike pairs (the ones left after the standing patrols and the support) times a level share (0.6 at Levels 1 and 2,
   0.9 at Level 3), divided by the 5.7 pairs one package uses, at least 1 and at most 4, 8 and 8 on a day turn (Levels 1, 2, 3), plus two on every
   day turn of Day 1 ("day 1 is brutal"; `engine.py`: `TASK_SHARE`, `PAIRS_PER_PACKAGE`, `N_MAX`, `DAY1_EXTRA`). A night turn plans a quarter (Level 1)
   or a third (Levels 2 and 3) of that. It takes the best-scoring job of each kind first, and no one kind may take more than 40% of the
   list, with the SAM wave (section 5) taken out first. The F-117A's night jobs (section 5) come on top of that list.
   A stand-off job is picked only while jets that carry its weapon are still free (a Standoff DEAD counts its two HARM flights too, as the same
   Vipers and Hornets fly them); otherwise the slot goes to the next target and the stand-off job waits for a later turn.
4. **Packages are built from the jets that are free.** A package is crewed from what the ledger shows (section 7). A job
   that cannot be crewed (no stand-off jets free, a target out of reach, no SEAD seat) waits for the next turn, and the turn tries other targets
   in its place (up to 12 tries): ones the jets left over can still reach, a strike behind a SEAD package already built among them. A turn can still end
   short when nothing else can be flown, mostly on Syria at Level 3 where nearly every open target needs a stand-off weapon, or when the SEAD jets run out.
5. **Start times are set in four waves, an hour apart.** The waves open with the turn and 60, 120 and 180 minutes later;
   packages start within about 25 minutes of their wave's opening. The jobs are spread over the four waves as evenly as they
   go, the earlier waves first; packages listed together (targets inside the Target Area Radius) stay together in one wave, and a carrier raid and its prep
   go in wave 1. A job goes to a later wave when its jets are not ready yet (section 7): the planner tries its wave and the later
   ones, and keeps the one that crews it best.

The jobs you can be offered are listed on the Missions tab: **Strike**, **Standoff Strike**, **OCA: Runway Strike**, **SEAD**,
**Standoff DEAD**, **Close DEAD**, **Close Air Support** (including **Troops in Contact**), **Fighter Sweep**, and **Intercept**
jobs against red's raids ("Base Defense", "Supply Defense", and so on). BARCAP is AI only. A job is shown only if your
squadron's jets can fly a seat in it. Each tasking can also bring extra flights: escort, TARCAP, SEAD.

### What a package looks like

A package is a set of flights with one target. The basic shapes (from `sqe/packages.py`):

| Job | Flights |
|---|---|
| Strike | 4 strikers, 2 SEAD if the target is under a SAM, TARCAP when red has fighters that can reach it. A plain-bomb strike (GBUs, not a stand-off kit) whose target is covered by a live fixed Tor (Level 3) takes a 4-jet SEAD escort instead (8 HARMs; a pair when only two jets are free) and waits for another day when none is free |
| DEAD | 2 SEAD, 4 strikers, TARCAP |
| CAS | 4 CAS, 2 SEAD if the target is under a SAM, TARCAP when red has fighters that can reach it |
| Standoff DEAD | one HARM flight (2 jets, 4 near a big cluster), 4 JSOW jets, and a second HARM flight (2 or 4) |
| EWR strike (stand-off) | 4 strikers with stand-off weapons, 2 TARCAP |
| Fighter Sweep | 4-jet sweep flights, one more for every 4 bandits beyond what the other packages' own cover can take |
| Night F-117A job (AI) | a pair or a four-ship of F-117A, no escort, no SEAD |
| Intercept (raid) | the fighters that cover what red is raiding |

The TARCAP (up to 4 jets) is sized to the fighters red can field near the target. Where red has more than that, the package
gets an escort as well, or a separate Fighter Sweep is planned ahead of it. A **Standoff** job (a site under a long-range SAM such as the SA-10) uses JSOWs,
SLAM-ERs or similar weapons released far outside the SAM's reach, with HARM shooters timed on the same minute.

**Routes round the SAM rings.** An AI flight, and you, fly round every live SAM ring on the way out to the marshal point, to the IP or the station, and home. The ring is the SAM's reach plus a margin: SA-10 35 nm,
SA-5 71, SA-2 26, SA-11 20, SA-6 16, SA-3 15 (the map draws the same rings). A flight that starts or ends inside a ring (a base near the front, an IP inside the target's ring) leaves or enters it by the nearest edge when that cuts its time inside.
Only the attack legs (IP to target to egress) go in as the job requires; your IP on a strike or SEAD is placed outside the rings that hold the target. The planner counts reach by the length of that route, and a job no jet can fly round the rings within
2.4 times its combat radius (1.5 times that with a tanker) is not offered, with no message; the same limit applies to each flight when the mission is built. A flight over that limit first tries a low leg straight under an SA-5 or SA-2 ring
(500 ft below the ring's lowest engagement height; each low nm counts 1.5) in place of its detour, then a shorter hold on station, and only then is left out.

**Package merging** (Settings > Mission build): when you fly, every package that starts inside the time windows (15 minutes
before and 30 after yours by default, Later Packages up to a whole turn) flies in the same mission, wherever its target is,
nearest to yours first, each still keeping its own time on target. The unit limit (250 by default, up to 750 in Settings) trades detail for
performance: over it the furthest packages are left out first, a Fighter Sweep stays while a package it covers stays, and
your own package and the ground war round your target keep their share before the others. The **Target Area Radius** (15 nm)
is that area: the supply sites and the ground war built round your target, the ruins of earlier strikes, and the packages the
Missions list shows together.

---------------------------------------------------------------------------------------------------

## 5. How red and blue fight

### The ground war

The front is a chain of sectors, one per airfield from Krymsk to Kutaisi, each with a red and a blue **force strength**. The level decides how many
are fought over: Levels 1 and 2 contest Sukhumi, Gudauta and Sochi, Level 3 adds Gelendzhik and Krymsk.
Each night the sectors in contact exchange losses (the defender fights at ×1.25, `DEFENDER`); a side under 30% of the
other's force in a sector withdraws from it (`BREAK_RATIO`) and nobody is hunted to the last unit. Both sides get
reinforcements, scaled by their **Force Index** (see below), and a dug-in **garrison** in each sector gives its side a bonus and a CAS target.

Blue's CAS and strike work lowers red's force in a sector and lowers its Force Index; red's raids do the same to blue. When
blue holds a sector in front of a red airfield and red has nothing organised there, **the airfield falls**: it and its
ground units go down for good, its jets withdraw to the nearest standing red field with 30% lost, and its depots and fuel
farms change sides with their stock. The next push then waits for the takeover (9 days; 1 day on Level 1 in Syria) and red's own attacks wait 3.

### The Force Index

The **Force Index** is how well supplied each side is, shown as a percentage on the Overview (Force Index tab) with a band: bad at 65% or
less, alright from 66 to 90, good above 90. It is the stock each side holds in fuel farms, depots and road **supply sites**, compared with what
it started with: from 35% (nothing left, the floor for both sides) to 100%. Replacement SAM batteries on their way cost a side some of it, even below the floor.
Red on Level 1 is counted differently in a new campaign: 70% of the figure is its inner sites' stock and 30% its road sites', and it never drops below 45%
(the insurgents are resupplied across the border by night). Capturing a site moves it and its stock to the captor.

The Force Index sets the pace of nearly everything that rebuilds:

* **Reinforcements** of the ground forces in each sector scale with it. (On the Caucasus at Level 3 red's daily reinforcement is more than three times the other levels', so the line toward Sochi and Krymsk can be pushed back.)
* **Jet replacements:** a squadron below strength gets a replacement pair every 24 hours divided by the Force Index (every 24 hours at 100%, about 69 hours
  at the 35% floor). The Tu-22M3 and the E-3 are the exception (section 7).
* **Site repair:** a damaged or destroyed supply site mends by the Force Index divided by 6 of a full site each night, so a destroyed one is back in 6 days
  at 100% and about 17 days at the 35% floor. A site that was struck that night does not mend.
* **Limping jets** take twice as long to refit, scaled by the Force Index.

Red's road sites are extra supply sites scattered along the roads (15 at Level 1, 30 at Levels 2 and 3, but 20 at Levels 2 and 3 in Syria), some guarded,
some a parked truck only. Hitting them, and the depots and fuel farms, is how blue lowers red's Force Index.

### Air defence

Red's SAM sites are **suppressed** (their radars blinded by SEAD) for two turns, then recover, or **destroyed** by DEAD. A
destroyed site is rebuilt later, at the pace of red's Force Index, and mobile sites move after being hurt. A **belt** of overlapping long-range
sites protects what is behind it: a site inside an intact belt cannot be offered as a target until the belt site covering
it falls.

The planner runs **SAM waves**: on every planned day turn it first takes a fixed number of SAM jobs (Level 3: two on the sea side, one on the
mountain side, one runway crater; Level 2: two, two, one; Level 1: one). The SEAD stages of a turn go in at least five
minutes apart, nearest first. Two axes are kept apart. The **mountain axis** is red's northern fields (Mozdok, Beslan, Nalchik, Maykop,
Mineralnye Vody, Krymsk, Gelendzhik): the waves go after their SAMs, EWRs and runways to take away red's air power, and this
is the only thing that moves it. The **sea axis** (Sukhumi, Gudauta, Sochi) is where the ground war is fought. There are no
depth tiers: any target that is not blocked by an intact belt can be offered on any turn. (The F-117A night strike below is the exception: it
ignores a belt.)

### The Nighthawks (F-117A)

Blue's small night squadron: 12 F-117A of the 8th FS 'Black Sheep', AI only, based at Kutaisi on the Caucasus and at Incirlik on Syria. It flies at night
only, one pair or four-ship at a time with no escort, and only against targets no red fighter can reach: a radar, a SAM site (the long-range ones first)
or an airfield runway with no patrol station or ready alert pair within 40 nm. It ignores a SAM belt in front of the target (stealth) but is not
safe over a covered target: each jet is lost with a small chance that grows with the SAM sites that cover it. At most 2 jobs a night turn, one runway
strike a night, and the same target is not offered again for 7 days. It is the highest-maintenance airframe: 16 hours of refit after a sortie and one
replacement airframe per 96 hours. Because red keeps fighters at almost every field, it flies rarely.
In a mission, red can still scramble against the strike, but red's early-warning radars and AWACS do not point its fighters at an F-117A: a red
fighter goes after one only once its own radar has picked it up.

### Runways

A runway strike that lands at least 4 of its bombs on the runway **craters the field** (fewer is damage the repair crews fix overnight): nothing launches from it, scrambles or lands there for 6
turns (24 hours); a field that holds a Tu-22M3 squadron (Mozdok, Damascus, Bassel Al-Assad) is repaired in 2 turns (8 hours), because red's bomber fields are its
best-repaired. A closed field's squadrons cannot fly from it and red's wings skip it.

### Red's air

Red flies standing **CAP pairs** over its fighter fields, **Fighter Sweeps** where the sector is contested, and **raids** on you.
It holds back **25%** of each squadron's ready fighters as a **reaction reserve** that is the only source of scrambles and
reinforcements; the rest are free for patrols and raids. Jets that fly go to refit; shot-down jets are gone until replaced.

**How red's jets are laid out.** At Levels 2 and 3 red fields about as many jets as blue (the Tu-22M3 wing not counted): on the Caucasus about 240 at Level 2 and 284 at
Level 3, on Syria 270 and 284 (blue has 284). Level 3 is harder than Level 2 through its types, its pilots and its SAMs, not through the count. Each field has a fixed
share of the jets, sized to its parking, and the fields have room left for squadrons that fall back from a lost field. Level 1 fills its four fields to about 70% (Gelendzhik about 60%). (These are the Caucasus figures; Syria's are in section 10.) The jets are grouped into squadrons of a few types per field, up to 6 jets at
Level 1, and 14 at Levels 2 and 3 (about 10 to 12 is the Soviet and Russian norm, so these are big squadrons), so a field flies one or two types in full squadrons, not
two or three jets of everything. The Forces screen lists them with in-universe names such as "Sochi-Adler MiG-21Bis Sqn #2"; a squadron that withdraws keeps its name.

A **raid** is a package that red actually plans: a Su-24M strike on a field, a supply site, a garrison or a
troop column, with escorts. Whether a raid goes in depends on whether red has the jets: nothing is rolled once you click
Fly. Some raids are **unwarned** (25%, 35% and 45% at Levels 1, 2, 3) and come with no warning. Blue sees a raid when an AWACS
(the E-3 or the E-2C) is on orbit that turn; with none up it still sees one in a quarter of cases. A raid blue does not see
is not listed as an Intercept job and is settled by the war simulation against blue's planned patrols alone.

**What red carries.** A raid's kit follows what it attacks. A Su-24M raid on a runway carries four BetAB-500ShP (rocket-boosted
concrete-piercing bombs, on pylons 2, 3, 6 and 7); on troops or a garrison four RBK-500U cluster bombs (126 OAB-2.5RT
fragmentation bomblets each, same pylons); on a supply site FAB-500 bombs on those four pylons and FAB-250 on the other four. (A
satellite-guided KAB-500S is planned for supply sites, a Lutorin pull-forward, but the Su-24M's weapon list in pydcs does not
offer it yet, so the supply kit is still the FAB one.) On Syria the Su-17M4 carries four BetAB-500ShP on a runway, four RBK-500
(268 PTAB-1M each) on troops and four FAB-500 on a supply site. Red's front-line strike on a blue column carries the troops kit.
Kh-59M raids, the Su-25's eight FAB-500 and the Tu-22M3 (three Kh-22 on the carrier raid, four racks of nine OFAB-250 on a land
strike: DCS's Kh-22 is an anti-ship missile and the AI does not fire it at land) are as before. Red's SEAD packages fire the
Kh-31P (50 nm), as described below; red's Tu-22M3 fields (Mozdok, Damascus, Bassel Al-Assad) are repaired in two
turns after a runway hit, see Runways.
Red's **SEAD raids** go after blue's Patriot and HAWK sites with anti-radiation missiles: a full Patriot is attacked
by three packages (two at Level 3, where a raid never flies more than 16 jets), a HAWK by two, escorted by one fighter for
every two jets (the figure from red's mass-raid doctrine) and preceded (at Levels 2 and 3) by a fighter sweep that makes up the rest,
up to 16 aircraft (16 jets: 8 escorts and 16 sweep; 12: 6 and 12; 8: 4 and 12), and tries to draw blue's fighters away. A package is 4 jets (8 at Level 3) with two
missiles a jet. Every package fires the **Kh-31P** from about 50 nm out, and the launch times are set so that every package's
missiles reach the site together. Red works from the **outside in**: a SEAD raid goes only for the sites it can attack
without another live Patriot reaching its attack point (the outermost ones); a site behind them is raided once the ones
in front are down. At Level 3 red may also send one bomber raid at that field behind its SEAD, from an axis at least 100 degrees away: the Patriot keeps facing the SEAD raid, so the bombers meet only the rest of the field's defences. At Level 3 a raid on an outer Patriot is followed by a second wave on the Patriot behind it (the one only that outer site covers), its missiles due 5 minutes after the first wave's land; it may cross the outer site's ring, but no other live Patriot's.
Only the **Su-24M** flies SEAD (it carries the pod its anti-radiation missiles need); the Su-17M4 does the CAS and bombing work.

At Levels 2 and 3 the **Tu-22M3 bomber wing** (at Mozdok on the Caucasus, split over Damascus and Bassel Al-Assad in Syria) can raid the carrier, after a quiet day, and then not again for 8 days (5 when it is desperate). At Level 3 red sends it when it
estimates a window it judges safe or when it is desperate; at Level 2 only when desperate (red's air arm or command structure is badly
hurt, or Mozdok is under pressure). This raid is
a flown set piece: the SEAD packages that clear its approach fly in the turn before.

The carrier does not sit on one spot. Every three days it takes a new station (a seeded pick among the spots within 80 km of the best one, and never more than 30 nm beyond the standoff from the nearest red airfield: the best spot is the nearest to the front that keeps the fleet's standoff from every red airfield and 25 nm off the coast), so red cannot count on finding it in the same place. At the start of a war red stages no raid for a while: three days on the Caucasus (the carrier has just arrived and red has to find it) and a week on Syria (blue's opening strike is a surprise). When a raid is staged (the day before it launches, while the wing is loading Kh-22 missiles) blue's intelligence picks that up: a red **INTELLIGENCE** banner shows above every page, a line goes in the war log, and the fleet sails out to at least 215 nm from every red airfield (at most 250 km in the day), so the raid has to come out over open water. At that distance the fleet's aircraft cannot reach inland targets, which is why there are no inland Hornet missions on those days. Once the raid is over the fleet returns to its station.

The staging day is a tell. Red's strikes, raids and surprise raids stop (as before), and the bomber field flies no ordinary patrol: its own escorts are held for the raid, and fighters from other fields within 300 nm cover it instead (two pairs a turn at Level 3, one at Level 2), by day and by night, so a night F-117A strike on the base meets them. The overview says so and the banner pill reads "Bomber base guarded". If the bomber field is cut or destroyed before the raid launches, no Tu-22M3 could take off: the staged raid is called off (banner and war-log line), the escorts are free again and the fleet sails back. A cut that is repaired before launch day does not stop it.

### Blue's air

Blue has a standing patrol system of its own (next section). It also scrambles alert pairs against raids and, if
the carrier is sunk, its aircraft are moved to land fields (any that cannot be parked are lost).

---------------------------------------------------------------------------------------------------

## 6. Winning and losing

* **Victory** (Caucasus; Syria's is in section 10) is by the ground war only: you take **Sochi** (Levels 1 and 2) or **Sochi and Krymsk** (Level 3). At Levels 2 and
  3 the red counter-force that arrives must also be beaten. Jet counts alone do not win the war.
* **Defeat** is either of: the coalition's air component falls below 15% of its authorised strength, or **3 of your airfields
  have fallen**. A sunk carrier does not count as a fallen field (its aircraft land elsewhere; the carrier group sails back in after 7
  days).
* **No idle surge, no Tactical Edge.** The war runs on its own: red does not press harder when you skip turns, and your sorties do not raise the odds of the AI's jobs. Your flying counts as part of the war through what you really destroy and defend. (The code for both is kept but switched off.)

---------------------------------------------------------------------------------------------------

## 7. Squadrons, jets and the ledger

Each blue squadron has jets *authorised*, *available* (ready now) and some in **refit** or **reserve**.

* A jet that flies a package or patrol lands and goes to **refit**: 3 hours as standard (the rugged A-10C and Su-25 take 2;
  the Tu-22M3 and E-3 take 8, the F-117A 16). A sortie lasts about 100 minutes, so a jet that flew in a turn's first wave is ready about
  40 to 65 minutes into the next turn (its second or third wave), one from the second wave 100 to 125 minutes in (third wave), one from
  the third wave 160 to 185 in (fourth wave), and one from the fourth wave not before the turn after. A jet that comes back damaged ("limping", under 90% health) takes twice as long to refit.
  A jet that was shot down is gone, and so is one that lands at a field that is not yours: it is captured at an enemy field, interned at a neutral one (the debrief says so, and the squadron loses the airframe).
* **Replacements** arrive as a pair every 24 hours at a Force Index of 100% (slower below that, see the Force Index). The Tu-22M3 and the E-3 are replaced one airframe every
  48 hours and the F-117A one every 96 hours, regardless of the Force Index.
* A planned turn draws its jets from the **ledger**: the jets ready now (wave 1), and for each later wave the jets whose refit
  ends by that wave's opening, so a package of wave 3 can use everything ready by the third wave and a package of wave 1 only the
  jets ready now. A later wave spends its newest jets first, so the early waves keep theirs. Standing patrols and guards are taken off first, packages after, so patrols and strikes compete for the same jets. A job
  that cannot be crewed from what is left waits.
* A squadron whose base falls moves to the nearest field with room, losing 30% of its jets, and sits out the move
  (3 or 6 turns).
* **Your own squadron** can be picked at any time; the planner offers you the jobs it can crew, and after a flown
  sortie your flight's losses and survivors are booked the same way as any other.

---------------------------------------------------------------------------------------------------

## 8. Standing cover: BARCAP, the AWACS, the tankers and their guards

* **BARCAP** is blue's patrol over the areas that face red's launch points. Each turn a share of the areas that a squadron can
  reach gets a pair (Level 3: 60% by day, 20% at night; Level 2: 40% and 16%; Level 1: 20% and 10%). A station gets at most two pairs
  a turn: the first goes up at the turn's start; when it leaves before the turn ends (a long-legged pair after 120 minutes, a short-legged
  one after 30) the relief goes up in the first wave that opens as it leaves, the third wave for a long-legged pair and the second for a
  short-legged one. Strike packages carry the BARCAP that faces
  their target while they fly; BARCAP is AI only.
* **The AWACS and the tankers are assets, not freebies.** Blue has 4 E-3s (12 hours on orbit, 6 refit), 4 E-2Cs (4 hours on
  orbit, 6 refit), 8 KC-135s (4 hours on orbit, 3 refit) and 8 S-3Bs (2 hours, 3 refit). A package gets the AWACS and a tanker
  only if one is on orbit while it flies: a jet with a boom gets a KC-135, a probe-and-drogue jet (F-14, F/A-18C) the carrier's
  S-3B. A lost airframe is replaced slowly. Today the war sim does **not** take AWACS losses on its own (`AWACS_LOSS_ON` is off).
* **Each of them has its own guard (HVAACAP).** Fighters guard the E-3, the E-2C and the tanker for as long as the
  asset is on orbit in the turn. The HVAACAP squadron (8 F-15C) guards the land-based E-3 only: a four-ship when it has four jets
  ready (four fly one turn, the other four the next), a pair when it has fewer. The tankers and the carrier's E-2C get a guard pair
  from the ordinary fighter squadrons, as does the E-3 when the HVAACAP squadron has no jets ready. The
  guard goes up in the last wave that opens before the asset's window starts (the first wave when the asset is up already), or in a later
  wave when no pair is ready sooner.
  Every package that carries the asset carries its guard. The pair can refuel on the orbit.
* **The AWACS sits under blue cover** (behind the front, from the rear base: Kutaisi on the Caucasus, Paphos on Syria), not near you or your target: within 30 nm of a defended
  field or the carrier group, or within 25 nm of a blue BARCAP that has a pair flying that turn. The tanker sits forward on the way home, under the same cover where it can, clear
  of SAM rings and red's scramble circles.
* **Both prefer cover to distance from raids.** The tanker's track tries to stay at least 50 nm from the routes a red raid flies and 100 nm from the route of a red fighter sweep;
  the AWACS tries to stay 40 nm from a raid's route and 100 nm from a sweep's. Cover comes first: the AWACS moves to the covered spot (up to 150 nm from its rear station, never nearer to
  red and never off the map) with the most room from those routes, and the tanker takes a covered spot that is clear of them when there is one, else the covered spot that is least
  inside them (at most 25 nm inside), else a clear spot with no cover; the build warns when a tanker sits inside. Only when no covered place exists does the AWACS move away from
  red's raid routes, as before. If there is no clear spot at all while the red raids and sweeps fly, the tanker **waits on the ground and launches once they are over**: about 10 minutes
  after the last red raid's time over its target, plus its flight to its track, and only when no red fighter is within 60 nm of the track. Its HVAACAP guard launches with it, and the
  briefing's intelligence says when. It will often arrive after your own flight has gone home (it is there for the later packages); a tanker that could launch only more than
  30 minutes after your planned recovery does not fly that mission. In the
  air, either one turns away when an enemy fighter comes within 60 nm: it flies 40 nm straight away from it and orbits there, and goes back to its track after 5 quiet minutes
  with no fighter within 80 nm. Red's sweeps do hunt them (a sweep can go 100 nm or more from its own bombers), and a tanker cannot outrun a fighter that is already close.

---------------------------------------------------------------------------------------------------

## 9. In the mission

* **AI flights fly the whole plan**: marshal, push, time on target, egress, recovery. A held flight waits at a gate for the
  target's radars to be down and fighters to be clear before going in (CAS and strikes), then resumes.
* **Your flight** is built the same way and then skips most of the AI's scripted tasks, because a person cannot be
  scripted. The mission is otherwise the same whether the AI or a person flies it: job, package, loadout, timing, route
  shape.
* The mission hook writes an `SQE_state.json` of what happened: aircraft lost and landed, ground units destroyed, where bombs
  fell, runway hits. **Accept results** applies exactly that to the war; **Abort** discards the sortie.
* **Scrubs.** If the strikers or the cover of an AI package have lost half their jets, the rest of the package goes home.
* After Accept you get a **debrief**: what was destroyed, your package's success, and the story line for the turn. A SAM
  left suppressed counts as a win for the package (its radars are out).

---------------------------------------------------------------------------------------------------

## 10. Syria 2001 (Operation LEVANT HORIZON)

The second map. You choose the map in the New Campaign dialog; a Syria campaign needs the DCS Syria map. Everything in sections 1 to 9 works the same there (the same turns, packages, Force Index, refit and ledger); this section is what is different. The Caucasus pages above give the Caucasus numbers; the numbers here are the Syria pack's (`sqe/data/theatres/syria.json`), as of v0.41.518.

### The war

It is June 2001 (the campaign starts on 12 June, at **00:00**). A US-led coalition has answered Turkey's request for help and fights its way down the **Hatay coast road** into Syria. Blue flies from **Incirlik**, from Akrotiri, Larnaca, Paphos and Muwaffaq Salti (Hatay is a recovery field only, but it has the full air defence of a blue field: Patriot, HAWK and AAA, so red's raids and SEAD packages treat it as a defended field), and from the carrier **USS Dwight D. Eisenhower**, which sits south of Cyprus (it keeps at least 130 nm from every red airfield, closing in as they fall). Red holds the Syrian airfields. The front is the coast road from Hatay through **Bassel Al-Assad**, **Rene Mouawad** and **Shayrat**, and the level decides how much of it is fought over: Level 1 contests Bassel Al-Assad only, Level 2 adds Rene Mouawad, Level 3 adds Shayrat. The deep rear (Hama, Abu al-Duhur, Tiyas, Palmyra, Sayqal, Damascus, Al-Dumayr, An Nasiriyah) is where the long-range air defence and the bomber wing sit.

Who you fight depends on the level: Level 1 is **the Northern Coastal Command** (the NCC, an insurgent force), Level 2 is **Syria**, Level 3 is **Syria and its Russian backers**.

### The three levels in Syria

| | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| Red airfields | 4: Bassel Al-Assad, Abu al-Duhur, Hama, Shayrat | 11, the whole coast road and the interior | 11 |
| Red aircraft at the start | 94 (MiG-21Bis, MiG-23MLD, Su-17M4, Su-24M) | 270 (adds MiG-29A and MiG-25PD) | 284, plus the bomber wing (all fourth-generation fighters: MiG-29A and S, Su-27, MiG-31; Su-17M4, Su-24M; no MiG-23s or MiG-25s left) |
| Red SAMs | SA-2, SA-3, AAA, MANPADS | SA-2, SA-3, SA-6, SA-11, AAA, two SA-5 batteries | SA-10, SA-11, SA-6, SA-15, SA-19, three SA-5 batteries |
| Air defence integration, red counter-attacks, ground pressure | as in section 2 (0.15 / 0.10 / 0.15) | 0.55 / 0.30 / 0.45 | 0.90 / 0.55 / 0.80 |
| Tu-22M3 bomber wing | none | none | 20 Tu-22M3 (14 at Damascus, 6 at Bassel Al-Assad) with 12 Su-27 escorts (6 at each) |
| Victory | take Bassel Al-Assad | destroy all of Lutorin Works, or red's supply collapses (see below) | destroy all of Lutorin Works, or red's supply collapses |

Red's jets fill each field's parking to about 75% at Level 1 (four small fields) and about 80% at Levels 2 and 3 (270 and 284 jets; the same jets per field; Level 2's types are older, a regional power's, with fewer Su-17M4 than before. Damascus is held back for the bomber wing at Level 3).

Red's raids on troops, garrisons and supply sites are led by the cheap **Su-17M4** attack jet. At Level 3 the Tu-22M3 wing raids the carrier along the line from the carrier through Damascus, at most 16 bombers at a time (drawn from both bomber fields, a closed one skipped), flown as a set piece with its SEAD in the turn before, as in section 5. The fleet's station moves and it sails out of the raid's reach on the staging day, as in section 5.

### Blue in Syria

Blue has 18 squadrons and 284 jets at every level: two F-14B squadrons and two F/A-18C squadrons on the carrier, five F-16C, three F-15C (plus the AI-only HVAACAP F-15C), three F-15E (AI only), one A-10 squadron at Incirlik and the **8th FS 'Black Sheep' (12 F-117A, AI only)**. You can fly the F-14B, F/A-18C, F-16C, F-15C and A-10. The **Era Equipment** setting (New Campaign) picks the airframes of the year: Syria 2001 defaults to the A-10A, the F-14B and no Link 16 data. The weapons follow the year: the A-10A carries no JDAM and no targeting pod (Mavericks, laser and cluster bombs), the F-14B and the F-117A drop laser-guided bombs only, while the F-16C, F/A-18C and F-15E carry JDAM, JSOW and SLAM-ER, all in service by 2001 but still new, and not on every jet.

### The opening night

The campaign starts at midnight, in the middle of a surprise attack. At Levels 2 and 3 the 12 **F-117A Nighthawks** of the 8th FS have just struck as six pairs, one pair per target: every long-range **SA-5** battery first (Homs and Damascus, and Tiyas at Level 3), then the deepest radars (Level 2: the four deep early-warning radars) or, at Level 3, some SA-10 sites and radars. The war log names every site and the pair that hit it. The sites are rebuilt by the normal rule (5 to 7 days, at half strength), so the opening is a window, not a won air war: the rest of the network, the fighters, and the SAM belt at the front are all still up. Level 1 has no opening strike.

The Nighthawks themselves start the war on their way home to Incirlik (the Overview squadron table says "returning", then "refitting"), land at about
00:40 to 00:50 and spend a 16-hour refit, so none of them is ready on the opening night; they are back for the 20:00 night turn of Day 1, and from
then on the squadron flies as described in section 5. You do not fly it; you will see its strikes in the war log and in the sites that fall.

### Winning and losing in Syria

* **Level 1:** victory is the ground war, as in section 6, a march through the cities in three stages: take **Bassel Al-Assad** (the Latakia coast), then **Rene Mouawad**, then **Shayrat** (the Homs gap). After a city falls the next push waits only one day (the takeover is 9 days at the other levels). A war with nobody flying lasts about two weeks at Level 1, about 18 days at Level 2 and about two months at Level 3; flying shortens it.
* **Levels 2 and 3:** no ground victory. The war is won in one of two ways, neither of them a conquest. **Lutorin Works** (below): all of them destroyed at the same time. Or **red's Force Index** (its supply, section 5) at or below 40% for **three nights in a row** (the Overview shows how close it is in a word: distant, approaching, close, under way); that is the depots, fuel farms and road sites, not the cities. The coalition's stated intent is to break Syria's supply and air defence. With red's air defence as strong as it is, the works are the more likely way.
* **Defeat:** the coalition's air component below 15% of its strength (as in section 6), or **one** airfield of yours lost (the Caucasus allows three).

### Lutorin Works

At Levels 2 and 3 five special plants stand in the Syrian rear: two near Palmyra, two in the Homs gap and one at Latakia. They belong to **Lutorin** (a billionaire at Level 2, the richest man in the world at Level 3, the same story), who makes a stabilizer there that gives old Soviet-era arsenals new life. It is made from a crystal that only forms in the Palmyra phosphate beds and cannot be shipped, so it can only be made in Syria; Damascus hosts the plants and his money and arms stand behind its claim on Hatay. The Overview names them in one line ("Lutorin Works: all operational", "most of them still operational", "only a few still operational", "all destroyed"), lists them at the top of the Force Index tab with their health and state, and the red assets list pins them at the top under their own heading and the war log reports each one that falls.

* **They are special targets.** The planner offers a strike on a Lutorin Works plant ahead of the ordinary supply strikes. A plant is a fixed target, so it is hit with stand-off weapons: SLAM-ER Hornets released far out and low, with no SEAD or DEAD job in front of it and without the flight route being stopped by the belt, for as long as a Hornet squadron has two jets to send. With none, the usual rules apply (behind the SEAD or DEAD on the air defence that covers it). The Palmyra plants sit under the long-range umbrella, so the odds there are the worst. A plant is hunted until it is destroyed (a damaged supply site is left alone to mend, a plant does not mend). **They are red's depots too:** each plant counts as a supply site in the Force Index (a site of the 25 red has at Levels 2 and 3: 12 fixed sites, 8 road sites and the 5 works), so a strike on a plant lowers the Force Index as much as one on a depot, and the nightly repair that mends depots does not mend them.
* **They are very hard to rebuild.** Two teams rebuild two destroyed plants at a time (at both levels), and each takes weeks (about a month); a third destroyed plant waits for a team to finish. At both levels one good strike puts a works out, as it would a depot. A damaged plant never repairs.
* **They feed the war on the front.** While the plants stand, the enemy's reinforcements, attacks and raids are stronger, so the more of them you destroy the weaker the push on Hatay. If every one of them is destroyed at the same moment and they all **stay** destroyed for a while (11 days at Level 2, 12 at Level 3: Lutorin's stockpile has to run out; the Overview says so) the war is won ("Lutorin Works is gone"). The other ending is the one the campaign already has: if Hatay falls, the war is lost.
* Your own flying counts as for any other strike: the plants are tasked like every other job, and a plant you hit yourself takes damage from the buildings you really destroy.

### Long-range air defence

The SA-5 is the new problem. A battery at Shayrat reaches over the whole coast from high altitude (the planner is altitude-blind: it treats the ring as reaching every altitude), but it cannot touch a flight low down: measured in DCS, its reach is about 65 nm at high altitude, about 20 nm at 5,000 ft and nothing at 500 ft. The SA-10s (Level 3) are the same kind of problem at shorter range. Standoff jobs, HARM shooters and the Nighthawks are how the belt is opened.

---------------------------------------------------------------------------------------------------

## 11. Still evolving

SQE is still being developed, and the rules on this page may change from one version to the next. The change log
(`docs/CHANGES.md`) says what each version did. If something in a mission behaves differently from this page, or you
find a bug, please report it at https://github.com/MarkuzJuniuz/SQE/issues/new.
