import unittest

from dte.services.storage import StorageLocation, best_location, parse_lsblk


def disk(children=None, tran="usb", fstype=None, name="sda"):
    return {"name": name, "path": "/dev/" + name, "tran": tran, "type": "disk",
            "fstype": fstype, "mountpoint": None, "label": None, "children": children}


def part(name, fstype, mountpoint=None):
    return {"name": name, "path": "/dev/" + name, "tran": None, "type": "part",
            "fstype": fstype, "mountpoint": mountpoint, "label": "CARD"}


class ParseLsblkTests(unittest.TestCase):
    def test_partition_inherits_usb_transport(self):
        found = parse_lsblk({"blockdevices": [disk([part("sda1", "exfat")])]})
        self.assertEqual(found["device"], "/dev/sda1")
        self.assertTrue(found["supported"])

    def test_unpartitioned_drive(self):
        found = parse_lsblk({"blockdevices": [disk(None, fstype="vfat")]})
        self.assertEqual(found["device"], "/dev/sda")
        self.assertEqual(found["fstype"], "vfat")

    def test_prefers_supported_partition(self):
        found = parse_lsblk({"blockdevices": [disk([part("sda1", "ntfs"), part("sda2", "vfat")])]})
        self.assertEqual(found["device"], "/dev/sda2")

    def test_unsupported_filesystem(self):
        found = parse_lsblk({"blockdevices": [disk([part("sda1", "ext4")])]})
        self.assertFalse(found["supported"])

    def test_ignores_non_usb_disks_and_empty_drives(self):
        data = {"blockdevices": [
            disk([part("mmcblk0p2", "ext4", "/")], tran=None, name="mmcblk0"),
            disk([part("sdb1", None)], name="sdb"),
        ]}
        self.assertIsNone(parse_lsblk(data))

    def test_existing_mountpoint_is_reported(self):
        found = parse_lsblk({"blockdevices": [disk([part("sda1", "exfat", "/media/x")])]})
        self.assertEqual(found["mountpoint"], "/media/x")


class LocationTests(unittest.TestCase):
    def test_priority(self):
        internal = StorageLocation("internal", "/home/dte/Videos")
        usb = StorageLocation("usb", "/media/dte/usb/Videos", "exfat", "/dev/sda1")
        bad_usb = StorageLocation("usb", "/media/dte/usb/Videos", "ntfs", "/dev/sdb1", supported=False)
        self.assertEqual(best_location([internal, usb]), usb)
        self.assertEqual(best_location([internal, bad_usb]), internal)

    def test_dvgrab_size(self):
        self.assertEqual(StorageLocation("usb", "/x", "vfat").dvgrab_size(), 4000)
        self.assertEqual(StorageLocation("usb", "/x", "exfat").dvgrab_size(), 0)
        self.assertEqual(StorageLocation("internal", "/x", "internal").dvgrab_size(), 0)


if __name__ == "__main__":
    unittest.main()
