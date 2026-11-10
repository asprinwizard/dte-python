"""FireWire device detection through sysfs.

Every second the monitor lists ``/sys/bus/firewire/devices/fwN`` nodes,
skips the Pi's own controller (``is_local == 1``) and picks the *active*
device: the remote node with the lowest ``fwN`` number. The active device
stays active until it is removed, even if other devices are connected, so a
second camera is only picked up after the first one is unplugged.
"""

import logging
import re
import threading
from pathlib import Path

from dte import events

log = logging.getLogger(__name__)

FALLBACK_PREFIX = "dte-capture"
LCD_NAME_WIDTH = 9
_NODE_RE = re.compile(r"^fw(\d+)$")


class Device(object):
    def __init__(self, node, guid, vendor=None, model=None):
        self.node = node          # e.g. "fw1"
        self.guid = guid          # e.g. "0x080046010412abcd"
        self.vendor = vendor or None
        self.model = model or None

    @property
    def number(self):
        return int(_NODE_RE.match(self.node).group(1))

    @property
    def key(self):
        return (self.node, self.guid)

    @property
    def full_name(self):
        parts = [p for p in (self.vendor, self.model) if p]
        return " ".join(parts) if parts else "Unknown"

    @property
    def lcd_name(self):
        return self.full_name[:LCD_NAME_WIDTH]

    @property
    def file_prefix(self):
        """Safe file name prefix, or ``dte-capture`` if vendor or model is missing."""
        if not (self.vendor and self.model):
            return FALLBACK_PREFIX
        prefix = re.sub(r"[^A-Za-z0-9-]+", "_", "{} {}".format(self.vendor, self.model)).strip("_")
        return prefix or FALLBACK_PREFIX

    def __eq__(self, other):
        return isinstance(other, Device) and self.key == other.key

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return "Device({}, {}, {!r})".format(self.node, self.guid, self.full_name)


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _unit_dirs(root, node):
    return sorted(p for p in Path(root).glob(node + ".*") if p.is_dir())


def scan(root):
    """Return remote FireWire devices under ``root``, lowest node number first."""
    root = Path(root)
    if not root.is_dir():
        return []
    devices = []
    for entry in root.iterdir():
        match = _NODE_RE.match(entry.name)
        if not match:
            continue
        units = _unit_dirs(root, entry.name)
        is_local = _read(entry / "is_local")
        if is_local is not None:
            if is_local == "1":
                continue
        elif not units:
            # Older kernels without is_local: the local node has no unit
            # directories, a camera always has an AV/C unit.
            continue
        guid = _read(entry / "guid")
        if not guid:
            continue
        vendor = _read(entry / "vendor_name")
        model = _read(entry / "model_name")
        for unit in units:
            # Sony often only puts the names in the unit directory.
            vendor = vendor or _read(unit / "vendor_name")
            model = model or _read(unit / "model_name")
        devices.append(Device(entry.name, guid, vendor, model))
    devices.sort(key=lambda d: d.number)
    return devices


class FirewireMonitor(object):
    def __init__(self, bus, root, interval=1.0):
        self._bus = bus
        self._root = root
        self._interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.active = None

    def poll_once(self):
        devices = scan(self._root)
        if self.active is not None and self.active not in devices:
            log.info("Device removed: %r", self.active)
            removed, self.active = self.active, None
            self._bus.post(events.DEVICE_REMOVED, {"device": removed})
            # The next device (if any) is picked up on the next poll, after
            # the app has finished tearing down the old capture.
            return
        if self.active is None and devices:
            self.active = devices[0]
            log.info("Device connected: %r", self.active)
            self._bus.post(events.DEVICE_CONNECTED, {"device": self.active})

    def _run(self):
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:
                log.exception("FireWire poll failed")
            self._stop.wait(self._interval)

    def start(self):
        self._thread = threading.Thread(target=self._run, name="firewire", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
