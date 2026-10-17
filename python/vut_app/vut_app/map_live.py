"""`vut map live`: start and finish one map build on the host tracker through the dongle.

Open loop on purpose: it sends the capture-verified commands and waits for the person at the keyboard to say when each scan
stage is reached; it reads nothing back (the map-status carrier in the dongle reports is not decoded yet). Watch the
tracker's light and VIVE-style progress yourself. This overwrites the map on every tracker, so it asks first.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence

from vut_dongle import DongleUnavailable, feature_writer, open_dongle
from vut_mapbuild import DEFAULT_COMMANDS, MapError
from vut_mapbuild.transport import DongleLink

STAGE_PROMPTS = (
    "Hold the host tracker and start walking the room slowly. Enter when the first area is covered (scan stage 0)",
    "Enter when the low scan of the room is done (scan stage 1)",
    "Enter when the high scan / walls are done (scan stage 2)",
    "Enter to run the final pass (scan stage 3)",
)


def run(link, tracker_slot: int, country: str, ask: Callable[[str], str], say: Callable[[str], None]) -> int:
    table = DEFAULT_COMMANDS
    try:
        start = table.start_commands(country)
    except ValueError as exc:
        raise MapError(str(exc)) from exc
    if ask("This replaces the map on ALL trackers. Type YES to start: ").strip() != "YES":
        say("not started")
        return 1
    for command in start:
        link.send(tracker_slot, command)
        say(f"sent {command}")
    for stage, prompt in enumerate(STAGE_PROMPTS):
        ask(prompt + ": ")
        link.send(tracker_slot, table.scan_events[stage])
        say(f"sent {table.scan_events[stage]}")
    ask("Enter to save the map (End map creation): ")
    for command in table.end:
        link.send(tracker_slot, command)
        say(f"sent {command}")
    say("done. The host saves in about 6 s, the others copy it over Wi-Fi in about 20 s. Check each tracker's map status.")
    return 0


def main(argv: Sequence[str] | None = None, *, hid_module=None, ask=input, say=print) -> int:
    parser = argparse.ArgumentParser(prog="vut map live", description=__doc__)
    parser.add_argument("--tracker-id", required=True, help="the host tracker's 5-byte id as 10 hex digits")
    parser.add_argument("--country", required=True, help="Wi-Fi country code, e.g. DE")
    ns = parser.parse_args(argv)
    try:
        tracker_id = bytes.fromhex(ns.tracker_id)
    except ValueError:
        print("--tracker-id must be hex", file=sys.stderr)
        return 2
    if len(tracker_id) != 5:
        print("--tracker-id must be 5 bytes (10 hex digits)", file=sys.stderr)
        return 2
    try:
        device = open_dongle(hid_module)
    except DongleUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1
    link = DongleLink(feature_writer(device), {0: tracker_id})
    try:
        return run(link, 0, ns.country, ask, say)
    except (MapError, OSError) as exc:
        print(f"stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        close = getattr(device, "close", None)
        if close:
            close()
