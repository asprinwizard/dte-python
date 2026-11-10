import shutil
import tempfile
import unittest
from pathlib import Path

from dte import events
from dte.services.firewire import Device, FirewireMonitor, scan


def make_node(root, node, guid, local=False, vendor=None, model=None, in_unit=False, is_local_attr=True):
    path = root / node
    path.mkdir(parents=True)
    (path / "guid").write_text(guid + "\n")
    if is_local_attr:
        (path / "is_local").write_text("1\n" if local else "0\n")
    target = path
    if not local:
        unit = root / (node + ".0")
        unit.mkdir()
        if in_unit:
            target = unit
    if vendor:
        (target / "vendor_name").write_text(vendor + "\n")
    if model:
        (target / "model_name").write_text(model + "\n")


class Bus(object):
    def __init__(self):
        self.events = []

    def post(self, type_, data=None):
        self.events.append((type_, data))


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(str(self.root))

    def test_skips_local_node_and_reads_names(self):
        make_node(self.root, "fw0", "0x01", local=True, vendor="Texas Instruments")
        make_node(self.root, "fw1", "0x02", vendor="Sony", model="HVR-A1E")
        devices = scan(self.root)
        self.assertEqual([d.node for d in devices], ["fw1"])
        self.assertEqual(devices[0].full_name, "Sony HVR-A1E")

    def test_names_from_unit_directory(self):
        make_node(self.root, "fw1", "0x02", vendor="Sony", model="HVR-A1E", in_unit=True)
        self.assertEqual(scan(self.root)[0].full_name, "Sony HVR-A1E")

    def test_without_is_local_attribute_uses_units(self):
        make_node(self.root, "fw0", "0x01", local=True, is_local_attr=False)
        make_node(self.root, "fw1", "0x02", vendor="Sony", model="X", is_local_attr=False)
        self.assertEqual([d.node for d in scan(self.root)], ["fw1"])

    def test_sorted_by_node_number(self):
        make_node(self.root, "fw10", "0x10")
        make_node(self.root, "fw2", "0x02")
        self.assertEqual([d.node for d in scan(self.root)], ["fw2", "fw10"])

    def test_missing_root(self):
        self.assertEqual(scan(self.root / "nope"), [])


class DeviceTests(unittest.TestCase):
    def test_prefix_and_lcd_name(self):
        device = Device("fw1", "0x02", "Sony", "HVR-A1E")
        self.assertEqual(device.file_prefix, "Sony_HVR-A1E")
        self.assertEqual(device.lcd_name, "Sony HVR-")

    def test_fallback_prefix(self):
        self.assertEqual(Device("fw1", "0x02").file_prefix, "dte-capture")
        self.assertEqual(Device("fw1", "0x02", "Sony").file_prefix, "dte-capture")
        self.assertEqual(Device("fw1", "0x02").lcd_name, "Unknown")

    def test_prefix_strips_unsafe_characters(self):
        self.assertEqual(Device("fw1", "0x2", "JVC/Kenwood", "GY HD100 (U)").file_prefix,
                         "JVC_Kenwood_GY_HD100_U")


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        make_node(self.root, "fw0", "0x01", local=True)
        self.bus = Bus()
        self.monitor = FirewireMonitor(self.bus, self.root)

    def tearDown(self):
        shutil.rmtree(str(self.root))

    def test_first_device_stays_active_until_removed(self):
        make_node(self.root, "fw2", "0x02", vendor="A", model="One")
        self.monitor.poll_once()
        make_node(self.root, "fw1", "0x03", vendor="B", model="Two")
        self.monitor.poll_once()
        self.assertEqual([e[0] for e in self.bus.events], [events.DEVICE_CONNECTED])
        self.assertEqual(self.monitor.active.node, "fw2")

        shutil.rmtree(str(self.root / "fw2"))
        self.monitor.poll_once()
        self.monitor.poll_once()
        self.assertEqual([e[0] for e in self.bus.events],
                         [events.DEVICE_CONNECTED, events.DEVICE_REMOVED, events.DEVICE_CONNECTED])
        self.assertEqual(self.monitor.active.node, "fw1")


if __name__ == "__main__":
    unittest.main()
