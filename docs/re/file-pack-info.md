# File-pack metadata: PC evidence audit (2026-10-15)

T1 is **partial**, not decoded. No JSON field names, checksum fields, signature
fields, or verification algorithm have been recovered. Do not implement a pack
serializer from the sizes below.

## Sources and method

**[log]** The owner's existing `hdlog-getmap2.tgz` backup was inspected locally,
without extracting members or reading the map databases or images. The archive
has 145 members and no regular member named `file_pack_info_<n>_<m>.json`.
The scanner read 44 selected text logs (current/previous system logs, tracking
logs and tracking-log backups, logcat, tombstones); no selected log exceeded its
16 MiB limit. It found 1,538 pack-related log lines, with zero lines matching a
quoted JSON key followed by a colon. That is a bounded negative result, not proof
that no schema could ever be recovered from other evidence.

**[string]** Local installed copies of `ViveTrackerServer.exe`,
`vive_tracker_driver.dll` and `UTLogRetriever.exe` were checked for the exact
ASCII and UTF-16LE strings `file_pack_info` and `FilePackManager`; no hits were
found. This is not disassembly and does not exclude indirect or constructed
strings, compression, or another binary implementing the format.

No tracker/dongle commands were issued. No binaries, raw log excerpts, map
contents, public keys, serials, MACs, network names or user IDs accompany this note.

## Transfer metadata observed

**[log]** These counts are occurrences of receive-header log lines, including
possible repeated/copied logs. They are not counts of independent transfers.
The values are transport fields, not JSON keys.

| Destination category | Metadata size in bytes | Log occurrences |
|---|---:|---:|
| `ed/` | 217 | 1 |
| `ed/` | 219 | 1 |
| `ed/` | 221 | 2 |
| `general_map/` | 502 | 2 |
| `gravity_info/` | 243 | 105 |
| `gravity_info/` | 245 | 28 |
| `gravity_info/` | 247 | 12 |

**[log]** The receive-header lines expose `filesize`, `mtu` (1048576), and
`outputfullname`. The metadata basenames follow
`file_pack_info_<pack>_<sender>.json` under
`/data/lambda/<slot>/<category>/`. The variable names in angle brackets are our
labels for the filename components, not recovered JSON fields.

**[log]** `FilePackManager::RemoveFile` occurs 110 times; clear-receive and
clear-send operations occur twice and once respectively. Previous notes' cleanup
and transfer-order observations remain consistent with this audit. See
[vivehub-map-import.md](vivehub-map-import.md) sections 3a.1 and 3a.2 for the
identity exchange and four-file map sequence.

## What remains unknown

| Question | Current evidence and confidence |
|---|---|
| JSON key names and types | Unknown; no metadata body in the archive listing or pack-related log lines. |
| Database filenames in JSON | **[guess]** plausible manifest design; not established by the four-file transfer order. |
| Per-file sizes or checksums in JSON | Unknown. The transfer trailer CRC-32 is separate evidence and does not establish a JSON checksum field. |
| Meaning of `<pack>` and `<sender>` | **[inferred]** pack/sender labels follow earlier notes; exact generation and semantics unverified. |
| Signature field or signature verification | Unknown. A public-key exchange is observed; its cryptographic purpose is not established. |
| Acceptance of a PC peer and activation of a supplied map | Unknown; no hardware test performed. |

The earlier heading "Signed packs" overstated the evidence: exchanging
`pubkey.pem` could support authentication, encryption, signing or another
protocol operation. It does not alone prove that the 502-byte JSON is signed.
Likewise, different metadata sizes do not identify keys, algorithms, or whether
one schema is shared across the three categories.

## Reproduce locally and next evidence needed

```powershell
python python/tools/vut_pack_evidence.py <local-hdlog-archive.tgz>
```

The tool emits aggregate counts and sizes only. It never extracts files, reads
map/image payloads, or emits arbitrary member names or log lines. It counts
metadata members but does not read their bodies. Synthetic tests cover privacy
of output, no extraction/archive modification, log-size limits and repeated logs.

T1 cannot meet its acceptance criteria from the reviewed evidence. The next
useful evidence is an actual metadata body with its associated file list, or the
tracker-side code that serializes/parses it. T2's passive connection capture may
only show the initial handshake: a normal file transfer is not guaranteed to
occur, and the listener never sends the replies that might advance it. Each
hardware action still needs the owner's approval under HANDOFF section 7.
Do not infer a working sender or import format from this note.
