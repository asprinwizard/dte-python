"""Filesystem locations used by the app.

Every location can be overridden with an environment variable, which the
simulator and the tests use to keep everything inside a scratch directory.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_path(name, default):
    value = os.environ.get(name)
    return Path(value).expanduser() if value else Path(default).expanduser()


def data_dir():
    """User data directory (~/.dte): config, logs."""
    return _env_path("DTE_HOME", "~/.dte")


def user_config_file():
    return data_dir() / "config.json"


def default_config_file():
    return _env_path("DTE_DEFAULT_CONFIG", PROJECT_ROOT / "config.json")


def internal_videos_dir():
    """Internal capture folder (~/Videos of the logged in user)."""
    return _env_path("DTE_INTERNAL_VIDEOS", "~/Videos")


def firewire_sysfs_dir():
    return _env_path("DTE_FIREWIRE_SYSFS", "/sys/bus/firewire/devices")


def usb_mount_point():
    return _env_path("DTE_USB_MOUNT", "/media/dte/usb")


def dvgrab_binary():
    return _env_path("DTE_DVGRAB", PROJECT_ROOT / "dvgrab")


def log_file():
    return data_dir() / "dte.log"


def dvgrab_log_file():
    return data_dir() / "dvgrab.log"
