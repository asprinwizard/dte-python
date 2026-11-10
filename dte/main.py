"""Builds the app from real hardware or the simulator, and runs it."""

import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path

from dte import paths

log = logging.getLogger("dte")


def setup_logging(to_console):
    paths.data_dir().mkdir(parents=True, exist_ok=True)
    handlers = [logging.handlers.RotatingFileHandler(str(paths.log_file()), maxBytes=1000000, backupCount=3)]
    if to_console:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _common(bus, lcd, backlight, system, usb_backend, lanc, light):
    from dte import config
    from dte.app import App
    from dte.services.battery import BatteryMonitor
    from dte.services.capture import CaptureService, check_version
    from dte.services.firewire import FirewireMonitor
    from dte.services.storage import InternalBackend, SdBackend, StorageMonitor

    config.load()
    capture = CaptureService(bus, paths.dvgrab_binary(), paths.dvgrab_log_file())
    firewire = FirewireMonitor(bus, paths.firewire_sysfs_dir())
    storage = StorageMonitor(bus, [SdBackend(), usb_backend, InternalBackend()])
    battery = BatteryMonitor(bus)
    app = App(bus, lcd, backlight, capture, firewire, storage, system,
              lanc=lanc, record_light=light, battery=battery,
              dvgrab_ok=check_version(paths.dvgrab_binary()))
    return app, [storage, firewire, battery]


def run_real():
    from dte import events, pins
    from dte.hardware.backlight import Backlight
    from dte.hardware.encoder import Encoder
    from dte.hardware.lcd import LCD, RPLCDDriver
    from dte.hardware.record_trigger import LancInput, RecordButton, RecordLight
    from dte.services.storage import UsbBackend
    from dte.services.system import System

    setup_logging(to_console=True)
    bus = events.EventBus()
    lcd = LCD(RPLCDDriver(pins))
    lcd.show(["DTE Recorder", "Starting..."])
    inputs = [Encoder(bus), RecordButton(bus)]
    lanc = LancInput(bus)
    light = RecordLight()
    backlight = Backlight()
    app, services = _common(bus, lcd, backlight, System(), UsbBackend(), lanc, light)

    signal.signal(signal.SIGTERM, lambda *_: bus.post(events.QUIT))
    for service in services:
        service.start()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    finally:
        for service in services:
            service.stop()
        for device in inputs + [lanc, light, backlight, lcd]:
            try:
                device.close()
            except Exception:
                log.exception("Close failed")


def run_sim(root):
    from dte.sim.world import SimWorld

    world = SimWorld(root)
    os.environ.update(world.env())

    from dte import events
    from dte.hardware.lcd import LCD
    from dte.sim.terminal import Terminal
    from dte.sim.world import SimBacklight, SimLanc, SimRecordLight, SimSystem, SimUsbBackend

    setup_logging(to_console=False)
    bus = events.EventBus()
    terminal = Terminal(world, bus)
    lcd = LCD(terminal.driver)
    app, services = _common(bus, lcd, SimBacklight(world), SimSystem(bus),
                            SimUsbBackend(world), SimLanc(world), SimRecordLight(world))
    terminal.start()
    for service in services:
        service.start()
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()
    finally:
        for service in services:
            service.stop()
        terminal.stop()
    print("Simulator stopped. Log: {}".format(paths.log_file()))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--sim" in argv or os.environ.get("DTE_SIM") == "1":
        run_sim(Path(os.environ.get("DTE_SIM_ROOT", paths.PROJECT_ROOT / ".sim")))
    else:
        run_real()
