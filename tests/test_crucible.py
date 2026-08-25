"""The Crucible: fusing spare relics into better ones.

The load-bearing property is that fusion never consumes a relic you are using,
or one the ranking would want to use. Everything else is bookkeeping.
"""

import random
import unittest

from seed import engine as E
from seed import gamedata as G
from seed.bignum import N, Num, ZERO
from seed.state import new_game


def run(s, seconds, dt=0.1, rng=None):
    rng = rng or random.Random(99)
    for _ in range(int(seconds / dt)):
        E.tick(s, dt, rng)


def relic(aid, rarity, kind, target, value):
    return {"id": aid, "name": aid, "kind": kind, "target": target,
            "value": value, "rarity": rarity, "desc": ""}


def stocked(spec, equip_best=True):
    s = new_game()
    s.artifacts = [relic(f"a{i}", r, k, tg, v) for i, (r, k, tg, v) in enumerate(spec)]
    s.equipped = []
    E.recompute(s)
    if equip_best:
        E.auto_equip(s)
    return s


def commons(n, value=1.05):
    return [("common", G.MULT_RES, "data", value)] * n


class TestFusionSafety(unittest.TestCase):
    def test_never_consumes_an_equipped_relic(self):
        s = stocked(commons(9), equip_best=False)
        s.equipped = ["a0", "a1", "a2"]
        E.fuse(s, "common", "max")
        surviving = {a["id"] for a in s.artifacts}
        for aid in ("a0", "a1", "a2"):
            self.assertIn(aid, surviving, f"{aid} was consumed while equipped")
        self.assertEqual(s.equipped, ["a0", "a1", "a2"])

    def test_never_consumes_a_relic_the_ranking_wants(self):
        s = stocked(commons(8) + [("common", G.MULT_GLOBAL, "", 1.9)],
                    equip_best=False)
        s.equipped = []
        wanted = set(E.best_loadout(s))
        E.fuse(s, "common", "max")
        surviving = {a["id"] for a in s.artifacts}
        self.assertTrue(wanted <= surviving, "fusion ate a best-loadout relic")

    def test_consumes_the_worst_first(self):
        s = stocked([("common", G.MULT_RES, "data", v)
                     for v in (1.02, 1.03, 1.04, 1.05, 1.06, 1.07)]
                    + [("common", G.MULT_GLOBAL, "", 1.60)], equip_best=False)
        s.equipped = []
        E.fuse(s, "common", 1)
        left = sorted(a["value"] for a in s.artifacts if a["rarity"] == "common")
        self.assertNotIn(1.02, left)
        self.assertNotIn(1.04, left)
        self.assertIn(1.05, left)
        self.assertIn(1.60, left, "the strongest relic must never be consumed")

    def test_your_best_relics_are_never_spare(self):
        """The top `relic_slots` relics are protected even when unslotted."""
        s = stocked(commons(20), equip_best=False)
        s.equipped = []
        spare = E.fusable_counts(s).get("common", 0)
        self.assertEqual(spare, 20 - E.relic_slots(s))

    def test_equipped_never_points_at_a_consumed_relic(self):
        s = stocked(commons(30))
        E.fuse_all(s)
        known = {a["id"] for a in s.artifacts}
        self.assertTrue(set(s.equipped) <= known)

    def test_fusing_never_lowers_your_multiplier(self):
        s = stocked(commons(30))
        E.auto_equip(s)
        before = E.collect_mults(s).glob
        E.fuse_all(s)
        E.auto_equip(s)
        self.assertGreaterEqual(E.collect_mults(s).glob, before)


