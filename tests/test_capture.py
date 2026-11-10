import os
import time
import unittest
from pathlib import Path

from dte import events
from dte.events import EventBus
from dte.services.capture import CaptureService, build_command, check_version, parse_line
from dte.services.firewire import Device
from dte.services.storage import StorageLocation
from tests.helpers import TempEnvTestCase

FAKE = Path(__file__).resolve().parent.parent / "dte" / "sim" / "fake_dvgrab.py"


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.device = Device("fw1", "0x0800460104", "Sony", "HVR-A1E")

    def test_auto_mode(self):
        loc = StorageLocation("usb", "/media/dte/usb/Videos", "vfat", "/dev/sda1")
        cmd = build_command("/opt/dvgrab", self.device, loc, "auto")
        self.assertEqual(cmd[0], "/opt/dvgrab")
        self.assertIn("--recordonly", cmd)
        self.assertIn("--autosplit", cmd)
        self.assertNotIn("--trigger", cmd)
        self.assertEqual(cmd[cmd.index("--size") + 1], "4000")
        self.assertEqual(cmd[cmd.index("--guid") + 1], "0x0800460104")
        self.assertEqual(cmd[-1], "/media/dte/usb/Videos/Sony_HVR-A1E-")
        for flag in ("--json", "--passive", "--timestamp", "--interactive"):
            self.assertIn(flag, cmd)

    def test_trigger_modes(self):
        loc = StorageLocation("internal", "/home/dte/Videos", "internal")
        for mode in ("standalone", "lanc"):
            cmd = build_command("/opt/dvgrab", self.device, loc, mode)
            self.assertIn("--trigger", cmd)
            self.assertNotIn("--recordonly", cmd)
            self.assertNotIn("--autosplit", cmd)
            self.assertEqual(cmd[cmd.index("--size") + 1], "0")

    def test_python_fake_runs_with_interpreter(self):
        loc = StorageLocation("internal", "/v", "internal")
        cmd = build_command("/x/fake_dvgrab.py", self.device, loc, "auto")
        self.assertTrue(cmd[0].endswith("python") or "python" in os.path.basename(cmd[0]))

    def test_parse_line(self):
        self.assertEqual(parse_line('{"type":"status","status":"REC"}')[0], events.CAPTURE_STATUS)
        self.assertEqual(parse_line('{"type":"file_closed"}')[0], events.CAPTURE_FILE)
        self.assertIsNone(parse_line("Capture Started"))
        self.assertIsNone(parse_line('{"type":"exit"}'))
        self.assertIsNone(parse_line("[1, 2]"))
        self.assertIsNone(parse_line(""))


class FakeDvgrabTests(TempEnvTestCase):
    """Runs the simulator's fake dvgrab through the real CaptureService."""

    def setUp(self):
        TempEnvTestCase.setUp(self)
        self.state_file = self.tmp / "camera_state"
        self.state_file.write_text("STBY")
        os.environ["DTE_FAKE_CAMERA_STATE"] = str(self.state_file)
        os.environ["DTE_FAKE_HDV_GUIDS"] = "0xHDV"
        self.bus = EventBus()
        self.capture = CaptureService(self.bus, FAKE, self.tmp / "dvgrab.log")
        self.location = StorageLocation("internal", self.tmp / "Videos", "internal")
        self.location.ensure_videos_dir()
        self.device = Device("fw1", "0xHDV", "Sony", "HVR-A1E")

    def tearDown(self):
        self.capture.stop()
        TempEnvTestCase.tearDown(self)

    def wait_for(self, predicate, timeout=8.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event = self.bus.get(timeout=0.1)
            if event is not None and predicate(event):
                return event
        self.fail("Timed out waiting for event")

    def files(self):
        return sorted(p.name for p in self.location.videos_dir.iterdir())

    def test_version_check(self):
        self.assertTrue(check_version(FAKE))
        self.assertFalse(check_version(self.tmp / "missing-binary"))

    def test_trigger_mode_one_file_per_take(self):
        self.capture.start(self.device, self.location, "standalone")
        ready = self.wait_for(lambda e: e.type == events.CAPTURE_READY)
        self.assertEqual(ready.data["format"], "HDV")
        self.assertEqual(ready.data["_gen"], self.capture.generation)

        self.capture.set_armed(True)
        rec = self.wait_for(lambda e: e.type == events.CAPTURE_STATUS and e.data["status"] == "REC")
        self.assertTrue(rec.data["file"].endswith(".m2t"))
        self.capture.set_armed(False)
        self.wait_for(lambda e: e.type == events.CAPTURE_FILE and e.data["type"] == "file_closed")
        time.sleep(1.1)  # new second -> new name
        self.capture.set_armed(True)
        self.wait_for(lambda e: e.type == events.CAPTURE_FILE and e.data["type"] == "file_open")
        self.capture.stop()
        names = self.files()
        self.assertEqual(len(names), 2, names)
        self.assertTrue(all(n.startswith("Sony_HVR-A1E-") for n in names))

    def test_auto_mode_follows_camera(self):
        self.capture.start(self.device, self.location, "auto")
        self.wait_for(lambda e: e.type == events.CAPTURE_READY)
        self.state_file.write_text("REC")
        self.wait_for(lambda e: e.type == events.CAPTURE_STATUS and e.data["status"] == "REC")
        self.state_file.write_text("STBY")
        self.wait_for(lambda e: e.type == events.CAPTURE_STATUS and e.data["status"] == "STBY")
        self.assertEqual(len(self.files()), 1)

    def test_stop_marks_old_events_stale(self):
        self.capture.start(self.device, self.location, "auto")
        self.wait_for(lambda e: e.type == events.CAPTURE_READY)
        gen = self.capture.generation
        self.capture.stop()
        self.assertFalse(self.capture.running)
        self.assertNotEqual(self.capture.generation, gen)


if __name__ == "__main__":
    unittest.main()
