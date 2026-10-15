#!/usr/bin/env bash
# Build the single-file `vut` executable for the current OS/architecture into dist/.
# Needs: pip install pyinstaller -e python/pose_daemon -e python/vut_roomstore -e python/vut_app
set -euo pipefail
cd "$(dirname "$0")/.."
pyinstaller packaging/vut_entry.py --onefile --clean --noconfirm --name vut \
    --paths python/vut_app --paths python/vut_roomstore --paths python/pose_daemon/src \
    --distpath dist --workpath build/pyinstaller --specpath build/pyinstaller
