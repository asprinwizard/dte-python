# DTE Recorder – Development Plan

Source spec: `ai_spec.txt`. This plan includes the amendments from 2026-11-10:

1. Configuration is stored as **JSON**, not `key=value` text.
2. A new **record mode** setting: `auto`, `standalone` or `lanc`.
3. The idle message is now `No Device Found`.
4. Answers to the first round of open questions (see §7).

**Related plan:** the dvgrab fork changes (JSON output and a record trigger) are in
[`../../dvgrab/json-status-output/plan.md`](../../dvgrab/json-status-output/plan.md).
That work needs to be done before Phase 3 of this plan.

---

## 1. What exists today (review of the current code)

| File | State | Action |
|---|---|---|
| `start.py` | Prototype. Uses `multiprocessing`, so the parent never sees `capture_instance.device_disconnected` because that flag changes in the child process. The encoder button is on GPIO17, which the spec gives to LCD EN. | Rewrite as a thin entry point |
| `capture.py` | Stub. `detect_device()` always returns `True`. Calls `dvgrab` from `PATH` instead of `./dvgrab`. Sends stderr to a log file and never parses it. | Replace |
| `process.py` | Doesn't run (syntax error at `def reset()`). | Delete |
| `start_new.py`, `log.py`, `dte_display.py`, `display_test.py` | Experiments | Delete |
| `config.py`, `config/loader.py`, `config.txt` | Text `key=value` loader that writes `.config` into the current directory, not `~/.dte`. | Replace with the JSON version |
| `display/lcd1602/lcd_display.py` | Uses Adafruit_CharLCD (deprecated) with pins that don't match the spec. `formatText` is missing `self`. | Replace |
| `display/lcd1602_IC2/*` | I2C driver. The hardware is not I2C. | Delete |
| `display/custom/chars/chars5x8.py` | Useful glyphs. **Bug:** trailing commas after `]` (`self.pause = [...],`) turn 7 glyphs, `pause` through `usb`, into tuples (lines 24–84). `record` and `play` are fine. There's no glyph for internal storage. | Keep the glyphs, fix the bug, add an internal-storage glyph |
| `controller/rotary/MenuNavigator.py` | Has the right idea (detects long presses). Pins are wrong, and the menu logic is tied to the GPIO code. | Replace with an encoder driver that emits events, plus separate screens |
| `dvgrab` | **32-bit ARM (armhf)** binary built from the DTE fork (`~/workspace/personal/dvgrab-dte`). It doesn't output JSON yet, and its DTE loop runs with no sleep. | Replace with an arm64 build of the fork after the changes in the dvgrab plan |
| `kernel/64-Bit/...` | Custom 64-bit kernel with FireWire enabled. | Keep (document it in the README) |

**Conclusion:** keep the glyph data and the kernel notes, and rebuild everything else as one structured package.

---

## 2. Architecture

### 2.1 Process model

The app runs as **one Python process with an event loop on the main thread**:

- **Background threads** watch the hardware and system and put events on a single `queue.Queue`:
  - FireWire monitor: polls sysfs every 1 s
  - Storage monitor: polls every 1 s
  - dvgrab stdout (JSON) and stderr (log) readers: one pair per capture
  - GPIO callbacks for the encoder and the record trigger
  - Battery monitor (placeholder)
- **The main loop** takes events off the queue one at a time and passes them to the active screen and the app state machine. All LCD writes happen on this thread, so the display has no race conditions.
- **dvgrab** runs as a child process (`subprocess.Popen`). The app reads its JSON status from stdout and sends it signals to start and stop recording (see §4.3).

This replaces the `multiprocessing` design, where state could not be shared between processes.

### 2.2 Package layout

```
dte-python/
├── start.py                  # entry point: sets up logging, runs dte.app.main()
├── config.json               # factory defaults (replaces config.txt)
├── dvgrab                    # custom fork binary
├── dte/
│   ├── app.py                # main loop, state machine, screen routing
│   ├── config.py             # JSON config singleton (get/set/reset)
│   ├── events.py             # event types + queue
│   ├── pins.py               # every GPIO number in one place
│   ├── hardware/
│   │   ├── lcd.py            # RPLCD wrapper, 16x2 frame buffer, custom-char slots
│   │   ├── glyphs.py         # 5x8 custom characters (from chars5x8.py)
│   │   ├── backlight.py      # PWM brightness/contrast
│   │   ├── encoder.py        # emits SCROLL_LEFT/RIGHT, CLICK, LONG_CLICK
│   │   ├── record_trigger.py # standalone button / LANC level → RECORD_ARM / RECORD_DISARM
│   │   └── sim.py            # terminal simulator (LCD + keyboard) for development
│   ├── services/
│   │   ├── firewire.py       # device detection via /sys/bus/firewire
│   │   ├── storage.py        # USB / SD / internal detection, mount, priority
│   │   ├── capture.py        # dvgrab lifecycle, JSON reader, SIGUSR1/2 control
│   │   ├── battery.py        # placeholder: always FULL
│   │   └── system.py         # reboot, factory reset
│   └── ui/
│       ├── screen.py         # base Screen: render(), on_scroll_left/right/click/long_click
│       ├── capture.py        # default screen
│       ├── message.py        # "No Device Found", "Please Wait", errors
│       ├── playback_list.py
│       ├── playback.py
│       └── settings/
│           ├── menu.py       # SETTINGS list (labels, keys, templates)
│           ├── root.py       # settings menu list screen
│           ├── range.py      # 'range' template
│           ├── confirm.py    # 'confirm' template
│           └── options.py    # 'options' template (for record_mode)
├── deploy/
│   ├── dte.service           # systemd unit
│   ├── 99-dte-sudoers        # passwordless reboot/mount/umount for user dte
│   └── setup.sh              # apt deps, venv, boot config, enable service
└── tests/                    # pytest: config, parser, storage priority, screens
```

