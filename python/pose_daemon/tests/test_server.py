import asyncio
import os
import socket
import sys
import tempfile
import unittest
from dataclasses import replace

from ultimate_linux_support.endpoint import parse_endpoint
from ultimate_linux_support.models import TrackerPose
from ultimate_linux_support.models import BatteryStatus, ButtonState, DeviceInfo, Event, Hello
from ultimate_linux_support.protocol import decode_message, decode_pose_line
from ultimate_linux_support.server import PoseServer
from ultimate_linux_support.sources import MockPoseSource, PoseSource, PyVutPoseSource


class FlakySource(PoseSource):
    def __init__(self) -> None:
        self.calls = 0

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def sample(self) -> list[TrackerPose]:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("boom")
        return await MockPoseSource(1).sample()


async def open_connection(spec: str):
    endpoint = parse_endpoint(spec)
    if endpoint.kind == "unix":
        return await asyncio.open_unix_connection(endpoint.path)
    return await asyncio.open_connection(endpoint.host, endpoint.port)


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        if sys.platform == "win32":  # no Unix sockets: loopback TCP, the Windows default transport
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
                self.path = f"tcp:127.0.0.1:{probe.getsockname()[1]}"
        else:
            self.path = os.path.join(self._tmp.name, "pose.sock")

    async def asyncTearDown(self) -> None:
        self._tmp.cleanup()

    async def _read_poses(self, count: int) -> list[TrackerPose]:
        reader, writer = await open_connection(self.path)
        try:
            poses = []
            while len(poses) < count:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line.startswith(b"POSE "):  # status lines are interleaved
                    poses.append(decode_pose_line(line.decode()))
            return poses
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_streams_mock_poses(self) -> None:
        server = PoseServer(self.path, MockPoseSource(tracker_count=2), hz=200)
        await server.start()
        try:
            poses = await self._read_poses(4)
        finally:
            await server.stop()
        self.assertEqual({p.serial for p in poses}, {"mock-0", "mock-1"})
        self.assertTrue(all(p.status == "ok" for p in poses))
        if sys.platform != "win32":
            self.assertFalse(os.path.exists(self.path))

    async def _read_messages(self, want: int) -> list:
        reader, writer = await open_connection(self.path)
        try:
            messages = []
            while len(messages) < want:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                messages.append(decode_message(line.decode()))
            return messages
        finally:
            writer.close()
            await writer.wait_closed()

    async def test_hello_first_then_devices(self) -> None:
        server = PoseServer(self.path, MockPoseSource(tracker_count=2), hz=200)
        await server.start()
        try:
            await asyncio.sleep(0.1)  # let the roster fill so a late joiner gets it from the cache
            messages = await self._read_messages(8)
        finally:
            await server.stop()
        self.assertIsInstance(messages[0], Hello)
        self.assertEqual(messages[0].source, "mock")
        devices = {m.serial: m for m in messages if isinstance(m, DeviceInfo)}
        self.assertEqual(set(devices), {"mock-0", "mock-1"})
        self.assertTrue(all(d.connected for d in devices.values()))

    async def test_source_error_event_sent_once_per_outage(self) -> None:
        class Broken(MockPoseSource):
            async def sample(self):
                raise RuntimeError("down")

        server = PoseServer(self.path, Broken(1), hz=200)
        await server.start()
        try:
            reader, writer = await open_connection(self.path)
            events = []
            for _ in range(10):
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                message = decode_message(line.decode())
                if isinstance(message, Event):
                    events.append(message)
                if events:
                    await asyncio.sleep(0.1)  # several failing cycles must not repeat the event
                    break
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()
        self.assertEqual([e.kind for e in events], ["source_error"])

    async def test_survives_source_error(self) -> None:
        server = PoseServer(self.path, FlakySource(), hz=200)
        await server.start()
        try:
            poses = await self._read_poses(2)
        finally:
            await server.stop()
        self.assertEqual(poses[0].serial, "mock-0")

    async def test_dropped_client_does_not_stop_others(self) -> None:
        server = PoseServer(self.path, MockPoseSource(1), hz=200)
        await server.start()
        try:
            _, w1 = await open_connection(self.path)
            w1.close()
            poses = await self._read_poses(2)
        finally:
            await server.stop()
        self.assertEqual(len(poses), 2)


    async def test_status_messages_reach_late_clients(self) -> None:
        server = PoseServer(self.path, MockPoseSource(tracker_count=1), hz=200)
        await server.start()
        try:
            await asyncio.sleep(0.05)  # let the first status broadcast populate the cache
            reader, writer = await open_connection(self.path)
            kinds = set()
            for _ in range(20):
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                kinds.add(type(decode_message(line.decode())))
                if {BatteryStatus, ButtonState} <= kinds:
                    break
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()
        self.assertIn(BatteryStatus, kinds)
        self.assertIn(ButtonState, kinds)


    async def test_haptic_from_client_reaches_source(self) -> None:
        source = MockPoseSource(tracker_count=1)
        server = PoseServer(self.path, source, hz=200)
        await server.start()
        try:
            reader, writer = await open_connection(self.path)
            writer.write(b"garbage\nHAPTIC 1 mock-0 0.1 160 1\nHAPTIC 1 mock-0 99 160 1\nHAPTIC 1 mock-0 0.2 100 0.5\n")
            await writer.drain()
            for _ in range(100):
                if len(source.haptics) >= 2:
                    break
                await asyncio.sleep(0.02)
            writer.close()
            await writer.wait_closed()
        finally:
            await server.stop()
        self.assertEqual([h.duration_s for h in source.haptics], [0.1, 0.2])  # bad lines dropped


class FakeRawPose:
    tracker_index = 1
    mac = "AA BB"
    tracking_status = 2
    position = (1.0, 2.0, 3.0)
    rotation = (0.0, 0.0, 0.0, 1.0)
    acceleration = (0.0, 0.0, 0.0)


class PyVutSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_pose_callback_and_staleness(self) -> None:
        source = PyVutPoseSource(stale_after_s=0.05)
        source._on_pose(FakeRawPose())
        fresh = await source.sample()
        self.assertEqual(len(fresh), 1)
        self.assertEqual(fresh[0].serial, "AA_BB")
        self.assertEqual(fresh[0].status, "ok")
        self.assertEqual(fresh[0].position_m, (1.0, 2.0, 3.0))

        await asyncio.sleep(0.1)
        stale = await source.sample()
        self.assertEqual(stale[0].status, "lost")
        self.assertEqual(stale[0].tracking_label, "STALE")

    async def test_status_mapping(self) -> None:
        self.assertEqual(PyVutPoseSource._normalize_status(2), ("ok", "OK"))
        self.assertEqual(PyVutPoseSource._normalize_status(3), ("lost", "LOST"))
        self.assertEqual(PyVutPoseSource._normalize_status(99)[0], "searching")


if __name__ == "__main__":
    unittest.main()
