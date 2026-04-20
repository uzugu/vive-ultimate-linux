#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <steamvr_bin_dir> <staged_driver_dir>" >&2
  echo "example: $0 \"$HOME/.steam/steam/steamapps/common/SteamVR/bin/linux64\" \"$PWD/steamvr_driver/build/stage/ultimate_tracker_linux\"" >&2
  exit 1
fi

steamvr_bin_dir="$1"
driver_dir="$2"

"$steamvr_bin_dir/vrpathreg" adddriver "$driver_dir"
"$steamvr_bin_dir/vrpathreg" show