### 2.3 Events

The encoder emits `SCROLL_LEFT`, `SCROLL_RIGHT`, `CLICK` and `LONG_CLICK`. Each screen subclasses `Screen` and handles only the events it needs. This meets the spec's requirement that each template can handle each event differently:

- The `range` template acts on scroll events.
- The `confirm` template acts on click.

System events go to the app state machine first, then to the current screen:

- `DEVICE_CONNECTED`, `DEVICE_REMOVED`
- `STORAGE_CHANGED`
- `CAPTURE_STATUS` (REC/STBY, timecode, format)
- `CAPTURE_EXITED`
- `RECORD_ARM`, `RECORD_DISARM`
- `BATTERY_LEVEL`
- `IDLE_TIMEOUT`

**Long press behaviour:** `LONG_CLICK` fires as soon as the button has been held for 2 s, so the user doesn't need to let go to see the result. The release that follows doesn't produce a `CLICK`.

### 2.4 Hardware abstraction and simulator

Development happens on WSL, so every hardware class has a simulated version that `DTE_SIM=1` turns on:

- **LCD:** draws a 16×2 box in the terminal.
- **Encoder:** `←`/`→` scroll, `Enter` clicks, `L` long-clicks.
- **Record button:** `R`.
- **FireWire:** a fake device that `D` plugs in or removes.
- **Storage:** `U` toggles a fake USB drive.
- **dvgrab:** a fake script (`tests/fake_dvgrab.py`) that takes the same arguments, prints the same JSON events, and responds to SIGUSR1/SIGUSR2. `C` toggles the fake camera's REC state, which is how `auto` mode is simulated.

With these, you can build and test the whole state machine before using the Pi.

---

## 3. Configuration (JSON)

- **Factory defaults:** `config.json` in the project root.
- **User settings:** `~/.dte/config.json`, created from the defaults on first start.
- **New settings in later versions:** on startup, any key that's in the defaults but missing from the user file is added. Existing values are kept.
- **Writes are atomic:** the app writes a temporary file, calls `fsync`, then renames it. A power cut during a live write can't corrupt the config.
- **Rapid encoder turns:** live `range` changes are applied to the hardware immediately, but the file is only written after 300 ms without further changes. This keeps the spec's "live update" while limiting flash wear.
- **Access from any module:** `from dte import config` then `config.get('lcd_brightness')` or `config.set('lcd_brightness', 9)`. This is the "global array" from the spec.

```json
{
  "lcd_brightness": 8,
  "lcd_contrast": 8,
  "record_mode": "auto"
}
```

Settings menu definition (`dte/ui/settings/menu.py`):

```python
SETTINGS = [
    {"label": "LCD Brightness", "key": "lcd_brightness", "template": "range", "min": 0, "max": 16},
    {"label": "LCD Contrast",   "key": "lcd_contrast",   "template": "range", "min": 0, "max": 16},
    {"label": "Record Mode",    "key": "record_mode",    "template": "options",
     "options": [("auto", "Auto"), ("standalone", "Standalone"), ("lanc", "LANC")]},
    {"label": "Factory Reset",  "template": "confirm", "action": "factory_reset"},
]
```

**`options` template.** This is new and is needed for record mode.

- Line 1 shows the setting's label. Line 2 shows `< Auto >`.
- Scrolling moves through the options. The selection is only saved on **click**, because changing the mode restarts dvgrab.
- After saving, the screen returns to the settings menu.

**Factory reset.** Deletes `~/.dte/config.json`, runs `sync`, then runs `sudo systemctl reboot`. A sudoers rule lets the `dte` user run this without a password.

---

## 4. Subsystems

### 4.1 FireWire device detection (`services/firewire.py`)

- Poll `/sys/bus/firewire/devices/fw*` every 1 s.
- Ignore the Pi's own controller node: skip nodes with `is_local == 1`, or if that attribute isn't there, match the local card's GUID. **Check on hardware.**
- Read `vendor_name`, `model_name` and `guid`. Fall back to the unit directory (`fwN.0`) if a value isn't on the node.
- **Active device:** the remote node with the lowest `fwN` number. It stays active until it's removed, even if other devices are connected. This covers the two-device edge case.
- **File prefix:** `"{vendor} {model}"`, cleaned up to safe characters, e.g. `Sony_HVR-A1E`. If either value is missing, use `dte-capture`.
- **LCD name:** the readable `Sony HVR-A1E`, cut to 9 characters (`Sony HVR-`).
- Start dvgrab with `--guid <guid>` so it captures from the active device and not whichever device the library finds first.

