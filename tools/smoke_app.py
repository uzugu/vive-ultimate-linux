#!/usr/bin/env python3
"""Exercise an installed or frozen vut client against a mock daemon; never uses hardware.

Run with the repository's Python environment (pose_daemon and vut_app installed):
  python tools/smoke_app.py --app dist/vut.exe --cpp-client build/tests/Release/ipc_pose_client_test.exe
All room/calibration writes are isolated in a temporary directory outside Git.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--cpp-client", type=Path)
    args = parser.parse_args()
    app = str(args.app.resolve())
    with tempfile.TemporaryDirectory(prefix="vut-smoke-") as temp:
        root = Path(temp)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = dict(os.environ, ULTIMATE_TRACKER_SOCKET_PATH=f"tcp:127.0.0.1:{port}",
                   ULTIMATE_TRACKER_ROOMS=str(root / "rooms"),
                   ULTIMATE_TRACKER_CALIBRATION=str(root / "calibration.txt"))

        def run(*command: str, expected: int = 0) -> str:
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=20)
            if result.returncode != expected:
                raise RuntimeError(f"{command[1:]} returned {result.returncode}: {result.stderr}")
            return result.stdout

        run(app, "version")
        run(app, "daemon", "--help")
        run(app, "gui", "--help")
        run(app, "doctor", expected=1)
        for room, offset in (("Room A", "1,0,0"), ("Room B", "0,0,2")):
            run(app, "room", "new", room, "--offset", offset)
        run(app, "room", "use", "room-b")
        assert (root / "rooms/active").read_text().strip() == "room-b"
        assert (root / "calibration.txt").read_text().startswith("CALIBRATION 1 0.000000000 0.000000000 2.000000000")
        assert "room-b" in run(app, "room", "list")

        with (root / "daemon.log").open("w") as log:
            daemon = subprocess.Popen([sys.executable, "-m", "vut_app", "daemon", "--source", "mock",
                                       "--tracker-count", "2"], env=env, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    if daemon.poll() is not None:
                        raise RuntimeError("mock daemon exited during startup")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                            break
                    except OSError:
                        time.sleep(0.05)
                else:
                    raise RuntimeError("mock daemon did not start")
                assert "reachable" in run(app, "doctor")
                poses = [json.loads(line) for line in run(app, "pose-dump", "--limit", "6", "--json").splitlines()]
                assert len(poses) == 6 and {p["serial"] for p in poses} == {"mock-0", "mock-1"}
                if args.cpp_client:
                    cpp_env = dict(env, UTS_E2E_SOCKET=env["ULTIMATE_TRACKER_SOCKET_PATH"])
                    subprocess.run([str(args.cpp_client.resolve())], env=cpp_env, check=True, timeout=20)
            finally:
                daemon.terminate()
                try:
                    daemon.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    daemon.kill()
                    daemon.wait(timeout=5)
    print("PASS: doctor offline/online, room switching, six mock poses" +
          (", Python-to-C++ integration" if args.cpp_client else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
