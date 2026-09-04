"""Prestige layer 5: Recursion.

Its identity is the verb change again: layers 1-4 sold upgrades, choices, floors
and exponents. Recursion sells DIFFICULTY. You descend into a deliberately worse
copy of the universe, because the worse it is, the more it pays.

Most of what is pinned here is the shape of the handicap: it has to bite without
bricking, and the payout has to reward speed without minting.
"""

import dataclasses
import random
import time
import unittest

from seed import engine as E
from seed import gamedata as G
from seed.bignum import N, Num, ZERO
from seed.state import RESET_SCOPE, GameState, new_game


def run(s, seconds, dt=0.25, rng=None):
    rng = rng or random.Random(13)
    for _ in range(int(seconds / dt)):
        E.tick(s, dt, rng)


def ready(sub=400):
    """A player deep enough in the Substrate era to Recurse."""
    s = new_game()
    s.p1_count, s.p2_count, s.p3_count, s.p4_count = 300, 40, 12, 3
    s.p4_sub = N(sub)
    s.p4_sub_life = N(sub)
    s.p4_levels["sb_exponent"] = 20
    s.p3_levels["ow_global"] = 8
    s.p2_levels["c_global"] = 6
    s.p1_levels["sg_global"] = 10
    s.research.add("r_landfall")
    s.upgrades.add("u_ore1")
    s.milestones.add("m_first_fab")
    s.res["exotic"] = N(1e9)
    E.recompute(s)
    return s


class TestGating(unittest.TestCase):
    def test_hidden_early(self):
        s = new_game()
        E.recompute(s)
        self.assertFalse(E.p5_visible(s))

    def test_visible_once_substrate_is_earned(self):
        s = ready()
        self.assertTrue(E.p5_visible(s))

    def test_the_layer_is_implemented(self):
        layer = G.LAYER_BY_ID["p5"]
        self.assertTrue(layer.implemented)
        self.assertIn(G.SUB, layer.wipes)

    def test_cond_recurse_is_actually_checked(self):
        """Cond.converge and Cond.overwrite BOTH shipped unchecked.

        The guard test derives its field list from the dataclass, so a new gate
        that `check()` ignores fails here rather than silently granting every
        milestone that uses it on a brand new game.
        """
        s = new_game()
        for field in dataclasses.fields(G.Cond):
            if field.name in ("res", "amount", "lifetime", "count",
                              "all_of", "any_of"):
                continue
            probe = G.Cond(**{field.name: 1 if field.type == "int" else "nope"}) \
                if field.type == "int" else None
            if probe is None:
                continue
            self.assertFalse(
                E.check(probe, s),
                f"Cond.{field.name} is never checked: it passes on a new game")


