from __future__ import annotations

import argparse
import time
from dataclasses import dataclass

from .models import TrackerPose
from .socket_client import PoseStreamClient


@dataclass(slots=True)
class TrackerStats:
    last_pose: TrackerPose
    sample_count: int
    first_seen_ns: int
    last_seen_ns: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show a live summary of trackers coming from the daemon socket.")
    parser.add_argument("--socket-path", default="/tmp/ultimate-tracker-linux.sock")
    parser.add_argument("--refresh-every", type=int, default=30, help="Print a summary every N received samples.")
    return parser.parse_args()


def print_summary(stats: dict[str, TrackerStats]) -> None:
    print("---- tracker summary ----")
    if not stats:
        print("no trackers seen yet")
        return

    now_ns = time.monotonic_ns()
    for serial in sorted(stats):
        item = stats[serial]
        age_ms = (now_ns - item.last_seen_ns) / 1_000_000.0
        span_s = max((item.last_seen_ns - item.first_seen_ns) / 1_000_000_000.0, 1e-9)
        rate_hz = item.sample_count / span_s
        px, py, pz = item.last_pose.position_m
        print(
            f"{serial}: status={item.last_pose.status} samples={item.sample_count} "
            f"raw={item.last_pose.tracking_code} label={item.last_pose.tracking_label} "
            f"rate_hz={rate_hz:.2f} age_ms={age_ms:.1f} "
            f"pos=({px:.4f},{py:.4f},{pz:.4f})"
        )


def main() -> None:
    args = parse_args()
    stats: dict[str, TrackerStats] = {}
    sample_counter = 0

    with PoseStreamClient(args.socket_path) as client:
        for pose in client.iter_poses():
            existing = stats.get(pose.serial)
            if existing is None:
                stats[pose.serial] = TrackerStats(
                    last_pose=pose,
                    sample_count=1,
                    first_seen_ns=pose.timestamp_ns,
                    last_seen_ns=pose.timestamp_ns,
                )
            else:
                existing.last_pose = pose
                existing.sample_count += 1
                existing.last_seen_ns = pose.timestamp_ns

            sample_counter += 1
            if sample_counter % args.refresh_every == 0:
                print_summary(stats)


if __name__ == "__main__":
    main()
