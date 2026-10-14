# VIVE Hub for Windows 1.2.7: pairing, unpairing and tracker status

Live cross-check (2026-10-14, three trackers on the dongle, see `vivehub-windows-live-crosscheck.md`) has been folded in: device index 0xFE, the watchdog behavior, slot status values and the battery formula are now confirmed; the `Trackers.json` key list is corrected.

Scope: how `vive_tracker_driver.dll` (1.0.7.98) and `ViveTrackerServer.exe` (1.1.4.30) pair and unpair trackers and report
battery, connection and tracking state. Compared with the public USB HID work (`shinyquagsire23/vive_ultimate_tracker_re`,
`nijkah/pyvut`). Read as prior-art cross-reference only; nothing here is copied from either.

Method: static only. PE exports, `strings`, and x86-64 disassembly of specific functions (Capstone, found by the log
strings each function prints). Nothing was run and no dongle was attached, so **every packet layout below is read from
code and still needs a capture to confirm.** Labels: **[code]** = read directly in the disassembly; **[strings]** = only
a log or JSON key name; **[match]** = agrees with pyvut's independently found enum; **[guess]** = our inference.
Addresses are RVAs in the DLL (`dll+0x...`) or the server (`srv+0x...`). HTC binaries are not committed.

## 1. Summary

1. **Pairing is a dongle command, not a tracker command.** The PC sends one 64-byte HID feature report to the dongle,
   command `0x1D` ("request RF change behavior"), with a behavior byte and a per-slot mask. Pair = behavior 0, unpair =
   behavior 6, power saving = 1, restart RF = 2, factory reset = 5. [code][match] This is the same command pyvut calls
   `DCMD_REQUEST_RF_CHANGE_BEHAVIOR` and the same behavior numbers.
2. **The dongle has five slots** and reports each slot's state in a 4-byte record: status byte, 16-bit timeout in ms, and
   a flag byte with seven named bits (power saving, exist-in-DB, pairing, connecting, RF connected, send-IMU-to-USB,
   handling-FOTA). [code] pyvut's "pair state" words (`0x320fc008` and so on) are exactly these records read as
   little-endian u32. [match]
3. **Windows adds one thing pyvut lacks: the PC chooses which slots to touch.** The "pair" packet carries a mask of the
   currently **empty** slots (built from a fresh `0x1E` status query), the "unpair" packet carries a one-hot slot.
4. **Battery and charging ride inside the tracker data stream**, two bytes per report: bit 6 is charging, the low six
   bits times two is the percentage; bit 7 switches the byte to pogo-pin accessory status instead. [code]
5. **Tracker identity and mode arrive as text indications** (`NADS`, `NASS`, `NASI`, `NAPI`, `NAV1`, `NARI`, `NAGN`, `NADN`,
   `NADI`, `NAZZ`), parsed by one function with a name-to-id table. [code] Matches pyvut's `ACK_*` names with an `N` prefix.
6. **The server turns all of this into JSON** with stable key names (section 6) for the VIVE Hub shell and the setup
   wizard. Those keys are the cleanest template for our own status model.

## 2. Transport and report framing

Dongle: USB `0bb4:0350` (from the Linux notes). Windows opens HID interfaces through `HIDManager`, which listens for
device arrival with `RegisterDeviceNotification`, logs `Tracker dongle is detected.`, `Dongle (%p) is added`, then
`TrackerDongleHID::Initial` reads `InputReportByteLength`, `OutputReportByteLength`, `FeatureReportByteLength`. [strings]

- Commands go out through `TrackerDongleHID::SendPacketToHID(buf, 0x40)` (`dll+0x3a940`). Packet is 64 bytes plus
  report id 0. In every builder the first byte is the command id and the second is the payload length. [code]
- Replies to feature requests are read back as a 64-byte feature report. The status query loops up to 10 times until the
  reply's first byte equals the command id (`cmp al, 0x1e`, `dll+0x39140`). [code][match: pyvut `send_cmd` does the same]
- Unsolicited input reports are read by `DataDispatchThreadProc` (overlapped `ReadFile`). Byte 0 must be 0
  (`First byte of payload is WRONG!` otherwise), byte 1 is the report type: **0x18 = pair/unpair event**,
  **0x28 = tracker data/indication** (`ParseDonglePayload`, `dll+0x35e40`). [code][match: `DRESP_PAIR_EVENT`, `DRESP_TRACKER_INCOMING`]
