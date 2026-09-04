"""The Defection.

Combat is the only system in the game that can take something back, so most of
what is pinned here is what it may NOT take. Everything else in SEED is
monotone; these tests are the fence around the one exception.
"""

import copy
import random
import unittest

from seed import engine as E
from seed import gamedata as G
from seed.bignum import N, Num, ZERO
from seed.state import RESET_SCOPE, new_game


def run(s, seconds, dt=0.25, rng=None):
    rng = rng or random.Random(11)
    for _ in range(int(seconds / dt)):
        E.tick(s, dt, rng)


def armed(swarm=1000, wins=1):
    """A player in the Overwrite era with a swarm big enough to defect."""
    s = new_game()
    s.p1_count, s.p2_count, s.p3_count = 50, 10, 2
    s.combat_wins = wins            # past the scripted tutorial unless told not to
    s.gens["R1"] = N(swarm)
    s.bought["R1"] = N(swarm)
    s.gens["E1"] = N(1e6)
    s.bought["E1"] = N(1e6)
    s.gens["E3"] = N(1e6)
    s.bought["E3"] = N(1e6)
    # An incursion is sized against the bank, so a fixture without one has
    # nothing to defend and nothing to defend it with.
    s.res["ore"] = N(1e14)
    s.res["alloy"] = N(1e12)
    E.recompute(s)
    return s


def fleet_to(s, want: Num):
    """Set the D1 count that yields `want` fleet damage per second.

    Bisected rather than divided because fleet power carries the per-10 bonus
    and so is not linear in count.
    """
    lo, hi = 0.0, 1e9
    for _ in range(90):
        mid = (lo + hi) / 2.0
        s.gens["D1"] = Num(mid)
        s.bought["D1"] = Num(mid)
        E.recompute(s)
        if E.fleet_power(s) < want:
            lo = mid
        else:
            hi = mid
    s.gens["D1"] = Num(lo)
    s.bought["D1"] = Num(lo)
    E.recompute(s)
    return s


def fight(s, size=None, limit=4000):
    """Spawn an incursion, optionally size the fleet to it, tick to a result.

    The fleet is sized against the incursion that ACTUALLY spawned, not against
    a reading taken beforehand. The demand tracks the bank, and these fixtures
    grow their bank by thousands of orders of magnitude per tick, so any
    earlier measurement is stale by the time the fight starts.
    """
    rng = random.Random(3)
    if s.incursion is None:
        s.threat = E.incursion_bar(s)
        E.tick(s, 0.25, rng)
    if size is not None and s.incursion is not None:
        fleet_to(s, Num.from_json(s.incursion["strength"]) * Num(size))
    w0, l0 = s.combat_wins, s.combat_losses
    for _ in range(int(limit / 0.25)):
        E.tick(s, 0.25, rng)
        if s.combat_wins > w0:
            return "win"
        if s.combat_losses > l0:
            return "loss"
    return "unresolved"


class TestGating(unittest.TestCase):
    def test_hidden_before_overwrite(self):
        s = new_game()
        E.recompute(s)
        self.assertFalse(s.has_flag("see_combat"))
        for g in G.DEFEND_GENS:
            self.assertNotIn(g.id, s.unlocked)

    def test_visible_in_the_overwrite_era(self):
        s = new_game()
        s.p3_count = 1
        E.recompute(s)
        self.assertTrue(s.has_flag("see_combat"))
        self.assertIn("D1", s.unlocked)

    def test_no_threat_without_a_swarm(self):
        s = new_game()
        s.p3_count = 1
        E.recompute(s)
        self.assertEqual(E.threat_rate(s), 0.0)
        run(s, 600)
        self.assertIsNone(s.incursion)


class TestNothingSacredIsLost(unittest.TestCase):
    """The test that matters most: an unwinnable fight must cost only machines."""

    def test_unwinnable_incursion_touches_nothing_it_may_not(self):
        s = armed()
        s.p1_sp, s.p2_coh, s.p3_oc, s.p4_sub = N(500), N(400), N(300), N(200)
        s.p1_levels["sg_global"] = 12
        s.p2_levels["c_global"] = 7
        s.p3_levels["ow_global"] = 5
        s.p4_levels["sb_global"] = 3
        s.upgrades.add("u_ore1")
        s.research.add("r_landfall")
        s.milestones.add("m_first_fab")
        s.achievements.add("a_first")
        # Rolled by the real roller: a hand-built artifact dict is the wrong
        # shape and would only test my typing.
        art = E._roll_artifact(s, G.TARGETS[0], random.Random(5))
        s.equipped = [art["id"]]
        E.recompute(s)
        # No fleet whatsoever: the worst case the system can produce.
        s.gens["D1"] = ZERO
        before = {
            "p1_sp": s.p1_sp, "p2_coh": s.p2_coh, "p3_oc": s.p3_oc,
            "p4_sub": s.p4_sub,
            "p1_levels": dict(s.p1_levels), "p2_levels": dict(s.p2_levels),
            "p3_levels": dict(s.p3_levels), "p4_levels": dict(s.p4_levels),
            "upgrades": set(s.upgrades), "research": set(s.research),
            "milestones": set(s.milestones), "achievements": set(s.achievements),
            "artifacts": copy.deepcopy(s.artifacts), "equipped": list(s.equipped),
            "unlocked": set(s.unlocked),
        }

        run(s, 2000)
        self.assertGreater(s.combat_losses, 0, "expected at least one loss")

        for key, was in before.items():
            now = getattr(s, key)
            if key == "milestones":
                # Milestones are earned, never lost: superset, not equality.
                self.assertTrue(was <= now, "a milestone was taken away")
            elif key in ("achievements", "unlocked", "upgrades", "research"):
                self.assertTrue(was <= now, f"{key} lost an entry")
            else:
                self.assertEqual(now, was, f"combat altered {key}")

    def test_power_generators_are_never_destroyed(self):
        s = armed()
        for gid in G.ENERGY_GENS:
            s.gens[gid] = N(5000)
            s.bought[gid] = N(5000)
        E.recompute(s)
        s.gens["D1"] = ZERO
        held = {gid: s.gens[gid] for gid in G.ENERGY_GENS}
        run(s, 2000)
        self.assertGreater(s.combat_losses, 0)
        for gid, was in held.items():
            self.assertGreaterEqual(
                s.gens[gid], was,
                f"{gid} was destroyed -- that is the death spiral the throttle "
                f"exemption exists to prevent")

    def test_the_fleet_itself_is_never_destroyed(self):
        """Fleet power is hyper-exponential in count, so erosion is a spiral."""
        s = armed()
        fight(s, size=0.2, limit=200)
        held = s.gens["D1"]
        fight(s, limit=4000)
        self.assertEqual(s.gens["D1"], held)

    def test_start_floors_hold(self):
        s = armed()
        s.p3_levels["ow_floor_e"] = 4      # 100 of each of E1-E5, every run
        E.recompute(s)
        floors = E.start_gen_counts(E.collect_mults(s))
        self.assertGreater(floors.get("E3", 0.0), 0.0)
        s.gens["E3"] = Num(floors["E3"])
        s.bought["E3"] = Num(floors["E3"])
        s.gens["D1"] = ZERO
        E.recompute(s)
        run(s, 2000)
        self.assertGreater(s.combat_losses, 0)
        self.assertGreaterEqual(s.gens["E3"], Num(floors["E3"]),
                                "a floor combat can eat is not a floor")


