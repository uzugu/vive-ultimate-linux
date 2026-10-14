from __future__ import annotations

import enum
import struct
from dataclasses import dataclass

HEADER_SIZE = 20
MAGIC_CLIENT = 0x22222222  # driver -> server requests
MAGIC_SERVER = 0x11111111  # server -> client responses and pushes

_HEADER = struct.Struct("<5I")


class Cmd(enum.IntEnum):
    """Command ids. Names follow the driver and server log strings."""

    POSE_DATA = 3
    NOTIFY_PAIR_INFO = 4
    PERIPHERAL_DATA = 5
    ERROR_NOTIFICATION = 7
    STATUS_INDICATOR = 8
    ACCESSORY_DATA = 10
    NOTIFY_HMD_TYPE = 0x13
    IS_BODY_TRACKING_SUPPORT = 0x14
    CREATE_TRACKER = 0x15
    DESTROY_TRACKER = 0x16
    ENUMERATE_TRACKERS = 0x17
    IDENTIFY_TRACKER = 0x18
    POWER_OFF_TRACKER = 0x19
    NOTIFY_START_SPACE_CALIBRATION = 0x1E
    SUBMIT_SPACE_CALIBRATION = 0x1F
    GET_SPACE_CALIBRATION_TIME = 0x20
    START_MAP_CREATION = 0x21
    END_MAP_CREATION = 0x22
    GET_LAST_MAP_CREATION_TIME = 0x23
    QUERY_MAP_AND_CALIBRATION_STATUS = 0x28
    SET_STEAMVR_TRACKER_INDEX = 0x25
    NOTIFY_CHAPERONE_UNIVERSE_CHANGED = 0x29
    GET_DEVICE_ID = 0x2A
    CREATE_BODY_TRACKER = 0x2D
    NOTIFY_STEAMVR_APP_EVENT = 0x31
    GET_BODY_SKELETON = 0x33
    SET_ACCESSORY_DATA = 0x35
    REBOOT_TRACKER = 0x36
    RELOCATE_TRACKER = 0x37


@dataclass(frozen=True)
class Header:
    magic: int
    cmd: int
    pid: int
    stamp: int
    length: int


@dataclass(frozen=True)
class Packet:
    header: Header
    payload: bytes


def pack_packet(magic: int, cmd: int, payload: bytes = b"", *, pid: int = 0, stamp: int = 0) -> bytes:
    return _HEADER.pack(magic, int(cmd), pid, stamp, len(payload)) + payload


def unpack_packet(data: bytes) -> Packet:
    """Parse one message (one pipe read). Raises ValueError on a short or inconsistent message."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"short message: {len(data)} bytes")
    header = Header(*_HEADER.unpack_from(data))
    payload = data[HEADER_SIZE:]
    # Requests are written from a fixed-size buffer, so trailing bytes beyond `length` are allowed.
    if len(payload) < header.length:
        raise ValueError(f"payload {len(payload)} bytes shorter than declared {header.length}")
    return Packet(header, payload[: header.length])
