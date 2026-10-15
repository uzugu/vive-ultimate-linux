"""`vut map`: inspect and rehearse map building. Nothing here talks to a tracker.

  vut map plan                  print the commands a build would send, with how sure we are of each
  vut map replay <server.log>   replay a ViveTrackerServer log through the model (what the Map tab would have shown)
  vut map quality <Calibration.json>
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from vut_mapbuild import DEFAULT_COMMANDS, read_calibration_map_setup
from vut_mapbuild.replay import main as replay_main


def plan() -> int:
    c = DEFAULT_COMMANDS
    print("Commands a map build sends to the host tracker (none are sent by this command):")
    for name in ("start", "end", "cancel"):
        print(f"  {name:<7} {' then '.join(getattr(c, name))}   [{c.confidence[name]}]")
    print(f"  scan    {c.scan_event or '(not known yet: nothing is sent)'}   [{c.confidence['scan_event']}]")
    print("See docs/mapbuild.md for what is proven and what needs a hardware check.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if args else 2
    cmd, rest = args[0], args[1:]
    if cmd == "plan":
        return plan()
    if cmd == "replay":
        return replay_main(rest)
    if cmd == "quality":
        parser = argparse.ArgumentParser(prog="vut map quality")
        parser.add_argument("calibration_json")
        ns = parser.parse_args(rest)
        try:
            created, q = read_calibration_map_setup(ns.calibration_json)
        except (OSError, ValueError) as exc:
            print(f"cannot read {ns.calibration_json}: {exc}", file=sys.stderr)
            return 1
        print(f"verdict: {q.verdict}; values: {list(q.values)}; weak sides: {[i + 1 for i in q.weak_sides]}; created (unix): {created}")
        return 0
    print(f"vut map: unknown subcommand '{cmd}'\n{__doc__}", file=sys.stderr)
    return 2
