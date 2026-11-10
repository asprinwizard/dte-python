import os
import shutil
import tempfile
import unittest
from pathlib import Path

from dte import config, paths


class TempEnvTestCase(unittest.TestCase):
    """Points every DTE path at a fresh temp directory."""

    ENV_KEYS = ("DTE_HOME", "DTE_INTERNAL_VIDEOS", "DTE_DEFAULT_CONFIG", "DTE_FIREWIRE_SYSFS",
                "DTE_USB_MOUNT", "DTE_DVGRAB", "DTE_FAKE_CAMERA_STATE", "DTE_FAKE_HDV_GUIDS")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dte-test-"))
        self._saved = {k: os.environ.get(k) for k in self.ENV_KEYS}
        os.environ["DTE_HOME"] = str(self.tmp / "home" / ".dte")
        os.environ["DTE_INTERNAL_VIDEOS"] = str(self.tmp / "home" / "Videos")
        defaults = self.tmp / "config.json"
        shutil.copy(str(paths.PROJECT_ROOT / "config.json"), str(defaults))
        os.environ["DTE_DEFAULT_CONFIG"] = str(defaults)
        config._listeners[:] = []
        config.load()

    def tearDown(self):
        config.flush()
        config._listeners[:] = []
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(str(self.tmp), ignore_errors=True)


class RecordingDriver(object):
    """LCD driver that remembers what is on screen."""

    def __init__(self):
        self.grid = [[" "] * 16 for _ in range(2)]
        self.chars = {}
        self.writes = []

    def create_char(self, slot, pattern):
        self.chars[slot] = list(pattern)

    def write(self, row, col, text):
        self.writes.append((row, col, text))
        for i, ch in enumerate(text):
            self.grid[row][col + i] = ch

    def rows(self):
        return ["".join(r) for r in self.grid]

    def close(self):
        pass
