import math
import os
import tempfile
import unittest

from ultimate_linux_support.calibration import fit_yaw_translation, format_calibration, main


def rotate_y(p, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return (p[0] * c + p[2] * s, p[1], -p[0] * s + p[2] * c)


class CalibrationTests(unittest.TestCase):
    def test_fit_recovers_known_transform(self) -> None:
        yaw = math.radians(37.0)
        offset = (0.4, 0.1, -1.2)
        src = [(0.0, 1.0, 0.0), (1.0, 1.1, 0.2), (0.3, 0.9, 1.5), (-0.8, 1.0, 0.7)]
        pairs = []
        for p in src:
            r = rotate_y(p, yaw)
            pairs.append((p, (r[0] + offset[0], r[1] + offset[1], r[2] + offset[2])))
        translation, fitted = fit_yaw_translation(pairs)
        self.assertAlmostEqual(fitted, yaw, places=9)
        for got, want in zip(translation, offset):
            self.assertAlmostEqual(got, want, places=9)

    def test_fit_needs_horizontal_spread(self) -> None:
        with self.assertRaises(ValueError):
            fit_yaw_translation([((0, 1, 0), (0, 1, 0)), ((0, 2, 0), (0, 2, 0))])
        with self.assertRaises(ValueError):
            fit_yaw_translation([((0, 1, 0), (0, 1, 0))])

    def test_format_matches_driver_grammar(self) -> None:
        line = format_calibration((1.0, 2.0, 3.0), math.pi / 2)
        parts = line.split()
        self.assertEqual(parts[:2], ["CALIBRATION", "1"])
        self.assertEqual(len(parts), 9)
        self.assertAlmostEqual(float(parts[6]), math.sin(math.pi / 4), places=8)

    def test_cli_writes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "sub", "calibration.txt")
            self.assertEqual(main(["--output", out, "--manual", "--yaw-deg", "90", "--offset", "0,0,2"]), 0)
            with open(out) as handle:
                self.assertTrue(handle.read().startswith("CALIBRATION 1 0.000000000 0.000000000 2.000000000"))
            self.assertEqual(main(["--output", out, "--identity"]), 0)


if __name__ == "__main__":
    unittest.main()