- Report 0x1D/0x1E responses carry slot state (section 4). pyvut names these `DRESP_TRACKER_NEW_RF_STATUS` / `..._RF_STATUS`. [match]

## 3. Pairing and unpairing

### 3.1 The packet (`dll+0x43360`, `dll+0x43460`)

```
byte  0   0x1D            command: request RF change behavior
byte  1   0x09            length
byte  2   behavior        0 pair, 1 RX power saving, 2 restart RF, 5 factory reset, 6 clear pairing info
byte  3   enable          1, except 0 for behaviors 5 and 6 when sent in "all" form
byte 4-8  slot flags      one byte per slot 0..4
rest      zero
```
[code] Behavior numbers [match] pyvut `RF_BEHAVIOR_*`. pyvut sends `0, 1, 1, 1, 1, 0, 0` (pair, enabled, slots 0 to 2
on, slots 3 and 4 off) with a hard-coded mask; HTC derives the mask.

There are two builders:

| Form | Used for | Slot flags |
|---|---|---|
| Single slot (`dll+0x43360`, `isAll = false`) | pair or unpair one slot | one-hot: flag *i* is 1 only for the target slot (slot 5 gives an all-zero mask) |
| All slots (`dll+0x43460`, `isAll = true`) | pair all, cancel pairing, power saving | behavior 0 and 3: `!exist_db` per slot (empty slots), after a fresh `0x1E` query. Behavior 1: all ones. Others: `exist_db` per slot |

In the all-slots form behavior 3 is rewritten to 2 on the wire, so "mode 3" in the HTC API means restart RF with the empty-slot mask. [code]
The cached per-slot value at `HIDManager+0x768..0x76c` is `NOT ((flags >> 1) & 1)`, i.e. "slot has no pairing entry". [code]

### 3.2 DLL export and server dispatch

The export `TriggerDongleMode(uint8 slot, int mode, bool isAll)` is a thin wrapper that walks the dongle list and calls
the packet builders. [code, `dll+0x1e680`] The server calls it from `OETServer::PairTrackerWithDongle` (`srv+0x4f610`)
and friends. The pipe command is JSON `CmdType 215 (0xD7)` with `CmdKey`, `DeviceIndex`, `IsPair`; the handler
`OETServer::PairDeviceAndResponse` (`srv+0x4f200`) logs `cmd_key: %s, device_index: %d, is pair: %d` and answers with
`Result`. [code] `OETServer::PairTracker(isPair, deviceIndex)` (`srv+0x4f480`) then treats the index specially:

| `DeviceIndex` | `IsPair` | What the server does | Dongle packet |
|---|---|---|---|
| `0..4` | 1 | `PairTrackerWithDongle` pair | `TriggerDongleMode(slot, 0, false)`: behavior 0, one-hot slot |
| `0..4` | 0 | unpair, then remove the server-side record (`srv+0x46100`) | `TriggerDongleMode(slot, 6, false)`: behavior 6, one-hot slot |
| `0xFD` | any | "Unpair All": loop slots 0..4 and unpair each | one behavior-6 packet per slot |
| `0xFE` (-2) | 1 | start pairing on the dongle (`srv+0x4fb10(1)`) | `TriggerDongleMode(5, 0, true)`: behavior 0, all empty slots. **Live-confirmed** |
| `0xFE` (-2) | 0 | `CancelPairing` (`Cancel pairing on dongle.`) | `TriggerDongleMode(0, 3, true)`: behavior 2 (restart RF), empty-slot mask. **Live-confirmed** |
| `0xFF` | any | `srv+0x4fb10(0)` | `TriggerDongleMode(5, 0, false)`: behavior 0, empty mask [guess: ends pairing] |