### 4.2 Storage (`services/storage.py`)

- **Priority:** SD → USB → internal. The SD backend is an empty stub that always returns "not present", ready to fill in when the hardware is known.
- **Mounting:** Pi OS Lite doesn't mount USB drives automatically. Every 1 s, the service runs `lsblk -J -o NAME,TRAN,TYPE,FSTYPE,MOUNTPOINT,LABEL` and **walks the device tree**. `TRAN=usb` is set only on the whole disk, so partitions take it from their parent disk.
  - The service uses the first partition that has a supported filesystem.
  - If the disk has no partitions and the filesystem is directly on the disk (e.g. `sda`), the disk itself is used.
  - It mounts at `/media/dte/usb`.
  - **Supported filesystems:** exFAT and FAT32 (`vfat`) (answer B5). **Mount options are different for each:**
    - vfat: `uid=dte,gid=dte,umask=022,flush`
    - exFAT: `uid=dte,gid=dte,umask=022,errors=remount-ro`. The exfat driver has **no `flush` option**, and an unknown option makes the mount fail.
  - **Kernel check:** the custom kernel in `kernel/64-Bit/6.6.44-*` comes without modules. In Phase 0, check `/proc/config.gz` on the running kernel to confirm that `exfat`, `vfat` and `usb-storage` are built in or have matching modules in `/lib/modules/6.6.44-v8+`.
  - `exfatprogs` and `dosfstools` are installed for `fsck`, and a future "Format Disk" setting can use them.
  - Any other filesystem (ext4, NTFS, etc.) isn't mounted. The LCD shows `USB Not Supported` for 3 s and recording stays on internal storage.
- **Capture folder:**
  - USB and SD: `Videos/` at the root of the drive, created if missing.
  - Internal: `/home/dte/Videos`.
- **When storage changes** (decided in answer 3):

  | Event | No device connected | Device connected, STBY | Device connected, REC |
  |---|---|---|---|
  | **The storage in use is removed** | Switch straight away | Switch straight away | **Stop capture immediately**, then switch |
  | **Higher-priority storage is added** (e.g. USB while using internal) | Switch straight away | **Ask the user** (see below) | **Keep recording.** Ask at the next STBY |
  | **Storage not in use is added or removed** | Update the list of available storage only | Same | Same |

  **Asking before switching storage** (answer B9). Switching restarts dvgrab, which takes 2–5 s. If the camera starts recording during that gap, the start of the take would be lost. So when a camera is connected, the switch only happens when the user confirms it.

  The prompt uses the existing `confirm` template:

  ```
  |USB Found       |
  |Switch? No      |
  ```

  - **Default is No.** Scrolling toggles between No and Yes.
  - **Click on Yes:** follow the switching steps below.
  - **Click on No, a long press, or 15 s without input:** stay on the current storage and go back to the capture screen. The prompt isn't shown again for that drive. The switch then happens on its own the next time no camera is connected, e.g. when the camera is unplugged.
  - **The camera starts recording while the prompt is open:** the prompt closes and the capture screen comes back (answer A5). The prompt comes back at the next STBY.
  - **While a switch is pending or declined,** the storage icon keeps showing the storage that's actually being recorded to.

  A plain click on the capture screen still opens playback. The prompt is its own screen, so a click never has two meanings.

  **Switching steps:**
  1. Emit `STORAGE_CHANGED`.
  2. Stop dvgrab: SIGINT, then SIGKILL after 3 s. dvgrab treats SIGTERM exactly like SIGINT, so it adds nothing.
  3. The LCD shows `Please Wait`.
  4. Switch to the new location, update the storage icon, and restart capture if a device is connected.
  5. If the old storage was a removed USB drive, lazily unmount it (`umount -l`).
- **Disk full** (new, not in the spec): check free space every 5 s while capturing. Below 200 MB, stop dvgrab and show `Storage Full`.
- **File size limit (`--size`).** By default dvgrab splits **every** file at 1000 MiB (`DEFAULT_SIZE`), so the app always sets the limit:
  - **FAT32:** `--size 4000`. FAT32 can't hold files over 4 GB, and an hour of HDV is about 13 GB.
  - **exFAT and internal:** `--size 0` (no limit).

### 4.3 Capture (`services/capture.py`)

This depends on the dvgrab fork changes (`--json`, `--trigger`, `--passive`). They're specified in the [dvgrab plan](../../dvgrab/json-status-output/plan.md).

**Command lines by record mode:**

| Mode | Command |
|---|---|
| `auto` | `./dvgrab --guid G --json --passive --sync-interval 2 --buffers 100 --size S --recordonly --autosplit --timestamp --interactive <dir>/<prefix>-` |
| `standalone` | Same as `auto`, but **`--trigger` replaces `--recordonly --autosplit`**. The record button arms and disarms recording. |
| `lanc` | Same as `standalone`. The Arduino holds a GPIO HIGH while recording (§4.6). |

