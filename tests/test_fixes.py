import errno
import os
import stat
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from file_collector import transfer
from file_collector.core import Filters, collision_name, make_plan, scan, split_name
from file_collector.i18n import CATALOG, LANGUAGES, translate
from file_collector.transfer import collect, history, restore


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "source"
        self.dest = self.root / "destination"
        self.src.mkdir()
        self.dest.mkdir()
        self.journal = self.root / "journal.sqlite3"

    def put(self, name, data=b"content"):
        path = self.src / (os.fsdecode(name) if isinstance(name, bytes) else name)
        path.write_bytes(data)
        return path

    def plan(self, **filters):
        return make_plan(scan([self.src], Filters(**filters)).files, self.dest)


class CompoundExtensionTests(Base):
    def test_tar_gz_filter_matches(self):
        self.put("backup.tar.gz")
        self.put("notes.gz")
        names = [f.path.name for f in scan([self.src], Filters(extensions="tar.gz")).files]
        self.assertEqual(names, ["backup.tar.gz"])

    def test_single_extension_still_matches_last_suffix(self):
        self.put("a.PDF")
        self.assertEqual(len(scan([self.src], Filters(extensions="pdf")).files), 1)

    def test_split_name_keeps_tar_together(self):
        self.assertEqual(split_name("a.tar.gz"), ("a", ".tar.gz"))
        self.assertEqual(split_name("a.txt"), ("a", ".txt"))
        self.assertEqual(split_name(".hidden"), (".hidden", ""))

    def test_collision_name_uses_compound_extension(self):
        self.assertEqual(collision_name("a.tar.gz", 1), "a_001.tar.gz")

    def test_collision_name_respects_name_limit(self):
        name = "é" * 120 + ".pdf"  # 244 bytes
        new = collision_name(name, 12)
        self.assertLessEqual(len(new.encode()), 255)
        self.assertTrue(new.endswith("_012.pdf"))

    def test_long_name_collision_moves_both(self):
        name = "x" * 251 + ".pdf"
        self.put(name)
        (self.dest / name).write_bytes(b"other")
        result = collect(self.plan(), self.journal)
        self.assertEqual((result.moved, result.errors), (1, []))


class NameTests(Base):
    def test_non_utf8_name_is_moved_and_restored(self):
        bad = os.fsencode(self.src) + b"/bad\xff.txt"
        with open(bad, "wb") as stream:
            stream.write(b"data")
        result = collect(self.plan(), self.journal)
        self.assertEqual((result.moved, result.errors), (1, []))
        self.assertTrue(os.path.exists(os.fsencode(self.dest) + b"/bad\xff.txt"))
        back = restore(result.run_id, self.journal)
        self.assertEqual((back.moved, back.errors), (1, []))
        self.assertTrue(os.path.exists(bad))


class JournalTests(Base):
    def test_failed_move_is_not_recorded_as_collection(self):
        self.put("a.pdf")
        with patch.object(transfer, "_move", side_effect=OSError(errno.EIO, "boom")):
            result = collect(self.plan(), self.journal)
        self.assertEqual((result.moved, len(result.errors)), (0, 1))
        self.assertEqual(history(self.journal), [])

    def test_duplicate_left_by_interruption_is_cleaned_by_restore(self):
        source = self.put("a.pdf")
        plan = self.plan()
        digest = transfer._digest(plan[0].file, threading.Event())
        with transfer.database(self.journal) as connection:
            connection.execute("INSERT INTO operations(run,source,target,digest,status) VALUES(?,?,?,?,?)",
                               ("run1", transfer._db_path(source), transfer._db_path(plan[0].target), digest, "pending"))
            connection.commit()
        plan[0].target.write_bytes(source.read_bytes())
        back = restore("run1", self.journal)
        self.assertEqual((back.moved, back.errors), (1, []))
        self.assertTrue(source.exists())
        self.assertFalse(plan[0].target.exists())

    def test_restore_reports_progress_for_unchanged_rows(self):
        source = self.put("a.pdf")
        plan = self.plan()
        with transfer.database(self.journal) as connection:
            connection.execute("INSERT INTO operations(run,source,target,digest,status) VALUES(?,?,?,?,?)",
                               ("run2", transfer._db_path(source), transfer._db_path(plan[0].target), "x", "pending"))
            connection.commit()
        calls = []
        restore("run2", self.journal, progress=lambda *args: calls.append(args))
        self.assertEqual(len(calls), 1)

    def test_stale_staging_files_are_removed(self):
        stale = self.dest / ".file-collector-abc"
        stale.write_bytes(b"partial")
        keep = self.dest / ".other"
        keep.write_bytes(b"x")
        self.put("a.pdf")
        collect(self.plan(), self.journal)
        self.assertFalse(stale.exists())
        self.assertTrue(keep.exists())


