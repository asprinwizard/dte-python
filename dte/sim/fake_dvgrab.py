#!/usr/bin/env python3
"""A stand-in for dvgrab-dte that speaks the planned JSON protocol.

Accepts the same arguments the app passes. Behaviour:
- ``--recordonly``: writes while the simulated camera is recording (read from
  the file in $DTE_FAKE_CAMERA_STATE: "REC" or "STBY").
- ``--trigger``: writes while armed (SIGUSR1 arms, SIGUSR2 disarms).
- Each take is its own file, named ``<base>DD-MM-YYYY_HH-MM-SS[-N].<ext>``.
- SIGINT/SIGTERM close the file and exit cleanly.

It deliberately has no imports from the ``dte`` package.
"""

import argparse
import datetime
import json
import os
import signal
import sys
import time

VERSION = "3.5-dte1 (simulated)"
state = {"done": False, "armed": False}


def emit(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def note(text):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def hms(seconds):
    seconds = int(seconds)
    return "{:02d}:{:02d}:{:02d}".format(seconds // 3600, seconds // 60 % 60, seconds % 60)


def camera_recording():
    path = os.environ.get("DTE_FAKE_CAMERA_STATE")
    if not path:
        return False
    try:
        with open(path) as handle:
            return handle.read().strip() == "REC"
    except OSError:
        return False


def unique_name(base, ext):
    stamp = datetime.datetime.now().strftime("%d-%m-%Y_%H-%M-%S")
    name = "{}{}{}".format(base, stamp, ext)
    copy = 2
    while os.path.exists(name):
        name = "{}{}-{}{}".format(base, stamp, copy, ext)
        copy += 1
    return name


def main():
    # Handlers first: an early SIGUSR1 must never kill the process.
    signal.signal(signal.SIGUSR1, lambda *_: state.update(armed=True))
    signal.signal(signal.SIGUSR2, lambda *_: state.update(armed=False))
    signal.signal(signal.SIGINT, lambda *_: state.update(done=True))
    signal.signal(signal.SIGTERM, lambda *_: state.update(done=True))

    parser = argparse.ArgumentParser(allow_abbrev=False)
    for flag in ("--json", "--passive", "--trigger", "--recordonly", "--autosplit",
                 "--timestamp", "--interactive", "--version"):
        parser.add_argument(flag, action="store_true")
    for option in ("--guid", "--sync-interval", "--buffers", "--size"):
        parser.add_argument(option)
    parser.add_argument("base", nargs="?")
    args = parser.parse_args()

    if args.version:
        note("dvgrab " + VERSION)
        return 0

    hdv = args.guid in os.environ.get("DTE_FAKE_HDV_GUIDS", "").split(",")
    fmt, ext = ("HDV", ".m2t") if hdv else ("DV", ".dv")
    note("Fake dvgrab for {} ({})".format(args.guid, fmt))

    emit({"type": "ready", "version": VERSION, "format": fmt, "guid": args.guid,
          "trigger": args.trigger, "recordonly": args.recordonly})

    # Waiting for the first frame.
    wait_until = time.monotonic() + 1.5
    while time.monotonic() < wait_until and not state["done"]:
        emit({"type": "status", "status": "WAIT", "timecode": "--:--:--", "elapsed": "00:00:00",
              "format": fmt, "file": None, "armed": state["armed"]})
        time.sleep(0.5)

    handle = None
    filename = None
    frames = 0
    take_started = 0.0
    camera_tc = 45 * 60          # the camera's tape timecode
    last_tick = time.monotonic()
    last_sent = None
    last_sent_at = 0.0

    def close(reason):
        nonlocal handle, filename
        if handle is None:
            return
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        size_mb = os.path.getsize(filename) / 1048576.0
        emit({"type": "file_closed", "file": filename, "reason": reason, "frames": frames,
              "size_mb": round(size_mb, 3), "dropped": 0, "damaged": 0})
        note("Closed " + filename)
        handle = None
        filename = None

    while not state["done"]:
        now = time.monotonic()
        step = now - last_tick
        last_tick = now
        cam_rec = camera_recording()
        if cam_rec:
            camera_tc += step

        if args.trigger:
            gate = state["armed"]
        elif args.recordonly:
            gate = cam_rec
        else:
            gate = True

        if gate and handle is None:
            filename = unique_name(args.base, ext)
            directory = os.path.dirname(filename)
            if directory:
                os.makedirs(directory, exist_ok=True)
            try:
                handle = open(filename, "wb")
            except OSError as exc:
                emit({"type": "error", "code": "write_failed", "message": str(exc)})
                break
            frames = 0
            take_started = now
            emit({"type": "file_open", "file": filename})
            note("Opened " + filename)
        elif not gate and handle is not None:
            close("take_end")

        if handle is not None:
            try:
                handle.write(b"\0" * 2048)
            except OSError as exc:
                emit({"type": "error", "code": "write_failed", "message": str(exc)})
                close("error")
                break
            frames += 2

        status = "REC" if handle is not None else "STBY"
        # In trigger mode the camera isn't recording, so there's no timecode.
        timecode = hms(camera_tc) if (cam_rec or not args.trigger) else "--:--:--"
        elapsed = hms(now - take_started) if handle is not None else "00:00:00"
        current = (status, timecode, filename, state["armed"])
        if current != last_sent or now - last_sent_at >= 1.0:
            emit({"type": "status", "status": status, "timecode": timecode, "elapsed": elapsed,
                  "transport": "Recording" if cam_rec else "Recording Pause",
                  "format": fmt, "file": filename, "armed": state["armed"]})
            last_sent, last_sent_at = current, now
        time.sleep(0.1)

    close("stop")
    emit({"type": "exit", "code": 0})
    return 0


if __name__ == "__main__":
    sys.exit(main())
