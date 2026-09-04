"""Prestige layer 3: Overwrite.

Its identity is that Charges come from PEAK Alloy per second, not from any
lifetime total, and that what they buy are floors — permanent starting states.
"""

import random
import unittest

from seed import engine as E
from seed import gamedata as G
from seed.bignum import N, Num, ZERO
from seed.state import RESET_SCOPE, new_game


def run(s, seconds, dt=0.1, rng=None):
    rng = rng or random.Random(5)
    for _ in range(int(seconds / dt)):
        E.tick(s, dt, rng)


def ready(peak_mult=1.0):
    """A player deep enough in the Convergence era to Overwrite."""
    s = new_game()
    s.p1_count, s.p2_count = 40, 6
    s.p2_coh = N(400)
    s.p2_coh_life = N(600)
    s.p2_levels["c_global"] = 12
    s.research.add("r_foreman")
    s.doctrines[1] = "d1_swarm"
    s.res["nanite"] = N(1e9)
    s.res["exotic"] = N(1e6)
    E.recompute(s)
    s.p3_peak_rate = E.p3_required(s) * Num(peak_mult)
    return s


class TestVisibilityAndGating(unittest.TestCase):
    def test_hidden_early(self):
        s = new_game()
        E.recompute(s)
        self.assertFalse(E.p3_visible(s))
        self.assertEqual(E.p3_gain(s), ZERO)

    def test_visible_before_reachable(self):
        s = new_game()
        s.p2_coh_life = G.P3_UNLOCK_COH
        E.recompute(s)
        self.assertTrue(E.p3_visible(s))
        self.assertFalse(E.p3_available(s))

    def test_locked_below_the_bar(self):
        s = ready(peak_mult=0.5)
        self.assertEqual(E.p3_gain(s), ZERO)
        self.assertEqual(E.overwrite(s), ZERO)
        self.assertEqual(s.p3_count, 0)

    def test_exotic_machines_need_an_overwrite(self):
        s = ready()
        E.recompute(s)
        self.assertNotIn("E10", s.unlocked)
        self.assertNotIn("R5", s.unlocked)
        E.overwrite(s)
        E.recompute(s)
        self.assertTrue(s.has_flag("exotics"))
        self.assertIn("E10", s.unlocked)


class TestChargesComeFromPeak(unittest.TestCase):
    def test_gain_at_the_bar(self):
        s = ready()
        self.assertEqual(E.p3_gain(s).to_float(), G.P3_BASE)

    def test_a_stronger_engine_pays_more(self):
        s = ready()
        at_bar = E.p3_gain(s)
        s.p3_peak_rate = E.p3_required(s) * Num(1e6)
        self.assertGreater(E.p3_gain(s), at_bar)

    def test_waiting_alone_earns_nothing(self):
        """The whole point of the layer: idling at a fixed rate adds no peak."""
        s = ready()
        before = E.p3_gain(s)
        run(s, 5.0)
        self.assertEqual(E.p3_gain(s), before)

    def test_peak_tracks_the_best_rate_reached(self):
        s = new_game()
        s.res["ore"] = N(1e12)
        s.run_life["ore"] = N(1e12)
        E.recompute(s)
        for gid in ("E1", "E2", "E3"):
            E.buy(s, gid, 20)
        E.recompute(s)
        E.buy(s, "E5", 10)               # Alloy starts flowing
        run(s, 1.0)
        peak = s.p3_peak_rate
        self.assertGreater(peak, ZERO, "no peak recorded at all")
        s.res["ore"] = N(1e24)           # fund a strictly better engine
        E.recompute(s)
        bought = E.buy(s, "E1", 300) + E.buy(s, "E3", 100)
        self.assertGreater(bought, 0, "test setup could not afford the upgrade")
        run(s, 1.0)
        self.assertGreater(s.p3_peak_rate, peak)

    def test_peak_survives_a_dispersal_and_a_convergence(self):
        s = ready()
        peak = s.p3_peak_rate
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        self.assertEqual(s.p3_peak_rate, peak, "a Dispersal reset the era peak")
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.p3_peak_rate, peak, "a Convergence reset the era peak")

    def test_the_bar_rises_with_charges_held(self):
        s = ready()
        base = E.p3_required(s)
        s.p3_oc_life = N(50)
        self.assertGreater(E.p3_required(s), base * N(100))

    def test_preview_matches_award(self):
        s = ready(peak_mult=1e4)
        preview = E.p3_gain(s)
        self.assertEqual(E.overwrite(s), preview)


