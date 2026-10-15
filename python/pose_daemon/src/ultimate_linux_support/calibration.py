"""Tracker-space to SteamVR-space calibration (see docs/calibration.md).

The driver reads one line, ``CALIBRATION 1 tx ty tz qx qy qz qw``, from the calibration file and applies
``p' = R p + t`` to every pose. This module fits a yaw-about-up-axis plus translation from matched
positions (tracker position, reference position) and writes that line. Both spaces are Y-up.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections.abc import Sequence

Vec3 = tuple[float, float, float]


def fit_yaw_translation(pairs: Sequence[tuple[Vec3, Vec3]]) -> tuple[Vec3, float]:
    """Least-squares yaw (radians, about +Y) and translation mapping source points onto target points.

    ``pairs`` is a sequence of ``(source, target)``. Needs at least two points that differ horizontally.
    """
    if len(pairs) < 2:
        raise ValueError("need at least two point pairs")
    n = len(pairs)
    src_mean = [sum(p[0][i] for p in pairs) / n for i in range(3)]
    dst_mean = [sum(p[1][i] for p in pairs) / n for i in range(3)]

    dot = cross = spread = 0.0
    for src, dst in pairs:
        ax, az = src[0] - src_mean[0], src[2] - src_mean[2]
        bx, bz = dst[0] - dst_mean[0], dst[2] - dst_mean[2]
        dot += bx * ax + bz * az
        cross += bx * az - bz * ax
        spread += ax * ax + az * az
    if spread < 1e-9:
        raise ValueError("source points do not differ horizontally; move the tracker around")

    yaw = math.atan2(cross, dot)
    c, s = math.cos(yaw), math.sin(yaw)
    rx = src_mean[0] * c + src_mean[2] * s
    rz = -src_mean[0] * s + src_mean[2] * c
    translation = (dst_mean[0] - rx, dst_mean[1] - src_mean[1], dst_mean[2] - rz)
    return translation, yaw


def format_calibration(translation: Vec3, yaw_rad: float) -> str:
    half = yaw_rad / 2.0
    qx, qy, qz, qw = 0.0, math.sin(half), 0.0, math.cos(half)
    values = (*translation, qx, qy, qz, qw)
    return "CALIBRATION 1 " + " ".join(f"{v:.9f}" for v in values)


def default_path() -> str:
    env = os.environ.get("ULTIMATE_TRACKER_CALIBRATION")
    if env:
        return env
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base and sys.platform == "win32":
        base = os.environ.get("APPDATA")
    base = base or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "ultimate-tracker", "calibration.txt")


def _parse_vec(text: str) -> Vec3:
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError(f"expected x,y,z, got {text!r}")
    return (parts[0], parts[1], parts[2])


def _parse_pair(text: str) -> tuple[Vec3, Vec3]:
    left, sep, right = text.partition(":")
    if not sep:
        raise argparse.ArgumentTypeError("expected tracker_x,y,z:reference_x,y,z")
    return _parse_vec(left), _parse_vec(right)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the driver calibration file.")
    parser.add_argument("--output", default=default_path())
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pair", action="append", type=_parse_pair, metavar="TRACKER:REFERENCE",
                       help="matched positions as x,y,z:x,y,z; give at least two (repeatable)")
    group.add_argument("--manual", action="store_true", help="use --yaw-deg and --offset")
    group.add_argument("--identity", action="store_true", help="write the identity calibration")
    parser.add_argument("--yaw-deg", type=float, default=0.0)
    parser.add_argument("--offset", type=_parse_vec, default=(0.0, 0.0, 0.0))
    args = parser.parse_args(argv)

    if args.pair:
        translation, yaw = fit_yaw_translation(args.pair)
    elif args.manual:
        translation, yaw = args.offset, math.radians(args.yaw_deg)
    else:
        translation, yaw = (0.0, 0.0, 0.0), 0.0

    line = format_calibration(translation, yaw)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    tmp = args.output + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(line + "\n")
    os.replace(tmp, args.output)  # atomic, so the driver never sees a half-written file
    print(f"wrote {args.output}: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
