"""Reader/writer for the server's Config.ini, which is JSON despite the name.

Layout and defaults from docs/re/settings-power.md section 5.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass
class ServerConfig:
    log_level: int = 2
    camera_frame_rate: int = 60
    ignore_force_update: bool = False
    is_auto_sleep: bool = False
    auto_sleep_timeout: int = 0

    @property
    def effective_auto_sleep(self) -> int:
        """What the server sends to trackers: the timeout, or 0 when auto-sleep is off."""
        return self.auto_sleep_timeout if self.is_auto_sleep else 0


def load_config(text: str) -> ServerConfig:
    server = json.loads(text).get("server", {})
    known = {k: v for k, v in server.items() if k in ServerConfig.__dataclass_fields__}
    return ServerConfig(**known)


def dump_config(cfg: ServerConfig) -> str:
    return json.dumps({"server": asdict(cfg)}, indent=2) + "\n"
