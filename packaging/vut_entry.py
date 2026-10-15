"""PyInstaller entry point: `pyinstaller packaging/vut_entry.py --onefile --name vut`."""

import sys

from vut_app.cli import main

if __name__ == "__main__":
    sys.exit(main())
