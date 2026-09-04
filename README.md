# SEED

A space incremental game where everything you own is partly a machine that builds
more machines. Local, offline, Windows, Python + Tkinter.

## Play it

Needs **Python 3.10+** on Windows, with Tkinter (included in the standard
python.org installer). No other dependencies, no internet, nothing to build.

```bash
git clone https://github.com/Bruhiann/incremental.git
```

Then double-click **`SEED.bat`**, or from a terminal in the project folder:

```bash
py run.py
```

If `py` is not found, use `python run.py`. (On the machine this was developed on,
the bare `python` command is the Microsoft Store alias stub and does not resolve,
which is why `py` is the default here.)

## Your save and your world are your own

Nothing about your progress lives in this repository. On first launch the game
creates a save in your own Windows user folder and rolls a **world seed** unique
to you, so everyone who clones this starts a different world and plays their own
game. Pulling updates never touches anyone's progress.

Your world seed is shown on the **Stats** tab. If you want to race a friend from
an identical start, both of you can delete your save and enter the same seed —
type a number or any words you like, and the same seed produces the same luck
(anomalies, artifact rolls, expedition results). Leave it blank to get a random
world.

## Where your save lives

```
%LOCALAPPDATA%\SEED\savegame.json
%LOCALAPPDATA%\SEED\savegame_backup.json
```

Autosaves every 30 seconds, on close, and on every Dispersal. Writes are atomic:
a temp file is written, fsynced, re-read to verify it parses, and only then
swapped in, with the previous save rotated to the backup. A corrupt main save
falls back to the backup; a corrupt backup falls back to a new game **without
deleting either file**. Deleting your save requires typing `DELETE`.

**There is no offline progress.** Time between sessions is recorded for
statistics only. Close the game and production stops.

## How it works

**Two ladders.** *Extraction* (E1 Regolith Scraper → E8 Stellar Siphon) makes
resources. *Replication* (R1 Fabricator Arm → R4 Seed Ship) makes machines — each
tier builds the tier below it, and R1 builds Regolith Scrapers for free forever.

**One rule ties them together:** each Replication tier multiplies every
Extraction tier, weighted toward the lower ones. It is logarithmic, so a count of
1e20 gives about x4 rather than x1e20 — that damping is the brake that keeps
machines-building-machines on a curve instead of detonating.

**Purchased vs. total count.** Cost and the "every 10 owned" bonus use what you
*bought*; production uses what you *have*. Free units from the swarm therefore
never inflate prices or run away with the multiplier.

**Power is a throttle, not a stockpile.** If demand exceeds supply, everything
except power generation runs at `supply / demand`, floored at 10%. Power
generators are never throttled — otherwise a brownout would be unrecoverable.

**Alloy** is the prestige metric. Refineries capture a fraction of your Ore
income, so Alloy rides your growth instead of being capped separately.

**Dispersal** (prestige 1) resets machines, resources and this run's upgrades;
keeps Research, artifacts, milestones, achievements and Seed Points. The Alloy
bar rises as you bank Seed Points, so a run always has to mean something.
Dispersals also unlock content: Forge Spiders and Exploration after the first,
Starlift after the second, Seed Ships after the third.

**Convergence** (prestige 2) unlocks at 20,000 lifetime Seed Points and wipes
everything Dispersal does *plus* Seed Points, the Seed Grid and all Research. It
grants Coherence and unlocks four things: **Nanite Mass** (a resource that
compounds in proportion to itself, with a deliberately logarithmic bonus so the
number runs away but the balance does not), **Doctrines** (five rows of three
mutually exclusive branches, free and switchable at any time, and kept through a
Convergence so no choice is a regret), **auto-Dispersal**, and an endless Coherence shop.

**Overwrite** (prestige 3) becomes visible at 150 lifetime Coherence and wipes
the whole Convergence era — Coherence, the Coherence Nodes and Exotic Matter —
on top of everything Convergence resets. It is a different *kind* of layer:
**Overwrite Charges come from your peak Alloy per second, never from a lifetime
total**, so waiting earns nothing and only a better engine does. Charges buy
**Floors** — permanent starting states, so a fresh Dispersal begins with hundreds
of machines already running and the early game stops being something you replay.
It also unlocks Exotic Matter, the Black Hole Tap, the Hive Ark, a Persistent
Archive that carries Research through Convergence, and auto-Convergence.

**Substrate Collapse** (prestige 4) wipes the Overwrite era and changes the verb.
By here every multiplier you own is astronomical, so another one is noise:
Substrate buys **exponents**. Production is raised to a power, and +0.002 sounds
like nothing until you notice it adds `0.002 x log10(your multiplier)` — against
a multiplier of 1e400 that is worth more than a hundred x10s. The crossover is
real and the game tells you where it is. It also unlocks a Cached Genome that
carries the Seed Grid through Convergence, and auto-Overwrite.

**Recursion** (prestige 5) wipes the Substrate era — your Substrate, the Lattice
and everything under it — and changes the verb one last time. The first four
layers sold you upgrades, choices, floors and exponents. Recursion sells
**difficulty**: you pick a depth and descend into a deliberately worse copy of
the universe, because the worse it is, the more it pays.

Depth makes every machine's costs scale harder, and named handicaps stack on top
as you go deeper — Hungry Machines at 3, Early Defection at 5, Dead Frame at 8,
Silent Sky at 12, Sterile at 15, Starved at 22, Diminished at 30. Every one of
them is listed on screen while it is doing it to you. **They hit costs, never
your exponent**, because production up here is hyper-exponential and a handicap
on the exponent is not difficulty, it is deletion.

