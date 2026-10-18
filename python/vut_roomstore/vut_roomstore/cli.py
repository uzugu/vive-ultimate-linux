from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .store import Calibration, RoomError, RoomStore


def _default_calibration_file() -> str:
    env = os.environ.get("ULTIMATE_TRACKER_CALIBRATION")
    if env:
        return env
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ultimate-tracker", "calibration.txt")


def _vec(text: str) -> tuple[float, ...]:
    return tuple(float(v) for v in text.split(","))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vut-room", description="Keep a calibration per room and switch between them.")
    parser.add_argument("--root", default=None, help="store directory (default: $ULTIMATE_TRACKER_ROOMS or XDG data dir)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list")
    p = sub.add_parser("new")
    p.add_argument("name")
    p.add_argument("--offset", type=_vec, default=(0.0, 0.0, 0.0), help="x,y,z metres")
    p.add_argument("--rotation", type=_vec, default=(0.0, 0.0, 0.0, 1.0), help="qx,qy,qz,qw")
    p.add_argument("--notes", default="")
    for name in ("show", "delete"):
        sub.add_parser(name).add_argument("name")
    p = sub.add_parser("use", help="make a room active and rewrite the driver's calibration file")
    p.add_argument("name")
    p.add_argument("--calibration-file", default=_default_calibration_file())
    p.add_argument("--no-write", action="store_true", help="only mark active; leave the driver file alone")
    p = sub.add_parser("import-htc", help="read a room's calibration from HTC's Calibration.json")
    p.add_argument("name")
    p.add_argument("path")
    p = sub.add_parser("attach-maps", help="copy exported map *.db files into the room's private store")
    p.add_argument("name")
    p.add_argument("files", nargs="+")
    p = sub.add_parser("serve", help="run the room service for the SteamVR overlay (development: fake tracker folder)")
    p.add_argument("--socket", required=True)
    p.add_argument("--fake-tracker", required=True, help="folder standing in for the tracker's map; no real transport exists yet")
    p.add_argument("--calibration-file", default=_default_calibration_file())

    args = parser.parse_args(argv)
    store = RoomStore(args.root)
    try:
        if args.command == "list":
            active = store.active_slug()
            for room in store.list():
                print(f"{'*' if room.slug == active else ' '} {room.slug}  ({room.name})")
        elif args.command == "new":
            room = store.create(args.name, Calibration(args.offset, args.rotation), args.notes)  # type: ignore[arg-type]
            print(f"created {room.slug}")
        elif args.command == "show":
            room = store.get(args.name)
            print(f"{room.name} ({room.slug})")
            print(f"  calibration: t={room.calibration.translation_m} q={room.calibration.rotation_xyzw}")
            print(f"  map files: {', '.join(room.map_files) or 'none'}")
            if room.last_map_creation_time:
                print(f"  last map creation: {room.last_map_creation_time}  quality: {room.map_quality}")
        elif args.command == "delete":
            store.delete(args.name)
        elif args.command == "use":
            room = store.use(args.name, None if args.no_write else args.calibration_file)
            print(f"active room: {room.slug}")
        elif args.command == "import-htc":
            store.import_htc_calibration(args.name, Path(args.path).read_text(encoding="utf-8"))
        elif args.command == "serve":
            from .service import FakeTransport, RoomService, serve

            server = serve(RoomService(store, FakeTransport(args.fake_tracker), args.calibration_file), args.socket)
            print(f"serving on {args.socket}")
            server.serve_forever()
        elif args.command == "attach-maps":
            store.attach_map_files(args.name, args.files)
    except (RoomError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
