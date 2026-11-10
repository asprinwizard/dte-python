import unittest

from dte.hardware import glyphs
from dte.hardware.lcd import LCD, fit
from tests.helpers import RecordingDriver


class LcdTests(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(fit("abc", 5), "abc  ")
        self.assertEqual(fit("abcdefgh", 3), "abc")
        self.assertEqual(fit(None, 2), "  ")

    def test_only_changed_characters_are_written(self):
        driver = RecordingDriver()
        lcd = LCD(driver)
        lcd.show(["HDV Sony HVR-", "\x01STBY   00:45:12"])
        driver.writes[:] = []
        lcd.show(["HDV Sony HVR-", "\x01STBY   00:45:13"])
        self.assertEqual(driver.writes, [(1, 15, "3")])

    def test_glyph_loaded_once(self):
        driver = RecordingDriver()
        lcd = LCD(driver)
        self.assertEqual(sorted(driver.chars), [0, 1, 2])
        lcd.set_glyph(glyphs.SLOT_STORAGE, "usb")
        lcd.set_glyph(glyphs.SLOT_STORAGE, "usb")
        self.assertEqual(driver.chars[3], glyphs.GLYPHS["usb"])
        self.assertEqual(lcd.slot_name(3), "usb")

    def test_all_glyphs_are_lists_of_eight_rows(self):
        for name, pattern in glyphs.GLYPHS.items():
            self.assertIsInstance(pattern, list, name)
            self.assertEqual(len(pattern), 8, name)
            self.assertTrue(all(0 <= row < 32 for row in pattern), name)


if __name__ == "__main__":
    unittest.main()
