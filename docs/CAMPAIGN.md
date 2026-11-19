# How the SQE campaign works

What the war is, what happens each turn, and the rules behind it. For installing and running SQE see `docs/GUIDE.md`
(section 4 there is the short "how a turn works"); for adding a map see `docs/THEATRES.md`.

Checked against the code as of v0.41.519, for both maps (the Caucasus, and Syria in section 10). The mod is still evolving, so things may change (see the last section). Numbers are
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

There are two maps: the Caucasus (this page's numbers, unless it says otherwise) and Syria 2000 (section 10, which lists what differs). On the Caucasus the coalition (blue) holds the south-east (Senaki, Kutaisi, Kobuleti, a carrier group at sea and
the rear support base at Kutaisi); red holds the north and the Black Sea coast (Sukhumi, Gudauta, Sochi, Gelendzhik,
Krymsk, and the northern fields such as Mozdok, Beslan, Nalchik, Maykop and Mineralnye Vody). On Syria blue holds Incirlik and the Cyprus fields and fights down the Hatay coast road.

---------------------------------------------------------------------------------------------------

## 2. The three levels

You pick the level when you start a campaign. It sets how strong red is and how it fights (`sqe/difficulty.py`). The table is the Caucasus; Syria's is in section 10.

| | Level 1, Insurgent | Level 2, Regional power | Level 3, Near-peer |
|---|---|---|---|
| Red airfields | 4: Sukhumi, Gudauta, Sochi, Gelendzhik | 10, the whole red coast and the north | 10, the whole red coast and the north |
| Red aircraft at the start | 94, old types kept supplied by a sponsor (MiG-21, MiG-23, Su-25, Su-24M) | 186, mixed (MiG-31, MiG-29, MiG-23, Su-24M, Su-25, plus the Mozdok bombers and escorts) | 254, modern (MiG-31, MiG-29S, Su-27, Su-24M, Su-25, plus the Mozdok bombers and escorts) |
| Red SAMs | SA-2, SA-3, AAA, MANPADS | SA-2, SA-3, SA-6, SA-11, AAA | SA-10, SA-11, SA-6, SA-15, SA-19 |
| Air defence integration (`iads`) | 0.15 | 0.55 | 0.90 |
| Red AI skill | Average | Good | High |
| Bomber wing (Tu-22M3 at Mozdok) | none | 14, raids the carrier only when red is desperate | 24, raids the carrier as a normal part of its plan |
| Red counter-attacks on blue bases (`counterstrike`) | low (0.10) | 0.30 | 0.55 |
| Ground war pressure (`red_attack`) | 0.15 | 0.45 | 0.80 |

Blue is the same at every level: 18 squadrons with 284 jets in total across the coalition fields and the carrier (F-14B(U), F/A-18C, F-16C, F-15C
and A-10C squadrons, plus F-15E and HAVCAP squadrons and the F-117A squadron that the AI flies). A person can fly the F-14B(U),
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
   site, a garrison, a troop column), skips ones that cannot be attacked yet, and takes a few. How many jobs a turn
   gets follows the jets: the free strike pairs (the ones left after the standing patrols and the support) times a level share (0.6 at Levels 1 and 2,
   0.9 at Level 3), divided by the 5.7 pairs one package uses, at least 1 and at most 4, 8 and 8 on a day turn (Levels 1, 2, 3), plus two on every
   day turn of Day 1 ("day 1 is brutal"; `engine.py`: `TASK_SHARE`, `PAIRS_PER_PACKAGE`, `N_MAX`, `DAY1_EXTRA`). A night turn plans a quarter (Level 1)
   or a third (Levels 2 and 3) of that. It takes the best-scoring job of each kind first, and no one kind may take more than 40% of the
   list, with the SAM wave (section 5) taken out first. The F-117A's night jobs (section 5) come on top of that list.
   list.
4. **Packages are built from the jets that are free.** A package is crewed from what the ledger shows (section 7). A job
   that cannot be crewed waits for the next turn.
5. **Start times are set in two waves.** Wave 1 opens with the turn, wave 2 two hours later; packages start within about
   25 minutes of their wave's opening.

The jobs you can be offered are listed on the Missions tab: **Strike**, **Standoff Strike**, **OCA: Runway Strike**, **SEAD**,
**Standoff DEAD**, **Close DEAD**, **Close Air Support** (including **Troops in Contact**), **Fighter Sweep**, and **Intercept**
jobs against red's raids ("Base Defense", "Supply Defense", and so on). BARCAP is AI only. A job is shown only if your
squadron's jets can fly a seat in it. Each tasking can also bring extra flights: escort, TARCAP, SEAD.

### What a package looks like

A package is a set of flights with one target. The basic shapes (from `sqe/packages.py`):

