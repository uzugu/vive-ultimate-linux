import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from vut_app import map_cli
from vut_app.map_model import STEPS, MapModel
from vut_mapbuild import RecordingLink, TrackerNotice, TrackerRecord

FIXTURE = Path(__file__).parents[2] / "vut_mapbuild" / "tests" / "fixtures" / "server-map-build-20261014.txt"


def rec(t, slot, *, host=False, trk=2, has=True):
    return TrackerRecord(t, slot, True, trk, 80, 0, 6, has, 0, host, -1)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class MapModelTests(unittest.TestCase):
    def test_default_link_shows_a_clear_error_and_stays_idle(self) -> None:
        m = MapModel()
        msg = m.start(0)
        self.assertIn("no transport", msg)
        v = m.view()
        self.assertEqual(v.phase, "idle")
        self.assertTrue(v.can_start)
        self.assertFalse(v.can_finish or v.can_cancel)
        self.assertIn("no transport", v.message)

    def test_walkthrough_buttons_follow_phase(self) -> None:
        clock, link = Clock(), RecordingLink()
        m = MapModel(link, clock)
        m.feed(rec(0, 4, host=True))
        m.start(4)
        v = m.view()
        self.assertEqual((v.phase, v.step, v.can_start, v.can_cancel, v.can_finish), ("starting", 0, False, True, False))
        clock.now = 3
        m.feed(rec(3, 4, host=True, trk=7, has=False))
        self.assertTrue(m.view().can_finish)
        self.assertIn("Hold", m.view().hint)
        m.scan_stage(1)
        self.assertIn("low", m.view().hint)
        m.feed(TrackerNotice(5, "overspeed", 4))
        self.assertEqual(m.view().warnings, 1)
        clock.now = 70
        m.finish()
        self.assertEqual(m.view().phase, "saving")
        m.feed(rec(75, 4, host=True))
        self.assertEqual(m.view().phase, "done")
        self.assertEqual(m.view().fraction, 1.0)
        self.assertEqual(m.view().elapsed, "1:15")

    def test_wrong_action_reports_error_not_exception(self) -> None:
        m = MapModel(RecordingLink())
        self.assertIn("cannot finish", m.finish())
        self.assertIn("nothing to cancel", m.cancel())

    def test_replay_of_real_log(self) -> None:
        m = MapModel()
        self.assertIn("final: done", m.replay_log(str(FIXTURE)))
        self.assertEqual(m.view().phase, "done")
        self.assertIn("No such file", m.replay_log("/nonexistent/x.log"))

    def test_replay_of_utf16_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "ViveTrackerServer.txt"
            f.write_bytes(b"\xff\xfe" + FIXTURE.read_text(encoding="utf-8").encode("utf-16-le"))
            m = MapModel()
            self.assertIn("final: done", m.replay_log(str(f)))
            self.assertEqual(self.run_cli_replay(f), 0)

    @staticmethod
    def run_cli_replay(path) -> int:  # type: ignore[no-untyped-def]
        with redirect_stdout(io.StringIO()):
            return map_cli.main(["replay", str(path)])

    def test_quality_text(self) -> None:
        self.assertEqual(MapModel().quality_text(), "No map recorded yet.")
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "Calibration.json"
            f.write_text(json.dumps({"map_setup": {"last_map_creation_time": 1, "map_quality": [85, 60, 85]}}))
            text = MapModel(calibration_file=str(f)).quality_text()
        self.assertIn("refinable", text)
        self.assertIn("Weak sides: 2", text)
        self.assertEqual(MapModel(calibration_file="/nonexistent.json").quality_text(), "No map recorded yet.")

    def test_steps(self) -> None:
        self.assertEqual(STEPS, ("Start", "Scan", "Review", "Save", "Share"))


class MapCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = map_cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_plan_lists_commands_and_confidence(self) -> None:
        code, out, _ = self.run_cli("plan")
        self.assertEqual(code, 0)
        self.assertIn("FW2 then ATM20", out)
        self.assertIn("[code]", out)
        self.assertIn("nothing is sent", out)

    def test_replay_prints_timeline(self) -> None:
        code, out, _ = self.run_cli("replay", str(FIXTURE))
        self.assertEqual(code, 0)
        self.assertIn("scanning", out)
        self.assertIn("final: done", out)

    def test_quality_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "c.json"
            f.write_text(json.dumps({"map_setup": {"map_quality": [85, 80]}}))
            code, out, _ = self.run_cli("quality", str(f))
        self.assertEqual((code, "ok" in out), (0, True))
        self.assertEqual(self.run_cli("quality", "/nonexistent.json")[0], 1)
        self.assertEqual(self.run_cli("bogus")[0], 2)
        self.assertEqual(self.run_cli()[0], 2)


if __name__ == "__main__":
    unittest.main()
