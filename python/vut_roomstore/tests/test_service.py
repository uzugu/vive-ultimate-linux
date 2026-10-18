import json
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from vut_roomstore import FakeTransport, RoomService, RoomStore, serve


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.tracker = base / "tracker"
        self.transport = FakeTransport(self.tracker)
        self.cal = base / "calibration.txt"
        self.service = RoomService(RoomStore(base / "rooms"), self.transport, self.cal)

    def set_map(self, content: str) -> None:
        for old in self.tracker.glob("*.db"):
            old.unlink()
        (self.tracker / "general.db").write_text(content)

    def test_save_switch_roundtrip(self) -> None:
        self.set_map("living")
        self.assertTrue(self.service.handle({"op": "save", "name": "Living room"})["ok"])
        self.set_map("garage")
        self.service.handle({"op": "save", "name": "Garage"})
        reply = self.service.handle({"op": "load", "name": "living-room"})
        self.assertTrue(reply["ok"] and reply["room"]["active"])
        self.assertEqual((self.tracker / "general.db").read_text(), "living")
        self.assertTrue(self.cal.read_text().startswith("CALIBRATION 1"))
        self.assertEqual([r["slug"] for r in self.service.handle({"op": "list"})["rooms"]], ["garage", "living-room"])

    def test_load_without_map_fails_and_keeps_active(self) -> None:
        self.service.store.create("Empty")
        reply = self.service.handle({"op": "load", "name": "Empty"})
        self.assertFalse(reply["ok"])
        self.assertIsNone(self.service.store.active_slug())

    def test_save_with_no_tracker_map_errors(self) -> None:
        self.assertFalse(self.service.handle({"op": "save", "name": "X"})["ok"])

    def test_socket(self) -> None:
        self.set_map("a")
        sock_path = Path(self._tmp.name) / "s.sock"
        server = serve(self.service, sock_path)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with socket.socket(socket.AF_UNIX) as s:
            s.connect(str(sock_path))
            s.sendall(b'{"op":"save","name":"A"}\n')
            self.assertTrue(json.loads(s.makefile().readline())["ok"])


if __name__ == "__main__":
    unittest.main()
