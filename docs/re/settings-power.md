# Tracker settings, power and maintenance: what VIVE Hub for Windows does

Scope: auto-sleep, power off, reset, reboot, camera frame rate / power frequency, log collection, and how a firmware
update is triggered (documented only, no flasher). Source: VIVE Ultimate Tracker 1.2.7 for Windows
(`ViveTrackerServer.exe` 1.1.4.30, `vive_tracker_driver.dll` 1.0.7.98, `UTCollectLog.exe`, `UTLogRetriever.exe`).

**Method and confidence.** Static analysis only (PE imports, strings, x86-64 disassembly of the call sites). Nothing was
run and no traffic was captured. Tags: **[code]** read directly from disassembled code, **[string]** from log/format
strings, **[inferred]** our reading, not confirmed. Only function names, message names and byte values are recorded here,
no HTC code or assets. HTC binaries stay out of git. See the licensing note at the end.

## 1. Layers

```
VIVE Hub shell ──\\.\pipe\VIVEHUB_DEVICE_MANAGE (JSON CmdType)──▶ ViveTrackerServer.exe (OETServer)
tracker_setup*.exe ──\\.\pipe\TrackerNamedPipe───────────────────▶   │
VBP service channel (encrypted JSON, remote)───────────────────────▶   │  calls
                                                                       ▼
                                          vive_tracker_driver.dll  (HIDManager → one object per tracker)
                                            ├─ TrackerOnWifi   TCP, 128-byte frames          (this doc §3)
                                            ├─ TrackerOnDongle same strings via dongle HID   (§3, inferred)
                                            └─ TrackerHID      USB feature reports           (§4)
```

`vive_tracker_driver.dll` exports one C function per feature, each a thin wrapper: look up the tracker in
`HIDManager`, then call a virtual method of the per-transport class **[code]**. The transport decides the bytes.

## 2. Hub-to-server commands (`VIVEHUB_DEVICE_MANAGE`)

`OETServer::ParseJsonDataFromVHServer` reads `CmdType` from a JSON object and dispatches on it with a 27-entry jump
table **[code]**. Requests are numbered 1 to 27; responses come back with `CmdType` 213 and up and echo `CmdKey`
(a request correlation string) plus `Result` (0 = ok).

| Request | Handler | Extra JSON keys | Response `CmdType` |
|---|---|---|---|
| 1 | Login callback (`ErrorCode`) | `ErrorCode` | none |
| 10 / 11 | create / destroy device | | |
| 12 | identify | | |
| 13 | power off one tracker (`PowerOffDeviceAndResponse`) | `DeviceIndex` | 213 (0xD5) |
| 14 | get device info | | |
| 15 | pair on dongle | | |
| 18 | start tracker firmware update | | |
| 19 | start dongle firmware update | | |
| 20 | factory reset tracker (`FactoryResetTrackerAndResponse`) | `DeviceIndex` | 220 (0xDC) |
| 21 | power off all trackers | | 221 (0xDD) |
| 22 | set camera frame rate on all trackers | `CameraFrameRate` | 222 (0xDE) |
| 23 | assign device name | | |
| 24 | set auto-sleep | `IsAutoSleep`, `AutoSleepTimeout` | 224 (0xE0) |
| 25 | (unmapped; result int) | | 225 (0xE1) |
| 27 | (unmapped; result 0) | | 227 (0xE3) |

2 to 9, 16, 17, 26 are unused (they fall to "Unknown cmd type"). 25 and 27 are the two remaining handlers (`0x5cbb0`,
`0x56520`); the same strings list "start tracker setup" and "reset space calibration" failures, so those are the likely
owners **[inferred]**. The server also reports state back to the Hub with status JSON (`IsAutoSleep`,
`AutoSleepTimeout`, `CameraFrameRate`, `HasNewDongleFW`, `DongleFWVersion`, `HasNewFW`, `FWLastUpdatedTime`,
`BatteryPercentage`, ...) **[string]**.

## 3. Wi-Fi tracker wire format (`TrackerOnWifi`)

Every command is one `send()` of a **128-byte frame** **[code]**:

| Offset | Value |
|---|---|
| 0 | `0x01` (command frame) |
| 1 | length of the ASCII command |
| 2.. | ASCII command, zero-padded to 128 bytes |

Commands seen at call sites **[code]** (fields in angle brackets are decimal ASCII):

