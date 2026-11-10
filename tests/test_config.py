import json
import time
import unittest

from dte import config, paths
from tests.helpers import TempEnvTestCase


class ConfigTests(TempEnvTestCase):
    def test_creates_user_file_from_defaults(self):
        user = paths.user_config_file()
        self.assertTrue(user.exists())
        self.assertEqual(json.loads(user.read_text())["lcd_brightness"], 8)
        self.assertEqual(config.get("record_mode"), "auto")

    def test_adds_new_default_keys_and_keeps_user_values(self):
        paths.user_config_file().write_text(json.dumps({"lcd_brightness": 3}))
        config.load()
        self.assertEqual(config.get("lcd_brightness"), 3)
        self.assertEqual(config.get("lcd_contrast"), 8)
        saved = json.loads(paths.user_config_file().read_text())
        self.assertEqual(saved, {"lcd_brightness": 3, "lcd_contrast": 8, "record_mode": "auto"})

    def test_corrupt_user_file_is_recreated(self):
        paths.user_config_file().write_text("{not json")
        config.load()
        self.assertEqual(config.get("lcd_brightness"), 8)

    def test_set_writes_immediately(self):
        config.set("lcd_contrast", 12)
        self.assertEqual(json.loads(paths.user_config_file().read_text())["lcd_contrast"], 12)

    def test_debounced_set_writes_later(self):
        config.set("lcd_brightness", 10, debounce=True)
        self.assertEqual(config.get("lcd_brightness"), 10)
        self.assertEqual(json.loads(paths.user_config_file().read_text())["lcd_brightness"], 8)
        time.sleep(config.DEBOUNCE_SECONDS + 0.2)
        self.assertEqual(json.loads(paths.user_config_file().read_text())["lcd_brightness"], 10)

    def test_listener_called(self):
        seen = []
        config.add_listener(lambda k, v: seen.append((k, v)))
        config.set("lcd_brightness", 4)
        config.set("lcd_brightness", 4)  # unchanged: no second call
        self.assertEqual(seen, [("lcd_brightness", 4)])

    def test_delete_user_file_then_reload_gives_defaults(self):
        config.set("lcd_brightness", 2)
        config.delete_user_file()
        self.assertFalse(paths.user_config_file().exists())
        config.load()
        self.assertEqual(config.get("lcd_brightness"), 8)

    def test_no_temp_files_left(self):
        config.set("lcd_brightness", 5)
        leftovers = [p.name for p in paths.data_dir().iterdir() if p.name.startswith(".config-")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
