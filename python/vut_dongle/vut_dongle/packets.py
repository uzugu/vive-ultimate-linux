"""RF behaviour packets (command 0x1D), docs/re/pairing-and-status.md section 3."""

from __future__ import annotations

from collections.abc import Sequence

PACKET_SIZE = 64
SLOT_COUNT = 5
CMD_RF_BEHAVIOR = 0x1D
PAYLOAD_LENGTH = 0x09

BEHAVIOR_PAIR = 0
BEHAVIOR_RX_POWER_SAVING = 1
BEHAVIOR_RESTART_RF = 2
BEHAVIOR_FACTORY_RESET = 5  # bricks dongles in the wild; never sent by the helpers below
BEHAVIOR_CLEAR_PAIRING = 6


def build_rf_behavior(behavior: int, enable: int, slot_flags: Sequence[int]) -> bytes:
    """`1D 09 <behavior> <enable> <flag slot0..4>`, zero padded to 64 bytes."""
    if not 0 <= behavior <= 0xFF or enable not in (0, 1):
        raise ValueError("behavior must be a byte and enable 0 or 1")
    if len(slot_flags) != SLOT_COUNT or any(f not in (0, 1) for f in slot_flags):
        raise ValueError(f"need {SLOT_COUNT} slot flags, each 0 or 1")
    return bytes([CMD_RF_BEHAVIOR, PAYLOAD_LENGTH, behavior, enable, *slot_flags]).ljust(PACKET_SIZE, b"\0")


def _one_hot(slot: int) -> list[int]:
    if not 0 <= slot < SLOT_COUNT:
        raise ValueError(f"slot must be 0..{SLOT_COUNT - 1}")
    return [1 if i == slot else 0 for i in range(SLOT_COUNT)]


def pair_slot(slot: int) -> bytes:
    """Pair one slot (HTC `TriggerDongleMode(slot, 0, false)`): behaviour 0, one-hot mask."""
    return build_rf_behavior(BEHAVIOR_PAIR, 1, _one_hot(slot))


def unpair_slot(slot: int) -> bytes:
    """Remove one slot's pairing (behaviour 6, one-hot mask). Unconfirmed on hardware: test on a spare tracker."""
    return build_rf_behavior(BEHAVIOR_CLEAR_PAIRING, 1, _one_hot(slot))


def pair_empty_slots(exists_in_db: Sequence[bool]) -> bytes:
    """Start pairing on every slot that has no pairing entry (HTC's device index 0xFE).

    `exists_in_db` is the per-slot "exist in DB" flag from a fresh slot status query. Unlike pyvut's fixed
    mask, this stays right with five trackers or after one slot was unpaired.
    """
    if len(exists_in_db) != SLOT_COUNT:
        raise ValueError(f"need {SLOT_COUNT} flags")
    return build_rf_behavior(BEHAVIOR_PAIR, 1, [0 if e else 1 for e in exists_in_db])


def cancel_pairing(exists_in_db: Sequence[bool]) -> bytes:
    """Stop pairing: HTC sends 'mode 3', which goes on the wire as behaviour 2 (restart RF) with the empty-slot mask."""
    if len(exists_in_db) != SLOT_COUNT:
        raise ValueError(f"need {SLOT_COUNT} flags")
    return build_rf_behavior(BEHAVIOR_RESTART_RF, 1, [0 if e else 1 for e in exists_in_db])


def with_report_id(packet: bytes, report_id: int = 0) -> bytes:
    """Prefix the HID report id (HTC writes 64 bytes plus report id 0)."""
    return bytes([report_id]) + packet
