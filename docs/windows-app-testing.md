# Local Windows app validation (2026-10-15)

Integration base: `main` at `33120e3` (merged PRs through #23), plus the PC
work from #10-#13 and the T9 claim #24. Older uncommitted local edits were saved
in Git stash before the main checkout was fast-forwarded. An isolated integration
worktree keeps the earlier T1/T2 branches intact. No remote PRs were merged by
this validation session.

## Environment and results

Windows 11, Python 3.13.7, MSVC 19.44 / Visual Studio 2022 Build Tools,
Windows SDK 10.0.20348.0, OpenVR v2.15.6, PyInstaller 6.22.3.

- Full Python app/protocol/tool suite: **107 passed, 77 subtests passed**,
  including a real Tk window/widget test and TCP daemon tests.
- OpenVR-free C++ tests: **2/2 passed** (IPC and calibration).
- Full Windows driver: built and staged as
  `build/driver/stage/ultimate_tracker_linux/bin/win64/driver_ultimate_tracker_linux.dll`.
- Installed client and frozen `dist/vut.exe`: doctor offline/online, two synthetic
  rooms, calibration selection, six poses from two mock trackers, and C++ client
  integration pass using `tools/smoke_app.py`.

The smoke harness starts a source Python daemon; it does not validate running a
frozen daemon. Tk widget checks exercise status values and the calibration button;
they are not a full visual review or a physical-device check. Room/calibration
writes use temporary files outside Git. No private maps or HTC binaries are
included. HTC's service was not stopped for these app checks.

## Fixes found by exercising the app

1. GUI close could hang on a silent connected daemon: `makefile` reader close
   blocked behind a read. The stream client now uses cancellable socket reads and
   bounded connection attempts; shutdown clears GUI connection state. A silent
   TCP server reproduces the old failure and verifies the fix.
2. Python calibration and room switching wrote `~/.config` on Windows, while the
   driver read `%APPDATA%`. Both now follow the driver's override/XDG/APPDATA
   precedence. GUI room switching shares the room CLI path.
3. A failed calibration-file write still marked the requested room active.
   The active marker is now written only after the calibration write succeeds.
   These are two file writes, not a transaction across both paths: a failure while
   updating the active marker after calibration succeeds is still possible.
4. The room-map permission test assumed POSIX mode bits on Windows. It now checks
   those bits only on POSIX; documentation states that Windows inherits parent
   ACLs and does not receive an application-enforced private ACL.
5. GUI status hid `lost` behind the device connection flag. It now shows tracking
   state, provides horizontal scrolling and a room refresh button, and explains
   that selecting a room applies calibration rather than importing a tracker map.
6. `vut doctor` now reports an invalid endpoint without a Python traceback.

Windows CI now covers app/room/dongle/settings/codec/tool tests, in addition to
pose-daemon tests. Package CI also exercises the frozen client against a source
mock daemon so it tests more than help output.

## Reproduce

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install pytest pyinstaller -e python/pose_daemon -e python/vut_app -e python/vut_roomstore -e python/vut_dongle -e python/vut_settings -e python/htc_pipe_codec
.venv/Scripts/python.exe -m pytest -q tests python/pose_daemon/tests python/vut_app/tests python/vut_roomstore/tests python/vut_dongle/tests python/vut_settings/tests python/htc_pipe_codec/tests
cmake -S steamvr_driver -B build/tests -DUTS_BUILD_DRIVER=OFF -DUTS_BUILD_TESTS=ON
cmake --build build/tests --config Release
ctest --test-dir build/tests -C Release --output-on-failure
.venv/Scripts/python.exe tools/smoke_app.py --app dist/vut.exe --cpp-client build/tests/Release/ipc_pose_client_test.exe
.venv/Scripts/python.exe tools/run_mock_demo.py
```

Build the executable first using `docs/packaging.md`; build the driver using
`docs/windows.md`. Neither binary is committed.

## Outstanding T9 checks

Driver registration/loading inside a real SteamVR session and validation with
one/two physical trackers remain unperformed. Pairing and tracker-map import
remain unavailable in this app. Further tracker/dongle actions follow the owner's
per-step approval rule in HANDOFF section 7.
