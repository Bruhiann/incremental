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

---

# Doctrines now survive a Convergence

They were LAYER-scoped and wiped on every Convergence, on the theory that
re-picking them was what stopped a choice becoming a permanent regret. That
reasoning was wrong: Doctrines can be switched at any time for free, so the
anti-regret property comes from **switching**, not from forced re-picking. All
the reset achieved was making the player re-click five rows after every reset —
and with auto-Convergence running, do it without noticing.

They are now PERMANENT: kept through both Convergence and Overwrite, and still
switchable whenever you like.

The reporting save made the cost obvious. After **17 Convergences it had all five
rows empty** — every Doctrine had been wiped and never re-picked, so a stack of
free multipliers (up to x8 global, x3 to an entire ladder) had gone unused for
the whole run. Nothing in the UI had ever mentioned it.

So the Next Goal strip now leads with unchosen Doctrines whenever any row is
empty, and the Convergence tab carries a gold note saying how many are unpicked
and that they are free. Free power should never be invisible.

---

# The purchase ceiling was throttling auto-buy

Reported as "I don't think the auto purchaser is working, or am I producing too
much". The tell in the screenshot: Solar Film, Asteroid Mine, Fusion Cell and
Orbital Refinery all sat at **exactly x82.3M**. Identical counts across machines
with wildly different prices means auto-buy is running fine and every one of them
is hitting the same ceiling.

`MAX_BUY` capped any single purchase at 1,000,000 units. On the reporting save the
player could afford **1,249,533,172** — the cap was throttling them by a factor of
1,250, and auto-buy (a tenth of that per tick) crawled at 100,000/tick while
income ran at 1e3,300,000/s.

The cap existed to keep counts sane, but the purchase maths is closed-form: a
billion units costs exactly as much to compute as ten. It is now `10**15`.
Measured against the Ore bank in the screenshot, Buy Max went from 1,000,000 to
**763,614,520 units actually purchased**.

## And a bonus that switched itself off

Raising the ceiling exposed a latent bug. The per-10 multiplier counted steps as
`int(bought.to_float() // 10) if bought.e < 15 else 0` — so at 1e15 purchased
units the entire per-10 bonus silently became **zero**, at exactly the point a
player grew strong enough to reach it. With the old ceiling that was unreachable;
with the new one it is not. `_tenfold_steps()` now degrades by magnitude instead
of vanishing, and a test asserts the bonus still appears in the multiplier
breakdown after a huge purchase.

So the answer to the question was: auto-buy was working, production was not too
fast, and the ceiling was simply set for a much smaller game than the one that
now exists.

---

# Prestige layer 4 — Substrate Collapse, and fixing Overwrite on the way

## The Overwrite runaway

Reported as "I'm basically done with Overwrite". The save showed why: 10
Overwrites, peak Alloy/s at `3.50e1.30Qa`, and **a next Overwrite paying 40.1
trillion Charges against a shop whose dearest node cost 50.4 thousand**. Five of
eleven nodes were already maxed. The layer had no tension left at all.

Cause: gain was `(depth + 1) ** 0.9`, and `depth` is `log10(peak) - log10(bar)`.
Production up here is hyper-exponential, so depth itself reached 1.3e15 and any
ordinary power of it produced absurd numbers. The requirement rises
polynomially with charges held, so it could never catch up.

*Fix:* gain is taken from the **log of the depth** —
`10 * log10(depth + 10) ** 1.9` — which holds the whole range from a first
Overwrite to a hyper-exponential one inside a readable band: 16 Charges at depth
10, 29 at depth 45, 301 at depth 1e6, 1,716 at depth 1e15. Shop prices dropped
from 1.32-1.60 per level to 1.13-1.30 so gain can keep buying levels. On the
reporting save the next Overwrite went from **40.1T to 1.90K Charges**, against
node prices of 61-379 — five to thirty levels per Overwrite.

## The new layer

Collapse wipes the Overwrite era (Charges and every Floor) on top of everything
Overwrite resets, via a new `OVER` scope. Its verb is different from every layer
below it: **Substrate buys exponents.** Production is raised to a power.

The honest maths, which the tests pin in both directions: `+e` adds
`e x log10(multiplier)`. So +0.010 is *worse* than a plain x10 until multipliers
pass `1e100`, and past that it runs away from them — at 1e400 a single +0.010 is
worth four hundred x10s. There are two tests, one for each side of that
crossover, because a layer whose selling point is "exponents beat multipliers"
should be honest about when that becomes true.