class TestOverwriteReset(unittest.TestCase):
    def test_it_wipes_the_convergence_era(self):
        s = ready(peak_mult=1e3)
        s.p1_sp = N(9999)
        s.p1_levels["sg_global"] = 20
        E.buy(s, "E1", 5)
        E.overwrite(s)
        self.assertEqual(s.p2_coh, ZERO)
        self.assertEqual(s.p2_coh_life, ZERO)
        self.assertEqual(s.p2_levels, {})
        self.assertEqual(s.res["exotic"], N(G.NANITE_SEED))
        self.assertEqual(s.p1_sp, ZERO)
        self.assertEqual(s.p1_levels, {})
        self.assertEqual(s.research, set())
        self.assertEqual(s.p3_peak_rate, ZERO)

    def test_doctrines_survive_an_overwrite_too(self):
        s = ready(peak_mult=1e3)
        s.doctrines[2] = "d2_forge"
        E.overwrite(s)
        self.assertEqual(s.doctrines, {1: "d1_swarm", 2: "d2_forge"})

    def test_it_keeps_identity_and_collections(self):
        s = ready(peak_mult=1e3)
        s.milestones.add("m_first_fab")
        s.achievements.add("a_first_ore")
        s.artifacts.append({"id": "a1", "name": "x", "kind": G.MULT_GLOBAL,
                            "target": "", "value": 3.0, "rarity": "epic",
                            "mutation": "plain", "desc": ""})
        E.overwrite(s)
        self.assertEqual(s.p1_count, 40)
        self.assertEqual(s.p2_count, 6)
        self.assertIn("m_first_fab", s.milestones)
        self.assertIn("a_first_ore", s.achievements)
        self.assertEqual(len(s.artifacts), 1)
        self.assertGreater(s.p3_oc, ZERO)
        self.assertEqual(s.p3_count, 1)

    def test_charges_and_floors_survive_later_overwrites(self):
        s = ready(peak_mult=1e6)
        E.overwrite(s)
        s.p3_oc = N(1e6)
        E.buy_overwrite(s, "ow_global", 5)
        s.p3_peak_rate = E.p3_required(s) * Num(1e6)
        E.overwrite(s)
        self.assertEqual(s.p3_levels["ow_global"], 5)
        self.assertEqual(s.p3_count, 2)

    def test_no_duplication_on_repeat(self):
        s = ready(peak_mult=1e3)
        first = E.overwrite(s)
        self.assertEqual(E.overwrite(s), ZERO)
        self.assertEqual(s.p3_oc, first)
        self.assertEqual(s.p3_count, 1)

    def test_every_cohere_field_is_declared(self):
        for field in ("p2_coh", "p2_coh_life", "p2_levels", "p3_peak_rate"):
            self.assertEqual(RESET_SCOPE.get(field), G.COHERE, field)


