"""Packet builders for the tracker Wi-Fi file-transfer messages seen in HTC's tracker library.

Status: decoded from static analysis of VIVE Hub for Windows 1.2.7 (docs/re/vivehub-windows-map-transfer.md).
NOT yet verified against a real tracker: field meanings marked "?" are guesses. Do not point this at hardware
you cannot recover (use a spare tracker, keep a map backup).

Wire format (little-endian), both messages are 0x80 bytes and share a header:
  +0  u16  magic 0xB9D7
  +2  u16  tracker id (the library also uses it as its "[%d]" log prefix)
  +4  u8   message type: 0x16 (22) = file header, 0x17 (23) = file trailer
Message 22:  +6 u32 file size, +0xA u16 0x400 when `flag` is set (chunk size?), +0xC char[0x60] remote path
Message 23:  +5 u32 CRC-32 of the file (IEEE, same as zlib.crc32), +0x49 u8 1 (?)
Between the two the file bytes are streamed on the same TCP socket.
"""
from __future__ import annotations

import struct
import zlib

MAGIC = 0xB9D7
MSG_FILE_HEADER = 0x16
MSG_FILE_TRAILER = 0x17
PACKET_LEN = 0x80
PATH_LEN = 0x60


def file_header(tracker_id: int, size: int, remote_path: str, flag: bool = False) -> bytes:
    path = remote_path.encode()
    if len(path) >= PATH_LEN:
        raise ValueError("remote path too long (HTC's client rejects >= 0x60 bytes)")
    buf = bytearray(PACKET_LEN)
    struct.pack_into("<HHB", buf, 0, MAGIC, tracker_id, MSG_FILE_HEADER)
    struct.pack_into("<I", buf, 6, size)
    if flag:
        struct.pack_into("<H", buf, 0xA, 0x400)
    buf[0xC:0xC + len(path)] = path
    return bytes(buf)


def file_trailer(tracker_id: int, data: bytes) -> bytes:
    buf = bytearray(PACKET_LEN)
    struct.pack_into("<HHB", buf, 0, MAGIC, tracker_id, MSG_FILE_TRAILER)
    struct.pack_into("<I", buf, 5, zlib.crc32(data) & 0xFFFFFFFF)
    buf[0x49] = 1
    return bytes(buf)


def parse(packet: bytes) -> dict:
    if len(packet) != PACKET_LEN:
        raise ValueError("expected a 0x80-byte packet")
    magic, tid, mtype = struct.unpack_from("<HHB", packet, 0)
    if magic != MAGIC:
        raise ValueError("bad magic")
    out = {"tracker_id": tid, "type": mtype}
    if mtype == MSG_FILE_HEADER:
        out["size"] = struct.unpack_from("<I", packet, 6)[0]
        out["flag"] = struct.unpack_from("<H", packet, 0xA)[0] == 0x400
        out["path"] = packet[0xC:0xC + PATH_LEN].split(b"\0")[0].decode()
    elif mtype == MSG_FILE_TRAILER:
        out["crc32"] = struct.unpack_from("<I", packet, 5)[0]
    return out
