import struct
import unittest

from vut_dongle import (
    ascii_command,
    BEHAVIOR_CLEAR_PAIRING,
    PACKET_SIZE,
    build_rf_behavior,
    build_status_query,
    cancel_pairing,
    decode_peripheral_battery,
    pair_empty_slots,
    pair_slot,
    parse_slot_status,
    unpair_slot,
    with_report_id,
)


def status_reply(words):
    """Build a reply from pyvut-style little-endian words: status | timeout << 8 | flags << 24."""
    body = b"".join(struct.pack("<I", w) for w in words)
    return (bytes([0x1E]) + bytes(8) + body).ljust(PACKET_SIZE, b"\0")


class PacketTests(unittest.TestCase):
    def test_layout(self) -> None:
        pkt = build_rf_behavior(0, 1, [1, 0, 1, 0, 0])
        self.assertEqual(len(pkt), 64)
        self.assertEqual(pkt[:9], bytes([0x1D, 9, 0, 1, 1, 0, 1, 0, 0]))
        self.assertEqual(pkt[9:], bytes(55))

    def test_single_slot_forms(self) -> None:
        self.assertEqual(pair_slot(2)[2:9], bytes([0, 1, 0, 0, 1, 0, 0]))
        unpair = unpair_slot(3)
        self.assertEqual(unpair[2], BEHAVIOR_CLEAR_PAIRING)
        self.assertEqual(unpair[4:9], bytes([0, 0, 0, 1, 0]))
        with self.assertRaises(ValueError):
            pair_slot(5)

    def test_empty_slot_masks(self) -> None:
        exists = [True, True, False, False, True]
        self.assertEqual(pair_empty_slots(exists)[2:9], bytes([0, 1, 0, 0, 1, 1, 0]))
        cancel = cancel_pairing(exists)
        self.assertEqual(cancel[2], 2)  # restart RF, not 3
        self.assertEqual(cancel[4:9], bytes([0, 0, 1, 1, 0]))

    def test_validation(self) -> None:
        with self.assertRaises(ValueError):
            build_rf_behavior(0, 2, [0] * 5)
        with self.assertRaises(ValueError):
            build_rf_behavior(0, 1, [0] * 4)
        with self.assertRaises(ValueError):
            pair_empty_slots([True] * 4)

    def test_report_id_and_query(self) -> None:
        self.assertEqual(with_report_id(build_status_query())[:3], bytes([0, 0x1E, 1]))


class StatusTests(unittest.TestCase):
    def test_pyvut_observed_words(self) -> None:
        slots = parse_slot_status(status_reply([0x320FC008, 0x4000003, 0x1000003, 0x320FC008, 0x4000003]))
        paired = slots[0]
        self.assertEqual((paired.status, paired.timeout_ms), (8, 4032))
        self.assertTrue(paired.exists_in_db and paired.rf_connected and paired.send_imu_to_usb)
        self.assertFalse(paired.pairing or paired.is_empty)
        self.assertTrue(slots[1].is_empty and slots[1].pairing)
        self.assertTrue(slots[2].is_empty and slots[2].power_saving)

    def test_rejects_bad_reports(self) -> None:
        with self.assertRaises(ValueError):
            parse_slot_status(b"\x1e" + bytes(10))
        with self.assertRaises(ValueError):
            parse_slot_status(bytes([0x1D]) + bytes(63))

    def test_battery_byte(self) -> None:
        self.assertEqual(decode_peripheral_battery(43).percent, 86)
        charging = decode_peripheral_battery(0x40 | 29)
        self.assertEqual((charging.percent, charging.charging), (58, True))
        self.assertEqual(decode_peripheral_battery(0x3F).percent, 100)
        self.assertIsNone(decode_peripheral_battery(0x80))
        with self.assertRaises(ValueError):
            decode_peripheral_battery(256)


class AsciiCommandTests(unittest.TestCase):
    """Expected bytes are the masked hex seen in a USB capture of HTC's software (tracker id replaced by 5 x 0xaa)."""

    TID = bytes([0xAA] * 5)

    def test_frames_match_capture(self) -> None:
        cases = {
            "ALE": "18 0f 03 23 aa aa aa aa aa 00 01 03 41 4c 45",
            "FW2": "18 0f 03 23 aa aa aa aa aa 00 01 03 46 57 32",
            "ATM20": "18 11 03 23 aa aa aa aa aa 00 01 05 41 54 4d 32 30",
            "pMS_SC": "18 12 03 23 aa aa aa aa aa 00 01 06 70 4d 53 5f 53 43",
            "pMS_ES": "18 12 03 23 aa aa aa aa aa 00 01 06 70 4d 53 5f 45 53",
            "AHT1,1,1,1": "18 16 03 23 aa aa aa aa aa 00 01 0a 41 48 54 31 2c 31 2c 31 2c 31",
        }
        for text, hexed in cases.items():
            want = bytes.fromhex(hexed)
            got = ascii_command(self.TID, text)
            self.assertEqual(got[: len(want)], want, text)
            self.assertEqual(len(got), 64)
            self.assertEqual(got[len(want) :], bytes(64 - len(want)))

    def test_limits(self) -> None:
        self.assertEqual(len(ascii_command(self.TID, "x" * 15)), 64)
        for bad_text in ("", "x" * 16, "é"):
            with self.assertRaises(ValueError):
                ascii_command(self.TID, bad_text)
        with self.assertRaises(ValueError):
            ascii_command(b"\0\0\0", "ALE")


if __name__ == "__main__":
    unittest.main()
