"""Open the dongle through hidapi and write feature reports. The only I/O in this package.

`hid` (the hidapi binding) is imported lazily so the rest of the package and its tests need no hardware or extra install.
"""

from __future__ import annotations

from collections.abc import Callable

from .packets import with_report_id

VENDOR_ID = 0x0BB4
PRODUCT_ID = 0x0350


class DongleUnavailable(RuntimeError):
    pass


def open_dongle(hid_module=None, vendor_id: int = VENDOR_ID, product_id: int = PRODUCT_ID):
    """Return an opened hid device for the dongle, or raise DongleUnavailable with the reason."""
    if hid_module is None:
        try:
            import hid as hid_module  # type: ignore[no-redef]
        except ImportError:
            raise DongleUnavailable("hidapi is not installed (pip install hidapi)") from None
    device = hid_module.device()
    try:
        device.open(vendor_id, product_id)
    except OSError as exc:
        raise DongleUnavailable(f"cannot open dongle {vendor_id:04x}:{product_id:04x}: {exc}") from None
    return device


def feature_writer(device) -> Callable[[bytes], None]:
    """A `send_feature` for DongleLink: one SET_REPORT feature write, report id 0 prepended."""

    def write(packet: bytes) -> None:
        data = with_report_id(packet)
        written = device.send_feature_report(data)
        if written is not None and written < 0:
            raise OSError("feature report write failed")

    return write
