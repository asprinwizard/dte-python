# dvgrab fork – JSON status output and record trigger

**Repository:** `~/workspace/personal/dvgrab-dte` (`git@github.com:asprinwizard/dvgrab-dte.git`). This is the DTE fork.
**Base branch:** `master`. Work happens on a new branch, `feature/json-status`.
**Not touched:** `~/workspace/personal/dvgrab`, the general fork, is kept separate on purpose. Nothing is merged into it.
**Used by:** the DTE recorder rebuild (`.documentation/dte-python/recorder-rebuild/development-plan.md`, §4.3)
**Revision 2 (2026-11-10):** updated after the devil's-advocate review (§7).

---

## 1. Goal

The DTE app needs dvgrab to give it five things:

1. **A machine-readable status stream** (JSON, one object per line) with REC/STBY, timecode, format and file events. The LCD shows these.
2. **External start/stop control** for the `standalone` and `lanc` record modes. In these modes the camera isn't recording, so `--recordonly` can't decide when to write.
3. **One file per take, closed as soon as the take ends**, in every mode.
4. **A safe run:**
   - no busy loop;
   - no transport commands sent to the camera;
   - no crash on write errors;
   - no files silently overwritten;
   - data flushed regularly in case the power is cut.
5. **File names dated `DD-MM-YYYY`**, e.g. `Sony_HVR-A1E-10-11-2026_14-22-01.m2t`.

---

## 2. Current state of the fork (checked against the source)

`dvgrab-dte` `master` has the DTE commits `9ec50f8`, `c8994ea`, `240bbd3` and `a39835a` ("Cody tidy for DTE mode") on top of upstream.

