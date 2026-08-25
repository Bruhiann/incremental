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
mutually exclusive branches, free and re-picked at every Convergence so no choice
is a permanent regret), **auto-Dispersal**, and an endless Coherence shop.

Every shop — machines, the Seed Grid and the Coherence Nodes — has the same
**Buy 1 / 10 / 25 / Max** control, and all of them price bulk purchases with a
closed-form geometric series rather than a loop.

**Automation** arrives as a reward, never as a given: Fabricator Arms (minute 5)
→ per-machine auto-buy with spending reserves (Foreman research) → auto-Research,
auto-Upgrades, auto-Relics and auto-Expedition (Seed Grid nodes) → auto-Dispersal
(a Coherence node). Auto-spending never touches your reserve, whatever it is
buying, and every automatic purchase goes through the same code path you do.

Relics are ranked by `log10(multiplier) x weight`, so scores add the way
multipliers compose and the top-scoring set really is the best one. Weights
reflect what actually moves your bottom line — a global bonus outranks a Data
bonus, and a Power relic is scored against your current throttle, so it is worth
almost nothing at full supply and a lot while you are throttled. The Exploration
tab has a free "Slot my best relics" button; the Curator Protocol Seed Grid node
does it for you continuously.

## Development

```bash
py -m unittest discover -s tests -t .   # 196 tests, headless
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
