from __future__ import annotations

import socket
from collections.abc import Iterator

from .models import TrackerPose
from .protocol import decode_pose_line


class PoseStreamClient:
    def __init__(self, socket_path: str) -> None:
        self._socket_path = socket_path
        self._sock: socket.socket | None = None
        self._reader = None

    def __enter__(self) -> "PoseStreamClient":
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(self._socket_path)
        self._reader = self._sock.makefile("r", encoding="utf-8", newline="\n")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def iter_poses(self) -> Iterator[TrackerPose]:
        if self._reader is None:
            raise RuntimeError("PoseStreamClient must be used as a context manager")

        for line in self._reader:
            stripped = line.strip()
            if not stripped:
                continue
            yield decode_pose_line(stripped)

