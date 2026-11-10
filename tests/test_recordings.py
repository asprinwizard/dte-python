import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from dte.ui.recordings import labels, list_recordings


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.dir))

    def touch(self, name):
        path = self.dir / name
        path.write_bytes(b"x")
        return path

    def test_sorted_newest_first_by_name_date(self):
        self.touch("Sony_HVR-A1E-09-11-2026_10-00-00.m2t")
        self.touch("Sony_HVR-A1E-10-11-2026_14-22-01.m2t")
        self.touch("Sony_HVR-A1E-31-12-2025_23-59-59.m2t")
        self.touch("notes.txt")
        names = [r.name for r in list_recordings(self.dir)]
        self.assertEqual(names, [
            "Sony_HVR-A1E-10-11-2026_14-22-01.m2t",
            "Sony_HVR-A1E-09-11-2026_10-00-00.m2t",
            "Sony_HVR-A1E-31-12-2025_23-59-59.m2t",
        ])

    def test_labels_normal(self):
        self.touch("Sony_HVR-A1E-10-11-2026_14-22-01.m2t")
        recs = list_recordings(self.dir)
        self.assertEqual(labels(recs, 16), ["10-11-2026 14:22"])
        self.assertEqual(labels(recs, 13), ["10-11 14:22"])

    def test_labels_same_minute_show_seconds(self):
        self.touch("Sony_HVR-A1E-10-11-2026_14-22-01.m2t")
        self.touch("Sony_HVR-A1E-10-11-2026_14-22-40.m2t")
        self.touch("Sony_HVR-A1E-10-11-2026_14-22-40-2.m2t")
        recs = list_recordings(self.dir)
        self.assertEqual(labels(recs, 16), ["10-11 14:22:40 2", "10-11 14:22:40", "10-11 14:22:01"])
        self.assertEqual(labels(recs, 13), ["10-11 14:22:4", "10-11 14:22:4", "10-11 14:22:0"])
        self.assertTrue(all(len(label) <= 16 for label in labels(recs, 16)))

    def test_labels_without_timestamp_use_end_of_name(self):
        path = self.touch("dvgrab-001.dv")
        os.utime(str(path), (time.time(), time.time()))
        self.assertEqual(labels(list_recordings(self.dir), 13), ["dvgrab-001.dv"])

    def test_missing_dir(self):
        self.assertEqual(list_recordings(self.dir / "missing"), [])


if __name__ == "__main__":
    unittest.main()
