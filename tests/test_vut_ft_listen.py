import socket
import queue
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python" / "tools"))

import vut_filetransfer as ft  # noqa: E402
import vut_ft_listen  # noqa: E402


def test_listener_records_frames(tmp_path, capsys):
    cap = tmp_path / "cap.bin"
    ready, stop = threading.Event(), threading.Event()
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    t = threading.Thread(target=vut_ft_listen.serve, args=("127.0.0.1", port, str(cap), ready, stop), daemon=True)
    t.start()
    assert ready.wait(2)
    data = b"hello"
    pkt = ft.file_header(3, len(data), "/sdcard/x.txt") + data + ft.file_trailer(3, data)
    with socket.create_connection(("127.0.0.1", port)) as c:
        c.sendall(pkt)
        time.sleep(0.3)
    time.sleep(0.3)
    stop.set()
    t.join(2)
    assert not t.is_alive()
    assert cap.read_bytes() == pkt
    out = capsys.readouterr().out
    assert "type=0x16" in out and "/sdcard/x.txt" in out
    assert "type=0x17" in out


@pytest.mark.parametrize("stride", [1, 2, 5, 127, 128, 129, 4096])
def test_stream_fragmentation_and_payload(stride):
    # Embedded magic and a valid-looking frame belong to the file, not control.
    data = b"prefix" + ft.file_header(99, 100, "/sdcard/false.txt") + b"suffix"
    wire = ft.file_header(3, len(data), "/sdcard/x.txt") + data + ft.file_trailer(3, data)
    decoder = vut_ft_listen.StreamDecoder()
    messages = []
    for offset in range(0, len(wire), stride):
        messages.extend(decoder.feed(wire[offset:offset + stride]))
    assert len(messages) == 2
    assert "type=0x16" in messages[0]
    assert "type=0x17" in messages[1]
    assert decoder.finish() == []


def test_stream_recovers_after_noise_and_split_magic():
    decoder = vut_ft_listen.StreamDecoder()
    header = ft.file_header(3, 0, "/sdcard/x.txt")
    assert "non-frame" in decoder.feed(b"noise" + header[:1])[0]
    assert "type=0x16" in decoder.feed(header[1:])[0]
    assert decoder.finish() == []


def test_stream_reports_truncation():
    decoder = vut_ft_listen.StreamDecoder()
    decoder.feed(ft.file_header(3, 10, "/sdcard/x.txt") + b"abc")
    assert decoder.finish() == ["incomplete file payload: 7 bytes missing"]
    decoder = vut_ft_listen.StreamDecoder()
    decoder.feed(b"\xd7")
    assert "incomplete frame: 1 bytes" in decoder.finish()[0]


def test_handler_is_passive_and_stops_with_idle_client(tmp_path):
    stop = threading.Event()
    server, client = socket.socketpair()
    try:
        with (tmp_path / "cap.bin").open("wb") as capture:
            worker = threading.Thread(
                target=vut_ft_listen.handle,
                args=(server, ("local", 0), capture, threading.Lock(), stop),
                daemon=True,
            )
            worker.start()
            client.settimeout(0.1)
            with pytest.raises(socket.timeout):
                client.recv(1)
            stop.set()
            worker.join(2)
            assert not worker.is_alive()
    finally:
        stop.set()
        server.close()
        client.close()


@pytest.mark.parametrize("duration", [0, -1, float("inf"), float("nan")])
def test_invalid_duration_rejected_before_capture_is_opened(tmp_path, duration):
    capture = tmp_path / "not-created.bin"
    with pytest.raises(ValueError, match="finite positive"):
        vut_ft_listen.serve("127.0.0.1", 0, str(capture), duration=duration)
    assert not capture.exists()


def test_bounded_server_stops_without_client(tmp_path):
    start = time.monotonic()
    vut_ft_listen.serve("127.0.0.1", 0, str(tmp_path / "empty.bin"), duration=0.05)
    assert time.monotonic() - start < 2
    assert (tmp_path / "empty.bin").read_bytes() == b""


def test_replay_never_opens_socket(tmp_path, capsys, monkeypatch):
    capture = tmp_path / "stream.bin"
    data = ft.file_header(99, 10, "/sdcard/false.txt")
    capture.write_bytes(ft.file_header(3, len(data), "/sdcard/x.txt") + data + ft.file_trailer(3, data))

    def forbidden(*args, **kwargs):
        raise AssertionError("offline replay must not open sockets")

    monkeypatch.setattr(socket, "socket", forbidden)
    vut_ft_listen.replay(str(capture))
    output = capsys.readouterr().out
    assert "type=0x16" in output and "type=0x17" in output
    assert "false.txt" not in output
    assert len(output.splitlines()) == 2


def test_replay_reports_incomplete_frame(tmp_path, capsys):
    capture = tmp_path / "partial.bin"
    capture.write_bytes(ft.file_header(3, 0, "/sdcard/x.txt")[:50])
    vut_ft_listen.replay(str(capture))
    assert "incomplete frame: 50 bytes" in capsys.readouterr().out


def test_duration_closes_idle_connection_before_return(tmp_path, monkeypatch):
    addresses = queue.Queue()
    ready = threading.Event()
    original_socket = socket.socket

    class ReportingSocket(original_socket):
        def bind(self, address):
            super().bind(address)
            addresses.put(self.getsockname())

    monkeypatch.setattr(socket, "socket", ReportingSocket)
    capture = tmp_path / "idle.bin"
    thread = threading.Thread(
        target=vut_ft_listen.serve,
        args=("127.0.0.1", 0, str(capture), ready),
        kwargs={"duration": 0.5},
        daemon=True,
    )
    thread.start()
    assert ready.wait(2)
    with socket.create_connection(addresses.get(timeout=2), timeout=2) as client:
        assert client.recv(1) == b""  # Timer stops the idle handler without sending.
    thread.join(2)
    assert not thread.is_alive()
    assert capture.read_bytes() == b""


def test_listener_refuses_occupied_port(tmp_path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        with pytest.raises(OSError):
            vut_ft_listen.serve("127.0.0.1", occupied.getsockname()[1], str(tmp_path / "unused.bin"))
