# Windows VIVE Hub: Ultimate Tracker feature parity checklist

Target: everything VIVE Hub on Windows does for the Ultimate Tracker, in our app, on Windows first and then on
Linux x86-64 and ARM64. Sources: HTC's support pages (linked), plus the Linux beta analysis in
[re/vivehub-linux-notes.md](re/vivehub-linux-notes.md). Status column: what we know about doing it ourselves.

| # | VIVE Hub feature (Windows) | Where in VIVE Hub | Our status |
|---|---|---|---|
| 1 | Install "VIVE Ultimate Tracker service" (dongle daemon + SteamVR driver) | VIVE Hub > Settings | Windows: `ViveTrackerServer.exe` + `vive_tracker_driver.dll` (44-export tracker library), same design as Linux `tracker_server`. Inspected, see [re/vivehub-windows-notes.md](re/vivehub-windows-notes.md) |
| 2 | Pair trackers to the dongle, unpair, list paired, identify (LED flashes) | Settings > VIVE Ultimate Tracker > Trackers | Protocol known (pyvut `DongleHID`, `PAIR_TRACKER` / `REMOVE_TRACKER`) |
| 3 | Live status per tracker (connected, tracking, lost tracking, battery) | Trackers tab | Known from status ACKs and VUT SDK `DeviceState` |
| 4 | Tracker setup wizard: create tracking map, host tracker, center point at 120 cm / 150 cm, scan low then standing per wall, auto-save, "Refine" weak sides ([HTC](https://www.vive.com/us/support/ultimate-tracker/category_howto/creating-a-tracking-map.html)) | Trackers tab > Tracker setup > Start setup | Partly known: host mode `ATM20`, `Start/End/Cancel_Map_Creation`, map-quality states. Needs traffic capture |
| 5 | Multi-tracker map sync: one host, clients sync over tracker Wi-Fi | automatic | Known (`WH`, `AssignWifiInfo`, pyvut `wifi_info.json`) |
| 6 | Expose trackers to SteamVR as generic trackers | SteamVR driver from the service | Our OpenVR driver skeleton exists (Linux); add Windows build |
| 7 | VIVE Space Calibrator: SteamVR dashboard overlay, hold controller + tracker, trace infinity sign ([HTC](https://www.vive.com/us/support/ultimate-tracker/category_howto/calibrating-the-trackers.html)) | SteamVR dashboard | Not started. Same math as OpenVR-SpaceCalibrator; we need our own (cross-platform) |
| 8 | Power frequency (50/60 Hz anti-flicker) ([HTC](https://www.vive.com/us/support/ultimate-tracker/category_howto/setting-power-frequency-and-auto-sleep-options.html)) | Settings > VIVE Ultimate Tracker > Advanced | Not in the Windows server or library; probably in the Hub shell. Hypothesis: camera frame rate / anti-flicker (`SetCameraFrameRate`, `ACF`). See [re/vivehub-windows-notes.md](re/vivehub-windows-notes.md) |
| 9 | Auto-sleep after 3 min idle | Advanced tab | `SetAutoSleep` export; stored in `Config.ini`. Easy |
| 10 | Firmware update: detect "Update available", then flash over USB-C one tracker at a time ([HTC](https://www.vive.com/us/support/ultimate-tracker/category_howto/updating-the-tracker-firmware-via-vive-hub.html)) | Settings > About > VIVE Ultimate Trackers > Update | Dongle: server runs HTC's `USBTool.exe upgrade rfmcuapp ... --ptdongle`. Trackers: HTC FOTA service + adb push + `StartFWUpdate`. Out of scope for v1 |
| 11 | Power off tracker, reset dongle, factory reset tracker | Trackers tab | Power off / reset dongle seen in Linux `tracker_server` |
| 12 | Tracker roles (body part / object) | SteamVR "Manage Trackers" on PC | Comes free once the SteamVR driver works |
| 13 | Use with third-party SteamVR headsets ([HTC](https://blog.vive.com/us/how-to-set-up-vive-ultimate-tracker-for-third-party-steamvr-headsets/)) | dongle on PC | Same as 6 + 7 |

Beyond parity (our extras): room switching (see [roadmap.md](roadmap.md)), headset-less mode, OSC/VMC output,
Linux x86-64 and ARM64, no account or VIVE Hub install needed.

## Order of work

1. ~~Inspect the Windows VIVE Hub tracker components~~ (first static pass done: [re/vivehub-windows-notes.md](re/vivehub-windows-notes.md)). Next: Ghidra on `vive_tracker_driver.dll`, Il2CppDumper on the setup apps.
2. Items 2, 3, 5, 11 (pairing and status): already mostly known, build them first.
3. Items 6, 7, 12 (SteamVR + calibration) on Windows.
4. Item 4 (map wizard) after capturing USB traffic of a real map build.
5. Items 8, 9 (settings) once their commands are identified.
6. Item 10 (firmware) last, with a recovery plan.
