import sys, zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "tools"))
import vut_filetransfer as ft


def test_header_roundtrip():
    p = ft.file_header(3, 1234, "/sdcard/autosave0", flag=True)
    assert len(p) == 0x80 and p[:2] == b"\xd7\xb9" and p[4] == 0x16
    assert ft.parse(p) == {"tracker_id": 3, "type": 0x16, "size": 1234, "flag": True, "path": "/sdcard/autosave0"}


def test_trailer_crc_matches_zlib():
    data = b"example map bytes" * 100
    p = ft.file_trailer(3, data)
    assert p[4] == 0x17 and p[0x49] == 1
    assert ft.parse(p)["crc32"] == zlib.crc32(data)


def test_path_limit():
    try:
        ft.file_header(0, 1, "x" * 0x60)
    except ValueError:
        return
    raise AssertionError("expected ValueError")
