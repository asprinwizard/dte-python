"""System actions: reboot and factory reset."""

import logging
import os
import subprocess

from dte import config

log = logging.getLogger(__name__)


class System(object):
    def reboot(self):
        log.info("Rebooting")
        os.sync()
        subprocess.run(["sudo", "-n", "systemctl", "reboot"], check=False)

    def factory_reset(self):
        """Delete ~/.dte/config.json and reboot; the next start recreates it
        from the factory defaults."""
        log.info("Factory reset")
        config.delete_user_file()
        self.reboot()
