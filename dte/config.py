"""Application settings.

Factory defaults live in ``config.json`` in the project root. The settings the
device actually uses live in ``~/.dte/config.json``, which is created from the
defaults on first start. Any key that is in the defaults but missing from the
user file (e.g. after a software update) is added on load.

Usage from anywhere in the app::

    from dte import config
    config.get("lcd_brightness")
    config.set("lcd_brightness", 9)

Writes are atomic (temp file + fsync + rename), so a power cut during a write
cannot corrupt the file. ``set(..., debounce=True)`` delays the disk write
until no further change has happened for 300 ms, which keeps live encoder
adjustments from hammering the flash.
"""

import json
import logging
import os
import tempfile
import threading

from dte import paths

log = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 0.3

_lock = threading.RLock()
_values = {}
_defaults = {}
_timer = None
_listeners = []


def _read_json(path):
    with open(str(path), "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("{} does not contain a JSON object".format(path))
    return data


def _atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".config-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load():
    """Load defaults and user settings. Creates or migrates the user file."""
    global _values, _defaults
    with _lock:
        _defaults = _read_json(paths.default_config_file())
        user_file = paths.user_config_file()
        user = {}
        if user_file.exists():
            try:
                user = _read_json(user_file)
            except (ValueError, OSError) as exc:
                log.error("Unreadable %s (%s); recreating from defaults", user_file, exc)
                user = {}
        else:
            log.info("%s not found; creating it from defaults", user_file)

        merged = dict(_defaults)
        merged.update(user)
        _values = merged
        if merged != user:
            _atomic_write(user_file, merged)
        return dict(_values)


def get(key, default=None):
    with _lock:
        return _values.get(key, _defaults.get(key, default))


def all_values():
    with _lock:
        return dict(_values)


def set(key, value, debounce=False):  # noqa: A001 - module API mirrors dict-like usage
    """Change a setting. Listeners are told straight away; the file is written
    now, or after ``DEBOUNCE_SECONDS`` of no further changes."""
    global _timer
    with _lock:
        if _values.get(key) == value:
            return
        _values[key] = value
        if _timer is not None:
            _timer.cancel()
            _timer = None
        if debounce:
            _timer = threading.Timer(DEBOUNCE_SECONDS, flush)
            _timer.daemon = True
            _timer.start()
        else:
            _write_now()
    for listener in list(_listeners):
        try:
            listener(key, value)
        except Exception:  # pragma: no cover - a listener bug must not break settings
            log.exception("Config listener failed for %s", key)


def _write_now():
    _atomic_write(paths.user_config_file(), _values)


def flush():
    """Write any pending (debounced) change to disk now."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        if _values:
            _write_now()


def add_listener(callback):
    """``callback(key, value)`` is called after every change."""
    _listeners.append(callback)


def remove_listener(callback):
    if callback in _listeners:
        _listeners.remove(callback)


def delete_user_file():
    """Used by factory reset: the next start recreates the file from defaults."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        user_file = paths.user_config_file()
        if user_file.exists():
            user_file.unlink()