class TestAttrition(unittest.TestCase):
    def test_gens_and_bought_fall_together(self):
        """The split exists because free units caused an unbounded runaway.

        Cutting only `gens` re-creates that inverted; cutting only `bought`
        hands out free production. They move as one or not at all.
        """
        s = armed()
        s.gens["D1"] = ZERO
        s.gens["E3"] = N(1e6)
        s.bought["E3"] = N(1e6)
        E.recompute(s)
        before_g, before_b = s.gens["E3"], s.bought["E3"]
        run(s, 2000)
        lost_g = before_g - s.gens["E3"]
        lost_b = before_b - s.bought["E3"]
        self.assertGreater(lost_g, ZERO, "expected E3 losses")
        self.assertEqual(lost_g, lost_b)

    def test_worst_case_is_bounded(self):
        s = armed()
        s.gens["D1"] = ZERO
        s.gens["E3"] = N(1e6)
        s.bought["E3"] = N(1e6)
        E.recompute(s)
        before = s.gens["E3"]
        fight(s)
        kept = (s.gens["E3"] / before).to_float()
        self.assertGreater(kept, 0.5,
                           "a single incursion must never take half a tier")

    def test_no_cliff_between_adequate_and_inadequate(self):
        """95% of what you need must lose a little more, never a run."""
        losses = []
        for mult in (1.0, 1.2, 2.0, 10.0):
            s = armed()
            s.threat = E.incursion_bar(s)
            E.tick(s, 0.25, random.Random(3))
            before = s.gens["E3"]
            self.assertEqual(fight(s, size=mult), "win", f"{mult}x should clear it")
            losses.append((s.gens["E3"] / before).to_float())
        for a, b in zip(losses, losses[1:]):
            self.assertLessEqual(a, b + 1e-9,
                                 "a stronger fleet must never lose more")

    def test_higher_tiers_are_tougher(self):
        # E1 is deliberately not measured here: Fabricator Arms rebuild it for
        # free during the fight, so its standing count says nothing about
        # attrition. These three are produced by nothing.
        tiers = ("E3", "E6", "E8")
        s = armed()
        s.gens["D1"] = ZERO
        for gid in tiers:
            s.gens[gid] = N(1e6)
            s.bought[gid] = N(1e6)
            s.unlocked.add(gid)
        E.recompute(s)
        before = {g: s.gens[g] for g in tiers}
        fight(s)
        kept = {g: (s.gens[g] / before[g]).to_float() for g in tiers}
        self.assertLess(kept["E3"], kept["E6"])
        self.assertLess(kept["E6"], kept["E8"])


class TestGrowthShape(unittest.TestCase):
    def test_threat_is_log_damped(self):
        """1e20 replicators must not produce 1e20 threat."""
        small, big = armed(swarm=100), armed(swarm=int(1e20))
        self.assertLess(E.threat_rate(big), 20.0 * E.threat_rate(small))

    def test_strength_tracks_the_bank(self):
        """Sizing an incursion off the swarm made it literally unwinnable.

        Measured on a real endgame save: 1e7.5Qa damage/s demanded against
        1e2.2Qa affordable. The swarm replicates for free and grows
        hyper-exponentially; a fleet is bought, and cost is exponential in
        count, so affordable power is only logarithmic in cash. The demand has
        to be measured against the wallet that has to meet it.
        """
        s = armed()
        poor = E.incursion_strength(s)
        s.res["ore"] = s.res["ore"] * N(1e10)
        E.recompute(s)
        self.assertGreater(E.incursion_strength(s), poor)

    def test_strength_does_not_ratchet_off_your_own_fleet(self):
        """Buying ships must not raise the bar you bought them to clear."""
        s = armed()
        before = E.incursion_strength(s)
        s.gens["D1"] = N(50_000)
        s.bought["D1"] = N(50_000)
        E.recompute(s)
        self.assertEqual(E.incursion_strength(s), before)

    def test_the_requirement_is_always_affordable(self):
        """It is a share of the bank by construction, so it can never brick."""
        for bank in (1e6, 1e18, 1e60, 1e200):
            s = armed()
            s.res["ore"] = N(bank)
            s.res["alloy"] = N(bank)
            E.recompute(s)
            need = E.incursion_strength(s)
            self.assertGreater(need, ZERO, f"no demand at a bank of {bank:g}")
            for g in reversed(G.DEFEND_GENS):
                if g.id in s.unlocked:
                    E.buy(s, g.id, "max")
                    break
            E.recompute(s)
            self.assertGreaterEqual(
                E.fleet_power(s), need,
                f"a full-bank fleet could not meet the demand at {bank:g}")

    def test_a_fleet_at_the_stated_requirement_actually_wins(self):
        """The header prints this number. It has to be true."""
        self.assertEqual(fight(armed(), size=1.0), "win")

    def test_a_token_fleet_does_not(self):
        self.assertEqual(fight(armed(), size=0.1), "loss")


