"""Rotary encoder -> SCROLL_LEFT / SCROLL_RIGHT / CLICK / LONG_CLICK events.

LONG_CLICK fires as soon as the button has been held for 2 s (the user doesn't
need to let go). The release after a long click does not produce a CLICK.
"""

from dte import events, pins

LONG_PRESS_SECONDS = 2.0
# Swap if the encoder is wired so that clockwise reads as left.
REVERSE_DIRECTION = False


class Encoder(object):
    def __init__(self, bus):
        from gpiozero import Button, RotaryEncoder

        self._bus = bus
        self._held = False
        self._rotary = RotaryEncoder(pins.ENCODER_A, pins.ENCODER_B, max_steps=0)
        right, left = events.SCROLL_RIGHT, events.SCROLL_LEFT
        if REVERSE_DIRECTION:
            right, left = left, right
        self._rotary.when_rotated_clockwise = lambda: bus.post(right)
        self._rotary.when_rotated_counter_clockwise = lambda: bus.post(left)

        self._button = Button(pins.ENCODER_SWITCH, pull_up=True, bounce_time=0.02,
                              hold_time=LONG_PRESS_SECONDS)
        self._button.when_pressed = self._pressed
        self._button.when_held = self._long
        self._button.when_released = self._released

    def _pressed(self):
        self._held = False

    def _long(self):
        self._held = True
        self._bus.post(events.LONG_CLICK)

    def _released(self):
        if not self._held:
            self._bus.post(events.CLICK)
        self._held = False

    def close(self):
        self._rotary.close()
        self._button.close()
