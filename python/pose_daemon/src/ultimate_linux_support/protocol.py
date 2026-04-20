from __future__ import annotations

import json

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

    tracking_code = None
    tracking_label = None
    if version == 2:
        tracking_code = int(parts[16])
        tracking_label = parts[17]

    return TrackerPose(
        tracker_index=int(parts[2]),
        serial=parts[3],
        status=parts[4],
        tracking_code=tracking_code,
        tracking_label=tracking_label,
        position_m=(float(parts[5]), float(parts[6]), float(parts[7])),
        orientation_xyzw=(float(parts[8]), float(parts[9]), float(parts[10]), float(parts[11])),
        linear_accel_m_s2=(float(parts[12]), float(parts[13]), float(parts[14])),
        timestamp_ns=int(parts[15]),
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
