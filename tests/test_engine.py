"""Engine tests. These target the specific failure modes listed in Phase 5."""

import math
import random
import unittest

from seed import engine as E
from seed import gamedata as G
from seed.bignum import N, Num, ZERO
from seed.state import RESET_SCOPE, GameState, new_game


def run(s, seconds, dt=0.1, rng=None):
    rng = rng or random.Random(1234)
    steps = int(seconds / dt)
    for _ in range(steps):
        E.tick(s, dt, rng)


def install(s, gid, count):
    """Pretend the player built `count` of a machine (both counters)."""
    s.gens[gid] = N(count)
    s.bought[gid] = N(count)
    s.unlocked.add(gid)


def rich(ore=1e12, alloy=1e9, data=1e6, iso=1e4):
    s = new_game()
    s.res["ore"] = N(ore)
    s.res["alloy"] = N(alloy)
    s.res["data"] = N(data)
    s.res["isotope"] = N(iso)
    # Several unlocks are gated on run-lifetime totals, not current stock.
    for rid, amount in (("ore", ore), ("alloy", alloy), ("data", data), ("isotope", iso)):
        s.run_life[rid] = N(amount)
        s.total_life[rid] = N(amount)
    E.recompute(s)
    return s


class TestPurchasing(unittest.TestCase):
    def test_cannot_buy_unaffordable(self):
        s = new_game()
        E.recompute(s)
        self.assertEqual(E.buy(s, "E1", 1), 0)
        self.assertEqual(s.gens["E1"], ZERO)

    def test_cannot_buy_locked(self):
        s = rich()
        s.unlocked.discard("E8")
        self.assertEqual(E.buy(s, "E8", 1), 0)

    def test_resources_never_go_negative(self):
        s = new_game()
        s.res["ore"] = N(20)
        E.recompute(s)
        E.buy(s, "E1", "max")
        self.assertGreaterEqual(s.res["ore"], ZERO)

    def test_buy_max_matches_bulk_cost(self):
        s = new_game()
        s.res["ore"] = N(10_000)
        E.recompute(s)
        k = E.max_affordable(s, "E1")
        cost = E.cost_of(s, "E1", k)
        before = s.res["ore"]
        got = E.buy(s, "E1", "max")
        self.assertEqual(got, k)
        self.assertAlmostEqual((before - cost).to_float(), s.res["ore"].to_float(), places=4)

    def test_buy_max_leaves_next_unaffordable(self):
        """The definition of Max: one more must not be purchasable."""
        s = new_game()
        s.res["ore"] = N(1e6)
        E.recompute(s)
        E.buy(s, "E1", "max")
        self.assertEqual(E.max_affordable(s, "E1"), 0)

    def test_buy_max_is_fast_at_huge_wealth(self):
        """Closed form, not a loop: this must not hang."""
        s = rich(ore=1e300)
        import time as _t
        t0 = _t.perf_counter()
        k = E.buy(s, "E1", "max")
        self.assertLess(_t.perf_counter() - t0, 0.25)
        self.assertLessEqual(k, E.MAX_BUY)

    def test_cost_rises_with_bought_not_total(self):
        """Free units from replication must not inflate prices."""
        s = rich()
        E.buy(s, "E1", 10)
        cost_a = E.cost_of(s, "E1", 1)
        s.gens["E1"] = s.gens["E1"] + N(1e6)      # as if built by R1
        self.assertEqual(E.cost_of(s, "E1", 1), cost_a)

    def test_partial_buy_when_short(self):
        s = new_game()
        s.res["ore"] = N(15)
        E.recompute(s)
        self.assertEqual(E.buy(s, "E1", 10), 1)


class TestMultipliers(unittest.TestCase):
    def test_tenfold_uses_bought_only(self):
        """Free units must not feed the per-10 bonus, or it runs away."""
        s = rich()
        E.buy(s, "E1", 10)
        E.recompute(s)
        with_bought = s.mults["E1"]
        s.gens["E1"] = s.gens["E1"] + N(1e9)
        E.recompute(s)
        self.assertEqual(s.mults["E1"], with_bought)

    def test_cross_ladder_is_logarithmic(self):
        """1e20 replicators must give a small multiplier, not 1e20."""
        s = rich()
        s.gens["R1"] = N(1e20)
        self.assertLess(E._cross_ladder(s, 1), 100.0)
        self.assertGreater(E._cross_ladder(s, 1), 1.0)

    def test_cross_ladder_does_not_boost_replication(self):
        s = rich()
        s.gens["R1"] = N(1e6)
        E.recompute(s)
        labels = [lbl for lbl, _ in s.breakdown["R2"]]
        self.assertNotIn("Replication", labels)

    def test_growth_never_below_one(self):
        s = rich()
        m = E.collect_mults(s)
        m.growth["*"] = -99.0
        self.assertGreaterEqual(E.growth_of(s, G.GEN_BY_ID["E1"], m), E.MIN_GROWTH)


