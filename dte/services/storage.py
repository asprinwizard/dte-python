"""Storage detection: SD card (not implemented yet), USB and internal.

Priority is SD -> USB -> internal. Internal is always available.

Each backend's ``scan()`` returns ``StorageLocation`` objects. The monitor
polls every second and posts STORAGE_CHANGED when the set of locations
changes. Deciding *whether to switch* is the app's job (it depends on whether
a camera is connected and recording).
"""

import json
import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

from dte import events, paths

log = logging.getLogger(__name__)

PRIORITY = {"sd": 0, "usb": 1, "internal": 2}
SUPPORTED_FS = ("vfat", "exfat")
MOUNT_OPTIONS = {
    # The exfat driver has no "flush" option; an unknown option fails the mount.
    "vfat": "uid={uid},gid={gid},umask=022,flush",
    "exfat": "uid={uid},gid={gid},umask=022,errors=remount-ro",
}
LOW_SPACE_BYTES = 200 * 1024 * 1024


class StorageLocation(object):
    def __init__(self, kind, videos_dir, fstype=None, device=None, supported=True, label=None):
        self.kind = kind              # "sd" | "usb" | "internal"
        self.videos_dir = Path(videos_dir)
        self.fstype = fstype
        self.device = device          # e.g. /dev/sda1 (removable media only)
        self.supported = supported
        self.label = label

    @property
    def key(self):
        return (self.kind, self.device or str(self.videos_dir), self.supported)

    @property
    def priority(self):
        return PRIORITY[self.kind]

    @property
    def display_name(self):
        return {"sd": "SD Card", "usb": "USB", "internal": "Internal"}[self.kind]

    def dvgrab_size(self):
        """dvgrab --size in MiB: FAT32 can't hold files over 4 GB, otherwise no limit
        (dvgrab's own default would split every file at 1000 MiB)."""
        return 4000 if self.fstype == "vfat" else 0

    def ensure_videos_dir(self):
        self.videos_dir.mkdir(parents=True, exist_ok=True)

    def free_bytes(self):
        try:
            return shutil.disk_usage(str(self.videos_dir)).free
        except OSError:
            return 0

    def __eq__(self, other):
        return isinstance(other, StorageLocation) and self.key == other.key

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return "StorageLocation({}, {}, {}, supported={})".format(
            self.kind, self.videos_dir, self.fstype, self.supported)


def best_location(locations):
    """Highest-priority supported location (internal is always there)."""
    usable = [loc for loc in locations if loc.supported]
    return min(usable, key=lambda loc: loc.priority) if usable else None


class InternalBackend(object):
    def scan(self):
        return [StorageLocation("internal", paths.internal_videos_dir(), fstype="internal")]

    def release(self, location):
        pass


class SdBackend(object):
    """Placeholder until the SD card hardware is known."""

    def scan(self):
        return []

    def release(self, location):
        pass


def parse_lsblk(data):
    """Find the first USB drive's usable filesystem in ``lsblk -J`` output.

    ``TRAN`` is only set on the whole disk, so partitions inherit it from
    their parent. A drive with no partition table (filesystem directly on the
    disk) is used as-is. Returns a dict, or None if no USB drive has a
    filesystem.
    """
    for disk in data.get("blockdevices", []):
        if disk.get("tran") != "usb" or disk.get("type") != "disk":
            continue
        candidates = disk.get("children") or [disk]
        with_fs = [c for c in candidates if c.get("fstype")]
        if not with_fs:
            continue
        supported = [c for c in with_fs if c.get("fstype") in SUPPORTED_FS]
        chosen = supported[0] if supported else with_fs[0]
        return {
            "device": chosen.get("path") or "/dev/" + chosen.get("name", ""),
            "fstype": chosen.get("fstype"),
            "mountpoint": chosen.get("mountpoint"),
            "label": chosen.get("label"),
            "supported": chosen.get("fstype") in SUPPORTED_FS,
        }
    return None


class UsbBackend(object):
    """Detects the first USB drive with ``lsblk`` and mounts it itself
    (Pi OS Lite has no automounter)."""

    def __init__(self, mount_point=None):
        self._mount_point = Path(mount_point or paths.usb_mount_point())
        self._mounted_device = None

    def _lsblk(self):
        result = subprocess.run(
            ["lsblk", "-J", "-o", "NAME,PATH,TRAN,TYPE,FSTYPE,MOUNTPOINT,LABEL"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5, check=True,
        )
        return json.loads(result.stdout.decode("utf-8"))

    def _run(self, args):
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if result.returncode != 0:
            log.warning("%s failed: %s", " ".join(args), result.stderr.decode("utf-8", "replace").strip())
        return result.returncode == 0

    def _mount(self, device, fstype):
        options = MOUNT_OPTIONS[fstype].format(uid=os.getuid(), gid=os.getgid())
        self._mount_point.mkdir(parents=True, exist_ok=True)
        ok = self._run(["sudo", "-n", "mount", "-t", fstype, "-o", options, device, str(self._mount_point)])
        if ok:
            self._mounted_device = device
            log.info("Mounted %s (%s) at %s", device, fstype, self._mount_point)
        return ok

    def _unmount(self):
        if self._mounted_device or os.path.ismount(str(self._mount_point)):
            self._run(["sudo", "-n", "umount", "-l", str(self._mount_point)])
            log.info("Unmounted %s", self._mount_point)
        self._mounted_device = None

    def scan(self):
        found = parse_lsblk(self._lsblk())
        if found is None:
            if self._mounted_device:
                # The drive was pulled out: drop the stale mount.
                self._unmount()
            return []
        if not found["supported"]:
            return [StorageLocation("usb", self._mount_point / "Videos", found["fstype"],
                                    found["device"], supported=False, label=found["label"])]
        mountpoint = found["mountpoint"]
        if not mountpoint:
            if not self._mount(found["device"], found["fstype"]):
                return []
            mountpoint = str(self._mount_point)
        return [StorageLocation("usb", Path(mountpoint) / "Videos", found["fstype"],
                                found["device"], label=found["label"])]

    def release(self, location):
        if location.kind == "usb":
            self._unmount()


class StorageMonitor(object):
    def __init__(self, bus, backends, interval=1.0):
        self._bus = bus
        self._backends = backends
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None
        self._last_keys = None
        self.locations = []

    def scan(self):
        locations = []
        for backend in self._backends:
            try:
                locations.extend(backend.scan())
            except Exception:
                log.exception("Storage scan failed in %s", type(backend).__name__)
        locations.sort(key=lambda loc: loc.priority)
        return locations

    def poll_once(self):
        locations = self.scan()
        keys = [loc.key for loc in locations]
        if keys != self._last_keys:
            self._last_keys = keys
            self.locations = locations
            log.info("Storage now: %s", locations)
            self._bus.post(events.STORAGE_CHANGED, {"locations": list(locations)})

    def release(self, location):
        for backend in self._backends:
            try:
                backend.release(location)
            except Exception:
                log.exception("Release failed for %r", location)

    def _run(self):
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self._interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="storage", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
