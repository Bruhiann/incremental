"""Prestige layer 4: Substrate Collapse.

Its identity is the verb change: every multiplier is astronomical by now, so
Substrate buys EXPONENTS instead. Production is raised to a power.
"""

import random
import unittest

from seed import engine as E
from seed import gamedata as G
from seed.bignum import N, Num, ZERO
from seed.state import RESET_SCOPE, new_game


def run(s, seconds, dt=0.1, rng=None):
    rng = rng or random.Random(7)
    for _ in range(int(seconds / dt)):
        E.tick(s, dt, rng)


def ready(oc_mult=1.0):
    """A player deep enough in the Overwrite era to Collapse."""
    s = new_game()
    s.p1_count, s.p2_count, s.p3_count = 200, 40, 8
    s.p3_levels["ow_global"] = 20
    s.p3_oc = N(500)
    s.res["exotic"] = N(1e12)
    s.res["nanite"] = N(1e12)
    E.recompute(s)
    s.p3_oc_life = E.p4_required(s) * Num(oc_mult)
    return s


class TestVisibilityAndGating(unittest.TestCase):
    def test_hidden_early(self):
        s = new_game()
        E.recompute(s)
        self.assertFalse(E.p4_visible(s))
        self.assertEqual(E.p4_gain(s), ZERO)

    def test_visible_before_reachable(self):
        s = new_game()
        s.p3_oc_life = G.P4_UNLOCK_OC
        E.recompute(s)
        self.assertTrue(E.p4_visible(s))
        self.assertFalse(E.p4_available(s))

    def test_locked_below_the_bar(self):
        s = ready(oc_mult=0.5)
        self.assertEqual(E.p4_gain(s), ZERO)
        self.assertEqual(E.collapse(s), ZERO)
        self.assertEqual(s.p4_count, 0)

    def test_gain_at_the_bar(self):
        s = ready()
        self.assertEqual(E.p4_gain(s).to_float(), G.P4_BASE)

    def test_depth_pays(self):
        s = ready()
        at_bar = E.p4_gain(s)
        s.p3_oc_life = E.p4_required(s) * Num(1e4)
        self.assertGreater(E.p4_gain(s), at_bar * N(3))

    def test_the_bar_rises_with_substrate_held(self):
        s = ready()
        base = E.p4_required(s)
        s.p4_sub_life = N(1000)
        self.assertGreater(E.p4_required(s), base * N(10))

    def test_preview_matches_award(self):
        s = ready(oc_mult=1e3)
        preview = E.p4_gain(s)
        self.assertEqual(E.collapse(s), preview)


class TestExponents(unittest.TestCase):
    """The verb change. Nothing else in the game raises production to a power."""

    def _with_exponent(self, levels):
        s = ready(oc_mult=1e3)
        E.collapse(s)
        s.p4_sub = N(1e12)
        E.buy_substrate(s, "sb_exponent", levels)
        E.recompute(s)
        return s

    def test_no_exponent_by_default(self):
        s = new_game()
        E.recompute(s)
        self.assertEqual(E.collect_mults(s).exponent, 0.0)

    def test_levels_raise_the_exponent(self):
        s = self._with_exponent(10)
        self.assertAlmostEqual(E.collect_mults(s).exponent,
                               10 * G.SUBSTRATE_EXP_STEP, places=9)

    def test_it_raises_production_to_a_power(self):
        plain = ready(oc_mult=1e3)
        E.collapse(plain)
        plain.gens["E1"] = N(1e6)
        plain.bought["E1"] = N(500)
        E.recompute(plain)
        base_mult = plain.mults["E1"]

        s = self._with_exponent(50)
        s.gens["E1"] = N(1e6)
        s.bought["E1"] = N(500)
        E.recompute(s)
        expected = base_mult ** (1.0 + 50 * G.SUBSTRATE_EXP_STEP)
        self.assertAlmostEqual(s.mults["E1"].log10(), expected.log10(), places=3)

    def test_a_multiplier_still_wins_while_numbers_are_small(self):
        """Honest about the crossover: +e adds e*log10(mult), so a x10 wins
        until multipliers pass 10**(1/e)."""
        s = self._with_exponent(0)
        s.gens["E1"] = N(1e6)
        s.bought["E1"] = N(2000)
        E.recompute(s)
        self.assertLess(s.mults["E1"].log10(), 100)

        E.buy_substrate(s, "sb_global", 1)           # x10
        E.recompute(s)
        with_mult = s.mults["E1"]
        s.p4_levels.pop("sb_global")
        E.buy_substrate(s, "sb_exponent", 5)         # +0.010
        E.recompute(s)
        self.assertLess(s.mults["E1"], with_mult)

    def test_it_dwarfs_a_multiplier_at_the_scale_this_layer_lives_at(self):
        """The premise of the layer: once multipliers are astronomical, another
        x10 is noise and only the exponent moves anything."""
        s = self._with_exponent(0)
        s.gens["E1"] = N(1e6)
        s.bought["E1"] = N(2000)
        s.p4_sub = N(1e80)                           # enough to reach the scale
        E.buy_substrate(s, "sb_global", 400)
        E.recompute(s)
        huge = s.mults["E1"]
        self.assertGreater(huge.log10(), 400, "test did not reach the scale")

        E.buy_substrate(s, "sb_global", 1)           # one more x10
        E.recompute(s)
        with_mult = s.mults["E1"]
        s.p4_levels["sb_global"] -= 1
        E.buy_substrate(s, "sb_exponent", 5)         # +0.010 instead
        E.recompute(s)
        with_exp = s.mults["E1"]
        self.assertGreater(with_exp, with_mult,
                           "the exponent should bury a x10 at this scale")
        self.assertGreater(with_exp.log10(), huge.log10() * 1.009)

    def test_it_shows_in_the_breakdown(self):
        s = self._with_exponent(10)
        s.gens["E1"] = N(1e6)
        s.bought["E1"] = N(500)
        E.recompute(s)
        labels = [lbl for lbl, _ in s.breakdown["E1"]]
        self.assertTrue(any("Substrate exponent" in lbl for lbl in labels))

    def test_it_never_shrinks_a_multiplier(self):
        """x ** 1.05 is smaller than x when x < 1, so guard the small case."""
        s = self._with_exponent(20)
        for gid in ("E1", "R1"):
            self.assertGreaterEqual(s.mults[gid], N(1), gid)

    def test_reaching_a_big_exponent_is_recorded(self):
        s = self._with_exponent(60)          # 0.12
        E.recompute(s)
        self.assertIn("ach_exponent", s.perm_flags)