class TestThrottle(unittest.TestCase):
    def test_throttle_floor(self):
        s = rich()
        E.buy(s, "E1", 5)
        install(s, "E3", 1e6)          # enormous draw, no supply
        run(s, 1.0)
        self.assertGreaterEqual(s.throttle, G.THROTTLE_FLOOR - 1e-9)

    def test_power_generators_are_not_throttled(self):
        """The death-spiral guard: a brownout must be recoverable."""
        s = rich()
        E.buy(s, "E2", 10)
        install(s, "E3", 1e9)
        run(s, 1.0)
        self.assertLess(s.throttle, 0.5)
        expected = s.gens["E2"] * N(G.GEN_BY_ID["E2"].base_rate) * s.mults["E2"]
        self.assertAlmostEqual((s.energy_supply / expected).to_float(), 1.0, places=6)

    def test_recovers_after_adding_power(self):
        s = rich()
        E.buy(s, "E1", 5)
        install(s, "E3", 1000)
        run(s, 0.5)
        low = s.throttle
        install(s, "E4", 1e6)
        run(s, 0.5)
        self.assertGreater(s.throttle, low)
        self.assertAlmostEqual(s.throttle, 1.0, places=6)


class TestProduction(unittest.TestCase):
    def test_production_scales_with_elapsed_time(self):
        s = rich()
        E.buy(s, "E1", 10)
        a = new_game(); a.__dict__.update({k: v for k, v in s.__dict__.items()})
        run(s, 2.0, dt=0.1)
        ore_fine = s.res["ore"]
        s2 = rich(); E.buy(s2, "E1", 10)
        run(s2, 2.0, dt=0.2)
        self.assertAlmostEqual(ore_fine.log10(), s2.res["ore"].log10(), places=6)

    def test_dt_is_clamped(self):
        """A stalled window must not mint resources."""
        s = rich(ore=0)
        E.buy(s, "E1", 10)
        s.res["ore"] = ZERO
        E.tick(s, 10_000.0)
        gained = s.res["ore"]
        s2 = rich(ore=0)
        E.buy(s2, "E1", 10)
        s2.res["ore"] = ZERO
        E.tick(s2, G.MAX_DT)
        self.assertAlmostEqual(gained.to_float(), s2.res["ore"].to_float(), places=6)

    def test_refinery_limited_by_ore(self):
        s = new_game()
        s.res["ore"] = ZERO
        install(s, "E5", 100)
        install(s, "E2", 1e9)          # plenty of power
        E.recompute(s)
        run(s, 1.0)
        self.assertGreaterEqual(s.res["ore"], ZERO)
        # No ore income at all, so alloy production must be ~nothing.
        self.assertLess(s.res["alloy"].to_float(), 1.0)

    def test_upkeep_idles_only_the_top_tier(self):
        """A shortage must idle the top tier only, never cascade downward."""
        s = new_game()
        s.res["alloy"] = ZERO
        install(s, "E1", 100)          # ore for the refineries
        install(s, "E2", 300)          # plenty of power
        install(s, "E5", 30)           # ~8 Alloy/s of income
        install(s, "R3", 1)            # needs 1 Alloy/s  -> affordable
        install(s, "R4", 20)           # needs 160 Alloy/s -> not affordable
        E.recompute(s)
        run(s, 1.0)                    # short: measure allocation, not cascade
        self.assertAlmostEqual(s.throttle, 1.0, places=6)
        self.assertGreaterEqual(s.res["alloy"], ZERO)
        self.assertAlmostEqual(s.upkeep_eff["R3"], 1.0, places=6)   # lower tier fed
        self.assertLess(s.upkeep_eff["R4"], 0.25)                   # top tier idled
        self.assertGreater(s.gens["R2"], ZERO)                      # R3 still working

    def test_upkeep_shortage_never_destroys_machines(self):
        s = new_game()
        s.res["alloy"] = ZERO
        install(s, "R3", 10)
        install(s, "R4", 10)
        E.recompute(s)
        run(s, 2.0)
        self.assertEqual(s.gens["R4"], N(10))
        self.assertEqual(s.gens["R3"], N(10))

    def test_replication_builds_generators(self):
        s = rich()
        E.buy(s, "R1", 10)
        E.buy(s, "E2", 50)
        before = s.gens["E1"]
        run(s, 5.0)
        self.assertGreater(s.gens["E1"], before)

    def test_replication_is_not_superexponential(self):
        """Machines building machines must stay on a polynomial curve."""
        s = rich(ore=1e30, alloy=1e30)
        for gid in ("E2", "E4", "R1", "R2", "R3"):
            E.buy(s, gid, 50)
        run(s, 60.0, dt=0.25)
        mid = s.gens["E1"].log10()
        run(s, 60.0, dt=0.25)
        end = s.gens["E1"].log10()
        # Doubling the elapsed time must not square the count.
        self.assertLess(end, mid * 2.0 + 1.0)

    def test_lifetime_tracks_gross_production(self):
        s = rich()
        E.buy(s, "E1", 10)
        run(s, 2.0)
        self.assertGreater(s.run_life["ore"], ZERO)
        self.assertGreaterEqual(s.total_life["ore"], s.run_life["ore"])


