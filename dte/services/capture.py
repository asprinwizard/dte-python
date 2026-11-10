"""dvgrab process management.

Runs dvgrab-dte with ``--json`` and turns its JSON Lines (stdout) into events.
stderr is copied to ``~/.dte/dvgrab.log``.

Rules from the dvgrab plan:
- stdin is /dev/null; stdout and stderr are separate pipes (dvgrab makes
  stderr non-blocking, so it must not share a pipe with the JSON stream).
- No SIGUSR1/SIGUSR2 is sent before dvgrab's ``ready`` event; an unhandled
  SIGUSR1 would kill it. After every ``ready`` the wanted armed state is resent.
- Stopping is SIGINT, then SIGKILL after 3 s (SIGTERM does the same as SIGINT).

Every event carries ``_gen``, the run it came from, so the app can ignore
late events from a dvgrab that has already been replaced.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time

from dte import events

log = logging.getLogger(__name__)

STOP_TIMEOUT = 3.0
TYPE_TO_EVENT = {
    "ready": events.CAPTURE_READY,
    "status": events.CAPTURE_STATUS,
    "file_open": events.CAPTURE_FILE,
    "file_closed": events.CAPTURE_FILE,
    "warning": events.CAPTURE_WARNING,
    "error": events.CAPTURE_ERROR,
}
TRIGGER_MODES = ("standalone", "lanc")


def command_prefix(binary):
    binary = str(binary)
    if binary.endswith(".py"):
        return [sys.executable, binary]
    return [binary]


def build_command(binary, device, location, mode):
    args = command_prefix(binary) + [
        "--guid", device.guid,
        "--json",
        "--passive",
        "--sync-interval", "2",
        "--buffers", "100",
        "--size", str(location.dvgrab_size()),
    ]
    if mode in TRIGGER_MODES:
        args += ["--trigger"]
    else:
        args += ["--recordonly", "--autosplit"]
    base = location.videos_dir / (device.file_prefix + "-")
    args += ["--timestamp", "--interactive", str(base)]
    return args


def parse_line(line):
    """Return (event_type, data) for a dvgrab JSON line, or None."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except ValueError:
        log.debug("Ignoring non-JSON dvgrab output: %r", line)
        return None
    if not isinstance(data, dict):
        return None
    event_type = TYPE_TO_EVENT.get(data.get("type"))
    if event_type is None:
        return None
    return event_type, data


def check_version(binary):
    """True if ``binary`` is a dvgrab-dte build with JSON support."""
    try:
        result = subprocess.run(command_prefix(binary) + ["--version"], stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.error("Can't run %s: %s", binary, exc)
        return False
    output = result.stdout.decode("utf-8", "replace")
    ok = "-dte" in output
    if not ok:
        log.error("%s is not a dvgrab-dte build with --json support: %r", binary, output.strip())
    return ok


class CaptureService(object):
    def __init__(self, bus, binary, log_path):
        self._bus = bus
        self._binary = binary
        self._log_path = log_path
        self._lock = threading.Lock()
        self._proc = None
        self._threads = []
        self._ready = False
        self._armed = False
        self._mode = "auto"
        self.generation = 0
        self.last_output = 0.0
        self.command = None

    @property
    def running(self):
        return self._proc is not None and self._proc.poll() is None

    @property
    def ready(self):
        return self._ready

    @property
    def armed(self):
        return self._armed

    def start(self, device, location, mode):
        self.stop()
        with self._lock:
            self.generation += 1
            gen = self.generation
            self._mode = mode
            self._ready = False
            self._armed = False
            self.command = build_command(self._binary, device, location, mode)
            log.info("Starting dvgrab: %s", " ".join(self.command))
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            self._proc = subprocess.Popen(
                self.command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # a Ctrl-C in the terminal must not reach dvgrab
            )
            self.last_output = time.monotonic()
            proc = self._proc
        self._threads = [
            threading.Thread(target=self._read_stdout, args=(proc, gen), name="dvgrab-out", daemon=True),
            threading.Thread(target=self._read_stderr, args=(proc,), name="dvgrab-err", daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    def _read_stdout(self, proc, gen):
        for raw in iter(proc.stdout.readline, b""):
            self.last_output = time.monotonic()
            parsed = parse_line(raw.decode("utf-8", "replace"))
            if parsed is None:
                continue
            event_type, data = parsed
            data["_gen"] = gen
            if event_type == events.CAPTURE_READY:
                with self._lock:
                    if gen == self.generation:
                        self._ready = True
                        self._send_armed_locked()
            self._bus.post(event_type, data)
        proc.stdout.close()
        returncode = proc.wait()
        log.info("dvgrab exited with %s", returncode)
        self._bus.post(events.CAPTURE_EXITED, {"returncode": returncode, "_gen": gen})

    def _read_stderr(self, proc):
        with open(str(self._log_path), "ab") as handle:
            for raw in iter(proc.stderr.readline, b""):
                handle.write(raw)
                handle.flush()
        proc.stderr.close()

    def set_armed(self, armed):
        """Standalone/LANC: arm (SIGUSR1) or disarm (SIGUSR2) recording."""
        with self._lock:
            self._armed = bool(armed)
            self._send_armed_locked()

    def _send_armed_locked(self):
        if self._mode not in TRIGGER_MODES or not self._ready or not self.running:
            return
        sig = signal.SIGUSR1 if self._armed else signal.SIGUSR2
        try:
            os.kill(self._proc.pid, sig)
        except OSError as exc:
            log.warning("Couldn't signal dvgrab: %s", exc)

    def stop(self):
        with self._lock:
            proc = self._proc
            self._proc = None
            self._ready = False
            self._armed = False
            self.generation += 1  # anything still arriving from the old run is stale
        if proc is None:
            return
        if proc.poll() is None:
            log.info("Stopping dvgrab (pid %s)", proc.pid)
            try:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                log.warning("dvgrab didn't stop within %ss; killing it", STOP_TIMEOUT)
                proc.kill()
                proc.wait()
            except OSError:
                pass
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads = []
