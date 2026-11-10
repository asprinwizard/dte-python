"""LCD brightness and contrast via the two hardware PWM channels.

Needs ``dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4`` in the boot config.
Config values run 0-16; the duty cycle is ``value / 16``.

Hardware notes:
- The contrast pin (V0) needs an RC low-pass filter after the PWM output, or
  the contrast flickers.
- On an HD44780 a *lower* V0 voltage gives *higher* contrast. If turning the
  encoder right makes the text fainter, set CONTRAST_INVERTED = True.
"""

import logging

from dte import pins

log = logging.getLogger(__name__)

MAX_LEVEL = 16
MIN_BRIGHTNESS = 1
BRIGHTNESS_HZ = 1000
CONTRAST_HZ = 10000
CONTRAST_INVERTED = False


def clamp(value, low=0, high=MAX_LEVEL):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = MAX_LEVEL // 2
    return max(low, min(high, value))


def brightness_duty(value):
    return clamp(value, MIN_BRIGHTNESS) * 100.0 / MAX_LEVEL


def contrast_duty(value):
    level = clamp(value)
    if CONTRAST_INVERTED:
        level = MAX_LEVEL - level
    return level * 100.0 / MAX_LEVEL


class Backlight(object):
    """Hardware PWM through rpi-hardware-pwm (sysfs)."""

    def __init__(self):
        from rpi_hardware_pwm import HardwarePWM

        self._brightness = HardwarePWM(pwm_channel=pins.PWM_BRIGHTNESS_CHANNEL, hz=BRIGHTNESS_HZ)
        self._contrast = HardwarePWM(pwm_channel=pins.PWM_CONTRAST_CHANNEL, hz=CONTRAST_HZ)
        self._brightness.start(0)
        self._contrast.start(0)

    def set_brightness(self, value):
        self._brightness.change_duty_cycle(brightness_duty(value))

    def set_contrast(self, value):
        self._contrast.change_duty_cycle(contrast_duty(value))

    def close(self):
        for pwm in (self._brightness, self._contrast):
            try:
                pwm.stop()
            except Exception:  # pragma: no cover
                log.exception("PWM stop failed")
