import tempfile
import threading
import unittest
from pathlib import Path

from vut_overlay.client import RoomClient
from vut_overlay.panel import Panel
from vut_roomstore import FakeTransport, RoomService, RoomStore, serve


class PanelTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.tracker = base / "tracker"
        service = RoomService(RoomStore(base / "rooms"), FakeTransport(self.tracker), base / "cal.txt")
        server = serve(service, base / "s.sock")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.panel = Panel(RoomClient(base / "s.sock", timeout=5))

    def press(self, label: str, room: str | None = None) -> None:
        b = next(b for b in self.panel.buttons if b.label == label and b.room == room)
        self.panel.click((b.box[0] + b.box[2]) // 2, (b.box[1] + b.box[3]) // 2)

    def test_save_new_then_load_other(self) -> None:
        (self.tracker / "general.db").write_text("one")
        self.press("Save current as new room")
        self.assertEqual(self.panel.status, "Saved Room 1")
        (self.tracker / "general.db").write_text("two")
        self.press("Save current as new room")
        self.press("Load", "room-1")  # room-2 is not active either; room-1 is not active yet
        self.assertEqual(self.panel.status, "Loaded Room 1")
        self.assertEqual((self.tracker / "general.db").read_text(), "one")
        self.assertFalse(any(b.label == "Load" and b.room == "room-1" for b in self.panel.buttons))

    def test_failure_is_shown(self) -> None:
        self.press("Save current as new room")  # tracker has no map
        self.assertTrue(self.panel.status.startswith("Failed"))

    def test_render_size(self) -> None:
        self.assertEqual(self.panel.render().size, (640, 480))

    def test_service_down(self) -> None:
        panel = Panel(RoomClient("/nonexistent.sock", timeout=1))
        self.assertIn("unreachable", panel.status)


if __name__ == "__main__":
    unittest.main()
