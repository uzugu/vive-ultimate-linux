from __future__ import annotations

import json
import math

from .models import TrackerPose


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
