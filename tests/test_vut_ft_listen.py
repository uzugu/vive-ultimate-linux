import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python" / "tools"))

import vut_filetransfer as ft  # noqa: E402
import vut_ft_listen  # noqa: E402


def test_listener_records_frames(tmp_path, capsys):
    cap = tmp_path / "cap.bin"
    ready, stop = threading.Event(), threading.Event()
    port = 18053
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
    assert cap.read_bytes() == pkt
    out = capsys.readouterr().out
    assert "type=0x16" in out and "/sdcard/x.txt" in out