class TestFusionMechanics(unittest.TestCase):
    def test_three_become_one_of_the_next_rarity(self):
        s = stocked(commons(3 + 3), equip_best=False)   # 3 spare, 3 protected
        s.equipped = []
        made = E.fuse(s, "common", 1)
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0]["rarity"], "uncommon")
        self.assertEqual(sum(1 for a in s.artifacts if a["rarity"] == "common"), 3)

    def test_needs_a_full_set(self):
        s = stocked(commons(2 + 3), equip_best=False)   # only 2 spare
        s.equipped = []
        self.assertEqual(E.fuse(s, "common", 1), [])
        self.assertEqual(len(s.artifacts), 5)

    def test_max_fuses_every_complete_set(self):
        s = stocked(commons(10 + 3), equip_best=False)  # 10 spare
        s.equipped = []
        made = E.fuse(s, "common", "max")
        self.assertEqual(len(made), 3)                  # 9 fused, 1 spare left
        self.assertEqual(sum(1 for a in s.artifacts if a["rarity"] == "common"), 4)

    def test_top_rarity_cannot_be_fused(self):
        s = stocked([("cosmic", G.MULT_GLOBAL, "", 3.0)] * 12, equip_best=False)
        s.equipped = []
        self.assertEqual(E.fuse(s, "cosmic", "max"), [])
        self.assertEqual(len(s.artifacts), 12)

    def test_unknown_rarity_is_safe(self):
        s = stocked(commons(9), equip_best=False)
        self.assertEqual(E.fuse(s, "not_a_rarity", "max"), [])

    def test_counts_are_exactly_conserved(self):
        s = stocked(commons(12), equip_best=False)
        s.equipped = []
        before = len(s.artifacts)
        made = E.fuse(s, "common", 1)
        self.assertEqual(len(made), 1)
        self.assertEqual(len(s.artifacts), before - G.FUSE_COUNT + len(made))

    def test_fuse_all_cascades_upward(self):
        s = stocked(commons(27), equip_best=False)
        s.equipped = []
        E.fuse_all(s)
        ranks = [E.rarity_rank(a["rarity"]) for a in s.artifacts]
        self.assertGreaterEqual(max(ranks), 2, "27 commons did not reach rare")

    def test_fusion_reduces_clutter(self):
        s = stocked(commons(60), equip_best=False)
        s.equipped = []
        before = len(s.artifacts)
        E.fuse_all(s)
        self.assertLess(len(s.artifacts), before / 2)

    def test_counts_report_only_spares(self):
        s = stocked(commons(9), equip_best=False)
        s.equipped = ["a0", "a1"]
        protected = len(E.protected_ids(s))
        self.assertEqual(E.fusable_counts(s).get("common", 0), 9 - protected)

    def test_fused_relics_are_real_and_usable(self):
        s = stocked(commons(6), equip_best=False)
        s.equipped = []
        made = E.fuse(s, "common", 1)
        self.assertGreater(E.artifact_score(s, made[0]), 0)
        self.assertIn(made[0]["id"], {a["id"] for a in s.artifacts})

    def test_fusing_does_not_inflate_the_found_counter(self):
        s = stocked(commons(6), equip_best=False)
        s.equipped = []
        found = s.stats.get("artifacts_found", 0)
        E.fuse(s, "common", 1)
        self.assertEqual(s.stats["artifacts_found"], found)
        self.assertEqual(s.stats["artifacts_fused"], G.FUSE_COUNT)

    def test_reaching_cosmic_by_fusing_is_recorded(self):
        s = stocked([("legendary", G.MULT_GLOBAL, "", 2.0)] * 6, equip_best=False)
        s.equipped = []
        made = E.fuse(s, "legendary", 1)
        self.assertEqual(made[0]["rarity"], "cosmic")
        self.assertIn("ach_fused_cosmic", s.perm_flags)

    def test_rarity_chain_is_well_formed(self):
        for i, r in enumerate(G.RARITY[:-1]):
            self.assertEqual(E.next_rarity(r.id).id, G.RARITY[i + 1].id)
        self.assertIsNone(E.next_rarity(G.RARITY[-1].id))


