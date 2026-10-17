"""Fields of the tracker data report (command 0x28) that map building needs: tracker id, button and battery.

Layout read off the 2026-10-17 dongle capture of VIVE Hub building a map (docs/mapbuild.md section 3):
* bytes 4..8 (five bytes) are the tracker id, the same id the ASCII command frame (`ascii_command`) is addressed to;
* byte 13 carries battery and button: bit 7 clear -> battery percent is the low 7 bits times 2; bit 7 set -> bit 0 is
  the system button (0x81 was seen on all four presses, matching the Hub log).
Only the offsets above are captured; the sizes of the other fields are not claimed.
"""

from __future__ import annotations

from dataclasses import dataclass

CMD_TRACKER_DATA = 0x28
ID_OFFSET = 4
ID_SIZE = 5
STATE_OFFSET = 13


@dataclass(frozen=True)
class TrackerReport:
    tracker_id: bytes
    battery_percent: int | None
    button_pressed: bool | None


def parse_tracker_report(report: bytes) -> TrackerReport:
    if len(report) <= STATE_OFFSET:
        raise ValueError("tracker report too short")
    if report[0] != CMD_TRACKER_DATA:
        raise ValueError(f"not a tracker data report: first byte 0x{report[0]:02x}")
    tracker_id = bytes(report[ID_OFFSET : ID_OFFSET + ID_SIZE])
    state = report[STATE_OFFSET]
    if state & 0x80:
        return TrackerReport(tracker_id, None, bool(state & 0x01))
    return TrackerReport(tracker_id, min(100, (state & 0x7F) * 2), None)


def find_pressed_tracker(reports) -> bytes | None:
    """The id of the first tracker whose report shows a button press; None if no report does."""
    for report in reports:
        try:
            parsed = parse_tracker_report(report)
        except ValueError:
            continue
        if parsed.button_pressed:
            return parsed.tracker_id
    return None