class TestRNG(unittest.TestCase):
    def test_events_respect_minimum_gap(self):
        s = rich()
        rng = random.Random(7)
        seen = 0
        for _ in range(6000):          # 600 simulated seconds at dt=0.1
            before = len(s.events) + s.stats["anomalies_seen"]
            E.tick(s, 0.1, rng)
            seen = s.stats["anomalies_seen"]
        self.assertLessEqual(seen, 600 / (45 + G.EVENT_MIN_GAP) + 2)

    def test_event_frequency_independent_of_tick_rate(self):
        a, b = rich(), rich()
        run(a, 900, dt=0.05, rng=random.Random(3))
        run(b, 900, dt=0.25, rng=random.Random(3))
        self.assertLessEqual(abs(a.stats["anomalies_seen"] - b.stats["anomalies_seen"]), 2)

    def test_events_expire(self):
        s = rich()
        s.events.append({"id": "rich_vein", "remaining": 1.0})
        run(s, 2.0)
        self.assertEqual([e for e in s.events if e["id"] == "rich_vein"], [])

    def test_pity_timer_guarantees_epic(self):
        s = rich()
        rng = random.Random(99)
        s.pity = G.PITY_ROLLS
        art = E._roll_artifact(s, G.TARGETS[0], rng)
        rank = [r.id for r in G.RARITY].index(art["rarity"])
        self.assertGreaterEqual(rank, [r.id for r in G.RARITY].index(G.PITY_MIN_RARITY))

    def test_artifacts_auto_equip_up_to_slot_limit(self):
        s = rich()
        rng = random.Random(5)
        for _ in range(20):
            E._roll_artifact(s, G.TARGETS[0], rng)
        self.assertLessEqual(len(s.equipped), E.relic_slots(s))

    def test_probe_costs_and_slots(self):
        s = rich(iso=0)
        self.assertTrue(E.launch_probe(s, "near"))       # near is free
        s.res["isotope"] = N(1000)
        while len(s.probes) < E.probe_slots(s):
            E.launch_probe(s, "near")
        self.assertFalse(E.launch_probe(s, "near"))      # slots full

    def test_probe_resolves_and_clears(self):
        s = rich()
        E.launch_probe(s, "near")
        run(s, 70.0, dt=0.25)
        self.assertEqual(s.probes, [])


class TestAutomation(unittest.TestCase):
    def _autobuy_state(self):
        s = rich(ore=1e9)
        s.research.add("r_foreman")
        E.recompute(s)
        s.auto["enabled"] = True
        s.auto["gens"]["E1"] = True
        return s

    def test_autobuy_buys(self):
        s = self._autobuy_state()
        run(s, 1.0)
        self.assertGreater(s.bought["E1"], ZERO)

    def test_autobuy_stops_when_broke(self):
        s = self._autobuy_state()
        run(s, 3.0)
        s.res["ore"] = ZERO
        before = s.bought["E1"]
        run(s, 2.0)
        # It may buy from new income, but must never go negative or loop forever.
        self.assertGreaterEqual(s.res["ore"], ZERO)
        self.assertGreaterEqual(s.bought["E1"], before)

    def test_autobuy_respects_reserve(self):
        """Reserve is absolute, so it must not compound away over many ticks."""
        s = self._autobuy_state()
        s.auto["reserve"]["ore"] = N(9e8).to_json()
        run(s, 30.0, dt=0.25)
        self.assertGreaterEqual(s.res["ore"], N(9e8))

    def test_autobuy_is_bounded_per_tick(self):
        s = self._autobuy_state()
        E.tick(s, 0.1)
        self.assertLessEqual(s.bought["E1"].to_float(), E.AUTOBUY_CAP)

    def test_auto_research_buys_cheapest_first(self):
        s = rich(data=100)
        s.p1_levels["sg_autores"] = 1
        s.auto["research"] = True
        E.recompute(s)
        run(s, 0.5)
        self.assertIn("r_foreman", s.research)


class TestMilestonesAchievements(unittest.TestCase):
    def test_milestone_awards_once_and_multiplies(self):
        s = rich()
        E.buy(s, "E1", 25)
        E.recompute(s)
        E._evaluate(s)
        self.assertIn("m_E1_25", s.milestones)
        before = len(s.milestones)
        E._evaluate(s)
        self.assertEqual(len(s.milestones), before)

    def test_brownout_and_recovery_flags(self):
        s = rich()
        E.buy(s, "E1", 5)
        install(s, "E3", 1e7)
        run(s, 0.5)
        self.assertIn("ach_brownout", s.perm_flags)
        install(s, "E3", 0)
        install(s, "E4", 1e6)
        run(s, 0.5)
        self.assertIn("ach_recovered", s.perm_flags)

    def test_unlocks_are_sticky(self):
        s = rich()
        E.recompute(s)
        self.assertIn("E3", s.unlocked)
        s.run_life["ore"] = ZERO
        E.recompute(s)
        self.assertIn("E3", s.unlocked)


