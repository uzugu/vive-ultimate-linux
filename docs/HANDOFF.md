# Handoff: open VIVE Ultimate Tracker app (state of 2026-10-15)

For agents continuing this project from the owner's own PC. Repo: <https://github.com/uzugu/vive-ultimate-linux>.
Detailed notes are linked below. Paths like `research/...` are in the project's shared folder and, once PR #1 is merged
or checked out, the same files live under `docs/`. Claims in the notes are tagged code / string / inferred / guess: trust them in that order.

## 1. Goal

One open app for **Linux x86-64, Linux ARM64 and Windows** that replaces the tracker part of VIVE Hub. The main objective is
**room switching**: keep one saved map per room and load the right one onto the trackers without rebuilding it.
First target is parity with VIVE Hub for Windows (v1.2.7), then the multiplatform app. Plan and milestones: `research/roadmap.md`
(`docs/roadmap.md`), parity list: `research/windows-parity.md`.

## 2. Repo layout and the four PRs

All PRs are open against `main`, which still holds only the original scaffold (Python pose daemon in `python/pose_daemon`,
Linux OpenVR driver skeleton in `steamvr_driver`, `protocol/pose-v1.md`).

| PR | Branch | Holds |
|---|---|---|
| #1 | `docs/prior-art-survey` | `docs/prior-art-survey.md`, `docs/roadmap.md`, `docs/windows-parity.md`; `docs/re/vivehub-linux-notes.md`, `vivehub-windows-notes.md`, `vivehub-windows-map-transfer.md`, `vivehub-map-format.md`, `vivehub-map-import.md`; tools `python/tools/vut_rooms.py` (adb snapshot, **unusable on firmware 1.0.999.178**), `vut_filetransfer.py` (builds/parses transfer messages 22/23, CRC-32), `vut_ft_listen.py` (passive TCP 8053 listener, never sends), `tools/re/xref.py`, tests. Latest commit 5ccaa77. |
| #2 | `claude/project-thread-tavwzs` | `docs/re/pairing-and-status.md` (dongle pair/unpair 0x1D, five-slot status 0x1E, battery decoding), `tools/re/pe_disasm.py`. Draft. |
| #3 | `claude/project-thread-6wlvjr` | `docs/re/settings-power.md` (auto-sleep, power off, reboot, reset, camera fps, logs, FOTA), `python/vut_settings` command and `Config.ini` builders with tests. Draft. |
| #4 | `claude/project-thread-kc6oqk` | `docs/re/driver-pipes.md` (SteamVR driver and server pipes, 20-byte framing, command tables), `python/htc_pipe_codec` with tests. Draft. |

#2 to #4 are static analysis only (nothing run on hardware); their wire formats are hypotheses until captured.

## 3. Proven on hardware (owner's PC and trackers)

