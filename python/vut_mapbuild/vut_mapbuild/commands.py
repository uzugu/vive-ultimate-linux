"""ASCII commands that put the host tracker into map-building mode and take it out again.

Source: docs/re/vivehub-windows-map-transfer.md section 1 and docs/mapbuild.md. Confidence per command is in
`CommandTable.confidence`. Nothing here is sent anywhere: a `Link` (session.py) carries the strings, and the framing
that carries them over the dongle's RF link is not decoded yet (docs/mapbuild.md, "Open").
"""

from __future__ import annotations

from dataclasses import dataclass, field

# HTC refuses dongle-path commands longer than this ("CMD EXCEEDS MAXIMUM LENGTH").
DONGLE_MAX_COMMAND = 15

CODE = "code"  # read from HTC's instructions
STRING = "string"  # string seen in a binary; its role is inferred from the name
GUESS = "guess"


@dataclass(frozen=True)
class CommandTable:
    """What to send for each wizard action. Replace a field to test another hypothesis on hardware."""

    # `TrackerOnDongle::CreateMap`: FW2, set Wi-Fi country code (separate call), ATM20.
    start: tuple[str, ...] = ("FW2", "ATM20")
    # `EndCreateMap` has its own command that is not decoded. "ALE" is listed as "end map" in the Linux tracker_server.
    end: tuple[str, ...] = ("ALE",)
    # The wizard's cancel handler id is uncertain (driver-pipes.md section 5); ending without keeping the result is a guess.
    cancel: tuple[str, ...] = ("ALE",)
    # `SendMapScanEvent` is a separate function that is not decoded; None means "do not send anything".
    scan_event: str | None = None
    confidence: dict[str, str] = field(
        default_factory=lambda: {"start": CODE, "end": STRING, "cancel": GUESS, "scan_event": GUESS}
    )

    def validate(self) -> None:
        for name in ("start", "end", "cancel"):
            for command in getattr(self, name):
                check_command(command)


def check_command(command: str) -> str:
    if not command.isascii() or not command.isprintable() or not command:
        raise ValueError(f"not a printable ASCII command: {command!r}")
    if len(command) > DONGLE_MAX_COMMAND:
        raise ValueError(f"command longer than {DONGLE_MAX_COMMAND} characters: {command!r}")
    return command


def identify(on: bool = True) -> str:
    """Wizard "Identify tracker" (blink the LED); seen in the driver log as `(AHT1,1,1,1)` every 3 s before a scan."""
    return "AHT1,1,1,1" if on else "AHT0,0,0,0"  # the off form is a guess


DEFAULT_COMMANDS = CommandTable()
