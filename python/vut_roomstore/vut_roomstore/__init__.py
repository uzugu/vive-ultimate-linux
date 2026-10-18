"""Room store: one directory per room with its calibration and metadata (docs/roomstore.md).

No hardware access. Map files are only ever copied into the owner's own store directory, never into a git work tree.
"""

from .store import (
    Calibration,
    Room,
    RoomError,
    RoomStore,
    calibration_from_htc,
    default_root,
    format_calibration_line,
    slugify,
)
from .service import FakeTransport, RoomService, Transport, TransportError, serve

__all__ = [
    "FakeTransport",
    "RoomService",
    "Transport",
    "TransportError",
    "serve",
    "Calibration",
    "Room",
    "RoomError",
    "RoomStore",
    "calibration_from_htc",
    "default_root",
    "format_calibration_line",
    "slugify",
]
