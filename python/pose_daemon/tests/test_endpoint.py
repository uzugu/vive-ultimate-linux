import asyncio
import socket
import unittest

from ultimate_linux_support.endpoint import parse_endpoint
from ultimate_linux_support.protocol import decode_pose_line
from ultimate_linux_support.server import PoseServer
from ultimate_linux_support.sources import MockPoseSource
from ultimate_linux_support.socket_client import PoseStreamClient


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    def test_parse(self) -> None:
        self.assertEqual(str(parse_endpoint("/tmp/x.sock")), "unix:/tmp/x.sock")
        self.assertEqual(str(parse_endpoint("unix:/tmp/x.sock")), "unix:/tmp/x.sock")
        tcp = parse_endpoint("tcp:127.0.0.1:38450")
        self.assertEqual((tcp.kind, tcp.host, tcp.port), ("tcp", "127.0.0.1", 38450))
        self.assertEqual(parse_endpoint("tcp:::1:5000").host, "::1")
        for bad in ("tcp:127.0.0.1", "tcp:127.0.0.1:0", "tcp:127.0.0.1:99999", "tcp:0.0.0.0:5000",
                    "tcp:example.com:5000", "tcp:10.0.0.5:5000", "unix:", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_endpoint(bad)

    async def test_server_and_client_over_tcp(self) -> None:
        spec = f"tcp:127.0.0.1:{free_port()}"
        server = PoseServer(spec, MockPoseSource(tracker_count=1), hz=200)
        await server.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", parse_endpoint(spec).port)
            line = b""
            while not line.startswith(b"POSE "):
                line = await asyncio.wait_for(reader.readline(), timeout=5)
            self.assertEqual(decode_pose_line(line.decode()).serial, "mock-0")
            writer.close()
            await writer.wait_closed()

            def read_one():
                with PoseStreamClient(spec) as client:
                    return next(client.iter_poses())

            pose = await asyncio.wait_for(asyncio.to_thread(read_one), timeout=5)
            self.assertEqual(pose.serial, "mock-0")
        finally:
            await server.stop()


if __name__ == "__main__":
    unittest.main()