class TestCollapseReset(unittest.TestCase):
    def test_it_wipes_the_overwrite_era(self):
        s = ready(oc_mult=1e3)
        E.collapse(s)
        self.assertEqual(s.p3_oc, ZERO)
        self.assertEqual(s.p3_oc_life, ZERO)
        self.assertEqual(s.p3_levels, {})
        self.assertEqual(s.p2_coh, ZERO)
        self.assertEqual(s.p2_levels, {})
        self.assertEqual(s.p1_sp, ZERO)
        self.assertEqual(s.p1_levels, {})
        self.assertEqual(s.research, set())

    def test_it_keeps_identity_and_collections(self):
        s = ready(oc_mult=1e3)
        s.milestones.add("m_first_fab")
        s.artifacts.append({"id": "a1", "name": "x", "kind": G.MULT_GLOBAL,
                            "target": "", "value": 3.0, "rarity": "epic",
                            "mutation": "plain", "desc": ""})
        E.collapse(s)
        self.assertEqual(s.p1_count, 200)
        self.assertEqual(s.p3_count, 8)
        self.assertIn("m_first_fab", s.milestones)
        self.assertEqual(len(s.artifacts), 1)
        self.assertGreater(s.p4_sub, ZERO)
        self.assertEqual(s.p4_count, 1)

    def test_substrate_survives_later_collapses(self):
        s = ready(oc_mult=1e6)
        E.collapse(s)
        s.p4_sub = N(1e9)
        E.buy_substrate(s, "sb_exponent", 7)
        s.p3_oc_life = E.p4_required(s) * Num(1e6)
        E.collapse(s)
        self.assertEqual(s.p4_levels["sb_exponent"], 7)
        self.assertEqual(s.p4_count, 2)

    def test_no_duplication_on_repeat(self):
        s = ready(oc_mult=1e3)
        first = E.collapse(s)
        self.assertEqual(E.collapse(s), ZERO)
        self.assertEqual(s.p4_sub, first)

    def test_every_over_field_is_declared(self):
        for field in ("p3_oc", "p3_oc_life", "p3_levels"):
            self.assertEqual(RESET_SCOPE.get(field), G.OVER, field)

    def test_prestige_dispatches_to_layer_four(self):
        s = ready(oc_mult=1e3)
        gain = E.p4_gain(s)
        self.assertEqual(E.prestige(s, "p4"), gain)

    def test_layer_five_still_does_nothing(self):
        s = ready(oc_mult=1e3)
        self.assertEqual(E.prestige(s, "p5"), ZERO)


