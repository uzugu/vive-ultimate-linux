"""Map-building state machine: the equivalent of VIVE Hub's room-setup wizard, without any UI or I/O.

Phases (docs/mapbuild.md section 2, read off the live timeline of one real build):

    IDLE -> STARTING -> SCANNING -> REVIEW -> SAVING -> SYNCING -> DONE        (CANCELLED / FAILED from any active phase)

* STARTING: start commands sent to the host; waits for the host to report "scanning" (tracking status 7).
* SCANNING: the user walks the room. The app notifies scan stages 0..3 (wizard "Map scan notification, type N").
* REVIEW: stage 3 sent and the host answered with its refine event; quality can be shown, the user may finish or rescan.
* SAVING: end command sent; waits for the host to report `has map` again (about 6 s in the live run).
* SYNCING: the other trackers copy the map over tracker Wi-Fi (17 to 19 s after the host in the live run).
* DONE: every connected tracker reports `has map`.

Time comes from the events (or `tick(now)`), so a recorded log can be replayed deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from .commands import DEFAULT_COMMANDS, CommandTable
from .records import (
    TRACKING_HOST_SCANNING,
    Event,
    ServiceStatus,
    TrackerNotice,
    TrackerRecord,
    WizardCommand,
)


class Phase(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    SCANNING = "scanning"
    REVIEW = "review"
    SAVING = "saving"
    SYNCING = "syncing"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def active(self) -> bool:
        return self in (Phase.STARTING, Phase.SCANNING, Phase.REVIEW, Phase.SAVING, Phase.SYNCING)


class Link(Protocol):
    """Carries one ASCII command to one tracker slot. The real implementation is the dongle (or Wi-Fi) transport."""

    def send(self, slot: int, command: str) -> None: ...


class LinkUnavailable(RuntimeError):
    """Raised by links that have no transport yet."""


class UnavailableLink:
    def send(self, slot: int, command: str) -> None:
        raise LinkUnavailable("no transport to the trackers is wired up yet (docs/mapbuild.md, Open)")


@dataclass
class RecordingLink:
    """Collects what would be sent; used for dry runs and tests."""

    sent: list[tuple[int, str]] = field(default_factory=list)

    def send(self, slot: int, command: str) -> None:
        self.sent.append((slot, command))


@dataclass
class Timeouts:
    start_s: float = 20.0  # host must report scanning
    save_s: float = 60.0  # host must report has_map again after the end command (live: ~6 s)
    sync_s: float = 120.0  # clients must follow (live: 17 to 19 s after the host)


STAGE_NAMES = ("started", "low scan", "walls", "finish")  # types 0..3; the labels are guesses from timing


@dataclass(frozen=True)
class Progress:
    phase: Phase
    host_slot: int | None
    scan_stage: int | None
    warnings: int  # "moving too fast" events
    elapsed_s: float
    pending_clients: tuple[int, ...]
    message: str
    can_finish: bool
    refine_ready: bool


class MapError(RuntimeError):
    pass


class MapBuildSession:
    def __init__(self, link: Link | None = None, commands: CommandTable = DEFAULT_COMMANDS, timeouts: Timeouts | None = None):
        commands.validate()
        self._link: Link = link or UnavailableLink()
        self._cmd, self._timeouts = commands, timeouts or Timeouts()
        self.phase = Phase.IDLE
        self.host_slot: int | None = None
        self.scan_stage: int | None = None
        self.refine_ready = False
        self.warnings = 0
        self.message = "ready"
        self._trackers: dict[int, TrackerRecord] = {}
        self._t0 = 0.0
        self._phase_t = 0.0
        self._now = 0.0
        self._host_scanning = False
        self._host_has_map = False
        self.log: list[str] = []

    # -- user actions -------------------------------------------------------------------------------------
    def start(self, host_slot: int, now: float, country: str = "") -> None:
        if self.phase.active:
            raise MapError(f"a map build is already running ({self.phase.value})")
        try:
            commands = self._cmd.start_commands(country)
        except ValueError as exc:
            raise MapError(str(exc)) from exc
        self._reset(now)
        self.host_slot = host_slot
        self._send_all(host_slot, commands)
        self._set(Phase.STARTING, "waiting for the host tracker to start scanning", now)

    def notify_scan(self, stage: int, now: float) -> None:
        """Tell the host which scan stage the user reached (0..3). Stage 3 asks it to refine the map."""
        if self.phase not in (Phase.SCANNING, Phase.REVIEW):
            raise MapError(f"cannot notify a scan stage while {self.phase.value}")
        if not 0 <= stage <= 3:
            raise ValueError("scan stage must be 0..3")
        if self.host_slot is not None and stage < len(self._cmd.scan_events):
            self._send_all(self.host_slot, (self._cmd.scan_events[stage],))
        self.scan_stage = stage
        self.refine_ready = False if stage < 3 else self.refine_ready
        self._now = now

    def finish(self, now: float) -> None:
        """Save the map (wizard "End map creation")."""
        if self.phase not in (Phase.SCANNING, Phase.REVIEW):
            raise MapError(f"cannot finish while {self.phase.value}")
        assert self.host_slot is not None
        self._host_has_map = False
        self._send_all(self.host_slot, self._cmd.end)
        self._set(Phase.SAVING, "saving the map on the host tracker", now)

    def cancel(self, now: float) -> None:
        if not self.phase.active:
            raise MapError(f"nothing to cancel ({self.phase.value})")
        assert self.host_slot is not None
        self._send_all(self.host_slot, self._cmd.cancel)
        note = "" if self._cmd.cancel else " (HTC's Hub sends nothing to the tracker on cancel either, so the host tracker was not told)"
        self._set(Phase.CANCELLED, "cancelled" + note, now)

    # -- inputs -------------------------------------------------------------------------------------------
    def feed(self, event: Event) -> None:
        self._now = max(self._now, event.t)
        if isinstance(event, TrackerRecord):
            self._on_record(event)
        elif isinstance(event, TrackerNotice):
            self._on_notice(event)
        elif isinstance(event, WizardCommand):
            self._on_wizard(event)
        elif isinstance(event, ServiceStatus):
            pass  # scan status is not a map-build signal: it already reads 1 before a build starts (live log)
        self.tick(event.t)

    def tick(self, now: float) -> None:
        self._now = max(self._now, now)
        waited = self._now - self._phase_t
        if self.phase is Phase.STARTING and waited > self._timeouts.start_s:
            self._set(Phase.FAILED, "the host tracker never started scanning; check it is on and in range", self._now)
        elif self.phase is Phase.SAVING and waited > self._timeouts.save_s:
            self._set(Phase.FAILED, "the host tracker did not confirm the saved map", self._now)
        elif self.phase is Phase.SYNCING and waited > self._timeouts.sync_s:
            self._set(Phase.FAILED, f"trackers {list(self._pending_clients())} did not receive the map", self._now)

    def progress(self) -> Progress:
        return Progress(
            phase=self.phase,
            host_slot=self.host_slot,
            scan_stage=self.scan_stage,
            warnings=self.warnings,
            elapsed_s=max(0.0, self._now - self._t0) if self.phase is not Phase.IDLE else 0.0,
            pending_clients=self._pending_clients() if self.phase in (Phase.SAVING, Phase.SYNCING) else (),
            message=self.message,
            can_finish=self.phase in (Phase.SCANNING, Phase.REVIEW),
            refine_ready=self.refine_ready,
        )

    # -- internals ----------------------------------------------------------------------------------------
    def _reset(self, now: float) -> None:
        self.scan_stage, self.refine_ready, self.warnings = None, False, 0
        self._host_scanning = self._host_has_map = False
        self._t0 = self._phase_t = self._now = now
        self.log.clear()

    def _send_all(self, slot: int, commands: tuple[str, ...]) -> None:
        for command in commands:
            self._link.send(slot, command)
            self.log.append(f"send slot {slot}: {command}")

    def _set(self, phase: Phase, message: str, now: float) -> None:
        self.phase, self.message, self._phase_t = phase, message, now
        self.log.append(f"{phase.value}: {message}")

    def _pending_clients(self) -> tuple[int, ...]:
        return tuple(sorted(s for s, r in self._trackers.items() if r.connected and s != self.host_slot and not r.has_map))

    def _on_record(self, r: TrackerRecord) -> None:
        self._trackers[r.slot] = r
        if self.host_slot is None and r.is_host and self.phase.active:
            self.host_slot = r.slot  # a build another program started: learn the host from the records
        if r.slot == self.host_slot:
            self._on_host(r)
        elif self.phase is Phase.SYNCING and not self._pending_clients():
            self._set(Phase.DONE, "map saved and shared with all trackers", r.t)

    def _on_host(self, r: TrackerRecord) -> None:
        if r.tracking_status == TRACKING_HOST_SCANNING and not r.has_map:
            self._host_scanning = True
            if self.phase is Phase.STARTING:
                self._set(Phase.SCANNING, "scanning: walk the room slowly", r.t)
        if self.phase is Phase.SAVING and r.has_map:
            self._host_has_map = True
            self._set(Phase.SYNCING, "host saved the map; sharing it with the other trackers", r.t)
            if not self._pending_clients():
                self._set(Phase.DONE, "map saved", r.t)

    def _on_notice(self, n: TrackerNotice) -> None:
        if n.kind == "overspeed" and self.phase in (Phase.SCANNING, Phase.REVIEW):
            self.warnings += 1
        elif n.kind == "refine" and self.phase is Phase.SCANNING:
            self.refine_ready = True
            self._set(Phase.REVIEW, "scan complete: review the quality, then save", n.t)
        elif n.kind == "refine":
            self.refine_ready = True

    def _on_wizard(self, c: WizardCommand) -> None:
        """Commands another program (HTC's wizard) sent: lets a replay or a passive monitor follow a build we did not start."""
        if c.kind == "start" and self.phase is Phase.IDLE:
            self.host_slot = next((s for s, r in self._trackers.items() if r.is_host), None)
            self._reset(c.t)
            self._set(Phase.STARTING, "map build started by another program", c.t)
        elif c.kind == "scan" and c.stage is not None and self.phase in (Phase.STARTING, Phase.SCANNING, Phase.REVIEW):
            self.scan_stage = c.stage
        elif c.kind == "end" and self.phase in (Phase.SCANNING, Phase.REVIEW, Phase.STARTING):
            self._host_has_map = False
            self._set(Phase.SAVING, "saving the map on the host tracker", c.t)
