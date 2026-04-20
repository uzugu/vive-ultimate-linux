# SteamVR One-Tracker Test

This is the first end-to-end SteamVR goal:

1. run the Python daemon against one mapped wireless tracker
2. build the Linux OpenVR driver
3. register the staged driver with SteamVR
4. confirm SteamVR shows one generic tracker

This step is intentionally only for one tracker and does not include calibration yet.

## What changed from the initial scaffold

The first real tracker bring-up showed that the Linux wireless path can produce usable live positions, but `pyvut` reports a raw tracking code of `18` that is not documented in the upstream enum table.

For the one-tracker bring-up, the SteamVR driver now treats these cases as pose-valid:

- `status == ok`
- `tracking_code == 2`
- `tracking_code == 18`
- non-zero positions that are not otherwise marked lost

This is a pragmatic compatibility heuristic for the current observed hardware behavior.

## Build prerequisites

- a local OpenVR SDK checkout from `ValveSoftware/openvr`
- SteamVR installed on Linux
- the pose daemon working with one mapped tracker

If you do not already have the SDK locally:

```bash
mkdir -p vendor
git clone https://github.com/ValveSoftware/openvr vendor/openvr
```

## Build the driver

```bash
cmake -S steamvr_driver -B steamvr_driver/build -DOPENVR_SDK_PATH=/path/to/openvr
cmake --build steamvr_driver/build
```

The staged runtime tree will be:

`steamvr_driver/build/stage/ultimate_tracker_linux`

## Start the pose daemon

Use the mapped tracker only.

```bash
cd python/pose_daemon
source .venv/bin/activate
ultimate-linux-support-daemon \
  --source pyvut \
  --mode DONGLE_USB \
  --wifi-info-path ../../config/wifi_info.local.json
```

## Register the driver with SteamVR

Valve's driver docs say external drivers should be added through `vrpathreg`, and drivers must be registered for SteamVR to load them.

First, locate your SteamVR binary directory on Linux. A common path is:

`$HOME/.steam/steam/steamapps/common/SteamVR/bin/linux64`

Then register the staged driver:

```bash
bash steamvr_driver/scripts/register_driver.sh \
  "$HOME/.steam/steam/steamapps/common/SteamVR/bin/linux64" \
  "$PWD/steamvr_driver/build/stage/ultimate_tracker_linux"
```

To remove it again:

```bash
bash steamvr_driver/scripts/unregister_driver.sh \
  "$HOME/.steam/steam/steamapps/common/SteamVR/bin/linux64" \
  "$PWD/steamvr_driver/build/stage/ultimate_tracker_linux"
```

## SteamVR settings reminder

Valve's driver documentation notes that drivers which are active alongside another HMD driver require `activateMultipleDrivers = true`.

Make sure your SteamVR settings allow multiple drivers before testing the tracker bridge.

## First success criteria

The first end-to-end test is successful if:

- SteamVR loads the external driver without rejecting it
- one generic tracker device is created
- the tracker pose in SteamVR changes as the mapped tracker moves

At this step, it is acceptable if:

- the tracker origin is wrong
- calibration is missing
- tracker role assignment is not finalized yet

## Sources

- OpenVR Driver API docs: https://github.com/ValveSoftware/openvr/blob/master/docs/Driver_API_Documentation.md
- OpenVR Driver Documentation wiki: https://github.com/ValveSoftware/openvr/wiki/Driver-Documentation
- OpenVR Local Driver Registration wiki: https://github.com/ValveSoftware/openvr/wiki/Local-Driver-Registration
