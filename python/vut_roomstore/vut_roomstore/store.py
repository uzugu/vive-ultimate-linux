from __future__ import annotations

import json
import math
import os
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAP_FILE_SUFFIXES = (".db",)  # the three SQLite files of a tracker map


class RoomError(Exception):
    pass


@dataclass
class Calibration:
    """T_steamvr_from_vut: translation in metres and a unit quaternion (x, y, z, w). Same meaning as the driver's file."""

    translation_m: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    def validate(self) -> None:
        values = (*self.translation_m, *self.rotation_xyzw)
        if len(values) != 7 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise RoomError("calibration needs seven finite numbers")
        if math.sqrt(sum(v * v for v in self.rotation_xyzw)) < 1e-6:
            raise RoomError("calibration rotation has zero length")

    def normalised(self) -> "Calibration":
        self.validate()
        norm = math.sqrt(sum(v * v for v in self.rotation_xyzw))
        return Calibration(tuple(self.translation_m), tuple(v / norm for v in self.rotation_xyzw))  # type: ignore[arg-type]


@dataclass
class Room:
    name: str
    slug: str
    created: int
    calibration: Calibration = field(default_factory=Calibration)
    host_serial: str | None = None
    last_map_creation_time: int | None = None  # unix seconds, from HTC's Calibration.json
    map_quality: list[int] = field(default_factory=list)
    map_files: list[str] = field(default_factory=list)  # names inside the room's private maps/ directory
    notes: str = ""

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["version"] = SCHEMA_VERSION
        return data

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Room":
        if data.get("version") != SCHEMA_VERSION:
            raise RoomError(f"unsupported room file version: {data.get('version')!r}")
        cal = data.get("calibration", {})
        calibration = Calibration(tuple(cal.get("translation_m", (0, 0, 0))), tuple(cal.get("rotation_xyzw", (0, 0, 0, 1))))  # type: ignore[arg-type]
        calibration.validate()
        return Room(
            name=str(data["name"]),
            slug=str(data["slug"]),
            created=int(data["created"]),
            calibration=calibration,
            host_serial=data.get("host_serial"),
            last_map_creation_time=data.get("last_map_creation_time"),
            map_quality=[int(v) for v in data.get("map_quality", [])],
            map_files=[str(v) for v in data.get("map_files", [])],
            notes=str(data.get("notes", "")),
        )


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise RoomError("room name must contain a letter or digit")
    return slug[:64]


def default_root() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(os.environ.get("ULTIMATE_TRACKER_ROOMS") or os.path.join(base, "ultimate-tracker", "rooms"))


def format_calibration_line(cal: Calibration) -> str:
    """The one-line file the SteamVR driver reads (docs/calibration.md)."""
    n = cal.normalised()
    return "CALIBRATION 1 " + " ".join(f"{v:.9f}" for v in (*n.translation_m, *n.rotation_xyzw))


def calibration_from_htc(text: str) -> tuple[Calibration, dict[str, Any]]:
    """Read HTC's Calibration.json (`transform.position`, `transform.rotation`, `map_setup`).

    HTC's `position` is taken as the translation of the same transform; that equivalence is an assumption until
    a live comparison agrees (docs/roomstore.md). Scale other than 1 is refused rather than silently dropped.
    """
    try:
        data = json.loads(text)
        transform = data["transform"]
        cal = Calibration(tuple(float(v) for v in transform["position"]), tuple(float(v) for v in transform["rotation"]))  # type: ignore[arg-type]
    except (ValueError, KeyError, TypeError) as exc:
        raise RoomError(f"not a usable Calibration.json: {exc}") from exc
    if len(cal.translation_m) != 3 or len(cal.rotation_xyzw) != 4:
        raise RoomError("transform needs a 3-vector position and a 4-vector rotation")
    if float(transform.get("scale", 1)) != 1.0:
        raise RoomError("calibration scale is not 1; refusing to drop it")
    cal = cal.normalised()
    setup = data.get("map_setup", {})
    meta = {
        "last_map_creation_time": setup.get("last_map_creation_time"),
        "map_quality": [int(v) for v in setup.get("map_quality", [])],
    }
    return cal, meta


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _inside_git_work_tree(path: Path) -> bool:
    for parent in [path.resolve(), *path.resolve().parents]:
        if (parent / ".git").exists():
            return True
    return False


class RoomStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()

    # -- rooms -------------------------------------------------------------------------------------------
    def _dir(self, slug: str) -> Path:
        return self.root / slug

    def list(self) -> list[Room]:
        if not self.root.is_dir():
            return []
        rooms = []
        for entry in sorted(self.root.iterdir()):
            if (entry / "room.json").is_file():
                rooms.append(self.get(entry.name))
        return rooms

    def get(self, name_or_slug: str) -> Room:
        slug = slugify(name_or_slug)
        path = self._dir(slug) / "room.json"
        if not path.is_file():
            raise RoomError(f"no room named {name_or_slug!r}")
        return Room.from_json(json.loads(path.read_text(encoding="utf-8")))

    def save(self, room: Room) -> None:
        directory = self._dir(room.slug)
        directory.mkdir(parents=True, exist_ok=True)
        _atomic_write(directory / "room.json", json.dumps(room.to_json(), indent=2, sort_keys=True) + "\n")

    def create(self, name: str, calibration: Calibration | None = None, notes: str = "") -> Room:
        slug = slugify(name)
        if (self._dir(slug) / "room.json").exists():
            raise RoomError(f"room {slug!r} already exists")
        room = Room(name=name.strip(), slug=slug, created=int(time.time()), notes=notes)
        if calibration is not None:
            room.calibration = calibration.normalised()
        self.save(room)
        return room

    def delete(self, name_or_slug: str) -> None:
        room = self.get(name_or_slug)
        if self.active_slug() == room.slug:
            (self.root / "active").unlink(missing_ok=True)
        shutil.rmtree(self._dir(room.slug))

    def set_calibration(self, name_or_slug: str, calibration: Calibration) -> Room:
        room = self.get(name_or_slug)
        room.calibration = calibration.normalised()
        self.save(room)
        return room

    def import_htc_calibration(self, name_or_slug: str, text: str) -> Room:
        cal, meta = calibration_from_htc(text)
        room = self.get(name_or_slug)
        room.calibration = cal
        room.last_map_creation_time = meta["last_map_creation_time"]
        room.map_quality = meta["map_quality"]
        self.save(room)
        return room

    # -- private map files -------------------------------------------------------------------------------
    def attach_map_files(self, name_or_slug: str, paths: list[Path | str]) -> Room:
        """Copy exported map databases into the room's private maps/ directory.

        Maps contain camera images of the owner's room: refuse if the store sits inside a git work tree, so they
        cannot be committed by accident.
        """
        if _inside_git_work_tree(self.root):
            raise RoomError("refusing to store map files inside a git work tree")
        room = self.get(name_or_slug)
        maps_dir = self._dir(room.slug) / "maps"
        maps_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(maps_dir, 0o700)
        for raw in paths:
            src = Path(raw)
            if src.suffix not in MAP_FILE_SUFFIXES or not src.is_file():
                raise RoomError(f"{src} is not a map database file (*.db)")
            shutil.copy2(src, maps_dir / src.name)
            if src.name not in room.map_files:
                room.map_files.append(src.name)
        self.save(room)
        return room

    # -- active room -------------------------------------------------------------------------------------
    def active_slug(self) -> str | None:
        path = self.root / "active"
        return path.read_text(encoding="utf-8").strip() or None if path.is_file() else None

    def use(self, name_or_slug: str, calibration_file: Path | str | None = None) -> Room:
        """Make a room active and, if given, rewrite the driver's calibration file so SteamVR switches live."""
        room = self.get(name_or_slug)
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.root / "active", room.slug + "\n")
        if calibration_file is not None:
            target = Path(calibration_file)
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, format_calibration_line(room.calibration) + "\n")
        return room
