from __future__ import annotations

import struct
from dataclasses import dataclass

POSE_RECORD_SIZE = 85
ACCESSORY_RECORD_SIZE = 20
_ENUM_ENTRY = struct.Struct("<32sii")  # serial, steamvr_index, display_index


@dataclass(frozen=True)
class PoseRecord:
    """One 85-byte pose record. `floats` keeps all 13 floats; order after position is unconfirmed."""

    vhandle: int
    device_flag: int
    pose_status: int
    floats: tuple[float, ...]
    tracking_state: int
    pose_time_offset: float
    word80: int
    extra: int

    @property
    def position(self) -> tuple[float, float, float]:
        return self.floats[0], self.floats[1], self.floats[2]

    @property
    def rotation_raw(self) -> tuple[float, float, float, float]:
        """Quaternion in the unconfirmed on-wire order."""
        return self.floats[3], self.floats[4], self.floats[5], self.floats[6]


@dataclass(frozen=True)
class AccessoryRecord:
    vhandle: int
    timestamp: float
    data: int


@dataclass(frozen=True)
class TrackerEntry:
    serial: str
    steamvr_index: int
    display_index: int


def parse_pose_records(payload: bytes) -> list[PoseRecord]:
    if len(payload) % POSE_RECORD_SIZE:
        raise ValueError(f"pose payload {len(payload)} is not a multiple of {POSE_RECORD_SIZE}")
    records = []
    for off in range(0, len(payload), POSE_RECORD_SIZE):
        rec = payload[off : off + POSE_RECORD_SIZE]
        (vhandle,) = struct.unpack_from("<Q", rec, 0)
        device_flag = rec[10]
        pose_status = rec[13]
        floats = struct.unpack_from("<13f", rec, 14)
        tracking_state = rec[68]
        (offset_s,) = struct.unpack_from("<d", rec, 72)
        (word80,) = struct.unpack_from("<I", rec, 80)
        records.append(PoseRecord(vhandle, device_flag, pose_status, floats, tracking_state, offset_s, word80, rec[84]))
    return records


def parse_accessory_records(payload: bytes) -> list[AccessoryRecord]:
    if len(payload) % ACCESSORY_RECORD_SIZE:
        raise ValueError(f"accessory payload {len(payload)} is not a multiple of {ACCESSORY_RECORD_SIZE}")
    out = []
    for off in range(0, len(payload), ACCESSORY_RECORD_SIZE):
        vhandle, ts, data = struct.unpack_from("<QdI", payload, off)
        out.append(AccessoryRecord(vhandle, ts, data))
    return out


def parse_enumerate_response(payload: bytes) -> tuple[list[TrackerEntry], int]:
    """Returns (entries, status). Payload: i32 count, count * 40-byte entries, i32 status."""
    (count,) = struct.unpack_from("<i", payload, 0)
    need = 4 + count * _ENUM_ENTRY.size + 4
    if count < 0 or len(payload) < need:
        raise ValueError(f"enumerate payload {len(payload)} too short for {count} entries")
    entries = []
    for i in range(count):
        raw, steamvr_index, display_index = _ENUM_ENTRY.unpack_from(payload, 4 + i * _ENUM_ENTRY.size)
        entries.append(TrackerEntry(raw.split(b"\0", 1)[0].decode("ascii", "replace"), steamvr_index, display_index))
    (status,) = struct.unpack_from("<i", payload, 4 + count * _ENUM_ENTRY.size)
    return entries, status
