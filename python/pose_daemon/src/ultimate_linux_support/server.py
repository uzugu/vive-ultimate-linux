from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Iterable

from .models import TrackerPose
from .protocol import encode_pose_line
from .sources import PoseSource


class PoseServer:
    def __init__(self, socket_path: str, source: PoseSource, hz: float = 90.0) -> None:
        self._socket_path = socket_path
        self._source = source
        self._hz = hz
        self._server: asyncio.AbstractServer | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._broadcast_task: asyncio.Task[None] | None = None

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
        try:
            while True:
                chunk = await reader.read(256)
                if not chunk:
                    break
        finally:
            self._clients.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _broadcast_loop(self) -> None:
        interval = 1.0 / self._hz
        while True:
            poses = await self._source.sample()
            await self._broadcast(poses)
            await asyncio.sleep(interval)

    async def _broadcast(self, poses: Iterable[TrackerPose]) -> None:
        if not self._clients:
            return

        payload = b"".join(encode_pose_line(pose) for pose in poses)
        stale_clients: list[asyncio.StreamWriter] = []

        for writer in self._clients:
            try:
                writer.write(payload)
                await writer.drain()
            except Exception:
                stale_clients.append(writer)

        for writer in stale_clients:
            self._clients.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

