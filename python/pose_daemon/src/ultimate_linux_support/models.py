from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TrackerPose:
    tracker_index: int
    serial: str
    status: str
    tracking_code: int | None
    tracking_label: str | None
    position_m: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]
    linear_accel_m_s2: tuple[float, float, float]
    timestamp_ns: int


@dataclass(slots=True)
class PoseBatch:
    poses: list[TrackerPose]