| Area | What the fork does now | Problem for the DTE |
|---|---|---|
| **DTE loop**<br>`main.cc:123-126` | `--interactive` has been changed into a "DTE mode". It calls `startCapture()`, then runs `while (!g_done) dvgrab.status();` **with no sleep**. Each pass makes two AV/C requests (`TransportStatus`, `Timecode`) and prints two lines to stderr. | The loop runs as fast as the FireWire bus answers, flooding the bus with requests and stderr with lines. The real CPU use and line rate haven't been measured; measure them on the Pi before and after the fix. |
| **Signal handlers**<br>`main.cc:102-107` | Installed only *after* `DVgrab dvgrab(argc, argv)` has been constructed. | Construction takes a while: it finds the camera, checks for HDV, connects, and in interactive mode sends Pause with a 250 ms sleep. By default **SIGUSR1 ends the process**, so an early signal from the app would kill dvgrab. |
| **`startCapture()`**<br>`dvgrab.cc:520, 628-633` | Holds `capture_mutex` and waits for the first frame. | No status is printed during this wait. If the camera sends no stream, dvgrab gives no sign of life. |
| **`status()`** | Prints `"<transport>" <avc timecode> "<file>" <sec> sec` plus an 80-space line. | The output is meant for people to read. It has no format field. |
| **Write gating**<br>`captureThreadRun()` | With `--recordonly`, frames are written only when the camera reports "Recording" and the timecode isn't 00:00:00:00. The test is `( … \|\| !m_avc \|\| !m_isRecordMode \|\| … )`. | Nothing can gate writes for standalone or LANC. Any new condition has to go **outside** that OR group, because `!m_avc` makes the whole group true. The only other `writeFrame` callers are the `--lockstep` paths (`dvgrab.cc:1001, 1031`), which the DTE doesn't use. |
| **End of a take** (auto mode) | When the camera goes to STBY, frames stop being written, but **the file stays open**. It's closed only when autosplit sees the next take (`filehandler.cc:371-376`) or dvgrab exits. Autosplit needs the frame's new-recording flag or a timecode jump. For HDV, that flag is **only implemented for the Sony A1** (`hdvframe.cc:286`). | Files stay open between takes, so a power cut can lose them. On other HDV cameras, separate takes can merge into one file. |
| **Default file size**<br>`dvgrab.h:44` | `DEFAULT_SIZE 1000` (MiB) | **Every file is split at about 1 GB** (about 5 minutes of HDV) unless `--size` is given. |
| **Transport commands** | The constructor sends Pause when interactive (`dvgrab.cc:120`). `startCapture()` sends Play whenever AV/C is available (`:623`). **`stopCapture()` sends Pause** when interactive (`:674`). `cleanup()` sends Stop unless `--nostop` (`:1325`). In `ieee1394io.cc`, `AVC::Play` and `AVC::Pause` do nothing while the camera is recording, but **`AVC::Stop` has no such check**. Pause and Stop each sleep 250 ms while holding `avc_mutex`. | With today's binary, **every shutdown sends Stop to a camera that may be recording.** In VCR mode, these commands start or stop the tape. |
| **Write errors**<br>`dvgrab.cc:884-888` | On the capture thread, `writeFrame` throws `std::string("writing failed")`, and `captureThreadRun` doesn't catch it. | Disk full or a removed USB drive **aborts dvgrab (SIGABRT)** instead of reporting an error. |
| **Camera unplug** | `ResetHandlerProxy` (`ieee1394io.cc:391-399`) compares `typeid(...) == typeid(void*)`, which is never true, so bus-reset handling never runs. The watchdog it would start has its own bugs: `throw;` with no active exception, and a double `free`. | When the camera is unplugged, dvgrab most likely **hangs** with the file open instead of exiting. A SIGINT still shuts it down cleanly (`cleanup()` → `StopThread`). |
| **Shutdown** | SIGINT, SIGTERM and SIGHUP all just set `g_done`. The destructor calls `cleanup()`, which calls `stopCapture()` and closes the file. Unwinding from a `startCapture` exception also reaches the destructor. | This works. SIGTERM does exactly the same as SIGINT. |
| **Output streams** | stderr is set to `O_NONBLOCK` (`main.cc:98`). When stdin isn't a TTY, `term_init()` makes stdin non-blocking (`io.c:153`). The HDV path prints `printf("PES data overflow!\n")` to **stdout** (`iec13818-1.cc:491`). `--version` prints to stderr. | Lines on stderr can be lost. The stray `printf` would corrupt a JSON stream on stdout. |
| **`--timestamp`**<br>`filehandler.cc:387-405` | Names files `YYYY.MM.DD_HH-MM-SS`, using the date recorded in the stream, or `time()` if there isn't one. `Create` opens with `O_TRUNC` and doesn't check whether the file exists (`:545, 1321`). | The DTE wants `DD-MM-YYYY`. **Two files with the same name overwrite each other silently**, e.g. when the camera clock is reset or the Pi clock is used. |
| **Data durability** | Never calls `fsync` or `fdatasync`. | On power loss, data still in the page cache is lost. |
| **`--buffers 10`** | About 0.33 s of buffering. | Too little to cover USB flash write stalls. The default is 100. |

**Bundled binary:** `dte-python/dvgrab` is a 32-bit ARM build. After this work, a **native arm64 binary** built from this branch on the Pi will replace it.

---

## 3. Design

### 3.1 Options

| Option | Effect |
|---|---|
| `--json` | Status output is JSON Lines on **stdout**, one object per line, flushed after each one. The human-readable messages stay on stderr. Can't be used with raw pipe output (`-` as the file name). |
| `--trigger` | Frames are written only while recording is **armed**. Recording starts disarmed. `SIGUSR1` arms it and `SIGUSR2` disarms it. Repeating a signal has no extra effect. |
| `--passive` | dvgrab never sends AV/C transport commands: no Play, Pause, Stop or Rewind anywhere, **including `stopCapture()`**. AV/C status and timecode queries still happen. This also implies `--nostop`. |
| `--sync-interval N` | `fdatasync` the open file every N seconds while recording. Default 0 (off). The DTE uses 2. |

These existing options are **set by the app**:

