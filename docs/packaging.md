# Packaging: the `vut` command

`python/vut_app` provides one `vut` command that dispatches to the existing tools:

| Command | Runs |
| --- | --- |
| `vut daemon` | pose daemon (`ultimate-linux-support-daemon`) |
| `vut pose-dump`, `vut inspect`, `vut capture` | the matching daemon helpers |
| `vut calibrate` | calibration fit |
| `vut room ...` | room store (`vut-room`, see `docs/roomstore.md`) |
| `vut map ...` | map building: `plan`, `replay`, `quality` (see `docs/mapbuild.md`) |
| `vut doctor` | shows endpoint and checks whether the daemon answers (read-only) |

Arguments after the subcommand go to that tool unchanged (`vut daemon --help`).

## Single-file build

```
pip install pyinstaller -e python/pose_daemon -e python/vut_roomstore -e python/vut_mapbuild -e python/vut_app
packaging/build.sh        # writes dist/vut (dist/vut.exe on Windows)
```

CI builds it for Linux x86-64, Linux ARM64 and Windows x86-64 and uploads each as an artifact (job `package`). PyInstaller cannot cross-compile, so each target builds on its own runner.

## Not included

- `pyvut` (the real tracker source) is an external dependency and is not bundled; the frozen build runs the mock source only until packaging of the hardware source is settled.
- The SteamVR driver binary is built separately (`steamvr_driver`, `docs/windows.md`).
- The GUI is a skeleton (see `vut gui` below); pairing is not wired.

## `vut gui`

`vut gui` opens a small Tk window (Tk ships with Python on Windows and macOS; on Debian/Ubuntu install `python3-tk`). Tabs:

- **Status**: live trackers from the daemon (state, tracking label, battery, buttons, position), plus the daemon's `HELLO` and last `EVENT`. Reconnects by itself when the daemon restarts.
- **Map**: map-building progress and buttons; no transport to the trackers yet, see `docs/mapbuild.md`.
- **Rooms**: the room store (`docs/roomstore.md`); "Use selected room" rewrites the driver's calibration file.
- **Pair**: read-only placeholder. Pairing needs dongle commands that have not been verified on hardware (HANDOFF T2/T3).

The logic is in `vut_app/gui_model.py` (headless, unit-tested with a real daemon over TCP); `gui.py` is only the Tk layout. CI runs a window smoke test under a virtual display. Nothing here has been looked at by a person yet, so expect layout rough edges.
