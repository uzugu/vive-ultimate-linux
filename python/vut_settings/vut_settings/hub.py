"""JSON commands of the Hub-to-server channel (docs/re/settings-power.md section 2, pairing notes section 3.2).

Lets our own frontend or a test double speak the same vocabulary as VIVE Hub. Builders only; nothing is sent.
Request numbers come from the server's jump table; the unmapped ones (25, 27) are left out on purpose.
"""

from __future__ import annotations

import json
import secrets
from typing import Any

CMD_POWER_OFF_DEVICE = 13
CMD_PAIR = 215  # HTC's pair/unpair request: CmdKey, DeviceIndex, IsPair (pairing notes 3.2)
CMD_FACTORY_RESET_DEVICE = 20
CMD_POWER_OFF_ALL = 21
CMD_SET_CAMERA_FRAME_RATE = 22
CMD_SET_AUTO_SLEEP = 24

# Response CmdType for each request, from the settings notes.
RESPONSE_TYPE = {
    CMD_POWER_OFF_DEVICE: 213,
    CMD_FACTORY_RESET_DEVICE: 220,
    CMD_POWER_OFF_ALL: 221,
    CMD_SET_CAMERA_FRAME_RATE: 222,
    CMD_SET_AUTO_SLEEP: 224,
}

# DeviceIndex values with a special meaning for pairing (pairing notes 3.2).
DEVICE_PAIR_ALL_EMPTY = 0xFE
DEVICE_UNPAIR_ALL = 0xFD

_MAX_SLOT = 4


def new_cmd_key() -> str:
    """Correlation string echoed back in the response."""
    return secrets.token_hex(8)


def request(cmd_type: int, cmd_key: str | None = None, **fields: Any) -> str:
    body: dict[str, Any] = {"CmdType": cmd_type, "CmdKey": cmd_key or new_cmd_key()}
    body.update(fields)
    return json.dumps(body, separators=(",", ":"))


def _slot(device_index: int) -> int:
    if not 0 <= device_index <= _MAX_SLOT:
        raise ValueError(f"DeviceIndex must be 0..{_MAX_SLOT}")
    return device_index


def power_off_device(device_index: int, cmd_key: str | None = None) -> str:
    return request(CMD_POWER_OFF_DEVICE, cmd_key, DeviceIndex=_slot(device_index))


def power_off_all(cmd_key: str | None = None) -> str:
    return request(CMD_POWER_OFF_ALL, cmd_key)


def set_camera_frame_rate(fps: int, cmd_key: str | None = None) -> str:
    if fps <= 0:
        raise ValueError("fps must be positive")
    return request(CMD_SET_CAMERA_FRAME_RATE, cmd_key, CameraFrameRate=fps)


def set_auto_sleep(enabled: bool, timeout: int, cmd_key: str | None = None) -> str:
    if timeout < 0:
        raise ValueError("timeout must be >= 0")
    return request(CMD_SET_AUTO_SLEEP, cmd_key, IsAutoSleep=bool(enabled), AutoSleepTimeout=timeout)


def pair(device_index: int, is_pair: bool, cmd_key: str | None = None) -> str:
    """Pair or unpair one slot (0..4), or use DEVICE_PAIR_ALL_EMPTY / DEVICE_UNPAIR_ALL."""
    if device_index not in (DEVICE_PAIR_ALL_EMPTY, DEVICE_UNPAIR_ALL):
        _slot(device_index)
    return request(CMD_PAIR, cmd_key, DeviceIndex=device_index, IsPair=int(is_pair))


def factory_reset_device(device_index: int, cmd_key: str | None = None) -> str:
    """Destructive; the notes say to test on a spare tracker last. Builder only."""
    return request(CMD_FACTORY_RESET_DEVICE, cmd_key, DeviceIndex=_slot(device_index))


def parse_response(text: str, expected_cmd_key: str | None = None) -> dict[str, Any]:
    """Parse a server reply. Raises ValueError if it is not a JSON object with CmdType, or the CmdKey differs."""
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not JSON: {exc}") from exc
    if not isinstance(body, dict) or not isinstance(body.get("CmdType"), int):
        raise ValueError("reply has no integer CmdType")
    if expected_cmd_key is not None and body.get("CmdKey") != expected_cmd_key:
        raise ValueError("CmdKey does not match the request")
    return body


def succeeded(response: dict[str, Any]) -> bool:
    """`Result` 0 means ok."""
    return response.get("Result") == 0