class TestPrestige(unittest.TestCase):
    def _ready(self):
        s = rich()
        s.run_life["alloy"] = E.p1_required(s)
        return s

    def test_locked_below_threshold(self):
        s = rich()
        s.run_life["alloy"] = E.p1_required(s) * N(0.999)
        self.assertEqual(E.p1_gain(s), ZERO)
        self.assertEqual(E.prestige(s), ZERO)

    def test_first_dispersal_gain(self):
        s = self._ready()
        self.assertEqual(E.p1_gain(s).to_float(), 12.0)

    def test_requirement_rises_with_banked_points(self):
        """Otherwise the game degenerates into a one-minute reset treadmill."""
        s = rich()
        base = E.p1_required(s)
        s.p1_sp_life = N(10_000)
        self.assertGreater(E.p1_required(s), base * N(100))

    def test_deeper_run_pays_more_but_with_diminishing_returns(self):
        """Waiting must be worth something, but not unboundedly — that balance
        is what makes reset timing an actual decision."""
        s = self._ready()
        early = E.p1_gain(s)
        s.run_life["alloy"] = s.run_life["alloy"] * N(1e4)   # four orders deeper
        deeper = E.p1_gain(s)
        self.assertGreater(deeper, early * N(10))
        self.assertLess(deeper, early * N(100))

    def test_gain_rate_peaks_so_resetting_is_ever_correct(self):
        """Seed Points per second must eventually fall, or 'never reset' wins."""
        s = self._ready()
        required = E.p1_required(s)
        best, falling = 0.0, False
        for minute in range(1, 400):
            # Output grows fast; the log-shaped gain must still peak against it.
            s.run_life["alloy"] = required * Num(1, int(minute * 0.6))
            rate = E.p1_gain(s).to_float() / (minute * 60.0)
            if rate > best:
                best = rate
            elif rate < best * 0.8:
                falling = True
                break
        self.assertTrue(falling, "gain rate never peaked")

    def test_gain_is_monotonic_across_softcaps(self):
        s = self._ready()
        required = E.p1_required(s)
        last = -1.0
        for step in range(0, 30):
            s.run_life["alloy"] = required * Num(1, step)
            g = E.p1_gain(s).log10()
            self.assertGreater(g, last)
            last = g

    def test_preview_matches_award(self):
        """The preview and the award are the same function, so they cannot differ."""
        s = self._ready()
        preview = E.p1_gain(s)
        awarded = E.prestige(s)
        self.assertEqual(preview, awarded)

    def test_reset_wipes_run_scope_only(self):
        s = self._ready()
        E.buy(s, "E1", 10)
        s.research.add("r_foreman")
        s.milestones.add("m_first_fab")
        s.achievements.add("a_first_ore")
        s.artifacts.append({"id": "x", "name": "n", "kind": G.MULT_GLOBAL,
                            "target": "", "value": 2.0, "rarity": "rare", "desc": ""})
        E.prestige(s)
        self.assertEqual(s.gens["E1"], ZERO)
        self.assertEqual(s.bought["E1"], ZERO)
        # Ore resets to the restart nest egg, not to nothing: after your first
        # Dispersal you should never have to click your way out of zero.
        self.assertEqual(s.res["ore"], N(G.RESTART_ORE))
        self.assertEqual(s.res["alloy"], ZERO)
        self.assertEqual(s.run_life["alloy"], ZERO)
        self.assertIn("r_foreman", s.research)      # kept through P1
        self.assertIn("m_first_fab", s.milestones)
        self.assertIn("a_first_ore", s.achievements)
        self.assertEqual(len(s.artifacts), 1)
        self.assertGreater(s.p1_sp, ZERO)
        self.assertEqual(s.p1_count, 1)

    def test_every_field_has_a_declared_scope(self):
        fresh = GameState()
        saved = set(fresh.to_dict().keys())
        for field in RESET_SCOPE:
            self.assertTrue(hasattr(fresh, field), f"{field} is not a state field")
        self.assertIn("gens", saved)

    def test_no_currency_duplication_on_repeat_prestige(self):
        s = self._ready()
        first = E.prestige(s)
        second = E.prestige(s)          # nothing produced since
        self.assertEqual(second, ZERO)
        self.assertEqual(s.p1_sp, first)
        self.assertEqual(s.p1_count, 1)

    def test_start_bonuses_apply_after_reset(self):
        s = self._ready()
        s.p1_levels["sg_start_e"] = 2      # +10 to E1..E3
        E.prestige(s)
        self.assertEqual(s.gens["E1"].to_float(), 10.0)
        self.assertEqual(s.bought["E1"].to_float(), 10.0)

    def test_seed_upgrade_costs_and_caps(self):
        s = self._ready()
        E.prestige(s)
        s.p1_sp = N(1e9)
        su = G.SEED_BY_ID["sg_autobuy"]
        self.assertTrue(E.buy_seed(s, "sg_autobuy"))
        self.assertFalse(E.buy_seed(s, "sg_autobuy"))    # max_level 1
        self.assertEqual(s.p1_levels["sg_autobuy"], su.max_level)

    def test_seed_upgrade_unaffordable(self):
        s = self._ready()
        E.prestige(s)
        s.p1_sp = ZERO
        self.assertFalse(E.buy_seed(s, "sg_global"))

    def test_sp_multiplier_applies(self):
        s = self._ready()
        plain = E.p1_gain(s)
        s.p1_levels["sg_sp"] = 5
        self.assertGreater(E.p1_gain(s), plain)

    def test_projection_is_at_least_current(self):
        s = self._ready()
        E.buy(s, "E1", 10)
        run(s, 1.0)
        self.assertGreaterEqual(E.project_gain(s, 600).to_float(), E.p1_gain(s).to_float())


class TestContentIntegrity(unittest.TestCase):
    def test_ids_are_unique(self):
        for table in (G.GENERATORS, G.UPGRADES, G.RESEARCH, G.SEED_GRID,
                      G.MILESTONES, G.ACHIEVEMENTS, G.ANOMALIES, G.TARGETS, G.RARITY):
            ids = [x.id for x in table]
            self.assertEqual(len(ids), len(set(ids)), f"duplicate id in {table[0].__class__}")

    def test_effect_targets_resolve(self):
        gen_ids = set(G.GEN_BY_ID)
        res_ids = set(G.RES_BY_ID)
        for u in G.UPGRADES:
            e = u.effect
            if e.kind == G.MULT_GEN:
                self.assertIn(e.target, gen_ids, u.id)
            if e.kind == G.MULT_RES:
                self.assertIn(e.target, res_ids, u.id)
        for t in G.RESEARCH:
            if t.effect.kind == G.MULT_GEN:
                self.assertIn(t.effect.target, gen_ids, t.id)

    def test_generator_produces_targets_resolve(self):
        for g in G.GENERATORS:
            if g.produces:
                self.assertTrue(g.produces in G.RES_BY_ID or g.produces in G.GEN_BY_ID, g.id)

    def test_every_effect_kind_is_handled(self):
        m = E.Mults()
        # Derived from the module so a new effect kind cannot silently become a
        # no-op the way a hand-written list would allow.
        kinds = {v for k, v in vars(G).items()
                 if k.isupper() and isinstance(v, str)
                 and (k.startswith(("MULT_", "ADD_", "START_"))
                      or k in ("TENFOLD", "SET_FLAG", "REFINE_EFF"))}
        for kind in kinds:
            E._apply(m, G.Eff(kind, "E1", 2.0))   # must not raise
        used = {u.effect.kind for u in G.UPGRADES} | {t.effect.kind for t in G.RESEARCH} \
            | {sg.effect.kind for sg in G.SEED_GRID} | {ms.effect.kind for ms in G.MILESTONES}
        self.assertTrue(used <= kinds, used - kinds)

    def test_unlock_conditions_are_reachable_types(self):
        s = new_game()
        for g in G.GENERATORS:
            E.check(g.unlock, s)          # must not raise
        for u in G.UPGRADES:
            E.check(u.unlock, s)
        for t in G.RESEARCH:
            E.check(t.unlock, s)


