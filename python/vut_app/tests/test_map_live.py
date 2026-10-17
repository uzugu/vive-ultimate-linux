import unittest

from vut_app import map_live
from vut_mapbuild import RecordingLink


class MapLiveTests(unittest.TestCase):
    def test_full_sequence(self):
        link, said = RecordingLink(), []
        answers = iter(["YES"] + [""] * 5)
        rc = map_live.run(link, 0, "DE", lambda _p: next(answers), said.append)
        self.assertEqual(rc, 0)
        self.assertEqual(
            [c for _s, c in link.sent],
            ["FW2", "WcDE", "ATM20", "pMS_SC", "pMS_ILA", "pMS_IHA", "pMS_ES", "ALE"],
        )

    def test_not_confirmed_sends_nothing(self):
        link = RecordingLink()
        self.assertEqual(map_live.run(link, 0, "DE", lambda _p: "no", lambda _m: None), 1)
        self.assertEqual(link.sent, [])

    def test_bad_tracker_id(self):
        self.assertEqual(map_live.main(["--tracker-id", "zz", "--country", "DE"]), 2)

    def test_no_hidapi(self):
        class NoDev:
            class device:
                def open(self, v, p):
                    raise OSError("none")

        self.assertEqual(map_live.main(["--tracker-id", "0102030405", "--country", "DE"], hid_module=NoDev), 1)

    def test_learns_host_from_button(self):
        class Dev:
            def __init__(self):
                self.reports = [b"\x28" + bytes([0] * 3) + bytes([7] * 5) + bytes(4) + bytes([0x81]) + bytes(50)]

            def read(self, size, timeout):
                return self.reports.pop(0) if self.reports else b""

        said = []
        self.assertEqual(map_live.learn_host_id(Dev(), said.append), bytes([7] * 5))

    def test_no_press_times_out(self):
        class Dev:
            def read(self, size, timeout):
                return b""

        ticks = iter(range(0, 1000))
        self.assertIsNone(map_live.learn_host_id(Dev(), lambda _m: None, timeout_s=3, clock=lambda: next(ticks)))


if __name__ == "__main__":
    unittest.main()
