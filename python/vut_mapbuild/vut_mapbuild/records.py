"""Parse the lines HTC's tracker server writes while a map is built (ViveTrackerServer log).

The same record shapes are what our own app has to produce from the dongle indications, so the log doubles as a replayable
test input: `parse_log_line` turns one log line into an event, and `session.MapBuildSession` consumes events.
Field meanings are inferred from when they change (docs/mapbuild.md section 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

# tracking status values seen live (docs/re/vivehub-windows-live-findings.md section 5)
TRACKING_OFFLINE = 0
TRACKING_STEADY = 2
TRACKING_HOST_STARTED = 3
TRACKING_CONNECTED = 5
TRACKING_CLIENT_CONNECTING = 6
TRACKING_HOST_SCANNING = 7  # also seen on a client while it receives the map

# map status values: host goes 1, 0, 2, 10, 3 while a scan starts; 6 is the steady state afterwards
MAP_STATUS_STEADY = 6

_TS = r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)"


@dataclass(frozen=True)
class TrackerRecord:
    """One `DeviceStatusToVHServer` line."""

    t: float
    slot: int
    connected: bool
    tracking_status: int
    battery_percent: int
    map_id: int
    map_status: int
    has_map: bool
    map_state: int
    is_host: bool
    error_code: int


@dataclass(frozen=True)
class ServiceStatus:
    t: float
    scan_status: int
    cali_status: int
    device_count: int


@dataclass(frozen=True)
class WizardCommand:
    """A command the setup wizard sent the server: 'start', 'end' or 'scan' (with `stage`)."""

    t: float
    kind: str
    stage: int | None = None


@dataclass(frozen=True)
class TrackerNotice:
    """Tracker-side notices: 'refine', 'overspeed', 'lost', 'reloc'."""

    t: float
    kind: str
    slot: int | None = None


Event = TrackerRecord | ServiceStatus | WizardCommand | TrackerNotice


def _epoch(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f").timestamp()


def _ints(line: str, pattern: str) -> dict[str, int]:
    return {m.group(1).strip(): int(m.group(2)) for m in re.finditer(pattern, line)}


def parse_log_line(line: str) -> Event | None:
    """One server log line to an event, or None for lines that do not matter for map building."""
    m = re.match(_TS, line)
    if not m:
        return None
    t = _epoch(m.group(1))
    if "DeviceStatusToVHServer" in line:
        f = _ints(line, r"([A-Za-z][A-Za-z ]*?): (-?\d+)")
        try:
            return TrackerRecord(
                t=t,
                slot=f["device index"],
                connected=bool(f["connected"]),
                tracking_status=f["tracking status"],
                battery_percent=f["percentage"],
                map_id=f["map ID"],
                map_status=f["map status"],
                has_map=bool(f["has map"]),
                map_state=f["map state"],
                is_host=bool(f["is host"]),
                error_code=f["error code"],
            )
        except KeyError:
            return None
    if "ServiceStatusToVHServer" in line:
        f = _ints(line, r"([A-Za-z][A-Za-z ]*?): (-?\d+)")
        try:
            return ServiceStatus(t, f["scan status"], f["cali status"], f["device counts"])
        except KeyError:
            return None
    if "Start map creation" in line:
        return WizardCommand(t, "start")
    if "End map creation" in line:
        return WizardCommand(t, "end")
    scan = re.search(r"Map scan notifcation, type: (\d+)", line)  # sic: HTC's spelling
    if scan:
        return WizardCommand(t, "scan", int(scan.group(1)))
    if "Refine event received" in line and "WaitForMapRefineNotification" not in line:
        return TrackerNotice(t, "refine")
    slot = re.search(r"\[(\d+)\] OET (OVERSPEED|LOST TRACKING)!|OET (reloc back)\. index: (\d+)", line)
    if slot:
        if slot.group(2) == "OVERSPEED":
            return TrackerNotice(t, "overspeed", int(slot.group(1)))
        if slot.group(2):
            return TrackerNotice(t, "lost", int(slot.group(1)))
        return TrackerNotice(t, "reloc", int(slot.group(4)))
    return None
