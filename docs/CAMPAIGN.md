# How the SQE campaign works

What the war is, what happens each turn, and the rules behind it. For installing and running SQE see `docs/GUIDE.md`
(section 4 there is the short "how a turn works"); for adding a map see `docs/THEATRES.md`.

Written from the code as of v0.41.430. **Nothing here has been checked in a flown mission unless a line says so**; the
last section lists what is newest and still unproven. Numbers are tuning values in the code and change between versions:
where one matters it is named, so you can find it. Several are the author's judgment calls with no public source, and
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

The map is the Caucasus. The coalition (blue) holds the south-east (Senaki, Kutaisi, Kobuleti, a carrier group at sea and
the rear support base at Kutaisi); red holds the north and the Black Sea coast (Sukhumi, Gudauta, Sochi, Gelendzhik,
Krymsk, and the northern fields such as Mozdok, Beslan, Nalchik, Maykop and Mineralnye Vody).

---------------------------------------------------------------------------------------------------

## 2. The three levels

You pick the level when you start a campaign. It sets how strong red is and how it fights (`sqe/difficulty.py`).

| | Level 1, Insurgent | Level 2, Regional power | Level 3, Near-peer |
|---|---|---|---|
| Red aircraft at the start | 44, old types (MiG-21, MiG-23, early MiG-29, Su-25, Su-24M) | 128, mixed (MiG-31, MiG-29, MiG-23, Su-24M, Su-25) | 256, modern (MiG-31, MiG-29S, Su-27, Su-34, Su-25) |
| Red SAMs | SA-2, SA-3, AAA, MANPADS | SA-2, SA-3, SA-6, SA-11, AAA | SA-10, SA-11, SA-6, SA-15, SA-19 |
| Air defence integration (`iads`) | 0.15 | 0.55 | 0.90 |
| Red AI skill | Average | Good | High |
| Bomber wing (Tu-22M3 at Mozdok) | none | 14, raids the carrier only when red is desperate | 24, raids the carrier as a normal part of its plan |
| Red counter-attacks on blue bases (`counterstrike`) | low (0.10) | 0.30 | 0.55 |
| Ground war pressure (`red_attack`) | 0.15 | 0.45 | 0.80 |

Blue is the same at every level: 17 squadrons with 272 jets in total across the coalition fields and the carrier (F-14B(U),
F/A-18C, F-16C, F-15C and A-10C squadrons, plus F-15E and HAVCAP squadrons that the AI flies). A person can fly the F-14B(U),
F/A-18C, F-16C, F-15C and A-10C; the F-15E is AI only. You can change the AI skill of each side in Settings.

---------------------------------------------------------------------------------------------------

## 3. The clock

* A **turn is 4 hours**. Six turns a day. Day 1 starts at 08:00, so it has four turns (08, 12, 16, 20).
* Turns that start at 20:00, 00:00 and 04:00 are **night turns**. With night operations off, nothing is planned for a
  night turn and the war resolves it by itself.
* One thing moves the clock: **Skip Turn** or a flown sortie. Either one is exactly one turn forward (a flown mission
  does not skip ahead to the end of the day).
* The war resolves a turn's unflown packages when the clock moves. At midnight the daily steps run: supply and repair,
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
   gets is a level value (`PACKAGES_PER_TURN`: 2, 3, 3 on a day turn at Levels 1, 2, 3, plus two on every turn of Day 1,
   "day 1 is brutal"). It takes the best-scoring job of each kind first, and no one kind may take more than 40% of the
   list.
4. **Packages are built from the jets that are free.** A package is crewed from what the ledger shows (section 7). A job
   that cannot be crewed waits for the next turn.
5. **Start times are set in two waves.** Wave 1 opens with the turn, wave 2 two hours later; packages start within about
   25 minutes of their wave's opening.

The jobs you can be offered are listed on the Missions tab: **Strike**, **Standoff Strike**, **Runway Strike**, **SEAD**,
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
| Fighter Sweep | 4 sweepers, 2 strikers (the sweep is for local air superiority) |
| Intercept (raid) | the fighters that cover what red is raiding |

