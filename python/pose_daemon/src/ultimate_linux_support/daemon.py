from __future__ import annotations

import argparse
import asyncio
import signal

from .endpoint import default_endpoint_spec
from .server import PoseServer
from .sources import MockPoseSource, PoseSource, PyVutPoseSource


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pose daemon for VIVE Ultimate Trackers on Linux.")
    parser.add_argument("--socket-path", default=default_endpoint_spec(),
                        help="unix:/path, tcp:127.0.0.1:PORT or a bare socket path")
    parser.add_argument("--source", choices=("mock", "pyvut"), default="mock")
    parser.add_argument("--hz", type=float, default=90.0)
    parser.add_argument("--tracker-count", type=int, default=3, help="Only used by the mock source.")
    parser.add_argument("--mode", default="DONGLE_USB", help="pyvut mode, for example DONGLE_USB.")
    parser.add_argument("--wifi-info-path", default=None)
    return parser.parse_args()


def build_source(args: argparse.Namespace) -> PoseSource:
    if args.source == "mock":
        return MockPoseSource(tracker_count=args.tracker_count)
    return PyVutPoseSource(mode=args.mode, wifi_info_path=args.wifi_info_path)


async def _run() -> None:
    args = parse_args()
    source = build_source(args)
    server = PoseServer(socket_path=args.socket_path, source=source, hz=args.hz)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # Windows event loops
            signal.signal(sig, lambda *_: loop.call_soon_threadsafe(stop_event.set))

    await server.start()
    print(f"pose daemon listening on {args.socket_path} using source={args.source}")

    try:
        await stop_event.wait()
    finally:
        await server.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()

