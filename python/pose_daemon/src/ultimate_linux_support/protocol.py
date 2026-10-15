from __future__ import annotations

import json
import math

from .models import BUTTON_ALL, BatteryStatus, ButtonState, HapticPulse, TrackerPose


PROTOCOL_VERSION = 2


def decode_pose_line(line: str) -> TrackerPose:
    parts = line.strip().split(" ")
    if len(parts) not in (16, 18):
        raise ValueError(f"expected 16 or 18 fields, got {len(parts)}")

    tag, version = parts[0], int(parts[1])
    if tag != "POSE":
        raise ValueError(f"unexpected tag: {tag}")
    if version not in (1, 2):
        raise ValueError(f"unsupported protocol version: {version}")
    # Version 1 lines have 16 fields, version 2 lines have 18 (see protocol/pose-v1.md).
    if len(parts) != (16 if version == 1 else 18):
        raise ValueError(f"version {version} line has {len(parts)} fields")

    tracking_code = None
    tracking_label = None
    if version == 2:
        tracking_code = int(parts[16])
        tracking_label = parts[17]

    floats = [float(v) for v in parts[5:15]]
    if not all(math.isfinite(v) for v in floats):
        raise ValueError("non-finite number in pose line")
    timestamp_ns = int(parts[15])
    if timestamp_ns < 0:
        raise ValueError("negative timestamp")

    return TrackerPose(
        tracker_index=int(parts[2]),
        serial=parts[3],
        status=parts[4],
        tracking_code=tracking_code,
        tracking_label=tracking_label,
        position_m=(floats[0], floats[1], floats[2]),
        orientation_xyzw=(floats[3], floats[4], floats[5], floats[6]),
        linear_accel_m_s2=(floats[7], floats[8], floats[9]),
        timestamp_ns=timestamp_ns,
    )


def pose_to_json_dict(pose: TrackerPose) -> dict[str, object]:
    return {
        "tracker_index": pose.tracker_index,
        "serial": pose.serial,
        "status": pose.status,
        "tracking_code": pose.tracking_code,
        "tracking_label": pose.tracking_label,
        "position_m": list(pose.position_m),
        "orientation_xyzw": list(pose.orientation_xyzw),
        "linear_accel_m_s2": list(pose.linear_accel_m_s2),
        "timestamp_ns": pose.timestamp_ns,
    }


def pose_to_json_line(pose: TrackerPose) -> str:
    return json.dumps(pose_to_json_dict(pose), separators=(",", ":"))


def encode_pose_line(pose: TrackerPose) -> bytes:
    parts = [
        "POSE",
        str(PROTOCOL_VERSION),
        str(pose.tracker_index),
        pose.serial,
        pose.status,
        f"{pose.position_m[0]:.6f}",
        f"{pose.position_m[1]:.6f}",
        f"{pose.position_m[2]:.6f}",
        f"{pose.orientation_xyzw[0]:.6f}",
        f"{pose.orientation_xyzw[1]:.6f}",
        f"{pose.orientation_xyzw[2]:.6f}",
        f"{pose.orientation_xyzw[3]:.6f}",
        f"{pose.linear_accel_m_s2[0]:.6f}",
        f"{pose.linear_accel_m_s2[1]:.6f}",
        f"{pose.linear_accel_m_s2[2]:.6f}",
        str(pose.timestamp_ns),
        str(-999 if pose.tracking_code is None else pose.tracking_code),
        "unknown" if pose.tracking_label is None else pose.tracking_label,
    ]
    return (" ".join(parts) + "\n").encode("utf-8")


def encode_battery_line(status: BatteryStatus) -> bytes:
    return f"BATTERY 1 {status.serial} {status.percent} {int(status.charging)}\n".encode("utf-8")


def encode_buttons_line(state: ButtonState) -> bytes:
    return f"BUTTONS 1 {state.serial} {state.mask}\n".encode("utf-8")


def decode_battery_line(line: str) -> BatteryStatus:
    parts = line.strip().split(" ")
    if len(parts) != 5 or parts[0] != "BATTERY" or parts[1] != "1":
        raise ValueError("malformed BATTERY line")
    percent, charging = int(parts[3]), int(parts[4])
    if not 0 <= percent <= 100 or charging not in (0, 1):
        raise ValueError("BATTERY value out of range")
    return BatteryStatus(serial=parts[2], percent=percent, charging=bool(charging))


def decode_buttons_line(line: str) -> ButtonState:
    parts = line.strip().split(" ")
    if len(parts) != 4 or parts[0] != "BUTTONS" or parts[1] != "1":
        raise ValueError("malformed BUTTONS line")
    mask = int(parts[3])
    if not 0 <= mask <= BUTTON_ALL:
        raise ValueError("BUTTONS mask out of range")
    return ButtonState(serial=parts[2], mask=mask)


def decode_message(line: str) -> TrackerPose | BatteryStatus | ButtonState:
    """Decode any line the daemon sends. Raises ValueError for unknown or malformed lines."""
    tag = line.lstrip().split(" ", 1)[0]
    if tag == "POSE":
        return decode_pose_line(line)
    if tag == "BATTERY":
        return decode_battery_line(line)
    if tag == "BUTTONS":
        return decode_buttons_line(line)
    raise ValueError(f"unknown message tag: {tag!r}")


def battery_from_peripheral_byte(p1: int) -> tuple[int, bool] | None:
    """Decode HTC's second peripheral byte (docs/re/pairing-and-status.md 5.1).

    Returns (percent, charging), or None when bit 7 marks pogo-pin accessory status instead.
    """
    if p1 & 0x80:
        return None
    return min(100, (p1 & 0x3F) * 2), bool(p1 & 0x40)


MAX_HAPTIC_DURATION_S = 10.0
MAX_HAPTIC_FREQUENCY_HZ = 1000.0


def encode_haptic_line(pulse: HapticPulse) -> bytes:
    return (
        f"HAPTIC 1 {pulse.serial} {pulse.duration_s:.4f} {pulse.frequency_hz:.2f} {pulse.amplitude:.4f}\n"
    ).encode("utf-8")


def decode_haptic_line(line: str) -> HapticPulse:
    parts = line.strip().split(" ")
    if len(parts) != 6 or parts[0] != "HAPTIC" or parts[1] != "1":
        raise ValueError("malformed HAPTIC line")
    duration, frequency, amplitude = float(parts[3]), float(parts[4]), float(parts[5])
    if not all(math.isfinite(v) for v in (duration, frequency, amplitude)):
        raise ValueError("non-finite HAPTIC value")
    if not (0.0 <= duration <= MAX_HAPTIC_DURATION_S and 0.0 <= frequency <= MAX_HAPTIC_FREQUENCY_HZ
            and 0.0 <= amplitude <= 1.0):
        raise ValueError("HAPTIC value out of range")
    return HapticPulse(serial=parts[2], duration_s=duration, frequency_hz=frequency, amplitude=amplitude)
