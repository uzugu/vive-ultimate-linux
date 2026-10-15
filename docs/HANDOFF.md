# Handoff: project status and instructions (2026-10-15)

For the next agent (or person) picking this project up, most likely on the owner's own Windows PC. Read sections 1 to 3
for orientation, section 7 before touching any hardware, and take tasks from section 6 in order.

Confidence tags used throughout the notes: **code** (read from instructions), **string** (seen in a binary or log), **inferred**, **guess**.
Trust them in that order. Anything not run on hardware is a hypothesis.

## 1. Goal

One open app for **Linux x86-64, Linux ARM64 and Windows** that replaces the tracker part of HTC's VIVE Hub for the VIVE Ultimate
Tracker, plus extras HTC does not offer (headset-less mode, OSC/VMC output, no account). The main objective is
**room switching**: build a map once per room, keep it, and load the right one onto the trackers later without rebuilding.
Order: first parity with VIVE Hub for Windows 1.2.7 ([windows-parity.md](windows-parity.md)), then the multiplatform app.

### Milestones ([roadmap.md](roadmap.md))

| | Milestone | State |
|---|---|---|
| M0 | Hardware baseline: poses from the dongle on Linux; map export proven; multi-map test | Export proven. Linux pose streaming not retested here. Multi-map not tested. |
| M1 | Manual room snapshots (`save` / `load`), re-imported map reports `MAP_REUSE_OK` | Save half proven (export). **Load half unsolved.** |
| M2 | Daemon + SteamVR driver, per-room calibration | Linux daemon and driver skeleton merged with CI. Calibration not started. |
| M3 | GUI: pair, status, rooms, one-click switch; builds for all three platforms | Not started |
| M4 | Auto room detection (`MAP_REUSE_*`), our own map-build flow | Not started |

## 2. What is on `main` (PRs #1 to #6 merged; CI runs every test)

| PR | What it brought |
|---|---|
| #1 | `docs/prior-art-survey.md`, `docs/roadmap.md`, `docs/windows-parity.md`, `docs/re/vivehub-linux-notes.md`, `vivehub-windows-notes.md`, `vivehub-windows-map-transfer.md`, `vivehub-map-format.md`, `vivehub-map-import.md`; `python/tools/vut_filetransfer.py` (messages 22/23 + CRC-32), `vut_ft_listen.py` (passive TCP 8053 listener, never sends), `vut_rooms.py` (adb snapshot; **dead on firmware 1.0.999.178**); `tools/re/xref.py` |
| #2 | `docs/re/pairing-and-status.md` (pair/unpair `0x1D`, slot status `0x1E`, battery decoding, status JSON), `tools/re/pe_disasm.py` |
| #3 | `docs/re/settings-power.md`, `python/vut_settings` (command and `Config.ini` builders, tests) |
| #4 | `docs/re/driver-pipes.md` (SteamVR driver and server pipes, 20-byte framing, command tables, plan for our driver), `python/htc_pipe_codec` (framing + records, tests) |
| #5 | Hardened Linux pose protocol: `protocol/pose-v1.md` (v2 with v1 accepted), shared fixtures `protocol/fixtures/`, daemon fixes (slow client, source error, reset), `STALE` after 0.5 s silence, C++ client `uts_ipc` with tests, CMake `UTS_BUILD_DRIVER` / `UTS_BUILD_TESTS` |
| #6 | CI step running `tests/`, `python/vut_settings/tests`, `python/htc_pipe_codec/tests` with pytest |

CI (`.github/workflows/ci.yml`): Python 3.10 and 3.13 unit tests, tool/research-helper tests, C++ tests, a Python-daemon-to-C++-client
check, and a full driver build against OpenVR v2.15.6. Run the same locally before pushing.

