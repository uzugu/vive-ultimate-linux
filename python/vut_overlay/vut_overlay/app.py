from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from .client import RoomClient
from .panel import HEIGHT, WIDTH, Panel


def default_socket() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "ultimate-tracker-rooms.sock"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SteamVR dashboard overlay for room switching")
    ap.add_argument("--socket", type=Path, default=default_socket())
    args = ap.parse_args(argv)

    import openvr  # needs `pip install vut-overlay[steamvr]` and a running SteamVR

    openvr.init(openvr.VRApplication_Overlay)
    vr = openvr.IVROverlay()
    handle, _thumb = vr.createDashboardOverlay("ultimate-tracker.rooms", "Rooms")
    vr.setOverlayWidthInMeters(handle, 2.0)
    vr.setOverlayInputMethod(handle, openvr.VROverlayInputMethod_Mouse)
    panel = Panel(RoomClient(args.socket))
    event = openvr.VREvent_t()
    try:
        while True:
            while vr.pollNextOverlayEvent(handle, event):
                if event.eventType == openvr.VREvent_MouseButtonDown:
                    # SteamVR gives mouse coordinates with the origin at the bottom left, in [0, 1] of the panel
                    # unless set otherwise; the panel's pixels start at the top left.
                    m = event.data.mouse
                    panel.click(int(m.x * WIDTH), int(HEIGHT - m.y * HEIGHT))
                elif event.eventType == openvr.VREvent_OverlayShown:
                    panel.refresh()
            img = panel.render().tobytes()
            vr.setOverlayRaw(handle, img, WIDTH, HEIGHT, 4)
            time.sleep(0.05)
    finally:
        openvr.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
