from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 640, 480
ROW_H = 56
LIST_TOP = 70
MAX_ROWS = 6


class Service(Protocol):
    def call(self, **request: Any) -> dict[str, Any]: ...


@dataclass
class Button:
    label: str
    box: tuple[int, int, int, int]  # x0, y0, x1, y1
    action: str
    room: str | None = None


class Panel:
    """Pure model of the overlay: rooms from the service, a save button, a status line, hit-testing and drawing.

    Coordinates are pixels with (0, 0) top left. Pointer events from SteamVR are mapped to this space by `app`.
    """

    def __init__(self, service: Service) -> None:
        self.service = service
        self.rooms: list[dict[str, Any]] = []
        self.status = "Ready"
        self.buttons: list[Button] = []
        self.refresh()

    def refresh(self) -> None:
        reply = self.service.call(op="list")
        if reply.get("ok"):
            self.rooms = reply["rooms"][:MAX_ROWS]
        else:
            self.rooms, self.status = [], reply.get("error", "error")
        self._layout()

    def _layout(self) -> None:
        self.buttons = []
        for i, room in enumerate(self.rooms):
            y = LIST_TOP + i * ROW_H
            if room["has_map"] and not room["active"]:
                self.buttons.append(Button("Load", (WIDTH - 220, y + 8, WIDTH - 130, y + ROW_H - 8), "load", room["slug"]))
            self.buttons.append(Button("Save", (WIDTH - 120, y + 8, WIDTH - 20, y + ROW_H - 8), "save", room["slug"]))
        self.buttons.append(Button("Save current as new room", (20, HEIGHT - 60, 300, HEIGHT - 16), "new"))

    def click(self, x: int, y: int) -> None:
        for b in self.buttons:
            if b.box[0] <= x < b.box[2] and b.box[1] <= y < b.box[3]:
                self._do(b)
                return

    def _do(self, b: Button) -> None:
        if b.action == "new":
            name = f"Room {len(self.rooms) + 1}"
            reply = self.service.call(op="save", name=name)
        else:
            reply = self.service.call(op=b.action, name=b.room)
        verb = {"load": "Loaded", "save": "Saved", "new": "Saved"}[b.action]
        self.status = f"{verb} {reply['room']['name']}" if reply.get("ok") else f"Failed: {reply.get('error')}"
        self.refresh()

    def render(self) -> Image.Image:
        img = Image.new("RGBA", (WIDTH, HEIGHT), (24, 26, 32, 255))
        d = ImageDraw.Draw(img)
        d.text((20, 20), "Ultimate Tracker rooms", fill=(255, 255, 255, 255))
        for i, room in enumerate(self.rooms):
            y = LIST_TOP + i * ROW_H
            tag = "  (active)" if room["active"] else ("" if room["has_map"] else "  (no map)")
            d.text((20, y + 20), room["name"] + tag, fill=(220, 220, 230, 255))
        for b in self.buttons:
            d.rectangle(b.box, fill=(60, 90, 160, 255))
            d.text((b.box[0] + 10, b.box[1] + 14), b.label, fill=(255, 255, 255, 255))
        d.text((320, HEIGHT - 44), self.status[:40], fill=(180, 180, 190, 255))
        return img
