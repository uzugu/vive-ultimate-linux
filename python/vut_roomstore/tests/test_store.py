import json
import os
import tempfile
import unittest
from pathlib import Path

from vut_roomstore import Calibration, RoomError, RoomStore, calibration_from_htc, format_calibration_line, slugify
from vut_roomstore.cli import main

HTC_SAMPLE = json.dumps(
    {
        "map_setup": {"last_map_creation_time": 1791997907, "map_quality": [85, 80, 75]},
        "transform": {
            "position": [1.054179310798645, 1.6590327024459839, 1.6691875457763672],
            "rotation": [0, 0.52774560451507568, 0, 0.84940248727798462],
            "scale": 1,
        },
    }
)


class StoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "rooms"
        self.store = RoomStore(self.root)

    def test_slugify(self) -> None:
        self.assertEqual(slugify("  Living Room #2 "), "living-room-2")
        with self.assertRaises(RoomError):
            slugify("!!!")

    def test_create_get_list_delete(self) -> None:
        self.store.create("Living room", Calibration((1, 2, 3), (0, 0, 0, 2)))
        self.store.create("Garage")
        room = self.store.get("living-room")
        self.assertEqual(room.calibration.translation_m, (1, 2, 3))
        self.assertEqual(room.calibration.rotation_xyzw, (0, 0, 0, 1))  # normalised
        self.assertEqual([r.slug for r in self.store.list()], ["garage", "living-room"])
        with self.assertRaises(RoomError):
            self.store.create("LIVING ROOM")
        self.store.delete("Garage")
        self.assertEqual([r.slug for r in self.store.list()], ["living-room"])
        with self.assertRaises(RoomError):
            self.store.get("garage")

    def test_bad_calibration_rejected(self) -> None:
        for bad in (Calibration((0, 0, 0), (0, 0, 0, 0)), Calibration((float("nan"), 0, 0), (0, 0, 0, 1))):
            with self.assertRaises(RoomError):
                self.store.create("x" + str(id(bad)), bad)

    def test_corrupt_or_future_file(self) -> None:
        self.store.create("a")
        path = self.root / "a" / "room.json"
        data = json.loads(path.read_text())
        data["version"] = 99
        path.write_text(json.dumps(data))
        with self.assertRaises(RoomError):
            self.store.get("a")

    def test_import_htc_calibration(self) -> None:
        cal, meta = calibration_from_htc(HTC_SAMPLE)
        self.assertAlmostEqual(cal.translation_m[2], 1.6691875457763672)
        self.assertAlmostEqual(sum(v * v for v in cal.rotation_xyzw), 1.0, places=9)
        self.assertEqual(meta["map_quality"], [85, 80, 75])
        self.store.create("lab")
        room = self.store.import_htc_calibration("lab", HTC_SAMPLE)
        self.assertEqual(room.last_map_creation_time, 1791997907)
        for bad in ("nope", "{}", json.dumps({"transform": {"position": [1, 2], "rotation": [0, 0, 0, 1]}}),
                    json.dumps({"transform": {"position": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": 2}})):
            with self.assertRaises(RoomError):
                calibration_from_htc(bad)

    def test_use_writes_driver_file_and_switches(self) -> None:
        self.store.create("a", Calibration((1, 0, 0), (0, 0, 0, 1)))
        self.store.create("b", Calibration((0, 0, 5), (0, 0.7071067811865476, 0, 0.7071067811865476)))
        target = Path(self._tmp.name) / "cfg" / "calibration.txt"
        self.store.use("a", target)
        self.assertEqual(self.store.active_slug(), "a")
        self.assertTrue(target.read_text().startswith("CALIBRATION 1 1.000000000 0.000000000 0.000000000"))
        self.store.use("b", target)
        self.assertEqual(self.store.active_slug(), "b")
        parts = target.read_text().split()
        self.assertEqual(len(parts), 9)
        self.assertEqual(parts[:2], ["CALIBRATION", "1"])
        self.store.delete("b")
        self.assertIsNone(self.store.active_slug())

    def test_format_line_matches_python_daemon_grammar(self) -> None:
        line = format_calibration_line(Calibration((0, 1, 2), (0, 0, 0, 3)))
        self.assertEqual(line, "CALIBRATION 1 0.000000000 1.000000000 2.000000000 0.000000000 0.000000000 0.000000000 1.000000000")

    def test_attach_maps_stays_private(self) -> None:
        self.store.create("a")
        db = Path(self._tmp.name) / "general.db"
        db.write_bytes(b"SQLite format 3\0")
        room = self.store.attach_map_files("a", [db])
        self.assertEqual(room.map_files, ["general.db"])
        self.assertTrue((self.root / "a" / "maps" / "general.db").is_file())
        self.assertEqual((self.root / "a" / "maps").stat().st_mode & 0o077, 0)
        with self.assertRaises(RoomError):
            self.store.attach_map_files("a", [Path(self._tmp.name) / "photo.jpg"])

    def test_attach_maps_refused_inside_git_tree(self) -> None:
        repo = Path(self._tmp.name) / "repo"
        (repo / ".git").mkdir(parents=True)
        store = RoomStore(repo / "rooms")
        store.create("a")
        db = Path(self._tmp.name) / "x.db"
        db.write_bytes(b"x")
        with self.assertRaises(RoomError):
            store.attach_map_files("a", [db])

    def test_cli(self) -> None:
        cal_file = Path(self._tmp.name) / "cal.txt"
        base = ["--root", str(self.root)]
        self.assertEqual(main(base + ["new", "Den", "--offset", "0,0,1"]), 0)
        self.assertEqual(main(base + ["use", "den", "--calibration-file", str(cal_file)]), 0)
        self.assertIn("CALIBRATION 1 0.000000000 0.000000000 1.000000000", cal_file.read_text())
        self.assertEqual(main(base + ["list"]), 0)
        self.assertEqual(main(base + ["show", "missing"]), 1)


if __name__ == "__main__":
    unittest.main()
