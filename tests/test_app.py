import unittest

from dte import config, events
from dte.app import IDLE_TIMEOUT, App
from dte.events import Event
from dte.hardware.lcd import LCD
from dte.services.firewire import Device
from dte.services.storage import StorageLocation
from dte.ui import screens
from tests.helpers import RecordingDriver, TempEnvTestCase


class FakeCapture(object):
    def __init__(self):
        self.generation = 0
        self.running = False
        self.ready = False
        self.armed = False
        self.started = []
        self.armed_calls = []
        self.last_output = 1e12

    def start(self, device, location, mode):
        self.generation += 1
        self.running = True
        self.ready = False
        self.armed = False
        self.started.append((device, location, mode))

    def stop(self):
        if self.running:
            self.generation += 1
        self.running = False
        self.ready = False
        self.armed = False

    def set_armed(self, armed):
        self.armed = armed
        self.armed_calls.append(armed)


class FakeStorageMonitor(object):
    def __init__(self):
        self.released = []

    def release(self, location):
        self.released.append(location)


class FakeBacklight(object):
    def __init__(self):
        self.brightness = None
        self.contrast = None

    def set_brightness(self, value):
        self.brightness = value

    def set_contrast(self, value):
        self.contrast = value


class FakeSystem(object):
    def __init__(self):
        self.reset = False

    def factory_reset(self):
        self.reset = True


class FakeLanc(object):
    def __init__(self):
        self.high = False

    def is_high(self):
        return self.high


class FakeLight(object):
    def __init__(self):
        self.on = False

    def set(self, on):
        self.on = on


class AppTestCase(TempEnvTestCase):
    def setUp(self):
        TempEnvTestCase.setUp(self)
        self.driver = RecordingDriver()
        self.capture = FakeCapture()
        self.monitor = FakeStorageMonitor()
        self.backlight = FakeBacklight()
        self.system = FakeSystem()
        self.lanc = FakeLanc()
        self.light = FakeLight()
        self.app = App(events.EventBus(), LCD(self.driver), self.backlight, self.capture, None,
                       self.monitor, self.system, lanc=self.lanc, record_light=self.light)
        self.internal = StorageLocation("internal", self.tmp / "home" / "Videos", "internal")
        self.usb = StorageLocation("usb", self.tmp / "usb" / "Videos", "exfat", "/dev/sda1")
        self.camera = Device("fw1", "0x080046", "Sony", "HVR-A1E")
        self.send(events.STORAGE_CHANGED, locations=[self.internal])

    # helpers
    def send(self, type_, **data):
        self.app.handle(Event(type_, data))
        self.app.tick()
        self.app.render()

    def rows(self):
        return self.driver.rows()

    def connect(self):
        self.send(events.DEVICE_CONNECTED, device=self.camera)
        self.send(events.CAPTURE_READY, type="ready", format="HDV", _gen=self.capture.generation)
        self.capture.ready = True

    def status(self, status, timecode="00:45:12", elapsed="00:00:00"):
        self.send(events.CAPTURE_STATUS, type="status", status=status, timecode=timecode,
                  elapsed=elapsed, _gen=self.capture.generation)

    def top(self):
        return type(self.app.top)


class CaptureScreenTests(AppTestCase):
    def test_idle_screen(self):
        self.assertEqual(self.rows()[0], "No Device Found ")
        self.assertEqual(self.app.storage, self.internal)
        self.assertEqual(self.capture.started, [])

    def test_connect_starts_capture_and_shows_layout(self):
        self.connect()
        self.assertEqual(self.capture.started[-1], (self.camera, self.internal, "auto"))
        self.status("STBY")
        self.assertEqual(self.rows(), ["HDV Sony HVR- \x03\x04", "\x01STBY   00:45:12"])
        self.status("REC", "00:45:13")
        self.assertEqual(self.rows()[1], "\x00REC    00:45:13")
        self.assertTrue(self.light.on)

    def test_elapsed_shown_when_no_timecode(self):
        self.connect()
        self.status("REC", "--:--:--", "00:01:05")
        self.assertEqual(self.rows()[1], "\x00REC    00:01:05")

    def test_stale_events_ignored(self):
        self.connect()
        self.send(events.CAPTURE_STATUS, type="status", status="REC", timecode="11:11:11",
                  _gen=self.capture.generation - 1)
        self.assertNotIn("11:11:11", self.rows()[1])

    def test_device_removed_returns_to_idle(self):
        self.connect()
        self.status("REC")
        self.send(events.DEVICE_REMOVED, device=self.camera)
        self.assertFalse(self.capture.running)
        self.assertEqual(self.rows()[0], "No Device Found ")
        self.assertFalse(self.light.on)

    def test_unexpected_exit_restarts_then_gives_up(self):
        self.connect()
        for _ in range(2):
            self.send(events.CAPTURE_EXITED, returncode=1, _gen=self.capture.generation)
            self.app._restart_at = 0  # don't wait 2 s
            self.app.tick()
        self.assertEqual(len(self.capture.started), 3)
        self.send(events.CAPTURE_EXITED, returncode=1, _gen=self.capture.generation)
        self.assertEqual(self.app.capture_error, "Capture Error")


