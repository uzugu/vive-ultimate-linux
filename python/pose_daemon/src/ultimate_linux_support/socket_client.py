from __future__ import annotations

import socket
from collections.abc import Iterator

from .endpoint import parse_endpoint
from .models import BatteryStatus, ButtonState, TrackerPose
from .protocol import decode_message


class PoseStreamClient:
    def __init__(self, socket_path: str) -> None:
        self._endpoint = parse_endpoint(socket_path)
        self._sock: socket.socket | None = None
        self._reader = None

    def __enter__(self) -> "PoseStreamClient":
        if self._endpoint.kind == "unix":
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.connect(self._endpoint.path)
        else:
            self._sock = socket.create_connection((self._endpoint.host, self._endpoint.port))
        self._reader = self._sock.makefile("r", encoding="utf-8", newline="\n")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def iter_messages(self) -> Iterator[TrackerPose | BatteryStatus | ButtonState]:
        if self._reader is None:
            raise RuntimeError("PoseStreamClient must be used as a context manager")

        for line in self._reader:
            stripped = line.strip()
            if not stripped:
                continue
            yield decode_message(stripped)

    def iter_poses(self) -> Iterator[TrackerPose]:
        """Poses only; battery and button messages are skipped."""
        for message in self.iter_messages():
            if isinstance(message, TrackerPose):
                yield message

