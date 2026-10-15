"""Headless model behind `vut gui`: live tracker state fed from the daemon, and the room list.

No Tk imports here so it is unit-testable anywhere; `gui.py` is the thin view on top.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from ultimate_linux_support.models import BatteryStatus, ButtonState, DeviceInfo, Event, Hello, TrackerPose
from ultimate_linux_support.socket_client import PoseStreamClient

BUTTON_NAMES = ((1, "power"), (2, "grip"), (4, "trigger"), (8, "trackpad"), (16, "menu"))


def button_names(mask: int) -> str:
    return ",".join(name for bit, name in BUTTON_NAMES if mask & bit) or "-"


@dataclass
class TrackerView:
    serial: str
    index: int = 0
    status: str = "unknown"
    tracking_label: str = "unknown"
    position_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    battery_percent: int | None = None
    charging: bool = False
    buttons: int = 0
    connected: bool = False
    last_pose_monotonic: float = 0.0


@dataclass
class LiveState:
    """Everything the status tab shows. `apply` is called from the worker thread, readers use `snapshot`."""

    connected: bool = False
    daemon: str = ""
    source: str = ""
    last_event: str = ""
    error: str = ""
    trackers: dict[str, TrackerView] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _tracker(self, serial: str) -> TrackerView:
        return self.trackers.setdefault(serial, TrackerView(serial))

    def apply(self, message: object) -> None:
        with self._lock:
            if isinstance(message, TrackerPose):
                t = self._tracker(message.serial)
                t.index, t.status = message.tracker_index, message.status
                t.tracking_label = message.tracking_label or "unknown"
                t.position_m = message.position_m
                t.last_pose_monotonic = time.monotonic()
            elif isinstance(message, BatteryStatus):
                t = self._tracker(message.serial)
                t.battery_percent, t.charging = message.percent, message.charging
            elif isinstance(message, ButtonState):
                self._tracker(message.serial).buttons = message.mask
            elif isinstance(message, DeviceInfo):
                t = self._tracker(message.serial)
                t.index, t.connected = message.tracker_index, message.connected
            elif isinstance(message, Hello):
                self.daemon, self.source = message.daemon_version, message.source
            elif isinstance(message, Event):
                self.last_event = message.kind + (f" ({message.serial})" if message.serial else "")

    def set_connection(self, connected: bool, error: str = "") -> None:
        with self._lock:
            self.connected, self.error = connected, error
            if not connected:
                for t in self.trackers.values():
                    t.connected = False

    def snapshot(self) -> tuple[bool, str, list[TrackerView]]:
        """(connected, one-line daemon summary, trackers sorted by index)."""
        with self._lock:
            summary = f"daemon {self.daemon} / source {self.source}" if self.daemon else ""
            if self.last_event:
                summary += f"   last event: {self.last_event}"
            trackers = sorted((TrackerView(**vars(t)) for t in self.trackers.values()), key=lambda t: (t.index, t.serial))
            return self.connected, summary or self.error, trackers


class StreamWorker:
    """Background thread: connect, read, reconnect with a short pause until `stop()`."""

    def __init__(self, endpoint: str, state: LiveState, retry_s: float = 1.0) -> None:
        self._endpoint, self._state, self._retry_s = endpoint, state, retry_s
        self._stop = threading.Event()
        self._client: PoseStreamClient | None = None
        self._thread = threading.Thread(target=self._run, name="vut-stream", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        client = self._client
        if client is not None:  # unblocks the reader
            try:
                client.__exit__(None, None, None)
            except Exception:
                pass
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with PoseStreamClient(self._endpoint) as client:
                    self._client = client
                    if self._stop.is_set():
                        break
                    self._state.set_connection(True)
                    for message in client.iter_messages():
                        self._state.apply(message)
                        if self._stop.is_set():
                            break
            except (OSError, ValueError) as exc:
                if not self._stop.is_set():
                    self._state.set_connection(False, f"waiting for daemon at {self._endpoint} ({exc})")
            finally:
                self._client = None
                if self._stop.is_set():
                    self._state.set_connection(False)
            if not self._stop.is_set():
                self._state.set_connection(False, self._state.error or f"waiting for daemon at {self._endpoint}")
                self._stop.wait(self._retry_s)


@dataclass
class RoomRow:
    slug: str
    name: str
    active: bool
    map_files: int


class RoomsModel:
    def __init__(self, store, calibration_file: str | None = None) -> None:
        self._store, self._calibration_file = store, calibration_file

    def rows(self) -> list[RoomRow]:
        active = self._store.active_slug()
        return [RoomRow(r.slug, r.name, r.slug == active, len(r.map_files)) for r in self._store.list()]

    def use(self, slug: str) -> str:
        """Make a room active and rewrite the driver's calibration file. Returns a status line."""
        room = self._store.use(slug, self._calibration_file)
        return f"active room: {room.name}"