**What the options do:**

- **`--timestamp`:** files are named after the date and time recorded in the stream, e.g. `Sony_HVR-A1E-10-11-2026_14-22-01.m2t` (answer 4). If a name already exists, dvgrab adds `-2`, `-3`, … instead of overwriting.
- **`--passive`:** dvgrab never sends Play, Pause or Stop to the camera, including on shutdown.
- **`--size S`:** the file size limit for the storage type (§4.2).
- **`--sync-interval 2`:** data is flushed to disk every 2 s, so a power cut loses no more than about 2 s.
- **`--buffers 100`:** covers USB flash write stalls. The old value of 10 was only about 0.33 s.

**Every take gets its own file and is closed as soon as it ends**, in every mode (dvgrab plan §3.3).

**Process setup:**

- `stdin=DEVNULL`.
- Separate stdout and stderr pipes. dvgrab makes stderr non-blocking, so it must not share a pipe with stdout.

**Startup contract:**

1. **Don't signal early.** The app sends no SIGUSR1/SIGUSR2 until dvgrab has sent its `ready` event. Before then, an unhandled SIGUSR1 would kill dvgrab.
2. **Waiting is not a hang.** `status: WAIT` means dvgrab is waiting for a stream (the LCD shows STBY). It isn't treated as a fault until 30 s pass with no `ready` and no status line.

**Start/stop control** (standalone and LANC):

- The app sends `SIGUSR1` to arm recording and `SIGUSR2` to disarm it.
- Repeated signals have no extra effect, so after every `ready` the app resends the current state (the LANC level, or "disarmed" for the button).

**Reading the status.** One thread reads JSON Lines from dvgrab's stdout and turns each `type` into an app event:

| JSON `type` | App event |
|---|---|
| `ready` | Sets the format (DV/HDV) |
| `status` | `CAPTURE_STATUS` with `status`, `timecode`, `elapsed` and `file`. The LCD shows `timecode`, or `elapsed` when the timecode is `--:--:--`, which is common in standalone and LANC modes. |
| `file_open` | Logged |
| `file_closed` | Logged |
| `warning` | Logged |
| `error` | `CAPTURE_ERROR`. For example, `write_failed` when a disk is full or a USB drive is pulled. |
| `exit` | `CAPTURE_EXITED` |

A line that isn't valid JSON is logged and skipped. A second thread copies dvgrab's stderr to `~/.dte/dvgrab.log`.

**Checking the binary:** at startup the app runs `./dvgrab --version` and checks for the `-dte` suffix. If the binary is too old, the LCD shows `dvgrab outdated` instead of failing silently.

**Display updates:** `CAPTURE_STATUS` events reach the main loop, and the screen only redraws characters that changed.

**When dvgrab exits unexpectedly:** if the device is still present, restart it after 2 s. If dvgrab keeps exiting, show `Capture Error`.

**Device removed:** stop dvgrab with SIGINT, then SIGKILL after 3 s. Then clear the device name, show `Please Wait`, then `No Device Found`, and resume polling.

**The app must do this itself.** dvgrab-dte has a bug in its bus-reset handling, so it **probably hangs** when the camera is unplugged instead of exiting. The app can't wait for dvgrab to notice the camera has gone. SIGINT still closes the file cleanly.

**dvgrab binary architecture.** The repo's kernel is 64-bit (`v8`), so the fork is rebuilt natively for arm64 on the Pi (dvgrab plan, step 8). Installing 32-bit ARM libraries to run the current binary is only a fallback.

**Camera clock.** `--timestamp` uses the date recorded by the camera. dvgrab uses the Pi's clock only when the stream has no date. The Pi has no network and may have no real-time clock, so its time can be wrong. Check during Phase 0 whether the CM4 host board has an RTC.

### 4.4 Display (`hardware/lcd.py`, `ui/*`)

- **Driver:** RPLCD in 4-bit GPIO mode (`RPLCD.gpio.CharLCD`).
- **Pins:** RS=4, E=17, D4–D7=22, 23, 24, 25. RW is tied to GND.
- **Frame buffer:** the LCD class keeps a 16×2 buffer and only writes cells that changed. This keeps the timecode updates free of flicker.

**Custom character slots.** The HD44780 has only 8 slots, and rewriting a slot changes every place that character is shown. The plan:

| Slot | Glyph |
|---|---|
| 0 | record ● |
| 1 | pause ‖ |
| 2 | play ▶ |
| 3 | storage. The glyph is swapped between SD, USB and internal (new glyph). |
| 4 | battery. The glyph is swapped between full, med, low and empty. |
| 5–7 | spare |

The solid block for the `range` bars uses the built-in ROM character `0xFF`, so it needs no slot.

**Screen layouts** (columns are 1-based):