class ButtonRuleTests(AppTestCase):
    def test_click_opens_playback_when_idle(self):
        self.send(events.CLICK)
        self.assertIs(self.top(), screens.PlaybackListScreen)
        self.assertEqual(self.rows(), ["Select File:    ", "No Files        "])

    def test_buttons_ignored_while_recording(self):
        self.connect()
        self.status("REC")
        self.send(events.CLICK)
        self.send(events.LONG_CLICK)
        self.assertIs(self.top(), screens.CaptureScreen)

    def test_recording_jumps_back_from_menus(self):
        self.connect()
        self.status("STBY")
        self.send(events.LONG_CLICK)
        self.assertIs(self.top(), screens.SettingsRootScreen)
        self.status("REC")
        self.assertIs(self.top(), screens.CaptureScreen)

    def test_idle_timeout(self):
        self.send(events.LONG_CLICK)
        self.app._last_input -= IDLE_TIMEOUT + 1
        self.app.tick()
        self.assertIs(self.top(), screens.CaptureScreen)

    def test_no_timeout_while_playing(self):
        videos = self.internal.videos_dir
        videos.mkdir(parents=True, exist_ok=True)
        (videos / "Sony_HVR-A1E-10-11-2026_14-22-01.m2t").write_bytes(b"x")
        self.send(events.CLICK)
        self.assertEqual(self.rows()[1], "10-11-2026 14:22")
        self.send(events.CLICK)
        self.assertIs(self.top(), screens.PlaybackScreen)
        self.assertEqual(self.rows()[0], "10-11 14:22   \x03\x04")
        self.assertTrue(self.rows()[1].startswith("\x02PLAY   "))
        self.app._last_input -= IDLE_TIMEOUT + 1
        self.app.tick()
        self.assertIs(self.top(), screens.PlaybackScreen)
        self.send(events.CLICK)  # pause
        self.assertTrue(self.rows()[1].startswith("\x01PAUSE  "))
        self.app._last_input -= IDLE_TIMEOUT + 1
        self.app.tick()
        self.assertIs(self.top(), screens.CaptureScreen)

    def test_long_press_in_playback_returns_to_list_then_home(self):
        videos = self.internal.videos_dir
        videos.mkdir(parents=True, exist_ok=True)
        (videos / "a-10-11-2026_14-22-01.dv").write_bytes(b"x")
        self.send(events.CLICK)
        self.send(events.CLICK)
        self.send(events.LONG_CLICK)
        self.assertIs(self.top(), screens.PlaybackListScreen)
        self.send(events.LONG_CLICK)
        self.assertIs(self.top(), screens.CaptureScreen)


class SettingsTests(AppTestCase):
    def open_item(self, label):
        self.send(events.LONG_CLICK)
        while self.rows()[1].strip() != label:
            self.send(events.SCROLL_RIGHT)
        self.send(events.CLICK)

    def test_range_updates_live(self):
        self.open_item("LCD Brightness")
        self.assertEqual(self.rows(), ["LCD Brightness  ", "\xff" * 8 + " " * 8])
        self.send(events.SCROLL_RIGHT)
        self.assertEqual(self.backlight.brightness, 9)
        self.assertEqual(self.rows()[1], "\xff" * 9 + " " * 7)
        for _ in range(20):
            self.send(events.SCROLL_LEFT)
        self.assertEqual(config.get("lcd_brightness"), 1)  # brightness never goes fully dark
        self.send(events.CLICK)
        self.assertIs(self.top(), screens.SettingsRootScreen)

    def test_long_press_on_range_goes_home(self):
        self.open_item("LCD Contrast")
        self.send(events.LONG_CLICK)
        self.assertIs(self.top(), screens.CaptureScreen)

    def test_record_mode_saved_on_click_only(self):
        self.connect()
        self.status("STBY")
        self.open_item("Record Mode")
        self.assertEqual(self.rows()[1].strip(), "< Auto >")
        self.send(events.SCROLL_RIGHT)
        self.assertEqual(config.get("record_mode"), "auto")
        self.send(events.CLICK)
        self.assertEqual(config.get("record_mode"), "standalone")
        self.assertEqual(self.capture.started[-1][2], "standalone")

    def test_factory_reset_defaults_to_no(self):
        self.open_item("Factory Reset")
        self.assertEqual(self.rows(), ["Are you sure?   ", "No              "])
        self.send(events.CLICK)
        self.assertFalse(self.system.reset)
        self.assertIs(self.top(), screens.SettingsRootScreen)
        self.send(events.CLICK)
        self.send(events.SCROLL_RIGHT)
        self.send(events.CLICK)
        self.assertTrue(self.system.reset)


