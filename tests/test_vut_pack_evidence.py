import io
import json
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "tools"))
import vut_pack_evidence as evidence


def make_archive(path, entries):
    with tarfile.open(path, "w:gz") as archive:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def test_counts_metadata_without_returning_private_lines(tmp_path):
    path = tmp_path / "logs.tgz"
    logs = (
        b"private-user private-network [FilePackManager::RemoveFile] secret\n"
        b"[#22] filesize=502, mtu=1048576 outputfullname=/data/lambda/0/general_map/file_pack_info_123_8.json\n"
        b"[#22] filesize=221, mtu=1048576 outputfullname=/data/lambda/0/ed/file_pack_info_124_8.json\n"
        b'file_pack_info {"private-key": "private-value"}\n'
    )
    make_archive(path, [
        ("data/hdlog/sys_log/current/log.txt.01", logs),
        ("data/hdlog/mapdata/map_1.db", b"private image bytes"),
        ("data/lambda/0/general_map/file_pack_info_123_8.json", b"private metadata"),
    ])
    before = path.read_bytes()
    result = evidence.summarize(path)
    assert result["archive_members"] == 3
    assert result["text_logs_scanned"] == 1
    assert result["pack_metadata_members"] == 1
    assert result["metadata_receive_log_sizes"]["general_map"] == {502: 1}
    assert result["metadata_receive_log_sizes"]["ed"] == {221: 1}
    assert result["pack_related_lines_with_json_keys"] == 1
    assert result["file_pack_function_log_counts"] == {"RemoveFile": 1}
    assert "private" not in json.dumps(result)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_oversized_logs_and_non_logs_not_read(tmp_path, monkeypatch):
    path = tmp_path / "logs.tgz"
    make_archive(path, [
        ("data/hdlog/tracking_log/slam.log.1", b"x" * 10),
        ("data/hdlog/tracking_log/debug.csv", b"file_pack_info"),
        ("data/hdlog/mapdata/general.db", b"file_pack_info"),
    ])
    monkeypatch.setattr(evidence, "MAX_LOG_BYTES", 5)
    result = evidence.summarize(path)
    assert result["text_logs_scanned"] == 0
    assert result["oversized_text_logs_skipped"] == 1


def test_counts_occurrences_not_unique_transfers(tmp_path):
    path = tmp_path / "logs.tgz"
    line = b"filesize=243 mtu=1048576 outputfullname=/data/lambda/0/gravity_info/file_pack_info_1_8.json\n"
    make_archive(path, [("data/hdlog/tracking_log_backup/slam.log.16", line * 2)])
    result = evidence.summarize(path)
    assert result["metadata_receive_log_sizes"]["gravity_info"] == {243: 2}
