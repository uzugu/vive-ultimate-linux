"""Dongle pairing and status packets, built from docs/re/pairing-and-status.md.

Pure functions, no I/O: nothing here talks to hardware. Every layout is read from HTC's code and still needs a
capture to confirm; see the "Open questions" in that document before trusting a byte.
"""

from .ascii import CMD_ASCII, MAX_TEXT, TRACKER_ID_SIZE, ascii_command
from .tracker_report import TrackerReport, find_pressed_tracker, parse_tracker_report
from .hidio import PRODUCT_ID, VENDOR_ID, DongleUnavailable, feature_writer, open_dongle
from .packets import (
    BEHAVIOR_CLEAR_PAIRING,
    BEHAVIOR_FACTORY_RESET,
    BEHAVIOR_PAIR,
    BEHAVIOR_RESTART_RF,
    BEHAVIOR_RX_POWER_SAVING,
    PACKET_SIZE,
    SLOT_COUNT,
    build_rf_behavior,
    cancel_pairing,
    pair_empty_slots,
    pair_slot,
    unpair_slot,
    with_report_id,
)
from .status import (
    STATUS_EMPTY,
    STATUS_PAIRED,
    STATUS_RF_CONNECTED,
    STATUS_TRANSITIONAL,
    PeripheralBattery,
    SlotState,
    build_status_query,
    decode_peripheral_battery,
    parse_slot_status,
)

__all__ = [
    "TrackerReport",
    "find_pressed_tracker",
    "parse_tracker_report",
    "PRODUCT_ID",
    "VENDOR_ID",
    "DongleUnavailable",
    "feature_writer",
    "open_dongle",
    "CMD_ASCII",
    "MAX_TEXT",
    "TRACKER_ID_SIZE",
    "ascii_command",
    "BEHAVIOR_CLEAR_PAIRING",
    "BEHAVIOR_FACTORY_RESET",
    "BEHAVIOR_PAIR",
    "BEHAVIOR_RESTART_RF",
    "BEHAVIOR_RX_POWER_SAVING",
    "PACKET_SIZE",
    "SLOT_COUNT",
    "STATUS_EMPTY",
    "STATUS_PAIRED",
    "STATUS_RF_CONNECTED",
    "STATUS_TRANSITIONAL",
    "PeripheralBattery",
    "SlotState",
    "build_rf_behavior",
    "build_status_query",
    "cancel_pairing",
    "decode_peripheral_battery",
    "pair_empty_slots",
    "pair_slot",
    "parse_slot_status",
    "unpair_slot",
    "with_report_id",
]
