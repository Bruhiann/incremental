# SEED — Technical Architecture (Phase 3)

Python 3.14 + Tkinter (stdlib only, no third-party runtime deps). Launched with `py`.
Target: one folder, runnable as `py run.py`, later frozen to `SEED.exe`.

## 1. File layout

```
incremental/
  run.py              # 10-line launcher
  seed/
    __init__.py
    __main__.py       # py -m seed
    bignum.py         # Num: mantissa/exponent big number + formatter    (~250 lines)
    gamedata.py       # ALL content as declarative tables                (~700, grows)
    state.py          # GameState, defaults, (de)serialization           (~250)
    engine.py         # tick, production, throttle, buy, prestige, RNG   (~700)
    saveman.py        # atomic save/load/backup/migrate                  (~200)
    ui.py             # Tk widgets, tabs, refresh loop                   (~900)
    balance.py        # headless simulator for Phase 6 (not shipped)     (~200)
  tests/
    test_bignum.py
    test_engine.py
    test_saveman.py
  ARCHITECTURE.md
```

Rationale for the split: `gamedata` is edited constantly during balancing, `engine` almost
never. Keeping them apart means Phase 6 tuning cannot break logic. `ui` computes nothing —
it only formats values the engine already derived.

## 2. The core rule: content is data, not code

Every generator, upgrade, research node, milestone, achievement, challenge, artifact and
anomaly is a frozen dataclass instance in `gamedata.py`. Effects are declarative records,
not lambdas, so they serialize, print and diff cleanly:

```python
Gen(id="E3", name="Asteroid Mine", ladder=EXTRACT, produces="ore",
    base_rate=8.0, base_cost=Num(900), cost_res="ore", growth=1.13,
    draw=4.0, unlock=Cond(res="ore", amount=250))

Upg(id="u_ore_2", name="Hardened Bits",
    desc="Regolith Scrapers produce 100% more Ore.",
    cost=Num(1500), cost_res="ore",
    effect=Eff(kind=MULT_GEN, target="E1", value=2.0),
    unlock=Cond(gen="E1", count=25))
```

`Eff.kind` is a small closed enum: `MULT_GEN`, `MULT_LADDER`, `MULT_GLOBAL`, `MULT_RES`,
`ADD_GROWTH`, `MULT_TENFOLD`, `UNLOCK_FLAG`, `ADD_SLOT`, `EXPONENT`. Adding content in
Phase 7 means appending rows, not writing branches.

## 3. Numbers — `bignum.py`

`Num` = normalized `(mantissa: float in [1,10), exp: int)`, immutable, with full arithmetic,
comparisons, `log10()` and `to_float()`. Below 1e15 it delegates to plain float for speed;
above that it uses the pair. Serializes as the string `"1.234e567"`.

One `fmt(n)` formatter: K/M/B/T/Qa/Qi… to 1e33, scientific beyond, `e1.4e6` at the extreme.
This exists from day one specifically so the Substrate exponent layer — which passes
float64's 1.8e308 ceiling — needs no retrofit of every formula, save field and label.

## 4. State management — `state.py`

A single mutable `GameState`; nothing else holds game data.

```python
res: dict[str, Num]              # current stocks
lifetime: dict[str, Num]         # per-run lifetime totals
gens: dict[str, int]             # generator id -> count
upgrades / research / milestones / achievements: set[str]
flags: dict[str, bool]           # unlock flags + automation toggles
artifacts: list[ArtifactInst];  relic_slots: int
events: list[ActiveEvent]        # temporary RNG modifiers with expiry
expeditions: list[ProbeRun]
p1..p5: PrestigeLayer            # currency, lifetime currency, purchased ids, count
stats: dict[str, Any]            # playtime, run time, peaks, purchases, bests
settings: dict[str, Any]
version: int
```

Three reset scopes are declared **on the field, in one table**: `RUN` (wiped by P1),
`LAYER` (wiped by P2), `PERMANENT`. `engine.prestige()` reads that table instead of
hand-clearing fields — hand-clearing is exactly how "a value that should have persisted got
wiped" bugs happen. Phase 5 tests both directions.

## 5. Game loop

`ui.py` schedules `root.after(100, tick)` — one loop, one owner, rescheduled at the **end**
of each tick so it can never double-register.

```
now = time.perf_counter(); dt = min(now - last, 0.25); last = now
engine.tick(state, dt)     # pure model update
ui.refresh(state)          # every 3rd tick (~3 Hz) — widget text is the slow part
```

`dt` is measured, never assumed, and clamped so a frozen or descheduled window cannot mint
resources. Time between sessions is recorded for statistics only: **no offline progress.**