- **`--size`:**
  - `--size 4000` on FAT32;
  - `--size 0` (no limit) on exFAT and internal storage.
- **`--buffers 100`.**

The DTE command lines:

```
auto:        dvgrab --guid G --json --passive --sync-interval 2 --buffers 100 --size S --recordonly --autosplit --timestamp --interactive <dir>/<prefix>-
standalone:  dvgrab --guid G --json --passive --sync-interval 2 --buffers 100 --size S --trigger --timestamp --interactive <dir>/<prefix>-
lanc:        same as standalone
```

Trigger mode leaves out `--autosplit`. Takes are already split when recording is disarmed, and an odd timecode in the camera's output stream could otherwise split a take in the wrong place.

### 3.2 Startup and signal rules

1. **Install handlers first.** `main()` installs the SIGINT, SIGTERM, SIGHUP, SIGPIPE, SIGUSR1 and SIGUSR2 handlers **before** creating `DVgrab`.
   - The handlers only store values in global `std::atomic<int>` variables (`g_done`, `g_armRequest`).
   - These are lock-free and safe to use from a signal handler.
2. **Send `ready` early.** After the constructor returns and **before** `startCapture()` waits for the first frame, dvgrab sends `{"type":"ready",…}`.
3. **Status while waiting.** While waiting for the first frame, a helper thread sends `{"type":"status","status":"WAIT",…}` every 1 s, so the app can tell "waiting for a stream" from "hung".
4. **App contract.** The app sends SIGUSR1 or SIGUSR2 **only after `ready`**. It should treat about 30 s without `ready` or any status line as a fault.
5. **Shutdown.** SIGINT starts a clean shutdown. The app escalates **straight to SIGKILL** after 3 s. SIGTERM adds nothing.

### 3.3 Takes and files

All file closing happens **on the capture thread, with `capture_mutex` held**, so no frame can slip in between the check and the close.

- **Gate.** The write condition is `existing_condition && (!m_trigger || armed)`.
- **Take ends.** When the gate goes from open to closed, the take has ended. In auto mode this is the camera going to STBY (the `--recordonly` condition becomes false); in trigger mode it's a disarm. On that edge dvgrab calls `CollectionCounterUpdate()` and `Close()`, then sends `file_closed`.
  - **Auto mode:** each take is closed as soon as it ends. This no longer depends on the HDV new-recording flag, which only the Sony A1 sets.
- **Short disarm/arm.** Every SIGUSR2/SIGUSR1 pair increases an atomic **generation counter**. If the capture thread sees the generation change while still armed (a disarm and re-arm between two frames), it closes the file anyway. Quick off/on presses therefore never merge two takes.
- **HDV start point.** After arming, the first file is only opened on a frame where `CanStartNewStream()` is true, so the file doesn't start in the middle of a GOP (group of pictures).
- **`file_closed` is sent everywhere a file closes:**
  - the take-end edge above;
  - autosplit or size splits, i.e. where `writeFrame` sees `IsNewFile() && !IsFirstFile()` (`dvgrab.cc:891`);
  - `stopCapture()`.
- **No overwriting.** Before `Create`, if the generated name already exists, add `-2`, `-3`, … before the extension.
- **Durability.** With `--sync-interval`, the writer calls `fdatasync` on its file descriptor every N seconds. This is done through a new virtual `FileHandler::Sync()`, implemented for the raw DV and MPEG-2 TS handlers. A file is also synced before it's closed.

### 3.4 JSON events

Every object has a `type` field. **Status objects use exactly the `status` and `timecode` keys from the original spec.**

