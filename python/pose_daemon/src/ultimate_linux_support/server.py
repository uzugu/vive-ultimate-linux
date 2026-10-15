from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Iterable

from .models import TrackerPose
from .models import BatteryStatus, ButtonState
from .protocol import encode_battery_line, encode_buttons_line, encode_pose_line
from .sources import PoseSource

log = logging.getLogger(__name__)

# A client that lets this much data pile up unread is dropped instead of stalling the others.
MAX_CLIENT_BACKLOG_BYTES = 1 << 20

# Battery/button state is sent on change, and repeated this often so late joiners and a restarted driver catch up.
STATUS_REFRESH_S = 1.0


class PoseServer:
    def __init__(self, socket_path: str, source: PoseSource, hz: float = 90.0) -> None:
        self._socket_path = socket_path
        self._source = source
        self._hz = hz
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._broadcast_task: asyncio.Task[None] | None = None
        self._status_cache: dict[tuple[str, str], bytes] = {}
        self._status_last_full = 0.0

    async def start(self) -> None:
        await self._source.start()

        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._socket_path)

        self._server = await asyncio.start_unix_server(self._handle_client, path=self._socket_path)
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())

    async def stop(self) -> None:
        if self._broadcast_task is not None:
            self._broadcast_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._broadcast_task

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

        for writer in list(self._clients):
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

        with contextlib.suppress(FileNotFoundError):
            os.unlink(self._socket_path)

        await self._source.stop()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)
        if self._status_cache:
            writer.write(b"".join(self._status_cache.values()))
        try:
            while True:
                chunk = await reader.read(256)
                if not chunk:
                    break
        except ConnectionError:
            pass
        finally:
            self._clients.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _broadcast_loop(self) -> None:
        interval = 1.0 / self._hz
        while True:
            try:
                poses = await self._source.sample()
                self._broadcast(poses)
                self._broadcast_status(await self._source.sample_status())
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("pose source failed; retrying")
            await asyncio.sleep(interval)

    def _broadcast(self, poses: Iterable[TrackerPose]) -> None:
        if not self._clients:
            return

        payload = b"".join(encode_pose_line(pose) for pose in poses)
        if not payload:
            return

        for writer in list(self._clients):
            try:
                if writer.transport.get_write_buffer_size() > MAX_CLIENT_BACKLOG_BYTES:
                    raise ConnectionError("client is not reading")
                writer.write(payload)
            except Exception:
                self._clients.discard(writer)
                writer.close()

    def _broadcast_status(self, statuses: Iterable[BatteryStatus | ButtonState]) -> None:
        now = time.monotonic()
        refresh = now - self._status_last_full >= STATUS_REFRESH_S
        if refresh:
            self._status_last_full = now

        changed: list[bytes] = []
        for status in statuses:
            if isinstance(status, BatteryStatus):
                key, line = (status.serial, "battery"), encode_battery_line(status)
            else:
                key, line = (status.serial, "buttons"), encode_buttons_line(status)
            if refresh or self._status_cache.get(key) != line:
                changed.append(line)
            self._status_cache[key] = line

        if not changed or not self._clients:
            return
        payload = b"".join(changed)
        for writer in list(self._clients):
            try:
                if writer.transport.get_write_buffer_size() > MAX_CLIENT_BACKLOG_BYTES:
                    raise ConnectionError("client is not reading")
                writer.write(payload)
            except Exception:
                self._clients.discard(writer)
                writer.close()