### `engine.tick(state, dt)` — fixed order, and the order matters
1. Expire timed events; advance expeditions; resolve completed probes.
2. Compute energy `supply` and `demand`; `throttle = clamp(supply/demand, 0.10, 1.0)`.
3. Per-generator output (§6). **Energy generators bypass throttle** — the death-spiral
   guard, asserted in tests.
4. Apply upkeep (Alloy, Isotopes). A deficit idles only the single highest-upkeep tier.
5. Credit resources: `res[k] += rate_k * dt`, clamped at zero, capped where caps apply.
6. Automation: auto-buy (respecting reserves), auto-refine, auto-research, auto-expedition,
   auto-prestige.
7. RNG rolls via accumulated-time counters, never per-tick probability — so event frequency
   is independent of tick rate.
8. Evaluate unlocks, milestones, achievements; queue popups.
9. Update stats and peaks.

## 6. Production calculation

`recompute_mults(state)` runs once per tick, filling a cached `dict[gen_id -> Num]` plus a
parallel `dict[gen_id -> list[(label, value)]]` breakdown for the hover tooltip. The UI
never recomputes; it formats the cache. Factor order is exactly §3 of the design doc, with
the Substrate exponent applied last.

## 7. Purchasing

Closed-form only — no loops:

```python
cost_bulk(gen, n, k)         = base * g**n * (g**k - 1) / (g - 1)
max_affordable(gen, n, cash) = floor(log(1 + cash*(g-1)/(base*g**n)) / log(g))
```

`engine.buy(state, gen_id, k | "max")` is the single mutation path: it recomputes cost,
checks affordability *inside* the call, deducts, increments, returns the count actually
bought. Buy Max caps at 1e6 units per call. **Automation calls this same function** — no
second, looser code path, which is the usual source of "purchased while unaffordable" bugs.

## 8. RNG

One `random.Random` seeded from the OS, seed saved so a session is reproducible for
debugging. Anomalies use an accumulating `next_event_at` timer with a hard 30 s floor and a
per-type active cap. Artifact drops use a rate counter plus a **pity counter** guaranteeing
Epic+ every 40 rolls. Rarity weights live in `gamedata.RARITY`. RNG never gates a tier or an
unlock — it only accelerates.

## 9. Prestige resets

```python
engine.prestige(state, layer):
    gain = LAYERS[layer].gain_fn(state)      # pure; UI calls this for the live preview
    for field, scope in FIELD_SCOPES.items():
        if scope <= LAYERS[layer].wipes: reset to default
    apply starting bonuses (milestones, Overwrite floors)
    state.p[n].currency += gain; count += 1; save immediately
```

`gain_fn` is pure and called every frame to show "gain if you reset now" plus the 10-minute
projection. Preview and award can never disagree because they are the same function.

## 10. Save/load — `saveman.py`

`%LOCALAPPDATA%\SEED\savegame.json` + `savegame_backup.json`, via `os.environ["LOCALAPPDATA"]`
with a `~/.seed` fallback. Write sequence:

1. Serialize to JSON **in memory**; if that raises, abort without touching disk.
2. Write `savegame.tmp`, `flush()`, `os.fsync()`.
3. Re-read and `json.loads` the temp file to verify it parses.
4. Copy current main to `savegame_backup.json`.
5. `os.replace(tmp, main)` — atomic on Windows.

Load: main, then backup, then a fresh game with a clear notice. **Never a silent wipe.**
`version` int with an ordered list of migrations applied in sequence. Autosave every 30 s,
plus on close (`WM_DELETE_WINDOW`), on any prestige, and on major unlocks. Hard reset
requires typing `DELETE`.

## 11. UI

`ttk.Notebook`; tabs are built lazily and `.add()`ed only when their unlock flag flips, so
the player starts with exactly one. Widgets are created once and cached in `dict[key ->
widget]`; refresh mutates `.config(text=…)` rather than rebuilding rows — rebuilding every
frame is the standard way Tkinter incrementals end up freezing. Rows scrolled out of view
skip their text update. Refresh ~3 Hz, model ~10 Hz.

## 12. Unlock conditions

`Cond` is a declarative record (`res`/`amount`, `gen`/`count`, `flag`, `research`,
`prestige_count`, or `all_of`/`any_of`). A single `check(cond, state) -> bool` serves
generators, upgrades, tabs, research and milestones alike. Unlocks are **sticky**: once
true the flag is stored, so a temporary dip never re-hides content.

## 13. Testing

`tests/` runs headless under `unittest` with no Tk import, driving `engine.tick` directly.
`balance.py` runs the same engine under a scripted "reasonable player" policy at 100× speed
and prints time-to-milestone tables for Phase 6. Because the UI holds no logic, the
simulator and the shipped game are guaranteed to be the same economy.
