import json
import unittest
from pathlib import Path

from ultimate_linux_support.models import TrackerPose
from ultimate_linux_support.protocol import decode_pose_line, encode_pose_line, pose_to_json_line

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


if __name__ == "__main__":
    unittest.main()
