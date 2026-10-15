#!/usr/bin/env python3
"""Passive listener for the tracker file-transfer port (TCP 8053 by default).

Accepts tracker connections, never sends anything, and records what arrives: every 0x80-byte
frame that starts with the 0xB9D7 magic is printed (type, id, decoded fields where known)
and the raw stream is appended to a capture file. Known message-22 payloads are
skipped by their declared size, so file bytes cannot be mistaken for control frames.
The capture combines received chunks from all connections; use one tracker at a
time for an unambiguous raw stream. Captures may contain private room images: keep
them local and never commit them. Use it to see what a tracker sends first
(see docs/re/vivehub-map-import.md section 3a.1). Stop HTC's ViveTrackerServer first: it
owns the same port.

  vut_ft_listen.py [--port 8053] [--bind 0.0.0.0] [--capture capture.bin] [--duration 60]
  vut_ft_listen.py --replay capture.bin
"""
from __future__ import annotations

import argparse
import math
import socket
import struct
import sys
import threading
import time

from vut_filetransfer import MAGIC, MSG_FILE_HEADER, PACKET_LEN, parse


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


class StreamDecoder:
    """Decode framed control messages without treating known file bytes as frames."""

    def __init__(self) -> None:
        self.buffer = b""
        self.payload_remaining = 0

    def feed(self, chunk: bytes) -> list[str]:
        self.buffer += chunk
        messages = []
        marker = struct.pack("<H", MAGIC)
        while self.buffer:
            if self.payload_remaining:
                count = min(len(self.buffer), self.payload_remaining)
                self.buffer = self.buffer[count:]
                self.payload_remaining -= count
                continue
            if not self.buffer.startswith(marker):
                # Keep a trailing first magic byte: TCP may split the marker.
                offset = self.buffer.find(marker)
                if offset < 0:
                    offset = len(self.buffer) - int(self.buffer.endswith(marker[:1]))
                if not offset:
                    break
                data, self.buffer = self.buffer[:offset], self.buffer[offset:]
                messages.append(f"{len(data)} bytes of non-frame data: {data[:32].hex()}")
                continue
            if len(self.buffer) < PACKET_LEN:
                break
            frame, self.buffer = self.buffer[:PACKET_LEN], self.buffer[PACKET_LEN:]
            messages.append(describe(frame))
            if frame[4] == MSG_FILE_HEADER:
                self.payload_remaining = struct.unpack_from("<I", frame, 6)[0]
        return messages

    def finish(self) -> list[str]:
        if self.payload_remaining:
            return [f"incomplete file payload: {self.payload_remaining} bytes missing"]
        if self.buffer:
            return [f"incomplete frame: {len(self.buffer)} bytes: {self.buffer[:32].hex()}"]
        return []


def handle(conn: socket.socket, addr, capture, lock: threading.Lock,
           stop: threading.Event | None = None) -> None:
    decoder = StreamDecoder()
    print(f"[{time.strftime('%H:%M:%S')}] connect {addr[0]}:{addr[1]}", flush=True)
    conn.settimeout(0.5)
    try:
        while not (stop and stop.is_set()):
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                continue
            if not chunk:
                break
            with lock:
                capture.write(chunk)
                capture.flush()
            for message in decoder.feed(chunk):
                print(f"[{time.strftime('%H:%M:%S')}] {addr[0]} {message}", flush=True)
    except OSError as error:
        print(f"[{time.strftime('%H:%M:%S')}] {addr[0]} connection error: {error}", flush=True)
    finally:
        for message in decoder.finish():
            print(f"[{time.strftime('%H:%M:%S')}] {addr[0]} {message}", flush=True)
        conn.close()
        print(f"[{time.strftime('%H:%M:%S')}] close {addr[0]}:{addr[1]}", flush=True)


def serve(bind: str, port: int, capture_path: str, ready: threading.Event | None = None, stop: threading.Event | None = None, *, duration: float | None = None) -> None:
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        raise ValueError("duration must be a finite positive number")
    lock = threading.Lock()
    stop = stop if stop is not None else threading.Event()
    workers = []
    with open(capture_path, "ab") as capture, socket.socket() as srv:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            # Windows SO_REUSEADDR can allow an ambiguous bind to an occupied port.
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((bind, port))
        srv.listen(8)
        srv.settimeout(0.5)
        print(f"listening on {bind}:{srv.getsockname()[1]}, capture -> {capture_path}", flush=True)
        timer = threading.Timer(duration, stop.set) if duration is not None else None
        if timer:
            timer.daemon = True
            timer.start()
        if ready:
            ready.set()
        try:
            while not stop.is_set():
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                worker = threading.Thread(target=handle, args=(conn, addr, capture, lock, stop), daemon=True)
                workers = [thread for thread in workers if thread.is_alive()]
                workers.append(worker)
                worker.start()
        finally:
            stop.set()
            if timer:
                timer.cancel()
            # Workers must stop writing before the capture file closes.
            for worker in workers:
                worker.join()


def replay(capture_path: str) -> None:
    """Decode a single-stream local capture without opening any sockets."""
    decoder = StreamDecoder()
    with open(capture_path, "rb") as source:
        while chunk := source.read(65536):
            for message in decoder.feed(chunk):
                print(message)
    for message in decoder.finish():
        print(message)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8053)
    p.add_argument("--bind", default="0.0.0.0")
    p.add_argument("--capture", default="vut-ft-capture.bin")
    p.add_argument("--duration", type=float, help="stop after this many seconds (positive, finite)")
    p.add_argument("--replay", metavar="CAPTURE", help="decode a local capture without listening")
    a = p.parse_args()
    if a.duration is not None and (not math.isfinite(a.duration) or a.duration <= 0):
        p.error("--duration must be a finite positive number")
    if a.replay and a.duration is not None:
        p.error("--duration applies only to a live capture")
    try:
        if a.replay:
            replay(a.replay)
        else:
            serve(a.bind, a.port, a.capture, duration=a.duration)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
