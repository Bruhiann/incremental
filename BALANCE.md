# Phase 6 — Balance findings

Measured with `py -m seed.balance <hours>`, which drives the real engine under a
scripted player at ~280x real time.  Because the UI holds no logic, this is the
same economy the game runs.

## Five real bugs the simulation found

These were not visible from the design document or from unit tests — only from
watching hours of simulated play.

**1. Autocatalysis was an unbounded exponential.**
The upgrade "Fabricator Arms also build Fabricator Arms" made R1 self-feeding at
a rate multiplied by every other bonus.  Three simulated hours produced
`1.11e6650` Regolith Scrapers.  *Fix:* it now builds from **purchased** arms
only, which are cost-gated, so it is a strong bonus rather than a bomb.

**2. Power demand scaled with free units, pinning throttle at its floor.**
Because the swarm's own copies counted toward demand, the runaway above dragged
throttle to the 10% floor and held it there permanently.  Every shortage message
became a lie — there was no purchase that could fix it.  *Fix:* demand scales
with machines you **built**; the swarm brings its own power.

**3. The prestige metric was decoupled from the economy.**
Alloy came from refineries at a flat 25 Ore/s each, so while Ore exploded to
`1e6655`, Alloy crawled to 50B and Seed Point gain flatlined.  The player's
entire engine had no connection to the thing progress was measured in.  *Fix:*
refineries now capture a **fraction of Ore income** (3% each, stacking toward
100%), so Alloy rides the swarm.  This also makes the bottleneck legible: you
can see you are only refining 43% of what you mine.

**4. "Never reset" was mathematically optimal.**
With a power-law gain (`alloy ** 0.5`), Seed Points per second rose monotonically
forever, so the correct play was to never prestige — the entire prestige layer
was dead content.  Softcapping the exponent only flattened the curve into a
plateau, which is just as bad: every reset time is equally good, so timing has no
answer.  *Fix:* gain is now **logarithmic** —
`8 x (orders of magnitude past the bar + 1) ** 2`.  Seed Points per second now
peaks sharply, which is what makes "when do I reset?" a real question.  It also
keeps Seed Points in the hundreds-to-thousands range, where Seed Grid prices can
be hand-tuned and read at a glance.

**5. Prestige degenerated into a one-minute treadmill.**
With a fixed 1e6 Alloy bar, a strong player re-cleared it instantly and the game
became 100+ consecutive one-minute resets.  *Fix:* the requirement rises with the
Seed Points you already hold (`1e12 x (1 + lifetime SP) ** 0.5`), so the bar and
your power grow together.

## A pacing problem, and the fix

After the fixes above, the entire content set — all twelve machines, all research
— was consumed in **fifteen minutes**, after which nothing was left but numbers.
The cause was structural: with all four replication tiers live in the first run,
output grows like `t^6` and blows past every gate at once.

R3 (Forge Spider) is now gated behind your **first Dispersal**, R4 (Seed Ship)
behind your **third**, Exploration and Landfall behind the first, and Starlift
behind the second.  This halves the early exponent and, more importantly, makes
prestige hand out **content** rather than only multipliers — which is a better
reward anyway.

## Where it landed

| | |
|---|---|
| First Regolith Scraper | 7 s |
| First Solar Film | 2m 30s |
| First Fabricator Arm (first automation) | 4m 30s |
| First Alloy / Orbital Refinery | 45 s / 11 min |
| First Replicator | 11m 30s |
| **First Dispersal available** | **~17 min simulated** |
| Dispersals 2–5 | 8–14 min each |
| Dispersals 6–20 | 7–12 min, gently lengthening |

Every machine still contributes at the four-hour mark, throttle sits at 100% once
the player invests in power, and no tier falls below 1% of its resource's output.

## Deviation from the approved design document

The design doc targeted a **1.5–2.5 hour** first Dispersal.  It lands at ~17
minutes simulated (a human, buying far less aggressively than the script, should
see roughly 25–40 minutes).

This is deliberate.  The MVP's content is exhausted at around 20 minutes of play,
so a 90-minute first run would be more than an hour of watching a number rise
with nothing new to unlock — the "long periods where there is nothing to do" the
brief explicitly rules out.  The right way to reach a 1.5-hour first run is to
add content in Phase 7 and then stretch the bar to match, not to stretch the bar
now.  `P1_REQ_BASE` in `gamedata.py` is the single knob that does it.

