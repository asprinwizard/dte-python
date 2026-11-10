"""Screens.

Each screen returns two 16-character rows from ``render()`` and reacts to the
encoder through ``on_scroll(step)``, ``on_click()`` and ``on_long_click()``.
Templates differ in *which* event does the work: a range screen acts on
scroll, a confirm screen acts on click.

``on_abandon(reason)`` is called when the app leaves a screen without the
user choosing to: ``"timeout"`` (15 s idle) or ``"recording"`` (the camera
started recording).
"""

import time

from dte import config
from dte.hardware import glyphs
from dte.hardware.lcd import fit
from dte.ui import recordings
from dte.ui.settings_menu import SETTINGS


class Screen(object):
    #: Whether the 15 s idle timeout returns to the capture screen.
    idle_timeout = True

    def __init__(self, app):
        self.app = app

    def render(self):
        return ["", ""]

    def on_scroll(self, step):
        pass

    def on_click(self):
        pass

    def on_long_click(self):
        self.app.go_home()

    def on_abandon(self, reason):
        pass

    def allows_idle_timeout(self):
        return self.idle_timeout


def status_icons():
    """Columns 15-16: storage and battery glyphs."""
    return glyphs.STORAGE + glyphs.BATTERY


class CaptureScreen(Screen):
    """Default screen. Shows "No Device Found" when no camera is connected."""

    idle_timeout = False

    def render(self):
        app = self.app
        if app.device is None:
            return ["No Device Found", " " * 14 + status_icons()]
        cap = app.capture_state
        fmt = fit(cap.get("format") or "", 3)
        row1 = fmt + " " + fit(app.device.lcd_name, 9) + " " + status_icons()
        if app.storage_full:
            return [row1, "Storage Full"]
        if app.capture_error:
            return [row1, fit(app.capture_error, 16)]
        recording = cap.get("status") == "REC"
        icon = glyphs.RECORD if recording else glyphs.PAUSE
        status = "REC" if recording else "STBY"
        timecode = cap.get("timecode") or "--:--:--"
        if timecode.startswith("--") and recording:
            timecode = cap.get("elapsed") or timecode
        return [row1, icon + fit(status, 6) + " " + fit(timecode, 8)]

    def on_click(self):
        if self.app.can_open_menus():
            self.app.open(PlaybackListScreen(self.app))

    def on_long_click(self):
        if self.app.can_open_menus():
            self.app.open(SettingsRootScreen(self.app))


class MessageScreen(Screen):
    def __init__(self, app, rows):
        Screen.__init__(self, app)
        self.rows = rows

    def render(self):
        return self.rows


# ----------------------------------------------------------------- playback

class PlaybackListScreen(Screen):
    def __init__(self, app):
        Screen.__init__(self, app)
        self.files = app.list_recordings()
        self.labels = recordings.labels(self.files, 16)
        self.index = 0

    def render(self):
        if not self.files:
            return ["Select File:", "No Files"]
        return ["Select File:", self.labels[self.index]]

    def on_scroll(self, step):
        if self.files:
            self.index = (self.index + step) % len(self.files)

    def on_click(self):
        if self.files:
            label = recordings.labels(self.files, 13)[self.index]
            self.app.open(PlaybackScreen(self.app, self.files[self.index], label))


class NullPlayer(object):
    """Playback output isn't decided yet (HDMI or FireWire). This keeps
    position only, so the screen and controls can be built now."""

    def __init__(self, recording):
        self.recording = recording
        self.playing = False
        self._position = 0.0
        self._started = None

    def play(self):
        if not self.playing:
            self.playing = True
            self._started = time.monotonic()

    def pause(self):
        if self.playing:
            self._position = self.position()
            self.playing = False
            self._started = None

    def stop(self):
        self.pause()

    def position(self):
        if self.playing and self._started is not None:
            return self._position + time.monotonic() - self._started
        return self._position


