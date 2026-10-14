import struct
import unittest

from htc_pipe_codec import (
    MAGIC_CLIENT,
    MAGIC_SERVER,
    Cmd,
    pack_packet,
    parse_accessory_records,
    parse_enumerate_response,
    parse_pose_records,
    unpack_packet,
)


class FramingTests(unittest.TestCase):
    def test_round_trip(self):
        raw = pack_packet(MAGIC_CLIENT, Cmd.ENUMERATE_TRACKERS, b"", pid=7, stamp=9)
        pkt = unpack_packet(raw)
        self.assertEqual((pkt.header.magic, pkt.header.cmd, pkt.header.pid, pkt.header.length), (MAGIC_CLIENT, 0x17, 7, 0))

    def test_trailing_bytes_ignored(self):
        raw = pack_packet(MAGIC_SERVER, Cmd.GET_DEVICE_ID, b"abcd") + b"\0" * 8
        self.assertEqual(unpack_packet(raw).payload, b"abcd")

    def test_short(self):
        with self.assertRaises(ValueError):
            unpack_packet(b"\0" * 19)
        with self.assertRaises(ValueError):
            unpack_packet(struct.pack("<5I", MAGIC_SERVER, 3, 0, 0, 10) + b"x")


class RecordTests(unittest.TestCase):
    def test_pose(self):
        rec = bytearray(85)
        struct.pack_into("<Q", rec, 0, 0xABC)
        rec[10], rec[13], rec[68], rec[84] = 1, 4, 2, 9
        struct.pack_into("<13f", rec, 14, *[float(i) for i in range(13)])
        struct.pack_into("<d", rec, 72, 0.25)
        struct.pack_into("<I", rec, 80, 77)
        (p,) = parse_pose_records(bytes(rec))
        self.assertEqual((p.vhandle, p.device_flag, p.pose_status, p.tracking_state, p.extra), (0xABC, 1, 4, 2, 9))
        self.assertEqual(p.position, (0.0, 1.0, 2.0))
        self.assertEqual(p.rotation_raw, (3.0, 4.0, 5.0, 6.0))
        self.assertEqual((p.pose_time_offset, p.word80), (0.25, 77))

    def test_pose_bad_size(self):
        with self.assertRaises(ValueError):
            parse_pose_records(b"\0" * 86)

    def test_accessory(self):
        (a,) = parse_accessory_records(struct.pack("<QdI", 5, 1.5, 3))
        self.assertEqual((a.vhandle, a.timestamp, a.data), (5, 1.5, 3))

    def test_enumerate(self):
        entry = struct.pack("<32sii", b"SN123", 4, 1)
        payload = struct.pack("<i", 1) + entry + struct.pack("<i", 0)
        entries, status = parse_enumerate_response(payload)
        self.assertEqual((entries[0].serial, entries[0].steamvr_index, entries[0].display_index, status), ("SN123", 4, 1, 0))


if __name__ == "__main__":
    unittest.main()
