"""Battery monitor placeholder.

The battery hardware isn't decided yet, so this always reports "full". The
display already uses the level, so a real monitor can replace this class
without changes elsewhere.
"""

import threading

from dte import events


class BatteryMonitor(object):
    def __init__(self, bus, interval=60.0):
        self._bus = bus
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None

    def read_level(self):
        return "full"

    def _run(self):
        while not self._stop.is_set():
            self._bus.post(events.BATTERY_LEVEL, {"level": self.read_level()})
            self._stop.wait(self._interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="battery", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