def hms(seconds):
    seconds = int(seconds)
    return "{:02d}:{:02d}:{:02d}".format(seconds // 3600 % 100, seconds // 60 % 60, seconds % 60)


class PlaybackScreen(Screen):
    def __init__(self, app, recording, label):
        Screen.__init__(self, app)
        self.label = label
        self.player = NullPlayer(recording)
        self.player.play()

    def allows_idle_timeout(self):
        return not self.player.playing

    def render(self):
        row1 = fit(self.label, 13) + " " + status_icons()
        if self.player.playing:
            row2 = glyphs.PLAY + fit("PLAY", 6)
        else:
            row2 = glyphs.PAUSE + fit("PAUSE", 6)
        return [row1, row2 + " " + hms(self.player.position())]

    def on_click(self):
        if self.player.playing:
            self.player.pause()
        else:
            self.player.play()

    def on_long_click(self):
        self.player.stop()
        self.app.back()

    def on_abandon(self, reason):
        self.player.stop()


# ----------------------------------------------------------------- settings

class SettingsRootScreen(Screen):
    def __init__(self, app):
        Screen.__init__(self, app)
        self.index = 0

    def render(self):
        return ["Settings", SETTINGS[self.index]["label"]]

    def on_scroll(self, step):
        self.index = (self.index + step) % len(SETTINGS)

    def on_click(self):
        item = SETTINGS[self.index]
        template = item["template"]
        if template == "range":
            self.app.open(RangeScreen(self.app, item))
        elif template == "options":
            self.app.open(OptionsScreen(self.app, item))
        elif template == "confirm":
            action = item["action"]
            self.app.open(ConfirmScreen(
                self.app, "Are you sure?",
                on_yes=lambda: self.app.run_action(action),
                on_no=self.app.back,
            ))


class RangeScreen(Screen):
    """Line 2 shows the value as solid blocks; scrolling saves it live."""

    def __init__(self, app, item):
        Screen.__init__(self, app)
        self.item = item

    def value(self):
        return int(config.get(self.item["key"], self.item["min"]))

    def render(self):
        value = max(0, min(16, self.value()))
        return [self.item["label"], glyphs.FULL_BLOCK * value]

    def on_scroll(self, step):
        value = max(self.item["min"], min(self.item["max"], self.value() + step))
        config.set(self.item["key"], value, debounce=True)

    def on_click(self):
        config.flush()
        self.app.back()

    def on_long_click(self):
        config.flush()
        self.app.go_home()


class OptionsScreen(Screen):
    """Scroll through choices; click saves (changing the record mode restarts
    dvgrab, so nothing happens until the user commits)."""

    def __init__(self, app, item):
        Screen.__init__(self, app)
        self.item = item
        values = [value for value, _ in item["options"]]
        current = config.get(item["key"])
        self.index = values.index(current) if current in values else 0

    def render(self):
        label = self.item["options"][self.index][1]
        return [self.item["label"], "< " + label + " >"]

    def on_scroll(self, step):
        self.index = (self.index + step) % len(self.item["options"])

    def on_click(self):
        config.set(self.item["key"], self.item["options"][self.index][0])
        self.app.back()


class ConfirmScreen(Screen):
    """Yes/No. Defaults to No so a double click can't confirm by mistake."""

    def __init__(self, app, title, on_yes, on_no, prefix="", on_abandoned=None):
        Screen.__init__(self, app)
        self.title = title
        self.prefix = prefix
        self.yes = False
        self._on_yes = on_yes
        self._on_no = on_no
        self._on_abandoned = on_abandoned

    def render(self):
        return [self.title, self.prefix + ("Yes" if self.yes else "No")]

    def on_scroll(self, step):
        self.yes = not self.yes

    def on_click(self):
        if self.yes:
            self._on_yes()
        else:
            self._on_no()

    def on_abandon(self, reason):
        if self._on_abandoned:
            self._on_abandoned(reason)