The TARCAP (up to 4 jets) is sized to the fighters red can field near the target. Where red has more than that, the package
gets an escort as well, or a separate Fighter Sweep is planned ahead of it. A **Standoff** job (a site under a long-range SAM such as the SA-10) uses JSOWs,
SLAM-ERs or similar weapons released far outside the SAM's reach, with HARM shooters timed on the same minute.

**Package merging** (Settings > Mission build) folds packages whose targets are close together into one mission, each
still keeping its own time on target. The unit limit trades detail for performance.

---------------------------------------------------------------------------------------------------

## 5. How red and blue fight

### The ground war

The front is a chain of sectors, one per airfield from Krymsk to Kutaisi, each with a red and a blue **force strength**.
Each night the sectors in contact exchange losses (the defender fights at ×1.25, `DEFENDER`); a side under 30% of the
other's force in a sector withdraws from it (`BREAK_RATIO`) and nobody is hunted to the last unit. Both sides get
reinforcements, scaled by their **supply**, and a dug-in **garrison** in each sector gives its side a bonus and a CAS target.

Blue's CAS and strike work lowers red's force in a sector and weakens its supply; red's raids do the same to blue. When
blue holds a sector in front of a red airfield and red has nothing organised there, **the airfield falls**: it and its
ground units go down for good, its jets withdraw to the nearest standing red field with 30% lost, and its depots and fuel
farms change sides with their stock. The next push then waits for the takeover (9 days) and red's own attacks wait 3.

### Supply and the Force Index

**Supply** is the stock each side holds in fuel farms, depots and road supply sites compared with what it started with, from
0.35 (nothing left) to 1.0. It sets how fast the side reinforces and replaces jets: a squadron gets a replacement pair every
24 hours divided by the supply figure. Sites repair a little each night unless they were hit that night. Capturing a site moves
it and its stock to the captor. Red's road sites are extra supply sites scattered along the roads (15 at Level 1, 30 at Levels 2 and 3), some guarded,
some a parked truck only.

### Air defence

Red's SAM sites are **suppressed** (their radars blinded by SEAD) for two turns, then recover, or **destroyed** by DEAD. A
destroyed site is rebuilt later by red's supply, and mobile sites move after being hurt. A **belt** of overlapping long-range
sites protects what is behind it: a site inside an intact belt cannot be offered as a target until the belt site covering
it falls.

The planner runs **SAM waves** on the first turns: a fixed number of SAM jobs each turn (Level 3: two on the sea side, one on the
mountain side, one runway crater; Level 2: two, two, one; Level 1: one). The SEAD stages of a turn go in at least five
minutes apart, nearest first. Two axes are kept apart. The **mountain axis** is red's northern fields (Mozdok, Beslan, Nalchik, Maykop,
Mineralnye Vody, Krymsk, Gelendzhik): the waves go after their SAMs, EWRs and runways to take away red's air power, and this
is the only thing that moves it. The **sea axis** (Sukhumi, Gudauta, Sochi) is where the ground war is fought. There are no
depth tiers: any target that is not blocked by an intact belt can be offered on any turn.

### Runways

A runway strike that lands its bombs **craters the field**: nothing launches from it, scrambles or lands there for 6
turns (24 hours). A closed field's squadrons cannot fly from it and red's wings skip it.

### Red's air

Red flies standing **CAP pairs** over its fighter fields, **Fighter Sweeps** where the sector is contested, and **raids** on you.
It holds back **25%** of each squadron's ready fighters as a **reaction reserve** that is the only source of scrambles and
reinforcements; the rest are free for patrols and raids. Jets that fly go to refit; shot-down jets are gone until replaced.

