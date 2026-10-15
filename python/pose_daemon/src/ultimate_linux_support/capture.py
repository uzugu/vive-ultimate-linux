from __future__ import annotations

import argparse
import json
import pathlib
import time

from .protocol import pose_to_json_dict
from .endpoint import default_endpoint_spec
from .socket_client import PoseStreamClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture raw tracker-space poses from the daemon socket to JSONL.")
    parser.add_argument("--socket-path", default=default_endpoint_spec())
    parser.add_argument("--output", required=True, help="Output JSONL file path.")
    parser.add_argument("--serial", default=None, help="Only record a specific tracker serial.")
    parser.add_argument("--duration", type=float, default=10.0, help="Capture duration in seconds.")
    parser.add_argument(
        "--label",
        default="unlabeled",
        help="Free-form label stored alongside each sample. Useful for later calibration or axis analysis sessions.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = pathlib.Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + args.duration
    written = 0

    with output_path.open("w", encoding="utf-8") as handle:
        with PoseStreamClient(args.socket_path) as client:
            for pose in client.iter_poses():
                if args.serial and pose.serial != args.serial:
                    continue

                record = {
                    "label": args.label,
                    "captured_at_ns": time.monotonic_ns(),
                    "pose": pose_to_json_dict(pose),
                }
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                written += 1

                if time.monotonic() >= deadline:
                    break

    print(f"wrote {written} samples to {output_path}")


if __name__ == "__main__":
    main()

