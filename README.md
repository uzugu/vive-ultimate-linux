# Ultimate Linux Support

This repository is the starting point for using HTC VIVE Ultimate Trackers on Linux with SteamVR.

The current implementation target is:

1. Read tracker poses on Linux through `pyvut`.
2. Publish those poses to a local IPC bridge.
3. Expose them to SteamVR through a Linux OpenVR driver as generic trackers.
4. Add calibration so the tracker space lines up with the HMD/controller space.

## Current state

This scaffold covers the first two engineering layers:

- a Python pose daemon with a mock source and a `pyvut` adapter stub
- a simple line-based pose protocol over a Unix domain socket
- a Linux OpenVR driver skeleton that can consume the protocol once the OpenVR SDK is installed locally

What is not done yet:

- real `pyvut` validation against hardware
- tracker-to-SteamVR calibration
- SteamVR dashboard UX
- packaging and installer scripts

## Repository layout

- [docs/implementation-brief.md](docs/implementation-brief.md): architecture and research summary
- [protocol/pose-v1.md](protocol/pose-v1.md): local IPC contract between the daemon and the SteamVR driver
- [python/pose_daemon](python/pose_daemon): Python daemon and source adapters
- [steamvr_driver](steamvr_driver): Linux OpenVR driver skeleton

## External dependencies

This repo does not commit upstream dependency checkouts under `vendor/`.

For local development, clone them like this:

```bash
mkdir -p vendor
git clone https://github.com/nijkah/pyvut vendor/pyvut
git clone https://github.com/ValveSoftware/openvr vendor/openvr
```

## Quick start

### 1. Run the daemon with mock poses

```bash
cd python/pose_daemon
python -m venv .venv
source .venv/bin/activate
pip install -e .
ultimate-linux-support-daemon --source mock --socket-path /tmp/ultimate-tracker-linux.sock
```

This publishes synthetic tracker poses over a Unix socket using the documented `POSE 1 ...` protocol.

### 2. Build the driver skeleton

The driver requires a local OpenVR SDK checkout. Point `OPENVR_SDK_PATH` at the OpenVR repository root.

```bash
cmake -S steamvr_driver -B steamvr_driver/build -DOPENVR_SDK_PATH=/path/to/openvr
cmake --build steamvr_driver/build
```

If you cloned the SDK into `vendor/openvr`, use:

```bash
cmake -S steamvr_driver -B steamvr_driver/build -DOPENVR_SDK_PATH="$PWD/vendor/openvr"
cmake --build steamvr_driver/build
```

The staged runtime layout is emitted under `steamvr_driver/build/stage/ultimate_tracker_linux`.

## Notes

- VRChat on Linux is still unofficial. The goal here is SteamVR compatibility first.
- HTC's official PCVR path for Ultimate Trackers is still Windows-centric, which is why `pyvut` is the important Linux building block.

## Milestone 0

Milestone 0 is now scaffolded for real hardware validation:

- `ultimate-linux-support-daemon`
- `ultimate-linux-support-pose-dump`
- `ultimate-linux-support-inspect-socket`
- `ultimate-linux-support-capture`

The step-by-step bring-up notes are in [docs/milestone-0-testing.md](docs/milestone-0-testing.md).
Additional `pyvut` bring-up notes are in [docs/pyvut-troubleshooting.md](docs/pyvut-troubleshooting.md).
The first SteamVR end-to-end path is documented in [docs/steamvr-one-tracker-test.md](docs/steamvr-one-tracker-test.md).
