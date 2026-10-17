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
CAPTURE = "capture"  # seen in a USB capture of HTC's own software doing it (2026-10-17)


@dataclass(frozen=True)
class CommandTable:
    """What to send for each wizard action. Replace a field to test another hypothesis on hardware."""

    # `TrackerOnDongle::CreateMap`: FW2, Wi-Fi country code (`Wc` + two letters), ATM20. Capture-verified 2026-10-17.
    start: tuple[str, ...] = ("FW2", "Wc{country}", "ATM20")
    # End map creation. Capture-verified 2026-10-17 (host reported has map about 5 s later).
    end: tuple[str, ...] = ("ALE",)
    # HTC's server "cancel map creation" only logs and replies OK; it sends nothing to the dongle (read from its code,
    # 2026-10-17). So there is no HTC cancel to copy. `ALE` would SAVE the map, so it must not be used here. A real
    # cancel for our app (for example switching the host back to normal mode) is untested and needs hardware.
    cancel: tuple[str, ...] = ()
    # One command per scan stage 0..3 (wizard "Map scan notification, type N"). Capture-verified 2026-10-17.
    scan_events: tuple[str, ...] = ("pMS_SC", "pMS_ILA", "pMS_IHA", "pMS_ES")
    confidence: dict[str, str] = field(
        default_factory=lambda: {"start": CAPTURE, "end": CAPTURE, "cancel": CODE, "scan_events": CAPTURE}
    )

    def validate(self) -> None:
        for name in ("start", "end", "cancel"):
            for command in getattr(self, name):
                check_command(command.format(country="US"))
        for command in self.scan_events:
            check_command(command)

    def start_commands(self, country: str) -> tuple[str, ...]:
        """The start sequence with the Wi-Fi country code filled in (two letters, e.g. DE)."""
        if "{country}" in "".join(self.start) and not (len(country) == 2 and country.isascii() and country.isalpha()):
            raise ValueError("a two-letter Wi-Fi country code is needed to start a map build")
        return tuple(check_command(c.format(country=country.upper())) for c in self.start)


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
