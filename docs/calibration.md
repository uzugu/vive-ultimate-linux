# Calibration offset

The Ultimate Tracker reports poses in its own map space. SteamVR needs them in the headset's playspace. The
daemon sends raw tracker-space poses ([protocol/pose-v1.md](../protocol/pose-v1.md)); the SteamVR driver applies
`T_steamvr_from_vut` to every usable pose before handing it to SteamVR (same split HTC uses: the server, not the
driver, owns `Calibration.json`).

## File

One line, `#` comments allowed before it:

```text
CALIBRATION 1 <tx> <ty> <tz> <qx> <qy> <qz> <qw>
```

`p' = R(q) * p + t`, `q' = q_cal * q_pose`, acceleration is rotated by `q_cal`. The quaternion is normalised on load;
zero-length, non-finite, wrong-version or extra-field lines are ignored.

Location: `$ULTIMATE_TRACKER_CALIBRATION`, else `$XDG_CONFIG_HOME/ultimate-tracker/calibration.txt`, else
`~/.config/ultimate-tracker/calibration.txt`. The driver checks the file's modification time every frame, so a tool
can rewrite it while SteamVR runs; a broken or missing file keeps the last good value (identity at start).

Poses that are not usable (lost, all-zero) are passed through uncalibrated, so an offset never turns an empty pose
into a live one.

## Writing it

```bash
# Hold the tracker at two or more spots; note tracker position (from the daemon) and a reference position
# (for example a controller at the same spot in SteamVR). Y is up in both spaces.
ultimate-linux-support-calibrate --pair 0,1,0:0.5,1,0.2 --pair 1,1,0:0.5,1,1.2

# Or set it by hand (yaw about +Y in degrees, then offset in metres):
ultimate-linux-support-calibrate --manual --yaw-deg 90 --offset 0,0,2
ultimate-linux-support-calibrate --identity
```

The fit solves yaw about the up axis plus a translation (least squares). Full 3D rotation is not needed because the
tracker's map is gravity-aligned; a tilted map would need a different fit. Not yet tested with real hardware.
