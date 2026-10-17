import os
from pathlib import Path
import tempfile
import threading
import unittest

from file_collector.core import Filters, scan, make_plan


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()

    def put(self, name, content=b"volume"):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_collect_hundred_volumes_without_accessories(self):
        for number in range(100):
            self.put(f"part-{number}/Serie {number:03}.PDF")
            self.put(f"part-{number}/readme.txt")
        result = scan([self.source], Filters(extensions="pdf,cbr,cbz"))
        self.assertEqual(len(result.files), 100)
        self.assertFalse(result.errors)

    def test_overlapping_roots_destination_and_links_are_excluded(self):
        self.put("one/deep/a.cbr")
        self.put("output/b.pdf")
        (self.source / "loop").symlink_to(self.source, target_is_directory=True)
        (self.source / "link.pdf").symlink_to(self.source / "one/deep/a.cbr")
        result = scan([self.source, self.source / "one"], Filters(), self.source / "output")
        self.assertEqual([f.path.name for f in result.files], ["a.cbr"])

    def test_filters_name_size_depth_hidden_and_exclusions(self):
        self.put("a.pdf", b"a")
        wanted = self.put("one/Serie 001.pdf", b"123456")
        self.put("one/two/Serie 002.pdf", b"123456")
        self.put(".hidden/Serie 003.pdf", b"123456")
        self.put("skip/Serie 004.pdf", b"123456")
        result = scan([self.source], Filters(name="serie", min_size=3,
                      max_depth=1, excluded="skip"))
        self.assertEqual([f.path for f in result.files], [wanted])

    def test_cancelled_search_does_not_report_completion(self):
        self.put("a.pdf")
        cancel = threading.Event()
        cancel.set()
        self.assertTrue(scan([self.source], Filters(), cancel=cancel).cancelled)

    def test_invalid_filters_raise(self):
        with self.assertRaises(ValueError):
            Filters(min_size=10, max_size=1)
        with self.assertRaises(ValueError):
            Filters(after="not a date")

    def test_plan_handles_existing_and_batch_conflicts(self):
        self.put("a/comic.pdf")
        self.put("b/comic.pdf")
        dest = self.root / "out"
        dest.mkdir()
        (dest / "comic.pdf").write_bytes(b"existing")
        files = scan([self.source], Filters()).files
        plan = make_plan(files, dest)
        self.assertEqual([p.target.name for p in plan], ["comic_001.pdf", "comic_002.pdf"])
        self.assertTrue(all(p.renamed for p in plan))
        self.assertTrue(all(p.skip for p in make_plan(files, dest, "skip")))

    def test_plan_skips_files_already_in_destination(self):
        self.put("comic.pdf")
        plan = make_plan(scan([self.source], Filters()).files, self.source)
        self.assertTrue(plan[0].skip)

    def test_date_filter_and_unicode(self):
        file = self.put("È già qui.cbz")
        os.utime(file, (946684800, 946684800))
        self.assertEqual(len(scan([self.source], Filters(before="2001-01-01")).files), 1)
        self.assertEqual(len(scan([self.source], Filters(after="2001-01-01")).files), 0)


if __name__ == "__main__":
    unittest.main()