- **Firmware 1.0.999.178** on the trackers; Android 7.1.2 userdebug build (arm64 msm8953).
- **adb is locked down**: only `shell ls -l /sdcard/`, sync listings of `/sdcard`, and a pull of `/sdcard/hdlog.tgz` work. Everything under `/data` is refused.
- **USB HID property reads work** (an allowlist). The HID file service sees only the SD card.
- **Map export works** through HTC's log tool: `UTLogRetriever.exe "-LogFolder:<dir>" -getmap` sends HID opcode 0x56 with type=1; the tracker builds `/sdcard/hdlog.tgz` (about 4 minutes, ~298 MB); `adb pull` it with HTC's own `adb.exe`; delete it afterwards with the HID file delete (bare name). Procedure: `vivehub-windows-live-map-format-20261014T230650-a2f0.md`.
- **Map format**: three SQLite 3 files in `data/hdlog/mapdata/`: `general.db` (registry plus visual-word index), `map_<id>.db` (ORB-SLAM-style map: keyframes, points, floor plane), `kf_<id>.db` (keyframe image pyramids).
- **One map per tracker.** `general.db` says `map_size` 3, but that equals `persist.lambda.multimap.size` and is probably a size class; every logged save holds exactly one map. Several rooms side by side on one tracker is **not evidenced**.
- **Maps are saved at standby** (about 6 s on "entered sleeping"), so an export reflects the last standby, not the live map.
- The PC `MAP\` folder is empty: the host tracker owns the map and syncs it to clients over Wi-Fi (17 to 19 s). Which tracker is host is per scan.

## 4. Map-transfer protocol decoded so far (from tracker logs, host to client)

Source: `research/vivehub-map-import.md` sections 3a and 3b.

- The tracker **dials out** to a TCP server on the PC/host. `ViveTrackerServer.exe` listens on TCP 3680, 8053, 9005, 9527, 15680 and UDP 9005; only 8053 (file transfer) and 9527 are tied to transfers so far, and 9527's exact role is unconfirmed. To receive tracker connections ourselves HTC's server must be stopped.
- Control link: host sends ack `FK<n>`, tracker answers and connects to `<host>:8053` to fetch file index `<n>`. State acks `P61:<key>,<value>`; reset trigger `P64:3`.
- Frames are 0x80 bytes, magic `0xB9D7`. Download family u21 to u24: hello, header (22: size, mtu 1048576, **output path chosen by the sender**), data, trailer (23: CRC-32 poly 0xEDB88320), status (24). Upload family u11 to u14 is tracker to host. HTC's PC library confines itself to `/sdcard/`; whether the tracker accepts other paths from a PC is untested.
- **Pack order** into `/data/lambda/<host slot>/general_map/`: (1) `file_pack_info_<N>_8.json`, **502 bytes**, (2) `<N>_8_general.db`, (3) `<N>_8_map_<id>.db`, (4) `<N>_8_kf_<id>.db`. The three databases are the same files the export gives, renamed.
- Before the pack, an identity step: each side sends a small `file_pack_info_<n>_<m>.json` (~217/219 B) and its `pubkey.pem` (426 B) into `/data/lambda/<dev>/ed/`.
- HTC's separate VBP route (`persist.vbp.map_*` plus a file `autosave0`, command `FD`+`autosave0`) is another candidate, from static analysis only: `research/vivehub-map-import.md` sections 1 to 3.

## 5. Open questions

1. **Format of the 502-byte `file_pack_info`** (names, sizes, checksums?) and whether it is **signed** against a sender's public key. No log contains its content.
2. Whether a tracker accepts a pack from a PC peer at all, and from which paths; whether import needs the identity (`ed/`) step first.
3. What `autosave0` is, and whether the VBP route accepts these databases.
4. Multi-map: build a second room without clearing the first, let the tracker standby, re-export, compare `general.db`.
5. Which of TCP 3680, 9005, 9527, 15680 does what; pose format details in `driver-pipes.md` (float order) need a capture.
6. Power frequency setting, `smallmap/` and `boundary_id_table_` contents, whether a client's map copy is byte-identical to the host's.
7. VIVE EULA reverse-engineering clause not yet reviewed; review before publishing derived work.

Next planned hardware step (not run): our own passive/active listener, then send a 1 KB test file to `/sdcard/` and read the tracker's message 24 reply (`research/vivehub-map-import.md` section 4).

## 6. Rules

- **No HTC binaries in the repo or any PR.** Notes, names, ids and layouts only. The HTC files are in the project folder as `vivehub-windows-*.zip` (index: `vivehub-windows-inventory-20261014T162631-90f9.md`).
- **Map files contain camera images of the owner's room.** They stay on the owner's PC (backup folder `Documents\VIVE-map-backups`); never upload, commit or paste them. Structure only in notes.
- **The owner approves each hardware step** on the trackers before it runs. Prefer the smallest step, and use a spare tracker with an exported backup for anything that writes.
- Division of labour: cloud sessions analyse and write exact commands or scripts; the PC session runs concrete, pre-planned steps and reports output.

## 7. Safety-check stops

The automatic safety check stopped Claude sessions twice while they were writing the PC-side map sender (the code, then its docs); no reason was given. The PC-side work is therefore at the passive listener (`vut_ft_listen.py`, commit 5ccaa77) and the message builders; no sender exists.

## 8. Where the evidence is

`research/`: `prior-art-survey.md`, `roadmap.md`, `vivehub-linux-notes.md`, `vivehub-windows-notes.md`, `vivehub-windows-map-transfer.md`, `vivehub-map-import.md`, `re-pairing-status.md`, `re-settings-power.md`, `re-driver-pipes.md`, `windows-parity.md`.
Live checks (project root): `vivehub-windows-live-findings.md`, `-crosscheck.md`, `-usb.md`, `-hid-probe.md`, `-ports-pipes.md`, `-tracker-bundle.md`, `-map-format-20261014T230650-a2f0.md`, `-adb-and-prior-art.md`; log extracts `hdlog-map-receive.txt`, `hdlog-transfer-lines.txt`.
