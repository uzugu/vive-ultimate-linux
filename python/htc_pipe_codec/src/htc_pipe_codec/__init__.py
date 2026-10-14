"""Codec for the HTC ViveTrackerServer named-pipe framing (see docs/re/driver-pipes.md).

Layouts marked "guess" in that document are exposed as raw fields so they can be settled
from captures without changing callers.
"""

from .framing import (
    HEADER_SIZE,
    MAGIC_CLIENT,
    MAGIC_SERVER,
    Cmd,
    Header,
    Packet,
    pack_packet,
    unpack_packet,
)
from .records import (
    ACCESSORY_RECORD_SIZE,
    POSE_RECORD_SIZE,
    AccessoryRecord,
    PoseRecord,
    TrackerEntry,
    parse_accessory_records,
    parse_enumerate_response,
    parse_pose_records,
)

__all__ = [
    "ACCESSORY_RECORD_SIZE",
    "HEADER_SIZE",
    "MAGIC_CLIENT",
    "MAGIC_SERVER",
    "POSE_RECORD_SIZE",
    "AccessoryRecord",
    "Cmd",
    "Header",
    "Packet",
    "PoseRecord",
    "TrackerEntry",
    "pack_packet",
    "parse_accessory_records",
    "parse_enumerate_response",
    "parse_pose_records",
    "unpack_packet",
]