Repo layout: `python/pose_daemon` (daemon, mock + `pyvut` source), `steamvr_driver` (OpenVR driver, Linux), `protocol/` (IPC contract),
`python/tools`, `python/vut_settings`, `python/htc_pipe_codec`, `docs/`, `docs/re/` (RE notes), `tools/re/` (static-analysis helpers), `tests/`.

## 3. State of each workstream

**Linux daemon and driver.** Mock source works end to end in CI. The `pyvut` source publishes real poses but was never validated in this project
against hardware; `pyvut` has no license, so it is an external dependency, not copied. Missing: calibration, Windows build of the driver
(plan in `driver-pipes.md` §8: same byte stream over a named pipe `\\.\pipe\ULTIMATE_TRACKER_DRIVER`), new message types (`DEVICE`, `BATTERY`, `BUTTONS`, `EVENT`, `HAPTIC`, `HELLO`).

**Pairing and status.** Fully decoded statically; nothing captured. Pair `1D 09 00 01 m0..m4`, unpair `1D 09 06 01`, status query `0x1E`, battery
`percent = (p1 & 0x3f) * 2`, charging `p1 & 0x40` ([pairing-and-status.md](re/pairing-and-status.md) §3, §5, §8). Live logs and dongle status agree at log level; raw bytes need a `usbmon` / USB capture.

**Settings and power.** Command strings known from code: auto-sleep `pAS_TS<n>`, power off `APF`, reboot `APR`, camera rate `ACF<n>`, factory reset USB HID `FF AF`
([settings-power.md](re/settings-power.md) §10). Power frequency not found. Wire commands are hypotheses until a capture agrees.

**SteamVR pipe protocol.** `TrackerNamedPipe` etc., framing and tables decoded; the 85-byte pose record's quaternion order and last six floats are unconfirmed
([driver-pipes.md](re/driver-pipes.md) §9). We do not need to speak HTC's protocol for the product; it is a spec of the data we need, and `htc_pipe_codec` can mock it for regression.

**Map export (proven).** Via HTC's log tool, see §4.

**Map import (unsolved).** See §5. No sender exists; the repo holds only message builders and a passive listener.

## 4. Proven on hardware