| Feature | Command | Notes |
|---|---|---|
| Auto-sleep | `pAS_TS<n>` | `n` from the Hub. Disabled is sent as `pAS_TS0` (server passes 0 when `IsAutoSleep` is false). Unit not confirmed; HTC's docs say 3 minutes, so minutes **[inferred]** |
| Camera frame rate | `ACF<n>` | `n` is the fps number, e.g. `ACF60`. Also sent once at tracker init with the stored rate |
| Reboot | `APR` | `OETServer::RebootTracker(serial)` |
| Power off | `APF` | power state 0 |
| Power on / start | `APS` (state 3), `ATM1` (state 11), `ATM<n>` (other states) | `ATM20` = host/SLAM map mode, `ATM51` = file-transfer mode |
| Set time | `ATS...` | sent at init |
| Start firmware (FOTA) | `AFM<path>` | path of the package already pushed to the tracker |
| Relocate | `pFL1` | |
| Log collection | `ATM51`, `FW2`, `WI`, `FW0`, `ALGM`/`ALGm` sequence | see §5 |

`PowerOffTracker` is `xor edx,edx; jmp [vtable+0x18]` on the tracker object, the same call shape as `SetPowerState(0)`
**[inferred]**, which matches `APF`.

For trackers behind the dongle the same strings are used: `TrackerOnDongle::SetAutoSleep` builds `pAS_TS<n>` and
refuses commands over 15 characters ("CMD EXCEEDS MAXIMUM LENGTH") **[code]**, then sends them through the dongle HID
channel. The HID framing of that channel is not decoded yet.

## 4. USB tracker (`TrackerHID`)

Commands are 64-byte payloads in a 65-byte HID feature report (`HidD_SetFeature`, report ID 0, then
`HidD_GetFeature` for the reply) **[code]**.

- Factory reset: payload starts `FF AF 00`, rest zero **[code]**. Windows only allows it over USB
  (`OETServer::FactoryResetTracker` fails with "NULL USB HANDLE" otherwise).
- Firmware: payload starts `22 A1`, followed by `/sdcard/<package name>` **[code]**.
- Auto-sleep and `AssignDeviceName` over USB: "NOT SUPPORTED" **[string]**.

## 5. Settings stored on the PC: `Config.ini`

Path: `%ProgramData%\HTC\ViveSoftware\ViveUltimateTracker\config\Config.ini`. Despite the name it is **JSON**
(`Fail to read config json`) with one object, `server` **[code]**:

```json
{ "server": { "log_level": 2, "camera_frame_rate": 60, "ignore_force_update": false,
              "is_auto_sleep": false, "auto_sleep_timeout": 0 } }
```

Defaults above are what the server writes when the file is missing (`ignore_force_update` is read but not in the default
set; treat as false) **[code]**. The server rewrites the file whenever the Hub changes auto-sleep or frame rate
(`UpdateConfigFile`). On start it re-applies `camera_frame_rate` to each tracker (`ACF<n>`) and auto-sleep through
`SetAutoSleep` **[inferred from call order; applying on connect not traced]**.
Sibling files: `Trackers.json`, `Calibration.json`, `tracking_info.json`.

## 6. Power frequency