[code] for the call arguments; `0xFE` is confirmed on hardware (server log `Pair tracker, isPair: 1, device index:-2`; the dongle's `Pairing` flag was then 1 on exactly the empty slots and back to 0 after `isPair: 0`). The meanings of `0xFD` and `0xFF` are still [guess] from the logs ("Unpair All").
Failure codes returned by `PairTracker` are `0x19` when the dongle call fails. Related: `OETServer::WakeupDongle` ("Wake up dongle") and
`SetDongleToPowerSavingMode` ("Set dongle into standby") most likely use behaviors 2 and 1; the call arguments were not read. [guess]

### 3.3 Events back from the dongle

- Report 0x18 is the pair/unpair event. HTC prints `slot num in dongle: %d` and calls `TrackerDongleHID::AddTracker`
  (`dll+0x2a480`, "Tracker is paired to slot %u, connected: %d"). pyvut decodes the same report as
  `[unk][is_unpair][mac…]`. [code][match] HTC keys everything on the **slot number** and treats the MAC as unreliable;
  pyvut says the MACs "have always been fake". [match]
- A connection watchdog `TrackerConnectionTimeoutProc` (`dll+0x43150`) logs `CONNECTION TIMEOUT! unpair tracker`,
  `Tracker failed to connect. retry: %d`. **Live-confirmed: a timeout drops the link but does not unpair.** Slot 3 timed out after
  10 s, the server removed it, the dongle slot kept `Exist DB` 1 (status 8 to 5), and it reconnected 7 s later with no pairing step. Despite the log text, treat the watchdog as a disconnect.
- At server start, saved trackers from `Trackers.json` are replayed to the Hub (`Report saved tracker`, `Skip this paired
  info`, `prev paired info overwritten`). If the dongle in the port differs from the one the saved info belongs to, the
  server creates `fake_<SN>` placeholder trackers and unpairs them (`Unpair fake tracker. dongle slot number: %d`). [strings]

### 3.4 Differences from pyvut / Linux `tracker_server`

- Linux `tracker_server` command names `PAIR_TRACKER` / `REMOVE_TRACKER` line up with `IsPair` 1/0 here. [match, strings]
- pyvut's first dongle command in `__init__` always pairs with a fixed mask `1,1,1,0,0`. HTC derives the mask, so with
  five trackers or after unpairing one slot the hard-coded mask is wrong. We should build the mask from the `0x1E` status
  like Windows does.
- pyvut lists behavior 6 as "clears pairing info maybe" and never uses it; Windows uses it for every unpair. This is the
  missing "unpair one tracker" primitive. It needs a hardware test before we trust it. Behavior 5 (factory reset) must not be
  sent without a warning: pyvut notes some dongle commands brick.
- Role id, tracking host and tracking mode are set after pairing over the ACK channel, same as pyvut `do_loop`.

## 4. Dongle slot state (`QueryConnectionStatus`, `dll+0x39010`)

Request: report `0x1E` (a 64-byte feature report; only `0x11e`, i.e. command 0x1E, length 1, is set). Reply starts at
byte 9 with five records of four bytes each. [code]

```
rec[i] (i = 0..4, offset 9 + 4*i)
  byte 0    status          3 empty slot, 5 paired but not connected, 8 RF connected, 6 transitional
                            (seen once with Pairing and Connecting set); live-confirmed
  byte 1-2  connection timeout, ms, little endian
  byte 3    flags
              bit 0  power saving
              bit 1  exist in DB       (a pairing entry exists in the dongle)
              bit 2  pairing           (slot is in pairing mode)
              bit 3  connecting
              bit 4  RF connected
              bit 5  send IMU to USB
              bit 6  handling FOTA
```
[code] bit order is from the argument order of the debug print at `dll+0x391df`; the order of the printed names there is
the one above.

Check against pyvut's observed words (u32 little-endian = status | timeout<<8 | flags<<24): [match]

| pyvut word | status | timeout | flags | Reading |
|---|---|---|---|---|
| `0x320fc008` | 0x08 paired | 4032 ms | `0x32` = exist DB, RF connected, send IMU | paired and streaming |
| `0x4000003` | 0x03 | 0 | `0x04` = pairing | empty slot, open for pairing |
| `0x1000003` | 0x03 | 0 | `0x01` = power saving | empty, dongle idle |

`dumpPUMRFQueryStatus` (`dll+…`, strings only) shows a second, longer dongle status report with the same columns plus
`Running Mode`, `Rx MFG Pass`, `Pairing Status x/y`, `Local FOTA`, `CR0/CR1 Remote FOTA`, `Any Exception`, `CR0/CR1 RF
Status`, `In Factory Reset`, `Connect Timeout`, and RF drop-rate/RSSI/channel counters. [strings] That is a diagnostics
page worth exposing; its binary layout was not decoded.

## 5. Tracker status

### 5.1 Battery, charging, pogo pins (`convert_peripheral_data`, `dll+0x481e2`)

Two bytes `p0, p1` per tracker data report: [code]

```
p0                    stored raw (buttons/accessory byte)
p1 bit 7 = 1          pogo mode: p1 & 0x7f = pogo status; bits 0,1,2,3,4 are five accessory flags
p1 bit 7 = 0          p1 bit 6 = isCharging
                      p1 & 0x3f = battery, percentage = (p1 & 0x3f) * 2   (live readings 86, 62, 60, 58: always even, steps of 2; confirmed)
```
The DLL logs `isCharging: %d, battery percentage: %d%` and `isCharging is changed from %d to %d`; it only forwards on change.
The server callback `OnPeripheralDataChanged` (`srv+0x4a200`) logs `is charging, battery percent, system button, grip,
trigger, trackpad, menu`, i.e. accessory inputs share this path. Where in the 0x28 payload these two bytes sit was not
yet located; the data format switch is on payload size `0x27` (39) and `0x32` (50) bytes (`dll+0x361d1`, `0x361db`). [code]

Open: the low-battery threshold that drives `SteamVRNotificationHelper.exe show … 20` ("Show low battery") was not found yet.

### 5.2 Identity and mode indications (`ParseIndication`, `dll+0x36750`)

Text messages inside report 0x28 are parsed with a table built at startup (`dll+0x1340`). Ids as stored: [code]

| Token | Id | Meaning in logs | pyvut ACK |
|---|---|---|---|
| `NANA` | 7 | tracker announced (device name base) [guess] | `ANA` |
| `NADS` | 8 | Device SN | `ADS` |
| `NASS` | 9 | Ship SN | `ASS` |
| `NASI` | 10 | SKU id | `ASI` |
| `NAPI` | 11 | PCB id | `API` |
| `NAV1` | 12 | firmware version (+ "version num") | `AV1` |
| `NARI` | 13 | role id | `ARI` |
| `NAGN` | 14 | working mode [guess from handler order] | `AGN` |
| `NADN` | 15 | device name [guess] | none |
| `NADI` | 16 | device id [guess] | none |
| `NAZZ` | 99 | power state change ("Tracker is going to power-off") | `AZZ` |
| `MS` | 2 | map status string ("Map status: %s") | `MS` |
| `LP` / `LS` | 4 / 5 | lambda property (`has_map`) / lambda status (`map_state`) | `LP` / `LS` |
| `APF` | 6 | power off | `APF` |
| `ARP`/`ARp`/`ArP`/`Arp` | 17 | role-id variants [guess] | none |

Other handled indication kinds, by log text: `OET mode: %s`, `map state: %s`, `indicator: u,u,u,u,u,u,u,u` (8 status
indicator values), `Refine event received`, and a chunked **JSON** transfer with `isCompressed`, `size`, `crc` and a CRC
check (`Json file is complete` / `broken`). [strings] Parsing starts with the slot digit: `slot - '0'` (`dll+0x36032`). [code]

### 5.3 Tracking state

- The server's per-tracker JSON has `TrackingStatus` and `OetIndicatorEvent`/`OetIndicatorValue`; `OetErrorCode` carries
  events such as lost tracking, relocalisation, sleep (see `OnTrackerErrorNotification` strings: `OET LOST TRACKING!`,
  `OET reloc back.`, `entered sleeping (lost tracking)`, `entered sleeping (table static)`, `OVERSPEED`). [strings]
- Environment light has two values, `NORMAL` and `LOW`, from the first status indicator group. [strings]
- Pose status used by the SteamVR driver is a separate matter (see the SteamVR driver thread). pyvut's `POSE_*` and `POSESTATE_*`
  enums describe the same values. The Linux repo's open question about raw code `18` is not answered here.

## 6. JSON the server publishes (names are exact strings from the server binary)

Service level (`ServiceStatusToVHServer`): `DongleIsConnected`, `DeviceCountsPairedOnDongle`, `MapState`,
`HasNewDongleFW`, `DongleFWVersion`, `SpaceCalibrationState`, `PluggedDeviceChanged`, `CameraFrameRate`,
`TrackerConnectionType`, `SystemErrorCode`, `OetIndicatorEvent`, `OetIndicatorValue`, `IsAutoSleep`, `AutoSleepTimeout`,
`LastCalibratedInUTCTS`, `CalibrationReset`. [strings]

Per device: `DeviceIndex`, `DeviceIsConnected`, `TrackingStatus`, `DeviceIsCharging`, `BatteryPercentage`, `ConnectedOnUSB`,
`HasNewFW`, `FWLastUpdatedTime`, `IsUnpaired`, `IsHost`, `IsEnterSleep`, `OetErrorCode`, `SerialNumber`, `DeviceName`,
`DeviceType`, `EnrollUID`, `TrackingMode`, `ConnectType`, `RomName`, `WifiConnected`, `ModelName`, `FwVersion`, `Role`,
`NeedForceUpdate`. [strings]

The server's one-line log of the same record shows the order and extras: `display index, device index, connected,
tracking status, charging, percentage, map ID, map status, has map, map state, is host, bIsConnectedOnUSB, has new fw,
is unpaired, last update time, error code, indicator event, indicator value`. [strings]

Persisted tracker list (`config\Trackers.json`): `Dongles` (each with `serial`, `tracker_count`, `Trackers`), `dongle_count`,
`WiFi.tracker_count`, and per tracker `strTrackerName`, `strTrackerFWVersion`, `strTrackerSN`, `uTrackerIndex`, `uDisplayIndex`.
**Corrected by the live cross-check:** the map and space keys (`map_setup`, `last_map_creation_time`, `map_quality`, `space_setup`,
`transform`, `universe_id`…) live in `Calibration.json`, not `Trackers.json`. This is the file whose schema our app can mirror to be
state-compatible with VIVE Hub.

`IsUnpaired` is a flag on the device record, not a missing record: Hub keeps showing an unpaired tracker's card until the
user dismisses it, which explains the UI states "Pairing begin/end, Unpairing begin/end" in the server resources. [guess]

## 7. USB-connected tracker (`TrackerHID`)

A tracker plugged into USB (`0bb4:06a3`) is handled by `TrackerHID`, not the dongle path. Strings show feature-report
commands for status (`PACKET_GET_STATUS`), UVC node config (`PACKET_SET_USB_UVC`), `SetHaptic`, `FactoryReset`, `Identify`,
`SetLocalTime`, `KickWatchDog`, and device info `DEVICE_INFO_TYPE` reads (serial, ship SN, SKU, PCB). `AssignDeviceName`
logs `NOT SUPPORTED!` on the USB path. [strings][match: pyvut `PACKET_*` in `enums_horusd_hid.py`]
Tracker pairing state is not visible over USB; pairing always goes through the dongle.

## 8. What our app should do

1. **Pair**: query `0x1E`, build the mask from empty slots (bit 1 clear), send `1D 09 00 01 m0 m1 m2 m3 m4`, wait for
   report `0x18` with `is_unpair = 0`, then re-query and show the slot as paired.
2. **Unpair one**: send `1D 09 06 01` with a one-hot slot, wait for report `0x18` with `is_unpair = 1`. Needs a hardware test first.
3. **Cancel pairing**: send behavior 2 with the empty-slot mask (Windows' Cancel).
4. **Status model**: reuse the JSON names in section 6 as our daemon's status fields; they are what the Hub UI already
   expects, so any Hub-style frontend maps 1:1.
5. **Battery**: `percent = (p1 & 0x3f) * 2` capped at 100, `charging = p1 & 0x40`, only when `p1 & 0x80 == 0`. The DLL forwards a change only when the value changes; before the first report the percentage reads 0.
6. **Slot table**: surface the seven flag bits per slot for the diagnostics page.

## 9. Open questions

1. Offset of the two peripheral bytes inside the 0x28 payload for each of the 39-byte and 50-byte formats.
2. What `0xFF` and `0xFD` really do (`0xFE` is settled).
3. Retry counts of the connection watchdog (one live case: 10 s, retry 10).
4. Low-battery threshold.
5. Binary layout of the extended dongle status report (`dumpPUMRFQueryStatus`) and the RF drop-rate report.
6. Whether `NADN`/`NADI` are what the Hub shows as the tracker name (`AssignDeviceName`, `AGs1,` JSON chunks).
7. Packet-level confirmation with `usbmon`. The live cross-check confirmed behavior at the log and dongle-status level only, not the raw `1D 09 …` bytes. Capture a pair, an unpair-one, a cancel, and a power-off.
8. The EULA reverse-engineering clause is still unread; keep this document internal until someone reads it.

## 10. Reproducing

`tools/re/pe_disasm.py` (our own helper) takes a PE path and a string, finds the code that references it, and
disassembles the containing function. Run it only on files you extracted into a fresh directory; the HTC DLLs are the
`vivehub-windows-01-server-driver-utils.zip` members `ViveUTServer/vive_tracker_driver.dll` and `ViveTrackerServer.exe`.
MD5 of the analysed files: DLL `8d3cd8a3bc0f1e25de3aa124be1039dc`, server `42f049e3b5b1ae4f31cfa9c14fa890ed`.
