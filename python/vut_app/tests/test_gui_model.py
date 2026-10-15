import asyncio
import importlib.util
import socket
import tempfile
import threading
import time
import unittest

from ultimate_linux_support.models import BatteryStatus, ButtonState, DeviceInfo, Event, Hello, TrackerPose
from ultimate_linux_support.server import PoseServer
from ultimate_linux_support.sources import MockPoseSource
from vut_app.gui_model import LiveState, RoomsModel, StreamWorker, button_names
from vut_roomstore.store import RoomStore


def pose(serial: str = "t0", index: int = 0, status: str = "ok") -> TrackerPose:
    return TrackerPose(index, serial, status, 2, "OK", (1.0, 2.0, 3.0), (0, 0, 0, 1), (0, 0, 0), 1)


class LiveStateTests(unittest.TestCase):
    def test_apply_all_message_types(self) -> None:
        s = LiveState()
        s.apply(Hello("0.1.0", "mock"))
        s.apply(pose("b", 1))
        s.apply(pose("a", 0))
        s.apply(BatteryStatus("a", 80, True))
        s.apply(ButtonState("a", 5))
        s.apply(DeviceInfo("a", 0, True))
        s.apply(Event("source_error", None, None))
        s.set_connection(True)
        connected, summary, trackers = s.snapshot()
        self.assertTrue(connected)
        self.assertIn("mock", summary)
        self.assertIn("source_error", summary)
        self.assertEqual([t.serial for t in trackers], ["a", "b"])  # sorted by index
        a = trackers[0]
        self.assertEqual((a.battery_percent, a.charging, a.buttons, a.connected), (80, True, 5, True))
        self.assertEqual(a.position_m, (1.0, 2.0, 3.0))

    def test_disconnect_clears_connected_flags(self) -> None:
        s = LiveState()
        s.apply(DeviceInfo("a", 0, True))
        s.set_connection(False, "waiting")
        connected, summary, trackers = s.snapshot()
        self.assertFalse(connected)
        self.assertEqual(summary, "waiting")
        self.assertFalse(trackers[0].connected)

    def test_snapshot_is_a_copy(self) -> None:
        s = LiveState()
        s.apply(pose())
        s.snapshot()[2][0].status = "mutated"
        self.assertEqual(s.snapshot()[2][0].status, "ok")

    def test_button_names(self) -> None:
        self.assertEqual(button_names(0), "-")
        self.assertEqual(button_names(1 | 4), "power,trigger")
        self.assertEqual(button_names(31), "power,grip,trigger,trackpad,menu")


class StreamWorkerTests(unittest.TestCase):
    def test_worker_follows_a_real_daemon_and_reconnects(self) -> None:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            spec = f"tcp:127.0.0.1:{probe.getsockname()[1]}"

        loop = asyncio.new_event_loop()
        started = threading.Event()
        holder = {}

        def run_server() -> None:
            asyncio.set_event_loop(loop)
            server = PoseServer(spec, MockPoseSource(tracker_count=2), hz=100)
            holder["server"] = server
            loop.run_until_complete(server.start())
            started.set()
            loop.run_forever()

        thread = threading.Thread(target=run_server, daemon=True)
        state = LiveState()
        worker = StreamWorker(spec, state, retry_s=0.05)
        worker.start()  # daemon not up yet: must keep retrying, not crash
        time.sleep(0.2)
        self.assertFalse(state.snapshot()[0])
        thread.start()
        self.assertTrue(started.wait(5))
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                connected, summary, trackers = state.snapshot()
                if connected and len(trackers) == 2 and "mock" in summary:
                    break
                time.sleep(0.05)
            self.assertTrue(connected)
            self.assertEqual({t.serial for t in trackers}, {"mock-0", "mock-1"})
            self.assertIn("mock", summary)
        finally:
            worker.stop()
            asyncio.run_coroutine_threadsafe(holder["server"].stop(), loop).result(5)
            loop.call_soon_threadsafe(loop.stop)
            thread.join(5)


class RoomsModelTests(unittest.TestCase):
    def test_rows_and_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RoomStore(f"{tmp}/rooms")
            store.create("Living room")
            store.create("Garage")
            calibration_file = f"{tmp}/calibration.txt"
            model = RoomsModel(store, calibration_file)
            self.assertEqual([r.name for r in model.rows()], ["Garage", "Living room"])
            self.assertFalse(any(r.active for r in model.rows()))
            self.assertIn("Garage", model.use("garage"))
            self.assertEqual([r.name for r in model.rows() if r.active], ["Garage"])
            self.assertTrue(open(calibration_file).read().startswith("CALIBRATION 1"))


@unittest.skipUnless(importlib.util.find_spec("tkinter"), "Tk not installed")
class TkSmokeTests(unittest.TestCase):
    def test_window_builds_and_refreshes(self) -> None:
        import tkinter as tk

        from vut_app.gui import build

        try:
            root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        try:
            state = LiveState()
            state.apply(pose())
            with tempfile.TemporaryDirectory() as tmp:
                store = RoomStore(f"{tmp}/rooms")
                store.create("Room A")
                from vut_app.map_model import MapModel
                from vut_mapbuild import RecordingLink

                mapper = MapModel(RecordingLink())
                refresh = build(root, state, RoomsModel(store, f"{tmp}/cal.txt"), mapper)
                refresh()
                mapper.start(0)
                refresh()
                root.update()
                self.assertEqual(mapper.view().phase, "starting")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
