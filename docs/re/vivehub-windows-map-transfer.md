# Map creation and file transfer in HTC's tracker library (static analysis)

Source: `vive_tracker_driver.dll` 1.0.7.98 from VIVE Hub for Windows (Ultimate Tracker service 1.2.7). Method: a small
pure-static tool, [`tools/re/xref.py`](../../tools/re/xref.py) (pefile + capstone), finds the code that loads each log
string and disassembles that function. Nothing was executed. **Confidence tags:** `[code]` = read directly from the
instructions; `[guess]` = our interpretation. Companion to [vivehub-windows-notes.md](vivehub-windows-notes.md).

## 1. Starting a map build (`TrackerOnDongle::CreateMap`) [code]

The dongle-side path sends three plain ASCII commands to the tracker, in this order, each logged as "Send (%s) to device":

1. `FW2` ("Fail to enable FW2 mode")
2. set the Wi-Fi country code (a separate call; "Fail to set country code")
3. `ATM20` ("Fail to enable ATM mode") = host/SLAM mapping mode

`EndCreateMap` and `SendMapScanEvent` are separate functions with their own commands (not decoded yet). Matches the
Linux `tracker_server` log "host map-mode AT sequence sent (ATM20)" and pyvut's tracking-mode 20.

## 2. Sending a file to a tracker (`TrackerWifi::StartFileTransfer` and `TrackerOnWifi::StartFileTransfer`)

Before the transfer the library puts the tracker in the transfer state with `ATM51` followed by `FW2` (and `FW0` to
leave it), unless it is already in mode 51 ("skip setting mode 51!") [code]. Then, over the tracker's existing TCP
connection to the PC [code]:

| Step | What | Detail |
|---|---|---|
| 1 | **Header, message 22** (0x80 bytes) | `u16 0xB9D7`, `u16 id`, `u8 0x16`, `u32 file size` at +6, `u16 0x400` at +0xA when a flag is set, remote path at +0xC (max 0x5F chars; the library prefixes `/sdcard/`) |
| 2 | File bytes | read fully from the local file first, size re-checked ("FILESIZE MISMATCH"), then `send()` in a loop with progress reporting |
| 3 | **Trailer, message 23** (0x80 bytes) | `u16 0xB9D7`, `u16 id`, `u8 0x17`, `u32 CRC-32` at +5, `u8 1` at +0x49 [guess: "last"] |

- The CRC is **standard CRC-32 (polynomial 0xEDB88320)** over the whole file: the table is generated at runtime from that
  constant and the routine is the usual table-driven loop, so `zlib.crc32(data)` [code].
- Tracker replies seen by name: message 21 (carries the device id), message 24 (status and id; non-zero means
  "FAILED TO TRANSFER FILE"), plus 12, 14 and 15 on the log-upload side [code, semantics guess].
- A tracker-to-PC upload also exists (`StartReceiveUploadFile`, OET log from `/data/sys_log/current/ot_log_*`) [code].
- The listeners (`WaitTcpStartFileTransfer`, UDP pose receiver, time-sync client) take their **ports from the object
  they belong to** rather than from constants in the function; the port numbers still have to be found where that
  object is created (open) [code].

A tested packet builder/parser for messages 22 and 23 is in [`python/tools/vut_filetransfer.py`](../../python/tools/vut_filetransfer.py)
(`pytest tests`). It has not been run against a real tracker yet.

## 3. What a "map import" most likely is [guess]

The server labels a job "Map Import" and the library reads a "MAP BINARY" from a local file, then pushes it with the
sequence above; the tracker-side names are `autosave0` / `FEautosave0`. So a **room = the tracker's `autosave0` map
file(s) plus its large-scale flag**, and switching rooms = put the tracker in transfer state, send that room's file
(message 22, bytes, message 23), then `RelocateTracker`. What is still unknown: where the tracker keeps `autosave0`
(the Linux notes say `/data/lambda` and `/data/mapdata`), how to *download* a map from a tracker (the upload path we found
is logs only), and whether clients need the host's map or only the host does.

## 3b. How it fits with the wizard pipe

The driver-pipes note (`re-driver-pipes.md`, section 5) lists the wizard's map commands on `TrackerNamedPipe`: start map
creation (0x21), end (0x22), last creation time (0x23), status (0x28), scan notification (0x2e/0x30). It confirms that
**map import is not a pipe command**: it is the server's own file-transfer job, which is the path decoded above. So a
room switcher needs both: the pipe-level (or our own) start/end/status calls for building a map, and this
header/bytes/trailer transfer for loading one.

Ports: a scan for constant port numbers written into the Wi-Fi object found none, so they come from elsewhere (server
config or the tracker is told them at connect). Cheapest way to close this: on the PC with trackers connected run
`netstat -ano | findstr <pid of ViveTrackerServer.exe>`; the listening TCP/UDP ports are the ones.

## 4. Test plan for hardware (smallest steps first)

0. With trackers connected, run `netstat -ano` and note the ports `ViveTrackerServer.exe` listens on.
1. In VIVE Hub on Windows, build a map; look in `%ProgramData%\HTC\ViveSoftware\ViveUltimateTracker\MAP` and note which files appear.
2. Run VIVE Hub's own "map import" if the UI exposes one and capture the TCP stream (Wireshark); compare to the packets above.
3. Only then try our sender, on a spare tracker, with a copy of a known-good map.