```jsonc
{"type":"ready","version":"3.5-dte1","format":"HDV","guid":"0x080046010412abcd","trigger":false,"recordonly":true}
{"type":"status","status":"WAIT","timecode":"--:--:--","elapsed":"00:00:00","format":"HDV","file":null,"armed":false}
{"type":"status","status":"STBY","timecode":"00:45:12","elapsed":"00:00:00","transport":"Recording Pause","format":"HDV","file":null,"armed":false}
{"type":"file_open","file":"/home/dte/Videos/Sony_HVR-A1E-10-11-2026_14-22-01.m2t"}
{"type":"status","status":"REC","timecode":"00:45:13","elapsed":"00:00:01","transport":"Recording","format":"HDV","file":"/home/dte/Videos/Sony_HVR-A1E-10-11-2026_14-22-01.m2t","armed":false}
{"type":"file_closed","file":"/home/dte/Videos/Sony_HVR-A1E-10-11-2026_14-22-01.m2t","reason":"take_end","frames":1500,"size_mb":234.5,"dropped":0,"damaged":0}
{"type":"warning","code":"dropped_frames","count":3,"message":"buffer underrun near timecode 00:45:20"}
{"type":"error","code":"write_failed","message":"writing failed"}
{"type":"exit","code":0}
```

**Field meanings:**

- **`status`:**
  - `WAIT` before the first frame;
  - `REC` if a frame was written in the last 500 ms;
  - `STBY` otherwise.
- **`timecode`:** `HH:MM:SS` from the latest frame's timecode, falling back to the AV/C timecode, then `--:--:--`.
- **`elapsed`:** time recorded in the current take. The app shows this when there's no timecode. In standalone and LANC modes the camera isn't recording, so the stream it outputs may not carry a timecode.
- **`file_closed.reason`:**
  - `take_end`
  - `split_size`
  - `split_autosplit`
  - `stop`
  - `error`

**When status lines are sent:** immediately on any change to `status`, `timecode` (to the second), `file` or `armed`. Otherwise once a second as a keep-alive.

### 3.5 Implementation outline

1. **`jsonout.{h,cc}` (new).** A JSON Lines writer:
   - string escaping;
   - a mutex, because several threads call it;
   - `fflush(stdout)` after each line;
   - blocking writes.
2. **`main.cc`.**
   - **Signal handlers before construction**, using `std::atomic`.
   - Send `ready`.
   - The DTE loop calls `status()` and `emitStatus()`, then sleeps 250 ms.
   - After the loop, call `stopCapture()` explicitly and send `exit`.
   - Catch blocks send an `error` event.
3. **`dvgrab.h/.cc`.**
   - Add the new options to `getargs` and the help text.
   - Combine the gate (outside the OR group) with the take-end edge detection, the generation counter and the HDV start-point check, all in `captureThreadRun`/`writeFrame` under `capture_mutex`.
   - Send `file_open` and `file_closed`.
   - **`--passive`** guards every `m_avc->Play`/`Pause`/`Stop`/`Rewind`, **including the one in `stopCapture()`**.
   - **`captureThreadRun` gets a try/catch:**
     1. Close the file.
     2. Send `error`.
     3. Set `g_done`.
     4. End the thread.

     The process then exits cleanly instead of aborting.
   - `emitStatus()` builds the status object.
   - `status()` prints nothing when `--json` is set.
4. **`filehandler.{h,cc}`.**
   - Change the timestamp format to `DD-MM-YYYY_HH-MM-SS`. This also applies to `--timesys`.
   - Add the existing-file suffix check before `Create`.
   - Add the virtual `Sync()`, plus the sync timer in `WriteFrame`.
5. **`iec13818-1.cc:491`:** change `printf` to `fprintf(stderr, …)`.
6. **Version:** add the `-dte1` suffix. Update `dvgrab.1` and `--help`.

**Not in scope:** fixing the bus-reset and watchdog code. The app detects camera removal through sysfs and sends SIGINT, which works. The `typeid` bug is noted in §2 for later.

### 3.6 What the app relies on

- **Signals, not keypresses:**
  - **Standalone button:** the app keeps track of armed/disarmed and sends SIGUSR1 or SIGUSR2.
  - **LANC level:** an edge sends the matching signal. The current level is also resent once a second and after every `ready`.
