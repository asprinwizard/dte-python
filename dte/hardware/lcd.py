"""16x2 character LCD with a frame buffer.

Screens produce two 16-character strings. ``LCD.show`` compares them with
what is already on the display and only writes the characters that changed,
which keeps timecode updates free of flicker.

Characters ``\\x00``-``\\x07`` are the custom glyph slots and ``\\xff`` is the
ROM full block. A driver must write those as raw bytes.
"""

import logging

from dte.hardware import glyphs

log = logging.getLogger(__name__)

ROWS = 2
COLS = 16


def fit(text, width=COLS):
    """Pad or cut ``text`` to exactly ``width`` characters."""
    text = "" if text is None else str(text)
    return text[:width].ljust(width)


class LCD(object):
    def __init__(self, driver):
        self.driver = driver
        self._shown = [None] * ROWS
        self._slots = {}
        for slot, name in glyphs.FIXED_SLOTS.items():
            self.set_glyph(slot, name)

    def set_glyph(self, slot, name):
        """Load glyph ``name`` into CGRAM ``slot`` if it isn't there already."""
        if self._slots.get(slot) == name:
            return
        self.driver.create_char(slot, glyphs.GLYPHS[name])
        self._slots[slot] = name

    def slot_name(self, slot):
        return self._slots.get(slot)

    def show(self, rows):
        rows = [fit(rows[i] if i < len(rows) else "") for i in range(ROWS)]
        for row, text in enumerate(rows):
            old = self._shown[row]
            if old is None:
                self.driver.write(row, 0, text)
            else:
                for col, chunk in _changed_runs(old, text):
                    self.driver.write(row, col, chunk)
            self._shown[row] = text

    def current(self):
        return list(self._shown)

    def clear(self):
        self.show(["", ""])

    def close(self):
        self.driver.close()


def _changed_runs(old, new):
    """Yield (column, text) for each run of characters that differ."""
    col = 0
    while col < len(new):
        if old[col] == new[col]:
            col += 1
            continue
        start = col
        while col < len(new) and old[col] != new[col]:
            col += 1
        yield start, new[start:col]


class RPLCDDriver(object):
    """HD44780 in 4-bit GPIO mode through RPLCD (which uses RPi.GPIO)."""

    def __init__(self, pins):
        import RPi.GPIO as GPIO  # noqa: N814 - library naming
        from RPLCD.gpio import CharLCD

        self._lcd = CharLCD(
            numbering_mode=GPIO.BCM,
            cols=COLS,
            rows=ROWS,
            pin_rs=pins.LCD_RS,
            pin_rw=None,
            pin_e=pins.LCD_EN,
            pins_data=[pins.LCD_D4, pins.LCD_D5, pins.LCD_D6, pins.LCD_D7],
            charmap="A00",
            auto_linebreaks=False,
            compat_mode=True,
        )
        self._lcd.clear()

    def create_char(self, slot, pattern):
        self._lcd.create_char(slot, tuple(pattern))

    def write(self, row, col, text):
        self._lcd.cursor_pos = (row, col)
        for ch in text:
            code = ord(ch)
            if code < 8 or code == 0xFF:
                self._lcd.write(code)
            else:
                self._lcd.write_string(ch)

    def close(self):
        try:
            self._lcd.close(clear=True)
        except Exception:  # pragma: no cover - best effort on shutdown
            log.exception("LCD close failed")
