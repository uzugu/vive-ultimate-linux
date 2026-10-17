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


if __name__ == "__main__":
    unittest.main()
