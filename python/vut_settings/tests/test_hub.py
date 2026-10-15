import json
import unittest

from vut_settings import hub


class HubTests(unittest.TestCase):
    def test_requests(self) -> None:
        self.assertEqual(json.loads(hub.power_off_device(2, "k")), {"CmdType": 13, "CmdKey": "k", "DeviceIndex": 2})
        self.assertEqual(json.loads(hub.power_off_all("k")), {"CmdType": 21, "CmdKey": "k"})
        self.assertEqual(json.loads(hub.set_camera_frame_rate(30, "k"))["CameraFrameRate"], 30)
        auto = json.loads(hub.set_auto_sleep(True, 10, "k"))
        self.assertEqual((auto["CmdType"], auto["IsAutoSleep"], auto["AutoSleepTimeout"]), (24, True, 10))
        pair = json.loads(hub.pair(hub.DEVICE_PAIR_ALL_EMPTY, True, "k"))
        self.assertEqual((pair["CmdType"], pair["DeviceIndex"], pair["IsPair"]), (215, 0xFE, 1))
        self.assertEqual(json.loads(hub.pair(3, False, "k"))["IsPair"], 0)
        self.assertEqual(json.loads(hub.factory_reset_device(0, "k"))["CmdType"], 20)

    def test_validation(self) -> None:
        for call in (
            lambda: hub.power_off_device(5),
            lambda: hub.set_camera_frame_rate(0),
            lambda: hub.set_auto_sleep(True, -1),
            lambda: hub.pair(7, True),
            lambda: hub.factory_reset_device(-1),
        ):
            with self.assertRaises(ValueError):
                call()

    def test_generated_keys_differ(self) -> None:
        self.assertNotEqual(json.loads(hub.power_off_all())["CmdKey"], json.loads(hub.power_off_all())["CmdKey"])

    def test_responses(self) -> None:
        reply = hub.parse_response('{"CmdType":213,"CmdKey":"k","Result":0}', "k")
        self.assertTrue(hub.succeeded(reply))
        self.assertFalse(hub.succeeded({"CmdType": 213, "Result": 25}))
        for bad in ("nope", "[]", '{"CmdType":"x"}'):
            with self.assertRaises(ValueError):
                hub.parse_response(bad)
        with self.assertRaises(ValueError):
            hub.parse_response('{"CmdType":213,"CmdKey":"other"}', "k")

    def test_response_types_match_notes(self) -> None:
        self.assertEqual(hub.RESPONSE_TYPE[hub.CMD_POWER_OFF_DEVICE], 0xD5)
        self.assertEqual(hub.RESPONSE_TYPE[hub.CMD_SET_AUTO_SLEEP], 0xE0)


if __name__ == "__main__":
    unittest.main()
