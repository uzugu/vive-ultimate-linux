#!/usr/bin/env python3
"""Experimental room-switching prototype: save and restore a tracker's SLAM map over adb.

The Ultimate Tracker keeps its map on-device in /data/lambda and /data/mapdata
(see docs/re/vivehub-linux-notes.md). This tool snapshots those directories from a
tracker connected over USB and restores them later.

WARNING: does NOT work on firmware 1.0.999.178 (VIVE Hub 1.2.7). There adbd only
answers `ls -l /sdcard/`; any other shell command closes at once and `pull` of the map
directories fails. Kept for older firmware with an open adb shell (pyvut's author had
one). Map export now works another way (docs/re/vivehub-map-format.md); import is unsolved.

Usage:
  vut_rooms.py check
  vut_rooms.py save <room> [--serial S]
  vut_rooms.py load <room> [--serial S]
  vut_rooms.py list
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

MAP_DIRS = ["lambda", "mapdata"]
REMOTE_TMP = "/data/local/tmp/vut_room.tar"
DEFAULT_STORE = Path.home() / ".local/share/vut/rooms"


def adb(serial: str | None, *args: str, capture: bool = True, stdout=None) -> subprocess.CompletedProcess:
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    return subprocess.run(cmd, check=True, capture_output=capture and stdout is None, stdout=stdout)


def shell(serial: str | None, command: str) -> str:
    return adb(serial, "shell", command).stdout.decode(errors="replace").strip()


def device_serial(serial: str | None) -> str:
    return serial or shell(None, "getprop ro.serialno")


def cmd_check(args) -> int:
    print(adb(None, "devices", "-l").stdout.decode())
    print("whoami:", shell(args.serial, "id"))
    for d in MAP_DIRS:
        print(f"--- /data/{d}")
        print(shell(args.serial, f"ls -la /data/{d} 2>&1; du -s /data/{d} 2>&1"))
    print("tar:", shell(args.serial, "command -v tar || echo missing"))
    return 0


def cmd_save(args) -> int:
    serial = device_serial(args.serial)
    room_dir = args.store / args.room
    room_dir.mkdir(parents=True, exist_ok=True)
    out = room_dir / f"{serial}.tar"
    with open(out, "wb") as f:
        adb(args.serial, "exec-out", f"tar -C /data -cf - {' '.join(MAP_DIRS)}", stdout=f)
    meta = {"serial": serial, "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "bytes": out.stat().st_size}
    (room_dir / f"{serial}.json").write_text(json.dumps(meta, indent=2))
    print(f"saved {out} ({meta['bytes']} bytes)")
    return 0


def cmd_load(args) -> int:
    serial = device_serial(args.serial)
    snap = args.store / args.room / f"{serial}.tar"
    if not snap.exists():
        print(f"no snapshot for tracker {serial} in room '{args.room}'", file=sys.stderr)
        return 1
    adb(args.serial, "push", str(snap), REMOTE_TMP)
    dirs = " ".join(f"/data/{d}" for d in MAP_DIRS)
    shell(args.serial, f"rm -rf {dirs} && tar -C /data -xf {REMOTE_TMP} && rm {REMOTE_TMP} && sync")
    print(f"restored room '{args.room}' to {serial}; power-cycle the tracker to reload the map")
    return 0


def cmd_list(args) -> int:
    if not args.store.exists():
        return 0
    for room in sorted(p for p in args.store.iterdir() if p.is_dir()):
        trackers = sorted(p.stem for p in room.glob("*.tar"))
        print(f"{room.name}: {', '.join(trackers) or '(empty)'}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store", type=Path, default=DEFAULT_STORE)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in [("check", cmd_check), ("save", cmd_save), ("load", cmd_load), ("list", cmd_list)]:
        sp = sub.add_parser(name)
        if name in ("save", "load"):
            sp.add_argument("room")
        sp.add_argument("--serial", help="adb serial when several trackers are plugged in")
        sp.set_defaults(fn=fn)
    args = p.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
