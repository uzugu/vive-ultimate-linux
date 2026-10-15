"""Headless model for the Map tab and `vut map`: drives a `MapBuildSession` and turns it into display text.

No Tk here. The link to the trackers is injected; until the dongle transport exists the default link refuses to send, so the
tab shows a clear message instead of pretending (docs/mapbuild.md, "Open").
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from vut_mapbuild import (
    Link,
    LinkUnavailable,
    MapBuildSession,
    MapError,
    Phase,
    QualityReport,
    UnavailableLink,
    read_calibration_map_setup,
)
from vut_mapbuild.replay import replay
from vut_mapbuild.textio import read_lines

STEPS = ("Start", "Scan", "Review", "Save", "Share")
_STEP_OF = {
    Phase.IDLE: -1,
    Phase.STARTING: 0,
    Phase.SCANNING: 1,
    Phase.REVIEW: 2,
    Phase.SAVING: 3,
    Phase.SYNCING: 4,
    Phase.DONE: 5,
    Phase.CANCELLED: -1,
    Phase.FAILED: -1,
}
SCAN_HINTS = {
    None: "Hold the host tracker at the centre of the room.",
    0: "Scan low, near the floor, then work upwards.",
    1: "Walk slowly along each wall.",
    2: "Cover the remaining sides, then finish the scan.",
    3: "Scan complete. Check the quality, then save.",
}


@dataclass(frozen=True)
class MapView:
    phase: str
    message: str
    step: int  # index into STEPS of the current step, len(STEPS) when done, -1 when not running
    fraction: float  # 0..1 for a progress bar
    hint: str
    elapsed: str
    warnings: int
    can_start: bool
    can_finish: bool
    can_cancel: bool
    pending: str


class MapModel:
    def __init__(
        self,
        link: Link | None = None,
        clock: Callable[[], float] = time.monotonic,
        calibration_file: str | None = None,
    ) -> None:
        self._link = link or UnavailableLink()
        self._clock = clock
        self._calibration_file = calibration_file
        self.session = MapBuildSession(self._link)
        self.error = ""
        self.quality: QualityReport | None = None
        self.created: int | None = None
        self.reload_quality()

    def reload_quality(self) -> None:
        """Read the last map's quality from the (HTC or our) Calibration.json if there is one."""
        if not self._calibration_file:
            return
        try:
            self.created, self.quality = read_calibration_map_setup(self._calibration_file)
        except (OSError, ValueError):
            self.created, self.quality = None, None

    def start(self, host_slot: int) -> str:
        self.error = ""
        try:
            self.session = MapBuildSession(self._link)
            self.session.start(host_slot, self._clock())
        except (MapError, LinkUnavailable) as exc:
            self.error = str(exc)
            self.session = MapBuildSession(self._link)
        return self.error or "map build started"

    def finish(self) -> str:
        return self._act(lambda: self.session.finish(self._clock()))

    def cancel(self) -> str:
        return self._act(lambda: self.session.cancel(self._clock()))

    def scan_stage(self, stage: int) -> str:
        return self._act(lambda: self.session.notify_scan(stage, self._clock()))

    def _act(self, action: Callable[[], None]) -> str:
        self.error = ""
        try:
            action()
        except (MapError, LinkUnavailable) as exc:
            self.error = str(exc)
        return self.error or self.session.message

    def feed(self, event) -> None:  # type: ignore[no-untyped-def]
        self.session.feed(event)

    def tick(self) -> None:
        self.session.tick(self._clock())

    def replay_log(self, path: str) -> str:
        """Show how a recorded ViveTrackerServer log would have looked in this tab."""
        try:
            session, changes = replay(read_lines(path))
        except OSError as exc:
            self.error = str(exc)
            return self.error
        self.error = ""
        self.session = session
        return f"replayed {len(changes)} phase changes, final: {session.phase.value}"

    def view(self) -> MapView:
        p = self.session.progress()
        step = _STEP_OF[p.phase]
        fraction = {Phase.IDLE: 0.0, Phase.CANCELLED: 0.0, Phase.FAILED: 0.0}.get(p.phase, min(1.0, (step + 0.5) / len(STEPS)))
        if p.phase is Phase.DONE:
            fraction = 1.0
        hint = SCAN_HINTS.get(p.scan_stage, SCAN_HINTS[None]) if p.phase in (Phase.SCANNING, Phase.REVIEW) else ""
        running = p.phase.active
        minutes, seconds = divmod(int(p.elapsed_s), 60)
        return MapView(
            phase=p.phase.value,
            message=self.error or p.message,
            step=step,
            fraction=fraction,
            hint=hint,
            elapsed=f"{minutes}:{seconds:02d}" if p.phase is not Phase.IDLE else "",
            warnings=p.warnings,
            can_start=not running,
            can_finish=p.can_finish,
            can_cancel=running,
            pending=", ".join(str(s) for s in p.pending_clients),
        )

    def quality_text(self) -> str:
        if self.quality is None:
            return "No map recorded yet."
        weak = f" Weak sides: {', '.join(str(i + 1) for i in self.quality.weak_sides)}." if self.quality.weak_sides else ""
        return f"Last map quality: {self.quality.verdict} ({' '.join(str(v) for v in self.quality.values)}).{weak}"
