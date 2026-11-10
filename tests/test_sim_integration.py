"""End to end: real app, monitors and capture service against the simulated
world (fake sysfs, fake USB folder, fake dvgrab)."""

import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from dte import config, events, paths
from tests.helpers import RecordingDriver


class SimIntegrationTests(unittest.TestCase):
    def setUp(self):
        from dte.sim.world import SimWorld

        self.tmp = Path(tempfile.mkdtemp(prefix="dte-sim-"))
        self.world = SimWorld(self.tmp)
        self._saved = dict(os.environ)
        os.environ.update(self.world.env())
        defaults = self.tmp / "config.json"
        shutil.copy(str(paths.PROJECT_ROOT / "config.json"), str(defaults))
        os.environ["DTE_DEFAULT_CONFIG"] = str(defaults)
        config._listeners[:] = []

        from dte.hardware.lcd import LCD
        from dte.main import _common
        from dte.sim.world import SimBacklight, SimLanc, SimRecordLight, SimSystem, SimUsbBackend

        self.bus = events.EventBus()
        self.driver = RecordingDriver()
        self.app, self.services = _common(
            self.bus, LCD(self.driver), SimBacklight(self.world), SimSystem(self.bus),
            SimUsbBackend(self.world), SimLanc(self.world), SimRecordLight(self.world))
        for service in self.services:
            service._interval = 0.2
            service.start()
        self.thread = threading.Thread(target=self.app.run, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.bus.post(events.QUIT)
        self.thread.join(timeout=10)
        for service in self.services:
            service.stop()
        config._listeners[:] = []
        os.environ.clear()
        os.environ.update(self._saved)
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def wait_rows(self, predicate, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = self.driver.rows()
            if predicate(rows):
                return rows
            time.sleep(0.05)
        self.fail("LCD never matched; last rows: {!r}".format(self.driver.rows()))

    def wait_until(self, predicate, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        self.fail("Condition never became true")

    def videos(self, base):
        return sorted(p.name for p in base.glob("*") if p.is_file())

    def test_auto_mode_record_cycle_and_usb_switch(self):
        self.wait_rows(lambda r: r[0].startswith("No Device Found"))
        self.assertTrue(self.app.dvgrab_ok)

        self.world.toggle_camera("fw1")
        self.wait_rows(lambda r: r[0].startswith("HDV Sony HVR-") and "STBY" in r[1])

        self.world.set_camera_recording(True)
        self.wait_rows(lambda r: "REC" in r[1])
        self.assertTrue(self.world.light)
        self.world.set_camera_recording(False)
        self.wait_rows(lambda r: "STBY" in r[1])
        internal = Path(os.environ["DTE_INTERNAL_VIDEOS"])
        files = self.videos(internal)
        self.assertEqual(len(files), 1, files)
        self.assertRegex(files[0], r"^Sony_HVR-A1E-\d{2}-\d{2}-\d{4}_\d{2}-\d{2}-\d{2}\.m2t$")

        # USB plugged in while a camera is connected -> prompt; say Yes.
        self.world.toggle_usb("exfat")
        self.wait_rows(lambda r: r == ["USB Found       ", "Switch? No      "])
        self.bus.post(events.SCROLL_RIGHT)
        self.bus.post(events.CLICK)
        self.wait_rows(lambda r: r[0].startswith("HDV Sony HVR-") and "STBY" in r[1])
        self.assertEqual(self.app.storage.kind, "usb")

        self.world.set_camera_recording(True)
        self.wait_rows(lambda r: "REC" in r[1])
        # Pull the USB drive mid-recording: stops and falls back to internal,
        # and recording resumes there because the camera is still recording.
        self.world.toggle_usb("exfat")
        self.wait_until(lambda: self.app.storage.kind == "internal")
        self.wait_rows(lambda r: r[0].startswith("HDV") and "REC" in r[1], timeout=15)
        self.world.set_camera_recording(False)
        self.wait_rows(lambda r: "STBY" in r[1])
        self.assertEqual(len(self.videos(internal)), 2)
        self.assertEqual(len(self.videos(self.world.usb_dir / "Videos")), 1)

        self.world.toggle_camera("fw1")
        self.wait_rows(lambda r: r[0].startswith("No Device Found"))

    def test_standalone_mode(self):
        config.load()
        config.set("record_mode", "standalone")
        self.world.toggle_camera("fw2")
        self.wait_rows(lambda r: r[0].startswith("DV  Canon XM2") and "STBY" in r[1])
        self.bus.post(events.RECORD_BUTTON)
        rows = self.wait_rows(lambda r: "REC" in r[1])
        self.assertIn("00:00:0", rows[1])  # elapsed time: no camera timecode in trigger mode
        time.sleep(1.1)
        self.bus.post(events.RECORD_BUTTON)
        self.wait_rows(lambda r: "STBY" in r[1])
        files = self.videos(Path(os.environ["DTE_INTERNAL_VIDEOS"]))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("Canon_XM2-") and files[0].endswith(".dv"))

    def test_camera_without_names_uses_fallback_prefix(self):
        self.world.toggle_camera("fw3")
        self.wait_rows(lambda r: "Unknown" in r[0])
        self.world.set_camera_recording(True)
        self.wait_rows(lambda r: "REC" in r[1])
        self.world.set_camera_recording(False)
        self.wait_rows(lambda r: "STBY" in r[1])
        files = self.videos(Path(os.environ["DTE_INTERNAL_VIDEOS"]))
        self.assertTrue(files and files[0].startswith("dte-capture-"), files)


if __name__ == "__main__":
    unittest.main()
