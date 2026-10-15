# Windows build

The pose daemon and the SteamVR driver also build on Windows. Local Windows 11 checks now build the driver and exercise the app with mock trackers; see [windows-app-testing.md](windows-app-testing.md). Real tracker streaming and loading this driver inside SteamVR remain unverified. CI also builds and tests the Windows transport.

## Transport

Windows has no usable Unix sockets for this, so the default endpoint is loopback TCP: `tcp:127.0.0.1:38450` (see `protocol/pose-v1.md`, Endpoints). Override with `ULTIMATE_TRACKER_SOCKET_PATH` for both processes, or `--socket-path` on the daemon. Only loopback addresses are accepted.

## Build

```
git clone --depth 1 --branch v2.15.6 https://github.com/ValveSoftware/openvr openvr
cmake -S steamvr_driver -B build -DOPENVR_SDK_PATH=openvr
cmake --build build --config Release
```

The staged driver lands in `build/stage/ultimate_tracker_linux/` with `bin/win64/driver_ultimate_tracker_linux.dll`. Register it with `vrpathreg adddriver <stage path>` (from SteamVR's `bin\win64`), the same way as on Linux.

## Calibration file

Windows default: `%APPDATA%\ultimate-tracker\calibration.txt` (or `ULTIMATE_TRACKER_CALIBRATION`).

## Run

```
pip install -e python/pose_daemon
ultimate-linux-support-daemon --source mock
```

## Not done

- Real tracker access from Windows (the daemon's `pyvut` source is Linux/libusb oriented; HTC's Windows runtime is the PC agent's area).
- Testing inside real SteamVR.
