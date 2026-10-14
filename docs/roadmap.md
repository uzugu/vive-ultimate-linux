# Roadmap: open multiplatform Ultimate Tracker app with room switching

Goal: one open-source app that replaces VIVE Hub for the Ultimate Tracker part, on **Linux x86-64, Linux
ARM64 and Windows**, with **room switching** as a headline feature. Background: [prior-art-survey.md](prior-art-survey.md),
[re/vivehub-linux-notes.md](re/vivehub-linux-notes.md).

## What "room switching" means here

Today a tracker set holds one map. Moving to another room means rebuilding the map in VIVE Hub, and going
back means rebuilding again. We want:

1. **Saved rooms**: build a map once per room and keep it.
2. **Switch**: pick a room in the app (or let it detect the room) and the trackers track in that room's map
   within seconds, without a rebuild.
3. **Per-room settings**: playspace origin/floor height, calibration offset to the headset's space, tracker roles.

## How it can work (hypotheses to prove on hardware)

| # | Approach | How | Risk |
|---|---|---|---|
| A | **Map snapshots of the host tracker** (a live check showed the PC `MAP` folder is empty and the host tracker owns the map and syncs it to the others; export likely via adb, import via adb or the file-transfer path, see [re/vivehub-windows-map-transfer.md](re/vivehub-windows-map-transfer.md)) | Maps live on the trackers in `/data/lambda` and `/data/mapdata`. Save = `adb pull` from the host tracker into `rooms/<name>/`. Switch = `adb push` back, then restart tracking (`ALE` / `RESET_MAP` / power-cycle) so the tracker reloads it. Clients resync from the host over Wi-Fi as usual. | Needs adb on the tracker over USB; may need a reboot per switch; map may be tied to the map UUID. |
| B | **Auto room detection** | Trackers already report `MAP_REUSE_OK` vs `MAP_REUSE_FAIL_FEATURE_DIFF` when relocalising. Try candidate room maps until one reports reuse OK. | Each try costs a reload; order by last used. |
| C | **Per-room calibration only** | Store origin + headset alignment per room and apply it in our driver, for when a map is rebuilt anyway. | Always works, but no rebuild savings. |

C ships first because it is pure software. A is the real feature; B builds on A.

## Architecture

```
            ┌──────────── vut-core (library) ────────────┐
dongle ─hid─▶ protocol (pyvut-derived) · pairing · map ctl │
tracker ─adb─▶ room store (snapshots, per-room settings)   │
            └──────────────┬─────────────────────────────┘
                     vutd (daemon, one per PC)
        ┌──────────────┼───────────────┬──────────────┐
   SteamVR driver   OSC / VMC out   local socket API   GUI app
   (OpenVR, Win+Linux) (VRChat, etc.)  (pose-v1 + control)  (pair, map, rooms)
```

- **Protocol layer**: hidapi only, so it runs unchanged on Windows, Linux x86-64 and Linux ARM64.
  Start from pyvut's decoder (as an external dependency, it has no license), replace pieces with our own
  clean implementation as RE confirms them.
- **Map building**: phase 1 delegates to VIVE Hub (Windows or the Linux beta) to build a map, then our app
  snapshots it. Phase 2 drives map building ourselves (`ATM20` host mode, `Start/End_Map_Creation` flow).
- **Outputs**: SteamVR driver (the existing skeleton, ported to build on Windows too), OSC/VMC for
  headset-less use, and the existing `POSE 1` socket for robotics/custom apps.
- **Language** (default picked): stay in Python for the daemon while RE is moving fast (pyvut is Python,
  runs on all three platforms, ships via PyInstaller). Port `vut-core` to Rust once the protocol is stable,
  for single-binary installs. The SteamVR driver stays C++.

## Milestones

1. **M0, hardware baseline**: pyvut streams poses from the dongle on Linux x86-64; confirm adb access to a
   tracker and list `/data/lambda`, `/data/mapdata`.
2. **M1, room snapshots (manual)**: CLI `vut room save <name>` / `vut room load <name>`; prove a pulled map
   re-pushed to the tracker reports `MAP_REUSE_OK`.
3. **M2, daemon + SteamVR**: finish the existing daemon and driver; per-room calibration (approach C).
4. **M3, GUI**: pair, status, rooms list with one-click switch. Linux x86-64, ARM64, Windows builds in CI.
5. **M4, auto room detection** (approach B) and our own map-build flow (no VIVE Hub at all).

## What we need from the hardware owner

- Dongle + at least two trackers, a Linux PC, and ideally a Windows PC with VIVE Hub for comparison.
- A USB-C cable to plug a tracker in directly (adb + USB HID).
- Two rooms to test switching.
