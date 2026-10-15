"""Read text files the way HTC writes them: its tracker-server logs are UTF-16 LE with a BOM (found on a real PC)."""

from __future__ import annotations

from pathlib import Path


def detect_encoding(head: bytes) -> str:
    """Pick the encoding from the first bytes: UTF-16 or UTF-8 BOM, else UTF-8."""
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"  # the codec consumes the BOM and picks the byte order
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "utf-8"


def read_lines(path: str | Path) -> list[str]:
    raw = Path(path).read_bytes()
    return raw.decode(detect_encoding(raw[:4]), errors="replace").splitlines()


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    return raw.decode(detect_encoding(raw[:4]), errors="replace")