class TestTutorial(unittest.TestCase):
    def test_first_incursion_cannot_be_lost(self):
        s = armed(wins=0)
        s.gens["D1"] = ZERO
        E.recompute(s)
        before = s.gens["E3"]
        self.assertEqual(fight(s), "win")
        self.assertEqual(s.combat_losses, 0)
        self.assertEqual(s.gens["E3"], before, "the tutorial cost the player")

    def test_the_second_one_is_real(self):
        s = armed(wins=0)
        s.gens["D1"] = ZERO
        E.recompute(s)
        self.assertEqual(fight(s), "win")        # tutorial
        self.assertEqual(fight(s), "loss")       # the real thing


class TestRewards(unittest.TestCase):
    def test_a_win_pays_salvage(self):
        s = armed()
        s.threat = E.incursion_bar(s)
        E.tick(s, 0.25, random.Random(3))
        before = s.res.get("alloy", ZERO)
        self.assertEqual(fight(s, size=5.0), "win")
        self.assertGreater(s.res["alloy"], before)

    def test_wins_pay_a_permanent_global_multiplier(self):
        s = armed()
        base = E.collect_mults(s).glob
        s.combat_wins = 999
        self.assertGreater(E.collect_mults(s).glob, base)

    def test_the_multiplier_is_logarithmic(self):
        """1,000 clears is x2.5, not x1,000."""
        s = armed()
        s.combat_wins = 0
        base = E.collect_mults(s).glob
        s.combat_wins = 1000
        ratio = (E.collect_mults(s).glob / base).to_float()
        self.assertLess(ratio, 4.0)
        self.assertGreater(ratio, 1.5)


class TestResetScope(unittest.TestCase):
    def test_threat_belongs_to_the_run(self):
        self.assertEqual(RESET_SCOPE["threat"], G.RUN)
        self.assertEqual(RESET_SCOPE["incursion"], G.RUN)

    def test_the_war_record_is_permanent(self):
        """It feeds a global multiplier; a tally that reset would never count."""
        for field in ("combat_wins", "combat_losses", "combat_lost_units"):
            self.assertNotIn(field, RESET_SCOPE)
        s = armed()
        s.combat_wins, s.combat_losses = 40, 3
        s.threat = 123.0
        s.run_life["alloy"] = N(1e12)     # enough that the Dispersal actually fires
        E.recompute(s)
        self.assertGreater(E.p1_gain(s), ZERO)
        E.prestige(s, "p1")
        self.assertEqual(s.combat_wins, 40)
        self.assertEqual(s.combat_losses, 3)
        self.assertEqual(s.threat, 0.0)
        self.assertIsNone(s.incursion)

    def test_a_fight_in_progress_survives_a_save(self):
        from seed.state import GameState
        s = armed()
        run(s, 1200)
        s.incursion = s.incursion or {"hp": "1", "hp0": "1", "strength": "1",
                                      "elapsed": 0.0, "lost": "0",
                                      "tutorial": False}
        back = GameState.from_dict(s.to_dict())
        self.assertEqual(back.incursion, s.incursion)
        self.assertEqual(back.combat_wins, s.combat_wins)


class TestAutomation(unittest.TestCase):
    def test_auto_defence_is_gated_on_its_unlock(self):
        s = armed()
        s.auto["defence_enabled"] = True
        s.gens["D1"] = ZERO
        E.recompute(s)
        run(s, 60)
        self.assertEqual(s.gens.get("D1", ZERO), ZERO)

    def test_auto_defence_builds_a_fleet(self):
        s = armed()
        s.perm_flags.add("auto_defence")
        s.auto["defence_enabled"] = True
        s.res["ore"] = N(1e30)
        s.res["alloy"] = N(1e30)
        E.recompute(s)
        run(s, 300)
        self.assertGreater(E.fleet_power(s), ZERO)


if __name__ == "__main__":
    unittest.main()