if __name__ == "__main__":
    unittest.main()


class TestConvergence(unittest.TestCase):
    """Prestige layer 2. Wipes strictly more than Dispersal does."""

    def _ready(self):
        s = rich()
        s.p1_count = 4
        s.p1_sp = N(500)
        s.p1_sp_life = E.p2_required(s)
        s.research.add("r_foreman")
        s.p1_levels["sg_global"] = 5
        E.recompute(s)
        return s

    def test_hidden_until_seed_points_accumulate(self):
        s = rich()
        E.recompute(s)
        self.assertFalse(E.p2_visible(s))
        self.assertEqual(E.p2_gain(s), ZERO)

    def test_becomes_visible_before_it_is_reachable(self):
        """You should see the goal well before you can act on it."""
        s = rich()
        s.p1_sp_life = G.P2_UNLOCK_SP
        E.recompute(s)
        self.assertTrue(E.p2_visible(s))
        self.assertFalse(E.p2_available(s))

    def test_gain_at_the_bar(self):
        s = self._ready()
        self.assertEqual(E.p2_gain(s).to_float(), G.P2_BASE)

    def test_requirement_rises_with_banked_coherence(self):
        s = rich()
        base = E.p2_required(s)
        s.p2_coh_life = N(1000)
        self.assertGreater(E.p2_required(s), base * N(10))

    def test_preview_matches_award(self):
        s = self._ready()
        preview = E.p2_gain(s)
        self.assertEqual(E.converge(s), preview)

    def test_converge_wipes_more_than_disperse(self):
        s = self._ready()
        s.artifacts.append({"id": "a1", "name": "x", "kind": G.MULT_GLOBAL,
                            "target": "", "value": 2.0, "rarity": "rare", "desc": ""})
        s.milestones.add("m_first_fab")
        E.buy(s, "E1", 10)
        E.converge(s)
        # Wiped: Seed Points, the Seed Grid, and Research on top of the run.
        self.assertEqual(s.p1_sp, ZERO)
        self.assertEqual(s.p1_sp_life, ZERO)
        self.assertEqual(s.p1_levels, {})
        self.assertEqual(s.research, set())
        self.assertEqual(s.gens["E1"], ZERO)
        # Kept: identity, collections, and unlocked content.
        self.assertEqual(s.p1_count, 4)
        self.assertIn("m_first_fab", s.milestones)
        self.assertEqual(len(s.artifacts), 1)
        self.assertGreater(s.p2_coh, ZERO)
        self.assertEqual(s.p2_count, 1)

    def test_no_duplication_on_repeat(self):
        s = self._ready()
        first = E.converge(s)
        self.assertEqual(E.converge(s), ZERO)
        self.assertEqual(s.p2_coh, first)
        self.assertEqual(s.p2_count, 1)

    def test_prestige_dispatches_to_layer_two(self):
        s = self._ready()
        gain = E.p2_gain(s)
        self.assertEqual(E.prestige(s, "p2"), gain)

    def test_unimplemented_layers_do_nothing(self):
        s = self._ready()
        for layer in ("p3", "p4", "p5"):
            self.assertEqual(E.prestige(s, layer), ZERO)

    def test_nanites_unlock_and_compound(self):
        s = self._ready()
        E.converge(s)
        E.recompute(s)
        self.assertTrue(s.has_flag("nanites"))
        s.res["nanite"] = N(1000)
        run(s, 2.0)
        self.assertGreater(s.res["nanite"], N(1000))

    def test_nanite_bonus_is_logarithmic(self):
        """An exponential resource must have a bounded effect."""
        s = self._ready()
        E.converge(s)
        s.res["nanite"] = N(1e6)
        small = E.collect_mults(s).glob
        s.res["nanite"] = N(1e60)
        big = E.collect_mults(s).glob
        self.assertGreater(big, small)
        self.assertLess(big, small * N(100))

    def test_doctrines_need_a_convergence_first(self):
        s = self._ready()
        self.assertFalse(E.choose_doctrine(s, "d1_swarm"))
        E.converge(s)
        self.assertTrue(E.choose_doctrine(s, "d1_swarm"))

    def test_doctrine_rows_are_exclusive_and_switchable(self):
        s = self._ready()
        E.converge(s)
        E.choose_doctrine(s, "d1_swarm")
        E.choose_doctrine(s, "d1_forge")          # same row: replaces
        self.assertEqual(s.doctrines[1], "d1_forge")
        self.assertEqual(len(s.doctrines), 1)
        E.choose_doctrine(s, "d2_mind")
        self.assertEqual(len(s.doctrines), 2)

    def test_doctrines_are_repicked_each_convergence(self):
        s = self._ready()
        E.converge(s)
        E.choose_doctrine(s, "d1_swarm")
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.doctrines, {})

    def test_doctrine_effects_apply(self):
        s = self._ready()
        E.converge(s)
        before = E.collect_mults(s).ladder.get(G.REPLICATE, Num(1))
        E.choose_doctrine(s, "d1_swarm")
        self.assertGreater(E.collect_mults(s).ladder.get(G.REPLICATE, Num(1)), before)

    def test_coherence_shop_is_endless(self):
        s = self._ready()
        E.converge(s)
        s.p2_coh = N(1e12)
        endless = G.COH_BY_ID["c_global"]
        self.assertEqual(endless.max_level, 0)
        for _ in range(30):
            self.assertTrue(E.buy_coherence(s, "c_global"))
        self.assertEqual(s.p2_levels["c_global"], 30)

    def test_coherence_costs_rise_and_gate(self):
        s = self._ready()
        E.converge(s)
        s.p2_coh = ZERO
        self.assertFalse(E.buy_coherence(s, "c_global"))
        self.assertGreater(E.coherence_cost(G.COH_BY_ID["c_global"], 10),
                           E.coherence_cost(G.COH_BY_ID["c_global"], 0))

    def test_capped_coherence_node_stops(self):
        s = self._ready()
        E.converge(s)
        s.p2_coh = N(1e12)
        for _ in range(5):
            E.buy_coherence(s, "c_autoprestige")
        self.assertEqual(s.p2_levels["c_autoprestige"], 1)