```
Capture   |DV  Sony HVR- SB|      1–3 format, 5–13 device, 15 storage, 16 battery
          |● REC   00:45:12|      1 icon, 2–7 status, 9–16 timecode
Idle      |No Device Found |
          |              SB|      storage + battery icons still shown
Wait      |Please Wait     |
Play list |Select File:    |
          |10-11-2026 14:22|      see "File names" below
Playback  |10-11 14:22   SB|      1–13 file name
          |▶ PLAY  00:00:00|
Range     |LCD Brightness  |
          |████████        |
Confirm   |Are you sure?   |
          |No              |
```

**File names** (answer 4). dvgrab-dte names files `<prefix>-DD-MM-YYYY_HH-MM-SS.<ext>`, for example `Sony_HVR-A1E-10-11-2026_14-22-01.m2t`. This needs a change to the fork (dvgrab plan, §3.5 step 4). The app reads the date and time from the name and formats it to fit, using `-` as the separator to match the file name:

| Where | Width | Format | Example |
|---|---|---|---|
| Play list, row 2 | 16 | `DD-MM-YYYY HH:MM` (exactly 16) | `10-11-2026 14:22` |
| Playback, row 1 | 13 | `DD-MM HH:MM` | `10-11 14:22` |

**Takes started in the same minute.** Seconds don't fit in the normal format, so two takes started in the same minute would look the same. For those files only, the screens switch to a format that includes seconds:

| Where | Format | Example |
|---|---|---|
| Play list | `DD-MM HH:MM:SS` (14 characters) | `10-11 14:22:01` |
| Playback | `DD-MM HH:MM:SS`, which is 14 characters, so the end is cut off to fit 13 | `10-11 14:22:0` |

Takes started in the same second already have different names, because dvgrab adds `-2`. The list shows them as `10-11 14:22:01 2`, which fits in 16 characters.

The list is sorted by the parsed date, newest first, because `DD-MM-YYYY` names don't sort by date alphabetically.

Files without a timestamp in their name fall back to the end of the file name.

The formatting is in one function, `format_filename(name, width)`. A `filename_display` setting can be added later to choose the format, with long names scrolling.

### 4.5 Brightness and contrast (`hardware/backlight.py`)

- **PWM:** GPIO12 and GPIO13 are the two hardware PWM channels. Add `dtoverlay=pwm-2chan,pin=12,func=4,pin2=13,func2=4` to the boot config and drive the channels with `rpi-hardware-pwm` (via sysfs). This avoids the jitter of software PWM.
- **Duty cycle:** `value / 16`. Brightness is clamped to at least 1, so the screen can't be turned fully dark by mistake.
- **Hardware notes:**
  - Contrast (V0) needs a **RC low-pass filter** after the PWM pin, or the contrast will flicker or shimmer.
  - On an HD44780, a *lower* V0 voltage gives *higher* contrast. The code may need to invert the value so turning the encoder right makes the text darker. Calibrate on the device.

### 4.6 Rotary encoder and record trigger

**GPIO allocation** (BCM numbers; header pins assume the standard 40-pin layout, so check them against your CM4 host board):

| GPIO | Header pin | Use | Status |
|---|---|---|---|
| 12 | 32 | PWM brightness | spec |
| 13 | 33 | PWM contrast | spec |
| 4 | 7 | LCD RS | spec |
| 17 | 11 | LCD EN | spec |
| 22 | 15 | LCD D4 | spec |
| 23 | 16 | LCD D5 | spec |
| 24 | 18 | LCD D6 | spec |
| 25 | 22 | LCD D7 | spec |
| 26 | 37 | Encoder A | spec |
| 20 | 38 | Encoder B | spec |
| 5 | 29 | Encoder switch | spec |
| **6** | **31** | **Standalone record button** (active low, internal pull-up) | **new** |
| **16** | **36** | **LANC record input from the Arduino** (reserved) | **new** |
| **27** | **13** | Record tally LED (optional, reserved) | **new** |

These avoid I2C (2/3), UART (14/15), SPI0 (7–11) and the ID EEPROM pins (0/1).

**Encoder:** gpiozero `RotaryEncoder(26, 20)` and `Button(5, hold_time=2)`, using the `lgpio` backend that is the default on Bookworm.

**Record trigger.** Both modes produce `RECORD_ARM` and `RECORD_DISARM` events. The capture service turns these into `SIGUSR1` (arm) and `SIGUSR2` (disarm).

- **Standalone:** `Button(6)`. Each press toggles between arm and disarm.
  - It only works when a device is connected and storage is ready.
  - Presses are debounced, and presses within 1 s of the last toggle are ignored.
- **LANC:** `DigitalInputDevice(16)`. The **level** decides the state (answer 2): HIGH = recording, LOW = standby.
  - The pin is debounced for about 50 ms.
  - A missed edge can't leave things out of step: the level is also checked once a second, and resent after every dvgrab `ready` event.
  - **Mode changes:** the settings menu can only be opened in STBY, and the mode is saved on click. On save, the app stops dvgrab and starts it again with the new mode. In `lanc` mode, if the Arduino is already holding the pin HIGH, recording starts as soon as `ready` arrives.
  - The Arduino is 5 V and the Pi is 3.3 V. **Use a level shifter or voltage divider.** A pull-down on the Pi side means a disconnected Arduino counts as standby.

