"""Map quality as the wizard judges it. Thresholds are the wizard's own `settings.json` (docs/mapbuild.md section 4).

`map_quality` in `Calibration.json` holds eight values (live: 85 80 85 80 75 70 80 70). That they are eight sides of the room
is a guess; the pass and poor thresholds are read from HTC's settings (70 and 40), the mapping to the wizard's states
(ok / refinable / poor) is a guess too.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .textio import read_text

PASS_THRESHOLD = 70
POOR_THRESHOLD = 40


@dataclass(frozen=True)
class QualityReport:
    values: tuple[int, ...]
    verdict: str  # "ok", "refinable", "poor" or "unknown"
    weak_sides: tuple[int, ...]  # indices below the pass threshold

    @property
    def usable(self) -> bool:
        return self.verdict in ("ok", "refinable")


def judge(values: list[int] | tuple[int, ...], passing: int = PASS_THRESHOLD, poor: int = POOR_THRESHOLD) -> QualityReport:
    vals = tuple(int(v) for v in values)
    if not vals:
        return QualityReport(vals, "unknown", ())
    weak = tuple(i for i, v in enumerate(vals) if v < passing)
    if not weak:
        verdict = "ok"
    elif min(vals) < poor:
        verdict = "poor"
    else:
        verdict = "refinable"
    return QualityReport(vals, verdict, weak)


def read_calibration_map_setup(path: str | Path) -> tuple[int | None, QualityReport]:
    """(last_map_creation_time, quality) from HTC's `Calibration.json` (or our mirror of it). Missing keys give unknown."""
    data = json.loads(read_text(path))
    setup = data.get("map_setup", {}) if isinstance(data, dict) else {}
    created = setup.get("last_map_creation_time")
    return (int(created) if created is not None else None), judge(setup.get("map_quality", []))
