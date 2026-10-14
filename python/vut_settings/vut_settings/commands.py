"""Command frames for a Wi-Fi connected tracker.

Derived from static analysis of the Windows tracker library, see docs/re/settings-power.md section 3.
Unconfirmed on hardware: treat every command here as a hypothesis until a capture agrees.
"""

FRAME_SIZE = 128
CMD_FRAME = 0x01
# The dongle path refuses commands longer than this.
DONGLE_MAX_COMMAND = 15


def frame(command: str) -> bytes:
    """Wrap an ASCII command: 0x01, length, command, zero padding to 128 bytes."""
    raw = command.encode("ascii")
    if len(raw) > FRAME_SIZE - 2:
        raise ValueError("command too long for one frame")
    return (bytes([CMD_FRAME, len(raw)]) + raw).ljust(FRAME_SIZE, b"\0")


def auto_sleep(timeout: int) -> bytes:
    """Auto-sleep; 0 disables it. Unit is probably minutes (unconfirmed)."""
    if timeout < 0:
        raise ValueError("timeout must be >= 0")
    return frame(f"pAS_TS{timeout}")


def camera_frame_rate(fps: int) -> bytes:
    if fps <= 0:
        raise ValueError("fps must be positive")
    return frame(f"ACF{fps}")


def power_off() -> bytes:
    return frame("APF")


def reboot() -> bytes:
    return frame("APR")
