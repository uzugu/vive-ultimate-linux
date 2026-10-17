"""A `Link` that sends commands through the dongle. No I/O of its own: the caller supplies the HID write.

`send_feature` must perform one HID SET_REPORT feature write of the 64 bytes it is given (on Linux hidapi's
`send_feature_report` with a leading report id 0, see `vut_dongle.with_report_id`). `tracker_ids` maps a slot number to the
tracker's 5-byte id; where that id comes from is still open (docs/mapbuild.md section 3).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from vut_dongle import ascii_command


class DongleLink:
    def __init__(self, send_feature: Callable[[bytes], None], tracker_ids: Mapping[int, bytes]) -> None:
        self._write = send_feature
        self._ids = dict(tracker_ids)

    def send(self, slot: int, command: str) -> None:
        try:
            tracker_id = self._ids[slot]
        except KeyError:
            raise KeyError(f"no tracker id known for slot {slot}") from None
        self._write(ascii_command(tracker_id, command))