Also in the Lattice: Constant Rewrite (x10 each), Denser Substrate (Charges x3),
Deep Cache (start with 100 more of E1-E5 per level), Woven Frame (+5 relic
slots), **Cached Genome** (the Seed Grid survives Convergence) and **Standing
Overwrite Orders** (auto-Overwrite at a chosen depth).

A related correctness fix: Persistent Archive and Cached Genome carry work
through the reset *below* them, never through the reset meant to clear their own
layer. A Collapse wipes the Seed Grid even with Cached Genome bought, and there
is a test saying so.

## Calibration against the reporting save

| | |
|---|---|
| Substrate tab visible at | 5,000 lifetime Charges (that save had 2.85M) |
| Collapse bar | 20,000 lifetime Charges |
| First Collapse pays | **49 Substrate** |
| Which buys | 7 levels of Rewritten Physics -> exponent ^1.014 |
| Next goals | Cached Genome (40), Standing Overwrite Orders (60) |

Recursion (layer 5) remains scaffolded and empty.

---

# The Defection (combat)

Everything in SEED is monotone: numbers only go up, and shortages slow but never
destroy. Combat is the one exception, so its whole design is a fence around what
it may take. Its single job is to pose the decision the economy cannot —
**spending on something that produces nothing** — and if it did not do that, it
would be a slot machine with extra steps and should not exist.

The theme was already in the game. *Rogue Replicator* is an anomaly that hands
you someone else's machine; the Defection is that inverted and made structural.

## Three shape failures, in order

Each was found by measurement, and each is the same underlying mistake: two
quantities that must be compared were put on different growth curves.

**1. Threat linear in progress vs a hyper-exponential fleet.** Threat was first
`0.9 * log10(swarm)`, giving an incursion strength roughly linear in game
progress. But fleet power carries the per-10 bonus like every other tier, so it
is hyper-exponential in count. Any fleet at all trivialised combat permanently —
a "0.25x" fleet in the first test rig measured at 350x, because 778 drones carry
`1.1**77`.

**2. The fleet eroding mid-fight.** With attrition applied to the D ladder, a
fleet sized at exactly the stated requirement *lost*: an 11% loss of hulls more
than halves fleet damage under the per-10 bonus, which loses the fight, which
costs more hulls. That is the same death spiral the energy-throttle exemption
exists to prevent, and it also made the requirement printed in the header a lie.
*Fix:* the Defence ladder is exempt from attrition, alongside power generators.
An incursion takes your economy, never your guns.

**3. Sizing the incursion off the swarm made it unwinnable.** Deriving strength
from swarm power put both sides on one curve, which fixed (1) — but the swarm is
**replicated for free** and grows hyper-exponentially, while a fleet is
**bought**, and cost is exponential in count, so affordable fleet power is only
*logarithmic* in cash. Measured on the reporting save: **1e7.5Qa damage/s
demanded against 1e2.2Qa affordable**, a gap of `1e5e15`. Not a tuning problem.

*Fix:* magnitude is measured against the **bank**, not the swarm — the strength
is whatever fleet 10% of your cash would buy at the best tier you have unlocked,
computed from a standing start so buying ships never raises the bar. The demand
is then always exactly as large as the decision it exists to pose, at every
scale, and it cannot brick or be outgrown.

Frequency and magnitude are separated for the same reason. Frequency is a
**period** (600 s, stretching with your war record), because a rate drawn from
swarm size came to 5.4e15 threat per second against a bar of 600 — an incursion
every tick, forever.

## A fourth loop, caught by a test

D2-D5 originally unlocked on D1 counts, like the R ladder does. But strength is
sized from the best tier *unlocked*, so buying D1 unlocked D2 and raised the very
bar the D1 was bought to clear. The Defence tiers now gate on lifetime Alloy,
like the Extraction ladder, and a test pins that buying ships cannot move the
requirement.

## The fight

A race, not a coin flip: the incursion has HP, the fleet has DPS, and killing it
sooner means losing less. Pressure is `strength / (strength + fleet)`, and losses
are `0.004 * pressure` of each tier per second, reduced by `1/(1 + 0.5*(tier-1))`
so the cheap tiers absorb the damage. A fight always ends — 120 s and the
incursion breaks off, which is a loss but a bounded one, so a fleet of zero still
reaches the other side.

Measured curve, at a fixed incursion (no cliff anywhere on it):

| fleet vs requirement | result |
|---|---|
| 0.10x | loss |
| 0.47x | loss |
| 0.90x | win |
| 1.00x | win |
| 10.0x | win, essentially free |