class TestAutoFuse(unittest.TestCase):
    def _ready(self, unlocked=True):
        s = stocked(commons(30, value=1.02), equip_best=False)
        s.equipped = []
        if unlocked:
            s.p1_levels["sg_autofuse"] = 1
        s.auto["fuse"] = True
        E.recompute(s)
        return s

    def test_locked_without_the_seed_node(self):
        s = self._ready(unlocked=False)
        run(s, 1.0)
        self.assertEqual(len(s.artifacts), 30)

    def test_toggle_off_does_nothing(self):
        s = self._ready()
        s.auto["fuse"] = False
        run(s, 1.0)
        self.assertEqual(len(s.artifacts), 30)

    def test_it_fuses_spares(self):
        s = self._ready()
        run(s, 1.0)
        self.assertLess(len(s.artifacts), 30)

    def test_it_leaves_the_working_set_alone(self):
        s = self._ready()
        s.artifacts.append(relic("keeper", "epic", G.MULT_GLOBAL, "", 8.0))
        E.recompute(s)
        E.auto_equip(s)
        run(s, 2.0)
        self.assertIn("keeper", {a["id"] for a in s.artifacts})
        self.assertIn("keeper", s.equipped)

    def test_it_settles_instead_of_churning(self):
        s = self._ready()
        run(s, 2.0)
        settled = len(s.artifacts)
        run(s, 2.0)
        self.assertEqual(len(s.artifacts), settled, "auto-fuse never stops")

    def test_it_improves_the_loadout(self):
        s = self._ready()
        E.auto_equip(s)
        before = E.collect_mults(s).glob
        run(s, 3.0)
        self.assertGreater(E.collect_mults(s).glob, before)

    def test_it_survives_a_dispersal(self):
        s = self._ready()
        run(s, 1.0)
        count = len(s.artifacts)
        s.run_life["alloy"] = E.p1_required(s)
        E.prestige(s, "p1")
        self.assertEqual(len(s.artifacts), count, "artifacts are not run-scoped")


class TestFusionCost(unittest.TestCase):
    def test_a_long_grind_can_reach_the_top_rarity(self):
        """Bad luck should slow the collection, not block it."""
        # 3^5 = 243 in theory, plus the protected working set kept back at each
        # tier, so a real grind needs comfortably more than the bare minimum.
        s = stocked(commons(1500), equip_best=False)
        s.equipped = []
        E.fuse_all(s)
        top = max(E.rarity_rank(a["rarity"]) for a in s.artifacts)
        self.assertEqual(top, len(G.RARITY) - 1,
                         "a large grind should reach the top rarity")

    def test_it_is_fast_with_a_large_collection(self):
        import time as _t
        s = stocked(commons(2000), equip_best=False)
        s.equipped = []
        t0 = _t.perf_counter()
        E.fuse_all(s)
        self.assertLess(_t.perf_counter() - t0, 1.0)


if __name__ == "__main__":
    unittest.main()