| Job | Flights |
|---|---|
| Strike | 4 strikers, 2 SEAD if the target is under a SAM, TARCAP when red has fighters that can reach it |
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

**Package merging** (Settings > Mission build) folds packages whose targets are close together into one mission, each
still keeping its own time on target. The unit limit trades detail for performance.

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
farms change sides with their stock. The next push then waits for the takeover (9 days) and red's own attacks wait 3.

### The Force Index

The **Force Index** is how well supplied each side is, shown as a percentage on the Overview (Force Index tab) with a band: bad at 65% or
less, alright from 66 to 90, good above 90. It is the stock each side holds in fuel farms, depots and road **supply sites**, compared with what
it started with: from 35% (nothing left, the floor for both sides) to 100%. Replacement SAM batteries on their way cost a side some of it, even below the floor.
Red on Level 1 is counted differently in a new campaign: 70% of the figure is its inner sites' stock and 30% its road sites', and it never drops below 45%
(the insurgents are resupplied across the border by night). Capturing a site moves it and its stock to the captor.

The Force Index sets the pace of nearly everything that rebuilds:

* **Reinforcements** of the ground forces in each sector scale with it.
* **Jet replacements:** a squadron below strength gets a replacement pair every 24 hours divided by the Force Index (every 24 hours at 100%, about 69 hours
  at the 35% floor). The Tu-22M3 and the E-3 are the exception (section 7).
* **Site repair:** a damaged or destroyed supply site mends by the Force Index divided by 6 of a full site each night, so a destroyed one is back in 6 days
  at 100% and about 17 days at the 35% floor. A site that was struck that night does not mend.
* **Limping jets** take twice as long to refit, scaled by the Force Index.

Red's road sites are extra supply sites scattered along the roads (15 at Level 1, 30 at Levels 2 and 3), some guarded,
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

### Runways

A runway strike that lands its bombs **craters the field**: nothing launches from it, scrambles or lands there for 6
turns (24 hours). A closed field's squadrons cannot fly from it and red's wings skip it.

### Red's air

Red flies standing **CAP pairs** over its fighter fields, **Fighter Sweeps** where the sector is contested, and **raids** on you.
It holds back **25%** of each squadron's ready fighters as a **reaction reserve** that is the only source of scrambles and
reinforcements; the rest are free for patrols and raids. Jets that fly go to refit; shot-down jets are gone until replaced.

