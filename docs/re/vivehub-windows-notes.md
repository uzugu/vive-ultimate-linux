# VIVE Hub for Windows (Ultimate Tracker 1.2.7): reverse-engineering notes

Source: the tracker service of VIVE Hub on Windows (`VIVE Ultimate Tracker\`, product 1.2.7, `ViveUTServer` 2.12.0.0,
build 2509150), copied from the owner's PC. First pass is static only (PE imports/exports and `strings`); nothing
was run and nothing was decompiled yet. **Confidence:** "seen" = a function/export/log string exists in the binary;
"inferred" = our reading of what that implies, not yet confirmed by code or traffic.
HTC binaries stay in the private project files and are not committed. Open licensing question: read the VIVE EULA's
reverse-engineering clause before publishing anything derived (see end).

## 1. Architecture (the same shape as the Linux beta)

```
 dongle (HID) ─┐                               ┌─ \\.\pipe\OPEN_VR_DRIVER ──▶ driver_vive_ultimate_tracker.dll (SteamVR)
 tracker (USB) ┼─▶ ViveTrackerServer.exe ──────┼─ \\.\pipe\TrackerNamedPipe ─▶ tracker_setup.exe / tracker_setup_lite.exe
 tracker (WiFi)┘   (OETServer)                 └─ \\.\pipe\VIVEHUB_DEVICE_MANAGE ─▶ VIVE Hub shell
                    └─ loads vive_tracker_driver.dll (HID / Wi-Fi / file transfer / map / FOTA)
```

- `TrackerNamedPipe` is the Windows twin of the Linux `TrackerNamedPipe.sock`; the setup wizard is a Unity app on both.
- `ViveTrackerServer.exe` (class `OETServer`) is the daemon. "OET" is HTC's internal name for the Ultimate Tracker.
- Per-user data (seen): `%ProgramData%\HTC\ViveSoftware\ViveUltimateTracker\` with `config\` (`Trackers.json`,
  `Config.ini`, `Calibration.json`), **`MAP\`**, `VUT_LOG\`, `CollectedLog\`, and `tracking_info.json`.
  `Config.ini` holds log level, "ignore force update", auto-sleep enable and auto-sleep timeout.
- The server starts SteamVR integration itself: registers the vrmanifest via `VrManifestAutoRegister.exe -add`,
  checks that `adb` and `tracker_setup.exe` exist, and can write a display frequency into the bundled
  `vive_null_headset` settings for headset-less use (the null-headset driver folder itself was not in the copy).

## 2. `vive_tracker_driver.dll`: the real tracker library

Despite the name this is not the SteamVR driver. It is HTC's whole tracker library (HID, Wi-Fi, maps, FOTA), a plain C
API with 44 exports (seen). This is the closest thing to a spec of what VIVE Hub can do:

| Group | Exports |
|---|---|
| Lifecycle | `Initial`, `Release`, `SetCallback`, `SetDongleConnectedCallback`, `SetDeviceInfoCallback`, `SetErrorNotificationCallback`, `SetNotificationMsgCallback`, `SetStatusIndicatorUpdateCallback`, `SetPeripheralDataChangedCallback`, `UpdateFileTransferProgressCallback` |
| Devices | `EnumerateDevices`, `GetDeviceInfo`, `GetDeviceStatus`, `GetTrackerSerialNumber`, `IdentifyTracker`, `AssignDeviceName`, `IsReadyToPowerOn` |
| Pairing / dongle | `TriggerDongleMode`, `DropWifiConnection`, `AssignHmdIp`, `AssignWifiInfo`, `QueryWifiInfo` |
| Tracking | `StartTracker`, `StopTracker`, `GetPoseData`, `GetBodyData`, `GetBodySkeleton`, `SetCameraFrameRate` |
| Maps | `CreateMap`, `EndCreateMap`, `SendMapScanEvent`, `RelocateTracker`, `StartFileTransfer` |
| Power / settings | `PowerOffTracker`, `RebootTracker`, `FactoryResetTracker`, `SetAutoSleep`, `SetPogoOutput`, `SetAccessoryRawData`(+callback), `SetVbpDeviceInfo`, `SetProperty` |
| Firmware / logs | `StartFWUpdate`, `CollectOetLog` |

Three transports, one class per transport (seen): `TrackerOnDongle` (wireless via dongle HID), `TrackerHID`
(tracker plugged in by USB), `TrackerOnWifi` (the tracker's own Wi-Fi link). Linux `tracker_server` does the same
three jobs.

### How the Wi-Fi link works (seen strings, inferred flow)

1. The dongle pairs trackers and hands out slots; `TrackerDongleHID` parses *indication* messages, including a JSON
   payload sent in chunks with CRC (`isCompressed`, `crc`, "Json file is complete").
2. The PC gives each tracker the PC's IP (`AssignHmdIp`, `PassHmdIp2Tracker`) and a Wi-Fi SSID/password
   (`AssignWifiInfo`); the tracker then connects **to a TCP server on the PC**. Poses arrive over UDP on the PC
   (`getUDPClientData`, `startGetPose`); a separate TCP connection does time sync (`TcpClientSyncTime`,
   `RF_Sync_Helper`, `Wifi_Sync_Helper`) so tracker timestamps can be mapped to PC time.
3. Commands to the tracker are short ASCII strings over that TCP socket: `ATM20` (host/SLAM map mode), `ATM51`,
   `ATS` (set time), `ACF` (camera fps), `ANI` (assign device id), `AGs1,`/`AGs2,` (device info JSON chunks);
   properties are read/written by name (`persist.tracking.mode.6dof`, `.wifipose`, `.hmdvo`, `.largescale`,
   `persist.vbp.enroll_uid`, `persist.customized.hid.acces`). Matches the Linux strings and pyvut's ACK names.
4. **File transfer** runs over the same TCP link with numbered transfer messages (12, 14, 15, 21 to 24 seen).
   Directions in both senses exist: PC to tracker (`StartFileTransfer`, "READ MAP BINARY", "FOTA package", size and
   CRC checked) and tracker to PC (`StartReceiveUploadFile`, OET log under `/data/sys_log/current/ot_log_...`).
   Server-side progress labels name four jobs: **"Firmware Update", "Map Import", "Log Collect", "File transfer"**.
   File names seen: `autosave0`, `FEautosave0`; status text "LargeScale : %s, mapSize : %s".

## 3. What this means for room switching

Stronger than the Linux-only hypothesis in [roadmap.md](../roadmap.md):

- HTC's own server has a **"Map Import"** job and a file-transfer path that sends a file from the PC to a tracker
  (inferred). **Correction after a live check:** the PC-side `MAP\` folder is empty; the host tracker holds the map and
  syncs it to the other trackers itself. Export from the host still needs a route (adb is locked down on firmware 1.0.999.178; USB HID is the candidate); import may use the
  file transfer. See [vivehub-windows-map-transfer.md](vivehub-windows-map-transfer.md) section 3.
- Enumerate checks the tracker serial against its map (`[ENUMERATE_TRACKERS] SN & MAP MISMATCH!`, seen), which
  suggests a map is tied to the set of trackers it was made with. Keep one map per room *per tracker set*.
- `RelocateTracker` (`OET RELOCATE`) and `MAP_REUSE_*` states from pyvut are the hooks for "load map then re-localise".
- `LargeScale` is a property (`persist.tracking.largescale`) that changes map handling; rooms should record it.
- `adb` is still bundled and used (FOTA package integrity check with `adb shell ls -l /sdcard/`, error code
  `ERROR_CODE_ADB_NOT_FOUND`), so `adb` is the fallback and for firmware.

To verify: capture the TCP traffic between a tracker and the PC during (a) map creation and (b) a "Map Import", and
look in `MAP\` after a map build to see what file(s) appear.

## 4. Parity checklist updates

- **Power frequency**: not found in the server or the library. Likely lives in the VIVE Hub shell (not collected)
  and may be applied as the camera frame rate / anti-flicker (`SetCameraFrameRate`, `ACF`, with `ACF60` seen on
  Linux). Hypothesis: 50 Hz regions use 50, 60 Hz regions use 60.
- **Auto-sleep**: `SetAutoSleep` export, `Config.ini` keys auto-sleep enable and timeout (3 min default per HTC docs).
  Plain command, easy.
- **Firmware, dongle**: server unzips `Dongle_release_*.zip` and runs `USBTool.exe upgrade rfmcuapp DONGLE.ota
  --ptdongle` (`USBTool.exe` was not in the copy). That is a USB update tool, not a protocol we have to re-invent
  at first: we can wrap it or find its protocol later.
- **Firmware, trackers**: server checks HTC's FOTA service over the internet, downloads a package, pushes it to
  `/sdcard/` with adb, checks size, then `StartFWUpdate` (`FOTA Initiated.`). Needs HTC's service and package signing;
  treat as out of scope for v1.
- **Pair / unpair / identify / power off / reset / reboot / relocate / log collection**: all are exports above.
- **Space calibration**: stored in `Calibration.json` (position, rotation, chaperone center, boundary, universe ID);
  the server compensates for headset space changes. The SteamVR-side math is the open-source Space Calibrator.
- **SteamVR driver**: thin; talks to the server over `\\.\pipe\OPEN_VR_DRIVER`. Our own driver should not need HTC's.

## 5. Next steps

1. Disassemble `vive_tracker_driver.dll` exports (Ghidra) for the HID packet IDs and the TCP message numbers; diff against
   pyvut's enums and the Linux `tracker_server`.
2. Dump the Unity setup apps with Il2CppDumper to get the exact pipe message structs
   (`CreateTracker`, `EnumerateTrackers`, `Start/End/Cancel_Map_Creation`, map-quality states).
3. Hardware: capture USB (dongle) and TCP (tracker Wi-Fi) while building and importing a map.
4. Ask for from the PC if needed: `VIVE Hub\ViveHubServer` and `VHConsole` (power-frequency setting) and `USBTool.exe`.

## Licensing note

HTC's EULA text was not reviewed. Before publishing anything derived from these binaries, someone should read its
reverse-engineering clause (interoperability exceptions differ by country). These notes contain function and message
names only, no HTC code or assets.
