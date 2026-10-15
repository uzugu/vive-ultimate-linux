from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

from .endpoint import parse_endpoint
from .models import BatteryStatus, ButtonState, DeviceInfo, Event, Hello, TrackerPose
from .protocol import decode_message


class PoseStreamClient:
    def __init__(self, socket_path: str) -> None:
        self._endpoint = parse_endpoint(socket_path)
        self._sock: socket.socket | None = None
        self._closed = threading.Event()
        self._close_lock = threading.Lock()

    def __enter__(self) -> "PoseStreamClient":
        try:
            if self._endpoint.kind == "unix":
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._sock.settimeout(1)
                self._sock.connect(self._endpoint.path)
            else:
                self._sock = socket.create_connection((self._endpoint.host, self._endpoint.port), timeout=1)
            self._sock.settimeout(0.25)
        except OSError:
            self.__exit__(None, None, None)
            raise
        self._closed.clear()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._closed.set()
        with self._close_lock:
            sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()

    def iter_messages(self) -> Iterator[TrackerPose | BatteryStatus | ButtonState | Hello | DeviceInfo | Event]:
        sock = self._sock
        if sock is None:
            raise RuntimeError("PoseStreamClient must be used as a context manager")
        # Poll the socket so cancellation also works on Windows when shutdown
        # races a blocking read. A makefile reader's close can wait on that read.
        pending = b""
        while not self._closed.is_set():
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                if self._closed.is_set():
                    return
                raise
            if not chunk:
                if pending.strip():
                    yield decode_message(pending.decode("utf-8").strip())
                return
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                stripped = line.decode("utf-8").strip()
                if stripped:
                    yield decode_message(stripped)
                if self._closed.is_set():
                    return
            if len(pending) > 65536:
                raise ValueError("daemon message exceeds 65536 bytes")

    def iter_poses(self) -> Iterator[TrackerPose]:
        """Poses only; every other message type is skipped."""
        for message in self.iter_messages():
            if isinstance(message, TrackerPose):
                yield message