- **Process setup:**
  - `stdin=DEVNULL`.
  - **Separate** stdout and stderr pipes.
  - stdout carries JSON only. stderr goes to `~/.dte/dvgrab.log`.
- **Privileges:** realtime scheduling and `mlockall` need privileges, which the app's systemd unit provides (main plan §5). The current code ignores these failures, so a non-root dvgrab runs **without** realtime priority and doesn't say so.

---

## 4. Build and test

### 4.1 Building

- **Dependencies** (WSL and the Pi): `build-essential autoconf automake libtool pkg-config libraw1394-dev libavc1394-dev libiec61883-dev libdv4-dev`
- **Commands:** `./bootstrap && ./configure && make`
- **Deploying:** build natively on the Pi (arm64), copy `dvgrab` into `dte-python/`, and record the commit hash in `dte-python/dvgrab.version`.

### 4.2 Testing on WSL (no FireWire)

dvgrab can read from a pipe: `-input -`. With file input, camera discovery is skipped, so there's no AV/C and `--noavc` isn't needed. `--recordonly` is always open in this setup, so the pipe tests cover `--trigger`, not auto mode.

- **DV:** `cat sample.dv | ./dvgrab -input - --json --trigger --sync-interval 2 out-`
- **HDV:** `cat sample.m2t | ./dvgrab -input - -f mpeg2 --json --trigger out-`
  - `-f mpeg2` is needed because the `out-` name has no extension, which defaults to raw DV.

**Signal test script.** A `pytest` script sends `kill -USR1`/`-USR2` (including a quick USR2→USR1 within 50 ms), then checks:

- only armed sections are written;
- each take is a separate file, with no merged takes and no one-frame stray files;
- HDV files start on a GOP;
- name clashes get `-2` instead of overwriting;
- the JSON output parses;
- `file_closed` appears for every file.

**Write-failure test.** Write to a small, full tmpfs: dvgrab sends `error` and `exit` and doesn't abort.

**Limits:** the non-interactive path never runs the 250 ms status loop, and `--interactive` is rejected with `-input -`. Status keep-alives and auto mode can only be tested on the Pi.

### 4.3 On the Pi (with a camera)

- [ ] Measure the current binary's CPU use and stderr line rate (the starting point)
- [ ] `ready` arrives before the first frame, and `WAIT` keep-alives arrive while no stream is coming
- [ ] SIGUSR1 sent right after `ready` doesn't kill dvgrab
- [ ] `ready` shows the correct `format` for a DV camera and for an HDV camera
- [ ] **auto:** camera REC → `file_open` + `REC`; camera STBY → `STBY` **and `file_closed` (`take_end`) within 0.5 s**; test with a non-A1 HDV camera if one is available
- [ ] **standalone:** SIGUSR1/SIGUSR2 make one file per take, without touching the camera; `elapsed` advances even when there's no timecode
- [ ] **passive:** no transport commands are sent at startup, take end, SIGINT or shutdown; a camera in VCR mode is never started or stopped
- [ ] CPU use while idle is under 5%
- [ ] SIGINT during REC → `file_closed` then `exit`; the file plays in VLC/ffprobe
- [ ] Unplug the camera during REC → record what dvgrab does (expected: it hangs); then SIGINT closes the file cleanly
- [ ] Pull the USB drive during REC → `error` + `exit`, not SIGABRT
- [ ] Pull the power during REC → no more than about 2 s of the take is lost
- [ ] Long take on FAT32 (`--size 4000`) splits into numbered files with no gaps

---

## 5. Steps

