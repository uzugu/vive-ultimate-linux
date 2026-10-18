from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any


class RoomClient:
    """Talks to the room service (vut_roomstore.service.serve): one JSON line out, one back."""

    def __init__(self, socket_path: Path | str, timeout: float = 120.0) -> None:
        self.socket_path = str(socket_path)
        self.timeout = timeout  # a map transfer can take a while

    def call(self, **request: Any) -> dict[str, Any]:
        try:
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(self.timeout)
                s.connect(self.socket_path)
                s.sendall((json.dumps(request) + "\n").encode())
                line = s.makefile().readline()
            return json.loads(line)
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": f"room service unreachable: {exc}"}