- Trackers run **firmware 1.0.999.178** (Android 7.1.2 userdebug, arm64). Dongle plus three trackers were in use; slot numbers vary, the host role is per scan.
- **adb is locked down**: only `shell ls -l /sdcard/`, sync listings of `/sdcard`, and a pull of `/sdcard/hdlog.tgz` work; every path outside `/sdcard` and every other shell command is refused.
- **USB HID property reads work** (allowlisted). Windows sees HID interfaces `MI_00`/`MI_01`, usage page `0xFF00`, 64-byte feature report, 1024-byte input report. A request is `00` + the 64 bytes pyvut sends (command u16 LE, length u8, 0, data); replies carry flag `0xFF`. `GET_STATUS` is `0xa002`, `GET_PROPERTY` is `0xa201`. The HID file service sees only the SD card. See `vivehub-windows-live-hid-probe.md` and `hid-probe.ps1` in the project files.
- **Map export**: `UTLogRetriever.exe "-LogFolder:<dir>" -getmap` (in `ViveUTUpdateManager\UTCollectLog\Tools\TrackerLogRetriever\`) sends HID opcode `0x56`, type=1. The tracker builds `/sdcard/hdlog.tgz` (about 4 min, ~298 MB). Pull it with HTC's own `CommonTools\ADB\adb.exe` once the size is stable, then delete the archive with the HID file delete (bare name `hdlog.tgz`) and stop the adb server. A second request while one runs is refused.
- **Map format**: `data/hdlog/mapdata/` holds three SQLite 3 files: `general.db` (registry + visual-word index), `map_<id>.db` (ORB-SLAM-style map: keyframes, points, floor plane), `kf_<id>.db` (keyframe image pyramids). Full structure: [vivehub-map-format.md](re/vivehub-map-format.md).
- **One map per tracker.** `general.db` says `map_size` 3, which equals `persist.lambda.multimap.size` and is probably a size class; every logged save holds exactly one map. Several rooms on one tracker is **not evidenced**.
- **Maps are saved at standby** (about 6 s after "entered sleeping"), so an export is the state of the last standby. The host tracker owns the map and copies it to clients over Wi-Fi (17 to 19 s). The PC `MAP\` folder is empty; the PC keeps only metadata in `config\Calibration.json`.
- Battery drain observed about 14 % per hour while tracking.

## 5. Map-transfer protocol decoded so far

Source: tracker logs, [vivehub-map-import.md](re/vivehub-map-import.md) §3a/3b and [vivehub-windows-map-transfer.md](re/vivehub-windows-map-transfer.md).

- The tracker **dials out** to a TCP server on the PC/host. `ViveTrackerServer.exe` listens on TCP 3680, 8053, 9005, 9527, 15680 and UDP 9005. Only **8053 = file transfer** is tied to a role; 9527 is seen next to it but unconfirmed; 9005 is probably poses/connection; others unmatched. HTC's server must be stopped to listen ourselves.
- Control link strings: host sends ack `FK<n>`, tracker answers `ft_download: filename=<n>` and connects to `<host>:8053` to fetch file index `<n>`. State acks `P61:<key>,<value>` (`P61:0,1` ready, `1,1` first file, `2,1` host key, `3,1` host map received, `5,1` map exists). Reset trigger `P64:3`.
- Frames are 0x80 bytes with magic `0xB9D7`. Download family: u21 hello, **u22 header** (size, mtu 1048576, output path chosen by the sender), data, **u23 trailer** (CRC-32, poly `0xEDB88320`), u24 status. Upload family u11 to u14 is tracker to host. HTC's PC library confines itself to `/sdcard/`; whether a tracker accepts other paths from a PC peer is untested.
- **Pack order** into `/data/lambda/<host slot>/general_map/`: (1) `file_pack_info_<N>_8.json` (**502 bytes**), (2) `<N>_8_general.db`, (3) `<N>_8_map_<id>.db`, (4) `<N>_8_kf_<id>.db`. The three databases are the exported files renamed.
- Identity step first: each side sends `file_pack_info_<n>_<m>.json` (~217/219 B) and `pubkey.pem` (426 B) into `/data/lambda/<dev>/ed/`. Packs appear to be signed or checked against that key: a forged pack may be rejected.
- Separate candidate: HTC's VBP "Map Import" (`persist.vbp.map_*` + a file `autosave0`, ASCII command `FD`+`autosave0`, then messages 22/23 to `/sdcard/`). Static analysis only; `autosave0` format unknown.

**Unknown, and decisive:** the 502-byte `file_pack_info` format and whether it is signed; whether a PC peer can be accepted as host.

## 6. Ownership and prioritised tasks

The work is split roughly 50/50 between two owners:

- **CLOUD** = the cloud Claude threads (T5 and T6 are with the Linux SteamVR driver thread; cloud does not redo blocked map-import work, so T1 and T13 are PC's).
  Owns everything that needs no hardware: Linux pose daemon and driver, pipe-protocol features (calibration offset, battery, buttons, haptics), code for pairing/status and settings/power, CI, packaging, the multiplatform app shell, docs.
- **PC** = the agent on the owner's PC. Owns everything that needs the PC or the trackers: map import and the 8053 transfer work, live hardware tests of each feature, Windows build and run checks, log collection.

**Claim or release a task by editing the Owner/Status columns below in a PR** (one small PR per change, title `handoff: claim T<n>` or `release T<n>`), so the two sides never collide. Do not start a task whose Status is `claimed` by the other side. Statuses: `open`, `claimed (who, date)`, `done (PR)`.
Hardware steps additionally need the owner's approval (section 7).

| # | Owner | Status | Task | HW |
|---|---|---|---|---|
| T1 | PC | claimed (PC Codex, 2026-10-15) | Decode `file_pack_info`: schema of the 502-byte JSON from log extracts and strings. New `docs/re/file-pack-info.md`. Done when every field is named and tagged and signatures/checksums are identified. | logs only |
| T2 | PC | open | Passive capture on 8053: stop HTC's `ViveTrackerServer.exe`, run `python/tools/vut_ft_listen.py`, let a tracker connect, record the first frames; match ports 8053/9527/9005 to roles. Files: extend `vut_ft_listen.py`, new note. Never sends. Done when ports are matched and frames documented. | yes |
| T3 | PC | open | Multi-map test: build a second map without clearing the first, standby, re-export with `-getmap`, compare `general.db`. Done when a note says whether two maps coexist. Decides the room design. | yes |
| T4 | CLOUD | open | Room store (no HW): per-room layout (name, host serial, origin, calibration), parse `Calibration.json` and `Map_main` times, synthetic tests. New `python/` package. Never commit real maps. | no |
| T5 | CLOUD | claimed (Linux SteamVR driver thread, 2026-10-15) | Pose protocol v3 in daemon + C++ client: `DEVICE`, `BATTERY`, `BUTTONS`, `EVENT`, `HAPTIC`, `HELLO` (see `driver-pipes.md` §8), with shared fixtures and CI. Done when both parsers pass the fixtures. | no |
| T6 | CLOUD | claimed (Linux SteamVR driver thread, 2026-10-15) | Calibration offset (daemon-side transform, per room) and a Space-Calibrator-style math module with tests. | no (needs T9 to verify live) |
| T7 | CLOUD | open | Pairing/status library from `pairing-and-status.md` §8 and settings library (`python/vut_settings` extended: auto-sleep, power, camera rate), written against a mock dongle/tracker with tests. | no |
| T8 | PC | open | Live validation of T7 and pairing/status: USB capture (`usbmon`/Wireshark USBPcap) of pair, unpair, cancel, power-off; TCP capture while changing each setting in HTC's Hub; report differences. Factory reset last, on a spare tracker. | yes |
| T9 | PC | open | Windows run checks: build the SteamVR driver and daemon on Windows, run the cross-language test, load the driver in SteamVR with one and two trackers. | yes |
| T10 | CLOUD | open | Windows transport and build: named-pipe transport beside the Unix socket, Windows CMake build, `openvrpaths.vrpath` registration, CI on a Windows runner. | no |
| T11 | PC | open | Pose capture to close `driver-pipes.md` §9 item 1: pipe proxy or hook on the running server with one and two trackers; log pose records. | yes |
| T12 | CLOUD | open | Packaging and app shell: single entry point (`vut` CLI/daemon), PyInstaller config, Linux x86-64/ARM64/Windows build matrix in CI, GUI skeleton (pair, status, rooms). | no |
| T13 | PC | open | Map import sender, last: needs T1 and T2 answers; spare tracker with a backed-up map. First step is a 1 KB file to `/sdcard/` and reading the u24 reply (`vivehub-map-import.md` §4). Earlier sessions were stopped by the automatic safety check here (section 9): if it happens, tell the owner, do not retry blindly. | yes |
| T14 | CLOUD | open | Docs and housekeeping: keep this file and the roadmap current, README refresh, read the VIVE EULA reverse-engineering clause and record the outcome before publishing beyond names/ids/layouts. | no |
| T15 | PC | open | Collect logs on request (`hdlog.tgz`, server/driver logs) and keep `%USERPROFILE%\Documents\VIVE-map-backups` current; check free disk on C: first (it was full). | yes |

Suggested order: T1, T2, T3 and T5 first (they unblock the rest), then T7/T8, T4/T6, T10/T9, T12, T13 last.

## 7. How to work with the owner

- **The owner approves each tracker/dongle step before it runs.** Describe the exact command and what it changes. Smallest step first; no bulk probing, no "while I'm here" extras. Read-only checks still get a heads-up.
- **No HTC binaries in the repo or any PR.** Notes, names, ids and layouts only. The HTC files exist only in the project's shared folder (`vivehub-windows-*.zip`, index `vivehub-windows-inventory-20261014T162631-90f9.md`).
- **Map files contain camera images of the owner's room.** They stay on the owner's PC, never uploaded, committed or pasted. Record structure only.
- No serials, MACs, Wi-Fi names or user ids in notes (the live files are masked).
- Cloud sessions analyse and write exact commands/scripts; the PC session runs concrete pre-planned steps and reports output. Give it commands inline.
- Open a PR for every change, keep tests green, state what was and was not run on hardware.

## 8. Environment

- Owner's PC: Windows, **VIVE Hub 1.2.7** (tracker server 1.1.4.30, driver DLL 1.0.7.98), installed under `C:\Program Files\VIVE Hub\VIVE Ultimate Tracker\`. Data: `C:\ProgramData\HTC\ViveSoftware\ViveUltimateTracker\` (`config\`, `Log\`, empty `MAP\`).
- Space Calibrator: `C:\Program Files (x86)\Steam\steamapps\common\01spacecalibrator\`.
- Trackers: firmware 1.0.999.178. Use HTC's own `adb.exe` (`CommonTools\ADB`) and `UTLogRetriever.exe` as in section 4.
- **Map backups on the PC:** `%USERPROFILE%\Documents\VIVE-map-backups\2026-10-14_map95_client-slot3\` (includes `hdlog-getmap2.tgz`). Do not move them off the PC.
- The PC session cannot read the cloud project's shared folder, so anything it needs must be sent inline or committed (docs only).
- Evidence (cloud project folder, not in the repo): `vivehub-windows-live-*.md` (findings, crosscheck, usb, hid-probe, ports-pipes, tracker-bundle, map-format), `hdlog-*.txt` log extracts, `research/*.md` drafts of the docs above.

## 9. Safety-check stops

The automatic safety check stopped Claude sessions while they were writing the PC-side map sender (the code, then its docs); no reason was given. Work is therefore at the passive listener (`vut_ft_listen.py`) and the message builders; no sender exists.

## 10. Glossary

- **Dongle**: USB receiver that talks to up to five trackers over RF; HID device.
- **Host / client tracker**: in a scan, one tracker owns the map (host); the others receive it over tracker Wi-Fi.
- **Map / room**: the host tracker's SLAM map, three SQLite files in `/data/mapdata/`; a "room" is our name for a stored map.
- **Standby save**: the tracker writes its map when it goes to sleep.
- **HID opcodes**: command ids on the USB HID link (e.g. `0xa002` status, `0xa201` get property, `0x56` generate log/map archive).
- **`-getmap`**: option of HTC's `UTLogRetriever.exe` that makes the log bundle include the map.
- **`file_pack_info`**: JSON that accompanies a map pack sent between trackers; format unknown (502 bytes for map packs).
- **Pack**: `file_pack_info` plus the three databases, sent host to client via port 8053.
- **`FK<n>` / `P61` / `P64`**: control-link strings: file-table ack, state report, command.
- **Messages 22 / 23 / 24**: transfer header, trailer (CRC-32) and tracker status on the file-transfer link.
- **VBP**: VIVE Business; its "Map Import" path uses `persist.vbp.map_*` and `autosave0`.
- **`MAP_REUSE_OK` / `MAP_REUSE_FAIL_FEATURE_DIFF`**: tracker messages when it relocalises into a stored map (basis of auto room detection).
- **`ATM20` / `ATM51`**: tracker mode commands (host mapping mode / file-transfer mode); `FW2` / `FW0` toggle firmware mode.
- **pyvut**: Python library for the dongle HID protocol (no license; external dependency only).
- **Space Calibrator**: SteamVR overlay that aligns tracker space to the headset's.
