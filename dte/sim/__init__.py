"""Simulator: runs the whole app on a development machine.

The real app code runs unchanged; only the hardware edges are replaced:
- LCD -> drawn in the terminal; encoder and buttons -> keyboard.
- FireWire -> a fake sysfs tree the real FireWire monitor reads.
- USB drive -> a folder; dvgrab -> ``fake_dvgrab.py`` (same JSON protocol).
"""
