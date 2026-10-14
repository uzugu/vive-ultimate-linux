import unittest

from vut_settings import ServerConfig, auto_sleep, camera_frame_rate, dump_config, load_config, power_off, reboot
from vut_settings.commands import FRAME_SIZE


class FrameTests(unittest.TestCase):
    def test_layout(self):
        f = reboot()
        self.assertEqual(len(f), FRAME_SIZE)
        self.assertEqual(f[:5], b"\x01\x03APR")
        self.assertEqual(f[5:], b"\0" * (FRAME_SIZE - 5))

    def test_commands(self):
        self.assertEqual(power_off()[2:5], b"APF")
        self.assertEqual(camera_frame_rate(60)[1:7], b"\x05ACF60")
        self.assertEqual(auto_sleep(0)[1:9], b"\x07pAS_TS0")
        self.assertEqual(auto_sleep(3)[1:9], b"\x07pAS_TS3")

    def test_validation(self):
        with self.assertRaises(ValueError):
            auto_sleep(-1)
        with self.assertRaises(ValueError):
            camera_frame_rate(0)


class ConfigTests(unittest.TestCase):
    def test_defaults_roundtrip(self):
        cfg = ServerConfig()
        self.assertEqual(load_config(dump_config(cfg)), cfg)

    def test_effective_auto_sleep(self):
        self.assertEqual(ServerConfig(is_auto_sleep=False, auto_sleep_timeout=5).effective_auto_sleep, 0)
        self.assertEqual(ServerConfig(is_auto_sleep=True, auto_sleep_timeout=5).effective_auto_sleep, 5)

    def test_unknown_keys_ignored(self):
        self.assertEqual(load_config('{"server": {"camera_frame_rate": 50, "x": 1}}').camera_frame_rate, 50)


if __name__ == "__main__":
    unittest.main()
