"""Map building (room setup) for the VIVE Ultimate Tracker. Pure logic, no I/O; see docs/mapbuild.md."""

from .commands import DEFAULT_COMMANDS, CommandTable, identify
from .quality import QualityReport, judge, read_calibration_map_setup
from .records import ServiceStatus, TrackerNotice, TrackerRecord, WizardCommand, parse_log_line
from .session import (
    Link,
    LinkUnavailable,
    MapBuildSession,
    MapError,
    Phase,
    Progress,
    RecordingLink,
    Timeouts,
    UnavailableLink,
)

__all__ = [
    "DEFAULT_COMMANDS",
    "CommandTable",
    "Link",
    "LinkUnavailable",
    "MapBuildSession",
    "MapError",
    "Phase",
    "Progress",
    "QualityReport",
    "RecordingLink",
    "ServiceStatus",
    "Timeouts",
    "TrackerNotice",
    "TrackerRecord",
    "UnavailableLink",
    "WizardCommand",
    "identify",
    "judge",
    "parse_log_line",
    "read_calibration_map_setup",
]
