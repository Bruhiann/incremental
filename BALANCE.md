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
