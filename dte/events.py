"""Events passed from background threads to the main loop.

Background threads (monitors, GPIO callbacks, dvgrab readers) never touch the
display or app state directly. They put an ``Event`` on the shared queue and
the main loop handles it.
"""

import queue
import time

# Input (rotary encoder)
SCROLL_LEFT = "scroll_left"
SCROLL_RIGHT = "scroll_right"
CLICK = "click"
LONG_CLICK = "long_click"

# Record trigger
RECORD_BUTTON = "record_button"      # standalone button pressed
LANC_LEVEL = "lanc_level"            # data: {"high": bool}

# FireWire
DEVICE_CONNECTED = "device_connected"  # data: {"device": Device}
DEVICE_REMOVED = "device_removed"      # data: {"device": Device}

# Storage
STORAGE_CHANGED = "storage_changed"    # data: {"locations": [StorageLocation]}

# dvgrab
CAPTURE_READY = "capture_ready"        # data: dvgrab "ready" object
CAPTURE_STATUS = "capture_status"      # data: dvgrab "status" object
CAPTURE_FILE = "capture_file"          # data: dvgrab "file_open"/"file_closed" object
CAPTURE_WARNING = "capture_warning"
CAPTURE_ERROR = "capture_error"
CAPTURE_EXITED = "capture_exited"      # data: {"returncode": int}

# Other
BATTERY_LEVEL = "battery_level"        # data: {"level": "full"|"med"|"low"|"empty"}
QUIT = "quit"

INPUT_EVENTS = (SCROLL_LEFT, SCROLL_RIGHT, CLICK, LONG_CLICK)


class Event(object):
    __slots__ = ("type", "data", "time")

    def __init__(self, type_, data=None):
        self.type = type_
        self.data = data or {}
        self.time = time.monotonic()

    def __repr__(self):
        return "Event({!r}, {!r})".format(self.type, self.data)


class EventBus(object):
    """Thin wrapper round a thread-safe queue."""

    def __init__(self):
        self._queue = queue.Queue()

    def post(self, type_, data=None):
        self._queue.put(Event(type_, data))

    def get(self, timeout=None):
        """Return the next event, or None if ``timeout`` passes first."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
