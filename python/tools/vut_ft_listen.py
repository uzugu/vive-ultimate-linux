#!/usr/bin/env python3
"""Passive listener for the tracker file-transfer port (TCP 8053 by default).

Accepts tracker connections, never sends anything, and records what arrives: every 0x80-byte
frame that starts with the 0xB9D7 magic is printed (type, id, decoded fields where known)
and the raw stream is appended to a capture file. Use it to see what a tracker sends first
(see docs/re/vivehub-map-import.md section 3a.1). Stop HTC's ViveTrackerServer first: it
owns the same port.

  vut_ft_listen.py [--port 8053] [--bind 0.0.0.0] [--capture capture.bin]
"""
from __future__ import annotations

import argparse
import socket
import struct
import sys
import threading
import time

from vut_filetransfer import MAGIC, PACKET_LEN, parse


def describe(frame: bytes) -> str:
    magic, tid, mtype = struct.unpack_from("<HHB", frame, 0)
    if magic != MAGIC:
        return f"no magic ({magic:#06x}) {frame[:16].hex()}"
    try:
        info = parse(frame)
    except ValueError as e:
        return f"id={tid} type={mtype:#04x} ({mtype}) {e}"
    extra = {k: v for k, v in info.items() if k not in ("tracker_id", "type")}
    return f"id={tid} type={mtype:#04x} ({mtype}) {extra if extra else frame[5:24].hex()}"


def handle(conn: socket.socket, addr, capture, lock: threading.Lock) -> None:
    buf = b""
    print(f"[{time.strftime('%H:%M:%S')}] connect {addr[0]}:{addr[1]}", flush=True)
    try:
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            with lock:
                capture.write(chunk)
                capture.flush()
            buf += chunk
            while len(buf) >= PACKET_LEN and struct.unpack_from("<H", buf, 0)[0] == MAGIC:
                print(f"[{time.strftime('%H:%M:%S')}] {addr[0]} {describe(buf[:PACKET_LEN])}", flush=True)
                buf = buf[PACKET_LEN:]
            if buf and struct.unpack_from("<H", buf.ljust(2, b"\0"), 0)[0] != MAGIC:
                print(f"[{time.strftime('%H:%M:%S')}] {addr[0]} {len(buf)} bytes of non-frame data: {buf[:32].hex()}", flush=True)
                buf = b""
    finally:
        conn.close()
        print(f"[{time.strftime('%H:%M:%S')}] close {addr[0]}:{addr[1]}", flush=True)


def serve(bind: str, port: int, capture_path: str, ready: threading.Event | None = None, stop: threading.Event | None = None) -> None:
    lock = threading.Lock()
    with open(capture_path, "ab") as capture, socket.socket() as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((bind, port))
        srv.listen(8)
        srv.settimeout(0.5)
        if ready:
            ready.set()
        while not (stop and stop.is_set()):
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            threading.Thread(target=handle, args=(conn, addr, capture, lock), daemon=True).start()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8053)
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--capture", default="vut-ft-capture.bin")
    a = p.parse_args()
    print(f"listening on {a.bind}:{a.port}, capture -> {a.capture} (Ctrl-C to stop)", flush=True)
    try:
        serve(a.bind, a.port, a.capture)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