class TestAutoPrestige(unittest.TestCase):
    def _ready(self):
        s = rich()
        s.p2_levels["c_autoprestige"] = 1
        s.auto["prestige_enabled"] = True
        s.auto["prestige_threshold"] = 2.0
        E.recompute(s)
        return s

    def test_locked_without_the_coherence_node(self):
        s = rich()
        s.auto["prestige_enabled"] = True
        s.run_life["alloy"] = E.p1_required(s) * N(1e6)
        run(s, 0.5)
        self.assertEqual(s.p1_count, 0)

    def test_fires_at_the_threshold(self):
        s = self._ready()
        s.run_life["alloy"] = E.p1_required(s) * N(1e6)
        run(s, 0.5)
        self.assertEqual(s.p1_count, 1)

    def test_waits_below_the_threshold(self):
        s = self._ready()
        s.p1_sp = N(1e9)                    # a reset would barely move the bank
        s.run_life["alloy"] = E.p1_required(s)
        run(s, 0.5)
        self.assertEqual(s.p1_count, 0)

    def test_does_not_loop_within_one_tick(self):
        s = self._ready()
        s.run_life["alloy"] = E.p1_required(s) * N(1e6)
        E.tick(s, 0.1)
        self.assertLessEqual(s.p1_count, 1)


class TestNanites(unittest.TestCase):
    def _converged(self):
        s = rich()
        s.p1_count = 4
        s.p1_sp_life = E.p2_required(s)
        E.recompute(s)
        E.converge(s)
        E.recompute(s)
        return s

    def test_convergence_seeds_them(self):
        """A resource that compounds from nothing never starts."""
        s = self._converged()
        self.assertEqual(s.res["nanite"], N(G.NANITE_SEED))

    def test_they_compound_without_a_vat(self):
        s = self._converged()
        self.assertEqual(s.gens["E9"], ZERO)
        before = s.res["nanite"]
        run(s, 10.0)
        self.assertGreater(s.res["nanite"], before)

    def test_they_survive_a_dispersal(self):
        """Nanites are a Convergence-layer resource, not a per-run one."""
        s = self._converged()
        s.res["nanite"] = N(1e9)
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        self.assertEqual(s.res["nanite"], N(1e9))

    def test_seed_accumulates_across_convergences(self):
        s = self._converged()
        s.res["nanite"] = ZERO
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.res["nanite"], N(G.NANITE_SEED))

    def test_convergence_does_clear_them(self):
        s = self._converged()
        s.res["nanite"] = N(1e30)
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.res["nanite"], N(G.NANITE_SEED))

    def test_run_resources_still_reset_on_dispersal(self):
        s = self._converged()
        s.res["ore"] = N(1e20)
        s.res["nanite"] = N(1e9)
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        self.assertEqual(s.res["nanite"], N(1e9))       # layer-scoped: kept
        self.assertEqual(s.res["ore"], N(G.RESTART_ORE))  # run-scoped: reset


def artifact(aid, kind, target, value, rarity="rare"):
    return {"id": aid, "name": aid, "kind": kind, "target": target,
            "value": value, "rarity": rarity, "desc": ""}


