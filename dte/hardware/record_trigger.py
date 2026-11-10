"""Record control inputs and the optional tally light.

- Standalone: a push button on GPIO6. Each press posts RECORD_BUTTON; the app
  toggles between armed and disarmed.
- LANC: the Arduino holds GPIO16 HIGH while recording. Edges post LANC_LEVEL,
  and ``is_high()`` lets the app re-check the level periodically so a missed
  edge can't leave things out of step. The Arduino is 5 V: use a level shifter.
"""

from dte import events, pins


class RecordButton(object):
    def __init__(self, bus):
        from gpiozero import Button

        self._button = Button(pins.RECORD_BUTTON, pull_up=True, bounce_time=0.05)
        self._button.when_pressed = lambda: bus.post(events.RECORD_BUTTON)

    def close(self):
        self._button.close()


class LancInput(object):
    def __init__(self, bus):
        from gpiozero import DigitalInputDevice

        # Pull-down: a disconnected Arduino reads as standby.
        self._input = DigitalInputDevice(pins.LANC_INPUT, pull_up=False, bounce_time=0.05)
        self._input.when_activated = lambda: bus.post(events.LANC_LEVEL, {"high": True})
        self._input.when_deactivated = lambda: bus.post(events.LANC_LEVEL, {"high": False})

    def is_high(self):
        return bool(self._input.value)

    def close(self):
        self._input.close()


class RecordLight(object):
    def __init__(self):
        from gpiozero import LED

        self._led = LED(pins.RECORD_LED)

    def set(self, on):
        if on:
            self._led.on()
        else:
            self._led.off()

    def close(self):
        self._led.close()
