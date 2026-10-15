"""Slot status (command 0x1E) and peripheral battery byte, docs/re/pairing-and-status.md sections 4 and 5.1."""

from __future__ import annotations

from dataclasses import dataclass

from .packets import PACKET_SIZE, SLOT_COUNT

CMD_STATUS = 0x1E
# Offset of the first slot record in the reply (HTC: "reply starts at byte 9"). Whether this counts the HID
# report id is not settled; pass `offset` if a capture says otherwise.
RECORD_OFFSET = 9
RECORD_SIZE = 4

STATUS_EMPTY = 3
STATUS_PAIRED = 5
STATUS_TRANSITIONAL = 6
STATUS_RF_CONNECTED = 8


@dataclass(frozen=True)
class SlotState:
    slot: int
    status: int
    timeout_ms: int
    power_saving: bool
    exists_in_db: bool
    pairing: bool
    connecting: bool
    rf_connected: bool
    send_imu_to_usb: bool
    handling_fota: bool

    @property
    def is_empty(self) -> bool:
        return self.status == STATUS_EMPTY and not self.exists_in_db


def build_status_query() -> bytes:
    """`1E 01`, zero padded to 64 bytes."""
    return bytes([CMD_STATUS, 0x01]).ljust(PACKET_SIZE, b"\0")


def parse_slot_status(report: bytes, offset: int = RECORD_OFFSET) -> list[SlotState]:
    """Decode five 4-byte records: status, timeout (u16 LE, ms), flags."""
    if len(report) < offset + SLOT_COUNT * RECORD_SIZE:
        raise ValueError("status report too short")
    if report[0] != CMD_STATUS:
        raise ValueError(f"not a status reply: first byte 0x{report[0]:02x}")
    slots = []
    for i in range(SLOT_COUNT):
        status, lo, hi, flags = report[offset + i * RECORD_SIZE : offset + (i + 1) * RECORD_SIZE]
        slots.append(
            SlotState(
                slot=i,
                status=status,
                timeout_ms=lo | hi << 8,
                power_saving=bool(flags & 0x01),
                exists_in_db=bool(flags & 0x02),
                pairing=bool(flags & 0x04),
                connecting=bool(flags & 0x08),
                rf_connected=bool(flags & 0x10),
                send_imu_to_usb=bool(flags & 0x20),
                handling_fota=bool(flags & 0x40),
            )
        )
    return slots


@dataclass(frozen=True)
class PeripheralBattery:
    percent: int
    charging: bool


def decode_peripheral_battery(p1: int) -> PeripheralBattery | None:
    """`percent = (p1 & 0x3f) * 2`, bit 6 charging; None when bit 7 marks pogo-pin accessory status."""
    if not 0 <= p1 <= 0xFF:
        raise ValueError("p1 must be a byte")
    if p1 & 0x80:
        return None
    return PeripheralBattery(percent=min(100, (p1 & 0x3F) * 2), charging=bool(p1 & 0x40))