**How red's jets are laid out.** Each level gives every red field a fixed number of jets, sized to the field's parking. At Level 3 a field is filled to
about 70% of its parking, which leaves room for squadrons that fall back from a lost field (about 30%). Level 2 has 75% of Level 3's jets at each
field, and Level 1 fills its four fields to about 70% (Gelendzhik about 60%). (These are the Caucasus figures; Syria's are in section 10.) The jets are grouped into squadrons of a few types per field, up to 6 jets at
Level 1, 12 at Level 2 and 14 at Level 3 (about 10 to 12 is the Soviet and Russian norm), so a field flies one or two types in full squadrons, not
two or three jets of everything. The Forces screen lists them with in-universe names such as "Sochi-Adler MiG-21Bis Sqn #2"; a squadron that withdraws keeps its name.

A **raid** is a package that red actually plans: a Su-24M strike on a field, a supply site, a garrison or a
troop column, with escorts. Whether a raid goes in depends on whether red has the jets: nothing is rolled once you click
Fly. Some raids are **unwarned** (25%, 35% and 45% at Levels 1, 2, 3) and come with no warning. Blue sees a raid when an AWACS
(the E-3 or the E-2C) is on orbit that turn; with none up it still sees one in a quarter of cases. A raid blue does not see
is not listed as an Intercept job and is settled by the war simulation against blue's planned patrols alone.
Red's **SEAD raids** go after blue's Patriot and HAWK sites with anti-radiation missiles: a full Patriot is attacked
by three packages, a HAWK by two, escorted and preceded (at Levels 2 and 3) by a fighter sweep that tries to draw
blue's fighters away.

At Levels 2 and 3 the **Tu-22M3 bomber wing at Mozdok** can raid the carrier, after a quiet day, and then not again for 8 days (5 when it is desperate). At Level 3 red sends it when it
estimates a window it judges safe or when it is desperate; at Level 2 only when desperate (red's air arm or command structure is badly
hurt, or Mozdok is under pressure). This raid is
a flown set piece: the SEAD packages that clear its approach fly in the turn before.

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
* **Idle surge.** If you keep skipping turns that had a flight you could have flown, red presses harder. Each such skipped
  turn counts one; a flown sortie resets the count to zero, and a turn with nothing for you to fly (a stand-down turn) is not
  counted. The first 12 counted turns (two days' worth) are free. Past that, red's reinforcements, attack chance and raid rate
  grow for each further day's worth of skipped turns (`red_surge`: 3% at Level 2, 8% at Level 3, none at Level 1). The **Tactical Edge** switch of a campaign (New Campaign: "your sorties affect the war") turns this off together with the Tactical Edge itself.

---------------------------------------------------------------------------------------------------

## 7. Squadrons, jets and the ledger

Each blue squadron has jets *authorised*, *available* (ready now) and some in **refit** or **reserve**.

* A jet that flies a package or patrol lands and goes to **refit**: 3 hours as standard (the rugged A-10C and Su-25 take 2;
  the Tu-22M3 and E-3 take 8, the F-117A 16). A sortie lasts about 100 minutes, so a jet from the first wave is ready for the next turn's
  second wave, not its first. A jet that comes back damaged ("limping", under 90% health) takes twice as long to refit.
  A jet that was shot down is gone.
* **Replacements** arrive as a pair every 24 hours at a Force Index of 100% (slower below that, see the Force Index). The Tu-22M3 and the E-3 are replaced one airframe every
  48 hours and the F-117A one every 96 hours, regardless of the Force Index.
* A planned turn draws its jets from the **ledger**: the jets ready now plus those that will be ready by the second wave.
  Standing patrols and guards are taken off first, packages after, so patrols and strikes compete for the same jets. A job
  that cannot be crewed from what is left waits.
* A squadron whose base falls moves to the nearest field with room, losing 30% of its jets, and sits out the move
  (3 or 6 turns).
* **Your own squadron** can be picked at any time; the planner offers you the jobs it can crew, and after a flown
  sortie your flight's losses and survivors are booked the same way as any other.

---------------------------------------------------------------------------------------------------

## 8. Standing cover: BARCAP, the AWACS, the tankers and their guards

* **BARCAP** is blue's patrol over the areas that face red's launch points. Each turn a share of the areas that a squadron can
  reach gets a pair (Level 3: 60% by day, 20% at night; Level 2: 40% and 16%; Level 1: 20% and 10%). A long-legged pair
  holds the whole turn; a short-legged pair is relieved in the second wave. Strike packages carry the BARCAP that faces
  their target while they fly; BARCAP is AI only.
* **The AWACS and the tankers are assets, not freebies.** Blue has 4 E-3s (12 hours on orbit, 6 refit), 4 E-2Cs (4 hours on
  orbit, 6 refit), 8 KC-135s (4 hours on orbit, 3 refit) and 8 S-3Bs (2 hours, 3 refit). A package gets the AWACS and a tanker
  only if one is on orbit while it flies: a jet with a boom gets a KC-135, a probe-and-drogue jet (F-14, F/A-18C) the carrier's
  S-3B. A lost airframe is replaced slowly. Today the war sim does **not** take AWACS losses on its own (`AWACS_LOSS_ON` is off).
* **Each of them has its own guard (HAVCAP).** One pair of fighters guards the E-3, the E-2C and the tanker for as long as the
  asset is on orbit in the turn, flown by the HAVCAP squadron where there is one and by an ordinary fighter squadron otherwise.
  Every package that carries the asset carries its guard. The pair can refuel on the orbit.
* **The AWACS sits on one fixed safe station** (behind the front, from the rear base: Kutaisi on the Caucasus, Paphos on Syria), not near you or your target. The tanker sits
  forward on the way home, clear of SAM rings and red's scramble circles.

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

## 10. Syria 2000 (Operation LEVANT HORIZON)

The second map. You choose the map in the New Campaign dialog; a Syria campaign needs the DCS Syria map. Everything in sections 1 to 9 works the same there (the same turns, packages, Force Index, refit and ledger); this section is what is different. The Caucasus pages above give the Caucasus numbers; the numbers here are the Syria pack's (`sqe/data/theatres/syria.json`), as of v0.41.518.

### The war

It is June 2000 (the campaign starts on 12 June, at **00:00**). A US-led coalition has answered Turkey's request for help and fights its way down the **Hatay coast road** into Syria. Blue flies from **Incirlik**, from Akrotiri, Larnaca, Paphos and Muwaffaq Salti (Hatay is a recovery field only), and from the carrier **USS Dwight D. Eisenhower**, which sits north of Cyprus (160 nm from the Syrian coast). Red holds the Syrian airfields. The front is the coast road from Hatay through **Bassel Al-Assad**, **Rene Mouawad** and **Shayrat**, and the level decides how much of it is fought over: Level 1 contests Bassel Al-Assad only, Level 2 adds Rene Mouawad, Level 3 adds Shayrat. The deep rear (Hama, Abu al-Duhur, Tiyas, Palmyra, Sayqal, Damascus, Al-Dumayr, An Nasiriyah) is where the long-range air defence and the bomber wing sit.

Who you fight depends on the level: Level 1 is **the Northern Coastal Command** (the NCC, an insurgent force), Level 2 is **Syria**, Level 3 is **Syria and its Russian backers**.

### The three levels in Syria

| | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| Red airfields | 4: Bassel Al-Assad, Abu al-Duhur, Hama, Shayrat | 11, the whole coast road and the interior | 11 |
| Red aircraft at the start | 94 (MiG-21Bis, MiG-23MLD, Su-17M4, Su-24M) | 202 (adds MiG-29A and MiG-25PD) | 238, plus the bomber wing (MiG-23MLD, MiG-29A and S, MiG-25PD, Su-27, MiG-31, Su-17M4, Su-24M) |
| Red SAMs | SA-2, SA-3, AAA, MANPADS | SA-2, SA-3, SA-6, SA-11, AAA, two SA-5 batteries | SA-10, SA-11, SA-6, SA-15, SA-19, three SA-5 batteries |
| Air defence integration, red counter-attacks, ground pressure | as in section 2 (0.15 / 0.10 / 0.15) | 0.55 / 0.30 / 0.45 | 0.90 / 0.55 / 0.80 |
| Tu-22M3 bomber wing | none | none | 16 Tu-22M3 with 12 Su-27 escorts at Damascus |
| Victory | take Bassel Al-Assad | red's supply collapses (see below) | red's supply collapses |

Red's jets fill each field's parking to about 75% at Level 1 (four small fields), about 60% at Level 2 (85% of Level 3's fill: a regional power) and about
70% at Level 3 (Damascus is held back for the bomber wing).

Red's raids on troops, garrisons and supply sites are led by the cheap **Su-17M4** attack jet. At Level 3 the Tu-22M3 wing raids the carrier along the line from the carrier through Damascus, at most 12 bombers at a time, flown as a set piece with its SEAD in the turn before, as in section 5.

### Blue in Syria

Blue has 18 squadrons and 284 jets at every level: two F-14B squadrons and two F/A-18C squadrons on the carrier, five F-16C, three F-15C (plus the AI-only HAVCAP F-15C), three F-15E (AI only), one A-10 squadron at Incirlik and the **8th FS 'Black Sheep' (12 F-117A, AI only)**. You can fly the F-14B, F/A-18C, F-16C, F-15C and A-10. The **Era Equipment** setting (New Campaign) picks the airframes of the year: Syria 2000 defaults to the A-10A, the F-14B and no Link 16 data.

### The opening night

The campaign starts at midnight, in the middle of a surprise attack. At Levels 2 and 3 the 12 **F-117A Nighthawks** of the 8th FS have just struck as six pairs, one pair per target: every long-range **SA-5** battery first (Homs and Damascus, and Tiyas at Level 3), then the deepest radars (Level 2: the four deep early-warning radars) or, at Level 3, some SA-10 sites and radars. The war log names every site and the pair that hit it. The sites are rebuilt by the normal rule (5 to 7 days, at half strength), so the opening is a window, not a won air war: the rest of the network, the fighters, and the SAM belt at the front are all still up. Level 1 has no opening strike.

The Nighthawks themselves start the war on their way home to Incirlik (the Overview squadron table says "returning", then "refitting"), land at about
00:40 to 00:50 and spend a 16-hour refit, so none of them is ready on the opening night; they are back for the 20:00 night turn of Day 1, and from
then on the squadron flies as described in section 5. You do not fly it; you will see its strikes in the war log and in the sites that fall.

### Winning and losing in Syria

* **Level 1:** victory is the ground war, as in section 6: take **Bassel Al-Assad**.
* **Levels 2 and 3:** no ground victory. The war is won when **red's Force Index** (its supply, section 5) has been at or below 40% for **three nights in a row**. The Overview shows how close it is in a word (distant, approaching, close, under way). That is the depots, fuel farms and road sites, not the cities: the coalition's stated intent is to break Syria's supply and air defence.
* **Defeat:** the coalition's air component below 15% of its strength (as in section 6), or **one** airfield of yours lost (the Caucasus allows three).

### Long-range air defence

The SA-5 is the new problem. A battery at Shayrat reaches over the whole coast from high altitude (the planner is altitude-blind: it treats the ring as reaching every altitude), but it cannot touch a flight low down: measured in DCS, its reach is about 65 nm at high altitude, about 20 nm at 5,000 ft and nothing at 500 ft. The SA-10s (Level 3) are the same kind of problem at shorter range. Standoff jobs, HARM shooters and the Nighthawks are how the belt is opened.

---------------------------------------------------------------------------------------------------

## 11. Still evolving

SQE is still being developed, and the rules on this page may change from one version to the next. The change log
(`docs/CHANGES.md`) says what each version did. If something in a mission behaves differently from this page, or you
find a bug, please report it at https://github.com/MarkuzJuniuz/SQE/issues/new.
