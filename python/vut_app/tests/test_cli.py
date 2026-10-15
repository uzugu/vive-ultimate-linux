import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from vut_app import cli


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_help_lists_commands(self) -> None:
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        for name in ("daemon", "room", "calibrate", "doctor"):
            self.assertIn(name, out)

    def test_no_args_is_usage_error(self) -> None:
        self.assertEqual(self.run_cli()[0], 2)

    def test_unknown_command(self) -> None:
        code, _, err = self.run_cli("nope")
        self.assertEqual(code, 2)
        self.assertIn("unknown command", err)

    def test_version(self) -> None:
        self.assertEqual(self.run_cli("version")[1].strip(), cli.__version__)

    def test_dispatch_passes_args_and_return_code(self) -> None:
        seen = {}

        def fake_main() -> int:
            import sys

            seen["argv"] = list(sys.argv)
            return 7

        with mock.patch.dict(cli.COMMANDS, {"room": (lambda: fake_main, "x")}):
            code, _, _ = self.run_cli("room", "list", "--root", "/tmp/r")
        self.assertEqual(code, 7)
        self.assertEqual(seen["argv"], ["vut room", "list", "--root", "/tmp/r"])

    def test_windows_calibration_paths_match_driver_precedence(self) -> None:
        from ultimate_linux_support.calibration import default_path
        from vut_roomstore.cli import _default_calibration_file

        env = {"APPDATA": "C:/profile/Roaming"}
        for function in (default_path, _default_calibration_file):
            with self.subTest(function=function.__module__):
                with mock.patch.dict(os.environ, env, clear=True), mock.patch("sys.platform", "win32"):
                    self.assertEqual(function(), os.path.join(env["APPDATA"], "ultimate-tracker", "calibration.txt"))
                    with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "C:/xdg"}):
                        self.assertEqual(function(), os.path.join("C:/xdg", "ultimate-tracker", "calibration.txt"))
                    with mock.patch.dict(os.environ, {"ULTIMATE_TRACKER_CALIBRATION": "C:/custom.txt"}):
                        self.assertEqual(function(), "C:/custom.txt")

    def test_doctor_reports_invalid_endpoint_without_traceback(self) -> None:
        with mock.patch.dict(os.environ, {"ULTIMATE_TRACKER_SOCKET_PATH": "tcp:0.0.0.0:38450"}):
            code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("loopback", out)

    def test_doctor_reports_unreachable_daemon(self) -> None:
        with mock.patch.dict("os.environ", {"ULTIMATE_TRACKER_SOCKET_PATH": "tcp:127.0.0.1:1"}):
            code, out, _ = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("not reachable", out)


if __name__ == "__main__":
    unittest.main()