class FilesystemTests(Base):
    def test_fifo_in_place_of_file_is_refused_without_hanging(self):
        source = self.put("a.pdf")
        plan = self.plan()
        source.unlink()
        os.mkfifo(source)
        result = collect(plan, self.journal)
        self.assertEqual(result.moved, 0)
        self.assertEqual(len(result.errors), 1)

    def test_setuid_bit_is_not_copied_across_devices(self):
        source = self.put("a.pdf")
        os.chmod(source, 0o4755)
        plan = self.plan()
        real = transfer._rename_noreplace
        def exdev(src, dst):
            if Path(src) == source:
                raise OSError(errno.EXDEV, "cross-device")
            return real(src, dst)
        with patch.object(transfer, "_rename_noreplace", side_effect=exdev):
            result = collect(plan, self.journal)
        self.assertEqual(result.moved, 1)
        mode = stat.S_IMODE(plan[0].target.stat().st_mode)
        self.assertEqual(mode & 0o6000, 0)

    def test_filesystem_without_noreplace_still_moves_and_never_overwrites(self):
        self.put("a.pdf")
        self.put("b.pdf")
        (self.dest / "b.pdf").write_bytes(b"other")
        plan = make_plan(scan([self.src], Filters()).files, self.dest, "skip")
        with patch.object(transfer, "_rename_noreplace", side_effect=OSError(errno.EINVAL, "unsupported")):
            result = collect(plan, self.journal)
        self.assertEqual((result.moved, result.errors), (1, []))
        self.assertEqual((self.dest / "b.pdf").read_bytes(), b"other")

    def test_noreplace_fallback_refuses_existing_target(self):
        source = self.put("a.pdf")
        target = self.dest / "a.pdf"
        target.write_bytes(b"other")
        with patch.object(transfer, "_rename_noreplace", side_effect=OSError(errno.EINVAL, "unsupported")):
            with self.assertRaises(FileExistsError):
                transfer._rename(source, target)
        self.assertEqual(target.read_bytes(), b"other")

    def test_fat_like_cross_device_copy_publishes_without_link(self):
        source = self.put("a.pdf")
        plan = self.plan()
        real = transfer._rename_noreplace
        def fake(src, dst):
            if Path(src) == source:
                raise OSError(errno.EXDEV, "cross-device")
            raise OSError(errno.EINVAL, "unsupported")
        with patch.object(transfer, "_rename_noreplace", side_effect=fake), \
                patch("os.link", side_effect=PermissionError(errno.EPERM, "no links")):
            result = collect(plan, self.journal)
        self.assertEqual((result.moved, result.errors), (1, []))
        self.assertTrue(plan[0].target.exists())
        self.assertFalse(source.exists())


class DestinationTests(Base):
    def test_destination_equal_to_source_is_explained(self):
        self.put("a.pdf")
        result = scan([self.src], Filters(), destination=self.src)
        self.assertEqual(result.files, [])
        self.assertTrue(any("destination" in error for error in result.errors))


class CatalogTests(unittest.TestCase):
    def test_every_entry_has_four_translations(self):
        for key, values in CATALOG.items():
            self.assertEqual(len(values), 4, key)
            self.assertTrue(all(values), key)

    def test_placeholders_match_english(self):
        import re
        for key, values in CATALOG.items():
            expected = sorted(re.findall(r"{\w+}", key))
            for value in values:
                self.assertEqual(sorted(re.findall(r"{\w+}", value)), expected, key)

    def test_all_languages_translate(self):
        for code in LANGUAGES:
            self.assertTrue(translate("Search finished with errors", code))


class PackageTests(unittest.TestCase):
    def test_version_matches_changelog_and_readme(self):
        from file_collector import __version__
        root = Path(__file__).resolve().parent.parent
        self.assertIn(f"## {__version__} ", (root / "CHANGELOG.md").read_text())
        self.assertIn(f"file-collector_{__version__}_all.deb", (root / "README.md").read_text())

    def test_installed_assets_exist(self):
        root = Path(__file__).resolve().parent.parent
        for name in ("icon.svg", "icon-small.svg", "icon-round.svg", "icon-small-round.svg", "style.css"):
            self.assertTrue((root / "src/file_collector" / name).is_file(), name)
        self.assertTrue((root / "packaging/copyright").is_file())


if __name__ == "__main__":
    unittest.main()
