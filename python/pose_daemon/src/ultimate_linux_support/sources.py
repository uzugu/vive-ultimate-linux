from __future__ import annotations

import abc
import math
import threading
import time
from dataclasses import replace

from .models import TrackerPose


class PoseSource(abc.ABC):
    @abc.abstractmethod
    async def start(self) -> None:
        """Prepare the source."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Release source resources."""

    @abc.abstractmethod
    async def sample(self) -> list[TrackerPose]:
        """Return the latest available poses."""


class MockPoseSource(PoseSource):
    def __init__(self, tracker_count: int = 3) -> None:
        self._tracker_count = tracker_count
        self._start = time.monotonic()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def sample(self) -> list[TrackerPose]:
        now = time.monotonic()
        timestamp_ns = time.monotonic_ns()
        t = now - self._start
        poses: list[TrackerPose] = []

        for tracker_index in range(self._tracker_count):
            phase = t + tracker_index * 0.7
            px = 0.20 * tracker_index + 0.08 * math.cos(phase)
            py = 1.0 + 0.03 * math.sin(phase * 1.3)
            pz = -0.30 + 0.10 * math.sin(phase)
            qx = 0.0
            qy = math.sin(phase * 0.5) * 0.25
            qz = 0.0
            qw = max(0.0, 1.0 - qy * qy) ** 0.5

            poses.append(
                TrackerPose(
                    tracker_index=tracker_index,
                    serial=f"mock-{tracker_index}",
                    status="ok",
                    tracking_code=2,
                    tracking_label="OK",
                    position_m=(px, py, pz),
                    orientation_xyzw=(qx, qy, qz, qw),
                    linear_accel_m_s2=(0.0, 0.0, 0.0),
                    timestamp_ns=timestamp_ns,
                )
            )

        return poses


class PyVutPoseSource(PoseSource):
    def __init__(
        self,
        mode: str = "DONGLE_USB",
        wifi_info_path: str | None = None,
        stale_after_s: float = 0.5,
    ) -> None:
        self._mode = mode
        # Trackers that stop reporting are published as `lost` so SteamVR does not hold a frozen pose.
        self._stale_after_ns = int(stale_after_s * 1e9)
        self._wifi_info_path = wifi_info_path
        self._api = None
        self._lock = threading.Lock()
        self._latest: dict[str, TrackerPose] = {}
        self._last_reported_code: dict[str, int] = {}

    async def start(self) -> None:
        try:
            from pyvut import UltimateTrackerAPI  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "pyvut is not installed in this environment. Install it before using --source pyvut."
            ) from exc

        kwargs = {"mode": self._mode}
        if self._wifi_info_path:
            kwargs["wifi_info_path"] = self._wifi_info_path

        self._api = UltimateTrackerAPI(**kwargs)
        self._api.__enter__()
        self._api.add_pose_callback(self._on_pose)

    async def stop(self) -> None:
        if self._api is not None:
            self._api.__exit__(None, None, None)
            self._api = None

    async def sample(self) -> list[TrackerPose]:
        now_ns = time.monotonic_ns()
        with self._lock:
            latest = list(self._latest.values())
        return [
            replace(p, status="lost", tracking_label="STALE") if now_ns - p.timestamp_ns > self._stale_after_ns else p
            for p in latest
        ]

    def _on_pose(self, pose: object) -> None:
        tracker_index = int(getattr(pose, "tracker_index", 0))
        serial = str(getattr(pose, "mac", f"tracker-{tracker_index}"))
        raw_tracking_status = int(getattr(pose, "tracking_status", -999))
        status, tracking_label = self._normalize_status(raw_tracking_status)
        position = tuple(float(v) for v in getattr(pose, "position", (0.0, 0.0, 0.0)))
        rotation = tuple(float(v) for v in getattr(pose, "rotation", (0.0, 0.0, 0.0, 1.0)))
        accel = tuple(float(v) for v in getattr(pose, "acceleration", (0.0, 0.0, 0.0)))

        tracker_pose = TrackerPose(
            tracker_index=tracker_index,
            serial=serial.replace(" ", "_"),
            status=status,
            tracking_code=raw_tracking_status,
            tracking_label=tracking_label,
            position_m=self._vec3(position),
            orientation_xyzw=self._quat(rotation),
            linear_accel_m_s2=self._vec3(accel),
            timestamp_ns=time.monotonic_ns(),
        )

        with self._lock:
            self._latest[tracker_pose.serial] = replace(tracker_pose)

        previous_code = self._last_reported_code.get(tracker_pose.serial)
        if previous_code != raw_tracking_status:
            self._last_reported_code[tracker_pose.serial] = raw_tracking_status
            print(
                "tracking status update:",
                tracker_pose.serial,
                f"raw={raw_tracking_status}",
                f"label={tracking_label}",
                f"status={status}",
                flush=True,
            )

    @staticmethod
    def _normalize_status(status: int) -> tuple[str, str]:
        mapping = {
            -1: ("searching", "SYSTEM_NOT_READY"),
            0: ("searching", "NO_IMAGES_YET"),
            1: ("searching", "NOT_INITIALIZED"),
            2: ("ok", "OK"),
            3: ("lost", "LOST"),
            4: ("lost", "RECENTLY_LOST"),
        }
        return mapping.get(status, ("searching", f"UNKNOWN_{status}"))

    @staticmethod
    def _vec3(value: tuple[float, ...]) -> tuple[float, float, float]:
        padded = list(value[:3]) + [0.0, 0.0, 0.0]
        return (padded[0], padded[1], padded[2])

    @staticmethod
    def _quat(value: tuple[float, ...]) -> tuple[float, float, float, float]:
        padded = list(value[:4]) + [0.0, 0.0, 0.0, 1.0]
        return (padded[0], padded[1], padded[2], padded[3])
