from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from file_collector.core import File, PlanItem, Filters, scan, make_plan
from file_collector.transfer import collect, history, restore, _digest, _rename_noreplace, _copy_verified


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "source"
        self.dest = self.root / "destination"
        self.src.mkdir()
        self.dest.mkdir()
        self.journal = self.root / "journal.sqlite3"

    def plan(self, name="comic.pdf"):
        file = self.src / name
        file.write_bytes(b"original volume" * 100)
        return make_plan(scan([self.src], Filters()).files, self.dest)

    def test_move_and_persistent_restore(self):
        plan = self.plan()
        result = collect(plan, self.journal)
        self.assertEqual(result.moved, 1)
        self.assertFalse(plan[0].file.path.exists())
        self.assertTrue(plan[0].target.exists())
        self.assertEqual(len(history(self.journal)), 1)
        back = restore(result.run_id, self.journal)
        self.assertEqual(back.moved, 1)
        self.assertTrue(plan[0].file.path.exists())
        self.assertFalse(plan[0].target.exists())
        self.assertFalse(history(self.journal))

    def test_late_conflict_never_overwrites(self):
        plan = self.plan()
        plan[0].target.write_bytes(b"other file")
        result = collect(plan, self.journal)
        self.assertEqual(result.moved, 0)
        self.assertEqual(plan[0].target.read_bytes(), b"other file")
        self.assertTrue(plan[0].file.path.exists())
        self.assertEqual(len(result.errors), 1)

    def test_changed_source_is_preserved(self):
        plan = self.plan()
        plan[0].file.path.write_bytes(b"changed")
        result = collect(plan, self.journal)
        self.assertEqual(len(result.errors), 1)
        self.assertFalse(plan[0].target.exists())

    def test_symlink_substitution_is_rejected(self):
        plan = self.plan()
        original = plan[0].file.path
        original.unlink()
        original.symlink_to(self.root / "missing")
        self.assertEqual(len(collect(plan, self.journal).errors), 1)

    def test_cancel_leaves_original_and_no_temporary_files(self):
        plan = self.plan()
        cancel = threading.Event()
        cancel.set()
        result = collect(plan, self.journal, cancel)
        self.assertTrue(result.cancelled)
        self.assertTrue(plan[0].file.path.exists())
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_cross_device_copy_and_restore(self):
        plan = self.plan()
        with patch("file_collector.transfer._rename", side_effect=OSError(18, "Cross-device link")):
            result = collect(plan, self.journal)
            self.assertEqual(result.moved, 1)
            self.assertEqual(restore(result.run_id, self.journal).moved, 1)

    def test_copy_failure_preserves_source(self):
        plan = self.plan()
        with patch("file_collector.transfer._rename", side_effect=OSError(18, "Cross-device link")), \
             patch("file_collector.transfer._copy_verified", side_effect=OSError(28, "No space left")):
            result = collect(plan, self.journal)
        self.assertEqual(len(result.errors), 1)
        self.assertTrue(plan[0].file.path.exists())

    def test_restore_refuses_modified_file_and_occupied_original(self):
        plan = self.plan()
        result = collect(plan, self.journal)
        plan[0].target.write_bytes(b"edited")
        back = restore(result.run_id, self.journal)
        self.assertEqual(len(back.errors), 1)
        self.assertFalse(plan[0].file.path.exists())

    def test_restore_never_overwrites_original(self):
        plan = self.plan()
        result = collect(plan, self.journal)
        plan[0].file.path.write_bytes(b"new original")
        back = restore(result.run_id, self.journal)
        self.assertEqual(back.moved, 0)
        self.assertEqual(plan[0].file.path.read_bytes(), b"new original")

    def test_skips_are_reported(self):
        plan = self.plan()
        skipped = PlanItem(plan[0].file, plan[0].target, skip=True)
        result = collect([skipped], self.journal)
        self.assertEqual(result.skipped, 1)
        self.assertTrue(plan[0].file.path.exists())

    def test_cancel_during_copy_cleans_staging_and_preserves_source(self):
        plan = self.plan()
        cancel = threading.Event()
        digest = _digest(plan[0].file, cancel)
        cancel.set()
        with self.assertRaises(InterruptedError):
            _copy_verified(plan[0].file, plan[0].target, digest, cancel)
        self.assertTrue(plan[0].file.path.exists())
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_corrupt_copy_is_not_published(self):
        plan = self.plan()
        cancel = threading.Event()
        with self.assertRaises(ValueError):
            _copy_verified(plan[0].file, plan[0].target, 'incorrect digest', cancel)
        self.assertTrue(plan[0].file.path.exists())
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_pending_move_after_journal_update_failure_can_be_restored(self):
        plan = self.plan()
        def moved_then_interrupted(source, target):
            _rename_noreplace(source, target)
            raise OSError(5, 'Interrupted after publication')
        with patch('file_collector.transfer._rename', side_effect=moved_then_interrupted):
            result = collect(plan, self.journal)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(restore(result.run_id, self.journal).moved, 1)
        self.assertTrue(plan[0].file.path.exists())

    def test_destination_symlink_substitution_is_rejected(self):
        plan = self.plan()
        elsewhere = self.root / 'elsewhere'
        elsewhere.mkdir()
        self.dest.rmdir()
        self.dest.symlink_to(elsewhere, target_is_directory=True)
        result = collect(plan, self.journal)
        self.assertEqual(len(result.errors), 1)
        self.assertTrue(plan[0].file.path.exists())
        self.assertEqual(list(elsewhere.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
