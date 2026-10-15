#!/usr/bin/env python3
"""Open the GUI with two mock trackers and disposable rooms. Never accesses hardware.

Run with the repository environment: python tools/run_mock_demo.py
Close the GUI to stop its daemon and remove the demo room/calibration directory.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from vut_app.gui import main as gui_main
from vut_roomstore import Calibration, RoomStore


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vut-demo-") as temp:
        root = Path(temp)
        store = RoomStore(root / "rooms")
        store.create("Demo room A", Calibration((1, 0, 0)))
        store.create("Demo room B", Calibration((0, 0, 2)))
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        endpoint = f"tcp:127.0.0.1:{port}"
        with (root / "daemon.log").open("w") as log:
            daemon = subprocess.Popen(
                [sys.executable, "-m", "vut_app", "daemon", "--source", "mock",
                 "--tracker-count", "2", "--socket-path", endpoint],
                stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                for _ in range(100):
                    if daemon.poll() is not None:
                        raise RuntimeError("mock daemon exited; check the installed packages")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("mock daemon did not start")
                return gui_main(["--endpoint", endpoint, "--rooms-root", str(store.root),
                                 "--calibration-file", str(root / "calibration.txt")])
            finally:
                daemon.terminate()
                try:
                    daemon.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
