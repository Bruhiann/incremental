"""Save safety: atomicity, corruption fallback, and never wiping the player."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from seed import engine as E
from seed import gamedata as G
from seed import saveman as S
from seed.bignum import N, Num, ZERO
from seed.state import new_game


class SaveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("LOCALAPPDATA")
        os.environ["LOCALAPPDATA"] = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self._old
        self._tmp.cleanup()

    def populated(self):
        s = new_game()
        s.res["ore"] = N(1.2345e40)
        s.run_life["alloy"] = N(5e7)
        s.total_life["ore"] = N(9e99)
        E.recompute(s)
        E.buy(s, "E1", 12)
        s.research.add("r_foreman")
        s.milestones.add("m_first_fab")
        s.achievements.add("a_first_ore")
        s.perm_flags.add("found_artifact")
        s.artifacts.append({"id": "a1", "name": "Fused Ferrous Core", "kind": G.MULT_RES,
                            "target": "ore", "value": 1.4, "rarity": "rare", "desc": "x"})
        s.equipped.append("a1")
        s.p1_sp = N(1234)
        s.p1_levels["sg_global"] = 3
        s.p1_count = 2
        s.auto["enabled"] = True
        s.auto["gens"]["E1"] = True
        s.auto["upgrades"] = True
        s.auto["relics"] = True
        s.p1_levels["sg_autoupg"] = 1
        s.p1_levels["sg_autorelic"] = 1
        s.p2_coh = N(87)
        s.p2_coh_life = N(412)
        s.p2_levels["c_global"] = 6
        s.p2_count = 3
        s.doctrines = {1: "d1_swarm", 3: "d3_mind"}
        s.res["nanite"] = N(1.5e25)
        s.probes.append({"target": "near", "remaining": 12.0, "total": 60.0})
        s.events.append({"id": "rich_vein", "remaining": 30.0})
        return s


class TestRoundTrip(SaveTest):
    def test_save_creates_file(self):
        self.assertTrue(S.save(self.populated()))
        self.assertTrue(S.save_path().exists())

    def test_full_round_trip(self):
        a = self.populated()
        S.save(a)
        b, status = S.load()
        self.assertEqual(status, "loaded")
        self.assertEqual(b.res["ore"], a.res["ore"])
        self.assertEqual(b.total_life["ore"], a.total_life["ore"])
        self.assertEqual(b.bought["E1"], a.bought["E1"])
        self.assertEqual(b.research, a.research)
        self.assertEqual(b.milestones, a.milestones)
        self.assertEqual(b.achievements, a.achievements)
        self.assertEqual(b.perm_flags, a.perm_flags)
        self.assertEqual(b.equipped, a.equipped)
        self.assertEqual(b.p1_sp, a.p1_sp)
        self.assertEqual(b.p1_levels, a.p1_levels)
        self.assertEqual(b.p1_count, a.p1_count)
        self.assertEqual(b.auto["gens"], a.auto["gens"])
        self.assertEqual(b.auto["upgrades"], a.auto["upgrades"])
        self.assertEqual(b.auto["relics"], a.auto["relics"])
        self.assertEqual(b.p2_coh, a.p2_coh)
        self.assertEqual(b.p2_coh_life, a.p2_coh_life)
        self.assertEqual(b.p2_levels, a.p2_levels)
        self.assertEqual(b.p2_count, a.p2_count)
        self.assertEqual(b.doctrines, a.doctrines)   # int keys survive JSON
        self.assertEqual(b.res["nanite"], a.res["nanite"])
        self.assertEqual(len(b.probes), 1)
        self.assertEqual(len(b.events), 1)

    def test_huge_numbers_survive(self):
        s = new_game()
        s.res["ore"] = Num(3.14159, 4321)
        S.save(s)
        b, _ = S.load()
        self.assertEqual(b.res["ore"].e, 4321)
        self.assertAlmostEqual(b.res["ore"].m, 3.14159, places=9)

    def test_derived_state_is_not_persisted(self):
        s = self.populated()
        S.save(s)
        raw = json.loads(S.save_path().read_text(encoding="utf-8"))
        for derived in ("mults", "breakdown", "rates", "throttle", "flags", "notices"):
            self.assertNotIn(derived, raw)

    def test_no_offline_progress(self):
        """Elapsed time between sessions must never be credited."""
        s = self.populated()
        E.buy(s, "E1", 10)
        ore = s.res["ore"]
        S.save(s)
        raw = json.loads(S.save_path().read_text(encoding="utf-8"))
        raw["stats"]["last_played"] = 0.0          # as if closed years ago
        S.save_path().write_text(json.dumps(raw), encoding="utf-8")
        b, _ = S.load()
        self.assertEqual(b.res["ore"], ore)


class TestSafety(SaveTest):
    def test_backup_is_written_on_second_save(self):
        s = self.populated()
        S.save(s)
        s.res["ore"] = N(1)
        S.save(s)
        self.assertTrue(S.backup_path().exists())

    def test_corrupt_main_falls_back_to_backup(self):
        s = self.populated()
        S.save(s)                       # main
        s.res["ore"] = N(777)
        S.save(s)                       # main again, previous copied to backup
        S.save_path().write_text("{ this is not json", encoding="utf-8")
        b, status = S.load()
        self.assertEqual(status, "backup")
        self.assertGreater(b.res["ore"], ZERO)

    def test_corrupt_both_starts_fresh_without_deleting(self):
        s = self.populated()
        S.save(s)
        S.save(s)
        S.save_path().write_text("garbage", encoding="utf-8")
        S.backup_path().write_text("also garbage", encoding="utf-8")
        b, status = S.load()
        self.assertEqual(status, "new")
        self.assertEqual(b.res["ore"], ZERO)
        # The corrupt files are left on disk for the player to recover manually.
        self.assertTrue(S.save_path().exists())
        self.assertTrue(S.backup_path().exists())

    def test_no_save_starts_fresh(self):
        b, status = S.load()
        self.assertEqual(status, "new")
        self.assertEqual(b.p1_count, 0)

    def test_main_is_untouched_when_serialization_fails(self):
        s = self.populated()
        S.save(s)
        good = S.save_path().read_text(encoding="utf-8")
        s.stats["bad"] = {1, 2, 3}       # a set is not JSON-serializable
        self.assertFalse(S.save(s))
        self.assertEqual(S.save_path().read_text(encoding="utf-8"), good)

    def test_temp_file_is_not_left_behind(self):
        S.save(self.populated())
        self.assertFalse((S.save_dir() / S.TEMP_NAME).exists())

    def test_load_tolerates_truncated_json(self):
        s = self.populated()
        S.save(s)
        text = S.save_path().read_text(encoding="utf-8")
        S.save_path().write_text(text[: len(text) // 2], encoding="utf-8")
        _, status = S.load()
        self.assertIn(status, ("backup", "new"))


class TestSchemaTolerance(SaveTest):
    def test_unknown_keys_are_ignored(self):
        s = self.populated()
        S.save(s)
        raw = json.loads(S.save_path().read_text(encoding="utf-8"))
        raw["some_future_field"] = {"a": 1}
        raw["gens"]["E_NOT_A_REAL_GEN"] = "1e5"
        S.save_path().write_text(json.dumps(raw), encoding="utf-8")
        b, status = S.load()
        self.assertEqual(status, "loaded")
        self.assertNotIn("E_NOT_A_REAL_GEN", b.gens)

    def test_missing_sections_use_defaults(self):
        s = self.populated()
        S.save(s)
        raw = json.loads(S.save_path().read_text(encoding="utf-8"))
        for key in ("auto", "stats", "settings", "p1_levels", "artifacts"):
            raw.pop(key, None)
        S.save_path().write_text(json.dumps(raw), encoding="utf-8")
        b, status = S.load()
        self.assertEqual(status, "loaded")
        self.assertIn("enabled", b.auto)
        self.assertIn("playtime", b.stats)
        self.assertEqual(b.artifacts, [])

    def test_equipped_referencing_missing_artifact_is_dropped(self):
        s = self.populated()
        s.equipped.append("ghost")
        S.save(s)
        b, _ = S.load()
        self.assertNotIn("ghost", b.equipped)

    def test_version_is_recorded(self):
        S.save(self.populated())
        raw = json.loads(S.save_path().read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], G.SAVE_VERSION)

    def test_loaded_save_is_immediately_tickable(self):
        S.save(self.populated())
        b, _ = S.load()
        E.tick(b, 0.1)
        E.tick(b, 0.1)
        self.assertGreaterEqual(b.res["ore"], ZERO)


class TestExportImport(SaveTest):
    def test_export_import_round_trip(self):
        a = self.populated()
        blob = S.export_text(a)
        b = S.import_text(blob)
        self.assertIsNotNone(b)
        self.assertEqual(b.res["ore"], a.res["ore"])
        self.assertEqual(b.p1_sp, a.p1_sp)

    def test_import_rejects_rubbish(self):
        self.assertIsNone(S.import_text("not base64 at all !!"))
        self.assertIsNone(S.import_text(""))

    def test_delete_save_removes_both_files(self):
        S.save(self.populated())
        S.save(self.populated())
        S.delete_save()
        self.assertFalse(S.save_path().exists())
        self.assertFalse(S.backup_path().exists())


if __name__ == "__main__":
    unittest.main()


class TestCloseBehaviour(SaveTest):
    """Closing the window is the main save path, so it gets a regression test."""

    def test_save_reports_failure_instead_of_lying(self):
        s = self.populated()
        S.save(s)
        good = S.save_path().read_text(encoding="utf-8")
        s.stats["unserializable"] = {1, 2}
        self.assertFalse(S.save(s), "a failed save must report False")
        self.assertEqual(S.save_path().read_text(encoding="utf-8"), good)

    def test_state_survives_a_save_load_cycle_unchanged(self):
        a = self.populated()
        E.tick(a, 0.1)
        self.assertTrue(S.save(a))
        b, status = S.load()
        self.assertEqual(status, "loaded")
        for gid in ("E1", "R1"):
            self.assertEqual(b.gens[gid], a.gens[gid])
            self.assertEqual(b.bought[gid], a.bought[gid])
