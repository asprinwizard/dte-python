"""The DTE recorder: main loop and state machine.

Background threads post events on the bus; ``run()`` takes them one at a time
on the main thread, updates state, and redraws the LCD. Nothing else touches
the display.
"""

import logging
import time

from dte import config, events
from dte.hardware import glyphs
from dte.services.storage import LOW_SPACE_BYTES, best_location
from dte.ui import recordings
from dte.ui.screens import CaptureScreen, ConfirmScreen

log = logging.getLogger(__name__)

IDLE_TIMEOUT = 15.0
TICK = 0.25
RESTART_DELAY = 2.0
MAX_FAILURES = 3
FAILURE_WINDOW = 60.0
WATCHDOG_TIMEOUT = 30.0
DISK_CHECK_INTERVAL = 5.0
RECORD_BUTTON_LOCKOUT = 1.0
TRANSIENT_SECONDS = 3.0


def _blank_capture_state():
    return {"status": "WAIT", "timecode": "--:--:--", "elapsed": "00:00:00", "format": None, "file": None}


class App(object):
    def __init__(self, bus, lcd, backlight, capture, firewire, storage_monitor, system,
                 lanc=None, record_light=None, battery=None, dvgrab_ok=True):
        self.bus = bus
        self.lcd = lcd
        self.backlight = backlight
        self.capture = capture
        self.firewire = firewire
        self.storage_monitor = storage_monitor
        self.system = system
        self.lanc = lanc
        self.record_light = record_light
        self.battery = battery
        self.dvgrab_ok = dvgrab_ok

        self.device = None
        self.locations = []
        self.storage = None
        self.declined = set()          # storage keys the user said No to
        self.capture_state = _blank_capture_state()
        self.capture_error = None if dvgrab_ok else "dvgrab outdated"
        self.storage_full = False
        self.battery_level = "full"
        self.screens = [CaptureScreen(self)]
        self.transient = None          # (rows, expires_at)
        self.running = False

        self._last_input = time.monotonic()
        self._restart_at = None
        self._failures = []
        self._last_disk_check = 0.0
        self._last_lanc_check = 0.0
        self._last_record_press = 0.0
        self._announced_unsupported = set()

        config.add_listener(self._on_config_changed)

    # ------------------------------------------------------------ main loop

    def run(self):
        self.running = True
        self.apply_backlight()
        self.render()
        while self.running:
            event = self.bus.get(timeout=TICK)
            if event is not None:
                try:
                    self.handle(event)
                except Exception:
                    log.exception("Error handling %r", event)
            try:
                self.tick()
            except Exception:
                log.exception("Error in tick")
            self.render()
        self.shutdown()

    def shutdown(self):
        config.flush()
        self.capture.stop()
        if self.record_light:
            self.record_light.set(False)

    def handle(self, event):
        handler = getattr(self, "_on_" + event.type, None)
        if event.type in events.INPUT_EVENTS:
            self._on_input(event)
        elif handler:
            handler(event)

    # --------------------------------------------------------------- render

    def render(self):
        storage_kind = self.storage.kind if self.storage else "internal"
        self.lcd.set_glyph(glyphs.SLOT_STORAGE, glyphs.STORAGE_GLYPH[storage_kind])
        self.lcd.set_glyph(glyphs.SLOT_BATTERY, glyphs.BATTERY_GLYPH.get(self.battery_level, "battery_full"))
        if self.transient and time.monotonic() < self.transient[1]:
            rows = self.transient[0]
        else:
            self.transient = None
            rows = self.screens[-1].render()
        self.lcd.show(rows)

    def show_now(self, rows):
        """Draw a message immediately (used before slow operations)."""
        self.lcd.show(rows)

    def flash(self, rows, seconds=TRANSIENT_SECONDS):
        self.transient = (rows, time.monotonic() + seconds)

    # ----------------------------------------------------------- navigation

    @property
    def top(self):
        return self.screens[-1]

    def open(self, screen):
        self.screens.append(screen)

    def back(self):
        if len(self.screens) > 1:
            self.screens.pop()

    def go_home(self, reason="user"):
        while len(self.screens) > 1:
            self.screens.pop().on_abandon(reason)

    def can_open_menus(self):
        """The button only works with no device connected, or in STBY."""
        return self.device is None or self.capture_state.get("status") != "REC"

    def list_recordings(self):
        if self.storage is None:
            return []
        return recordings.list_recordings(self.storage.videos_dir)

    def run_action(self, action):
        if action == "factory_reset":
            self.show_now(["Resetting...", ""])
            self.capture.stop()
            self.system.factory_reset()
        else:
            log.error("Unknown action %s", action)
            self.back()

    # --------------------------------------------------------------- input

    def _on_input(self, event):
        self._last_input = time.monotonic()
        if self.transient:
            self.transient = None
        screen = self.top
        if event.type == events.SCROLL_LEFT:
            screen.on_scroll(-1)
        elif event.type == events.SCROLL_RIGHT:
            screen.on_scroll(1)
        elif event.type == events.CLICK:
            screen.on_click()
        elif event.type == events.LONG_CLICK:
            screen.on_long_click()

    def _on_quit(self, event):
        self.running = False

    # -------------------------------------------------------------- devices

    def _on_device_connected(self, event):
        self.device = event.data["device"]
        log.info("Using device %r (prefix %s)", self.device, self.device.file_prefix)
        self.capture_error = None if self.dvgrab_ok else "dvgrab outdated"
        self._failures = []
        self.start_capture()

    def _on_device_removed(self, event):
        self.show_now(["Please Wait", ""])
        self.capture.stop()
        self.device = None
        self.capture_state = _blank_capture_state()
        self._restart_at = None
        self._set_light(False)
        # With no camera connected, switch to better storage without asking.
        best = best_location(self.locations)
        if best is not None and best != self.storage:
            self.switch_storage(best)
        self.go_home("device_removed")

    # -------------------------------------------------------------- storage

    def _on_storage_changed(self, event):
        self.locations = event.data["locations"]
        present = {loc.key for loc in self.locations}
        self.declined &= present

        for loc in self.locations:
            if not loc.supported and loc.key not in self._announced_unsupported:
                self._announced_unsupported.add(loc.key)
                self.flash(["USB Not Supported", "Using " + (self.storage.display_name if self.storage else "Internal")])
        self._announced_unsupported &= present

        best = best_location(self.locations)
        if best is None:
            return
        if self.storage is None or self.storage not in self.locations:
            # First start, or the storage in use was removed: switch now,
            # even mid-recording.
            old = self.storage
            self.switch_storage(best, removed=old)
        elif best != self.storage and self.device is None:
            self.switch_storage(best)
        # Otherwise a camera is connected: tick() asks the user at STBY.

    def switch_storage(self, location, removed=None):
        log.info("Switching storage to %r", location)
        self.show_now(["Please Wait", ""])
        was_capturing = self.capture.running or self.device is not None
        self.capture.stop()
        if removed is not None:
            self.storage_monitor.release(removed)
        self.storage = location
        self.storage_full = False
        try:
            location.ensure_videos_dir()
        except OSError as exc:
            log.error("Can't create %s: %s", location.videos_dir, exc)
        self.capture_state = _blank_capture_state()
        if was_capturing and self.device is not None:
            self.start_capture()

    def _better_storage_waiting(self):
        best = best_location(self.locations)
        return (best is not None and self.storage is not None and best != self.storage
                and best.key not in self.declined)

    def _ask_to_switch(self):
        best = best_location(self.locations)

        def yes():
            self.go_home("answered")
            self.switch_storage(best)

        def no():
            self.declined.add(best.key)
            self.back()

        def abandoned(reason):
            # Timed out or long-pressed: treat as No. If the camera started
            # recording, ask again at the next STBY.
            if reason != "recording":
                self.declined.add(best.key)

        self.open(ConfirmScreen(self, fit_title(best.display_name + " Found"), yes, no,
                                prefix="Switch? ", on_abandoned=abandoned))
        self._last_input = time.monotonic()

    # -------------------------------------------------------------- capture

    def record_mode(self):
        return config.get("record_mode", "auto")

    def start_capture(self):
        self._restart_at = None
        self.capture_state = _blank_capture_state()
        if self.device is None or self.storage is None or not self.dvgrab_ok or self.storage_full:
            return
        try:
            self.storage.ensure_videos_dir()
            self.capture.start(self.device, self.storage, self.record_mode())
        except OSError as exc:
            log.error("Couldn't start dvgrab: %s", exc)
            self.capture_error = "Capture Error"

    def _current(self, event):
        return event.data.get("_gen") == self.capture.generation

    def _on_capture_ready(self, event):
        if not self._current(event):
            return
        self.capture_state["format"] = event.data.get("format")
        if self.record_mode() == "lanc" and self.lanc is not None:
            self.capture.set_armed(self.lanc.is_high())

    def _on_capture_status(self, event):
        if not self._current(event):
            return
        data = event.data
        for key in ("status", "timecode", "elapsed", "format", "file"):
            if key in data and data[key] is not None:
                self.capture_state[key] = data[key]
        recording = data.get("status") == "REC"
        self._set_light(recording)
        if recording:
            self.capture_error = None
            if len(self.screens) > 1:
                self.go_home("recording")

    def _on_capture_file(self, event):
        if self._current(event):
            log.info("dvgrab %s: %s", event.data.get("type"), event.data.get("file"))

    def _on_capture_warning(self, event):
        if self._current(event):
            log.warning("dvgrab warning: %s", event.data.get("message"))

    def _on_capture_error(self, event):
        if not self._current(event):
            return
        log.error("dvgrab error: %s", event.data)
        if event.data.get("code") == "write_failed" and self.storage is not None:
            if self.storage.free_bytes() < LOW_SPACE_BYTES:
                self.storage_full = True

    def _on_capture_exited(self, event):
        if not self._current(event):
            return
        log.warning("dvgrab exited unexpectedly (%s)", event.data.get("returncode"))
        self._set_light(False)
        self.capture_state = _blank_capture_state()
        self._note_failure()

    def _note_failure(self):
        now = time.monotonic()
        self._failures = [t for t in self._failures if now - t < FAILURE_WINDOW] + [now]
        if self.device is None or self.storage_full:
            return
        if len(self._failures) >= MAX_FAILURES:
            log.error("dvgrab keeps failing; giving up until the device is reconnected")
            self.capture_error = "Capture Error"
            self.capture.stop()
            return
        self._restart_at = now + RESTART_DELAY

    def _set_light(self, on):
        if self.record_light:
            self.record_light.set(on)

    # ------------------------------------------------------- record trigger

    def _on_record_button(self, event):
        if self.record_mode() != "standalone" or self.device is None or not self.capture.ready:
            return
        now = time.monotonic()
        if now - self._last_record_press < RECORD_BUTTON_LOCKOUT:
            return
        self._last_record_press = now
        self.capture.set_armed(not self.capture.armed)

    def _on_lanc_level(self, event):
        if self.record_mode() == "lanc" and self.device is not None:
            self.capture.set_armed(event.data["high"])

    # --------------------------------------------------------------- other

    def _on_battery_level(self, event):
        self.battery_level = event.data.get("level", "full")

    def apply_backlight(self):
        self.backlight.set_brightness(config.get("lcd_brightness", 8))
        self.backlight.set_contrast(config.get("lcd_contrast", 8))

    def _on_config_changed(self, key, value):
        # Called on the main thread (from a screen handler).
        if key == "lcd_brightness":
            self.backlight.set_brightness(value)
        elif key == "lcd_contrast":
            self.backlight.set_contrast(value)
        elif key == "record_mode":
            log.info("Record mode is now %s", value)
            if self.device is not None:
                self.show_now(["Please Wait", ""])
                self.start_capture()

    # ---------------------------------------------------------------- tick

    def tick(self):
        now = time.monotonic()

        if (len(self.screens) > 1 and self.top.allows_idle_timeout()
                and now - self._last_input > IDLE_TIMEOUT):
            self.go_home("timeout")

        if self._restart_at is not None and now >= self._restart_at:
            self._restart_at = None
            log.info("Restarting dvgrab")
            self.start_capture()

        if self.capture.running:
            if now - self.capture.last_output > WATCHDOG_TIMEOUT:
                log.error("No output from dvgrab for %ss; restarting it", WATCHDOG_TIMEOUT)
                self.capture.stop()
                self._note_failure()
            elif now - self._last_disk_check > DISK_CHECK_INTERVAL and self.storage is not None:
                self._last_disk_check = now
                if self.storage.free_bytes() < LOW_SPACE_BYTES:
                    log.error("Storage full: %s", self.storage)
                    self.storage_full = True
                    self.capture.stop()
                    self._set_light(False)
                    self.capture_state = _blank_capture_state()

        if (self.record_mode() == "lanc" and self.lanc is not None and self.device is not None
                and now - self._last_lanc_check >= 1.0):
            self._last_lanc_check = now
            self.capture.set_armed(self.lanc.is_high())

        if (self.device is not None and self.capture_state.get("status") != "REC"
                and len(self.screens) == 1 and self.transient is None
                and self._better_storage_waiting()):
            self._ask_to_switch()


def fit_title(text):
    return text[:16]