A **raid** is a package that red actually plans: a Su-24M or Su-34 strike on a field, a supply site, a garrison or a
troop column, with escorts. Whether a raid goes in depends on whether red has the jets: nothing is rolled once you click
Fly. Some raids are **unwarned** (25%, 35% and 45% at Levels 1, 2, 3) and come with no warning. Blue sees a raid when an AWACS
(the E-3 or the E-2C) is on orbit that turn; with none up it still sees one in a quarter of cases. A raid blue does not see
is not listed as an Intercept job and is settled by the war simulation against blue's planned patrols alone.
Red's **SEAD raids** go after blue's Patriot and HAWK sites with anti-radiation missiles: a full Patriot is attacked
by three packages, a HAWK by two, escorted and preceded (at Levels 2 and 3) by a fighter sweep that tries to draw
blue's fighters away.

At Levels 2 and 3 the **Tu-22M3 bomber wing at Mozdok** can raid the carrier, at most once a day. At Level 3 red sends it when it
estimates a window it judges safe or when it is desperate; at Level 2 only when desperate (red's air arm or command structure is badly
hurt, or Mozdok is under pressure). This raid is
a flown set piece: the SEAD packages that clear its approach fly in the turn before.

### Blue's air

Blue has a standing patrol system of its own (next section). It also scrambles alert pairs against raids and, if
the carrier is sunk, its aircraft are moved to land fields (any that cannot be parked are lost).

---------------------------------------------------------------------------------------------------

## 6. Winning and losing

* **Victory** is by the ground war only: you take **Sochi** (Levels 1 and 2) or **Sochi and Krymsk** (Level 3). At Levels 2 and
  3 the red counter-force that arrives must also be beaten. Jet counts alone do not win the war.
* **Defeat** is either of: the coalition's air component falls below 15% of its authorised strength, or **3 of your airfields
  have fallen**. A sunk carrier does not count as a fallen field (its aircraft land elsewhere; the carrier group sails back in after 7
  days).
* **Idle surge.** If you keep skipping turns that had a flight you could have flown, red presses harder. Each such skipped
  turn counts one; a flown sortie resets the count to zero, and a turn with nothing for you to fly (a stand-down turn) is not
  counted. The first 12 counted turns (two days' worth) are free. Past that, red's reinforcements, attack chance and raid rate
  grow for each further day's worth of skipped turns (`red_surge`: 3% at Level 2, 8% at Level 3, none at Level 1). The Pilot Influence setting turns this off.

---------------------------------------------------------------------------------------------------

## 7. Squadrons, jets and the ledger

Each blue squadron has jets *authorised*, *available* (ready now) and some in **refit** or **reserve**.

* A jet that flies a package or patrol lands and goes to **refit**: 3 hours as standard (the rugged A-10C and Su-25 take 2;
  the Tu-22M3 and E-3 take 8). A sortie lasts about 100 minutes, so a jet from the first wave is ready for the next turn's
  second wave, not its first. A jet that comes back damaged ("limping", under 90% health) takes twice as long to refit.
  A jet that was shot down is gone.
* **Replacements** arrive as a pair every 24 hours at full supply. The Tu-22M3 and the E-3 are replaced one airframe every
  48 hours, regardless of supply.
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
* **The AWACS sits on one fixed safe station** (behind the front, from Kutaisi), not near you or your target. The tanker sits
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

## 10. Newest and not yet flown

Built, compiled and probed, but not yet seen in a flown mission as of this version; treat the behaviour as unproven.

* The **HAVCAP guard for every package that carries an AWACS or tanker** and the S-3B tanker's guard (v0.41.429).
* Red's **fighter sweep ahead of red SEAD raids** and Level 2 SEAD escorts at 1:1 (v0.41.427).
* **Stand-off EWR strikes** (JSOW, SLAM-ER) and **runway strikes with plain Bombing tasks along the runway** (v0.41.428).
* The **SAM waves** and the removal of the old depth tiers (v0.41.367 to v0.41.371).
* Red's **Patriot raids as three packages**, and Kh-59M stand-off raids.
* The Level 3 **Su-34**, the **F-15E** and the new squadron laydown.

If something behaves differently from this page in a flown mission, it is a bug in the page or in the code. The
change log (`docs/CHANGES.md`) says what each version did.
