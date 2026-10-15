"""`vut`: one entry point that dispatches to the existing tool mains.

Subcommands keep their own argument parsing; `vut daemon --help` is the daemon's help.
Imports are explicit (not importlib strings) so PyInstaller finds every module.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence

from . import __version__


def _daemon() -> Callable[[], object]:
    from ultimate_linux_support.daemon import main

    return main


def _pose_dump() -> Callable[[], object]:
    from ultimate_linux_support.pose_dump import main

    return main


def _inspect() -> Callable[[], object]:
    from ultimate_linux_support.inspect_socket import main

    return main


def _capture() -> Callable[[], object]:
    from ultimate_linux_support.capture import main

    return main


def _calibrate() -> Callable[[], object]:
    from ultimate_linux_support.calibration import main

    return main


def _room() -> Callable[[], object]:
    from vut_roomstore.cli import main

    return main


def _map() -> Callable[[], object]:
    from .map_cli import main

    return main


def _gui() -> Callable[[], object]:
    from .gui import main

    return main


COMMANDS: dict[str, tuple[Callable[[], Callable[[], object]], str]] = {
    "daemon": (_daemon, "run the pose daemon (serves poses to the SteamVR driver)"),
    "pose-dump": (_pose_dump, "print poses from the daemon"),
    "inspect": (_inspect, "inspect the daemon socket"),
    "capture": (_capture, "record a pose capture"),
    "calibrate": (_calibrate, "fit the SteamVR calibration from captures"),
    "gui": (_gui, "open the status / rooms / pairing window (needs Tk)"),
    "room": (_room, "per-room calibration store (list/new/use/...)"),
    "map": (_map, "map building: plan, replay a server log, check quality (no hardware access)"),
}


def doctor() -> int:
    """Report where things live and whether the daemon answers. Read-only."""
    import platform
    import socket

    from ultimate_linux_support.endpoint import default_endpoint_spec, parse_endpoint

    spec = default_endpoint_spec()
    print(f"vut {__version__}  python {platform.python_version()}  {platform.system()} {platform.machine()}")
    print(f"endpoint: {spec}")
    calibration = os.environ.get("ULTIMATE_TRACKER_CALIBRATION", "(default location)")
    print(f"calibration file: {calibration}")
    endpoint = parse_endpoint(spec)
    try:
        if endpoint.kind == "tcp":
            conn = socket.create_connection((endpoint.host, endpoint.port), timeout=1)
        else:
            conn = socket.socket(socket.AF_UNIX)
            conn.settimeout(1)
            conn.connect(endpoint.path)
        conn.close()
        print("daemon: reachable")
        return 0
    except OSError as exc:
        print(f"daemon: not reachable ({exc}); start it with `vut daemon`")
        return 1


def _usage() -> str:
    lines = ["usage: vut <command> [args...]", "", "commands:"]
    lines += [f"  {name:<10} {help_text}" for name, (_, help_text) in COMMANDS.items()]
    lines += ["  doctor     show endpoint/paths and check whether the daemon is reachable", "  version    print the version"]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0 if args else 2
    command, rest = args[0], args[1:]
    if command in ("version", "--version"):
        print(__version__)
        return 0
    if command == "doctor":
        return doctor()
    entry = COMMANDS.get(command)
    if entry is None:
        print(f"vut: unknown command '{command}'\n\n{_usage()}", file=sys.stderr)
        return 2
    target = entry[0]()
    saved = sys.argv
    sys.argv = [f"vut {command}", *rest]
    try:
        result = target()
    finally:
        sys.argv = saved
    return result if isinstance(result, int) else 0