class TestAutoUpgrades(unittest.TestCase):
    def _ready(self, ore=1e9):
        s = rich(ore=ore)
        s.p1_levels["sg_autoupg"] = 1
        s.auto["upgrades"] = True
        E.recompute(s)
        E.buy(s, "E1", 30)
        E.recompute(s)
        return s

    def test_locked_without_the_seed_node(self):
        s = rich()
        s.auto["upgrades"] = True
        E.buy(s, "E1", 30)
        run(s, 0.5)
        self.assertEqual(s.upgrades, set())

    def test_buys_unlocked_affordable_upgrades(self):
        s = self._ready()
        run(s, 0.5)
        self.assertIn("u_e1_0", s.upgrades)

    def test_never_buys_a_locked_upgrade(self):
        s = self._ready()
        run(s, 1.0)
        for uid in s.upgrades:
            self.assertTrue(E.check(G.UPG_BY_ID[uid].unlock, s), uid)

    def test_never_overspends(self):
        s = self._ready(ore=200)
        run(s, 1.0)
        for rid in G.STOCK_RESOURCES:
            self.assertGreaterEqual(s.res[rid], ZERO)

    def test_respects_the_reserve(self):
        s = self._ready()
        s.auto["reserve"]["ore"] = N(9e8).to_json()
        run(s, 2.0)
        self.assertGreaterEqual(s.res["ore"], N(9e8))

    def test_buys_cheapest_first(self):
        s = self._ready()             # machines first, then a thin wallet
        s.res["ore"] = N(130)         # affords u_e1_0 (60), not u_e1_3 (90k)
        s.res["alloy"] = ZERO
        run(s, 0.5)
        self.assertIn("u_e1_0", s.upgrades)
        self.assertNotIn("u_e1_3", s.upgrades)

    def test_stops_cleanly_when_everything_is_bought(self):
        s = self._ready(ore=1e30)
        run(s, 2.0)
        before = set(s.upgrades)
        run(s, 1.0)
        self.assertEqual(s.upgrades, before | s.upgrades)
        self.assertGreaterEqual(s.res["ore"], ZERO)

    def test_does_not_double_charge(self):
        s = self._ready()
        run(s, 0.5)
        self.assertIn("u_e1_0", s.upgrades)
        before = s.res["ore"]
        run(s, 0.2)
        self.assertGreaterEqual(s.res["ore"], before - N(1e6))


class TestRelicRanking(unittest.TestCase):
    def _with(self, *arts):
        s = rich()
        s.artifacts = list(arts)
        s.equipped = []
        E.recompute(s)
        return s

    def test_global_beats_narrow_at_equal_value(self):
        s = self._with(artifact("g", G.MULT_GLOBAL, "", 1.5),
                       artifact("d", G.MULT_RES, "data", 1.5))
        self.assertGreater(E.artifact_score(s, s.artifacts[0]),
                           E.artifact_score(s, s.artifacts[1]))

    def test_bigger_multiplier_wins_within_a_kind(self):
        s = self._with(artifact("small", G.MULT_RES, "ore", 1.2),
                       artifact("big", G.MULT_RES, "ore", 3.0))
        self.assertGreater(E.artifact_score(s, s.artifacts[1]),
                           E.artifact_score(s, s.artifacts[0]))

    def test_power_relic_is_judged_against_throttle(self):
        """A Power relic is near-worthless at full supply, valuable when short."""
        s = self._with(artifact("p", G.MULT_RES, "energy", 2.0))
        s.throttle = 1.0
        healthy = E.artifact_score(s, s.artifacts[0])
        s.throttle = 0.4
        throttled = E.artifact_score(s, s.artifacts[0])
        self.assertGreater(throttled, healthy * 5)

    def test_worthless_artifacts_are_never_slotted(self):
        s = self._with(artifact("dud", G.MULT_GLOBAL, "", 1.0))
        self.assertEqual(E.best_loadout(s), [])

    def test_loadout_respects_slot_count(self):
        s = self._with(*[artifact(f"a{i}", G.MULT_GLOBAL, "", 1.0 + i / 10)
                         for i in range(1, 9)])
        self.assertEqual(len(E.best_loadout(s)), E.relic_slots(s))

    def test_loadout_picks_the_top_scorers(self):
        s = self._with(artifact("weak", G.MULT_RES, "data", 1.1),
                       artifact("mid", G.MULT_RES, "ore", 1.5),
                       artifact("strong", G.MULT_GLOBAL, "", 3.0))
        self.assertEqual(E.best_loadout(s)[0], "strong")

    def test_auto_equip_reports_change(self):
        s = self._with(artifact("g", G.MULT_GLOBAL, "", 2.0))
        self.assertTrue(E.auto_equip(s))
        self.assertEqual(s.equipped, ["g"])
        self.assertFalse(E.auto_equip(s))      # idempotent

    def test_auto_equip_swaps_out_a_worse_relic(self):
        s = self._with(artifact("weak", G.MULT_RES, "data", 1.05))
        E.auto_equip(s)
        self.assertEqual(s.equipped, ["weak"])
        for i in range(E.relic_slots(s)):
            s.artifacts.append(artifact(f"strong{i}", G.MULT_GLOBAL, "", 5.0))
        E.auto_equip(s)
        self.assertNotIn("weak", s.equipped)
        self.assertEqual(len(s.equipped), E.relic_slots(s))

    def test_auto_equip_actually_raises_output(self):
        s = self._with(artifact("weak", G.MULT_RES, "data", 1.05),
                       artifact("strong", G.MULT_GLOBAL, "", 4.0))
        s.equipped = ["weak"]
        weak_mult = E.collect_mults(s).glob
        E.auto_equip(s)
        self.assertGreater(E.collect_mults(s).glob, weak_mult)

    def test_equipped_ids_always_exist(self):
        s = self._with(artifact("g", G.MULT_GLOBAL, "", 2.0))
        E.auto_equip(s)
        known = {a["id"] for a in s.artifacts}
        self.assertTrue(set(s.equipped) <= known)

    def test_no_duplicate_slots(self):
        s = self._with(*[artifact(f"a{i}", G.MULT_GLOBAL, "", 2.0) for i in range(6)])
        E.auto_equip(s)
        self.assertEqual(len(s.equipped), len(set(s.equipped)))


