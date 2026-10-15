# T2: bounded passive capture preparation

Status: tooling tested with synthetic loopback traffic on Windows; **tracker
capture not run**. T2 remains incomplete until connections/frames and port roles
are observed. Host-only inspection on 2026-10-15 confirmed `ViveTrackerServer`
listening on TCP 3680, 8053, 9005, 9527 and 15680. Owning a port does not establish
its protocol role. UDP was not inspected in this check.

## Approval boundary

[HANDOFF section 7](HANDOFF.md#7-how-to-work-with-the-owner) requires the owner to
approve each tracker/dongle step. The following is a reviewable plan, not a record
of commands already run. Stopping HTC's server interrupts tracking. No process
has been stopped for this preparation. Do not silently add reboot, reset, pairing,
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
