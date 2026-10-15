import json
import unittest
from pathlib import Path

from ultimate_linux_support.models import BUTTON_GRIP, BUTTON_TRIGGER, BatteryStatus, ButtonState, TrackerPose
from ultimate_linux_support.protocol import (
    battery_from_peripheral_byte,
    decode_battery_line,
    decode_buttons_line,
    decode_message,
    decode_pose_line,
    encode_battery_line,
    encode_buttons_line,
    encode_pose_line,
    pose_to_json_line,
)

FIXTURES = Path(__file__).resolve().parents[3] / "protocol" / "fixtures"


def fixture_lines(name: str) -> list[str]:
    return [
        line
        for line in (FIXTURES / name).read_text().splitlines()
        if line and not line.startswith("#")
    ]


class ProtocolTests(unittest.TestCase):
    def test_valid_fixtures_decode(self) -> None:
        lines = fixture_lines("valid.txt")
        self.assertGreaterEqual(len(lines), 4)
        for line in lines:
            decode_pose_line(line)

    def test_invalid_fixtures_rejected(self) -> None:
        for line in fixture_lines("invalid.txt"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                decode_pose_line(line)

    def test_roundtrip(self) -> None:
        pose = TrackerPose(
            tracker_index=2,
            serial="AA:BB",
            status="ok",
            tracking_code=2,
            tracking_label="OK",
            position_m=(0.1, 1.2, -0.3),
            orientation_xyzw=(0.0, 0.5, 0.0, 0.866025),
            linear_accel_m_s2=(0.0, -9.81, 0.0),
            timestamp_ns=123456789,
        )
        line = encode_pose_line(pose)
        self.assertTrue(line.endswith(b"\n"))
        self.assertEqual(decode_pose_line(line.decode()), pose)

    def test_v1_has_no_tracking_info(self) -> None:
        pose = decode_pose_line(fixture_lines("valid.txt")[0])
        self.assertIsNone(pose.tracking_code)
        self.assertIsNone(pose.tracking_label)

    def test_json_line(self) -> None:
        pose = decode_pose_line(fixture_lines("valid.txt")[1])
        data = json.loads(pose_to_json_line(pose))
        self.assertEqual(data["serial"], "mock-0")
        self.assertEqual(data["orientation_xyzw"][1], 0.198669)

    def test_battery_roundtrip_and_validation(self) -> None:
        status = BatteryStatus("AA:BB", 86, True)
        self.assertEqual(decode_battery_line(encode_battery_line(status).decode()), status)
        for bad in ("BATTERY 1 a 101 0", "BATTERY 1 a -1 0", "BATTERY 1 a 50 2", "BATTERY 2 a 50 0", "BATTERY 1 a 50"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                decode_battery_line(bad)

    def test_buttons_roundtrip_and_validation(self) -> None:
        state = ButtonState("AA:BB", BUTTON_GRIP | BUTTON_TRIGGER)
        self.assertEqual(decode_buttons_line(encode_buttons_line(state).decode()), state)
        for bad in ("BUTTONS 1 a 32", "BUTTONS 1 a -1", "BUTTONS 1 a", "BUTTONS 1 a x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                decode_buttons_line(bad)

    def test_decode_message_dispatch(self) -> None:
        self.assertIsInstance(decode_message(fixture_lines("valid.txt")[1]), TrackerPose)
        self.assertIsInstance(decode_message("BATTERY 1 a 50 0"), BatteryStatus)
        self.assertIsInstance(decode_message("BUTTONS 1 a 4"), ButtonState)
        with self.assertRaises(ValueError):
            decode_message("HELLO 1")

    def test_status_fixtures(self) -> None:
        for line in fixture_lines("status_valid.txt"):
            with self.subTest(line=line):
                self.assertIsInstance(decode_message(line), (BatteryStatus, ButtonState))
        for line in fixture_lines("status_invalid.txt"):
            with self.subTest(line=line), self.assertRaises(ValueError):
                decode_message(line)

    def test_peripheral_byte(self) -> None:
        self.assertEqual(battery_from_peripheral_byte(43), (86, False))
        self.assertEqual(battery_from_peripheral_byte(0x40 | 31), (62, True))
        self.assertEqual(battery_from_peripheral_byte(0x3F), (100, False))  # 126 capped
        self.assertIsNone(battery_from_peripheral_byte(0x80 | 5))


if __name__ == "__main__":
    unittest.main()