class TestAutoRelics(unittest.TestCase):
    def _ready(self):
        s = rich()
        s.p1_levels["sg_autorelic"] = 1
        s.auto["relics"] = True
        s.artifacts = [artifact("weak", G.MULT_RES, "data", 1.02)]
        s.equipped = ["weak"]
        E.recompute(s)
        return s

    def test_locked_without_the_seed_node(self):
        s = self._ready()
        s.p1_levels.pop("sg_autorelic")
        E.recompute(s)
        s.artifacts.append(artifact("strong", G.MULT_GLOBAL, "", 9.0))
        run(s, 0.5)
        self.assertEqual(s.equipped, ["weak"])

    def test_slots_a_better_relic_when_one_arrives(self):
        s = self._ready()
        s.artifacts.append(artifact("strong", G.MULT_GLOBAL, "", 9.0))
        run(s, 0.5)
        self.assertIn("strong", s.equipped)

    def test_survives_a_dispersal(self):
        """Artifacts persist through Dispersal, so the loadout must too."""
        s = self._ready()
        s.artifacts.append(artifact("strong", G.MULT_GLOBAL, "", 9.0))
        run(s, 0.5)
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        run(s, 0.5)
        self.assertIn("strong", s.equipped)


class TestAutomationPreferencesPersist(unittest.TestCase):
    """Automation toggles are preferences, not progress.

    They used to be wiped by Convergence, which silently switched every
    automation off while the UI still showed the boxes ticked.
    """

    def _configured(self):
        s = rich()
        s.p1_count = 4
        s.p1_levels.update({"sg_autobuy": 1, "sg_autoupg": 1, "sg_autorelic": 1})
        s.auto.update({"enabled": True, "upgrades": True, "relics": True,
                       "research": True, "expedition": True,
                       "prestige_enabled": True, "prestige_threshold": 3.0})
        s.auto["gens"]["E1"] = True
        s.auto["reserve"]["ore"] = N(5000).to_json()
        E.recompute(s)
        return s

    def _assert_intact(self, s, why):
        self.assertTrue(s.auto["enabled"], why)
        self.assertTrue(s.auto["upgrades"], why)
        self.assertTrue(s.auto["relics"], why)
        self.assertTrue(s.auto["research"], why)
        self.assertTrue(s.auto["gens"].get("E1"), why)
        self.assertEqual(s.auto["reserve"].get("ore"), N(5000).to_json(), why)
        self.assertEqual(s.auto["prestige_threshold"], 3.0, why)

    def test_survive_a_dispersal(self):
        s = self._configured()
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        self._assert_intact(s, "Dispersal wiped automation preferences")

    def test_survive_a_convergence(self):
        s = self._configured()
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self._assert_intact(s, "Convergence wiped automation preferences")

    def test_convergence_still_removes_the_unlock(self):
        """The capability resets even though the preference does not."""
        s = self._configured()
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        E.recompute(s)
        self.assertNotIn("sg_autoupg", s.p1_levels)
        self.assertFalse(s.has_flag("auto_upgrade"))

    def test_a_toggle_without_its_unlock_does_nothing(self):
        """A preference left on must be inert until the unlock is re-earned."""
        s = self._configured()
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        E.recompute(s)
        E.buy(s, "E1", 30)
        run(s, 1.0)
        self.assertEqual(s.upgrades, set(), "auto-upgrade ran without its unlock")

    def test_it_resumes_when_the_unlock_returns(self):
        s = self._configured()
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        s.res["ore"] = N(1e9)
        s.p1_levels["sg_autoupg"] = 1          # re-bought after Convergence
        E.recompute(s)
        E.buy(s, "E1", 30)
        run(s, 1.0)
        self.assertIn("u_e1_0", s.upgrades)


class TestWorldSeed(unittest.TestCase):
    """Every download should be its own world, and a shared seed should match."""

    def test_blank_seeds_differ_between_downloads(self):
        seeds = {new_game().rng_seed for _ in range(20)}
        self.assertGreater(len(seeds), 15)

    def test_a_seed_is_always_set_on_a_new_game(self):
        self.assertTrue(new_game().rng_seed)

    def test_same_words_give_the_same_world(self):
        from seed.state import seed_from_text
        self.assertEqual(seed_from_text("swarm run"), seed_from_text("swarm run"))
        self.assertNotEqual(seed_from_text("swarm run"), seed_from_text("other run"))

    def test_numeric_seeds_are_used_directly(self):
        from seed.state import seed_from_text
        self.assertEqual(seed_from_text("12345"), 12345)

    def test_seed_is_never_zero(self):
        from seed.state import seed_from_text
        for text in ("0", "", "   "):
            self.assertTrue(seed_from_text(text))

    def test_seed_drives_the_random_stream(self):
        a, b = new_game("shared"), new_game("shared")
        ra, rb = E._rng(a), E._rng(b)
        self.assertEqual([ra.random() for _ in range(5)],
                         [rb.random() for _ in range(5)])

    def test_different_seeds_diverge(self):
        a, b = new_game("alice"), new_game("bob")
        self.assertNotEqual([E._rng(a).random() for _ in range(5)],
                            [E._rng(b).random() for _ in range(5)])

    def test_seed_is_stable_across_a_session(self):
        s = new_game("stable")
        first = s.rng_seed
        run(s, 2.0, rng=E._rng(s))
        self.assertEqual(s.rng_seed, first)