class TestHandicaps(unittest.TestCase):
    def test_depth_raises_cost_growth_on_every_ladder(self):
        flat, deep = ready(), ready()
        deep.p5_active_depth = 20
        E.recompute(flat)
        E.recompute(deep)
        for g in G.GENERATORS:
            self.assertGreater(
                E.growth_of(deep, g), E.growth_of(flat, g),
                f"{g.id} is not harder at depth 20")

    def test_handicaps_never_touch_the_exponent(self):
        """A ^0.9 handicap stacked to depth 40 is ^0.015. Not difficulty."""
        flat, deep = ready(), ready()
        deep.p5_active_depth = 40
        self.assertEqual(E.collect_mults(deep).exponent,
                         E.collect_mults(flat).exponent)

    def test_named_handicaps_switch_on_at_their_depth(self):
        for mod in G.RECURSE_MODS:
            s = ready()
            s.p5_active_depth = mod.depth - 1
            self.assertFalse(E.depth_mod(s, mod.id), f"{mod.id} fired early")
            s.p5_active_depth = mod.depth
            self.assertTrue(E.depth_mod(s, mod.id), f"{mod.id} never fired")

    def test_dead_frame_disables_artifacts(self):
        s = ready()
        art = E._roll_artifact(s, G.TARGETS[0], random.Random(4))
        s.equipped = [art["id"]]
        E.recompute(s)
        # Compared on the generator the relic actually targets: a rolled relic
        # is not necessarily global, and asserting on `glob` would pass or fail
        # on the seed rather than on the handicap.
        probe = art.get("target") or "E1"
        if probe not in s.mults:
            probe = "E1"
        with_relic = s.mults[probe]
        s.p5_active_depth = G.MOD_BY_ID["norelic"].depth
        E.recompute(s)
        self.assertLess(s.mults[probe], with_relic,
                        "the Relic Frame still paid at Dead Frame depth")

    def test_silent_sky_stops_anomalies(self):
        s = ready()
        s.p5_active_depth = G.MOD_BY_ID["noanom"].depth
        E.recompute(s)
        run(s, 3000)
        self.assertEqual(s.events, [])

    def test_sterile_stops_machines_building_machines(self):
        s = ready()
        s.p5_active_depth = G.MOD_BY_ID["norep"].depth
        s.gens["R1"] = N(1e6)
        s.bought["R1"] = N(1e6)
        s.unlocked.update({"R1", "E1"})
        E.recompute(s)
        before = s.gens["E1"]
        run(s, 60)
        self.assertEqual(s.gens["E1"], before)

    def test_hungry_machines_triples_the_draw(self):
        s = ready()
        s.gens["E3"] = s.bought["E3"] = N(1000)
        s.unlocked.add("E3")
        E.recompute(s)
        E.tick(s, 0.25)
        plain = s.energy_demand
        s.p5_active_depth = G.MOD_BY_ID["draw"].depth
        E.recompute(s)
        E.tick(s, 0.25)
        self.assertAlmostEqual((s.energy_demand / plain).to_float(), 3.0, places=6)

    def test_diminished_weakens_the_per_ten_bonus(self):
        s = ready()
        s.p5_active_depth = G.MOD_BY_ID["tenfold"].depth
        m = E.collect_mults(s)
        self.assertAlmostEqual(E._tenfold_step(G.GEN_BY_ID["E1"], m), 1.05,
                               places=6)

    def test_shallow_water_softens_and_floors(self):
        s = ready()
        s.p5_active_depth = 100
        E.recompute(s)
        harsh = E.growth_of(s, G.GEN_BY_ID["E1"])
        s.p5_levels["rc_shallow"] = 6
        E.recompute(s)
        softened = E.growth_of(s, G.GEN_BY_ID["E1"])
        self.assertLess(softened, harsh)
        # Never below the floor, however much is bought.
        s.p5_levels["rc_shallow"] = 10_000
        E.recompute(s)
        floor_growth = (G.GEN_BY_ID["E1"].growth
                        + G.RECURSE_GROWTH_FLOOR * 100)
        self.assertAlmostEqual(E.growth_of(s, G.GEN_BY_ID["E1"]), floor_growth,
                               places=6)

    def test_handicaps_slow_but_never_block(self):
        """Depth 40 must still be playable: a wall, not a brick."""
        s = ready()
        s.p5_levels["rc_start"] = 8
        E.recurse(s, 40)
        self.assertGreater(s.gens["E1"], ZERO, "Compiled Start gave nothing")
        run(s, 900)
        self.assertGreater(s.run_life.get("ore", ZERO), ZERO,
                           "the economy produced nothing at depth 40")
        # Something, somewhere, must be purchasable once you have earned a bank.
        s.res["ore"] = N(1e40)
        s.res["alloy"] = N(1e40)
        E.recompute(s)
        buyable = [g.id for g in G.GENERATORS
                   if g.id in s.unlocked and E.max_affordable(s, g.id) > 0]
        self.assertTrue(buyable, "nothing at all is buyable at depth 40")


class TestPayout(unittest.TestCase):
    def test_gain_rises_with_depth(self):
        par = G.P5_PAR_BASE
        seq = [E.p5_gain_at(d, par) for d in (1, 5, 20, 50, 100)]
        for a, b in zip(seq, seq[1:]):
            self.assertLess(a, b)

    def test_gain_rises_with_speed(self):
        slow = E.p5_gain_at(20, E.p5_par_time(20))
        fast = E.p5_gain_at(20, E.p5_par_time(20) / 5)
        self.assertGreater(fast, slow)

    def test_the_speed_bonus_is_capped(self):
        """A one-second clear must not mint infinity."""
        self.assertEqual(E.p5_speed_bonus(50, 1e-9), G.P5_SPEED_CAP)
        self.assertEqual(E.p5_speed_bonus(50, 0.0), G.P5_SPEED_CAP)
        huge = E.p5_gain_at(50, 1e-9)
        self.assertEqual(huge, E.p5_gain_at(50, E.p5_par_time(50) / 1000))

    def test_the_speed_bonus_never_penalises(self):
        self.assertEqual(E.p5_speed_bonus(10, 1e9), 1.0)

    def test_targets_are_exponential_in_depth(self):
        self.assertGreater(
            (E.p5_target(20) / E.p5_target(10)).log10(), 30.0)

    def test_clearing_pays_the_moment_it_happens(self):
        """Not on the next Recurse: the first descent would be a pure loss."""
        s = ready()
        E.recurse(s, 1)
        self.assertFalse(s.p5_cleared)
        s.p5_alloy = E.p5_target(1)
        E.tick(s, 0.25)
        self.assertTrue(s.p5_cleared)
        self.assertGreater(s.p5_depth, ZERO)
        self.assertEqual(s.p5_best_depth, 1)

    def test_a_depth_pays_only_once(self):
        s = ready()
        E.recurse(s, 1)
        s.p5_alloy = E.p5_target(1) * N(1e9)
        E.tick(s, 0.25)
        banked = s.p5_depth
        run(s, 300)
        self.assertEqual(s.p5_depth, banked)

    def test_an_uncleared_depth_pays_nothing(self):
        s = ready()
        E.recurse(s, 5)
        s.p5_alloy = E.p5_target(5) / N(100)
        banked = s.p5_depth
        gained = E.recurse(s, 1)
        self.assertEqual(gained, ZERO)
        self.assertEqual(s.p5_depth, banked)

    def test_recursing_out_of_a_cleared_depth_does_not_double_pay(self):
        s = ready()
        E.recurse(s, 1)
        s.p5_alloy = E.p5_target(1)
        E.tick(s, 0.25)
        banked = s.p5_depth
        self.assertEqual(E.recurse(s, 2), ZERO)
        self.assertEqual(s.p5_depth, banked)


