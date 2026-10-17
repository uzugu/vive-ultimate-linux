"""ASCII command to a tracker through the dongle (HID feature report, 64 bytes).

Layout read from a USB capture of HTC's software building a map (2026-10-17, docs/mapbuild.md section 3):

    18 | L | 03 | 23 | tracker id (5 bytes) | 00 | 01 | n | text (n bytes) | zeros to 64      with L = 12 + n

Each message is one HID SET_REPORT on the control endpoint (bmRequestType 0x21, bRequest 0x09, wValue 0x0300, wLength 64).
How the 5-byte tracker id relates to a slot number is not decoded yet; callers must pass it.
"""

from __future__ import annotations

from .packets import PACKET_SIZE

CMD_ASCII = 0x18
TRACKER_ID_SIZE = 5
MAX_TEXT = 15  # the longest command HTC sends is exactly 15 characters; its code refuses more


def ascii_command(tracker_id: bytes, text: str) -> bytes:
    """Wrap an ASCII command for one tracker."""
    if len(tracker_id) != TRACKER_ID_SIZE:
        raise ValueError(f"tracker id must be {TRACKER_ID_SIZE} bytes")
    raw = text.encode("ascii")
    if not raw or len(raw) > MAX_TEXT:
        raise ValueError(f"command must be 1..{MAX_TEXT} ASCII characters")
    n = len(raw)
    return (bytes([CMD_ASCII, 12 + n, 0x03, 0x23]) + tracker_id + bytes([0x00, 0x01, n]) + raw).ljust(PACKET_SIZE, b"\0")
