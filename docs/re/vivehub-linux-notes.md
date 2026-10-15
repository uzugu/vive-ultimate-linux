# VIVE Hub for Linux 1.0.3: reverse-engineering notes

Source: `VIVEHub-Linux-v1.0.3-x86_64.tar.gz` from the official
[ViveRoboticsSoftware/vivehub-linux](https://github.com/ViveRoboticsSoftware/vivehub-linux) releases
(built 2026-09-07). First pass is static only: file layout, `strings`, and the bundled SDK headers/README.
No HTC binaries are committed to this repo; do not redistribute them.

## Package layout

| Path | What it is |
|---|---|
| `vivehub` | UI. Dear ImGui + GLFW + OpenGL, x86-64 ELF, stripped. Launches and talks to `tracker_server`. |
| `tracker_server` | Dongle daemon, 121 KB, stripped, x86-64 ELF. All USB/RF protocol logic lives here. |
| `tracker_setup/TrackerSetup_build_linux/` | Map-building wizard. Unity IL2CPP build (`GameAssembly.so` + `global-metadata.dat`), bundles `libopenvr_api.so`. |
| `sdk/` | "VUT SDK": `libvut_sdk.a`, headers `vut_client.h`, `vut_types.h`, `vut_version.h`, demo. |
| `udev/70-vive-tracker.rules` | USB IDs: dongle `0bb4:0350`, tracker over USB `0bb4:06a3`. |
| `lib/` | Bundled `libhidapi-hidraw.so.0`, `libglfw.so.3`. |

## Process and socket architecture

```
vivehub (UI) ──▶ $XDG_RUNTIME_DIR/HTC/VIVEUltimateTracker/tracker_server.sock (or /tmp/tracker_server-<uid>.sock)
tracker_setup ─▶ .../TrackerNamedPipe.sock   ("setup_server": map wizard commands)
3rd-party app ─▶ /tmp/vut.sock               ("vut_bridge": VUT SDK pose/status stream)
                         │
                   tracker_server ──hidraw──▶ dongle 0bb4:0350 ──RF──▶ trackers
```

- Single instance enforced with `tracker_server.pid`; `--daemon | --foreground | --version`.
- Paired trackers persisted per dongle in `~/.local/share/HTC/VIVEUltimateTracker/trackers.json`
  (`trackerIndex`, `trackerName`, `trTrackerSN`, `trTrackerFWVersion`).
- Logs: `~/.local/share/HTC/VIVEUltimateTracker/logs/`.
- UI → daemon command names seen: `PAIR_TRACKER`, `REMOVE_TRACKER`, `OPEN_TRACKER`, `GET_TRACKER_INFO`,
  `RESET_DONGLE`, identify, power off.
- Wizard → daemon (Unity side method names): `CreateTracker`, `EnumerateTrackers`, `GetTrackerCount`,
  `IdentifyTracker`, `Start_Map_Creation`, `End_Map_Creation`, `Cancel_Map_Creation`,
  `Get_Last_Map_Creation_Time`. Map quality states: `ControlMapQualityCheck/Ok/Poor/Refinable/PoorRefinable`,
  `ControlMapSaveDone`.

## Tracker command strings (ACK channel)

ASCII commands found in `tracker_server` (cross-check with pyvut `enums_horusd_ack.py`):

`ALE` (end map), `ATH` (tracking host), `ATW`, `ATM11` / `ATM20` / `ATM21` (tracking-mode: 11 = SLAM client,
20 = SLAM host, 21 = ?), `ATS`, `ATU`, `ATUH`, `ATA`, `ATD`, `ATE1`, `ATI`, `ATL`, `AT1`, `AUA`, `AUE`, `AUE1`,
`AUH`, `AUI`, `AUL`, `AUM`, `AVA`, `AVH`, `AVI`, `AVL`, `AW1`, `AWA`, `AWI`, `AWL`, `APF`, `ARD`, `ARP`, `ASD`,
`ACF60`, `FW1`, `FW2`, plus `LP` (lambda property, carries `has_map`) and `LS` (lambda status, carries `map_state`),
`WH` (host Wi-Fi info), `NA` (bootstrap/new device).

Log lines worth knowing:

- `[setup_server] Start_Map_Creation -> pMS_SC + LOADING pulse`
- `[state] host map-mode AT sequence sent slot=%d (ATM20)`: map building = put the host tracker in mode 20.
- `[state] LP slot=%d has_map=%u` and `[state] LS slot=%d target=%d map_state=%d`.
- `[state] QueryWifiInfo -> host`, `AssignWifiInfo -> client`: clients get the host's Wi-Fi AP to sync the map.

## Where maps live

The map is **stored on the trackers themselves**, not on the PC. Each tracker runs Android; pyvut's
`clear_maps.sh` wipes `/data/lambda/` and `/data/mapdata/` over `adb`. The host tracker owns the map and
clients pull it over the tracker-hosted Wi-Fi AP. Relevant status values from pyvut:

- `KEY_CURRENT_MAP_ID`, `LAMBDA_MESSAGE_UPDATE_MAP_UUID`: maps have IDs/UUIDs.
- `MAP_REUSE_OK`, `MAP_REUSE_FAIL_FEATURE_DIFF`, `MAP_REUSE_FAIL_FEATURE_LESS`: on boot the tracker tries to
  relocalise in its stored map and reports whether the room matches.
- `LAMBDA_CMD_RESET_MAP`, `LAMBDA_PROP_SAVE_MAP`, `SYSTEM_STATE_SAVE_ROOM_SETUP`.

**VIVE Hub for Linux has no multi-room support**: one map at a time; a new room means rebuilding.

## Next RE steps

1. Run `tracker_server --foreground` with a real dongle and capture hidraw traffic (`usbmon` + Wireshark) during
   pair, map build, and normal tracking. Diff against pyvut's decoder.
2. Load `tracker_server` in Ghidra (or via the REA MCP server) and recover the command table around the
   `AT*` strings and the setup_server socket message format.
3. Dump the wizard with Il2CppDumper (`GameAssembly.so` + `global-metadata.dat`) to get the exact
   setup-socket message structs and map-quality logic.
4. On a tracker: `adb shell ls -la /data/lambda /data/mapdata` and check whether `adb pull`/`push` of those
   directories round-trips a map (the basis for room switching).
