"""Room service: the API the SteamVR overlay talks to (docs/overlay-room-switching.md).

The tracker map transfer sits behind `Transport`. Export works over USB today, import and any wireless route are
unproven, so the service and the overlay are built against `FakeTransport` and a real transport plugs in later.
"""

from __future__ import annotations

import json
import os
import shutil
import socketserver
import tempfile
import threading
from pathlib import Path
from typing import Any, Protocol

from .store import MAP_FILE_SUFFIXES, RoomError, RoomStore


class TransportError(RoomError):
    pass


class Transport(Protocol):
    def export_map(self, dest: Path) -> list[Path]:
        """Copy the tracker's current map (the three *.db files) into `dest` and return the files."""

    def import_map(self, files: list[Path]) -> None:
        """Replace the tracker's map with these files."""


class FakeTransport:
    """A stand-in tracker: its 'map' is a folder of .db files. For tests and for developing the overlay."""

    def __init__(self, tracker_dir: Path | str) -> None:
        self.dir = Path(tracker_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def export_map(self, dest: Path) -> list[Path]:
        files = sorted(p for p in self.dir.iterdir() if p.suffix in MAP_FILE_SUFFIXES)
        if not files:
            raise TransportError("the tracker has no map to export")
        dest.mkdir(parents=True, exist_ok=True)
        return [Path(shutil.copy2(p, dest / p.name)) for p in files]

    def import_map(self, files: list[Path]) -> None:
        for old in self.dir.glob("*.db"):
            old.unlink()
        for src in files:
            shutil.copy2(src, self.dir / src.name)


class RoomService:
    def __init__(self, store: RoomStore, transport: Transport, calibration_file: Path | str | None = None) -> None:
        self.store = store
        self.transport = transport
        self.calibration_file = calibration_file
        self._lock = threading.Lock()  # one transfer at a time

    def _summary(self, room: Any) -> dict[str, Any]:
        return {
            "name": room.name,
            "slug": room.slug,
            "has_map": bool(room.map_files),
            "active": room.slug == self.store.active_slug(),
        }

    def list_rooms(self) -> list[dict[str, Any]]:
        return [self._summary(r) for r in self.store.list()]

    def save_current(self, name: str) -> dict[str, Any]:
        """Export the tracker's map into the room (created if new)."""
        with self._lock:
            try:
                room = self.store.get(name)
            except RoomError:
                room = self.store.create(name)
            with tempfile.TemporaryDirectory() as tmp:
                files = self.transport.export_map(Path(tmp))
                room = self.store.attach_map_files(room.slug, files)
            return self._summary(room)

    def load(self, name: str) -> dict[str, Any]:
        """Push the room's map to the tracker, then switch calibration. Calibration only changes if the import worked."""
        with self._lock:
            room = self.store.get(name)
            if not room.map_files:
                raise RoomError(f"room {room.slug!r} has no saved map")
            maps_dir = self.store.root / room.slug / "maps"
            self.transport.import_map([maps_dir / n for n in room.map_files])
            room = self.store.use(room.slug, self.calibration_file)
            return self._summary(room)

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            op = request.get("op")
            if op == "list":
                return {"ok": True, "rooms": self.list_rooms()}
            if op == "save":
                return {"ok": True, "room": self.save_current(str(request["name"]))}
            if op == "load":
                return {"ok": True, "room": self.load(str(request["name"]))}
            return {"ok": False, "error": f"unknown op {op!r}"}
        except (RoomError, KeyError, OSError) as exc:
            return {"ok": False, "error": str(exc)}


def serve(service: RoomService, socket_path: Path | str) -> socketserver.UnixStreamServer:
    """One JSON object per line in, one per line out, on a Unix socket (mode 0600). Caller runs serve_forever()."""

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for line in self.rfile:
                try:
                    reply = service.handle(json.loads(line))
                except ValueError:
                    reply = {"ok": False, "error": "bad json"}
                self.wfile.write((json.dumps(reply) + "\n").encode())

    path = Path(socket_path)
    path.unlink(missing_ok=True)
    server = socketserver.ThreadingUnixStreamServer(str(path), Handler)
    os.chmod(path, 0o600)
    return server