## Known soft spots

- **Minutes 5–10 are the thinnest stretch of the game**: E3 and E4 are bought and
  Alloy has not started flowing yet.  Worth an extra early upgrade or two.
- The scripted player buys ~8 machines/second, so all times above are floors.
- Cadence past Dispersal 20 is untested beyond four simulated hours.

---

# Phase 7 — Early upgrades and Convergence

## Ten new early upgrades

Filling the 5–10 minute gap flagged above. They unlock at low machine counts
(E1 x5, E2 x5, R1 x3, E3 x3, E1 x30, E4 x3, E3 x8, E4 x5, E5 x3, E6 x5) and cost
between 60 and 55,000 Ore, so something is always within reach during the stretch
where Alloy has not started flowing yet.

## Convergence (prestige layer 2)

Wipes everything Dispersal does **plus** Seed Points, the whole Seed Grid, and all
Research. Grants Coherence, and unlocks Nanite Mass, Doctrines, auto-Dispersal and
an endless Coherence shop.

Gain uses the same logarithmic shape as Seed Points, for the same reason
established above: a power law never peaks against this economy, so reset timing
would have no answer.

**Doctrines** are 5 rows of 3 mutually exclusive branches (Swarm / Forge / Mind).
They are free and re-picked from scratch at every Convergence, so a wrong choice
is never a permanent regret — the design doc's problem 7.

## Three more bugs the simulation found

**6. `Cond.converge` was never checked.** Adding a field to the condition record
without adding a handler makes it read as *satisfied*, so every Convergence
milestone fired on a brand-new game — a fresh save silently carried a x500 global
multiplier. Fixed, and there is now a test that asserts every `Cond` field is
actually consulted, plus one asserting a new game has no unearned bonuses.

**7. Convergence was a treadmill too.** At the first-pass numbers it fired 13
times in five simulated hours, and because it wipes Research the player ended with
0/13 techs — permanently. The bar is now 2e5 lifetime Seed Points rising with
banked Coherence at `^0.85`, which puts the first Convergence at **3h 25m** and
leaves Research intact at 13/13.

**8. Nanite Mass never started.** It compounds in proportion to itself, so a
starting value of zero stays zero forever, and the Nanite Vat that seeds it was
too expensive to ever be bought in practice — the layer's flagship resource was
unreachable. Convergence now seeds 250 Nanites directly, and the Vat costs 1e7
Alloy instead of 1e9. It reaches ~1e43 over the following six hours.

Related: Nanites were being wiped by every Dispersal, which reset them to nothing
every ten minutes and made compounding impossible. They are now **layer-scoped** —
Dispersal leaves them alone, Convergence clears them. `LAYER_RESOURCES` in
`gamedata.py` declares this.

Nanites grow exponentially on purpose; their bonus is `(1 + log10(mass)) ** 0.6`,
so the number runs away while the balance does not (~x10 at 1e43, ~x64 after a
week of play).

## Where layer 2 landed

| | |
|---|---|
| Convergence tab becomes visible | 20,000 lifetime Seed Points |
| **First Convergence** | **~3h 25m simulated** |
| Dispersal cadence | 12–17 min, gently lengthening |
| Research at 10 hours | 13/13 (was 0/13 before the fix) |
| Nanite Mass at 10 hours | ~1e43 |

---

# Phase 7b — Auto-upgrades and relic curation

Both follow the established manual -> automated arc rather than being handed over
for free:

- **Standing Upgrade Orders** (Seed Grid, 90 SP) buys unlocked upgrades cheapest
  first, through the same `buy_upgrade` path the player uses, and never touches
  the spending reserve.
- **Curator Protocol** (Seed Grid, 150 SP) keeps your best relics slotted.
- A free **"Slot my best relics"** button on the Exploration tab does one pass by
  hand, so the capability exists before the automation does.

## Ranking relics

`score = log10(multiplier) x weight`. Logs are used so scores add the way
multipliers compose, which makes "the top N by score" genuinely the best set
rather than an approximation.

