from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .protocol import pose_to_json_line
from .socket_client import PoseStreamClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print parsed pose samples from the local daemon socket.")
    parser.add_argument("--socket-path", default="/tmp/ultimate-tracker-linux.sock")
    parser.add_argument("--serial", default=None, help="Only print a specific tracker serial.")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N matching samples. 0 means no limit.")
    parser.add_argument("--json", action="store_true", help="Print JSON lines instead of a text summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    emitted = 0

    with PoseStreamClient(args.socket_path) as client:
        for pose in client.iter_poses():
            if args.serial and pose.serial != args.serial:
                continue

            if args.json:
                print(pose_to_json_line(pose))
            else:
                stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
                px, py, pz = pose.position_m
                qx, qy, qz, qw = pose.orientation_xyzw
                tracking = ""
                if pose.tracking_code is not None:
                    tracking = f" raw={pose.tracking_code}"
                if pose.tracking_label is not None:
                    tracking += f" label={pose.tracking_label}"
                print(
                    f"[{stamp}] serial={pose.serial} idx={pose.tracker_index} status={pose.status} "
                    f"{tracking.strip()} "
                    f"pos=({px:.4f},{py:.4f},{pz:.4f}) quat=({qx:.4f},{qy:.4f},{qz:.4f},{qw:.4f}) "
                    f"ts_ns={pose.timestamp_ns}"
                )

            emitted += 1
            if args.limit > 0 and emitted >= args.limit:
                break


if __name__ == "__main__":
    main()
