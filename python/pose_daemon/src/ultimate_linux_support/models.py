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


# Button bits in ButtonState.mask (HTC order: system button, grip, trigger, trackpad, menu).
BUTTON_POWER = 1
BUTTON_GRIP = 2
BUTTON_TRIGGER = 4
BUTTON_TRACKPAD = 8
BUTTON_MENU = 16
BUTTON_ALL = 31


@dataclass(slots=True)
class BatteryStatus:
    serial: str
    percent: int
    charging: bool


@dataclass(slots=True)
class ButtonState:
    serial: str
    mask: int


@dataclass(slots=True)
class HapticPulse:
    """Driver to daemon: vibrate one tracker (SteamVR's haptic event, unchanged)."""

    serial: str
    duration_s: float
    frequency_hz: float
    amplitude: float