Not found in anything we have. HTC's setting (50 or 60 Hz anti-flicker) lives in the Hub shell's Advanced tab, and
`ViveHubServer`/`VHConsole` were not collected. The only server-side knob that fits is **camera frame rate**
(`CameraFrameRate` on the pipe, `server.camera_frame_rate` default 60, `ACF<n>` to the tracker). Hypothesis: 60 Hz
mains uses `ACF60`, 50 Hz uses `ACF50` **[inferred]**. Needs the Hub component or a hardware test (set 50, check flicker
under 50 Hz light and the status JSON's `CameraFrameRate`). Unrelated: `display_frequency` in `vive_null_headset`'s
`default.vrsettings` is the null headset's refresh rate, not a tracker setting.

## 7. Log collection

Two separate paths:

1. **Wi-Fi, from the server.** `OETServer::StartCollectLog` → `TrackerOnWifi::CollectOetLog`: sets file-transfer mode
   (`ATM51`), exchanges `FW2`/`WI`/`FW0` then `ALGM`/`ALGm` and receives the file over the file-transfer channel
   into `%ProgramData%\HTC\ViveSoftware\ViveUltimateTracker\CollectedLog\` **[code for strings, flow inferred]**. The
   tracker-side source is `/data/sys_log/current/ot_log_*` **[string]**. Triggered by the VBP service channel (remote
   command), not by a numbered Hub command.
2. **USB, from `UTCollectLog.exe`** (the "collect log" button): zips `VUT_LOG`, tracker-setup logs and
   `UTCollectLog_<time>.txt`, then runs `UTWaitDevice.exe` ("connect your tracker via USB") and `UTLogRetriever.exe`
   **[string]**. The retriever:
   - reads `persist.lambda.debuglog` via `adb shell getprop`, sets it to 0 while collecting and restores it **[string]**;
   - old ROMs: pulls `hdlog.tgz` with adb and `adb shell rm` it; new ROMs: HID **GenLog = command 0x56**, poll
     **GetLogStatus = command 0x57** (status 1 = in progress), then **file-size query** (dword `0xFF090010`, name
     `hdlog.tgz`) and block-wise **big-data read with CRC32** into `TrackerLog_<time>_<n>.tgz` **[code]**;
   - reads `ro.htc.release.version` for the ROM version.

## 8. Firmware update: how it is triggered (documentation only)

Tracker (FOTA) **[string/code]**:
1. `FWUpdater::CheckHasNewFOTAPackage` posts a check-in JSON to HTC's FOTA service (Android-style check-in: build
   info, serial, firmware version). Response `reason` `FOTACANCEL_NO_MATCH_RULE` means up to date; otherwise a
   `data_uri` for a package. The request carries static header and device-identifier values; **we deliberately do not
   record them here** and a clean-room client should not copy them.
2. Package downloaded as `update_<...>.zip` to the server's storage folder.
3. `PushPackageToDevice`: `adb -s <serial> push <pkg> /sdcard/`, then `CheckFotaPackageIntegrity` compares size from
   `adb shell ls -l /sdcard/` to the size the service reported.
4. `StartFWUpdate`: USB = HID `22 A1 /sdcard/<name>`; Wi-Fi = `AFM<path>`. Success is judged by the firmware version
   changing (`Tracker::CheckFWUpdateFinished`), with timeout "FOTA TIMEOUT".
5. `Tracker::StartFWUpdate` logs "USB is not connected." and "Wi-Fi FOTA started."; the push step needs adb over USB, so a USB connection looks required even for Wi-Fi trackers **[inferred]**.

Dongle: server unzips the bundled `Dongle_release_*.zip` and runs `USBTool.exe upgrade rfmcuapp DONGLE.ota --ptdongle`
if the packaged version is newer. `USBTool.exe` was not collected.

Packages are vendor-signed and the service is HTC's; **we do not plan to build flashing**. A future tool could wrap
`adb push` plus the two commands above for packages the user already has, with a recovery warning.

## 9. Other power-related behaviour

- Dongle: `OETServer::WakeupDongle` / `SetDongleToPowerSavingMode` (standby when no trackers), cancel pairing, plus
  Linux `RESET_DONGLE` equivalent not yet located in `TriggerDongleMode` **[unverified]**.
- Auto-sleep events reported to the Hub: "entered sleeping (lost tracking)" and "(table static)" **[string]**.
- Remote management: `VBPServiceCenter::ProcessEncryptedData` accepts encrypted JSON commands (reboot, log collect and
  upload). Out of scope for us; do not implement.

## 10. What we can build now, and what needs hardware

| Feature | Plan | Needs hardware first |
|---|---|---|
| Auto-sleep | send `pAS_TS<n>`; keep `Config.ini` format for compatibility | check the unit |
| Power off / reboot | `APF` / `APR` | confirm on Wi-Fi tracker |
| Camera frame rate | `ACF<n>` | which values the firmware accepts; flicker test |
| Factory reset | USB HID `FF AF` | yes, destructive: test on a spare tracker last |
| Log collection | adb path first (`getprop`/pull), Wi-Fi path later | yes |
| Firmware | document only | n/a |

Also: capture TCP between server and a tracker while changing each setting in the Hub; that confirms every table row
in §3 and gives the replies (our static pass saw sends only).

## Licensing note

HTC's EULA reverse-engineering clause has not been reviewed (see the Windows notes). This document contains command
names, byte values and file layouts only.
