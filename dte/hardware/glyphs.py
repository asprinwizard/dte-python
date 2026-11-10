"""5x8 custom characters for the HD44780 (from display/custom/chars/chars5x8.py,
with the tuple bug fixed and an internal-storage glyph added)."""

GLYPHS = {
    "record": [
        0b00000,
        0b00000,
        0b01110,
        0b11111,
        0b11111,
        0b11111,
        0b01110,
        0b00000,
    ],
    "pause": [
        0b00000,
        0b00000,
        0b01010,
        0b01010,
        0b01010,
        0b01010,
        0b01010,
        0b00000,
    ],
    "play": [
        0b00000,
        0b10000,
        0b11000,
        0b11100,
        0b11110,
        0b11100,
        0b11000,
        0b10000,
    ],
    "battery_full": [
        0b01110,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
    ],
    "battery_med": [
        0b01110,
        0b10001,
        0b10001,
        0b10001,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
    ],
    "battery_low": [
        0b01110,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b11111,
        0b11111,
    ],
    "battery_empty": [
        0b01110,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b11111,
    ],
    "sd": [
        0b00111,
        0b01111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
        0b11111,
    ],
    "usb": [
        0b01110,
        0b01110,
        0b11111,
        0b10001,
        0b10001,
        0b10001,
        0b10001,
        0b11111,
    ],
    # New: a chip outline for internal storage.
    "internal": [
        0b01010,
        0b11111,
        0b10001,
        0b10101,
        0b10001,
        0b11111,
        0b01010,
        0b00000,
    ],
}

# CGRAM slot plan. Slots 3 and 4 have their glyph swapped as state changes.
SLOT_RECORD = 0
SLOT_PAUSE = 1
SLOT_PLAY = 2
SLOT_STORAGE = 3
SLOT_BATTERY = 4

FIXED_SLOTS = {
    SLOT_RECORD: "record",
    SLOT_PAUSE: "pause",
    SLOT_PLAY: "play",
}

# Characters to put in display strings.
RECORD = chr(SLOT_RECORD)
PAUSE = chr(SLOT_PAUSE)
PLAY = chr(SLOT_PLAY)
STORAGE = chr(SLOT_STORAGE)
BATTERY = chr(SLOT_BATTERY)
FULL_BLOCK = "\xff"  # built into the HD44780 A00 character ROM

STORAGE_GLYPH = {"sd": "sd", "usb": "usb", "internal": "internal"}
BATTERY_GLYPH = {
    "full": "battery_full",
    "med": "battery_med",
    "low": "battery_low",
    "empty": "battery_empty",
}
