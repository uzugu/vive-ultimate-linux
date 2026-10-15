#!/usr/bin/env python3
"""Summarize file-pack evidence in a local hdlog archive without extracting files.

Only selected text logs are read. Output contains counts and numeric transfer
sizes, never log lines, paths, identifiers, JSON contents, or map/image bytes.
Counts describe log occurrences, not necessarily distinct transfers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tarfile

MAX_LOG_BYTES = 16 * 1024 * 1024
PACK_NAME = re.compile(r"file_pack_info_\d+_\d+\.json$")
LOG_NAME = re.compile(r"(?:\.log(?:\.\d+)?|log\.txt(?:\.\d+)?|logcat[^/]*\.txt)$")
RECEIVE = re.compile(
    r"filesize=(\d+).*?outputfullname=/data/lambda/\d+/"
    r"(ed|general_map|gravity_info)/file_pack_info_\d+_\d+\.json(?:\s|$)"
)
FUNCTION = re.compile(
    r"\[FilePackManager::(RemoveFile|ClearReceiveFilePackOfDevice|ClearSendFilePackOfDevice)\]"
)


def is_text_log(name: str) -> bool:
    path = "/" + name.lstrip("./")
    return bool(
        (("/sys_log/" in path or "/tracking_log/" in path or "/tracking_log_backup/" in path)
         and LOG_NAME.search(path))
        or path == "/data/hdlog/logcat.txt"
        or re.fullmatch(r"/data/hdlog/tombstones/tombstone_\d+", path)
    )


def summarize(archive: str | Path) -> dict:
    sizes = {category: Counter() for category in ("ed", "general_map", "gravity_info")}
    functions = Counter()
    report = {
        "archive_members": 0,
        "pack_metadata_members": 0,
        "text_logs_scanned": 0,
        "oversized_text_logs_skipped": 0,
        "pack_related_lines": 0,
        "pack_related_lines_with_json_keys": 0,
    }
    # Streaming iteration avoids extracting members, following links, or loading maps.
    with tarfile.open(archive, "r|*") as tar:
        for member in tar:
            report["archive_members"] += 1
            if not member.isfile():
                continue
            if PACK_NAME.fullmatch(member.name.rsplit("/", 1)[-1]):
                report["pack_metadata_members"] += 1
            if not is_text_log(member.name):
                continue
            if member.size > MAX_LOG_BYTES:
                report["oversized_text_logs_skipped"] += 1
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            with source:
                text = source.read(MAX_LOG_BYTES + 1).decode("utf-8", "replace")
            report["text_logs_scanned"] += 1
            for line in text.splitlines():
                match = RECEIVE.search(line)
                if match:
                    sizes[match[2]][int(match[1])] += 1
                functions.update(FUNCTION.findall(line))
                if "file_pack_info" in line or "FilePackManager" in line:
                    report["pack_related_lines"] += 1
                    if re.search(r'"[^"\r\n]+"\s*:', line):
                        report["pack_related_lines_with_json_keys"] += 1
    report["metadata_receive_log_sizes"] = {
        category: dict(sorted(counts.items())) for category, counts in sizes.items()
    }
    report["file_pack_function_log_counts"] = dict(sorted(functions.items()))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        result = summarize(args.archive)
    except (OSError, tarfile.TarError):
        # Do not print exception messages: they can contain private member names.
        parser.exit(1, "Could not read the local archive. Check its format and permissions.\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
