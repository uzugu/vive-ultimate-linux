# pyvut Bring-Up Notes

These are the concrete requirements that stood out from the upstream `pyvut` docs and code while bringing up VIVE Ultimate Trackers on Linux.

## 1. The vendored `wifi_info.json` is placeholder data

The vendored file at `vendor/pyvut/pyvut/wifi_info.json` currently contains:

- `ssid = test_5G`
- `pass = testtest`
- `country = US`
- `freq = 5240`

The upstream docs explicitly say to update this before using the dongle helper path.

Use your own file instead of editing the vendored one directly. An example is provided at:

- [config/wifi_info.example.json](/mnt/windows/Users/uzuik/Documents/VRmakes/Projects/Ultimate-linux-support/config/wifi_info.example.json)

Then point the daemon at it:

```bash
ultimate-linux-support-daemon \
  --source pyvut \
  --mode DONGLE_USB \
  --wifi-info-path ../../config/wifi_info.example.json
```

If `vendor/pyvut` is not present yet, clone it locally first:

```bash
mkdir -p vendor
git clone https://github.com/nijkah/pyvut vendor/pyvut
```

## 2. Windows-side readiness still matters

The upstream README says the initial map must be created on Windows with SteamVR and VIVE Streaming Hub, and the trackers should show as ready there before returning to Ubuntu.

If Linux only shows:

- quaternion changes
- fixed position
- `CURRENT_TRACKING_STATE = NOT_INITIALIZED`

then the tracker is still not fully initialized for usable positional tracking.

## 3. For single-tracker debugging, direct USB is the cleanest test

The upstream docs support both:

- `DONGLE_USB`
- `TRACKER_USB`

If you are trying to prove that one mapped tracker can produce real 6DoF on Linux, `TRACKER_USB` is the simplest diagnostic because it bypasses dongle host/client role assignment.

Run either the upstream demo or the local daemon with the mapped tracker connected directly over USB.

Upstream:

```bash
source python/pose_daemon/.venv/bin/activate
python vendor/pyvut/scripts/stream_poses.py --mode TRACKER_USB
```

Local daemon:

```bash
cd python/pose_daemon
source .venv/bin/activate
ultimate-linux-support-daemon --source pyvut --mode TRACKER_USB
```

If `TRACKER_USB` gives real changing position while `DONGLE_USB` does not, the tracker map is probably fine and the problem is in the dongle-side bring-up path.

## 4. Power-on order matters on the dongle path

`pyvut`'s dongle path auto-promotes the first tracker it sees to the SLAM host.

So for the dongle path:

1. plug in the dongle
2. power on only the mapped tracker first
3. wait for tracking to initialize
4. only then bring up additional trackers