class RecordModeTests(AppTestCase):
    def test_standalone_button_toggles(self):
        config.set("record_mode", "standalone")
        self.connect()
        self.send(events.RECORD_BUTTON)
        self.assertTrue(self.capture.armed)
        self.send(events.RECORD_BUTTON)  # within 1 s lockout: ignored
        self.assertTrue(self.capture.armed)
        self.app._last_record_press -= 2
        self.send(events.RECORD_BUTTON)
        self.assertFalse(self.capture.armed)

    def test_button_ignored_in_auto_mode(self):
        self.connect()
        self.send(events.RECORD_BUTTON)
        self.assertEqual(self.capture.armed_calls, [])

    def test_lanc_level(self):
        config.set("record_mode", "lanc")
        self.lanc.high = True
        self.connect()
        self.assertTrue(self.capture.armed)  # applied on ready
        self.send(events.LANC_LEVEL, high=False)
        self.assertFalse(self.capture.armed)
        self.lanc.high = True
        self.app._last_lanc_check = 0
        self.app.tick()  # periodic re-check catches a missed edge
        self.assertTrue(self.capture.armed)


class StorageTests(AppTestCase):
    def test_usb_added_without_camera_switches(self):
        self.send(events.STORAGE_CHANGED, locations=[self.usb, self.internal])
        self.assertEqual(self.app.storage, self.usb)
        self.assertEqual(self.app.lcd.slot_name(3), "usb")

    def test_usb_added_with_camera_asks_yes(self):
        self.connect()
        self.status("STBY")
        self.send(events.STORAGE_CHANGED, locations=[self.usb, self.internal])
        self.assertIs(self.top(), screens.ConfirmScreen)
        self.assertEqual(self.rows(), ["USB Found       ", "Switch? No      "])
        self.send(events.SCROLL_RIGHT)
        self.send(events.CLICK)
        self.assertEqual(self.app.storage, self.usb)
        self.assertEqual(self.capture.started[-1][1], self.usb)
        self.assertIs(self.top(), screens.CaptureScreen)

    def test_usb_added_with_camera_no_then_switch_when_unplugged(self):
        self.connect()
        self.status("STBY")
        self.send(events.STORAGE_CHANGED, locations=[self.usb, self.internal])
        self.send(events.CLICK)  # No
        self.assertEqual(self.app.storage, self.internal)
        self.app.tick()
        self.assertIs(self.top(), screens.CaptureScreen)  # not asked again
        self.send(events.DEVICE_REMOVED, device=self.camera)
        self.assertEqual(self.app.storage, self.usb)

    def test_prompt_timeout_counts_as_no(self):
        self.connect()
        self.status("STBY")
        self.send(events.STORAGE_CHANGED, locations=[self.usb, self.internal])
        self.app._last_input -= IDLE_TIMEOUT + 1
        self.app.tick()
        self.assertIs(self.top(), screens.CaptureScreen)
        self.app.tick()
        self.assertIs(self.top(), screens.CaptureScreen)
        self.assertEqual(self.app.storage, self.internal)

    def test_usb_added_while_recording_asks_at_stby(self):
        self.connect()
        self.status("REC")
        self.send(events.STORAGE_CHANGED, locations=[self.usb, self.internal])
        self.assertIs(self.top(), screens.CaptureScreen)
        self.assertEqual(self.app.storage, self.internal)
        self.status("STBY")
        self.assertIs(self.top(), screens.ConfirmScreen)

    def test_prompt_closed_by_recording_is_asked_again(self):
        self.connect()
        self.status("STBY")
        self.send(events.STORAGE_CHANGED, locations=[self.usb, self.internal])
        self.status("REC")
        self.assertIs(self.top(), screens.CaptureScreen)
        self.status("STBY")
        self.assertIs(self.top(), screens.ConfirmScreen)

    def test_removing_storage_in_use_stops_recording(self):
        self.send(events.STORAGE_CHANGED, locations=[self.usb, self.internal])
        self.connect()
        self.status("REC")
        starts = len(self.capture.started)
        self.send(events.STORAGE_CHANGED, locations=[self.internal])
        self.assertEqual(self.app.storage, self.internal)
        self.assertEqual(self.monitor.released, [self.usb])
        self.assertEqual(len(self.capture.started), starts + 1)
        self.assertEqual(self.capture.started[-1][1], self.internal)

    def test_unsupported_usb_is_announced(self):
        bad = StorageLocation("usb", self.tmp / "usb" / "Videos", "ntfs", "/dev/sda1", supported=False)
        self.send(events.STORAGE_CHANGED, locations=[bad, self.internal])
        self.assertEqual(self.rows()[0], "USB Not Supporte")
        self.assertEqual(self.app.storage, self.internal)


if __name__ == "__main__":
    unittest.main()