### 4.7 App state machine and button rules

```
            ┌──────────── LONG_CLICK (from list/settings root) / 15 s idle ───────────┐
            ▼                                                                         │
   CAPTURE (default) ── CLICK* ──► PLAYBACK_LIST ── CLICK ──► PLAYBACK ── LONG ──► PLAYBACK_LIST
        │                                                       │ CLICK = pause/resume
        └── LONG_CLICK* ──► SETTINGS_ROOT ── CLICK ──► RANGE / CONFIRM / OPTIONS
                                  ▲                        │ CLICK (or "No") ──┘
                                  └────────────────────────┘
            * only when no device is connected, or the device is in STBY
```

**Long press (2 s) on each screen.** This follows the spec, `ai_spec.txt:85` and `:109`:

| Screen | Long press does |
|---|---|
| Capture (no device, or STBY) | Open settings |
| Capture (REC) | Nothing |
| Playback list | Return to capture |
| Playback | Stop playback and return to the list |
| Settings menu, `range`, `confirm`, `options` | **Return to capture**. Any unsaved `options` choice is discarded. |

- **While recording:** the encoder button is ignored in capture mode.
- **Idle timeout:** after 15 s with no encoder input in playback or settings, the app returns to capture. The timer doesn't run while a file is actually playing (answer B4).
- **Background capture:** dvgrab keeps running while the user is in playback or settings, so a recording started from the camera is still captured. If capture switches to REC, the UI jumps straight back to the capture screen. Confirmed (answer 5).

### 4.8 Playback (placeholder)

- **File list:** files in the active storage's `Videos/` with the extensions `.dv`, `.m2t` and `.avi`, sorted newest first. Scrolling moves through the list, which wraps at each end.
- **Playback screen:** the screen is built and pause/resume works, but the timecode is a dummy counter. The actual output (HDMI or FireWire) will be added later through a `Player` interface with a no-op version for now.
- **Clash with capture:** FireWire playback later will conflict with dvgrab, because both use the device. The `Player` interface includes a hook to pause capture first.

### 4.9 Battery

`services/battery.py` reports `FULL` every 60 s. The display already uses the battery level, so the real monitor can replace this later without changes elsewhere.

---

## 5. Deployment

**Target OS** (answer B1): Raspberry Pi OS **Bookworm Lite, 64-bit**, built with pi-gen at commit `48efb5f` up to stage 2. That commit is on pi-gen's `arm64` branch (June 2024, kernel 6.6, Python 3.11).

- **Stay on Bookworm.** The custom FireWire kernel in `kernel/64-Bit/6.6.44-*` was built for it. Moving to a newer release (Trixie) would mean rebuilding that kernel, so it's out of scope here.
- **Optional, in Phase 8:** you already build the image with pi-gen, so `setup.sh` could become a custom pi-gen stage (`stage-dte`). That stage would install the kernel, boot config, packages, dvgrab-dte, the app and the service. Every image would then boot straight into a working recorder, without running anything on the Pi.

- **Service:** `deploy/dte.service`, a systemd unit that runs as user `dte` with `WorkingDirectory=/home/dte/dte-python` and `Restart=always`. It replaces the current "run start.py on boot" setup.
- **Python environment:** a virtual environment created with `--system-site-packages` (Bookworm enforces PEP 668).
- **Packages:**
  - apt: `python3-lgpio python3-gpiozero python3-rpi.gpio exfatprogs dosfstools`.
    - **RPLCD imports `RPi.GPIO`**, so it's listed explicitly.
    - pi-gen stage 2 already installs `python3-rpi.gpio` and `python3-gpiozero`, but not `python3-lgpio`.
    - RPi.GPIO (used by the LCD) and lgpio (used by gpiozero for the encoder and buttons) can run together because they use different pins.
  - pip: `RPLCD rpi-hardware-pwm`
- **Users and groups:** `dte` is a member of `gpio` (GPIO access), `video` (FireWire, see below) and `plugdev`.
- **FireWire device permissions** (`deploy/99-dte-firewire.rules`). By default only root can open `/dev/fw*`, and dvgrab needs both the camera's node and the Pi's own controller node. Without this rule, the service fails as user `dte`:

  ```
  SUBSYSTEM=="firewire", KERNEL=="fw*", GROUP="video", MODE="0660"
  ```

- **Realtime priority for dvgrab.** dvgrab asks for realtime scheduling (`SCHED_RR`), a raised priority and locked memory, but **silently carries on without them** if it's not allowed. The unit grants them with:

  ```
  LimitRTPRIO=99
  LimitNICE=-20
  LimitMEMLOCK=infinity
  ```

  Alternatively, use `AmbientCapabilities=CAP_SYS_NICE CAP_IPC_LOCK`. Phase 0 checks that dvgrab really gets `SCHED_RR`, using `chrt -p`.
