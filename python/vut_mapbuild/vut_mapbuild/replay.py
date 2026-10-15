"""Replay a HTC tracker-server log through the state machine and print the timeline (no hardware needed)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence

from .records import parse_log_line
from .session import MapBuildSession, Phase


def replay(lines: Iterable[str]) -> tuple[MapBuildSession, list[tuple[float, Phase, str]]]:
    """Feed every line; return the session and its phase changes as (seconds since first event, phase, message)."""
    session = MapBuildSession()
    changes: list[tuple[float, Phase, str]] = []
    first: float | None = None
    last = Phase.IDLE
    for line in lines:
        event = parse_log_line(line)
        if event is None:
            continue
        first = event.t if first is None else first
        session.feed(event)
        if session.phase is not last:
            last = session.phase
            changes.append((event.t - first, session.phase, session.message))
    return session, changes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vut map replay", description="Replay a ViveTrackerServer log through the map-build model.")
    parser.add_argument("log", help="path to a ViveTrackerServer log")
    args = parser.parse_args(argv)
    with open(args.log, encoding="utf-8", errors="replace") as f:
        session, changes = replay(f)
    for t, phase, message in changes:
        print(f"{t:7.1f}s  {phase.value:<9} {message}")
    p = session.progress()
    print(f"final: {p.phase.value}; scan stage {p.scan_stage}; too-fast warnings {p.warnings}")
    return 0 if p.phase is Phase.DONE else 1


if __name__ == "__main__":
    sys.exit(main())
