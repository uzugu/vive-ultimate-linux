"""Where the daemon listens and the driver connects (protocol/pose-v1.md, "Endpoints").

An endpoint is a string: ``unix:/path/to/socket`` or ``tcp:127.0.0.1:38450``. A bare path means ``unix:``.
Unix sockets are the default on Linux; Windows has no usable asyncio Unix sockets, so it defaults to loopback TCP.
"""

from __future__ import annotations

import ipaddress
import os
import sys
from dataclasses import dataclass

DEFAULT_TCP_PORT = 38450
DEFAULT_UNIX_PATH = "/tmp/ultimate-tracker-linux.sock"


@dataclass(frozen=True)
class Endpoint:
    kind: str  # "unix" or "tcp"
    path: str = ""
    host: str = ""
    port: int = 0

    def __str__(self) -> str:
        return f"unix:{self.path}" if self.kind == "unix" else f"tcp:{self.host}:{self.port}"


def parse_endpoint(spec: str) -> Endpoint:
    if spec.startswith("tcp:"):
        host, sep, port_text = spec[4:].rpartition(":")
        if not sep or not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
            raise ValueError(f"bad tcp endpoint {spec!r}; expected tcp:127.0.0.1:PORT")
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError(f"tcp endpoint {spec!r} must be a loopback address")
        except ValueError as exc:
            raise ValueError(f"tcp endpoint {spec!r} must be a loopback IP address") from exc
        return Endpoint("tcp", host=host, port=int(port_text))
    path = spec[5:] if spec.startswith("unix:") else spec
    if not path:
        raise ValueError("empty socket path")
    return Endpoint("unix", path=path)


def default_endpoint_spec() -> str:
    env = os.environ.get("ULTIMATE_TRACKER_SOCKET_PATH")
    if env:
        return env
    return f"tcp:127.0.0.1:{DEFAULT_TCP_PORT}" if sys.platform == "win32" else DEFAULT_UNIX_PATH