- **Power-loss safety** (battery powered):
  - dvgrab flushes data to disk every 2 s (`--sync-interval`).
  - Also lower `vm.dirty_expire_centisecs` and `vm.dirty_writeback_centisecs` to about 100 (1 s) in `/etc/sysctl.d/`.
  - Keep raw `.dv`/`.m2t` output and never AVI, whose index is only written when the file is closed.
  - **Optional, later:** a read-only or overlay root filesystem to protect the OS, and a low-battery shutdown once the battery hardware is known.
- **Sudoers:** passwordless `systemctl reboot`, `mount` and `umount` for user `dte`, limited to the exact commands.
- **`setup.sh`:**
  - Adds the FireWire kernel and `pcie-32bit-dma` overlay (from the README) and the PWM overlay to the boot config. On Bookworm the file is `/boot/firmware/config.txt`.
  - Installs the dvgrab dependencies.
  - Sets the unit to start on boot.

---

## 6. Phased delivery

Each phase finishes with something that works and can be tested. Phases 1–5 can be built and tested in the simulator on WSL. Phases 0 and 8 need the Pi. Phase 0b (the dvgrab fork) is built on WSL and finished on the Pi.

| # | Phase | Deliverables | Done when |
|---|---|---|---|
| 0 | **Hardware spikes** (on the Pi) | Short scripts: (a) list `/sys/bus/firewire/devices` with a camera connected, recording the attributes on `fwN` **and** `fwN.0`; (b) build dvgrab-dte on the Pi (arm64), and measure the current binary's CPU use and stderr line rate; (c) light the LCD with RPLCD on the spec pins; (d) check PWM on 12/13; (e) check whether the host board has an RTC; (f) check `/proc/config.gz` for `exfat`/`vfat`/`usb-storage`; (g) run dvgrab as user `dte` with the udev rule and systemd limits, and confirm it can open `/dev/fw*` and runs under `SCHED_RR` | Sysfs attributes recorded; dvgrab builds and runs as non-root; filesystems available; pins confirmed |
| 0b | **dvgrab fork** | Everything in the [dvgrab plan](../../dvgrab/json-status-output/plan.md). Can be built on WSL alongside Phases 1–2. | Camera checklist in the dvgrab plan passes; JSON samples saved to `tests/fixtures/` |
| 1 | **Foundation** | Package layout, `pins.py`, JSON config with migration and atomic writes, event queue, logging to `~/.dte/dte.log`, simulator LCD and input | `DTE_SIM=1 ./start.py` shows the idle screen; config tests pass |
| 2 | **Drivers** | LCD frame buffer and glyph slots (glyph bug fixed), backlight PWM, encoder events, record trigger | Encoder events are logged on the Pi; brightness and contrast follow the config |
| 3 | **Services** | FireWire monitor, storage monitor (mounting, priority, switch delayed until STBY), capture wrapper (JSON reader, signals), fake dvgrab, battery stub | Reader tests pass on the Phase 0b samples; plugging and unplugging is handled in the simulator |
| 4 | **Capture UI and state machine** | Capture, idle, wait and error screens; the full plug/unplug lifecycle; button rules while recording | A full record cycle works on the Pi in `auto` mode |
| 5 | **Settings** | Root menu, `range` (live), `confirm`, `options` (record mode, which restarts capture), factory reset, 15 s timeout | Every menu path works; reset reboots to defaults |
| 6 | **Playback (placeholder)** | File list, playback screen, pause/stop, `Player` interface | Navigation matches the spec |
| 7 | **Record modes** | Standalone button on GPIO6, LANC level input on GPIO16 (testable with a jumper wire to 3.3 V), optional tally LED | Standalone start/stop and the LANC level both produce one file per take on the Pi |
| 8 | **Deploy and harden** | systemd unit, sudoers, `setup.sh`, README, old prototype files deleted (answer B6), disk-full handling, watchdog restart; optional pi-gen `stage-dte` | Cold boot → recording with no keyboard attached |

### On-device acceptance checklist

