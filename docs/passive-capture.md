# T2: bounded passive capture preparation

Status: tooling tested with synthetic loopback traffic on Windows; one approved
60-second live passive capture completed with zero connections and bytes. T2
remains incomplete until connections/frames and port roles are observed. Host-only inspection on 2026-10-15 confirmed `ViveTrackerServer`
listening on TCP 3680, 8053, 9005, 9527 and 15680. Owning a port does not establish
its protocol role. UDP was not inspected in this check.

## Approval boundary

[HANDOFF section 7](HANDOFF.md#7-how-to-work-with-the-owner) requires the owner to
approve each tracker/dongle step. The commands below describe the original approved plan. The observed result and
recovery deviation are recorded at the end of this note; a new attempt needs
separate approval. Stopping HTC's server interrupts tracking. The initial tooling preparation stopped no processes; the later approved capture
and recovery did stop the host server, as recorded below. Do not silently add reboot, reset, pairing,
transfer-mode commands, firewall rules or an active sender to the test.

Use one powered tracker for an unambiguous capture. A shared capture file appends
chunks across clients and sessions without recording their boundaries. A fresh
file and one connection are required for reliable offline replay. If more than
one client connects, retain the local console log and do not interpret the raw
file as a single stream.

## Exact first capture plan (after approval)

Run from the repository root. Preserve a way to reopen VIVE Hub afterwards.
Use a fresh directory outside Git; raw captures and console logs can contain
private paths, network identifiers and room images and must stay on this PC.

```powershell
$captureDir = Join-Path $env:USERPROFILE ('Documents/VIVE-map-backups/passive-8053-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $captureDir -ErrorAction Stop | Out-Null
$hubShortcut = 'C:/ProgramData/Microsoft/Windows/Start Menu/Programs/VIVE Hub/VIVE Hub.lnk'
try {
    Stop-Process -Name ViveTrackerServer -ErrorAction Stop
    python python/tools/vut_ft_listen.py --bind 0.0.0.0 --port 8053 --duration 60 --capture (Join-Path $captureDir 'stream.bin') 2>&1 | Tee-Object -FilePath (Join-Path $captureDir 'console.txt')
} finally {
    Start-Process -FilePath $hubShortcut -WindowStyle Hidden
}
```

The listener accepts TCP connections and records received bytes; it never sends
application bytes. After 60 seconds it closes the listener and idle connections.
The listening socket reserves its port exclusively on Windows, so it refuses an
occupied port rather than sharing it with HTC's server. A firewall prompt or
blocked connection requires a separate decision; this plan changes no rules.
The `finally` block invokes the installed VIVE Hub shortcut after the capture.
Verify the server listeners and tracking recover; a launch request alone does not
prove recovery. If HTC restarts its server during capture, stop this attempt
rather than repeatedly killing it. Do not start the tracker server executable directly with guessed args.

A tracker may never connect: the control channel may need HTC's stopped server,
or a file-transfer trigger may be required. A silent capture does not disprove
port 8053's transfer role. Stop there and record the outcome; any additional
trigger or tracker action is a separate approved step.

## Offline analysis (no hardware connection)

```powershell
python python/tools/vut_ft_listen.py --replay (Join-Path $captureDir 'stream.bin')
```

Replay opens only a file, never a socket. The decoder preserves partial magic
markers across reads, resynchronizes after noise, skips known message-22 payloads
by declared length, and reports a truncated frame or payload at end of stream.
Upload-family payload layouts and other unknown messages are not decoded; do
not infer their file boundaries from this tool. The raw capture remains the local
evidence. This is not a sender, a proxy, or a metadata extractor.

For public findings record only counts, frame types, sizes, protocol roles with
confidence labels, and whether the capture ended early. Keep raw logs and bytes
local; neither a filename nor an ignore rule substitutes for reviewing a commit.


## Approved live result (2026-10-15)

**[observed on PC]** The owner approved stopping HTC's tracker server, a 60-second
passive listen on TCP 8053, and reopening VIVE Hub. The listener bound successfully,
ran to its deadline, and exited with status 0. Result: **zero connections, zero
received bytes, zero frame lines**, and no traceback. Raw capture, console output,
and a numeric summary remain in a timestamped folder under the owner's local
`Documents/VIVE-map-backups/`; no raw files or identifiers are committed.

**[observed on PC]** The tracker-server process start time fell during the capture
window, showing that HTC relaunched it before our listener finished. After the
capture and launcher invocation, HTC owned TCP 3680, 9005, 9527 and 15680, while
8053 had no listener. With our listener closed, one additional host-server restart
and launcher invocation restored **all five original TCP listeners**, including
8053. No tracker/dongle commands, active file transfers, firewall changes, pairing,
reset or reboot were performed. Live tracking itself was not independently
verified; recovery is established only at process/listening-port level.

**[inferred]** HTC's early relaunch may have attempted to bind 8053 while our
listener owned it. No direct bind-error log was found in the inspected recent
log tails, so that mechanism is not proven. The empty capture does not prove a
tracker was powered/connected or that its control channel requested a transfer.

A further attempt needs an approved plan that accounts for HTC's automatic
relaunch and identifies how the tracker is expected to initiate the connection.
Do not repeat this attempt blindly or count T2 as done: no frame layouts or new
port roles were learned. The concurrent HTC process also means this result
cannot be treated as a capture with HTC's server absent for the whole window.
