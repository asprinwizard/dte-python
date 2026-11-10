# dte-python

Software for a DTE recorder: a Raspberry Pi CM4 that records DV and HDV from a
FireWire camera, with a 16x2 LCD and a rotary encoder.

Plans and design notes are in `.documentation/`.

## Run the simulator (any Linux / WSL)

```
./start.py --sim
```

The LCD is drawn in the terminal. Keys:

| Key | Does |
|---|---|
| ← / → | Turn the encoder |
| Enter | Click |
| L | Long press (2 s) |
| 1 / 2 / 3 | Plug or unplug a camera (Sony HDV / Canon DV / camera with no name) |
| C | Camera REC on/off (auto mode) |
| R | Standalone record button |
| H | LANC level high/low |
| U / F / N | Insert or remove an exFAT / FAT32 / NTFS USB drive |
| Q | Quit |

Simulator files (recordings, config, logs) go in `.sim/`.

## Tests

```
python3 -m unittest discover -s tests -t .
```

## Install on the Pi

Raspberry Pi OS Bookworm Lite, 64-bit, user `dte`, project in `/home/dte/dte-python`.

1. Custom FireWire kernel: copy `kernel/64-Bit/6.6.44-v8+/kernel-firewire.img` to
   `/boot/firmware/`, and add to `/boot/firmware/config.txt`:
   ```
   # Firewire
   dtoverlay=pcie-32bit-dma

   # Custom Kernel
   kernel=kernel-firewire.img
   ```
2. Build dvgrab-dte (`feature/json-status` branch) on the Pi and copy the
   `dvgrab` binary into this folder. The app checks for the `-dte` version and
   shows `dvgrab outdated` if the binary doesn't support `--json`.
3. `sudo ./deploy/setup.sh`, then reboot.

The recorder runs as the `dte` systemd service: `systemctl status dte`,
logs in `~/.dte/dte.log` and `~/.dte/dvgrab.log`.
