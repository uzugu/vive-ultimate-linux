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

## 3. What this means for rooms (updated after a live check on the owner's PC)

A live check ([vivehub-windows-live-findings.md](../../../mnt/project-files/vivehub-windows-live-findings.md), project files) corrected
my first reading: the PC-side `MAP\` folder is **empty and has never been written**. The PC only keeps map *metadata*
(`Calibration.json`: creation time, eight quality values). The host tracker owns the map, and after a scan the other trackers
report "has map" again 17 to 19 seconds later without any file on the PC, so host-to-client sync happens between the trackers.

So the file-transfer path above (the library's "Map Import" job, tracker-side names `autosave0` / `FEautosave0`) is real code
but not what a normal map build uses [guess: it is for import/diagnostic/enterprise use]. Revised room-switching model:

- A **room = the host tracker's map**. Clients follow the host automatically, so we only have to put the right map on the host.
- **Export** (host to PC) has no known wire path yet. Candidates: `adb pull` of the host's map directories (Linux notes:
  `/data/lambda`, `/data/mapdata`; HTC's server bundles adb and uses it for firmware), or find a tracker-to-PC upload type
  (only logs found so far).
- **Import** (PC to host): the header/bytes/trailer transfer in section 2, then relocate, or `adb push`.
- Which tracker is host is per scan (`is host`, slot 4 here), so a room record must also store which serial was host.

## 3b. How it fits with the wizard pipe

The driver-pipes note (`re-driver-pipes.md`, section 5) lists the wizard's map commands on `TrackerNamedPipe`: start map
creation (0x21), end (0x22), last creation time (0x23), status (0x28), scan notification (0x2e/0x30). It confirms that
**map import is not a pipe command**: it is the server's own file-transfer job, which is the path decoded above. So a
room switcher needs both: the pipe-level (or our own) start/end/status calls for building a map, and this
header/bytes/trailer transfer for loading one.

Ports: no constants in the Wi-Fi object. Live check: `ViveTrackerServer.exe` listens on TCP 3680, 8053, 9005, 9527, 15680 and
UDP 9005 (only 15680 is named in a log). Likely: UDP 9005 = poses, one TCP port = time sync, one = file transfer; not yet
matched. Match them by logging which port the tracker connects to during a transfer.

## 4. Test plan for hardware (smallest steps first)

0. ~~List the server's listening ports~~ (done, see section 3b).
1. ~~Look in the PC `MAP` folder after a map build~~ (done: empty). Next: with one tracker plugged in by USB-C and `adb devices` working, run `python3 python/tools/vut_rooms.py check` to see whether the tracker's map directories exist and are readable.
2. Run VIVE Hub's own "map import" if the UI exposes one and capture the TCP stream (Wireshark); compare to the packets above.
3. Only then try our sender, on a spare tracker, with a copy of a known-good map.
