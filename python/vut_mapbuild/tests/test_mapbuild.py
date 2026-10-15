import json
from pathlib import Path

import pytest

from vut_mapbuild import (
    CommandTable,
    MapBuildSession,
    MapError,
    Phase,
    RecordingLink,
    Timeouts,
    TrackerNotice,
    TrackerRecord,
    UnavailableLink,
    WizardCommand,
    judge,
    parse_log_line,
    read_calibration_map_setup,
)
from vut_mapbuild.commands import check_command
from vut_mapbuild.replay import replay

FIXTURE = Path(__file__).parent / "fixtures" / "server-map-build-20261014.txt"


def rec(t, slot, *, host=False, trk=2, has=True, mst=6, connected=True):
    return TrackerRecord(t, slot, connected, trk, 80, 0, mst, has, 0, host, -1)


# -- parsing -------------------------------------------------------------------------------------------------
def test_parse_real_lines():
    lines = FIXTURE.read_text().splitlines()
    events = [e for e in map(parse_log_line, lines) if e]
    skipped = [l for l in lines if parse_log_line(l) is None]
    assert len(skipped) == 1 and "WaitForMapRefineNotification" in skipped[0]  # duplicate of the refine line
    kinds = {type(e).__name__ for e in events}
    assert kinds == {"TrackerRecord", "ServiceStatus", "WizardCommand", "TrackerNotice"}
    stages = [e.stage for e in events if isinstance(e, WizardCommand) and e.kind == "scan"]
    assert stages == [0, 1, 2, 3]
    host = [e for e in events if isinstance(e, TrackerRecord) and e.is_host]
    assert {e.slot for e in host} == {4}


def test_parse_ignores_noise():
    assert parse_log_line("garbage") is None
    assert parse_log_line("[2026-10-14 19:10:06.709 +1 0x1 INFO OETServer::Other] [1] hello") is None


# -- replay of the real build --------------------------------------------------------------------------------
def test_replay_real_build_matches_live_timeline():
    session, changes = replay(FIXTURE.read_text().splitlines())
    assert [c[1] for c in changes] == [Phase.STARTING, Phase.SCANNING, Phase.REVIEW, Phase.SAVING, Phase.SYNCING, Phase.DONE]
    times = {phase: t for t, phase, _ in changes}
    assert 90 < times[Phase.REVIEW] < 100  # refine event ~97 s after start
    assert 5 < times[Phase.SYNCING] - times[Phase.SAVING] < 6.5  # host has_map ~5.7 s after "End map creation"
    assert 17 < times[Phase.DONE] - times[Phase.SYNCING] < 20  # clients follow 17 to 19 s later
    p = session.progress()
    assert p.phase is Phase.DONE and p.scan_stage == 3 and p.warnings == 3 and p.host_slot == 4


# -- driving a build ourselves -------------------------------------------------------------------------------
def started(link=None, **kw):
    link = link if link is not None else RecordingLink()
    s = MapBuildSession(link, **kw)
    s.feed(rec(0, 3, has=True))
    s.feed(rec(0, 4, host=True))
    s.start(4, 1.0)
    return s, link


def test_start_sends_commands_to_host_only():
    s, link = started()
    assert link.sent == [(4, "FW2"), (4, "ATM20")]
    assert s.phase is Phase.STARTING and not s.progress().can_finish


def test_full_build_flow():
    s, link = started()
    s.feed(rec(2, 4, host=True, trk=7, has=False, mst=10))
    assert s.phase is Phase.SCANNING and s.progress().can_finish
    s.feed(TrackerNotice(5, "overspeed", 4))
    s.notify_scan(3, 50)
    s.feed(TrackerNotice(51, "refine"))
    assert s.phase is Phase.REVIEW and s.progress().refine_ready
    s.feed(rec(52, 3, has=False, trk=6, mst=1))  # a client loses has_map while the host scans
    s.finish(60)
    assert link.sent[-1] == (4, "ALE") and s.phase is Phase.SAVING
    s.feed(rec(66, 4, host=True, trk=5, has=True, mst=3))
    assert s.phase is Phase.SYNCING and s.progress().pending_clients == (3,)
    s.feed(rec(85, 3, has=True))
    assert s.phase is Phase.DONE and s.progress().warnings == 1


def test_cancel_and_double_start():
    s, link = started()
    with pytest.raises(MapError):
        s.start(4, 2.0)
    s.cancel(3.0)
    assert s.phase is Phase.CANCELLED and not s.phase.active
    with pytest.raises(MapError):
        s.cancel(4.0)
    s.start(4, 10.0)  # can start again after a cancel
    assert s.phase is Phase.STARTING


def test_actions_refused_in_wrong_phase():
    s = MapBuildSession(RecordingLink())
    with pytest.raises(MapError):
        s.finish(0)
    with pytest.raises(MapError):
        s.notify_scan(0, 0)


def test_timeouts_fail_the_build():
    s, _ = started(timeouts=Timeouts(start_s=5))
    s.tick(10)
    assert s.phase is Phase.FAILED and "never started" in s.message
    s, _ = started(timeouts=Timeouts(save_s=5))
    s.feed(rec(2, 4, host=True, trk=7, has=False))
    s.finish(3)
    s.tick(9)
    assert s.phase is Phase.FAILED
    s, _ = started(timeouts=Timeouts(sync_s=5))
    s.feed(rec(2, 4, host=True, trk=7, has=False))
    s.feed(rec(2.5, 3, has=False))
    s.finish(3)
    s.feed(rec(4, 4, host=True, has=True))
    s.tick(10)
    assert s.phase is Phase.FAILED and "3" in s.message


def test_default_link_has_no_transport():
    s = MapBuildSession()
    with pytest.raises(Exception, match="no transport"):
        s.start(0, 0)
    assert isinstance(s._link, UnavailableLink)


def test_scan_event_command_is_only_sent_when_configured():
    s, link = started()
    s.feed(rec(2, 4, host=True, trk=7, has=False))
    s.notify_scan(1, 3)
    assert len(link.sent) == 2  # only the start commands: scan_event is unknown, so nothing is sent
    s2, link2 = started(commands=CommandTable(scan_event="ASE"))
    s2.feed(rec(2, 4, host=True, trk=7, has=False))
    s2.notify_scan(2, 3)
    assert link2.sent[-1] == (4, "ASE2")


# -- commands / quality --------------------------------------------------------------------------------------
def test_command_validation():
    assert check_command("ATM20") == "ATM20"
    for bad in ("", "x" * 16, "bé", "a\nb"):
        with pytest.raises(ValueError):
            check_command(bad)
    with pytest.raises(ValueError):
        CommandTable(start=("x" * 20,)).validate()


def test_quality_judge_with_real_values_and_thresholds(tmp_path):
    assert judge([85, 80, 85, 80, 75, 70, 80, 70]).verdict == "ok"
    r = judge([85, 60, 85, 80, 75, 70, 80, 70])
    assert r.verdict == "refinable" and r.weak_sides == (1,) and r.usable
    assert judge([85, 30, 85]).verdict == "poor" and not judge([85, 30, 85]).usable
    assert judge([]).verdict == "unknown"
    f = tmp_path / "Calibration.json"
    f.write_text(json.dumps({"map_setup": {"last_map_creation_time": 1791997907, "map_quality": [85, 80, 85, 80, 75, 70, 80, 70]}}))
    created, q = read_calibration_map_setup(f)
    assert created == 1791997907 and q.verdict == "ok"