Worst case, no fleet at all: a tier-3 machine keeps 78.7%, and `gens` and
`bought` fall by exactly the same count — that split exists because free units
caused an unbounded runaway once, so cutting only one side re-creates it. Taking
both means a loss costs **time, not money**: costs fall with `bought`.

## What it may never take

Prestige currency of any layer, upgrades, research, relics, milestones,
achievements, unlocks, power generators, the fleet itself, and anything below the
floor your Overwrite and Substrate levels grant you. Each of those is a test, and
the first one runs a deliberately unwinnable fight from a rich state and asserts
the rest of the save comes out unchanged.

The first incursion is scripted and unlosable. A player who meets combat for the
first time by losing half a run has learned the wrong thing.

## Calibration against the reporting save

| | |
|---|---|
| Visible from | the first Overwrite (that save has 10) |
| Incursion period | 10 minutes, stretching with wins |
| Requirement | 2.88e6.07T damage/s |
| Fleet after one Buy Max of D5 | 5.37e6.07T — still behind |
| Fleet after two | 1.60e12.1T — comfortably ahead, nothing lost |

Two clicks on an endgame save. That is deliberately the mild end for the first
release of the only system that can take something away.

---

# Prestige layer 5 — Recursion

Every layer so far changed the verb: upgrades, then choices, then floors, then
exponents. What is left is the game itself. **Recursion sells difficulty** — you
descend into a deliberately worse copy of the universe, because the worse it is,
the more it pays.

## The rejected design, and why

The design doc said Recursion "auto-replays the entire game at compressed speed
to a chosen depth." That is a dead idea, and it is worth writing down why: by
here the player owns auto-Dispersal, auto-Convergence, auto-Overwrite,
auto-Defence and Standing Orders for three shops. **The game already replays
itself.** A literal replay layer would rename automation they have and turn them
into a spectator watching a gauge, at the cost of a second tick path.

The doc's *payout* rule survives untouched — depth reached x speed of clear. Only
the mechanism is thrown out: the compressed replay is the player's own
automation, through an early game that the Defection made worth revisiting.

This is also the **Challenge system** the doc promised at layer 2 and that was
never written, arriving at the layer where it belongs.

## Handicaps hit costs, never the exponent

The main balance decision in the layer, and the one place this codebase's
recurring failure was foreseen rather than discovered. Production here is
hyper-exponential. A `^0.9` handicap stacked to depth 40 is `^0.015` — that is
not difficulty, it is deletion. Cost growth is the one axis that scales smoothly
and that the player owns real tools against.

```
m.growth["*"] += (0.004 - soften) * depth        # floored at 0.001
```

One line in `recompute`, flowing through `growth_of` into `cost_of`,
`bulk_cost`, `bulk_affordable`, `max_affordable` and Buy Max. Measured:

| depth | E1 growth | R5 growth |
|---|---|---|
| 0 | 1.110 | 1.200 |
| 10 | 1.150 | 1.240 |
| 30 | 1.230 | 1.320 |
| 50 | 1.310 | 1.400 |
| 100 | 1.510 | 1.600 |
| 100, Shallow Water x6 | 1.210 | 1.300 |

Named handicaps arrive on top, in a declarative table so the header can print
them: Hungry Machines (3), Early Defection (5), Dead Frame (8), Silent Sky (12),
Sterile (15), Starved (22), Diminished (30). A handicap the player cannot see is
indistinguishable from a bug, so the depth strip lists every active one.

## Payout

```
target(D) = 1e6 * 1e4**D          Alloy earned INSIDE the depth
par(D)    = 300 + 90*D  seconds
speed     = clamp(par/actual, 1, 10)
gain(D)   = floor(2.0 * D**1.35 * speed)
```

Requirement exponential in depth, gain mildly polynomial — the shape that stopped
layers 3 and 4 running away. The speed term is the first mechanic in the game
that rewards *active* play at the endgame, and it is honest because there is no
offline progress: `p5_elapsed` is saved as a duration, so closing the game cannot
buy a speed bonus.

| depth | target | par | pays at par | pays fast |
|---|---|---|---|---|
| 1 | 10.0B | 6m 30s | 2 | 20 |
| 5 | 100Sp | 12m 30s | 17 | 175 |
| 20 | 1e86 | 35m | 114 | 1.14K |
| 100 | 1e406 | 2h 35m | 1.00K | 10.0K |

**The payout lands on the clear, not on the reset** — the one structural
difference from every layer below, and a necessary one. A layer that only paid on
reset would make the first descent, which wipes the Substrate era and hands back
nothing, a pure loss until the player guessed they were allowed to leave.