class TestFloors(unittest.TestCase):
    def test_extraction_floor_applies_at_every_dispersal(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.p3_oc = N(1e9)
        E.buy_overwrite(s, "ow_floor_e", 2)      # +50 of E1..E5
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        for gid in ("E1", "E2", "E3", "E4", "E5"):
            self.assertEqual(s.gens[gid].to_float(), 50.0, gid)
            self.assertEqual(s.bought[gid].to_float(), 50.0, gid)

    def test_replication_floor_applies(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.p3_oc = N(1e9)
        E.buy_overwrite(s, "ow_floor_r", 1)      # +10 of R1..R3
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        for gid in ("R1", "R2", "R3"):
            self.assertEqual(s.gens[gid].to_float(), 10.0, gid)

    def test_floors_survive_a_convergence(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.p3_oc = N(1e9)
        E.buy_overwrite(s, "ow_floor_e", 1)
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.gens["E5"].to_float(), 25.0)

    def test_a_floor_makes_the_restart_immediately_productive(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.p3_oc = N(1e9)
        E.buy_overwrite(s, "ow_floor_e", 3)
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        run(s, 1.0)
        self.assertGreater(s.rates.get("ore", ZERO), ZERO)
        self.assertGreater(s.rates.get("alloy", ZERO), ZERO)

    def test_persistent_archive_keeps_research_through_convergence(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.p3_oc = N(1e9)
        E.buy_overwrite(s, "ow_archive", 1)
        s.research.add("r_foreman")
        s.research.add("r_probes")
        E.recompute(s)
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertIn("r_foreman", s.research)
        self.assertIn("r_probes", s.research)

    def test_research_is_still_wiped_without_the_archive(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.research.add("r_foreman")
        E.recompute(s)
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.research, set())

    def test_shop_respects_caps_and_endlessness(self):
        s = ready(peak_mult=1e6)
        E.overwrite(s)
        s.p3_oc = N(1e12)
        E.buy_overwrite(s, "ow_relic", 99)
        self.assertEqual(s.p3_levels["ow_relic"], G.OVER_BY_ID["ow_relic"].max_level)
        E.buy_overwrite(s, "ow_global", 40)
        self.assertEqual(s.p3_levels["ow_global"], 40)   # endless

    def test_shop_never_overspends(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.p3_oc = N(7)
        E.buy_overwrite(s, "ow_global", "max")
        self.assertGreaterEqual(s.p3_oc, ZERO)

    def test_bulk_matches_singles(self):
        a, b = ready(peak_mult=1e3), ready(peak_mult=1e3)
        for s in (a, b):
            E.overwrite(s)
            s.p3_oc = N(1e9)
        E.buy_overwrite(a, "ow_global", 12)
        for _ in range(12):
            E.buy_overwrite(b, "ow_global", 1)
        self.assertEqual(a.p3_levels["ow_global"], b.p3_levels["ow_global"])
        self.assertAlmostEqual(a.p3_oc.log10(), b.p3_oc.log10(), places=6)


class TestExotics(unittest.TestCase):
    def test_overwrite_seeds_them(self):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        self.assertGreater(s.res["exotic"], ZERO)

    def test_their_bonus_is_logarithmic(self):
        s = ready()
        s.res["exotic"] = N(1e6)
        small = E.collect_mults(s).glob
        s.res["exotic"] = N(1e60)
        big = E.collect_mults(s).glob
        self.assertGreater(big, small)
        self.assertLess(big, small * N(1000))

    def test_they_are_era_scoped(self):
        """A Dispersal and a Convergence both leave Exotic Matter alone."""
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.res["exotic"] = N(1e20)
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        self.assertEqual(s.res["exotic"], N(1e20))
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        self.assertEqual(s.res["exotic"], N(1e20))


class TestAutoConverge(unittest.TestCase):
    def _ready(self, unlocked=True):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        if unlocked:
            s.p3_levels["ow_autoconv"] = 1
        s.auto["converge_enabled"] = True
        s.auto["converge_depth"] = 1.0          # 10x past the bar
        E.recompute(s)
        return s

    def test_locked_without_the_node(self):
        s = self._ready(unlocked=False)
        s.p1_sp_life = E.p2_required(s) * N(1e6)
        run(s, 0.5)
        self.assertEqual(s.p2_count, 6)

    def test_fires_past_the_chosen_depth(self):
        s = self._ready()
        before = s.p2_count
        s.p1_sp_life = E.p2_required(s) * N(1e6)
        run(s, 0.5)
        self.assertGreater(s.p2_count, before)

    def test_waits_below_the_chosen_depth(self):
        s = self._ready()
        before = s.p2_count
        s.p1_sp_life = E.p2_required(s)          # exactly at the bar, depth 0
        run(s, 0.5)
        self.assertEqual(s.p2_count, before)


if __name__ == "__main__":
    unittest.main()


class TestAutoCoherence(unittest.TestCase):
    """Standing Coherence Orders: the Convergence shop buys itself."""

    def _ready(self, coh=1e6, unlocked=True):
        s = ready(peak_mult=1e3)
        E.overwrite(s)
        s.p2_coh = N(coh)
        if unlocked:
            s.p3_levels["ow_autocoh"] = 1
        s.auto["coherence"] = True
        E.recompute(s)
        return s

    def test_locked_without_the_node(self):
        s = self._ready(unlocked=False)
        run(s, 1.0)
        self.assertEqual(s.p2_levels, {})

    def test_toggle_off_does_nothing(self):
        s = self._ready()
        s.auto["coherence"] = False
        run(s, 1.0)
        self.assertEqual(s.p2_levels, {})

    def test_it_buys_nodes(self):
        s = self._ready()
        run(s, 1.0)
        self.assertTrue(s.p2_levels, "auto-coherence bought nothing")
        self.assertLess(s.p2_coh, N(1e6))

    def test_it_spends_down_to_unaffordable(self):
        s = self._ready(coh=500)
        run(s, 3.0)
        cheapest = min(
            E.coherence_cost(cu, int(s.p2_levels.get(cu.id, 0))).to_float()
            for cu in G.COHERENCE_GRID
            if not cu.max_level or s.p2_levels.get(cu.id, 0) < cu.max_level)
        self.assertLess(s.p2_coh.to_float(), cheapest)

    def test_currency_never_goes_negative(self):
        s = self._ready(coh=37)
        run(s, 3.0)
        self.assertGreaterEqual(s.p2_coh, ZERO)

    def test_it_respects_caps(self):
        s = self._ready(coh=1e12)
        run(s, 3.0)
        for cu in G.COHERENCE_GRID:
            if cu.max_level:
                self.assertLessEqual(s.p2_levels.get(cu.id, 0), cu.max_level, cu.id)

    def test_it_spreads_across_nodes(self):
        s = self._ready(coh=1e5)
        run(s, 3.0)
        self.assertGreater(len(s.p2_levels), 3, s.p2_levels)

    def test_it_settles_instead_of_churning(self):
        s = self._ready(coh=1000)
        run(s, 2.0)
        settled = dict(s.p2_levels)
        run(s, 2.0)
        self.assertEqual(s.p2_levels, settled)

    def test_purchases_take_effect(self):
        s = self._ready()
        before = E.collect_mults(s).glob
        run(s, 2.0)
        self.assertGreater(E.collect_mults(s).glob, before)

    def test_it_survives_a_convergence(self):
        s = self._ready()
        run(s, 1.0)
        s.p1_sp_life = E.p2_required(s)
        E.converge(s)
        s.p2_coh = N(1e6)
        run(s, 1.0)
        self.assertTrue(s.p2_levels)


class TestAutoBuyKeepsUp(unittest.TestCase):
    """A flat 50-per-tick allowance crawls once you can afford a million."""

    def _rich_autobuyer(self, ore=None):
        # Costs grow at 1.11, so affordability is logarithmic in wealth: it
        # takes an absurd bank to reach the regime the player reported, where
        # the buy button reads "x1000000".
        s = new_game()
        bank = Num(1, 5000) if ore is None else N(ore)
        s.res["ore"] = bank
        s.run_life["ore"] = bank
        s.p1_levels["sg_autobuy"] = 1
        s.auto["enabled"] = True
        E.recompute(s)
        for g in G.GENERATORS:
            s.auto["gens"][g.id] = True
        return s

    def test_allowance_scales_with_what_you_can_afford(self):
        s = self._rich_autobuyer()
        m = E.recompute(s)
        afford = E.max_affordable(s, "E1", m)
        allowance = E._autobuy_amount(s, "E1", m)
        self.assertGreater(afford, 10_000, "test bank is not large enough")
        self.assertGreater(allowance, E.AUTOBUY_CAP * 100,
                           "auto-buy is still crawling at the flat floor")
        self.assertAlmostEqual(allowance / afford, E.AUTOBUY_FRACTION, places=3)

    def test_small_bank_still_uses_the_floor(self):
        s = self._rich_autobuyer(ore=200)
        m = E.recompute(s)
        self.assertEqual(E._autobuy_amount(s, "E1", m), E.AUTOBUY_CAP)

    def test_allowance_is_bounded(self):
        s = self._rich_autobuyer()
        m = E.recompute(s)
        self.assertLessEqual(E._autobuy_amount(s, "E1", m), E.MAX_BUY)

    def test_it_buys_far_more_per_tick_than_the_old_floor(self):
        s = self._rich_autobuyer()
        E.tick(s, 0.1)
        self.assertGreater(s.bought["E1"].to_float(), E.AUTOBUY_CAP * 10)

    def test_it_still_leaves_budget_for_other_machines(self):
        s = self._rich_autobuyer()
        run(s, 1.0)
        bought = [g.id for g in G.GENERATORS
                  if g.cost_res == "ore" and s.bought.get(g.id, ZERO) > 0]
        self.assertGreater(len(bought), 3,
                           "the first machine swallowed the whole budget")

    def test_it_never_overspends(self):
        s = self._rich_autobuyer(ore=1e6)
        run(s, 2.0)
        self.assertGreaterEqual(s.res["ore"], ZERO)


class TestArchiveLifetime(unittest.TestCase):
    """Persistent Archive protects Research for as long as the node lasts.

    It lives in `p3_levels`, which only a Collapse clears -- so it must hold
    Research through a Dispersal, a Convergence AND an Overwrite, then stop.
    It previously stopped one layer early, going dormant while still owned.
    """

    def _stocked(self):
        s = new_game()
        s.p1_count, s.p2_count, s.p3_count = 200, 30, 6
        s.p3_levels = {"ow_archive": 1}
        s.research = {"r_landfall", "r_starlift"}
        s.p1_levels = {"sg_global": 9}
        E.recompute(s)
        return s

    def test_research_survives_up_to_and_including_an_overwrite(self):
        for layer_id in ("p1", "p2", "p3"):
            s = self._stocked()
            E._reset_scopes(s, G.LAYER_BY_ID[layer_id].wipes)
            self.assertEqual(s.research, {"r_landfall", "r_starlift"},
                             f"{layer_id} took Research despite the Archive")

    def test_a_collapse_takes_the_node_and_the_protection_together(self):
        s = self._stocked()
        E._reset_scopes(s, G.LAYER_BY_ID["p4"].wipes)
        self.assertEqual(s.p3_levels, {}, "the Archive node survived a Collapse")
        self.assertEqual(s.research, set())

    def test_without_the_archive_a_convergence_takes_research(self):
        s = self._stocked()
        s.p3_levels = {}
        E.recompute(s)
        E._reset_scopes(s, G.LAYER_BY_ID["p2"].wipes)
        self.assertEqual(s.research, set())