You clear a depth by earning enough Alloy inside it, and the payout scales with
**how deep you went and how fast you cleared it** — the first mechanic in the
game that rewards playing rather than waiting. It pays the moment you clear,
not when you next reset. Depth buys the **Stack**: a Compiled Start, a Retained
Exponent that carries part of your Substrate through the wipe, a Standing Army
that carries part of your fleet, Shallow Water that makes every depth a little
gentler, E11 and R8 at the top of both ladders, and Standing Recursion Orders.

Depth is unbounded. That is the endgame.

## The Defection

You built self-replicating machines. From your first Overwrite, some of them
stop answering.

Every other system in SEED only adds. The Defection is the one that can take
something back, and it exists to pose the one decision an economy cannot: the
**Defence ladder produces nothing at all**. Sentry Drones, Picket Cruisers,
Lance Frigates, Bastions and Nemesis Hulls draw power, eat upkeep, and make no
Ore, no Alloy and no machines. Choosing how much of your wealth to park in them
is the mechanic.

An incursion is a race rather than a dice roll: it has HP, your fleet has damage
per second, and killing it sooner costs you less. There is no cliff anywhere on
that curve — a fleet at 90% of what it needs still wins, slightly more expensively.
What it demands is always **a share of your bank**, so it scales with you forever
and can never become impossible.

What it can take is machines, and nothing else. Not prestige currency, not
upgrades, not research, not relics, not your power plants, not your fleet, and
never below the floor your Overwrite and Substrate levels grant you. Losses come
out of purchased counts too, so a loss costs you time rather than money. Every
one of those limits is a test.

Winning pays salvage, relics pulled out of the wreck, and a permanent global
multiplier that grows with your war record. The very first incursion is scripted
and cannot be lost.

Every shop — machines, the Seed Grid, the Coherence Nodes, the Floors, the
Lattice and the Stack — has the same
**Buy 1 / 10 / 25 / Max** control, and all of them price bulk purchases with a
closed-form geometric series rather than a loop.

**Automation** arrives as a reward, never as a given: Fabricator Arms (minute 5)
→ per-machine auto-buy with spending reserves (Foreman research) → auto-Research,
auto-Upgrades, auto-Relics and auto-Expedition (Seed Grid nodes) → auto-Dispersal
and auto-Seed-Grid (Coherence nodes) → Standing Defence Orders, which keeps the
fleet a margin ahead of the next incursion so you stop watching the bar →
Standing Recursion Orders, which descends a depth further every time it clears.
The Seed Grid and Dispersal pair together make the whole
Dispersal layer hands-off: it resets itself and spends the Seed Points itself. Auto-spending never touches your reserve, whatever it is
buying, and every automatic purchase goes through the same code path you do.

**Relics have two axes.** *Rarity* (Common → Cosmic) says how strong one is;
a *mutation* (Shiny, Mutated, Alien, Ancient, Entangled, Singular) says how
strange it is and multiplies the bonus it carries. They roll independently, so a
Singular Common beats a plain Rare and low-rarity drops stay worth reading.

**The Crucible** fuses three spare relics of one rarity into one of the next
rarity up, keeping the strangest mutation that went in. It never consumes a relic
you have slotted, or one the ranking would slot — that guarantee is enforced in
the selection itself, not checked afterwards. It also solves the long-game
problem where a Common drop is dead loot once you own something better: now every
drop is progress toward the next tier, and Cosmic is reachable by effort as well
as by a 0.1% roll. Unlocked by the Transmutation research; the Automatic Crucible
Seed Grid node runs it for you.

Relics are ranked by `log10(multiplier) x weight`, so scores add the way
multipliers compose and the top-scoring set really is the best one. Weights
reflect what actually moves your bottom line — a global bonus outranks a Data
bonus, and a Power relic is scored against your current throttle, so it is worth
almost nothing at full supply and a lot while you are throttled. The Exploration
tab has a free "Slot my best relics" button; the Curator Protocol Seed Grid node
does it for you continuously.

## Development

```bash
py -m unittest discover -s tests -t .   # 366 tests, headless
py tests/smoke_ui.py                    # builds the real window and drives it
py -m seed.balance 4                    # simulate 4 hours, print pacing tables
```

`gamedata.py` holds all content as declarative tables — balancing is editing rows,
not code. `engine.py` holds all logic. `ui.py` computes nothing; it formats what
the engine derived, which is why the balance simulator and the game are
guaranteed to be the same economy.

See `ARCHITECTURE.md` for the design and `BALANCE.md` for tuning findings.

## For your friends: what "download and play" looks like

1. Install Python from python.org (tick *Add Python to PATH*).
2. Download this repo (green **Code** button → *Download ZIP*) and unzip it,
   or `git clone` it.
3. Double-click `SEED.bat`.

They get their own save and their own world seed. Nothing is shared between
players unless you both deliberately pick the same seed.

## Package as an .exe (Phase 8)

```bash
py -m pip install pyinstaller
```

```bash
py -m PyInstaller --onefile --windowed --name SEED --clean run.py
```

The result is `dist\SEED.exe`. It reads and writes the same
`%LOCALAPPDATA%\SEED\` folder as the script version, so moving or replacing the
exe never touches your progress.