class TestSubstrateShop(unittest.TestCase):
    def _stocked(self, sub=1e9):
        s = ready(oc_mult=1e3)
        E.collapse(s)
        s.p4_sub = N(sub)
        E.recompute(s)
        return s

    def test_bulk_matches_singles(self):
        a, b = self._stocked(), self._stocked()
        E.buy_substrate(a, "sb_exponent", 12)
        for _ in range(12):
            E.buy_substrate(b, "sb_exponent", 1)
        self.assertEqual(a.p4_levels["sb_exponent"], b.p4_levels["sb_exponent"])
        self.assertAlmostEqual(a.p4_sub.log10(), b.p4_sub.log10(), places=6)

    def test_caps_and_endlessness(self):
        s = self._stocked(1e15)
        E.buy_substrate(s, "sb_relic", 99)
        self.assertEqual(s.p4_levels["sb_relic"], G.SUB_BY_ID["sb_relic"].max_level)
        E.buy_substrate(s, "sb_exponent", 60)
        self.assertEqual(s.p4_levels["sb_exponent"], 60)

    def test_never_overspends(self):
        s = self._stocked(sub=9)
        E.buy_substrate(s, "sb_exponent", "max")
        self.assertGreaterEqual(s.p4_sub, ZERO)

    def test_flat_priced_node_does_not_overshoot(self):
        s = self._stocked(1e12)
        E.buy_substrate(s, "sb_autoover", "max")
        self.assertEqual(s.p4_levels["sb_autoover"], 1)

    def test_cached_genome_keeps_the_seed_grid_through_convergence(self):
        s = self._stocked(1e12)
        E.buy_substrate(s, "sb_genome", 1)
        s.p1_levels["sg_global"] = 12
        E.recompute(s)
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.p1_levels.get("sg_global"), 12)

    def test_the_seed_grid_is_still_wiped_without_it(self):
        s = self._stocked(1e12)
        s.p1_levels["sg_global"] = 12
        E.recompute(s)
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.p1_levels, {})

    def test_genome_protects_for_exactly_as_long_as_it_survives(self):
        """This test previously asserted the opposite, and was wrong.

        It pinned "a Collapse wipes the Seed Grid even with Cached Genome",
        which sounded principled -- do not carry work through the reset meant
        to clear it -- but Cached Genome lives in `p4_levels`, and a Collapse
        does not clear those. Only a Recursion does. The node therefore went
        dormant while still owned and still paid for, which is what a player
        actually noticed. The rule is now "you keep it while the thing that
        promised it survives", and this asserts both halves of it.
        """
        s = self._stocked(1e12)
        E.buy_substrate(s, "sb_genome", 1)
        s.p1_levels["sg_global"] = 12
        E.recompute(s)

        # A Collapse leaves the node alone, so it keeps working.
        E._reset_scopes(s, G.LAYER_BY_ID["p4"].wipes)
        self.assertEqual(s.p4_levels.get("sb_genome"), 1)
        self.assertEqual(s.p1_levels, {"sg_global": 12})

        # A Recursion takes the node, and the protection goes with it.
        E._reset_scopes(s, G.LAYER_BY_ID["p5"].wipes)
        self.assertEqual(s.p4_levels, {})
        self.assertEqual(s.p1_levels, {})

    def test_genome_holds_the_seed_grid_through_an_overwrite(self):
        """The reset the player asked about."""
        s = self._stocked(1e12)
        E.buy_substrate(s, "sb_genome", 1)
        s.p1_levels["sg_global"] = 12
        E.recompute(s)
        E._reset_scopes(s, G.LAYER_BY_ID["p3"].wipes)
        self.assertEqual(s.p1_levels, {"sg_global": 12})

    def test_without_genome_an_overwrite_takes_the_seed_grid(self):
        s = self._stocked(1e12)
        s.p1_levels["sg_global"] = 12
        E.recompute(s)
        E._reset_scopes(s, G.LAYER_BY_ID["p3"].wipes)
        self.assertEqual(s.p1_levels, {})

    def test_charge_multiplier_applies(self):
        s = self._stocked(1e12)
        s.p3_peak_rate = E.p3_required(s) * Num(1e6)
        plain = E.p3_gain(s)
        E.buy_substrate(s, "sb_oc", 2)
        self.assertGreater(E.p3_gain(s), plain)


class TestAutoOverwrite(unittest.TestCase):
    def _ready(self, unlocked=True):
        s = ready(oc_mult=1e3)
        E.collapse(s)
        s.p4_sub = N(1e12)
        if unlocked:
            E.buy_substrate(s, "sb_autoover", 1)
        s.auto["overwrite_enabled"] = True
        s.auto["overwrite_depth"] = 1.0
        E.recompute(s)
        return s

    def test_locked_without_the_node(self):
        s = self._ready(unlocked=False)
        s.p3_peak_rate = E.p3_required(s) * N(1e6)
        run(s, 0.5)
        self.assertEqual(s.p3_count, 8)

    def test_fires_past_the_chosen_depth(self):
        s = self._ready()
        before = s.p3_count
        s.p3_peak_rate = E.p3_required(s) * N(1e6)
        run(s, 0.5)
        self.assertGreater(s.p3_count, before)

    def test_waits_below_the_chosen_depth(self):
        s = self._ready()
        before = s.p3_count
        s.p3_peak_rate = E.p3_required(s)
        run(s, 0.5)
        self.assertEqual(s.p3_count, before)


if __name__ == "__main__":
    unittest.main()