## Two bugs found while building it

**The depth needed its own Alloy accumulator.** `run_life` resets every Dispersal
and a Recursion contains many of those, so the clear condition reads a SUB-scoped
`p5_alloy` instead. `SUB` appears in no layer's wipe list but Recursion's, which
is what makes the depth ride out a Dispersal, a Convergence, an Overwrite and a
Collapse.

**Side outputs were being discarded.** E11 yields Ore, Alloy, Data and Isotopes
at once via a new declarative `Gen.extra` field. Step 5 of `_produce` *assigns*
`rates["alloy"]` outright, so the Alloy written at step 3 vanished. Caught by the
test that asserted all four resources, not just the headline one.

## The Stack

Compiled Start, **Retained Exponent** (+0.001 of the Substrate exponent survives
a Recursion, per level — the node that stops the wipe reading as pure loss, since
depth pays layer 4 back in layer 4's own currency), **Standing Army** (keep 10%
of the fleet per level), Thicker Substrate, **Shallow Water** (the difficulty
dial: a player at their ceiling buys past it instead of stalling), Wider Frame,
**Vacuum Decay Well** (E11) and **Galactic Bloom** (R8), which close out ladders
that stopped dead at E10 and R5, and Standing Recursion Orders.

## The `Cond` guard, third time lucky

`Cond.converge` and `Cond.overwrite` both shipped unchecked, each granting every
milestone that used them on a brand new game. The guard test now derives its
field list from `dataclasses.fields(G.Cond)`, so `Cond.recurse` could not repeat
it. Verified by deleting the check and watching the test fail.

---

# MAX_BUY, the third time

Reported as "is auto buy working or is it just slow — too many products get
loaded and I don't see the number going down."

Auto-buy was working. Measured on the reporting save, one tick bought 17.7K
Regolith Scrapers, 13.2K Solar Films and thousands of every other tier including
the whole Defence ladder, with every per-machine toggle on and no reserves set.
Spending was 0.00% of income over sixty seconds, which is the honest answer to
the second half of the question: affordability is *logarithmic* in cash, so at
this scale no amount of buying can visibly dent the bank, and it never will.

But the first half was right, and the cause was `MAX_BUY`.

```
        E1 bought      still affordable
  0s         882K               156,000
300s        7.46Qa    1,000,000,000,000,000   <- exactly MAX_BUY
675s         157Qa    1,000,000,000,000,000
700s         167Qa    ...
725s         177Qa
```

After about five minutes of play, affordability crossed the cap and growth
**changed character**: from compounding to strictly linear, +10 Qa every 25
seconds forever, while the bank kept growing hyper-exponentially. The ratio
decayed 1.07x -> 1.03x -> and would have kept decaying toward 1.00x. Nothing
errored. Auto-buy simply looked broken while doing exactly what it was told.

This is the same cap that was raised from 1e6 to 1e15 once already, for the same
reason, on the same save. **A fixed integer cap is the wrong shape** in a game
whose counts are `Num`: affordability is logarithmic in cash and cash is
hyper-exponential, so every finite cap is eventually crossed, and crossing it is
silent.

*Fix:* `MAX_BUY = 10**300`, set at the edge of what a float can carry rather
than at a number that felt large, with the reasoning written at the constant so
the next person does not pick a fresh round number. `_levels_from_ratio` now
guards `math.isfinite` before `int()`, since a division that overflows is
reachable at this ceiling. `gens_bought` moved to a `Num`, and Buy Max labels
and the Stats row now format through `fmt` — a 300-digit integer is not a button
caption.

Measured on the same save, same twenty minutes:

| | machine count at 20 min | growth per 25 s |
|---|---|---|
| before | 3.67e17 | x1.03, linear |
| after | 3.72e149 | x98,006, compounding |

## A second bug the cap was hiding

Raising it broke an existing test, which is what tests are for.
`bulk_affordable` short-circuited flat-priced shop nodes (`cost_growth == 1.0`)
to `MAX_BUY` whenever the cash-to-price ratio passed 1e12 — harmless while
MAX_BUY was small, but at the float ceiling it promised 1e300 levels for 1e50 of
cash, and `buy` would price them and refuse. The threshold now matches the cap.

Four regression tests pin the symptom rather than the constant: affordability
must rise with the bank, the auto-buy allowance must track affordability rather
than its floor, a purchase past 1e15 must go through, and the machines-bought
stat must survive a save round-trip. All four fail if the cap is put back to
1e15, which is how they were checked.
