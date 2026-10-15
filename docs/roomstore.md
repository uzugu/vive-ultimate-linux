# Room store

Approach C of the roadmap (`docs/roadmap.md`): a saved room is a name plus the calibration that lines the trackers up with
the headset's playspace in that room. Switching rooms rewrites the driver's calibration file
([calibration.md](calibration.md)); SteamVR picks it up live. It works without any new tracker capability, so it ships
before the map-import work.

## Layout

`$ULTIMATE_TRACKER_ROOMS`, else `$XDG_DATA_HOME/ultimate-tracker/rooms` (default `~/.local/share/...`):

```text
active                 slug of the active room
<slug>/room.json       name, created, calibration {translation_m, rotation_xyzw}, host_serial, map times, notes
<slug>/maps/*.db       optional private copies of exported tracker maps (mode 0700)
```

`room.json` is versioned (`"version": 1`); a different version is refused instead of guessed at.

## Commands (`vut-room`, package `python/vut_roomstore`)

```bash
vut-room new "Living room" --offset 0,0,1.2        # calibration starts as given (default identity)
vut-room import-htc "Living room" Calibration.json # take transform + map times from HTC's file
vut-room use "Living room"                         # mark active and rewrite ~/.config/ultimate-tracker/calibration.txt
vut-room list | show NAME | delete NAME
vut-room attach-maps "Living room" general.db map_1.db kf_1.db
```

## Privacy

Tracker maps hold camera images of the owner's room. `attach-maps` copies them only into the owner's store, sets the
directory to 0700, and **refuses to run if the store sits inside a git work tree**. No map file belongs in this
repository or in any PR.

## Assumptions to check

- HTC's `Calibration.json` `transform.position` / `rotation` is read as the same translation + quaternion our driver
  applies. The saved sample (`vivehub-windows-live-Calibration.json`) has the shape of a yaw-only gravity-aligned
  transform, which fits, but nobody has compared the two on a live setup. A non-1 `scale` is refused.
- A room's calibration is only meaningful together with that room's map (a rebuilt map has a new origin). Until map
  import works, switching rooms means "I rebuilt or kept the map for this room myself".
