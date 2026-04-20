# SteamVR Driver Skeleton

This directory contains the Linux OpenVR driver scaffold for exposing Ultimate Tracker poses as SteamVR generic trackers.

## Purpose

The driver consumes the local Unix socket pose stream and translates it into:

- `TrackedDeviceClass_GenericTracker` devices
- live `TrackedDevicePoseUpdated()` calls
- stable serial numbers for SteamVR tracker-role assignment

## Build prerequisites

- a local checkout of `ValveSoftware/openvr`
- a Linux SteamVR environment for actual runtime testing

## Build

```bash
cmake -S steamvr_driver -B steamvr_driver/build -DOPENVR_SDK_PATH=/path/to/openvr
cmake --build steamvr_driver/build
```

For the first real end-to-end test, follow [docs/steamvr-one-tracker-test.md](/mnt/windows/Users/uzuik/Documents/VRmakes/Projects/Ultimate-linux-support/docs/steamvr-one-tracker-test.md).

## Output

The build stages a SteamVR driver runtime tree at:

`steamvr_driver/build/stage/ultimate_tracker_linux`

That tree contains:

- `driver.vrdrivermanifest`
- `resources/`
- `bin/linux64/driver_ultimate_tracker_linux.so`

## Current limitations

- no calibration transform is applied yet
- no dynamic settings UI yet
- no tracker role assignment helper yet
- one-tracker pose validity currently uses a pragmatic heuristic for `pyvut` raw tracking code `18`