| # | Step | Est. |
|---|---|---|
| 1 | Create the `feature/json-status` branch from `master` in `dvgrab-dte` | small |
| 2 | Set up the build on WSL | small |
| 3 | `jsonout` + `--json` + early signal handlers + `ready`/`WAIT`/`exit`/`error` | small |
| 4 | Fix the DTE loop, `emitStatus`, catch errors on the capture thread, move the stray `printf` to stderr | medium |
| 5 | Gate, take-end close, generation counter, HDV start point, `file_open`/`file_closed` everywhere | **large** |
| 6 | `--trigger` + SIGUSR1/2 | small (after 5) |
| 7 | `--passive` (all five transport command sites) | small |
| 8 | Timestamp format, name-clash suffix, `Sync()` + `--sync-interval` | medium |
| 9 | Pipe tests on WSL, help text, man page, version | small |
| 10 | Build on the Pi + run the camera checklist; copy the arm64 binary into `dte-python` | needs hardware |

---

## 6. Open questions

1. ~~**Two repos.**~~ **Answered:** `dvgrab-dte` is the DTE fork. `dvgrab` stays separate.
2. **Plain `--interactive`.** Should the original keyboard mode be restored and the DTE behaviour moved behind a `--dte` flag? *Assumption: no. Leave `--interactive` as it is to keep this change small.*

---

## 7. Review log

A devil's-advocate review on 2026-11-10 checked revision 1 against the source. Corrections made in this revision:

- **Missing settings:** the default `--size 1000` was missed. Fixed by having the app set `--size`.
- **`--passive` gap:** it missed the Pause in `stopCapture()`, and the Stop in `AVC::Stop` has no check for a recording camera.
- **`file_closed` gap:** it was only sent from `stopCapture()`.
- **Open files between takes:** in auto mode a take stayed open until the next one started.
- **Signal race:** SIGUSR1 could arrive before the handler was installed and kill dvgrab.
- **Disarm race:** closing on disarm ran on the main thread, so takes could merge or a stray one-frame file could appear.
- **Write errors:** a write failure aborted dvgrab instead of reporting an error.
- **Overwritten files:** `--timestamp` names could overwrite each other.
- **Power loss:** data was never synced to disk.
- **Busy loop:** CPU use and line rate were stated as fact without being measured.
- **WSL testing:** the pipe test notes were corrected (`--noavc` isn't needed, and `-f mpeg2` is needed for HDV).

---

## 8. Implementation status (2026-11-10)

Steps 1–9 are done on `feature/json-status` in `dvgrab-dte`. Nothing is committed yet. Step 10 (Pi build + camera checklist) is still to do.

Tested on WSL against a 12 s PAL DV clip piped in (`tests/pipe_test.py`, 10 tests, passed 6 runs in a row):
- trigger takes, including a 50 ms disarm/re-arm, with one file per take and `file_closed` for each;
- SIGUSR1 while the object is still being built doesn't kill dvgrab;
- an existing file name gets `-2` and the original isn't touched;
- size splits report `split` for each file;
- a write failure (forced with `ulimit -f`) gives `error`/`write_failed`, the file closed with reason `error`, and a normal `exit` (no SIGABRT);
- SIGINT in the middle of the stream exits within 5 s;
- the JSON parses and `--version` reports `3.5-dte1`.

**Not testable without a camera:** auto mode (`--recordonly`), `--passive`, the 250 ms DTE loop, WAIT keep-alives while waiting for a stream, HDV start points, CPU use and unplugging the camera.

**Extra bugs found and fixed while testing:**
- **`DVgrab::done()`:** it treated any interrupted sleep as "stop", so the first SIGUSR2 ended the whole capture. It now returns `g_done`.
- **`pipeReader::StopThread()`:** it didn't wake the capture thread, so stopping before the end of a pipe hung forever. This existed upstream and only affects pipe input. It now calls `TriggerAction()` like the FireWire reader does.
- **`set_format_from_name()`:** it looked for the extension anywhere in the path, so a dot in a folder name gave "Unknown filename extension". It now only looks at the file name.
- **Status after a take:** status could say REC with no file for up to 500 ms after a take closed. It now switches to STBY immediately.

**Build note:** `<atomic>` and `<mutex>` need C++11. GCC 12 on Bookworm defaults to C++17, so `configure` needs no changes.