class TestMutations(unittest.TestCase):
    """A second axis on top of rarity: how strange the relic is."""

    def _mint(self, rarity_id, mutation_id=None, seed=1):
        s = new_game()
        rng = random.Random(seed)
        mut = G.MUTATION_BY_ID[mutation_id] if mutation_id else None
        return s, E._mint_artifact(s, G.RARITY_BY_ID[rarity_id], rng,
                                   found=True, mutation=mut)

    def test_every_relic_carries_one(self):
        _, art = self._mint("common")
        self.assertIn("mutation", art)
        self.assertIn(art["mutation"], G.MUTATION_BY_ID)

    def test_plain_changes_nothing(self):
        _, plain = self._mint("rare", "plain")
        expected = 1.0 + (plain["value"] - 1.0)
        self.assertAlmostEqual(plain["value"], expected, places=9)

    def test_mutations_scale_the_bonus_not_the_total(self):
        _, plain = self._mint("rare", "plain", seed=7)
        _, shiny = self._mint("rare", "shiny", seed=7)
        power = G.MUTATION_BY_ID["shiny"].power
        self.assertAlmostEqual(shiny["value"] - 1.0,
                               (plain["value"] - 1.0) * power, places=9)

    def test_the_ladder_is_strictly_increasing(self):
        values = []
        for mut in G.MUTATIONS:
            _, art = self._mint("epic", mut.id, seed=3)
            values.append(art["value"])
        self.assertEqual(values, sorted(values))

    def test_a_lucky_common_can_beat_a_dull_rare(self):
        """The whole point of a second axis: low rarity still worth reading."""
        s, singular_common = self._mint("common", "singular", seed=5)
        _, plain_rare = self._mint("rare", "plain", seed=5)
        self.assertGreater(singular_common["value"], plain_rare["value"])

    def test_scoring_accounts_for_mutations(self):
        s, plain = self._mint("rare", "plain", seed=11)
        _, alien = self._mint("rare", "alien", seed=11)
        s.artifacts = [plain, alien]
        self.assertGreater(E.artifact_score(s, alien), E.artifact_score(s, plain))

    def test_a_mutated_relic_is_preferred_by_the_loadout(self):
        s = new_game()
        rng = random.Random(2)
        for _ in range(6):
            E._mint_artifact(s, G.RARITY_BY_ID["common"], rng, found=True,
                             mutation=G.MUTATION_BY_ID["plain"])
        star = E._mint_artifact(s, G.RARITY_BY_ID["common"], rng, found=True,
                                mutation=G.MUTATION_BY_ID["singular"])
        s.equipped = []
        E.recompute(s)
        self.assertIn(star["id"], E.best_loadout(s))

    def test_rolled_weights_are_sane(self):
        s = new_game()
        rng = random.Random(4)
        seen = {}
        for _ in range(4000):
            mut = E._roll_mutation(rng)
            seen[mut.id] = seen.get(mut.id, 0) + 1
        self.assertGreater(seen.get("plain", 0), seen.get("shiny", 0))
        self.assertGreater(seen.get("shiny", 0), seen.get("alien", 0))
        self.assertLess(seen.get("singular", 0), 60)

    def test_finding_one_is_recorded(self):
        s, _ = self._mint("common", "singular")
        self.assertIn("ach_mutation", s.perm_flags)
        self.assertIn("ach_singular", s.perm_flags)
        self.assertEqual(s.stats["artifacts_by_mutation"]["singular"], 1)

    def test_plain_relics_are_not_counted_as_mutated(self):
        s, _ = self._mint("common", "plain")
        self.assertNotIn("ach_mutation", s.perm_flags)
        self.assertEqual(s.stats.get("artifacts_by_mutation", {}), {})

    def test_the_name_says_what_it_is(self):
        _, art = self._mint("legendary", "ancient")
        self.assertTrue(art["name"].startswith("Ancient "), art["name"])

    # -- interaction with fusion --------------------------------------
    def test_fusion_keeps_the_strangest_input(self):
        s = new_game()
        rng = random.Random(8)
        for mid in ("plain", "plain", "alien"):
            E._mint_artifact(s, G.RARITY_BY_ID["common"], rng, found=True,
                             mutation=G.MUTATION_BY_ID[mid])
        # Filler strong enough to fill the working set on its own, so all three
        # commons are genuinely spare.
        for _ in range(E.relic_slots(s) + 1):
            E._mint_artifact(s, G.RARITY_BY_ID["cosmic"], rng, found=True,
                             mutation=G.MUTATION_BY_ID["plain"])
        s.equipped = []
        E.recompute(s)
        made = E.fuse(s, "common", 1)
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0]["mutation"], "alien",
                         "fusing away a mutated relic threw the mutation away")

    def test_fusion_of_plain_relics_stays_plain(self):
        s = stocked(commons(12), equip_best=False)
        s.equipped = []
        made = E.fuse(s, "common", 1)
        self.assertEqual(made[0]["mutation"], "plain")

    # -- save compatibility -------------------------------------------
    def test_relics_saved_before_mutations_existed_read_as_plain(self):
        legacy = {"id": "old", "name": "Old Core", "kind": G.MULT_GLOBAL,
                  "target": "", "value": 1.5, "rarity": "rare", "desc": ""}
        self.assertEqual(E.mutation_of(legacy).id, "plain")
        self.assertEqual(E.mutation_rank("plain"), 0)

    def test_unknown_mutation_id_degrades_safely(self):
        weird = {"id": "x", "name": "x", "kind": G.MULT_GLOBAL, "target": "",
                 "value": 1.5, "rarity": "rare", "mutation": "not_real", "desc": ""}
        self.assertEqual(E.mutation_of(weird).id, "plain")
        self.assertEqual(E.mutation_rank("not_real"), 0)

    def test_legacy_relics_still_fuse(self):
        s = new_game()
        s.artifacts = [{"id": f"old{i}", "name": "Old", "kind": G.MULT_RES,
                        "target": "data", "value": 1.05, "rarity": "common",
                        "desc": ""} for i in range(12)]
        s.equipped = []
        E.recompute(s)
        made = E.fuse(s, "common", 1)
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0]["mutation"], "plain")
