"""The simulated outside world: cameras, USB drive, LANC level, camera REC."""

import os
import shutil
import threading
from pathlib import Path

from dte.services.storage import SUPPORTED_FS, StorageLocation

CAMERAS = {
    "fw1": {"guid": "0x080046010412abcd", "vendor_name": "Sony", "model_name": "HVR-A1E", "format": "HDV"},
    "fw2": {"guid": "0x0000850000e01234", "vendor_name": "Canon", "model_name": "XM2", "format": "DV"},
    "fw3": {"guid": "0x00000000deadbeef", "format": "DV"},  # no vendor/model -> dte-capture
}
USB_FS_LABEL = {"exfat": "exFAT", "vfat": "FAT32", "ntfs": "NTFS"}


class SimWorld(object):
    def __init__(self, root):
        self.root = Path(root)
        self.sysfs = self.root / "sysfs"
        self.usb_dir = self.root / "usb"
        self.camera_state_file = self.root / "camera_state"
        self.usb_fs = None
        self.lanc_high = False
        self.brightness = None
        self.contrast = None
        self.light = False
        self._lock = threading.Lock()
        self._listeners = []

        if self.sysfs.exists():
            shutil.rmtree(str(self.sysfs))
        local = self.sysfs / "fw0"
        local.mkdir(parents=True)
        (local / "is_local").write_text("1\n")
        (local / "guid").write_text("0x0011060000000001\n")
        self.set_camera_recording(False)

    def env(self):
        """Environment for paths and the fake dvgrab."""
        hdv = ",".join(c["guid"] for c in CAMERAS.values() if c["format"] == "HDV")
        return {
            "DTE_HOME": str(self.root / "home" / ".dte"),
            "DTE_INTERNAL_VIDEOS": str(self.root / "home" / "Videos"),
            "DTE_FIREWIRE_SYSFS": str(self.sysfs),
            "DTE_USB_MOUNT": str(self.usb_dir),
            "DTE_DVGRAB": str(Path(__file__).with_name("fake_dvgrab.py")),
            "DTE_FAKE_CAMERA_STATE": str(self.camera_state_file),
            "DTE_FAKE_HDV_GUIDS": hdv,
        }

    def on_change(self, callback):
        self._listeners.append(callback)

    def _changed(self):
        for callback in self._listeners:
            callback()

    # cameras -----------------------------------------------------------

    def camera_connected(self, node):
        return (self.sysfs / node).exists()

    def toggle_camera(self, node):
        path = self.sysfs / node
        if path.exists():
            shutil.rmtree(str(path))
        else:
            info = CAMERAS[node]
            path.mkdir(parents=True)
            (path / "is_local").write_text("0\n")
            (path / "guid").write_text(info["guid"] + "\n")
            unit = self.sysfs / (node + ".0")
            unit.mkdir(exist_ok=True)
            # Like many Sony cameras, the names live in the unit directory.
            for key in ("vendor_name", "model_name"):
                if key in info:
                    (unit / key).write_text(info[key] + "\n")
            path.joinpath("units").write_text("0x00a02d:0x010001\n")
        if not path.exists():
            unit = self.sysfs / (node + ".0")
            if unit.exists():
                shutil.rmtree(str(unit))
        self._changed()

    def connected_cameras(self):
        return [n for n in sorted(CAMERAS) if self.camera_connected(n)]

    def camera_recording(self):
        try:
            return self.camera_state_file.read_text().strip() == "REC"
        except OSError:
            return False

    def set_camera_recording(self, recording):
        self.camera_state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.camera_state_file.with_suffix(".tmp")
        tmp.write_text("REC\n" if recording else "STBY\n")
        os.replace(str(tmp), str(self.camera_state_file))
        self._changed()

    def toggle_camera_recording(self):
        self.set_camera_recording(not self.camera_recording())

    # usb ---------------------------------------------------------------

    def toggle_usb(self, fstype):
        with self._lock:
            self.usb_fs = None if self.usb_fs == fstype else fstype
        self._changed()

    # lanc --------------------------------------------------------------

    def toggle_lanc(self):
        self.lanc_high = not self.lanc_high
        self._changed()
        return self.lanc_high


class SimUsbBackend(object):
    def __init__(self, world):
        self._world = world

    def scan(self):
        fstype = self._world.usb_fs
        if fstype is None:
            return []
        return [StorageLocation("usb", self._world.usb_dir / "Videos", fstype, "/dev/sim-usb",
                                supported=fstype in SUPPORTED_FS, label="SIMUSB")]

    def release(self, location):
        pass


class SimLanc(object):
    def __init__(self, world):
        self._world = world

    def is_high(self):
        return self._world.lanc_high


class SimBacklight(object):
    def __init__(self, world):
        self._world = world

    def set_brightness(self, value):
        self._world.brightness = value
        self._world._changed()

    def set_contrast(self, value):
        self._world.contrast = value
        self._world._changed()

    def close(self):
        pass


class SimRecordLight(object):
    def __init__(self, world):
        self._world = world

    def set(self, on):
        if self._world.light != on:
            self._world.light = on
            self._world._changed()


class SimSystem(object):
    def __init__(self, bus):
        self._bus = bus
        self.rebooted = False

    def reboot(self):
        self.rebooted = True
        from dte import events
        self._bus.post(events.QUIT)

    def factory_reset(self):
        from dte import config
        config.delete_user_file()
        self.reboot()
