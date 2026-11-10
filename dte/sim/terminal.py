"""Terminal front end for the simulator: draws the LCD and reads the keyboard."""

import os
import select
import sys
import threading

from dte import events
from dte.hardware.glyphs import GLYPHS
from dte.sim.world import USB_FS_LABEL

SYMBOLS = {
    "record": "●", "pause": "‖", "play": "▶",
    "sd": "S", "usb": "U", "internal": "I",
    "battery_full": "▮", "battery_med": "▬", "battery_low": "▂", "battery_empty": "▯",
}
_PATTERN_NAMES = {tuple(p): name for name, p in GLYPHS.items()}

HELP = [
    "Encoder:  ← / →  scroll    Enter  click    L  long press (2 s)",
    "Camera:   1 / 2 / 3  plug or unplug a camera    C  camera REC on/off",
    "Record:   R  standalone record button    H  LANC level high/low",
    "USB:      U  exFAT drive    F  FAT32 drive    N  NTFS (unsupported)",
    "          Q  quit",
]


class SimLCDDriver(object):
    def __init__(self, on_change):
        self.grid = [[" "] * 16 for _ in range(2)]
        self.slots = {}
        self._on_change = on_change

    def create_char(self, slot, pattern):
        self.slots[slot] = _PATTERN_NAMES.get(tuple(pattern), "?")
        self._on_change()

    def write(self, row, col, text):
        for i, ch in enumerate(text):
            if col + i < 16:
                self.grid[row][col + i] = ch
        self._on_change()

    def rows(self):
        result = []
        for row in self.grid:
            out = []
            for ch in row:
                code = ord(ch)
                if code < 8:
                    out.append(SYMBOLS.get(self.slots.get(code), "?"))
                elif code == 0xFF:
                    out.append("█")
                else:
                    out.append(ch)
            result.append("".join(out))
        return result

    def close(self):
        pass


class Terminal(object):
    def __init__(self, world, bus):
        self.world = world
        self.bus = bus
        self.driver = SimLCDDriver(self.redraw)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._old_tty = None
        self.enabled = sys.stdin.isatty() and sys.stdout.isatty()
        world.on_change(self.redraw)

    def redraw(self):
        if not self.enabled:
            return
        world = self.world
        rows = self.driver.rows()
        cams = ", ".join(world.connected_cameras()) or "none"
        usb = USB_FS_LABEL.get(world.usb_fs, "none") if world.usb_fs else "none"
        lines = [
            "DTE recorder simulator",
            "",
            "  ┌────────────────┐",
            "  │" + rows[0] + "│",
            "  │" + rows[1] + "│",
            "  └────────────────┘",
            "",
            "  Cameras: {:<12} Camera REC: {:<4} USB: {:<6} LANC: {:<4} Light: {}".format(
                cams, "on" if world.camera_recording() else "off", usb,
                "HIGH" if world.lanc_high else "LOW", "●" if world.light else "○"),
            "  Brightness: {}/16   Contrast: {}/16   Files: {}".format(
                world.brightness, world.contrast, world.root),
            "",
        ] + ["  " + h for h in HELP]
        with self._lock:
            sys.stdout.write("\x1b[H\x1b[J" + "\r\n".join(lines) + "\r\n")
            sys.stdout.flush()

    def start(self):
        if not self.enabled:
            return
        import termios
        import tty

        fd = sys.stdin.fileno()
        self._old_tty = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l\x1b[2J")
        self._thread = threading.Thread(target=self._read_keys, name="keyboard", daemon=True)
        self._thread.start()
        self.redraw()

    def stop(self):
        self._stop.set()
        if self._old_tty is not None:
            import termios

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_tty)
            self._old_tty = None
            sys.stdout.write("\x1b[?25h\r\n")
            sys.stdout.flush()

    def _read_char(self, timeout):
        fd = sys.stdin.fileno()
        ready, _, _ = select.select([fd], [], [], timeout)
        if not ready:
            return None
        return os.read(fd, 1).decode("utf-8", "ignore")

    def _read_keys(self):
        while not self._stop.is_set():
            ch = self._read_char(0.2)
            if ch is None:
                continue
            if ch == "\x1b":
                if self._read_char(0.05) == "[":
                    code = self._read_char(0.05)
                    if code == "C":
                        self.bus.post(events.SCROLL_RIGHT)
                    elif code == "D":
                        self.bus.post(events.SCROLL_LEFT)
                continue
            self._key(ch.lower())

    def _key(self, ch):
        world, bus = self.world, self.bus
        if ch in ("\n", "\r", " "):
            bus.post(events.CLICK)
        elif ch == "l":
            bus.post(events.LONG_CLICK)
        elif ch in ("1", "2", "3"):
            world.toggle_camera("fw" + ch)
        elif ch == "c":
            world.toggle_camera_recording()
        elif ch == "r":
            bus.post(events.RECORD_BUTTON)
        elif ch == "h":
            bus.post(events.LANC_LEVEL, {"high": world.toggle_lanc()})
        elif ch == "u":
            world.toggle_usb("exfat")
        elif ch == "f":
            world.toggle_usb("vfat")
        elif ch == "n":
            world.toggle_usb("ntfs")
        elif ch == "q":
            bus.post(events.QUIT)
