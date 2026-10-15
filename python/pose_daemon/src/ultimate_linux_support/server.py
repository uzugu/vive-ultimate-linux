from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from collections.abc import Iterable

from .models import TrackerPose
from .endpoint import parse_endpoint
from .models import BatteryStatus, ButtonState
from .protocol import decode_haptic_line, encode_battery_line, encode_buttons_line, encode_pose_line
from .sources import PoseSource

log = logging.getLogger(__name__)

# A client that lets this much data pile up unread is dropped instead of stalling the others.
MAX_CLIENT_BACKLOG_BYTES = 1 << 20

# Battery/button state is sent on change, and repeated this often so late joiners and a restarted driver catch up.
STATUS_REFRESH_S = 1.0

# Clients (the driver) only send short HAPTIC lines.
MAX_CLIENT_LINE_BYTES = 4096


class PoseServer:
    def __init__(self, socket_path: str, source: PoseSource, hz: float = 90.0) -> None:
        self._endpoint = parse_endpoint(socket_path)
        self._source = source
        self._hz = hz
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._broadcast_task: asyncio.Task[None] | None = None
        self._status_cache: dict[tuple[str, str], bytes] = {}
        self._status_last_full = 0.0

    async def start(self) -> None:
        await self._source.start()

        if self._endpoint.kind == "unix":
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self._endpoint.path)
            self._server = await asyncio.start_unix_server(self._handle_client, path=self._endpoint.path)
        else:
            self._server = await asyncio.start_server(
                self._handle_client, host=self._endpoint.host, port=self._endpoint.port
            )
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

        if self._endpoint.kind == "unix":
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self._endpoint.path)

        await self._source.stop()

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.add(writer)
        if self._status_cache:
            writer.write(b"".join(self._status_cache.values()))
        try:
            buffer = b""
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > MAX_CLIENT_LINE_BYTES and b"\n" not in buffer:
                    log.warning("client sent an over-long line; disconnecting")
                    break
                *lines, buffer = buffer.split(b"\n")
                for raw in lines:
                    await self._handle_client_line(raw)
        except ConnectionError:
            pass
        finally:
            self._clients.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _handle_client_line(self, raw: bytes) -> None:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("HAPTIC "):
            return  # unknown client messages are ignored, like unknown daemon messages on the driver side
        try:
            pulse = decode_haptic_line(line)
        except ValueError as exc:
            log.warning("ignoring bad client line %r: %s", line[:80], exc)
            return
        try:
            await self._source.haptic(pulse)
        except Exception:
            log.exception("haptic request failed")

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
