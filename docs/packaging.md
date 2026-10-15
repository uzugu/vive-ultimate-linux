# Packaging: the `vut` command

`python/vut_app` provides one `vut` command that dispatches to the existing tools:

| Command | Runs |
| --- | --- |
| `vut daemon` | pose daemon (`ultimate-linux-support-daemon`) |
| `vut pose-dump`, `vut inspect`, `vut capture` | the matching daemon helpers |
| `vut calibrate` | calibration fit |
| `vut room ...` | room store (`vut-room`, see `docs/roomstore.md`) |
| `vut doctor` | shows endpoint and checks whether the daemon answers (read-only) |

Arguments after the subcommand go to that tool unchanged (`vut daemon --help`).

## Single-file build

```
pip install pyinstaller -e python/pose_daemon -e python/vut_roomstore -e python/vut_app
packaging/build.sh        # writes dist/vut (dist/vut.exe on Windows)
```

CI builds it for Linux x86-64, Linux ARM64 and Windows x86-64 and uploads each as an artifact (job `package`). PyInstaller cannot cross-compile, so each target builds on its own runner.

## Not included

- `pyvut` (the real tracker source) is an external dependency and is not bundled; the frozen build runs the mock source only until packaging of the hardware source is settled.
- The SteamVR driver binary is built separately (`steamvr_driver`, `docs/windows.md`).
- No GUI yet (pair/status/rooms screens are the next piece).