| Effect | Weight | Why |
|---|---|---|
| Global | 1.00 | multiplies everything |
| Alloy | 1.00 | Alloy is the prestige metric |
| Ore | 0.90 | Alloy rides Ore income |
| Replication ladder | 0.85 | compounds into everything |
| Extraction ladder | 0.80 | broad but not universal |
| Power | 0.90 / 0.10 | judged live against throttle |
| Data | 0.30 | buys Research, not production |

The Power case is the one worth calling out: a Power relic is nearly worthless at
full supply and valuable while you are throttled, so its weight is decided at
ranking time rather than baked in. The Exploration tab shows each relic's score
and tints the button gold when the ranking would rather have it slotted.

## Cost

With every automation enabled, 33/33 upgrades bought and 300 artifacts held, the
tick costs **0.89 ms** against a 100 ms budget at 10 Hz. Auto-relic re-ranks every
tick; at that size it is not close to a problem.

---

# Bug: automation silently switching itself off after Convergence

Reported as "sometimes when I prestige, my stuff isn't getting auto upgraded".
It was a real bug, and it was specific to **Convergence** — Dispersal was fine,
which is what made it feel intermittent.

`state.auto` (every automation toggle, the per-machine checkboxes, the spending
reserves, the auto-Dispersal threshold) was LAYER-scoped, so Convergence reset it
to defaults: everything off. Two things then went wrong at once:

1. The player had to re-tick every box after each Convergence, on top of
   re-earning the Seed Grid nodes.
2. Worse, **the UI never re-read the state**. The checkbox variables were built
   once at startup, so the Automation tab still showed every box ticked while the
   settings behind them were off. There was no way to tell from looking that
   anything had happened.

**Fix, part one:** `auto` is now PERMANENT. Toggles are *preferences*, not
progress — the capability is already gated by flags from the Seed Grid and
Research, so a preference left on while its unlock is gone is simply inert, and
it resumes working the moment the node is re-bought. Convergence still removes the
unlock; it just no longer forgets how you had things configured.

**Fix, part two:** `_sync_automation_controls()` pushes state into the widgets on
every Automation refresh, so a control can never disagree with the setting behind
it. This also covers a hard reset and loading a different save, both of which
replace the state object wholesale and had the same latent problem.

Five engine tests cover preference persistence across both prestige layers,
including that a toggle without its unlock stays inert and resumes afterwards.

---

# Bulk buying in the prestige shops

The Seed Grid and Coherence Nodes now have the same Buy 1 / 10 / 25 / Max control
as the Production tab, sharing one closed-form implementation (`bulk_cost` /
`bulk_affordable`) rather than a purchase loop.

One trap worth recording: several shop nodes are priced **flat**
(`cost_growth == 1.0`) — the one-shot unlocks like Permanent Foreman and Standing
Dispersal Orders. The geometric series divides by `growth - 1`, so a flat node
would have raised ZeroDivisionError the first time anyone clicked Max on it. Flat
pricing is handled as its own case, and a test asserts it directly.

Both shops share the generator behaviour a player already knows: a bulk button
disables when the full amount is unaffordable, and Max buys as much as the
currency allows. Caps are respected in both directions — a capped node never
overshoots, and an endless node (max_level 0) has no ceiling but is still bounded
by MAX_BUY per click.

21 tests cover the maths and both shops, including that bulk purchases charge
exactly what buying one at a time would, at several growth rates and starting
levels.

---

# Standing Seed Orders (auto-buying the Seed Grid)

A Coherence node (max level 1) that makes the Seed Grid buy itself, always taking
whichever level is **cheapest next**. Paired with Standing Dispersal Orders it
closes the loop on the whole Dispersal layer: reset, collect, spend, repeat.

## Why cheapest-first

Every Seed Grid node's cost rises exponentially, so buying the cheapest next level
naturally equalises marginal cost across the grid rather than pouring everything
into one node. Measured over 40 ticks from 1e6 Seed Points it bought **172 levels
spread across all 18 nodes**, which is the behaviour you want.

It is also *legible*: "buys whatever is cheapest" is something a player can
predict. A value-weighted heuristic would pick better in theory but would be
invisible and unpredictable, and Seed Points have no use other than this grid, so
there is nothing to hold back for.

## Pricing it

Priced at **15 Coherence** — the most expensive node in the shop, next being Deep
Coupling at 10.