class TestResetScope(unittest.TestCase):
    def test_recursion_wipes_the_substrate_era(self):
        s = ready()
        self.assertGreater(s.p4_sub, ZERO)
        self.assertTrue(s.p4_levels)
        E.recurse(s, 1)
        self.assertEqual(s.p4_sub, ZERO)
        self.assertEqual(s.p4_sub_life, ZERO)
        self.assertEqual(s.p4_levels, {})
        self.assertEqual(s.p3_oc, ZERO)
        self.assertEqual(s.p2_coh, ZERO)
        self.assertEqual(s.p1_sp, ZERO)

    def test_the_substrate_era_survives_a_collapse(self):
        """SUB is in no layer's wipe list but Recursion's."""
        for field in ("p4_sub", "p4_sub_life", "p4_levels", "p5_active_depth",
                      "p5_alloy", "p5_run_start", "p5_cleared"):
            self.assertEqual(RESET_SCOPE[field], G.SUB)
        for layer_id in ("p1", "p2", "p3", "p4"):
            self.assertNotIn(G.SUB, G.LAYER_BY_ID[layer_id].wipes)

    def test_everything_p5_survives_a_recursion(self):
        s = ready()
        s.p5_depth = N(500)
        s.p5_depth_life = N(900)
        s.p5_levels["rc_start"] = 7
        s.p5_count = 4
        s.p5_best_depth = 12
        E.recurse(s, 13)
        self.assertEqual(s.p5_depth, N(500))
        self.assertEqual(s.p5_depth_life, N(900))
        self.assertEqual(s.p5_levels["rc_start"], 7)
        self.assertEqual(s.p5_count, 5)
        self.assertEqual(s.p5_best_depth, 12)

    def test_permanent_progress_survives(self):
        s = ready()
        s.achievements.add("a_first")
        s.combat_wins = 30
        arts = list(s.artifacts)
        E.recurse(s, 3)
        self.assertIn("m_first_fab", s.milestones)
        self.assertIn("a_first", s.achievements)
        self.assertEqual(s.combat_wins, 30)
        self.assertEqual(s.artifacts, arts)

    def test_the_depth_survives_the_resets_beneath_it(self):
        s = ready()
        E.recurse(s, 9)
        s.p5_alloy = N(1234)
        s.run_life["alloy"] = N(1e12)
        E.recompute(s)
        E.prestige(s, "p1")
        self.assertEqual(s.p5_active_depth, 9)
        self.assertEqual(s.p5_alloy, N(1234))

    def test_a_save_round_trip_keeps_the_depth(self):
        s = ready()
        E.recurse(s, 7)
        s.p5_alloy = N(4321)
        s.p5_depth = N(88)
        back = GameState.from_dict(s.to_dict())
        self.assertEqual(back.p5_active_depth, 7)
        self.assertEqual(back.p5_alloy, N(4321))
        self.assertEqual(back.p5_depth, N(88))
        self.assertEqual(back.p5_count, s.p5_count)

    def test_elapsed_depth_time_is_a_duration_not_wall_clock(self):
        """No offline progress: closing the game must not buy a speed bonus."""
        s = ready()
        E.recurse(s, 3)
        s.p5_run_start = time.time() - 120.0
        back = GameState.from_dict(s.to_dict())
        self.assertAlmostEqual(back.depth_time(), 120.0, delta=5.0)