- [ ] Boot with no camera → `No Device Found`
- [ ] Plug in the camera → name, format and storage icon appear; STBY
- [ ] Camera records (auto) → `● REC` and the timecode advances; the file appears in the correct `Videos/`
- [ ] Unplug the camera mid-recording → the file is closed and playable; `Please Wait` → idle
- [ ] Two cameras connected → only the first is used; unplug it → the second is picked up
- [ ] A camera with no vendor/model → files named `dte-capture-*`
- [ ] Plug in USB with no camera → it switches to USB straight away, and the icon changes; remove it → back to internal
- [ ] Plug in USB with a camera in STBY → `USB Found / Switch? No`; Yes switches; No or 15 s keeps internal; then unplug the camera → it switches to USB on its own
- [ ] Plug in USB while REC → recording continues on internal, and the prompt appears at the next STBY
- [ ] Camera starts recording while the prompt is open → back to the capture screen; the prompt returns at the next STBY
- [ ] Remove the USB drive being recorded to → capture stops immediately and switches to internal
- [ ] An exFAT drive and a FAT32 drive both work; a take over 4 GB on FAT32 is split into several files
- [ ] An ext4 or NTFS drive → `USB Not Supported`, and recording stays on internal
- [ ] Files are named `<prefix>-DD-MM-YYYY_HH-MM-SS.<ext>`, and the play list shows `DD-MM-YYYY HH:MM`
- [ ] LANC mode: GPIO16 HIGH → REC, LOW → STBY
- [ ] Every take is its own file, closed within 0.5 s of STBY or disarm; an HDV camera other than the Sony A1 also splits correctly (if one is available)
- [ ] Unplug the camera during REC → the app SIGINTs dvgrab, and the file is closed and playable
- [ ] Pull the power during REC → no more than about 2 s of the take is lost, and the OS boots normally
- [ ] Disk full or USB pulled mid-write → `Storage Full` or `Please Wait`, and dvgrab exits cleanly (no SIGABRT in the log)
- [ ] The service runs as `dte`, not root; dvgrab runs under `SCHED_RR` (`chrt -p`)
- [ ] Long press on the range, confirm and options screens returns to capture
- [ ] The encoder button is ignored while recording
- [ ] Click → playback list; 15 s idle → back to capture
- [ ] Hold 2 s → settings; brightness and contrast change live, and the value is kept after a reboot
- [ ] Factory reset → No does nothing; Yes reboots with the defaults
- [ ] Standalone mode → GPIO6 button starts and stops recording; the camera's own record button is not required

---

## 7. Open questions

### Answered (2026-11-10)

| # | Question | Decision |
|---|---|---|
| A1 | Where is the dvgrab fork? | `~/workspace/personal/dvgrab-dte` (the DTE fork). JSON output is added there; see the dvgrab plan. `~/workspace/personal/dvgrab` stays separate, and nothing is merged into it. |
| A2 | LANC: pulse or level? | **Level**, HIGH = recording. A pulse could be missed. |
| A3 | Storage added during REC? | Adding storage doesn't interrupt the recording; the switch waits for STBY. **Removing the storage in use stops the recording immediately.** |
| A4 | File names on the LCD? | Date and time (dvgrab `--timestamp`), with the date as **`DD-MM-YYYY`** in both the file name and the LCD. A display-format option with scrolling may come later. |
| A5 | REC while in menus → jump back to capture? | Yes. |
| — | Idle wording | `No Device Found` |

### Answered, second round (2026-11-10)

| # | Question | Decision |
|---|---|---|
| B1 | OS | pi-gen `48efb5f` (`arm64` branch), stage 2 = **Bookworm Lite 64-bit**. dvgrab-dte is rebuilt for arm64. Can be upgraded later; see §5. |
| B2 | Standalone record button | **Toggle:** one press starts recording, the next press stops it. |
| B3 | Where `record_mode` is set | In the **settings menu** (`options` template). |
| B4 | Idle timeout during playback | Not while a file is playing. It applies on the file list, the settings screens and when playback is paused. |
| B5 | USB filesystems | **exFAT and FAT32**, both supported. FAT32 files are split at 4 GB. |
| B6 | Delete old prototypes | Yes, in Phase 8. They stay in git history. |
| B7 | DV/HDV before dvgrab starts | Blank until dvgrab's `ready` event. |

| B8 | Record button pin | **GPIO6 (pin 31) is free** and confirmed for the standalone record button. |
| B10 | Record light pin | **GPIO27 (pin 13) is free.** |
| B9 | Switching to newly added storage with a camera connected | **Only after the user confirms** with a Yes/No prompt (`USB Found / Switch? No`). With no camera connected, it switches on its own. See §4.2. |

### Still open

- None. GPIO27 (pin 13) is confirmed free for the optional record light (answer B10).

---

## 8. Review log

A devil's-advocate review on 2026-11-10 checked this plan and the dvgrab plan against the source code and platform documentation. The key claims were spot-checked again by hand. Corrections in this plan:

- **exFAT mount:** `flush` isn't an exFAT option and would have made every exFAT mount fail. Options are now different for vfat and exFAT.
- **File size limit:** dvgrab splits files at 1 GB by default. `--size` is now set for each storage type.
- **USB detection:** `lsblk` sets `TRAN` only on the disk, and disks without partitions also need handling.
- **Shutdown signals:** SIGTERM is the same as SIGINT in dvgrab, so the sequence is now SIGINT → SIGKILL.
- **Camera unplug:** dvgrab probably hangs, so the app must SIGINT it.
- **Signals:** none are sent before `ready`.
- **Process setup:** stdin is `DEVNULL`, with separate stdout and stderr pipes.
- **Timecode:** `elapsed` is shown when there's no timecode.
- **Same-minute takes:** shown with seconds. The earlier counter example didn't fit.
- **Long press:** behaviour on the range, confirm and options screens was added (spec line 109).
- **Missing deployment items added:**
  - FireWire udev permissions;
  - realtime limits;
  - RPi.GPIO for RPLCD;
  - `gpio`/`video` groups;
  - a kernel filesystem check;
  - power-loss safety.
- **Glyph bug:** corrected to 7 glyphs, not all of them.