The suggested figure was 30. Measured against actual accumulation, lifetime
Coherence is **10 after the first Convergence (3h 25m)** and **20 after the second
(10h)**, so 30 would have meant roughly three Convergences of banking *everything*
and touching no other node — a 15+ hour wall before the feature existed at all.
15 lands it around Convergence #2 for a player who prioritises it, while still
reading as the premium unlock it is. `COHERENCE_GRID` in `gamedata.py` is the one
line to change if it should be harsher.

## A test-harness bug worth recording

The GUI smoke test began hanging after this was added. It was not the feature:
`app.tick()` reschedules itself through `after()`, so calling it in a loop piles
up callbacks the real game never creates — the scheduler only ever has one
outstanding. The smoke now advances the model with `E.tick` directly and
exercises `app.tick()` once, separately, to prove the scheduled path still
advances the loop exactly one step.

---

# The Crucible, and relic mutations

## Fusing, not deleting

The ask was a way to clear out old relics: delete them, or fuse them. Deleting
tidies the list but leaves the actual problem in place — once you hold a decent
relic, every later Common is dead loot, and the "whoa, I found something" moment
that RNG exists to create quietly dies. Deleting just hides that. Fusing turns
the junk into progress, so every drop stays worth reading, and it gives the top
rarities a route through effort instead of luck alone.

**Three spare relics of one rarity become one of the next rarity up.**

The load-bearing rule is that fusion **never consumes a relic you are using, or
one the ranking would want to use**. That is enforced inside the selection —
`fusable()` excludes `equipped | best_loadout` before anything is chosen — rather
than checked after the fact, and consumption always takes the worst-scoring
spares first. Five tests exist purely for this property, including one asserting
that fusing can never lower your multiplier.

A consequence worth knowing: a collection barely larger than your slot count has
nothing spare, because your whole hoard *is* your working set. That is correct,
and it is what several of my first test fixtures got wrong.

## Mutations: a second axis

Rarity says how strong; a mutation says how strange. They roll independently.

| Mutation | Weight | Bonus multiplier |
|---|---|---|
| (plain) | 62% | x1 |
| Shiny | 15% | x1.6 |
| Mutated | 10% | x2.2 |
| Alien | 7% | x3 |
| Ancient | 4% | x4.5 |
| Entangled | 1.6% | x7 |
| Singular | 0.4% | x12 |

The multiplier scales the relic's **bonus**, not its total, so x1 really is no
change. Because the axes are independent, a Singular Common outranks a plain
Rare — which is the point: it keeps low-rarity drops worth looking at instead of
becoming noise the moment you own an Epic.

Fusion **inherits the best mutation among the relics consumed**, so a mutated
relic you fuse away is not simply lost. In practice this fires rarely, because
mutations raise a relic's score and high-scoring relics are consumed last — it is
a consolation, not a strategy.

Scoring needed no changes: `artifact_score` reads `value`, and mutations are
already baked into it.

## Save compatibility

Relics written before mutations existed have no `mutation` field. `mutation_of()`
defaults them to plain, and an unknown id degrades to plain rather than raising.
Four tests cover loading, scoring, fusing and ticking a legacy save.

## Clutter and cost

The relic list previously rendered one row per artifact forever — and once
fusion could destroy relics, those rows would have lingered pointing at things
that no longer existed. The list now shows your slotted relics plus the ten best
spares, destroys rows for relics that are gone, and reports the rest as a vault
count. With **800 relics** auto-fusing down to 18, a tick costs **0.30 ms**
against a 100 ms budget.

---

# Bug: the Convergence wall (found from a real 10-hour save)

Reported as "I feel bottlenecked". Diagnosed by loading the actual save (on a
copy) rather than guessing. State: 10h 15m played, 414 Dispersals, 17
Convergences, **14/14 research, 33/33 upgrades, every machine unlocked**, Alloy
at 1e135.

## What was actually wrong

**Coherence income grows logarithmically; Coherence prices grew exponentially.**
That gap can never close, and it is a wall by construction rather than by tuning.

- A Convergence paid **8 Coherence**, and 17 of them had produced 244 total.
- The next level of Coherent Design cost **43** — 5.4 Convergences for one level.
  Level 20 would have cost 12,100, or roughly 1,500 Convergences.

Three compounding causes:

1. **The bar tracked power too closely.** `P2_REQ_EXP` at 0.85 meant the
   requirement rose almost as fast as Seed Points accumulated, so depth past the
   bar stayed near zero and the log-shaped gain never grew.
2. **Node prices grew at 1.6-2.4 per level** against that flat income.
3. **The Seed Grid had saturated** — 10 of 19 nodes capped, the rest costing
   3-7M SP against 6.6M per Dispersal. Seed Points had almost nowhere to go, so
   the Dispersal layer had stopped converting effort into anything.

## Fixes

| | Before | After |
|---|---|---|
| `P2_BASE` | 5 | 10 |
| `P2_LOG_EXP` | 1.8 | 2.2 |
| `P2_REQ_EXP` | 0.85 | 0.65 |
| Coherence node growth | 1.6 – 2.4 | 1.28 – 1.55 |
| Endless Seed Grid nodes | 0 | 7 |

Measured on the reporting save: the Convergence bar fell from 21.5M to 7.14M
lifetime SP, a Convergence went from **8 to 39 Coherence**, and the next
Coherent Design level went from **43 to 7.2**. Roughly a 30x improvement in
levels-per-Convergence.

## The UX half of the bug

The Dispersal screen has always shown a projection ("in 10 minutes at this
rate"). The **Convergence screen showed only the current gain**, so nothing ever
told the player that depth pays: 1x the bar gives 10 Coherence, 100x gives 112,
10,000x gives 344. Converging the moment the bar cleared was the natural move and
also the worst one — which is exactly what 17 Convergences at minimum value look
like. The screen now shows what waiting is worth.

## Not a regression

A fresh 10-hour simulation still puts the first Convergence at 3h 06m and the
second at 5h 28m, with Research intact at 14/14 — the treadmill this exponent
originally guarded against has not come back.

## The part that is not a bug

That save had consumed **all** the content: every research node, every upgrade,
every machine. Layer 3 (Overwrite) does not exist yet, and at 17 Convergences
that is what the player is actually out of.

---

# Prestige layer 3 — Overwrite

Built because the reporting save had consumed all the content: every research
node, every upgrade, every machine, at 17 Convergences.

## What makes it a different kind of layer

Layers 1 and 2 both pay from a lifetime total, so the answer to "how do I earn
more?" is ultimately "keep going". **Overwrite Charges come from peak Alloy per
second**, tracked across the whole Convergence era and untouched by Dispersals or
Convergences. Idling at a fixed rate earns literally nothing — there is a test
for exactly that. The only way to earn is to build an engine that has never run
faster.

What Charges buy are **Floors**: permanent starting states. Ten levels of
Substrate Cache means every future Dispersal begins with 250 of each of E1-E5
already running. The early game stops being something you replay at all, which is
the design doc's stated purpose for this layer.

Also unlocked: Exotic Matter (era-scoped, logarithmic bonus like Nanites), the
Black Hole Tap, the Hive Ark extending the replication ladder to R5, a Persistent
Archive that carries Research through Convergence, and auto-Convergence with a
configurable depth.

## Calibration against the reporting save

| | |
|---|---|
| Tab visible at | 150 lifetime Coherence (that save had 244) |
| Overwrite bar | 1e90 peak Alloy/s (that save was at 1.95e135) |
| First Overwrite pays | **31 Charges** |
| Rewritten Constants / Substrate Cache | 2 / 3 Charges, so immediately affordable |
| Persistent Archive / Standing Convergence Orders | 40 / 60 Charges, the next goals |

## Two bugs found while building it

**`Cond.overwrite` was never checked** — the exact repeat of the `Cond.converge`
bug, and for the same reason: an unhandled condition field reads as *satisfied*,
so both Overwrite milestones fired on a brand-new game and handed out a x30
global multiplier. The guard test from last time listed fields by hand, so a new
field walked straight past it. It now derives the field list from
`dataclasses.fields(Cond)` and fails if any field lacks coverage.

**`Num` was serialized with 15 significant digits.** A float64 needs **17** to
round-trip exactly, so every quantity in the game lost its last mantissa digit on
each save/load cycle. Found because the smoke test compared a saved value against
its reload and they differed in the sixteenth digit. Two tests now pin it,
including 50 consecutive save/load cycles with no drift.

---

# Three bugs visible in one screenshot

Reported as "why does it say I have 0 material sometimes". All three confirmed
against the reporting save before touching anything.

## 1. Refineries captured 100% of the Ore stream

Converters take a fraction of an input resource's income, asymptotic to 1.0 so
they never stop being useful. At 400 Orbital Refineries that asymptote reached
**100.000000%**, so net Ore income was exactly zero, the Ore stock sat at zero,
and **every Ore-priced machine was permanently unbuyable** — a hard progression
block, not a display quirk. The capture also drew from the Ore *stock*, not just
income, so a bank could never build up either.

*Fix:* capture applies to income only, and is capped at `MAX_CAPTURE = 0.90`, so
a tenth of the stream always reaches your pocket. Alloy is unaffected in
practice — refinery quality multipliers carry the scaling. On the reporting save
Ore went from a pinned 0 to 2.81e201/s with all eight Ore-priced machines
buyable again; a 4-hour simulation shows Dispersal cadence unchanged.

## 2. Nanite Vats and Black Hole Taps produced nothing

Production credited a hardcoded `("ore", "data", "isotope")` — a list written
before Nanites and Exotics existed and never updated. Both machines were fully
purchasable, showed a rate in the UI, and contributed **zero**. The reporting
save had 4,890 Black Hole Taps displaying 3.41e51 Exotic Matter/s while the
engine credited none of it.

*Fix:* the loop derives producers from the resource table instead of a literal.
A test now walks every Extraction machine that produces a resource and asserts it
actually credits some, so a new resource cannot be silently dropped again.

## 3. Machines listed under the wrong heading

Tk appends on `pack()`, so a row hidden while locked and re-shown on unlock lands
at the bottom of the list. Because machines unlock at different times, the
Production tab drifted out of order — the screenshot showed a Black Hole Tap
filed under "Replication — machines that make machines".

*Fix:* `pack_ordered()` inserts each row before the first still-packed row that
should follow it.

The underlying mistake was subtler and worth recording: the show/hide logic used
`winfo_ismapped()`, which reports **on-screen visibility** and is False for every
widget on a tab the player is not currently looking at. Rows on a background tab
were therefore re-packed on every refresh, reshuffling themselves. All 21 uses
now go through `is_packed()`, which asks `winfo_manager()` — "is this managed by
pack right now" — which is what the logic always meant.

---

# Buy Max claimed a million and bought nothing

Reported as "the auto purchasing isn't buying fast enough". The screenshot showed
a `Buy x1000000` button on an Orbital Refinery, which was the tell.

`max_affordable` short-circuited to `MAX_BUY` whenever cash was more than 300
orders of magnitude past the next unit's price — a shortcut added because a float
cannot hold `10**5000`. It is simply wrong: with 1e5000 Ore and 1.14 cost growth
the true answer is **87,796 levels, not 1,000,000**, and a million costs
`6.09e56908`.

The consequence was worse than an overstated label. `buy()` recomputes the price
for the count it was handed, finds it unaffordable, decrements by one, finds that
unaffordable too, and **returns zero**. So Buy Max offered a million and purchased
nothing, and auto-buy silently stalled on every machine the player was rich
enough to trip the shortcut on — which is exactly the "not buying fast enough"
that was reported.

*Fix:* `_levels_from_ratio()` solves for k in log space, so the large branch is
exact rather than a guess. On the reporting save Buy Max went from "1,000,000,
bought 0" to "16,565, bought 16,565".

Two more found while fixing it:

- **`bulk_affordable` raised OverflowError** on a flat-priced shop node with an
  astronomical bank: `int(inf)`. That would have crashed the game outright on a
  Max click. It now decides in log space before converting.
- **Auto-buy's flat 50-per-tick allowance** was glacial once affordability ran to
  five figures. It is now a share of what you could buy outright
  (`AUTOBUY_FRACTION`, floored at the old 50), which keeps up with wealth while
  still leaving budget for the other machines in the same tick.

# Standing Coherence Orders

An Overwrite node (30 Charges, max level 1) that buys Coherence Nodes on its own,
cheapest level first — the Convergence layer's equivalent of Standing Seed
Orders. With it, Standing Convergence Orders and Standing Dispersal Orders, the
whole prestige stack below Overwrite runs itself.
