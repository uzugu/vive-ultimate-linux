# VIVE Ultimate Tracker: prior-art survey

Checked 2026-10-14. Goal of this project: make VIVE Ultimate Trackers (VUT) easy to use on Windows and Linux, with more options than HTC's own software, by building on reverse-engineering work.

## TL;DR

- **The protocol is already partly reverse engineered.** `shinyquagsire23/vive_ultimate_tracker_re` cracked the USB HID / dongle protocol and pairing; `nijkah/pyvut` extended it into a working Python library that gets **6DoF poses on Linux without a headset**.
- **HTC itself shipped "VIVE Hub for Linux (Beta)" in Sept 2026**, with pairing, the map-build wizard and a C++ pose SDK. It is closed-source (VIVE Product EULA), but it removes pyvut's biggest blocker: needing Windows to build the tracking map.
- **Nobody has a SteamVR-on-Linux driver for VUT yet.** ALVR and Monado have open requests/no support. That gap is exactly what `uzugu/vive-ultimate-linux` already scaffolds (pose daemon → Unix socket → OpenVR driver).
- `morluto/rea` is not a Vive project; it is a general reverse-engineering MCP toolkit (Ghidra/IDA/Hopper, .NET, Electron, network captures) useful for analysing HTC's binaries.

## Projects

| Project | What it is | Language / license | State | Useful for us |
|---|---|---|---|---|
| [shinyquagsire23/vive_ultimate_tracker_re](https://github.com/shinyquagsire23/vive_ultimate_tracker_re) | Original RE of the tracker USB HID and the 2.4 GHz dongle protocol. `hid_test.py` (tracker over USB), `rf_hid_test.py` (dongle + RF), `ota_parse.py` (firmware OTA parsing), `tracker_toybox/` | Python, no license file | Last commit 2024-01-15. Pairing multiple trackers works; 3DoF "PCVR mode" over USB works; 6DoF over RF was TODO | Protocol reference, firmware parsing |
| [nijkah/pyvut](https://github.com/nijkah/pyvut) | Fork of the above turned into a library: `UltimateTrackerAPI`, `TrackerPose` callbacks, up to 5 trackers, SLAM host role, Wi-Fi host config, haptics, pygame visualiser, `stream_poses.py`, multi-process demo. Command enums named after HTC's `horusd` daemon | Python, no license stated | Active (last 2026-04-09). Experimental. Needs Windows (SteamVR + VIVE Streaming Hub) for initial map; adb to clear maps; hard-coded HID interface; some commands can brick | **Our pose source today.** Enum files are the best protocol documentation available |
| [ViveRoboticsSoftware/vivehub-linux](https://github.com/ViveRoboticsSoftware/vivehub-linux) | HTC's official Linux beta: UI + `tracker_server` dongle daemon, map-build wizard (x86_64 Unity, box64 on ARM), C++ "VUT SDK" (`libvut_sdk.a`, `vut_demo`). No HMD support | Binary only, proprietary (VIVE Product EULA) | v1.0.0–1.0.3, Sept 2026, Ubuntu 20.04+ | Build maps on Linux (replaces the Windows step). Alternative pose source via SDK. Its daemon/wire traffic is a fresh RE target |
| [morluto/rea](https://github.com/morluto/rea) | "Reverse Engineer Anything" MCP server/CLI for agents: native binaries via Ghidra/IDA/Hopper, .NET, Electron, APKs, network captures, firmware | TypeScript/Node, MIT | Active | Tooling to analyse VIVE Hub (Windows .NET/Unity bits, Linux `tracker_server`), tracker firmware/APK |
| [username223/SteamVRNoHeadset](https://github.com/username223/SteamVRNoHeadset) | SteamVR null-driver config for running without an HMD | config | — | Needed for headset-less SteamVR testing |
| [ALVR issue #3139](https://github.com/alvr-org/ALVR/issues/3139) | Request to support VUT in ALVR | — | Open, no implementation | Shows demand; a SteamVR driver would make ALVR users work too |
| Monado / libsurvive, spacecal, motoc | Linux XR stack and calibration tools | — | No VUT support found | Calibration ideas (motoc/spacecal) for aligning tracker space to HMD space |

Older, not VUT-specific (Lighthouse-era Vive Trackers): [fughilli/ViveTrackedDevice](https://github.com/fughilli/ViveTrackedDevice), [n1ckfg/ViveTrackerExample](https://github.com/n1ckfg/ViveTrackerExample). The Ultimate Tracker uses inside-out camera SLAM, not Lighthouse, so these do not apply directly.

## What this means for the plan

1. **Linux SteamVR driver** (existing scaffold in `uzugu/vive-ultimate-linux`): keep pyvut as the pose source, add a VIVE Hub SDK source as a second option, finish the OpenVR driver and calibration.
2. **Map building on Linux**: use VIVE Hub for Linux now; long term, RE its map-build flow so the whole thing can be open.
3. **Windows "more options"**: Windows already has VIVE Hub; the open angle is a headset-agnostic SteamVR driver / OSC or VMC output that avoids VIVE Hub streaming, plus robotics/mocap use. pyvut's protocol code is OS-neutral (hidapi), so a Windows port is mostly packaging.
4. **RE targets** (with REA/Ghidra): `tracker_server` on Linux, VIVE Hub on Windows, tracker OTA firmware, to fill gaps (6DoF over RF reliability, map management without adb).

## Caveats

- Neither RE repo states a license; we should not copy their code into ours without asking the authors. Depending on pyvut as an external package (as the scaffold does) is fine.
- VIVE Hub binaries are under HTC's EULA; do not redistribute them. Interoperability RE is a separate legal question by jurisdiction.