class TestTheStack(unittest.TestCase):
    def test_retained_exponent_survives_but_the_lattice_does_not(self):
        s = ready()
        s.p4_levels["sb_exponent"] = 50
        s.p5_levels["rc_exponent"] = 30
        E.recompute(s)
        before = E.collect_mults(s).exponent
        E.recurse(s, 1)
        after = E.collect_mults(s).exponent
        self.assertEqual(s.p4_levels, {}, "the Lattice survived a Recursion")
        self.assertLess(after, before, "the raw Lattice exponent was kept")
        self.assertAlmostEqual(after, 30 * 0.001, places=9)

    def test_standing_army_carries_a_share_of_the_fleet(self):
        s = ready()
        s.p5_levels["rc_army"] = 5          # 50%
        s.gens["D1"] = s.bought["D1"] = N(1000)
        E.recompute(s)
        E.recurse(s, 1)
        self.assertAlmostEqual(s.gens["D1"].to_float(), 500.0, delta=1.0)
        self.assertAlmostEqual(s.bought["D1"].to_float(), 500.0, delta=1.0)

    def test_no_standing_army_means_no_fleet(self):
        s = ready()
        s.gens["D1"] = s.bought["D1"] = N(1000)
        E.recompute(s)
        E.recurse(s, 1)
        self.assertEqual(s.gens["D1"], ZERO)

    def test_compiled_start_seeds_both_ladders(self):
        s = ready()
        s.p5_levels["rc_start"] = 4         # 100 of each
        E.recurse(s, 1)
        for gid in ("E1", "E5", "R1", "R3"):
            self.assertGreaterEqual(s.gens[gid], N(100), gid)

    def test_thicker_substrate_scales_the_collapse_payout(self):
        s = ready()
        s.p3_oc_life = E.p4_required(s) * N(1e6)
        plain = E.p4_gain(s)
        s.p5_levels["rc_sub"] = 2           # x9
        boosted = E.p4_gain(s)
        self.assertAlmostEqual((boosted / plain).to_float(), 9.0, places=6)

    def test_the_top_tiers_unlock(self):
        s = ready()
        E.recompute(s)
        self.assertNotIn("E11", s.unlocked)
        self.assertNotIn("R8", s.unlocked)
        s.p5_levels["rc_e11"] = 1
        s.p5_levels["rc_r8"] = 1
        E.recompute(s)
        self.assertIn("E11", s.unlocked)
        self.assertIn("R8", s.unlocked)

    def test_e11_yields_four_resources_at_once(self):
        s = ready()
        s.p5_levels["rc_e11"] = 1
        E.recompute(s)
        s.gens["E11"] = s.bought["E11"] = N(10)
        for gid in G.ENERGY_GENS:
            s.gens[gid] = s.bought[gid] = N(1e30)
        E.recompute(s)
        E.tick(s, 0.25)
        for rid in ("ore", "alloy", "data", "isotope"):
            self.assertGreater(s.rates.get(rid, ZERO), ZERO,
                               f"E11 produced no {rid}")

    def test_the_stack_prices_in_bulk_without_a_loop(self):
        s = ready()
        s.p5_depth = N(1e9)
        bought = E.buy_recursion(s, "rc_start", 25)
        self.assertEqual(bought, 25)
        self.assertEqual(s.p5_levels["rc_start"], 25)

    def test_capped_nodes_respect_their_cap(self):
        s = ready()
        s.p5_depth = N(1e12)
        E.buy_recursion(s, "rc_army", "max")
        self.assertLessEqual(s.p5_levels["rc_army"],
                             G.REC_BY_ID["rc_army"].max_level)


class TestAutomation(unittest.TestCase):
    def test_auto_recursion_is_gated_on_its_unlock(self):
        s = ready()
        s.auto["recurse_enabled"] = True
        E.recurse(s, 1)
        s.p5_alloy = E.p5_target(1)
        run(s, 30)
        self.assertEqual(s.p5_count, 1, "auto-Recursion ran without its node")

    def test_auto_recursion_descends_when_it_clears(self):
        s = ready()
        s.perm_flags.add("auto_recurse")
        s.auto["recurse_enabled"] = True
        E.recurse(s, 1)
        s.p5_alloy = E.p5_target(1)
        run(s, 30)
        self.assertGreater(s.p5_count, 1)
        self.assertEqual(s.p5_active_depth, 2)


if __name__ == "__main__":
    unittest.main()
